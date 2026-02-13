"""Tests for WorkerManager start_worker() registration timing.

These tests verify the fixes for Issue 3: Manager registration timing race.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from routilux.core.flow import Flow
from routilux.core.manager import WorkerManager, reset_worker_manager
from routilux.core.routine import Routine
from routilux.core.status import ExecutionStatus


class TestManagerRegistrationTiming:
    """Tests for start_worker() registration timing."""

    @pytest.fixture(autouse=True)
    def reset_manager(self):
        """Reset global manager before and after each test."""
        reset_worker_manager()
        yield
        reset_worker_manager()

    @pytest.fixture
    def flow(self):
        """Create a basic flow for testing."""
        flow = Flow("test_flow")
        routine = Routine()
        flow.add_routine(routine)
        return flow

    def test_executor_not_registered_on_start_failure(self, flow):
        """Test that executor is NOT registered if start() fails."""
        manager = WorkerManager(max_workers=4)

        # Mock WorkerExecutor.start() to raise an exception
        # Patch at the module level where it's imported
        import routilux.core.executor as executor_module

        with patch.object(executor_module, "WorkerExecutor") as mock_executor_class:
            mock_executor = MagicMock()
            mock_executor.start.side_effect = RuntimeError("Start failed")
            mock_executor.worker_state = MagicMock()
            mock_executor.worker_state.worker_id = "test-worker-id"
            mock_executor_class.return_value = mock_executor

            with pytest.raises(RuntimeError, match="Start failed"):
                manager.start_worker(flow)

            # Executor should NOT be registered
            assert len(manager.running_workers) == 0

        manager.shutdown(wait=False)

    def test_executor_registered_after_successful_start(self, flow):
        """Test that executor IS registered after successful start()."""
        manager = WorkerManager(max_workers=4)

        worker_state = manager.start_worker(flow)

        # Wait a bit for start to complete
        time.sleep(0.1)

        # Executor should be registered
        assert worker_state.worker_id in manager.running_workers
        assert len(manager.running_workers) == 1

        manager.shutdown(wait=False)

    def test_worker_state_marked_failed_on_start_failure(self, flow):
        """Test that WorkerState is marked FAILED when start() fails.

        This test verifies that when executor.start() raises an exception,
        the manager properly sets the worker_state status to FAILED.
        """
        from routilux.core import executor as executor_module

        # Patch WorkerExecutor at the source module
        original_worker_executor = executor_module.WorkerExecutor

        captured_worker_state = None

        def mock_worker_executor(*args, **kwargs):
            nonlocal captured_worker_state
            # Create real executor to get real worker_state
            executor = original_worker_executor(*args, **kwargs)
            captured_worker_state = executor.worker_state

            # Make start() fail
            def failing_start():
                raise RuntimeError("Start failed")

            executor.start = failing_start
            return executor

        with patch.object(executor_module, "WorkerExecutor", mock_worker_executor):
            manager = WorkerManager(max_workers=4)

            with pytest.raises(RuntimeError, match="Start failed"):
                manager.start_worker(flow)

            # The worker_state should have been marked FAILED
            assert captured_worker_state is not None
            assert captured_worker_state.status == ExecutionStatus.FAILED

            manager.shutdown(wait=False)

    def test_concurrent_start_worker_calls(self, flow):
        """Test that concurrent start_worker calls are handled correctly."""
        manager = WorkerManager(max_workers=10)

        num_workers = 10
        worker_ids = []
        errors = []
        lock = threading.Lock()

        def start_worker_thread(i):
            try:
                state = manager.start_worker(flow)
                with lock:
                    worker_ids.append(state.worker_id)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [
            threading.Thread(target=start_worker_thread, args=(i,)) for i in range(num_workers)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        # All workers should have started
        assert len(errors) == 0, f"Errors during concurrent start: {errors}"
        assert len(worker_ids) == num_workers

        # All should be registered
        with manager._lock:
            assert len(manager.running_workers) == num_workers

        manager.shutdown(wait=False)

    def test_start_after_shutdown_raises_error(self, flow):
        """Test that starting a worker after shutdown raises RuntimeError."""
        manager = WorkerManager(max_workers=4)

        manager.shutdown(wait=True)

        with pytest.raises(RuntimeError, match="shut down"):
            manager.start_worker(flow)


class TestManagerShutdownSafety:
    """Tests for safe shutdown behavior."""

    @pytest.fixture(autouse=True)
    def reset_manager(self):
        """Reset global manager before and after each test."""
        reset_worker_manager()
        yield
        reset_worker_manager()

    @pytest.fixture
    def flow(self):
        """Create a basic flow for testing."""
        flow = Flow("test_flow")
        routine = Routine()
        flow.add_routine(routine)
        return flow

    def test_shutdown_cancels_running_workers(self, flow):
        """Test that shutdown cancels all running workers."""
        manager = WorkerManager(max_workers=4)

        # Start multiple workers
        states = []
        for _ in range(3):
            state = manager.start_worker(flow)
            states.append(state)

        time.sleep(0.1)  # Let workers start

        # Shutdown
        manager.shutdown(wait=True, timeout=5.0)

        # All workers should be cancelled or completed
        for state in states:
            assert state.status in (
                ExecutionStatus.CANCELLED,
                ExecutionStatus.COMPLETED,
                ExecutionStatus.FAILED,
            )

    def test_shutdown_clears_running_workers(self, flow):
        """Test that shutdown clears the running_workers dict."""
        manager = WorkerManager(max_workers=4)

        manager.start_worker(flow)
        time.sleep(0.1)

        manager.shutdown(wait=True, timeout=5.0)

        assert len(manager.running_workers) == 0

    def test_fast_cleanup_for_exit(self, flow):
        """Test that fast_cleanup=True skips waiting."""
        manager = WorkerManager(max_workers=4)

        manager.start_worker(flow)
        time.sleep(0.1)

        # Fast cleanup should not wait
        start = time.time()
        manager.shutdown(wait=False, fast_cleanup=True)
        elapsed = time.time() - start

        # Should be very fast (no waiting)
        assert elapsed < 1.0
        assert len(manager.running_workers) == 0
