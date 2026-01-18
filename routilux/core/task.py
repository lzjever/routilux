"""
Task-related classes for workflow execution.

Contains TaskPriority enum, SlotActivationTask and EventRoutingTask dataclasses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from routilux.core.connection import Connection
    from routilux.core.context import JobContext
    from routilux.core.event import Event
    from routilux.core.runtime import Runtime
    from routilux.core.slot import Slot
    from routilux.core.worker import WorkerState


class TaskPriority(Enum):
    """Task priority for queue scheduling."""

    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class SlotActivationTask:
    """Slot activation task for queue-based execution.

    Each task is associated with a WorkerState and optionally a JobContext
    to track execution state. This allows tasks executed in worker threads
    to access and update the correct state, even when running concurrently.

    Attributes:
        slot: Target slot to activate
        data: Data to pass to the slot
        worker_state: WorkerState for this execution
        job_context: Optional JobContext for tracking this specific job
        connection: Source connection (None for external events)
        priority: Task priority
        retry_count: Current retry count
        max_retries: Maximum retries allowed
        created_at: When the task was created
    """

    slot: "Slot"
    data: dict[str, Any]
    worker_state: Optional["WorkerState"] = None
    job_context: Optional["JobContext"] = None
    connection: Optional["Connection"] = None
    priority: TaskPriority = TaskPriority.NORMAL
    retry_count: int = 0
    max_retries: int = 0
    created_at: Optional[datetime] = field(default=None)

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

    def __lt__(self, other):
        """For priority queue sorting."""
        if not isinstance(other, SlotActivationTask):
            return NotImplemented
        return self.priority.value < other.priority.value


@dataclass
class EventRoutingTask:
    """Event routing task for queue-based message routing.

    This task is used to route events to connected slots in the event loop thread,
    ensuring that all message routing happens in a single dedicated thread per worker.

    Attributes:
        event: Event being routed
        event_data: Event data with metadata
        worker_state: WorkerState for this execution
        runtime: Runtime for routing
        job_context: Optional JobContext for tracking this specific job
        priority: Task priority
        created_at: When the task was created
    """

    event: "Event"
    event_data: dict[str, Any]
    worker_state: "WorkerState"
    runtime: "Runtime"
    job_context: Optional["JobContext"] = None
    priority: TaskPriority = TaskPriority.NORMAL
    created_at: Optional[datetime] = field(default=None)

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

    def __lt__(self, other):
        """For priority queue sorting."""
        if not isinstance(other, EventRoutingTask):
            return NotImplemented
        return self.priority.value < other.priority.value
