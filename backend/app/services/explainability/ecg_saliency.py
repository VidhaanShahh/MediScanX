"""
MediScanX — M8 ECG Saliency Explainability Service.

Computes input-gradient saliency for the ACTUAL M6 ECG model using
autograd.  The saliency map visualizes input sensitivity — which
temporal/lead regions of the ECG input most influence the selected
model output.

It is NOT proof of clinical causality.

Algorithm reference
-------------------
P3 § 9  "A8: Explainability"

Saliency method:
    saliency = abs( d(target_output) / d(input) )

Default target:
    risk = 1 - P(NORM)   (i.e. gradient of all non-NORM outputs)
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import torch

from app.services.ecg.ecg_service import (
    load_model as load_ecg_model,
    _holder as ecg_holder,
    SUPERCLASSES,
    N_CLASSES,
    NUM_LEADS,
    TARGET_SAMPLES,
)

logger = logging.getLogger(__name__)


def generate_ecg_saliency(
    preprocessed_signal: np.ndarray,
    target_class: Optional[str] = None,
) -> dict:
    """
    Compute input-gradient saliency for the M6 ECG model.

    Parameters
    ----------
    preprocessed_signal : np.ndarray
        Preprocessed ECG signal of shape ``(12, 1000)`` or ``(1000, 12)``
        as produced by the M4 ECG preprocessing pipeline.
    target_class : str or None
        One of the 5 PTB-XL superclasses (NORM, MI, STTC, CD, HYP).
        If None, the default target is ``risk = 1 - P(NORM)``.

    Returns
    -------
    dict with keys:
        saliency       : np.ndarray of shape (1000, 12), values in [0, 1]
        target_class   : str — the class or "risk" used for saliency
        probabilities  : dict[str, float] — all 5 superclass probabilities
        model_name     : str
        model_version  : str

    Raises
    ------
    ValueError
        If target_class is supplied but is not one of the 5 superclasses.
    """
    # ── Validate target class ────────────────────────────────────
    if target_class is not None and target_class not in SUPERCLASSES:
        raise ValueError(
            f"Invalid target class '{target_class}'. "
            f"Must be one of: {SUPERCLASSES}"
        )

    # ── Prepare signal in (1000, 12) format ──────────────────────
    sig = preprocessed_signal.copy().astype(np.float32)
    if sig.shape == (NUM_LEADS, TARGET_SAMPLES):
        sig = sig.T  # → (1000, 12)
    elif sig.shape != (TARGET_SAMPLES, NUM_LEADS):
        raise ValueError(
            f"Expected signal shape (12, 1000) or (1000, 12), got {sig.shape}"
        )

    # ── Load model (reuses singleton) ────────────────────────────
    model = load_ecg_model()

    # ── Apply normalisation if available (mirrors predict_ecg) ───
    if ecg_holder.mean is not None and ecg_holder.std is not None:
        lead_stds = np.std(sig, axis=0)
        is_unit_std = np.all(np.abs(lead_stds - 1.0) < 0.2)
        if not is_unit_std:
            sig = (sig - ecg_holder.mean) / ecg_holder.std

    # ── Create input tensor with gradient tracking ───────────────
    # Model expects (batch, 1000, 12)
    input_tensor = torch.from_numpy(sig[np.newaxis, ...]).float()
    input_tensor.requires_grad_(True)

    # ── Forward pass ─────────────────────────────────────────────
    output = model(input_tensor, training=False)  # (1, 5)
    probs = output.squeeze(0).detach().cpu().numpy()  # (5,)

    # ── Determine target ─────────────────────────────────────────
    if target_class is None:
        # Default: risk = 1 - P(NORM)
        # Gradient of risk = gradient of (1 - output[0]) = -gradient of output[0]
        # We want saliency = abs(gradient), so direction doesn't matter
        # Equivalently: gradient of sum of non-NORM outputs
        norm_idx = SUPERCLASSES.index("NORM")
        target_value = 1.0 - output[0, norm_idx]
        target_label = "risk_1_minus_NORM"
    else:
        target_idx = SUPERCLASSES.index(target_class)
        target_value = output[0, target_idx]
        target_label = target_class

    # ── Backward pass ────────────────────────────────────────────
    target_value.backward()

    # ── Extract gradient saliency ────────────────────────────────
    if input_tensor.grad is not None:
        saliency = input_tensor.grad.squeeze(0).detach().cpu().numpy()  # (1000, 12)
        saliency = np.abs(saliency)

        # ── Safe normalisation to [0, 1] ─────────────────────────
        s_min = saliency.min()
        s_max = saliency.max()
        if s_max - s_min > 1e-8:
            saliency = (saliency - s_min) / (s_max - s_min)
        else:
            saliency = np.zeros_like(saliency, dtype=np.float32)

        # Ensure finite values
        saliency = np.nan_to_num(saliency, nan=0.0, posinf=1.0, neginf=0.0)
        saliency = saliency.astype(np.float32)
    else:
        logger.warning("No gradients available for ECG saliency; returning zeros.")
        saliency = np.zeros((TARGET_SAMPLES, NUM_LEADS), dtype=np.float32)

    # Build probabilities dict
    probabilities = {
        SUPERCLASSES[i]: float(probs[i]) for i in range(N_CLASSES)
    }

    return {
        "saliency": saliency,
        "target_class": target_label,
        "probabilities": probabilities,
        "model_name": "PTB-XL-1D-CNN",
        "model_version": "v1.0-ptbxl",
    }


def render_ecg_saliency(
    signal: np.ndarray,
    saliency: np.ndarray,
    fs: float = 100.0,
) -> bytes:
    """
    Render ECG signal with saliency overlay as a 12-lead diagnostic plot.

    Parameters
    ----------
    signal    : np.ndarray of shape (12, 1000) or (1000, 12)
    saliency  : np.ndarray of shape (1000, 12), values in [0, 1]
    fs        : sampling frequency in Hz

    Returns
    -------
    bytes : PNG image bytes of the saliency-overlaid ECG plot.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.collections as mcoll
    import io

    # Ensure signal shape is (12, N)
    if signal.shape[0] != NUM_LEADS and signal.shape[1] == NUM_LEADS:
        sig = signal.T
    elif signal.shape[0] == NUM_LEADS:
        sig = signal
    else:
        raise ValueError(f"Expected 12 leads, got signal shape {signal.shape}")

    # Ensure saliency shape is (1000, 12)
    if saliency.shape == (NUM_LEADS, TARGET_SAMPLES):
        sal = saliency.T
    else:
        sal = saliency

    num_samples = sig.shape[1]
    time_axis = np.arange(num_samples) / fs

    lead_names = [
        "I", "II", "III", "aVR", "aVL", "aVF",
        "V1", "V2", "V3", "V4", "V5", "V6",
    ]

    fig, axes = plt.subplots(6, 2, figsize=(14, 10), sharex=True)
    fig.suptitle(
        "ECG Saliency Map — Input Gradient Sensitivity",
        fontsize=12, fontweight="bold", y=0.98,
    )

    lead_order = [
        (0, "I"), (6, "V1"),
        (1, "II"), (7, "V2"),
        (2, "III"), (8, "V3"),
        (3, "aVR"), (9, "V4"),
        (4, "aVL"), (10, "V5"),
        (5, "aVF"), (11, "V6"),
    ]

    for idx, (lead_idx, name) in enumerate(lead_order):
        row = idx // 2
        col = idx % 2
        ax = axes[row, col]

        lead_data = sig[lead_idx]
        lead_sal = sal[:, lead_idx]

        # Plot the signal coloured by saliency
        ax.plot(time_axis, lead_data, color="#0b2545", lw=0.6, alpha=0.3)

        # Overlay with scatter coloured by saliency intensity
        sc = ax.scatter(
            time_axis, lead_data, c=lead_sal, cmap="YlOrRd",
            s=1, vmin=0, vmax=1, alpha=0.8, rasterized=True,
        )

        ax.set_ylabel(name, fontsize=10, fontweight="bold", rotation=0, labelpad=15)
        ax.grid(True, which="both", color="#ffcccc", linestyle="-", linewidth=0.5, alpha=0.5)
        ax.tick_params(labelsize=7)

        if row == 5:
            ax.set_xlabel("Time (s)", fontsize=9)

    fig.colorbar(sc, ax=axes, label="Saliency", shrink=0.6, pad=0.02)
    plt.tight_layout(rect=[0, 0, 0.92, 0.96])

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)

    return buf.getvalue()
