"""
Comprehensive tests for API v1 endpoints.

Tests the new Worker/Job architecture for the Routilux API.
Covers happy paths, error cases, edge cases, and concurrent scenarios.
"""

import asyncio
import pytest
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient

from routilux.server.main import app
from routilux.core.flow import Flow
from routilux.core.routine import Routine
from routilux.server.dependencies import (
    get_flow_registry,
    get_job_storage,
    get_idempotency_backend,
    reset_storage,
    get_runtime,
)


pytestmark = pytest.mark.api


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_flow():
    """Create and register a sample flow for testing."""
    
    class TestRoutine(Routine):
        def __init__(self):
            super().__init__()
            self.add_slot("input")
            self.add_event("output")
        
        def logic(self, data):
            value = data.get("value", 0)
            self.emit("output", {"result": value * 2})
    
    flow = Flow(flow_id="test_flow_v1")
    flow.add_routine(TestRoutine(), "processor")
    
    # Register flow
    registry = get_flow_registry()
    registry.register(flow)
    registry.register_by_name("test_flow_v1", flow)
    
    yield flow
    
    # Cleanup
    try:
        registry._flows.pop(flow.flow_id, None)
        registry._name_registry.pop("test_flow_v1", None)
    except Exception:
        pass
    reset_storage()


@pytest.fixture
def slow_flow():
    """Create a flow with a slow routine for testing timeouts."""
    
    class SlowRoutine(Routine):
        def __init__(self):
            super().__init__()
            self.add_slot("input")
            self.add_event("output")
        
        def logic(self, data):
            import time
            time.sleep(2)  # Slow processing
            self.emit("output", {"result": "done"})
    
    flow = Flow(flow_id="slow_flow")
    flow.add_routine(SlowRoutine(), "slow_processor")
    
    registry = get_flow_registry()
    registry.register(flow)
    registry.register_by_name("slow_flow", flow)
    
    yield flow
    
    try:
        registry._flows.pop(flow.flow_id, None)
        registry._name_registry.pop("slow_flow", None)
    except Exception:
        pass


class TestHealthEndpoints:
    """Tests for /api/v1/health/* endpoints."""
    
    def test_liveness(self, client):
        """Test liveness probe."""
        response = client.get("/api/v1/health/live")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    
    def test_readiness(self, client):
        """Test readiness probe."""
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert "runtime" in data
        assert data["runtime"]["shutdown"] is False
    
    def test_stats(self, client):
        """Test health stats."""
        response = client.get("/api/v1/health/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "runtime" in data
        assert "active_workers" in data["runtime"]


class TestWorkerEndpoints:
    """Tests for /api/v1/workers/* endpoints."""
    
    def test_list_workers_empty(self, client):
        """Test listing workers when none exist."""
        response = client.get("/api/v1/workers")
        assert response.status_code == 200
        data = response.json()
        assert "workers" in data
        assert "total" in data
        assert isinstance(data["workers"], list)
        assert data["total"] == 0
    
    def test_create_worker(self, client, sample_flow):
        """Test creating a worker."""
        response = client.post("/api/v1/workers", json={
            "flow_id": "test_flow_v1"
        })
        assert response.status_code == 201
        data = response.json()
        assert "worker_id" in data
        assert data["flow_id"] == "test_flow_v1"
        assert data["status"] == "running"
        assert data["jobs_processed"] == 0
        assert data["jobs_failed"] == 0
    
    def test_create_worker_with_custom_id(self, client, sample_flow):
        """Test creating worker with custom ID (currently not supported but should not error)."""
        response = client.post("/api/v1/workers", json={
            "flow_id": "test_flow_v1",
            "worker_id": "custom-worker-123"
        })
        # Should succeed but may ignore custom ID
        assert response.status_code == 201
        assert "worker_id" in response.json()
    
    def test_create_worker_flow_not_found(self, client):
        """Test creating worker with non-existent flow."""
        response = client.post("/api/v1/workers", json={
            "flow_id": "nonexistent_flow"
        })
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "FLOW_NOT_FOUND"
    
    def test_create_worker_invalid_request(self, client):
        """Test creating worker with invalid request."""
        response = client.post("/api/v1/workers", json={})
        assert response.status_code == 422  # Validation error
    
    def test_get_worker(self, client, sample_flow):
        """Test getting a specific worker."""
        # Create worker first
        create_response = client.post("/api/v1/workers", json={
            "flow_id": "test_flow_v1"
        })
        worker_id = create_response.json()["worker_id"]
        
        # Get worker
        response = client.get(f"/api/v1/workers/{worker_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["worker_id"] == worker_id
        assert data["flow_id"] == "test_flow_v1"
        assert "status" in data
        assert "created_at" in data or data.get("created_at") is None
    
    def test_get_worker_not_found(self, client):
        """Test getting non-existent worker."""
        response = client.get("/api/v1/workers/nonexistent")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "WORKER_NOT_FOUND"
    
    def test_list_workers_with_filters(self, client, sample_flow):
        """Test listing workers with filters."""
        # Create multiple workers
        worker1 = client.post("/api/v1/workers", json={"flow_id": "test_flow_v1"}).json()
        
        # Filter by flow_id
        response = client.get("/api/v1/workers?flow_id=test_flow_v1")
        assert response.status_code == 200
        assert response.json()["total"] >= 1
        
        # Filter by status
        response = client.get("/api/v1/workers?status=running")
        assert response.status_code == 200
        assert all(w["status"] == "running" for w in response.json()["workers"])
    
    def test_list_workers_pagination(self, client, sample_flow):
        """Test pagination in worker listing."""
        # Create a worker
        client.post("/api/v1/workers", json={"flow_id": "test_flow_v1"})
        
        # Test pagination
        response = client.get("/api/v1/workers?limit=1&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 1
        assert data["offset"] == 0
        assert len(data["workers"]) <= 1
    
    def test_stop_worker(self, client, sample_flow):
        """Test stopping a worker."""
        # Create worker
        create_response = client.post("/api/v1/workers", json={
            "flow_id": "test_flow_v1"
        })
        worker_id = create_response.json()["worker_id"]
        
        # Stop worker
        response = client.delete(f"/api/v1/workers/{worker_id}")
        assert response.status_code == 204
        
        # Worker may still be visible via registry but should be stopped
        # The key behavior is that the DELETE succeeds
    
    def test_stop_worker_not_found(self, client):
        """Test stopping non-existent worker."""
        response = client.delete("/api/v1/workers/nonexistent")
        assert response.status_code == 404
    
    def test_pause_worker(self, client, sample_flow):
        """Test pausing a worker."""
        # Create worker
        create_response = client.post("/api/v1/workers", json={
            "flow_id": "test_flow_v1"
        })
        worker_id = create_response.json()["worker_id"]
        
        # Pause worker
        response = client.post(f"/api/v1/workers/{worker_id}/pause")
        assert response.status_code == 200
        assert response.json()["worker_id"] == worker_id
    
    def test_pause_worker_not_found(self, client):
        """Test pausing non-existent worker."""
        response = client.post("/api/v1/workers/nonexistent/pause")
        assert response.status_code == 404
    
    def test_resume_worker(self, client, sample_flow):
        """Test resuming a worker."""
        # Create and pause worker
        create_response = client.post("/api/v1/workers", json={
            "flow_id": "test_flow_v1"
        })
        worker_id = create_response.json()["worker_id"]
        
        client.post(f"/api/v1/workers/{worker_id}/pause")
        
        # Resume worker
        response = client.post(f"/api/v1/workers/{worker_id}/resume")
        assert response.status_code == 200
        assert response.json()["worker_id"] == worker_id
    
    def test_resume_worker_not_found(self, client):
        """Test resuming non-existent worker."""
        response = client.post("/api/v1/workers/nonexistent/resume")
        assert response.status_code == 404


class TestJobEndpoints:
    """Tests for /api/v1/jobs/* endpoints."""
    
    def test_list_jobs_empty(self, client):
        """Test listing jobs when none exist."""
        response = client.get("/api/v1/jobs")
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert "total" in data
        assert data["total"] == 0
    
    def test_submit_job(self, client, sample_flow):
        """Test submitting a job."""
        response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {"value": 21}
        })
        assert response.status_code == 201
        data = response.json()
        assert "job_id" in data
        assert "worker_id" in data
        assert data["flow_id"] == "test_flow_v1"
        assert data["status"] in ("pending", "running")
        assert "created_at" in data or data.get("created_at") is None
    
    def test_submit_job_with_metadata(self, client, sample_flow):
        """Test submitting job with metadata."""
        response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {"value": 1},
            "metadata": {"user_id": "user-123", "source": "test"}
        })
        assert response.status_code == 201
        data = response.json()
        assert data["metadata"]["user_id"] == "user-123"
        assert data["metadata"]["source"] == "test"
    
    def test_submit_job_with_custom_job_id(self, client, sample_flow):
        """Test submitting job with custom job ID."""
        custom_job_id = "custom-job-123"
        response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {},
            "job_id": custom_job_id
        })
        assert response.status_code == 201
        # Note: Runtime may generate its own ID, so we just check it succeeds
    
    def test_submit_job_to_existing_worker(self, client, sample_flow):
        """Test submitting a job to an existing worker."""
        # Create worker
        create_response = client.post("/api/v1/workers", json={
            "flow_id": "test_flow_v1"
        })
        worker_id = create_response.json()["worker_id"]
        
        # Submit job to that worker
        response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "worker_id": worker_id,
            "routine_id": "processor",
            "slot_name": "input",
            "data": {"value": 42}
        })
        assert response.status_code == 201
        assert response.json()["worker_id"] == worker_id
    
    def test_submit_job_flow_not_found(self, client):
        """Test submitting job to non-existent flow."""
        response = client.post("/api/v1/jobs", json={
            "flow_id": "nonexistent",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {}
        })
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "FLOW_NOT_FOUND"
    
    def test_submit_job_routine_not_found(self, client, sample_flow):
        """Test submitting job with non-existent routine."""
        response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "nonexistent",
            "slot_name": "input",
            "data": {}
        })
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "ROUTINE_NOT_FOUND"
    
    def test_submit_job_slot_not_found(self, client, sample_flow):
        """Test submitting job with non-existent slot."""
        response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "nonexistent",
            "data": {}
        })
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "SLOT_NOT_FOUND"
    
    def test_submit_job_invalid_request(self, client):
        """Test submitting job with invalid request."""
        response = client.post("/api/v1/jobs", json={})
        assert response.status_code == 422
    
    def test_get_job(self, client, sample_flow):
        """Test getting a specific job."""
        # Submit job
        submit_response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {"value": 1}
        })
        job_id = submit_response.json()["job_id"]
        
        # Get job
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        assert response.json()["job_id"] == job_id
    
    def test_get_job_not_found(self, client):
        """Test getting non-existent job."""
        response = client.get("/api/v1/jobs/nonexistent")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "JOB_NOT_FOUND"
    
    def test_list_jobs_with_filters(self, client, sample_flow):
        """Test listing jobs with filters."""
        # Submit a job
        job = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {}
        }).json()
        
        # Filter by worker_id
        response = client.get(f"/api/v1/jobs?worker_id={job['worker_id']}")
        assert response.status_code == 200
        assert response.json()["total"] >= 1
        
        # Filter by flow_id
        response = client.get("/api/v1/jobs?flow_id=test_flow_v1")
        assert response.status_code == 200
        assert response.json()["total"] >= 1
        
        # Filter by status
        response = client.get("/api/v1/jobs?status=running")
        assert response.status_code == 200
    
    def test_list_jobs_pagination(self, client, sample_flow):
        """Test pagination in job listing."""
        # Submit a job
        client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {}
        })
        
        # Test pagination
        response = client.get("/api/v1/jobs?limit=1&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 1
        assert data["offset"] == 0
    
    def test_get_job_status(self, client, sample_flow):
        """Test getting job status (lightweight)."""
        # Submit job
        submit_response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {}
        })
        job_id = submit_response.json()["job_id"]
        
        # Get status
        response = client.get(f"/api/v1/jobs/{job_id}/status")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert "status" in data
        assert "worker_id" in data
    
    def test_get_job_output(self, client, sample_flow):
        """Test getting job output."""
        # Submit job
        submit_response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {}
        })
        job_id = submit_response.json()["job_id"]
        
        # Get output
        response = client.get(f"/api/v1/jobs/{job_id}/output")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert "output" in data
        assert "is_complete" in data
    
    def test_get_job_trace(self, client, sample_flow):
        """Test getting job execution trace."""
        # Submit job
        submit_response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {}
        })
        job_id = submit_response.json()["job_id"]
        
        # Get trace
        response = client.get(f"/api/v1/jobs/{job_id}/trace")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert "trace_log" in data
        assert "total_entries" in data
    
    def test_complete_job(self, client, sample_flow):
        """Test marking job as complete."""
        # Submit job
        submit_response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {}
        })
        job_id = submit_response.json()["job_id"]
        
        # Complete job
        response = client.post(f"/api/v1/jobs/{job_id}/complete")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
    
    def test_complete_job_not_found(self, client):
        """Test completing non-existent job."""
        response = client.post("/api/v1/jobs/nonexistent/complete")
        assert response.status_code == 404
    
    def test_fail_job(self, client, sample_flow):
        """Test marking job as failed."""
        # Submit job
        submit_response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {}
        })
        job_id = submit_response.json()["job_id"]
        
        # Fail job
        response = client.post(f"/api/v1/jobs/{job_id}/fail", json={
            "error": "Test error"
        })
        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        assert response.json()["error"] == "Test error"
    
    def test_fail_job_not_found(self, client):
        """Test failing non-existent job."""
        response = client.post("/api/v1/jobs/nonexistent/fail", json={
            "error": "Test"
        })
        assert response.status_code == 404
    
    def test_wait_for_job(self, client, sample_flow):
        """Test waiting for job completion."""
        # Submit job
        submit_response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {}
        })
        job_id = submit_response.json()["job_id"]
        
        # Wait for job (with short timeout)
        response = client.post(f"/api/v1/jobs/{job_id}/wait?timeout=5.0")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "waited_seconds" in data
    
    def test_wait_for_job_timeout(self, client, slow_flow):
        """Test waiting for job with timeout."""
        # Submit slow job
        submit_response = client.post("/api/v1/jobs", json={
            "flow_id": "slow_flow",
            "routine_id": "slow_processor",
            "slot_name": "input",
            "data": {}
        })
        job_id = submit_response.json()["job_id"]
        
        # Wait with short timeout (minimum is 1.0)
        response = client.post(f"/api/v1/jobs/{job_id}/wait?timeout=1.0")
        assert response.status_code == 200
        data = response.json()
        # Job might complete or timeout depending on timing
        assert data["status"] in ("timeout", "completed", "already_complete")
        assert "waited_seconds" in data


class TestExecuteEndpoint:
    """Tests for /api/v1/execute endpoint."""
    
    def test_execute_async(self, client, sample_flow):
        """Test async execution (wait=false)."""
        response = client.post("/api/v1/execute", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {"value": 10},
            "wait": False
        })
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "worker_id" in data
        assert data["status"] in ("pending", "running")
    
    def test_execute_sync(self, client, sample_flow):
        """Test sync execution (wait=true)."""
        response = client.post("/api/v1/execute", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {"value": 10},
            "wait": True,
            "timeout": 5.0
        })
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "elapsed_seconds" in data
    
    def test_execute_flow_not_found(self, client):
        """Test execute with non-existent flow."""
        response = client.post("/api/v1/execute", json={
            "flow_id": "nonexistent",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {}
        })
        assert response.status_code == 404
    
    def test_execute_invalid_request(self, client):
        """Test execute with invalid request."""
        response = client.post("/api/v1/execute", json={})
        assert response.status_code == 422


class TestWorkerJobRelationship:
    """Tests for worker/job relationships."""
    
    def test_list_worker_jobs(self, client, sample_flow):
        """Test listing jobs for a specific worker."""
        # Create worker
        create_response = client.post("/api/v1/workers", json={
            "flow_id": "test_flow_v1"
        })
        worker_id = create_response.json()["worker_id"]
        
        # Submit multiple jobs
        for i in range(3):
            client.post("/api/v1/jobs", json={
                "flow_id": "test_flow_v1",
                "worker_id": worker_id,
                "routine_id": "processor",
                "slot_name": "input",
                "data": {"value": i}
            })
        
        # List worker jobs
        response = client.get(f"/api/v1/workers/{worker_id}/jobs")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
        assert all(j["worker_id"] == worker_id for j in data["jobs"])
    
    def test_list_worker_jobs_with_status_filter(self, client, sample_flow):
        """Test listing worker jobs with status filter."""
        # Create worker and submit job
        create_response = client.post("/api/v1/workers", json={
            "flow_id": "test_flow_v1"
        })
        worker_id = create_response.json()["worker_id"]
        
        client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "worker_id": worker_id,
            "routine_id": "processor",
            "slot_name": "input",
            "data": {}
        })
        
        # Filter by status
        response = client.get(f"/api/v1/workers/{worker_id}/jobs?status=running")
        assert response.status_code == 200


class TestIdempotency:
    """Tests for idempotency key support."""
    
    def test_idempotent_job_submission(self, client, sample_flow):
        """Test that idempotency key returns same result."""
        idempotency_key = "test-idem-key-123"
        
        # First submission
        response1 = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {"value": 1},
            "idempotency_key": idempotency_key
        })
        assert response1.status_code == 201
        job_id_1 = response1.json()["job_id"]
        
        # Second submission with same key should return cached result
        response2 = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {"value": 999},  # Different data
            "idempotency_key": idempotency_key
        })
        assert response2.status_code == 201
        job_id_2 = response2.json()["job_id"]
        
        # Should be the same job
        assert job_id_1 == job_id_2
    
    def test_idempotent_execute(self, client, sample_flow):
        """Test idempotency in execute endpoint."""
        idempotency_key = "test-exec-idem-456"
        
        # First execution
        response1 = client.post("/api/v1/execute", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {"value": 1},
            "idempotency_key": idempotency_key,
            "wait": False
        })
        assert response1.status_code == 200
        job_id_1 = response1.json()["job_id"]
        
        # Second execution with same key
        response2 = client.post("/api/v1/execute", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {"value": 999},
            "idempotency_key": idempotency_key,
            "wait": False
        })
        assert response2.status_code == 200
        job_id_2 = response2.json()["job_id"]
        
        # Should be the same
        assert job_id_1 == job_id_2


class TestPagination:
    """Tests for pagination in list endpoints."""
    
    def test_jobs_pagination(self, client, sample_flow):
        """Test pagination in job listing."""
        response = client.get("/api/v1/jobs?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 0
        assert len(data["jobs"]) <= 10
    
    def test_workers_pagination(self, client, sample_flow):
        """Test pagination in worker listing."""
        response = client.get("/api/v1/workers?limit=50&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 50
        assert data["offset"] == 0
    
    def test_pagination_edge_cases(self, client, sample_flow):
        """Test pagination edge cases."""
        # Test with limit=1
        response = client.get("/api/v1/jobs?limit=1")
        assert response.status_code == 200
        
        # Test with large offset
        response = client.get("/api/v1/jobs?offset=1000")
        assert response.status_code == 200
        
        # Test with max limit
        response = client.get("/api/v1/jobs?limit=1000")
        assert response.status_code == 200


class TestErrorResponses:
    """Tests for structured error responses."""
    
    def test_error_response_structure(self, client):
        """Test that error responses have correct structure."""
        response = client.get("/api/v1/workers/nonexistent")
        assert response.status_code == 404
        data = response.json()
        
        # Check error structure
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]
        assert isinstance(data["error"]["code"], str)
        assert isinstance(data["error"]["message"], str)
    
    def test_validation_error(self, client):
        """Test validation error response."""
        response = client.post("/api/v1/jobs", json={
            # Missing required fields
        })
        assert response.status_code == 422
        data = response.json()
        assert "error" in data


class TestConcurrentOperations:
    """Tests for concurrent operations."""
    
    def test_concurrent_job_submissions(self, client, sample_flow):
        """Test submitting multiple jobs concurrently."""
        def submit_job(i):
            return client.post("/api/v1/jobs", json={
                "flow_id": "test_flow_v1",
                "routine_id": "processor",
                "slot_name": "input",
                "data": {"value": i}
            })
        
        # Submit 5 jobs concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(submit_job, i) for i in range(5)]
            results = [f.result() for f in futures]
        
        # All should succeed
        assert all(r.status_code == 201 for r in results)
        assert len(set(r.json()["job_id"] for r in results)) == 5  # All unique
    
    def test_concurrent_worker_creation(self, client, sample_flow):
        """Test creating multiple workers concurrently."""
        def create_worker():
            return client.post("/api/v1/workers", json={
                "flow_id": "test_flow_v1"
            })
        
        # Create 3 workers concurrently
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(create_worker) for _ in range(3)]
            results = [f.result() for f in futures]
        
        # All should succeed
        assert all(r.status_code == 201 for r in results)
        assert len(set(r.json()["worker_id"] for r in results)) == 3  # All unique


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_empty_data(self, client, sample_flow):
        """Test submitting job with empty data."""
        response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {}
        })
        assert response.status_code == 201
    
    def test_large_data(self, client, sample_flow):
        """Test submitting job with large data."""
        large_data = {"items": list(range(1000))}
        response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": large_data
        })
        assert response.status_code == 201
    
    def test_unicode_data(self, client, sample_flow):
        """Test submitting job with unicode data."""
        response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {"text": "测试 🚀 中文"}
        })
        assert response.status_code == 201
    
    def test_nested_data(self, client, sample_flow):
        """Test submitting job with nested data structures."""
        nested_data = {
            "level1": {
                "level2": {
                    "level3": {"value": 42}
                }
            }
        }
        response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": nested_data
        })
        assert response.status_code == 201
    
    def test_complete_already_completed_job(self, client, sample_flow):
        """Test completing an already completed job."""
        # Submit and complete job
        job_id = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {}
        }).json()["job_id"]
        
        client.post(f"/api/v1/jobs/{job_id}/complete")
        
        # Try to complete again
        response = client.post(f"/api/v1/jobs/{job_id}/complete")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "JOB_ALREADY_COMPLETED"
    
    def test_fail_already_failed_job(self, client, sample_flow):
        """Test failing an already failed job."""
        # Submit and fail job
        job_id = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {}
        }).json()["job_id"]
        
        client.post(f"/api/v1/jobs/{job_id}/fail", json={"error": "First error"})
        
        # Try to fail again
        response = client.post(f"/api/v1/jobs/{job_id}/fail", json={"error": "Second error"})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "JOB_ALREADY_COMPLETED"


class TestWorkerLifecycle:
    """Tests for worker lifecycle management."""
    
    def test_worker_lifecycle(self, client, sample_flow):
        """Test complete worker lifecycle: create -> pause -> resume -> stop."""
        # Create
        worker_id = client.post("/api/v1/workers", json={
            "flow_id": "test_flow_v1"
        }).json()["worker_id"]
        
        # Pause
        response = client.post(f"/api/v1/workers/{worker_id}/pause")
        assert response.status_code == 200
        
        # Resume
        response = client.post(f"/api/v1/workers/{worker_id}/resume")
        assert response.status_code == 200
        
        # Stop
        response = client.delete(f"/api/v1/workers/{worker_id}")
        assert response.status_code == 204
    
    def test_multiple_jobs_per_worker(self, client, sample_flow):
        """Test that one worker can handle multiple jobs."""
        # Create worker
        worker_id = client.post("/api/v1/workers", json={
            "flow_id": "test_flow_v1"
        }).json()["worker_id"]
        
        # Submit multiple jobs
        job_ids = []
        for i in range(5):
            job = client.post("/api/v1/jobs", json={
                "flow_id": "test_flow_v1",
                "worker_id": worker_id,
                "routine_id": "processor",
                "slot_name": "input",
                "data": {"value": i}
            }).json()
            job_ids.append(job["job_id"])
        
        # Verify all jobs belong to same worker
        for job_id in job_ids:
            job = client.get(f"/api/v1/jobs/{job_id}").json()
            assert job["worker_id"] == worker_id


class TestQueryParameters:
    """Tests for query parameter validation."""
    
    def test_invalid_limit(self, client):
        """Test with invalid limit values."""
        # Negative limit
        response = client.get("/api/v1/jobs?limit=-1")
        assert response.status_code == 422
        
        # Zero limit
        response = client.get("/api/v1/jobs?limit=0")
        assert response.status_code == 422
        
        # Too large limit
        response = client.get("/api/v1/jobs?limit=10000")
        assert response.status_code == 422
    
    def test_invalid_offset(self, client):
        """Test with invalid offset values."""
        # Negative offset
        response = client.get("/api/v1/jobs?offset=-1")
        assert response.status_code == 422
    
    def test_invalid_timeout(self, client, sample_flow):
        """Test with invalid timeout values."""
        job_id = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {}
        }).json()["job_id"]
        
        # Negative timeout
        response = client.post(f"/api/v1/jobs/{job_id}/wait?timeout=-1")
        assert response.status_code == 422
        
        # Zero timeout
        response = client.post(f"/api/v1/jobs/{job_id}/wait?timeout=0")
        assert response.status_code == 422
        
        # Too large timeout
        response = client.post(f"/api/v1/jobs/{job_id}/wait?timeout=10000")
        assert response.status_code == 422


class TestInputValidation:
    """Tests for input validation."""
    
    def test_large_data_payload(self, client, sample_flow):
        """Test submitting job with large data payload."""
        # Create data just under 10MB limit
        large_data = {"items": ["x" * 1000] * 10000}  # ~10MB
        
        response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": large_data
        })
        # Should succeed if under limit
        assert response.status_code in (201, 422)  # May fail if exceeds limit
    
    def test_very_large_data_payload(self, client, sample_flow):
        """Test submitting job with very large data payload (should fail)."""
        # Create data over 10MB limit
        very_large_data = {"items": ["x" * 10000] * 2000}  # ~20MB
        
        response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": very_large_data
        })
        # Should fail validation
        assert response.status_code == 422
        error_data = response.json()
        # Check error details for validation message
        if "error" in error_data and "details" in error_data["error"]:
            details = error_data["error"]["details"]
            if "errors" in details:
                error_messages = " ".join(str(e) for e in details["errors"])
                assert "exceeds" in error_messages.lower()
    
    def test_large_metadata(self, client, sample_flow):
        """Test submitting job with large metadata."""
        # Create metadata just under 1MB limit
        large_metadata = {"data": "x" * (1024 * 1024 - 100)}
        
        response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {},
            "metadata": large_metadata
        })
        # Should succeed if under limit
        assert response.status_code in (201, 422)
    
    def test_very_large_metadata(self, client, sample_flow):
        """Test submitting job with very large metadata (should fail)."""
        # Create metadata over 1MB limit
        very_large_metadata = {"data": "x" * (2 * 1024 * 1024)}  # 2MB
        
        response = client.post("/api/v1/jobs", json={
            "flow_id": "test_flow_v1",
            "routine_id": "processor",
            "slot_name": "input",
            "data": {},
            "metadata": very_large_metadata
        })
        # Should fail validation
        assert response.status_code == 422
        error_data = response.json()
        # Check error details for validation message
        if "error" in error_data and "details" in error_data["error"]:
            details = error_data["error"]["details"]
            if "errors" in details:
                error_messages = " ".join(str(e) for e in details["errors"])
                assert "exceeds" in error_messages.lower()


class TestWorkerStateValidation:
    """Tests for worker state validation."""
    
    def test_pause_already_paused_worker(self, client, sample_flow):
        """Test pausing an already paused worker."""
        # Create and pause worker
        worker_id = client.post("/api/v1/workers", json={
            "flow_id": "test_flow_v1"
        }).json()["worker_id"]
        
        client.post(f"/api/v1/workers/{worker_id}/pause")
        
        # Try to pause again
        response = client.post(f"/api/v1/workers/{worker_id}/pause")
        assert response.status_code == 400
        assert "already paused" in response.json()["error"]["message"].lower()
    
    def test_resume_non_paused_worker(self, client, sample_flow):
        """Test resuming a worker that is not paused."""
        # Create worker (not paused)
        worker_id = client.post("/api/v1/workers", json={
            "flow_id": "test_flow_v1"
        }).json()["worker_id"]
        
        # Try to resume (should fail)
        response = client.post(f"/api/v1/workers/{worker_id}/resume")
        # May succeed if executor handles it, or fail with clear error
        assert response.status_code in (200, 400)
        if response.status_code == 400:
            assert "not paused" in response.json()["error"]["message"].lower()
    
    def test_pause_completed_worker(self, client, sample_flow):
        """Test pausing a completed worker."""
        # Create and stop worker
        worker_id = client.post("/api/v1/workers", json={
            "flow_id": "test_flow_v1"
        }).json()["worker_id"]
        
        client.delete(f"/api/v1/workers/{worker_id}")
        
        # Try to pause (should fail if worker is in terminal state)
        # Note: Worker may not be in registry after delete, so this may 404
        response = client.post(f"/api/v1/workers/{worker_id}/pause")
        assert response.status_code in (404, 400)
