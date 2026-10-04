"""
MediScanX — Unit and Integration tests for M6 (ECG AI Analysis).

Tests:
    1.  ECG model loads successfully from checkpoint
    2.  Model output has 5 superclasses (NORM, MI, STTC, CD, HYP)
    3.  Class names and threshold structure
    4.  Inference on synthetic signal (both 12×1000 and 1000×12 shapes)
    5.  Probabilities in valid range [0, 1] and threshold evaluation
    6.  Input validation rejects wrong dimensions and shapes
    7.  Input validation rejects non-ndarray input
    8.  Model metadata contains required keys and information
    9.  Singleton caching and reset functionality
    10. Heart rate estimation on synthetic periodic signal
    11. Heart rate estimation on real normal sinus rhythm (Record 00001)
    12. Heart rate estimation on real sinus bradycardia (Record 00002)
    13. Heart rate estimation handles flat or insufficient signals safely
    14. 12-lead ECG plot rendering produces valid base64 PNG data
    15. End-to-end inference on real PTB-XL record
    16. API integration: POST /api/cases/{id}/analyze with an ECG record
    17. API integration: POST /api/cases/{id}/analyze with both image and ECG
"""

import os
import sys
import base64
import numpy as np
import pytest

from app.core.exceptions import InferenceError

# ════════════════════════════════════════════════════════════════
# Paths and preconditions
# ════════════════════════════════════════════════════════════════

_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "models", "ecg", "ecg_model.keras"
)
_HAS_MODEL = os.path.isfile(_MODEL_PATH)

_SAMPLE_WFDB = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "PTB-XL",
    "records100",
    "records100",
    "00000",
    "00001_lr",
)
_HAS_SAMPLE_WFDB = os.path.isfile(f"{_SAMPLE_WFDB}.hea")

requires_ecg_model = pytest.mark.skipif(
    not _HAS_MODEL,
    reason="Pre-trained ECG model not found in models/ecg/",
)

requires_sample_ecg = pytest.mark.skipif(
    not _HAS_SAMPLE_WFDB,
    reason="Sample PTB-XL WFDB record not found",
)


# ════════════════════════════════════════════════════════════════
# 1. ECG model loads successfully
# ════════════════════════════════════════════════════════════════

@requires_ecg_model
def test_ecg_model_loads():
    from app.services.ecg.ecg_service import load_model, reset_model

    reset_model()
    model = load_model()
    assert model is not None


# ════════════════════════════════════════════════════════════════
# 2. Model has 5 output classes
# ════════════════════════════════════════════════════════════════

@requires_ecg_model
def test_model_has_5_superclasses():
    from app.services.ecg.ecg_service import load_model, N_CLASSES, SUPERCLASSES

    model = load_model()
    assert N_CLASSES == 5
    assert SUPERCLASSES == ["NORM", "MI", "STTC", "CD", "HYP"]


# ════════════════════════════════════════════════════════════════
# 3. Model metadata
# ════════════════════════════════════════════════════════════════

@requires_ecg_model
def test_model_metadata():
    from app.services.ecg.ecg_service import get_model_metadata

    meta = get_model_metadata()
    assert meta["num_classes"] == 5
    assert meta["class_names"] == ["NORM", "MI", "STTC", "CD", "HYP"]
    assert "thresholds" in meta
    assert meta["thresholds"]["NORM"] > 0
    assert meta["model_name"] == "PTB-XL-1D-CNN"


# ════════════════════════════════════════════════════════════════
# 4. Inference on synthetic signal (both shapes)
# ════════════════════════════════════════════════════════════════

@requires_ecg_model
def test_inference_synthetic_signal_shapes():
    from app.services.ecg.ecg_service import predict_ecg

    # Shape 1: (12, 1000) as returned by M4 preprocess_ecg
    sig_12x1000 = np.random.randn(12, 1000).astype(np.float32)
    res1 = predict_ecg(sig_12x1000, compute_hr=False, generate_plot=False)
    assert len(res1.predictions) == 5
    assert res1.num_classes == 5
    assert res1.inference_ms >= 0

    # Shape 2: (1000, 12) samples first
    sig_1000x12 = np.random.randn(1000, 12).astype(np.float32)
    res2 = predict_ecg(sig_1000x12, compute_hr=False, generate_plot=False)
    assert len(res2.predictions) == 5


# ════════════════════════════════════════════════════════════════
# 5. Probabilities in valid range & threshold evaluation
# ════════════════════════════════════════════════════════════════

@requires_ecg_model
def test_probabilities_in_valid_range():
    from app.services.ecg.ecg_service import predict_ecg

    sig = np.random.randn(12, 1000).astype(np.float32)
    res = predict_ecg(sig, compute_hr=False, generate_plot=False)

    for item in res.predictions:
        assert 0.0 <= item.probability <= 1.0
        assert item.threshold > 0.0
        assert item.above_threshold == (item.probability >= item.threshold)


# ════════════════════════════════════════════════════════════════
# 6. Input validation rejects invalid shapes
# ════════════════════════════════════════════════════════════════

@requires_ecg_model
def test_predict_rejects_invalid_shapes():
    from app.services.ecg.ecg_service import predict_ecg

    # 1D array
    with pytest.raises(InferenceError):
        predict_ecg(np.zeros(1000, dtype=np.float32))

    # 3D array
    with pytest.raises(InferenceError):
        predict_ecg(np.zeros((1, 12, 1000), dtype=np.float32))

    # Wrong number of leads
    with pytest.raises(InferenceError):
        predict_ecg(np.zeros((8, 1000), dtype=np.float32))

    # Wrong number of samples
    with pytest.raises(InferenceError):
        predict_ecg(np.zeros((12, 500), dtype=np.float32))


# ════════════════════════════════════════════════════════════════
# 7. Input validation rejects non-ndarray
# ════════════════════════════════════════════════════════════════

@requires_ecg_model
def test_predict_rejects_non_ndarray():
    from app.services.ecg.ecg_service import predict_ecg

    with pytest.raises(InferenceError):
        predict_ecg([[0.0] * 1000] * 12)  # type: ignore


# ════════════════════════════════════════════════════════════════
# 8. Singleton reuse and reset
# ════════════════════════════════════════════════════════════════

@requires_ecg_model
def test_singleton_reuse_and_reset():
    from app.services.ecg.ecg_service import load_model, reset_model

    reset_model()
    m1 = load_model()
    m2 = load_model()
    assert m1 is m2

    reset_model()
    m3 = load_model()
    assert m3 is not None


# ════════════════════════════════════════════════════════════════
# 9. Heart rate estimation: synthetic signal
# ════════════════════════════════════════════════════════════════

def test_heart_rate_estimation_synthetic():
    from app.services.ecg.ecg_service import estimate_heart_rate

    fs = 100.0
    t = np.arange(1000) / fs
    # Create synthetic periodic R-peaks at 1.0 Hz (60 bpm)
    # Filter is 5-15 Hz bandpass, so use a ~10 Hz burst at 1 Hz intervals
    signal = np.zeros(1000, dtype=np.float64)
    for beat_time in np.arange(0.5, 9.5, 1.0):
        idx = int(beat_time * fs)
        # Add a sharp QRS-like spike
        signal[idx - 2 : idx + 3] += np.array([2.0, 8.0, 15.0, 8.0, 2.0])

    bpm = estimate_heart_rate(signal, fs=fs)
    assert bpm is not None
    assert 55.0 <= bpm <= 65.0


# ════════════════════════════════════════════════════════════════
# 10. Heart rate estimation: real normal sinus rhythm (Record 00001)
# ════════════════════════════════════════════════════════════════

@requires_sample_ecg
def test_heart_rate_real_normal_record():
    import wfdb
    from app.services.ecg.ecg_service import estimate_heart_rate

    rec = wfdb.rdrecord(_SAMPLE_WFDB)
    lead_ii = rec.p_signal[:, 1]
    bpm = estimate_heart_rate(lead_ii, fs=rec.fs)

    assert bpm is not None
    # Normal adult resting HR is 60–100 bpm; record 1 is ~64 bpm
    assert 58.0 <= bpm <= 75.0


# ════════════════════════════════════════════════════════════════
# 11. Heart rate estimation: real sinus bradycardia (Record 00002)
# ════════════════════════════════════════════════════════════════

@requires_sample_ecg
def test_heart_rate_real_bradycardia_record():
    import wfdb
    from app.services.ecg.ecg_service import estimate_heart_rate

    rec_path = os.path.join(
        os.path.dirname(_SAMPLE_WFDB), "00002_lr"
    )
    if not os.path.isfile(f"{rec_path}.hea"):
        pytest.skip("Record 00002 not available")

    rec = wfdb.rdrecord(rec_path)
    lead_ii = rec.p_signal[:, 1]
    bpm = estimate_heart_rate(lead_ii, fs=rec.fs)

    assert bpm is not None
    # Record 2 is diagnosed with sinus bradycardia (HR < 60 bpm, measured ~45.8 bpm)
    assert bpm < 55.0


# ════════════════════════════════════════════════════════════════
# 12. Heart rate safe fallback on flat/invalid signal
# ════════════════════════════════════════════════════════════════

def test_heart_rate_safe_fallback():
    from app.services.ecg.ecg_service import estimate_heart_rate

    # Flat line
    assert estimate_heart_rate(np.zeros(1000)) is None
    # Too short
    assert estimate_heart_rate(np.ones(50)) is None
    # Empty
    assert estimate_heart_rate(np.array([])) is None


# ════════════════════════════════════════════════════════════════
# 13. 12-lead plot rendering
# ════════════════════════════════════════════════════════════════

def test_12_lead_plot_rendering():
    from app.services.ecg.ecg_service import render_ecg_plot

    sig = np.random.randn(12, 1000).astype(np.float32)
    b64_str = render_ecg_plot(sig, fs=100.0, title="Test Plot")

    assert isinstance(b64_str, str)
    assert len(b64_str) > 1000
    # Verify it decodes to valid PNG header bytes
    raw_png = base64.b64decode(b64_str)
    assert raw_png[:8] == b"\x89PNG\r\n\x1a\n"


# ════════════════════════════════════════════════════════════════
# 14. Real PTB-XL record end-to-end inference
# ════════════════════════════════════════════════════════════════

@requires_ecg_model
@requires_sample_ecg
def test_real_record_inference():
    import wfdb
    from app.services.preprocessing.ecg import preprocess_ecg
    from app.services.ecg.ecg_service import predict_ecg

    rec = wfdb.rdrecord(_SAMPLE_WFDB)
    raw_sig = rec.p_signal.astype(np.float32)

    preprocessed, flags = preprocess_ecg(raw_sig, fs=rec.fs)
    assert preprocessed.shape == (12, 1000)

    result = predict_ecg(preprocessed, fs=rec.fs, compute_hr=True, generate_plot=True)
    assert result.num_classes == 5
    assert len(result.predictions) == 5

    # Record 00001 is normal ECG; NORM probability should be high
    norm_pred = next(p for p in result.predictions if p.superclass == "NORM")
    assert norm_pred.probability > 0.5
    assert norm_pred.above_threshold is True

    # Heart rate and plot should be populated
    assert result.heart_rate_bpm is not None
    assert result.plot_image_base64 is not None


# ════════════════════════════════════════════════════════════════
# 15. API integration: Analyze case with ECG record
# ════════════════════════════════════════════════════════════════

@requires_ecg_model
@requires_sample_ecg
def test_api_analyze_ecg_case(client, auth_headers):
    # 1. Create a patient
    p_resp = client.post(
        "/api/patients/",
        json={"full_name": "Test Patient", "anon_code": "TEST-ECG-01", "age": 45, "sex": "M"},
        headers=auth_headers,
    )
    assert p_resp.status_code == 201
    patient_id = p_resp.json()["id"]

    # 2. Create a case
    c_resp = client.post(
        "/api/cases/",
        json={"name": "Test Case", "patient_id": patient_id},
        headers=auth_headers,
    )
    assert c_resp.status_code == 201
    case_id = c_resp.json()["id"]

    # 3. Create a synthetic 12-lead CSV for upload
    import io
    import pandas as pd
    leads = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
    df = pd.DataFrame(np.random.randn(1000, 12), columns=leads)
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    u_resp = client.post(
        f"/api/cases/{case_id}/upload",
        params={"file_type": "ecg"},
        files={"file": ("test_ecg.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=auth_headers,
    )
    assert u_resp.status_code == 200
    assert u_resp.json()["file_type"] == "ecg"

    # 4. Trigger analysis
    a_resp = client.post(
        f"/api/cases/{case_id}/analyze",
        headers=auth_headers,
    )
    assert a_resp.status_code == 200
    data = a_resp.json()
    assert data["case_id"] == case_id
    assert data["status"] == "completed"
    assert data["ecg_predictions"] is not None
    assert len(data["ecg_predictions"]["predictions"]) == 5
    assert data["ecg_predictions"]["num_classes"] == 5
    assert data["ecg_predictions"]["inference_ms"] > 0


# ════════════════════════════════════════════════════════════════
# 16. API integration: Dual modality case (Image + ECG)
# ════════════════════════════════════════════════════════════════

@requires_ecg_model
def test_api_analyze_dual_modality_case(client, auth_headers):
    # 1. Create patient and case
    p_resp = client.post(
        "/api/patients/",
        json={"full_name": "Test Patient 2", "anon_code": "TEST-DUAL-01", "age": 52, "sex": "F"},
        headers=auth_headers,
    )
    patient_id = p_resp.json()["id"]

    c_resp = client.post(
        "/api/cases/",
        json={"name": "Test Case 2", "patient_id": patient_id},
        headers=auth_headers,
    )
    case_id = c_resp.json()["id"]

    # 2. Upload synthetic 224x224 PNG image
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

    # 3. Upload synthetic 12-lead ECG CSV
    import pandas as pd
    leads = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
    df = pd.DataFrame(np.random.randn(1000, 12), columns=leads)
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    u_ecg = client.post(
        f"/api/cases/{case_id}/upload",
        params={"file_type": "ecg"},
        files={"file": ("test_ecg.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers=auth_headers,
    )
    assert u_ecg.status_code == 200

    # 4. Trigger analysis
    a_resp = client.post(
        f"/api/cases/{case_id}/analyze",
        headers=auth_headers,
    )
    assert a_resp.status_code == 200
    data = a_resp.json()
    assert data["case_id"] == case_id
    assert data["status"] == "completed"
    assert data["imaging_predictions"] is not None
    assert data["ecg_predictions"] is not None
    assert len(data["imaging_predictions"]["predictions"]) == 14
    assert len(data["ecg_predictions"]["predictions"]) == 5
