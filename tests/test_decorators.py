"""
Tests for the @routine decorator.
"""


from routilux import Flow, routine


class TestRoutineDecorator:
    """Tests for the @routine decorator."""

    def test_basic_routine_creation(self):
        """Test that @routine creates a valid Routine class."""

        @routine()
        def double(data):
            return data * 2

        # Should be a class
        assert isinstance(double, type)

        # Create instance
        instance = double()
        assert hasattr(instance, "_slots")
        assert hasattr(instance, "_events")
        assert "input" in instance._slots
        assert "output" in instance._events

    def test_custom_slot_event_names(self):
        """Test custom slot and event names."""

        @routine(input_slot="data_in", output_event="result")
        def process(data):
            return {"processed": data}

        instance = process()
        assert "data_in" in instance._slots
        assert "result" in instance._events

    def test_routine_class_name(self):
        """Test that routine class has correct name."""

        @routine()
        def my_processor(data):
            return data

        assert my_processor.__name__ == "my_processor"

        @routine(name="CustomName")
        def another_func(data):
            return data

        assert another_func.__name__ == "CustomName"

    def test_routine_has_activation_policy(self):
        """Test that routine has activation policy set."""

        @routine()
        def simple(data):
            return data

        instance = simple()
        assert instance._activation_policy is not None
        assert instance._logic is not None


class TestRoutineDecoratorIntegration:
    """Integration tests for @routine with Flow and Runtime."""

    def test_routine_in_flow(self):
        """Test that decorated routine can be added to a Flow."""

        @routine()
        def add_one(data):
            return data + 1

        flow = Flow("test_flow")
        instance = add_one()
        flow.add_routine(instance, "adder")

        assert "adder" in flow.routines
        assert flow.routines["adder"] is instance

    def test_chain_with_pipe(self):
        """Test chaining decorated routines with pipe()."""

        @routine()
        def step1(data):
            return data * 2

        @routine()
        def step2(data):
            return data + 10

        flow = Flow("pipeline")
        flow.pipe(step1(), "step1")
        flow.pipe(step2(), "step2")

        assert len(flow.routines) == 2
        assert len(flow.connections) == 1
