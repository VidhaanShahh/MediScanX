"""
MediScanX — Custom exception classes.

These are caught by FastAPI exception handlers defined in main.py.
"""

from fastapi import HTTPException, status


class MediScanXError(Exception):
    """Base for all domain-level exceptions."""

    def __init__(self, detail: str = "An error occurred"):
        self.detail = detail
        super().__init__(detail)


class ValidationError(MediScanXError):
    """Raised when upload or input validation fails."""


class AuthenticationError(MediScanXError):
    """Raised when authentication fails."""


class AuthorizationError(MediScanXError):
    """Raised when a user lacks the required role."""


class NotFoundError(MediScanXError):
    """Raised when a requested resource does not exist."""


class PreprocessingError(MediScanXError):
    """Raised when image or ECG preprocessing fails."""


class InferenceError(MediScanXError):
    """Raised when ML model loading or inference fails."""


# ── Convenience HTTP exceptions ─────────────────────────────────

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

forbidden_exception = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Not enough permissions",
)
