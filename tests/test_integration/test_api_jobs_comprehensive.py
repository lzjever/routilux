"""
Comprehensive API tests for job execution.

These tests verify API behavior based on interface contracts, not implementation.
They challenge the API to ensure it correctly uses Runtime and handles all edge cases.
"""

import pytest
import time

import httpx
from fastapi.testclient import TestClient
from routilux.server.main import app
from routilux import Flow, Routine
from routilux.activation_policies import immediate_policy
from routilux.job_state import JobState
from routilux.monitoring.flow_registry import FlowRegistry
from routilux.monitoring.storage import flow_store, job_store
from routilux.runtime import Runtime
from routilux.status import ExecutionStatus

# Import Mock for testing (always available in Python 3.3+)
from unittest.mock import Mock, patch

# Integration tests marker
pytestmark = pytest.mark.integration


@pytest.fixture
def api_client():
    """Create FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def test_flow():
    """Create a test flow."""
    flow = Flow("test_flow")
    routine = Routine()
    routine.define_slot("trigger")

    def my_logic(trigger_data, policy_message, job_state):
        pass

    routine.set_logic(my_logic)
    routine.set_activation_policy(immediate_policy())
    flow.add_routine(routine, "entry")

    # Register in FlowRegistry
    FlowRegistry.get_instance().register_by_name("test_flow", flow)

    # Also add to flow_store for API
    flow_store.add(flow)

    yield flow

    # Cleanup
    flow_store.remove(flow.flow_id)
    FlowRegistry.get_instance().clear()


class TestAPIJobExecutionInterface:
    """Test API job execution interface compliance."""

    def test_api_start_job_returns_job_response(self, api_client, test_flow):
        """Test: POST /api/jobs should return JobResponse with required fields."""
        response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id},
        )

        # Verify response structure
        assert response.status_code == 201
        data = response.json()

        # Required fields per JobResponse interface
        assert "job_id" in data, "Response must contain job_id"
        assert "flow_id" in data, "Response must contain flow_id"
        assert "status" in data, "Response must contain status"
        assert "created_at" in data, "Response must contain created_at"

        # Verify types
        assert isinstance(data["job_id"], str)
        assert isinstance(data["flow_id"], str)
        assert isinstance(data["status"], str)

        # Verify status is valid
        assert data["status"] in [
            "pending",
            "running",
            "completed",
            "failed",
            "paused",
            "cancelled",
        ], f"Invalid status: {data['status']}"

    def test_api_start_job_creates_job_in_runtime(self, api_client, test_flow):
        """Test: Starting job via API should register job in Runtime."""
        response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id},
        )

        assert response.status_code == 201
        job_data = response.json()
        job_id = job_data["job_id"]

        # Verify job is in Runtime's active jobs
        from routilux.runtime import get_runtime_instance

        runtime = get_runtime_instance()
        runtime_job = runtime._active_jobs.get(job_id)
        assert runtime_job is not None, "Job should be registered in Runtime"
        assert runtime_job.job_id == job_id

    def test_api_post_to_job_success(self, api_client, test_flow):
        """Test: POST /api/jobs/{job_id}/post should deliver data to a routine slot."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id},
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]

        # Post data to entry routine's trigger slot
        post_response = api_client.post(
            f"/api/jobs/{job_id}/post",
            json={
                "routine_id": "entry",
                "slot_name": "trigger",
                "data": {"param1": "value1", "param2": 42},
            },
        )
        assert post_response.status_code == 200
        assert post_response.json() == {"status": "posted", "job_id": job_id}

    def test_api_start_job_with_invalid_flow_id(self, api_client):
        """Test: API should return 404 for non-existent flow."""
        response = api_client.post(
            "/api/jobs",
            json={"flow_id": "nonexistent_flow"},
        )

        # Should return error (404 or 400)
        assert response.status_code in [400, 404], (
            f"Expected 400 or 404 for invalid flow_id, got {response.status_code}"
        )

    def test_api_resume_when_not_running_returns_409(self, api_client, test_flow):
        """Test: POST /api/jobs/{job_id}/resume returns 409 when job has no active executor."""
        # Create a job state and add to store without starting via Runtime (no executor)
        job_state = JobState(test_flow.flow_id)
        job_store.add(job_state)

        response = api_client.post(f"/api/jobs/{job_state.job_id}/resume")
        assert response.status_code == 409
        assert "not running" in response.json().get("detail", "").lower()

    def test_api_post_to_job_404_nonexistent_routine(self, api_client, test_flow):
        """Test: POST /api/jobs/{job_id}/post returns 404 for non-existent routine."""
        start_response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id},
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]

        post_response = api_client.post(
            f"/api/jobs/{job_id}/post",
            json={
                "routine_id": "nonexistent_routine",
                "slot_name": "trigger",
                "data": {},
            },
        )
        assert post_response.status_code == 404

    def test_api_start_job_handles_runtime_errors(self, api_client, test_flow):
        """Test: API should handle Runtime.exec() errors gracefully."""
        # Mock get_runtime_instance to return a runtime that raises on exec
        mock_runtime = Mock(spec=Runtime)
        mock_runtime.exec = Mock(side_effect=RuntimeError("Runtime execution error"))

        with patch("routilux.api.routes.jobs.get_runtime_instance", return_value=mock_runtime):
            response = api_client.post(
                "/api/jobs",
                json={"flow_id": test_flow.flow_id},
            )

        # Should return error status
        assert response.status_code == 400, "API should return 400 when Runtime.exec() fails"
        data = response.json()
        assert "detail" in data or "error" in str(data).lower()


class TestAPIJobStateManagement:
    """Test API job state management interface."""

    def test_api_get_job_returns_correct_structure(self, api_client, test_flow):
        """Test: GET /api/jobs/{job_id} should return JobResponse."""
        # Create job first
        create_response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id},
        )
        assert create_response.status_code == 201
        job_id = create_response.json()["job_id"]

        # Get job
        get_response = api_client.get(f"/api/jobs/{job_id}")
        assert get_response.status_code == 200

        data = get_response.json()
        assert "job_id" in data
        assert data["job_id"] == job_id

    def test_api_get_job_returns_404_for_nonexistent(self, api_client):
        """Test: GET /api/jobs/{job_id} should return 404 for non-existent job."""
        response = api_client.get("/api/jobs/nonexistent_job_id")
        assert response.status_code == 404

    def test_api_get_job_state_returns_serialized_state(self, api_client, test_flow):
        """Test: GET /api/jobs/{job_id}/state should return serialized JobState."""
        # Create job
        create_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": test_flow.flow_id,
                "entry_routine_id": "entry",
            },
        )
        assert create_response.status_code == 201
        job_id = create_response.json()["job_id"]

        # Get job state
        state_response = api_client.get(f"/api/jobs/{job_id}/state")
        assert state_response.status_code == 200

        state_data = state_response.json()
        # Should be a dictionary (serialized JobState)
        assert isinstance(state_data, dict)
        assert "job_id" in state_data
        assert "flow_id" in state_data
        assert "status" in state_data

    def test_api_list_jobs_returns_paginated_results(self, api_client, test_flow):
        """Test: GET /api/jobs should return paginated list."""
        # Create multiple jobs
        job_ids = []
        for i in range(3):
            response = api_client.post(
                "/api/jobs",
                json={"flow_id": test_flow.flow_id},
            )
            if response.status_code == 201:
                job_ids.append(response.json()["job_id"])

        # List jobs
        list_response = api_client.get("/api/jobs?limit=2&offset=0")
        assert list_response.status_code == 200

        data = list_response.json()
        assert "jobs" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

        # Verify pagination fields
        assert isinstance(data["jobs"], list)
        assert isinstance(data["total"], int)
        assert data["limit"] == 2
        assert data["offset"] == 0

    def test_api_list_jobs_filters_by_status(self, api_client, test_flow):
        """Test: GET /api/jobs?status=... should filter correctly."""
        # Create a job
        create_response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id},
        )
        assert create_response.status_code == 201

        # List with status filter
        list_response = api_client.get("/api/jobs?status=running")
        assert list_response.status_code == 200

        data = list_response.json()
        # All returned jobs should have status="running"
        for job in data["jobs"]:
            assert job["status"] == "running", f"Filtered job has wrong status: {job['status']}"

    def test_api_list_jobs_filters_by_flow_id(self, api_client, test_flow):
        """Test: GET /api/jobs?flow_id=... should filter correctly."""
        # Create a job
        create_response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id},
        )
        assert create_response.status_code == 201

        # List with flow_id filter
        list_response = api_client.get(f"/api/jobs?flow_id={test_flow.flow_id}")
        assert list_response.status_code == 200

        data = list_response.json()
        # All returned jobs should have matching flow_id
        for job in data["jobs"]:
            assert job["flow_id"] == test_flow.flow_id, (
                f"Filtered job has wrong flow_id: {job['flow_id']}"
            )


class TestAPIJobExecutionFlow:
    """Test complete job execution flow via API."""

    def test_api_job_lifecycle(self, api_client, test_flow):
        """Test: Complete job lifecycle via API (start -> status -> state)."""
        # 1. Start job
        start_response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id},
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]

        # 2. Check status
        status_response = api_client.get(f"/api/jobs/{job_id}/status")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["job_id"] == job_id
        assert "status" in status_data

        # 3. Get full state
        state_response = api_client.get(f"/api/jobs/{job_id}/state")
        assert state_response.status_code == 200
        state_data = state_response.json()
        assert state_data["job_id"] == job_id

        # 4. Wait and verify status (job starts idle, waiting for data)
        time.sleep(0.5)  # Wait for job initialization

        final_status_response = api_client.get(f"/api/jobs/{job_id}/status")
        assert final_status_response.status_code == 200
        final_status = final_status_response.json()["status"]
        # Jobs start idle in the new design, waiting for data to be posted
        assert final_status in ["completed", "failed", "running", "idle"], (
            f"Unexpected final status: {final_status}"
        )

    def test_api_multiple_concurrent_jobs(self, api_client, test_flow):
        """Test: API should handle multiple concurrent job starts."""
        # Start multiple jobs concurrently
        responses = []
        for i in range(3):
            response = api_client.post(
                "/api/jobs",
                json={"flow_id": test_flow.flow_id},
            )
            responses.append(response)

        # All should succeed
        job_ids = []
        for response in responses:
            assert response.status_code == 201, (
                f"Concurrent job start failed with status {response.status_code}"
            )
            job_ids.append(response.json()["job_id"])

        # All job IDs should be unique
        assert len(job_ids) == len(set(job_ids)), "Job IDs should be unique"

        # All jobs should be accessible
        for job_id in job_ids:
            get_response = api_client.get(f"/api/jobs/{job_id}")
            assert get_response.status_code == 200

    def test_api_job_status_updates_over_time(self, api_client, test_flow):
        """Test: Job status should update as execution progresses."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id},
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]

        # Check initial status
        initial_status = api_client.get(f"/api/jobs/{job_id}/status").json()["status"]
        assert initial_status in ["pending", "running"], (
            f"Initial status should be pending or running, got {initial_status}"
        )

        # Wait and check again
        time.sleep(0.5)
        final_status = api_client.get(f"/api/jobs/{job_id}/status").json()["status"]

        # Status should be in valid state (jobs start idle in new design)
        assert final_status in ["completed", "failed", "running", "idle"], (
            f"Final status should be completed/failed/running/idle, got {final_status}"
        )


class TestAPIJobErrorHandling:
    """Test API error handling and edge cases."""

    def test_api_start_job_with_missing_required_fields(self, api_client):
        """Test: API should return 422 for missing required fields."""
        # Missing flow_id
        response = api_client.post(
            "/api/jobs",
            json={},
        )
        assert response.status_code == 422, "Should return 422 for missing required field"

    def test_api_start_job_with_invalid_timeout(self, api_client, test_flow):
        """Test: API should validate timeout parameter."""
        # Negative timeout
        response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id, "timeout": -1},
        )
        assert response.status_code == 422, "Should reject negative timeout"

        # Too large timeout
        response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id, "timeout": 100000},  # > 24 hours
        )
        assert response.status_code == 422, "Should reject timeout > 24 hours"

    def test_api_job_state_serialization_handles_all_fields(self, api_client, test_flow):
        """Test: Job state serialization should include all required fields."""
        # Create job
        create_response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id},
        )
        assert create_response.status_code == 201
        job_id = create_response.json()["job_id"]

        # Get state
        state_response = api_client.get(f"/api/jobs/{job_id}/state")
        assert state_response.status_code == 200

        state_data = state_response.json()

        # Verify all critical fields are present
        required_fields = ["job_id", "flow_id", "status", "created_at"]
        for field in required_fields:
            assert field in state_data, f"Serialized state missing required field: {field}"

    def test_api_job_list_pagination_boundaries(self, api_client, test_flow):
        """Test: Job list pagination should handle boundary cases."""
        # Test with limit=0 (should be rejected or use default)
        response = api_client.get("/api/jobs?limit=0")
        # Should either reject or use default limit
        assert response.status_code in [200, 422]

        # Test with negative offset
        response = api_client.get("/api/jobs?offset=-1")
        assert response.status_code == 422, "Should reject negative offset"

        # Test with very large limit
        response = api_client.get("/api/jobs?limit=10000")
        # Should either reject or cap at max
        assert response.status_code in [200, 422]
