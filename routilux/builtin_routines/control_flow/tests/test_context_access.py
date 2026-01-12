"""
Test cases for accessing config and stats in ConditionalRouter conditions.
"""

import unittest

from routilux.builtin_routines.control_flow import ConditionalRouter
from routilux.slot import Slot


class TestConditionContextAccess(unittest.TestCase):
    """Test cases for accessing config and stats in conditions."""

    def test_string_condition_with_config(self):
        """Test string condition accessing config."""
        router = ConditionalRouter()
        router.set_config(
            routes=[
                ("high", "data.get('value', 0) > config.get('threshold', 0)"),
                ("low", "data.get('value', 0) <= config.get('threshold', 0)"),
            ],
            threshold=10,
        )

        received_high = []
        received_low = []

        high_slot = Slot("high", None, lambda **kwargs: received_high.append(kwargs))
        low_slot = Slot("low", None, lambda **kwargs: received_low.append(kwargs))

        if router.get_event("high") is None:
            router.define_event("high", ["data", "route"])
        if router.get_event("low") is None:
            router.define_event("low", ["data", "route"])

        router.get_event("high").connect(high_slot)
        router.get_event("low").connect(low_slot)

        # Test high route
        router.input_slot.receive({"data": {"value": 15}})
        self.assertEqual(len(received_high), 1)
        self.assertEqual(len(received_low), 0)

        # Test low route
        router.input_slot.receive({"data": {"value": 5}})
        self.assertEqual(len(received_high), 1)
        self.assertEqual(len(received_low), 1)

    def test_string_condition_with_stats(self):
        """Test string condition accessing stats (deprecated - stats is now empty dict)."""
        router = ConditionalRouter()
        # Note: stats is now deprecated, always returns empty dict
        # This test verifies backward compatibility
        router.set_config(
            routes=[
                ("active", "stats.get('count', 0) < 10"),  # Will always match since stats is {}
                ("full", "stats.get('count', 0) >= 10"),
            ]
        )

        received_active = []
        received_full = []

        active_slot = Slot("active", None, lambda **kwargs: received_active.append(kwargs))
        full_slot = Slot("full", None, lambda **kwargs: received_full.append(kwargs))

        if router.get_event("active") is None:
            router.define_event("active", ["data", "route"])
        if router.get_event("full") is None:
            router.define_event("full", ["data", "route"])

        router.get_event("active").connect(active_slot)
        router.get_event("full").connect(full_slot)

        # Test active route (stats is empty dict, so count is 0, which is < 10)
        router.input_slot.receive({"data": {}})
        self.assertEqual(len(received_active), 1)
        self.assertEqual(len(received_full), 0)

    def test_function_condition_with_config(self):
        """Test function condition accessing config."""

        def check_threshold(data, config):
            threshold = config.get("threshold", 0)
            return data.get("value", 0) > threshold

        router = ConditionalRouter()
        router.set_config(
            routes=[
                ("high", check_threshold),
            ],
            threshold=10,
        )

        received_high = []
        high_slot = Slot("high", None, lambda **kwargs: received_high.append(kwargs))

        if router.get_event("high") is None:
            router.define_event("high", ["data", "route"])
        router.get_event("high").connect(high_slot)

        router.input_slot.receive({"data": {"value": 15}})
        self.assertEqual(len(received_high), 1)

    def test_lambda_with_closure(self):
        """Test lambda condition with closure (runtime only)."""
        router = ConditionalRouter()
        threshold = 10

        # Lambda accesses threshold via closure
        router.set_config(
            routes=[
                ("high", lambda data: data.get("value", 0) > threshold),
            ]
        )

        received_high = []
        high_slot = Slot("high", None, lambda **kwargs: received_high.append(kwargs))

        if router.get_event("high") is None:
            router.define_event("high", ["data", "route"])
        router.get_event("high").connect(high_slot)

        # Test at runtime
        router.input_slot.receive({"data": {"value": 15}})
        self.assertEqual(len(received_high), 1)
