"""
Serialization logic for Flow.

Handles serialization and deserialization of Flow objects.
"""

from typing import TYPE_CHECKING, Any, Dict

from serilux import Serializable

if TYPE_CHECKING:
    from routilux.flow.flow import Flow


def serialize_flow(flow: "Flow") -> Dict[str, Any]:
    """Serialize Flow, including all routines and connections.

    Before serialization, this method validates that all Serializable objects
    in the Flow (routines, connections, slots, events, etc.) can be constructed
    without arguments. This ensures that deserialization will succeed.

    Args:
        flow: Flow object.

    Returns:
        Serialized dictionary containing flow data.

    Raises:
        TypeError: If any Serializable object in the Flow cannot be constructed
            without arguments.
    """
    from serilux import validate_serializable_tree

    validate_serializable_tree(flow)

    # Call parent class serialize method
    data = Serializable.serialize(flow)

    return data


def deserialize_flow(flow: "Flow", data: Dict[str, Any]) -> None:
    """Deserialize Flow, restoring all routines and connections.

    Args:
        flow: Flow object.
        data: Serialized data dictionary (structure only, no execution state).
    """
    Serializable.deserialize(flow, data)

    for routine in flow.routines.values():
        routine.current_flow = flow._current_flow

    valid_connections = []
    for connection in flow.connections:
        source_event_name = getattr(connection, "_source_event_name", None)
        target_slot_name = getattr(connection, "_target_slot_name", None)

        if source_event_name:
            for routine in flow.routines.values():
                source_event = routine.get_event(source_event_name)
                if source_event:
                    connection.source_event = source_event
                    break

        if target_slot_name:
            for routine in flow.routines.values():
                target_slot = routine.get_slot(target_slot_name)
                if target_slot:
                    connection.target_slot = target_slot
                    break

        if connection.source_event and connection.target_slot:
            if connection.target_slot not in connection.source_event.connected_slots:
                connection.source_event.connect(connection.target_slot)
            if connection.source_event not in connection.target_slot.connected_events:
                connection.target_slot.connect(connection.source_event)

            valid_connections.append(connection)
            key = (connection.source_event, connection.target_slot)
            flow._event_slot_connections[key] = connection

    flow.connections = valid_connections
