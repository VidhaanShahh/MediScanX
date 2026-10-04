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
from app.models.models import User, Patient, Case, AuditLog
from app.schemas.schemas import CaseCreate, CaseResponse, CaseDetailResponse

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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List, search and filter cases by status (FR-2.3)."""
    q = db.query(Case)
    if status_filter:
        q = q.filter(Case.status == status_filter)
    return q.order_by(Case.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/cases/{case_id}", response_model=CaseDetailResponse)
def get_case(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get case with all related studies and predictions."""
    case = (
        db.query(Case)
        .options(
            joinedload(Case.patient),
            joinedload(Case.imaging_studies),
            joinedload(Case.ecg_records),
            joinedload(Case.predictions),
        )
        .filter(Case.id == case_id)
        .first()
    )
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


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
