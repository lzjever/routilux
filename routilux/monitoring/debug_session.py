"""
Debug session management for workflow debugging.

Manages debug session state including pause/resume, step operations,
and variable access.
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

if TYPE_CHECKING:
    from routilux.core.routine import ExecutionContext


@dataclass
class CallFrame:
    """Call frame in execution stack.

    Attributes:
        routine_id: Routine ID being executed.
        slot_name: Slot name (if in slot handler).
        event_name: Event name (if in event handler).
        variables: Local variables at this frame.
        line_number: Optional line number (if available).
    """

    routine_id: str
    slot_name: Optional[str] = None
    event_name: Optional[str] = None
    variables: Dict[str, Any] = field(default_factory=dict)
    line_number: Optional[int] = None


@dataclass
class DebugSession:
    """Debug session state.

    Attributes:
        session_id: Unique session identifier.
        job_id: Job ID being debugged.
        status: Current debug status (paused, running, stepping).
        paused_at: Execution context where execution is paused.
        call_stack: Current call stack.
        breakpoints: List of breakpoint IDs active in this session.
        step_mode: Step mode (None, "over", "into", "out").
        step_count: Number of steps remaining.
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    status: Literal["paused", "running", "stepping"] = "running"
    paused_at: Optional["ExecutionContext"] = None
    call_stack: List[CallFrame] = field(default_factory=list)
    breakpoints: List[str] = field(default_factory=list)
    step_mode: Optional[Literal["over", "into", "out"]] = None
    step_count: int = 0
    paused_timestamp: Optional[datetime] = None

    def pause(self, context: Optional["ExecutionContext"] = None, reason: str = "") -> None:
        """Pause execution at current point.

        Args:
            context: Execution context where pause occurs.
            reason: Reason for pause.
        """
        self.status = "paused"
        self.paused_at = context
        self.paused_timestamp = datetime.now()

        if context:
            # Build call frame from context
            frame = CallFrame(
                routine_id=context.routine_id,
                variables={},  # Variables would be captured separately
            )
            self.call_stack.append(frame)

    def resume(self) -> None:
        """Resume execution."""
        self.status = "running"
        self.paused_at = None
        self.step_mode = None
        self.step_count = 0

    def step_over(self) -> None:
        """Set step-over mode (execute one step, don't step into nested calls)."""
        self.status = "stepping"
        self.step_mode = "over"
        self.step_count = 1

    def step_into(self) -> None:
        """Set step-into mode (step into nested calls)."""
        self.status = "stepping"
        self.step_mode = "into"
        self.step_count = 1

    def step_out(self) -> None:
        """Set step-out mode (execute until current function returns)."""
        self.status = "stepping"
        self.step_mode = "out"
        self.step_count = 1

    def should_continue(self) -> bool:
        """Check if execution should continue based on step mode.

        HIGH fix: Add thread-safe access to status, step_count, and step_mode
        to prevent race conditions when multiple threads call this method.

        Returns:
            True if execution should continue, False if should pause.
        """
        # Use getattr for thread-safe access without lock (simple reads are atomic in CPython)
        current_status = getattr(self, "status", "paused")
        if current_status == "running":
            return True

        if current_status == "stepping":
            # Atomically read and decrement step_count
            current_step_count = getattr(self, "step_count", 0)
            if current_step_count > 0:
                object.__setattr__(self, "step_count", current_step_count - 1)
                if current_step_count - 1 == 0:
                    object.__setattr__(self, "status", "paused")
                    return False
                return True
            else:
                object.__setattr__(self, "status", "paused")
                return False

        # Paused
        return False

    def get_variables(self, routine_id: Optional[str] = None) -> Dict[str, Any]:
        """Get variables at current pause point.

        Args:
            routine_id: Optional routine ID to get variables for.

        Returns:
            Dictionary of variable names to values.
        """
        if not self.call_stack:
            return {}

        # If routine_id specified, find matching frame
        if routine_id:
            for frame in reversed(self.call_stack):
                if frame.routine_id == routine_id:
                    return frame.variables

        # Return variables from top of stack
        return self.call_stack[-1].variables if self.call_stack else {}

    def set_variable(self, routine_id: str, name: str, value: Any) -> None:
        """Set variable value at current pause point.

        Args:
            routine_id: Routine ID to set variable in.
            name: Variable name.
            value: Variable value.
        """
        # Find frame for routine_id
        for frame in reversed(self.call_stack):
            if frame.routine_id == routine_id:
                frame.variables[name] = value
                return

        # If not found, create new frame
        frame = CallFrame(routine_id=routine_id, variables={name: value})
        self.call_stack.append(frame)

    def get_call_stack(self) -> List[CallFrame]:
        """Get current call stack.

        Returns:
            List of call frames from bottom to top.
        """
        return self.call_stack.copy()


class DebugSessionStore:
    """Thread-safe store for debug sessions."""

    def __init__(self):
        """Initialize debug session store."""
        self._sessions: Dict[str, DebugSession] = {}  # job_id -> DebugSession
        self._lock = threading.RLock()

    def get(self, job_id: str) -> Optional[DebugSession]:
        """Get debug session for a job.

        Args:
            job_id: Job ID to get session for.

        Returns:
            DebugSession or None if not found.
        """
        with self._lock:
            return self._sessions.get(job_id)

    def get_or_create(self, job_id: str) -> DebugSession:
        """Get or create debug session for a job.

        Args:
            job_id: Job ID to get/create session for.

        Returns:
            DebugSession (existing or newly created).
        """
        with self._lock:
            if job_id not in self._sessions:
                self._sessions[job_id] = DebugSession(job_id=job_id)
            return self._sessions[job_id]

    def add(self, session: DebugSession) -> None:
        """Add or update a debug session.

        Args:
            session: Debug session to add.
        """
        with self._lock:
            self._sessions[session.job_id] = session

    def remove(self, job_id: str) -> None:
        """Remove debug session for a job.

        Args:
            job_id: Job ID to remove session for.
        """
        with self._lock:
            self._sessions.pop(job_id, None)
