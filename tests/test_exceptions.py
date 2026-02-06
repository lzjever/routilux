"""Tests for custom exception hierarchy."""

from routilux.exceptions import (
    ConfigurationError,
    ExecutionError,
    RoutiluxError,
    SerializationError,
    SlotHandlerError,
    StateError,
)


class TestRoutiluxError:
    """Tests for base RoutiluxError."""

    def test_base_exception_is_exception(self):
        """RoutiluxError should be an Exception subclass."""
        assert issubclass(RoutiluxError, Exception)

    def test_base_exception_can_be_instantiated(self):
        """RoutiluxError should be instantiable with a message."""
        exc = RoutiluxError("test message")
        assert str(exc) == "test message"
        assert isinstance(exc, Exception)


class TestExecutionError:
    """Tests for ExecutionError."""

    def test_execution_error_is_routilux_error(self):
        """ExecutionError should be a RoutiluxError subclass."""
        assert issubclass(ExecutionError, RoutiluxError)

    def test_execution_error_with_routine_id(self):
        """ExecutionError should support routine_id context."""
        exc = ExecutionError("Failed to execute", routine_id="test_routine")
        assert str(exc) == "Failed to execute (routine_id=test_routine)"
        assert exc.routine_id == "test_routine"

    def test_execution_error_can_wrap_original_exception(self):
        """ExecutionError should support exception chaining."""
        original = ValueError("original error")
        try:
            raise ExecutionError("Wrapper error") from original
        except ExecutionError as exc:
            assert exc.__cause__ is original


class TestSerializationError:
    """Tests for SerializationError."""

    def test_serialization_error_is_routilux_error(self):
        """SerializationError should be a RoutiluxError subclass."""
        assert issubclass(SerializationError, RoutiluxError)

    def test_serialization_error_with_object_type(self):
        """SerializationError should support object_type context."""
        exc = SerializationError("Cannot serialize", object_type="MyClass")
        assert str(exc) == "Cannot serialize (type=MyClass)"
        assert exc.object_type == "MyClass"


class TestConfigurationError:
    """Tests for ConfigurationError."""

    def test_configuration_error_is_routilux_error(self):
        """ConfigurationError should be a RoutiluxError subclass."""
        assert issubclass(ConfigurationError, RoutiluxError)


class TestStateError:
    """Tests for StateError."""

    def test_state_error_is_routilux_error(self):
        """StateError should be a RoutiluxError subclass."""
        assert issubclass(StateError, RoutiluxError)


class TestSlotHandlerError:
    """Tests for SlotHandlerError."""

    def test_slot_handler_error_is_routilux_error(self):
        """SlotHandlerError should be a RoutiluxError subclass."""
        assert issubclass(SlotHandlerError, RoutiluxError)

    def test_slot_handler_error_with_slot_name(self):
        """SlotHandlerError should support slot_name context."""
        exc = SlotHandlerError("Handler failed", slot_name="input_slot")
        assert str(exc) == "Handler failed (slot=input_slot)"
        assert exc.slot_name == "input_slot"
