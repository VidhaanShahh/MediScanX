"""
MediScanX — M5 Imaging AI Service (CheXNet / DenseNet-121).

Loads the pre-trained CheXNet checkpoint (models/imaging/model.pth.tar)
once as a process-level singleton and exposes a function to run inference
on a single chest X-ray image, returning 14 disease probabilities.

Key design decisions
--------------------
- The original checkpoint was saved with ``torch.nn.DataParallel``, so every
  key in ``state_dict`` is prefixed with ``module.``.  We strip that prefix
  and load into an unwrapped ``DenseNet121`` for CPU inference.
- We do NOT use TenCrop (which the original evaluation script used for AUC
  benchmarks).  Single centre-crop is the standard deployment strategy and
  matches the 224×224 output of the M4 preprocessing pipeline.
- The model is loaded lazily on first call, then cached.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
import torchvision

from app.core.exceptions import InferenceError

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────

N_CLASSES = 14

CLASS_NAMES: list[str] = [
    "Atelectasis",
    "Cardiomegaly",
    "Effusion",
    "Infiltration",
    "Mass",
    "Nodule",
    "Pneumonia",
    "Pneumothorax",
    "Consolidation",
    "Edema",
    "Emphysema",
    "Fibrosis",
    "Pleural_Thickening",
    "Hernia",
]

MODEL_NAME = "CheXNet-DenseNet121"
MODEL_VERSION = "v1.0-chestxray14"

# Default path — can be overridden via CHEXNET_CHECKPOINT env var
_DEFAULT_CKPT = str(
    Path(__file__).resolve().parents[4] / "models" / "imaging" / "model.pth.tar"
)


# ── DenseNet121 architecture (mirrors models/imaging/model.py) ──

class DenseNet121(nn.Module):
    """DenseNet-121 with 14-class sigmoid classifier (CheXNet)."""

    def __init__(self, out_size: int = N_CLASSES):
        super().__init__()
        self.densenet121 = torchvision.models.densenet121(weights=None)
        num_ftrs = self.densenet121.classifier.in_features
        self.densenet121.classifier = nn.Sequential(
            nn.Linear(num_ftrs, out_size),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.densenet121(x)


# ── Singleton model holder ───────────────────────────────────────

@dataclass
class _ModelHolder:
    """Process-level singleton that owns the loaded model."""

    model: Optional[DenseNet121] = None
    checkpoint_path: Optional[str] = None
    load_time_ms: float = 0.0
    epoch: Optional[int] = None
    arch: Optional[str] = None

    def is_loaded(self) -> bool:
        return self.model is not None


_holder = _ModelHolder()


def _fix_state_dict_keys(state_dict: dict) -> dict:
    """
    Fix state_dict keys for compatibility with current torchvision.

    Handles two transformations:
    1. Strip ``module.`` prefix added by ``DataParallel``.
    2. Translate old DenseNet key names (``norm.1`` → ``norm1``,
       ``conv.1`` → ``conv1``, etc.) to current torchvision naming.
       This is a well-known incompatibility between old CheXNet
       checkpoints and modern torchvision (changed circa v0.12+).
    """
    import re

    # Pattern: denselayerN.norm.K or denselayerN.conv.K → denselayerN.normK / convK
    _OLD_DENSE_PATTERN = re.compile(r"(denselayer\d+)\.(norm|conv)\.(\d+)")

    new_sd: dict = {}
    for key, value in state_dict.items():
        new_key = key
        # 1) Strip DataParallel prefix
        if new_key.startswith("module."):
            new_key = new_key.replace("module.", "", 1)
        # 2) Translate old DenseNet naming
        new_key = _OLD_DENSE_PATTERN.sub(r"\1.\2\3", new_key)
        new_sd[new_key] = value
    return new_sd


def load_model(checkpoint_path: str | None = None) -> DenseNet121:
    """
    Load the CheXNet checkpoint into a DenseNet121 on CPU.

    The model is cached in a module-level singleton.  Subsequent calls
    return the cached model unless *checkpoint_path* differs.

    Parameters
    ----------
    checkpoint_path : path to ``model.pth.tar``.
        Falls back to ``CHEXNET_CHECKPOINT`` env var, then the default
        location ``models/imaging/model.pth.tar``.

    Returns
    -------
    DenseNet121
        The model in eval mode, on CPU.

    Raises
    ------
    InferenceError
        If the checkpoint file is missing or cannot be loaded.
    """
    ckpt_path = (
        checkpoint_path
        or os.environ.get("CHEXNET_CHECKPOINT")
        or _DEFAULT_CKPT
    )

    # Return cached model if same checkpoint
    if _holder.is_loaded() and _holder.checkpoint_path == ckpt_path:
        return _holder.model  # type: ignore[return-value]

    if not Path(ckpt_path).is_file():
        raise InferenceError(
            f"CheXNet checkpoint not found at {ckpt_path}. "
            "Set CHEXNET_CHECKPOINT env var or place model.pth.tar in models/imaging/."
        )

    t0 = time.perf_counter()

    try:
        checkpoint = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    except Exception as exc:
        raise InferenceError(f"Failed to load checkpoint: {exc}") from exc

    if "state_dict" not in checkpoint:
        raise InferenceError(
            f"Checkpoint at {ckpt_path} does not contain 'state_dict'. "
            f"Keys found: {list(checkpoint.keys())}"
        )

    model = DenseNet121(out_size=N_CLASSES)
    cleaned_sd = _fix_state_dict_keys(checkpoint["state_dict"])

    try:
        model.load_state_dict(cleaned_sd, strict=True)
    except Exception as exc:
        raise InferenceError(
            f"state_dict is incompatible with DenseNet121(out_size={N_CLASSES}): {exc}"
        ) from exc

    model.eval()

    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Cache in singleton
    _holder.model = model
    _holder.checkpoint_path = ckpt_path
    _holder.load_time_ms = elapsed_ms
    _holder.epoch = checkpoint.get("epoch")
    _holder.arch = checkpoint.get("arch")

    logger.info(
        "CheXNet loaded in %.1f ms  (arch=%s, epoch=%s, params=%d)",
        elapsed_ms,
        _holder.arch,
        _holder.epoch,
        sum(p.numel() for p in model.parameters()),
    )

    return model


def get_model_metadata() -> dict:
    """Return metadata about the currently loaded model."""
    return {
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "architecture": _holder.arch or "densenet121",
        "num_classes": N_CLASSES,
        "class_names": list(CLASS_NAMES),
        "checkpoint": _holder.checkpoint_path,
        "training_epoch": _holder.epoch,
        "load_time_ms": round(_holder.load_time_ms, 1),
    }


# ── Inference ────────────────────────────────────────────────────

@dataclass
class PredictionResult:
    """Structured result for one disease label."""

    disease: str
    probability: float


@dataclass
class ImagingInferenceResult:
    """Full result of running CheXNet on one image."""

    predictions: list[PredictionResult] = field(default_factory=list)
    inference_ms: float = 0.0
    model_name: str = MODEL_NAME
    model_version: str = MODEL_VERSION
    num_classes: int = N_CLASSES


def predict_image(preprocessed: np.ndarray) -> ImagingInferenceResult:
    """
    Run CheXNet inference on a single preprocessed image.

    Parameters
    ----------
    preprocessed : np.ndarray
        ImageNet-normalised float32 array of shape ``(224, 224, 3)`` as
        produced by :func:`app.services.preprocessing.image.preprocess_image`.

    Returns
    -------
    ImagingInferenceResult
        Contains 14 ``PredictionResult`` objects plus timing metadata.

    Raises
    ------
    InferenceError
        If the model is not loaded or input shape is invalid.
    """
    # Validate input shape
    if not isinstance(preprocessed, np.ndarray):
        raise InferenceError(
            f"Expected numpy ndarray, got {type(preprocessed).__name__}"
        )
    if preprocessed.ndim != 3 or preprocessed.shape != (224, 224, 3):
        raise InferenceError(
            f"Expected shape (224, 224, 3), got {preprocessed.shape}"
        )

    model = load_model()

    # Convert HWC → CHW and add batch dim: (1, 3, 224, 224)
    tensor = torch.from_numpy(
        preprocessed.transpose(2, 0, 1).copy()
    ).unsqueeze(0).float()

    t0 = time.perf_counter()

    with torch.no_grad():
        output = model(tensor)  # shape: (1, 14)

    elapsed_ms = (time.perf_counter() - t0) * 1000
    probs = output.squeeze(0).cpu().numpy()  # (14,)

    predictions = [
        PredictionResult(disease=name, probability=float(probs[i]))
        for i, name in enumerate(CLASS_NAMES)
    ]

    return ImagingInferenceResult(
        predictions=predictions,
        inference_ms=round(elapsed_ms, 2),
    )


def reset_model() -> None:
    """Clear the cached model (useful for testing)."""
    _holder.model = None
    _holder.checkpoint_path = None
    _holder.load_time_ms = 0.0
    _holder.epoch = None
    _holder.arch = None
