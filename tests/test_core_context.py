"""Tests for JobContext and context management."""

import time
from datetime import datetime

from routilux.core import (
    JobContext,
    get_current_job,
    get_current_job_id,
    get_current_worker_state,
    set_current_job,
)


class TestJobContext:
    """Test JobContext class."""

    def test_job_context_creation(self):
        """Test creating a JobContext with default values."""
        job = JobContext()

        assert job.job_id is not None
        assert len(job.job_id) > 0
        assert job.worker_id == ""
        assert isinstance(job.created_at, datetime)
        assert job.completed_at is None
        assert job.metadata == {}
        assert job.data == {}
        assert job.trace_log == []
        assert job.status == "pending"
        assert job.error is None

    def test_job_context_custom_values(self):
        """Test creating a JobContext with custom values."""
        job_id = "test-job-123"
        worker_id = "worker-456"
        metadata = {"user_id": "user123", "source": "api"}

        job = JobContext(job_id=job_id, worker_id=worker_id, metadata=metadata)

        assert job.job_id == job_id
        assert job.worker_id == worker_id
        assert job.metadata == metadata

    def test_job_context_trace(self):
        """Test adding trace entries to JobContext."""
        job = JobContext()

        job.trace("routine1", "slot_activated", {"data": "test"})
        job.trace("routine2", "completed", {"result": "success"})

        assert len(job.trace_log) == 2
        assert job.trace_log[0]["routine_id"] == "routine1"
        assert job.trace_log[0]["action"] == "slot_activated"
        assert job.trace_log[0]["details"] == {"data": "test"}
        assert "timestamp" in job.trace_log[0]

        assert job.trace_log[1]["routine_id"] == "routine2"
        assert job.trace_log[1]["action"] == "completed"

    def test_job_context_set_data(self):
        """Test setting job-level data."""
        job = JobContext()

        job.set_data("key1", "value1")
        job.set_data("key2", {"nested": "data"})

        assert job.get_data("key1") == "value1"
        assert job.get_data("key2") == {"nested": "data"}
        assert job.data == {"key1": "value1", "key2": {"nested": "data"}}

    def test_job_context_get_data_default(self):
        """Test getting job data with default value."""
        job = JobContext()

        assert job.get_data("nonexistent") is None
        assert job.get_data("nonexistent", "default") == "default"

    def test_job_context_start(self):
        """Test starting a job."""
        job = JobContext()

        assert job.status == "pending"
        job.start()

        assert job.status == "running"
        assert job.completed_at is None

    def test_job_context_complete(self):
        """Test completing a job."""
        job = JobContext()
        job.start()

        job.complete()

        assert job.status == "completed"
        assert job.completed_at is not None
        assert isinstance(job.completed_at, datetime)

    def test_job_context_fail(self):
        """Test failing a job."""
        job = JobContext()
        job.start()

        error_msg = "Test error"
        job.complete(status="failed", error=error_msg)

        assert job.status == "failed"
        assert job.error == error_msg
        assert job.completed_at is not None

    def test_job_context_to_dict(self):
        """Test converting JobContext to dictionary."""
        job = JobContext(job_id="test-123", worker_id="worker-456")
        job.set_data("key", "value")
        job.trace("routine1", "action", {"detail": "test"})

        job_dict = job.to_dict()

        assert job_dict["job_id"] == "test-123"
        assert job_dict["worker_id"] == "worker-456"
        assert job_dict["data"] == {"key": "value"}
        assert len(job_dict["trace_log"]) == 1
        assert "created_at" in job_dict


class TestContextVariables:
    """Test context variable management."""

    def test_set_and_get_current_job(self):
        """Test setting and getting current job from context."""
        job = JobContext(job_id="test-job")

        # Initially no job
        assert get_current_job() is None

        # Set job
        set_current_job(job)
        assert get_current_job() == job
        assert get_current_job_id() == "test-job"

        # Reset
        set_current_job(None)
        assert get_current_job() is None

    def test_context_isolation(self):
        """Test that context variables are isolated between threads."""
        import threading

        results = {}

        def worker(thread_id):
            job = JobContext(job_id=f"job-{thread_id}")
            set_current_job(job)
            time.sleep(0.1)  # Simulate work
            results[thread_id] = get_current_job_id()
            set_current_job(None)

        threads = []
        for i in range(3):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Each thread should see its own job
        assert results[0] == "job-0"
        assert results[1] == "job-1"
        assert results[2] == "job-2"

    def test_get_current_worker_state(self):
        """Test getting current worker state from context."""
        # Initially no worker state
        assert get_current_worker_state() is None

        # Note: We can't easily test setting worker state without creating
        # a WorkerState, which requires a Flow. This will be tested in
        # integration tests.
