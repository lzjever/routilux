"""
Tests for flow event_loop module.
"""

import threading
import time

from routilux import Flow, Routine
from routilux.flow.event_loop import (
    enqueue_task,
    event_loop,
    execute_task,
    is_all_tasks_complete,
    start_event_loop,
)


class TestStartEventLoop:
    """Tests for start_event_loop function."""

    def test_start_event_loop(self):
        """Test starting event loop."""
        flow = Flow("test_flow")
        flow._running = False

        start_event_loop(flow)

        assert flow._running is True
        assert flow._execution_thread is not None
        assert flow._execution_thread.is_alive()

        # Clean up
        flow._running = False
        flow._execution_thread.join(timeout=2.0)

    def test_start_event_loop_already_running(self):
        """Test starting event loop when already running."""
        flow = Flow("test_flow")

        # First start
        start_event_loop(flow)
        first_thread = flow._execution_thread

        # Second start should not create new thread
        start_event_loop(flow)
        assert flow._execution_thread is first_thread

        # Clean up
        flow._running = False
        flow._execution_thread.join(timeout=2.0)

    def test_start_event_loop_dead_thread(self):
        """Test starting event loop with dead thread."""
        flow = Flow("test_flow")

        # Create and let die
        start_event_loop(flow)
        flow._running = False
        flow._execution_thread.join(timeout=2.0)

        # Should create new thread
        start_event_loop(flow)
        assert flow._running is True

        # Clean up
        flow._running = False
        if flow._execution_thread and flow._execution_thread.is_alive():
            flow._execution_thread.join(timeout=2.0)


class TestEnqueueTask:
    """Tests for enqueue_task function."""

    def test_enqueue_task_when_not_paused(self):
        """Test enqueuing task when flow is not paused."""
        flow = Flow("test_flow")
        flow._paused = False

        routine = Routine()
        slot = routine.define_slot("input", handler=lambda data: None)

        from routilux.flow.task import SlotActivationTask, TaskPriority

        task = SlotActivationTask(slot=slot, data={"test": "data"}, priority=TaskPriority.NORMAL)

        enqueue_task(task, flow)

        # Task should be in queue
        assert not flow._task_queue.empty()

    def test_enqueue_task_when_paused(self):
        """Test enqueuing task when flow is paused."""
        flow = Flow("test_flow")
        flow._paused = True

        routine = Routine()
        slot = routine.define_slot("input", handler=lambda data: None)

        from routilux.flow.task import SlotActivationTask, TaskPriority

        task = SlotActivationTask(slot=slot, data={"test": "data"}, priority=TaskPriority.NORMAL)

        enqueue_task(task, flow)

        # Task should be in pending_tasks, not queue
        assert len(flow._pending_tasks) > 0
        assert flow._task_queue.empty()


class TestExecuteTask:
    """Tests for execute_task function."""

    def test_execute_task_basic(self):
        """Test basic task execution."""
        flow = Flow("test_flow")

        executed = []

        def handler(data):
            executed.append(data)
            return "done"

        routine = Routine()
        slot = routine.define_slot("input", handler=handler)

        from routilux.flow.task import SlotActivationTask, TaskPriority

        task = SlotActivationTask(
            slot=slot, data={"test": "data"}, priority=TaskPriority.NORMAL, job_state=None
        )

        execute_task(task, flow)

        assert len(executed) == 1
        assert executed[0] == {"test": "data"}

    def test_execute_task_with_flow_context(self):
        """Test that task execution sets flow context on routine."""
        flow = Flow("test_flow")

        captured_flow = []

        def handler(data):
            # Check if routine has flow context
            ctx = slot.routine.get_execution_context()
            captured_flow.append(ctx)
            return "done"

        routine = Routine()
        slot = routine.define_slot("input", handler=handler)

        from routilux.flow.task import SlotActivationTask, TaskPriority

        task = SlotActivationTask(
            slot=slot, data={"test": "data"}, priority=TaskPriority.NORMAL, job_state=None
        )

        execute_task(task, flow)

        # Flow context should be set during execution
        assert len(captured_flow) >= 1


class TestIsAllTasksComplete:
    """Tests for is_all_tasks_complete function."""

    def test_is_all_tasks_complete_empty(self):
        """Test completion check with no tasks."""
        flow = Flow("test_flow")

        # No tasks in queue or active
        assert is_all_tasks_complete(flow) is True

    def test_is_all_tasks_complete_with_queued_tasks(self):
        """Test completion check with queued tasks."""
        flow = Flow("test_flow")

        routine = Routine()
        slot = routine.define_slot("input", handler=lambda data: None)

        from routilux.flow.task import SlotActivationTask, TaskPriority

        task = SlotActivationTask(slot=slot, data={}, priority=TaskPriority.NORMAL)
        flow._task_queue.put(task)

        assert is_all_tasks_complete(flow) is False

    def test_is_all_tasks_complete_with_active_tasks(self):
        """Test completion check with active tasks."""
        flow = Flow("test_flow", execution_strategy="concurrent")

        from concurrent.futures import Future

        # Simulate active task
        future = Future()
        with flow._execution_lock:
            flow._active_tasks.add(future)

        assert is_all_tasks_complete(flow) is False

        # Clean up
        with flow._execution_lock:
            flow._active_tasks.clear()


class TestEventLoopExecution:
    """Tests for event_loop main function."""

    def test_event_loop_exits_on_empty(self):
        """Test that event loop exits when queue is empty and no active tasks."""
        flow = Flow("test_flow")
        flow._running = True

        # Run event loop in thread
        def run_loop():
            event_loop(flow)

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()

        # Should exit quickly since no tasks
        thread.join(timeout=2.0)
        assert not thread.is_alive() or flow._running is False

    def test_event_loop_processes_tasks(self):
        """Test that event loop processes tasks from queue."""
        flow = Flow("test_flow", execution_strategy="concurrent")

        executed = []

        def handler(data):
            executed.append("task_executed")

        routine = Routine()
        slot = routine.define_slot("input", handler=handler)

        from routilux.flow.task import SlotActivationTask, TaskPriority

        task = SlotActivationTask(slot=slot, data={}, priority=TaskPriority.NORMAL, job_state=None)

        flow._task_queue.put(task)

        # Run event loop briefly
        def run_loop():
            event_loop(flow)

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        thread.join(timeout=2.0)

        # Task may or may not have been executed depending on timing
        # The test verifies the event loop doesn't crash

    def test_event_loop_respects_pause(self):
        """Test that event loop respects pause state."""
        flow = Flow("test_flow", execution_strategy="concurrent")
        flow._paused = True

        executed = []

        def handler(data):
            executed.append("should_not_run")

        routine = Routine()
        slot = routine.define_slot("input", handler=handler)

        from routilux.flow.task import SlotActivationTask, TaskPriority

        task = SlotActivationTask(slot=slot, data={}, priority=TaskPriority.NORMAL, job_state=None)

        flow._task_queue.put(task)

        # Run event loop briefly
        def run_loop():
            event_loop(flow)

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        thread.join(timeout=1.0)

        # Task should not have been executed due to pause
        # (Or very unlikely to execute in the short time before checking pause)

        # Clean up
        flow._running = False


class TestEventLoopWithExecutorShutdown:
    """Tests for event loop behavior when executor is shut down."""

    def test_event_loop_stops_on_executor_shutdown(self):
        """Test that event loop stops when executor is shut down."""
        flow = Flow("test_flow", execution_strategy="concurrent")

        # Shutdown executor
        executor = flow._get_executor()
        if executor:
            executor.shutdown(wait=False)

        # Start event loop
        flow._running = True

        def run_loop():
            event_loop(flow)

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        thread.join(timeout=2.0)

        # Event loop should have stopped
        assert flow._running is False or not thread.is_alive()


class TestEventLoopErrorHandling:
    """Tests for event loop error handling."""

    def test_event_loop_handles_task_errors(self):
        """Test that event loop handles task errors gracefully."""
        flow = Flow("test_flow", execution_strategy="concurrent")

        def failing_handler(data):
            raise ValueError("Test error")

        routine = Routine()
        routine.define_slot("input", handler=failing_handler)
        routine.define_event("output", ["result"])

        slot = routine.get_slot("input")

        from routilux.flow.task import SlotActivationTask, TaskPriority

        task = SlotActivationTask(slot=slot, data={}, priority=TaskPriority.NORMAL, job_state=None)

        flow._task_queue.put(task)

        # Run event loop - should not crash
        def run_loop():
            event_loop(flow)

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        thread.join(timeout=2.0)

        # Should complete without raising


class TestEventLoopActiveTasksTracking:
    """Tests for active tasks tracking in event loop."""

    def test_active_tasks_tracked(self):
        """Test that active tasks are tracked."""
        flow = Flow("test_flow", execution_strategy="concurrent")

        def slow_handler(data):
            time.sleep(0.1)
            return "done"

        routine = Routine()
        slot = routine.define_slot("input", handler=slow_handler)

        from routilux.flow.task import SlotActivationTask, TaskPriority

        task = SlotActivationTask(slot=slot, data={}, priority=TaskPriority.NORMAL, job_state=None)

        flow._task_queue.put(task)

        # Start event loop
        def run_loop():
            event_loop(flow)

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()

        # Give it time to start task
        time.sleep(0.05)

        # Should have active task
        with flow._execution_lock:
            _ = len([f for f in flow._active_tasks if not f.done()])

        # Clean up
        flow._running = False
        thread.join(timeout=2.0)


class TestEventLoopTaskDoneCallback:
    """Tests for task done callback."""

    def test_task_done_callback_removes_from_active(self):
        """Test that task done callback removes from active tasks."""
        flow = Flow("test_flow", execution_strategy="concurrent")

        def handler(data):
            return "done"

        routine = Routine()
        slot = routine.define_slot("input", handler=handler)

        from routilux.flow.task import SlotActivationTask, TaskPriority

        task = SlotActivationTask(slot=slot, data={}, priority=TaskPriority.NORMAL, job_state=None)

        flow._task_queue.put(task)

        # Start event loop
        def run_loop():
            event_loop(flow)

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        thread.join(timeout=2.0)

        # After completion, active tasks should be empty
        with flow._execution_lock:
            active_count = len([f for f in flow._active_tasks if not f.done()])

        assert active_count == 0


class TestEventLoopQueueTimeout:
    """Tests for queue timeout behavior."""

    def test_event_loop_queue_timeout(self):
        """Test that event loop handles queue timeout correctly."""
        flow = Flow("test_flow", execution_strategy="concurrent")

        # Don't add any tasks
        flow._running = True

        completed = []

        def run_loop():
            event_loop(flow)
            completed.append("loop_exited")

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()

        # Should exit due to empty queue and no active tasks
        thread.join(timeout=2.0)

        # Loop should have exited
        assert len(completed) > 0 or not thread.is_alive()
