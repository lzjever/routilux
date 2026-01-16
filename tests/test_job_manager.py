"""Tests for GlobalJobManager."""

import pytest
import time
from routilux import Flow, Routine
from routilux.job_manager import get_job_manager, GlobalJobManager, reset_job_manager
from routilux.status import ExecutionStatus


class SimpleTestRoutine(Routine):
    """Simple test routine for testing."""

    def __init__(self):
        super().__init__()
        self.trigger_slot = self.define_slot("trigger", handler=self.handle)
        self.output_event = self.define_event("output", ["data"])

    def handle(self, **kwargs):
        """Handle trigger."""
        self.emit("output", data="test")


def test_global_job_manager_singleton():
    """Test that GlobalJobManager is a singleton."""
    reset_job_manager()
    manager1 = get_job_manager(max_workers=50)
    manager2 = get_job_manager(max_workers=100)  # Should return same instance

    assert manager1 is manager2
    assert manager1.max_workers == 50  # First call's value


def test_start_job():
    """Test starting a job."""
    reset_job_manager()
    flow = Flow(flow_id="test_flow")
    routine = SimpleTestRoutine()
    flow.add_routine(routine, "test")

    manager = get_job_manager()
    job_state = manager.start_job(
        flow=flow,
        entry_routine_id="test",
        entry_params={"data": "test"}
    )

    assert job_state.status == ExecutionStatus.RUNNING
    assert job_state.job_id is not None

    # Wait for completion
    time.sleep(0.5)

    executor = manager.get_job(job_state.job_id)
    # Executor might be None if job already completed
    if executor is not None:
        assert executor.is_running() or executor.job_state.status == ExecutionStatus.COMPLETED


def test_wait_for_all_jobs():
    """Test waiting for all jobs."""
    reset_job_manager()
    flow = Flow(flow_id="test_flow")
    routine = SimpleTestRoutine()
    flow.add_routine(routine, "test")

    manager = get_job_manager()

    # Start multiple jobs
    job1 = manager.start_job(flow, "test")
    job2 = manager.start_job(flow, "test")
    job3 = manager.start_job(flow, "test")

    # Wait for all
    completed = manager.wait_for_all_jobs(timeout=5.0)
    assert completed is True

    # Check all completed
    for job in [job1, job2, job3]:
        executor = manager.get_job(job.job_id)
        assert executor is None or not executor.is_running()


def test_wait_for_job():
    """Test waiting for a specific job."""
    reset_job_manager()
    flow = Flow(flow_id="test_flow")
    routine = SimpleTestRoutine()
    flow.add_routine(routine, "test")

    manager = get_job_manager()
    job_state = manager.start_job(flow, "test")

    completed = manager.wait_for_job(job_state.job_id, timeout=5.0)
    assert completed is True


def test_get_job():
    """Test getting a job executor."""
    reset_job_manager()
    flow = Flow(flow_id="test_flow")
    routine = SimpleTestRoutine()
    flow.add_routine(routine, "test")

    manager = get_job_manager()
    job_state = manager.start_job(flow, "test")

    executor = manager.get_job(job_state.job_id)
    assert executor is not None
    assert executor.job_state.job_id == job_state.job_id

    # Wait for completion
    manager.wait_for_job(job_state.job_id, timeout=5.0)

    # After completion, executor should be removed
    executor = manager.get_job(job_state.job_id)
    assert executor is None


def test_list_jobs():
    """Test listing running jobs."""
    reset_job_manager()
    flow = Flow(flow_id="test_flow")
    routine = SimpleTestRoutine()
    flow.add_routine(routine, "test")

    manager = get_job_manager()

    # Start multiple jobs
    job1 = manager.start_job(flow, "test")
    job2 = manager.start_job(flow, "test")
    job3 = manager.start_job(flow, "test")

    # List jobs
    job_ids = manager.list_jobs()
    assert len(job_ids) == 3
    assert job1.job_id in job_ids
    assert job2.job_id in job_ids
    assert job3.job_id in job_ids

    # Wait for all to complete
    manager.wait_for_all_jobs(timeout=5.0)

    # After completion, list should be empty
    job_ids = manager.list_jobs()
    assert len(job_ids) == 0


def test_shutdown():
    """Test shutting down the job manager."""
    reset_job_manager()
    flow = Flow(flow_id="test_flow")
    routine = SimpleTestRoutine()
    flow.add_routine(routine, "test")

    manager = get_job_manager()
    job_state = manager.start_job(flow, "test")

    # Shutdown
    manager.shutdown(wait=True, timeout=5.0)

    assert manager.is_shutdown() is True

    # Should not be able to start new jobs
    with pytest.raises(RuntimeError, match="shut down"):
        manager.start_job(flow, "test")


def test_multiple_jobs_concurrent():
    """Test multiple jobs running concurrently."""
    reset_job_manager()
    flow = Flow(flow_id="test_flow")
    routine = SimpleTestRoutine()
    flow.add_routine(routine, "test")

    manager = get_job_manager()

    # Start 10 jobs
    jobs = []
    for i in range(10):
        job = manager.start_job(flow, "test", entry_params={"index": i})
        jobs.append(job)

    # Wait for all
    completed = manager.wait_for_all_jobs(timeout=10.0)
    assert completed is True

    # Check all completed
    for job in jobs:
        assert job.status == ExecutionStatus.COMPLETED
