"""
WorkerState class for tracking long-running worker execution.

A Worker is a long-running execution instance of a Flow.
One Worker can process multiple Jobs.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from serilux import Serializable

if TYPE_CHECKING:
    from routilux.core.flow import Flow

from routilux.core.status import ExecutionStatus

logger = logging.getLogger(__name__)


@dataclass
class ExecutionRecord:
    """Execution record for a single routine execution.

    Captures information about when and how a routine was executed.
    """

    routine_id: str = ""
    event_name: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def __repr__(self) -> str:
        return f"ExecutionRecord[{self.routine_id}.{self.event_name}@{self.timestamp}]"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "routine_id": self.routine_id,
            "event_name": self.event_name,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionRecord:
        """Create from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now()
        return cls(
            routine_id=data.get("routine_id", ""),
            event_name=data.get("event_name", ""),
            data=data.get("data", {}),
            timestamp=timestamp,
        )


# Note: Not using @register_serializable to avoid conflict with legacy module
class WorkerState(Serializable):
    """Worker state for tracking long-running workflow execution.

    A Worker is a long-running execution instance (like a server process).
    One Worker can process multiple Jobs (like HTTP requests).

    Key Responsibilities:
        - Status Tracking: Monitor overall worker execution status
        - Routine States: Track individual routine execution states
        - Execution History: Record all routine executions with timestamps
        - Pause Points: Support execution pausing and resumption
        - Statistics: Track jobs processed/failed counts

    Status Values:
        - "pending": Worker created but not yet started
        - "running": Worker execution in progress
        - "idle": All routines idle, waiting for new jobs
        - "paused": Worker execution paused (can be resumed)
        - "completed": Worker explicitly completed
        - "failed": Worker execution failed
        - "cancelled": Worker execution cancelled

    Note:
        This is a simplified version of the legacy JobState.
        The following have been removed (moved to JobContext):
        - shared_data: Use JobContext.data instead
        - shared_log: Use JobContext.trace_log instead
        - output_handler: Use RoutedStdout instead
        - output_log: Use RoutedStdout instead
        - current_routine_id: Meaningless in concurrent model
        - _activation_policies: Moved to Flow/Routine level

    Examples:
        >>> worker = WorkerState(flow_id="my_flow")
        >>> worker.status = ExecutionStatus.RUNNING
        >>> worker.update_routine_state("processor", {"status": "completed"})
        >>> worker.record_execution("processor", "output", {"result": "success"})
    """

    def __init__(self, flow_id: str = ""):
        """Initialize WorkerState.

        Args:
            flow_id: Flow identifier
        """
        super().__init__()
        self.flow_id: str = flow_id
        self.worker_id: str = str(uuid.uuid4())
        self.status: str | ExecutionStatus = ExecutionStatus.PENDING

        # Worker-level state tracking
        self.routine_states: dict[str, dict[str, Any]] = {}
        self.execution_history: list[ExecutionRecord] = []
        self._max_execution_history: int = 1000

        # Statistics
        self.jobs_processed: int = 0
        self.jobs_failed: int = 0

        # Timestamps
        self.created_at: datetime = datetime.now()
        self.updated_at: datetime = datetime.now()
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None

        # Error information (worker-level fatal errors)
        self.error: str | None = None
        self.error_traceback: str | None = None

        # Pause/resume support
        self.pause_points: list[dict[str, Any]] = []
        self.deferred_events: list[dict[str, Any]] = []
        self.pending_tasks: list[dict[str, Any]] = []

        # Thread-safe locks (not serialized)
        self._routine_states_lock: threading.RLock = threading.RLock()
        self._execution_history_lock: threading.RLock = threading.RLock()
        self._status_lock: threading.RLock = threading.RLock()
        self._pause_points_lock: threading.RLock = threading.RLock()
        self._pending_tasks_lock: threading.RLock = threading.RLock()

        # Runtime references (not serialized)
        self._executor: Any | None = None  # WorkerExecutor
        self._runtime: Any | None = None  # Runtime

        # Register serializable fields
        self.add_serializable_fields(
            [
                "flow_id",
                "worker_id",
                "status",
                "routine_states",
                "execution_history",
                "jobs_processed",
                "jobs_failed",
                "created_at",
                "updated_at",
                "started_at",
                "completed_at",
                "error",
                "error_traceback",
                "pause_points",
                "deferred_events",
                "pending_tasks",
            ]
        )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"WorkerState[{self.worker_id}:{self.status}]"

    @property
    def max_execution_history(self) -> int:
        """Get maximum execution history size."""
        return self._max_execution_history

    @max_execution_history.setter
    def max_execution_history(self, value: int) -> None:
        """Set maximum execution history size."""
        if value < 10:
            raise ValueError(f"max_execution_history must be >= 10, got {value}")
        old_value = self._max_execution_history
        self._max_execution_history = value

        if value < old_value:
            with self._execution_history_lock:
                excess = len(self.execution_history) - value
                if excess > 0:
                    self.execution_history = self.execution_history[excess:]

    def update_routine_state(self, routine_id: str, state: dict[str, Any]) -> None:
        """Update state for a specific routine (thread-safe).

        Args:
            routine_id: Routine identifier
            state: State dictionary
        """
        if not isinstance(state, dict):
            raise TypeError(f"state must be a dict, got {type(state).__name__}")

        with self._routine_states_lock:
            self.routine_states[routine_id] = state.copy()
            self.updated_at = datetime.now()

    def get_routine_state(self, routine_id: str) -> dict[str, Any] | None:
        """Get state for a specific routine (thread-safe).

        Args:
            routine_id: Routine identifier

        Returns:
            State dictionary or None
        """
        with self._routine_states_lock:
            return self.routine_states.get(routine_id)

    def record_execution(self, routine_id: str, event_name: str, data: dict[str, Any]) -> None:
        """Record an execution event (thread-safe).

        Args:
            routine_id: Routine identifier
            event_name: Event name
            data: Event data
        """
        record = ExecutionRecord(routine_id, event_name, data)

        with self._execution_history_lock:
            self.execution_history.append(record)
            if len(self.execution_history) > self._max_execution_history:
                excess = len(self.execution_history) - self._max_execution_history
                del self.execution_history[:excess]
            self.updated_at = datetime.now()

    def get_execution_history(self, routine_id: str | None = None) -> list[ExecutionRecord]:
        """Get execution history (thread-safe).

        Args:
            routine_id: Optional filter by routine

        Returns:
            List of ExecutionRecord
        """
        with self._execution_history_lock:
            if routine_id is None:
                history = self.execution_history.copy()
            else:
                history = [r for r in self.execution_history if r.routine_id == routine_id]

        return sorted(history, key=lambda x: x.timestamp)

    def increment_jobs_processed(self, success: bool = True) -> None:
        """Increment jobs processed count.

        Args:
            success: True if job succeeded, False if failed
        """
        with self._status_lock:
            self.jobs_processed += 1
            if not success:
                self.jobs_failed += 1
            self.updated_at = datetime.now()

    def _set_paused(self, reason: str = "", checkpoint: dict[str, Any] | None = None) -> None:
        """Set paused state (internal).

        Args:
            reason: Reason for pausing
            checkpoint: Checkpoint data
        """
        with self._status_lock:
            self.status = ExecutionStatus.PAUSED

        pause_point = {
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "checkpoint": checkpoint or {},
        }
        with self._pause_points_lock:
            self.pause_points.append(pause_point)
        self.updated_at = datetime.now()

    def _set_running(self) -> None:
        """Set running state (internal)."""
        with self._status_lock:
            if self.status in (ExecutionStatus.PAUSED, "paused"):
                self.status = ExecutionStatus.RUNNING
                self.updated_at = datetime.now()

    def _set_cancelled(self, reason: str = "") -> None:
        """Set cancelled state (internal).

        Args:
            reason: Reason for cancellation
        """
        with self._status_lock:
            self.status = ExecutionStatus.CANCELLED
        self.updated_at = datetime.now()
        if reason:
            with self._routine_states_lock:
                self.routine_states.setdefault("_cancellation", {})["reason"] = reason

    def add_deferred_event(self, routine_id: str, event_name: str, data: dict[str, Any]) -> None:
        """Add a deferred event for resume (thread-safe).

        Args:
            routine_id: Routine identifier
            event_name: Event name
            data: Event data
        """
        with self._pause_points_lock:
            self.deferred_events.append(
                {
                    "routine_id": routine_id,
                    "event_name": event_name,
                    "data": data,
                    "timestamp": datetime.now().isoformat(),
                }
            )
            self.updated_at = datetime.now()

    def save(self, filepath: str) -> None:
        """Save state to file.

        Args:
            filepath: File path
        """
        import os

        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)

        data = self.serialize()
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        except OSError as e:
            logger.error(f"Failed to write worker state to {filepath}: {e}")
            raise

    @classmethod
    def load(cls, filepath: str) -> WorkerState:
        """Load state from file.

        Args:
            filepath: File path

        Returns:
            WorkerState object
        """
        import os

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"WorkerState file not found: {filepath}")

        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to read worker state from {filepath}: {e}")
            raise

        worker_state = cls(data.get("flow_id", ""))
        worker_state.deserialize(data)
        return worker_state

    def serialize(self) -> dict[str, Any]:
        """Serialize WorkerState."""
        data = super().serialize()

        # Handle datetime
        for field in ["created_at", "updated_at", "started_at", "completed_at"]:
            if isinstance(data.get(field), datetime):
                data[field] = data[field].isoformat()

        # Handle ExecutionRecord list
        if "execution_history" in data:
            data["execution_history"] = [
                r.to_dict() if isinstance(r, ExecutionRecord) else r
                for r in data["execution_history"]
            ]

        # Handle status enum
        if isinstance(data.get("status"), ExecutionStatus):
            data["status"] = data["status"].value

        return data

    def deserialize(self, data: dict[str, Any], strict: bool = False, registry: Any = None) -> None:
        """Deserialize WorkerState."""
        # Handle datetime
        for field in ["created_at", "updated_at", "started_at", "completed_at"]:
            if isinstance(data.get(field), str):
                try:
                    data[field] = datetime.fromisoformat(data[field])
                except (ValueError, TypeError):
                    data[field] = datetime.now() if field in ["created_at", "updated_at"] else None

        # Handle ExecutionRecord list
        if "execution_history" in data and isinstance(data["execution_history"], list):
            data["execution_history"] = [
                ExecutionRecord.from_dict(r) if isinstance(r, dict) else r
                for r in data["execution_history"]
            ]

        # Handle status enum
        if isinstance(data.get("status"), str):
            try:
                data["status"] = ExecutionStatus(data["status"])
            except ValueError:
                data["status"] = ExecutionStatus.PENDING

        super().deserialize(data, strict=strict, registry=registry)

    @staticmethod
    def wait_for_completion(
        flow: Flow,
        worker_state: WorkerState,
        timeout: float | None = None,
        check_interval: float = 0.1,
    ) -> bool:
        """Wait for worker execution to complete.

        Args:
            flow: Flow object
            worker_state: WorkerState to monitor
            timeout: Maximum wait time in seconds (None = 1 hour default)
            check_interval: Check interval in seconds

        Returns:
            True if completed, False if timeout
        """
        max_timeout = timeout if timeout is not None else 3600.0
        start_time = time.time()

        while True:
            elapsed = time.time() - start_time
            if elapsed >= max_timeout:
                logger.warning(
                    f"Worker completion wait timed out after {max_timeout}s. "
                    f"Status: {worker_state.status}"
                )
                return False

            # Check if complete
            if worker_state.status in [
                ExecutionStatus.COMPLETED,
                ExecutionStatus.FAILED,
                ExecutionStatus.CANCELLED,
                "completed",
                "failed",
                "cancelled",
            ]:
                return True

            # Check if idle (all work done but not explicitly completed)
            if worker_state.status in [ExecutionStatus.IDLE, "idle"]:
                # Check if executor has no pending work
                executor = getattr(worker_state, "_executor", None)
                if executor is not None:
                    if hasattr(executor, "_is_complete") and executor._is_complete():
                        return True
                else:
                    return True

            time.sleep(check_interval)
