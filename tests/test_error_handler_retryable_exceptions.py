"""
Test retryable_exceptions functionality in ErrorHandler.
"""

from routilux import Flow, Routine, ErrorHandler, ErrorStrategy


class TestRetryableExceptions:
    """Test retryable_exceptions feature."""

    def test_retry_only_retryable_exceptions(self):
        """Test that only retryable exceptions are retried."""
        flow = Flow()
        call_count = [0]

        class FailingRoutine(Routine):
            def __call__(self):
                call_count[0] += 1
                if call_count[0] == 1:
                    # First call raises retryable exception
                    raise ConnectionError("Network error")
                else:
                    # Subsequent calls raise non-retryable exception
                    raise ValueError("Non-retryable error")

        routine = FailingRoutine()
        routine_id = flow.add_routine(routine, "failing")

        # Only retry ConnectionError, not ValueError
        error_handler = ErrorHandler(
            strategy=ErrorStrategy.RETRY,
            max_retries=3,
            retry_delay=0.1,
            retryable_exceptions=(ConnectionError,),
        )
        flow.set_error_handler(error_handler)

        job_state = flow.execute(routine_id)

        # Should stop immediately when ValueError is raised (not retryable)
        assert job_state.status == "failed"
        assert call_count[0] == 2  # Initial + 1 retry (ConnectionError), then ValueError stops

    def test_retry_all_exceptions_by_default(self):
        """Test that all exceptions are retryable by default."""
        flow = Flow()
        call_count = [0]

        class FailingRoutine(Routine):
            def __call__(self):
                call_count[0] += 1
                if call_count[0] < 3:
                    raise ValueError("Error")
                # Succeed on 3rd attempt

        routine = FailingRoutine()
        routine_id = flow.add_routine(routine, "failing")

        # Default: all exceptions are retryable
        error_handler = ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=3, retry_delay=0.1)
        flow.set_error_handler(error_handler)

        job_state = flow.execute(routine_id)

        # Should succeed after retries
        assert job_state.status == "completed"
        assert call_count[0] == 3

    def test_non_retryable_exception_stops_immediately(self):
        """Test that non-retryable exception stops immediately."""
        flow = Flow()
        call_count = [0]

        class FailingRoutine(Routine):
            def __call__(self):
                call_count[0] += 1
                raise ValueError("Non-retryable")

        routine = FailingRoutine()
        routine_id = flow.add_routine(routine, "failing")

        # Only retry ConnectionError
        error_handler = ErrorHandler(
            strategy=ErrorStrategy.RETRY,
            max_retries=5,
            retry_delay=0.1,
            retryable_exceptions=(ConnectionError,),
        )
        flow.set_error_handler(error_handler)

        job_state = flow.execute(routine_id)

        # Should stop immediately (ValueError is not retryable)
        assert job_state.status == "failed"
        assert call_count[0] == 1  # Only initial call, no retries
        assert error_handler.retry_count == 0  # No retries attempted
