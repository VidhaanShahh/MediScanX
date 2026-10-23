"""
Tests for Core Computer Science Enhancements:
- Cross-Modal Contradiction and Consistency Engine
- Real DBMS Query Demonstrations & ACID Transaction Rollback
- Patient History Timeline
- Clinical Review Workflow
- COA Hardware/Runtime Inference Benchmark
"""

import uuid
import pytest
from app.services.fusion.cross_modal_service import (
    evaluate_cross_modal_consistency,
    CATEGORY_CONSISTENT,
    CATEGORY_CONFLICT,
    CATEGORY_INSUFFICIENT,
    CATEGORY_INCOMPARABLE,
    CATEGORY_UNAVAILABLE,
    CATEGORY_REVIEW_REQUIRED,
)
from app.models.models import Case, Patient, User, CrossModalConsistency, ClinicalReview


def test_cross_modal_both_missing():
    result = evaluate_cross_modal_consistency(None, None)
    assert result.category == CATEGORY_UNAVAILABLE
    assert result.requires_human_review is False


def test_cross_modal_single_modality():
    # Only CXR
    img_probs = {"Cardiomegaly": 0.72, "Edema": 0.40}
    res_img = evaluate_cross_modal_consistency(img_probs, None)
    assert res_img.category == CATEGORY_INSUFFICIENT
    assert res_img.source_imaging_finding == "Cardiomegaly"

    # Only ECG
    ecg_probs = {"NORM": 0.88, "MI": 0.05}
    res_ecg = evaluate_cross_modal_consistency(None, ecg_probs)
    assert res_ecg.category == CATEGORY_INSUFFICIENT
    assert res_ecg.source_ecg_finding == "NORM"


def test_cross_modal_concordant_decompensation():
    # Corroborating CXR Edema + ECG MI
    img_probs = {"Cardiomegaly": 0.40, "Edema": 0.75, "Effusion": 0.30}
    ecg_probs = {"NORM": 0.05, "MI": 0.82, "HYP": 0.10, "STTC": 0.15, "CD": 0.05}
    result = evaluate_cross_modal_consistency(img_probs, ecg_probs)
    assert result.category == CATEGORY_CONSISTENT
    assert "Edema" in result.source_imaging_finding
    assert "MI" in result.source_ecg_finding


def test_cross_modal_discordance_conflict():
    # Marked structural enlargement on CXR with high normality on ECG
    img_probs = {"Cardiomegaly": 0.85, "Edema": 0.10, "Effusion": 0.05}
    ecg_probs = {"NORM": 0.92, "MI": 0.01, "HYP": 0.02, "STTC": 0.02, "CD": 0.03}
    result = evaluate_cross_modal_consistency(img_probs, ecg_probs)
    assert result.category == CATEGORY_CONFLICT
    assert result.requires_human_review is True
    assert result.source_imaging_finding == "Cardiomegaly"
    assert result.source_ecg_finding == "NORM"


def test_cross_modal_acute_infarction_alert():
    # High ECG MI with clear CXR lungs
    img_probs = {"Cardiomegaly": 0.10, "Edema": 0.05, "Effusion": 0.05}
    ecg_probs = {"NORM": 0.05, "MI": 0.80, "HYP": 0.10, "STTC": 0.05, "CD": 0.00}
    result = evaluate_cross_modal_consistency(img_probs, ecg_probs)
    assert result.category == CATEGORY_REVIEW_REQUIRED
    assert result.requires_human_review is True


def test_cross_modal_incomparable_pulmonary():
    # Pneumothorax on CXR vs ECG NORM
    img_probs = {"Pneumothorax": 0.78, "Cardiomegaly": 0.10, "Edema": 0.05}
    ecg_probs = {"NORM": 0.85, "MI": 0.02, "HYP": 0.03, "STTC": 0.05, "CD": 0.05}
    result = evaluate_cross_modal_consistency(img_probs, ecg_probs)
    assert result.category == CATEGORY_INCOMPARABLE
    assert result.source_imaging_finding == "Pneumothorax"


def test_dbms_api_stats_and_queries(client, auth_headers):
    # Test real database statistics endpoint
    res_stats = client.get("/api/dbms/stats", headers=auth_headers)
    assert res_stats.status_code == 200
    stats_data = res_stats.json()
    assert "database_engine" in stats_data
    assert "table_counts" in stats_data
    assert "cases" in stats_data["table_counts"]

    # Test list queries
    res_queries = client.get("/api/dbms/queries", headers=auth_headers)
    assert res_queries.status_code == 200
    queries_list = res_queries.json()
    assert len(queries_list) >= 5

    # Test parameterized query execution
    res_run = client.get("/api/dbms/query/modality_breakdown", headers=auth_headers)
    assert res_run.status_code == 200
    run_data = res_run.json()
    assert run_data["query_key"] == "modality_breakdown"
    assert "execution_time_ms" in run_data
    assert isinstance(run_data["rows"], list)


def test_dbms_transaction_verification(client, auth_headers):
    res_tx = client.post("/api/dbms/verify-transaction", headers=auth_headers)
    assert res_tx.status_code == 200
    tx_data = res_tx.json()
    assert tx_data["simulated_failure_triggered"] is True
    assert tx_data["rollback_verified"] is True
    assert tx_data["initial_patient_count"] == tx_data["final_patient_count"]


def test_patient_timeline_and_clinical_review(client, auth_headers):
    # 1. Create Patient
    p_res = client.post("/api/patients/", json={"full_name": "Test Subject", "age": 52, "sex": "M"}, headers=auth_headers)
    assert p_res.status_code == 201
    patient_id = p_res.json()["id"]

    # 2. Create Case
    c_res = client.post("/api/cases", json={"patient_id": patient_id, "name": "Timeline Test Case"}, headers=auth_headers)
    assert c_res.status_code == 201
    case_id = c_res.json()["id"]

    # 3. Submit Clinical Review
    rev_res = client.post(
        f"/api/cases/{case_id}/reviews",
        json={
            "status": "Reviewed",
            "findings_summary": "Clinician reviewed AI findings and concurred with low risk.",
            "agreed_with_ai": True,
            "notes": "Patient advised routine follow-up.",
        },
        headers=auth_headers,
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["status"] == "Reviewed"
    assert rev_res.json()["agreed_with_ai"] is True

    # 4. Verify Case Details has review
    case_detail_res = client.get(f"/api/cases/{case_id}", headers=auth_headers)
    assert case_detail_res.status_code == 200
    assert case_detail_res.json()["review_status"] == "Reviewed"
    assert len(case_detail_res.json()["reviews"]) >= 1

    # 5. Verify Patient Timeline
    tl_res = client.get(f"/api/patients/{patient_id}/timeline", headers=auth_headers)
    assert tl_res.status_code == 200
    tl_data = tl_res.json()
    assert tl_data["patient"]["id"] == patient_id
    assert len(tl_data["timeline"]) >= 1
    assert tl_data["timeline"][0]["review_status"] == "Reviewed"
