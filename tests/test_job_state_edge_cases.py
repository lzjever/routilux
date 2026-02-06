"""Edge case tests for job_state module."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from routilux.job_state import ExecutionRecord, JobState


class TestExecutionRecordEdgeCases:
    """Test edge cases for ExecutionRecord class."""

    def test_execution_record_with_none_data(self):
        """Test ExecutionRecord with None data."""
        record = ExecutionRecord(routine_id="test", event_name="test_event", data=None)

        assert record.data == {}

    def test_execution_record_with_custom_timestamp(self):
        """Test ExecutionRecord with custom timestamp."""
        custom_time = datetime(2024, 1, 1, 12, 0, 0)
        record = ExecutionRecord(
            routine_id="test",
            event_name="test_event",
            data={},
            timestamp=custom_time,
        )

        assert record.timestamp == custom_time

    def test_execution_record_repr(self):
        """Test __repr__ method."""
        record = ExecutionRecord(
            routine_id="my_routine",
            event_name="output",
            data={"value": 42},
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = repr(record)
        assert "ExecutionRecord" in result
        assert "my_routine" in result
        assert "output" in result

    def test_serialize_deserialize_execution_record(self):
        """Test serialization and deserialization of ExecutionRecord."""
        record = ExecutionRecord(
            routine_id="test",
            event_name="test_event",
            data={"key": "value"},
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        )

        serialized = record.serialize()
        assert serialized["timestamp"] == "2024-01-01T12:00:00"

        new_record = ExecutionRecord()
        new_record.deserialize(serialized)

        assert new_record.routine_id == "test"
        assert new_record.event_name == "test_event"
        assert new_record.data == {"key": "value"}

    def test_execution_record_with_complex_data(self):
        """Test ExecutionRecord with complex nested data."""
        complex_data = {
            "nested": {"key": "value", "number": 42},
            "list": [1, 2, 3],
            "mixed": [{"a": 1}, {"b": 2}],
        }

        record = ExecutionRecord(
            routine_id="test",
            event_name="test_event",
            data=complex_data,
        )

        assert record.data == complex_data


class TestJobStateEdgeCases:
    """Test edge cases for JobState class."""

    def test_job_state_initialization_defaults(self):
        """Test JobState initialization with default values."""
        job_state = JobState()

        assert job_state.flow_id == ""
        assert job_state.status == "pending"
        assert job_state.routine_states == {}
        assert job_state.execution_history == []
        assert job_state.pause_points == []
        assert job_state.current_routine_id is None
        assert job_state.deferred_events == []
        assert job_state.shared_data == {}
        assert job_state.shared_log == []
        assert job_state.output_log == []

    def test_job_state_repr(self):
        """Test __repr__ method."""
        job_state = JobState("test_flow")

        result = repr(job_state)
        assert "JobState" in result
        assert job_state.job_id in result
        assert "pending" in result

    def test_update_routine_state_copies_state(self):
        """Test that update_routine_state copies the state dict."""
        job_state = JobState()
        original_state = {"status": "completed", "result": "success"}

        job_state.update_routine_state("r1", original_state)

        # Modify original
        original_state["status"] = "failed"

        # Stored state should not be affected
        assert job_state.routine_states["r1"]["status"] == "completed"

    def test_get_routine_state_nonexistent(self):
        """Test get_routine_state for non-existent routine."""
        job_state = JobState()

        result = job_state.get_routine_state("nonexistent")

        assert result is None

    def test_record_execution_triggers_cleanup(self):
        """Test that record_execution triggers history cleanup."""
        job_state = JobState()
        job_state.max_history_size = 5

        # Add more records than max_history_size
        for i in range(10):
            job_state.record_execution(f"r{i}", "test", {"index": i})

        # Should only keep last 5
        assert len(job_state.execution_history) == 5
        assert job_state.execution_history[0].routine_id == "r5"

    def test_cleanup_history_with_ttl(self):
        """Test history cleanup with TTL."""
        job_state = JobState()
        job_state.history_ttl_seconds = 60  # 1 minute

        # Add old records
        old_time = datetime.now() - timedelta(seconds=120)
        record1 = ExecutionRecord("r1", "test", {}, timestamp=old_time)
        job_state.execution_history.append(record1)

        # Add recent record
        job_state.record_execution("r2", "test", {})

        # Should only have recent record
        assert len(job_state.execution_history) == 1
        assert job_state.execution_history[0].routine_id == "r2"

    def test_cleanup_history_with_zero_max_size(self):
        """Test cleanup with max_history_size=0."""
        job_state = JobState()
        job_state.max_history_size = 0

        job_state.record_execution("r1", "test", {})

        # All history should be removed
        assert len(job_state.execution_history) == 0

    def test_cleanup_history_with_none_limits(self):
        """Test cleanup with None limits (unlimited)."""
        job_state = JobState()
        job_state.max_history_size = None
        job_state.history_ttl_seconds = None

        # Add many records
        for i in range(100):
            job_state.record_execution(f"r{i}", "test", {"index": i})

        # All records should be kept
        assert len(job_state.execution_history) == 100

    def test_get_execution_history_sorted(self):
        """Test that execution history is sorted by timestamp."""
        job_state = JobState()

        # Add records in non-chronological order
        t1 = datetime(2024, 1, 1, 12, 0, 0)
        t2 = datetime(2024, 1, 1, 11, 0, 0)
        t3 = datetime(2024, 1, 1, 13, 0, 0)

        job_state.execution_history.append(ExecutionRecord("r1", "test", {}, timestamp=t1))
        job_state.execution_history.append(ExecutionRecord("r2", "test", {}, timestamp=t2))
        job_state.execution_history.append(ExecutionRecord("r3", "test", {}, timestamp=t3))

        history = job_state.get_execution_history()

        # Should be sorted
        assert history[0].timestamp == t2
        assert history[1].timestamp == t1
        assert history[2].timestamp == t3

    def test_get_execution_history_filtered(self):
        """Test filtering execution history by routine_id."""
        job_state = JobState()

        job_state.record_execution("r1", "test", {"value": 1})
        job_state.record_execution("r2", "test", {"value": 2})
        job_state.record_execution("r1", "test", {"value": 3})

        r1_history = job_state.get_execution_history("r1")

        assert len(r1_history) == 2
        assert all(r.routine_id == "r1" for r in r1_history)

    def test_add_deferred_event(self):
        """Test adding deferred events."""
        job_state = JobState()

        job_state.add_deferred_event("r1", "output", {"data": "test"})

        assert len(job_state.deferred_events) == 1
        assert job_state.deferred_events[0]["routine_id"] == "r1"
        assert job_state.deferred_events[0]["event_name"] == "output"
        assert "timestamp" in job_state.deferred_events[0]

    def test_shared_data_operations(self):
        """Test shared data get/set operations."""
        job_state = JobState()

        job_state.update_shared_data("key1", "value1")
        job_state.update_shared_data("key2", 42)

        assert job_state.get_shared_data("key1") == "value1"
        assert job_state.get_shared_data("key2") == 42
        assert job_state.get_shared_data("nonexistent", "default") == "default"
        assert job_state.get_shared_data("nonexistent") is None

    def test_shared_log_operations(self):
        """Test shared log operations."""
        job_state = JobState()

        job_state.append_to_shared_log({"level": "info", "message": "test1"})
        job_state.append_to_shared_log({"level": "error", "message": "test2"})

        log = job_state.get_shared_log()

        assert len(log) == 2
        assert log[0]["message"] == "test1"
        assert log[1]["message"] == "test2"

    def test_shared_log_auto_adds_timestamp(self):
        """Test that shared log auto-adds timestamp if missing."""
        job_state = JobState()

        job_state.append_to_shared_log({"message": "test"})

        log = job_state.get_shared_log()
        assert "timestamp" in log[0]

    def test_shared_log_rejects_non_dict(self):
        """Test that shared log rejects non-dict entries."""
        job_state = JobState()

        with pytest.raises(ValueError, match="Entry must be a dictionary"):
            job_state.append_to_shared_log("not a dict")  # type: ignore

    def test_shared_log_with_filter(self):
        """Test filtering shared log."""
        job_state = JobState()

        job_state.append_to_shared_log({"level": "info", "message": "info1"})
        job_state.append_to_shared_log({"level": "error", "message": "error1"})
        job_state.append_to_shared_log({"level": "info", "message": "info2"})

        error_logs = job_state.get_shared_log(
            filter_func=lambda entry: entry.get("level") == "error"
        )

        assert len(error_logs) == 1
        assert error_logs[0]["message"] == "error1"

    def test_set_output_handler(self):
        """Test setting output handler."""
        job_state = JobState()
        handler = MagicMock()

        job_state.set_output_handler(handler)

        assert job_state.output_handler is handler

    def test_set_output_handler_none(self):
        """Test setting output handler to None."""
        job_state = JobState()
        job_state.output_handler = MagicMock()

        job_state.set_output_handler(None)

        assert job_state.output_handler is None

    def test_send_output_calls_handler(self):
        """Test that send_output calls output handler."""
        job_state = JobState()
        handler = MagicMock()
        job_state.set_output_handler(handler)

        job_state.send_output("r1", "result", {"data": "test"})

        handler.handle.assert_called_once()
        call_args = handler.handle.call_args
        assert call_args[1]["job_id"] == job_state.job_id
        assert call_args[1]["routine_id"] == "r1"
        assert call_args[1]["output_type"] == "result"
        assert call_args[1]["data"] == {"data": "test"}

    def test_send_output_adds_to_output_log(self):
        """Test that send_output adds to output_log."""
        job_state = JobState()

        job_state.send_output("r1", "result", {"data": "test"})

        assert len(job_state.output_log) == 1
        assert job_state.output_log[0]["routine_id"] == "r1"
        assert job_state.output_log[0]["output_type"] == "result"

    def test_send_output_handler_failure_is_ignored(self):
        """Test that output handler failures are caught and ignored."""
        job_state = JobState()

        def failing_handler(**kwargs):
            raise ValueError("Handler failed")

        job_state.set_output_handler(failing_handler)

        # Should not raise exception
        job_state.send_output("r1", "result", {"data": "test"})

        # Should still add to output_log
        assert len(job_state.output_log) == 1

    def test_set_paused(self):
        """Test _set_paused method."""
        job_state = JobState()
        job_state.current_routine_id = "r1"

        job_state._set_paused("test reason", {"checkpoint": "data"})

        assert job_state.status == "paused"
        assert len(job_state.pause_points) == 1
        assert job_state.pause_points[0]["reason"] == "test reason"
        assert job_state.pause_points[0]["checkpoint"] == {"checkpoint": "data"}

    def test_set_running_from_paused(self):
        """Test _set_running from paused state."""
        job_state = JobState()
        job_state.status = "paused"

        job_state._set_running()

        assert job_state.status == "running"

    def test_set_running_from_non_paused(self):
        """Test _set_running from non-paused state."""
        job_state = JobState()
        job_state.status = "pending"

        job_state._set_running()

        # Should not change status
        assert job_state.status == "pending"

    def test_set_cancelled(self):
        """Test _set_cancelled method."""
        job_state = JobState()

        job_state._set_cancelled("user request")

        assert job_state.status == "cancelled"
        assert job_state.routine_states["_cancellation"]["reason"] == "user request"


class TestJobStateSerialization:
    """Test serialization edge cases."""

    def test_save_and_load(self, tmp_path):
        """Test saving and loading JobState."""
        job_state = JobState("test_flow")
        job_state.update_routine_state("r1", {"status": "completed"})
        job_state.record_execution("r1", "output", {"data": "test"})

        filepath = tmp_path / "job_state.json"

        job_state.save(str(filepath))

        loaded_state = JobState.load(str(filepath))

        assert loaded_state.flow_id == "test_flow"
        assert loaded_state.routine_states["r1"]["status"] == "completed"
        assert len(loaded_state.execution_history) == 1

    def test_load_nonexistent_file(self):
        """Test loading non-existent file."""
        with pytest.raises(FileNotFoundError):
            JobState.load("/nonexistent/path.json")

    def test_load_invalid_format(self, tmp_path):
        """Test loading file with invalid format."""
        filepath = tmp_path / "invalid.json"
        filepath.write_text('{"_type": "InvalidType"}')

        with pytest.raises(ValueError, match="Invalid JobState file format"):
            JobState.load(str(filepath))

    def test_serialize_deserialize_datetime_fields(self):
        """Test datetime serialization/deserialization."""
        job_state = JobState("test_flow")

        serialized = job_state.serialize()

        assert isinstance(serialized["created_at"], str)
        assert isinstance(serialized["updated_at"], str)

        new_job_state = JobState()
        new_job_state.deserialize(serialized)

        assert isinstance(new_job_state.created_at, datetime)
        assert isinstance(new_job_state.updated_at, datetime)

    def test_serialize_deserialize_execution_history(self):
        """Test serialization/deserialization of execution history."""
        job_state = JobState("test_flow")
        job_state.record_execution("r1", "test", {"data": "value"})

        serialized = job_state.serialize()

        # ExecutionRecord should be serialized
        assert "execution_history" in serialized
        assert len(serialized["execution_history"]) == 1
        assert serialized["execution_history"][0]["routine_id"] == "r1"

        # Deserialize
        new_job_state = JobState()
        new_job_state.deserialize(serialized)

        assert len(new_job_state.execution_history) == 1
        assert new_job_state.execution_history[0].routine_id == "r1"
        assert new_job_state.execution_history[0].data == {"data": "value"}

    def test_serialize_deserialize_with_all_fields(self):
        """Test serialization with all fields populated."""
        job_state = JobState("test_flow")
        job_state.update_routine_state("r1", {"status": "completed"})
        job_state.record_execution("r1", "output", {"data": "test"})
        job_state.add_deferred_event("r2", "input", {"key": "value"})
        job_state.update_shared_data("shared", "data")
        job_state.append_to_shared_log({"level": "info"})

        serialized = job_state.serialize()

        new_job_state = JobState()
        new_job_state.deserialize(serialized)

        assert new_job_state.flow_id == "test_flow"
        assert new_job_state.routine_states["r1"]["status"] == "completed"
        assert len(new_job_state.execution_history) == 1
        assert len(new_job_state.deferred_events) == 1
        assert new_job_state.shared_data["shared"] == "data"
        assert len(new_job_state.shared_log) == 1


class TestJobStateWaitMethods:
    """Test wait methods edge cases."""

    def test_wait_for_completion_mock(self):
        """Test wait_for_completion with mocked flow."""
        job_state = JobState("test_flow")
        job_state.status = "completed"

        flow = MagicMock()
        flow._task_queue.empty.return_value = True
        flow._active_tasks = []
        flow._execution_lock.__enter__ = MagicMock()
        flow._execution_lock.__exit__ = MagicMock()

        result = JobState.wait_for_completion(flow, job_state, timeout=1.0, check_interval=0.01)

        assert result is True

    def test_wait_for_completion_timeout(self):
        """Test wait_for_completion timeout."""
        job_state = JobState("test_flow")
        job_state.status = "running"

        flow = MagicMock()
        flow._task_queue.empty.return_value = False  # Never empty
        flow._active_tasks = []
        flow._execution_lock.__enter__ = MagicMock()
        flow._execution_lock.__exit__ = MagicMock()

        result = JobState.wait_for_completion(flow, job_state, timeout=0.1, check_interval=0.05)

        assert result is False

    def test_wait_until_condition_met(self):
        """Test wait_until_condition when condition is met."""
        job_state = JobState("test_flow")
        job_state.status = "running"

        flow = MagicMock()

        condition = MagicMock(side_effect=[False, False, True])

        result = JobState.wait_until_condition(
            flow, job_state, condition, timeout=1.0, check_interval=0.01
        )

        assert result is True
        assert condition.call_count == 3

    def test_wait_until_condition_timeout(self):
        """Test wait_until_condition timeout."""
        job_state = JobState("test_flow")
        job_state.status = "running"

        flow = MagicMock()

        condition = MagicMock(return_value=False)  # Never met

        result = JobState.wait_until_condition(
            flow, job_state, condition, timeout=0.1, check_interval=0.05
        )

        assert result is False

    def test_wait_until_condition_execution_completed(self):
        """Test wait_until_condition when execution completes."""
        job_state = JobState("test_flow")
        job_state.status = "running"

        flow = MagicMock()
        call_count = [0]

        def condition(f, js):
            call_count[0] += 1
            # After 2 calls, mark as completed
            if call_count[0] > 2:
                js.status = "completed"
            return False

        result = JobState.wait_until_condition(
            flow, job_state, condition, timeout=1.0, check_interval=0.01
        )

        assert result is False
        assert job_state.status == "completed"

    def test_wait_until_condition_with_exception(self):
        """Test wait_until_condition when condition raises exception."""
        job_state = JobState("test_flow")
        job_state.status = "running"

        flow = MagicMock()

        def failing_condition(f, js):
            call_count = failing_condition.call_count
            failing_condition.call_count += 1
            if call_count < 2:
                raise ValueError("Test error")
            return True

        failing_condition.call_count = 0

        result = JobState.wait_until_condition(
            flow, job_state, failing_condition, timeout=1.0, check_interval=0.01
        )

        # Should continue waiting despite exceptions
        assert result is True
