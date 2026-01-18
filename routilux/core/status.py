"""
Status enums for Routilux execution and routine states.

Provides type-safe status values instead of magic strings.
"""

from enum import Enum


class ExecutionStatus(str, Enum):
    """Worker execution status.

    These values represent the overall status of a Worker execution.
    Use these enums instead of string literals for type safety and IDE support.

    Examples:
        >>> from routilux.core import ExecutionStatus
        >>> if worker_state.status == ExecutionStatus.COMPLETED:
        ...     print("Worker completed successfully")
    """

    PENDING = "pending"
    RUNNING = "running"
    IDLE = "idle"  # All routines completed, waiting for new jobs
    PAUSED = "paused"
    COMPLETED = "completed"  # User explicitly completed
    FAILED = "failed"
    CANCELLED = "cancelled"


class RoutineStatus(str, Enum):
    """Routine execution status.

    These values represent the status of individual routine execution.
    Use these enums instead of string literals for type safety and IDE support.

    Examples:
        >>> from routilux.core import RoutineStatus
        >>> state = worker_state.get_routine_state("my_routine")
        >>> if state and state["status"] == RoutineStatus.COMPLETED:
        ...     print("Routine completed successfully")
    """

    PENDING = "pending"
    RUNNING = "running"
    IDLE = "idle"  # No pending data, waiting for new data
    COMPLETED = "completed"
    FAILED = "failed"
    ERROR_CONTINUED = "error_continued"
    SKIPPED = "skipped"


class JobStatus(str, Enum):
    """Job (single task) execution status.

    These values represent the status of a single job/task within a worker.

    Examples:
        >>> from routilux.core import JobStatus
        >>> if job.status == JobStatus.COMPLETED:
        ...     print("Job completed successfully")
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
