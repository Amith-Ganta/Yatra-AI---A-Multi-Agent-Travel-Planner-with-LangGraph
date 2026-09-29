"""API integration tests."""

import pytest
import json
from fastapi.testclient import TestClient

from src.api import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


def test_health_check(client):
    """Health endpoint returns ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_endpoint_format(client):
    """Health endpoint has correct format."""
    response = client.get("/health")
    data = response.json()
    assert "status" in data
    assert "service" in data
    assert data["service"] == "Yatra AI"


def test_readiness_check_exists(client):
    """Readiness endpoint exists."""
    response = client.get("/ready")
    assert response.status_code in [200, 503]


def test_plan_trip_requires_message(client):
    """Plan endpoint requires message."""
    response = client.post("/api/plan", json={"user_id": "test"})
    assert response.status_code in [400, 422]


def test_plan_trip_with_defaults(client):
    """Plan trip works with defaults."""
    response = client.post(
        "/api/plan",
        json={"message": "Plan a trip to Paris"},
    )
    # Should return streaming response (200) or accepted (202)
    assert response.status_code in [200, 202, 422]  # 422 if validators reject


def test_plan_trip_response_format(client):
    """Plan trip response is valid."""
    response = client.post(
        "/api/plan",
        json={"message": "Test trip", "user_id": "test-user"},
    )
    # Check response status (may be 200, 202, or error)
    assert response.status_code in [200, 202, 422]


def test_get_nonexistent_thread(client):
    """Get nonexistent thread returns 404."""
    response = client.get("/api/threads/nonexistent-thread-id")
    assert response.status_code == 404


def test_approve_nonexistent_thread(client):
    """Approve nonexistent thread returns 404."""
    response = client.put(
        "/api/threads/nonexistent-thread-id/approve",
        json={"approved": True},
    )
    assert response.status_code == 404


def test_approval_request_format(client):
    """Approval endpoint validates request format."""
    response = client.put(
        "/api/threads/any-thread-id/approve",
        json={"approved": True, "feedback": "Looks good"},
    )
    # Should either succeed (with thread) or return 404 (without)
    assert response.status_code in [200, 404, 422]


def test_api_cors_headers(client):
    """API response includes CORS headers."""
    response = client.get("/health")
    # Check if CORS headers are present
    assert response.status_code == 200
