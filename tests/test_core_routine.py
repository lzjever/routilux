"""Tests for Routine class."""

import pytest

from routilux.core import Routine


class TestRoutine:
    """Test Routine class."""

    def test_routine_creation(self):
        """Test creating a routine."""

        class TestRoutine(Routine):
            def setup(self):
                pass

        routine = TestRoutine()

        assert routine._id is not None
        assert routine._slots == {}
        assert routine._events == {}
        assert routine._config == {}

    def test_routine_add_slot(self):
        """Test adding a slot to a routine."""

        class TestRoutine(Routine):
            def setup(self):
                self.add_slot("input")

        routine = TestRoutine()
        routine.setup()

        assert "input" in routine._slots
        assert routine._slots["input"].name == "input"

    def test_routine_add_event(self):
        """Test adding an event to a routine."""

        class TestRoutine(Routine):
            def setup(self):
                self.add_event("output")

        routine = TestRoutine()
        routine.setup()

        assert "output" in routine._events
        assert routine._events["output"].name == "output"

    def test_routine_set_config(self):
        """Test setting routine configuration."""

        class TestRoutine(Routine):
            def setup(self):
                pass

        routine = TestRoutine()
        routine.set_config(name="test", timeout=30)

        assert routine._config["name"] == "test"
        assert routine._config["timeout"] == 30

    def test_routine_get_execution_context_no_context(self):
        """Test getting execution context when not in execution."""

        class TestRoutine(Routine):
            def setup(self):
                pass

        routine = TestRoutine()
        context = routine.get_execution_context()

        # Should return None when not in execution context
        assert context is None

    def test_routine_emit_requires_context(self):
        """Test that emit requires execution context."""

        class TestRoutine(Routine):
            def setup(self):
                self.add_event("output")

        routine = TestRoutine()
        routine.setup()

        # Emit should fail without execution context
        with pytest.raises((AttributeError, RuntimeError)):
            routine.emit("output", data={"test": "value"})


class TestRoutineLogic:
    """Test routine logic execution."""

    def test_routine_logic_execution(self):
        """Test that routine logic can be executed."""

        class ProcessorRoutine(Routine):
            def setup(self):
                self.add_slot("input")
                self.add_event("output")

            def logic(self, input_data, **kwargs):
                return {"result": input_data.get("value", 0) * 2}

        routine = ProcessorRoutine()
        routine.setup()

        # Test logic directly (not through slot call)
        result = routine.logic({"value": 5})
        assert result == {"result": 10}

    def test_routine_logic_with_kwargs(self):
        """Test routine logic with additional kwargs."""

        class TestRoutine(Routine):
            def setup(self):
                self.add_slot("input")

            def logic(self, input_data, **kwargs):
                return {"data": input_data, "extra": kwargs.get("extra", None)}

        routine = TestRoutine()
        routine.setup()

        result = routine.logic({"test": "data"}, extra="value")
        assert result["data"] == {"test": "data"}
        assert result["extra"] == "value"
