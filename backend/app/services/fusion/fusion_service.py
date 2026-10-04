"""
MediScanX — M7 Multimodal Fusion Service (P3 Algorithm A7).

Implements decision-level weighted fusion of imaging (M5) and ECG (M6)
branch predictions into a single cardiac-concern score, risk band, and
cross-modality disagreement flag.

Algorithm reference
-------------------
P3 § 8  "A7: Fusion of the two branches"
SRS § 4.4  "Multimodal Fusion"

Key formulae (P3 Algorithm A7)
------------------------------
    p_img  = max(P(Cardiomegaly), P(Edema), P(Effusion))
    p_ecg  = 1 − P(NORM)
    S      = (w_img · p_img + w_ecg · p_ecg) / (w_img + w_ecg)
    disagree = |p_img − p_ecg| > 0.5
    band   = "Low" if S < 0.33, "Moderate" if S < 0.66, else "High"

Weights *w_img* and *w_ecg* equal each branch's validation AUROC.  Since
this project has not yet conducted its own validation evaluation, the
SRS-stated *target* AUROCs (0.80 imaging, 0.87 ECG) are used as
provisional starting values.  They are **not** measured clinical AUROCs
and must be replaced once held-out evaluation is performed.

IMPORTANT — Screening disclaimer
---------------------------------
The fusion score is a screening / decision-support indicator only.
It is NOT a medical diagnosis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# ── Configurable provisional AUROC weights ───────────────────────
#
#   These are the SRS-stated *target* AUROCs (SRS § 5 "Model quality"),
#   NOT measured validation results.  Replace with actual measured
#   AUROCs once held-out evaluation is completed.
#
#   The weights are used in the P3 A7 formula:
#       S = (w_img * p_img + w_ecg * p_ecg) / (w_img + w_ecg)
#
DEFAULT_WEIGHT_IMAGE: float = 0.80   # SRS target: imaging mean AUROC ≥ 0.80
DEFAULT_WEIGHT_ECG: float = 0.87     # SRS target: ECG macro AUROC ≥ 0.87

# ── Risk band thresholds (P3 A7) ────────────────────────────────
BAND_LOW_UPPER: float = 0.33     # score < 0.33  → Low
BAND_MOD_UPPER: float = 0.66     # score < 0.66  → Moderate; ≥ 0.66 → High

# ── Disagreement threshold (P3 A7) ──────────────────────────────
DISAGREE_THRESHOLD: float = 0.5  # |p_img − p_ecg| > 0.5


# ── Data structures ─────────────────────────────────────────────

@dataclass
class FusionResult:
    """Structured output of Algorithm A7 fusion.

    Attributes
    ----------
    available       : True when at least one modality contributed.
    modality_used   : "image_only", "ecg_only", or "both".
    image_score     : p_img (None if imaging not available).
    ecg_score       : p_ecg (None if ECG not available).
    fusion_score    : S — the final cardiac-concern score.
    risk_band       : "Low", "Moderate", or "High".
    disagreement    : True when modalities disagree (|p_img − p_ecg| > 0.5).
    difference      : Absolute difference |p_img − p_ecg| (None if single-modality).
    weight_image    : w_img used in the weighted average.
    weight_ecg      : w_ecg used in the weighted average.
    screening_only  : Always True — reminder that this is not a diagnosis.
    """

    available: bool
    modality_used: str  # "image_only" | "ecg_only" | "both"
    image_score: Optional[float]
    ecg_score: Optional[float]
    fusion_score: float
    risk_band: str  # "Low" | "Moderate" | "High"
    disagreement: bool
    difference: Optional[float]
    weight_image: float
    weight_ecg: float
    source_image_weight: str
    source_ecg_weight: str
    screening_only: bool = True


# ── Core functions ───────────────────────────────────────────────

def compute_image_risk(
    imaging_probs: dict[str, float],
) -> float:
    """Compute p_img = max(P(Cardiomegaly), P(Edema), P(Effusion)).

    Parameters
    ----------
    imaging_probs : dict mapping disease name → probability.
        Must contain keys "Cardiomegaly", "Edema", and "Effusion".

    Returns
    -------
    float : p_img ∈ [0, 1].

    Raises
    ------
    ValueError
        If any of the three required diseases is missing.
    """
    required = ("Cardiomegaly", "Edema", "Effusion")
    missing = [d for d in required if d not in imaging_probs]
    if missing:
        raise ValueError(
            f"Missing required imaging predictions for fusion: {missing}"
        )

    p_img = max(
        imaging_probs["Cardiomegaly"],
        imaging_probs["Edema"],
        imaging_probs["Effusion"],
    )

    if not (0.0 <= p_img <= 1.0):
        logger.warning("p_img = %.4f is outside [0, 1]; clamping.", p_img)
        p_img = max(0.0, min(1.0, p_img))

    return p_img


def compute_ecg_risk(
    ecg_probs: dict[str, float],
) -> float:
    """Compute p_ecg = 1 − P(NORM).

    Parameters
    ----------
    ecg_probs : dict mapping superclass name → probability.
        Must contain key "NORM".

    Returns
    -------
    float : p_ecg ∈ [0, 1].

    Raises
    ------
    ValueError
        If "NORM" is missing.
    """
    if "NORM" not in ecg_probs:
        raise ValueError("Missing required ECG 'NORM' probability for fusion.")

    p_ecg = 1.0 - ecg_probs["NORM"]

    if not (0.0 <= p_ecg <= 1.0):
        logger.warning("p_ecg = %.4f is outside [0, 1]; clamping.", p_ecg)
        p_ecg = max(0.0, min(1.0, p_ecg))

    return p_ecg


def classify_risk_band(score: float) -> str:
    """Classify a fusion score into a risk band (P3 A7).

    Boundary rules (as specified in P3):
        score < 0.33  → "Low"
        0.33 ≤ score < 0.66  → "Moderate"
        score ≥ 0.66  → "High"
    """
    if score < BAND_LOW_UPPER:
        return "Low"
    elif score < BAND_MOD_UPPER:
        return "Moderate"
    else:
        return "High"


def fuse(
    imaging_probs: Optional[dict[str, float]] = None,
    ecg_probs: Optional[dict[str, float]] = None,
    weight_image: Optional[float] = None,
    weight_ecg: Optional[float] = None,
) -> FusionResult:
    """Run P3 Algorithm A7 — decision-level weighted fusion.

    Parameters
    ----------
    imaging_probs : dict mapping disease name → sigmoid probability.
        Must include "Cardiomegaly", "Edema", "Effusion".
        None if no imaging data available.
    ecg_probs : dict mapping superclass name → probability.
        Must include "NORM".
        None if no ECG data available.
    weight_image : Optional manual weight for the imaging branch.
    weight_ecg : Optional manual weight for the ECG branch.

    Returns
    -------
    FusionResult
        Structured fusion output including score, risk band,
        disagreement, and screening disclaimer.

    Raises
    ------
    ValueError
        If both imaging_probs and ecg_probs are None.
        If required prediction keys are missing.
    """
    has_image = imaging_probs is not None
    has_ecg = ecg_probs is not None

    if not has_image and not has_ecg:
        raise ValueError(
            "At least one modality (imaging or ECG) is required for fusion."
        )

    p_img: Optional[float] = None
    p_ecg: Optional[float] = None

    if has_image:
        p_img = compute_image_risk(imaging_probs)  # type: ignore[arg-type]

    if has_ecg:
        p_ecg = compute_ecg_risk(ecg_probs)  # type: ignore[arg-type]

    # ── Load configured weights if not provided ──────────────────
    source_img = "provisional_srs_target"
    source_ecg = "provisional_srs_target"
    
    try:
        from app.services.evaluation.metrics import load_evaluation_results
        eval_results = load_evaluation_results()
    except Exception:
        eval_results = {}
        
    if weight_image is None:
        if eval_results.get("imaging_measured_test_auroc") is not None:
            weight_image = eval_results["imaging_measured_test_auroc"]
            source_img = "measured_test_auroc"
        elif eval_results.get("imaging_measured_validation_auroc") is not None:
            weight_image = eval_results["imaging_measured_validation_auroc"]
            source_img = "measured_validation_auroc"
        else:
            weight_image = DEFAULT_WEIGHT_IMAGE
            
    if weight_ecg is None:
        if eval_results.get("ecg_measured_test_auroc") is not None:
            weight_ecg = eval_results["ecg_measured_test_auroc"]
            source_ecg = "measured_test_auroc"
        elif eval_results.get("ecg_measured_validation_auroc") is not None:
            weight_ecg = eval_results["ecg_measured_validation_auroc"]
            source_ecg = "measured_validation_auroc"
        else:
            weight_ecg = DEFAULT_WEIGHT_ECG

    # ── Compute fusion score (P3 A7) ─────────────────────────────
    if has_image and has_ecg:
        # Dual-modality weighted average
        assert p_img is not None and p_ecg is not None
        w_sum = weight_image + weight_ecg
        fusion_score = (weight_image * p_img + weight_ecg * p_ecg) / w_sum
        modality_used = "both"
        difference = abs(p_img - p_ecg)
        disagreement = difference > DISAGREE_THRESHOLD
    elif has_image:
        # Image only
        assert p_img is not None
        fusion_score = p_img
        modality_used = "image_only"
        difference = None
        disagreement = False
    else:
        # ECG only
        assert p_ecg is not None
        fusion_score = p_ecg
        modality_used = "ecg_only"
        difference = None
        disagreement = False

    risk_band = classify_risk_band(fusion_score)

    return FusionResult(
        available=True,
        modality_used=modality_used,
        image_score=round(p_img, 6) if p_img is not None else None,
        ecg_score=round(p_ecg, 6) if p_ecg is not None else None,
        fusion_score=round(fusion_score, 6),
        risk_band=risk_band,
        disagreement=disagreement,
        difference=round(difference, 6) if difference is not None else None,
        weight_image=weight_image,
        weight_ecg=weight_ecg,
        source_image_weight=source_img,
        source_ecg_weight=source_ecg,
        screening_only=True,
    )
