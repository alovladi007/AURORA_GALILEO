import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
import json
import os

# Import app and models
from ops.main import app, get_db
from ops.models import Base, User, ProcessingJob
from ops.schemas import UserCreate, PlanRequest, IngestRequest, ProcessRequest, CatalogRequest

# Test database
TEST_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override dependency
def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

# Create test client
client = TestClient(app)

# Setup and teardown
@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Create test database tables"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def auth_headers():
    """Get authentication headers for test user"""
    # Register user
    response = client.post(
        "/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123"
        }
    )
    
    # Login
    response = client.post(
        "/auth/token",
        data={
            "username": "testuser",
            "password": "testpass123"
        }
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

# Test Health Check
def test_health_check():
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

# Test Authentication
def test_user_registration():
    """Test user registration"""
    response = client.post(
        "/auth/register",
        json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "newpass123"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "newuser"
    assert data["email"] == "new@example.com"

def test_user_login():
    """Test user login"""
    # First register
    client.post(
        "/auth/register",
        json={
            "username": "loginuser",
            "email": "login@example.com",
            "password": "loginpass123"
        }
    )
    
    # Then login
    response = client.post(
        "/auth/token",
        data={
            "username": "loginuser",
            "password": "loginpass123"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_get_current_user(auth_headers):
    """Test getting current user info"""
    response = client.get("/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"

# Test Planning Endpoint
def test_create_plan(auth_headers):
    """Test creating a processing plan"""
    plan_request = {
        "start_time": "2025-01-01T00:00:00Z",
        "end_time": "2025-01-31T23:59:59Z",
        "satellites": ["GRACE-A", "GRACE-B"],
        "time_step": 60,
        "processing_mode": "standard",
        "output_format": "spherical_harmonic",
        "degree_max": 60
    }
    
    response = client.post(
        "/ops/plan",
        json=plan_request,
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["job_type"] == "plan"
    assert data["status"] == "pending"
    assert "id" in data

# Test Ingest Endpoint
def test_ingest_data(auth_headers):
    """Test data ingestion"""
    ingest_request = {
        "data_source": "s3://gravity-data/raw/2025-01/",
        "data_type": "l1b",
        "satellites": ["GRACE-A", "GRACE-B"],
        "start_time": "2025-01-01T00:00:00Z",
        "end_time": "2025-01-31T23:59:59Z",
        "validate_data": True
    }
    
    response = client.post(
        "/ops/ingest",
        json=ingest_request,
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["job_type"] == "ingest"
    assert data["status"] == "pending"

# Test Process Endpoint
def test_process_data(auth_headers):
    """Test gravity field processing"""
    process_request = {
        "algorithm": "variational",
        "degree_max": 60,
        "regularization": {
            "kaula": 1e-5,
            "tikhonov": 0.0
        },
        "output_products": ["coefficients", "grids", "uncertainties"]
    }
    
    response = client.post(
        "/ops/process",
        json=process_request,
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["job_type"] == "process"
    assert data["status"] == "pending"

# Test Catalog Endpoint
def test_catalog_products(auth_headers):
    """Test product cataloging"""
    catalog_request = {
        "product_ids": ["550e8400-e29b-41d4-a716-446655440000"],
        "metadata": {
            "mission": "GRACE-FO",
            "processing_center": "CSR",
            "version": "RL06.1"
        },
        "publish": False,
        "archive": True
    }
    
    response = client.post(
        "/ops/catalog",
        json=catalog_request,
        headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["job_type"] == "catalog"
    assert data["status"] == "pending"

# Test Job Management
def test_list_jobs(auth_headers):
    """Test listing jobs"""
    response = client.get("/ops/jobs", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

def test_get_job(auth_headers):
    """Test getting specific job"""
    # First create a job
    plan_request = {
        "start_time": "2025-01-01T00:00:00Z",
        "end_time": "2025-01-31T23:59:59Z",
        "satellites": ["GRACE-A"],
        "time_step": 60,
        "processing_mode": "standard",
        "output_format": "spherical_harmonic",
        "degree_max": 60
    }
    
    create_response = client.post(
        "/ops/plan",
        json=plan_request,
        headers=auth_headers
    )
    job_id = create_response.json()["id"]
    
    # Then get it
    response = client.get(f"/ops/jobs/{job_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job_id

def test_cancel_job(auth_headers):
    """Test cancelling a job"""
    # First create a job
    plan_request = {
        "start_time": "2025-01-01T00:00:00Z",
        "end_time": "2025-01-31T23:59:59Z",
        "satellites": ["GRACE-C"],
        "time_step": 60,
        "processing_mode": "quick",
        "output_format": "grid",
        "degree_max": 30
    }
    
    create_response = client.post(
        "/ops/plan",
        json=plan_request,
        headers=auth_headers
    )
    job_id = create_response.json()["id"]
    
    # Then cancel it
    response = client.delete(f"/ops/jobs/{job_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Job cancelled successfully"

# Test Error Handling
def test_unauthorized_access():
    """Test accessing protected endpoint without auth"""
    response = client.get("/ops/jobs")
    assert response.status_code == 401

def test_invalid_job_id(auth_headers):
    """Test getting non-existent job"""
    response = client.get(
        "/ops/jobs/550e8400-e29b-41d4-a716-446655440000",
        headers=auth_headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"

def test_duplicate_user_registration():
    """Test registering duplicate user"""
    user_data = {
        "username": "duplicate",
        "email": "dup@example.com",
        "password": "pass123"
    }
    
    # First registration
    client.post("/auth/register", json=user_data)
    
    # Second registration should fail
    response = client.post("/auth/register", json=user_data)
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"]

# Test Input Validation
def test_invalid_plan_request(auth_headers):
    """Test plan with invalid parameters"""
    invalid_request = {
        "start_time": "2025-01-01T00:00:00Z",
        "end_time": "2025-01-31T23:59:59Z",
        "satellites": [],  # Empty list should fail
        "time_step": 60,
        "processing_mode": "invalid_mode",  # Invalid mode
        "output_format": "spherical_harmonic",
        "degree_max": 500  # Too high
    }
    
    response = client.post(
        "/ops/plan",
        json=invalid_request,
        headers=auth_headers
    )
    assert response.status_code == 422  # Validation error

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
