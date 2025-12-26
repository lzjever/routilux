"""
JobState and ExecutionRecord classes.

Used for recording flow execution state.
"""
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from flowforge.utils.serializable import register_serializable, Serializable
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
        timestamp: Optional[datetime] = None
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
    
    Maintains comprehensive state information about flow execution including
    routine states, execution history, pause points, and status tracking.
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
        self.add_serializable_fields([
            "flow_id", "job_id", "status", "current_routine_id",
            "routine_states", "execution_history", "created_at", "updated_at", "pause_points"
        ])
    
    def __repr__(self) -> str:
        """Return string representation of the JobState."""
        return f"JobState[{self.job_id}:{self.status}]"
    
    def update_routine_state(self, routine_id: str, state: Dict[str, Any]) -> None:
        """Update state for a routine.

        Args:
            routine_id: Routine identifier.
            state: State dictionary.
        """
        self.routine_states[routine_id] = state.copy()
        self.updated_at = datetime.now()
    
    def get_routine_state(self, routine_id: str) -> Optional[Dict[str, Any]]:
        """Get state for a routine.

        Args:
            routine_id: Routine identifier.

        Returns:
            State dictionary if found, None otherwise.
        """
        return self.routine_states.get(routine_id)
    
    def record_execution(
        self,
        routine_id: str,
        event_name: str,
        data: Dict[str, Any]
    ) -> None:
        """Record execution history.

        Args:
            routine_id: Routine identifier.
            event_name: Event name.
            data: Transmitted data.
        """
        record = ExecutionRecord(routine_id, event_name, data)
        self.execution_history.append(record)
        self.updated_at = datetime.now()
    
    def get_execution_history(
        self,
        routine_id: Optional[str] = None
    ) -> List[ExecutionRecord]:
        """Get execution history.

        Args:
            routine_id: If specified, only return history for this routine.

        Returns:
            List of execution records sorted by time.
        """
        if routine_id is None:
            history = self.execution_history
        else:
            history = [
                r for r in self.execution_history
                if r.routine_id == routine_id
            ]
        
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
            "checkpoint": checkpoint or {}
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
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, filepath: str) -> 'JobState':
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
        
        with open(filepath, 'r', encoding='utf-8') as f:
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
                        datetime.fromisoformat(record_data["timestamp"]) if isinstance(record_data.get("timestamp"), str) else None
                    )
                    records.append(record)
            data["execution_history"] = records
        
        super().deserialize(data)

