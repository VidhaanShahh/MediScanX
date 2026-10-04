import pytest
from app.models.models import AuditLog, User, Patient, Case

def test_admin_endpoint_unauthenticated(client):
    response = client.get("/api/admin/audit-logs")
    assert response.status_code == 403 or response.status_code == 401

def test_admin_endpoint_forbidden_for_normal_user(client, registered_user):
    # registered_user is a normal user
    user_data, password = registered_user
    email = user_data["email"]
    token = client.post("/api/auth/login", json={"email": email, "password": password}).json()["access_token"]
    response = client.get("/api/admin/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403

def test_admin_endpoint_success(client, db):
    # Create admin user
    from app.core.security import hash_password
    admin = User(email="admin@example.com", password_hash=hash_password("admin123"), role="admin")
    db.add(admin)
    db.commit()

    token = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"}).json()["access_token"]
    
    response = client.get("/api/admin/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data

def test_audit_event_registration_and_login(client, db):
    # Clear existing logs for predictable counts
    db.query(AuditLog).delete()
    db.commit()

    # Registration
    resp_reg = client.post("/api/auth/register", json={"name": "Audit Test", "email": "audit_test@example.com", "password": "password123", "role": "user"})
    assert resp_reg.status_code == 201

    # Login
    resp_login = client.post("/api/auth/login", json={"email": "audit_test@example.com", "password": "password123"})
    assert resp_login.status_code == 200

    logs = db.query(AuditLog).order_by(AuditLog.timestamp.asc()).all()
    actions = [log.action for log in logs]
    assert "register" in actions
    assert "login" in actions

def test_audit_event_patient_case_creation(client, db, registered_user):
    user_data, password = registered_user
    email = user_data["email"]
    token = client.post("/api/auth/login", json={"email": email, "password": password}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create patient
    resp_patient = client.post("/api/patients/", json={"full_name": "Audit Patient", "anon_code": "AUDIT-001", "age": 45, "sex": "M"}, headers=headers)
    assert resp_patient.status_code == 201
    
    # Create case
    patient_id = resp_patient.json()["id"]
    resp_case = client.post("/api/cases/", json={"name": "Audit Case", "patient_id": patient_id}, headers=headers)
    assert resp_case.status_code == 201
    
    # Verify logs
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).all()
    actions = [log.action for log in logs]
    assert "create_patient" in actions
    assert "create_case" in actions

def test_pagination_and_filtering(client, db):
    from app.core.security import hash_password
    admin = db.query(User).filter_by(email="admin@example.com").first()
    if not admin:
        admin = User(email="admin@example.com", password_hash=hash_password("admin123"), role="admin")
        db.add(admin)
        db.commit()

    token = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin123"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Add some dummy logs
    db.add(AuditLog(action="test_action", user_id=admin.id))
    db.commit()

    response = client.get("/api/admin/audit-logs?action=test_action", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["items"][0]["action"] == "test_action"

    # Secrets not exposed
    assert "password" not in str(data)
    assert "token" not in str(data)
