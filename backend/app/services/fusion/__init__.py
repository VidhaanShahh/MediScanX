# M7 — Multimodal fusion services
from app.services.fusion.fusion_service import (  # noqa: F401
    fuse,
    compute_image_risk,
    compute_ecg_risk,
    classify_risk_band,
    FusionResult,
    DEFAULT_WEIGHT_IMAGE,
    DEFAULT_WEIGHT_ECG,
)
