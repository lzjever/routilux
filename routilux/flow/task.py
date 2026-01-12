"""
Task-related classes for Flow execution.

Contains TaskPriority enum and SlotActivationTask dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from routilux.connection import Connection
    from routilux.slot import Slot


class TaskPriority(Enum):
    """Task priority for queue scheduling."""

    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class SlotActivationTask:
    """Slot activation task for queue-based execution.

    Each task is associated with a JobState to track execution state.
    This allows tasks executed in worker threads to access and update
    the correct JobState, even when running concurrently.
    """

    slot: Slot
    data: dict[str, Any]
    connection: Connection | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    retry_count: int = 0
    max_retries: int = 0
    created_at: datetime | None = None
    job_state: Any | None = None  # JobState for this execution

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

    def __lt__(self, other):
        """For priority queue sorting."""
        return self.priority.value < other.priority.value
