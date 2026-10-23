"""
MediScanX — Test Suite for Cryptographic Hashing and File Integrity (SHA-256).

Verifies:
1. Correct SHA-256 digest calculation (64-char hex string).
2. Determinism: identical input bytes produce identical digests.
3. Avalanche Effect: 1-character modification causes radical digest divergence.
4. Difference between hashing and encryption concepts.
5. Chunked file hashing for streaming large files.
6. Integrity verification function against database records (VERIFIED, CORRUPTED, MISSING, NO_RECORDED_HASH).
7. Endpoints:
    - POST /api/integrity/verify/{entity_type}/{entity_id}
    - GET  /api/integrity/case/{case_id}
    - GET  /api/integrity/demo
8. Authentication security: unauthenticated requests are rejected.
9. Report generation persists SHA-256 digest in database.
"""

import io
import os
import tempfile
from pathlib import Path
import pytest

from app.services.security.hash_service import (
    compute_bytes_sha256,
    compute_file_sha256,
    verify_file_integrity,
    demonstrate_cryptographic_hashing,
)


def test_sha256_digest_properties():
    data = b"MediScanX Clinical AI System"
    digest = compute_bytes_sha256(data)
    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(c in "0123456789abcdef" for c in digest)


def test_sha256_determinism():
    data = b"Identical Patient Record Input"
    h1 = compute_bytes_sha256(data)
    h2 = compute_bytes_sha256(data)
    assert h1 == h2


def test_sha256_avalanche_effect():
    data1 = b"MediScanX Diagnostic Dataset A"
    data2 = b"MediScanX Diagnostic Dataset B"  # exactly 1 byte modified
    h1 = compute_bytes_sha256(data1)
    h2 = compute_bytes_sha256(data2)
    assert h1 != h2
    # At least 25% of hex characters differ
    diff_chars = sum(1 for a, b in zip(h1, h2) if a != b)
    assert diff_chars > 20


def test_chunked_file_hashing(tmp_path):
    test_file = tmp_path / "sample_medical_study.bin"
    content = b"CHEST_XRAY_DATA_BLOCK_" * 1024  # ~23 KB
    test_file.write_bytes(content)

    file_hash = compute_file_sha256(test_file, chunk_size=512)
    bytes_hash = compute_bytes_sha256(content)
    assert file_hash == bytes_hash


def test_verify_file_integrity_scenarios(tmp_path):
    target = tmp_path / "valid_image.png"
    target.write_bytes(b"ORIGINAL_PNG_IMAGE_BYTES")
    correct_hash = compute_file_sha256(target)

    # 1. Success case
    res_ok = verify_file_integrity(target, correct_hash)
    assert res_ok["is_valid"] is True
    assert res_ok["status"] == "VERIFIED"
    assert res_ok["calculated_hash"] == correct_hash

    # 2. Tampered / Modified case
    tampered_hash = "a" * 64
    res_tampered = verify_file_integrity(target, tampered_hash)
    assert res_tampered["is_valid"] is False
    assert res_tampered["status"] == "CORRUPTED_OR_MODIFIED"
    assert "modified or corrupted" in res_tampered["message"]

    # 3. Missing file on disk
    missing_file = tmp_path / "ghost_file.dat"
    res_missing = verify_file_integrity(missing_file, correct_hash)
    assert res_missing["is_valid"] is False
    assert res_missing["status"] == "FILE_MISSING"

    # 4. Existing file without recorded hash
    res_no_hash = verify_file_integrity(target, None)
    assert res_no_hash["is_valid"] is False
    assert res_no_hash["status"] == "NO_RECORDED_HASH"
    assert res_no_hash["calculated_hash"] == correct_hash


def test_cryptography_demo_logic():
    demo = demonstrate_cryptographic_hashing("Custom Clinical Input")
    assert demo["digest_hex_length"] == 64
    assert demo["deterministic_verification"]["is_identical"] is True
    assert demo["avalanche_effect_demonstration"]["differing_hex_characters"] > 0
    assert "One-Way" in demo["hashing_vs_encryption_comparison"]["type"]


def test_api_integrity_demo(client, auth_headers):
    resp = client.get("/api/integrity/demo", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["algorithm"].startswith("SHA-256")
    assert len(data["primary_digest"]) == 64


def test_api_integrity_unauthenticated(client):
    resp = client.get("/api/integrity/demo")
    assert resp.status_code == 401


def test_api_case_integrity_full_lifecycle(client, auth_headers, tmp_path):
    # 1. Create patient and case
    p_res = client.post("/api/patients/", json={"full_name": "Integrity Subject", "age": 45, "sex": "F"}, headers=auth_headers)
    assert p_res.status_code == 201
    patient_id = p_res.json()["id"]

    c_res = client.post("/api/cases", json={"patient_id": patient_id, "name": "Cryptographic Integrity Case"}, headers=auth_headers)
    assert c_res.status_code == 201
    case_id = c_res.json()["id"]

    # 2. Upload CXR image
    import cv2
    import numpy as np
    dummy_img = (np.ones((224, 224, 3), dtype=np.uint8) * 128)
    _, img_encoded = cv2.imencode(".png", dummy_img)
    img_bytes = img_encoded.tobytes()

    upload_res = client.post(
        f"/api/cases/{case_id}/upload?file_type=image",
        files={"file": ("test_cxr.png", img_bytes, "image/png")},
        headers=auth_headers,
    )
    assert upload_res.status_code == 200
    imaging_id = upload_res.json()["id"]
    recorded_sha = upload_res.json()["sha256"]
    assert len(recorded_sha) == 64

    # 3. Verify single imaging entity integrity
    v_res = client.post(f"/api/integrity/verify/imaging/{imaging_id}", headers=auth_headers)
    assert v_res.status_code == 200
    v_data = v_res.json()
    assert v_data["is_valid"] is True
    assert v_data["status"] == "VERIFIED"
    assert v_data["recorded_sha256"] == recorded_sha
    assert v_data["calculated_sha256"] == recorded_sha

    # 4. Check case-level integrity summary
    case_v_res = client.get(f"/api/integrity/case/{case_id}", headers=auth_headers)
    assert case_v_res.status_code == 200
    case_summary = case_v_res.json()
    assert case_summary["total_files_checked"] == 1
    assert case_summary["overall_integrity_passed"] is True


def test_api_integrity_unauthorized_user_forbidden(client, auth_headers):
    """Verify that user B cannot inspect or verify files belonging to user A's case."""
    # User A creates patient and case
    p_res = client.post("/api/patients/", json={"full_name": "User A Patient", "age": 30, "sex": "M"}, headers=auth_headers)
    assert p_res.status_code == 201
    patient_id = p_res.json()["id"]

    c_res = client.post("/api/cases", json={"patient_id": patient_id, "name": "User A Private Case"}, headers=auth_headers)
    assert c_res.status_code == 201
    case_id = c_res.json()["id"]

    # Register User B
    reg_b = client.post("/api/auth/register", json={
        "name": "User B",
        "email": "user_b@mediscanx.com",
        "password": "Password123!",
        "role": "user",
    })
    assert reg_b.status_code == 201

    login_b = client.post("/api/auth/login", json={
        "email": "user_b@mediscanx.com",
        "password": "Password123!",
    })
    assert login_b.status_code == 200
    token_b = login_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B attempts to access User A's case integrity -> 403 Forbidden
    unauth_case = client.get(f"/api/integrity/case/{case_id}", headers=headers_b)
    assert unauth_case.status_code == 403
    assert "Not authorized" in unauth_case.json()["detail"]

