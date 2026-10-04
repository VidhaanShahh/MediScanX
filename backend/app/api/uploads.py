"""
MediScanX — M3 Upload API route.

POST /api/cases/{case_id}/upload
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.db.database import get_db
from app.api.deps import get_current_user
from app.models.models import User, Case, ImagingStudy, ECGRecord, AuditLog
from app.schemas.schemas import UploadResponse
from app.services.upload_service import validate_image, validate_ecg, compute_sha256

router = APIRouter(prefix="/api/cases", tags=["uploads"])


@router.post("/{case_id}/upload", response_model=UploadResponse)
async def upload_file(
    case_id: str,
    file: UploadFile = File(...),
    file_type: str = "image",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload an image or ECG file to a case (FR-3.1, FR-3.2).

    - file_type: "image" or "ecg"
    - Validates content, not just extension (FR-3.3)
    - No ML inference is performed during upload
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Read file content
    file_bytes = await file.read()

    if len(file_bytes) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum is {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )

    filename = file.filename or "unknown"

    try:
        if file_type == "image":
            result = _handle_image_upload(file_bytes, filename, case_id, db)
        elif file_type == "ecg":
            result = _handle_ecg_upload(file_bytes, filename, case_id, db)
        else:
            raise HTTPException(
                status_code=400,
                detail="file_type must be 'image' or 'ecg'.",
            )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc.detail))

    # Update case status
    case.status = "uploaded"
    db.add(AuditLog(
        user_id=current_user.id,
        action=f"upload_{file_type}",
        target_id=case_id,
    ))
    db.commit()

    return result


# ── Internal handlers ────────────────────────────────────────────

def _handle_image_upload(
    file_bytes: bytes, filename: str, case_id: str, db: Session
) -> UploadResponse:
    """Validate, save, and record an image upload."""
    info = validate_image(file_bytes, filename)

    # Save file
    ext = Path(filename).suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = settings.upload_path / "images" / stored_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(file_bytes)

    study = ImagingStudy(
        case_id=case_id,
        modality=info["modality"],
        file_path=str(dest),
        original_filename=filename,
        sha256=info["sha256"],
    )
    db.add(study)
    db.flush()

    return UploadResponse(
        id=study.id,
        file_type="image",
        sha256=info["sha256"],
        message="Image uploaded and validated successfully.",
    )


def _handle_ecg_upload(
    file_bytes: bytes, filename: str, case_id: str, db: Session
) -> UploadResponse:
    """Validate, save, and record an ECG upload."""
    info = validate_ecg(file_bytes, filename)

    ext = Path(filename).suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    dest = settings.upload_path / "ecg" / stored_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(file_bytes)

    record = ECGRecord(
        case_id=case_id,
        file_path=str(dest),
        original_filename=filename,
        sha256=info["sha256"],
        sampling_rate=info.get("sampling_rate"),
        num_leads=info["num_leads"],
    )
    db.add(record)
    db.flush()

    return UploadResponse(
        id=record.id,
        file_type="ecg",
        sha256=info["sha256"],
        message="ECG uploaded and validated successfully.",
    )
