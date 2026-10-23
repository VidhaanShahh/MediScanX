"""
MediScanX — File Integrity and Cryptographic Hashing API.

Endpoints:
- POST /api/integrity/verify/{entity_type}/{entity_id}
    Recalculates SHA-256 for an imaging study, ECG record, or generated PDF report
    and verifies it against the authoritative database digest.
- GET  /api/integrity/case/{case_id}
    Retrieves the integrity status of all uploaded files and reports associated with a case.
- GET  /api/integrity/demo
    Provides a live, interactive demonstration of cryptographic hashing concepts
    (determinism, 256-bit fixed output, avalanche effect, and hashing vs. encryption).
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.deps import get_current_user
from app.models.models import User, Case, ImagingStudy, ECGRecord, Report, AuditLog
from app.services.security.hash_service import (
    compute_file_sha256,
    verify_file_integrity,
    demonstrate_cryptographic_hashing,
)

router = APIRouter(prefix="/api/integrity", tags=["integrity"])


class IntegrityVerificationResult(BaseModel):
    entity_id: str
    entity_type: str  # "imaging", "ecg", "report"
    original_filename: Optional[str] = None
    is_valid: bool
    file_exists: bool
    recorded_sha256: Optional[str] = None
    calculated_sha256: Optional[str] = None
    status: str
    message: str


class CaseIntegritySummary(BaseModel):
    case_id: str
    overall_integrity_passed: bool
    total_files_checked: int
    files: List[IntegrityVerificationResult]


class CryptographyDemoResponse(BaseModel):
    algorithm: str
    digest_bit_length: int
    digest_hex_length: int
    sample_input: str
    primary_digest: str
    deterministic_verification: Dict[str, Any]
    avalanche_effect_demonstration: Dict[str, Any]
    hashing_vs_encryption_comparison: Dict[str, Any]


@router.get("/demo", response_model=CryptographyDemoResponse)
def get_cryptography_demonstration(
    input_text: str = Query(
        "MediScanX Clinical AI Chest X-Ray Study - Patient MSX-P-001",
        description="Custom text to hash and demonstrate avalanche effect",
        max_length=256,
    ),
    current_user: User = Depends(get_current_user),
):
    """
    Demonstrate cryptographic hashing principles for educational viva presentation:
    - 256-bit fixed length digest (64 hex characters)
    - Determinism across repeated executions
    - Avalanche effect (drastic output divergence upon 1-character modification)
    - Theoretical difference between one-way hashing and two-way encryption
    """
    return demonstrate_cryptographic_hashing(sample_text=input_text)


@router.post("/verify/{entity_type}/{entity_id}", response_model=IntegrityVerificationResult)
def verify_single_entity_integrity(
    entity_type: str,
    entity_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Recalculate SHA-256 for a stored file and compare against the authoritative database digest.
    Entity types: 'imaging', 'ecg', or 'report'.
    """
    entity_type_lower = entity_type.lower()
    file_path: Optional[str] = None
    recorded_hash: Optional[str] = None
    filename: Optional[str] = None
    case_id: Optional[str] = None

    if entity_type_lower == "imaging":
        study = db.query(ImagingStudy).filter(ImagingStudy.id == entity_id).first()
        if not study:
            raise HTTPException(status_code=404, detail="Imaging study record not found")
        file_path = study.file_path
        recorded_hash = study.sha256
        filename = study.original_filename
        case_id = study.case_id

    elif entity_type_lower == "ecg":
        ecg = db.query(ECGRecord).filter(ECGRecord.id == entity_id).first()
        if not ecg:
            raise HTTPException(status_code=404, detail="ECG record not found")
        file_path = ecg.file_path
        recorded_hash = ecg.sha256
        filename = ecg.original_filename
        case_id = ecg.case_id

    elif entity_type_lower == "report":
        report = db.query(Report).filter(Report.id == entity_id).first()
        if not report:
            raise HTTPException(status_code=404, detail="Report record not found")
        file_path = report.file_path
        recorded_hash = report.sha256
        filename = f"report_{report.id}.pdf"
        case_id = report.case_id

    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid entity_type. Must be 'imaging', 'ecg', or 'report'.",
        )

    # Authorization check: verify user owns the case or has admin role
    if case_id:
        case = db.query(Case).filter(Case.id == case_id).first()
        if case and case.created_by and case.created_by != current_user.id and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access or verify this case's files.",
            )

    res = verify_file_integrity(file_path=file_path, recorded_hash=recorded_hash)

    # Log audit event for integrity check
    db.add(AuditLog(
        user_id=current_user.id,
        action="verify_file_integrity",
        target_id=entity_id,
        detail=f"Entity: {entity_type_lower}. Status: {res['status']}. Valid: {res['is_valid']}",
    ))
    db.commit()

    return IntegrityVerificationResult(
        entity_id=entity_id,
        entity_type=entity_type_lower,
        original_filename=filename,
        is_valid=res["is_valid"],
        file_exists=res["file_exists"],
        recorded_sha256=res["recorded_hash"],
        calculated_sha256=res["calculated_hash"],
        status=res["status"],
        message=res["message"],
    )


@router.get("/case/{case_id}", response_model=CaseIntegritySummary)
def verify_all_case_files(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Audit and verify the cryptographic integrity of all medical files and reports in a case.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Authorization check: verify user owns the case or has admin role
    if case.created_by and case.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access or verify this case's files.",
        )

    file_results: List[IntegrityVerificationResult] = []

    # Verify imaging studies
    for img in case.imaging_studies:
        res = verify_file_integrity(img.file_path, img.sha256)
        file_results.append(IntegrityVerificationResult(
            entity_id=img.id,
            entity_type="imaging",
            original_filename=img.original_filename,
            is_valid=res["is_valid"],
            file_exists=res["file_exists"],
            recorded_sha256=res["recorded_hash"],
            calculated_sha256=res["calculated_hash"],
            status=res["status"],
            message=res["message"],
        ))

    # Verify ECG records
    for ecg in case.ecg_records:
        res = verify_file_integrity(ecg.file_path, ecg.sha256)
        file_results.append(IntegrityVerificationResult(
            entity_id=ecg.id,
            entity_type="ecg",
            original_filename=ecg.original_filename,
            is_valid=res["is_valid"],
            file_exists=res["file_exists"],
            recorded_sha256=res["recorded_hash"],
            calculated_sha256=res["calculated_hash"],
            status=res["status"],
            message=res["message"],
        ))

    # Verify Reports
    for rpt in case.reports:
        res = verify_file_integrity(rpt.file_path, rpt.sha256)
        file_results.append(IntegrityVerificationResult(
            entity_id=rpt.id,
            entity_type="report",
            original_filename=f"report_{rpt.id}.pdf",
            is_valid=res["is_valid"],
            file_exists=res["file_exists"],
            recorded_sha256=res["recorded_hash"],
            calculated_sha256=res["calculated_hash"],
            status=res["status"],
            message=res["message"],
        ))

    all_passed = (len(file_results) > 0) and all(f.is_valid for f in file_results)

    return CaseIntegritySummary(
        case_id=case_id,
        overall_integrity_passed=all_passed,
        total_files_checked=len(file_results),
        files=file_results,
    )
