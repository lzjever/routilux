"""
Event class.

Output events for sending data to other routines.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from routilux.flow import Flow
    from routilux.routine import Routine
    from routilux.slot import Slot

from serilux import Serializable, register_serializable


@register_serializable
class Event(Serializable):
    """Output event for transmitting data to other routines.

    An Event represents an output point in a Routine that can transmit data
    to connected Slots in other routines. Events enable one-to-many data
    distribution: when an event is emitted, all connected slots receive
    the data simultaneously.

    Key Concepts:
        - Events are defined in routines using define_event()
        - Events are emitted using emit() or Routine.emit()
        - Events can connect to multiple slots (broadcast pattern)
        - Slots can connect to multiple events (aggregation pattern)

    Connection Model:
        Events support many-to-many connections:
        - One event can connect to many slots (broadcasting)
        - One slot can connect to many events (aggregation)
        - Connections are managed via Flow.connect()

    Examples:
        Basic usage:
            >>> class MyRoutine(Routine):
            ...     def __init__(self):
            ...         super().__init__()
            ...         self.output = self.define_event("output", ["result"])
            ...
            ...     def __call__(self):
            ...         self.emit("output", result="success", status=200)

        Multiple connections:
            >>> # One event, multiple receivers
            >>> flow.connect(source_id, "output", target1_id, "input1")
            >>> flow.connect(source_id, "output", target2_id, "input2")
            >>> # Both targets receive data when source emits "output"
    """

    def __init__(
        self,
        name: str = "",
        routine: Routine | None = None,
        output_params: list[str] | None = None,
    ):
        """Initialize an Event.

        Args:
            name: Event name.
            routine: Parent Routine object.
            output_params: List of output parameter names (for documentation).
        """
        super().__init__()
        self.name: str = name
        self.routine: Routine | None = routine
        self.output_params: list[str] = output_params or []
        self.connected_slots: list[Slot] = []

        # Register serializable fields
        self.add_serializable_fields(["name", "output_params"])

    def serialize(self) -> dict[str, Any]:
        """Serialize the Event.

        Returns:
            Serialized dictionary containing event data.
        """
        # Let base class handle registered fields (name, output_params)
        # Base class is sufficient - no special handling needed
        # Note: _routine_id is NOT serialized here - it's Flow's responsibility
        # Flow will add routine_id when serializing routines
        return super().serialize()

    def deserialize(
        self, data: dict[str, Any], strict: bool = False, registry: Any | None = None
    ) -> None:
        """Deserialize the Event.

        Args:
            data: Serialized data dictionary.
            strict: Whether to enforce strict deserialization.
            registry: Optional ObjectRegistry for deserializing callables.
        """
        # Let base class handle registered fields (name, output_params)
        # Base class is sufficient - no special handling needed
        super().deserialize(data, strict=strict, registry=registry)

    def __repr__(self) -> str:
        """Return string representation of the Event."""
        if self.routine:
            return f"Event[{self.routine._id}.{self.name}]"
        else:
            return f"Event[{self.name}]"

    def connect(self, slot: Slot) -> None:
        """Connect to a slot.

        Args:
            slot: Slot object to connect to.
        """
        if slot not in self.connected_slots:
            self.connected_slots.append(slot)
            # Bidirectional connection
            if self not in slot.connected_events:
                slot.connected_events.append(self)

    def disconnect(self, slot: Slot) -> None:
        """Disconnect from a slot.

        Args:
            slot: Slot object to disconnect from.
        """
        if slot in self.connected_slots:
            self.connected_slots.remove(slot)
            # Bidirectional disconnection
            if self in slot.connected_events:
                slot.connected_events.remove(self)

    def emit(self, flow: Flow | None = None, **kwargs) -> None:
        """Emit the event and send data to all connected slots.

        This method transmits data to all slots connected to this event using
        a queue-based mechanism. Tasks are enqueued and executed asynchronously,
        allowing emit() to return immediately without waiting for downstream
        execution.

        Execution Mode:
            - All execution uses a unified queue-based mechanism
            - Sequential mode: max_workers=1, tasks execute one at a time
            - Concurrent mode: max_workers>1, tasks execute in parallel
            - emit() is always non-blocking and returns immediately

        Flow Context Auto-Detection:
            If flow parameter is None, this method automatically attempts to
            get the flow from the routine's context (routine._current_flow).
            This allows simpler usage: event.emit(data="value") instead of
            event.emit(flow=my_flow, data="value").

            The flow context is automatically set by Flow.execute() and Flow.resume().

        Args:
            flow: Optional Flow object. If None, automatically attempts to get
                from routine._current_flow (set by Flow.execute()).
                Required for:
                - Finding Connection objects
                - Recording execution history in JobState
                - Queue-based task execution
                If no flow is available, falls back to direct slot.receive() call (legacy mode).
            ``**kwargs``: Data to transmit. These keyword arguments form the
                data dictionary sent to connected slots. All values must be
                serializable if the flow uses persistence.
                Example: emit(result="success", count=42)

        Examples:
            Basic emission (automatic flow detection):
                >>> event = routine.define_event("output", ["result"])
                >>> # Inside a routine handler called by Flow.execute():
                >>> event.emit(result="data", status="ok")
                >>> # Automatically uses routine._current_flow

            Explicit flow parameter:
                >>> event.emit(flow=my_flow, result="data", status="ok")
                >>> # Explicitly specify flow (useful for testing or edge cases)

            Without flow (legacy mode):
                >>> event.emit(result="data")  # Direct call, no queue
                >>> # Only works if no flow context available
        """
        # Auto-detect flow from routine context if not provided
        if flow is None and self.routine:
            flow = getattr(self.routine, "_current_flow", None)

        # If no flow context, use legacy direct call
        if flow is None:
            for slot in self.connected_slots:
                slot.receive(kwargs)
            return

        # Queue-based execution: create tasks and enqueue
        from routilux.flow.task import SlotActivationTask, TaskPriority

        # Get JobState from kwargs or context variable
        job_state = kwargs.pop("job_state", None)
        if job_state is None:
            from routilux.routine import _current_job_state

            job_state = _current_job_state.get(None)

        for slot in self.connected_slots:
            connection = flow._find_connection(self, slot)

            # Create task
            task = SlotActivationTask(
                slot=slot,
                data=kwargs.copy(),
                connection=connection,
                priority=TaskPriority.NORMAL,
                created_at=datetime.now(),
                job_state=job_state,  # Pass JobState to task
            )

            # Enqueue (non-blocking)
            flow._enqueue_task(task)

        # Return immediately, no waiting
