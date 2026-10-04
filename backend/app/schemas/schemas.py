"""
MediScanX — Pydantic schemas for request/response validation.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ═══════════════════════════════════════════════════════════════
# M1 — Auth schemas
# ═══════════════════════════════════════════════════════════════

class UserRegister(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="user", pattern="^(user|admin)$")


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    name: Optional[str] = None
    email: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════
# M2 — Patient schemas
# ═══════════════════════════════════════════════════════════════

class PatientCreate(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    anon_code: Optional[str] = Field(default=None, min_length=1, max_length=50)
    age: Optional[int] = Field(default=None, ge=0, le=150)
    sex: Optional[str] = Field(default=None, pattern="^(M|F|O)$")


class PatientResponse(BaseModel):
    id: str
    full_name: Optional[str] = None
    anon_code: str
    age: Optional[int] = None
    sex: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════
# M2 — Case schemas
# ═══════════════════════════════════════════════════════════════

class CaseCreate(BaseModel):
    patient_id: str
    name: str = Field(..., min_length=1, max_length=255)


class CaseResponse(BaseModel):
    id: str
    name: Optional[str] = None
    patient_id: str
    created_by: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PredictionResponse(BaseModel):
    id: str
    case_id: str
    source: str
    label: str
    probability: float
    above_threshold: Optional[bool] = None
    model_id: Optional[str] = None
    inference_ms: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CaseDetailResponse(CaseResponse):
    patient: Optional[PatientResponse] = None
    imaging_studies: list["ImagingStudyResponse"] = []
    ecg_records: list["ECGRecordResponse"] = []
    predictions: list[PredictionResponse] = []


# ═══════════════════════════════════════════════════════════════
# M3 — Upload schemas
# ═══════════════════════════════════════════════════════════════

class UploadResponse(BaseModel):
    id: str
    file_type: str
    sha256: str
    quality_flag: Optional[str] = None
    message: str


class ImagingStudyResponse(BaseModel):
    id: str
    case_id: str
    modality: str
    file_path: str
    original_filename: Optional[str] = None
    sha256: str
    quality_flag: Optional[str] = None
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class ECGRecordResponse(BaseModel):
    id: str
    case_id: str
    file_path: str
    original_filename: Optional[str] = None
    sha256: str
    sampling_rate: Optional[float] = None
    num_leads: Optional[int] = None
    quality_flag: Optional[str] = None
    uploaded_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════
# M4 — Preprocessing schemas
# ═══════════════════════════════════════════════════════════════

class ImagePreprocessResult(BaseModel):
    shape: list[int]
    poor_quality: bool
    message: str


class ECGPreprocessResult(BaseModel):
    shape: list[int]
    lead_flags: dict[str, str]
    message: str


# ═══════════════════════════════════════════════════════════════
# M5 — Imaging prediction schemas
# ═══════════════════════════════════════════════════════════════

class DiseasePrediction(BaseModel):
    disease: str
    probability: float


class ImagingPredictionResponse(BaseModel):
    predictions: list[DiseasePrediction]
    num_classes: int
    inference_ms: float
    model_name: str
    model_version: str


# ═══════════════════════════════════════════════════════════════
# M6 — ECG prediction schemas
# ═══════════════════════════════════════════════════════════════

class ECGClassPrediction(BaseModel):
    superclass: str
    probability: float
    threshold: float
    above_threshold: bool


class ECGPredictionResponse(BaseModel):
    predictions: list[ECGClassPrediction]
    num_classes: int
    heart_rate_bpm: Optional[float] = None
    plot_image_base64: Optional[str] = None
    inference_ms: float
    model_name: str
    model_version: str


# ═══════════════════════════════════════════════════════════════
# M7 — Multimodal Fusion schemas
# ═══════════════════════════════════════════════════════════════

class FusionResponse(BaseModel):
    """Decision-level fusion output (P3 Algorithm A7).

    ``screening_only`` is always ``True`` — the fusion score is a
    screening/decision-support indicator only, NOT a medical diagnosis.
    """

    available: bool
    modality_used: str  # "image_only" | "ecg_only" | "both"
    image_score: Optional[float] = None
    ecg_score: Optional[float] = None
    fusion_score: float
    risk_band: str  # "Low" | "Moderate" | "High"
    disagreement: bool
    difference: Optional[float] = None
    weight_image: float
    weight_ecg: float
    screening_only: bool = True


# ═══════════════════════════════════════════════════════════════
# M8 — Explainability schemas
# ═══════════════════════════════════════════════════════════════

class ExplanationItem(BaseModel):
    """Metadata for a single M8 explanation artifact.

    The explanation is an attention/plausibility visualization.
    It is NOT proof of disease location or causal reasoning.
    """

    modality: str  # "imaging" | "ecg"
    explanation_type: str  # "gradcam" | "saliency"
    target_class: str
    file_path: Optional[str] = None
    model_name: str
    model_version: str


class AnalysisResponse(BaseModel):
    case_id: str
    status: str
    imaging_predictions: Optional[ImagingPredictionResponse] = None
    ecg_predictions: Optional[ECGPredictionResponse] = None
    fusion: Optional[FusionResponse] = None
    explanations: Optional[list[ExplanationItem]] = None
    message: str


# ═══════════════════════════════════════════════════════════════
# General
# ═══════════════════════════════════════════════════════════════

class MessageResponse(BaseModel):
    message: str

class ReportResponse(BaseModel):
    id: str
    case_id: str
    file_path: str
    generated_at: datetime
    remarks: Optional[str] = None

