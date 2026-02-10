"""
Routine base class for Routilux core.

Improved Routine mechanism supporting slots (input) and events (output).
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from serilux import Serializable

# Import worker state context from context.py
from routilux.core.context import get_current_worker_state as _get_current_worker_state

if TYPE_CHECKING:
    from routilux.core.context import ExecutionContext
    from routilux.core.error import ErrorHandler
    from routilux.core.event import Event
    from routilux.core.slot import Slot
    from routilux.core.worker import WorkerState

T = TypeVar("T")


# Note: Not using @register_serializable to avoid conflict with legacy module
class Routine(Serializable):
    """Improved Routine base class with enhanced capabilities.

    Features:
        - Support for slots (input slots)
        - Support for events (output events)
        - Configuration dictionary (_config) for storing routine-specific settings
        - Separation of activation policy and logic

    Important Constraints:
        - Routines MUST NOT accept constructor parameters (except self).
          This is required for proper serialization/deserialization.
        - All configuration should be stored in the _config dictionary.
        - During execution, routines MUST NOT modify any instance variables.
        - All execution-related state should be stored in WorkerState.
        - Routines can only READ from _config during execution.
        - Routines can WRITE to WorkerState (via worker_state.update_routine_state()).

    Note on Job-level vs Worker-level State:
        - Worker-level state: Use WorkerState (long-running, persistent)
        - Job-level state: Use JobContext (per-request, temporary)
        - Access JobContext via get_current_job() in your logic

    Examples:
        >>> class MyRoutine(Routine):
        ...     def setup(self):
        ...         self.add_slot("input")
        ...         self.add_event("output")
        ...         self.set_config(name="processor", timeout=30)
        ...
        ...     def logic(self, input_data, **kwargs):
        ...         # Get job context for job-specific data
        ...         from routilux.core import get_current_job
        ...         job = get_current_job()
        ...         if job:
        ...             job.set_data("processed", True)
        ...         # Emit output
        ...         self.emit("output", result="processed")
    """

    def __init__(self):
        """Initialize Routine object.

        Note:
            This constructor accepts no parameters (except self). All configuration
            should be stored in self._config dictionary after object creation.
        """
        super().__init__()
        self._id: str = hex(id(self))
        self._slots: dict[str, Slot] = {}
        self._events: dict[str, Event] = {}

        # Configuration dictionary for storing routine-specific settings
        self._config: dict[str, Any] = {}
        self._config_lock: threading.RLock = threading.RLock()

        # Error handler for this routine (optional)
        self._error_handler: ErrorHandler | None = None

        # Activation policy and logic
        self._activation_policy: Callable | None = None
        self._logic: Callable | None = None

        # Register serializable fields
        self.add_serializable_fields(
            [
                "_id",
                "_config",
                "_error_handler",
                "_slots",
                "_events",
                "_activation_policy",
                "_logic",
            ]
        )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"{self.__class__.__name__}[{self._id}]"

    def add_slot(self, name: str, max_queue_length: int = 1000, watermark: float = 0.8) -> Slot:
        """Add an input slot for receiving data.

        Args:
            name: Slot name (must be unique within this routine)
            max_queue_length: Maximum queue length (default: 1000)
            watermark: Watermark threshold for auto-shrink (default: 0.8)

        Returns:
            Slot object

        Raises:
            ValueError: If slot name already exists
        """
        if max_queue_length <= 0:
            raise ValueError(f"max_queue_length must be > 0, got {max_queue_length}")
        if not 0.0 <= watermark <= 1.0:
            raise ValueError(f"watermark must be between 0.0 and 1.0, got {watermark}")

        with self._config_lock:
            if name in self._slots:
                raise ValueError(f"Slot '{name}' already exists in {self}")

            from routilux.core.slot import Slot

            slot = Slot(name, self, max_queue_length=max_queue_length, watermark=watermark)
            self._slots[name] = slot
            return slot

    def add_event(self, name: str, output_params: list[str] | None = None) -> Event:
        """Add an output event for transmitting data.

        Args:
            name: Event name (must be unique within this routine)
            output_params: Optional list of parameter names (for documentation)

        Returns:
            Event object

        Raises:
            ValueError: If event name already exists
        """
        with self._config_lock:
            if name in self._events:
                raise ValueError(f"Event '{name}' already exists in {self}")

            from routilux.core.event import Event

            event = Event(name, self, output_params or [])
            self._events[name] = event
            return event

    def emit(
        self,
        event_name: str,
        runtime: Any | None = None,
        worker_state: WorkerState | None = None,
        **kwargs: Any,
    ) -> None:
        """Emit an event and send data to connected slots.

        Args:
            event_name: Name of the event to emit
            runtime: Optional Runtime object
            worker_state: Optional WorkerState object
            **kwargs: Data to transmit

        Raises:
            ValueError: If event_name does not exist
            RuntimeError: If runtime or worker_state cannot be determined

        **Context Variable (contextvar) Behavior:**

        This method uses context variables to automatically retrieve missing parameters:

        1. **runtime**: If not provided, retrieved from ``worker_state._runtime``
           (set by Runtime during worker creation)

        2. **worker_state**: If not provided, retrieved from thread-local context
           using ``get_current_worker_state()`` (set by WorkerExecutor)

        3. **job_context**: The underlying ``Event.emit()`` method automatically
           retrieves job_context from thread-local context using ``get_current_job()``

        **Important for Testing:**
        When calling ``emit()`` directly in tests (outside of normal routine execution),
        you must ensure the context variables are set:

        .. code-block:: python

            from routilux.core.context import set_current_job, set_current_worker_state

            # In your test
            worker_state, job_context = runtime.post(...)
            set_current_worker_state(worker_state)  # If worker_state not provided
            set_current_job(job_context)  # Required for breakpoint checking

            # Now emit will work correctly
            routine.emit("output", runtime=runtime, data="test")
            # Or with worker_state from context:
            routine.emit("output", runtime=runtime, data="test")

        **Normal Usage (within routine logic):**
        When called from within a routine's logic method, all context variables
        are automatically set by WorkerExecutor before execution, so you can
        simply call:

        .. code-block:: python

            def logic(self, input_data, **kwargs):
                # All context is automatically available
                self.emit("output", data="result")
        """
        if event_name not in self._events:
            raise ValueError(f"Event '{event_name}' does not exist in {self}")

        event = self._events[event_name]

        # Try to get context from ExecutionContext first
        from routilux.core.context import get_current_execution_context

        ctx = get_current_execution_context()

        # Determine worker_state
        if worker_state is None:
            if ctx:
                worker_state = ctx.worker_state
            else:
                worker_state = _get_current_worker_state()

        if worker_state is None:
            raise RuntimeError(
                "WorkerState is required for emit(). "
                "Provide worker_state parameter or ensure routine is executing within Runtime context."
            )

        # Determine runtime (for backwards compatibility)
        if runtime is None:
            runtime = getattr(worker_state, "_runtime", None)
            if runtime is None and ctx:
                # Use ExecutionContext - Flow in ctx implements routing interface
                runtime = ctx

        event.emit(runtime=runtime, worker_state=worker_state, **kwargs)

    def get_slot(self, name: str) -> Slot | None:
        """Get specified slot."""
        return self._slots.get(name)

    def get_event(self, name: str) -> Event | None:
        """Get specified event."""
        return self._events.get(name)

    @property
    def slots(self) -> dict[str, Slot]:
        """Get all slots."""
        return self._slots

    @property
    def events(self) -> dict[str, Event]:
        """Get all events."""
        return self._events

    def set_config(self, **kwargs: Any) -> None:
        """Set configuration values.

        Args:
            **kwargs: Configuration key-value pairs
        """
        with self._config_lock:
            # Prevent modification during execution
            from routilux.core.context import get_current_execution_context

            ctx = get_current_execution_context()
            if ctx is not None:
                raise RuntimeError(
                    "Cannot modify _config during execution. "
                    "Use WorkerState for execution-specific state."
                )
            self._config.update(kwargs)

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        with self._config_lock:
            return self._config.get(key, default)

    def config(self) -> dict[str, Any]:
        """Get a copy of the configuration dictionary."""
        with self._config_lock:
            return self._config.copy()

    def set_error_handler(self, error_handler: ErrorHandler) -> None:
        """Set error handler for this routine."""
        self._error_handler = error_handler

    def get_error_handler(self) -> ErrorHandler | None:
        """Get error handler for this routine."""
        return self._error_handler

    def set_activation_policy(self, policy: Callable) -> Routine:
        """Set activation policy for this routine.

        The activation policy determines when the routine's logic should be executed.
        It receives (slots, worker_state) and returns (should_activate, data_slice, policy_message).

        Args:
            policy: Activation policy function

        Returns:
            Self for method chaining
        """
        self._activation_policy = policy
        return self

    def get_activation_policy_info(self) -> dict[str, Any]:
        """Get activation policy information.

        Returns:
            Dictionary with policy type and description
        """
        if self._activation_policy is None:
            return {
                "type": "immediate",
                "description": "Default activation policy - routine activates immediately when data arrives",
            }

        # Try to get policy name/type
        policy_name = getattr(self._activation_policy, "__name__", "custom")
        policy_module = getattr(self._activation_policy, "__module__", "")

        # Check if it's a known policy type
        if "breakpoint" in policy_name.lower() or "breakpoint" in policy_module.lower():
            return {
                "type": "breakpoint",
                "description": "Breakpoint policy - routine pauses at breakpoint",
            }
        elif "batch" in policy_name.lower():
            return {
                "type": "batch",
                "description": "Batch policy - routine activates when batch size reached",
            }
        elif "time" in policy_name.lower() or "interval" in policy_name.lower():
            return {
                "type": "time_interval",
                "description": "Time interval policy - routine activates at intervals",
            }
        else:
            return {
                "type": "custom",
                "description": f"Custom activation policy: {policy_name}",
                "module": policy_module,
            }

    def get_all_config(self) -> dict[str, Any]:
        """Get all configuration values.

        Returns:
            Copy of the configuration dictionary
        """
        return self.config()  # Use existing config() method

    def set_logic(self, logic: Callable) -> Routine:
        """Set logic function for this routine.

        The logic function processes data from slots.

        Args:
            logic: Logic function

        Returns:
            Self for method chaining
        """
        self._logic = logic
        return self

    def get_execution_context(self) -> ExecutionContext | None:
        """Get execution context from ContextVar (direct access).

        Returns:
            ExecutionContext if in execution context, None otherwise
        """
        from routilux.core.context import get_current_execution_context

        return get_current_execution_context()

    def get_state(
        self, worker_state: WorkerState, key: str | None = None, default: Any = None
    ) -> Any:
        """Get routine-specific state from worker_state.

        Args:
            worker_state: WorkerState object
            key: Optional key to get specific value
            default: Default value if key doesn't exist

        Returns:
            Routine state or specific key value
        """
        from routilux.core.context import get_current_execution_context

        ctx = get_current_execution_context()
        if ctx is None or not ctx.routine_id:
            return default if key else default

        state = worker_state.get_routine_state(ctx.routine_id)
        if state is None:
            return default if key else default

        if key is None:
            return state
        return state.get(key, default)

    def set_state(self, worker_state: WorkerState, key: str, value: Any) -> None:
        """Set routine-specific state in worker_state.

        Args:
            worker_state: WorkerState object
            key: Key to set
            value: Value to set
        """
        from routilux.core.context import get_current_execution_context

        ctx = get_current_execution_context()
        if ctx is None or not ctx.routine_id:
            return

        current_state = worker_state.get_routine_state(ctx.routine_id) or {}
        current_state[key] = value
        worker_state.update_routine_state(ctx.routine_id, current_state)

    def update_state(self, worker_state: WorkerState, updates: dict[str, Any]) -> None:
        """Update multiple routine-specific state keys at once.

        Args:
            worker_state: WorkerState object
            updates: Dictionary of key-value pairs to update
        """
        from routilux.core.context import get_current_execution_context

        ctx = get_current_execution_context()
        if ctx is None or not ctx.routine_id:
            return

        current_state = worker_state.get_routine_state(ctx.routine_id) or {}
        current_state.update(updates)
        worker_state.update_routine_state(ctx.routine_id, current_state)

    def set_job_data(self, key: str, value: Any) -> None:
        """Set job-level data for this routine (automatically namespaced by routine_id).

        This is the recommended way to store routine-specific job state.
        Automatically uses routine_id as namespace to prevent key collisions.

        Args:
            key: Data key (without routine_id prefix)
            value: Data value

        Raises:
            RuntimeError: If job context or routine_id is not available
        """
        from routilux.core.context import get_current_execution_context, get_current_job

        ctx = get_current_execution_context()
        if ctx is None:
            raise RuntimeError(
                "set_job_data requires execution context. "
                "This method must be called during routine execution."
            )

        if not ctx.routine_id:
            raise RuntimeError(
                "set_job_data requires routine_id. "
                "This routine must be added to a flow before execution."
            )

        job = get_current_job()
        if job is None:
            raise RuntimeError("set_job_data requires job context")

        # Direct access to routine_id from ExecutionContext
        full_key = f"{ctx.routine_id}_{key}"
        job.data[full_key] = value

    def get_job_data(self, key: str, default: Any = None) -> Any:
        """Get job-level data for this routine (automatically namespaced by routine_id).

        Args:
            key: Data key (without routine_id prefix)
            default: Default value if key doesn't exist

        Returns:
            Data value or default
        """
        from routilux.core.context import get_current_execution_context, get_current_job

        ctx = get_current_execution_context()
        if ctx is None or not ctx.routine_id:
            return default

        job = get_current_job()
        if job is None:
            return default

        # Direct access to routine_id from ExecutionContext
        full_key = f"{ctx.routine_id}_{key}"
        return job.data.get(full_key, default)

    def __call__(self, **kwargs: Any) -> None:
        """Execute routine (deprecated - use slot handlers instead).

        Note:
            Direct calling of routines is deprecated. Routines should be
            executed through slot handlers via set_logic().
        """
        pass

    def serialize(self) -> dict[str, Any]:
        """Serialize the Routine."""
        data = super().serialize()
        # Handle slots and events serialization
        if "_slots" in data:
            data["_slots"] = {name: slot.serialize() for name, slot in self._slots.items()}
        if "_events" in data:
            data["_events"] = {name: event.serialize() for name, event in self._events.items()}
        return data

    def deserialize(self, data: dict[str, Any], strict: bool = False, registry: Any = None) -> None:
        """Deserialize the Routine."""
        # Handle slots
        if "_slots" in data and isinstance(data["_slots"], dict):
            from routilux.core.slot import Slot

            for name, slot_data in data["_slots"].items():
                if isinstance(slot_data, dict):
                    slot = Slot(name, self)
                    slot.deserialize(slot_data, strict=strict, registry=registry)
                    self._slots[name] = slot
            del data["_slots"]

        # Handle events
        if "_events" in data and isinstance(data["_events"], dict):
            from routilux.core.event import Event

            for name, event_data in data["_events"].items():
                if isinstance(event_data, dict):
                    event = Event(name, self)
                    event.deserialize(event_data, strict=strict, registry=registry)
                    self._events[name] = event
            del data["_events"]

        super().deserialize(data, strict=strict, registry=registry)
