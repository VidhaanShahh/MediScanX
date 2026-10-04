"""
MediScanX — M6 ECG AI Service.

Loads the pre-trained PTB-XL ECG classification model (models/ecg/ecg_model.keras),
normalisation parameters (models/ecg/normalisation_params.npz), and per-class decision
thresholds (models/ecg/thresholds.json) as a process-level singleton.

Provides:
    - 5-class superclass prediction (NORM, MI, STTC, CD, HYP)
    - Threshold evaluation (above_threshold boolean per class)
    - Heart rate estimation from R-peaks on Lead II (P3 Algorithm A6)
    - 12-lead ECG plot rendering (SRS FR-6.2)
    - Model metadata and inference timing (SRS FR-6.4)
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
from scipy import signal as sp_signal

# Ensure Keras uses PyTorch backend
os.environ.setdefault("KERAS_BACKEND", "torch")

import torch
import keras

from app.core.exceptions import InferenceError

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────

SUPERCLASSES: list[str] = ["NORM", "MI", "STTC", "CD", "HYP"]
N_CLASSES: int = len(SUPERCLASSES)

LEAD_NAMES: list[str] = [
    "I", "II", "III", "aVR", "aVL", "aVF",
    "V1", "V2", "V3", "V4", "V5", "V6",
]
NUM_LEADS: int = len(LEAD_NAMES)
DEFAULT_FS: float = 100.0
TARGET_SAMPLES: int = 1000

MODEL_NAME = "PTB-XL-1D-CNN"
MODEL_VERSION = "v1.0-ptbxl"

# Default paths — can be overridden via ECG_MODEL_DIR or ECG_MODEL_PATH env vars
_BASE_ECG_DIR = Path(__file__).resolve().parents[4] / "models" / "ecg"
_DEFAULT_MODEL_PATH = str(_BASE_ECG_DIR / "ecg_model.keras")
_DEFAULT_NORM_PATH = str(_BASE_ECG_DIR / "normalisation_params.npz")
_DEFAULT_THRESHOLDS_PATH = str(_BASE_ECG_DIR / "thresholds.json")


# ── Data structures ──────────────────────────────────────────────

@dataclass
class ECGPredictionItem:
    """Prediction result for a single ECG superclass."""

    superclass: str
    probability: float
    threshold: float
    above_threshold: bool


@dataclass
class ECGInferenceResult:
    """Full result of running ECG analysis on one record."""

    predictions: list[ECGPredictionItem] = field(default_factory=list)
    num_classes: int = N_CLASSES
    heart_rate_bpm: Optional[float] = None
    plot_image_base64: Optional[str] = None
    inference_ms: float = 0.0
    model_name: str = MODEL_NAME
    model_version: str = MODEL_VERSION


@dataclass
class _ModelHolder:
    """Process-level singleton holding the loaded Keras model and parameters."""

    model: Optional[Any] = None
    model_path: Optional[str] = None
    mean: Optional[np.ndarray] = None
    std: Optional[np.ndarray] = None
    thresholds: Optional[dict[str, float]] = None
    load_time_ms: float = 0.0

    def is_loaded(self) -> bool:
        return self.model is not None and self.thresholds is not None


_holder = _ModelHolder()


# ── Model loading ────────────────────────────────────────────────

def load_model(
    model_path: str | None = None,
    norm_path: str | None = None,
    thresholds_path: str | None = None,
) -> Any:
    """
    Load the pre-trained Keras ECG model, normalization params, and thresholds.

    Cached as a process-level singleton. Subsequent calls return the cached
    model unless model_path differs.
    """
    m_path = (
        model_path
        or os.environ.get("ECG_MODEL_PATH")
        or _DEFAULT_MODEL_PATH
    )
    n_path = norm_path or _DEFAULT_NORM_PATH
    t_path = thresholds_path or _DEFAULT_THRESHOLDS_PATH

    # Return cached model if same path
    if _holder.is_loaded() and _holder.model_path == m_path:
        return _holder.model

    if not Path(m_path).is_file():
        raise InferenceError(
            f"ECG model checkpoint not found at {m_path}. "
            "Set ECG_MODEL_PATH env var or place ecg_model.keras in models/ecg/."
        )

    t0 = time.perf_counter()

    try:
        model = keras.saving.load_model(m_path)
    except Exception as exc:
        raise InferenceError(f"Failed to load ECG model from {m_path}: {exc}") from exc

    # Load normalisation params
    mean, std = None, None
    if Path(n_path).is_file():
        try:
            npz = np.load(n_path)
            mean = npz["mean"].squeeze().astype(np.float32)
            std = npz["std"].squeeze().astype(np.float32)
        except Exception as exc:
            logger.warning("Could not load ECG normalisation params: %s", exc)

    # Load thresholds
    thresholds: dict[str, float] = {
        "NORM": 0.44,
        "MI": 0.35,
        "STTC": 0.33,
        "CD": 0.26,
        "HYP": 0.20,
    }
    if Path(t_path).is_file():
        try:
            with open(t_path, "r", encoding="utf-8") as f:
                thresholds = json.load(f)
        except Exception as exc:
            logger.warning("Could not load ECG thresholds JSON: %s", exc)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    _holder.model = model
    _holder.model_path = m_path
    _holder.mean = mean
    _holder.std = std
    _holder.thresholds = thresholds
    _holder.load_time_ms = elapsed_ms

    logger.info(
        "ECG model loaded in %.1f ms (classes=%d, thresholds=%s)",
        elapsed_ms,
        N_CLASSES,
        thresholds,
    )

    return model


def get_model_metadata() -> dict:
    """Return metadata about the currently loaded ECG model."""
    load_model()
    return {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "architecture": "1D-CNN (4-stage Conv1D + GAP + Dense)",
        "num_classes": N_CLASSES,
        "class_names": list(SUPERCLASSES),
        "thresholds": dict(_holder.thresholds or {}),
        "checkpoint": _holder.model_path,
        "load_time_ms": round(_holder.load_time_ms, 1),
    }


def reset_model() -> None:
    """Reset the cached model (useful for unit testing)."""
    _holder.model = None
    _holder.model_path = None
    _holder.mean = None
    _holder.std = None
    _holder.thresholds = None
    _holder.load_time_ms = 0.0


# ── Heart Rate Estimation (P3 Algorithm A6) ──────────────────────

def estimate_heart_rate(
    lead_signal: np.ndarray,
    fs: float = DEFAULT_FS,
) -> float | None:
    """
    Estimate heart rate in beats per minute from R-peaks (P3 Algorithm A6).

    Parameters
    ----------
    lead_signal : 1-D ndarray of samples for Lead II (or another lead)
    fs          : sampling rate in Hz (default 100 Hz)

    Returns
    -------
    float or None : Estimated BPM, or None if fewer than 2 peaks detected.
    """
    if not isinstance(lead_signal, np.ndarray) or lead_signal.ndim != 1:
        return None
    if len(lead_signal) < int(fs):  # less than 1 second
        return None

    # Check for flat signal
    if np.std(lead_signal) < 1e-6:
        return None

    try:
        # Band-pass filter 5–15 Hz to highlight the QRS complex
        nyq = fs / 2.0
        low = max(5.0 / nyq, 1e-4)
        high = min(15.0 / nyq, 1.0 - 1e-4)
        b, a = sp_signal.butter(2, [low, high], btype="band")
        filtered = sp_signal.filtfilt(b, a, lead_signal)

        # Square the signal
        s = filtered ** 2
        max_s = np.max(s)
        if max_s <= 1e-8:
            return None

        # R-peak detection: minimum distance of 0.25 s (max 240 bpm)
        min_dist = max(int(0.25 * fs), 1)
        peaks, _ = sp_signal.find_peaks(s, height=0.3 * max_s, distance=min_dist)

        if len(peaks) < 2:
            return None

        # Differences between consecutive peaks in seconds
        gaps = np.diff(peaks) / fs
        median_gap = np.median(gaps)
        if median_gap <= 0:
            return None

        bpm = 60.0 / median_gap
        # Sanity check: physiologically plausible range (20 to 300 bpm)
        if 20.0 <= bpm <= 300.0:
            return round(float(bpm), 1)
        return None
    except Exception as exc:
        logger.warning("Heart rate estimation error: %s", exc)
        return None


# ── 12-Lead ECG Plot Rendering (SRS FR-6.2) ──────────────────────

def render_ecg_plot(
    signal: np.ndarray,
    fs: float = DEFAULT_FS,
    title: str = "12-Lead ECG (10s @ 100 Hz)",
    save_path: str | None = None,
) -> str:
    """
    Render the 12-lead ECG signal as a diagnostic plot and return base64 PNG data.

    Parameters
    ----------
    signal    : ndarray of shape (12, N) or (N, 12)
    fs        : sampling frequency in Hz
    title     : plot title
    save_path : optional file path to save the PNG image

    Returns
    -------
    str : Base64-encoded PNG image string.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if signal.ndim != 2:
        raise InferenceError(f"ECG signal must be 2D, got shape {signal.shape}")

    # Ensure shape is (12, N)
    if signal.shape[0] != NUM_LEADS and signal.shape[1] == NUM_LEADS:
        sig = signal.T
    elif signal.shape[0] == NUM_LEADS:
        sig = signal
    else:
        raise InferenceError(
            f"Expected 12 leads, got signal shape {signal.shape}"
        )

    num_samples = sig.shape[1]
    time_axis = np.arange(num_samples) / fs

    # Create 6 rows x 2 columns subplot grid (I, aVR, II, aVL, III, aVF, V1, V4, V2, V5, V3, V6)
    # Standard ECG column pairing: Limb leads on left, precordial on right
    lead_order = [
        (0, "I"), (6, "V1"),
        (1, "II"), (7, "V2"),
        (2, "III"), (8, "V3"),
        (3, "aVR"), (9, "V4"),
        (4, "aVL"), (10, "V5"),
        (5, "aVF"), (11, "V6"),
    ]

    fig, axes = plt.subplots(6, 2, figsize=(12, 8), sharex=True)
    fig.suptitle(title, fontsize=12, fontweight="bold", y=0.98)

    for idx, (lead_idx, name) in enumerate(lead_order):
        row = idx // 2
        col = idx % 2
        ax = axes[row, col]
        lead_data = sig[lead_idx]

        ax.plot(time_axis, lead_data, color="#0b2545", lw=0.8)
        ax.set_ylabel(name, fontsize=10, fontweight="bold", rotation=0, labelpad=15)
        ax.grid(True, which="both", color="#ffcccc", linestyle="-", linewidth=0.5, alpha=0.7)
        ax.tick_params(labelsize=8)

        if row == 5:
            ax.set_xlabel("Time (s)", fontsize=9)

    plt.tight_layout(rect=[0, 0, 1, 0.96])

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)

    img_bytes = buf.getvalue()

    if save_path:
        try:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).write_bytes(img_bytes)
        except Exception as exc:
            logger.warning("Could not save ECG plot to %s: %s", save_path, exc)

    return base64.b64encode(img_bytes).decode("utf-8")


# ── Inference Pipeline ───────────────────────────────────────────

def predict_ecg(
    signal: np.ndarray,
    fs: float = DEFAULT_FS,
    compute_hr: bool = True,
    generate_plot: bool = True,
) -> ECGInferenceResult:
    """
    Run ECG inference on a 12-lead signal.

    Parameters
    ----------
    signal        : ndarray of shape (12, 1000) or (1000, 12).
    fs            : original sampling rate (default 100 Hz).
    compute_hr    : whether to compute heart rate from R-peaks.
    generate_plot : whether to generate base64 12-lead diagnostic plot.

    Returns
    -------
    ECGInferenceResult
        Contains 5 superclass predictions with probabilities and threshold
        flags, estimated heart rate, base64 plot, and inference timing.
    """
    if not isinstance(signal, np.ndarray):
        raise InferenceError(
            f"Expected numpy ndarray, got {type(signal).__name__}"
        )

    if signal.ndim != 2:
        raise InferenceError(
            f"Expected 2D array, got {signal.ndim}D array with shape {signal.shape}"
        )

    # Convert shape to (1000, 12) if needed
    if signal.shape == (NUM_LEADS, TARGET_SAMPLES):
        sig_leads_first = signal
        x = signal.T.astype(np.float32)  # (1000, 12)
    elif signal.shape == (TARGET_SAMPLES, NUM_LEADS):
        sig_leads_first = signal.T
        x = signal.astype(np.float32)
    else:
        raise InferenceError(
            f"Expected signal shape (12, 1000) or (1000, 12), got {signal.shape}"
        )

    model = load_model()
    thresholds = _holder.thresholds or {c: 0.5 for c in SUPERCLASSES}

    # Normalize if dataset normalization params available and signal not already standardized
    # If signal is already per-lead standardized (mean ~ 0, std ~ 1), model accepts it directly.
    # If signal is in raw mV, apply dataset mean and std.
    if _holder.mean is not None and _holder.std is not None:
        # Check if signal is in raw millivolts (e.g. std < 0.5 or > 2.0)
        lead_stds = np.std(x, axis=0)
        is_unit_std = np.all(np.abs(lead_stds - 1.0) < 0.2)
        if not is_unit_std:
            x = (x - _holder.mean) / _holder.std

    t0 = time.perf_counter()

    # Convert to PyTorch tensor with batch dimension (1, 1000, 12)
    tensor = torch.from_numpy(x[np.newaxis, ...]).float()

    with torch.no_grad():
        out = model(tensor, training=False)

    elapsed_ms = (time.perf_counter() - t0) * 1000
    probs = out.squeeze(0).cpu().numpy()  # shape (5,)

    # Build predictions
    predictions = [
        ECGPredictionItem(
            superclass=sc,
            probability=round(float(probs[i]), 6),
            threshold=thresholds.get(sc, 0.5),
            above_threshold=bool(probs[i] >= thresholds.get(sc, 0.5)),
        )
        for i, sc in enumerate(SUPERCLASSES)
    ]

    # Heart rate estimation (Lead II is index 1)
    hr_bpm = None
    if compute_hr:
        lead_ii = sig_leads_first[1]
        hr_bpm = estimate_heart_rate(lead_ii, fs=fs)
        if hr_bpm is None:
            # Fallback to Lead I or Lead V5
            hr_bpm = estimate_heart_rate(sig_leads_first[0], fs=fs) or estimate_heart_rate(sig_leads_first[10], fs=fs)

    # 12-lead plot generation
    plot_b64 = None
    if generate_plot:
        try:
            plot_b64 = render_ecg_plot(sig_leads_first, fs=fs)
        except Exception as exc:
            logger.warning("Could not render ECG plot: %s", exc)

    return ECGInferenceResult(
        predictions=predictions,
        num_classes=N_CLASSES,
        heart_rate_bpm=hr_bpm,
        plot_image_base64=plot_b64,
        inference_ms=round(elapsed_ms, 2),
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
    )
