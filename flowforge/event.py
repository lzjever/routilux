"""
Event class.

Output events for sending data to other routines.
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from flowforge.routine import Routine
    from flowforge.slot import Slot
    from flowforge.flow import Flow

from flowforge.utils.serializable import register_serializable, Serializable


@register_serializable
class Event(Serializable):
    """Output event for transmitting data to other routines.
    
    An Event can be connected to multiple Slots (many-to-many relationship),
    allowing data to be broadcast to multiple receivers simultaneously.
    """
    
    def __init__(
        self,
        name: str = "",
        routine: Optional['Routine'] = None,
        output_params: Optional[List[str]] = None
    ):
        """Initialize an Event.

        Args:
            name: Event name.
            routine: Parent Routine object.
            output_params: List of output parameter names (for documentation).
        """
        super().__init__()
        self.name: str = name
        self.routine: 'Routine' = routine
        self.output_params: List[str] = output_params or []
        self.connected_slots: List['Slot'] = []
        
        # Register serializable fields
        self.add_serializable_fields(["name", "output_params"])
    
    def serialize(self) -> Dict[str, Any]:
        """Serialize the Event.

        Returns:
            Serialized dictionary containing event data and references.
        """
        data = super().serialize()
        
        # Save routine reference (via routine_id)
        if self.routine:
            data["_routine_id"] = self.routine._id
        
        return data
    
    def deserialize(self, data: Dict[str, Any]) -> None:
        """Deserialize the Event.

        Args:
            data: Serialized data dictionary.
        """
        # Save routine_id for later reference restoration
        routine_id = data.pop("_routine_id", None)
        
        # Deserialize basic fields
        super().deserialize(data)
        
        # Routine reference needs to be restored when Flow is reconstructed
        if routine_id:
            self._routine_id = routine_id
    
    def __repr__(self) -> str:
        """Return string representation of the Event."""
        if self.routine:
            return f"Event[{self.routine._id}.{self.name}]"
        else:
            return f"Event[{self.name}]"
    
    def connect(self, slot: 'Slot', param_mapping: Optional[Dict[str, str]] = None) -> None:
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
    
    def disconnect(self, slot: 'Slot') -> None:
        """Disconnect from a slot.

        Args:
            slot: Slot object to disconnect from.
        """
        if slot in self.connected_slots:
            self.connected_slots.remove(slot)
            # Bidirectional disconnection
            if self in slot.connected_events:
                slot.connected_events.remove(self)
    
    def emit(self, flow: Optional['Flow'] = None, **kwargs) -> None:
        """Emit the event and send data to all connected slots.
        
        In concurrent mode, uses a thread pool to execute connected routines concurrently.

        Args:
            flow: Flow object (used to find Connection for parameter mapping).
            **kwargs: Data to transmit.
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
            from concurrent.futures import ThreadPoolExecutor, Future
            
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
                            s.routine._stats.setdefault("errors", []).append({
                                "slot": s.name,
                                "error": str(e)
                            })
                
                # Submit task to thread pool without waiting (avoid nested waits causing deadlock)
                future = executor.submit(activate_slot)
                
                # Add future to Flow's tracking set (add immediately after submission to avoid race conditions)
                if flow is not None and hasattr(flow, '_active_futures'):
                    with flow._execution_lock:
                        flow._active_futures.add(future)
                    
                    # Add callback to automatically remove when task completes (add callback outside lock to avoid deadlock)
                    def remove_future(fut=future, f=flow):
                        """Remove from tracking set when task completes."""
                        if f is not None and hasattr(f, '_active_futures'):
                            with f._execution_lock:
                                f._active_futures.discard(fut)
                    
                    # Note: If future is already done, callback executes immediately
                    future.add_done_callback(remove_future)
            
            # Note: Do not wait for futures to complete, let them execute asynchronously
            # This avoids deadlock issues with nested concurrent execution
            # If waiting is needed, call Flow.wait_for_completion() or Flow.shutdown()

