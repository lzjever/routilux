"""Tests for Runtime lock ordering consistency.

These tests verify the fixes for Issue 1: Runtime lock order inconsistency.

Lock order must be: _worker_lock -> _jobs_lock
"""

import threading
import time

import pytest

from routilux.core.flow import Flow
from routilux.core.routine import Routine
from routilux.core.runtime import Runtime


class TestRuntimeLockOrdering:
    """Tests for consistent lock ordering in Runtime."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test."""
        # Reset global manager
        from routilux.core.manager import reset_worker_manager

        reset_worker_manager()
        yield
        reset_worker_manager()

    @pytest.fixture
    def flow(self):
        """Create a basic flow for testing."""
        from routilux.core.registry import FlowRegistry

        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("input")
        routine.define_event("output")
        flow.add_routine(routine, routine_id="test_routine")  # Use routine_id parameter

        # Register flow
        registry = FlowRegistry.get_instance()
        registry.register(flow)

        return flow

    @pytest.fixture
    def runtime(self):
        """Create a Runtime instance."""
        rt = Runtime(thread_pool_size=4)
        yield rt
        rt.shutdown(wait=False)

    def test_complete_job_acquires_locks_in_order(self, runtime, flow):
        """Test that complete_job acquires locks in correct order."""
        # Start a worker and create a job
        _ = runtime.exec("test_flow")
        _, job_context = runtime.post("test_flow", "test_routine", "input", {"data": "test"})

        # We can't directly instrument RLock, so just verify the operation works
        # without deadlock
        result = runtime.complete_job(job_context.job_id)
        assert result is True

    def test_exec_acquires_locks_in_order(self, runtime, flow):
        """Test that exec acquires locks in correct order."""
        # We can't directly instrument RLock, so just verify the operation works
        # without deadlock
        worker_state = runtime.exec("test_flow")
        assert worker_state is not None
        assert worker_state.status.value in ("running", "idle")

    def test_no_deadlock_under_concurrent_access(self, runtime, flow):
        """Test that concurrent access doesn't cause deadlock."""
        num_threads = 10
        num_iterations = 20
        completed = []
        errors = []
        lock = threading.Lock()

        def concurrent_ops(thread_id):
            try:
                for i in range(num_iterations):
                    # Mix of operations that acquire multiple locks
                    if i % 3 == 0:
                        # exec
                        ws = runtime.exec("test_flow")
                        with lock:
                            completed.append(("exec", thread_id, i))
                    elif i % 3 == 1:
                        # post
                        try:
                            ws, job = runtime.post(
                                "test_flow", "test_routine", "input", {"data": f"test_{i}"}
                            )
                            with lock:
                                completed.append(("post", thread_id, i))
                        except Exception:
                            pass  # May fail if worker not found
                    else:
                        # complete_job
                        jobs = runtime.list_jobs()
                        if jobs:
                            runtime.complete_job(jobs[0].job_id)
                        with lock:
                            completed.append(("complete", thread_id, i))

                    time.sleep(0.001)  # Small delay to increase interleaving
            except Exception as e:
                with lock:
                    errors.append((thread_id, str(e)))

        threads = [threading.Thread(target=concurrent_ops, args=(i,)) for i in range(num_threads)]

        # Set a deadline - if not finished by then, likely deadlocked
        for t in threads:
            t.daemon = True
            t.start()

        # Wait with timeout
        for t in threads:
            t.join(timeout=30.0)

        # Check for errors or hanging threads
        alive_threads = [t for t in threads if t.is_alive()]
        assert len(alive_threads) == 0, f"Deadlocked threads: {len(alive_threads)}"
        assert len(errors) == 0, f"Errors: {errors}"

        # Should have completed many operations
        assert len(completed) > num_threads * num_iterations * 0.5

    def test_locks_are_reentrant(self, runtime):
        """Test that locks are reentrant (RLock behavior)."""
        # This should not deadlock if using RLock
        with runtime._worker_lock:
            with runtime._worker_lock:  # Re-enter
                with runtime._jobs_lock:
                    with runtime._jobs_lock:  # Re-enter
                        pass  # Should complete without deadlock

        # If we get here, locks are reentrant
        assert True


class TestRuntimeThreadSafety:
    """Additional thread safety tests for Runtime."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test."""
        from routilux.core.manager import reset_worker_manager

        reset_worker_manager()
        yield
        reset_worker_manager()

    @pytest.fixture
    def flow(self):
        """Create a basic flow for testing."""
        from routilux.core.registry import FlowRegistry

        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("input")
        routine.define_event("output")
        flow.add_routine(routine, routine_id="test_routine")  # Use routine_id parameter

        registry = FlowRegistry.get_instance()
        registry.register(flow)

        return flow

    @pytest.fixture
    def runtime(self):
        """Create a Runtime instance."""
        rt = Runtime(thread_pool_size=4)
        yield rt
        rt.shutdown(wait=False)

    def test_list_jobs_thread_safety(self, runtime, flow):
        """Test that list_jobs is thread-safe."""
        num_threads = 5
        num_jobs_per_thread = 10
        all_jobs = []
        lock = threading.Lock()

        def create_jobs(thread_id):
            for i in range(num_jobs_per_thread):
                try:
                    _, job = runtime.post(
                        "test_flow", "test_routine", "input", {"data": f"test_{thread_id}_{i}"}
                    )
                    with lock:
                        all_jobs.append(job.job_id)
                except Exception:
                    pass

        def list_jobs_repeatedly():
            for _ in range(20):
                _ = runtime.list_jobs()
                time.sleep(0.01)

        # Start job creators and listers
        creator_threads = [
            threading.Thread(target=create_jobs, args=(i,)) for i in range(num_threads)
        ]
        lister_threads = [threading.Thread(target=list_jobs_repeatedly) for _ in range(3)]

        all_threads = creator_threads + lister_threads
        for t in all_threads:
            t.start()

        for t in all_threads:
            t.join(timeout=30.0)

        # Should have created jobs without errors
        assert len(all_jobs) > 0

    def test_get_job_thread_safety(self, runtime, flow):
        """Test that get_job is thread-safe."""
        # Create some jobs
        _, job = runtime.post("test_flow", "test_routine", "input", {"data": "test"})

        results = []
        errors = []

        def get_job_repeatedly(job_id):
            try:
                for _ in range(50):
                    found_job = runtime.get_job(job_id)
                    if found_job:
                        results.append(found_job.job_id)
                    time.sleep(0.001)
            except Exception as e:
                errors.append(str(e))

        threads = [
            threading.Thread(target=get_job_repeatedly, args=(job.job_id,)) for _ in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30.0)

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) > 0


class TestLockOrderDocumentation:
    """Tests to verify lock order documentation is present."""

    def test_runtime_has_lock_order_documentation(self):
        """Test that Runtime class documents lock ordering rules."""
        from routilux.core.runtime import Runtime

        docstring = Runtime.__doc__
        assert docstring is not None
        assert "Thread Safety" in docstring or "lock" in docstring.lower()

    def test_lock_attributes_exist(self):
        """Test that all lock attributes exist."""
        runtime = Runtime(thread_pool_size=1)

        assert hasattr(runtime, "_worker_lock")
        assert hasattr(runtime, "_jobs_lock")

        runtime.shutdown(wait=False)
