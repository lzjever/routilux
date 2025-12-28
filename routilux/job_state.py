"""
JobState and ExecutionRecord classes.

Used for recording flow execution state.
"""

import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from serilux import register_serializable, Serializable
import json


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

    def deserialize(self, data: Dict[str, Any]) -> None:
        """Deserialize, handling datetime conversion."""
        # Convert string to datetime
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        super().deserialize(data)


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
        self.created_at: datetime = datetime.now()
        self.updated_at: datetime = datetime.now()

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

        with open(filepath, "r", encoding="utf-8") as f:
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

    def deserialize(self, data: Dict[str, Any]) -> None:
        """Deserialize, handling datetime and ExecutionRecord."""
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

        super().deserialize(data)
