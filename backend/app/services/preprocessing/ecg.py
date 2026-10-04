"""
MediScanX — M4 ECG preprocessing service.

Implements Algorithm A3 from P3 exactly:

    1. Accept 12-lead signal
    2. Resample to 100 Hz target sampling rate
    3. 0.5–40 Hz 4th-order Butterworth band-pass filter  (scipy.signal.filtfilt)
    4. Per-lead normalisation  (zero mean, unit std)
    5. Pad / trim to 10 s  → 12 × 1000 output
    6. Flag flat or noisy leads
"""

import io
from pathlib import Path

import numpy as np
from scipy import signal as sp_signal

from app.core.exceptions import PreprocessingError

TARGET_FS = 100        # Hz
TARGET_DURATION = 10   # seconds
TARGET_SAMPLES = TARGET_FS * TARGET_DURATION  # 1000
NUM_LEADS = 12

# Butterworth filter parameters
BUTTER_ORDER = 4
BAND_LOW = 0.5   # Hz
BAND_HIGH = 40.0  # Hz

# Quality thresholds
FLAT_STD_THRESHOLD = 1e-6
NOISE_HF_RATIO_THRESHOLD = 0.5  # ratio of power above 40 Hz


def preprocess_ecg(
    signal_data: np.ndarray,
    fs: float = TARGET_FS,
) -> tuple[np.ndarray, dict[str, str]]:
    """
    Preprocess a 12-lead ECG signal for the 1D-CNN model.

    Parameters
    ----------
    signal_data : ndarray of shape (N, 12)  — samples × leads
    fs          : original sampling rate in Hz

    Returns
    -------
    (output, lead_flags)
        output     — float32 ndarray of shape (12, 1000)
        lead_flags — dict mapping lead name → quality note (empty if OK)
    """
    lead_names = [
        "I", "II", "III", "aVR", "aVL", "aVF",
        "V1", "V2", "V3", "V4", "V5", "V6",
    ]

    if signal_data.ndim != 2:
        raise PreprocessingError(
            f"ECG signal must be 2-D (samples × leads), got shape {signal_data.shape}."
        )
    if signal_data.shape[1] != NUM_LEADS:
        raise PreprocessingError(
            f"ECG must have exactly 12 leads, but got {signal_data.shape[1]}."
        )

    sig = signal_data.astype(np.float64)

    # ── 1. Resample to 100 Hz if needed ──────────────────────────
    if fs != TARGET_FS:
        num_target = int(round(sig.shape[0] * TARGET_FS / fs))
        sig = sp_signal.resample(sig, num_target, axis=0)

    # ── 2. Band-pass filter (0.5–40 Hz, Butterworth, zero-phase) ─
    nyq = TARGET_FS / 2.0
    low = BAND_LOW / nyq
    high = BAND_HIGH / nyq

    # Clamp to valid range (0, 1) exclusive
    low = max(low, 1e-5)
    high = min(high, 1.0 - 1e-5)

    b, a = sp_signal.butter(BUTTER_ORDER, [low, high], btype="band")

    lead_flags: dict[str, str] = {}

    for i in range(NUM_LEADS):
        lead = sig[:, i]
        name = lead_names[i]

        # Apply zero-phase filter
        try:
            sig[:, i] = sp_signal.filtfilt(b, a, lead)
        except Exception:
            lead_flags[name] = "filter_failed"
            continue

        # ── 3. Quality checks ────────────────────────────────────
        std = np.std(sig[:, i])
        if std < FLAT_STD_THRESHOLD:
            lead_flags[name] = "flat"
        elif _is_noisy(sig[:, i], TARGET_FS):
            lead_flags[name] = "noisy"

        # ── 4. Per-lead normalisation ────────────────────────────
        mean = np.mean(sig[:, i])
        std = np.std(sig[:, i])
        if std > FLAT_STD_THRESHOLD:
            sig[:, i] = (sig[:, i] - mean) / std
        else:
            sig[:, i] = 0.0

    # ── 5. Pad / trim to exactly 1000 samples ────────────────────
    current = sig.shape[0]
    if current > TARGET_SAMPLES:
        sig = sig[:TARGET_SAMPLES, :]
    elif current < TARGET_SAMPLES:
        pad = np.zeros((TARGET_SAMPLES - current, NUM_LEADS), dtype=np.float64)
        sig = np.concatenate([sig, pad], axis=0)

    # Transpose to (12, 1000) — leads × samples, as expected by the CNN
    output = sig.T.astype(np.float32)

    return output, lead_flags


def load_ecg_csv(file_bytes: bytes) -> tuple[np.ndarray, float]:
    """
    Load a CSV ECG file.  Returns (signal, assumed_fs).

    The CSV is expected to have 12 numeric columns (one per lead).
    Sampling rate is assumed to be 500 Hz if not otherwise specified.
    """
    import pandas as pd

    try:
        df = pd.read_csv(io.BytesIO(file_bytes))
    except Exception as exc:
        raise PreprocessingError(f"Cannot parse ECG CSV: {exc}")

    if df.shape[1] != NUM_LEADS:
        raise PreprocessingError(
            f"ECG CSV must have 12 columns, but has {df.shape[1]}."
        )

    sig = df.values.astype(np.float64)

    # Replace NaN with 0
    sig = np.nan_to_num(sig, nan=0.0)

    return sig, 500.0  # default assumption


def load_ecg_wfdb(record_path: str) -> tuple[np.ndarray, float]:
    """Load a WFDB record.  Returns (signal, fs)."""
    try:
        import wfdb
    except ImportError:
        raise PreprocessingError("WFDB support requires the wfdb package.")

    try:
        record = wfdb.rdrecord(record_path)
    except Exception as exc:
        raise PreprocessingError(f"Cannot read WFDB record: {exc}")

    if record.n_sig != NUM_LEADS:
        raise PreprocessingError(
            f"ECG must have 12 leads, but found {record.n_sig}."
        )

    return record.p_signal.astype(np.float64), float(record.fs)


# ── Internal helpers ─────────────────────────────────────────────

def _is_noisy(lead: np.ndarray, fs: float) -> bool:
    """Estimate if a lead has excessive high-frequency content."""
    freqs, psd = sp_signal.welch(lead, fs=fs, nperseg=min(256, len(lead)))
    total_power = np.sum(psd)
    if total_power < 1e-12:
        return False
    hf_mask = freqs > 40.0
    hf_power = np.sum(psd[hf_mask])
    return (hf_power / total_power) > NOISE_HF_RATIO_THRESHOLD
