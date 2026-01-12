"""
Output handler for routine outputs.

Provides unified output mechanism for execution-specific data streaming.
Output handlers are bound to JobState (execution), not Flow.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional


class OutputHandler(ABC):
    """Base class for output handlers.

    Output handlers receive execution-specific data with context information.
    Each execution (JobState) can have its own output handler.
    """

    @abstractmethod
    def handle(
        self,
        job_id: str,
        routine_id: str,
        output_type: str,
        data: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Handle output from routine during execution.

        Args:
            job_id: ID of the execution (JobState.job_id).
            routine_id: ID of the routine that generated the output.
            output_type: Type of output (e.g., 'user_data', 'status', 'result').
            data: Output data dictionary (user-defined structure).
            timestamp: Timestamp of the output (defaults to now).
        """
        pass


class QueueOutputHandler(OutputHandler):
    """Output handler that puts output into a queue.

    This is the most common handler for service integration.
    Business code can read from the queue and process outputs.
    """

    def __init__(self, queue):
        """Initialize queue output handler.

        Args:
            queue: Queue object (e.g., queue.Queue, multiprocessing.Queue).
        """
        self.queue = queue

    def handle(
        self,
        job_id: str,
        routine_id: str,
        output_type: str,
        data: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Put output into queue."""
        entry = {
            "job_id": job_id,
            "routine_id": routine_id,
            "output_type": output_type,
            "data": data,
            "timestamp": (timestamp or datetime.now()).isoformat(),
        }
        self.queue.put(entry)


class CallbackOutputHandler(OutputHandler):
    """Output handler that calls a callback function.

    Useful for simple integrations or testing.
    """

    def __init__(self, callback):
        """Initialize callback output handler.

        Args:
            callback: Function that takes (job_id, routine_id, output_type, data, timestamp).
        """
        self.callback = callback

    def handle(
        self,
        job_id: str,
        routine_id: str,
        output_type: str,
        data: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Call callback function."""
        self.callback(job_id, routine_id, output_type, data, timestamp or datetime.now())


class NullOutputHandler(OutputHandler):
    """Output handler that does nothing (for testing or when output is disabled)."""

    def handle(
        self,
        job_id: str,
        routine_id: str,
        output_type: str,
        data: Dict[str, Any],
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Do nothing."""
        pass
