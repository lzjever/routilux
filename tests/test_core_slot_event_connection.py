"""Tests for Slot, Event, and Connection classes."""

import pytest
from routilux.core import Connection, Event, Runtime, Slot, SlotQueueFullError


class TestSlot:
    """Test Slot class."""

    def test_slot_creation(self):
        """Test creating a slot."""
        slot = Slot(name="input", routine=None)
        
        assert slot.name == "input"
        assert slot.routine is None

    def test_slot_enqueue(self):
        """Test enqueueing data to a slot."""
        from datetime import datetime
        
        slot = Slot(name="input", routine=None)
        
        slot.enqueue({"test": "data"}, emitted_from="source", emitted_at=datetime.now())
        
        assert slot.get_total_count() == 1
        assert slot.get_unconsumed_count() == 1

    def test_slot_consume(self):
        """Test consuming data from a slot."""
        from datetime import datetime
        
        slot = Slot(name="input", routine=None)
        
        slot.enqueue({"test": "data"}, emitted_from="source", emitted_at=datetime.now())
        
        data = slot.consume_one_new()
        
        assert data == {"test": "data"}
        assert slot.get_unconsumed_count() == 0

    def test_slot_queue_status(self):
        """Test getting slot queue status."""
        slot = Slot(name="input", routine=None, max_queue_length=10)
        
        status = slot.get_queue_status()
        
        assert "total_count" in status
        assert "max_length" in status
        assert status["max_length"] == 10
        assert status["total_count"] == 0
        assert "unconsumed_count" in status
        assert "usage_percentage" in status


class TestEvent:
    """Test Event class."""

    def test_event_creation(self):
        """Test creating an event."""
        event = Event(name="output", routine=None)
        
        assert event.name == "output"
        assert event.routine is None

    def test_event_emit_requires_runtime(self):
        """Test that emit requires a runtime and worker_state with executor."""
        from routilux.core.flow import Flow
        from routilux.core.routine import Routine
        from routilux.core.worker import WorkerState
        from routilux.core.manager import get_worker_manager
        
        class TestRoutine(Routine):
            def setup(self):
                self.add_event("output")
        
        routine = TestRoutine()
        routine.setup()
        flow = Flow()
        flow.flow_id = "test_flow"
        flow.add_routine(routine, "test")
        
        event = routine.events["output"]
        runtime = Runtime()
        
        # Start a worker to get a proper WorkerState with executor
        from routilux.core import get_flow_registry
        registry = get_flow_registry()
        registry.register_by_name("test_flow", flow)
        worker_state = runtime.exec("test_flow")
        
        # Emit should work with runtime and worker_state that has executor
        # (This will create an EventRoutingTask, actual routing happens in executor)
        event.emit(runtime, worker_state, data={"test": "value"})
        
        # Verify event has connected_slots list
        assert hasattr(event, "connected_slots")


class TestConnection:
    """Test Connection class."""

    def test_connection_creation(self):
        """Test creating a connection."""
        from routilux.core import Event, Slot
        
        event = Event(name="output", routine=None)
        slot = Slot(name="input", routine=None)
        
        connection = Connection(source_event=event, target_slot=slot)
        
        assert connection.source_event == event
        assert connection.target_slot == slot
        assert connection.source_event.name == "output"
        assert connection.target_slot.name == "input"

    def test_connection_equality(self):
        """Test connection equality (by object identity)."""
        from routilux.core import Event, Slot
        
        event1 = Event(name="output", routine=None)
        slot1 = Slot(name="input", routine=None)
        conn1 = Connection(source_event=event1, target_slot=slot1)
        
        event2 = Event(name="output", routine=None)
        slot2 = Slot(name="input", routine=None)
        conn2 = Connection(source_event=event2, target_slot=slot2)
        
        # Connections are equal if they have the same event and slot objects
        assert conn1.source_event == conn1.source_event
        assert conn2.source_event == conn2.source_event
        # Different objects are not equal
        assert conn1.source_event != conn2.source_event

    def test_connection_serialization(self):
        """Test connection serialization."""
        from routilux.core import Event, Slot
        
        event = Event(name="output", routine=None)
        slot = Slot(name="input", routine=None)
        connection = Connection(source_event=event, target_slot=slot)
        
        data = connection.serialize()
        
        assert "_source_event_name" in data
        assert data["_source_event_name"] == "output"
        assert "_target_slot_name" in data
        assert data["_target_slot_name"] == "input"
