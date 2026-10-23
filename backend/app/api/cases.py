"""
MediScanX — M2 Case API routes.

POST   /api/cases
GET    /api/cases
GET    /api/cases/{case_id}
DELETE /api/cases/{case_id}
GET    /api/patients/{patient_id}/cases   (case history)
"""

import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.api.deps import get_current_user
from app.models.models import User, Patient, Case, AuditLog, ClinicalReview, CrossModalConsistency
from app.schemas.schemas import (
    CaseCreate,
    CaseResponse,
    CaseDetailResponse,
    ClinicalReviewCreate,
    ClinicalReviewResponse,
    CrossModalConsistencyResponse,
)

router = APIRouter(prefix="/api", tags=["cases"])


@router.post("/cases", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
def create_case(
    body: CaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new case linked to a patient (FR-2.2)."""
    patient = db.query(Patient).filter(Patient.id == body.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    case = Case(name=body.name, patient_id=body.patient_id, created_by=current_user.id)
    db.add(case)
    db.commit()
    db.refresh(case)

    db.add(AuditLog(user_id=current_user.id, action="create_case", target_id=case.id))
    db.commit()

    return case


@router.get("/cases", response_model=list[CaseResponse])
def list_cases(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
    review_status_filter: str | None = Query(None, alias="review_status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List, search and filter cases by status and review status (FR-2.3)."""
    q = db.query(Case)
    if status_filter:
        q = q.filter(Case.status == status_filter)
    if review_status_filter:
        q = q.filter(Case.review_status == review_status_filter)
    return q.order_by(Case.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/cases/{case_id}", response_model=CaseDetailResponse)
def get_case(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get case with all related studies, predictions, consistency records, and clinical reviews."""
    case = (
        db.query(Case)
        .options(
            joinedload(Case.patient),
            joinedload(Case.imaging_studies),
            joinedload(Case.ecg_records),
            joinedload(Case.predictions),
            joinedload(Case.consistency_analyses),
            joinedload(Case.reviews),
        )
        .filter(Case.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.post("/cases/{case_id}/reviews", response_model=ClinicalReviewResponse)
def submit_clinical_review(
    case_id: str,
    body: ClinicalReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Submit clinical review for a case (clinical review workflow).
    Transitions case review_status to 'Reviewed' or specified validated state.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    allowed_statuses = ["Reviewed", "Awaiting Review", "Review Required"]
    if body.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid review status. Must be one of {allowed_statuses}")

    review = ClinicalReview(
        case_id=case.id,
        reviewer_id=current_user.id,
        status=body.status,
        findings_summary=body.findings_summary,
        agreed_with_ai=body.agreed_with_ai,
        notes=body.notes,
    )
    db.add(review)
    case.review_status = body.status
    
    # Audit trail for clinical review transition
    db.add(AuditLog(
        user_id=current_user.id,
        action="clinical_review_submitted",
        target_id=case.id,
        detail=f"Status set to {body.status}. Clinician agreed: {body.agreed_with_ai}",
    ))

    db.commit()
    db.refresh(review)
    return review


@router.get("/cases/{case_id}/consistency", response_model=list[CrossModalConsistencyResponse])
def get_case_consistency(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve persisted cross-modal consistency records for a case."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return db.query(CrossModalConsistency).filter(CrossModalConsistency.case_id == case_id).all()



@router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a case and its stored files (FR-2.5)."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Remove files on disk for imaging studies and ECG records
    for study in case.imaging_studies:
        _try_remove(study.file_path)
    for ecg in case.ecg_records:
        _try_remove(ecg.file_path)

    db.add(AuditLog(user_id=current_user.id, action="delete_case", target_id=case_id))
    db.delete(case)
    db.commit()


@router.get(
    "/patients/{patient_id}/cases",
    response_model=list[CaseResponse],
    tags=["patients"],
)
def patient_case_history(
    patient_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Show a patient's previous cases and predictions (FR-2.4)."""
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return (
        db.query(Case)
        .filter(Case.patient_id == patient_id)
        .order_by(Case.created_at.desc())
        .all()
    )


# ── Helpers ──────────────────────────────────────────────────────

def _try_remove(path: str | None) -> None:
    """Best-effort file deletion; never raises."""
    if not path:
        return
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
    except OSError:
        pass
