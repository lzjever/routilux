"""
Flow class for Routilux core.

Flow manager responsible for managing multiple Routine nodes and execution flow.
"""

from __future__ import annotations

import threading
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Type

from serilux import Serializable

if TYPE_CHECKING:
    from routilux.core.connection import Connection
    from routilux.core.error import ErrorHandler
    from routilux.core.event import Event
    from routilux.core.routine import Routine
    from routilux.core.slot import Slot
    from routilux.core.worker import WorkerState


class WorkerNotRunningError(ValueError):
    """Raised when resume is called but the worker has no active WorkerExecutor."""


# Note: Not using @register_serializable to avoid conflict with legacy module
class Flow(Serializable):
    """Flow manager for orchestrating workflow execution.

    A Flow is a container that manages multiple Routine nodes and their
    connections, providing workflow orchestration capabilities.

    Key Responsibilities:
        - Routine Management: Add, organize, and track routines
        - Connection Management: Link routines via events and slots
        - Execution Control: Execute workflows via Runtime
        - Error Handling: Apply error handling strategies

    Examples:
        >>> flow = Flow()
        >>> routine1 = DataProcessor()
        >>> routine2 = DataValidator()
        >>> flow.add_routine(routine1, "processor")
        >>> flow.add_routine(routine2, "validator")
        >>> flow.connect("processor", "output", "validator", "input")
    """

    def __init__(
        self,
        flow_id: Optional[str] = None,
        execution_timeout: Optional[float] = None,
    ):
        """Initialize Flow.

        Args:
            flow_id: Flow identifier (auto-generated if None)
            execution_timeout: Default timeout for execution (seconds)
        """
        super().__init__()
        self.flow_id: str = flow_id or str(uuid.uuid4())
        self.routines: Dict[str, "Routine"] = {}
        self.connections: List["Connection"] = []
        self.error_handler: Optional["ErrorHandler"] = None

        # Thread safety lock for configuration operations
        self._config_lock: threading.RLock = threading.RLock()

        # Validate execution_timeout
        if execution_timeout is not None:
            if not isinstance(execution_timeout, (int, float)):
                raise TypeError(
                    f"execution_timeout must be numeric, got {type(execution_timeout).__name__}"
                )
            if execution_timeout <= 0:
                raise ValueError(f"execution_timeout must be positive, got {execution_timeout}")
        self.execution_timeout: float = (
            execution_timeout if execution_timeout is not None else 300.0
        )

        # Internal lookup cache
        self._event_slot_connections: Dict[Tuple["Event", "Slot"], "Connection"] = {}

        # Auto-register with global registry
        try:
            from routilux.core.registry import FlowRegistry

            registry = FlowRegistry.get_instance()
            registry.register(self)
        except ImportError:
            pass

        self.add_serializable_fields(
            [
                "flow_id",
                "error_handler",
                "routines",
                "connections",
            ]
        )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"Flow[{self.flow_id}]"

    def _get_routine_id(self, routine: "Routine") -> Optional[str]:
        """Find the ID of a Routine object within this Flow.

        Args:
            routine: Routine object

        Returns:
            Routine ID if found, None otherwise
        """
        for rid, r in self.routines.items():
            if r is routine:
                return rid
        return None

    def add_routine(
        self, routine: "Routine", routine_id: Optional[str] = None
    ) -> str:
        """Add a routine to the flow.

        Args:
            routine: Routine instance to add
            routine_id: Optional unique identifier

        Returns:
            The routine ID used

        Raises:
            ValueError: If routine_id already exists
        """
        with self._config_lock:
            rid = routine_id or (
                getattr(routine, "_id", None) if routine else None
            )
            if rid is None:
                raise ValueError(
                    "routine_id must be provided or routine must have _id attribute"
                )
            if rid in self.routines:
                raise ValueError(f"Routine ID '{rid}' already exists in flow")

            self.routines[rid] = routine
            return rid

    def connect(
        self,
        source_routine_id: str,
        source_event: str,
        target_routine_id: str,
        target_slot: str,
    ) -> "Connection":
        """Connect two routines by linking a source event to a target slot.

        Args:
            source_routine_id: Routine that emits the event
            source_event: Event name
            target_routine_id: Routine that receives the data
            target_slot: Slot name

        Returns:
            Connection object

        Raises:
            ValueError: If any component doesn't exist
        """
        with self._config_lock:
            if source_routine_id not in self.routines:
                raise ValueError(
                    f"Source routine '{source_routine_id}' not found in flow"
                )

            source_routine = self.routines[source_routine_id]
            source_event_obj = source_routine.get_event(source_event)
            if source_event_obj is None:
                raise ValueError(
                    f"Event '{source_event}' not found in routine '{source_routine_id}'"
                )

            if target_routine_id not in self.routines:
                raise ValueError(
                    f"Target routine '{target_routine_id}' not found in flow"
                )

            target_routine = self.routines[target_routine_id]
            target_slot_obj = target_routine.get_slot(target_slot)
            if target_slot_obj is None:
                raise ValueError(
                    f"Slot '{target_slot}' not found in routine '{target_routine_id}'"
                )

            from routilux.core.connection import Connection

            connection = Connection(source_event_obj, target_slot_obj)
            self.connections.append(connection)

            key = (source_event_obj, target_slot_obj)
            self._event_slot_connections[key] = connection

            return connection

    def get_connections_for_event(self, event: "Event") -> List["Connection"]:
        """Get all connections for a specific event.

        Args:
            event: Event object

        Returns:
            List of Connection objects
        """
        with self._config_lock:
            return [conn for conn in self.connections if conn.source_event == event]

    def _find_connection(
        self, event: "Event", slot: "Slot"
    ) -> Optional["Connection"]:
        """Find Connection from event to slot.

        Args:
            event: Event object
            slot: Slot object

        Returns:
            Connection object if found, None otherwise
        """
        key = (event, slot)
        return self._event_slot_connections.get(key)

    def set_error_handler(self, error_handler: "ErrorHandler") -> None:
        """Set error handler for the flow.

        Args:
            error_handler: ErrorHandler object
        """
        self.error_handler = error_handler

    def get_error_handler(self) -> Optional["ErrorHandler"]:
        """Get error handler for the flow."""
        return self.error_handler

    def find_routines_by_type(
        self, routine_type: Type["Routine"]
    ) -> List[Tuple[str, "Routine"]]:
        """Find routines by type.

        Args:
            routine_type: Type of routine to find

        Returns:
            List of (routine_id, routine) tuples
        """
        return [
            (rid, routine)
            for rid, routine in self.routines.items()
            if isinstance(routine, routine_type)
        ]

    def _get_error_handler_for_routine(
        self, routine: "Routine", routine_id: str
    ) -> Optional["ErrorHandler"]:
        """Get error handler for a routine.

        Priority: routine-level > flow-level

        Args:
            routine: Routine object
            routine_id: Routine ID

        Returns:
            ErrorHandler or None
        """
        # Routine-level first
        routine_handler = routine.get_error_handler()
        if routine_handler is not None:
            return routine_handler

        # Flow-level fallback
        return self.error_handler

    def validate(self) -> List[str]:
        """Validate flow structure and return list of issues.

        Returns:
            List of validation messages (empty = valid)
        """
        issues = []

        # Check for routines without connections
        for rid, routine in self.routines.items():
            has_incoming = False
            has_outgoing = False

            for conn in self.connections:
                if conn.target_slot and conn.target_slot.routine is routine:
                    has_incoming = True
                if conn.source_event and conn.source_event.routine is routine:
                    has_outgoing = True

            if not has_incoming and len(routine.slots) > 0:
                issues.append(f"Warning: Routine '{rid}' has slots but no incoming connections")
            if not has_outgoing and len(routine.events) > 0:
                issues.append(f"Warning: Routine '{rid}' has events but no outgoing connections")

        # Check for invalid connections
        for conn in self.connections:
            if conn.source_event is None:
                issues.append("Error: Connection has no source event")
            if conn.target_slot is None:
                issues.append("Error: Connection has no target slot")

        return issues

    def serialize(self) -> Dict[str, Any]:
        """Serialize Flow."""
        data = super().serialize()

        # Serialize routines
        if "routines" in data:
            data["routines"] = {
                rid: routine.serialize() for rid, routine in self.routines.items()
            }

        # Serialize connections
        if "connections" in data:
            serialized_connections = []
            for conn in self.connections:
                conn_data = conn.serialize() if hasattr(conn, "serialize") else {}

                # Add routine IDs for reconstruction
                if conn.source_event and conn.source_event.routine:
                    conn_data["_source_routine_id"] = self._get_routine_id(
                        conn.source_event.routine
                    )
                if conn.target_slot and conn.target_slot.routine:
                    conn_data["_target_routine_id"] = self._get_routine_id(
                        conn.target_slot.routine
                    )

                serialized_connections.append(conn_data)
            data["connections"] = serialized_connections

        return data

    def deserialize(
        self, data: Dict[str, Any], strict: bool = False, registry: Any = None
    ) -> None:
        """Deserialize Flow."""
        from routilux.core.connection import Connection
        from routilux.core.routine import Routine

        # Deserialize routines first
        routines_data = data.pop("routines", {})
        connections_data = data.pop("connections", [])

        super().deserialize(data, strict=strict, registry=registry)

        # Restore routines
        for rid, routine_data in routines_data.items():
            if isinstance(routine_data, dict):
                # Create routine from data
                routine = Routine()
                routine.deserialize(routine_data, strict=strict, registry=registry)
                self.routines[rid] = routine

        # Restore connections
        for conn_data in connections_data:
            source_routine_id = conn_data.get("_source_routine_id")
            source_event_name = conn_data.get("_source_event_name")
            target_routine_id = conn_data.get("_target_routine_id")
            target_slot_name = conn_data.get("_target_slot_name")

            if (
                source_routine_id
                and source_event_name
                and target_routine_id
                and target_slot_name
            ):
                source_routine = self.routines.get(source_routine_id)
                target_routine = self.routines.get(target_routine_id)

                if source_routine and target_routine:
                    source_event = source_routine.get_event(source_event_name)
                    target_slot = target_routine.get_slot(target_slot_name)

                    if source_event and target_slot:
                        connection = Connection(source_event, target_slot)
                        self.connections.append(connection)
                        self._event_slot_connections[(source_event, target_slot)] = connection

    @classmethod
    def from_dict(cls, spec: Dict[str, Any]) -> "Flow":
        """Create Flow from specification dictionary.

        This method allows creating flows from dictionaries.
        Routines must be registered in ObjectFactory before use.

        Args:
            spec: Flow specification dictionary

        Returns:
            Constructed Flow object
        """
        # Import ObjectFactory for DSL loading
        try:
            from routilux.tools.factory.factory import ObjectFactory

            factory = ObjectFactory.get_instance()
            return factory.load_flow_from_dsl(spec)
        except ImportError:
            # Fallback: manual construction
            flow = cls(
                flow_id=spec.get("flow_id"),
                execution_timeout=spec.get("execution_timeout"),
            )
            # Note: Without factory, only basic flow structure can be created
            return flow

    @classmethod
    def from_yaml(cls, yaml_str: str) -> "Flow":
        """Create Flow from YAML string.

        Args:
            yaml_str: YAML string containing flow specification

        Returns:
            Constructed Flow object
        """
        try:
            import yaml
        except ImportError as e:
            raise ImportError(
                "YAML support requires 'pyyaml' package. Install with: pip install pyyaml"
            ) from e

        try:
            spec = yaml.safe_load(yaml_str)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML: {e}") from e

        if spec is None:
            raise ValueError("YAML string is empty or invalid")

        return cls.from_dict(spec)


class RoutineConfig:
    """Helper class for routine configuration chaining."""

    def __init__(self, routine: "Routine"):
        """Initialize RoutineConfig.

        Args:
            routine: Routine to configure
        """
        self._routine = routine

    def config(self, key: str, value: Any) -> "RoutineConfig":
        """Set a configuration value.

        Args:
            key: Config key
            value: Config value

        Returns:
            Self for chaining
        """
        self._routine.set_config(**{key: value})
        return self

    def error_handler(self, handler: "ErrorHandler") -> "RoutineConfig":
        """Set error handler.

        Args:
            handler: ErrorHandler to set

        Returns:
            Self for chaining
        """
        self._routine.set_error_handler(handler)
        return self
