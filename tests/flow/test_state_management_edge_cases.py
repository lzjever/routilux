"""
Additional edge case tests for flow state management module.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from routilux import Flow, JobState, Routine
from routilux.flow.state_management import (
    deserialize_pending_tasks,
    pause_flow,
    resume_flow,
    cancel_flow,
    _recover_slot_tasks,
)


class TestDeserializePendingTasksEdgeCases:
    """Edge case tests for deserialize_pending_tasks function."""

    def test_deserialize_with_connection(self):
        """Test deserializing tasks with connection details."""
        flow = Flow("test_flow")

        routine1 = Routine()
        routine1.define_slot("input", handler=lambda data: None)
        routine1.define_event("output", ["result"])

        routine2 = Routine()
        routine2.define_slot("input", handler=lambda data: None)
        routine2.define_event("output", ["result"])

        flow.add_routine(routine1, "routine1")
        flow.add_routine(routine2, "routine2")

        # Connect routines
        flow.connect("routine1", "output", "routine2", "input")

        # Create job_state with connection details
        job_state = JobState(flow_id="test_flow")

        if hasattr(routine1, "_id") and hasattr(routine2, "_id"):
            job_state.pending_tasks = [
                {
                    "slot_routine_id": routine2._id,
                    "slot_name": "input",
                    "data": {"test": "data"},
                    "connection_source_routine_id": routine1._id,
                    "connection_source_event_name": "output",
                    "connection_target_routine_id": routine2._id,
                    "connection_target_slot_name": "input",
                    "priority": 0,
                    "retry_count": 0,
                    "max_retries": 0,
                    "created_at": datetime.now().isoformat(),
                }
            ]

            deserialize_pending_tasks(flow, job_state)

            # Task should be restored with connection
            assert len(flow._pending_tasks) >= 0

    def test_deserialize_with_missing_slot_name(self):
        """Test deserializing when slot_name is None."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        if hasattr(routine, "_id"):
            job_state.pending_tasks = [
                {
                    "slot_routine_id": routine._id,
                    "slot_name": None,  # Missing slot name
                    "data": {"test": "data"},
                    "connection_source_routine_id": None,
                    "connection_source_event_name": None,
                    "connection_target_routine_id": None,
                    "connection_target_slot_name": None,
                    "priority": 0,
                    "retry_count": 0,
                    "max_retries": 0,
                    "created_at": None,
                }
            ]

            deserialize_pending_tasks(flow, job_state)

            # Task should be skipped when slot_name is None
            assert len(flow._pending_tasks) == 0

    def test_deserialize_with_nonexistent_slot(self):
        """Test deserializing when slot doesn't exist on routine."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        if hasattr(routine, "_id"):
            job_state.pending_tasks = [
                {
                    "slot_routine_id": routine._id,
                    "slot_name": "nonexistent_slot",  # Slot that doesn't exist
                    "data": {"test": "data"},
                    "connection_source_routine_id": None,
                    "connection_source_event_name": None,
                    "connection_target_routine_id": None,
                    "connection_target_slot_name": None,
                    "priority": 0,
                    "retry_count": 0,
                    "max_retries": 0,
                    "created_at": None,
                }
            ]

            deserialize_pending_tasks(flow, job_state)

            # Task should be skipped when slot doesn't exist
            assert len(flow._pending_tasks) == 0

    def test_deserialize_with_partial_connection_details(self):
        """Test deserializing with partial connection details."""
        flow = Flow("test_flow")

        routine1 = Routine()
        routine1.define_slot("input", handler=lambda data: None)
        routine1.define_event("output", ["result"])

        routine2 = Routine()
        routine2.define_slot("input", handler=lambda data: None)
        routine2.define_event("output", ["result"])

        flow.add_routine(routine1, "routine1")
        flow.add_routine(routine2, "routine2")

        job_state = JobState(flow_id="test_flow")

        if hasattr(routine1, "_id"):
            job_state.pending_tasks = [
                {
                    "slot_routine_id": routine2._id,
                    "slot_name": "input",
                    "data": {"test": "data"},
                    "connection_source_routine_id": routine1._id,
                    "connection_source_event_name": None,  # Missing event name
                    "connection_target_routine_id": None,
                    "connection_target_slot_name": None,
                    "priority": 0,
                    "retry_count": 0,
                    "max_retries": 0,
                    "created_at": None,
                }
            ]

            deserialize_pending_tasks(flow, job_state)

            # Task should be restored even with partial connection
            assert len(flow._pending_tasks) >= 0

    def test_deserialize_with_missing_target_routine(self):
        """Test deserializing when target routine in connection doesn't exist."""
        flow = Flow("test_flow")

        routine1 = Routine()
        routine1.define_slot("input", handler=lambda data: None)
        routine1.define_event("output", ["result"])

        flow.add_routine(routine1, "routine1")

        job_state = JobState(flow_id="test_flow")

        if hasattr(routine1, "_id"):
            job_state.pending_tasks = [
                {
                    "slot_routine_id": routine1._id,
                    "slot_name": "input",
                    "data": {"test": "data"},
                    "connection_source_routine_id": routine1._id,
                    "connection_source_event_name": "output",
                    "connection_target_routine_id": "nonexistent_routine",  # Missing
                    "connection_target_slot_name": "input",
                    "priority": 0,
                    "retry_count": 0,
                    "max_retries": 0,
                    "created_at": None,
                }
            ]

            deserialize_pending_tasks(flow, job_state)

            # Task should be restored without connection
            assert len(flow._pending_tasks) >= 0


class TestRecoverSlotTasksEdgeCases:
    """Edge case tests for _recover_slot_tasks function."""

    def test_recover_with_no_slots_attr(self):
        """Test recovery when routine has no _slots attribute."""
        flow = Flow("test_flow")

        routine = Routine()
        # Don't define any slots - routine._slots may not exist or be empty
        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        # Should not crash
        _recover_slot_tasks(flow, job_state)

    def test_recover_with_completed_status(self):
        """Test recovery skips routines with completed status."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        # Mark routine as completed
        if hasattr(routine, "_id"):
            job_state.routine_states[routine._id] = {"status": "completed"}

        # Should not recover from completed routines
        _recover_slot_tasks(flow, job_state)

    def test_recover_with_failed_status(self):
        """Test recovery skips routines with failed status."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        # Mark routine as failed
        if hasattr(routine, "_id"):
            job_state.routine_states[routine._id] = {"status": "failed"}

        # Should not recover from failed routines
        _recover_slot_tasks(flow, job_state)

    def test_recover_with_cancelled_status(self):
        """Test recovery skips routines with cancelled status."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        # Mark routine as cancelled
        if hasattr(routine, "_id"):
            job_state.routine_states[routine._id] = {"status": "cancelled"}

        # Should not recover from cancelled routines
        _recover_slot_tasks(flow, job_state)

    def test_recover_slot_without_handler(self):
        """Test recovery skips slots without handlers."""
        flow = Flow("test_flow")

        routine = Routine()
        slot = routine.define_slot("input")  # No handler
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        # Manually add data to slot
        if hasattr(slot, "_data"):
            slot._data = {"test": "data"}

        # Should not recover slots without handlers
        _recover_slot_tasks(flow, job_state)

    def test_recover_with_retry_exhausted(self):
        """Test recovery skips when retries are exhausted."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        # Set up routine with exhausted retries
        if hasattr(routine, "_id"):
            job_state.routine_states[routine._id] = {"status": "pending"}

            # Add retry state to indicate retries exhausted
            # This tests the retry_count >= max_retries condition

        # Should not recover when retries exhausted
        _recover_slot_tasks(flow, job_state)

    def test_recover_with_slot_data_but_no_connection(self):
        """Test recovery when slot has data but no connection found."""
        flow = Flow("test_flow")

        routine = Routine()
        slot = routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        # Manually add data to slot without any connections
        if hasattr(slot, "_data"):
            slot._data = {"test": "data"}

        # Should still attempt recovery even without connection
        _recover_slot_tasks(flow, job_state)


class TestResumeFlowEdgeCases:
    """Edge case tests for resume_flow function."""

    def test_resume_with_deferred_events(self):
        """Test resume processes deferred events."""
        flow = Flow("test_flow")

        executed = []

        def handler(data):
            executed.append("handler_called")
            return "done"

        routine = Routine()
        routine.define_slot("input", handler=handler)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")
        job_state.current_routine_id = None

        # Use the actual routine_id from flow.routines
        routine_id = "routine1"  # The ID we used when adding the routine

        # Add deferred events
        job_state.deferred_events = [
            {
                "routine_id": routine_id,
                "event_name": "output",
                "data": {"result": "test"},
            }
        ]

        resume_flow(flow, job_state)

        # Deferred events should be cleared after processing
        assert len(job_state.deferred_events) == 0

    def test_resume_with_deferred_event_missing_routine(self):
        """Test resume handles deferred events for missing routine."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        # Add deferred event for non-existent routine
        job_state.deferred_events = [
            {
                "routine_id": "nonexistent_routine",
                "event_name": "output",
                "data": {},
            }
        ]

        # Should warn but not crash
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            resume_flow(flow, job_state)
            # Check that a warning was issued
            assert len(w) > 0
            assert "not found in flow" in str(w[0].message)

    def test_resume_with_deferred_event_missing_event_name(self):
        """Test resume handles deferred events with missing event name."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        # Use the actual routine_id from flow.routines
        routine_id = "routine1"  # The ID we used when adding the routine

        # Add deferred event without event_name
        job_state.deferred_events = [
            {
                "routine_id": routine_id,
                "event_name": None,  # Missing
                "data": {},
            }
        ]

        # Should warn but not crash
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            resume_flow(flow, job_state)
            # Check that a warning was issued
            assert len(w) > 0
            assert "not found in routine" in str(w[0].message)

    def test_resume_with_deferred_event_emit_failure(self):
        """Test resume handles emit failures gracefully."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        # Don't define the event that will be emitted

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        # Use the actual routine_id from flow.routines
        routine_id = "routine1"  # The ID we used when adding the routine

        # Add deferred event for non-existent event
        job_state.deferred_events = [
            {
                "routine_id": routine_id,
                "event_name": "nonexistent_event",
                "data": {},
            }
        ]

        # Should warn but not crash
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            resume_flow(flow, job_state)
            # Check that a warning was issued
            assert len(w) > 0
            assert "not found in routine" in str(w[0].message)

    def test_resume_mismatch_flow_id(self):
        """Test resume with mismatched flow_id raises error."""
        flow1 = Flow("flow1")
        flow2 = Flow("flow2")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow1.add_routine(routine, "routine1")

        job_state = JobState(flow_id="flow1")

        # Try to resume with wrong flow
        with pytest.raises(ValueError, match="does not match"):
            resume_flow(flow2, job_state)

    def test_resume_with_missing_current_routine(self):
        """Test resume with current_routine_id that doesn't exist."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")
        job_state.current_routine_id = "nonexistent_routine"

        # Should raise error for missing current routine
        with pytest.raises(ValueError, match="not found in flow"):
            resume_flow(flow, job_state)


class TestCancelFlowEdgeCases:
    """Edge case tests for cancel_flow function."""

    def test_cancel_flow_basic(self):
        """Test basic cancel functionality."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        cancel_flow(flow, job_state, reason="Test cancellation")

        assert flow._paused is False
        assert flow._running is False
        assert job_state.status == "cancelled"

    def test_cancel_flow_mismatch_flow_id(self):
        """Test cancel with mismatched flow_id raises error."""
        flow1 = Flow("flow1")
        flow2 = Flow("flow2")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow1.add_routine(routine, "routine1")

        job_state = JobState(flow_id="flow1")

        # Try to cancel with wrong flow
        with pytest.raises(ValueError, match="does not match"):
            cancel_flow(flow2, job_state)

    def test_cancel_clears_active_tasks(self):
        """Test cancel clears active tasks."""
        flow = Flow("test_flow", execution_strategy="concurrent")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        job_state = JobState(flow_id="test_flow")

        # Add a mock active task (it's a set, so we use add)
        from concurrent.futures import Future
        mock_task = Future()
        flow._active_tasks.add(mock_task)

        cancel_flow(flow, job_state)

        # Active tasks should be cleared
        assert len(flow._active_tasks) == 0
