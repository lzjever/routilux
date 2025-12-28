"""
Comprehensive test cases for built-in routines.

Tests all routines to ensure they work correctly and handle edge cases.

"""
import unittest
import time
from unittest.mock import Mock, patch, MagicMock
from routilux import Flow
from routilux.builtin_routines.utils import (
    TimeProvider,
    DataFlattener,
)
from routilux.utils.serializable import Serializable
from routilux.slot import Slot


class TestTimeProvider(unittest.TestCase):
    """Test cases for TimeProvider routine."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.time_provider = TimeProvider()
        self.received_data = []
        
        # Create a test slot to capture output
        self.capture_slot = Slot("capture", None, lambda **kwargs: self.received_data.append(kwargs))
        self.time_provider.get_event("output").connect(self.capture_slot)
    
    def test_get_time_iso(self):
        """Test getting time in ISO format."""
        self.time_provider.set_config(format="iso")
        self.time_provider.trigger_slot.receive({})
        
        self.assertEqual(len(self.received_data), 1)
        self.assertIn("time_string", self.received_data[0])
        self.assertIn("timestamp", self.received_data[0])
        self.assertIn("datetime", self.received_data[0])
    
    def test_get_time_formatted(self):
        """Test getting time in formatted format."""
        self.time_provider.set_config(format="formatted", locale="zh_CN")
        self.time_provider.trigger_slot.receive({})
        
        self.assertEqual(len(self.received_data), 1)
        time_str = self.received_data[0]["time_string"]
        self.assertIn("年", time_str)
    
    def test_get_time_timestamp(self):
        """Test getting time as timestamp."""
        self.time_provider.set_config(format="timestamp")
        self.time_provider.trigger_slot.receive({})
        
        self.assertEqual(len(self.received_data), 1)
        timestamp = self.received_data[0]["timestamp"]
        self.assertIsInstance(timestamp, float)
        self.assertGreater(timestamp, 0)
    
    def test_custom_format(self):
        """Test custom format."""
        self.time_provider.set_config(format="custom", custom_format="%Y-%m-%d")
        self.time_provider.trigger_slot.receive({})
        
        self.assertEqual(len(self.received_data), 1)
        time_str = self.received_data[0]["time_string"]
        self.assertRegex(time_str, r"\d{4}-\d{2}-\d{2}")


class TestDataFlattener(unittest.TestCase):
    """Test cases for DataFlattener routine."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.flattener = DataFlattener()
        self.received_data = []
        
        # Create a test slot to capture output
        self.capture_slot = Slot("capture", None, lambda **kwargs: self.received_data.append(kwargs))
        self.flattener.get_event("output").connect(self.capture_slot)
    
    def test_flatten_dict(self):
        """Test flattening a dictionary."""
        data = {"a": {"b": 1, "c": 2}}
        self.flattener.input_slot.receive({"data": data})
        
        self.assertEqual(len(self.received_data), 1)
        flattened = self.received_data[0]["flattened_data"]
        self.assertIn("a.b", flattened)
        self.assertEqual(flattened["a.b"], 1)
    
    def test_flatten_list(self):
        """Test flattening a list."""
        data = {"items": [1, 2, 3]}
        self.flattener.input_slot.receive({"data": data})
        
        self.assertEqual(len(self.received_data), 1)
        flattened = self.received_data[0]["flattened_data"]
        self.assertIn("items.0", flattened)
        self.assertEqual(flattened["items.0"], 1)
    
    def test_flatten_nested(self):
        """Test flattening deeply nested structures."""
        data = {"a": {"b": {"c": {"d": 1}}}}
        self.flattener.input_slot.receive({"data": data})
        
        self.assertEqual(len(self.received_data), 1)
        flattened = self.received_data[0]["flattened_data"]
        self.assertIn("a.b.c.d", flattened)
    
    def test_flatten_primitive(self):
        """Test flattening primitive value."""
        self.flattener.input_slot.receive({"data": 42})
        
        self.assertEqual(len(self.received_data), 1)
        flattened = self.received_data[0]["flattened_data"]
        self.assertIn("value", flattened)
        self.assertEqual(flattened["value"], 42)
    
    def test_custom_separator(self):
        """Test custom separator."""
        self.flattener.set_config(separator="_")
        data = {"a": {"b": 1}}
        self.flattener.input_slot.receive({"data": data})
        
        self.assertEqual(len(self.received_data), 1)
        flattened = self.received_data[0]["flattened_data"]
        self.assertIn("a_b", flattened)


