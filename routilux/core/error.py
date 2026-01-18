"""
Error handling strategies for Routilux.

Defines error handling strategies and retry mechanisms.
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import TYPE_CHECKING, Any

from serilux import Serializable

if TYPE_CHECKING:
    from routilux.core.flow import Flow
    from routilux.core.routine import Routine
    from routilux.core.worker import WorkerState

logger = logging.getLogger(__name__)


class ErrorStrategy(Enum):
    """Error handling strategy enumeration.

    Defines how errors in routine execution should be handled.

    Available strategies:

    - STOP: Immediately stop execution when an error occurs.
    - CONTINUE: Log error but continue execution.
    - RETRY: Automatically retry with exponential backoff.
    - SKIP: Skip the failed routine and continue.
    """

    STOP = "stop"
    CONTINUE = "continue"
    RETRY = "retry"
    SKIP = "skip"


# Note: Not using @register_serializable to avoid conflict with legacy module
# Will be registered after legacy module is removed
class ErrorHandler(Serializable):
    """Error handler for managing error handling strategies and retry mechanisms.

    An ErrorHandler defines how errors in routine execution should be handled.
    It can be set at the Flow level (default for all routines) or at the Routine
    level (override for specific routines).

    Priority: Routine-level > Flow-level > Default (STOP)

    Examples:
        >>> handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)
        >>> flow.set_error_handler(handler)

        >>> handler = ErrorHandler(
        ...     strategy=ErrorStrategy.RETRY,
        ...     max_retries=5,
        ...     retry_delay=2.0,
        ...     retry_backoff=1.5,
        ... )
        >>> routine.set_error_handler(handler)
    """

    def __init__(
        self,
        strategy: str | ErrorStrategy = "stop",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
        retryable_exceptions: tuple[type, ...] | None = None,
        is_critical: bool = False,
    ):
        """Initialize ErrorHandler.

        Args:
            strategy: Error handling strategy ("stop", "continue", "retry", "skip")
            max_retries: Maximum retry attempts for RETRY strategy
            retry_delay: Initial delay before first retry (seconds)
            retry_backoff: Multiplier for exponential backoff
            retryable_exceptions: Tuple of exception types to retry
            is_critical: If True, flow fails when all retries fail
        """
        super().__init__()

        # Validate and convert strategy
        if isinstance(strategy, str):
            self.strategy: ErrorStrategy = ErrorStrategy(strategy)
        elif isinstance(strategy, ErrorStrategy):
            self.strategy = strategy
        else:
            raise TypeError(f"strategy must be str or ErrorStrategy, got {type(strategy).__name__}")

        # Validate retry parameters
        if max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {max_retries}")
        if retry_delay < 0:
            raise ValueError(f"retry_delay must be >= 0, got {retry_delay}")
        if retry_backoff < 1.0:
            raise ValueError(f"retry_backoff must be >= 1.0, got {retry_backoff}")

        self.max_retries: int = max_retries
        self.retry_delay: float = retry_delay
        self.retry_backoff: float = retry_backoff
        self.retryable_exceptions: tuple[type, ...] = retryable_exceptions or (Exception,)
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
        routine: Routine,
        routine_id: str,
        flow: Flow,
        worker_state: WorkerState | None = None,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Handle an error according to the configured strategy.

        Args:
            error: Exception that occurred
            routine: Routine where error occurred
            routine_id: Routine identifier
            flow: Flow managing execution
            worker_state: Worker state for recording errors
            context: Optional additional context

        Returns:
            True if execution should continue, False if should stop
        """
        context = context or {}

        if self.strategy == ErrorStrategy.STOP:
            logger.error(f"Error in routine {routine_id}: {error}. Stopping execution.")
            return False

        elif self.strategy == ErrorStrategy.CONTINUE:
            logger.warning(f"Error in routine {routine_id}: {error}. Continuing execution.")
            if worker_state:
                worker_state.record_execution(
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
                return False

            if self.retry_count < self.max_retries:
                self.retry_count += 1
                delay = self.retry_delay * (self.retry_backoff ** (self.retry_count - 1))
                logger.warning(
                    f"Error in routine {routine_id}: {error}. "
                    f"Retrying ({self.retry_count}/{self.max_retries}) after {delay}s..."
                )
                time.sleep(delay)
                return True
            else:
                if self.is_critical:
                    logger.error(
                        f"Error in routine {routine_id}: {error}. "
                        f"Critical routine failed after {self.max_retries} retries."
                    )
                else:
                    logger.error(
                        f"Error in routine {routine_id}: {error}. "
                        f"Max retries ({self.max_retries}) exceeded. Stopping."
                    )
                return False

        elif self.strategy == ErrorStrategy.SKIP:
            logger.warning(f"Error in routine {routine_id}: {error}. Skipping routine.")
            if worker_state:
                worker_state.update_routine_state(
                    routine_id, {"status": "skipped", "error": str(error)}
                )
            return True

        return False

    def reset(self) -> None:
        """Reset the retry count."""
        self.retry_count = 0

    def serialize(self) -> dict[str, Any]:
        """Serialize the ErrorHandler."""
        data = super().serialize()
        if isinstance(data.get("strategy"), ErrorStrategy):
            data["strategy"] = data["strategy"].value
        return data

    def deserialize(
        self, data: dict[str, Any], strict: bool = False, registry: Any | None = None
    ) -> None:
        """Deserialize the ErrorHandler."""
        if "strategy" in data and isinstance(data["strategy"], str):
            data["strategy"] = ErrorStrategy(data["strategy"])
        super().deserialize(data, strict=strict, registry=registry)
