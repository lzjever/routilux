"""
Connection class representing a link from an event to a slot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from routilux.core.event import Event
    from routilux.core.slot import Slot

from serilux import Serializable


# Note: Not using @register_serializable to avoid conflict with legacy module
class Connection(Serializable):
    """Connection object representing a link from an event to a slot.

    A Connection establishes a unidirectional data flow path from a source Event
    to a target Slot. When the source event is emitted, Runtime routes the data
    to the target slot's queue.

    Key Concepts:
        - One-to-One: Each Connection links exactly one Event to one Slot
        - Automatic Routing: Data flows automatically when event is emitted
        - Bidirectional Link: Also establishes link between Event and Slot

    Examples:
        >>> connection = Connection(source_event, target_slot)
        >>> # Event emits: {"data": "value"}
        >>> # Slot queue receives: {"data": "value"}
    """

    def __init__(
        self,
        source_event: Optional["Event"] = None,
        target_slot: Optional["Slot"] = None,
    ):
        """Initialize a Connection.

        Args:
            source_event: Source Event that will emit data
            target_slot: Target Slot that will receive data
        """
        super().__init__()
        self.source_event: Optional["Event"] = source_event
        self.target_slot: Optional["Slot"] = target_slot

        # Establish connection if both are provided
        if source_event is not None and target_slot is not None:
            source_event.connect(target_slot)

        # Register serializable fields
        self.add_serializable_fields([])

    def __repr__(self) -> str:
        """Return string representation."""
        source = (
            f"{getattr(self.source_event, 'name', 'unknown')}"
            if self.source_event
            else "None"
        )
        target = (
            f"{getattr(self.target_slot, 'name', 'unknown')}"
            if self.target_slot
            else "None"
        )
        return f"Connection[{source} -> {target}]"

    def disconnect(self) -> None:
        """Disconnect the connection."""
        if self.source_event is not None and self.target_slot is not None:
            self.source_event.disconnect(self.target_slot)

    def serialize(self) -> dict[str, Any]:
        """Serialize the Connection."""
        data = super().serialize()

        if self.source_event:
            data["_source_event_name"] = self.source_event.name
        if self.target_slot:
            data["_target_slot_name"] = self.target_slot.name

        return data

    def deserialize(
        self, data: dict[str, Any], strict: bool = False, registry: Any | None = None
    ) -> None:
        """Deserialize the Connection."""
        # Save reference information for later restoration by Flow
        source_routine_id = data.pop("_source_routine_id", None)
        source_event_name = data.pop("_source_event_name", None)
        target_routine_id = data.pop("_target_routine_id", None)
        target_slot_name = data.pop("_target_slot_name", None)

        # Ignore param_mapping if present in old serialized data
        data.pop("param_mapping", None)

        super().deserialize(data, strict=strict, registry=registry)

        # Save reference information for Flow.deserialize()
        if source_routine_id:
            self._source_routine_id = source_routine_id
        if source_event_name:
            self._source_event_name = source_event_name
        if target_routine_id:
            self._target_routine_id = target_routine_id
        if target_slot_name:
            self._target_slot_name = target_slot_name
