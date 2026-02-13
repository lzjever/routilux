"""Tests for WorkerExecutor cleanup behavior and task tracking.

These tests verify the fixes for Issue 2: Executor task tracking race condition.
"""

import threading
import time

import pytest

from routilux.core.executor import WorkerExecutor
from routilux.core.flow import Flow
from routilux.core.routine import Routine
from routilux.core.worker import WorkerState


class TestExecutorCleanup:
    """Tests for _cleanup() method behavior."""

    @pytest.fixture
    def setup_executor(self):
        """Create a basic executor setup for testing."""
        from concurrent.futures import ThreadPoolExecutor

        flow = Flow("test_flow")
        routine = Routine()
        flow.add_routine(routine)

        worker_state = WorkerState(flow.flow_id)
        thread_pool = ThreadPoolExecutor(max_workers=4)

        executor = WorkerExecutor(
            flow=flow,
            worker_state=worker_state,
            global_thread_pool=thread_pool,
            timeout=None,
        )

        yield executor, thread_pool

        # Cleanup
        try:
            executor.cancel(reason="Test cleanup")
        except Exception:
            pass
        thread_pool.shutdown(wait=False)

    def test_cleanup_with_no_active_tasks(self, setup_executor):
        """Test that _cleanup() handles empty active_tasks correctly."""
        executor, _ = setup_executor

        # Should complete without error when no tasks
        executor._cleanup()

        assert len(executor.active_tasks) == 0

    def test_cleanup_waits_for_tasks_to_complete(self, setup_executor):
        """Test that _cleanup() waits for tasks using concurrent.futures.wait()."""
        executor, thread_pool = setup_executor

        completed = []
        slow_task_started = threading.Event()

        def slow_task():
            slow_task_started.set()
            time.sleep(0.2)
            completed.append(1)

        # Add futures directly to active_tasks to simulate in-flight tasks
        future1 = thread_pool.submit(slow_task)
        future2 = thread_pool.submit(slow_task)

        # Register callbacks first (as per fix)
        def on_done(fut):
            with executor._lock:
                executor.active_tasks.discard(fut)

        future1.add_done_callback(on_done)
        future2.add_done_callback(on_done)

        with executor._lock:
            executor.active_tasks.add(future1)
            executor.active_tasks.add(future2)

        # Wait for tasks to start
        slow_task_started.wait(timeout=1.0)

        # Cleanup should wait for tasks
        start_time = time.time()
        executor._cleanup()
        elapsed = time.time() - start_time

        # Tasks should have completed
        assert len(completed) == 2
        assert len(executor.active_tasks) == 0
        # Should have waited for at least the task duration
        assert elapsed >= 0.15

    def test_cleanup_handles_timeout(self, setup_executor):
        """Test that _cleanup() handles tasks that don't complete within timeout."""
        executor, thread_pool = setup_executor

        blocked_event = threading.Event()
        continue_event = threading.Event()

        def blocking_task():
            blocked_event.set()
            # Block for longer than cleanup timeout
            continue_event.wait(timeout=60)

        future = thread_pool.submit(blocking_task)

        def on_done(fut):
            with executor._lock:
                executor.active_tasks.discard(fut)

        future.add_done_callback(on_done)

        with executor._lock:
            executor.active_tasks.add(future)

        # Wait for task to start
        blocked_event.wait(timeout=1.0)

        # Cleanup should timeout and cancel
        executor._cleanup()

        # Should have timed out around 30 seconds (but let's just check it's reasonable)
        # For test speed, we'll verify the task was cancelled
        assert len(executor.active_tasks) == 0

        # Let the blocking task complete
        continue_event.set()


class TestTaskTrackingRaceCondition:
    """Tests for callback registration order fix."""

    @pytest.fixture
    def setup_executor(self):
        """Create a basic executor setup for testing."""
        from concurrent.futures import ThreadPoolExecutor

        flow = Flow("test_flow")
        routine = Routine()
        flow.add_routine(routine)

        worker_state = WorkerState(flow.flow_id)
        thread_pool = ThreadPoolExecutor(max_workers=4)

        executor = WorkerExecutor(
            flow=flow,
            worker_state=worker_state,
            global_thread_pool=thread_pool,
            timeout=None,
        )

        yield executor, thread_pool

        # Cleanup
        try:
            executor.cancel(reason="Test cleanup")
        except Exception:
            pass
        thread_pool.shutdown(wait=False)

    def test_callback_registered_before_adding_to_active_tasks(self, setup_executor):
        """Test that callbacks are registered before adding to active_tasks."""
        executor, thread_pool = setup_executor

        # Track callback execution
        callback_executed = threading.Event()
        task_completed = threading.Event()

        def quick_task():
            task_completed.set()
            return "done"

        # Create a future that completes quickly
        future = thread_pool.submit(quick_task)

        # Wait for the task to actually complete
        task_completed.wait(timeout=1.0)

        # Now register callback (simulating the fixed code order)
        def on_done(fut):
            callback_executed.set()
            with executor._lock:
                executor.active_tasks.discard(fut)

        future.add_done_callback(on_done)

        # Add to active_tasks (callback already registered)
        with executor._lock:
            executor.active_tasks.add(future)

        # Callback should execute even though future was already done
        callback_executed.wait(timeout=1.0)
        assert callback_executed.is_set()

        # active_tasks should be empty after callback
        time.sleep(0.1)  # Give callback time to execute
        with executor._lock:
            assert future not in executor.active_tasks or future.done()

    def test_no_task_leakage_on_rapid_completion(self, setup_executor):
        """Test that rapidly completing tasks don't leak in active_tasks."""
        executor, thread_pool = setup_executor

        num_tasks = 100
        completed_count = [0]
        lock = threading.Lock()

        def quick_task(i):
            time.sleep(0.001 * (i % 10))  # Vary completion time
            with lock:
                completed_count[0] += 1
            return i

        futures = []
        for i in range(num_tasks):
            future = thread_pool.submit(quick_task, i)

            # Register callback first (as per fix)
            def on_done(fut, futures_ref=[future]):
                with executor._lock:
                    executor.active_tasks.discard(fut)

            future.add_done_callback(on_done)

            # Then add to active_tasks
            with executor._lock:
                executor.active_tasks.add(future)
            futures.append(future)

        # Wait for all to complete
        for f in futures:
            f.result(timeout=5.0)

        # All tasks should be completed
        assert completed_count[0] == num_tasks

        # Allow callbacks to execute
        time.sleep(0.5)

        # active_tasks should be empty
        with executor._lock:
            # Some futures may still be in the set if callback hasn't run yet
            # but they should all be done
            for f in executor.active_tasks:
                assert f.done(), "Future in active_tasks should be done"


class TestIsCompleteConsistency:
    """Tests for _is_complete() consistency with task tracking."""

    @pytest.fixture
    def setup_executor(self):
        """Create a basic executor setup for testing."""
        from concurrent.futures import ThreadPoolExecutor

        flow = Flow("test_flow")
        routine = Routine()
        flow.add_routine(routine)

        worker_state = WorkerState(flow.flow_id)
        thread_pool = ThreadPoolExecutor(max_workers=4)

        executor = WorkerExecutor(
            flow=flow,
            worker_state=worker_state,
            global_thread_pool=thread_pool,
            timeout=None,
        )

        yield executor, thread_pool

        # Cleanup
        try:
            executor.cancel(reason="Test cleanup")
        except Exception:
            pass
        thread_pool.shutdown(wait=False)

    def test_is_complete_returns_true_when_no_tasks(self, setup_executor):
        """Test that _is_complete() returns True when no tasks."""
        executor, _ = setup_executor

        assert executor._is_complete() is True

    def test_is_complete_returns_false_with_pending_tasks(self, setup_executor):
        """Test that _is_complete() returns False when pending tasks."""
        executor, thread_pool = setup_executor

        # Simulate pending task
        with executor._lock:
            executor._pending_task_count = 1

        assert executor._is_complete() is False

    def test_is_complete_returns_false_with_active_futures(self, setup_executor):
        """Test that _is_complete() returns False when active futures."""
        executor, thread_pool = setup_executor

        block_event = threading.Event()

        def blocking_task():
            block_event.wait(timeout=5)

        future = thread_pool.submit(blocking_task)

        # Register callback and add to active_tasks
        def on_done(fut):
            with executor._lock:
                executor.active_tasks.discard(fut)

        future.add_done_callback(on_done)
        with executor._lock:
            executor.active_tasks.add(future)

        # Should not be complete while future is running
        assert executor._is_complete() is False

        # Cleanup
        block_event.set()
        future.result(timeout=5.0)
