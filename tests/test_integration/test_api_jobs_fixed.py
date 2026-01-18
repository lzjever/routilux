"""
API tests for fixed job execution.

Tests that API correctly uses Runtime.exec() instead of flow.start().
"""

import pytest

import httpx
from fastapi.testclient import TestClient
from routilux.server.main import app
from routilux import Flow, Routine
from routilux.activation_policies import immediate_policy
from routilux.monitoring.flow_registry import FlowRegistry
from routilux.monitoring.storage import flow_store, job_store

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

    flow.add_routine(routine, "entry")

    # Register in FlowRegistry
    FlowRegistry.get_instance().register_by_name("test_flow", flow)

    # Also add to flow_store for API
    flow_store.add(flow)

    yield flow

    # Cleanup
    flow_store.remove(flow.flow_id)
    FlowRegistry.get_instance().clear()


class TestAPIJobExecution:
    """Test API job execution with Runtime."""

    def test_api_start_job_with_runtime(self, api_client, test_flow):
        """Test that API starts job using Runtime."""
        response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id},
        )

        assert response.status_code == 201
        job_data = response.json()
        assert "job_id" in job_data
        assert job_data["status"] in ["running", "completed", "pending"]

    def test_api_job_status_tracking(self, api_client, test_flow):
        """Test that job status is tracked correctly."""
        response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id},
        )

        assert response.status_code == 201
        job_data = response.json()
        job_id = job_data["job_id"]

        # Check job status
        status_response = api_client.get(f"/api/jobs/{job_id}/status")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["job_id"] == job_id
        assert "status" in status_data

    def test_api_job_list_with_runtime(self, api_client, test_flow):
        """Test that job listing works."""
        # Create a job
        response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id},
        )
        assert response.status_code == 201

        # List jobs
        list_response = api_client.get("/api/jobs")
        assert list_response.status_code == 200
        list_data = list_response.json()
        assert "jobs" in list_data
        assert len(list_data["jobs"]) > 0

    def test_api_job_state_serialization(self, api_client, test_flow):
        """Test that job state can be serialized."""
        response = api_client.post(
            "/api/jobs",
            json={"flow_id": test_flow.flow_id},
        )

        assert response.status_code == 201
        job_data = response.json()
        job_id = job_data["job_id"]

        # Get job state
        state_response = api_client.get(f"/api/jobs/{job_id}/state")
        assert state_response.status_code == 200
        state_data = state_response.json()
        assert "job_id" in state_data
        assert "flow_id" in state_data
