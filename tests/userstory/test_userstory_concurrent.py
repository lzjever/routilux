"""
Category 7: Concurrent User Scenarios - User Story Tests

Tests for concurrent operations and multi-user scenarios, including:
- Multiple concurrent workers
- Concurrent job submission to same worker
- Concurrent flow modifications
- Thread safety under load

These tests verify system behavior under concurrent access.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

pytestmark = pytest.mark.userstory


class TestConcurrentWorkers:
    """Test scenarios with multiple concurrent workers.

    User Story: As a user, I want to run multiple workers
    simultaneously without interference.
    """

    def test_create_multiple_workers_concurrently(self, api_client, registered_pipeline_flow):
        """Test creating multiple workers concurrently."""

        def create_worker(i):
            response = api_client.post(
                "/api/v1/workers", json={"flow_id": registered_pipeline_flow.flow_id}
            )
            return response.json()["worker_id"]

        # Create 5 workers concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_worker, i) for i in range(5)]
            worker_ids = [f.result() for f in as_completed(futures)]

        # All should succeed with unique IDs
        assert len(set(worker_ids)) == 5

        # Cleanup
        for worker_id in worker_ids:
            api_client.delete(f"/api/v1/workers/{worker_id}")

    def test_concurrent_workers_process_jobs_independently(self, api_client):
        """Test that concurrent workers process jobs independently."""
        from tests.helpers.flow_builder import FlowBuilder

        # Create flow
        builder = FlowBuilder(api_client)
        builder.create_empty("concurrent_worker_flow")
        builder.build_pipeline()

        # Create multiple workers
        worker_ids = []
        for _ in range(3):
            response = api_client.post("/api/v1/workers", json={"flow_id": builder.flow_id})
            worker_ids.append(response.json()["worker_id"])

        # Submit job to each worker
        job_ids = []
        for worker_id in worker_ids:
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

        # All jobs should be created
        assert len(job_ids) == 3

        # Verify each job is assigned to correct worker
        for i, job_id in enumerate(job_ids):
            response = api_client.get(f"/api/v1/jobs/{job_id}")
            assert response.json()["worker_id"] == worker_ids[i]

        # Cleanup
        for worker_id in worker_ids:
            api_client.delete(f"/api/v1/workers/{worker_id}")
        builder.delete()


class TestConcurrentJobSubmission:
    """Test concurrent job submission scenarios.

    User Story: As a user, I want to submit multiple jobs
    concurrently without conflicts.
    """

    def test_concurrent_job_submission_to_same_worker(self, api_client, registered_pipeline_flow):
        """Test submitting multiple jobs to the same worker concurrently."""
        flow_id = registered_pipeline_flow.flow_id

        # Create worker
        response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
        worker_id = response.json()["worker_id"]

        def submit_job(i):
            response = api_client.post(
                "/api/v1/jobs",
                json={
                    "flow_id": flow_id,
                    "worker_id": worker_id,
                    "routine_id": "source",
                    "slot_name": "trigger",
                    "data": {"index": i},
                },
            )
            return response.json()["job_id"]

        # Submit 10 jobs concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(submit_job, i) for i in range(10)]
            job_ids = [f.result() for f in as_completed(futures)]

        # All should succeed with unique job IDs
        assert len(set(job_ids)) == 10

    def test_concurrent_job_submission_to_different_workers(self, api_client):
        """Test submitting jobs to different workers concurrently."""
        from tests.helpers.flow_builder import FlowBuilder

        # Create flow
        builder = FlowBuilder(api_client)
        builder.create_empty("multi_worker_flow")
        builder.build_pipeline()

        # Create multiple workers
        worker_ids = []
        for _ in range(3):
            response = api_client.post("/api/v1/workers", json={"flow_id": builder.flow_id})
            worker_ids.append(response.json()["worker_id"])

        def submit_job(worker_id):
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
            return response.json()["job_id"]

        # Submit jobs to different workers concurrently
        with ThreadPoolExecutor(max_workers=len(worker_ids)) as executor:
            futures = [executor.submit(submit_job, wid) for wid in worker_ids]
            job_ids = [f.result() for f in as_completed(futures)]

        # All should succeed
        assert len(job_ids) == len(worker_ids)

        # Cleanup
        for worker_id in worker_ids:
            api_client.delete(f"/api/v1/workers/{worker_id}")
        builder.delete()


class TestConcurrentFlowModifications:
    """Test concurrent flow modification scenarios.

    User Story: As a user, I want to modify flows while
    they're being used without breaking the system.
    """

    def test_concurrent_flow_creation(self, api_client):
        """Test creating multiple flows concurrently."""
        from tests.helpers.flow_builder import FlowBuilder

        def create_flow(i):
            builder = FlowBuilder(api_client)
            builder.create_empty(f"concurrent_flow_{i}")
            builder.add_routine("source", "data_source", {"count": 1})
            builder.add_routine("sink", "data_sink")
            builder.add_connection("source", "output", "sink", "input")
            return builder.flow_id

        # Create 5 flows concurrently
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_flow, i) for i in range(5)]
            flow_ids = [f.result() for f in as_completed(futures)]

        # All should succeed with unique IDs
        assert len(set(flow_ids)) == 5

        # Cleanup
        for flow_id in flow_ids:
            builder = FlowBuilder(api_client)
            builder.flow_id = flow_id
            builder.delete()

    def test_concurrent_flow_validation(self, api_client):
        """Test validating multiple flows concurrently."""
        from tests.helpers.flow_builder import FlowBuilder

        # Create flows first
        flow_ids = []
        for i in range(3):
            builder = FlowBuilder(api_client)
            builder.create_empty(f"validation_flow_{i}")
            builder.build_pipeline()
            flow_ids.append(builder.flow_id)

        def validate_flow(flow_id):
            response = api_client.post(f"/api/v1/flows/{flow_id}/validate")
            data = response.json()
            # Flow is valid if there are no errors (warnings are acceptable)
            # Check errors field if available, otherwise check issues for errors
            errors = data.get("errors", [])
            if not errors:
                # Check issues for errors if errors field not available
                issues = data.get("issues", [])
                errors = [issue for issue in issues if issue.startswith("Error:")]
            return len(errors) == 0

        # Validate all flows concurrently
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(validate_flow, fid) for fid in flow_ids]
            results = [f.result() for f in as_completed(futures)]

        # All should be valid (no errors, warnings are acceptable)
        assert all(results)

        # Cleanup
        for flow_id in flow_ids:
            builder = FlowBuilder(api_client)
            builder.flow_id = flow_id
            builder.delete()


class TestConcurrentReadOperations:
    """Test concurrent read operations.

    User Story: As a user, I want multiple clients to read
    workflow information concurrently.
    """

    def test_concurrent_flow_listings(self, api_client):
        """Test multiple clients listing flows concurrently."""

        def list_flows(i):
            response = api_client.get("/api/v1/flows")
            return response.json()["total"]

        # List flows 10 times concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(list_flows, i) for i in range(10)]
            results = [f.result() for f in as_completed(futures)]

        # All should return consistent counts
        assert len(set(results)) <= 2  # May vary slightly if other tests run

    def test_concurrent_worker_listings(self, api_client):
        """Test multiple clients listing workers concurrently."""

        def list_workers(i):
            response = api_client.get("/api/v1/workers")
            return response.json()["total"]

        # List workers 10 times concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(list_workers, i) for i in range(10)]
            results = [f.result() for f in as_completed(futures)]

        # All should return consistent counts
        assert all(isinstance(r, int) for r in results)

    def test_concurrent_job_status_checks(self, api_client, registered_pipeline_flow):
        """Test multiple clients checking job status concurrently."""
        flow_id = registered_pipeline_flow.flow_id

        # Create worker and submit job
        response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
        worker_id = response.json()["worker_id"]

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
        job_id = response.json()["job_id"]

        def check_status(i):
            response = api_client.get(f"/api/v1/jobs/{job_id}/status")
            return response.json()["status"]

        # Check status 20 times concurrently
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(check_status, i) for i in range(20)]
            results = [f.result() for f in as_completed(futures)]

        # All should succeed
        assert len(results) == 20


class TestConcurrentMixedOperations:
    """Test mixed concurrent operations.

    User Story: As a user, I want the system to handle
    various operations concurrently without issues.
    """

    def test_mixed_read_write_operations(self, api_client):
        """Test mixed read and write operations concurrently."""
        from tests.helpers.flow_builder import FlowBuilder

        # Create initial flow
        builder = FlowBuilder(api_client)
        builder.create_empty("mixed_ops_flow")
        builder.build_pipeline()

        def create_worker():
            response = api_client.post("/api/v1/workers", json={"flow_id": builder.flow_id})
            return response.json()["worker_id"]

        def list_workers():
            response = api_client.get("/api/v1/workers")
            return response.json()["total"]

        def get_flow():
            response = api_client.get(f"/api/v1/flows/{builder.flow_id}")
            return response.json()["flow_id"]

        # Run mixed operations concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            # Submit various operations
            for _ in range(3):
                futures.append(executor.submit(create_worker))
            for _ in range(3):
                futures.append(executor.submit(list_workers))
            for _ in range(3):
                futures.append(executor.submit(get_flow))

            results = [f.result() for f in as_completed(futures)]

        # All operations should complete
        assert len(results) == 9

        # Cleanup
        builder.delete()

    def test_concurrent_job_lifecycle_operations(self, api_client, registered_pipeline_flow):
        """Test concurrent job lifecycle operations."""
        flow_id = registered_pipeline_flow.flow_id

        # Create worker
        response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
        worker_id = response.json()["worker_id"]

        # Submit initial jobs
        job_ids = []
        for _ in range(5):
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
            job_ids.append(response.json()["job_id"])

        def get_job(job_id):
            response = api_client.get(f"/api/v1/jobs/{job_id}")
            return response.json()["status"]

        def get_job_status(job_id):
            response = api_client.get(f"/api/v1/jobs/{job_id}/status")
            return response.json()["status"]

        def get_job_output(job_id):
            response = api_client.get(f"/api/v1/jobs/{job_id}/output")
            return response.json()["job_id"]

        # Run various job operations concurrently
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = []
            for job_id in job_ids:
                futures.append(executor.submit(get_job, job_id))
                futures.append(executor.submit(get_job_status, job_id))
                futures.append(executor.submit(get_job_output, job_id))

            results = [f.result() for f in as_completed(futures)]

        # All operations should complete
        assert len(results) == 15


class TestRaceConditionPrevention:
    """Test that race conditions are properly prevented.

    User Story: As a user, I want the system to handle
    concurrent operations safely without race conditions.
    """

    def test_no_duplicate_worker_ids(self, api_client):
        """Test that concurrent worker creation produces unique IDs."""
        from tests.helpers.flow_builder import FlowBuilder

        builder = FlowBuilder(api_client)
        builder.create_empty("race_test_flow")
        builder.build_pipeline()

        def create_worker():
            response = api_client.post("/api/v1/workers", json={"flow_id": builder.flow_id})
            return response.json()["worker_id"]

        # Create many workers rapidly
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(create_worker) for _ in range(20)]
            worker_ids = [f.result() for f in as_completed(futures)]

        # All IDs should be unique
        assert len(worker_ids) == len(set(worker_ids))

        # Cleanup
        for worker_id in worker_ids:
            api_client.delete(f"/api/v1/workers/{worker_id}")
        builder.delete()

    def test_no_duplicate_job_ids(self, api_client, registered_pipeline_flow):
        """Test that concurrent job submission produces unique IDs."""
        flow_id = registered_pipeline_flow.flow_id

        # Create worker
        response = api_client.post("/api/v1/workers", json={"flow_id": flow_id})
        worker_id = response.json()["worker_id"]

        def submit_job(i):
            response = api_client.post(
                "/api/v1/jobs",
                json={
                    "flow_id": flow_id,
                    "worker_id": worker_id,
                    "routine_id": "source",
                    "slot_name": "trigger",
                    "data": {"index": i},
                },
            )
            return response.json()["job_id"]

        # Submit many jobs rapidly
        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(submit_job, i) for i in range(30)]
            job_ids = [f.result() for f in as_completed(futures)]

        # All IDs should be unique
        assert len(job_ids) == len(set(job_ids))
