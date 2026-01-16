"""Tests for JobExecutor."""

import pytest
import time
from routilux import Flow, Routine
from routilux.job_executor import JobExecutor
from routilux.job_manager import get_job_manager, reset_job_manager
from routilux.job_state import JobState
from routilux.status import ExecutionStatus


class DelayRoutine(Routine):
    """Routine with configurable delay."""

    def __init__(self, delay: float = 0.1):
        super().__init__()
        self.delay = delay
        self.trigger_slot = self.define_slot("trigger", handler=self.handle_trigger)
        self.output_event = self.define_event("output", ["result"])

    def handle_trigger(self, index=0, **kwargs):
        """Handle trigger with delay."""
        time.sleep(self.delay)
        self.emit("output", result=f"job_{index}_result")


class ErrorRoutine(Routine):
    """Routine that raises an error."""

    def __init__(self):
        super().__init__()
        self.trigger_slot = self.define_slot("trigger", handler=self.handle_trigger)

    def handle_trigger(self, **kwargs):
        """Handle trigger with error."""
        raise ValueError("Test error")


def test_job_executor_basic():
    """Test basic JobExecutor functionality."""
    reset_job_manager()
    flow = Flow(flow_id="test")
    routine = DelayRoutine(delay=0.1)
    flow.add_routine(routine, "test")

    job_state = JobState(flow.flow_id)
    manager = get_job_manager()

    executor = JobExecutor(
        flow=flow,
        job_state=job_state,
        global_thread_pool=manager.global_thread_pool,
    )

    executor.start("test", {})

    # Wait a bit
    time.sleep(0.3)

    # Check status
    assert job_state.status in [ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED]


def test_job_executor_timeout():
    """Test timeout handling."""
    reset_job_manager()
    flow = Flow(flow_id="test")
    routine = DelayRoutine(delay=0.5)  # Longer delay
    flow.add_routine(routine, "test")

    job_state = JobState(flow.flow_id)
    manager = get_job_manager()

    executor = JobExecutor(
        flow=flow,
        job_state=job_state,
        global_thread_pool=manager.global_thread_pool,
        timeout=0.2,  # Short timeout
    )

    executor.start("test", {})

    # Wait for timeout
    executor.wait(timeout=1.0)

    # Check status
    assert job_state.status == ExecutionStatus.FAILED
    assert "timed out" in job_state.shared_data.get("error", "").lower()


def test_job_executor_pause_resume():
    """Test pause and resume."""
    reset_job_manager()
    flow = Flow(flow_id="test")
    routine = DelayRoutine(delay=0.2)
    flow.add_routine(routine, "test")

    job_state = JobState(flow.flow_id)
    manager = get_job_manager()

    executor = JobExecutor(
        flow=flow,
        job_state=job_state,
        global_thread_pool=manager.global_thread_pool,
    )

    executor.start("test", {})

    # Wait a bit
    time.sleep(0.05)

    # Pause
    executor.pause(reason="Test pause")

    assert executor.is_paused() is True
    assert job_state.status == ExecutionStatus.PAUSED

    # Resume
    executor.resume()

    assert executor.is_paused() is False

    # Wait for completion
    executor.wait(timeout=5.0)

    assert job_state.status == ExecutionStatus.COMPLETED


def test_job_executor_cancel():
    """Test cancellation."""
    reset_job_manager()
    flow = Flow(flow_id="test")
    routine = DelayRoutine(delay=0.5)
    flow.add_routine(routine, "test")

    job_state = JobState(flow.flow_id)
    manager = get_job_manager()

    executor = JobExecutor(
        flow=flow,
        job_state=job_state,
        global_thread_pool=manager.global_thread_pool,
    )

    executor.start("test", {})

    # Wait a bit
    time.sleep(0.05)

    # Cancel
    executor.cancel(reason="Test cancel")

    assert job_state.status == ExecutionStatus.CANCELLED
    assert executor.is_running() is False


def test_job_executor_error_handling():
    """Test error handling."""
    reset_job_manager()
    flow = Flow(flow_id="test")
    routine = ErrorRoutine()
    flow.add_routine(routine, "test")

    # Set error handler to STOP strategy to ensure job fails on error
    from routilux import ErrorHandler, ErrorStrategy
    flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.STOP))

    job_state = JobState(flow.flow_id)
    manager = get_job_manager()

    executor = JobExecutor(
        flow=flow,
        job_state=job_state,
        global_thread_pool=manager.global_thread_pool,
    )

    executor.start("test", {})

    # Wait for error
    executor.wait(timeout=5.0)

    # Check status - with STOP strategy, job should fail
    assert job_state.status == ExecutionStatus.FAILED


def test_multiple_jobs_concurrent():
    """Test multiple jobs running concurrently."""
    reset_job_manager()
    flow = Flow(flow_id="test")
    routine = DelayRoutine(delay=0.3)
    flow.add_routine(routine, "test")

    manager = get_job_manager()

    # Start 5 jobs
    jobs = []
    for i in range(5):
        job = manager.start_job(flow, "test", entry_params={"index": i})
        jobs.append(job)

    # Wait for all
    completed = manager.wait_for_all_jobs(timeout=10.0)
    assert completed is True

    # Check all completed
    for job in jobs:
        assert job.status == ExecutionStatus.COMPLETED


def test_job_executor_cleanup():
    """Test that executor is cleaned up after completion."""
    reset_job_manager()
    flow = Flow(flow_id="test")
    routine = DelayRoutine(delay=0.1)
    flow.add_routine(routine, "test")

    manager = get_job_manager()
    job_state = manager.start_job(flow, "test")

    # Wait for completion
    manager.wait_for_job(job_state.job_id, timeout=5.0)

    # Executor should be removed
    executor = manager.get_job(job_state.job_id)
    assert executor is None
