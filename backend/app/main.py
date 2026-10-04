"""
MediScanX — FastAPI application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.exceptions import (
    MediScanXError,
    ValidationError,
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    PreprocessingError,
    InferenceError,
)
from app.db.base import Base
from app.db.database import engine

# Import all models so Base.metadata is populated
from app.models.models import (  # noqa: F401
    User, Patient, Case, ImagingStudy, ECGRecord,
    Prediction, Explanation, Report, ModelVersion, AuditLog,
)

# Import routers
from app.api.auth import router as auth_router
from app.api.patients import router as patients_router
from app.api.cases import router as cases_router
from app.api.uploads import router as uploads_router
from app.api.analysis import router as analysis_router
from app.api.reports import router as reports_router
from app.api.admin import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup (dev convenience)."""
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "MediScanX — Online-Based Multimodal AI Diagnostic System "
        "for Thoracic and Cardiac Disease Detection. "
        "Academic prototype; not a medical device."
    ),
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=settings.upload_path), name="uploads")

# ── Exception handlers ───────────────────────────────────────────

@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.detail})


@app.exception_handler(AuthenticationError)
async def auth_error_handler(request: Request, exc: AuthenticationError):
    return JSONResponse(status_code=401, content={"detail": exc.detail})


@app.exception_handler(AuthorizationError)
async def authz_error_handler(request: Request, exc: AuthorizationError):
    return JSONResponse(status_code=403, content={"detail": exc.detail})


@app.exception_handler(NotFoundError)
async def not_found_handler(request: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": exc.detail})


@app.exception_handler(PreprocessingError)
async def preprocessing_error_handler(request: Request, exc: PreprocessingError):
    return JSONResponse(status_code=422, content={"detail": exc.detail})


@app.exception_handler(InferenceError)
async def inference_error_handler(request: Request, exc: InferenceError):
    return JSONResponse(status_code=500, content={"detail": exc.detail})


# ── Health check ─────────────────────────────────────────────────

@app.get("/", tags=["health"])
def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


# ── Register routers ─────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(patients_router)
app.include_router(cases_router)
app.include_router(uploads_router)
app.include_router(analysis_router)
app.include_router(reports_router)
app.include_router(admin_router)
