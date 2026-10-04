"""
MediScanX — FastAPI dependencies (auth, role checks).
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.core.exceptions import credentials_exception, forbidden_exception
from app.db.database import get_db
from app.models.models import User

security_scheme = HTTPBearer()


def get_current_user(
    token: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decode JWT and return the authenticated User, or 401."""
    payload = decode_access_token(token.credentials)
    if payload is None:
        raise credentials_exception
    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Ensure the current user has the *admin* role."""
    if current_user.role != "admin":
        raise forbidden_exception
    return current_user
