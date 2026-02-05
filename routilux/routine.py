"""
Routine base class.

Improved Routine mechanism supporting slots (input slots) and events (output events).

Refactored to use mixins for separation of concerns:
- ConfigMixin: Configuration and parameter management
- ExecutionMixin: Event emission and slot management
- LifecycleMixin: Lifecycle hooks and state management
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from routilux.error_handler import ErrorHandler, ErrorStrategy
    from routilux.flow import Flow
    from routilux.job_state import JobState

from serilux import Serializable, register_serializable

from routilux.routine_mixins import ConfigMixin, ExecutionMixin, LifecycleMixin

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
class Routine(ConfigMixin, ExecutionMixin, LifecycleMixin, Serializable):
    """Improved Routine base class with enhanced capabilities.

    Features:
    - Support for slots (input slots) via ExecutionMixin
    - Support for events (output events) via ExecutionMixin
    - Configuration dictionary (_config) via ConfigMixin
    - Lifecycle hooks via LifecycleMixin

    The Routine class is now a composition of three mixins:
    - ConfigMixin: Configuration and parameter management
    - ExecutionMixin: Event emission and slot management
    - LifecycleMixin: State management and lifecycle hooks

    Configuration Management (_config):
        The _config dictionary stores routine-specific configuration that should
        persist across serialization. Use set_config() and get_config() methods
        for convenient access. Also provides configure() and get_param() aliases.

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
            ...         # Or use the new alias:
            ...         self.configure(name="my_routine", timeout=30)
            ...
            ...     def process(self, **kwargs):
            ...         # Use configuration
            ...         timeout = self.get_config("timeout", default=10)
            ...         # Or use the new alias:
            ...         timeout = self.get_param("timeout", default=10)

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
        # Call all mixin __init__ methods (ConfigMixin, ExecutionMixin, LifecycleMixin)
        # and Serializable.__init__()
        super().__init__()
        self._id: str = hex(id(self))

        # Error handler for this routine (optional)
        # Priority: routine-level error handler > flow-level error handler > default (STOP)
        self._error_handler: ErrorHandler | None = None

        # Register serializable fields
        # _config, _slots, _events are from mixins and need to be registered
        # _id and _error_handler are from Routine
        # _before_hooks, _after_hooks are from LifecycleMixin
        self.add_serializable_fields(
            ["_id", "_config", "_error_handler", "_slots", "_events", "_before_hooks", "_after_hooks"]
        )

    def __repr__(self) -> str:
        """Return string representation of the Routine."""
        return f"{self.__class__.__name__}[{self._id}]"

    # Note: define_slot, define_event, emit, get_slot, get_event, _prepare_execution_data,
    # _extract_input_data are now provided by ExecutionMixin

    # Note: set_config, get_config, config, configure, get_param are now provided by ConfigMixin

    # Note: before_execution, after_execution, _run_before_hooks, _run_after_hooks
    # are now provided by LifecycleMixin

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

    def set_as_optional(self, strategy: ErrorStrategy | None = None) -> None:
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
        # Get flow from routine context
        flow = getattr(self, "_current_flow", None)
        if flow is None:
            return None

        # Get job_state from context variable (thread-safe)
        # This method returns None if called outside of execution context
        job_state = _current_job_state.get(None)
        if job_state is None:
            return None

        routine_id = flow._get_routine_id(self)
        if routine_id is None:
            return None

        return ExecutionContext(flow=flow, job_state=job_state, routine_id=routine_id)

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

    def deserialize(self, data: dict[str, Any], strict: bool = False, registry: Any | None = None) -> None:
        """Deserialize Routine.

        Args:
            data: Serialized data dictionary.
            strict: Whether to enforce strict deserialization.
            registry: Optional ObjectRegistry for deserializing callables.
        """

        # Let base class handle all registered fields including _slots and _events
        # Base class automatically deserializes Serializable objects in dicts
        super().deserialize(data, strict=strict, registry=registry)

        # Restore routine references for slots and events (required after deserialization)
        if hasattr(self, "_slots") and self._slots:
            for slot in self._slots.values():
                slot.routine = self

        if hasattr(self, "_events") and self._events:
            for event in self._events.values():
                event.routine = self
