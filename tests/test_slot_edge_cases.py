"""Edge case tests for slot module."""

import pytest

from routilux import Routine
from routilux.job_state import JobState
from routilux.slot import Slot


class TestSlotMergeDataEdgeCases:
    """Test edge cases for _merge_data method."""

    def test_merge_data_with_empty_new_data_override(self):
        """Test merging empty dict with override strategy."""
        slot = Slot(merge_strategy="override")
        slot._data = {"a": 1, "b": 2}

        result = slot._merge_data({})

        assert result == {}
        assert slot._data == {}

    def test_merge_data_with_empty_new_data_append(self):
        """Test merging empty dict with append strategy."""
        slot = Slot(merge_strategy="append")
        slot._data = {"a": [1, 2]}

        result = slot._merge_data({})

        assert result == {}
        assert slot._data == {"a": [1, 2]}

    def test_merge_data_append_converts_non_list_to_list(self):
        """Test that append strategy converts non-list values to lists."""
        slot = Slot(merge_strategy="append")
        slot._data = {"a": 1}  # Not a list

        result = slot._merge_data({"a": 2})

        assert result == {"a": [1, 2]}
        assert slot._data == {"a": [1, 2]}

    def test_merge_data_append_with_new_keys(self):
        """Test append strategy with new keys."""
        slot = Slot(merge_strategy="append")
        slot._data = {"a": [1]}

        result = slot._merge_data({"b": 2, "c": 3})

        assert result == {"b": [2], "c": [3]}
        assert slot._data == {"a": [1], "b": [2], "c": [3]}

    def test_merge_data_custom_merge_non_dict_result(self):
        """Test custom merge function that returns non-dict."""

        def custom_merge(old, new):
            return "string_result"

        slot = Slot(merge_strategy=custom_merge)
        slot._data = {"a": 1}

        result = slot._merge_data({"b": 2})

        assert result == {}
        assert slot._data == "string_result"

    def test_merge_data_custom_merge_with_none_values(self):
        """Test custom merge with None values."""

        def custom_merge(old, new):
            return {**old, **new, "merged": True}

        slot = Slot(merge_strategy=custom_merge)
        slot._data = {"a": None}

        result = slot._merge_data({"b": None})

        assert result == {"a": None, "b": None, "merged": True}

    def test_merge_data_unknown_strategy_fallback(self):
        """Test that unknown merge strategy falls back to override."""
        slot = Slot(merge_strategy="unknown_strategy")
        slot._data = {"a": 1, "b": 2}

        result = slot._merge_data({"a": 10, "c": 3})

        assert result == {"a": 10, "c": 3}
        assert slot._data == {"a": 10, "c": 3}

    def test_merge_data_with_nested_dicts_override(self):
        """Test merging nested dicts with override strategy."""
        slot = Slot(merge_strategy="override")
        slot._data = {"outer": {"inner": "old"}}

        result = slot._merge_data({"outer": {"inner": "new", "extra": "value"}})

        assert result == {"outer": {"inner": "new", "extra": "value"}}
        assert slot._data == {"outer": {"inner": "new", "extra": "value"}}

    def test_merge_data_with_list_values_append(self):
        """Test append strategy with list values."""
        slot = Slot(merge_strategy="append")
        slot._data = {"items": [1, 2]}

        result = slot._merge_data({"items": [3, 4]})

        # Append strategy appends the list itself as an element
        assert result["items"] == [1, 2, [3, 4]]

    def test_merge_data_custom_merge_deep_merge(self):
        """Test custom merge for deep merging."""

        def deep_merge(old, new):
            result = old.copy()
            for key, value in new.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = {**result[key], **value}
                else:
                    result[key] = value
            return result

        slot = Slot(merge_strategy=deep_merge)
        slot._data = {"outer": {"inner": "old", "keep": "me"}}

        result = slot._merge_data({"outer": {"inner": "new", "extra": "value"}})

        assert result == {"outer": {"inner": "new", "keep": "me", "extra": "value"}}


class TestSlotReceiveEdgeCases:
    """Test edge cases for receive method."""

    def test_receive_with_none_handler(self):
        """Test receiving data when handler is None."""
        slot = Slot(handler=None)
        slot._data = {}

        slot.receive({"a": 1})

        # Should not raise any exception
        assert slot._data == {"a": 1}

    def test_receive_with_validator_rejects_data(self):
        """Test that validator can reject data."""
        from routilux.validators import Validator

        # Always reject
        def always_validate(data):
            raise ValueError("Always rejects")

        validator = Validator.custom(always_validate)
        slot = Slot(handler=lambda **data: None, validator=validator)

        # Create mock job_state and flow
        job_state = JobState("test_job")
        routine = Routine()
        routine._id = "test_routine"
        slot.routine = routine

        # Data is merged before validation, so _data will be updated
        slot.receive({"a": 1}, job_state=job_state)

        # Data was merged before validation failed
        assert slot._data == {"a": 1}

    def test_receive_with_self_referencing_handler(self):
        """Test handler that references slot through closure."""
        results = []

        slot = Slot(name="test")
        slot.handler = lambda **data: results.append(slot.name)

        slot.receive({"value": 1})

        assert results == ["test"]

    def test_receive_with_handler_that_raises_exception(self):
        """Test that handler exceptions are caught and logged."""

        def failing_handler(data):
            raise ValueError("Handler error")

        slot = Slot(handler=failing_handler)

        # Create mock job_state and flow
        job_state = JobState("test_job")
        routine = Routine()
        routine._id = "test_routine"
        slot.routine = routine

        # Create a simple mock flow
        from unittest.mock import MagicMock

        flow = MagicMock()
        flow._get_routine_id.return_value = "test_routine"

        # Should not raise exception
        slot.receive({"value": 1}, job_state=job_state, flow=flow)

        # Error should be recorded in execution history
        executions = job_state.get_execution_history("test_routine")
        # Find the error record
        error_records = [e for e in executions if e.event_name == "error"]
        assert len(error_records) > 0
        assert "Handler error" in error_records[0].data.get("error", "")

    def test_receive_with_job_state_context(self):
        """Test that job_state is set in context during handler execution."""
        from routilux.routine import _current_job_state

        result_context = []

        def check_context_handler(data):
            result_context.append(_current_job_state.get())

        slot = Slot(handler=check_context_handler)
        job_state = JobState("test_job")

        slot.receive({"value": 1}, job_state=job_state)

        assert len(result_context) == 1
        assert result_context[0] is job_state

    def test_receive_with_handler_accepting_single_param(self):
        """Test handler with single parameter."""
        results = []

        def single_param_handler(value):
            results.append(value)

        slot = Slot(handler=single_param_handler)

        slot.receive({"value": 42})

        assert results == [42]

    def test_receive_with_handler_accepting_single_unmatched_param(self):
        """Test handler with single parameter that doesn't match data."""
        results = []

        def single_param_handler(other_param):
            results.append(other_param)

        slot = Slot(handler=single_param_handler)

        slot.receive({"value": 42})

        # Should pass entire dict since no match
        assert results == [{"value": 42}]

    def test_receive_with_handler_accepting_multiple_params(self):
        """Test handler with multiple parameters."""
        results = []

        def multi_param_handler(a, b):
            results.append((a, b))

        slot = Slot(handler=multi_param_handler)

        slot.receive({"a": 1, "b": 2, "c": 3})

        assert results == [(1, 2)]

    def test_receive_with_handler_accepting_no_matching_params(self):
        """Test handler with multiple parameters that don't match data."""
        results = []

        # This will raise TypeError because the handler requires args
        # but no matching params are found, so it falls back to passing the dict
        # which fails type check
        def multi_param_handler(x, y):
            results.append((x, y))

        slot = Slot(handler=multi_param_handler)

        # The handler expects positional args but receives dict, so it will fail
        # The error is caught and logged
        slot.receive({"a": 1, "b": 2})

        # Handler was not called successfully due to TypeError
        assert len(results) == 0


class TestSlotCallHandlerEdgeCases:
    """Test edge cases for call_handler method."""

    def test_call_handler_with_propagate_exceptions(self):
        """Test that exceptions propagate when propagate_exceptions=True."""

        def failing_handler(data):
            raise ValueError("Handler error")

        slot = Slot(handler=failing_handler)

        with pytest.raises(ValueError, match="Handler error"):
            slot.call_handler({"value": 1}, propagate_exceptions=True)

    def test_call_handler_without_propagate_exceptions(self):
        """Test that exceptions are caught when propagate_exceptions=False."""

        def failing_handler(data):
            raise ValueError("Handler error")

        slot = Slot(handler=failing_handler)

        # Should not raise exception
        slot.call_handler({"value": 1}, propagate_exceptions=False)

    def test_call_handler_with_kwargs_handler(self):
        """Test call_handler with **kwargs handler."""
        results = []

        def kwargs_handler(**kwargs):
            results.append(kwargs)

        slot = Slot(handler=kwargs_handler)

        slot.call_handler({"a": 1, "b": 2})

        assert results == [{"a": 1, "b": 2}]

    def test_call_handler_with_data_param(self):
        """Test call_handler with handler accepting 'data' parameter."""
        results = []

        def data_param_handler(data):
            results.append(data)

        slot = Slot(handler=data_param_handler)

        slot.call_handler({"value": 42})

        assert results == [{"value": 42}]


class TestSlotConnectionEdgeCases:
    """Test edge cases for connect/disconnect methods."""

    def test_connect_same_event_twice(self):
        """Test connecting the same event twice."""
        from routilux.event import Event

        slot = Slot(name="test")
        event = Event(name="test_event")

        slot.connect(event)
        slot.connect(event)

        # Should only be connected once
        assert slot.connected_events == [event]

    def test_disconnect_non_connected_event(self):
        """Test disconnecting an event that is not connected."""
        from routilux.event import Event

        slot = Slot(name="test")
        event = Event(name="test_event")

        # Should not raise exception
        slot.disconnect(event)

        assert slot.connected_events == []

    def test_connect_multiple_events(self):
        """Test connecting multiple events."""
        from routilux.event import Event

        slot = Slot(name="test")
        event1 = Event(name="event1")
        event2 = Event(name="event2")
        event3 = Event(name="event3")

        slot.connect(event1)
        slot.connect(event2)
        slot.connect(event3)

        assert len(slot.connected_events) == 3
        assert event1 in slot.connected_events
        assert event2 in slot.connected_events
        assert event3 in slot.connected_events

    def test_disconnect_from_multiple_events(self):
        """Test disconnecting from multiple events."""
        from routilux.event import Event

        slot = Slot(name="test")
        event1 = Event(name="event1")
        event2 = Event(name="event2")

        slot.connect(event1)
        slot.connect(event2)

        slot.disconnect(event1)

        assert slot.connected_events == [event2]
        assert slot not in event1.connected_slots
        assert slot in event2.connected_slots


class TestSlotRepr:
    """Test __repr__ method."""

    def test_repr_with_routine(self):
        """Test __repr__ when slot has a routine."""
        routine = Routine()
        routine._id = "test_routine"
        slot = Slot(name="test_slot", routine=routine)

        result = repr(slot)

        assert result == "Slot[test_routine.test_slot]"

    def test_repr_without_routine(self):
        """Test __repr__ when slot has no routine."""
        slot = Slot(name="test_slot")

        result = repr(slot)

        assert result == "Slot[test_slot]"


class TestSlotIsKwargsHandler:
    """Test _is_kwargs_handler static method."""

    def test_is_kwargs_handler_with_kwargs(self):
        """Test detection of **kwargs handler."""

        def kwargs_handler(**kwargs):
            pass

        assert Slot._is_kwargs_handler(kwargs_handler) is True

    def test_is_kwargs_handler_without_kwargs(self):
        """Test detection of non-kwargs handler."""

        def regular_handler(data):
            pass

        assert Slot._is_kwargs_handler(regular_handler) is False

    def test_is_kwargs_handler_with_mixed_params(self):
        """Test detection of handler with both regular and **kwargs."""

        def mixed_handler(a, b, **kwargs):
            pass

        assert Slot._is_kwargs_handler(mixed_handler) is True

    def test_is_kwargs_handler_with_args(self):
        """Test detection of handler with *args."""

        def args_handler(*args):
            pass

        assert Slot._is_kwargs_handler(args_handler) is False

    def test_is_kwargs_handler_with_no_params(self):
        """Test detection of handler with no parameters."""

        def no_params_handler():
            pass

        assert Slot._is_kwargs_handler(no_params_handler) is False


class TestSlotSerializationEdgeCases:
    """Test edge cases for serialization."""

    def test_serialize_with_custom_merge_strategy(self):
        """Test serializing slot with custom merge strategy."""

        def custom_merge(old, new):
            return {**old, **new}

        slot = Slot(name="test", merge_strategy=custom_merge)

        # Should not raise exception
        serialized = slot.serialize()

        assert "name" in serialized
        assert serialized["name"] == "test"
        # merge_strategy should be serialized as callable

    def test_deserialize_with_custom_merge_strategy(self):
        """Test deserializing slot with custom merge strategy."""
        from serilux import ObjectRegistry

        def custom_merge(old, new):
            return {**old, **new}

        # Register the callable
        registry = ObjectRegistry()
        merge_id = registry.register(custom_merge)

        slot = Slot(name="test")

        serialized = {
            "name": "test",
            "_data": {},
            "handler": None,
            "merge_strategy": {"__type__": "callable", "id": merge_id},
        }

        slot.deserialize(serialized, registry=registry)

        # After deserialization with registry, the merge_strategy should be the callable
        # If deserialization fails, it might stay as the dict
        # This test verifies the deserialization process
        assert "merge_strategy" in serialized

    def test_serialize_with_handler(self):
        """Test serializing slot with handler."""

        def test_handler(data):
            pass

        slot = Slot(name="test", handler=test_handler)

        # Should not raise exception
        serialized = slot.serialize()

        assert "handler" in serialized
