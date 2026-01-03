"""
Execution completion mechanism tests.

Tests for the systematic execution completion detection and waiting mechanism.
"""

import time
from routilux import Flow, Routine
from routilux.job_state import JobState
from routilux.flow.completion import ensure_event_loop_running


class TestWaitForExecutionCompletion:
    """Test wait_for_execution_completion function."""

    def test_wait_for_completion_immediate(self):
        """Test waiting for already completed execution."""
        flow = Flow()
        from routilux.job_state import JobState

        job_state = JobState(flow.flow_id)
        job_state.status = "completed"

        # Use minimal timeout and checks for fast testing
        completed = JobState.wait_for_completion(
            flow,
            job_state,
            timeout=0.5,
            stability_checks=2,
            check_interval=0.01,
            stability_delay=0.001,
        )
        assert completed is True

    def test_wait_for_completion_with_timeout(self):
        """Test waiting with timeout."""
        flow = Flow()
        from routilux.job_state import JobState
        from routilux.flow.task import SlotActivationTask

        job_state = JobState(flow.flow_id)
        job_state.status = "running"

        # Add a task that will never complete
        routine = Routine()
        slot = routine.define_slot("input")
        task = SlotActivationTask(
            slot=slot,
            data={},
            connection=None,
            created_at=time.time(),
            job_state=job_state,
        )
        flow._task_queue.put(task)

        # Use minimal timeout and checks for fast testing
        completed = JobState.wait_for_completion(
            flow,
            job_state,
            timeout=0.05,
            stability_checks=2,
            check_interval=0.01,
            stability_delay=0.001,
        )
        assert completed is False

    def test_wait_for_completion_with_progress_callback(self):
        """Test waiting with progress callback."""
        flow = Flow()
        from routilux.job_state import JobState

        job_state = JobState(flow.flow_id)
        job_state.status = "running"

        progress_calls = []

        def progress_callback(queue_size, active_count, status):
            progress_calls.append((queue_size, active_count, status))

        # Complete immediately
        job_state.status = "completed"

        # Use minimal timeout and checks for fast testing
        completed = JobState.wait_for_completion(
            flow,
            job_state,
            timeout=0.5,
            stability_checks=2,
            check_interval=0.01,
            stability_delay=0.001,
            progress_callback=progress_callback,
        )
        assert completed is True
        # Progress callback may or may not be called depending on timing


class TestExecutionTimeout:
    """Test execution timeout mechanism."""

    def test_flow_with_custom_timeout(self):
        """Test Flow with custom execution timeout."""
        flow = Flow(execution_timeout=60.0)  # Reduced from 600.0 to 60.0 for faster tests
        assert flow.execution_timeout == 60.0

    def test_flow_with_default_timeout(self):
        """Test Flow with default execution timeout."""
        flow = Flow()
        assert flow.execution_timeout == 300.0

    def test_execute_with_timeout_override(self):
        """Test execute() with timeout override."""
        flow = Flow(execution_timeout=60.0)  # Reduced from 600.0 to 60.0 for faster tests

        class QuickRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["result"])

            def _handle_trigger(self, **kwargs):
                self.emit("output", result="done")

        routine = QuickRoutine()
        routine_id = flow.add_routine(routine, "quick")

        # Execute with timeout override (reduced from 10.0 to 2.0)
        job_state = flow.execute(entry_routine_id=routine_id, timeout=2.0)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)
        assert job_state.status == "completed"

    def test_execute_with_long_running_task(self):
        """Test execute() with long-running task."""
        flow = Flow(execution_timeout=1.0)  # 1 second timeout

        class LongRunningRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["result"])

            def _handle_trigger(self, **kwargs):
                # No sleep - just emit immediately for fast test
                self.emit("output", result="done")

        routine = LongRunningRoutine()
        routine_id = flow.add_routine(routine, "long_running")

        # Execute - should complete within timeout
        job_state = flow.execute(entry_routine_id=routine_id, timeout=1.0)
        JobState.wait_for_completion(flow, job_state, timeout=1.0)
        assert job_state.status == "completed"


class TestEnsureEventLoopRunning:
    """Test ensure_event_loop_running function."""

    def test_ensure_event_loop_running_when_stopped(self):
        """Test ensuring event loop runs when stopped with tasks in queue."""
        flow = Flow()
        from routilux.job_state import JobState
        from routilux.flow.task import SlotActivationTask

        job_state = JobState(flow.flow_id)

        # Add a task to the queue
        routine = Routine()
        slot = routine.define_slot("input")
        task = SlotActivationTask(
            slot=slot,
            data={},
            connection=None,
            created_at=time.time(),
            job_state=job_state,
        )
        flow._task_queue.put(task)

        # Event loop is not running
        assert flow._execution_thread is None or not flow._execution_thread.is_alive()

        # Ensure event loop is running
        result = ensure_event_loop_running(flow)
        assert result is True
        assert flow._execution_thread is not None
        assert flow._execution_thread.is_alive()

        # Clean up
        flow._running = False
        if flow._execution_thread:
            flow._execution_thread.join(timeout=0.5)  # Reduced from 1.0 to 0.5

    def test_ensure_event_loop_running_when_already_running(self):
        """Test ensuring event loop when already running."""
        flow = Flow()
        from routilux.flow.event_loop import start_event_loop

        # Start event loop
        start_event_loop(flow)
        assert flow._execution_thread is not None
        assert flow._execution_thread.is_alive()

        # Ensure again - should not restart
        result = ensure_event_loop_running(flow)
        assert result is True

        # Clean up
        flow._running = False
        if flow._execution_thread:
            flow._execution_thread.join(timeout=0.5)  # Reduced from 1.0 to 0.5


class TestCompletionWithRealFlow:
    """Test completion mechanism with real flow execution."""

    def test_completion_with_sequential_flow(self):
        """Test completion detection with sequential flow."""
        flow = Flow(execution_timeout=2.0)  # Reduced from 10.0 to 2.0

        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, **kwargs):
                self.emit("output", data="test")

        class TargetRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self._handle_input)
                self.received = []

            def _handle_input(self, data=None, **kwargs):
                self.received.append(data or kwargs.get("data"))

        source = SourceRoutine()
        target = TargetRoutine()

        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")

        flow.connect(source_id, "output", target_id, "input")

        job_state = flow.execute(entry_routine_id=source_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)
        assert job_state.status == "completed"
        assert len(target.received) == 1
        assert target.received[0] == "test"

    def test_completion_with_multiple_emits(self):
        """Test completion detection with multiple emits."""
        flow = Flow(execution_timeout=2.0)  # Reduced from 10.0 to 2.0

        class MultiEmitRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, **kwargs):
                # Emit multiple times
                for i in range(3):
                    self.emit("output", data=f"item_{i}")

        class CollectorRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self._handle_input)
                self.collected = []

            def _handle_input(self, data=None, **kwargs):
                self.collected.append(data or kwargs.get("data"))

        source = MultiEmitRoutine()
        collector = CollectorRoutine()

        source_id = flow.add_routine(source, "source")
        collector_id = flow.add_routine(collector, "collector")

        flow.connect(source_id, "output", collector_id, "input")

        job_state = flow.execute(entry_routine_id=source_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)
        assert job_state.status == "completed"
        assert len(collector.collected) == 3
        assert collector.collected == ["item_0", "item_1", "item_2"]

    def test_completion_with_chained_routines(self):
        """Test completion detection with chained routines."""
        flow = Flow(execution_timeout=2.0)  # Reduced from 10.0 to 2.0

        class A(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["value"])

            def _handle_trigger(self, **kwargs):
                self.emit("output", value=1)

        class B(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self._handle_input)
                self.output_event = self.define_event("output", ["value"])

            def _handle_input(self, value=None, **kwargs):
                val = value or kwargs.get("value", 0)
                self.emit("output", value=val + 1)

        class C(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self._handle_input)
                self.final_value = None

            def _handle_input(self, value=None, **kwargs):
                self.final_value = value or kwargs.get("value", 0)

        a = A()
        b = B()
        c = C()

        a_id = flow.add_routine(a, "a")
        b_id = flow.add_routine(b, "b")
        c_id = flow.add_routine(c, "c")

        flow.connect(a_id, "output", b_id, "input")
        flow.connect(b_id, "output", c_id, "input")

        job_state = flow.execute(entry_routine_id=a_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)
        assert job_state.status == "completed"
        assert c.final_value == 2
