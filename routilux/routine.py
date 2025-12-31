"""
Routine base class.

Improved Routine mechanism supporting slots (input slots) and events (output events).
"""

from __future__ import annotations
from typing import Dict, Any, Callable, Optional, List, TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from routilux.slot import Slot
    from routilux.event import Event
    from routilux.flow import Flow
    from routilux.error_handler import ErrorHandler, ErrorStrategy
    from routilux.job_state import JobState

from serilux import register_serializable, Serializable


class ExecutionContext(NamedTuple):
    """Execution context containing flow, job_state, and routine_id.

    This is returned by Routine.get_execution_context() to provide convenient
    access to execution-related handles during routine execution.

    Attributes:
        flow: The Flow object managing this execution.
        job_state: The JobState object tracking this execution's state.
        routine_id: The string ID of this routine in the flow.
    """

    flow: "Flow"
    job_state: "JobState"
    routine_id: str


@register_serializable
class Routine(Serializable):
    """Improved Routine base class with enhanced capabilities.

    Features:
    - Support for slots (input slots)
    - Support for events (output events)
    - Configuration dictionary (_config) for storing routine-specific settings

    Configuration Management (_config):
        The _config dictionary stores routine-specific configuration that should
        persist across serialization. Use set_config() and get_config() methods
        for convenient access.

    Important Constraints:
        - Routines MUST NOT accept constructor parameters (except self).
          This is required for proper serialization/deserialization.
        - All configuration should be stored in the _config dictionary.
        - _config is automatically included in serialization.
        - **During execution, routines MUST NOT modify any instance variables.**
        - **All execution-related state should be stored in JobState.**
        - Routines can only READ from _config during execution.
        - Routines can WRITE to JobState (via job_state.update_routine_state(), etc.).

    Execution State Management:
        During execution, routines should:
        - Read configuration from _config (via get_config())
        - Write execution state to JobState (via job_state.update_routine_state())
        - Store shared data in JobState.shared_data
        - Append logs to JobState.shared_log
        - Send outputs via Routine.send_output() (which uses JobState.send_output())

    Why This Constraint?
        The same routine object can be used by multiple concurrent executions.
        Modifying instance variables during execution would cause data corruption
        and break execution isolation. All execution-specific state must be stored
        in JobState, which is unique per execution.

    Examples:
        Correct usage with configuration:
            >>> class MyRoutine(Routine):
            ...     def __init__(self):
            ...         super().__init__()
            ...         # Set configuration
            ...         self.set_config(name="my_routine", timeout=30)
            ...
            ...     def process(self, **kwargs):
            ...         # Use configuration
            ...         timeout = self.get_config("timeout", default=10)
            ...         # Store execution state in JobState
            ...         flow = getattr(self, "_current_flow", None)
            ...         if flow:
            ...             job_state = getattr(flow._current_execution_job_state, "value", None)
            ...             if job_state:
            ...                 routine_id = flow._get_routine_id(self)
            ...                 job_state.update_routine_state(routine_id, {"processed": True})

        Incorrect usage (will break serialization):
            >>> class BadRoutine(Routine):
            ...     def __init__(self, name: str):  # ❌ Don't do this!
            ...         super().__init__()
            ...         self.name = name  # Use _config instead!

        Incorrect usage (will break execution isolation):
            >>> class BadRoutine(Routine):
            ...     def process(self, **kwargs):
            ...         self.counter += 1  # ❌ Don't modify instance variables!
            ...         self.data.append(kwargs)  # ❌ Don't modify instance variables!
            ...         # Use JobState instead:
            ...         job_state = getattr(flow._current_execution_job_state, 'value', None)
            ...         if job_state:
            ...             job_state.update_routine_state(routine_id, {'counter': counter + 1})
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
        self.add_serializable_fields(["_id", "_config", "_error_handler", "_slots", "_events"])

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

        # If flow exists, record execution history
        # Note: JobState is passed through tasks, so we can't access it directly here
        # Execution history is recorded when tasks are created in event.emit()
        # This is handled in the event emission logic
        if flow is not None:
            # Use get_execution_context() for convenient access
            ctx = self.get_execution_context()
            if ctx is not None:
                ctx.job_state.record_execution(ctx.routine_id, event_name, kwargs)

            # Record to execution tracker
            if flow.execution_tracker is not None:
                # Find target routine (via connected slots)
                target_routine_id = None
                event_obj = self._events.get(event_name)
                if event_obj and event_obj.connected_slots:
                    # Get routine of first connected slot
                    target_routine_id = event_obj.connected_slots[0].routine._id

                flow.execution_tracker.record_event(self._id, event_name, target_routine_id, kwargs)

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

    def __call__(self, **kwargs) -> None:
        r"""Execute routine (deprecated - use slot handlers instead).

        .. deprecated::
            Direct calling of routines is deprecated. Routines should be executed
            through slot handlers. Entry routines should define a "trigger" slot
            that will be called by Flow.execute().

        This method is kept for backward compatibility but should not be used
        in new code. Instead, define slot handlers that contain your execution logic.

        Args:
            ``**kwargs``: Parameters passed to the routine.

        Note:
            In the new architecture, routines should be triggered through
            slots, and execution state should be tracked in JobState.

        Examples:
            Old way (deprecated):
            >>> class MyRoutine(Routine):
            ...     def __call__(self, \*\*kwargs):
            ...         # This is deprecated
            ...         pass

            New way (recommended):
            >>> class MyRoutine(Routine):
            ...     def __init__(self):
            ...         super().__init__()
            ...         # Define trigger slot for entry routine
            ...         self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
            ...
            ...     def _handle_trigger(self, \*\*kwargs):
            ...         # Execution logic here
            ...         # Store execution state in JobState if needed
        """
        # Note: In the new architecture, routines should be executed through slot handlers
        # This method is kept for compatibility but should not be overridden in new code
        # Execution state should be tracked in JobState, not routine._stats
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

    def get_execution_context(self) -> Optional[ExecutionContext]:
        """Get execution context (flow, job_state, routine_id).

        This method provides convenient access to execution-related handles
        during routine execution. It automatically retrieves the flow from
        routine context, job_state from thread-local storage, and routine_id
        from the flow's routine mapping.

        Returns:
            ExecutionContext object containing (flow, job_state, routine_id)
            if in execution context, None otherwise.

        Examples:
            Basic usage:
                >>> ctx = self.get_execution_context()
                >>> if ctx:
                ...     # Access flow, job_state, and routine_id
                ...     ctx.flow
                ...     ctx.job_state
                ...     ctx.routine_id
                ...     # Update routine state
                ...     ctx.job_state.update_routine_state(ctx.routine_id, {"processed": True})

            Unpacking:
                >>> ctx = self.get_execution_context()
                >>> if ctx:
                ...     flow, job_state, routine_id = ctx
                ...     job_state.update_routine_state(routine_id, {"count": 1})

        Note:
            This method only works when the routine is executing within a Flow
            context. For standalone usage or testing, it will return None.
        """
        # Get flow from routine context
        flow = getattr(self, "_current_flow", None)
        if flow is None:
            return None

        # Get job_state from thread-local storage
        job_state = getattr(flow._current_execution_job_state, "value", None)
        if job_state is None:
            return None

        # Get routine_id from flow
        routine_id = flow._get_routine_id(self)
        if routine_id is None:
            return None

        return ExecutionContext(flow, job_state, routine_id)

    def emit_deferred_event(self, event_name: str, **kwargs) -> None:
        """Emit a deferred event that will be processed when the flow is resumed.

        This method is similar to emit(), but instead of immediately emitting
        the event, it stores the event information in JobState.deferred_events.
        When the flow is resumed (via flow.resume()), these deferred events
        will be automatically emitted.

        This is useful for scenarios where you want to pause the execution
        and emit events after resuming, such as in LLM agent workflows where
        you need to wait for user input.

        Args:
            event_name: Name of the event to emit (must be defined via define_event()).
            **kwargs: Data to pass to the event.

        Raises:
            RuntimeError: If not in execution context (no flow/job_state available).

        Examples:
            Basic usage:
                >>> class MyRoutine(Routine):
                ...     def process(self, **kwargs):
                ...         # Emit a deferred event
                ...         self.emit_deferred_event("user_input_required", question="What is your name?")
                ...         # Pause the execution
                ...         ctx = self.get_execution_context()
                ...         if ctx:
                ...             ctx.flow.pause(ctx.job_state, reason="Waiting for user input")

            After resume:
                >>> # When flow.resume() is called, deferred events are automatically emitted
                >>> flow.resume(job_state)
                >>> # The "user_input_required" event will be emitted automatically

        Note:
            - The event must be defined using define_event() before calling this method.
            - Deferred events are stored in JobState and are serialized/deserialized
              along with the JobState.
            - Deferred events are emitted in the order they were added.
        """
        ctx = self.get_execution_context()
        if ctx is None:
            raise RuntimeError(
                "Cannot emit deferred event: not in execution context. "
                "This method can only be called during flow execution."
            )

        ctx.job_state.add_deferred_event(ctx.routine_id, event_name, kwargs)

    def send_output(self, output_type: str, **data) -> None:
        """Send output data via JobState output handler.

        This is a convenience method that automatically gets the execution
        context and calls job_state.send_output(). It provides a simple way
        to send execution-specific output data (not events) to output handlers
        like console, queue, or custom handlers.

        Args:
            output_type: Type of output (e.g., 'user_data', 'status', 'result').
            **data: Output data dictionary (user-defined structure).

        Raises:
            RuntimeError: If not in execution context (no flow/job_state available).

        Examples:
            Basic usage:
                >>> class MyRoutine(Routine):
                ...     def process(self, **kwargs):
                ...         # Send output data
                ...         self.send_output("user_data", message="Processing started", count=10)
                ...         # Process data...
                ...         self.send_output("result", processed_items=5, status="success")

            With output handler:
                >>> from routilux import QueueOutputHandler
                >>> job_state = JobState(flow_id="my_flow")
                >>> job_state.set_output_handler(QueueOutputHandler())
                >>> # Now all send_output() calls will be sent to the queue

        Note:
            - This is different from emit() which sends events to connected slots.
            - Output is sent to the output_handler set on JobState.
            - Output is also logged to job_state.output_log for persistence.
            - If no output_handler is set, output is only logged (not sent anywhere).
        """
        ctx = self.get_execution_context()
        if ctx is None:
            raise RuntimeError(
                "Cannot send output: not in execution context. "
                "This method can only be called during flow execution."
            )

        ctx.job_state.send_output(ctx.routine_id, output_type, data)

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
