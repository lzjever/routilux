"""
Context management for Routilux.

Provides JobContext for tracking single job/task execution across routines,
and WorkerState context for thread-local access.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from routilux.core.worker import WorkerState

# Context Variables for thread-safe access
_current_worker_state: ContextVar[Optional["WorkerState"]] = ContextVar(
    "_current_worker_state", default=None
)
_current_job: ContextVar[Optional["JobContext"]] = ContextVar(
    "_current_job", default=None
)


@dataclass
class JobContext:
    """Job-level context for tracking single task execution across routines.

    A Job represents a single task/request that flows through multiple routines.
    Each call to runtime.post() creates a new JobContext.

    Lifecycle:
        - Created when runtime.post() is called
        - Bound to execution context via contextvars
        - Available to all routines processing this job
        - Completed when all related routines finish

    Note:
        - Job is a single task (like an HTTP request)
        - Worker is a long-running execution instance (like a server process)
        - One Worker can process multiple Jobs

    Attributes:
        job_id: Unique identifier for this job
        worker_id: ID of the worker processing this job
        created_at: When the job was created
        completed_at: When the job completed (None if still running)
        metadata: User-defined metadata (user_id, source, etc.)
        data: Job-level data storage (replaces WorkerState.shared_data)
        trace_log: Execution trace for debugging
        status: Current job status
        error: Error message if failed

    Examples:
        >>> from routilux.core import get_current_job
        >>> 
        >>> # Inside a routine's logic
        >>> job = get_current_job()
        >>> if job:
        ...     user_id = job.metadata.get("user_id")
        ...     job.set_data("processed", True)
        ...     job.trace("processor", "completed", {"count": 10})
    """

    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    worker_id: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)
    trace_log: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "pending"  # pending, running, completed, failed
    error: Optional[str] = None

    def trace(
        self, routine_id: str, action: str, details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record a trace entry for this job.

        Args:
            routine_id: ID of the routine performing the action
            action: Action being performed (e.g., "slot_activated", "completed", "error")
            details: Optional additional details
        """
        self.trace_log.append(
            {
                "timestamp": datetime.now().isoformat(),
                "routine_id": routine_id,
                "action": action,
                "details": details or {},
            }
        )

    def set_data(self, key: str, value: Any) -> None:
        """Set job-level data.

        This replaces WorkerState.shared_data for job-scoped data sharing.

        Args:
            key: Data key
            value: Data value
        """
        self.data[key] = value

    def get_data(self, key: str, default: Any = None) -> Any:
        """Get job-level data.

        Args:
            key: Data key
            default: Default value if key not found

        Returns:
            Value for key, or default
        """
        return self.data.get(key, default)

    def start(self) -> None:
        """Mark job as running."""
        self.status = "running"

    def complete(self, status: str = "completed", error: Optional[str] = None) -> None:
        """Mark job as completed.

        Args:
            status: Final status ("completed" or "failed")
            error: Error message if failed
        """
        self.status = status
        self.error = error
        self.completed_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization/API response.

        Returns:
            Dictionary representation
        """
        return {
            "job_id": self.job_id,
            "worker_id": self.worker_id,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
            "data": self.data,
            "trace_log": self.trace_log,
            "status": self.status,
            "error": self.error,
        }


def get_current_job() -> Optional[JobContext]:
    """Get the current job context.

    Returns:
        Current JobContext if set, None otherwise

    Examples:
        >>> from routilux.core import get_current_job
        >>> job = get_current_job()
        >>> if job:
        ...     print(f"Processing job {job.job_id}")
    """
    return _current_job.get(None)


def get_current_job_id() -> Optional[str]:
    """Get the current job ID (convenience function).

    Returns:
        Current job ID if set, None otherwise

    Examples:
        >>> from routilux.core import get_current_job_id
        >>> job_id = get_current_job_id()
        >>> if job_id:
        ...     print(f"Job ID: {job_id}")
    """
    job = _current_job.get(None)
    return job.job_id if job else None


def get_current_worker_state() -> Optional["WorkerState"]:
    """Get the current worker state.

    Returns:
        Current WorkerState if set, None otherwise

    Examples:
        >>> from routilux.core import get_current_worker_state
        >>> worker = get_current_worker_state()
        >>> if worker:
        ...     print(f"Worker {worker.worker_id}, status: {worker.status}")
    """
    return _current_worker_state.get(None)


def set_current_job(job: Optional[JobContext]) -> None:
    """Set the current job context (internal use).

    Args:
        job: JobContext to set, or None to clear
    """
    _current_job.set(job)


def set_current_worker_state(worker: Optional["WorkerState"]) -> None:
    """Set the current worker state (internal use).

    Args:
        worker: WorkerState to set, or None to clear
    """
    _current_worker_state.set(worker)
