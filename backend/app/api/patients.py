"""
MediScanX — M2 Patient API routes.

POST /api/patients
GET  /api/patients
GET  /api/patients/{patient_id}
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.deps import get_current_user
from app.models.models import User, Patient, Case, AuditLog
from app.schemas.schemas import PatientCreate, PatientResponse

router = APIRouter(prefix="/api/patients", tags=["patients"])


@router.post("/", response_model=PatientResponse, status_code=status.HTTP_201_CREATED)
def create_patient(
    body: PatientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a patient record with anonymised ID, age, sex only (FR-2.1)."""
    anon_code = body.anon_code
    if anon_code is None:
        anon_code = _generate_anon_code(db)
    elif db.query(Patient).filter(Patient.anon_code == anon_code).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Patient with this anon_code already exists",
        )

    patient = Patient(
        full_name=body.full_name,
        anon_code=anon_code,
        age=body.age,
        sex=body.sex,
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    
    # Audit log
    db.add(AuditLog(user_id=current_user.id, action="create_patient", target_id=patient.id))
    db.commit()
    
    return patient


@router.delete("/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_patient(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a patient, their cases, stored files, and dependent records."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    for case in patient.cases:
        for study in case.imaging_studies:
            _try_remove(study.file_path)
        for ecg in case.ecg_records:
            _try_remove(ecg.file_path)
        db.delete(case)

    db.add(AuditLog(user_id=current_user.id, action="delete_patient", target_id=patient_id))
    db.delete(patient)
    db.commit()


@router.get("/", response_model=list[PatientResponse])
def list_patients(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all patients."""
    return db.query(Patient).offset(skip).limit(limit).all()


@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve a single patient by ID."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.get("/{patient_id}/timeline")
def get_patient_timeline(
    patient_id: str,
    modality_filter: str | None = Query(None, alias="modality"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve comprehensive chronological history and timeline of cases, analyses,
    consistency outcomes, and clinical reviews for a patient.
    """
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    cases = (
        db.query(Case)
        .filter(Case.patient_id == patient_id)
        .order_by(Case.created_at.desc())
        .all()
    )

    timeline_entries = []
    for c in cases:
        has_img = len(c.imaging_studies) > 0
        has_ecg = len(c.ecg_records) > 0

        # Filter by modality if requested
        if modality_filter:
            if modality_filter.lower() == "cxr" and not has_img:
                continue
            if modality_filter.lower() == "ecg" and not has_ecg:
                continue

        # Extract top findings from predictions
        top_img_pred = None
        top_ecg_pred = None
        fusion_pred = None

        img_preds = [p for p in c.predictions if p.source == "image"]
        ecg_preds = [p for p in c.predictions if p.source == "ecg"]
        f_preds = [p for p in c.predictions if p.source == "fusion"]

        if img_preds:
            top_img = max(img_preds, key=lambda x: x.probability)
            top_img_pred = {"label": top_img.label, "probability": top_img.probability}
        if ecg_preds:
            top_ecg = max(ecg_preds, key=lambda x: x.probability)
            top_ecg_pred = {"label": top_ecg.label, "probability": top_ecg.probability}
        if f_preds:
            fusion_pred = {"label": f_preds[0].label, "probability": f_preds[0].probability}

        consistency = c.consistency_analyses[0] if c.consistency_analyses else None
        latest_review = c.reviews[-1] if c.reviews else None

        timeline_entries.append({
            "case_id": c.id,
            "case_name": c.name or "Untitled Case",
            "created_at": c.created_at.isoformat(),
            "status": c.status,
            "review_status": c.review_status,
            "has_imaging": has_img,
            "has_ecg": has_ecg,
            "top_imaging_finding": top_img_pred,
            "top_ecg_finding": top_ecg_pred,
            "fusion": fusion_pred,
            "consistency_category": consistency.category if consistency else None,
            "consistency_explanation": consistency.explanation if consistency else None,
            "latest_review": {
                "status": latest_review.status,
                "notes": latest_review.notes,
                "agreed_with_ai": latest_review.agreed_with_ai,
                "reviewed_at": latest_review.reviewed_at.isoformat(),
            } if latest_review else None,
            "report_count": len(c.reports),
        })

    return {
        "patient": {
            "id": patient.id,
            "anon_code": patient.anon_code,
            "age": patient.age,
            "sex": patient.sex,
            "created_at": patient.created_at.isoformat(),
        },
        "timeline": timeline_entries,
    }


def _generate_anon_code(db: Session) -> str:
    """Generate a server-owned anonymous reference without exposing UUIDs in forms."""
    while True:
        code = f"MSX-P-{uuid.uuid4().hex[:8].upper()}"
        if not db.query(Patient).filter(Patient.anon_code == code).first():
            return code



def _try_remove(path: str | None) -> None:
    if not path:
        return
    try:
        file_path = Path(path)
        if file_path.exists():
            file_path.unlink()
    except OSError:
        pass
