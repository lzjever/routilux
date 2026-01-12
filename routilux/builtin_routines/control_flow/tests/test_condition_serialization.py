"""
Test cases for serialization and deserialization of lambda and function conditions.
"""

import unittest

from routilux import Flow
from routilux.builtin_routines.control_flow import ConditionalRouter
from routilux.slot import Slot


# Module-level function for testing function condition serialization
def check_priority_high(data):
    """Module-level function for testing."""
    return isinstance(data, dict) and data.get("priority") == "high"


def check_priority_low(data):
    """Module-level function for testing."""
    return isinstance(data, dict) and data.get("priority") == "low"


def check_value_with_config(data, config):
    """Module-level function that accepts config."""
    threshold = config.get("threshold", 0)
    return data.get("value", 0) > threshold


class TestConditionSerialization(unittest.TestCase):
    """Test cases for condition serialization and deserialization."""

    def test_lambda_condition_serialization(self):
        """Test lambda condition serialization and deserialization."""

        # Create function at module level (so inspect.getsource can work)
        def test_lambda(x):
            return x.get("priority") == "high"

        router1 = ConditionalRouter()
        router1.set_config(
            routes=[
                ("high", test_lambda),
            ]
        )

        # Serialize
        serialized = router1.serialize()
        self.assertIn("_config", serialized)
        self.assertIn("routes", serialized["_config"])

        routes = serialized["_config"]["routes"]
        self.assertEqual(len(routes), 1)

        # Check serialization format
        route_data = routes[0][1]
        # Lambda should be converted to lambda_expression or function type
        self.assertIsInstance(route_data, dict)
        self.assertIn("_type", route_data)

        # Deserialize
        router2 = ConditionalRouter()
        router2.deserialize(serialized)

        # Verify routes are restored
        deserialized_routes = router2.get_config("routes")
        self.assertEqual(len(deserialized_routes), 1)
        self.assertEqual(deserialized_routes[0][0], "high")

        # Verify condition is callable
        condition = deserialized_routes[0][1]
        self.assertTrue(callable(condition), "Condition should be callable after deserialization")

        # Test functionality
        received_high = []
        high_slot = Slot("high", None, lambda **kwargs: received_high.append(kwargs))

        if router2.get_event("high") is None:
            router2.define_event("high", ["data", "route"])
        router2.get_event("high").connect(high_slot)

        router2.input_slot.receive({"data": {"priority": "high"}})
        self.assertEqual(
            len(received_high), 1, "Lambda condition should work after deserialization"
        )

    def test_function_condition_serialization(self):
        """Test function condition serialization and deserialization."""
        router1 = ConditionalRouter()
        router1.set_config(
            routes=[
                ("high", check_priority_high),
                ("low", check_priority_low),
            ]
        )

        # Serialize
        serialized = router1.serialize()
        routes = serialized["_config"]["routes"]
        self.assertEqual(len(routes), 2)

        # Check serialization format
        high_route = routes[0]
        self.assertEqual(high_route[0], "high")
        self.assertIsInstance(high_route[1], dict)
        self.assertEqual(high_route[1].get("_type"), "callable")
        self.assertEqual(high_route[1].get("callable_type"), "function")
        self.assertIn("module", high_route[1])
        self.assertIn("name", high_route[1])

        # Deserialize
        router2 = ConditionalRouter()
        router2.deserialize(serialized)

        # Verify routes are restored
        deserialized_routes = router2.get_config("routes")
        self.assertEqual(len(deserialized_routes), 2)

        # Verify conditions are callable
        high_condition = deserialized_routes[0][1]
        low_condition = deserialized_routes[1][1]
        self.assertTrue(callable(high_condition), "Function condition should be callable")
        self.assertTrue(callable(low_condition), "Function condition should be callable")

        # Test functionality
        received_high = []
        received_low = []

        high_slot = Slot("high", None, lambda **kwargs: received_high.append(kwargs))
        low_slot = Slot("low", None, lambda **kwargs: received_low.append(kwargs))

        if router2.get_event("high") is None:
            router2.define_event("high", ["data", "route"])
        if router2.get_event("low") is None:
            router2.define_event("low", ["data", "route"])

        router2.get_event("high").connect(high_slot)
        router2.get_event("low").connect(low_slot)

        router2.input_slot.receive({"data": {"priority": "high"}})
        self.assertEqual(
            len(received_high), 1, "Function condition should work after deserialization"
        )

        router2.input_slot.receive({"data": {"priority": "low"}})
        self.assertEqual(
            len(received_low), 1, "Function condition should work after deserialization"
        )

    def test_function_with_config_serialization(self):
        """Test function condition with config parameter serialization."""
        router1 = ConditionalRouter()
        router1.set_config(
            routes=[
                ("high", check_value_with_config),
            ],
            threshold=10,
        )

        # Serialize
        serialized = router1.serialize()

        # Deserialize
        router2 = ConditionalRouter()
        router2.deserialize(serialized)
        router2.set_config(threshold=10)  # Restore config

        # Verify condition is callable
        routes = router2.get_config("routes")
        self.assertEqual(len(routes), 1)
        condition = routes[0][1]
        self.assertTrue(callable(condition), "Function with config should be callable")

        # Test functionality
        received_high = []
        high_slot = Slot("high", None, lambda **kwargs: received_high.append(kwargs))

        if router2.get_event("high") is None:
            router2.define_event("high", ["data", "route"])
        router2.get_event("high").connect(high_slot)

        router2.input_slot.receive({"data": {"value": 15}})
        self.assertEqual(
            len(received_high), 1, "Function with config should work after deserialization"
        )

    def test_mixed_conditions_serialization(self):
        """Test serialization of mixed condition types."""

        # Module-level function for testing
        def test_lambda(x):
            return x.get("type") == "test"

        router1 = ConditionalRouter()
        router1.set_config(
            routes=[
                ("high", check_priority_high),  # Function
                ("low", test_lambda),  # Lambda
                ("medium", {"priority": "medium"}),  # Dict
                ("custom", "data.get('custom') == True"),  # String
            ]
        )

        # Serialize
        serialized = router1.serialize()
        routes = serialized["_config"]["routes"]
        self.assertEqual(len(routes), 4, "All routes should be serialized")

        # Deserialize
        router2 = ConditionalRouter()
        router2.deserialize(serialized)

        # Verify all routes are restored
        deserialized_routes = router2.get_config("routes")
        self.assertEqual(len(deserialized_routes), 4, "All routes should be deserialized")

        # Verify each route type
        route_names = [r[0] for r in deserialized_routes]
        self.assertIn("high", route_names)
        self.assertIn("low", route_names)
        self.assertIn("medium", route_names)
        self.assertIn("custom", route_names)

        # Test functionality
        received = {}
        for route_name in ["high", "low", "medium", "custom"]:
            received[route_name] = []
            slot = Slot(
                route_name, None, lambda name=route_name, **kwargs: received[name].append(kwargs)
            )
            if router2.get_event(route_name) is None:
                router2.define_event(route_name, ["data", "route"])
            router2.get_event(route_name).connect(slot)

        router2.input_slot.receive({"data": {"priority": "high"}})
        self.assertEqual(len(received["high"]), 1, "Function condition should work")

        router2.input_slot.receive({"data": {"type": "test"}})
        self.assertEqual(len(received["low"]), 1, "Lambda condition should work")

        router2.input_slot.receive({"data": {"priority": "medium"}})
        self.assertEqual(len(received["medium"]), 1, "Dict condition should work")

        router2.input_slot.receive({"data": {"custom": True}})
        self.assertEqual(len(received["custom"]), 1, "String condition should work")

    def test_flow_level_serialization_with_lambda(self):
        """Test Flow-level serialization with lambda condition."""

        def test_lambda(x):
            return x.get("priority") == "high"

        flow1 = Flow(flow_id="test_flow")
        router = ConditionalRouter()
        router.set_config(
            routes=[
                ("high", test_lambda),
            ]
        )

        flow1.add_routine(router, "router")

        # Serialize Flow
        serialized = flow1.serialize()

        # Deserialize Flow
        flow2 = Flow(flow_id="test_flow_2")
        flow2.deserialize(serialized)

        # Verify router exists
        self.assertIn("router", flow2.routines)
        deserialized_router = flow2.routines["router"]
        self.assertIsInstance(deserialized_router, ConditionalRouter)

        # Verify routes
        routes = deserialized_router.get_config("routes")
        self.assertEqual(len(routes), 1)
        condition = routes[0][1]
        self.assertTrue(callable(condition), "Lambda should be callable after Flow deserialization")

        # Test functionality
        received_high = []
        high_slot = Slot("high", None, lambda **kwargs: received_high.append(kwargs))

        if deserialized_router.get_event("high") is None:
            deserialized_router.define_event("high", ["data", "route"])
        deserialized_router.get_event("high").connect(high_slot)

        deserialized_router.input_slot.receive({"data": {"priority": "high"}})
        self.assertEqual(len(received_high), 1, "Lambda should work after Flow deserialization")

    def test_flow_level_serialization_with_function(self):
        """Test Flow-level serialization with function condition."""
        flow1 = Flow(flow_id="test_flow")
        router = ConditionalRouter()
        router.set_config(
            routes=[
                ("high", check_priority_high),
            ]
        )

        flow1.add_routine(router, "router")

        # Serialize Flow
        serialized = flow1.serialize()

        # Deserialize Flow
        flow2 = Flow(flow_id="test_flow_2")
        flow2.deserialize(serialized)

        # Verify router exists
        self.assertIn("router", flow2.routines)
        deserialized_router = flow2.routines["router"]

        # Verify routes
        routes = deserialized_router.get_config("routes")
        self.assertEqual(len(routes), 1)
        condition = routes[0][1]
        self.assertTrue(
            callable(condition), "Function should be callable after Flow deserialization"
        )

        # Test functionality
        received_high = []
        high_slot = Slot("high", None, lambda **kwargs: received_high.append(kwargs))

        if deserialized_router.get_event("high") is None:
            deserialized_router.define_event("high", ["data", "route"])
        deserialized_router.get_event("high").connect(high_slot)

        deserialized_router.input_slot.receive({"data": {"priority": "high"}})
        self.assertEqual(len(received_high), 1, "Function should work after Flow deserialization")

    def test_json_roundtrip_with_lambda(self):
        """Test JSON serialization roundtrip with lambda."""
        import json

        def test_lambda(x):
            return x.get("priority") == "high"

        router1 = ConditionalRouter()
        router1.set_config(
            routes=[
                ("high", test_lambda),
            ]
        )

        # Serialize to dict
        serialized = router1.serialize()

        # Convert to JSON and back
        json_str = json.dumps(serialized)
        restored_data = json.loads(json_str)

        # Deserialize
        router2 = ConditionalRouter()
        router2.deserialize(restored_data)

        # Verify functionality
        routes = router2.get_config("routes")
        self.assertEqual(len(routes), 1)
        condition = routes[0][1]
        self.assertTrue(callable(condition), "Lambda should work after JSON roundtrip")

        received_high = []
        high_slot = Slot("high", None, lambda **kwargs: received_high.append(kwargs))

        if router2.get_event("high") is None:
            router2.define_event("high", ["data", "route"])
        router2.get_event("high").connect(high_slot)

        router2.input_slot.receive({"data": {"priority": "high"}})
        self.assertEqual(len(received_high), 1, "Lambda should work after JSON roundtrip")

    def test_json_roundtrip_with_function(self):
        """Test JSON serialization roundtrip with function."""
        import json

        router1 = ConditionalRouter()
        router1.set_config(
            routes=[
                ("high", check_priority_high),
            ]
        )

        # Serialize to dict
        serialized = router1.serialize()

        # Convert to JSON and back
        json_str = json.dumps(serialized)
        restored_data = json.loads(json_str)

        # Deserialize
        router2 = ConditionalRouter()
        router2.deserialize(restored_data)

        # Verify functionality
        routes = router2.get_config("routes")
        self.assertEqual(len(routes), 1)
        condition = routes[0][1]
        self.assertTrue(callable(condition), "Function should work after JSON roundtrip")

        received_high = []
        high_slot = Slot("high", None, lambda **kwargs: received_high.append(kwargs))

        if router2.get_event("high") is None:
            router2.define_event("high", ["data", "route"])
        router2.get_event("high").connect(high_slot)

        router2.input_slot.receive({"data": {"priority": "high"}})
        self.assertEqual(len(received_high), 1, "Function should work after JSON roundtrip")
