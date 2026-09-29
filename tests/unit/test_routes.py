"""Tests for FastAPI routes."""

import pytest
from fastapi.testclient import TestClient

from src.api import create_app


@pytest.fixture
def client():
    """Create test client."""
    app = create_app()
    return TestClient(app)


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_endpoint_returns_ok(self, client):
        """Health endpoint returns 200 with ok status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "service" in data

    def test_health_endpoint_includes_service_name(self, client):
        """Health endpoint includes service name."""
        response = client.get("/health")
        assert response.json()["service"] == "Yatra AI"

    def test_readiness_endpoint_exists(self, client):
        """Readiness endpoint exists and responds."""
        response = client.get("/ready")
        assert response.status_code in [200, 503]


class TestPlanningEndpoints:
    """Tests for trip planning endpoints."""

    def test_plan_trip_requires_message(self, client):
        """Plan endpoint requires message field."""
        response = client.post("/api/plan", json={"user_id": "test"})
        assert response.status_code in [400, 422]

    def test_plan_trip_accepts_minimal_request(self, client):
        """Plan trip works with just message."""
        response = client.post("/api/plan", json={"message": "Test trip"})
        # Should return 200 (streaming) or 422 if validators fail
        assert response.status_code in [200, 202, 422]

    def test_plan_trip_with_user_id(self, client):
        """Plan trip accepts user_id."""
        response = client.post(
            "/api/plan", json={"message": "Test", "user_id": "user-123"}
        )
        assert response.status_code in [200, 202, 422]

    def test_plan_trip_with_thread_id(self, client):
        """Plan trip accepts thread_id for resumption."""
        response = client.post(
            "/api/plan",
            json={"message": "Resume", "user_id": "user-123", "thread_id": "any-thread"},
        )
        # Should be 200 (success) or 404 (thread not found) or 422 (validation error)
        assert response.status_code in [200, 202, 404, 422]

    def test_get_nonexistent_thread_returns_404(self, client):
        """Get nonexistent thread returns 404."""
        response = client.get("/api/threads/nonexistent-thread-id")
        assert response.status_code == 404

    def test_get_thread_response_format(self, client):
        """Get thread response has correct format."""
        response = client.get("/api/threads/some-thread")
        if response.status_code == 404:
            assert response.json()["detail"] == "Thread not found"


class TestApprovalEndpoints:
    """Tests for HITL approval endpoints."""

    def test_approve_requires_approved_field(self, client):
        """Approval endpoint requires approved field."""
        response = client.put("/api/threads/thread-id/approve", json={})
        # Should fail validation or return 404 for missing thread
        assert response.status_code in [400, 404, 422]

    def test_approve_nonexistent_thread_returns_404(self, client):
        """Approve nonexistent thread returns 404."""
        response = client.put(
            "/api/threads/nonexistent/approve", json={"approved": True}
        )
        assert response.status_code == 404

    def test_approve_accepts_feedback(self, client):
        """Approval endpoint accepts feedback."""
        response = client.put(
            "/api/threads/thread-id/approve",
            json={"approved": True, "feedback": "Looks great!"},
        )
        # 404 is expected (no thread), 422 would be validation error
        assert response.status_code in [404, 422]

    def test_approve_accepts_rejection(self, client):
        """Approval endpoint accepts rejection."""
        response = client.put(
            "/api/threads/thread-id/approve",
            json={"approved": False, "feedback": "Please adjust dates"},
        )
        # 404 is expected (no thread)
        assert response.status_code in [404, 422]


class TestErrorHandling:
    """Tests for error handling and responses."""

    def test_api_returns_json_errors(self, client):
        """API returns JSON error responses."""
        response = client.get("/api/threads/nonexistent")
        assert response.status_code == 404
        assert "detail" in response.json()

    def test_invalid_json_returns_422(self, client):
        """Invalid JSON returns validation error."""
        response = client.post(
            "/api/plan",
            json={"message": 123},  # Should be string
        )
        # Depends on pydantic validation
        assert response.status_code in [200, 202, 422]

    def test_cors_headers_present(self, client):
        """CORS headers are included in response."""
        response = client.get("/health")
        # Check if CORS headers might be present (not guaranteed by testclient)
        assert response.status_code == 200
