"""Tests for Flow class."""

import pytest
from routilux.core import Connection, Flow, Routine, WorkerNotRunningError


class TestFlow:
    """Test Flow class."""

    def test_flow_creation(self):
        """Test creating an empty flow."""
        flow = Flow()
        
        assert flow.flow_id is not None
        assert flow.routines == {}
        assert flow.connections == []
        assert flow.error_handler is None

    def test_flow_add_routine(self):
        """Test adding a routine to a flow."""
        class TestRoutine(Routine):
            def setup(self):
                self.add_slot("input")
        
        flow = Flow()
        routine = TestRoutine()
        routine.setup()
        
        routine_id = flow.add_routine(routine)
        
        assert routine_id in flow.routines
        assert flow.routines[routine_id] == routine

    def test_flow_add_routine_with_custom_id(self):
        """Test adding a routine with a custom ID."""
        class TestRoutine(Routine):
            def setup(self):
                pass
        
        flow = Flow()
        routine = TestRoutine()
        routine.setup()
        
        routine_id = flow.add_routine(routine, routine_id="custom_id")
        
        assert routine_id == "custom_id"
        assert flow.routines["custom_id"] == routine

    def test_flow_connect(self):
        """Test connecting routines in a flow."""
        class SourceRoutine(Routine):
            def setup(self):
                self.add_event("output")
        
        class TargetRoutine(Routine):
            def setup(self):
                self.add_slot("input")
        
        flow = Flow()
        source = SourceRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        
        connection = flow.connect(source_id, "output", target_id, "input")
        
        assert isinstance(connection, Connection)
        assert connection.source_event is not None
        assert connection.source_event.name == "output"
        assert connection.target_slot is not None
        assert connection.target_slot.name == "input"
        assert connection in flow.connections

    def test_flow_connect_invalid_source(self):
        """Test connecting with invalid source routine."""
        flow = Flow()
        
        with pytest.raises(ValueError):
            flow.connect("nonexistent", "event", "target", "slot")

    def test_flow_connect_invalid_event(self):
        """Test connecting with invalid event name."""
        class TestRoutine(Routine):
            def setup(self):
                self.add_event("output")
        
        flow = Flow()
        routine = TestRoutine()
        routine.setup()
        routine_id = flow.add_routine(routine, "source")
        
        with pytest.raises(ValueError):
            flow.connect(routine_id, "nonexistent_event", "target", "slot")

    def test_flow_serialization(self):
        """Test flow serialization."""
        class TestRoutine(Routine):
            def setup(self):
                self.add_slot("input")
                self.add_event("output")
        
        flow = Flow()
        routine = TestRoutine()
        routine.setup()
        flow.add_routine(routine, "test")
        
        data = flow.serialize()
        
        assert "flow_id" in data
        assert "routines" in data
        assert "connections" in data
        assert data["flow_id"] == flow.flow_id

    def test_flow_deserialization(self):
        """Test flow deserialization."""
        class TestRoutine(Routine):
            def setup(self):
                self.add_slot("input")
                self.add_event("output")
        
        flow = Flow()
        routine = TestRoutine()
        routine.setup()
        flow.add_routine(routine, "test")
        
        data = flow.serialize()
        restored = Flow()
        restored.deserialize(data)
        
        assert restored.flow_id == flow.flow_id
        assert len(restored.routines) == 1
        assert "test" in restored.routines
