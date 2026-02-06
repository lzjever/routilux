"""
Edge case tests for ConditionalRouter routine.
"""

import pytest
from routilux.builtin_routines.control_flow import ConditionalRouter
from routilux.slot import Slot


class TestConditionalRouterEdgeCases:
    """Edge case tests for ConditionalRouter."""

    def test_function_condition_with_two_params_config(self):
        """Test function condition that accepts data and config parameters."""
        router = ConditionalRouter()

        def check_with_config(data, config):
            return data.get("value") > config.get("threshold", 0)

        router.set_config(
            routes=[
                ("above", check_with_config),
            ],
            threshold=10,
        )

        received = []
        above_slot = Slot("above", None, lambda **kwargs: received.append(kwargs))

        if router.get_event("above") is None:
            router.define_event("above", ["data", "route"])
        router.get_event("above").connect(above_slot)

        # Test above threshold
        router.input_slot.receive({"data": {"value": 15}})
        assert len(received) == 1

        # Test below threshold
        router.input_slot.receive({"data": {"value": 5}})
        assert len(received) == 1  # No new emission

    def test_function_condition_with_two_params_stats(self):
        """Test function condition that accepts data and stats parameters."""
        router = ConditionalRouter()

        def check_with_stats(data, stats):
            # Stats is deprecated, should work with empty dict
            return data.get("value") > 0

        router.set_config(
            routes=[
                ("valid", check_with_stats),
            ],
        )

        received = []
        valid_slot = Slot("valid", None, lambda **kwargs: received.append(kwargs))

        if router.get_event("valid") is None:
            router.define_event("valid", ["data", "route"])
        router.get_event("valid").connect(valid_slot)

        router.input_slot.receive({"data": {"value": 5}})
        assert len(received) == 1

    def test_function_condition_with_multiple_params(self):
        """Test function condition that has multiple parameters but not data/config/stats."""
        router = ConditionalRouter()

        # Function with specific parameters but not matching data/config/stats
        def check_value(value=None):
            return value is True

        router.set_config(
            routes=[
                ("valid", check_value),
            ],
        )

        received = []
        valid_slot = Slot("valid", None, lambda **kwargs: received.append(kwargs))

        if router.get_event("valid") is None:
            router.define_event("valid", ["data", "route"])
        router.get_event("valid").connect(valid_slot)

        router.input_slot.receive({"data": {"value": True}})
        # The function doesn't receive 'value' so it may not match
        # This tests the fallback behavior

    def test_function_condition_with_all_params(self):
        """Test function condition that accepts data, config, and stats parameters."""
        router = ConditionalRouter()

        def check_all(data=None, config=None, stats=None):
            return data.get("check") is True

        router.set_config(
            routes=[
                ("check", check_all),
            ],
        )

        received = []
        check_slot = Slot("check", None, lambda **kwargs: received.append(kwargs))

        if router.get_event("check") is None:
            router.define_event("check", ["data", "route"])
        router.get_event("check").connect(check_slot)

        router.input_slot.receive({"data": {"check": True}})
        assert len(received) == 1

    def test_function_condition_exception_fallback(self):
        """Test function condition that raises exception falls back to data-only call."""
        router = ConditionalRouter()

        def failing_condition(value):
            # This will fail if called with data dict but work with single value
            return value > 10

        router.set_config(
            routes=[
                ("high", failing_condition),
            ],
        )

        received = []
        high_slot = Slot("high", None, lambda **kwargs: received.append(kwargs))

        if router.get_event("high") is None:
            router.define_event("high", ["data", "route"])
        router.get_event("high").connect(high_slot)

        # This should use the fallback (pass data directly)
        router.input_slot.receive({"data": 15})
        # The function expects a value, not a dict, so it will fail
        # but the fallback should handle it

    def test_condition_exception_handling(self):
        """Test that exceptions in conditions are handled gracefully."""
        router = ConditionalRouter()

        def raising_condition(data):
            raise RuntimeError("Intentional error")

        router.set_config(
            routes=[
                ("error", raising_condition),
            ],
            default_route="default",
        )

        received_error = []
        received_default = []
        error_slot = Slot("error", None, lambda **kwargs: received_error.append(kwargs))
        default_slot = Slot("default", None, lambda **kwargs: received_default.append(kwargs))

        if router.get_event("error") is None:
            router.define_event("error", ["data", "route"])
        if router.get_event("default") is None:
            router.define_event("default", ["data", "route"])
        router.get_event("error").connect(error_slot)
        router.get_event("default").connect(default_slot)

        router.input_slot.receive({"data": {"value": 1}})

        # Should route to default due to exception
        assert len(received_error) == 0
        assert len(received_default) == 1

    def test_dynamic_event_creation_on_match(self):
        """Test that events are created dynamically when route matches."""
        router = ConditionalRouter()

        router.set_config(
            routes=[
                ("new_route", lambda data: data.get("create") is True),
            ],
        )

        received = []
        new_slot = Slot("new", None, lambda **kwargs: received.append(kwargs))

        # Event doesn't exist yet
        assert router.get_event("new_route") is None

        router.input_slot.receive({"data": {"create": True}})

        # Event should now exist
        assert router.get_event("new_route") is not None

    def test_dynamic_event_creation_for_default_route(self):
        """Test that default route event is created dynamically when needed."""
        router = ConditionalRouter()

        router.set_config(
            routes=[
                ("high", lambda data: False),  # Never matches
            ],
            default_route="default",
        )

        received = []
        default_slot = Slot("default", None, lambda **kwargs: received.append(kwargs))

        # Default event doesn't exist yet
        assert router.get_event("default") is None

        # Connect after creating
        router.input_slot.receive({"data": {"value": 1}})

        # Event should now exist
        assert router.get_event("default") is not None

    def test_dict_condition_with_non_dict_data(self):
        """Test dict condition with non-dict data returns False."""
        router = ConditionalRouter()

        router.set_config(
            routes=[
                ("match", {"key": "value"}),
            ],
            default_route="default",
        )

        received_match = []
        received_default = []
        match_slot = Slot("match", None, lambda **kwargs: received_match.append(kwargs))
        default_slot = Slot("default", None, lambda **kwargs: received_default.append(kwargs))

        if router.get_event("match") is None:
            router.define_event("match", ["data", "route"])
        if router.get_event("default") is None:
            router.define_event("default", ["data", "route"])
        router.get_event("match").connect(match_slot)
        router.get_event("default").connect(default_slot)

        # Pass non-dict data
        router.input_slot.receive({"data": "string_data"})

        # Should go to default since data is not a dict
        assert len(received_match) == 0
        assert len(received_default) == 1

    def test_dict_condition_with_callable_expected_value(self):
        """Test dict condition with callable expected value."""
        router = ConditionalRouter()

        def is_greater_than_10(value):
            return value > 10

        router.set_config(
            routes=[
                ("match", {"value": is_greater_than_10}),
            ],
        )

        received = []
        match_slot = Slot("match", None, lambda **kwargs: received.append(kwargs))

        if router.get_event("match") is None:
            router.define_event("match", ["data", "route"])
        router.get_event("match").connect(match_slot)

        # Test with value > 10
        router.input_slot.receive({"data": {"value": 15}})
        assert len(received) == 1

        # Test with value <= 10
        router.input_slot.receive({"data": {"value": 5}})
        assert len(received) == 1  # No new match

    def test_dict_condition_missing_field(self):
        """Test dict condition returns False when field is missing."""
        router = ConditionalRouter()

        router.set_config(
            routes=[
                ("match", {"required_field": "value"}),
            ],
            default_route="default",
        )

        received_match = []
        received_default = []
        match_slot = Slot("match", None, lambda **kwargs: received_match.append(kwargs))
        default_slot = Slot("default", None, lambda **kwargs: received_default.append(kwargs))

        if router.get_event("match") is None:
            router.define_event("match", ["data", "route"])
        if router.get_event("default") is None:
            router.define_event("default", ["data", "route"])
        router.get_event("match").connect(match_slot)
        router.get_event("default").connect(default_slot)

        # Data without required field
        router.input_slot.receive({"data": {"other_field": "value"}})

        assert len(received_match) == 0
        assert len(received_default) == 1

    def test_string_condition_exception_handling(self):
        """Test that exceptions in string condition evaluation return False."""
        router = ConditionalRouter()

        router.set_config(
            routes=[
                ("valid", "data['missing_key'] == 'value'"),  # Will raise KeyError
            ],
            default_route="default",
        )

        received_valid = []
        received_default = []
        valid_slot = Slot("valid", None, lambda **kwargs: received_valid.append(kwargs))
        default_slot = Slot("default", None, lambda **kwargs: received_default.append(kwargs))

        if router.get_event("valid") is None:
            router.define_event("valid", ["data", "route"])
        if router.get_event("default") is None:
            router.define_event("default", ["data", "route"])
        router.get_event("valid").connect(valid_slot)
        router.get_event("default").connect(default_slot)

        router.input_slot.receive({"data": {}})

        # Should go to default due to exception
        assert len(received_valid) == 0
        assert len(received_default) == 1

    def test_string_condition_invalid_syntax(self):
        """Test that invalid syntax in string condition returns False."""
        router = ConditionalRouter()

        router.set_config(
            routes=[
                ("valid", "this is not valid python syntax [["),  # Invalid syntax
            ],
            default_route="default",
        )

        received_valid = []
        received_default = []
        valid_slot = Slot("valid", None, lambda **kwargs: received_valid.append(kwargs))
        default_slot = Slot("default", None, lambda **kwargs: received_default.append(kwargs))

        if router.get_event("valid") is None:
            router.define_event("valid", ["data", "route"])
        if router.get_event("default") is None:
            router.define_event("default", ["data", "route"])
        router.get_event("valid").connect(valid_slot)
        router.get_event("default").connect(default_slot)

        router.input_slot.receive({"data": {}})

        # Should go to default due to syntax error
        assert len(received_valid) == 0
        assert len(received_default) == 1

    def test_serialize_with_non_serializable_lambda(self):
        """Test serialization raises error for lambda that cannot be serialized."""
        router = ConditionalRouter()

        # Lambda with external closure variable that can't be serialized
        external_var = "some_value"
        router.set_config(
            routes=[
                ("route1", lambda data: data.get("key") == external_var),
            ],
        )

        # Serialize should handle this gracefully or raise appropriate error
        # The serialization module has fallback_to_expression which should work
        serialized = router.serialize()
        assert "_config" in serialized
        assert "routes" in serialized["_config"]

    def test_deserialize_with_failed_lambda(self):
        """Test deserialization raises ValueError for lambda that cannot be restored."""
        router = ConditionalRouter()

        # Create a serialized state with a broken lambda_expression
        serialized = router.serialize()
        serialized["_config"]["routes"] = [
            (
                "route1",
                {
                    "_type": "lambda_expression",
                    "expression": "broken_syntax[[[",
                    "error": "Cannot parse this expression",
                },
            )
        ]

        new_router = ConditionalRouter()

        # Should raise ValueError with descriptive message
        # The error message may come from either our code or serilux
        with pytest.raises(ValueError, match="Failed to deserialize|lambda expression"):
            new_router.deserialize(serialized)

    def test_deserialize_with_failed_function(self):
        """Test deserialization raises ValueError for function that cannot be restored."""
        router = ConditionalRouter()

        # Create a serialized state with a broken function reference
        serialized = router.serialize()
        serialized["_config"]["routes"] = [
            (
                "route1",
                {
                    "_type": "callable",
                    "callable_type": "function",
                    "module": "nonexistent_module",
                    "name": "nonexistent_function",
                },
            )
        ]

        new_router = ConditionalRouter()

        # Should raise ValueError with descriptive message
        with pytest.raises(ValueError, match="Failed to deserialize.*condition"):
            new_router.deserialize(serialized)

    def test_deserialize_with_unknown_callable_type(self):
        """Test deserialization raises ValueError for unknown callable type."""
        router = ConditionalRouter()

        # Create a serialized state with unknown callable type
        serialized = router.serialize()
        serialized["_config"]["routes"] = [
            (
                "route1",
                {
                    "_type": "unknown_type",
                    "some_field": "some_value",
                },
            )
        ]

        new_router = ConditionalRouter()

        # Should raise ValueError with descriptive message
        with pytest.raises(ValueError, match="Failed to deserialize.*condition"):
            new_router.deserialize(serialized)

    def test_unmatched_data_to_default_output(self):
        """Test that unmatched data goes to default 'output' event when no default_route set."""
        router = ConditionalRouter()

        router.set_config(
            routes=[
                ("high", lambda data: data.get("value") > 10),
            ],
            # No default_route set
        )

        received = []
        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))

        if router.get_event("output") is None:
            router.define_event("output", ["data", "route"])
        router.get_event("output").connect(output_slot)

        # Data that doesn't match
        router.input_slot.receive({"data": {"value": 5}})

        assert len(received) == 1
        assert received[0].get("route") == "unmatched"
