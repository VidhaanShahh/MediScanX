"""
Tests for M7 — Multimodal Fusion (P3 Algorithm A7).

Covers:
- Image-only fusion
- ECG-only fusion
- Dual-modality fusion (AUROC weighted)
- Disagreement threshold
- Risk band boundaries
- Missing modality handling
- API integration
- Persistence
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.models import Case, Prediction
from app.services.fusion.fusion_service import (
    fuse,
    compute_image_risk,
    compute_ecg_risk,
    classify_risk_band,
    BAND_LOW_UPPER,
    BAND_MOD_UPPER,
    DEFAULT_WEIGHT_IMAGE,
    DEFAULT_WEIGHT_ECG,
)

# ── 1. Unit Tests for Core Logic (A-F) ──────────────────────────────

def test_compute_image_risk():
    """Test p_img calculation: max(Cardiomegaly, Edema, Effusion)."""
    probs = {
        "Cardiomegaly": 0.1,
        "Edema": 0.5,
        "Effusion": 0.3,
        "Atelectasis": 0.9,  # Should be ignored
    }
    p_img = compute_image_risk(probs)
    assert p_img == 0.5


def test_compute_ecg_risk():
    """Test p_ecg calculation: 1 - NORM."""
    probs = {
        "NORM": 0.2,
        "MI": 0.8,
    }
    p_ecg = compute_ecg_risk(probs)
    assert pytest.approx(p_ecg) == 0.8


def test_risk_band_boundaries():
    """Test strict risk band boundaries."""
    assert classify_risk_band(0.0) == "Low"
    assert classify_risk_band(BAND_LOW_UPPER - 0.001) == "Low"
    assert classify_risk_band(BAND_LOW_UPPER) == "Moderate"
    assert classify_risk_band(BAND_MOD_UPPER - 0.001) == "Moderate"
    assert classify_risk_band(BAND_MOD_UPPER) == "High"
    assert classify_risk_band(1.0) == "High"


def test_fuse_image_only():
    """Test fusion with only imaging data."""
    img_probs = {"Cardiomegaly": 0.8, "Edema": 0.1, "Effusion": 0.2}
    result = fuse(imaging_probs=img_probs)
    
    assert result.available is True
    assert result.modality_used == "image_only"
    assert result.image_score == 0.8
    assert result.ecg_score is None
    assert result.fusion_score == 0.8
    assert result.risk_band == "High"
    assert result.disagreement is False
    assert result.difference is None
    assert result.source_image_weight is not None
    assert result.source_ecg_weight is not None


def test_fuse_ecg_only():
    """Test fusion with only ECG data."""
    ecg_probs = {"NORM": 0.9}
    result = fuse(ecg_probs=ecg_probs)
    
    assert result.available is True
    assert result.modality_used == "ecg_only"
    assert result.image_score is None
    assert pytest.approx(result.ecg_score) == 0.1
    assert pytest.approx(result.fusion_score) == 0.1
    assert result.risk_band == "Low"
    assert result.disagreement is False
    assert result.difference is None
    assert result.source_image_weight is not None
    assert result.source_ecg_weight is not None


def test_fuse_dual_modality():
    """Test dual-modality weighted fusion and disagreement."""
    img_probs = {"Cardiomegaly": 0.1, "Edema": 0.2, "Effusion": 0.3}  # p_img = 0.3
    ecg_probs = {"NORM": 0.1}  # p_ecg = 0.9
    
    # 0.3 and 0.9 have a difference of 0.6 (> 0.5), so they disagree
    
    result = fuse(
        imaging_probs=img_probs, 
        ecg_probs=ecg_probs,
        weight_image=0.80,
        weight_ecg=0.87,
    )
    
    assert result.available is True
    assert result.modality_used == "both"
    assert result.image_score == 0.3
    assert pytest.approx(result.ecg_score) == 0.9
    
    expected_score = (0.80 * 0.3 + 0.87 * 0.9) / (0.80 + 0.87)
    assert pytest.approx(result.fusion_score) == expected_score
    
    assert result.disagreement is True
    assert pytest.approx(result.difference) == 0.6
    assert result.source_image_weight == "provisional_srs_target"
    assert result.source_ecg_weight == "provisional_srs_target"


def test_fuse_disagreement_boundary():
    """Test the exact 0.5 disagreement boundary (should be > 0.5 to disagree)."""
    img_probs = {"Cardiomegaly": 0.7, "Edema": 0.0, "Effusion": 0.0} # 0.7
    ecg_probs = {"NORM": 0.8} # 1 - 0.8 = 0.2
    
    # Difference is exactly 0.5
    result = fuse(imaging_probs=img_probs, ecg_probs=ecg_probs)
    assert pytest.approx(result.difference) == 0.5
    assert result.disagreement is False # must be > 0.5


def test_fuse_missing_both():
    """Test fusion fails if both are missing."""
    with pytest.raises(ValueError, match="At least one modality"):
        fuse()


# ── 1.5 Unit Tests for Evaluation Metric Weighting ────────────────
def test_fuse_fallback_to_provisional_on_subset_metrics(monkeypatch):
    """Test that M7 falls back to provisional targets when only subset metrics exist."""
    def mock_load_results():
        return {
            "imaging_development_subset_auroc": 0.493,
            "ecg_cross_fold_subset_auroc": 0.951
        }
    monkeypatch.setattr("app.services.evaluation.metrics.load_evaluation_results", mock_load_results)
    
    img_probs = {"Cardiomegaly": 0.5, "Edema": 0.2, "Effusion": 0.2}
    ecg_probs = {"NORM": 0.8}
    result = fuse(imaging_probs=img_probs, ecg_probs=ecg_probs)
    
    assert result.source_image_weight == "provisional_srs_target"
    assert result.source_ecg_weight == "provisional_srs_target"
    assert result.weight_image == 0.80
    assert result.weight_ecg == 0.87

def test_fuse_uses_measured_test_auroc(monkeypatch):
    """Test that M7 correctly uses measured test AUROCs when explicitly available."""
    def mock_load_results():
        return {
            "imaging_measured_test_auroc": 0.85,
            "ecg_measured_test_auroc": 0.90,
            "imaging_development_subset_auroc": 0.493,  # Should ignore this
        }
    monkeypatch.setattr("app.services.evaluation.metrics.load_evaluation_results", mock_load_results)
    
    img_probs = {"Cardiomegaly": 0.5, "Edema": 0.2, "Effusion": 0.2}
    ecg_probs = {"NORM": 0.8}
    result = fuse(imaging_probs=img_probs, ecg_probs=ecg_probs)
    
    assert result.source_image_weight == "measured_test_auroc"
    assert result.source_ecg_weight == "measured_test_auroc"
    assert result.weight_image == 0.85
    assert result.weight_ecg == 0.90


# ── 2. Integration Tests (G, H) ──────────────────────────────────

def test_api_fusion_image_only(client: TestClient, auth_headers: dict):
    """Test API analysis endpoint with only image (M5 + M7)."""
    # 1. Setup case
    p_resp = client.post("/api/patients/", json={"full_name": "Test Patient", "anon_code": "TEST-FUSION-1"}, headers=auth_headers)
    patient_id = p_resp.json()["id"]
    c_resp = client.post("/api/cases/", json={"name": "Test Case", "patient_id": patient_id}, headers=auth_headers)
    case_id = c_resp.json()["id"]

    # 2. Upload image
    import io
    from PIL import Image
    img = Image.new("L", (224, 224), color=128)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    client.post(
        f"/api/cases/{case_id}/upload",
        files={"file": ("test_chest.png", io.BytesIO(buf.getvalue()), "image/png")},
        headers=auth_headers,
    )

    # 3. Analyze
    resp = client.post(
        f"/api/cases/{case_id}/analyze",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["status"] == "completed"
    assert data["imaging_predictions"] is not None
    assert data["ecg_predictions"] is None
    
    fusion = data["fusion"]
    assert fusion is not None
    assert fusion["available"] is True
    assert fusion["modality_used"] == "image_only"
    assert fusion["ecg_score"] is None
    assert fusion["disagreement"] is False
    assert fusion["screening_only"] is True


def test_api_fusion_ecg_only(client: TestClient, auth_headers: dict):
    """Test API analysis endpoint with only ECG (M6 + M7)."""
    # 1. Setup case
    p_resp = client.post("/api/patients/", json={"full_name": "Test Patient 2", "anon_code": "TEST-FUSION-2"}, headers=auth_headers)
    patient_id = p_resp.json()["id"]
    c_resp = client.post("/api/cases/", json={"name": "Test Case 2", "patient_id": patient_id}, headers=auth_headers)
    case_id = c_resp.json()["id"]

    # 2. Upload ECG
    import pandas as pd
    import numpy as np
    import io
    leads = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
    df = pd.DataFrame(np.random.randn(1000, 12), columns=leads)
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    client.post(
        f"/api/cases/{case_id}/upload",
        params={"file_type": "ecg"},
        files={"file": ("test_ecg.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=auth_headers,
    )

    # 3. Analyze
    resp = client.post(
        f"/api/cases/{case_id}/analyze",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["status"] == "completed"
    assert data["imaging_predictions"] is None
    assert data["ecg_predictions"] is not None
    
    fusion = data["fusion"]
    assert fusion is not None
    assert fusion["available"] is True
    assert fusion["modality_used"] == "ecg_only"
    assert fusion["image_score"] is None


def test_api_fusion_dual_modality(client: TestClient, auth_headers: dict):
    """Test API analysis endpoint with both image and ECG (M5 + M6 + M7)."""
    # 1. Setup case
    p_resp = client.post("/api/patients/", json={"full_name": "Test Patient 3", "anon_code": "TEST-FUSION-3"}, headers=auth_headers)
    patient_id = p_resp.json()["id"]
    c_resp = client.post("/api/cases/", json={"name": "Test Case 3", "patient_id": patient_id}, headers=auth_headers)
    case_id = c_resp.json()["id"]

    # 2. Upload Image
    import io
    from PIL import Image
    img = Image.new("L", (224, 224), color=128)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    client.post(
        f"/api/cases/{case_id}/upload",
        files={"file": ("test_chest.png", io.BytesIO(buf.getvalue()), "image/png")},
        headers=auth_headers,
    )

    # 3. Upload ECG
    import pandas as pd
    import numpy as np
    leads = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
    df = pd.DataFrame(np.random.randn(1000, 12), columns=leads)
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    client.post(
        f"/api/cases/{case_id}/upload",
        params={"file_type": "ecg"},
        files={"file": ("test_ecg.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=auth_headers,
    )

    # 4. Analyze
    resp = client.post(
        f"/api/cases/{case_id}/analyze",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["status"] == "completed"
    assert data["imaging_predictions"] is not None
    assert data["ecg_predictions"] is not None
    
    fusion = data["fusion"]
    assert fusion is not None
    assert fusion["available"] is True
    assert fusion["modality_used"] == "both"
    assert fusion["image_score"] is not None
    assert fusion["ecg_score"] is not None
    assert fusion["difference"] is not None
    assert "disagreement" in fusion
