"""
Connection class.

Represents a connection from an event to a slot.
"""
from __future__ import annotations
from typing import Dict, Optional, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from flowforge.event import Event
    from flowforge.slot import Slot

from flowforge.utils.serializable import register_serializable, Serializable


@register_serializable
class Connection(Serializable):
    """Connection object representing a link from an event to a slot.
    
    A Connection establishes a data flow path from a source Event to a target Slot,
    with optional parameter mapping to transform the data during transmission.
    """
    
    def __init__(
        self,
        source_event: Optional['Event'] = None,
        target_slot: Optional['Slot'] = None,
        param_mapping: Optional[Dict[str, str]] = None
    ):
        """Initialize a Connection.

        Args:
            source_event: Source Event object.
            target_slot: Target Slot object.
            param_mapping: Parameter mapping dictionary that maps source parameter
                names to target parameter names.
        """
        super().__init__()
        self.source_event: Optional['Event'] = source_event
        self.target_slot: Optional['Slot'] = target_slot
        self.param_mapping: Dict[str, str] = param_mapping or {}
        
        # Establish connection if both event and slot are provided
        if source_event is not None and target_slot is not None:
            source_event.connect(target_slot)
        
        # Register serializable fields
        self.add_serializable_fields(["param_mapping"])
    
    def serialize(self) -> Dict[str, Any]:
        """Serialize the Connection.

        Returns:
            Serialized dictionary containing connection data and references.
        """
        data = super().serialize()
        
        # Save reference information (via routine_id + event/slot name)
        if self.source_event and self.source_event.routine:
            data["_source_routine_id"] = self.source_event.routine._id
            data["_source_event_name"] = self.source_event.name
        
        if self.target_slot and self.target_slot.routine:
            data["_target_routine_id"] = self.target_slot.routine._id
            data["_target_slot_name"] = self.target_slot.name
        
        return data
    
    def deserialize(self, data: Dict[str, Any]) -> None:
        """Deserialize the Connection.

        Args:
            data: Serialized data dictionary.
        """
        # Save reference information for later restoration
        source_routine_id = data.pop("_source_routine_id", None)
        source_event_name = data.pop("_source_event_name", None)
        target_routine_id = data.pop("_target_routine_id", None)
        target_slot_name = data.pop("_target_slot_name", None)
        
        # Deserialize basic fields
        super().deserialize(data)
        
        # Save reference information to be restored when Flow is reconstructed
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
        """Activate the connection and transmit data.

        Args:
            data: Data dictionary to transmit.
        """
        # Apply parameter mapping
        mapped_data = self._apply_mapping(data)
        
        # Transmit to target slot
        self.target_slot.receive(mapped_data)
    
    def _apply_mapping(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply parameter mapping to transform data.

        Args:
            data: Original data dictionary.

        Returns:
            Mapped data dictionary with transformed parameter names.
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

