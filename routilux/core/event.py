"""
Event class for sending data to other routines.

Output events for transmitting data to connected slots.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from routilux.core.routine import Routine
    from routilux.core.runtime import Runtime
    from routilux.core.slot import Slot
    from routilux.core.worker import WorkerState

from serilux import Serializable


# Note: Not using @register_serializable to avoid conflict with legacy module
class Event(Serializable):
    """Output event for transmitting data to other routines.

    An Event represents an output point in a Routine that can transmit data
    to connected Slots. Events enable one-to-many data distribution.

    Key Concepts:
        - Events are defined in routines using add_event()
        - Events are emitted using emit() or Routine.emit()
        - Events can connect to multiple slots (broadcast pattern)

    Examples:
        >>> class MyRoutine(Routine):
        ...     def setup(self):
        ...         self.add_event("output")
        ...
        ...     def logic(self, *args, **kwargs):
        ...         self.emit("output", result="success")
    """

    def __init__(
        self,
        name: str = "",
        routine: Routine | None = None,
        output_params: list[str] | None = None,
    ):
        """Initialize an Event.

        Args:
            name: Event name
            routine: Parent Routine object
            output_params: List of output parameter names (for documentation)
        """
        super().__init__()
        self.name: str = name
        self.routine: Routine | None = routine
        self.output_params: list[str] = output_params or []
        self.connected_slots: list[Slot] = []
        self._connection_lock: threading.RLock = threading.RLock()

        # Register serializable fields
        self.add_serializable_fields(["name", "output_params"])

    def __repr__(self) -> str:
        """Return string representation."""
        if self.routine:
            return f"Event[{getattr(self.routine, '_id', 'unknown')}.{self.name}]"
        return f"Event[{self.name}]"

    def connect(self, slot: Slot) -> None:
        """Connect to a slot (thread-safe)."""
        lock1, lock2 = sorted((self._connection_lock, slot._connection_lock), key=id)
        with lock1, lock2:
            if slot not in self.connected_slots:
                self.connected_slots.append(slot)
                if self not in slot.connected_events:
                    slot.connected_events.append(self)

    def disconnect(self, slot: Slot) -> None:
        """Disconnect from a slot (thread-safe)."""
        lock1, lock2 = sorted((self._connection_lock, slot._connection_lock), key=id)
        with lock1, lock2:
            if slot in self.connected_slots:
                self.connected_slots.remove(slot)
                if self in slot.connected_events:
                    slot.connected_events.remove(self)

    def emit(self, runtime: Runtime, worker_state: WorkerState, **kwargs: Any) -> None:
        """Emit the event and route data to connected slots.

        This method packs data with metadata and creates an EventRoutingTask
        that will be processed in the WorkerExecutor's event loop thread.

        Args:
            runtime: Runtime object for event routing
            worker_state: WorkerState for this execution
            **kwargs: Data to transmit

        Examples:
            >>> event.emit(runtime=runtime, worker_state=worker_state, result="data")
        """
        # Pack data with metadata
        emitted_from = "unknown"
        if self.routine:
            emitted_from = getattr(self.routine, "_id", None) or self.routine.__class__.__name__

        event_data = {
            "data": kwargs,
            "metadata": {
                "emitted_at": datetime.now(),
                "emitted_from": emitted_from,
                "event_name": self.name,
            },
        }

        # Get WorkerExecutor from worker_state
        worker_executor = getattr(worker_state, "_executor", None)
        if worker_executor is None:
            raise RuntimeError(
                "WorkerExecutor not found in worker_state. Event routing requires a WorkerExecutor."
            )

        # Get current job context for propagation
        from routilux.core.context import get_current_job

        job_context = get_current_job()

        # Create routing task and submit to event loop thread
        from routilux.core.task import EventRoutingTask

        routing_task = EventRoutingTask(
            event=self,
            event_data=event_data,
            worker_state=worker_state,
            runtime=runtime,
            job_context=job_context,  # Pass job_context for propagation
        )

        worker_executor.enqueue_task(routing_task)

    def serialize(self) -> dict[str, Any]:
        """Serialize the Event."""
        return super().serialize()

    def deserialize(
        self, data: dict[str, Any], strict: bool = False, registry: Any | None = None
    ) -> None:
        """Deserialize the Event."""
        super().deserialize(data, strict=strict, registry=registry)
