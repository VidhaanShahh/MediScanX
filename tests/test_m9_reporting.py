import pytest
import os
from pathlib import Path
from app.models.models import User, Patient, Case, Prediction, Explanation

@pytest.fixture
def setup_data(db):
    import uuid
    u = User(email=f"m9_tester_{uuid.uuid4().hex[:6]}@example.com", password_hash="hash", role="admin")
    db.add(u)
    p = Patient(anon_code=f"M9_{uuid.uuid4().hex[:6]}", age=50, sex="M")
    db.add(p)
    db.commit()
    
    # Cases
    c_img = Case(patient_id=p.id, created_by=u.id)
    c_ecg = Case(patient_id=p.id, created_by=u.id)
    c_both = Case(patient_id=p.id, created_by=u.id)
    c_none = Case(patient_id=p.id, created_by=u.id)
    
    db.add_all([c_img, c_ecg, c_both, c_none])
    db.commit()
    
    # Add predictions
    pred_img = Prediction(case_id=c_img.id, source="image", label="Infiltration", probability=0.8, above_threshold=True)
    pred_ecg = Prediction(case_id=c_ecg.id, source="ecg", label="NORM", probability=0.9, above_threshold=True)
    pred_both_i = Prediction(case_id=c_both.id, source="image", label="Atelectasis", probability=0.6, above_threshold=True)
    pred_both_e = Prediction(case_id=c_both.id, source="ecg", label="MI", probability=0.7, above_threshold=True)
    pred_both_f = Prediction(case_id=c_both.id, source="fusion", label="High risk", probability=0.85, above_threshold=True)
    
    db.add_all([pred_img, pred_ecg, pred_both_i, pred_both_e, pred_both_f])
    db.commit()
    
    # Explanations (fake paths for testing, missing shouldn't break)
    db.add(Explanation(prediction_id=pred_img.id, type="gradcam", file_path="missing.png"))
    db.commit()

    return {
        "user": u, "c_img": c_img, "c_ecg": c_ecg, "c_both": c_both, "c_none": c_none
    }

def test_missing_analysis_fails(client, setup_data, auth_headers):
    c_none = setup_data["c_none"]
    
    resp = client.post(f"/api/reports/cases/{c_none.id}/generate", headers=auth_headers)
    assert resp.status_code == 400
    assert "No analysis results available" in resp.json()["detail"]

def test_generate_image_only_pdf(client, setup_data, auth_headers):
    c_img = setup_data["c_img"]
    resp = client.post(f"/api/reports/cases/{c_img.id}/generate", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "file_path" in data
    
    # Verify PDF
    pdf_path = data["file_path"]
    assert os.path.exists(pdf_path)
    assert os.path.getsize(pdf_path) > 0
    assert "MediScanX_" in pdf_path
    
    # Verify assets
    save_dir = os.path.dirname(pdf_path)
    assert os.path.exists(os.path.join(save_dir, f"{c_img.id}_XRAY_ORIGINAL.png")) is False # False because no image in test case originally
    assert os.path.exists(os.path.join(save_dir, f"{c_img.id}_XRAY_GRADCAM.png")) is False

def test_generate_ecg_only_pdf(client, setup_data, auth_headers):
    c_ecg = setup_data["c_ecg"]
    resp = client.post(f"/api/reports/cases/{c_ecg.id}/generate", headers=auth_headers)
    assert resp.status_code == 200
    
    pdf_path = resp.json()["file_path"]
    assert os.path.exists(pdf_path)
    assert "MediScanX_" in pdf_path

def test_generate_dual_modality_pdf(client, setup_data, auth_headers):
    c_both = setup_data["c_both"]
    resp = client.post(f"/api/reports/cases/{c_both.id}/generate", headers=auth_headers)
    assert resp.status_code == 200
    
    pdf_path = resp.json()["file_path"]
    assert os.path.exists(pdf_path)
    assert "MediScanX_" in pdf_path
