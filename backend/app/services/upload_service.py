"""
MediScanX — M3 Upload validation service.

Implements Algorithm A1 from P3 exactly:
  - Check file size (<= 20 MB)
  - For images: validate extension, decode content, check dimensions, DICOM anonymisation
  - For ECG: validate CSV (12 leads) or WFDB format
  - Compute SHA-256 hash
"""

import hashlib
import io
import tempfile
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from PIL import Image

from app.core.config import settings
from app.core.exceptions import ValidationError


# Tags to remove from DICOM headers for anonymisation (FR-3.5)
DICOM_SENSITIVE_TAGS = [
    (0x0010, 0x0010),  # PatientName
    (0x0010, 0x0020),  # PatientID
    (0x0010, 0x0030),  # PatientBirthDate
    (0x0010, 0x0040),  # PatientSex (keep age/sex from our schema, not DICOM)
    (0x0010, 0x1000),  # OtherPatientIDs
    (0x0010, 0x1001),  # OtherPatientNames
    (0x0008, 0x0080),  # InstitutionName
    (0x0008, 0x0081),  # InstitutionAddress
    (0x0008, 0x0090),  # ReferringPhysicianName
    (0x0008, 0x1050),  # PerformingPhysicianName
]


def compute_sha256(data: bytes) -> str:
    """Return the hex-digest SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


# ─────────────────────────────────────────────────────────────────
# Image validation
# ─────────────────────────────────────────────────────────────────

def validate_image(file_bytes: bytes, filename: str) -> dict:
    """
    Validate an uploaded image file (JPEG / PNG / DICOM).

    Returns dict with keys: width, height, channels, sha256, modality, dicom_metadata.
    Raises ValidationError on failure.
    """
    ext = Path(filename).suffix.lower()

    if len(file_bytes) > settings.max_upload_bytes:
        raise ValidationError(
            f"File too large ({len(file_bytes) / 1024 / 1024:.1f} MB). "
            f"Maximum is {settings.MAX_UPLOAD_SIZE_MB} MB."
        )

    if ext in (".dcm", ".dicom"):
        return _validate_dicom(file_bytes)
    elif ext in (".jpg", ".jpeg", ".png"):
        return _validate_standard_image(file_bytes, ext)
    else:
        raise ValidationError(
            f"Unsupported image type '{ext}'. Accepted: jpg, jpeg, png, dcm."
        )


def _validate_standard_image(file_bytes: bytes, ext: str) -> dict:
    """Decode JPEG/PNG and validate content."""
    try:
        buf = np.frombuffer(file_bytes, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValidationError("Image is corrupt or cannot be decoded.")
    except ValidationError:
        raise
    except Exception:
        raise ValidationError("Image is corrupt or cannot be decoded.")

    h, w = img.shape[:2]
    if min(h, w) < 128:
        raise ValidationError(
            f"Image too small ({w}x{h}). Minimum dimension is 128 px."
        )

    channels = 1 if img.ndim == 2 else img.shape[2]

    return {
        "width": w,
        "height": h,
        "channels": channels,
        "sha256": compute_sha256(file_bytes),
        "modality": "CXR",
        "dicom_metadata": None,
    }


def _validate_dicom(file_bytes: bytes) -> dict:
    """Parse DICOM, remove sensitive tags, validate pixel data."""
    try:
        import pydicom
    except ImportError:
        raise ValidationError("DICOM support requires pydicom to be installed.")

    try:
        ds = pydicom.dcmread(io.BytesIO(file_bytes))
    except Exception:
        raise ValidationError("DICOM file is corrupt or cannot be parsed.")

    if not hasattr(ds, "pixel_array"):
        raise ValidationError("DICOM file has no pixel data.")

    arr = ds.pixel_array
    h, w = arr.shape[:2]
    if min(h, w) < 128:
        raise ValidationError(
            f"DICOM image too small ({w}x{h}). Minimum dimension is 128 px."
        )

    # Anonymise: remove sensitive tags (FR-3.5)
    safe_meta = {}
    for tag in DICOM_SENSITIVE_TAGS:
        if tag in ds:
            del ds[tag]
    # Keep useful non-sensitive metadata
    for key in ("Modality", "Rows", "Columns", "BitsAllocated"):
        if hasattr(ds, key):
            safe_meta[key] = str(getattr(ds, key))

    channels = 1 if arr.ndim == 2 else arr.shape[2]

    return {
        "width": w,
        "height": h,
        "channels": channels,
        "sha256": compute_sha256(file_bytes),
        "modality": safe_meta.get("Modality", "CXR"),
        "dicom_metadata": safe_meta,
    }


# ─────────────────────────────────────────────────────────────────
# ECG validation
# ─────────────────────────────────────────────────────────────────

def validate_ecg(file_bytes: bytes, filename: str) -> dict:
    """
    Validate an uploaded ECG file (CSV or WFDB).

    Returns dict with keys: num_leads, num_samples, sampling_rate, sha256.
    Raises ValidationError on failure.
    """
    ext = Path(filename).suffix.lower()

    if len(file_bytes) > settings.max_upload_bytes:
        raise ValidationError(
            f"File too large ({len(file_bytes) / 1024 / 1024:.1f} MB). "
            f"Maximum is {settings.MAX_UPLOAD_SIZE_MB} MB."
        )

    if ext == ".csv":
        return _validate_ecg_csv(file_bytes)
    elif ext in (".hea", ".dat"):
        return _validate_ecg_wfdb(file_bytes, filename)
    else:
        raise ValidationError(
            f"Unsupported ECG type '{ext}'. Accepted: csv, hea, dat."
        )


def _validate_ecg_csv(file_bytes: bytes) -> dict:
    """Parse CSV with one column per lead and validate 12-lead structure."""
    import pandas as pd

    try:
        df = pd.read_csv(io.BytesIO(file_bytes))
    except Exception:
        raise ValidationError("CSV file is corrupt or cannot be parsed.")

    if df.shape[1] != 12:
        raise ValidationError(
            f"ECG must have exactly 12 leads, but found {df.shape[1]} columns."
        )

    # Check for valid numeric data
    if not all(np.issubdtype(df[col].dtype, np.number) for col in df.columns):
        raise ValidationError("All ECG lead columns must contain numeric data.")

    if df.isnull().all().any():
        raise ValidationError("One or more ECG leads contain only missing data.")

    return {
        "num_leads": 12,
        "num_samples": len(df),
        "sampling_rate": None,  # CSV has no built-in sampling-rate header
        "sha256": compute_sha256(file_bytes),
    }


def _validate_ecg_wfdb(file_bytes: bytes, filename: str) -> dict:
    """Parse WFDB .hea/.dat and validate 12-lead structure."""
    try:
        import wfdb
    except ImportError:
        raise ValidationError("WFDB support requires the wfdb package.")

    # WFDB expects files on disk — write temporarily
    stem = Path(filename).stem
    with tempfile.TemporaryDirectory() as tmpdir:
        # We need both .hea and .dat; for now handle the provided file
        target = Path(tmpdir) / Path(filename).name
        target.write_bytes(file_bytes)

        try:
            record = wfdb.rdrecord(str(Path(tmpdir) / stem))
        except Exception as exc:
            raise ValidationError(f"WFDB record cannot be read: {exc}")

        if record.n_sig != 12:
            raise ValidationError(
                f"ECG must have exactly 12 leads, but found {record.n_sig}."
            )

        return {
            "num_leads": record.n_sig,
            "num_samples": record.sig_len,
            "sampling_rate": record.fs,
            "sha256": compute_sha256(file_bytes),
        }
