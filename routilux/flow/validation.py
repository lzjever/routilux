"""
Flow validation module.

Provides validation logic for Flow structures including cycle detection,
unconnected component detection, and connection validation.
"""

from typing import TYPE_CHECKING, List, Set, Tuple

if TYPE_CHECKING:
    from routilux.flow.flow import Flow


def detect_cycles(flow: "Flow") -> List[List[str]]:
    """Detect circular dependencies in the flow using DFS.

    Args:
        flow: Flow object to validate.

    Returns:
        List of cycles, where each cycle is a list of routine IDs forming a cycle.
        Empty list if no cycles found.
    """
    from routilux.flow.dependency import build_dependency_graph

    dependency_graph = build_dependency_graph(flow.routines, flow.connections)
    cycles: List[List[str]] = []
    visited: Set[str] = set()
    rec_stack: Set[str] = set()
    path: List[str] = []

    def dfs(routine_id: str) -> bool:
        """DFS helper to detect cycles."""
        visited.add(routine_id)
        rec_stack.add(routine_id)
        path.append(routine_id)

        for dep_id in dependency_graph.get(routine_id, set()):
            if dep_id not in visited:
                if dfs(dep_id):
                    return True
            elif dep_id in rec_stack:
                # Found a cycle
                cycle_start = path.index(dep_id)
                cycle = path[cycle_start:] + [dep_id]
                cycles.append(cycle)
                return True

        rec_stack.remove(routine_id)
        path.pop()
        return False

    for routine_id in flow.routines.keys():
        if routine_id not in visited:
            dfs(routine_id)

    return cycles


def find_unconnected_events(flow: "Flow") -> List[Tuple[str, str]]:
    """Find events that are not connected to any slots.

    Args:
        flow: Flow object to validate.

    Returns:
        List of (routine_id, event_name) tuples for unconnected events.
    """
    unconnected: List[Tuple[str, str]] = []

    # Build set of connected events
    connected_events: Set[Tuple[str, str]] = set()
    for connection in flow.connections:
        # Critical fix: Check if connection and source_event exist before accessing
        if connection.source_event is None or connection.source_event.routine is None:
            continue  # Skip incomplete connections
        source_routine_id = flow._get_routine_id(connection.source_event.routine)
        if source_routine_id:
            connected_events.add((source_routine_id, connection.source_event.name))

    # Check all events
    for routine_id, routine in flow.routines.items():
        for event_name, event in routine._events.items():
            if (routine_id, event_name) not in connected_events:
                unconnected.append((routine_id, event_name))

    return unconnected


def find_unconnected_slots(flow: "Flow") -> List[Tuple[str, str]]:
    """Find slots that are not connected to any events.

    Args:
        flow: Flow object to validate.

    Returns:
        List of (routine_id, slot_name) tuples for unconnected slots.
    """
    unconnected: List[Tuple[str, str]] = []

    # Build set of connected slots
    connected_slots: Set[Tuple[str, str]] = set()
    for connection in flow.connections:
        # Critical fix: Check if connection and target_slot exist before accessing
        if connection.target_slot is None or connection.target_slot.routine is None:
            continue  # Skip incomplete connections
        target_routine_id = flow._get_routine_id(connection.target_slot.routine)
        if target_routine_id:
            connected_slots.add((target_routine_id, connection.target_slot.name))

    # Check all slots
    for routine_id, routine in flow.routines.items():
        for slot_name, slot in routine._slots.items():
            if (routine_id, slot_name) not in connected_slots:
                unconnected.append((routine_id, slot_name))

    return unconnected


def validate_flow(flow: "Flow") -> List[str]:
    """Validate flow structure and return list of issues.

    Args:
        flow: Flow object to validate.

    Returns:
        List of validation error/warning messages. Empty list means valid.
    """
    issues: List[str] = []

    # Check for circular dependencies
    cycles = detect_cycles(flow)
    if cycles:
        cycle_strs = [" -> ".join(cycle) for cycle in cycles]
        issues.append(f"Circular dependencies detected: {'; '.join(cycle_strs)}")

    # Check for unconnected events (warnings, not errors)
    unconnected_events = find_unconnected_events(flow)
    if unconnected_events:
        event_strs = [f"{rid}.{ename}" for rid, ename in unconnected_events]
        issues.append(f"Warning: Unconnected events (data will be lost): {', '.join(event_strs)}")

    # Check for unconnected slots (warnings)
    unconnected_slots = find_unconnected_slots(flow)
    if unconnected_slots:
        slot_strs = [f"{rid}.{sname}" for rid, sname in unconnected_slots]
        issues.append(
            f"Warning: Unconnected slots (will never receive data): {', '.join(slot_strs)}"
        )

    # Validate connections reference valid routines/events/slots
    for connection in flow.connections:
        # Critical fix: Check if connection and its attributes exist before accessing
        if connection.source_event is None or connection.source_event.routine is None:
            issues.append("Connection has missing source event or source routine")
            continue
        if connection.target_slot is None or connection.target_slot.routine is None:
            issues.append("Connection has missing target slot or target routine")
            continue

        source_routine_id = flow._get_routine_id(connection.source_event.routine)
        target_routine_id = flow._get_routine_id(connection.target_slot.routine)

        if source_routine_id is None:
            issues.append(
                f"Connection references unknown source routine: {connection.source_event.routine}"
            )
        elif source_routine_id not in flow.routines:
            issues.append(f"Connection references source routine not in flow: {source_routine_id}")
        elif connection.source_event.name not in flow.routines[source_routine_id]._events:
            issues.append(
                f"Connection references unknown event: {source_routine_id}.{connection.source_event.name}"
            )

        if target_routine_id is None:
            issues.append(
                f"Connection references unknown target routine: {connection.target_slot.routine}"
            )
        elif target_routine_id not in flow.routines:
            issues.append(f"Connection references target routine not in flow: {target_routine_id}")
        elif connection.target_slot.name not in flow.routines[target_routine_id]._slots:
            issues.append(
                f"Connection references unknown slot: {target_routine_id}.{connection.target_slot.name}"
            )

    return issues
