"""
In-memory storage managers for flows, jobs, and debug sessions.

These stores are used by the FastAPI backend to manage flow and job state.
"""

import threading
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from routilux.core.flow import Flow


class FlowStore:
    """In-memory flow storage.

    Thread-safe store for Flow objects.
    """

    def __init__(self):
        """Initialize flow store."""
        self._flows: Dict[str, Flow] = {}
        self._lock = threading.RLock()

    def get(self, flow_id: str) -> Optional["Flow"]:
        """Get flow by ID.

        First checks local store, then falls back to global registry.
        This allows the API to discover flows created outside the API.

        Args:
            flow_id: Flow identifier.

        Returns:
            Flow object or None if not found.
        """
        with self._lock:
            # First check local store
            flow = self._flows.get(flow_id)
            if flow is not None:
                return flow

            # Fall back to global registry
            try:
                from routilux.core.registry import FlowRegistry

                registry = FlowRegistry.get_instance()
                flow = registry.get(flow_id)
                if flow is not None:
                    # Auto-add to local store for future queries
                    self._flows[flow_id] = flow
                return flow
            except ImportError:
                # Registry not available, return None
                return None

    def add(self, flow: "Flow") -> None:
        """Add or update a flow.

        Args:
            flow: Flow object to store.
        """
        with self._lock:
            self._flows[flow.flow_id] = flow

    def remove(self, flow_id: str) -> None:
        """Remove a flow.

        Args:
            flow_id: Flow identifier.
        """
        with self._lock:
            self._flows.pop(flow_id, None)

    def list_all(self) -> List["Flow"]:
        """List all flows.

        Combines local store and global registry.
        This allows the API to discover flows created outside the API.

        Returns:
            List of all Flow objects.
        """
        with self._lock:
            local_flows = list(self._flows.values())

            # Also get flows from global registry
            try:
                from routilux.core.registry import FlowRegistry

                registry = FlowRegistry.get_instance()
                registry_flows = registry.list_all()

                # Merge (avoid duplicates)
                flow_ids = {f.flow_id for f in local_flows}
                for flow in registry_flows:
                    if flow.flow_id not in flow_ids:
                        local_flows.append(flow)
                        self._flows[flow.flow_id] = flow  # Cache in local store
            except ImportError:
                # Registry not available, return local flows only
                pass

            return local_flows

    def clear(self) -> None:
        """Clear all flows."""
        with self._lock:
            self._flows.clear()


# Global instances (used by API)
flow_store = FlowStore()
# Note: JobStore removed - use MemoryJobStorage from routilux.server.storage.memory instead
