"""
Comprehensive test cases for built-in routines.

Tests all routines to ensure they work correctly and handle edge cases.

"""
import unittest
import time
from unittest.mock import Mock, patch, MagicMock
from routilux import Flow
from routilux.builtin_routines.text_processing import (
    TextClipper,
    TextRenderer,
    ResultExtractor,
)
from routilux.utils.serializable import Serializable
from routilux.slot import Slot


class TestTextClipper(unittest.TestCase):
    """Test cases for TextClipper routine."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.clipper = TextClipper()
        self.clipper.set_config(max_length=50)
        self.received_data = []
        
        # Create a test slot to capture output
        self.capture_slot = Slot("capture", None, lambda **kwargs: self.received_data.append(kwargs))
        self.clipper.get_event("output").connect(self.capture_slot)
    
    def test_clip_short_text(self):
        """Test clipping short text (should not clip)."""
        text = "Short text"
        self.clipper.input_slot.receive({"text": text})
        
        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["clipped_text"], text)
        self.assertFalse(self.received_data[0]["was_clipped"])
        self.assertEqual(self.received_data[0]["original_length"], len(text))
    
    def test_clip_long_text(self):
        """Test clipping long text."""
        text = "\n".join([f"Line {i}" for i in range(20)])
        self.clipper.input_slot.receive({"text": text})
        
        self.assertEqual(len(self.received_data), 1)
        self.assertTrue(self.received_data[0]["was_clipped"])
        self.assertIn("省略了", self.received_data[0]["clipped_text"])
    
    def test_preserve_traceback(self):
        """Test that tracebacks are preserved."""
        text = "Traceback (most recent call last):\n  File 'test.py', line 1\n    error\n"
        self.clipper.set_config(preserve_tracebacks=True)
        self.clipper.input_slot.receive({"text": text})
        
        self.assertEqual(len(self.received_data), 1)
        self.assertFalse(self.received_data[0]["was_clipped"])
        self.assertIn("Traceback", self.received_data[0]["clipped_text"])
    
    def test_non_string_input(self):
        """Test handling non-string input."""
        self.clipper.input_slot.receive({"text": 12345})
        
        self.assertEqual(len(self.received_data), 1)
        self.assertIsInstance(self.received_data[0]["clipped_text"], str)
    
    def test_empty_text(self):
        """Test handling empty text."""
        self.clipper.input_slot.receive({"text": ""})
        
        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["clipped_text"], "")
        self.assertFalse(self.received_data[0]["was_clipped"])
    
    def test_statistics(self):
        """Test that statistics are tracked."""
        self.clipper.input_slot.receive({"text": "test"})
        
        stats = self.clipper.stats()
        self.assertGreater(stats.get("total_clips", 0), 0)


class TestTextRenderer(unittest.TestCase):
    """Test cases for TextRenderer routine."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.renderer = TextRenderer()
        self.received_data = []
        
        # Create a test slot to capture output
        self.capture_slot = Slot("capture", None, lambda **kwargs: self.received_data.append(kwargs))
        self.renderer.get_event("output").connect(self.capture_slot)
    
    def test_render_dict(self):
        """Test rendering a dictionary."""
        data = {"name": "test", "value": 42}
        self.renderer.input_slot.receive({"data": data})
        
        self.assertEqual(len(self.received_data), 1)
        rendered = self.received_data[0]["rendered_text"]
        self.assertIn("<name>test</name>", rendered)
        self.assertIn("<value>42</value>", rendered)
    
    def test_render_nested_dict(self):
        """Test rendering nested dictionaries."""
        data = {"a": {"b": 1, "c": 2}}
        self.renderer.input_slot.receive({"data": data})
        
        self.assertEqual(len(self.received_data), 1)
        rendered = self.received_data[0]["rendered_text"]
        self.assertIn("<a>", rendered)
    
    def test_render_list(self):
        """Test rendering a list."""
        data = [1, 2, 3]
        self.renderer.input_slot.receive({"data": data})
        
        self.assertEqual(len(self.received_data), 1)
        rendered = self.received_data[0]["rendered_text"]
        self.assertIn("item_0", rendered)
    
    def test_render_primitive(self):
        """Test rendering primitive types."""
        self.renderer.input_slot.receive({"data": "test"})
        
        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["rendered_text"], "test")
    
    def test_markdown_format(self):
        """Test markdown format rendering."""
        self.renderer.set_config(tag_format="markdown")
        data = {"name": "test"}
        self.renderer.input_slot.receive({"data": data})
        
        self.assertEqual(len(self.received_data), 1)
        rendered = self.received_data[0]["rendered_text"]
        self.assertIn("**name**", rendered)


class TestResultExtractor(unittest.TestCase):
    """Test cases for ResultExtractor routine."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.extractor = ResultExtractor()
        self.received_data = []
        
        # Create a test slot to capture output
        self.capture_slot = Slot("capture", None, lambda **kwargs: self.received_data.append(kwargs))
        self.extractor.get_event("output").connect(self.capture_slot)
    
    def test_extract_json_block(self):
        """Test extracting JSON code block."""
        text = "Some text\n```json\n{\"key\": \"value\"}\n```\nMore text"
        self.extractor.input_slot.receive({"data": text})
        
        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["format"], "json")
        self.assertIsInstance(self.received_data[0]["extracted_result"], dict)
        self.assertIn("confidence", self.received_data[0])
        self.assertIn("extraction_path", self.received_data[0])
    
    def test_extract_json_string(self):
        """Test extracting JSON from plain string."""
        text = '{"key": "value"}'
        self.extractor.set_config(parse_json_strings=True)
        self.extractor.input_slot.receive({"data": text})
        
        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["format"], "json")
        self.assertIsInstance(self.received_data[0]["extracted_result"], dict)
    
    def test_extract_code_block(self):
        """Test extracting code block."""
        text = "```python\nprint('hello')\n```"
        self.extractor.input_slot.receive({"data": text})
        
        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["format"], "python")
        self.assertIn("code_block", self.received_data[0]["metadata"]["extraction_method"])
    
    def test_extract_interpreter_output(self):
        """Test extracting interpreter output."""
        outputs = [
            {"format": "output", "content": "Hello"},
            {"format": "output", "content": "World"}
        ]
        self.extractor.input_slot.receive({"data": outputs})
        
        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["format"], "interpreter_output")
        self.assertIn("Hello", self.received_data[0]["extracted_result"])
        self.assertEqual(self.received_data[0]["metadata"]["output_count"], 2)
    
    def test_extract_dict(self):
        """Test extracting from dictionary."""
        data = {"key": "value", "number": 42}
        self.extractor.input_slot.receive({"data": data})
        
        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["format"], "dict")
        self.assertEqual(self.received_data[0]["extracted_result"], data)
    
    def test_extract_list(self):
        """Test extracting from list."""
        data = [1, 2, 3]
        self.extractor.input_slot.receive({"data": data})
        
        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["format"], "list")
        self.assertEqual(self.received_data[0]["extracted_result"], data)
    
    def test_strategy_first_match(self):
        """Test first_match strategy."""
        self.extractor.set_config(strategy="first_match")
        text = "```json\n{\"key\": \"value\"}\n```\n```python\nprint('test')\n```"
        self.extractor.input_slot.receive({"data": text})
        
        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["format"], "json")
    
    def test_strategy_priority(self):
        """Test priority strategy."""
        self.extractor.set_config(
            strategy="priority",
            extractor_priority=["code_block", "json_code_block"]
        )
        text = "```json\n{\"key\": \"value\"}\n```"
        self.extractor.input_slot.receive({"data": text})
        
        self.assertEqual(len(self.received_data), 1)
        # Should use code_block extractor first due to priority
        self.assertIn(self.received_data[0]["metadata"]["extractor"], ["code_block", "json_code_block"])
    
    def test_custom_extractor(self):
        """Test registering and using custom extractor."""
        def custom_extractor(data, config):
            if isinstance(data, str) and data.startswith("CUSTOM:"):
                return data[7:], "custom", {"method": "prefix"}
            return None
        
        self.extractor.register_extractor("custom_prefix", custom_extractor)
        self.extractor.set_config(extractor_priority=["custom_prefix"])
        
        self.extractor.input_slot.receive({"data": "CUSTOM:test_value"})
        
        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["format"], "custom")
        self.assertEqual(self.received_data[0]["extracted_result"], "test_value")
        self.assertEqual(self.received_data[0]["metadata"]["method"], "prefix")
    
    def test_confidence_calculation(self):
        """Test confidence score calculation."""
        text = "```json\n{\"key\": \"value\"}\n```"
        self.extractor.input_slot.receive({"data": text})
        
        self.assertEqual(len(self.received_data), 1)
        confidence = self.received_data[0]["confidence"]
        self.assertGreaterEqual(confidence, 0.0)
        self.assertLessEqual(confidence, 1.0)
        self.assertGreater(confidence, 0.5)  # Should have good confidence for JSON
    
    def test_error_handling(self):
        """Test error handling with invalid data."""
        self.extractor.set_config(continue_on_error=True, return_original_on_failure=True)
        
        # Invalid JSON in code block
        text = "```json\n{invalid json}\n```"
        self.extractor.input_slot.receive({"data": text})
        
        self.assertEqual(len(self.received_data), 1)
        # Should fall back to code block extraction or original
        self.assertIn("extracted_result", self.received_data[0])
    
    def test_plain_text_fallback(self):
        """Test handling plain text when extraction fails."""
        text = "Just plain text with no structure"
        self.extractor.set_config(return_original_on_failure=True)
        self.extractor.input_slot.receive({"data": text})
        
        self.assertEqual(len(self.received_data), 1)
        # Should return original text
        self.assertEqual(self.received_data[0]["extracted_result"], text)
        self.assertEqual(self.received_data[0]["confidence"], 0.0)


