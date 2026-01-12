"""
Comprehensive test cases for built-in routines.

Tests all routines to ensure they work correctly and handle edge cases.

"""

import unittest

from routilux.builtin_routines.data_processing import (
    DataTransformer,
    DataValidator,
)
from routilux.slot import Slot


class TestDataTransformer(unittest.TestCase):
    """Test cases for DataTransformer routine."""

    def setUp(self):
        """Set up test fixtures."""
        self.transformer = DataTransformer()
        self.received_data = []

        # Create a test slot to capture output
        self.capture_slot = Slot(
            "capture", None, lambda **kwargs: self.received_data.append(kwargs)
        )
        self.transformer.get_event("output").connect(self.capture_slot)

    def test_lowercase_transformation(self):
        """Test lowercase transformation."""
        self.transformer.set_config(transformations=["lowercase"])
        self.transformer.input_slot.receive({"data": "HELLO"})

        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["transformed_data"], "hello")

    def test_multiple_transformations(self):
        """Test chaining multiple transformations."""
        self.transformer.set_config(transformations=["lowercase", "strip_whitespace"])
        self.transformer.input_slot.receive({"data": "  HELLO  "})

        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["transformed_data"], "hello")

    def test_custom_transformation(self):
        """Test custom transformation."""

        def double(x):
            return x * 2

        self.transformer.register_transformation("double", double)
        self.transformer.set_config(transformations=["double"])
        self.transformer.input_slot.receive({"data": 5})

        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["transformed_data"], 10)

    def test_transformation_error(self):
        """Test handling transformation errors."""
        self.transformer.set_config(transformations=["to_int"])
        self.transformer.input_slot.receive({"data": "not_a_number"})

        self.assertEqual(len(self.received_data), 1)
        self.assertIsNotNone(self.received_data[0]["errors"])


class TestDataValidator(unittest.TestCase):
    """Test cases for DataValidator routine."""

    def setUp(self):
        """Set up test fixtures."""
        self.validator = DataValidator()
        self.received_valid = []
        self.received_invalid = []

        # Create test slots to capture output
        self.valid_slot = Slot("valid", None, lambda **kwargs: self.received_valid.append(kwargs))
        self.invalid_slot = Slot(
            "invalid", None, lambda **kwargs: self.received_invalid.append(kwargs)
        )
        self.validator.get_event("valid").connect(self.valid_slot)
        self.validator.get_event("invalid").connect(self.invalid_slot)

    def test_valid_data(self):
        """Test validating valid data."""
        self.validator.set_config(
            rules={"name": "not_empty", "age": "is_int"}, required_fields=["name", "age"]
        )
        self.validator.input_slot.receive({"data": {"name": "test", "age": 25}})

        self.assertEqual(len(self.received_valid), 1)
        self.assertEqual(len(self.received_invalid), 0)

    def test_invalid_data(self):
        """Test validating invalid data."""
        self.validator.set_config(rules={"name": "not_empty", "age": "is_int"})
        self.validator.input_slot.receive({"data": {"name": "", "age": "not_int"}})

        self.assertEqual(len(self.received_valid), 0)
        self.assertEqual(len(self.received_invalid), 1)
        self.assertGreater(len(self.received_invalid[0]["errors"]), 0)

    def test_missing_required_field(self):
        """Test missing required field."""
        self.validator.set_config(required_fields=["name"])
        self.validator.input_slot.receive({"data": {}})

        self.assertEqual(len(self.received_invalid), 1)
        self.assertIn("missing", str(self.received_invalid[0]["errors"][0]).lower())

    def test_custom_validator(self):
        """Test custom validator."""

        def is_even(x):
            return isinstance(x, int) and x % 2 == 0

        self.validator.register_validator("is_even", is_even)
        self.validator.set_config(rules={"number": "is_even"})
        self.validator.input_slot.receive({"data": {"number": 4}})

        self.assertEqual(len(self.received_valid), 1)

    def test_strict_mode(self):
        """Test strict mode (stop on first error)."""
        self.validator.set_config(
            rules={"field1": "is_string", "field2": "is_string"}, strict_mode=True
        )
        self.validator.input_slot.receive({"data": {"field1": 123, "field2": 456}})

        self.assertEqual(len(self.received_invalid), 1)
        # Should only have one error in strict mode
        self.assertEqual(len(self.received_invalid[0]["errors"]), 1)
