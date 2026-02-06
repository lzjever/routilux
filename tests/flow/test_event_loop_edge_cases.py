"""
Edge case tests for flow event_loop module.
"""

import threading
import time
from unittest.mock import Mock

from routilux import Flow, JobState, Routine
from routilux.flow.event_loop import (
    enqueue_task,
    event_loop,
    execute_task,
)
from routilux.flow.task import SlotActivationTask, TaskPriority


class TestEventLoopExecutorShutdown:
    """Tests for event loop behavior when executor is shut down."""

    def test_event_loop_with_none_executor(self):
        """Test that event loop stops when executor returns None."""
        flow = Flow("test_flow", execution_strategy="concurrent")

        # Mock _get_executor to return None
        flow._get_executor = Mock(return_value=None)

        # Add a task to queue
        routine = Routine()
        slot = routine.define_slot("input", handler=lambda data: None)

        task = SlotActivationTask(slot=slot, data={}, priority=TaskPriority.NORMAL)
        flow._task_queue.put(task)

        flow._running = True

        # Run event loop - should stop when executor is None
        def run_loop():
            event_loop(flow)

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        thread.join(timeout=2.0)

        # Event loop should have stopped
        assert flow._running is False or not thread.is_alive()

    def test_event_loop_with_executor_shutdown_error(self):
        """Test that event loop handles executor shutdown RuntimeError."""
        flow = Flow("test_flow", execution_strategy="concurrent")

        # Mock executor that raises RuntimeError on submit
        mock_executor = Mock()
        mock_executor.submit.side_effect = RuntimeError(
            "cannot schedule new futures after shutdown"
        )

        flow._get_executor = Mock(return_value=mock_executor)

        # Add a task to queue
        routine = Routine()
        slot = routine.define_slot("input", handler=lambda data: None)

        task = SlotActivationTask(slot=slot, data={}, priority=TaskPriority.NORMAL)
        flow._task_queue.put(task)

        flow._running = True

        # Run event loop - should handle RuntimeError gracefully
        def run_loop():
            event_loop(flow)

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        thread.join(timeout=2.0)

        # Event loop should have stopped
        assert flow._running is False or not thread.is_alive()


class TestExecuteTaskErrorHandling:
    """Tests for execute_task error handling."""

    def test_execute_task_with_exception(self):
        """Test that execute_task handles exceptions via error handler."""
        flow = Flow("test_flow")

        def failing_handler(data):
            raise ValueError("Test error in handler")

        routine = Routine()
        routine.define_slot("input", handler=failing_handler)
        routine.define_event("output", ["result"])

        slot = routine.get_slot("input")

        job_state = JobState(flow_id="test_flow")

        task = SlotActivationTask(
            slot=slot, data={}, priority=TaskPriority.NORMAL, job_state=job_state
        )

        # Should not raise - error is handled by handle_task_error
        execute_task(task, flow)

    def test_execute_task_sets_flow_context(self):
        """Test that execute_task sets _current_flow on routine."""
        flow = Flow("test_flow")

        captured_flows = []

        def handler(data):
            # Capture the flow context
            if hasattr(slot.routine, "_current_flow"):
                captured_flows.append(slot.routine._current_flow)
            return "done"

        routine = Routine()
        slot = routine.define_slot("input", handler=handler)

        task = SlotActivationTask(slot=slot, data={}, priority=TaskPriority.NORMAL, job_state=None)

        execute_task(task, flow)

        # Flow context should have been set
        assert len(captured_flows) >= 1


class TestEventLoopPausedBehavior:
    """Tests for event loop behavior when paused."""

    def test_event_loop_sleeps_when_paused(self):
        """Test that event loop sleeps when flow is paused."""
        flow = Flow("test_flow", execution_strategy="concurrent")
        flow._paused = True

        # Add a task to queue
        routine = Routine()
        slot = routine.define_slot("input", handler=lambda data: None)

        task = SlotActivationTask(slot=slot, data={}, priority=TaskPriority.NORMAL)
        flow._task_queue.put(task)

        flow._running = True

        # Track whether event loop exits quickly (should not when paused)
        start_time = time.time()
        loop_exited = []

        def run_loop():
            event_loop(flow)
            loop_exited.append(time.time() - start_time)

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()

        # Wait a bit - loop should still be running due to pause
        time.sleep(0.2)

        # Unpause and let it finish
        flow._paused = False
        thread.join(timeout=2.0)

        # Loop should have taken some time due to pause
        # (minimum 0.2s from our sleep + processing time)


class TestEventLoopExceptionHandling:
    """Tests for event loop exception handling."""

    def test_event_loop_handles_general_exception(self):
        """Test that event loop handles general exceptions without crashing."""
        flow = Flow("test_flow", execution_strategy="concurrent")

        # Create a task that will cause an exception during execution
        def failing_handler(data):
            raise RuntimeError("Unexpected error in event loop")

        routine = Routine()
        slot = routine.define_slot("input", handler=failing_handler)

        task = SlotActivationTask(slot=slot, data={}, priority=TaskPriority.NORMAL, job_state=None)

        flow._task_queue.put(task)
        flow._running = True

        # Run event loop - should handle exception and continue
        def run_loop():
            event_loop(flow)

        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        thread.join(timeout=2.0)

        # Should complete without raising (exception is logged)


class TestEnqueueTaskPausedState:
    """Tests for enqueue_task with paused state."""

    def test_enqueue_task_goes_to_pending_when_paused(self):
        """Test that tasks go to pending_tasks when flow is paused."""
        flow = Flow("test_flow")
        flow._paused = True

        routine = Routine()
        slot = routine.define_slot("input", handler=lambda data: None)

        task = SlotActivationTask(slot=slot, data={}, priority=TaskPriority.NORMAL)

        enqueue_task(task, flow)

        # Task should be in pending_tasks, not queue
        assert len(flow._pending_tasks) > 0
        assert flow._task_queue.empty()

    def test_enqueue_task_goes_to_queue_when_not_paused(self):
        """Test that tasks go to queue when flow is not paused."""
        flow = Flow("test_flow")
        flow._paused = False

        routine = Routine()
        slot = routine.define_slot("input", handler=lambda data: None)

        task = SlotActivationTask(slot=slot, data={}, priority=TaskPriority.NORMAL)

        enqueue_task(task, flow)

        # Task should be in queue, not pending_tasks
        assert not flow._task_queue.empty()
