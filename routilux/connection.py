"""
Connection class.

Represents a connection from an event to a slot.
"""

from __future__ import annotations
from typing import Dict, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from routilux.event import Event
    from routilux.slot import Slot

from serilux import register_serializable, Serializable


@register_serializable
class Connection(Serializable):
    """Connection object representing a link from an event to a slot.

    A Connection establishes a unidirectional data flow path from a source Event
    to a target Slot. When the source event is emitted, the connection automatically
    transmits the data to the target slot, optionally applying parameter mapping
    to transform parameter names during transmission.

    Key Concepts:
        - One-to-One Relationship: Each Connection links exactly one Event to one Slot
        - Parameter Mapping: Can rename parameters when transmitting data
        - Automatic Transmission: Data flows automatically when event is emitted
        - Bidirectional Link: Connection also establishes bidirectional link between
          Event and Slot (Event.connected_slots and Slot.connected_events)

    Parameter Mapping:
        Parameter mapping allows you to rename parameters when data flows from
        event to slot. This is useful when:
        - Event and slot use different parameter names for the same data
        - You want to standardize parameter names across different routines
        - You need to map multiple events to the same slot with different names

        Format: {event_param_name: slot_param_name}
        - Mapped parameters: Renamed according to mapping
        - Unmapped parameters: Passed with original names (if not conflicting)
        - If a parameter is in mapping but not in event data: Not included
        - If a parameter is in mapping values but not in event data: Not included

    Data Flow:
        1. Event emits data via ``emit(**kwargs)``
        2. Connection receives data dictionary
        3. Connection applies parameter mapping (if defined)
        4. Connection calls slot.receive(mapped_data)
        5. Slot merges data and calls handler

    Examples:
        Basic connection (no parameter mapping):
            >>> connection = Connection(source_event, target_slot)
            >>> # Event emits: {"data": "value", "count": 5}
            >>> # Slot receives: {"data": "value", "count": 5}

        Connection with parameter mapping:
            >>> connection = Connection(
            ...     source_event, target_slot,
            ...     param_mapping={"source_data": "target_input", "count": "total"}
            ... )
            >>> # Event emits: {"source_data": "x", "count": 5, "extra": "ignored"}
            >>> # Slot receives: {"target_input": "x", "total": 5, "extra": "ignored"}
    """

    def __init__(
        self,
        source_event: Optional["Event"] = None,
        target_slot: Optional["Slot"] = None,
        param_mapping: Optional[Dict[str, str]] = None,
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
            param_mapping: Optional dictionary mapping event parameter names to
                slot parameter names. Format: {event_param: slot_param}
                If None or empty, parameters are passed unchanged.
                Example: {"event_data": "slot_input", "event_count": "slot_total"}

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

            Connection with parameter mapping:
                >>> connection = Connection(
                ...     event, slot,
                ...     param_mapping={"result": "data", "status": "state"}
                ... )
                >>> # When event emits {"result": "x", "status": "ok"},
                >>> # slot receives {"data": "x", "state": "ok"}
        """
        super().__init__()
        self.source_event: Optional["Event"] = source_event
        self.target_slot: Optional["Slot"] = target_slot
        self.param_mapping: Dict[str, str] = param_mapping or {}

        # Establish connection if both event and slot are provided
        if source_event is not None and target_slot is not None:
            source_event.connect(target_slot)

        # Register serializable fields
        self.add_serializable_fields(["param_mapping"])

    def serialize(self) -> Dict[str, Any]:
        """Serialize the Connection.

        Returns:
            Serialized dictionary containing connection data.
        """
        # Let base class handle registered fields (param_mapping)
        data = super().serialize()

        # Save event and slot names (Connection's responsibility)
        if self.source_event:
            data["_source_event_name"] = self.source_event.name
        if self.target_slot:
            data["_target_slot_name"] = self.target_slot.name

        # Note: routine_id is NOT serialized here - it's Flow's responsibility
        # Flow will add routine_id when serializing connections

        return data

    def deserialize(self, data: Dict[str, Any]) -> None:
        """Deserialize the Connection.

        Args:
            data: Serialized data dictionary.
        """
        # Save reference information for later restoration by Flow
        source_routine_id = data.pop("_source_routine_id", None)
        source_event_name = data.pop("_source_event_name", None)
        target_routine_id = data.pop("_target_routine_id", None)
        target_slot_name = data.pop("_target_slot_name", None)

        # Let base class handle registered fields (param_mapping)
        super().deserialize(data)

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

    def activate(self, data: Dict[str, Any]) -> None:
        """Activate the connection and transmit data to the target slot.

        This method is called automatically when the source event is emitted.
        It applies parameter mapping (if defined) and transmits the data to
        the target slot. You typically don't call this directly.

        Processing Steps:
            1. Apply parameter mapping to transform parameter names
            2. Call target_slot.receive() with the mapped data
            3. Slot merges data and calls its handler

        Args:
            data: Data dictionary from the source event. This is the kwargs
                passed to ``Event.emit(**kwargs)``. The dictionary will be
                transformed according to param_mapping before being sent to
                the slot.
                Example: {"result": "success", "count": 42}

        Examples:
            Manual activation (for testing):
                >>> connection = Connection(event, slot, {"old": "new"})
                >>> connection.activate({"old": "value", "other": "data"})
                >>> # Slot receives {"new": "value", "other": "data"}

            Automatic activation (normal usage):
                >>> # When event emits, activate() is called automatically
                >>> event.emit(flow=my_flow, result="data", count=5)
                >>> # Connection.activate() is called internally
        """
        # Apply parameter mapping
        mapped_data = self._apply_mapping(data)

        # Transmit to target slot
        self.target_slot.receive(mapped_data)

    def _apply_mapping(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply parameter mapping to transform data dictionary.

        This method transforms parameter names according to the param_mapping
        dictionary. Mapped parameters are renamed, while unmapped parameters
        are passed through unchanged (if they don't conflict with mapped names).

        Mapping Rules:
            - If param_mapping is empty/None: Returns data unchanged
            - For each (source_key, target_key) in param_mapping:
              - If source_key exists in data: Add target_key with that value
              - If source_key doesn't exist: Skip (target_key not added)
            - For unmapped keys in data:
              - If key doesn't conflict with any target_key: Include unchanged
              - If key conflicts with a target_key: Excluded (mapped version used)

        Args:
            data: Original data dictionary from the event emission.
                This contains the keyword arguments passed to ``Event.emit(**kwargs)``.

        Returns:
            Transformed data dictionary with parameter names mapped according
            to param_mapping. Mapped parameters use new names, unmapped parameters
            keep original names (if not conflicting).

        Examples:
            Simple mapping:
                >>> mapping = {"old_name": "new_name"}
                >>> data = {"old_name": "value", "other": "data"}
                >>> result = connection._apply_mapping(data)
                >>> # result = {"new_name": "value", "other": "data"}

            Multiple mappings:
                >>> mapping = {"a": "x", "b": "y"}
                >>> data = {"a": 1, "b": 2, "c": 3}
                >>> result = connection._apply_mapping(data)
                >>> # result = {"x": 1, "y": 2, "c": 3}
        """
        if not self.param_mapping:
            # No mapping, return as is
            return data

        mapped_data = {}
        for source_key, target_key in self.param_mapping.items():
            if source_key in data:
                mapped_data[target_key] = data[source_key]

        # For unmapped parameters, also pass them if the target slot's handler needs them
        # Simplified handling: pass all unmapped parameters if target parameter name
        # matches source parameter name
        for key, value in data.items():
            if key not in self.param_mapping.values() and key not in mapped_data:
                # Check if it matches target parameter name (simplified, should check handler signature)
                mapped_data[key] = value

        return mapped_data

    def disconnect(self) -> None:
        """Disconnect the connection."""
        self.source_event.disconnect(self.target_slot)
