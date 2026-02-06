"""
Connection class.

Represents a connection from an event to a slot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from routilux.event import Event
    from routilux.slot import Slot

from serilux import Serializable, register_serializable


@register_serializable
class Connection(Serializable):
    """Connection object representing a link from an event to a slot.

    A Connection establishes a unidirectional data flow path from a source Event
    to a target Slot. When the source event is emitted, the connection automatically
    transmits the data to the target slot.

    Key Concepts:
        - One-to-One Relationship: Each Connection links exactly one Event to one Slot
        - Automatic Transmission: Data flows automatically when event is emitted
        - Direct Data Pass-through: Data is transmitted without transformation
        - Bidirectional Link: Connection also establishes bidirectional link between
          Event and Slot (Event.connected_slots and Slot.connected_events)

    Data Flow:
        1. Event emits data via ``emit(**kwargs)``
        2. Connection receives data dictionary
        3. Connection calls slot.receive(data)
        4. Slot merges data and calls handler

    Examples:
        Basic connection:
            >>> connection = Connection(source_event, target_slot)
            >>> # Event emits: {"data": "value", "count": 5}
            >>> # Slot receives: {"data": "value", "count": 5}
    """

    def __init__(
        self,
        source_event: Event | None = None,
        target_slot: Slot | None = None,
    ):
        """Initialize a Connection between an event and a slot.

        This constructor creates a connection and automatically establishes the
        bidirectional link between the event and slot. The connection is ready
        to transmit data immediately after creation.

        Args:
            source_event: Source Event object that will emit data.
                Must be an Event instance created via Routine.define_event().
                If None, connection is created but not active until both are set.
            target_slot: Target Slot object that will receive data.
                Must be a Slot instance created via Routine.define_slot().
                If None, connection is created but not active until both are set.

        Side Effects:
            - Automatically calls source_event.connect(target_slot) if both are provided
            - Establishes bidirectional link between event and slot
            - Connection is immediately active and ready to transmit data

        Examples:
            Basic connection:
                >>> event = routine1.define_event("output")
                >>> slot = routine2.define_slot("input")
                >>> connection = Connection(event, slot)
                >>> # Connection is active, data will flow when event emits
        """
        super().__init__()
        self.source_event: Event | None = source_event
        self.target_slot: Slot | None = target_slot

        # Establish connection if both event and slot are provided
        if source_event is not None and target_slot is not None:
            source_event.connect(target_slot)

    def serialize(self) -> dict[str, Any]:
        """Serialize the Connection.

        Returns:
            Serialized dictionary containing connection data.
        """
        # Let base class handle registered fields
        data = super().serialize()

        # Save event and slot names (Connection's responsibility)
        if self.source_event:
            data["_source_event_name"] = self.source_event.name
        if self.target_slot:
            data["_target_slot_name"] = self.target_slot.name

        # Note: routine_id is NOT serialized here - it's Flow's responsibility
        # Flow will add routine_id when serializing connections

        return data

    def deserialize(
        self, data: dict[str, Any], strict: bool = False, registry: Any | None = None
    ) -> None:
        """Deserialize the Connection.

        Args:
            data: Serialized data dictionary.
            strict: Whether to enforce strict deserialization.
            registry: Optional registry for custom deserializers.
        """
        # Save reference information for later restoration by Flow
        source_routine_id = data.pop("_source_routine_id", None)
        source_event_name = data.pop("_source_event_name", None)
        target_routine_id = data.pop("_target_routine_id", None)
        target_slot_name = data.pop("_target_slot_name", None)

        # Let base class handle registered fields
        super().deserialize(data, strict=strict, registry=registry)

        # Save reference information to be restored by Flow.deserialize()
        # (Flow has access to routines dictionary to restore references)
        if source_routine_id:
            self._source_routine_id = source_routine_id
        if source_event_name:
            self._source_event_name = source_event_name
        if target_routine_id:
            self._target_routine_id = target_routine_id
        if target_slot_name:
            self._target_slot_name = target_slot_name

    def __repr__(self) -> str:
        """Return string representation of the Connection."""
        return f"Connection[{self.source_event} -> {self.target_slot}]"

    def activate(self, data: dict[str, Any]) -> None:
        """Activate the connection and transmit data to the target slot.

        This method is called automatically when the source event is emitted.
        It transmits the data directly to the target slot without transformation.
        You typically don't call this directly.

        Processing Steps:
            1. Call target_slot.receive() with the data
            2. Slot merges data and calls its handler

        Args:
            data: Data dictionary from the source event. This is the kwargs
                passed to ``Event.emit(**kwargs)``. The dictionary is sent
                to the slot as-is.
                Example: {"result": "success", "count": 42}

        Examples:
            Manual activation (for testing):
                >>> connection = Connection(event, slot)
                >>> connection.activate({"value": "data", "other": "info"})
                >>> # Slot receives {"value": "data", "other": "info"}

            Automatic activation (normal usage):
                >>> # When event emits, activate() is called automatically
                >>> event.emit(flow=my_flow, result="data", count=5)
                >>> # Connection.activate() is called internally
        """
        # Transmit to target slot
        if self.target_slot is not None:
            self.target_slot.receive(data)

    def disconnect(self) -> None:
        """Disconnect the connection."""
        if self.source_event is not None and self.target_slot is not None:
            self.source_event.disconnect(self.target_slot)
