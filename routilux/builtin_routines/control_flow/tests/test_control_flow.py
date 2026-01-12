"""
Comprehensive test cases for built-in routines.

Tests all routines to ensure they work correctly and handle edge cases.
"""

import unittest

from routilux.builtin_routines.control_flow import (
    ConditionalRouter,
)
from routilux.slot import Slot


class TestConditionalRouter(unittest.TestCase):
    """Test cases for ConditionalRouter routine."""

    def setUp(self):
        """Set up test fixtures."""
        self.router = ConditionalRouter()
        self.received_high = []
        self.received_low = []
        self.received_normal = []

        # Create test slots to capture output
        self.high_slot = Slot("high", None, lambda **kwargs: self.received_high.append(kwargs))
        self.low_slot = Slot("low", None, lambda **kwargs: self.received_low.append(kwargs))
        self.normal_slot = Slot(
            "normal", None, lambda **kwargs: self.received_normal.append(kwargs)
        )

        self.router.set_config(
            routes=[
                ("high", lambda x: isinstance(x, dict) and x.get("priority") == "high"),
                ("low", lambda x: isinstance(x, dict) and x.get("priority") == "low"),
            ],
            default_route="normal",
        )

        # Events are created dynamically, so we need to trigger creation first
        # or connect after they're created
        # For now, let's connect after setting up routes
        high_event = self.router.get_event("high")
        if high_event:
            high_event.connect(self.high_slot)
        else:
            self.router.define_event("high", ["data", "route"]).connect(self.high_slot)

        low_event = self.router.get_event("low")
        if low_event:
            low_event.connect(self.low_slot)
        else:
            self.router.define_event("low", ["data", "route"]).connect(self.low_slot)

        normal_event = self.router.get_event("normal")
        if normal_event:
            normal_event.connect(self.normal_slot)
        else:
            self.router.define_event("normal", ["data", "route"]).connect(self.normal_slot)

    def test_route_high_priority(self):
        """Test routing high priority data."""
        self.router.input_slot.receive({"data": {"priority": "high", "value": 1}})

        self.assertEqual(len(self.received_high), 1)
        self.assertEqual(len(self.received_low), 0)
        self.assertEqual(len(self.received_normal), 0)

    def test_route_low_priority(self):
        """Test routing low priority data."""
        self.router.input_slot.receive({"data": {"priority": "low", "value": 2}})

        self.assertEqual(len(self.received_high), 0)
        self.assertEqual(len(self.received_low), 1)
        self.assertEqual(len(self.received_normal), 0)

    def test_default_route(self):
        """Test default route for unmatched data."""
        self.router.input_slot.receive({"data": {"priority": "medium", "value": 3}})

        self.assertEqual(len(self.received_high), 0)
        self.assertEqual(len(self.received_low), 0)
        self.assertEqual(len(self.received_normal), 1)

    def test_dict_condition(self):
        """Test dictionary-based condition."""
        self.router.add_route("exact", {"priority": "exact"})
        received_exact = []
        exact_slot = Slot("exact", None, lambda **kwargs: received_exact.append(kwargs))
        self.router.get_event("exact").connect(exact_slot)

        self.router.input_slot.receive({"data": {"priority": "exact"}})

        self.assertEqual(len(received_exact), 1)

    def test_string_condition(self):
        """Test string expression condition."""
        router = ConditionalRouter()
        router.set_config(
            routes=[
                ("high", "data.get('priority') == 'high'"),
                ("low", "isinstance(data, dict) and data.get('priority') == 'low'"),
            ],
            default_route="normal",
        )

        received_high = []
        received_low = []
        received_normal = []

        high_slot = Slot("high", None, lambda **kwargs: received_high.append(kwargs))
        low_slot = Slot("low", None, lambda **kwargs: received_low.append(kwargs))
        normal_slot = Slot("normal", None, lambda **kwargs: received_normal.append(kwargs))

        # Ensure events are created
        if router.get_event("high") is None:
            router.define_event("high", ["data", "route"])
        if router.get_event("low") is None:
            router.define_event("low", ["data", "route"])
        if router.get_event("normal") is None:
            router.define_event("normal", ["data", "route"])

        router.get_event("high").connect(high_slot)
        router.get_event("low").connect(low_slot)
        router.get_event("normal").connect(normal_slot)

        # Test high priority
        router.input_slot.receive({"data": {"priority": "high"}})
        self.assertEqual(len(received_high), 1)
        self.assertEqual(len(received_low), 0)
        self.assertEqual(len(received_normal), 0)

        # Test low priority
        router.input_slot.receive({"data": {"priority": "low"}})
        self.assertEqual(len(received_high), 1)
        self.assertEqual(len(received_low), 1)
        self.assertEqual(len(received_normal), 0)

        # Test default
        router.input_slot.receive({"data": {"priority": "medium"}})
        self.assertEqual(len(received_high), 1)
        self.assertEqual(len(received_low), 1)
        self.assertEqual(len(received_normal), 1)

    def test_serialize_lambda_condition(self):
        """Test serialization of lambda condition."""
        router = ConditionalRouter()
        router.set_config(
            routes=[
                ("high", lambda x: x.get("priority") == "high"),
                ("low", {"priority": "low"}),  # Dict condition for comparison
            ]
        )

        # Serialize
        serialized = router.serialize()

        # Check that routes are serialized
        self.assertIn("_config", serialized)
        self.assertIn("routes", serialized["_config"])
        routes = serialized["_config"]["routes"]

        # Lambda should be converted to lambda_expression (if inspect.getsource works)
        # or remain as function if it can be serialized normally
        high_route = routes[0]
        self.assertEqual(high_route[0], "high")
        self.assertIsInstance(high_route[1], dict)
        # Lambda might be serialized as function if it has a module, or as lambda_expression
        condition_type = high_route[1].get("_type")
        self.assertIn(condition_type, ["function", "lambda_expression"])
        if condition_type == "lambda_expression":
            self.assertIn("expression", high_route[1])

        # Dict condition should remain as dict
        low_route = routes[1]
        self.assertEqual(low_route[0], "low")
        self.assertIsInstance(low_route[1], dict)
        self.assertNotIn("_type", low_route[1])

    def test_deserialize_lambda_condition(self):
        """Test deserialization of lambda condition (using string expression as fallback)."""
        # Use string expression instead of lambda for reliable serialization
        router = ConditionalRouter()
        router.set_config(
            routes=[
                ("high", "data.get('priority') == 'high'"),  # String expression
            ]
        )

        # Serialize and deserialize
        serialized = router.serialize()

        new_router = ConditionalRouter()
        new_router.deserialize(serialized)

        # Test that deserialized router works
        received_high = []
        high_slot = Slot("high", None, lambda **kwargs: received_high.append(kwargs))

        # Ensure event is created
        if new_router.get_event("high") is None:
            new_router.define_event("high", ["data", "route"])
        new_router.get_event("high").connect(high_slot)

        new_router.input_slot.receive({"data": {"priority": "high"}})
        self.assertEqual(len(received_high), 1)

    def test_serialize_string_condition(self):
        """Test serialization of string condition."""
        router = ConditionalRouter()
        router.set_config(
            routes=[
                ("high", "data.get('priority') == 'high'"),
            ]
        )

        # Serialize
        serialized = router.serialize()

        # String condition should remain as string
        routes = serialized["_config"]["routes"]
        self.assertEqual(routes[0][0], "high")
        self.assertEqual(routes[0][1], "data.get('priority') == 'high'")

    def test_serialize_function_condition(self):
        """Test serialization of function condition."""

        def check_priority(data):
            return data.get("priority") == "high"

        router = ConditionalRouter()
        router.set_config(
            routes=[
                ("high", check_priority),
            ]
        )

        # Serialize
        serialized = router.serialize()

        # Function should be serialized (as callable if accessible from module, or lambda_expression if not)
        routes = serialized["_config"]["routes"]
        self.assertEqual(routes[0][0], "high")
        self.assertIsInstance(routes[0][1], dict)
        condition_type = routes[0][1].get("_type")
        # Function defined in test method cannot be accessed from module level,
        # so it will be serialized as lambda_expression
        self.assertIn(condition_type, ["callable", "lambda_expression"])
        if condition_type == "callable":
            self.assertEqual(routes[0][1].get("callable_type"), "function")
        elif condition_type == "lambda_expression":
            self.assertIn("expression", routes[0][1])

    def test_serialize_deserialize_roundtrip(self):
        """Test complete serialize-deserialize roundtrip."""
        # Create router with mixed condition types
        # Use string conditions for reliable serialization
        router = ConditionalRouter()
        router.set_config(
            routes=[
                ("high", "data.get('priority') == 'high'"),  # String
                ("low", "data.get('priority') == 'low'"),  # String
                ("medium", {"priority": "medium"}),  # Dict
                ("custom", "data.get('type') == 'custom'"),  # String
            ],
            default_route="default",
            route_priority="first_match",
        )

        # Serialize
        serialized = router.serialize()

        # Deserialize
        new_router = ConditionalRouter()
        new_router.deserialize(serialized)

        # Verify config
        self.assertEqual(new_router.get_config("default_route"), "default")
        self.assertEqual(new_router.get_config("route_priority"), "first_match")

        # Test routing
        received_high = []
        received_low = []
        received_medium = []
        received_custom = []
        received_default = []

        high_slot = Slot("high", None, lambda **kwargs: received_high.append(kwargs))
        low_slot = Slot("low", None, lambda **kwargs: received_low.append(kwargs))
        medium_slot = Slot("medium", None, lambda **kwargs: received_medium.append(kwargs))
        custom_slot = Slot("custom", None, lambda **kwargs: received_custom.append(kwargs))
        default_slot = Slot("default", None, lambda **kwargs: received_default.append(kwargs))

        # Ensure events are created
        for event_name in ["high", "low", "medium", "custom", "default"]:
            if new_router.get_event(event_name) is None:
                new_router.define_event(event_name, ["data", "route"])

        new_router.get_event("high").connect(high_slot)
        new_router.get_event("low").connect(low_slot)
        new_router.get_event("medium").connect(medium_slot)
        new_router.get_event("custom").connect(custom_slot)
        new_router.get_event("default").connect(default_slot)

        # Test each route
        new_router.input_slot.receive({"data": {"priority": "high"}})
        self.assertEqual(len(received_high), 1)

        new_router.input_slot.receive({"data": {"priority": "low"}})
        self.assertEqual(len(received_low), 1)

        new_router.input_slot.receive({"data": {"priority": "medium"}})
        self.assertEqual(len(received_medium), 1)

        new_router.input_slot.receive({"data": {"type": "custom"}})
        self.assertEqual(len(received_custom), 1)

        new_router.input_slot.receive({"data": {"priority": "unknown"}})
        self.assertEqual(len(received_default), 1)
