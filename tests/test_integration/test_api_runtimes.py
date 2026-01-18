"""
Integration tests for Runtime API endpoints.

Tests Runtime Registry and API functionality including:
- Listing runtimes
- Getting runtime details
- Creating new runtimes
- Using runtime_id when starting jobs
"""

import pytest
from fastapi.testclient import TestClient

from routilux.server.main import app
from routilux.monitoring.runtime_registry import RuntimeRegistry


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def runtime_registry():
    """Get runtime registry and ensure default runtime exists."""
    registry = RuntimeRegistry.get_instance()
    # Ensure default runtime exists
    registry.get_or_create_default(thread_pool_size=0)
    yield registry


class TestRuntimeAPI:
    """Test Runtime API endpoints."""

    def test_list_runtimes(self, client, runtime_registry):
        """Test: GET /api/runtimes returns list of runtimes."""
        response = client.get("/api/runtimes")
        assert response.status_code == 200
        data = response.json()
        
        assert "runtimes" in data
        assert "total" in data
        assert "default_runtime_id" in data
        assert isinstance(data["runtimes"], list)
        assert data["total"] >= 1  # At least default runtime should exist
        
        # Check default runtime exists
        default_id = data["default_runtime_id"]
        assert default_id is not None
        
        # Find default runtime in list
        default_runtime = next(
            (r for r in data["runtimes"] if r["runtime_id"] == default_id),
            None
        )
        assert default_runtime is not None
        assert default_runtime["is_default"] is True

    def test_get_runtime_details(self, client, runtime_registry):
        """Test: GET /api/runtimes/{runtime_id} returns runtime details."""
        # First, get default runtime ID
        list_response = client.get("/api/runtimes")
        assert list_response.status_code == 200
        default_id = list_response.json()["default_runtime_id"]
        
        # Get runtime details
        response = client.get(f"/api/runtimes/{default_id}")
        assert response.status_code == 200
        data = response.json()
        
        assert "runtime" in data
        runtime = data["runtime"]
        assert runtime["runtime_id"] == default_id
        assert "thread_pool_size" in runtime
        assert "is_default" in runtime
        assert "active_job_count" in runtime
        assert "is_shutdown" in runtime

    def test_get_runtime_not_found(self, client):
        """Test: GET /api/runtimes/{runtime_id} returns 404 for non-existent runtime."""
        response = client.get("/api/runtimes/non_existent_runtime")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_runtime(self, client, runtime_registry):
        """Test: POST /api/runtimes creates a new runtime."""
        request_data = {
            "runtime_id": "test_runtime",
            "thread_pool_size": 5,
            "is_default": False
        }
        
        response = client.post("/api/runtimes", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        assert "runtime" in data
        runtime = data["runtime"]
        assert runtime["runtime_id"] == "test_runtime"
        assert runtime["thread_pool_size"] == 5
        assert runtime["is_default"] is False
        assert runtime["active_job_count"] == 0
        assert runtime["is_shutdown"] is False
        
        # Verify it appears in list
        list_response = client.get("/api/runtimes")
        assert list_response.status_code == 200
        runtimes = list_response.json()["runtimes"]
        test_runtime = next(
            (r for r in runtimes if r["runtime_id"] == "test_runtime"),
            None
        )
        assert test_runtime is not None

    def test_create_runtime_duplicate(self, client, runtime_registry):
        """Test: POST /api/runtimes returns 400 for duplicate runtime_id."""
        request_data = {
            "runtime_id": "duplicate_test",
            "thread_pool_size": 5,
            "is_default": False
        }
        
        # Create first runtime
        response1 = client.post("/api/runtimes", json=request_data)
        assert response1.status_code == 200
        
        # Try to create duplicate
        response2 = client.post("/api/runtimes", json=request_data)
        assert response2.status_code == 400
        assert "already exists" in response2.json()["detail"].lower()

    def test_create_runtime_as_default(self, client, runtime_registry):
        """Test: POST /api/runtimes can create a default runtime."""
        request_data = {
            "runtime_id": "new_default",
            "thread_pool_size": 10,
            "is_default": True
        }
        
        response = client.post("/api/runtimes", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        assert data["runtime"]["is_default"] is True
        
        # Verify it's now the default
        list_response = client.get("/api/runtimes")
        assert list_response.status_code == 200
        assert list_response.json()["default_runtime_id"] == "new_default"

    def test_create_runtime_with_zero_thread_pool(self, client, runtime_registry):
        """Test: POST /api/runtimes accepts thread_pool_size=0."""
        request_data = {
            "runtime_id": "zero_pool_runtime",
            "thread_pool_size": 0,
            "is_default": False
        }
        
        response = client.post("/api/runtimes", json=request_data)
        assert response.status_code == 200
        data = response.json()
        assert data["runtime"]["thread_pool_size"] == 0


class TestRuntimeJobIntegration:
    """Test Runtime integration with job starting."""

    def test_start_job_with_default_runtime(self, client):
        """Test: Starting job without runtime_id uses default runtime."""
        # Create a test flow first
        flow_data = {
            "flow_id": "test_flow_for_runtime",
            "routines": []
        }
        flow_response = client.post("/api/flows", json=flow_data)
        assert flow_response.status_code == 201
        
        # Start job without runtime_id
        job_data = {
            "flow_id": "test_flow_for_runtime"
        }
        job_response = client.post("/api/jobs", json=job_data)
        assert job_response.status_code == 201
        
        # Job should be created successfully
        job = job_response.json()
        assert "job_id" in job
        assert job["flow_id"] == "test_flow_for_runtime"

    def test_start_job_with_specific_runtime(self, client, runtime_registry):
        """Test: Starting job with runtime_id uses specified runtime."""
        # Create a test runtime
        runtime_data = {
            "runtime_id": "job_test_runtime",
            "thread_pool_size": 5,
            "is_default": False
        }
        runtime_response = client.post("/api/runtimes", json=runtime_data)
        assert runtime_response.status_code == 200
        
        # Create a test flow
        flow_data = {
            "flow_id": "test_flow_for_specific_runtime",
            "routines": []
        }
        flow_response = client.post("/api/flows", json=flow_data)
        assert flow_response.status_code == 201
        
        # Start job with specific runtime_id
        job_data = {
            "flow_id": "test_flow_for_specific_runtime",
            "runtime_id": "job_test_runtime"
        }
        job_response = client.post("/api/jobs", json=job_data)
        assert job_response.status_code == 201
        
        # Job should be created successfully
        job = job_response.json()
        assert "job_id" in job
        assert job["flow_id"] == "test_flow_for_specific_runtime"

    def test_start_job_with_invalid_runtime(self, client):
        """Test: Starting job with invalid runtime_id returns 404."""
        # Create a test flow
        flow_data = {
            "flow_id": "test_flow_invalid_runtime",
            "routines": []
        }
        flow_response = client.post("/api/flows", json=flow_data)
        assert flow_response.status_code == 201
        
        # Try to start job with invalid runtime_id
        job_data = {
            "flow_id": "test_flow_invalid_runtime",
            "runtime_id": "non_existent_runtime"
        }
        job_response = client.post("/api/jobs", json=job_data)
        assert job_response.status_code == 404
        assert "not found" in job_response.json()["detail"].lower()
        assert "GET /api/runtimes" in job_response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
