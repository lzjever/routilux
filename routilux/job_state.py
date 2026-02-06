"""
JobState and ExecutionRecord classes.

Used for recording flow execution state.
"""

import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from serilux import Serializable, register_serializable

if TYPE_CHECKING:
    from routilux.flow.flow import Flow

logger = logging.getLogger(__name__)


@register_serializable
class ExecutionRecord(Serializable):
    """Execution record for a single routine execution.

    Captures information about when and how a routine was executed,
    including parameters, timestamp, and event information.
    """

    def __init__(
        self,
        routine_id: str = "",
        event_name: str = "",
        data: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ):
        """Initialize ExecutionRecord.

        Args:
            routine_id: Routine identifier.
            event_name: Event name.
            data: Transmitted data.
            timestamp: Timestamp (uses current time if None).
        """
        super().__init__()
        self.routine_id: str = routine_id
        self.event_name: str = event_name
        self.data: Dict[str, Any] = data or {}
        self.timestamp: datetime = timestamp or datetime.now()

        # Register serializable fields
        self.add_serializable_fields(["routine_id", "event_name", "data", "timestamp"])

    def __repr__(self) -> str:
        """Return string representation of the ExecutionRecord."""
        return f"ExecutionRecord[{self.routine_id}.{self.event_name}@{self.timestamp}]"

    def serialize(self) -> Dict[str, Any]:
        """Serialize, handling datetime conversion."""
        data = super().serialize()
        # Convert datetime to string
        if isinstance(data.get("timestamp"), datetime):
            data["timestamp"] = data["timestamp"].isoformat()
        return data

    def deserialize(
        self, data: Dict[str, Any], strict: bool = False, registry: Optional[Any] = None
    ) -> None:
        """Deserialize, handling datetime conversion.

        Args:
            data: Serialized data dictionary.
            strict: Whether to enforce strict deserialization.
            registry: Optional registry for custom deserializers.
        """
        # Convert string to datetime
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        super().deserialize(data, strict=strict, registry=registry)


@register_serializable
class JobState(Serializable):
    """Job state for tracking flow execution.

    JobState maintains comprehensive state information about flow execution,
    including routine states, execution history, pause points, and overall
    execution status. It provides a complete snapshot of workflow execution
    that can be serialized, persisted, and used for resumption.

    Key Responsibilities:
        - Status Tracking: Monitor overall flow execution status
        - Routine States: Track individual routine execution states
        - Execution History: Record all routine executions with timestamps
        - Pause Points: Support execution pausing and resumption
        - State Queries: Provide methods to query execution state

    Status Values:
        - "pending": Flow created but not yet started
        - "running": Flow execution in progress
        - "paused": Flow execution paused (can be resumed)
        - "completed": Flow execution completed successfully
        - "failed": Flow execution failed due to error
        - "cancelled": Flow execution cancelled by user

    Routine State Values:
        - "pending": Routine not yet executed
        - "running": Routine execution in progress
        - "completed": Routine executed successfully
        - "failed": Routine execution failed
        - "error_continued": Routine failed but execution continued (CONTINUE strategy)
        - "skipped": Routine was skipped (SKIP strategy)

    Examples:
        Basic usage:
            >>> job_state = flow.execute(entry_routine_id)
            >>> print(job_state.status)  # "completed" or "failed"
            >>> routine_state = job_state.get_routine_state(routine_id)
            >>> print(routine_state["status"])  # "completed"

        Query execution history:
            >>> history = job_state.get_execution_history()
            >>> for record in history:
            ...     print(f"{record.routine_id} emitted {record.event_name}")

        Check specific routine:
            >>> routine_state = job_state.get_routine_state("my_routine")
            >>> if routine_state and routine_state["status"] == "completed":
            ...     print("Routine completed successfully")
    """

    def __init__(self, flow_id: str = ""):
        """Initialize JobState.

        Args:
            flow_id: Flow identifier.
        """
        super().__init__()
        self.flow_id: str = flow_id
        self.job_id: str = str(uuid.uuid4())
        self.status: str = "pending"  # pending, running, paused, completed, failed, cancelled
        self.pause_points: List[Dict[str, Any]] = []
        self.current_routine_id: Optional[str] = None
        self.routine_states: Dict[str, Dict[str, Any]] = {}
        self.execution_history: List[ExecutionRecord] = []
        self.pending_tasks: List[Dict[str, Any]] = []  # Serialized pending tasks
        self.created_at: datetime = datetime.now()
        self.updated_at: datetime = datetime.now()

        # Deferred events to be emitted on resume
        self.deferred_events: List[Dict[str, Any]] = []

        # History retention policies
        self.max_history_size: Optional[int] = 1000  # Keep last 1000 records
        self.history_ttl_seconds: Optional[int] = 3600  # Remove records older than 1 hour

        # Shared data area for execution-wide data storage
        self.shared_data: Dict[str, Any] = {}
        self.shared_log: List[Dict[str, Any]] = []

        # Output handler for this execution (not serialized)
        self.output_handler: Optional[Any] = None  # OutputHandler, but avoid circular import

        # Output log for persistence (optional)
        self.output_log: List[Dict[str, Any]] = []

        # Register serializable fields
        self.add_serializable_fields(
            [
                "flow_id",
                "job_id",
                "status",
                "current_routine_id",
                "routine_states",
                "execution_history",
                "created_at",
                "updated_at",
                "pause_points",
                "pending_tasks",
                "deferred_events",
                "shared_data",
                "shared_log",
                "output_log",
                "max_history_size",
                "history_ttl_seconds",
            ]
        )

    def __repr__(self) -> str:
        """Return string representation of the JobState."""
        return f"JobState[{self.job_id}:{self.status}]"

    def update_routine_state(self, routine_id: str, state: Dict[str, Any]) -> None:
        """Update state for a specific routine.

        This method updates or sets the execution state for a routine.
        The state dictionary typically contains information like:
        - "status": Execution status ("completed", "failed", etc.)
        - "error": Error message if execution failed
        - "result": Execution result (if any)
        - Custom state information added by routines

        Args:
            routine_id: Unique identifier of the routine in the flow.
                Must match the ID used when adding the routine to the flow.
            state: Dictionary containing routine state information.
                Common keys:
                - "status": str - Execution status
                - "error": str - Error message (if failed)
                - "result": Any - Execution result
                - Custom keys as needed
                The dictionary is copied, so modifications to the original
                won't affect the stored state.

        Side Effects:
            - Updates routine_states[routine_id] with the new state
            - Updates updated_at timestamp

        Examples:
            Update routine status:
                >>> job_state.update_routine_state("my_routine", {
                ...     "status": "completed",
                ...     "result": "success"
                ... })

            Mark routine as failed:
                >>> job_state.update_routine_state("my_routine", {
                ...     "status": "failed",
                ...     "error": "Connection timeout"
                ... })
        """
        self.routine_states[routine_id] = state.copy()
        self.updated_at = datetime.now()

    def get_routine_state(self, routine_id: str) -> Optional[Dict[str, Any]]:
        """Get execution state for a specific routine.

        This method retrieves the current execution state of a routine.
        Returns None if the routine hasn't been executed or doesn't exist.

        Args:
            routine_id: Unique identifier of the routine in the flow.
                Must match the ID used when adding the routine to the flow.

        Returns:
            Dictionary containing routine state information, or None if:
            - Routine hasn't been executed yet
            - Routine ID doesn't exist in the flow
            - State hasn't been set yet

            Common keys in returned dictionary:
            - "status": str - Execution status ("completed", "failed", etc.)
            - "error": str - Error message (if execution failed)
            - "result": Any - Execution result (if any)
            - Custom keys added by routines

        Examples:
            Check if routine completed:
                >>> state = job_state.get_routine_state("my_routine")
                >>> if state and state.get("status") == "completed":
                ...     print("Routine completed successfully")

            Get execution result:
                >>> state = job_state.get_routine_state("processor")
                >>> if state:
                ...     result = state.get("result")
                ...     print(f"Result: {result}")

            Check for errors:
                >>> state = job_state.get_routine_state("validator")
                >>> if state and "error" in state:
                ...     print(f"Error: {state['error']}")
        """
        return self.routine_states.get(routine_id)

    def record_execution(self, routine_id: str, event_name: str, data: Dict[str, Any]) -> None:
        """Record an execution event in the execution history.

        This method creates an ExecutionRecord and adds it to the execution
        history. The history provides a chronological log of all routine
        executions, event emissions, and data transmissions.

        Execution history is useful for:
        - Debugging: Trace data flow through the workflow
        - Monitoring: Track which routines executed and when
        - Analysis: Understand execution patterns and performance
        - Auditing: Maintain a record of all operations

        Args:
            routine_id: Unique identifier of the routine that executed.
                This is the routine that emitted the event or completed execution.
            event_name: Name of the event that was emitted, or action name.
                Common values: event names like "output", "result", or
                special actions like "error_continued", "skipped".
            data: Dictionary of data transmitted or associated with the execution.
                This typically contains the parameters passed to the event,
                or error information for error records.
                Example: {"result": "success", "count": 42}

        Side Effects:
            - Creates a new ExecutionRecord with current timestamp
            - Appends record to execution_history list
            - Updates updated_at timestamp

        Examples:
            Record event emission:
                >>> job_state.record_execution(
                ...     "processor",
                ...     "output",
                ...     {"result": "processed", "count": 10}
                ... )

            Record error continuation:
                >>> job_state.record_execution(
                ...     "optional_routine",
                ...     "error_continued",
                ...     {"error": "Service unavailable", "error_type": "ConnectionError"}
                ... )
        """
        record = ExecutionRecord(routine_id, event_name, data)
        self.execution_history.append(record)
        self.updated_at = datetime.now()

        # Clean up history based on retention policies
        self._cleanup_history()

    def _cleanup_history(self) -> None:
        """Clean up execution history based on retention policies.

        Enforces max_history_size and history_ttl_seconds limits.
        Called automatically by record_execution().

        Note:
            - max_history_size: None = unlimited, 0 = clear all history
            - history_ttl_seconds: None = unlimited, 0 = no time-based cleanup
        """
        now = datetime.now()

        # Apply size limit
        if self.max_history_size is not None and self.max_history_size >= 0:
            excess = len(self.execution_history) - self.max_history_size
            if excess > 0:
                # Remove oldest entries
                self.execution_history = self.execution_history[excess:]

        # Apply time limit
        if self.history_ttl_seconds is not None and self.history_ttl_seconds > 0:
            cutoff_time = now - timedelta(seconds=self.history_ttl_seconds)
            self.execution_history = [
                record for record in self.execution_history if record.timestamp > cutoff_time
            ]

    def get_execution_history(self, routine_id: Optional[str] = None) -> List[ExecutionRecord]:
        """Get execution history, optionally filtered by routine.

        This method returns the execution history, which is a chronological
        list of all routine executions and event emissions. You can filter
        to get history for a specific routine.

        Args:
            routine_id: Optional routine identifier to filter history.
                If provided, returns only ExecutionRecords for this routine.
                If None, returns all execution records.

        Returns:
            List of ExecutionRecord objects, sorted by timestamp (chronological order).
            Each ExecutionRecord contains:
            - routine_id: str - Routine that executed
            - event_name: str - Event emitted or action name
            - data: Dict[str, Any] - Data transmitted
            - timestamp: datetime - When the execution occurred

        Examples:
            Get all execution history:
                >>> history = job_state.get_execution_history()
                >>> for record in history:
                ...     print(f"{record.timestamp}: {record.routine_id} -> {record.event_name}")

            Get history for specific routine:
                >>> processor_history = job_state.get_execution_history("processor")
                >>> for record in processor_history:
                ...     print(f"Event: {record.event_name}, Data: {record.data}")

            Find error records:
                >>> history = job_state.get_execution_history()
                >>> errors = [r for r in history if "error" in r.event_name]
                >>> print(f"Found {len(errors)} error records")
        """
        if routine_id is None:
            history = self.execution_history
        else:
            history = [r for r in self.execution_history if r.routine_id == routine_id]

        # Sort by time
        return sorted(history, key=lambda x: x.timestamp)

    def _set_paused(self, reason: str = "", checkpoint: Optional[Dict[str, Any]] = None) -> None:
        """Internal method: Set paused state (called by Flow).

        Args:
            reason: Reason for pausing.
            checkpoint: Checkpoint data.
        """
        self.status = "paused"
        pause_point = {
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "current_routine_id": self.current_routine_id,
            "checkpoint": checkpoint or {},
        }
        self.pause_points.append(pause_point)
        self.updated_at = datetime.now()

    def _set_running(self) -> None:
        """Internal method: Set running state (called by Flow)."""
        if self.status == "paused":
            self.status = "running"
            self.updated_at = datetime.now()

    def _set_cancelled(self, reason: str = "") -> None:
        """Internal method: Set cancelled state (called by Flow).

        Args:
            reason: Reason for cancellation.
        """
        self.status = "cancelled"
        self.updated_at = datetime.now()
        if reason:
            self.routine_states.setdefault("_cancellation", {})["reason"] = reason

    def save(self, filepath: str) -> None:
        """Persist state to file.

        Args:
            filepath: File path.
        """
        import os

        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)

        data = self.serialize()
        # Handle datetime
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = data["created_at"].isoformat()
        if isinstance(data.get("updated_at"), datetime):
            data["updated_at"] = data["updated_at"].isoformat()

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, filepath: str) -> "JobState":
        """Load state from file.

        Args:
            filepath: File path.

        Returns:
            JobState object.

        Raises:
            FileNotFoundError: If file does not exist.
            ValueError: If file format is incorrect.
        """
        import os

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"JobState file not found: {filepath}")

        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        # Validate data format
        if "_type" not in data or data["_type"] != "JobState":
            raise ValueError(f"Invalid JobState file format: {filepath}")

        # Create object
        job_state = cls(data.get("flow_id", ""))
        job_state.deserialize(data)

        # Handle datetime
        if isinstance(job_state.created_at, str):
            job_state.created_at = datetime.fromisoformat(job_state.created_at)
        if isinstance(job_state.updated_at, str):
            job_state.updated_at = datetime.fromisoformat(job_state.updated_at)

        return job_state

    def serialize(self) -> Dict[str, Any]:
        """Serialize, handling datetime and ExecutionRecord."""
        data = super().serialize()
        # Handle datetime
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = data["created_at"].isoformat()
        if isinstance(data.get("updated_at"), datetime):
            data["updated_at"] = data["updated_at"].isoformat()
        return data

    def deserialize(
        self, data: Dict[str, Any], strict: bool = False, registry: Optional[Any] = None
    ) -> None:
        """Deserialize, handling datetime and ExecutionRecord.

        Args:
            data: Serialized data dictionary.
            strict: Whether to enforce strict deserialization.
            registry: Optional registry for custom deserializers.
        """
        # Handle datetime
        if isinstance(data.get("created_at"), str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if isinstance(data.get("updated_at"), str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        # Handle ExecutionRecord list
        if "execution_history" in data and isinstance(data["execution_history"], list):
            records = []
            for record_data in data["execution_history"]:
                if isinstance(record_data, dict):
                    record = ExecutionRecord(
                        record_data.get("routine_id", ""),
                        record_data.get("event_name", ""),
                        record_data.get("data", {}),
                        (
                            datetime.fromisoformat(record_data["timestamp"])
                            if isinstance(record_data.get("timestamp"), str)
                            else None
                        ),
                    )
                    records.append(record)
            data["execution_history"] = records

        super().deserialize(data, strict=strict, registry=registry)

    def add_deferred_event(self, routine_id: str, event_name: str, data: Dict[str, Any]) -> None:
        """Add a deferred event to be emitted on resume.

        Args:
            routine_id: ID of the routine that will emit the event.
            event_name: Name of the event to emit.
            data: Data to pass to the event.
        """
        self.deferred_events.append(
            {
                "routine_id": routine_id,
                "event_name": event_name,
                "data": data,
                "timestamp": datetime.now().isoformat(),
            }
        )
        self.updated_at = datetime.now()

    def update_shared_data(self, key: str, value: Any) -> None:
        """Update shared data.

        Thread-safe in CPython (GIL protected).

        Args:
            key: Key to update.
            value: Value to set.
        """
        self.shared_data[key] = value
        self.updated_at = datetime.now()

    def get_shared_data(self, key: str, default: Any = None) -> Any:
        """Get shared data.

        Args:
            key: Key to get.
            default: Default value if key doesn't exist.

        Returns:
            Value for key, or default if key doesn't exist.
        """
        return self.shared_data.get(key, default)

    def append_to_shared_log(self, entry: Dict[str, Any]) -> None:
        """Append entry to shared log.

        Thread-safe in CPython (GIL protected).

        Args:
            entry: Dictionary to append to log.
        """
        if not isinstance(entry, dict):
            raise ValueError("Entry must be a dictionary")

        # Automatically add timestamp if not present
        if "timestamp" not in entry:
            entry = entry.copy()
            entry["timestamp"] = datetime.now().isoformat()

        self.shared_log.append(entry)
        self.updated_at = datetime.now()

    def get_shared_log(
        self, filter_func: Optional[Callable[[Dict[str, Any]], bool]] = None
    ) -> List[Dict[str, Any]]:
        """Get shared log, optionally filtered.

        Args:
            filter_func: Optional function to filter entries.
                Should return True to include entry.

        Returns:
            List of log entries.
        """
        if filter_func is None:
            return self.shared_log.copy()
        return [entry for entry in self.shared_log if filter_func(entry)]

    def set_output_handler(self, handler: Any) -> None:
        """Set output handler for this execution.

        Args:
            handler: OutputHandler instance. Use None to disable output.
        """
        self.output_handler = handler

    def send_output(self, routine_id: str, output_type: str, data: Dict[str, Any]) -> None:
        """Send output from routine.

        This method is called by routines to send execution-specific data.
        The output includes execution context (job_id, routine_id, timestamp).

        Args:
            routine_id: ID of the routine generating the output.
            output_type: Type of output (e.g., 'user_data', 'status', 'result').
            data: Output data dictionary (user-defined structure).

        Note:
            This method was renamed from emit_output() to avoid confusion
            with Routine.emit() which emits events to connected slots.
            Use Routine.send_output() for convenient access.
        """
        timestamp = datetime.now()

        # Call output_handler if set
        if self.output_handler:
            try:
                self.output_handler.handle(
                    job_id=self.job_id,
                    routine_id=routine_id,
                    output_type=output_type,
                    data=data,
                    timestamp=timestamp,
                )
            except Exception as e:
                # Ignore output handler failures
                import warnings

                warnings.warn(f"Output handler failed: {e}")

        # Optionally save to output_log for persistence
        self.output_log.append(
            {
                "routine_id": routine_id,
                "output_type": output_type,
                "data": data,
                "timestamp": timestamp.isoformat(),
            }
        )
        self.updated_at = timestamp

    @staticmethod
    def wait_for_completion(
        flow: "Flow",
        job_state: "JobState",
        timeout: Optional[float] = None,
        stability_checks: int = 5,
        check_interval: float = 0.1,
        stability_delay: float = 0.05,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> bool:
        """Wait for flow execution to complete.

        Args:
            flow: Flow object to wait for.
            job_state: JobState object to monitor.
            timeout: Maximum time to wait in seconds. None for no timeout.
            stability_checks: Number of consecutive checks required for stability.
            check_interval: Interval between checks in seconds.
            stability_delay: Delay between stability checks in seconds.
            progress_callback: Optional callback function called periodically with
                (queue_size, active_count, status) tuple.

        Returns:
            True if execution completed before timeout, False if timeout occurred.

        Examples:
            Basic usage:
                >>> job_state = flow.execute(entry_routine_id, entry_params)
                >>> completed = JobState.wait_for_completion(flow, job_state, timeout=300.0)
                >>> if completed:
                ...     print("Execution completed successfully")
        """
        checker = _ExecutionCompletionChecker(
            flow=flow,
            job_state=job_state,
            stability_checks=stability_checks,
            check_interval=check_interval,
            stability_delay=stability_delay,
        )

        start_time = time.time()
        last_progress_time = 0.0
        progress_interval = 5.0

        while True:
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    logger.warning(
                        f"Execution completion wait timed out after {timeout} seconds. "
                        f"Queue size: {flow._task_queue.qsize()}, "
                        f"Active tasks: {len([f for f in flow._active_tasks if not f.done()])}, "
                        f"Status: {job_state.status}"
                    )
                    return False

            if checker.check_with_stability():
                logger.debug("Execution completed successfully")
                if job_state.status == "running":
                    # Before setting to "completed", check if there are any critical failures
                    # in routine states (not just errors in execution history)
                    # We need to distinguish between:
                    # 1. Critical failures: routine status is "failed" or "error" (not "error_continued")
                    # 2. Tolerated errors: routine status is "error_continued" (CONTINUE strategy)
                    # 3. Slot handler errors: only in execution history, routine status not "failed"
                    has_critical_failure = False

                    # Check routine states for critical failure status
                    # Only "failed" or "error" (not "error_continued") indicate critical failures
                    for routine_id, routine_state in job_state.routine_states.items():
                        if isinstance(routine_state, dict):
                            status = routine_state.get("status")
                            # "error_continued" means error was tolerated (CONTINUE strategy)
                            # Only "failed" or "error" indicate critical failures
                            if status in ["failed", "error"]:
                                has_critical_failure = True
                                logger.debug(
                                    f"Critical failure detected in routine state: {routine_id} has status {status}"
                                )
                                break

                    if has_critical_failure:
                        logger.warning(
                            "Execution completed but critical failures detected in routine states. "
                            "Setting status to 'failed' instead of 'completed'."
                        )
                        job_state.status = "failed"
                    else:
                        # No critical failures: errors in execution history are tolerated
                        # (either CONTINUE strategy or slot handler errors that were caught)
                        job_state.status = "completed"
                return True

            if progress_callback is not None:
                current_time = time.time()
                if current_time - last_progress_time >= progress_interval:
                    queue_size = flow._task_queue.qsize()
                    with flow._execution_lock:
                        active_count = len([f for f in flow._active_tasks if not f.done()])
                    progress_callback(queue_size, active_count, job_state.status)
                    last_progress_time = current_time

            time.sleep(check_interval)

    @staticmethod
    def wait_until_condition(
        flow: "Flow",
        job_state: "JobState",
        condition: Callable[["Flow", "JobState"], bool],
        timeout: Optional[float] = None,
        check_interval: float = 0.1,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> bool:
        """Wait until a condition is met.

        This method continuously checks a condition function until it returns True,
        or until a timeout occurs. Useful for waiting for specific states like
        retry count reaching a threshold.

        Args:
            flow: Flow object to monitor.
            job_state: JobState object to monitor.
            condition: Callable that takes (flow, job_state) and returns bool.
                Should return True when the condition is met.
            timeout: Maximum time to wait in seconds. None for no timeout.
            check_interval: Interval between checks in seconds.
            progress_callback: Optional callback function called periodically with
                (queue_size, active_count, status) tuple.

        Returns:
            True if condition was met before timeout, False if timeout occurred.

        Examples:
            Wait until retry count reaches 2:
                >>> def condition(flow, job_state):
                ...     retry_count = flow.get_routine_retry_count("processor")
                ...     return retry_count is not None and retry_count >= 2
                >>> JobState.wait_until_condition(flow, job_state, condition, timeout=30.0)

            Wait until a specific routine completes:
                >>> def condition(flow, job_state):
                ...     state = job_state.get_routine_state("validator")
                ...     return state is not None and state.get("status") == "completed"
                >>> JobState.wait_until_condition(flow, job_state, condition)
        """
        start_time = time.time()
        last_progress_time = 0.0
        progress_interval = 5.0

        while True:
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    logger.warning(
                        f"Condition wait timed out after {timeout} seconds. "
                        f"Status: {job_state.status}"
                    )
                    return False

            # Check if condition is met
            try:
                if condition(flow, job_state):
                    logger.debug("Condition met successfully")
                    return True
            except Exception as e:
                logger.warning(f"Error checking condition: {e}")
                # Continue waiting even if condition check fails

            # Check if execution completed (condition might never be met)
            if job_state.status in ["completed", "failed", "cancelled"]:
                logger.debug(
                    f"Execution completed with status '{job_state.status}' before condition was met"
                )
                # Check condition one more time before returning
                try:
                    if condition(flow, job_state):
                        return True
                except Exception:
                    pass
                return False

            # Call progress callback if provided
            if progress_callback is not None:
                current_time = time.time()
                if current_time - last_progress_time >= progress_interval:
                    try:
                        queue_size = flow._task_queue.qsize()
                    except AttributeError:
                        queue_size = 0
                    try:
                        with flow._execution_lock:
                            active_count = len([f for f in flow._active_tasks if not f.done()])
                    except AttributeError:
                        active_count = 0
                    progress_callback(queue_size, active_count, job_state.status)
                    last_progress_time = current_time

            time.sleep(check_interval)


class _ExecutionCompletionChecker:
    """Execution completion checker (internal)."""

    def __init__(
        self,
        flow: "Flow",
        job_state: "JobState",
        stability_checks: int = 5,
        check_interval: float = 0.1,
        stability_delay: float = 0.05,
    ):
        self.flow = flow
        self.job_state = job_state
        self.stability_checks = stability_checks
        self.check_interval = check_interval
        self.stability_delay = stability_delay

    def is_complete(self) -> bool:
        """Check if execution is complete."""
        if self.job_state.status in ["paused", "cancelled"]:
            return True

        if self.job_state.status == "failed":
            return True

        queue_empty = self.flow._task_queue.empty()
        with self.flow._execution_lock:
            active_tasks = [f for f in self.flow._active_tasks if not f.done()]
            active_count = len(active_tasks)

        if queue_empty and active_count == 0:
            if self.job_state.status in ["completed", "failed", "paused", "cancelled"]:
                return True
            if self.job_state.status == "running":
                return True

        return False

    def check_with_stability(self) -> bool:
        """Check completion with stability verification."""
        for _ in range(self.stability_checks):
            if not self.is_complete():
                return False
            time.sleep(self.stability_delay)

        return True
