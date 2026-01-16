"""
Dependency graph management for Flow execution.

Handles building and querying routine dependency graphs.
"""

from typing import TYPE_CHECKING, Dict, List, Set

if TYPE_CHECKING:
    from routilux.connection import Connection
    from routilux.routine import Routine


def build_dependency_graph(
    routines: Dict[str, "Routine"], connections: List["Connection"]
) -> Dict[str, Set[str]]:
    """Build routine dependency graph.

    Determines dependencies by analyzing connections:
    - If A.event -> B.slot, then B depends on A (B must wait for A to complete).

    Args:
        routines: Dictionary of routine_id -> Routine.
        connections: List of Connection objects.

    Returns:
        Dependency graph dictionary: {routine_id: {dependent routine_ids}}.
    """
    # Fix: Create a snapshot to avoid modification during iteration
    routines_snapshot = dict(routines)
    graph = {rid: set() for rid in routines_snapshot.keys()}

    def get_routine_id(routine: "Routine") -> str | None:
        """Find the ID of a Routine object within routines dict."""
        for rid, r in routines_snapshot.items():
            if r is routine:
                return rid
        return None

    for conn in connections:
        # Critical fix: Check if source_event and target_slot exist before accessing attributes
        # These can be None during deserialization or if connection is not fully initialized
        if conn.source_event is None or conn.target_slot is None:
            continue

        # Additional fix: Check if .routine attribute is not None
        if conn.source_event.routine is None or conn.target_slot.routine is None:
            continue

        source_rid = get_routine_id(conn.source_event.routine)
        target_rid = get_routine_id(conn.target_slot.routine)

        if source_rid and target_rid and source_rid != target_rid:
            graph[target_rid].add(source_rid)

    return graph


def get_ready_routines(
    completed: Set[str],
    dependency_graph: Dict[str, Set[str]],
    running: Set[str],
) -> List[str]:
    """Get routines ready for execution (all dependencies completed and not running).

    Args:
        completed: Set of completed routine IDs.
        dependency_graph: Dependency graph.
        running: Set of currently running routine IDs.

    Returns:
        List of routine IDs ready for execution.
    """
    ready = []
    for routine_id, dependencies in dependency_graph.items():
        if (
            dependencies.issubset(completed)
            and routine_id not in completed
            and routine_id not in running
        ):
            ready.append(routine_id)
    return ready
