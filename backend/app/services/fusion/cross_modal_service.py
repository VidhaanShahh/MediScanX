"""
MediScanX — Cross-Modal Consistency & Contradiction Evaluation Engine.

Evaluates findings from Chest X-ray (CXR, 14 thoracic disease labels) and
12-lead ECG (5 PTB-XL superclasses: NORM, MI, STTC, CD, HYP).

Clinically Defensible Framework:
--------------------------------
1. Chest X-rays depict structural and anatomical features (cardiac silhouette, lung parenchyma, pleural space).
2. ECG records depict electrophysiological activity and conduction timing.
3. Therefore:
   - A normal ECG does NOT simply contradict an anatomical finding like Cardiomegaly or Pleural Effusion (structural enlargement can be electrically silent or compensated).
   - An abnormal ECG (e.g. STTC or CD) does NOT contradict a clear lung field on CXR.
   - However, severe cardiomegaly (> 0.65) paired with strong NORM ECG (> 0.85) warrants clinician scrutiny ("POTENTIAL CROSS-MODAL CONFLICT") due to discordant cardiac risk signaling.
   - Acute ischemic signs (ECG MI > 0.6) paired with acute pulmonary edema on CXR (> 0.6) represents highly correlated, mutually corroborating cardiac compromise ("CONSISTENT OR COMPATIBLE FINDINGS").
   - When only one modality is present, the status is "INSUFFICIENT INFORMATION".
   - When findings involve orthogonal, non-cardiac conditions (e.g., Pneumothorax vs Sinus Rhythm), they are "INCOMPARABLE FINDINGS".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ConsistencyEvaluation:
    category: str
    explanation: str
    source_imaging_finding: Optional[str]
    source_imaging_prob: Optional[float]
    source_ecg_finding: Optional[str]
    source_ecg_prob: Optional[float]
    rule_version: str
    requires_human_review: bool


RULE_VERSION = "v1.0-heuristic-clinical-rules"

# Classification categories
CATEGORY_CONSISTENT = "CONSISTENT OR COMPATIBLE FINDINGS"
CATEGORY_CONFLICT = "POTENTIAL CROSS-MODAL CONFLICT"
CATEGORY_INSUFFICIENT = "INSUFFICIENT INFORMATION"
CATEGORY_INCOMPARABLE = "INCOMPARABLE FINDINGS"
CATEGORY_UNAVAILABLE = "ANALYSIS UNAVAILABLE OR FAILED"
CATEGORY_REVIEW_REQUIRED = "REVIEW REQUIRED"


def evaluate_cross_modal_consistency(
    imaging_preds: Optional[dict[str, float]],
    ecg_preds: Optional[dict[str, float]],
) -> ConsistencyEvaluation:
    """
    Evaluate consistency between chest X-ray disease probabilities and ECG superclass probabilities.

    Parameters:
    -----------
    imaging_preds : dict of label -> probability for CXR (or None if unavailable/failed)
    ecg_preds : dict of superclass -> probability for ECG (or None if unavailable/failed)

    Returns:
    --------
    ConsistencyEvaluation dataclass detailing category, clinical rationale, source labels, and review flag.
    """
    if not imaging_preds and not ecg_preds:
        return ConsistencyEvaluation(
            category=CATEGORY_UNAVAILABLE,
            explanation="Neither chest X-ray nor ECG analysis results are available for this case.",
            source_imaging_finding=None,
            source_imaging_prob=None,
            source_ecg_finding=None,
            source_ecg_prob=None,
            rule_version=RULE_VERSION,
            requires_human_review=False,
        )

    if imaging_preds and not ecg_preds:
        top_img = max(imaging_preds.items(), key=lambda x: x[1])
        return ConsistencyEvaluation(
            category=CATEGORY_INSUFFICIENT,
            explanation=(
                f"Only chest X-ray analysis is available (top finding: {top_img[0]} at {top_img[1]*100:.1f}%). "
                "ECG record is missing; cross-modal validation cannot be performed."
            ),
            source_imaging_finding=top_img[0],
            source_imaging_prob=round(top_img[1], 4),
            source_ecg_finding=None,
            source_ecg_prob=None,
            rule_version=RULE_VERSION,
            requires_human_review=False,
        )

    if ecg_preds and not imaging_preds:
        top_ecg = max(ecg_preds.items(), key=lambda x: x[1])
        return ConsistencyEvaluation(
            category=CATEGORY_INSUFFICIENT,
            explanation=(
                f"Only ECG analysis is available (top finding: {top_ecg[0]} at {top_ecg[1]*100:.1f}%). "
                "Chest X-ray is missing; cross-modal validation cannot be performed."
            ),
            source_imaging_finding=None,
            source_imaging_prob=None,
            source_ecg_finding=top_ecg[0],
            source_ecg_prob=round(top_ecg[1], 4),
            rule_version=RULE_VERSION,
            requires_human_review=False,
        )

    # Both modalities are present
    assert imaging_preds is not None and ecg_preds is not None

    top_img_label, top_img_prob = max(imaging_preds.items(), key=lambda x: x[1])
    top_ecg_label, top_ecg_prob = max(ecg_preds.items(), key=lambda x: x[1])

    # Key cardiac and pulmonary indicators
    cardiomegaly_p = imaging_preds.get("Cardiomegaly", 0.0)
    edema_p = imaging_preds.get("Edema", 0.0)
    effusion_p = imaging_preds.get("Effusion", 0.0)

    norm_p = ecg_preds.get("NORM", 0.0)
    mi_p = ecg_preds.get("MI", 0.0)
    hyp_p = ecg_preds.get("HYP", 0.0)
    sttc_p = ecg_preds.get("STTC", 0.0)
    cd_p = ecg_preds.get("CD", 0.0)

    # Rule 1: Non-cardiac CXR conditions (e.g. Pneumothorax, Nodule, Atelectasis)
    non_cardiac_labels = ["Pneumothorax", "Nodule", "Mass", "Fibrosis", "Emphysema", "Pneumonia", "Hernia", "Atelectasis"]
    if top_img_label in non_cardiac_labels and top_img_prob >= 0.5:
        return ConsistencyEvaluation(
            category=CATEGORY_INCOMPARABLE,
            explanation=(
                f"Top chest X-ray finding is pulmonary/structural ({top_img_label}: {top_img_prob*100:.1f}%), which does not have "
                f"a direct 1:1 electrophysiological counter-marker on ECG (top ECG: {top_ecg_label} at {top_ecg_prob*100:.1f}%). "
                "Findings are physiologically distinct and non-contradictory."
            ),
            source_imaging_finding=top_img_label,
            source_imaging_prob=round(top_img_prob, 4),
            source_ecg_finding=top_ecg_label,
            source_ecg_prob=round(top_ecg_prob, 4),
            rule_version=RULE_VERSION,
            requires_human_review=False,
        )

    # Rule 2: Corroborating Heart Failure / Cardiac Decompensation
    # Elevated Cardiomegaly or Edema on CXR and Hypertrophy (HYP) or Myocardial Infarction (MI) on ECG
    if (cardiomegaly_p >= 0.5 or edema_p >= 0.5) and (hyp_p >= 0.5 or mi_p >= 0.5):
        cxr_source = "Cardiomegaly" if cardiomegaly_p >= edema_p else "Edema"
        ecg_source = "HYP" if hyp_p >= mi_p else "MI"
        return ConsistencyEvaluation(
            category=CATEGORY_CONSISTENT,
            explanation=(
                f"Concordant findings of cardiac enlargement/congestion: CXR shows elevated {cxr_source} "
                f"({imaging_preds[cxr_source]*100:.1f}%), accompanied by ECG evidence of {ecg_source} "
                f"({ecg_preds[ecg_source]*100:.1f}%). Findings are mutually compatible with cardiopulmonary compromise."
            ),
            source_imaging_finding=cxr_source,
            source_imaging_prob=round(imaging_preds[cxr_source], 4),
            source_ecg_finding=ecg_source,
            source_ecg_prob=round(ecg_preds[ecg_source], 4),
            rule_version=RULE_VERSION,
            requires_human_review=False,
        )

    # Rule 3: Both modalities normal
    if norm_p >= 0.70 and max(cardiomegaly_p, edema_p, effusion_p) < 0.30:
        return ConsistencyEvaluation(
            category=CATEGORY_CONSISTENT,
            explanation=(
                f"Concordant non-acute findings: ECG indicates high probability of normal rhythm (NORM: {norm_p*100:.1f}%), "
                f"and CXR shows low probability for cardiac enlargement or vascular congestion (max cardiac marker < 30%)."
            ),
            source_imaging_finding=top_img_label,
            source_imaging_prob=round(top_img_prob, 4),
            source_ecg_finding="NORM",
            source_ecg_prob=round(norm_p, 4),
            rule_version=RULE_VERSION,
            requires_human_review=False,
        )

    # Rule 4: Potential Cross-Modal Conflict / Discordance
    # Substantial anatomical cardiomegaly or pulmonary edema with exceptionally high ECG NORM
    if (cardiomegaly_p >= 0.65 or edema_p >= 0.65) and norm_p >= 0.80:
        culprit_cxr = "Cardiomegaly" if cardiomegaly_p >= edema_p else "Edema"

        return ConsistencyEvaluation(
            category=CATEGORY_CONFLICT,
            explanation=(
                f"Marked cross-modal discordance: CXR predicts substantial {culprit_cxr} "
                f"({imaging_preds[culprit_cxr]*100:.1f}%), yet ECG indicates high normality (NORM: {norm_p*100:.1f}%). "
                "While chronic structural dilation can exist with unremarkable conduction, this divergence requires clinician review."
            ),
            source_imaging_finding=culprit_cxr,
            source_imaging_prob=round(imaging_preds[culprit_cxr], 4),
            source_ecg_finding="NORM",
            source_ecg_prob=round(norm_p, 4),
            rule_version=RULE_VERSION,
            requires_human_review=True,
        )

    # Rule 5: Acute ECG ischemia/infarction (MI > 0.65) with totally clear CXR
    if mi_p >= 0.65 and max(cardiomegaly_p, edema_p) < 0.25:
        return ConsistencyEvaluation(
            category=CATEGORY_REVIEW_REQUIRED,
            explanation=(
                f"Urgent electrophysiological finding: ECG indicates high probability of Myocardial Infarction (MI: {mi_p*100:.1f}%), "
                "while CXR does not show secondary congestion. Early acute infarction often precedes radiographic edema. Immediate clinical review required."
            ),
            source_imaging_finding="Normal/Low CXR markers",
            source_imaging_prob=round(max(cardiomegaly_p, edema_p), 4),
            source_ecg_finding="MI",
            source_ecg_prob=round(mi_p, 4),
            rule_version=RULE_VERSION,
            requires_human_review=True,
        )


    # Default fallback
    return ConsistencyEvaluation(
        category=CATEGORY_CONSISTENT,
        explanation=(
            f"Cross-modal analysis completed without severe contradiction: top CXR finding is {top_img_label} "
            f"({top_img_prob*100:.1f}%) and top ECG finding is {top_ecg_label} ({top_ecg_prob*100:.1f}%). "
            "Both findings fall within expected clinical variance."
        ),
        source_imaging_finding=top_img_label,
        source_imaging_prob=round(top_img_prob, 4),
        source_ecg_finding=top_ecg_label,
        source_ecg_prob=round(top_ecg_prob, 4),
        rule_version=RULE_VERSION,
        requires_human_review=False,
    )
