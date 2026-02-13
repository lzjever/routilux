"""
Tests for the Flow.pipe() method.
"""


from routilux import Flow, Routine
from routilux.builtin_routines import Mapper


class TestFlowPipe:
    """Tests for the Flow.pipe() method."""

    def test_pipe_adds_routine(self):
        """Test that pipe() adds a routine to the flow."""
        flow = Flow("test")
        mapper = Mapper()

        result = flow.pipe(mapper, "mapper")

        # Returns self for chaining
        assert result is flow
        assert "mapper" in flow.routines

    def test_pipe_creates_connection(self):
        """Test that pipe() creates connection to previous routine."""
        flow = Flow("test")
        mapper1 = Mapper()
        mapper2 = Mapper()

        flow.pipe(mapper1, "m1")
        flow.pipe(mapper2, "m2")

        # Should have 2 routines and 1 connection
        assert len(flow.routines) == 2
        assert len(flow.connections) == 1

        # Verify connection is from m1.output to m2.input
        conn = flow.connections[0]
        assert conn.source_event.name == "output"
        assert conn.target_slot.name == "input"

    def test_pipe_chain(self):
        """Test chaining multiple pipe() calls."""
        flow = Flow("pipeline")

        flow.pipe(Mapper(), "step1")
        flow.pipe(Mapper(), "step2")
        flow.pipe(Mapper(), "step3")

        assert len(flow.routines) == 3
        assert len(flow.connections) == 2  # step1->step2, step2->step3

    def test_pipe_custom_event_slot(self):
        """Test pipe() with custom event and slot names."""
        flow = Flow("test")

        # Create routines with custom events/slots
        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.add_event("data")
                self.set_activation_policy(lambda s, w: (True, {}, "always"))

        class TargetRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.add_slot("items")
                self.add_event("output")
                self.set_activation_policy(lambda s, w: (False, {}, "never"))

        flow.pipe(SourceRoutine(), "source")
        flow.pipe(TargetRoutine(), "target", from_event="data", to_slot="items")

        assert len(flow.connections) == 1
        conn = flow.connections[0]
        assert conn.source_event.name == "data"
        assert conn.target_slot.name == "items"

    def test_pipe_from_specific_routine(self):
        """Test pipe() connecting from a specific routine."""
        flow = Flow("test")

        # Create a branching flow
        flow.pipe(Mapper(), "source")
        flow.pipe(Mapper(), "branch_a")

        # Connect branch_b also from source
        flow.pipe(Mapper(), "branch_b", from_routine="source")

        assert len(flow.routines) == 3
        assert len(flow.connections) == 2

        # Both connections should be from source
        for conn in flow.connections:
            assert conn.source_event.routine is flow.routines["source"]

    def test_first_pipe_no_connection(self):
        """Test that first pipe() doesn't create a connection."""
        flow = Flow("test")

        flow.pipe(Mapper(), "first")

        assert len(flow.routines) == 1
        assert len(flow.connections) == 0  # No previous routine to connect from

    def test_pipe_auto_id(self):
        """Test pipe() with auto-generated routine ID."""
        flow = Flow("test")
        mapper = Mapper()

        # Pipe without explicit ID uses routine._id
        flow.pipe(mapper)

        # Routine should be added
        assert len(flow.routines) == 1
