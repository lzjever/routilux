"""
Error handling strategies.

Defines error handling strategies and retry mechanisms.
"""
from __future__ import annotations
from typing import Callable, Optional, Dict, Any, List, TYPE_CHECKING
from enum import Enum
import time
import logging
from flowforge.utils.serializable import register_serializable, Serializable

if TYPE_CHECKING:
    from flowforge.routine import Routine
    from flowforge.flow import Flow

logger = logging.getLogger(__name__)


class ErrorStrategy(Enum):
    """Error handling strategy enumeration."""
    STOP = "stop"  # Stop execution
    CONTINUE = "continue"  # Continue to next routine
    RETRY = "retry"  # Retry the operation
    SKIP = "skip"  # Skip the routine


@register_serializable
class ErrorHandler(Serializable):
    """Error handler for managing error handling strategies and retry mechanisms.
    
    Provides configurable error handling strategies including stop, continue, retry,
    and skip. Supports configurable retry delays and backoff strategies.
    """
    
    def __init__(
        self,
        strategy: str = "stop",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        retry_backoff: float = 2.0,
        retryable_exceptions: Optional[tuple] = None
    ):
        """Initialize ErrorHandler.

        Args:
            strategy: Error handling strategy (string or ErrorStrategy enum).
            max_retries: Maximum number of retry attempts.
            retry_delay: Initial retry delay in seconds.
            retry_backoff: Retry delay backoff multiplier.
            retryable_exceptions: Tuple of exception types that can be retried.
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
        
        # Register serializable fields
        self.add_serializable_fields([
            "strategy", "max_retries", "retry_delay", "retry_backoff", "retry_count"
        ])
    
    def handle_error(
        self,
        error: Exception,
        routine: 'Routine',
        routine_id: str,
        flow: 'Flow',
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle an error according to the configured strategy.

        Args:
            error: Exception object that occurred.
            routine: Routine where the error occurred.
            routine_id: ID of the routine.
            flow: Flow object managing the execution.
            context: Optional context information.

        Returns:
            True if execution should continue, False otherwise.
        """
        context = context or {}
        
        if self.strategy == ErrorStrategy.STOP:
            logger.error(f"Error in routine {routine_id}: {error}. Stopping execution.")
            return False
        
        elif self.strategy == ErrorStrategy.CONTINUE:
            logger.warning(f"Error in routine {routine_id}: {error}. Continuing execution.")
            # Record error but continue execution
            if flow.job_state:
                flow.job_state.record_execution(routine_id, "error_continued", {
                    "error": str(error),
                    "error_type": type(error).__name__
                })
            return True
        
        elif self.strategy == ErrorStrategy.RETRY:
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
                logger.error(
                    f"Error in routine {routine_id}: {error}. "
                    f"Max retries ({self.max_retries}) exceeded. Stopping."
                )
                return False
        
        elif self.strategy == ErrorStrategy.SKIP:
            logger.warning(f"Error in routine {routine_id}: {error}. Skipping routine.")
            # Mark as skipped
            if flow.job_state:
                flow.job_state.update_routine_state(routine_id, {
                    "status": "skipped",
                    "error": str(error)
                })
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
    
    def deserialize(self, data: Dict[str, Any]) -> None:
        """Deserialize the ErrorHandler.

        Args:
            data: Serialized data dictionary.
        """
        # ErrorStrategy needs to be converted from string to enum
        if "strategy" in data and isinstance(data["strategy"], str):
            data["strategy"] = ErrorStrategy(data["strategy"])
        super().deserialize(data)

