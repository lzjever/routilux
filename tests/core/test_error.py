"""
Unit tests for routilux.core.error module.

Tests ErrorHandler class and ErrorStrategy enum.
"""

from unittest.mock import MagicMock

import pytest

from routilux.core.error import ErrorHandler, ErrorStrategy


class TestErrorStrategy:
    """Tests for ErrorStrategy enum."""

    def test_strategy_values(self):
        """Test ErrorStrategy enum values."""
        assert ErrorStrategy.STOP.value == "stop"
        assert ErrorStrategy.CONTINUE.value == "continue"
        assert ErrorStrategy.RETRY.value == "retry"
        assert ErrorStrategy.SKIP.value == "skip"

    def test_strategy_count(self):
        """Test that all strategies are defined."""
        assert len(ErrorStrategy) == 4


class TestErrorHandlerInit:
    """Tests for ErrorHandler initialization."""

    def test_init_default(self):
        """Test default initialization."""
        handler = ErrorHandler()
        assert handler.strategy == ErrorStrategy.STOP
        assert handler.max_retries == 3
        assert handler.retry_delay == 1.0
        assert handler.retry_backoff == 2.0
        assert handler.retry_count == 0
        assert handler.is_critical is False
        assert handler.retryable_exceptions == (Exception,)

    def test_init_with_string_strategy(self):
        """Test initialization with string strategy."""
        handler = ErrorHandler(strategy="continue")
        assert handler.strategy == ErrorStrategy.CONTINUE

        handler2 = ErrorHandler(strategy="retry")
        assert handler2.strategy == ErrorStrategy.RETRY

        handler3 = ErrorHandler(strategy="skip")
        assert handler3.strategy == ErrorStrategy.SKIP

    def test_init_with_enum_strategy(self):
        """Test initialization with enum strategy."""
        handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)
        assert handler.strategy == ErrorStrategy.CONTINUE

    def test_init_with_custom_retry_params(self):
        """Test initialization with custom retry parameters."""
        handler = ErrorHandler(
            strategy=ErrorStrategy.RETRY,
            max_retries=5,
            retry_delay=0.5,
            retry_backoff=1.5,
        )
        assert handler.max_retries == 5
        assert handler.retry_delay == 0.5
        assert handler.retry_backoff == 1.5

    def test_init_with_retryable_exceptions(self):
        """Test initialization with custom retryable exceptions."""
        handler = ErrorHandler(
            strategy=ErrorStrategy.RETRY,
            retryable_exceptions=(ValueError, TypeError, KeyError),
        )
        assert ValueError in handler.retryable_exceptions
        assert TypeError in handler.retryable_exceptions
        assert KeyError in handler.retryable_exceptions

    def test_init_with_is_critical(self):
        """Test initialization with is_critical flag."""
        handler = ErrorHandler(strategy=ErrorStrategy.RETRY, is_critical=True)
        assert handler.is_critical is True

    def test_init_invalid_strategy_type(self):
        """Test that invalid strategy type raises TypeError."""
        with pytest.raises(TypeError, match="strategy must be str or ErrorStrategy"):
            ErrorHandler(strategy=123)

    def test_init_invalid_strategy_string(self):
        """Test that invalid strategy string raises ValueError."""
        with pytest.raises(ValueError):
            ErrorHandler(strategy="invalid")

    def test_init_negative_max_retries(self):
        """Test that negative max_retries raises ValueError."""
        with pytest.raises(ValueError, match="max_retries must be >= 0"):
            ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=-1)

    def test_init_negative_retry_delay(self):
        """Test that negative retry_delay raises ValueError."""
        with pytest.raises(ValueError, match="retry_delay must be >= 0"):
            ErrorHandler(strategy=ErrorStrategy.RETRY, retry_delay=-1.0)

    def test_init_invalid_retry_backoff(self):
        """Test that retry_backoff < 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="retry_backoff must be >= 1.0"):
            ErrorHandler(strategy=ErrorStrategy.RETRY, retry_backoff=0.5)


class TestErrorHandlerReset:
    """Tests for ErrorHandler.reset method."""

    def test_reset(self):
        """Test that reset clears retry_count."""
        handler = ErrorHandler(strategy=ErrorStrategy.RETRY)
        handler.retry_count = 5
        handler.reset()
        assert handler.retry_count == 0


class TestErrorHandlerSerialization:
    """Tests for ErrorHandler serialization."""

    def test_serialize(self):
        """Test serialization of ErrorHandler."""
        handler = ErrorHandler(
            strategy=ErrorStrategy.RETRY,
            max_retries=5,
            retry_delay=2.0,
            retry_backoff=1.5,
            is_critical=True,
        )
        handler.retry_count = 3

        data = handler.serialize()

        assert data["strategy"] == "retry"
        assert data["max_retries"] == 5
        assert data["retry_delay"] == 2.0
        assert data["retry_backoff"] == 1.5
        assert data["retry_count"] == 3
        assert data["is_critical"] is True

    def test_deserialize(self):
        """Test deserialization of ErrorHandler."""
        handler = ErrorHandler()

        data = {
            "strategy": "retry",
            "max_retries": 5,
            "retry_delay": 2.0,
            "retry_backoff": 1.5,
            "retry_count": 3,
            "is_critical": True,
        }

        handler.deserialize(data)

        assert handler.strategy == ErrorStrategy.RETRY
        assert handler.max_retries == 5
        assert handler.retry_delay == 2.0
        assert handler.retry_backoff == 1.5
        assert handler.retry_count == 3
        assert handler.is_critical is True

    def test_serialize_deserialize_roundtrip(self):
        """Test that serialize/deserialize roundtrip preserves data."""
        original = ErrorHandler(
            strategy=ErrorStrategy.CONTINUE,
            max_retries=10,
            retry_delay=0.5,
            retry_backoff=3.0,
            is_critical=False,
        )
        original.retry_count = 7

        data = original.serialize()
        restored = ErrorHandler()
        restored.deserialize(data)

        assert restored.strategy == original.strategy
        assert restored.max_retries == original.max_retries
        assert restored.retry_delay == original.retry_delay
        assert restored.retry_backoff == original.retry_backoff
        assert restored.retry_count == original.retry_count
        assert restored.is_critical == original.is_critical


class TestErrorHandlerHandleError:
    """Tests for ErrorHandler.handle_error method."""

    def test_handle_error_stop_strategy(self):
        """Test STOP strategy returns False."""
        handler = ErrorHandler(strategy=ErrorStrategy.STOP)
        error = ValueError("test error")

        result = handler.handle_error(
            error=error,
            routine=None,
            routine_id="test_routine",
            flow=None,
        )

        assert result is False

    def test_handle_error_continue_strategy(self):
        """Test CONTINUE strategy returns True."""
        handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)
        error = ValueError("test error")

        result = handler.handle_error(
            error=error,
            routine=None,
            routine_id="test_routine",
            flow=None,
        )

        assert result is True

    def test_handle_error_skip_strategy(self):
        """Test SKIP strategy returns True."""
        handler = ErrorHandler(strategy=ErrorStrategy.SKIP)
        error = ValueError("test error")

        result = handler.handle_error(
            error=error,
            routine=None,
            routine_id="test_routine",
            flow=None,
        )

        assert result is True

    def test_handle_error_retry_within_limit(self):
        """Test RETRY strategy returns True when within retry limit."""
        handler = ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=3, retry_delay=0.01)
        error = ValueError("test error")

        result = handler.handle_error(
            error=error,
            routine=None,
            routine_id="test_routine",
            flow=None,
        )

        assert result is True
        assert handler.retry_count == 1

    def test_handle_error_retry_exceeds_limit(self):
        """Test RETRY strategy returns False when retries exceeded."""
        handler = ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=2, retry_delay=0.01)
        error = ValueError("test error")

        # First retry
        result1 = handler.handle_error(error=error, routine=None, routine_id="test", flow=None)
        assert result1 is True
        assert handler.retry_count == 1

        # Second retry
        result2 = handler.handle_error(error=error, routine=None, routine_id="test", flow=None)
        assert result2 is True
        assert handler.retry_count == 2

        # Third call - should fail (max_retries exceeded)
        result3 = handler.handle_error(error=error, routine=None, routine_id="test", flow=None)
        assert result3 is False

    def test_handle_error_retry_non_retryable_exception(self):
        """Test RETRY strategy returns False for non-retryable exceptions."""
        handler = ErrorHandler(
            strategy=ErrorStrategy.RETRY,
            max_retries=3,
            retryable_exceptions=(KeyError,),
            retry_delay=0.01,
        )
        error = ValueError("not retryable")

        result = handler.handle_error(
            error=error,
            routine=None,
            routine_id="test_routine",
            flow=None,
        )

        assert result is False
        assert handler.retry_count == 0

    def test_handle_error_retry_critical_failure(self):
        """Test RETRY strategy with critical flag."""
        handler = ErrorHandler(
            strategy=ErrorStrategy.RETRY,
            max_retries=1,
            retry_delay=0.01,
            is_critical=True,
        )
        error = ValueError("test error")

        # First retry
        handler.handle_error(error=error, routine=None, routine_id="test", flow=None)
        # Second call - exceeds limit
        result = handler.handle_error(error=error, routine=None, routine_id="test", flow=None)

        assert result is False

    def test_handle_error_retry_backoff_calculation(self):
        """Test that retry backoff is calculated correctly."""
        handler = ErrorHandler(
            strategy=ErrorStrategy.RETRY,
            max_retries=5,
            retry_delay=1.0,
            retry_backoff=2.0,
        )

        # Test exponential backoff calculation
        # delay = retry_delay * (retry_backoff ** (retry_count - 1))
        # First retry: 1.0 * (2.0 ** 0) = 1.0
        # Second retry: 1.0 * (2.0 ** 1) = 2.0
        # Third retry: 1.0 * (2.0 ** 2) = 4.0
        import time

        start = time.time()
        handler.handle_error(error=ValueError(), routine=None, routine_id="test", flow=None)
        elapsed1 = time.time() - start
        assert elapsed1 < 1.5  # Should be around 1.0 second

    def test_handle_error_with_context(self):
        """Test handle_error with optional context parameter."""
        handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)
        error = ValueError("test error")

        result = handler.handle_error(
            error=error,
            routine=None,
            routine_id="test_routine",
            flow=None,
            context={"key": "value"},
        )

        assert result is True

    def test_handle_error_continue_with_worker_state(self):
        """Test CONTINUE strategy with worker_state records execution."""
        handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)
        error = ValueError("test error")
        worker_state = MagicMock()
        worker_state.record_execution = MagicMock()

        result = handler.handle_error(
            error=error,
            routine=None,
            routine_id="test_routine",
            flow=None,
            worker_state=worker_state,
        )

        assert result is True
        worker_state.record_execution.assert_called_once()
        call_args = worker_state.record_execution.call_args
        assert call_args[0][0] == "test_routine"
        assert call_args[0][1] == "error_continued"

    def test_handle_error_skip_with_worker_state(self):
        """Test SKIP strategy with worker_state updates routine state."""
        handler = ErrorHandler(strategy=ErrorStrategy.SKIP)
        error = ValueError("test error")
        worker_state = MagicMock()
        worker_state.update_routine_state = MagicMock()

        result = handler.handle_error(
            error=error,
            routine=None,
            routine_id="test_routine",
            flow=None,
            worker_state=worker_state,
        )

        assert result is True
        worker_state.update_routine_state.assert_called_once_with(
            "test_routine", {"status": "skipped", "error": "test error"}
        )
