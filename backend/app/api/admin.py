from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.database import get_db
from app.models.models import AuditLog, User
from app.api.deps import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])

class AuditLogResponse(BaseModel):
    id: str
    action: str
    user_id: Optional[str]
    target_id: Optional[str]
    detail: Optional[str]
    timestamp: datetime
    
    class Config:
        from_attributes = True

class AuditLogPaginated(BaseModel):
    items: List[AuditLogResponse]
    total: int
    page: int
    page_size: int

@router.get("/audit-logs", response_model=AuditLogPaginated)
def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    target_id: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Retrieve administrative audit logs (M10)."""
    query = db.query(AuditLog)
    
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if target_id:
        query = query.filter(AuditLog.target_id == target_id)
        
    total = query.count()
    items = query.order_by(AuditLog.timestamp.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    return AuditLogPaginated(
        items=items,
        total=total,
        page=page,
        page_size=page_size
    )
