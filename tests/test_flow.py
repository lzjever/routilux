"""
Flow tests for current API.

Tests for Flow class functionality using Runtime API for execution.
"""

import pytest

from routilux import Flow, Routine
from routilux.core import FlowRegistry


class TestFlowManagement:
    """Flow management tests."""

    def test_create_flow(self):
        """Test creating a Flow."""
        # With auto-generated flow_id
        flow = Flow()
        assert flow.flow_id is not None

        # With specified flow_id
        flow = Flow(flow_id="test_flow")
        assert flow.flow_id == "test_flow"

    def test_add_routine(self):
        """Test adding a Routine."""
        flow = Flow()
        routine = Routine()

        # Add routine with auto-generated id
        routine_id = flow.add_routine(routine)
        assert routine_id is not None
        assert routine_id in flow.routines
        assert flow.routines[routine_id] == routine

        # Add routine with specified id
        routine = Routine()
        routine_id2 = flow.add_routine(routine, routine_id="custom_id")
        assert routine_id2 == "custom_id"
        assert "custom_id" in flow.routines

    def test_connect_routines(self):
        """Test connecting Routines."""
        flow = Flow()

        routine1 = Routine()
        routine2 = Routine()

        # Define events and slots
        routine1.add_event("output", ["data"])
        routine2.add_slot("input")

        # Add to flow
        id1 = flow.add_routine(routine1, "routine1")
        id2 = flow.add_routine(routine2, "routine2")

        # Connect
        connection = flow.connect(id1, "output", id2, "input")
        assert connection is not None
        assert connection in flow.connections

    def test_connect_invalid_routine(self):
        """Test invalid connection - nonexistent routine."""
        flow = Flow()

        # Trying to connect nonexistent routine should raise error
        with pytest.raises(ValueError):
            flow.connect("nonexistent", "output", "target", "input")

    def test_connect_invalid_event(self):
        """Test invalid connection - nonexistent event."""
        flow = Flow()

        routine1 = Routine()
        routine2 = Routine()

        id1 = flow.add_routine(routine1, "routine1")
        id2 = flow.add_routine(routine2, "routine2")

        # Trying to connect nonexistent event should raise error
        with pytest.raises(ValueError):
            flow.connect(id1, "nonexistent_event", id2, "input")

    def test_connect_invalid_slot(self):
        """Test invalid connection - nonexistent slot."""
        flow = Flow()

        routine1 = Routine()
        routine2 = Routine()

        routine1.add_event("output")

        id1 = flow.add_routine(routine1, "routine1")
        id2 = flow.add_routine(routine2, "routine2")

        # Trying to connect nonexistent slot should raise error
        with pytest.raises(ValueError):
            flow.connect(id1, "output", id2, "nonexistent_slot")


class TestFlowConfiguration:
    """Flow configuration tests."""

    def test_empty_flow(self):
        """Test empty Flow."""
        flow = Flow()

        assert len(flow.routines) == 0
        assert len(flow.connections) == 0

    def test_flow_with_multiple_routines(self):
        """Test flow with multiple routines."""
        flow = Flow()

        routine1 = Routine()
        routine2 = Routine()
        routine3 = Routine()

        routine1.add_event("output")
        routine2.add_slot("input")
        routine2.add_event("output")
        routine3.add_slot("input")

        id1 = flow.add_routine(routine1, "r1")
        id2 = flow.add_routine(routine2, "r2")
        id3 = flow.add_routine(routine3, "r3")

        flow.connect(id1, "output", id2, "input")
        flow.connect(id2, "output", id3, "input")

        assert len(flow.routines) == 3
        assert len(flow.connections) == 2

    def test_flow_error_handler(self):
        """Test flow error handler."""
        from routilux import ErrorHandler, ErrorStrategy

        flow = Flow()
        handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)

        flow.set_error_handler(handler)

        assert flow.error_handler == handler

    def test_flow_get_error_handler(self):
        """Test flow get_error_handler."""
        from routilux import ErrorHandler, ErrorStrategy

        flow = Flow()

        # No error handler by default
        assert flow.get_error_handler() is None

        # Set error handler
        handler = ErrorHandler(strategy=ErrorStrategy.STOP)
        flow.set_error_handler(handler)

        assert flow.get_error_handler() == handler


class TestFlowSerialization:
    """Flow serialization tests."""

    def test_flow_serialize(self):
        """Test flow serialization."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.add_slot("input")
        routine.add_event("output", ["data"])

        flow.add_routine(routine, "test_routine")

        data = flow.serialize()

        assert "flow_id" in data
        assert "routines" in data
        assert "connections" in data

    def test_flow_deserialize(self):
        """Test flow deserialization."""
        flow = Flow("test_flow")

        routine = Routine()
        routine.add_slot("input")
        routine.add_event("output")

        flow.add_routine(routine, "test_routine")

        # Serialize and deserialize
        data = flow.serialize()
        new_flow = Flow()
        new_flow.deserialize(data)

        assert new_flow.flow_id == flow.flow_id


class TestFlowFindRoutines:
    """Test Flow.find_routines_by_type method."""

    def test_find_routines_by_type(self):
        """Test finding routines by type."""

        class CustomRoutine(Routine):
            pass

        flow = Flow()

        r1 = Routine()
        r2 = CustomRoutine()
        r3 = CustomRoutine()

        flow.add_routine(r1, "standard")
        flow.add_routine(r2, "custom1")
        flow.add_routine(r3, "custom2")

        # Find CustomRoutine instances
        found = flow.find_routines_by_type(CustomRoutine)

        assert len(found) == 2
        ids = [rid for rid, _ in found]
        assert "custom1" in ids
        assert "custom2" in ids


class TestFlowRegistry:
    """Test flow registration with FlowRegistry."""

    def test_register_flow_by_name(self):
        """Test registering flow by name."""
        # Reset registry
        FlowRegistry._instance = None
        registry = FlowRegistry.get_instance()

        flow = Flow("registered_flow")
        registry.register_by_name("my_flow", flow)

        # Retrieve by name
        retrieved = registry.get_by_name("my_flow")
        assert retrieved is flow

    def test_register_flow_weak_ref(self):
        """Test registering flow with weak reference."""
        # Reset registry
        FlowRegistry._instance = None
        registry = FlowRegistry.get_instance()

        flow = Flow("weak_flow")
        registry.register(flow)

        # Should be retrievable by flow_id
        retrieved = registry.get(flow.flow_id)
        assert retrieved is not None
