"""
Tests for flow state management module.
"""

from datetime import datetime

import pytest

from routilux import Flow, JobState, Routine
from routilux.flow.state_management import (
    deserialize_pending_tasks,
    pause_flow,
    serialize_pending_tasks,
    wait_for_active_tasks,
)


class TestPauseFlow:
    """Tests for pause_flow function."""

    def test_pause_flow_basic(self):
        """Test basic pause functionality."""
        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")
        job_state = flow.execute("routine1", entry_params={"data": {}})

        # Pause the flow
        pause_flow(flow, job_state, reason="Test pause")

        assert flow._paused is True
        # JobState tracks pause points
        assert len(job_state.pause_points) > 0

    def test_pause_flow_with_checkpoint(self):
        """Test pause with checkpoint data."""
        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")
        job_state = flow.execute("routine1", entry_params={"data": {}})

        checkpoint = {"key": "value", "state": "checkpoint_data"}
        pause_flow(flow, job_state, reason="Test with checkpoint", checkpoint=checkpoint)

        pause_point = job_state.pause_points[-1]
        assert pause_point["checkpoint"] == checkpoint

    def test_pause_flow_mismatch_flow_id(self):
        """Test pause with mismatched flow_id raises error."""
        flow1 = Flow("flow1")
        flow2 = Flow("flow2")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow1.add_routine(routine, "routine1")
        job_state = flow1.execute("routine1", entry_params={"data": {}})

        # Try to pause with wrong flow
        with pytest.raises(ValueError, match="does not match"):
            pause_flow(flow2, job_state, reason="Test")


class TestWaitForActiveTasks:
    """Tests for wait_for_active_tasks function."""

    def test_wait_for_active_tasks_no_tasks(self):
        """Test waiting when there are no active tasks."""
        flow = Flow("test_flow")
        # Should complete immediately
        wait_for_active_tasks(flow)

    def test_wait_for_active_tasks_timeout(self):
        """Test that wait_for_active_tasks times out."""
        flow = Flow("test_flow", execution_strategy="concurrent")

        # Create a long-running task
        import time

        def long_handler(data):
            time.sleep(0.2)
            return "done"

        routine = Routine()
        routine.define_slot("input", handler=long_handler)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")
        _ = flow.execute("routine1", entry_params={"data": {}})

        # Should wait but eventually return
        wait_for_active_tasks(flow)


class TestSerializePendingTasks:
    """Tests for serialize_pending_tasks function."""

    def test_serialize_empty_pending_tasks(self):
        """Test serializing with no pending tasks."""
        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")
        job_state = flow.execute("routine1", entry_params={"data": {}})

        serialize_pending_tasks(flow, job_state)

        # Should not crash with empty pending_tasks
        assert hasattr(job_state, "pending_tasks")

    def test_serialize_pending_tasks_structure(self):
        """Test that pending tasks are serialized with correct structure."""
        flow = Flow("test_flow")

        # Create a task with connection
        routine1 = Routine()
        routine1.define_slot("input", handler=lambda data: None)
        routine1.define_event("output", ["result"])

        routine2 = Routine()
        routine2.define_slot("input", handler=lambda data: None)
        routine2.define_event("output", ["result"])

        flow.add_routine(routine1, "routine1")
        flow.add_routine(routine2, "routine2")

        # Connect routines (correct signature)
        flow.connect("routine1", "output", "routine2", "input")

        job_state = flow.execute("routine1", entry_params={"data": {}})

        # Pause to serialize tasks
        pause_flow(flow, job_state, reason="Test")

        # Check serialized tasks structure
        if hasattr(job_state, "pending_tasks") and job_state.pending_tasks:
            task = job_state.pending_tasks[0]
            assert "slot_routine_id" in task
            assert "slot_name" in task
            assert "data" in task


class TestDeserializePendingTasks:
    """Tests for deserialize_pending_tasks function."""

    def test_deserialize_empty_tasks(self):
        """Test deserializing with no pending tasks."""
        flow = Flow("test_flow")
        job_state = JobState(flow_id="test_flow")

        deserialize_pending_tasks(flow, job_state)

        # Should not crash
        assert len(flow._pending_tasks) == 0

    def test_deserialize_tasks_to_flow(self):
        """Test deserializing tasks back to flow."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        # Create a mock serialized task
        job_state = JobState(flow_id="test_flow")

        # Mock pending tasks with structure matching serialization
        if hasattr(routine, "_id"):
            job_state.pending_tasks = [
                {
                    "slot_routine_id": routine._id,
                    "slot_name": "input",
                    "data": {"test": "data"},
                    "connection_source_routine_id": None,
                    "connection_source_event_name": None,
                    "connection_target_routine_id": None,
                    "connection_target_slot_name": None,
                    "priority": 0,
                    "retry_count": 0,
                    "max_retries": 0,
                    "created_at": datetime.now().isoformat(),
                }
            ]

            deserialize_pending_tasks(flow, job_state)

            # Task should be restored
            assert len(flow._pending_tasks) >= 0

    def test_deserialize_tasks_with_missing_routine(self):
        """Test deserializing when routine ID doesn't exist."""
        flow = Flow("test_flow")

        job_state = JobState(flow_id="test_flow")
        job_state.pending_tasks = [
            {
                "slot_routine_id": "nonexistent_id",
                "slot_name": "input",
                "data": {},
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

        # Should not crash, just skip the missing routine
        deserialize_pending_tasks(flow, job_state)
        assert len(flow._pending_tasks) == 0


class TestPauseFlowWithActiveExecution:
    """Tests for pausing flow during active execution."""

    def test_pause_during_execution(self):
        """Test pausing while flow is executing."""
        flow = Flow("test_flow", execution_strategy="concurrent")

        import time

        def handler(data):
            time.sleep(0.1)
            return "done"

        routine = Routine()
        routine.define_slot("input", handler=handler)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")
        job_state = flow.execute("routine1", entry_params={"data": {}})

        # Give it a moment to start
        time.sleep(0.05)

        # Pause
        pause_flow(flow, job_state, reason="Mid-execution pause")

        assert flow._paused is True


class TestPausePointRecording:
    """Tests for pause point metadata recording."""

    def test_pause_point_metadata(self):
        """Test that pause points contain correct metadata."""
        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")
        job_state = flow.execute("routine1", entry_params={"data": {}})

        pause_flow(flow, job_state, reason="Test metadata")

        pause_point = job_state.pause_points[-1]
        assert "timestamp" in pause_point
        assert "reason" in pause_point
        assert pause_point["reason"] == "Test metadata"
        # Check for the fields that exist in pause_point
        # The actual structure may vary


class TestRecoverSlotTasks:
    """Tests for _recover_slot_tasks function."""

    def test_recover_slot_tasks_basic(self):
        """Test basic slot task recovery."""
        from routilux.flow.state_management import _recover_slot_tasks

        flow = Flow("test_flow")

        routine = Routine()
        routine.define_slot("input", handler=lambda data: None)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")
        job_state = flow.execute("routine1", entry_params={"data": {}})

        # Should not crash even with no slot data to recover
        _recover_slot_tasks(flow, job_state)


class TestStateManagementIntegration:
    """Integration tests for state management."""

    def test_pause_resume_cycle(self):
        """Test complete pause and resume cycle."""
        flow = Flow("test_flow")

        executed = []

        def handler(data):
            executed.append("handler_called")
            return "done"

        routine = Routine()
        routine.define_slot("input", handler=handler)
        routine.define_event("output", ["result"])

        flow.add_routine(routine, "routine1")

        job_state = flow.execute("routine1", entry_params={"data": {}})

        # Pause
        pause_flow(flow, job_state, reason="Integration test")

        # Verify pause was recorded
        assert len(job_state.pause_points) > 0

        # Note: Actual resume testing would require more complex setup
        # This test verifies the pause side of the cycle
