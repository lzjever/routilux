"""
Event class.

Output events for sending data to other routines.
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from routilux.routine import Routine
    from routilux.slot import Slot
    from routilux.flow import Flow

from serilux import register_serializable, Serializable


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
        - Parameter mapping can transform data during transmission

    Connection Model:
        Events support many-to-many connections:
        - One event can connect to many slots (broadcasting)
        - One slot can connect to many events (aggregation)
        - Connections are managed via Flow.connect()
        - Parameter mappings can rename parameters per connection

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
        routine: Optional["Routine"] = None,
        output_params: Optional[List[str]] = None,
    ):
        """Initialize an Event.

        Args:
            name: Event name.
            routine: Parent Routine object.
            output_params: List of output parameter names (for documentation).
        """
        super().__init__()
        self.name: str = name
        self.routine: "Routine" = routine
        self.output_params: List[str] = output_params or []
        self.connected_slots: List["Slot"] = []

        # Register serializable fields
        self.add_serializable_fields(["name", "output_params"])

    def serialize(self) -> Dict[str, Any]:
        """Serialize the Event.

        Returns:
            Serialized dictionary containing event data.
        """
        # Let base class handle registered fields (name, output_params)
        # Base class is sufficient - no special handling needed
        # Note: _routine_id is NOT serialized here - it's Flow's responsibility
        # Flow will add routine_id when serializing routines
        return super().serialize()

    def deserialize(self, data: Dict[str, Any], registry: Optional[Any] = None) -> None:
        """Deserialize the Event.

        Args:
            data: Serialized data dictionary.
            registry: Optional ObjectRegistry for deserializing callables.
        """
        # Let base class handle registered fields (name, output_params)
        # Base class is sufficient - no special handling needed
        super().deserialize(data, registry=registry)

    def __repr__(self) -> str:
        """Return string representation of the Event."""
        if self.routine:
            return f"Event[{self.routine._id}.{self.name}]"
        else:
            return f"Event[{self.name}]"

    def connect(self, slot: "Slot", param_mapping: Optional[Dict[str, str]] = None) -> None:
        """Connect to a slot.

        Args:
            slot: Slot object to connect to.
            param_mapping: Parameter mapping dictionary (managed by Connection,
                this method only establishes the connection).
        """
        if slot not in self.connected_slots:
            self.connected_slots.append(slot)
            # Bidirectional connection
            if self not in slot.connected_events:
                slot.connected_events.append(self)

    def disconnect(self, slot: "Slot") -> None:
        """Disconnect from a slot.

        Args:
            slot: Slot object to disconnect from.
        """
        if slot in self.connected_slots:
            self.connected_slots.remove(slot)
            # Bidirectional disconnection
            if self in slot.connected_events:
                slot.connected_events.remove(self)

    def emit(self, flow: Optional["Flow"] = None, **kwargs) -> None:
        """Emit the event and send data to all connected slots.

        This method transmits data to all slots connected to this event.
        The data is sent according to the connection's parameter mapping,
        then merged with each slot's existing data according to the slot's
        merge_strategy, and finally passed to the slot's handler.

        Execution Mode:
            - Sequential mode: Handlers are called synchronously, one after another.
              Execution order follows the order of connections.
            - Concurrent mode: Handlers may execute in parallel threads if the
              flow's execution_strategy is "concurrent". This allows independent
              routines to process data simultaneously.

        Parameter Mapping:
            If a Connection has param_mapping defined (via Flow.connect()),
            parameter names are transformed before being sent to the slot.
            Unmapped parameters are passed with their original names.

        Args:
            flow: Optional Flow object. Required for:
                - Finding Connection objects to apply parameter mappings
                - Recording execution history in JobState
                - Enabling concurrent execution mode
                If None, parameter mapping won't work and execution history
                won't be recorded. Should be provided when emitting from
                within a Flow execution context.
            ``**kwargs``: Data to transmit. These keyword arguments form the
                data dictionary sent to connected slots. All values must be
                serializable if the flow uses persistence.
                Example: emit(flow=my_flow, result="success", count=42)

        Examples:
            Basic emission:
                >>> event = routine.define_event("output", ["result"])
                >>> event.emit(flow=my_flow, result="data", status="ok")
                >>> # Sends data to all connected slots

            Without flow (limited functionality):
                >>> event.emit(result="data")  # No parameter mapping, no history
                >>> # Still works, but parameter mapping won't be applied
        """
        if flow is None or flow.execution_strategy != "concurrent":
            # Sequential execution mode
            for slot in self.connected_slots:
                if flow is not None:
                    connection = flow._find_connection(self, slot)
                    if connection is not None:
                        connection.activate(kwargs)
                    else:
                        slot.receive(kwargs)
                else:
                    slot.receive(kwargs)
        else:
            # Concurrent execution mode
            executor = flow._get_executor()

            # Submit task for each connected slot (asynchronous execution, non-blocking)
            for slot in self.connected_slots:

                def activate_slot(s=slot, f=flow, k=kwargs.copy()):
                    """Thread-safe slot activation function."""
                    try:
                        if f is not None:
                            connection = f._find_connection(self, s)
                            if connection is not None:
                                connection.activate(k)
                            else:
                                s.receive(k)
                        else:
                            s.receive(k)
                    except Exception as e:
                        import logging

                        logging.exception(f"Error in concurrent slot activation: {e}")
                        # Record error to routine stats
                        if s.routine:
                            s.routine._stats.setdefault("errors", []).append(
                                {"slot": s.name, "error": str(e)}
                            )

                # Submit task to thread pool without waiting (avoid nested waits causing deadlock)
                future = executor.submit(activate_slot)

                # Add future to Flow's tracking set (add immediately after submission to avoid race conditions)
                if flow is not None and hasattr(flow, "_active_futures"):
                    with flow._execution_lock:
                        flow._active_futures.add(future)

                    # Add callback to automatically remove when task completes (add callback outside lock to avoid deadlock)
                    def remove_future(fut=future, f=flow):
                        """Remove from tracking set when task completes."""
                        if f is not None and hasattr(f, "_active_futures"):
                            with f._execution_lock:
                                f._active_futures.discard(fut)

                    # Note: If future is already done, callback executes immediately
                    future.add_done_callback(remove_future)

            # Note: Do not wait for futures to complete, let them execute asynchronously
            # This avoids deadlock issues with nested concurrent execution
            # If waiting is needed, call Flow.wait_for_completion() or Flow.shutdown()
