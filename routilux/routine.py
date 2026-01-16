"""
Routine base class.

Improved Routine mechanism supporting slots (input slots) and events (output events).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, NamedTuple, Optional, TypeVar

T = TypeVar("T")
from contextvars import ContextVar  # noqa: E402

if TYPE_CHECKING:
    from routilux.error_handler import ErrorHandler, ErrorStrategy
    from routilux.event import Event
    from routilux.flow import Flow
    from routilux.job_state import JobState
    from routilux.slot import Slot

from serilux import Serializable, register_serializable  # noqa: E402

# Context variable for thread-safe job_state access
# Each execution context has its own value, even in the same thread
_current_job_state: ContextVar[JobState | None] = ContextVar("_current_job_state", default=None)


class ExecutionContext(NamedTuple):
    """Execution context containing flow, job_state, and routine_id.

    This is returned by Routine.get_execution_context() to provide convenient
    access to execution-related handles during routine execution.

    Attributes:
        flow: The Flow object managing this execution.
        job_state: The JobState object tracking this execution's state.
        routine_id: The string ID of this routine in the flow.
    """

    flow: Flow
    job_state: JobState
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
        self._slots: dict[str, Slot] = {}
        self._events: dict[str, Event] = {}

        # Configuration dictionary for storing routine-specific settings
        # All configuration values are automatically serialized/deserialized
        # Use set_config() and get_config() methods for convenient access
        self._config: dict[str, Any] = {}

        # Error handler for this routine (optional)
        # Priority: routine-level error handler > flow-level error handler > default (STOP)
        self._error_handler: ErrorHandler | None = None

        # Activation policy and logic (new design)
        self._activation_policy: Callable | None = None
        self._logic: Callable | None = None

        # Register serializable fields
        # _slots and _events are included - base class automatically serializes/deserializes them
        # Note: _activation_policy and _logic are callables, handled by serilux
        self.add_serializable_fields(["_id", "_config", "_error_handler", "_slots", "_events", "_activation_policy", "_logic"])

    def __repr__(self) -> str:
        """Return string representation of the Routine."""
        return f"{self.__class__.__name__}[{self._id}]"

    def define_slot(
        self, name: str, max_queue_length: int = 1000, watermark: float = 0.8
    ) -> Slot:
        """Define an input slot for receiving data from other routines.

        This method creates a new slot that can be connected to events from
        other routines. Data is enqueued in the slot's queue when events are emitted.

        Args:
            name: Slot name. Must be unique within this routine. Used to
                identify the slot when connecting events.
            max_queue_length: Maximum number of data points in the queue.
                Default: 1000
            watermark: Watermark threshold (0.0 to 1.0). When queue reaches
                this percentage of max_queue_length, consumed data is cleared.
                Default: 0.8 (80%)

        Returns:
            Slot object that can be connected to events from other routines.

        Raises:
            ValueError: If slot name already exists in this routine.

        Examples:
            Basic slot definition:
                >>> routine = MyRoutine()
                >>> slot = routine.define_slot("input")

            Custom queue size:
                >>> slot = routine.define_slot("input", max_queue_length=100, watermark=0.7)
        """
        if name in self._slots:
            raise ValueError(f"Slot '{name}' already exists in {self}")

        # Lazy import to avoid circular dependency
        from routilux.slot import Slot

        slot = Slot(name, self, max_queue_length=max_queue_length, watermark=watermark)
        self._slots[name] = slot
        return slot

    def define_event(self, name: str, output_params: list[str] | None = None) -> Event:
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

    def emit(self, event_name: str, runtime=None, job_state=None, **kwargs) -> None:
        """Emit an event and send data to all connected slots.

        This method triggers the specified event and routes it through Runtime
        to connected slots. The Runtime handles event routing and slot enqueueing.

        Args:
            event_name: Name of the event to emit. Must be defined using
                define_event() before calling this method.
            runtime: Optional Runtime object. If None, attempts to get from context.
            job_state: Optional JobState object. If None, attempts to get from context.
            ``**kwargs``: Data to transmit via the event.

        Raises:
            ValueError: If event_name does not exist in this routine.
            RuntimeError: If runtime or job_state cannot be determined.

        Examples:
            Basic emission:
                >>> routine.define_event("output", ["result"])
                >>> routine.emit("output", runtime=runtime, job_state=job_state, result="data")
        """
        if event_name not in self._events:
            raise ValueError(f"Event '{event_name}' does not exist in {self}")

        event = self._events[event_name]

        # Get runtime and job_state from context if not provided
        if runtime is None:
            # Try to get from context (stored by Runtime)
            runtime = getattr(self, "_current_runtime", None)
        if runtime is None:
            raise RuntimeError(
                "Runtime is required for emit(). "
                "Provide runtime parameter or ensure routine is executing within Runtime context."
            )

        if job_state is None:
            job_state = _current_job_state.get(None)
        if job_state is None:
            raise RuntimeError(
                "JobState is required for emit(). "
                "Provide job_state parameter or ensure routine is executing within Runtime context."
            )

        # Emit event through Runtime
        event.emit(runtime=runtime, job_state=job_state, **kwargs)

    def _prepare_execution_data(self, kwargs: dict[str, Any]) -> dict[str, Any]:
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
            # Fix: Use next() for safer single value extraction
            return next(iter(kwargs.values()))

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
        # Deprecated: Kept for compatibility, should not be overridden in new code
        # Execution state should be tracked in JobState, not routine._stats
        pass

    def get_slot(self, name: str) -> Slot | None:
        """Get specified slot.

        Args:
            name: Slot name.

        Returns:
            Slot object if found, None otherwise.
        """
        return self._slots.get(name)

    def get_event(self, name: str) -> Event | None:
        """Get specified event.

        Args:
            name: Event name.

        Returns:
            Event object if found, None otherwise.
        """
        return self._events.get(name)

    def set_config(self, **kwargs: Any) -> None:
        """Set configuration values in the _config dictionary.

        This is the recommended way to set routine configuration after object
        creation. All configuration values are stored in self._config and will
        be automatically serialized/deserialized.

        Args:
            ``**kwargs``: Configuration key-value pairs to set. These will be stored
                in self._config dictionary.

        Raises:
            RuntimeError: If called during execution (when routine is in a flow context).
            ValueError: If any value is not serializable.

        Examples:
            >>> routine = MyRoutine()
            >>> routine.set_config(name="processor_1", timeout=30, retries=3)
            >>> # Now routine._config contains:
            >>> # {"name": "processor_1", "timeout": 30, "retries": 3}

            >>> # You can also set config directly:
            >>> routine._config["custom_setting"] = "value"

        Note:
            - Configuration can be set at any time after object creation, but NOT during execution.
            - All values in _config are automatically serialized.
            - Use this method instead of constructor parameters to ensure
              proper serialization/deserialization support.
            - During execution, use JobState.shared_data for execution-specific state.
        """
        # Prevent modification during execution
        if hasattr(self, "_current_flow") and getattr(self, "_current_flow", None):
            raise RuntimeError(
                "Cannot modify _config during execution. "
                "Use JobState.shared_data for execution-specific state."
            )

        # Validate serializability
        for key, value in kwargs.items():
            if not self._is_serializable(value):
                raise ValueError(
                    f"Config value for '{key}' must be serializable. Got {type(value).__name__}"
                )

        self._config.update(kwargs)

    def _is_serializable(self, value: Any) -> bool:
        """Check if value is serializable.

        Args:
            value: Value to check.

        Returns:
            True if value is serializable, False otherwise.

        Note:
            Lists and dicts are always considered serializable, even if they
            contain functions, because serilux can handle serialization of
            callables within containers. Only top-level functions are rejected.
        """
        import json
        import types

        from serilux import Serializable

        # Basic types that are always serializable
        if isinstance(value, (str, int, float, bool, type(None))):
            return True

        # Lists and dicts are always serializable containers
        # (functions within them are handled by serilux during serialization)
        if isinstance(value, (list, tuple, dict)):
            return True

        # Functions, methods, and callables at top level are NOT serializable
        # (but they can be inside lists/dicts, which are handled by serilux)
        if isinstance(value, (types.FunctionType, types.MethodType, types.BuiltinFunctionType)):
            return False
        if callable(value) and not isinstance(value, type):
            return False

        # Serializable objects
        if isinstance(value, Serializable):
            return True

        # Try to serialize to JSON as a test (without default=str to catch real issues)
        try:
            json.dumps(value)
            return True
        except (TypeError, ValueError):
            # Try with default=str as fallback, but only for basic types
            try:
                json.dumps(value, default=str)
                # If it serializes with default=str, it's not truly serializable
                # (functions, classes, etc. would serialize as strings)
                return False
            except (TypeError, ValueError):
                return False

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

    def config(self) -> dict[str, Any]:
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

    def set_timeout(self, timeout: float) -> None:
        """Set execution timeout for this routine.

        Args:
            timeout: Timeout in seconds. If a slot handler takes longer than
                this time, a TimeoutError will be raised.

        Examples:
            >>> routine = MyRoutine()
            >>> routine.set_timeout(30.0)  # 30 second timeout
        """
        self.set_config(timeout=timeout)

    def set_error_handler(self, error_handler: ErrorHandler) -> None:
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

    def get_error_handler(self) -> ErrorHandler | None:
        """Get error handler for this routine.

        Returns:
            ErrorHandler instance if set, None otherwise.
        """
        return self._error_handler

    def set_as_optional(self, strategy: ErrorStrategy = None) -> None:
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
        from routilux.error_handler import ErrorHandler, ErrorStrategy

        if strategy is None:
            strategy = ErrorStrategy.CONTINUE
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

    def set_activation_policy(self, policy: Callable) -> Routine:
        """Set activation policy for this routine.

        The activation policy determines when the routine's logic should be executed.
        It receives (slots, job_state) and returns (should_activate, data_slice, policy_message).

        Args:
            policy: Activation policy function with signature:
                (slots: Dict[str, Slot], job_state: JobState) -> Tuple[bool, Dict[str, List[Any]], Any]

        Returns:
            Self for method chaining.

        Examples:
            >>> from routilux.activation_policies import time_interval_policy
            >>> policy = time_interval_policy(5.0)
            >>> routine.set_activation_policy(policy)
        """
        self._activation_policy = policy
        return self

    def set_logic(self, logic: Callable) -> Routine:
        """Set logic function for this routine.

        The logic function processes data from slots. It receives slot data lists
        (1:1 mapping with slots), policy_message, and job_state.

        Args:
            logic: Logic function with signature:
                (*slot_data_lists, policy_message: Any, job_state: JobState) -> None

        Returns:
            Self for method chaining.

        Examples:
            >>> def my_logic(customer_calls, boss_calls, policy_message, job_state):
            ...     # Process data
            ...     result = process(customer_calls, boss_calls)
            ...     # Emit result
            ...     routine.emit("output", runtime=runtime, job_state=job_state, result=result)
            >>> routine.set_logic(my_logic)
        """
        self._logic = logic
        return self

    def _on_slot_update(self, slot: Slot, job_state: JobState) -> None:
        """Called by Runtime when a slot receives new data.

        This method checks the activation policy and activates the routine
        if conditions are met.

        Args:
            slot: Slot that received new data.
            job_state: JobState for this execution.
        """
        # This is called by Runtime, which handles activation checking
        # We don't need to do anything here - Runtime will call _check_routine_activation
        pass

    def _get_routine_id(self, job_state: JobState) -> Optional[str]:
        """Get routine_id for this routine.

        Args:
            job_state: JobState for this execution.

        Returns:
            Routine ID if found, None otherwise.
        """
        from routilux.flow.flow import Flow

        flow = getattr(self, "_current_flow", None)
        if flow:
            return flow._get_routine_id(self)
        return None

    @property
    def slots(self) -> dict[str, Slot]:
        """Get all slots for this routine.

        Returns:
            Dictionary of slot_name -> Slot object.
        """
        return self._slots

    def get_state(self, job_state: JobState, key: str = None, default: Any = None) -> Any:
        """Get routine-specific state from job_state.

        Convenience method that automatically uses routine_id.

        Args:
            job_state: JobState object.
            key: Optional key to get specific value from routine state.
                 If None, returns entire routine state dict.
            default: Default value if key doesn't exist.

        Returns:
            If key is None: entire routine state dict.
            If key is provided: value for that key.

        Examples:
            >>> # Get entire routine state
            >>> state = routine.get_state(job_state)
            >>> # Get specific key
            >>> count = routine.get_state(job_state, "processing_count", 0)
        """
        routine_id = self._get_routine_id(job_state)
        if routine_id is None:
            return default if key is None else default

        state = job_state.get_routine_state(routine_id)
        if state is None:
            return default if key is None else default

        if key is None:
            return state
        return state.get(key, default)

    def set_state(self, job_state: JobState, key: str, value: Any) -> None:
        """Set routine-specific state in job_state.

        Convenience method that automatically uses routine_id.

        Args:
            job_state: JobState object.
            key: Key to set.
            value: Value to set.

        Examples:
            >>> routine.set_state(job_state, "processing_count", 10)
            >>> routine.set_state(job_state, "last_result", result)
        """
        routine_id = self._get_routine_id(job_state)
        if routine_id is None:
            return

        current_state = job_state.get_routine_state(routine_id) or {}
        current_state[key] = value
        job_state.update_routine_state(routine_id, current_state)

    def update_state(self, job_state: JobState, updates: Dict[str, Any]) -> None:
        """Update multiple routine-specific state keys at once.

        Convenience method that automatically uses routine_id.

        Args:
            job_state: JobState object.
            updates: Dictionary of key-value pairs to update.

        Examples:
            >>> routine.update_state(job_state, {
            ...     "processing_count": 10,
            ...     "last_result": result,
            ...     "status": "completed"
            ... })
        """
        routine_id = self._get_routine_id(job_state)
        if routine_id is None:
            return

        current_state = job_state.get_routine_state(routine_id) or {}
        current_state.update(updates)
        job_state.update_routine_state(routine_id, current_state)

    def get_execution_context(self) -> ExecutionContext | None:
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
        import logging

        logger = logging.getLogger(__name__)

        # Get flow from routine context
        flow = getattr(self, "_current_flow", None)
        if flow is None:
            logger.debug(
                f"No flow context available for {self.__class__.__name__}. "
                "This routine may not be executing within a Flow. "
                "Make sure to call flow.execute() or flow.resume()."
            )
            return None

        # Get job_state from context variable (thread-safe)
        # This method returns None if called outside of execution context
        job_state = _current_job_state.get(None)
        if job_state is None:
            logger.debug(
                f"No job_state in context for {self.__class__.__name__}. "
                "This may indicate the routine is being called outside Flow.execute()."
            )
            return None

        routine_id = flow._get_routine_id(self)
        if routine_id is None:
            logger.warning(
                f"Routine {self.__class__.__name__} is not registered in flow {flow.flow_id if flow else 'Unknown'}. "
                "Make sure to call flow.add_routine() before execution."
            )
            return None

        return ExecutionContext(flow=flow, job_state=job_state, routine_id=routine_id)

    @property
    def job_state(self) -> JobState | None:
        """Get current job_state, or None if not in execution context.

        This is a convenience property that provides direct access to the
        current job_state without needing to call get_execution_context().

        Returns:
            JobState object if in execution context, None otherwise.

        Examples:
            >>> job_state = self.job_state
            >>> if job_state:
            ...     job_id = job_state.job_id
            ...     job_state.update_routine_state(routine_id, {"status": "done"})
        """
        ctx = self.get_execution_context()
        return ctx.job_state if ctx else None

    @property
    def job_id(self) -> str | None:
        """Get current job_id, or None if not in execution context.

        This is a convenience property that provides direct access to the
        current job_id without needing to call get_execution_context().

        Returns:
            Job ID string if in execution context, None otherwise.

        Examples:
            >>> job_id = self.job_id
            >>> if not job_id:
            ...     raise ValueError("job_id is required")
        """
        ctx = self.get_execution_context()
        return ctx.job_state.job_id if ctx and ctx.job_state else None

    @property
    def flow(self) -> Flow | None:
        """Get current flow, or None if not in execution context.

        This is a convenience property that provides direct access to the
        current flow without needing to call get_execution_context().

        Returns:
            Flow object if in execution context, None otherwise.

        Examples:
            >>> flow = self.flow
            >>> if flow:
            ...     routine_id = flow._get_routine_id(self)
        """
        ctx = self.get_execution_context()
        return ctx.flow if ctx else None

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

    def serialize(self) -> dict[str, Any]:
        """Serialize Routine, including class information and state.

        Returns:
            Serialized dictionary.
        """
        # Let base class handle all registered fields including _slots and _events
        # Base class automatically handles Serializable objects in dicts
        data = super().serialize()

        return data

    def deserialize(self, data: dict[str, Any], registry: Any | None = None) -> None:
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
