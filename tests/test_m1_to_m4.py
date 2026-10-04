"""
MediScanX — Unit tests for M1–M4.

Tests:
    1.  Password hashing
    2.  JWT generation / validation
    3.  Protected route returns 401 without token
    4.  Image validation accepts valid PNG
    5.  20 MB file-size limit
    6.  Invalid (corrupt) image rejection
    7.  SHA-256 hash computation
    8.  Image preprocessing → (224, 224, 3)
    9.  ECG preprocessing runs correctly
    10. ECG preprocessing → (12, 1000)
    11. Invalid ECG rejection (wrong number of leads)
"""

import hashlib
import io
import os
import sys

import cv2
import numpy as np
import pytest

# ════════════════════════════════════════════════════════════════
# 1. Password hashing
# ════════════════════════════════════════════════════════════════

def test_password_hashing():
    from app.core.security import hash_password, verify_password

    plain = "S3cureP@ss!"
    hashed = hash_password(plain)

    assert hashed != plain
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert verify_password(plain, hashed) is True
    assert verify_password("wrong", hashed) is False


# ════════════════════════════════════════════════════════════════
# 2. JWT generation and validation
# ════════════════════════════════════════════════════════════════

def test_jwt_generation_and_validation():
    from app.core.security import create_access_token, decode_access_token

    token = create_access_token(data={"sub": "user-123", "role": "user"})

    assert isinstance(token, str)
    assert len(token) > 10

    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "user-123"
    assert payload["role"] == "user"
    assert "exp" in payload


def test_jwt_invalid_token():
    from app.core.security import decode_access_token

    result = decode_access_token("totally.invalid.token")
    assert result is None


# ════════════════════════════════════════════════════════════════
# 3. Protected route returns 401 without token
# ════════════════════════════════════════════════════════════════

def test_protected_route_requires_auth(client):
    resp = client.get("/api/patients/")
    assert resp.status_code == 401


def test_protected_route_with_valid_token(client, auth_headers):
    resp = client.get("/api/patients/", headers=auth_headers)
    assert resp.status_code == 200


# ════════════════════════════════════════════════════════════════
# 4. Image validation — valid PNG
# ════════════════════════════════════════════════════════════════

def _make_png_bytes(width=256, height=256) -> bytes:
    """Create a synthetic valid PNG image in memory."""
    from PIL import Image as PILImage

    img = PILImage.fromarray(
        np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_image_validation_valid_png():
    from app.services.upload_service import validate_image

    png_bytes = _make_png_bytes(512, 512)
    result = validate_image(png_bytes, "chest.png")

    assert result["width"] == 512
    assert result["height"] == 512
    assert len(result["sha256"]) == 64


# ════════════════════════════════════════════════════════════════
# 5. 20 MB file-size limit
# ════════════════════════════════════════════════════════════════

def test_file_size_limit():
    from app.services.upload_service import validate_image
    from app.core.exceptions import ValidationError

    # Create a 21 MB blob (just random bytes — will also fail decode)
    big = b"\x00" * (21 * 1024 * 1024)
    with pytest.raises(ValidationError, match="too large"):
        validate_image(big, "huge.png")


# ════════════════════════════════════════════════════════════════
# 6. Invalid / corrupt image rejection
# ════════════════════════════════════════════════════════════════

def test_invalid_image_rejection():
    from app.services.upload_service import validate_image
    from app.core.exceptions import ValidationError

    garbage = b"this is definitely not a PNG"
    with pytest.raises(ValidationError, match="corrupt"):
        validate_image(garbage, "bad.png")


def test_unsupported_extension():
    from app.services.upload_service import validate_image
    from app.core.exceptions import ValidationError

    with pytest.raises(ValidationError, match="Unsupported"):
        validate_image(b"data", "file.bmp")


# ════════════════════════════════════════════════════════════════
# 7. SHA-256 hash
# ════════════════════════════════════════════════════════════════

def test_sha256_hash():
    from app.services.upload_service import compute_sha256

    data = b"hello mediscanx"
    expected = hashlib.sha256(data).hexdigest()
    assert compute_sha256(data) == expected
    assert len(compute_sha256(data)) == 64


# ════════════════════════════════════════════════════════════════
# 8. Image preprocessing → (224, 224, 3)
# ════════════════════════════════════════════════════════════════

def test_image_preprocessing_shape():
    from app.services.preprocessing.image import preprocess_image

    # Create a synthetic 512×512 grayscale image
    raw = np.random.randint(50, 200, (512, 512), dtype=np.uint8)
    tensor, poor = preprocess_image(raw)

    assert tensor.shape == (224, 224, 3)
    assert tensor.dtype == np.float32
    assert isinstance(poor, bool)


def test_image_preprocessing_with_clahe():
    from app.services.preprocessing.image import preprocess_image

    raw = np.random.randint(50, 200, (300, 400), dtype=np.uint8)
    tensor, poor = preprocess_image(raw, use_clahe=True)

    assert tensor.shape == (224, 224, 3)


def test_image_preprocessing_3channel_input():
    """3-channel colour input should still produce (224, 224, 3)."""
    from app.services.preprocessing.image import preprocess_image

    raw = np.random.randint(0, 255, (400, 400, 3), dtype=np.uint8)
    tensor, poor = preprocess_image(raw)

    assert tensor.shape == (224, 224, 3)


def test_image_preprocessing_low_contrast():
    """Near-uniform image should be flagged as poor quality."""
    from app.services.preprocessing.image import preprocess_image

    # Very uniform image (std < 10)
    raw = np.full((256, 256), 128, dtype=np.uint8)
    tensor, poor = preprocess_image(raw)

    assert poor is True
    assert tensor.shape == (224, 224, 3)


def test_image_preprocessing_from_bytes():
    """Preprocessing should accept raw PNG bytes too."""
    from app.services.preprocessing.image import preprocess_image

    png_bytes = _make_png_bytes(256, 256)
    tensor, poor = preprocess_image(png_bytes)
    assert tensor.shape == (224, 224, 3)


# ════════════════════════════════════════════════════════════════
# 9. ECG preprocessing
# ════════════════════════════════════════════════════════════════

def test_ecg_preprocessing_runs():
    from app.services.preprocessing.ecg import preprocess_ecg

    # 10 seconds at 100 Hz, 12 leads
    signal = np.random.randn(1000, 12)
    output, flags = preprocess_ecg(signal, fs=100)

    assert output.shape == (12, 1000)
    assert output.dtype == np.float32
    assert isinstance(flags, dict)


def test_ecg_preprocessing_resamples():
    """Signal at 500 Hz should be resampled to 100 Hz."""
    from app.services.preprocessing.ecg import preprocess_ecg

    # 10 seconds at 500 Hz = 5000 samples
    signal = np.random.randn(5000, 12)
    output, flags = preprocess_ecg(signal, fs=500)

    assert output.shape == (12, 1000)


def test_ecg_preprocessing_pads_short():
    """Short signal should be zero-padded to 1000 samples."""
    from app.services.preprocessing.ecg import preprocess_ecg

    signal = np.random.randn(300, 12)
    output, flags = preprocess_ecg(signal, fs=100)

    assert output.shape == (12, 1000)


def test_ecg_preprocessing_trims_long():
    """Long signal should be trimmed to 1000 samples."""
    from app.services.preprocessing.ecg import preprocess_ecg

    signal = np.random.randn(2000, 12)
    output, flags = preprocess_ecg(signal, fs=100)

    assert output.shape == (12, 1000)


def test_ecg_flat_lead_flagged():
    """A flat lead (all zeros) should be flagged."""
    from app.services.preprocessing.ecg import preprocess_ecg

    signal = np.random.randn(1000, 12)
    signal[:, 3] = 0.0  # make lead 4 (aVR) flat

    output, flags = preprocess_ecg(signal, fs=100)
    assert "aVR" in flags


# ════════════════════════════════════════════════════════════════
# 10. ECG preprocessing output shape — 12 × 1000
# ════════════════════════════════════════════════════════════════

def test_ecg_output_exact_shape():
    from app.services.preprocessing.ecg import preprocess_ecg

    signal = np.random.randn(1000, 12)
    output, _ = preprocess_ecg(signal, fs=100)

    assert output.shape[0] == 12, f"Expected 12 leads, got {output.shape[0]}"
    assert output.shape[1] == 1000, f"Expected 1000 samples, got {output.shape[1]}"


# ════════════════════════════════════════════════════════════════
# 11. Invalid ECG rejection
# ════════════════════════════════════════════════════════════════

def test_invalid_ecg_wrong_leads():
    from app.services.preprocessing.ecg import preprocess_ecg
    from app.core.exceptions import PreprocessingError

    # 8 leads instead of 12
    signal = np.random.randn(1000, 8)
    with pytest.raises(PreprocessingError, match="12 leads"):
        preprocess_ecg(signal, fs=100)


def test_invalid_ecg_1d_input():
    from app.services.preprocessing.ecg import preprocess_ecg
    from app.core.exceptions import PreprocessingError

    signal = np.random.randn(1000)
    with pytest.raises(PreprocessingError, match="2-D"):
        preprocess_ecg(signal, fs=100)


def test_ecg_csv_validation_wrong_columns():
    from app.services.upload_service import validate_ecg
    from app.core.exceptions import ValidationError

    # CSV with 8 columns
    csv_content = ",".join([f"lead{i}" for i in range(8)]) + "\n"
    csv_content += ",".join(["1.0"] * 8) + "\n"
    with pytest.raises(ValidationError, match="12 leads"):
        validate_ecg(csv_content.encode(), "bad.csv")


# ════════════════════════════════════════════════════════════════
# Auth API integration tests
# ════════════════════════════════════════════════════════════════

def test_register_and_login(client):
    resp = client.post("/api/auth/register", json={
        "name": "New User",
        "email": "newuser@test.com",
        "password": "SecurePass1!",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "id" in data
    assert data["email"] == "newuser@test.com"
    assert "password_hash" not in data  # never expose

    resp2 = client.post("/api/auth/login", json={
        "email": "newuser@test.com",
        "password": "SecurePass1!",
    })
    assert resp2.status_code == 200
    assert "access_token" in resp2.json()


def test_duplicate_registration(client, registered_user):
    resp = client.post("/api/auth/register", json={
        "name": "Test User",
        "email": "test@mediscanx.com",
        "password": "AnotherPass1!",
    })
    assert resp.status_code == 409


def test_login_wrong_password(client, registered_user):
    resp = client.post("/api/auth/login", json={
        "email": "test@mediscanx.com",
        "password": "WrongPassword!",
    })
    assert resp.status_code == 401


# ════════════════════════════════════════════════════════════════
# Patient + Case API integration tests
# ════════════════════════════════════════════════════════════════

def test_create_patient(client, auth_headers):
    resp = client.post("/api/patients/", json={
        "full_name": "Test Patient",
        "anon_code": "PAT-001",
        "age": 55,
        "sex": "M",
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["anon_code"] == "PAT-001"


def test_create_and_get_case(client, auth_headers):
    # Create patient first
    pr = client.post("/api/patients/", json={
        "full_name": "Test Patient 2",
        "anon_code": "PAT-002",
        "age": 30,
        "sex": "F",
    }, headers=auth_headers)
    patient_id = pr.json()["id"]

    # Create case
    cr = client.post("/api/cases", json={
        "name": "Test Case",
        "patient_id": patient_id,
    }, headers=auth_headers)
    assert cr.status_code == 201
    case_id = cr.json()["id"]

    # Get case
    gr = client.get(f"/api/cases/{case_id}", headers=auth_headers)
    assert gr.status_code == 200
    assert gr.json()["patient_id"] == patient_id


def test_delete_case(client, auth_headers):
    pr = client.post("/api/patients/", json={
        "full_name": "Test Patient 3",
        "anon_code": "PAT-003",
    }, headers=auth_headers)
    patient_id = pr.json()["id"]

    cr = client.post("/api/cases", json={
        "name": "Test Case",
        "patient_id": patient_id,
    }, headers=auth_headers)
    case_id = cr.json()["id"]

    dr = client.delete(f"/api/cases/{case_id}", headers=auth_headers)
    assert dr.status_code == 204

    # Should be gone
    gr = client.get(f"/api/cases/{case_id}", headers=auth_headers)
    assert gr.status_code == 404
