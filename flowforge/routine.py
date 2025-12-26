"""
Routine base class.

Improved Routine mechanism supporting slots (input slots) and events (output events).
"""
from __future__ import annotations
import uuid
from typing import Dict, Any, Callable, Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from flowforge.slot import Slot
    from flowforge.event import Event
    from flowforge.flow import Flow

from flowforge.utils.serializable import register_serializable, Serializable
from flowforge.serialization_utils import get_routine_class_info


@register_serializable
class Routine(Serializable):
    """Improved Routine base class with enhanced capabilities.
    
    Features:
    - Support for slots (input slots)
    - Support for events (output events)
    - Provides stats() method to return state dictionary
    - Configuration dictionary (_config) for storing routine-specific settings
    
    Important Constraints:
        - Routines MUST NOT accept constructor parameters (except self).
          This is required for proper serialization/deserialization.
        - All configuration should be stored in the _config dictionary.
        - Configuration can be set after object creation using set_config()
          or by directly modifying self._config.
        - The _config dictionary is automatically included in serialization.
    
    Examples:
        Correct usage:
            >>> class MyRoutine(Routine):
            ...     def __init__(self):
            ...         super().__init__()
            ...         self._config["name"] = "my_routine"
            ...         self._config["timeout"] = 30
            ...         # Or use set_config()
            ...         self.set_config(name="my_routine", timeout=30)
        
        Incorrect usage (will break serialization):
            >>> class BadRoutine(Routine):
            ...     def __init__(self, name: str):  # ❌ Don't do this!
            ...         super().__init__()
            ...         self.name = name
    """
    
    def __init__(self):
        """Initialize Routine object.
        
        Note:
            This constructor accepts no parameters (except self). All configuration
            should be stored in self._config dictionary after object creation.
            See set_config() method for a convenient way to set configuration.
        """
        super().__init__()
        self._id: str = hex(id(self))
        self._slots: Dict[str, 'Slot'] = {}
        self._events: Dict[str, 'Event'] = {}
        self._stats: Dict[str, Any] = {}
        self._config: Dict[str, Any] = {}  # Configuration dictionary
        
        # Register serializable fields
        # _config is included to ensure configuration is preserved during serialization
        self.add_serializable_fields(["_id", "_stats", "_slots", "_events", "_config"])
    
    def __repr__(self) -> str:
        """Return string representation of the Routine."""
        return f"{self.__class__.__name__}[{self._id}]"
    
    def define_slot(
        self,
        name: str,
        handler: Optional[Callable] = None,
        merge_strategy: str = "override"
    ) -> 'Slot':
        """Define an input slot for receiving data from other routines.

        This method creates a new slot that can be connected to events from
        other routines. When data is received, it's merged with existing data
        according to the merge_strategy, then passed to the handler.

        Args:
            name: Slot name. Must be unique within this routine. Used to
                identify the slot when connecting events.
            handler: Handler function called when slot receives data. The function
                signature can be flexible - see Slot.__init__ documentation for
                details on how data is passed to the handler. If None, no handler
                is called when data is received.
            merge_strategy: Strategy for merging new data with existing data.
                - "override" (default): New data completely replaces old data.
                  Each receive() passes only the new data to the handler.
                  Use this when you only need the latest data.
                - "append": New values are appended to lists. The handler receives
                  accumulated data each time. Use this for aggregation scenarios
                  where you need to collect multiple data points.
                - Callable: A function(old_data: Dict, new_data: Dict) -> Dict
                  that implements custom merge logic. Use this for complex
                  requirements like deep merging or domain-specific operations.
                See Slot class documentation for detailed examples and behavior.

        Returns:
            Slot object that can be connected to events from other routines.

        Raises:
            ValueError: If slot name already exists in this routine.

        Examples:
            Simple slot with override strategy (default):
                >>> routine = MyRoutine()
                >>> slot = routine.define_slot("input", handler=process_data)
                >>> # slot uses "override" strategy by default
            
            Aggregation slot with append strategy:
                >>> slot = routine.define_slot(
                ...     "input",
                ...     handler=aggregate_data,
                ...     merge_strategy="append"
                ... )
                >>> # Values will be accumulated in lists
            
            Custom merge strategy:
                >>> def deep_merge(old, new):
                ...     result = old.copy()
                ...     for k, v in new.items():
                ...         if k in result and isinstance(result[k], dict):
                ...             result[k] = deep_merge(result[k], v)
                ...         else:
                ...             result[k] = v
                ...     return result
                >>> slot = routine.define_slot("input", merge_strategy=deep_merge)
        """
        if name in self._slots:
            raise ValueError(f"Slot '{name}' already exists in {self}")
        
        # Lazy import to avoid circular dependency
        from flowforge.slot import Slot
        
        slot = Slot(name, self, handler, merge_strategy)
        self._slots[name] = slot
        return slot
    
    def define_event(
        self,
        name: str,
        output_params: Optional[List[str]] = None
    ) -> 'Event':
        """Define an output event.

        Args:
            name: Event name.
            output_params: List of output parameter names (optional, for documentation).

        Returns:
            Event object.

        Raises:
            ValueError: If event name already exists.
        """
        if name in self._events:
            raise ValueError(f"Event '{name}' already exists in {self}")
        
        # Lazy import to avoid circular dependency
        from flowforge.event import Event
        
        event = Event(name, self, output_params or [])
        self._events[name] = event
        return event
    
    def emit(self, event_name: str, flow: Optional['Flow'] = None, **kwargs) -> None:
        """Emit an event.

        Args:
            event_name: Event name.
            flow: Flow object (for parameter mapping, optional, will try to get from context if not provided).
            **kwargs: Data to pass to the event.

        Raises:
            ValueError: If event does not exist.
        """
        if event_name not in self._events:
            raise ValueError(f"Event '{event_name}' does not exist in {self}")
        
        event = self._events[event_name]
        
        # If flow not provided, try to get from context
        if flow is None and hasattr(self, '_current_flow'):
            flow = getattr(self, '_current_flow', None)
        
        event.emit(flow=flow, **kwargs)
        
        # Update state
        self._stats.setdefault("emitted_events", []).append({
            "event": event_name,
            "data": kwargs
        })
        
        # If flow exists, record execution history
        if flow is not None:
            if flow.job_state is not None:
                flow.job_state.record_execution(self._id, event_name, kwargs)
            
            # Record to execution tracker
            if flow.execution_tracker is not None:
                # Find target routine (via connected slots)
                target_routine_id = None
                event_obj = self._events.get(event_name)
                if event_obj and event_obj.connected_slots:
                    # Get routine of first connected slot
                    target_routine_id = event_obj.connected_slots[0].routine._id
                
                flow.execution_tracker.record_event(
                    self._id, event_name, target_routine_id, kwargs
                )
    
    def stats(self) -> Dict[str, Any]:
        """Return a copy of the state dictionary.

        Returns:
            Copy of the state dictionary.
        """
        return self._stats.copy()
    
    def __call__(self, **kwargs) -> None:
        """Execute routine.

        Subclasses should override this method to implement specific execution logic.

        Args:
            **kwargs: Parameters passed to the routine.
        """
        # Update state
        self._stats["called"] = True
        self._stats["call_count"] = self._stats.get("call_count", 0) + 1
        
        # Subclasses can override this method to implement specific logic
        pass
    
    def get_slot(self, name: str) -> Optional['Slot']:
        """Get specified slot.

        Args:
            name: Slot name.

        Returns:
            Slot object if found, None otherwise.
        """
        return self._slots.get(name)
    
    def get_event(self, name: str) -> Optional['Event']:
        """Get specified event.

        Args:
            name: Event name.

        Returns:
            Event object if found, None otherwise.
        """
        return self._events.get(name)
    
    def set_config(self, **kwargs) -> None:
        """Set configuration values in the _config dictionary.
        
        This is the recommended way to set routine configuration after object
        creation. All configuration values are stored in self._config and will
        be automatically serialized/deserialized.
        
        Args:
            **kwargs: Configuration key-value pairs to set. These will be stored
                in self._config dictionary.
        
        Examples:
            >>> routine = MyRoutine()
            >>> routine.set_config(name="processor_1", timeout=30, retries=3)
            >>> # Now routine._config contains:
            >>> # {"name": "processor_1", "timeout": 30, "retries": 3}
            
            >>> # You can also set config directly:
            >>> routine._config["custom_setting"] = "value"
        
        Note:
            - Configuration can be set at any time after object creation.
            - All values in _config are automatically serialized.
            - Use this method instead of constructor parameters to ensure
              proper serialization/deserialization support.
        """
        self._config.update(kwargs)
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a configuration value from the _config dictionary.
        
        Args:
            key: Configuration key to retrieve.
            default: Default value to return if key doesn't exist.
        
        Returns:
            Configuration value if found, default value otherwise.
        
        Examples:
            >>> routine = MyRoutine()
            >>> routine.set_config(timeout=30)
            >>> timeout = routine.get_config("timeout", default=10)  # Returns 30
            >>> retries = routine.get_config("retries", default=0)  # Returns 0
        """
        return self._config.get(key, default)
    
    def config(self) -> Dict[str, Any]:
        """Get a copy of the configuration dictionary.
        
        Returns:
            Copy of the _config dictionary. Modifications to the returned
            dictionary will not affect the original _config.
        
        Examples:
            >>> routine = MyRoutine()
            >>> routine.set_config(name="test", timeout=30)
            >>> config = routine.config()
            >>> print(config)  # {"name": "test", "timeout": 30}
        """
        return self._config.copy()
    
    def serialize(self) -> Dict[str, Any]:
        """Serialize Routine, including class information and state.

        Returns:
            Serialized dictionary.
        """
        data = super().serialize()
        
        # Add class information
        class_info = get_routine_class_info(self)
        data["_class_info"] = class_info
        
        # Serialize slots (save name and metadata, not handler function)
        slots_data = {}
        for name, slot in self._slots.items():
            slot_data = slot.serialize()
            # Save handler metadata
            from flowforge.serialization_utils import serialize_callable
            handler_data = serialize_callable(slot.handler)
            if handler_data:
                slot_data["_handler_metadata"] = handler_data
            slots_data[name] = slot_data
        data["_slots"] = slots_data
        
        # Serialize events
        events_data = {}
        for name, event in self._events.items():
            events_data[name] = event.serialize()
        data["_events"] = events_data
        
        return data
    
    def deserialize(self, data: Dict[str, Any]) -> None:
        """Deserialize Routine.

        Args:
            data: Serialized data dictionary.
        """
        # First deserialize basic fields (excluding _slots and _events, which need special handling)
        basic_data = {k: v for k, v in data.items() if k not in ["_slots", "_events", "_class_info"]}
        super().deserialize(basic_data)
        
        # Restore slots (basic structure, handler restored in Flow.deserialize)
        if "_slots" in data:
            from flowforge.slot import Slot
            
            self._slots = {}
            for name, slot_data in data["_slots"].items():
                slot = Slot()
                slot.name = slot_data.get("name", name)
                slot._data = slot_data.get("_data", {})
                slot.merge_strategy = slot_data.get("merge_strategy", "override")
                slot.routine = self
                # Save handler metadata for later restoration
                if "_handler_metadata" in slot_data:
                    slot._handler_metadata = slot_data["_handler_metadata"]
                if "_merge_strategy_metadata" in slot_data:
                    slot._merge_strategy_metadata = slot_data["_merge_strategy_metadata"]
                self._slots[name] = slot
        
        # Restore events
        if "_events" in data:
            from flowforge.event import Event
            
            self._events = {}
            for name, event_data in data["_events"].items():
                event = Event()
                event.deserialize(event_data)
                event.routine = self
                self._events[name] = event

