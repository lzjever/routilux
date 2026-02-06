"""Tests for output_handler module."""

import queue
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from routilux.output_handler import (
    CallbackOutputHandler,
    NullOutputHandler,
    OutputHandler,
    QueueOutputHandler,
)


class TestOutputHandler:
    """Test base OutputHandler class."""

    def test_output_handler_is_abstract(self):
        """Test that OutputHandler cannot be instantiated directly."""
        with pytest.raises(TypeError):
            OutputHandler()  # type: ignore


class TestQueueOutputHandler:
    """Test QueueOutputHandler class."""

    def test_init_with_queue(self):
        """Test initialization with a queue."""
        q = queue.Queue()
        handler = QueueOutputHandler(q)
        assert handler.queue is q

    def test_handle_puts_entry_in_queue(self):
        """Test that handle puts an entry in the queue."""
        q = queue.Queue()
        handler = QueueOutputHandler(q)

        handler.handle(
            job_id="job1",
            routine_id="routine1",
            output_type="result",
            data={"key": "value"},
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = q.get()
        assert result["job_id"] == "job1"
        assert result["routine_id"] == "routine1"
        assert result["output_type"] == "result"
        assert result["data"] == {"key": "value"}
        assert result["timestamp"] == "2024-01-01T12:00:00"

    def test_handle_without_timestamp_uses_now(self):
        """Test that handle uses current time when no timestamp provided."""
        q = queue.Queue()
        handler = QueueOutputHandler(q)

        before = datetime.now()
        handler.handle(
            job_id="job2",
            routine_id="routine2",
            output_type="status",
            data={"status": "processing"},
        )
        after = datetime.now()

        result = q.get()
        # Parse the timestamp to check it's within expected range
        result_time = datetime.fromisoformat(result["timestamp"])
        assert before <= result_time <= after

    def test_handle_with_various_data_types(self):
        """Test handle with various data types."""
        q = queue.Queue()
        handler = QueueOutputHandler(q)

        test_cases = [
            {"string": "value"},
            {"number": 42},
            {"float": 3.14},
            {"bool": True},
            {"null": None},
            {"list": [1, 2, 3]},
            {"nested": {"key": {"deep": "value"}}},
        ]

        for data in test_cases:
            handler.handle("job1", "routine1", "test", data)
            result = q.get()
            assert result["data"] == data

    def test_handle_multiple_entries(self):
        """Test handling multiple output entries."""
        q = queue.Queue()
        handler = QueueOutputHandler(q)

        for i in range(5):
            handler.handle(
                job_id=f"job{i}",
                routine_id=f"routine{i}",
                output_type="result",
                data={"index": i},
            )

        assert q.qsize() == 5

        for i in range(5):
            result = q.get()
            assert result["job_id"] == f"job{i}"
            assert result["data"]["index"] == i


class TestCallbackOutputHandler:
    """Test CallbackOutputHandler class."""

    def test_init_with_callback(self):
        """Test initialization with a callback."""
        callback = MagicMock()
        handler = CallbackOutputHandler(callback)
        assert handler.callback is callback

    def test_handle_calls_callback_with_all_params(self):
        """Test that handle calls callback with all parameters."""
        callback = MagicMock()
        handler = CallbackOutputHandler(callback)

        timestamp = datetime(2024, 1, 1, 12, 0, 0)
        handler.handle(
            job_id="job1",
            routine_id="routine1",
            output_type="result",
            data={"key": "value"},
            timestamp=timestamp,
        )

        callback.assert_called_once_with("job1", "routine1", "result", {"key": "value"}, timestamp)

    def test_handle_without_timestamp_passes_now(self):
        """Test that handle passes current time when no timestamp provided."""
        callback = MagicMock()
        handler = CallbackOutputHandler(callback)

        before = datetime.now()
        handler.handle(
            job_id="job2",
            routine_id="routine2",
            output_type="status",
            data={"status": "done"},
        )
        after = datetime.now()

        callback.assert_called_once()
        call_args = callback.call_args[0]
        assert call_args[0] == "job2"
        assert call_args[1] == "routine2"
        assert call_args[2] == "status"
        assert call_args[3] == {"status": "done"}
        # Check timestamp is within expected range
        assert before <= call_args[4] <= after

    def test_handle_with_exception_in_callback(self):
        """Test that exceptions in callback are propagated."""

        def failing_callback(*args):
            raise ValueError("Callback failed")

        handler = CallbackOutputHandler(failing_callback)

        with pytest.raises(ValueError, match="Callback failed"):
            handler.handle("job1", "routine1", "test", {})

    def test_handle_multiple_calls(self):
        """Test multiple calls to handle."""
        callback = MagicMock()
        handler = CallbackOutputHandler(callback)

        for i in range(3):
            handler.handle(f"job{i}", f"routine{i}", "test", {"index": i})

        assert callback.call_count == 3

        # Verify each call was made
        assert callback.call_args_list[0][0][0] == "job0"
        assert callback.call_args_list[0][0][1] == "routine0"
        assert callback.call_args_list[0][0][2] == "test"
        assert callback.call_args_list[0][0][3] == {"index": 0}

        assert callback.call_args_list[1][0][0] == "job1"
        assert callback.call_args_list[1][0][1] == "routine1"
        assert callback.call_args_list[1][0][2] == "test"
        assert callback.call_args_list[1][0][3] == {"index": 1}

        assert callback.call_args_list[2][0][0] == "job2"
        assert callback.call_args_list[2][0][1] == "routine2"
        assert callback.call_args_list[2][0][2] == "test"
        assert callback.call_args_list[2][0][3] == {"index": 2}


class TestNullOutputHandler:
    """Test NullOutputHandler class."""

    def test_handle_does_nothing(self):
        """Test that handle does nothing."""
        handler = NullOutputHandler()

        # Should not raise any exception
        handler.handle("job1", "routine1", "result", {"data": "value"})

        # Can be called multiple times
        for i in range(10):
            handler.handle(f"job{i}", f"routine{i}", "test", {"index": i})

    def test_handle_with_timestamp(self):
        """Test that handle ignores timestamp parameter."""
        handler = NullOutputHandler()
        timestamp = datetime(2024, 1, 1, 12, 0, 0)

        # Should not raise any exception
        handler.handle(
            job_id="job1",
            routine_id="routine1",
            output_type="result",
            data={},
            timestamp=timestamp,
        )

    def test_null_handler_is_singleton_like(self):
        """Test that multiple NullOutputHandler instances can be created."""
        handler1 = NullOutputHandler()
        handler2 = NullOutputHandler()

        # They are different instances but both behave the same
        assert handler1 is not handler2

        # Both do nothing
        handler1.handle("job1", "routine1", "test", {})
        handler2.handle("job2", "routine2", "test", {})


class TestOutputHandlerIntegration:
    """Integration tests for output handlers."""

    def test_switching_between_handlers(self):
        """Test switching between different output handlers."""
        q = queue.Queue()
        queue_handler = QueueOutputHandler(q)

        callback_results = []
        callback_handler = CallbackOutputHandler(
            lambda job_id, routine_id, output_type, data, timestamp: callback_results.append(
                (job_id, routine_id, output_type, data)
            )
        )

        null_handler = NullOutputHandler()

        # Use queue handler
        queue_handler.handle("job1", "routine1", "result", {"handler": "queue"})
        assert q.get()["data"]["handler"] == "queue"

        # Use callback handler
        callback_handler.handle("job2", "routine2", "result", {"handler": "callback"})
        assert len(callback_results) == 1
        assert callback_results[0][3]["handler"] == "callback"

        # Use null handler
        null_handler.handle("job3", "routine3", "result", {"handler": "null"})
        # No output, no exception

    def test_output_handler_with_unicode_data(self):
        """Test output handlers with Unicode data."""
        q = queue.Queue()
        handler = QueueOutputHandler(q)

        unicode_data = {
            "emoji": "😀🎉",
            "chinese": "你好世界",
            "arabic": "مرحبا",
            "russian": "Привет",
        }

        handler.handle("job1", "routine1", "unicode", unicode_data)

        result = q.get()
        assert result["data"] == unicode_data

    def test_output_handler_with_large_data(self):
        """Test output handlers with large data."""
        q = queue.Queue()
        handler = QueueOutputHandler(q)

        large_data = {"items": list(range(10000))}

        handler.handle("job1", "routine1", "large", large_data)

        result = q.get()
        assert len(result["data"]["items"]) == 10000

    def test_callback_output_handler_accumulates_results(self):
        """Test callback handler that accumulates results."""
        results = []

        def accumulator(job_id, routine_id, output_type, data, timestamp):
            results.append(
                {
                    "job": job_id,
                    "routine": routine_id,
                    "type": output_type,
                    "data": data,
                    "time": timestamp.isoformat(),
                }
            )

        handler = CallbackOutputHandler(accumulator)

        for i in range(3):
            handler.handle(f"job{i}", f"routine{i}", "step", {"iteration": i})

        assert len(results) == 3
        for i, result in enumerate(results):
            assert result["job"] == f"job{i}"
            assert result["data"]["iteration"] == i
