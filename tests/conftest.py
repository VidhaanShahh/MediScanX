"""
MediScanX — conftest.py for pytest.

Provides:
    - SQLite in-memory database for isolated testing
    - FastAPI TestClient
    - Auth helper fixtures
"""

import os
import sys

# Ensure the project root and backend package are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Override DATABASE_URL before any app import
os.environ["DATABASE_URL"] = "sqlite:///./test_mediscanx.db"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["UPLOAD_DIR"] = "test_uploads"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.database import get_db
from app.main import app


# In-memory SQLite for tests
TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    """Create fresh tables before each test, tear down after."""
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def registered_user(client):
    """Register a user and return (response_data, password)."""
    resp = client.post("/api/auth/register", json={
        "name": "Test User",
        "email": "test@mediscanx.com",
        "password": "TestPass123!",
        "role": "user",
    })
    assert resp.status_code == 201
    return resp.json(), "TestPass123!"


@pytest.fixture
def auth_token(client, registered_user):
    """Login and return bearer token string."""
    _, pw = registered_user
    resp = client.post("/api/auth/login", json={
        "email": "test@mediscanx.com",
        "password": pw,
    })
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    """Return Authorization headers dict."""
    return {"Authorization": f"Bearer {auth_token}"}
