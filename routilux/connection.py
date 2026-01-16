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
    to a target Slot. When the source event is emitted, Runtime routes the data
    to the target slot's queue.

    Key Concepts:
        - One-to-One Relationship: Each Connection links exactly one Event to one Slot
        - Automatic Routing: Data flows automatically when event is emitted
        - Bidirectional Link: Connection also establishes bidirectional link between
          Event and Slot (Event.connected_slots and Slot.connected_events)

    Data Flow:
        1. Event emits data via ``emit(runtime, job_state, **kwargs)``
        2. Runtime routes event to connected slots
        3. Data is enqueued in slot's queue
        4. Activation policy consumes data when conditions are met

    Examples:
        Basic connection:
            >>> connection = Connection(source_event, target_slot)
            >>> # Event emits: {"data": "value", "count": 5}
            >>> # Slot queue receives: {"data": "value", "count": 5}
    """

    def __init__(
        self,
        source_event: Event | None = None,
        target_slot: Slot | None = None,
        param_mapping: dict[str, str] | None = None,
    ):
        """Initialize a Connection between an event and a slot.

        This constructor creates a connection and automatically establishes the
        bidirectional link between the event and slot. The connection is ready
        to route data immediately after creation.

        Args:
            source_event: Source Event object that will emit data.
                Must be an Event instance created via Routine.define_event().
                If None, connection is created but not active until both are set.
            target_slot: Target Slot object that will receive data.
                Must be a Slot instance created via Routine.define_slot().
                If None, connection is created but not active until both are set.
            param_mapping: Optional mapping from source parameter names to target
                parameter names. Allows renaming/mapping parameters during data transfer.

        Side Effects:
            - Automatically calls source_event.connect(target_slot) if both are provided
            - Establishes bidirectional link between event and slot
            - Connection is immediately active and ready to route data

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
        self.param_mapping: dict[str, str] | None = param_mapping

        # Establish connection if both event and slot are provided
        if source_event is not None and target_slot is not None:
            source_event.connect(target_slot)

        # Register serializable fields
        self.add_serializable_fields([])

    def serialize(self) -> dict[str, Any]:
        """Serialize the Connection.

        Returns:
            Serialized dictionary containing connection data.
        """
        data = super().serialize()

        # Save event and slot names (Connection's responsibility)
        if self.source_event:
            data["_source_event_name"] = self.source_event.name
        if self.target_slot:
            data["_target_slot_name"] = self.target_slot.name

        # Save param_mapping if it exists
        if self.param_mapping is not None:
            data["param_mapping"] = self.param_mapping

        # Note: routine_id is NOT serialized here - it's Flow's responsibility
        # Flow will add routine_id when serializing connections

        return data

    def deserialize(
        self, data: dict[str, Any], strict: bool = False, registry: Any | None = None
    ) -> None:
        """Deserialize the Connection.

        Args:
            data: Serialized data dictionary.
            strict: Whether to use strict deserialization.
            registry: Optional ObjectRegistry for deserializing callables.
        """
        # Save reference information for later restoration by Flow
        source_routine_id = data.pop("_source_routine_id", None)
        source_event_name = data.pop("_source_event_name", None)
        target_routine_id = data.pop("_target_routine_id", None)
        target_slot_name = data.pop("_target_slot_name", None)

        # Restore param_mapping if it exists
        self.param_mapping = data.pop("param_mapping", None)

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
        # Fix: Handle None values and missing name attribute
        source = f"{getattr(self.source_event, 'name', 'unknown')}" if self.source_event else "None"
        target = f"{getattr(self.target_slot, 'name', 'unknown')}" if self.target_slot else "None"
        return f"Connection[{source} -> {target}]"

    def disconnect(self) -> None:
        """Disconnect the connection.

        Safely disconnects the event from the slot. If either endpoint is None,
        this method does nothing (no-op).

        Raises:
            AttributeError: If source_event or target_slot are invalid (not None
                but don't have the expected disconnect/connect methods).
        """
        # Fix: Add None checks to prevent AttributeError
        if self.source_event is not None and self.target_slot is not None:
            self.source_event.disconnect(self.target_slot)
