"""
MediScanX — SQLAlchemy ORM models for all SRS entities.

Tables (Section 5 of the SRS, Table 3):
    users, patients, cases, imaging_studies, ecg_records,
    predictions, explanations, reports, model_versions, audit_logs
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────
# M1 — users
# ─────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    name = Column(String(255), nullable=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(
        SAEnum("user", "admin", name="user_role"),
        nullable=False,
        default="user",
    )
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # relationships
    cases = relationship("Case", back_populates="creator", lazy="dynamic")
    audit_logs = relationship("AuditLog", back_populates="user", lazy="dynamic")


# ─────────────────────────────────────────────────────────────────
# M2 — patients
# ─────────────────────────────────────────────────────────────────

class Patient(Base):
    __tablename__ = "patients"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    full_name = Column(String(255), nullable=True)
    anon_code = Column(String(50), unique=True, nullable=False, index=True)
    age = Column(Integer, nullable=True)
    sex = Column(
        SAEnum("M", "F", "O", name="patient_sex"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    cases = relationship("Case", back_populates="patient", lazy="dynamic")


# ─────────────────────────────────────────────────────────────────
# M2 — cases
# ─────────────────────────────────────────────────────────────────

class Case(Base):
    __tablename__ = "cases"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    name = Column(String(255), nullable=True)
    patient_id = Column(
        String(36), ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    created_by = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status = Column(
        SAEnum("created", "uploaded", "analyzing", "completed", "error",
               name="case_status"),
        nullable=False,
        default="created",
    )
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # relationships
    patient = relationship("Patient", back_populates="cases")
    creator = relationship("User", back_populates="cases")
    imaging_studies = relationship(
        "ImagingStudy", back_populates="case", cascade="all, delete-orphan"
    )
    ecg_records = relationship(
        "ECGRecord", back_populates="case", cascade="all, delete-orphan"
    )
    predictions = relationship(
        "Prediction", back_populates="case", cascade="all, delete-orphan"
    )
    reports = relationship(
        "Report", back_populates="case", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────────
# M3 — imaging_studies
# ─────────────────────────────────────────────────────────────────

class ImagingStudy(Base):
    __tablename__ = "imaging_studies"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    case_id = Column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    modality = Column(
        SAEnum("CXR", "CT", name="imaging_modality"),
        nullable=False,
        default="CXR",
    )
    file_path = Column(String(512), nullable=False)
    original_filename = Column(String(255), nullable=True)
    sha256 = Column(String(64), nullable=False)
    quality_flag = Column(String(50), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    case = relationship("Case", back_populates="imaging_studies")


# ─────────────────────────────────────────────────────────────────
# M3 — ecg_records
# ─────────────────────────────────────────────────────────────────

class ECGRecord(Base):
    __tablename__ = "ecg_records"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    case_id = Column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    file_path = Column(String(512), nullable=False)
    original_filename = Column(String(255), nullable=True)
    sha256 = Column(String(64), nullable=False)
    sampling_rate = Column(Float, nullable=True)
    num_leads = Column(Integer, nullable=True)
    quality_flag = Column(String(50), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    case = relationship("Case", back_populates="ecg_records")


# ─────────────────────────────────────────────────────────────────
# M5/M6/M7 — predictions
# ─────────────────────────────────────────────────────────────────

class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    case_id = Column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    source = Column(
        SAEnum("image", "ecg", "fusion", name="prediction_source"),
        nullable=False,
    )
    label = Column(String(100), nullable=False)
    probability = Column(Float, nullable=False)
    above_threshold = Column(Boolean, nullable=True)
    model_id = Column(
        String(36),
        ForeignKey("model_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    inference_ms = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    case = relationship("Case", back_populates="predictions")
    model_version = relationship("ModelVersion", back_populates="predictions")
    explanations = relationship(
        "Explanation", back_populates="prediction", cascade="all, delete-orphan"
    )


# ─────────────────────────────────────────────────────────────────
# M8 — explanations
# ─────────────────────────────────────────────────────────────────

class Explanation(Base):
    __tablename__ = "explanations"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    prediction_id = Column(
        String(36), ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False
    )
    type = Column(
        SAEnum("gradcam", "saliency", name="explanation_type"),
        nullable=False,
    )
    file_path = Column(String(512), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    prediction = relationship("Prediction", back_populates="explanations")


# ─────────────────────────────────────────────────────────────────
# M9 — reports
# ─────────────────────────────────────────────────────────────────

class Report(Base):
    __tablename__ = "reports"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    case_id = Column(
        String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False
    )
    file_path = Column(String(512), nullable=True)
    remarks = Column(Text, nullable=True)
    generated_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    case = relationship("Case", back_populates="reports")


# ─────────────────────────────────────────────────────────────────
# M10 — model_versions
# ─────────────────────────────────────────────────────────────────

class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    name = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    dataset = Column(String(100), nullable=True)
    val_auroc = Column(Float, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    predictions = relationship("Prediction", back_populates="model_version")


# ─────────────────────────────────────────────────────────────────
# M10 — audit_logs
# ─────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action = Column(String(100), nullable=False)
    target_id = Column(String(36), nullable=True)
    detail = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    user = relationship("User", back_populates="audit_logs")
