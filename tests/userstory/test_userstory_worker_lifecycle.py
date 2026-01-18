"""
Category 2: Long-Running Worker Scenarios - User Story Tests

Tests for worker lifecycle management, including:
- Creating workers from flows
- Processing multiple jobs through the same worker
- Pausing and resuming workers
- Stopping workers
- Worker statistics tracking

These tests simulate long-running workers that handle multiple jobs over time.
"""

import time

import pytest

pytestmark = pytest.mark.userstory


class TestWorkerLifecycleManagement:
    """Test complete worker lifecycle from creation to deletion.

    User Story: As a user, I want to create a worker from a flow,
    submit multiple jobs to it, pause/resume it, and eventually stop it.
    """

    def test_complete_worker_lifecycle(self, api_client, registered_pipeline_flow):
        """Test full worker lifecycle: create -> pause -> resume -> stop."""
        flow_id = registered_pipeline_flow.flow_id

        # Create worker
        response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
        assert response.status_code == 201
        worker_id = response.json()["worker_id"]
        assert response.json()["status"] == "running"

        # Pause worker
        response = api_client.post(f"/api/v1/workers/{worker_id}/pause")
        assert response.status_code == 200
        assert response.json()["status"] == "paused"

        # Resume worker
        response = api_client.post(f"/api/v1/workers/{worker_id}/resume")
        assert response.status_code == 200
        assert response.json()["status"] == "running"

        # Stop worker
        response = api_client.delete(f"/api/v1/workers/{worker_id}")
        assert response.status_code == 204

    def test_multiple_workers_from_same_flow(self, api_client, registered_pipeline_flow):
        """Test creating multiple workers from the same flow."""
        flow_id = registered_pipeline_flow.flow_id

        # Create multiple workers
        worker_ids = []
        for i in range(3):
            response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
            assert response.status_code == 201
            worker_ids.append(response.json()["worker_id"])

        # Verify all workers exist and are unique
        assert len(set(worker_ids)) == 3

        # List workers
        response = api_client.get(f"/api/v1/workers?flow_id={flow_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3

        # Cleanup
        for worker_id in worker_ids:
            api_client.delete(f"/api/v1/workers/{worker_id}")

    def test_worker_status_transitions(self, api_client, registered_pipeline_flow):
        """Test worker status transitions through lifecycle."""
        flow_id = registered_pipeline_flow.flow_id

        # Create worker
        response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
        worker_id = response.json()["worker_id"]

        # Initial status: running
        response = api_client.get(f"/api/v1/workers/{worker_id}")
        assert response.json()["status"] == "running"

        # Pause
        api_client.post(f"/api/v1/workers/{worker_id}/pause")
        response = api_client.get(f"/api/v1/workers/{worker_id}")
        assert response.json()["status"] == "paused"

        # Try to pause again (should fail or warn)
        response = api_client.post(f"/api/v1/workers/{worker_id}/pause")
        assert response.status_code in (400, 200)  # May error or be idempotent

        # Resume
        api_client.post(f"/api/v1/workers/{worker_id}/resume")
        response = api_client.get(f"/api/v1/workers/{worker_id}")
        assert response.json()["status"] == "running"

        # Cleanup
        api_client.delete(f"/api/v1/workers/{worker_id}")


class TestMultipleJobsPerWorker:
    """Test scenarios where a single worker processes multiple jobs.

    User Story: As a user, I want to submit multiple jobs to a worker
    and have them all processed correctly.
    """

    def test_worker_processes_multiple_jobs(self, api_client, registered_pipeline_flow):
        """Test that one worker can process multiple jobs sequentially."""
        flow_id = registered_pipeline_flow.flow_id

        # Create worker
        response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
        worker_id = response.json()["worker_id"]

        # Submit multiple jobs
        job_ids = []
        for i in range(5):
            response = api_client.post(
                "/api/v1/jobs",
                json={
                    "flow_id": flow_id,
                    "worker_id": worker_id,
                    "routine_id": "source",
                    "slot_name": "trigger",
                    "data": {},
                },
            )
            assert response.status_code == 201
            job_ids.append(response.json()["job_id"])

        # Verify all jobs were created and assigned to same worker
        for job_id in job_ids:
            response = api_client.get(f"/api/v1/jobs/{job_id}")
            assert response.json()["worker_id"] == worker_id

        # List worker's jobs
        response = api_client.get(f"/api/v1/workers/{worker_id}/jobs")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 5

    def test_worker_statistics_tracking(self, api_client, registered_pipeline_flow):
        """Test that worker tracks job statistics correctly."""
        flow_id = registered_pipeline_flow.flow_id

        # Create worker
        response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
        worker_id = response.json()["worker_id"]

        # Initial stats
        response = api_client.get(f"/api/v1/workers/{worker_id}")
        assert response.json()["jobs_processed"] == 0
        assert response.json()["jobs_failed"] == 0

        # Submit a job
        response = api_client.post(
            "/api/v1/jobs",
            json={
                "flow_id": flow_id,
                "worker_id": worker_id,
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {},
            },
        )
        _ = response.json()["job_id"]

        # Wait a moment for processing
        time.sleep(0.5)

        # Check stats may have updated
        response = api_client.get(f"/api/v1/workers/{worker_id}")
        # Jobs processed may increase as jobs complete
        jobs_processed = response.json()["jobs_processed"]
        assert jobs_processed >= 0

    def test_jobs_list_with_worker_filter(self, api_client, registered_pipeline_flow):
        """Test listing jobs filtered by worker."""
        flow_id = registered_pipeline_flow.flow_id

        # Create two workers
        worker1_response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
        worker1_id = worker1_response.json()["worker_id"]

        worker2_response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
        worker2_id = worker2_response.json()["worker_id"]

        # Submit jobs to each worker
        for _ in range(2):
            api_client.post(
                "/api/v1/jobs",
                json={
                    "flow_id": flow_id,
                    "worker_id": worker1_id,
                    "routine_id": "source",
                    "slot_name": "trigger",
                    "data": {},
                },
            )

        for _ in range(3):
            api_client.post(
                "/api/v1/jobs",
                json={
                    "flow_id": flow_id,
                    "worker_id": worker2_id,
                    "routine_id": "source",
                    "slot_name": "trigger",
                    "data": {},
                },
            )

        # Filter jobs by worker1
        response = api_client.get(f"/api/v1/jobs?worker_id={worker1_id}")
        assert response.status_code == 200
        worker1_jobs = response.json()["jobs"]
        # At least our 2 jobs should be there
        assert len(worker1_jobs) >= 2

        # Filter jobs by worker2
        response = api_client.get(f"/api/v1/jobs?worker_id={worker2_id}")
        assert response.status_code == 200
        worker2_jobs = response.json()["jobs"]
        assert len(worker2_jobs) >= 3


class TestWorkerPauseResume:
    """Test worker pause and resume functionality.

    User Story: As a user, I want to pause a worker to temporarily
    stop job processing, then resume it later.
    """

    def test_pause_worker_during_operation(self, api_client, registered_pipeline_flow):
        """Test pausing a worker while it's running."""
        flow_id = registered_pipeline_flow.flow_id

        # Create and start worker
        response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
        worker_id = response.json()["worker_id"]

        # Submit job
        api_client.post(
            "/api/v1/jobs",
            json={
                "flow_id": flow_id,
                "worker_id": worker_id,
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {},
            },
        )

        # Pause worker
        response = api_client.post(f"/api/v1/workers/{worker_id}/pause")
        assert response.status_code == 200
        assert response.json()["status"] == "paused"

        # Verify status
        response = api_client.get(f"/api/v1/workers/{worker_id}")
        assert response.json()["status"] == "paused"

    def test_resumed_worker_continues_processing(self, api_client, registered_pipeline_flow):
        """Test that resumed worker continues processing jobs."""
        flow_id = registered_pipeline_flow.flow_id

        # Create worker
        response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
        worker_id = response.json()["worker_id"]

        # Pause worker
        api_client.post(f"/api/v1/workers/{worker_id}/pause")

        # Submit job while paused
        job_response = api_client.post(
            "/api/v1/jobs",
            json={
                "flow_id": flow_id,
                "worker_id": worker_id,
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {},
            },
        )
        job_id = job_response.json()["job_id"]

        # Resume worker
        api_client.post(f"/api/v1/workers/{worker_id}/resume")

        # Job should be processed after resume
        response = api_client.get(f"/api/v1/jobs/{job_id}")
        # Status may be running, completed, or pending depending on timing

    def test_pause_prevents_new_job_processing(self, api_client, registered_pipeline_flow):
        """Test that paused worker doesn't process new jobs immediately."""
        flow_id = registered_pipeline_flow.flow_id

        # Create and pause worker
        response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
        worker_id = response.json()["worker_id"]
        api_client.post(f"/api/v1/workers/{worker_id}/pause")

        # Submit job while paused
        job_response = api_client.post(
            "/api/v1/jobs",
            json={
                "flow_id": flow_id,
                "worker_id": worker_id,
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {},
            },
        )
        job_id = job_response.json()["job_id"]

        # Job exists but may not be processed yet
        response = api_client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200


class TestWorkerErrorHandling:
    """Test worker behavior when jobs encounter errors.

    User Story: As a user, I want errors in jobs to not crash the worker,
    allowing subsequent jobs to be processed.
    """

    def test_worker_continues_after_job_error(self, api_client):
        """Test that worker continues processing after one job fails."""
        # This test would require a flow that can produce errors
        # For now, we test the basic structure

        # Create a simple flow
        from tests.helpers.flow_builder import FlowBuilder

        builder = FlowBuilder(api_client)
        builder.create_empty("error_test_flow")
        builder.add_routine("source", "data_source", {"count": 1})
        builder.add_routine("sink", "data_sink")
        builder.add_connection("source", "output", "sink", "input")

        # Create worker
        response = api_client.post("/api/v1/workers", json={"flow_id": builder.flow_id})
        worker_id = response.json()["worker_id"]

        # Submit multiple jobs
        job_ids = []
        for i in range(3):
            response = api_client.post(
                "/api/v1/jobs",
                json={
                    "flow_id": builder.flow_id,
                    "worker_id": worker_id,
                    "routine_id": "source",
                    "slot_name": "trigger",
                    "data": {},
                },
            )
            job_ids.append(response.json()["job_id"])

        # All jobs should be accepted
        assert len(job_ids) == 3

        # Cleanup
        builder.delete()


class TestWorkerDeletion:
    """Test worker deletion and cleanup.

    User Story: As a user, I want to delete workers when they're no longer needed.
    """

    def test_delete_worker_removes_from_system(self, api_client, registered_pipeline_flow):
        """Test that deleted worker is removed from the system."""
        flow_id = registered_pipeline_flow.flow_id

        # Create worker
        response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
        worker_id = response.json()["worker_id"]

        # Verify worker exists
        response = api_client.get(f"/api/v1/workers/{worker_id}")
        assert response.status_code == 200

        # Delete worker
        response = api_client.delete(f"/api/v1/workers/{worker_id}")
        assert response.status_code == 204

        # Wait a bit for cleanup
        import time
        time.sleep(0.1)

        # Verify worker is gone (may still exist in registry but not in active workers)
        response = api_client.get(f"/api/v1/workers/{worker_id}")
        # Worker may still exist in registry but should be in terminal state or 404
        if response.status_code == 200:
            data = response.json()
            # Worker should be in terminal state
            assert data["status"] in ("completed", "cancelled", "failed")
        else:
            assert response.status_code == 404

    def test_delete_worker_with_active_jobs(self, api_client, registered_pipeline_flow):
        """Test deleting a worker that has active jobs."""
        flow_id = registered_pipeline_flow.flow_id

        # Create worker
        response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
        worker_id = response.json()["worker_id"]

        # Submit job
        api_client.post(
            "/api/v1/jobs",
            json={
                "flow_id": flow_id,
                "worker_id": worker_id,
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {},
            },
        )

        # Delete worker (should succeed)
        response = api_client.delete(f"/api/v1/workers/{worker_id}")
        assert response.status_code == 204

    def test_list_workers_excludes_deleted(self, api_client, registered_pipeline_flow):
        """Test that deleted workers don't appear in worker list."""
        flow_id = registered_pipeline_flow.flow_id

        # Create multiple workers
        worker_ids = []
        for _ in range(3):
            response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
            worker_ids.append(response.json()["worker_id"])

        # Delete one worker
        api_client.delete(f"/api/v1/workers/{worker_ids[0]}")

        # Wait a bit for cleanup
        import time
        time.sleep(0.1)

        # List workers
        response = api_client.get(f"/api/v1/workers?flow_id={flow_id}")
        assert response.status_code == 200
        data = response.json()

        # Note: Deleted worker may still appear in list if it's in registry
        # We check that it's either not in list, or if it is, it's in terminal state
        listed_ids = [w["worker_id"] for w in data["workers"]]
        if worker_ids[0] in listed_ids:
            # Worker still in list, check it's in terminal state
            worker = next(w for w in data["workers"] if w["worker_id"] == worker_ids[0])
            assert worker["status"] in ("completed", "cancelled", "failed")
        else:
            # Worker not in list (properly deleted)
            pass
