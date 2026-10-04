"""
MediScanX — Analysis API route (M5 imaging, M6 ECG, M7 fusion, M8 explainability).

POST /api/cases/{case_id}/analyze

Orchestrates:
    1. Validate case exists and has data (image and/or ECG)
    2. For imaging studies → M4 preprocessing → M5 CheXNet inference
    3. For ECG records    → M4 preprocessing → M6 1D-CNN inference + HR + 12-lead plot
    4. M7 decision-level fusion (P3 Algorithm A7)
    5. M8 explainability (Grad-CAM / ECG saliency)
    6. Persist predictions and explanations to database
    7. Return structured results
"""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.exceptions import InferenceError, PreprocessingError
from app.core.config import settings
from app.db.database import get_db
from app.api.deps import get_current_user
from app.models.models import (
    User, Case, Prediction, Explanation, ModelVersion, AuditLog,
)
from app.schemas.schemas import (
    AnalysisResponse,
    DiseasePrediction,
    ImagingPredictionResponse,
    ECGClassPrediction,
    ECGPredictionResponse,
    FusionResponse,
    ExplanationItem,
)
from app.services.preprocessing.image import preprocess_image
from app.services.preprocessing.ecg import preprocess_ecg, load_ecg_csv, load_ecg_wfdb
from app.services.imaging.chexnet import (
    predict_image,
    MODEL_NAME as IMAGING_MODEL_NAME,
    MODEL_VERSION as IMAGING_MODEL_VERSION,
)
from app.services.ecg.ecg_service import (
    predict_ecg,
    MODEL_NAME as ECG_MODEL_NAME,
    MODEL_VERSION as ECG_MODEL_VERSION,
)
from app.services.fusion.fusion_service import (
    fuse,
    DEFAULT_WEIGHT_IMAGE,
    DEFAULT_WEIGHT_ECG,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["analysis"])


def _get_or_create_model_version(
    db: Session,
    name: str = IMAGING_MODEL_NAME,
    version: str = IMAGING_MODEL_VERSION,
    dataset: str = "ChestX-ray14",
) -> ModelVersion:
    """Ensure a model_versions row exists for a model and return it."""
    mv = (
        db.query(ModelVersion)
        .filter(
            ModelVersion.name == name,
            ModelVersion.version == version,
        )
        .first()
    )
    if mv is None:
        mv = ModelVersion(
            name=name,
            version=version,
            dataset=dataset,
            is_active=True,
        )
        db.add(mv)
        db.flush()
    return mv


@router.post("/cases/{case_id}/analyze", response_model=AnalysisResponse)
def analyze_case(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run analysis pipeline on a case (P3 Algorithm A9).

    Supports:
        - M5: Imaging AI (CheXNet DenseNet-121, 14 classes)
        - M6: ECG Analysis (1D-CNN, 5 PTB-XL superclasses, heart rate, 12-lead plot)
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    has_image = len(case.imaging_studies) > 0
    has_ecg = len(case.ecg_records) > 0

    if not has_image and not has_ecg:
        raise HTTPException(
            status_code=400,
            detail="Nothing to analyse — upload an image and/or ECG first.",
        )

    db.add(AuditLog(
        user_id=current_user.id,
        action="analyze_started",
        target_id=case_id,
    ))

    # Update case status
    case.status = "analyzing"
    db.flush()

    imaging_response = None
    ecg_response = None
    preprocessed_image = None
    preprocessed_ecg = None
    messages = []

    # ── M5: Imaging inference ────────────────────────────────────
    if has_image:
        study = case.imaging_studies[0]  # Analyse the first uploaded image
        try:
            preprocessed_image, poor_quality = preprocess_image(study.file_path)

            if poor_quality:
                messages.append(
                    f"Warning: image '{study.original_filename}' flagged as "
                    "low-contrast; predictions may be unreliable."
                )

            result = predict_image(preprocessed_image)

            # Persist predictions
            mv_img = _get_or_create_model_version(
                db,
                name=IMAGING_MODEL_NAME,
                version=IMAGING_MODEL_VERSION,
                dataset="ChestX-ray14",
            )

            for pred in result.predictions:
                db.add(Prediction(
                    case_id=case_id,
                    source="image",
                    label=pred.disease,
                    probability=pred.probability,
                    above_threshold=pred.probability >= 0.5,
                    model_id=mv_img.id,
                    inference_ms=result.inference_ms,
                ))
            db.flush()

            imaging_response = ImagingPredictionResponse(
                predictions=[
                    DiseasePrediction(
                        disease=p.disease,
                        probability=round(p.probability, 6),
                    )
                    for p in result.predictions
                ],
                num_classes=result.num_classes,
                inference_ms=result.inference_ms,
                model_name=result.model_name,
                model_version=result.model_version,
            )

            messages.append(
                f"Imaging analysis complete: {result.num_classes} disease "
                f"probabilities computed in {result.inference_ms:.1f} ms."
            )

        except PreprocessingError as exc:
            messages.append(f"Imaging preprocessing failed: {exc.detail}")
        except InferenceError as exc:
            messages.append(f"Imaging inference failed: {exc.detail}")
        except Exception as exc:
            logger.exception("Unexpected error during imaging analysis")
            messages.append(f"Imaging analysis error: {str(exc)}")

    # ── M6: ECG inference ────────────────────────────────────────
    if has_ecg:
        ecg_rec = case.ecg_records[0]  # Analyse the first uploaded ECG
        try:
            p = Path(ecg_rec.file_path)
            fs = ecg_rec.sampling_rate or 100.0

            if p.suffix.lower() == ".csv":
                sig, assumed_fs = load_ecg_csv(p.read_bytes())
                fs = ecg_rec.sampling_rate or assumed_fs
            else:
                rec_base = str(p.with_suffix(""))
                sig, assumed_fs = load_ecg_wfdb(rec_base)
                fs = ecg_rec.sampling_rate or assumed_fs

            preprocessed_ecg, lead_flags = preprocess_ecg(sig, fs=fs)

            if lead_flags:
                flag_str = ", ".join(f"{k}:{v}" for k, v in lead_flags.items())
                messages.append(f"Warning: ECG lead flags: {flag_str}")

            ecg_result = predict_ecg(preprocessed_ecg, fs=fs)

            # Persist predictions to database
            mv_ecg = _get_or_create_model_version(
                db,
                name=ECG_MODEL_NAME,
                version=ECG_MODEL_VERSION,
                dataset="PTB-XL",
            )

            for pred in ecg_result.predictions:
                db.add(Prediction(
                    case_id=case_id,
                    source="ecg",
                    label=pred.superclass,
                    probability=pred.probability,
                    above_threshold=pred.above_threshold,
                    model_id=mv_ecg.id,
                    inference_ms=ecg_result.inference_ms,
                ))
            db.flush()

            ecg_response = ECGPredictionResponse(
                predictions=[
                    ECGClassPrediction(
                        superclass=p.superclass,
                        probability=p.probability,
                        threshold=p.threshold,
                        above_threshold=p.above_threshold,
                    )
                    for p in ecg_result.predictions
                ],
                num_classes=ecg_result.num_classes,
                heart_rate_bpm=ecg_result.heart_rate_bpm,
                plot_image_base64=ecg_result.plot_image_base64,
                inference_ms=ecg_result.inference_ms,
                model_name=ecg_result.model_name,
                model_version=ecg_result.model_version,
            )

            hr_info = (
                f", estimated HR: {ecg_result.heart_rate_bpm:.1f} bpm"
                if ecg_result.heart_rate_bpm
                else ""
            )
            messages.append(
                f"ECG analysis complete: {ecg_result.num_classes} superclasses evaluated "
                f"in {ecg_result.inference_ms:.1f} ms{hr_info}."
            )

        except PreprocessingError as exc:
            messages.append(f"ECG preprocessing failed: {exc.detail}")
        except InferenceError as exc:
            messages.append(f"ECG inference failed: {exc.detail}")
        except Exception as exc:
            logger.exception("Unexpected error during ECG analysis")
            messages.append(f"ECG analysis error: {str(exc)}")
    # ── M7: Multimodal Fusion (P3 Algorithm A7) ────────────────────
    fusion_response = None
    if imaging_response or ecg_response:
        try:
            # Build probability dicts from M5/M6 response schemas
            img_probs = None
            if imaging_response is not None:
                img_probs = {
                    p.disease: p.probability
                    for p in imaging_response.predictions
                }

            ecg_probs = None
            if ecg_response is not None:
                ecg_probs = {
                    p.superclass: p.probability
                    for p in ecg_response.predictions
                }

            # Look up measured AUROCs from ModelVersion rows if available,
            # otherwise fall back to configurable provisional defaults.
            w_img = DEFAULT_WEIGHT_IMAGE
            w_ecg = DEFAULT_WEIGHT_ECG
            try:
                if imaging_response is not None:
                    mv_img_row = (
                        db.query(ModelVersion)
                        .filter(
                            ModelVersion.name == IMAGING_MODEL_NAME,
                            ModelVersion.version == IMAGING_MODEL_VERSION,
                        )
                        .first()
                    )
                    if mv_img_row and mv_img_row.val_auroc is not None:
                        w_img = mv_img_row.val_auroc

                if ecg_response is not None:
                    mv_ecg_row = (
                        db.query(ModelVersion)
                        .filter(
                            ModelVersion.name == ECG_MODEL_NAME,
                            ModelVersion.version == ECG_MODEL_VERSION,
                        )
                        .first()
                    )
                    if mv_ecg_row and mv_ecg_row.val_auroc is not None:
                        w_ecg = mv_ecg_row.val_auroc
            except Exception:
                logger.debug("Could not read val_auroc; using defaults.")

            fusion_result = fuse(
                imaging_probs=img_probs,
                ecg_probs=ecg_probs,
                weight_image=w_img,
                weight_ecg=w_ecg,
            )

            # Persist fusion prediction row
            db.add(Prediction(
                case_id=case_id,
                source="fusion",
                label=f"cardiac_risk:{fusion_result.risk_band}",
                probability=fusion_result.fusion_score,
                above_threshold=fusion_result.fusion_score >= 0.5,
                model_id=None,  # Fusion is not tied to a single model
                inference_ms=0.0,
            ))

            fusion_response = FusionResponse(
                available=fusion_result.available,
                modality_used=fusion_result.modality_used,
                image_score=fusion_result.image_score,
                ecg_score=fusion_result.ecg_score,
                fusion_score=fusion_result.fusion_score,
                risk_band=fusion_result.risk_band,
                disagreement=fusion_result.disagreement,
                difference=fusion_result.difference,
                weight_image=fusion_result.weight_image,
                weight_ecg=fusion_result.weight_ecg,
                screening_only=True,
            )

            messages.append(
                f"Fusion score: {fusion_result.fusion_score:.4f} "
                f"({fusion_result.risk_band} risk, "
                f"modality: {fusion_result.modality_used}). "
                "Screening indicator only — not a diagnosis."
            )

        except Exception as exc:
            logger.exception("Unexpected error during M7 fusion")
            messages.append(f"Fusion error: {str(exc)}")

    # ── M8: Explainability ────────────────────────────────────────
    explanation_items: list[ExplanationItem] = []
    explanations_dir = Path(settings.UPLOAD_DIR) / "explanations" / case_id
    explanations_dir.mkdir(parents=True, exist_ok=True)

    # M8a: Imaging Grad-CAM
    if imaging_response is not None and has_image:
        try:
            from app.services.explainability.gradcam import (
                generate_gradcam,
                render_gradcam_overlay,
            )

            study = case.imaging_studies[0]
            gcam_result = generate_gradcam(preprocessed_image)

            # Render overlay (does NOT modify the original image)
            overlay_bytes = render_gradcam_overlay(
                original_image_path=study.file_path,
                heatmap=gcam_result["heatmap"],
            )

            overlay_filename = f"gradcam_{uuid.uuid4().hex[:8]}.png"
            overlay_path = str(explanations_dir / overlay_filename)
            Path(overlay_path).write_bytes(overlay_bytes)

            # Find the imaging prediction row to link to
            img_pred_row = (
                db.query(Prediction)
                .filter(
                    Prediction.case_id == case_id,
                    Prediction.source == "image",
                    Prediction.label == gcam_result["target_class"],
                )
                .first()
            )
            if img_pred_row:
                db.add(Explanation(
                    prediction_id=img_pred_row.id,
                    type="gradcam",
                    file_path=overlay_path,
                ))

            explanation_items.append(ExplanationItem(
                modality="imaging",
                explanation_type="gradcam",
                target_class=gcam_result["target_class"],
                file_path=overlay_path,
                model_name=gcam_result["model_name"],
                model_version=gcam_result["model_version"],
            ))

            messages.append(
                f"Grad-CAM generated for '{gcam_result['target_class']}'. "
                "Attention visualization only — not proof of disease location."
            )

        except Exception as exc:
            logger.exception("M8 Grad-CAM generation failed")
            messages.append(f"Grad-CAM generation failed (non-fatal): {str(exc)}")

    # M8b: ECG Saliency
    if ecg_response is not None and has_ecg:
        try:
            from app.services.explainability.ecg_saliency import (
                generate_ecg_saliency,
                render_ecg_saliency,
            )

            sal_result = generate_ecg_saliency(preprocessed_ecg)

            # Render saliency plot
            sal_bytes = render_ecg_saliency(
                signal=preprocessed_ecg,
                saliency=sal_result["saliency"],
            )

            sal_filename = f"ecg_saliency_{uuid.uuid4().hex[:8]}.png"
            sal_path = str(explanations_dir / sal_filename)
            Path(sal_path).write_bytes(sal_bytes)

            # Find the ECG NORM prediction row to link to
            ecg_pred_row = (
                db.query(Prediction)
                .filter(
                    Prediction.case_id == case_id,
                    Prediction.source == "ecg",
                    Prediction.label == "NORM",
                )
                .first()
            )
            if ecg_pred_row:
                db.add(Explanation(
                    prediction_id=ecg_pred_row.id,
                    type="saliency",
                    file_path=sal_path,
                ))

            explanation_items.append(ExplanationItem(
                modality="ecg",
                explanation_type="saliency",
                target_class=sal_result["target_class"],
                file_path=sal_path,
                model_name=sal_result["model_name"],
                model_version=sal_result["model_version"],
            ))

            messages.append(
                "ECG saliency map generated. "
                "Input sensitivity visualization only — not proof of clinical causality."
            )

        except Exception as exc:
            logger.exception("M8 ECG saliency generation failed")
            messages.append(f"ECG saliency generation failed (non-fatal): {str(exc)}")

    # Update case status
    case.status = "completed" if (imaging_response or ecg_response) else "error"

    db.add(AuditLog(
        user_id=current_user.id,
        action="analyze_completed",
        target_id=case_id,
    ))
    db.commit()

    return AnalysisResponse(
        case_id=case_id,
        status=case.status,
        imaging_predictions=imaging_response,
        ecg_predictions=ecg_response,
        fusion=fusion_response,
        explanations=explanation_items if explanation_items else None,
        message=" | ".join(messages),
    )
