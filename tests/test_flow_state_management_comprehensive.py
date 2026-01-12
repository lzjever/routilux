"""
Comprehensive tests for Flow state management.

Tests pause, resume, cancel, and task serialization/deserialization.
"""

import time

import pytest

from routilux import Flow, JobState, Routine
from routilux.flow.state_management import (
    cancel_flow,
    deserialize_pending_tasks,
    pause_flow,
    resume_flow,
    serialize_pending_tasks,
    wait_for_active_tasks,
)


class TestPauseFlow:
    """Test pause functionality."""

    def test_pause_without_job_state(self):
        """Test pause without job_state raises error."""
        from routilux import JobState

        flow = Flow()
        # Create a JobState with wrong flow_id to test validation
        wrong_job_state = JobState(flow_id="wrong_flow_id")

        with pytest.raises(ValueError, match="does not match"):
            pause_flow(flow, wrong_job_state, reason="test")

    def test_pause_with_checkpoint(self):
        """Test pause with checkpoint data."""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"
        # job_state is now passed directly, no need to set thread-local storage

        checkpoint = {"step": 1, "data": "test"}
        pause_flow(flow, job_state, reason="test pause", checkpoint=checkpoint)

        assert flow._paused is True
        assert job_state.status == "paused"
        assert len(job_state.pause_points) > 0
        assert job_state.pause_points[-1]["checkpoint"] == checkpoint

    def test_pause_serializes_pending_tasks(self):
        """Test pause serializes pending tasks."""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"
        # job_state is now passed directly, no need to set thread-local storage

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, **kwargs):
                pass

        routine = TestRoutine()
        flow.add_routine(routine, "test")
        slot = routine.get_slot("input")

        from routilux.flow.task import SlotActivationTask

        task = SlotActivationTask(slot=slot, data={"test": "data"})
        flow._pending_tasks.append(task)

        pause_flow(flow, job_state, reason="test")

        assert hasattr(job_state, "pending_tasks")
        assert len(job_state.pending_tasks) == 1
        assert job_state.pending_tasks[0]["slot_name"] == "input"


class TestResumeFlow:
    """Test resume functionality."""

    def test_resume_without_job_state(self):
        """Test resume without job_state raises error."""
        flow = Flow()

        from routilux import JobState

        # resume_flow now requires job_state parameter
        wrong_job_state = JobState(flow_id="wrong")
        with pytest.raises(ValueError, match="does not match"):
            resume_flow(flow, wrong_job_state)

    def test_resume_with_mismatched_flow_id(self):
        """Test resume with mismatched flow_id raises error."""
        flow = Flow(flow_id="flow1")
        job_state = JobState("flow2")

        with pytest.raises(ValueError, match="flow_id.*does not match"):
            resume_flow(flow, job_state)

    def test_resume_with_missing_routine(self):
        """Test resume with missing routine raises error."""
        flow = Flow(flow_id="flow1")
        job_state = JobState("flow1")
        job_state.current_routine_id = "missing_routine"

        with pytest.raises(ValueError, match="not found in flow"):
            resume_flow(flow, job_state)

    def test_resume_restores_routine_state(self):
        """Test resume restores routine state in JobState."""
        flow = Flow(flow_id="flow1")

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self.process)

            def process(self, **kwargs):
                pass

        routine = TestRoutine()
        routine_id = flow.add_routine(routine, "test")

        job_state = JobState("flow1")
        job_state.status = "paused"
        job_state.routine_states[routine_id] = {
            "status": "running",
            "processed": 5,
            "count": 10,
        }
        # job_state is now passed directly, no need to set thread-local storage

        resume_flow(flow, job_state)

        # Routine state is stored in JobState, not routine._stats
        restored_state = job_state.get_routine_state(routine_id)
        assert restored_state["processed"] == 5
        assert restored_state["count"] == 10

    def test_resume_deserializes_pending_tasks(self):
        """Test resume deserializes pending tasks."""
        flow = Flow(flow_id="flow1")

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, **kwargs):
                pass

        routine = TestRoutine()
        routine_id = flow.add_routine(routine, "test")

        job_state = JobState("flow1")
        job_state.status = "paused"
        # Get the actual routine_id (might be hex)
        actual_routine_id = routine_id

        job_state.pending_tasks = [
            {
                "slot_routine_id": actual_routine_id,
                "slot_name": "input",
                "data": {"test": "data"},
                "connection_source_routine_id": None,
                "connection_source_event_name": None,
                "connection_target_routine_id": None,
                "connection_target_slot_name": None,
                "param_mapping": {},
                "priority": 2,
                "retry_count": 0,
                "max_retries": 0,
                "created_at": None,
            }
        ]
        # job_state is now passed directly, no need to set thread-local storage

        resume_flow(flow, job_state)

        # After resume, pending tasks should be moved to queue or cleared
        # The tasks are put into queue during resume, so _pending_tasks should be empty
        # But we can check that the task was processed
        assert len(flow._pending_tasks) == 0  # Tasks moved to queue


class TestCancelFlow:
    """Test cancel functionality."""

    def test_cancel_without_job_state(self):
        """Test cancel without job_state raises error."""
        from routilux import JobState

        flow = Flow()
        # cancel_flow now requires job_state parameter
        wrong_job_state = JobState(flow_id="wrong")
        with pytest.raises(ValueError, match="does not match"):
            cancel_flow(flow, wrong_job_state, reason="test")

    def test_cancel_stops_execution(self):
        """Test cancel stops execution."""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"
        # job_state is now passed directly, no need to set thread-local storage
        flow._running = True

        cancel_flow(flow, job_state, reason="test cancel")

        assert job_state.status == "cancelled"
        assert not flow._paused
        assert not flow._running


class TestTaskSerialization:
    """Test task serialization/deserialization."""

    def test_serialize_pending_tasks_with_connection(self):
        """Test serialize pending tasks with connection."""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        # job_state is now passed directly, no need to set thread-local storage

        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

        class TargetRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, **kwargs):
                pass

        source = SourceRoutine()
        target = TargetRoutine()
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")

        flow.connect(source_id, "output", target_id, "input")

        source_event = source.get_event("output")
        target_slot = target.get_slot("input")
        connection = flow._find_connection(source_event, target_slot)

        from routilux.flow.task import SlotActivationTask

        task = SlotActivationTask(
            slot=target_slot,
            data={"test": "data"},
            connection=connection,
        )
        flow._pending_tasks.append(task)

        serialize_pending_tasks(flow, job_state)

        assert len(job_state.pending_tasks) == 1
        serialized = job_state.pending_tasks[0]
        assert serialized["slot_name"] == "input"
        # Note: routine_id might be hex ID, so we check it exists
        assert serialized["connection_source_routine_id"] is not None
        assert serialized["connection_target_routine_id"] is not None

    def test_deserialize_pending_tasks_invalid_routine(self):
        """Test deserialize with invalid routine ID."""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.pending_tasks = [
            {
                "slot_routine_id": "invalid_id",
                "slot_name": "input",
                "data": {},
            }
        ]
        # job_state is now passed directly, no need to set thread-local storage

        deserialize_pending_tasks(flow, job_state)

        assert len(flow._pending_tasks) == 0

    def test_deserialize_pending_tasks_invalid_slot(self):
        """Test deserialize with invalid slot name."""
        flow = Flow()

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, **kwargs):
                pass

        routine = TestRoutine()
        routine_id = flow.add_routine(routine, "test")

        job_state = JobState(flow.flow_id)
        job_state.pending_tasks = [
            {
                "slot_routine_id": routine_id,
                "slot_name": "invalid_slot",
                "data": {},
            }
        ]
        # job_state is now passed directly, no need to set thread-local storage

        deserialize_pending_tasks(flow, job_state)

        assert len(flow._pending_tasks) == 0


class TestWaitForActiveTasks:
    """Test wait for active tasks."""

    def test_wait_for_active_tasks_timeout(self):
        """Test wait for active tasks with timeout."""
        flow = Flow()
        from concurrent.futures import Future

        # Create a mock future that never completes
        future = Future()
        flow._active_tasks.add(future)

        start_time = time.time()
        wait_for_active_tasks(flow)
        elapsed = time.time() - start_time

        # Should timeout after max_wait_time (5.0 seconds)
        assert elapsed < 6.0  # Allow some margin
        assert elapsed >= 4.0  # Should wait at least close to timeout
