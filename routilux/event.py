"""
Event class.

Output events for sending data to other routines.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from routilux.job_state import JobState
    from routilux.routine import Routine
    from routilux.runtime import Runtime
    from routilux.slot import Slot

from serilux import Serializable, register_serializable


@register_serializable
class Event(Serializable):
    """Output event for transmitting data to other routines.

    An Event represents an output point in a Routine that can transmit data
    to connected Slots in other routines. Events enable one-to-many data
    distribution: when an event is emitted, all connected slots receive
    the data simultaneously.

    Key Concepts:
        - Events are defined in routines using define_event()
        - Events are emitted using emit() or Routine.emit()
        - Events can connect to multiple slots (broadcast pattern)
        - Slots can connect to multiple events (aggregation pattern)
        - Parameter mapping can transform data during transmission

    Connection Model:
        Events support many-to-many connections:
        - One event can connect to many slots (broadcasting)
        - One slot can connect to many events (aggregation)
        - Connections are managed via Flow.connect()
        - Parameter mappings can rename parameters per connection

    Examples:
        Basic usage:
            >>> class MyRoutine(Routine):
            ...     def __init__(self):
            ...         super().__init__()
            ...         self.output = self.define_event("output", ["result"])
            ...
            ...     def __call__(self):
            ...         self.emit("output", result="success", status=200)

        Multiple connections:
            >>> # One event, multiple receivers
            >>> flow.connect(source_id, "output", target1_id, "input1")
            >>> flow.connect(source_id, "output", target2_id, "input2")
            >>> # Both targets receive data when source emits "output"
    """

    def __init__(
        self,
        name: str = "",
        routine: Routine | None = None,
        output_params: list[str] | None = None,
    ):
        """Initialize an Event.

        Args:
            name: Event name.
            routine: Parent Routine object.
            output_params: List of output parameter names (for documentation).
        """
        super().__init__()
        self.name: str = name
        self.routine: Routine = routine
        self.output_params: list[str] = output_params or []
        self.connected_slots: list[Slot] = []

        # Register serializable fields
        self.add_serializable_fields(["name", "output_params"])

    def serialize(self) -> dict[str, Any]:
        """Serialize the Event.

        Returns:
            Serialized dictionary containing event data.
        """
        # Let base class handle registered fields (name, output_params)
        # Base class is sufficient - no special handling needed
        # Note: _routine_id is NOT serialized here - it's Flow's responsibility
        # Flow will add routine_id when serializing routines
        return super().serialize()

    def deserialize(self, data: dict[str, Any], registry: Any | None = None) -> None:
        """Deserialize the Event.

        Args:
            data: Serialized data dictionary.
            registry: Optional ObjectRegistry for deserializing callables.
        """
        # Let base class handle registered fields (name, output_params)
        # Base class is sufficient - no special handling needed
        super().deserialize(data, registry=registry)

    def __repr__(self) -> str:
        """Return string representation of the Event."""
        if self.routine:
            return f"Event[{self.routine._id}.{self.name}]"
        else:
            return f"Event[{self.name}]"

    def connect(self, slot: Slot) -> None:
        """Connect to a slot.

        Args:
            slot: Slot object to connect to.
        """
        if slot not in self.connected_slots:
            self.connected_slots.append(slot)
            # Bidirectional connection
            if self not in slot.connected_events:
                slot.connected_events.append(self)

    def disconnect(self, slot: Slot) -> None:
        """Disconnect from a slot.

        Args:
            slot: Slot object to disconnect from.
        """
        if slot in self.connected_slots:
            self.connected_slots.remove(slot)
            # Bidirectional disconnection
            if self in slot.connected_events:
                slot.connected_events.remove(self)

    def emit(self, runtime: Runtime, job_state: JobState, **kwargs) -> None:
        """Emit the event and route data through Runtime to connected slots.

        This method packs data with metadata and routes it through Runtime,
        which handles slot enqueueing and routine activation.

        Args:
            runtime: Runtime object for event routing.
            job_state: JobState for this execution.
            ``**kwargs``: Data to transmit. These keyword arguments form the
                data dictionary sent to connected slots.

        Examples:
            Basic emission:
                >>> event.emit(runtime=runtime, job_state=job_state, result="data", status="ok")
        """
        # Pack data with metadata
        # Use routine class name or _id as emitted_from
        emitted_from = "unknown"
        if self.routine:
            emitted_from = self.routine.__class__.__name__ or getattr(self.routine, "_id", "unknown")

        event_data = {
            "data": kwargs,
            "metadata": {
                "emitted_at": datetime.now(),
                "emitted_from": emitted_from,
                "event_name": self.name,
            },
        }

        # Route through Runtime
        runtime.handle_event_emit(self, event_data, job_state)
