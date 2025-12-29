"""
Routine base class.

Improved Routine mechanism supporting slots (input slots) and events (output events).
"""

from __future__ import annotations
from typing import Dict, Any, Callable, Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from routilux.slot import Slot
    from routilux.event import Event
    from routilux.flow import Flow
    from routilux.error_handler import ErrorHandler, ErrorStrategy

from serilux import register_serializable, Serializable


@register_serializable
class Routine(Serializable):
    """Improved Routine base class with enhanced capabilities.

    Features:
    - Support for slots (input slots)
    - Support for events (output events)
    - Statistics dictionary (_stats) for tracking execution metrics
    - Configuration dictionary (_config) for storing routine-specific settings

    Statistics Management (_stats):
        The _stats dictionary is used to track runtime statistics and execution
        metrics. It is automatically serialized/deserialized and can be accessed
        via stats(), get_stat(), set_stat(), and increment_stat() methods.

        Common statistics tracked automatically:
        - "called": Boolean indicating if routine has been called
        - "call_count": Number of times routine has been executed
        - "emitted_events": List of events emitted with their data

        Subclasses can track custom statistics:
        - Processing counts, error counts, timing information, etc.
        - Use set_stat() or increment_stat() for type-safe updates
        - Direct access via self._stats is also supported

    Configuration Management (_config):
        The _config dictionary stores routine-specific configuration that should
        persist across serialization. Use set_config() and get_config() methods
        for convenient access.

    Important Constraints:
        - Routines MUST NOT accept constructor parameters (except self).
          This is required for proper serialization/deserialization.
        - All configuration should be stored in the _config dictionary.
        - All statistics should be stored in the _stats dictionary.
        - Both _config and _stats are automatically included in serialization.

    Examples:
        Correct usage with configuration and statistics:
            >>> class MyRoutine(Routine):
            ...     def __init__(self):
            ...         super().__init__()
            ...         # Set configuration
            ...         self.set_config(name="my_routine", timeout=30)
            ...         # Initialize statistics
            ...         self.set_stat("processed_count", 0)
            ...         self.set_stat("error_count", 0)
            ...
            ...     def __call__(self, **kwargs):
            ...         super().__call__(**kwargs)
            ...         # Track custom statistics
            ...         self.increment_stat("processed_count")
            ...         # Use configuration
            ...         timeout = self.get_config("timeout", default=10)

        Incorrect usage (will break serialization):
            >>> class BadRoutine(Routine):
            ...     def __init__(self, name: str):  # ❌ Don't do this!
            ...         super().__init__()
            ...         self.name = name  # Use _config instead!
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
        self._slots: Dict[str, "Slot"] = {}
        self._events: Dict[str, "Event"] = {}

        # Statistics dictionary for tracking execution metrics and runtime statistics
        # Automatically tracked statistics:
        #   - "called": Boolean, set to True when routine is executed
        #   - "call_count": Integer, incremented each time routine is called
        #   - "emitted_events": List of dicts, records each event emission with data
        # Subclasses can add custom statistics like:
        #   - Processing counts, error counts, timing information, etc.
        # Use set_stat(), get_stat(), increment_stat() methods for type-safe access
        # Direct access via self._stats[key] is also supported
        self._stats: Dict[str, Any] = {}

        # Configuration dictionary for storing routine-specific settings
        # All configuration values are automatically serialized/deserialized
        # Use set_config() and get_config() methods for convenient access
        self._config: Dict[str, Any] = {}

        # Error handler for this routine (optional)
        # If set, this routine will use its own error handler instead of the flow's default
        # Priority: routine-level error handler > flow-level error handler > default (STOP)
        self._error_handler: Optional["ErrorHandler"] = None

        # Register serializable fields
        # _slots and _events are included - base class will automatically serialize/deserialize them
        # We only need to restore routine references after deserialization
        self.add_serializable_fields(
            ["_id", "_stats", "_config", "_error_handler", "_slots", "_events"]
        )

    def __repr__(self) -> str:
        """Return string representation of the Routine."""
        return f"{self.__class__.__name__}[{self._id}]"

    def define_slot(
        self, name: str, handler: Optional[Callable] = None, merge_strategy: str = "override"
    ) -> "Slot":
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
                Possible values:

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
        from routilux.slot import Slot

        slot = Slot(name, self, handler, merge_strategy)
        self._slots[name] = slot
        return slot

    def define_event(self, name: str, output_params: Optional[List[str]] = None) -> "Event":
        """Define an output event for transmitting data to other routines.

        This method creates a new event that can be connected to slots in
        other routines. When you emit this event, the data is automatically
        sent to all connected slots.

        Event Emission:
            Use emit() method to trigger the event and send data:
            - ``emit(event_name, **kwargs)`` - passes kwargs as data
            - Data is sent to all connected slots via their connections
            - Parameter mapping (from Flow.connect()) is applied during transmission

        Args:
            name: Event name. Must be unique within this routine.
                Used to identify the event when connecting via Flow.connect().
                Example: "output", "result", "error"
            output_params: Optional list of parameter names this event emits.
                This is for documentation purposes only - it doesn't enforce
                what parameters can be emitted. Helps document the event's API.
                Example: ["result", "status", "metadata"]

        Returns:
            Event object. You typically don't need to use this, but it can be
            useful for programmatic access or advanced use cases.

        Raises:
            ValueError: If event name already exists in this routine.

        Examples:
            Basic event definition:
                >>> class MyRoutine(Routine):
                ...     def __init__(self):
                ...         super().__init__()
                ...         self.output_event = self.define_event("output", ["result", "status"])
                ...
                ...     def __call__(self):
                ...         self.emit("output", result="success", status=200)

            Event with documentation:
                >>> routine.define_event("data_ready", output_params=["data", "timestamp", "source"])
                >>> # Documents that this event emits these parameters

            Multiple events:
                >>> routine.define_event("success", ["result"])
                >>> routine.define_event("error", ["error_code", "message"])
                >>> # Can emit different events for different outcomes
        """
        if name in self._events:
            raise ValueError(f"Event '{name}' already exists in {self}")

        # Lazy import to avoid circular dependency
        from routilux.event import Event

        event = Event(name, self, output_params or [])
        self._events[name] = event
        return event

    def emit(self, event_name: str, flow: Optional["Flow"] = None, **kwargs) -> None:
        """Emit an event and send data to all connected slots.

        This method triggers the specified event and transmits the provided
        data to all slots connected to this event. The data transmission
        respects parameter mappings defined in Flow.connect().

        Data Flow:
            1. Event is emitted with ``**kwargs`` data
            2. For each connected slot:
               a. Parameter mapping is applied (if defined in Flow.connect())
               b. Data is merged with slot's existing data (according to merge_strategy)
               c. Slot's handler is called with the merged data
            3. In concurrent mode, handlers may execute in parallel threads

        Flow Context:
            If flow is not provided, the method attempts to get it from the
            routine's context (_current_flow). This works automatically when
            the routine is executed within a Flow context. For standalone
            usage or testing, you may need to provide the flow explicitly.

        Args:
            event_name: Name of the event to emit. Must be defined using
                define_event() before calling this method.
            flow: Optional Flow object. Used for:
                - Finding Connection objects for parameter mapping
                - Recording execution history
                - Tracking event emissions
                If None, attempts to get from routine context.
                Provide explicitly for standalone usage or testing.
            ``**kwargs``: Data to transmit via the event. These keyword arguments
                become the data dictionary sent to connected slots.
                Example: emit("output", result="success", count=42)
                sends {"result": "success", "count": 42} to connected slots.

        Raises:
            ValueError: If event_name does not exist in this routine.
                Define the event first using define_event().

        Examples:
            Basic emission:
                >>> routine.define_event("output", ["result"])
                >>> routine.emit("output", result="data", status="ok")
                >>> # Sends {"result": "data", "status": "ok"} to connected slots

            Emission with flow context:
                >>> routine.emit("output", flow=my_flow, data="value")
                >>> # Explicitly provides flow for parameter mapping

            Multiple parameters:
                >>> routine.emit("result",
                ...              success=True,
                ...              data={"key": "value"},
                ...              timestamp=time.time(),
                ...              metadata={"source": "processor"})
                >>> # All parameters are sent to connected slots
        """
        if event_name not in self._events:
            raise ValueError(f"Event '{event_name}' does not exist in {self}")

        event = self._events[event_name]

        # If flow not provided, try to get from context
        if flow is None and hasattr(self, "_current_flow"):
            flow = getattr(self, "_current_flow", None)

        event.emit(flow=flow, **kwargs)

        # Track event emission in statistics
        # This records each event emission for monitoring and debugging purposes
        # The emitted_events list contains dictionaries with event name and data
        # This is useful for:
        #   - Debugging event flow
        #   - Monitoring routine behavior
        #   - Analyzing execution patterns
        if "emitted_events" not in self._stats:
            self._stats["emitted_events"] = []
        self._stats["emitted_events"].append({"event": event_name, "data": kwargs})

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

                flow.execution_tracker.record_event(self._id, event_name, target_routine_id, kwargs)

    def stats(self) -> Dict[str, Any]:
        """Return a copy of the statistics dictionary.

        This method returns a snapshot of all statistics tracked by this routine.
        The returned dictionary is a copy, so modifications won't affect the
        original _stats dictionary.

        Returns:
            Copy of the _stats dictionary containing all tracked statistics.
            Common keys include:
            - "called": Boolean indicating if routine has been executed
            - "call_count": Number of times routine has been called
            - "emitted_events": List of event emission records
            - Custom statistics added by subclasses

        Examples:
            >>> routine = MyRoutine()
            >>> routine()  # Execute routine
            >>> stats = routine.stats()
            >>> print(stats["call_count"])  # 1
            >>> print(stats["called"])  # True
            >>> print(len(stats.get("emitted_events", [])))  # Number of events emitted
        """
        return self._stats.copy()

    def set_stat(self, key: str, value: Any) -> None:
        """Set a statistics value in the _stats dictionary.

        This is the recommended way to set or update statistics. All statistics
        are automatically serialized/deserialized.

        Args:
            key: Statistics key name.
            value: Statistics value to set. Can be any serializable type.

        Examples:
            >>> routine = MyRoutine()
            >>> routine.set_stat("processed_count", 0)
            >>> routine.set_stat("last_processed_time", time.time())
            >>> routine.set_stat("status", "active")

            >>> # You can also set stats directly:
            >>> routine._stats["custom_metric"] = 42
        """
        self._stats[key] = value

    def get_stat(self, key: str, default: Any = None) -> Any:
        """Get a statistics value from the _stats dictionary.

        Args:
            key: Statistics key to retrieve.
            default: Default value to return if key doesn't exist.

        Returns:
            Statistics value if found, default value otherwise.

        Examples:
            >>> routine = MyRoutine()
            >>> routine.set_stat("processed_count", 10)
            >>> count = routine.get_stat("processed_count", default=0)  # Returns 10
            >>> errors = routine.get_stat("error_count", default=0)  # Returns 0
        """
        return self._stats.get(key, default)

    def increment_stat(self, key: str, amount: int = 1) -> int:
        """Increment a numeric statistics value.

        This is a convenience method for incrementing counters. If the key
        doesn't exist, it's initialized to 0 before incrementing.

        Args:
            key: Statistics key to increment.
            amount: Amount to increment by (default: 1).

        Returns:
            The new value after incrementing.

        Examples:
            >>> routine = MyRoutine()
            >>> routine.increment_stat("processed_count")  # Returns 1
            >>> routine.increment_stat("processed_count")  # Returns 2
            >>> routine.increment_stat("processed_count", amount=5)  # Returns 7
            >>> routine.get_stat("processed_count")  # 7
        """
        if key not in self._stats:
            self._stats[key] = 0
        self._stats[key] += amount
        return self._stats[key]

    def reset_stats(self, keys: Optional[List[str]] = None) -> None:
        """Reset statistics values.

        Args:
            keys: List of statistic keys to reset. If None, resets all statistics
                except "emitted_events" (which is typically preserved for history).
                If empty list, no statistics are reset.

        Examples:
            >>> routine = MyRoutine()
            >>> routine.set_stat("count", 10)
            >>> routine.set_stat("errors", 5)
            >>> routine.reset_stats(["count"])  # Reset only "count"
            >>> routine.get_stat("count")  # None or default
            >>> routine.get_stat("errors")  # Still 5

            >>> routine.reset_stats()  # Reset all except "emitted_events"
        """
        if keys is None:
            # Reset all statistics except emitted_events (preserve history)
            emitted_events = self._stats.get("emitted_events", [])
            self._stats.clear()
            if emitted_events:
                self._stats["emitted_events"] = emitted_events
        else:
            # Reset only specified keys
            for key in keys:
                if key in self._stats:
                    del self._stats[key]

    def _extract_input_data(self, data: Any = None, **kwargs) -> Any:
        """Extract input data from slot parameters.

        This method provides a consistent way to extract data from slot inputs,
        handling various input patterns. It's particularly useful in slot handlers
        to simplify data extraction logic.

        Input patterns handled:
        - Direct data parameter: Returns data as-is
        - 'data' key in kwargs: Returns kwargs["data"]
        - Single value in kwargs: Returns the single value
        - Multiple values in kwargs: Returns the entire kwargs dict
        - Empty input: Returns empty dict

        Args:
            data: Direct data parameter (optional).
            **kwargs: Additional keyword arguments from slot.

        Returns:
            Extracted data value. Type depends on input.

        Examples:
            >>> # In a slot handler
            >>> def _handle_input(self, data=None, **kwargs):
            ...     # Extract data using helper
            ...     data = self._extract_input_data(data, **kwargs)
            ...     # Process data...

            >>> # Direct parameter
            >>> self._extract_input_data("text")
            'text'

            >>> # From kwargs
            >>> self._extract_input_data(None, data="text")
            'text'

            >>> # Single value in kwargs
            >>> self._extract_input_data(None, text="value")
            'value'

            >>> # Multiple values
            >>> self._extract_input_data(None, a=1, b=2)
            {'a': 1, 'b': 2}
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

    def _track_operation(self, operation_name: str, success: bool = True, **metadata) -> None:
        """Track operation statistics with metadata.

        This method provides a consistent way to track operations across routines,
        automatically maintaining success/failure counts and operation history.

        Args:
            operation_name: Name of the operation (e.g., "processing", "validation").
            success: Whether operation succeeded (default: True).
            **metadata: Additional metadata to store in operation history.

        Examples:
            >>> # Track successful operation
            >>> self._track_operation("processing", success=True, items_processed=10)

            >>> # Track failed operation with error info
            >>> self._track_operation("validation", success=False, error="Invalid format")

            >>> # Access statistics
            >>> stats = self.stats()
            >>> print(stats["total_processing"])  # Total operations
            >>> print(stats["successful_processing"])  # Successful operations
            >>> print(stats["processing_history"])  # Operation history with metadata
        """
        self.increment_stat(f"total_{operation_name}")
        if success:
            self.increment_stat(f"successful_{operation_name}")
        else:
            self.increment_stat(f"failed_{operation_name}")

        if metadata:
            history_key = f"{operation_name}_history"
            history = self._stats.get(history_key, [])
            history.append(metadata)
            self._stats[history_key] = history

    def __call__(self, **kwargs) -> None:
        """Execute routine (deprecated - use slot handlers instead).

        .. deprecated::
            Direct calling of routines is deprecated. Routines should be executed
            through slot handlers. Entry routines should define a "trigger" slot
            that will be called by Flow.execute().

        This method is kept for backward compatibility but should not be used
        in new code. Instead, define slot handlers that contain your execution logic.

        Args:
            ``**kwargs``: Parameters passed to the routine.

        Note:
            The base implementation automatically updates statistics:
            - Sets "called" to True
            - Increments "call_count" by 1

            However, in the new architecture, routines should be triggered through
            slots, and statistics should be tracked in slot handlers.

        Examples:
            Old way (deprecated):
            >>> class MyRoutine(Routine):
            ...     def __call__(self, **kwargs):
            ...         # This is deprecated
            ...         pass

            New way (recommended):
            >>> class MyRoutine(Routine):
            ...     def __init__(self):
            ...         super().__init__()
            ...         # Define trigger slot for entry routine
            ...         self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
            ...
            ...     def _handle_trigger(self, **kwargs):
            ...         # Execution logic here
            ...         self.increment_stat("custom_operations")
        """
        # Track execution statistics
        # Mark routine as having been called at least once
        self._stats["called"] = True

        # Increment call counter to track how many times routine has been executed
        # This is useful for monitoring routine usage and performance analysis
        if "call_count" not in self._stats:
            self._stats["call_count"] = 0
        self._stats["call_count"] += 1

        # Note: In the new architecture, routines should be executed through slot handlers
        # This method is kept for compatibility but should not be overridden in new code
        pass

    def get_slot(self, name: str) -> Optional["Slot"]:
        """Get specified slot.

        Args:
            name: Slot name.

        Returns:
            Slot object if found, None otherwise.
        """
        return self._slots.get(name)

    def get_event(self, name: str) -> Optional["Event"]:
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
            ``**kwargs``: Configuration key-value pairs to set. These will be stored
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

    def set_error_handler(self, error_handler: "ErrorHandler") -> None:
        """Set error handler for this routine.

        When an error occurs in this routine, the routine-level error handler
        takes priority over the flow-level error handler. If no routine-level
        error handler is set, the flow-level error handler (if any) will be used.

        Args:
            error_handler: ErrorHandler instance to use for this routine.

        Examples:
            >>> from routilux import ErrorHandler, ErrorStrategy
            >>> routine = MyRoutine()
            >>> routine.set_error_handler(ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=3))
        """
        self._error_handler = error_handler

    def get_error_handler(self) -> Optional["ErrorHandler"]:
        """Get error handler for this routine.

        Returns:
            ErrorHandler instance if set, None otherwise.
        """
        return self._error_handler

    def set_as_optional(self, strategy: "ErrorStrategy" = None) -> None:
        """Mark this routine as optional (failures are tolerated).

        This is a convenience method that sets up an error handler with CONTINUE
        strategy by default, allowing the routine to fail without stopping the flow.

        Args:
            strategy: Error handling strategy. If None, defaults to CONTINUE.
                Can be ErrorStrategy.CONTINUE or ErrorStrategy.SKIP.

        Examples:
            >>> from routilux import ErrorStrategy
            >>> optional_routine = OptionalRoutine()
            >>> optional_routine.set_as_optional()  # Uses CONTINUE by default
            >>> optional_routine.set_as_optional(ErrorStrategy.SKIP)  # Use SKIP instead
        """
        from routilux.error_handler import ErrorHandler, ErrorStrategy as ES

        if strategy is None:
            strategy = ES.CONTINUE
        self.set_error_handler(ErrorHandler(strategy=strategy, is_critical=False))

    def set_as_critical(
        self, max_retries: int = 3, retry_delay: float = 1.0, retry_backoff: float = 2.0
    ) -> None:
        """Mark this routine as critical (must succeed, retry on failure).

        This is a convenience method that sets up an error handler with RETRY
        strategy and is_critical=True. If all retries fail, the flow will fail.

        Args:
            max_retries: Maximum number of retry attempts.
            retry_delay: Initial retry delay in seconds.
            retry_backoff: Retry delay backoff multiplier.

        Examples:
            >>> critical_routine = CriticalRoutine()
            >>> critical_routine.set_as_critical(max_retries=5, retry_delay=2.0)
        """
        from routilux.error_handler import ErrorHandler, ErrorStrategy

        self.set_error_handler(
            ErrorHandler(
                strategy=ErrorStrategy.RETRY,
                max_retries=max_retries,
                retry_delay=retry_delay,
                retry_backoff=retry_backoff,
                is_critical=True,
            )
        )

    def serialize(self) -> Dict[str, Any]:
        """Serialize Routine, including class information and state.

        Returns:
            Serialized dictionary.
        """
        # Let base class handle all registered fields including _slots and _events
        # Base class automatically handles Serializable objects in dicts
        data = super().serialize()

        return data

    def deserialize(self, data: Dict[str, Any], registry: Optional[Any] = None) -> None:
        """Deserialize Routine.

        Args:
            data: Serialized data dictionary.
            registry: Optional ObjectRegistry for deserializing callables.
        """

        # Let base class handle all registered fields including _slots and _events
        # Base class automatically deserializes Serializable objects in dicts
        super().deserialize(data, registry=registry)

        # Restore routine references for slots and events (required after deserialization)
        if hasattr(self, "_slots") and self._slots:
            for slot in self._slots.values():
                slot.routine = self

        if hasattr(self, "_events") and self._events:
            for event in self._events.values():
                event.routine = self
