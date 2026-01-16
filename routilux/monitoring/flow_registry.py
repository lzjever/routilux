"""
Global flow registry for API discovery.

This registry tracks all Flow instances created in the system,
allowing the API to discover flows created outside the API.
Uses weak references to avoid preventing garbage collection.
"""

import threading
import weakref
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from routilux.flow.flow import Flow


class FlowRegistry:
    """Global registry for Flow instances.
    
    Thread-safe singleton that uses weak references to track Flow instances.
    Automatically cleans up dead references when flows are garbage collected.
    """
    
    _instance: Optional["FlowRegistry"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        """Initialize registry (private - use get_instance())."""
        self._flows: Dict[str, weakref.ref] = {}  # flow_id -> weakref
        self._named_flows: Dict[str, "Flow"] = {}  # name -> Flow (strong reference)
        self._lock = threading.RLock()
    
    @classmethod
    def get_instance(cls) -> "FlowRegistry":
        """Get singleton instance.
        
        Returns:
            FlowRegistry singleton instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def register(self, flow: "Flow") -> None:
        """Register a flow instance.
        
        Args:
            flow: Flow instance to register.
            
        Raises:
            TypeError: If flow is not a Flow instance.
        """
        if not hasattr(flow, 'flow_id'):
            raise TypeError("flow must be a Flow instance with flow_id attribute")
        
        with self._lock:
            # Use weak reference with callback to auto-cleanup
            def cleanup_callback(ref):
                """Callback when flow is garbage collected."""
                with self._lock:
                    # Find and remove dead reference
                    flow_id = None
                    for fid, r in list(self._flows.items()):
                        if r is ref:
                            flow_id = fid
                            break
                    if flow_id:
                        self._flows.pop(flow_id, None)
            
            self._flows[flow.flow_id] = weakref.ref(flow, cleanup_callback)
    
    def get(self, flow_id: str) -> Optional["Flow"]:
        """Get flow by ID.
        
        Args:
            flow_id: Flow identifier.
            
        Returns:
            Flow instance if found and still alive, None otherwise.
        """
        with self._lock:
            ref = self._flows.get(flow_id)
            if ref is None:
                return None
            flow = ref()
            if flow is None:
                # Flow was garbage collected, remove from registry
                self._flows.pop(flow_id, None)
            return flow
    
    def list_all(self) -> List["Flow"]:
        """List all registered flows.
        
        Returns:
            List of Flow instances (only alive ones).
        """
        with self._lock:
            flows = []
            dead_flow_ids = []
            
            for flow_id, ref in self._flows.items():
                flow = ref()
                if flow is None:
                    dead_flow_ids.append(flow_id)
                else:
                    flows.append(flow)
            
            # Clean up dead references
            for flow_id in dead_flow_ids:
                self._flows.pop(flow_id, None)
            
            return flows
    
    def register_by_name(self, name: str, flow: "Flow") -> None:
        """Register a flow by name.
        
        This creates a strong reference to the flow, so it won't be
        garbage collected. Use this for flows that should be available
        by name for execution.
        
        Args:
            name: Unique name for the flow.
            flow: Flow instance to register.
            
        Raises:
            TypeError: If flow is not a Flow instance.
            ValueError: If name is already registered.
        """
        if not hasattr(flow, 'flow_id'):
            raise TypeError("flow must be a Flow instance with flow_id attribute")
        
        with self._lock:
            if name in self._named_flows:
                raise ValueError(f"Flow name '{name}' is already registered")
            
            # Store strong reference
            self._named_flows[name] = flow
            
            # Also register by flow_id (weak reference)
            self.register(flow)
    
    def get_by_name(self, name: str) -> Optional["Flow"]:
        """Get flow by name.
        
        Args:
            name: Flow name.
            
        Returns:
            Flow instance if found, None otherwise.
        """
        with self._lock:
            return self._named_flows.get(name)
    
    def unregister_by_name(self, name: str) -> bool:
        """Unregister a flow by name.
        
        Args:
            name: Flow name.
            
        Returns:
            True if flow was unregistered, False if not found.
        """
        with self._lock:
            if name in self._named_flows:
                del self._named_flows[name]
                return True
            return False
    
    def clear(self) -> None:
        """Clear all registered flows (for testing only)."""
        with self._lock:
            self._flows.clear()
            self._named_flows.clear()
