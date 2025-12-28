"""
Error handling strategies.

Defines error handling strategies and retry mechanisms.
"""

from __future__ import annotations
from typing import Optional, Dict, Any, TYPE_CHECKING
from enum import Enum
import time
import logging
from serilux import register_serializable, Serializable

if TYPE_CHECKING:
    from routilux.routine import Routine
    from routilux.flow import Flow

logger = logging.getLogger(__name__)


class ErrorStrategy(Enum):
    """Error handling strategy enumeration.

    Defines how errors in routine execution should be handled. Each strategy
    has different behavior regarding flow continuation, error logging, and
    retry mechanisms.

    Available strategies:

    - STOP: Immediately stop flow execution when an error occurs.
      Flow status set to "failed", execution stops immediately, no retry attempts.
      Use for critical workflows where any error is unacceptable.

    - CONTINUE: Log error but continue flow execution.
      Flow status set to "completed" (not "failed"), routine marked as "error_continued",
      execution continues to downstream routines.
      Use for non-critical operations where failures are acceptable.

    - RETRY: Automatically retry the failed routine.
      Retries up to max_retries times, uses exponential backoff for delays,
      only retries retryable exceptions. If all retries fail: stops (or fails flow if is_critical=True).
      Use for transient failures (network, timeouts).

    - SKIP: Skip the failed routine and continue.
      Routine marked as "skipped", flow status set to "completed",
      execution continues to downstream routines.
      Use for optional processing steps.
    """

    STOP = "stop"  # Stop execution immediately
    CONTINUE = "continue"  # Continue to next routine
    RETRY = "retry"  # Retry the operation
    SKIP = "skip"  # Skip the routine


@register_serializable
class ErrorHandler(Serializable):
    """Error handler for managing error handling strategies and retry mechanisms.

    An ErrorHandler defines how errors in routine execution should be handled.
    It can be set at the Flow level (default for all routines) or at the Routine
    level (override for specific routines). Routine-level handlers take priority.

    Key Features:

    - Multiple Strategies: STOP, CONTINUE, RETRY, SKIP
    - Configurable Retry: Max retries, delays, exponential backoff
    - Exception Filtering: Only retry specific exception types
    - Critical Flag: Mark routines as critical (must succeed)

    Retry Mechanism:

    When using RETRY strategy, retries only occur for exceptions in
    retryable_exceptions tuple. Delay between retries is calculated as:
    ``retry_delay * (retry_backoff ** (retry_count - 1))``.

    Example with retry_delay=1.0, retry_backoff=2.0:
    Retry 1: 1.0s delay, Retry 2: 2.0s delay, Retry 3: 4.0s delay.

    If max_retries exceeded: is_critical=True causes flow to fail,
    is_critical=False stops execution.

    Priority System:

    Error handlers are checked in this order:
    1. Routine-level handler (if set via routine.set_error_handler())
    2. Flow-level handler (if set via flow.set_error_handler())
    3. Default behavior (STOP)

    Examples:
        Basic error handler:
            >>> handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)
            >>> flow.set_error_handler(handler)

        Retry handler with custom config:
            >>> handler = ErrorHandler(
            ...     strategy=ErrorStrategy.RETRY,
            ...     max_retries=5,
            ...     retry_delay=2.0,
            ...     retry_backoff=1.5,
            ...     retryable_exceptions=(ConnectionError, TimeoutError)
            ... )
            >>> routine.set_error_handler(handler)

        Critical routine handler:
            >>> handler = ErrorHandler(
            ...     strategy=ErrorStrategy.RETRY,
            ...     max_retries=3,
            ...     is_critical=True  # Flow fails if all retries fail
            ... )
            >>> critical_routine.set_error_handler(handler)
    """

    def __init__(
        self,
        strategy: str = "stop",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
        retryable_exceptions: Optional[tuple] = None,
        is_critical: bool = False,
    ):
        """Initialize ErrorHandler with configuration.

        Args:
            strategy: Error handling strategy. Can be:
                - String: "stop", "continue", "retry", "skip"
                - ErrorStrategy enum: ErrorStrategy.STOP, etc.
                Default: "stop"
            max_retries: Maximum number of retry attempts for RETRY strategy.
                Only used when strategy is RETRY. Default: 3
            retry_delay: Initial delay in seconds before first retry.
                Subsequent retries use: retry_delay * (retry_backoff ** retry_count)
                Default: 1.0 seconds
            retry_backoff: Multiplier for exponential backoff between retries.
                Each retry delay is multiplied by this value.
                Example: delay=1.0, backoff=2.0 → delays: 1s, 2s, 4s, 8s...
                Default: 2.0
            retryable_exceptions: Tuple of exception types that should be retried.
                If an exception is not in this tuple, it won't be retried (stops immediately).
                If None, defaults to (Exception,) - retries all exceptions.
                Example: (ConnectionError, TimeoutError, OSError)
            is_critical: If True, marks the routine as critical.
                For RETRY strategy: If all retries fail, the flow will fail.
                For other strategies: This flag has no effect (for future use).
                Default: False

        Examples:
            Stop on any error:
                >>> handler = ErrorHandler(strategy="stop")

            Continue on error:
                >>> handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)

            Retry with exponential backoff:
                >>> handler = ErrorHandler(
                ...     strategy="retry",
                ...     max_retries=5,
                ...     retry_delay=1.0,
                ...     retry_backoff=2.0
                ... )

            Retry only network errors:
                >>> handler = ErrorHandler(
                ...     strategy="retry",
                ...     retryable_exceptions=(ConnectionError, TimeoutError)
                ... )
        """
        super().__init__()
        # Support both string and enum
        if isinstance(strategy, str):
            self.strategy: ErrorStrategy = ErrorStrategy(strategy)
        else:
            self.strategy: ErrorStrategy = strategy
        self.max_retries: int = max_retries
        self.retry_delay: float = retry_delay
        self.retry_backoff: float = retry_backoff
        self.retryable_exceptions: tuple = retryable_exceptions or (Exception,)
        self.retry_count: int = 0
        self.is_critical: bool = is_critical

        # Register serializable fields
        self.add_serializable_fields(
            [
                "strategy",
                "max_retries",
                "retry_delay",
                "retry_backoff",
                "retry_count",
                "is_critical",
            ]
        )

    def handle_error(
        self,
        error: Exception,
        routine: "Routine",
        routine_id: str,
        flow: "Flow",
        context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Handle an error according to the configured strategy.

        This method is called by the Flow when a routine execution fails.
        It implements the error handling logic based on the configured strategy
        and returns whether execution should continue.

        Strategy Behaviors:

            STOP: Logs error and returns False (stop execution)

            CONTINUE: Logs warning, records error, returns True (continue)

            SKIP: Logs warning, marks routine as skipped, returns True (continue)

            RETRY:
                - If exception not retryable: Returns False (stop immediately)
                - If retries remaining: Increments count, sleeps, returns True (retry)
                - If max retries exceeded:
                  - is_critical=True: Returns False (flow fails)
                  - is_critical=False: Returns False (stop execution)

        Args:
            error: Exception object that occurred during routine execution.
                The exception type is checked against retryable_exceptions
                for RETRY strategy.
            routine: Routine instance where the error occurred.
                Used for accessing routine state and statistics.
            routine_id: Unique identifier of the routine in the flow.
                Used for logging and state tracking.
            flow: Flow object managing the execution.
                Used for accessing job_state and recording execution history.
            context: Optional context dictionary with additional information.
                Currently not used but reserved for future extensions.

        Returns:
            bool: True if execution should continue (retry or proceed),
                  False if execution should stop (error or max retries).

            The Flow uses this return value to decide whether to:
            - Continue execution (True): Retry routine or proceed to next
            - Stop execution (False): Mark flow as failed and stop

        Side Effects:
            - Logs error/warning messages
            - Updates retry_count for RETRY strategy
            - Records error in job_state for CONTINUE/SKIP strategies
            - Sleeps for retry delay in RETRY strategy

        Examples:
            The method is called automatically by Flow:
                >>> # Flow detects error in routine execution
                >>> should_continue = error_handler.handle_error(
                ...     error=ValueError("Something went wrong"),
                ...     routine=my_routine,
                ...     routine_id="my_routine",
                ...     flow=my_flow
                ... )
                >>> # Returns True/False based on strategy
        """
        context = context or {}

        if self.strategy == ErrorStrategy.STOP:
            logger.error(f"Error in routine {routine_id}: {error}. Stopping execution.")
            return False

        elif self.strategy == ErrorStrategy.CONTINUE:
            logger.warning(f"Error in routine {routine_id}: {error}. Continuing execution.")
            # Record error but continue execution
            if flow.job_state:
                flow.job_state.record_execution(
                    routine_id,
                    "error_continued",
                    {"error": str(error), "error_type": type(error).__name__},
                )
            return True

        elif self.strategy == ErrorStrategy.RETRY:
            # Check if exception is retryable
            if not isinstance(error, self.retryable_exceptions):
                logger.error(
                    f"Error in routine {routine_id}: {error}. "
                    f"Exception type {type(error).__name__} is not retryable. Stopping."
                )
                # Non-retryable exceptions should stop immediately (don't enter retry loop)
                # The is_critical flag only affects behavior after retries are exhausted
                return False

            if self.retry_count < self.max_retries:
                self.retry_count += 1
                delay = self.retry_delay * (self.retry_backoff ** (self.retry_count - 1))
                logger.warning(
                    f"Error in routine {routine_id}: {error}. "
                    f"Retrying ({self.retry_count}/{self.max_retries}) after {delay}s..."
                )
                time.sleep(delay)
                return True  # Return True to indicate retry should occur
            else:
                # Max retries exceeded
                if self.is_critical:
                    logger.error(
                        f"Error in routine {routine_id}: {error}. "
                        f"Critical routine failed after {self.max_retries} retries. Flow will fail."
                    )
                else:
                    logger.error(
                        f"Error in routine {routine_id}: {error}. "
                        f"Max retries ({self.max_retries}) exceeded. Stopping."
                    )
                # For critical routines, retry failure means flow must fail
                return not self.is_critical

        elif self.strategy == ErrorStrategy.SKIP:
            logger.warning(f"Error in routine {routine_id}: {error}. Skipping routine.")
            # Mark as skipped
            if flow.job_state:
                flow.job_state.update_routine_state(
                    routine_id, {"status": "skipped", "error": str(error)}
                )
            return True

        return False

    def reset(self) -> None:
        """Reset the retry count."""
        self.retry_count = 0

    def serialize(self) -> Dict[str, Any]:
        """Serialize the ErrorHandler.

        Returns:
            Serialized dictionary containing error handler configuration.
        """
        data = super().serialize()
        # ErrorStrategy enum needs to be converted to string
        if isinstance(data.get("strategy"), ErrorStrategy):
            data["strategy"] = data["strategy"].value
        return data

    def deserialize(self, data: Dict[str, Any], registry: Optional[Any] = None) -> None:
        """Deserialize the ErrorHandler.

        Args:
            data: Serialized data dictionary.
            registry: Optional ObjectRegistry for deserializing callables.
        """
        # ErrorStrategy needs to be converted from string to enum
        if "strategy" in data and isinstance(data["strategy"], str):
            data["strategy"] = ErrorStrategy(data["strategy"])
        super().deserialize(data, registry=registry)
