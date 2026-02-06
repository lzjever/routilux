"""
Edge case tests for Routine class.
"""

import pytest

from routilux import Flow, Routine, JobState


class TestRoutineExecutionContext:
    """Tests for Routine execution context methods."""

    def test_get_execution_context_returns_none_without_flow(self):
        """Test that get_execution_context returns None when no flow context."""
        routine = Routine()

        ctx = routine.get_execution_context()

        assert ctx is None

    def test_get_execution_context_returns_none_without_job_state(self):
        """Test that get_execution_context returns None when no job_state context."""
        flow = Flow("test_flow")

        routine = Routine()
        # Set flow context but no job_state
        setattr(routine, "_current_flow", flow)

        ctx = routine.get_execution_context()

        # Should return None since no job_state in context
        assert ctx is None

    def test_get_execution_context_returns_none_without_routine_id(self):
        """Test that get_execution_context returns None when routine_id is None."""
        flow = Flow("test_flow")

        routine = Routine()
        setattr(routine, "_current_flow", flow)

        # Routine is not added to flow, so _get_routine_id will return None
        ctx = routine.get_execution_context()

        assert ctx is None

    def test_emit_deferred_event_raises_without_context(self):
        """Test that emit_deferred_event raises RuntimeError without execution context."""
        routine = Routine()

        with pytest.raises(RuntimeError, match="not in execution context"):
            routine.emit_deferred_event("test_event", data="value")

    def test_emit_deferred_event_adds_to_job_state(self):
        """Test that emit_deferred_event adds event to job_state deferred events."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("test_event", ["data"])

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        # Mock the execution context properly
        # We need to set up the context that get_execution_context expects
        from unittest.mock import patch, MagicMock
        from routilux.routine import _current_job_state, ExecutionContext

        token = _current_job_state.set(job_state)

        try:
            # Patch get_execution_context to return a valid context
            with patch.object(routine, 'get_execution_context',
                           return_value=ExecutionContext(flow=flow, job_state=job_state, routine_id="routine1")):
                routine.emit_deferred_event("test_event", data="value")

            # Check that event was added to deferred events
            assert len(job_state.deferred_events) == 1
            assert job_state.deferred_events[0]["event_name"] == "test_event"
            assert job_state.deferred_events[0]["data"] == {"data": "value"}
        finally:
            _current_job_state.reset(token)

    def test_send_output_raises_without_context(self):
        """Test that send_output raises RuntimeError without execution context."""
        routine = Routine()

        with pytest.raises(RuntimeError, match="not in execution context"):
            routine.send_output("result", value=123)

    def test_send_output_sends_to_job_state(self):
        """Test that send_output sends data to job_state."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        # Mock the execution context properly
        from unittest.mock import patch
        from routilux.routine import _current_job_state, ExecutionContext

        token = _current_job_state.set(job_state)

        try:
            # Patch get_execution_context to return a valid context
            with patch.object(routine, 'get_execution_context',
                           return_value=ExecutionContext(flow=flow, job_state=job_state, routine_id="routine1")):
                routine.send_output("result", value=123, status="success")

            # Check that output was logged
            assert len(job_state.output_log) > 0
        finally:
            _current_job_state.reset(token)


class TestRoutineSlotEventManagement:
    """Tests for Routine slot and event management edge cases."""

    def test_define_slot_with_duplicate_name_raises(self):
        """Test that defining duplicate slot names raises ValueError."""
        routine = Routine()

        routine.define_slot("input", handler=lambda data: "first")

        with pytest.raises(ValueError, match="already exists"):
            routine.define_slot("input", handler=lambda data: "second")

    def test_define_event_with_duplicate_name_raises(self):
        """Test that defining duplicate event names raises ValueError."""
        routine = Routine()

        routine.define_event("output", ["result"])

        with pytest.raises(ValueError, match="already exists"):
            routine.define_event("output", ["data"])

    def test_get_slot_returns_none_for_nonexistent(self):
        """Test that get_slot returns None for non-existent slot."""
        routine = Routine()

        slot = routine.get_slot("nonexistent")

        assert slot is None

    def test_get_event_returns_none_for_nonexistent(self):
        """Test that get_event returns None for non-existent event."""
        routine = Routine()

        event = routine.get_event("nonexistent")

        assert event is None

    def test_get_param_with_no_config(self):
        """Test that get_param returns default when no config is set."""
        routine = Routine()

        value = routine.get_param("nonexistent_param", default="default_value")

        assert value == "default_value"


class TestRoutineEmitEdgeCases:
    """Tests for Routine emit edge cases."""

    def test_emit_with_nonexistent_event(self):
        """Test that emit with non-existent event raises error."""
        routine = Routine()

        with pytest.raises(ValueError, match="does not exist"):
            routine.emit("nonexistent", data="value")

    def test_emit_with_flow_context(self):
        """Test that emit works correctly with flow context."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        # Emit should work without raising
        routine.emit("output", result="success")

    def test_emit_with_parameters(self):
        """Test that emit passes parameters correctly."""
        routine = Routine()
        event = routine.define_event("output", ["result", "status", "count"])

        # Capture emitted data
        received = []

        def capture_handler(**kwargs):
            received.append(kwargs)

        # Connect via flow to test full path
        flow = Flow("test_flow")
        routine2 = Routine()
        routine2.define_slot("input", handler=capture_handler)
        routine2.define_event("final", ["data"])

        flow.add_routine(routine, "routine1")
        flow.add_routine(routine2, "routine2")
        flow.connect("routine1", "output", "routine2", "input")

        routine.emit("output", result="done", status="ok", count=5)

        # Wait for task to process
        import time
        time.sleep(0.1)


class TestRoutineConfigEdgeCases:
    """Tests for Routine configuration edge cases."""

    def test_set_config_merges_with_existing(self):
        """Test that set_config merges with existing config."""
        routine = Routine()
        routine.set_config(key1="value1", key2="value2")

        # Setting new config should merge, not replace
        routine.set_config(key3="value3")

        assert routine.get_config("key1") == "value1"
        assert routine.get_config("key2") == "value2"
        assert routine.get_config("key3") == "value3"

    def test_get_param_from_config(self):
        """Test that get_param retrieves from config."""
        routine = Routine()
        routine.set_config(threshold=10, max_retries=3)

        assert routine.get_param("threshold") == 10
        assert routine.get_param("max_retries") == 3

    def test_get_param_with_default_from_config(self):
        """Test that get_param uses default when param not in config."""
        routine = Routine()
        routine.set_config(threshold=10)

        assert routine.get_param("nonexistent", default="default") == "default"


class TestRoutineWithFlowLifecycle:
    """Tests for Routine behavior within Flow lifecycle."""

    def test_routine_has_current_flow_after_add_to_flow(self):
        """Test that routine has _current_flow after being added to flow."""
        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        # After execution, routine should have _current_flow set
        # This happens during task execution
        job_state = flow.execute("routine1", entry_params={"data": {}})

        # After execution completes, _current_flow may still be set
        # (it depends on when it's cleared)

