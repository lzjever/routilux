"""
Comprehensive integration tests for Monitoring API endpoints.

Tests all monitoring API endpoints:
- GET /api/jobs/{job_id}/routines/{routine_id}/queue-status
- GET /api/jobs/{job_id}/queues/status
- GET /api/flows/{flow_id}/routines/{routine_id}/info
- GET /api/jobs/{job_id}/routines/status
- GET /api/jobs/{job_id}/monitoring

These tests are written strictly against the API interface without
looking at implementation details.
"""

import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from routilux import Flow, Routine
from routilux.activation_policies import batch_size_policy, immediate_policy
from routilux.api.main import app
from routilux.monitoring.flow_registry import FlowRegistry
from routilux.monitoring.storage import flow_store, job_store
from routilux.runtime import Runtime


@pytest.fixture
def api_client():
    """Create test client for API."""
    return TestClient(app)


@pytest.fixture
def test_flow():
    """Create a test flow with routines."""
    flow = Flow("test_flow")

    class RoutineA(Routine):
        def __init__(self):
            super().__init__()
            self.input_slot = self.define_slot("input")
            self.output_event = self.define_event("output", ["data"])

            def my_logic(input_data, policy_message, job_state):
                pass

            self.set_logic(my_logic)
            self.set_activation_policy(immediate_policy())
            self.set_config(name="RoutineA", timeout=30)

    class RoutineB(Routine):
        def __init__(self):
            super().__init__()
            self.input_slot = self.define_slot("input")
            self.output_event = self.define_event("output", ["data"])

            def my_logic(input_data, policy_message, job_state):
                pass

            self.set_logic(my_logic)
            self.set_activation_policy(batch_size_policy(5))
            self.set_config(name="RoutineB", retries=3)

    routine_a = RoutineA()
    routine_b = RoutineB()
    flow.add_routine(routine_a, "routine_a")
    flow.add_routine(routine_b, "routine_b")
    flow.connect("routine_a", "output", "routine_b", "input")

    FlowRegistry.get_instance().register(flow)
    flow_store.add(flow)

    yield flow

    # Cleanup
    flow_store.remove("test_flow")
    FlowRegistry.get_instance().clear()


@pytest.fixture
def test_job(test_flow):
    """Create and start a test job."""
    runtime = Runtime()
    job_state = runtime.exec("test_flow")
    # Ensure job is in job_store for API access
    job_store.add(job_state)
    time.sleep(0.1)  # Allow execution to start
    yield job_state
    # Cleanup
    job_store.remove(job_state.job_id)
    runtime.shutdown(wait=True)


class TestQueueStatusAPI:
    """Test queue status API endpoints"""

    def test_get_routine_queue_status_success(self, api_client, test_flow, test_job):
        """Test: GET /api/jobs/{job_id}/routines/{routine_id}/queue-status returns queue status"""
        response = api_client.get(
            f"/api/jobs/{test_job.job_id}/routines/routine_a/queue-status",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, list)
        # Should have at least one slot (input)
        assert len(data) >= 1

        # Verify structure of each queue status
        for queue_status in data:
            assert "slot_name" in queue_status
            assert "routine_id" in queue_status
            assert queue_status["routine_id"] == "routine_a"
            assert "unconsumed_count" in queue_status
            assert "total_count" in queue_status
            assert "max_length" in queue_status
            assert "watermark_threshold" in queue_status
            assert "usage_percentage" in queue_status
            assert "pressure_level" in queue_status
            assert "is_full" in queue_status
            assert "is_near_full" in queue_status

            # Verify value ranges
            assert queue_status["unconsumed_count"] >= 0
            assert queue_status["total_count"] >= 0
            assert 0.0 <= queue_status["usage_percentage"] <= 1.0
            assert queue_status["pressure_level"] in ["low", "medium", "high", "critical"]
            assert isinstance(queue_status["is_full"], bool)
            assert isinstance(queue_status["is_near_full"], bool)

    def test_get_routine_queue_status_non_existent_job(self, api_client):
        """Test: GET /api/jobs/{job_id}/routines/{routine_id}/queue-status returns 404 for non-existent job"""
        response = api_client.get(
            "/api/jobs/non_existent_job/routines/routine_a/queue-status",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_get_routine_queue_status_non_existent_routine(self, api_client, test_job):
        """Test: GET /api/jobs/{job_id}/routines/{routine_id}/queue-status returns 404 for non-existent routine"""
        response = api_client.get(
            f"/api/jobs/{test_job.job_id}/routines/non_existent_routine/queue-status",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_get_job_queues_status_success(self, api_client, test_flow, test_job):
        """Test: GET /api/jobs/{job_id}/queues/status returns queue status for all routines"""
        response = api_client.get(
            f"/api/jobs/{test_job.job_id}/queues/status",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, dict)
        # Should have both routines
        assert "routine_a" in data
        assert "routine_b" in data

        # Verify structure
        for routine_id, queue_statuses in data.items():
            assert isinstance(queue_statuses, list)
            for queue_status in queue_statuses:
                assert "slot_name" in queue_status
                assert "routine_id" in queue_status
                assert queue_status["routine_id"] == routine_id

    def test_get_job_queues_status_non_existent_job(self, api_client):
        """Test: GET /api/jobs/{job_id}/queues/status returns 404 for non-existent job"""
        response = api_client.get(
            "/api/jobs/non_existent_job/queues/status",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 404


class TestRoutineInfoAPI:
    """Test routine info API endpoints"""

    def test_get_routine_info_success(self, api_client, test_flow):
        """Test: GET /api/flows/{flow_id}/routines/{routine_id}/info returns routine metadata"""
        response = api_client.get(
            "/api/flows/test_flow/routines/routine_a/info",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["routine_id"] == "routine_a"
        assert "routine_type" in data
        assert "activation_policy" in data
        assert "config" in data
        assert "slots" in data
        assert "events" in data

        # Verify activation policy structure
        policy = data["activation_policy"]
        assert "type" in policy
        assert "config" in policy
        assert "description" in policy
        assert policy["type"] == "immediate"

        # Verify config
        assert isinstance(data["config"], dict)
        assert data["config"]["name"] == "RoutineA"
        assert data["config"]["timeout"] == 30

        # Verify slots and events
        assert isinstance(data["slots"], list)
        assert "input" in data["slots"]
        assert isinstance(data["events"], list)
        assert "output" in data["events"]

    def test_get_routine_info_non_existent_flow(self, api_client):
        """Test: GET /api/flows/{flow_id}/routines/{routine_id}/info returns 404 for non-existent flow"""
        response = api_client.get(
            "/api/flows/non_existent_flow/routines/routine_a/info",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 404

    def test_get_routine_info_non_existent_routine(self, api_client, test_flow):
        """Test: GET /api/flows/{flow_id}/routines/{routine_id}/info returns 404 for non-existent routine"""
        response = api_client.get(
            "/api/flows/test_flow/routines/non_existent_routine/info",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 404

    def test_get_routine_info_different_policy_types(self, api_client, test_flow):
        """Test: GET /api/flows/{flow_id}/routines/{routine_id}/info returns correct policy info for different types"""
        # Test immediate policy
        response = api_client.get(
            "/api/flows/test_flow/routines/routine_a/info",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        assert response.json()["activation_policy"]["type"] == "immediate"

        # Test batch_size policy
        response = api_client.get(
            "/api/flows/test_flow/routines/routine_b/info",
            headers={"X-API-Key": "test-key"},
        )
        assert response.status_code == 200
        assert response.json()["activation_policy"]["type"] == "batch_size"
        assert "min_batch_size" in response.json()["activation_policy"]["config"]


class TestRoutineStatusAPI:
    """Test routine status API endpoints"""

    def test_get_routines_status_success(self, api_client, test_flow, test_job):
        """Test: GET /api/jobs/{job_id}/routines/status returns status for all routines"""
        response = api_client.get(
            f"/api/jobs/{test_job.job_id}/routines/status",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data, dict)
        assert "routine_a" in data
        assert "routine_b" in data

        # Verify structure of each status
        for routine_id, status in data.items():
            assert status["routine_id"] == routine_id
            assert "is_active" in status
            assert "status" in status
            assert "last_execution_time" in status
            assert "execution_count" in status
            assert "error_count" in status

            # Verify value types and ranges
            assert isinstance(status["is_active"], bool)
            assert status["status"] in ["pending", "running", "completed", "failed", "error_continued", "skipped"]
            assert isinstance(status["execution_count"], int)
            assert status["execution_count"] >= 0
            assert isinstance(status["error_count"], int)
            assert status["error_count"] >= 0

    def test_get_routines_status_non_existent_job(self, api_client):
        """Test: GET /api/jobs/{job_id}/routines/status returns 404 for non-existent job"""
        response = api_client.get(
            "/api/jobs/non_existent_job/routines/status",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 404


class TestJobMonitoringAPI:
    """Test complete job monitoring API endpoint"""

    def test_get_job_monitoring_data_success(self, api_client, test_flow, test_job):
        """Test: GET /api/jobs/{job_id}/monitoring returns complete monitoring data"""
        response = api_client.get(
            f"/api/jobs/{test_job.job_id}/monitoring",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify top-level structure
        assert data["job_id"] == test_job.job_id
        assert data["flow_id"] == "test_flow"
        assert "job_status" in data
        assert "routines" in data
        assert "updated_at" in data

        # Verify routines structure
        routines = data["routines"]
        assert isinstance(routines, dict)
        assert "routine_a" in routines
        assert "routine_b" in routines

        # Verify each routine has complete data
        for routine_id, routine_data in routines.items():
            assert routine_data["routine_id"] == routine_id
            assert "execution_status" in routine_data
            assert "queue_status" in routine_data
            assert "info" in routine_data

            # Verify execution_status
            exec_status = routine_data["execution_status"]
            assert "is_active" in exec_status
            assert "status" in exec_status

            # Verify queue_status
            queue_status = routine_data["queue_status"]
            assert isinstance(queue_status, list)

            # Verify info
            info = routine_data["info"]
            assert "activation_policy" in info
            assert "config" in info
            assert "slots" in info
            assert "events" in info

    def test_get_job_monitoring_data_non_existent_job(self, api_client):
        """Test: GET /api/jobs/{job_id}/monitoring returns 404 for non-existent job"""
        response = api_client.get(
            "/api/jobs/non_existent_job/monitoring",
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 404

    def test_get_job_monitoring_data_consistency(self, api_client, test_flow, test_job):
        """Test: GET /api/jobs/{job_id}/monitoring data is consistent across calls"""
        response1 = api_client.get(
            f"/api/jobs/{test_job.job_id}/monitoring",
            headers={"X-API-Key": "test-key"},
        )
        response2 = api_client.get(
            f"/api/jobs/{test_job.job_id}/monitoring",
            headers={"X-API-Key": "test-key"},
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        # Job ID and flow ID should be consistent
        assert data1["job_id"] == data2["job_id"]
        assert data1["flow_id"] == data2["flow_id"]

        # Routine IDs should be consistent
        assert set(data1["routines"].keys()) == set(data2["routines"].keys())


class TestMonitoringAPIAuthentication:
    """Test monitoring API authentication"""

    def test_monitoring_endpoints_require_auth(self, api_client, test_job):
        """Test: All monitoring endpoints require authentication"""
        from routilux.api.config import get_config
        
        config = get_config()
        # Skip test if auth is disabled (common in test environments)
        if not config.api_key_enabled:
            pytest.skip("API key authentication is disabled in test environment")
        
        endpoints = [
            f"/api/jobs/{test_job.job_id}/routines/routine_a/queue-status",
            f"/api/jobs/{test_job.job_id}/queues/status",
            "/api/flows/test_flow/routines/routine_a/info",
            f"/api/jobs/{test_job.job_id}/routines/status",
            f"/api/jobs/{test_job.job_id}/monitoring",
        ]

        for endpoint in endpoints:
            response = api_client.get(endpoint)
            # Should return 401 or 403 without auth
            assert response.status_code in [401, 403], f"Endpoint {endpoint} should require auth"
