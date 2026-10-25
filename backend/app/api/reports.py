from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime

from app.db.database import get_db
from app.models.models import User, Case, Report, Prediction, AuditLog
from app.api.deps import get_current_user
from app.schemas.schemas import ReportResponse
from app.services.reporting.pdf_generator import generate_pdf_report

from fastapi.responses import FileResponse
from pathlib import Path
import uuid

router = APIRouter(prefix="/api/reports", tags=["reports"])

@router.get("", response_model=list[ReportResponse])
@router.get("/", response_model=list[ReportResponse])
def get_all_reports(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List all reports accessible to the user (admins see all, normal users see own cases)."""
    if current_user.role == "admin":
        return db.query(Report).order_by(Report.generated_at.desc()).all()
    return (
        db.query(Report)
        .join(Case, Report.case_id == Case.id)
        .filter(Case.created_by == current_user.id)
        .order_by(Report.generated_at.desc())
        .all()
    )


@router.get("/case/{case_id}", response_model=list[ReportResponse])
def list_reports(case_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Report).filter(Report.case_id == case_id).order_by(Report.generated_at.desc()).all()

def _resolve_report_path(file_path_str: str) -> Path:
    """Resolve report path against CWD and repo root."""
    p = Path(file_path_str)
    if p.is_file():
        return p
    # Try resolving relative to repository root (one level above backend)
    repo_root = Path(__file__).resolve().parents[3]
    candidate = repo_root / file_path_str
    if candidate.is_file():
        return candidate
    # Try resolving relative to backend directory
    backend_dir = Path(__file__).resolve().parents[2]
    candidate_backend = backend_dir / file_path_str
    if candidate_backend.is_file():
        return candidate_backend
    return p


@router.get("/download/{report_id}")
def download_report(report_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # Check authorization: user must own the case or be admin
    case = db.query(Case).filter(Case.id == report.case_id).first()
    if case and case.created_by and case.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access or download this report."
        )

    resolved_path = _resolve_report_path(report.file_path)
    if not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="PDF file not found on disk")
    
    db.add(AuditLog(user_id=current_user.id, action="download_report", target_id=report_id))
    db.commit()

    return FileResponse(
        str(resolved_path),
        media_type='application/pdf',
        filename=f"report_{report.id}.pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{report.id}.pdf"}
    )


@router.get("/view/{report_id}")
def view_report_inline(report_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Stream PDF inline for browser viewing and printing."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # Check authorization: user must own the case or be admin
    case = db.query(Case).filter(Case.id == report.case_id).first()
    if case and case.created_by and case.created_by != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access or view this report."
        )

    resolved_path = _resolve_report_path(report.file_path)
    if not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="PDF file not found on disk")
    
    db.add(AuditLog(user_id=current_user.id, action="view_report", target_id=report_id))
    db.commit()

    return FileResponse(
        str(resolved_path),
        media_type='application/pdf',
        headers={"Content-Disposition": f"inline; filename=report_{report.id}.pdf"}
    )


@router.post("/cases/{case_id}/generate", response_model=ReportResponse)
def generate_report(case_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Generate a PDF report for an analyzed case.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
        
    # Optional: check if the user has access. Assuming all authenticated users can for now,
    # or if we need to restrict:
    # if case.created_by != current_user.id and not current_user.is_admin:
    #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        
    # Check if analysis exists
    predictions = db.query(Prediction).filter(Prediction.case_id == case.id).count()
    if predictions == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No analysis results available for this case")
        
    report_id = str(uuid.uuid4())
    try:
        pdf_path = generate_pdf_report(case, db, report_id=report_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"PDF generation failed: {str(e)}")
        
    from datetime import datetime, timezone
    from app.services.security.hash_service import compute_file_sha256
    pdf_sha256 = compute_file_sha256(pdf_path)

    # Save Report to DB
    report = Report(
        id=report_id,
        case_id=case.id,
        file_path=pdf_path,
        sha256=pdf_sha256,
        generated_at=datetime.now(timezone.utc),
        remarks="Auto-generated by M9"
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    
    # Audit log
    db.add(AuditLog(user_id=current_user.id, action="generate_report", target_id=report.id))
    db.commit()
    
    return report
