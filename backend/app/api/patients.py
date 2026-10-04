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
