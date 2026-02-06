"""Routine mixins for separating concerns.

This module contains mixin classes that split the Routine class's
responsibilities into focused, single-purpose components.

Mixin Architecture:
    - ConfigMixin: Configuration and parameter management
    - ExecutionMixin: Event emission and slot management
    - LifecycleMixin: State management and lifecycle hooks

The Routine class inherits from all three mixins in order.
"""

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, cast

# TYPE_CHECKING imports to avoid circular dependencies
if TYPE_CHECKING:
    from routilux.event import Event
    from routilux.flow import Flow
    from routilux.job_state import JobState
    from routilux.routine import Routine
    from routilux.slot import Slot


def _get_current_job_state():
    """Get the module-level _current_job_state from routine module.

    This function exists to avoid circular imports between routine_mixins
    and routine modules.
    """
    import routilux.routine as routine_module

    return getattr(routine_module, "_current_job_state", None)


class ConfigMixin:
    """Mixin for routine configuration and parameter management.

    Provides methods for configuring routine parameters and
    retrieving configuration values.

    Attributes:
        _config: Dictionary of configuration parameters.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize ConfigMixin.

        Note: This is a mixin, called via super().__init__() from Routine.
        """
        super().__init__(*args, **kwargs)
        self._config: Dict[str, Any] = {}

    def configure(self, **params) -> "ConfigMixin":
        """Configure routine parameters.

        This is a convenience method that sets configuration values.
        It's an alias for set_config() with a more fluent interface.

        Args:
            **params: Keyword arguments for configuration.

        Returns:
            Self for method chaining.

        Examples:
            >>> routine.configure(timeout=30, retries=3)
        """
        self._config.update(params)
        return self

    def get_param(self, key: str, default: Any = None) -> Any:
        """Get a configuration parameter value.

        This is a convenience method that retrieves configuration values.
        It's an alias for get_config() with a more semantic name.

        Args:
            key: Parameter name.
            default: Default value if key not found.

        Returns:
            Parameter value or default.
        """
        return self._config.get(key, default)

    def set_config(self, **kwargs) -> None:
        """Set configuration values in the _config dictionary.

        This is the recommended way to set routine configuration after object
        creation. All configuration values are stored in self._config and will
        be automatically serialized/deserialized.

        Args:
            **kwargs: Configuration key-value pairs to set.

        Examples:
            >>> routine.set_config(name="processor_1", timeout=30, retries=3)
        """
        self._config.update(kwargs)

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a configuration value from the _config dictionary.

        Args:
            key: Configuration key to retrieve.
            default: Default value to return if key doesn't exist.

        Returns:
            Configuration value if found, default value otherwise.
        """
        return self._config.get(key, default)

    def config(self) -> Dict[str, Any]:
        """Get a copy of the configuration dictionary.

        Returns:
            Copy of the _config dictionary. Modifications to the returned
            dictionary will not affect the original _config.
        """
        return self._config.copy()


class ExecutionMixin:
    """Mixin for event emission and slot management.

    Provides methods for emitting events, defining slots, and
    managing event-slot connections.

    Attributes:
        _slots: Dictionary of slot name to Slot object.
        _events: Dictionary of event name to Event object.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize ExecutionMixin.

        Note: This is a mixin, called via super().__init__() from Routine.
        """
        super().__init__(*args, **kwargs)
        self._slots: Dict[str, Slot] = {}
        self._events: Dict[str, Event] = {}

    def define_slot(
        self,
        name: str,
        handler: Optional[Callable] = None,
        merge_strategy: str = "override",
    ) -> "Slot":
        """Define an input slot for receiving data from other routines.

        This method creates a new slot that can be connected to events from
        other routines. When data is received, it's merged with existing data
        according to the merge_strategy, then passed to the handler.

        Args:
            name: Slot name. Must be unique within this routine.
            handler: Handler function called when slot receives data.
            merge_strategy: Strategy for merging new data with existing data.

        Returns:
            Slot object.

        Raises:
            ValueError: If slot name already exists in this routine.

        Examples:
            >>> def my_handler(data):
            ...     print(data)
            >>> routine.define_slot("input", handler=my_handler)
        """
        if name in self._slots:
            raise ValueError(f"Slot '{name}' already exists in {self}")

        from routilux.slot import Slot

        slot = Slot(name, cast("Routine", self), handler, merge_strategy)
        self._slots[name] = slot
        return slot

    def define_event(self, name: str, output_params: Optional[List[str]] = None) -> "Event":
        """Define an output event for transmitting data to other routines.

        This method creates a new event that can be connected to slots in
        other routines. When you emit this event, the data is automatically
        sent to all connected slots.

        Args:
            name: Event name. Must be unique within this routine.
            output_params: Optional list of parameter names this event emits.

        Returns:
            Event object.

        Raises:
            ValueError: If event name already exists in this routine.

        Examples:
            >>> routine.define_event("output", output_params=["result", "status"])
        """
        if name in self._events:
            raise ValueError(f"Event '{name}' already exists in {self}")

        from routilux.event import Event

        event = Event(name, cast("Routine", self), output_params or [])
        self._events[name] = event
        return event

    def get_slot(self, name: str) -> Optional["Slot"]:
        """Get a slot by name.

        Args:
            name: Slot name.

        Returns:
            Slot object or None if not found.
        """
        return self._slots.get(name)

    def get_event(self, name: str) -> Optional["Event"]:
        """Get an event by name.

        Args:
            name: Event name.

        Returns:
            Event object or None if not found.
        """
        return self._events.get(name)

    def emit(self, event_name: str, flow: Optional["Flow"] = None, **kwargs) -> None:
        """Emit an event and send data to all connected slots.

        This method triggers the specified event and transmits the provided
        data to all slots connected to this event.

        Args:
            event_name: Name of the event to emit.
            flow: Optional Flow object for context.
            **kwargs: Data to transmit via the event.

        Raises:
            ValueError: If event_name does not exist in this routine.
        """
        if event_name not in self._events:
            raise ValueError(f"Event '{event_name}' does not exist in {self}")

        event = self._events[event_name]

        # If flow not provided, try to get from context
        if flow is None and hasattr(self, "_current_flow"):
            flow = getattr(self, "_current_flow", None)

        # Get job_state from context variable if not in kwargs
        # Note: event.emit() will pop job_state from kwargs, so we need to preserve it
        job_state = kwargs.get("job_state")
        if job_state is None:
            _current_job_state = _get_current_job_state()
            if _current_job_state is not None:
                job_state = _current_job_state.get(None)
                if job_state is not None:
                    kwargs["job_state"] = job_state

        # Emit event (this will create tasks and enqueue them)
        event.emit(flow=flow, **kwargs)

        # Record execution history if we have flow and job_state
        # Skip during serialization to avoid recursion
        if flow is not None and job_state is not None and not getattr(flow, "_serializing", False):
            routine_id = flow._get_routine_id(cast("Routine", self))
            if routine_id:
                # Create safe data copy for execution history
                safe_data = self._prepare_execution_data(kwargs)
                job_state.record_execution(routine_id, event_name, safe_data)

            # Record to execution tracker
            if flow.execution_tracker is not None:
                # Get all target routine IDs (there may be multiple connected slots)
                target_routine_ids = []
                event_obj = self._events.get(event_name)
                if event_obj and event_obj.connected_slots:
                    for slot in event_obj.connected_slots:
                        if slot.routine:
                            target_routine_ids.append(getattr(slot.routine, "_id", ""))

                # Use first target routine ID for tracker (or None if no connections)
                target_routine_id = target_routine_ids[0] if target_routine_ids else None
                flow.execution_tracker.record_event(
                    getattr(cast("Routine", self), "_id", ""), event_name, target_routine_id, kwargs
                )

    def _prepare_execution_data(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare data for execution history recording.

        Removes job_state and converts Serializable objects to strings
        to avoid circular references during serialization.

        Args:
            kwargs: Original keyword arguments from emit().

        Returns:
            Safe dictionary for execution history recording.
        """
        safe_data = {}
        from serilux import Serializable

        for k, v in kwargs.items():
            if k == "job_state":
                continue  # Skip job_state to avoid circular reference
            # Convert Serializable objects to strings to prevent recursion during serialization
            if isinstance(v, Serializable):
                safe_data[k] = str(v)
            else:
                safe_data[k] = v
        return safe_data

    def _extract_input_data(self, data: Any = None, **kwargs) -> Any:
        """Extract input data from slot parameters.

        This method provides a consistent way to extract data from slot inputs,
        handling various input patterns. It's particularly useful in slot handlers
        to simplify data extraction logic.

        Args:
            data: Direct data parameter (optional).
            **kwargs: Additional keyword arguments from slot.

        Returns:
            Extracted data value.
        """
        if data is not None:
            return data

        if "data" in kwargs:
            return kwargs["data"]

        if len(kwargs) == 1:
            return list(kwargs.values())[0]

        if len(kwargs) > 0:
            return kwargs

        return {}


class LifecycleMixin:
    """Mixin for state management and lifecycle hooks.

    Provides methods for lifecycle hooks (before/after execution)
    and state management integration.

    Attributes:
        _before_hooks: List of functions to call before execution.
        _after_hooks: List of functions to call after execution.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize LifecycleMixin.

        Note: This is a mixin, called via super().__init__() from Routine.
        """
        super().__init__(*args, **kwargs)
        self._before_hooks: List[Callable[[], None]] = []
        self._after_hooks: List[Callable[[JobState], None]] = []

    def before_execution(self, hook: Callable[[], None]) -> "LifecycleMixin":
        """Register a hook to run before routine execution.

        Args:
            hook: Function to call before execution.

        Returns:
            Self for method chaining.

        Examples:
            >>> def setup():
            ...     print("Setting up...")
            >>> routine.before_execution(setup)
        """
        self._before_hooks.append(hook)
        return self

    def after_execution(self, hook: Callable[["JobState"], None]) -> "LifecycleMixin":
        """Register a hook to run after routine execution.

        Args:
            hook: Function to call after execution, receives JobState.

        Returns:
            Self for method chaining.

        Examples:
            >>> def cleanup(state):
            ...     print(f"Done with status: {state.status}")
            >>> routine.after_execution(cleanup)
        """
        self._after_hooks.append(hook)
        return self

    def _run_before_hooks(self) -> None:
        """Run all before_execution hooks (internal)."""
        for hook in self._before_hooks:
            hook()

    def _run_after_hooks(self, job_state: "JobState") -> None:
        """Run all after_execution hooks (internal)."""
        for hook in self._after_hooks:
            hook(job_state)


__all__ = [
    "ConfigMixin",
    "ExecutionMixin",
    "LifecycleMixin",
]
