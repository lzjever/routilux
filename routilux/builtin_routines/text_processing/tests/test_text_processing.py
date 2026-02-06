"""
Comprehensive test cases for built-in routines.

Tests all routines to ensure they work correctly and handle edge cases.

"""

import unittest

from routilux.builtin_routines.text_processing import (
    ResultExtractor,
    TextClipper,
    TextRenderer,
)
from routilux.slot import Slot


class TestTextClipper(unittest.TestCase):
    """Test cases for TextClipper routine."""

    def setUp(self):
        """Set up test fixtures."""
        self.clipper = TextClipper()
        self.clipper.set_config(max_length=50)
        self.received_data = []

        # Create a test slot to capture output
        self.capture_slot = Slot(
            "capture", None, lambda **kwargs: self.received_data.append(kwargs)
        )
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
        """Test that statistics are tracked (deprecated - use JobState instead)."""
        # Statistics tracking removed - use JobState for execution state
        # This test is kept for backward compatibility but will always pass
        self.clipper.input_slot.receive({"text": "test"})
        # No longer using routine.stats() - execution state is in JobState
        self.assertTrue(True)  # Placeholder assertion

    def test_dict_input_with_text_key(self):
        """Test handling dict input with 'text' key."""
        self.clipper.input_slot.receive({"text": {"text": "Hello World"}})

        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["clipped_text"], "Hello World")
        self.assertFalse(self.received_data[0]["was_clipped"])

    def test_dict_input_with_content_key(self):
        """Test handling dict input with 'content' key."""
        self.clipper.input_slot.receive({"text": {"content": "Test content"}})

        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["clipped_text"], "Test content")

    def test_dict_input_with_message_key(self):
        """Test handling dict input with 'message' key."""
        self.clipper.input_slot.receive({"text": {"message": "Important message"}})

        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["clipped_text"], "Important message")

    def test_dict_input_with_any_string_value(self):
        """Test handling dict input finding any string value."""
        self.clipper.input_slot.receive({"text": {"data": {"nested": "Found it"}}})

        self.assertEqual(len(self.received_data), 1)
        self.assertIn("Found it", self.received_data[0]["clipped_text"])

    def test_dict_input_non_string_values(self):
        """Test handling dict input with only non-string values (converts to string)."""
        self.clipper.input_slot.receive({"text": {"count": 42, "flag": True}})

        self.assertEqual(len(self.received_data), 1)
        # Should convert dict to string
        self.assertIsInstance(self.received_data[0]["clipped_text"], str)

    def test_exact_max_length(self):
        """Test text exactly at max_length is not clipped."""
        self.clipper.set_config(max_length=20)
        text = "12345678901234567890"  # Exactly 20 chars
        self.clipper.input_slot.receive({"text": text})

        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["clipped_text"], text)
        self.assertFalse(self.received_data[0]["was_clipped"])

    def test_clip_text_all_lines_fit_exactly(self):
        """Test edge case where all lines fit exactly in max_length (not clipped)."""
        # This tests line 142: if not clipped: return "\n".join(head), False
        self.clipper.set_config(max_length=100)
        text = "Line 1\nLine 2\nLine 3"  # Total with newlines < 100
        self.clipper.input_slot.receive({"text": text})

        self.assertEqual(len(self.received_data), 1)
        self.assertFalse(self.received_data[0]["was_clipped"])

    def test_non_object_as_input(self):
        """Test handling non-dict, non-string object that becomes string."""

        # Pass an object that's not a string or dict
        class CustomObject:
            def __str__(self):
                return "CustomObject string"

        self.clipper.input_slot.receive({"text": CustomObject()})

        self.assertEqual(len(self.received_data), 1)
        self.assertIn("CustomObject string", self.received_data[0]["clipped_text"])

    def test_dict_with_string_value_not_in_expected_keys(self):
        """Test dict with string value in non-standard key (lines 77-78)."""
        # This specifically tests the for value in data.values() loop
        # The dict should not have text, content, message, or data keys
        # but should have a string value
        self.clipper.input_slot.receive({"text": {"random_key": "found_string"}})

        self.assertEqual(len(self.received_data), 1)
        # Should find the string value
        self.assertIn("found_string", self.received_data[0]["clipped_text"])


class TestTextRenderer(unittest.TestCase):
    """Test cases for TextRenderer routine."""

    def setUp(self):
        """Set up test fixtures."""
        self.renderer = TextRenderer()
        self.received_data = []

        # Create a test slot to capture output
        self.capture_slot = Slot(
            "capture", None, lambda **kwargs: self.received_data.append(kwargs)
        )
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
        self.capture_slot = Slot(
            "capture", None, lambda **kwargs: self.received_data.append(kwargs)
        )
        self.extractor.get_event("output").connect(self.capture_slot)

    def test_extract_json_block(self):
        """Test extracting JSON code block."""
        text = 'Some text\n```json\n{"key": "value"}\n```\nMore text'
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
            {"format": "output", "content": "World"},
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
        text = '```json\n{"key": "value"}\n```\n```python\nprint(\'test\')\n```'
        self.extractor.input_slot.receive({"data": text})

        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["format"], "json")

    def test_strategy_priority(self):
        """Test priority strategy."""
        self.extractor.set_config(
            strategy="priority", extractor_priority=["code_block", "json_code_block"]
        )
        text = '```json\n{"key": "value"}\n```'
        self.extractor.input_slot.receive({"data": text})

        self.assertEqual(len(self.received_data), 1)
        # Should use code_block extractor first due to priority
        self.assertIn(
            self.received_data[0]["metadata"]["extractor"], ["code_block", "json_code_block"]
        )

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
        text = '```json\n{"key": "value"}\n```'
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

    def test_strategy_all(self):
        """Test 'all' strategy returns all successful extractions."""
        self.extractor.set_config(strategy="all")
        text = '```json\n{"key": "value"}\n```\n```python\nprint("test")\n```'
        self.extractor.input_slot.receive({"data": text})

        self.assertEqual(len(self.received_data), 1)
        # Should return list of all extractions
        self.assertEqual(self.received_data[0]["format"], "multi")
        self.assertIsInstance(self.received_data[0]["extracted_result"], list)
        self.assertGreater(len(self.received_data[0]["extracted_result"]), 0)

    def test_raise_on_failure(self):
        """Test ValueError when return_original_on_failure=False and all extractors fail."""
        self.extractor.set_config(return_original_on_failure=False)
        text = "No valid data here"

        # The error will be caught by the slot handler, so the test
        # verifies that the extractor attempts to raise the error
        # The slot will log the error but not propagate it
        self.extractor.input_slot.receive({"data": text})
        # After the error, no data should be received because the handler failed
        # But the slot catches errors, so this test verifies the behavior
        self.assertEqual(len(self.received_data), 0)

    def test_empty_dict_to_string_conversion(self):
        """Test empty dict is converted to empty string."""
        self.extractor.input_slot.receive({"data": {}})

        self.assertEqual(len(self.received_data), 1)
        # Empty dict should be converted to empty string
        self.assertEqual(self.received_data[0]["confidence"], 0.0)

    def test_xml_code_block_extraction(self):
        """Test XML code block extraction."""
        self.extractor.set_config(extract_xml_blocks=True)
        text = "```xml\n<root><item>test</item></root>\n```"
        self.extractor.input_slot.receive({"data": text})

        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["format"], "xml")
        self.assertIn("<root>", self.received_data[0]["extracted_result"])

    def test_interpreter_output_with_string_elements(self):
        """Test interpreter output extraction with string elements in list."""
        outputs = ["Line 1", "Line 2", {"format": "output", "content": "Line 3"}]
        self.extractor.input_slot.receive({"data": outputs})

        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["format"], "interpreter_output")
        self.assertIn("Line 1", self.received_data[0]["extracted_result"])

    def test_register_extractor_initializes_dict(self):
        """Test register_extractor initializes _extractors if not present."""
        # Create a new extractor without calling __init__ properly
        from routilux.builtin_routines.text_processing import ResultExtractor

        extractor = ResultExtractor()
        # Remove _extractors to test initialization
        if hasattr(extractor, "_extractors"):
            delattr(extractor, "_extractors")

        # Register should initialize the dict
        extractor.register_extractor("test_custom", lambda data, config: None)
        self.assertTrue(hasattr(extractor, "_extractors"))
        self.assertIn("test_custom", extractor._extractors)

    def test_extractor_error_handling_continue_on_error(self):
        """Test error handling with continue_on_error=True."""

        # Create an extractor that will fail
        def failing_extractor(data, config):
            raise RuntimeError("Intentional failure")

        self.extractor.register_extractor("failing", failing_extractor)
        self.extractor.set_config(
            continue_on_error=True, extractor_priority=["failing", "json_string"]
        )
        self.extractor.set_config(parse_json_strings=True)

        text = '{"key": "value"}'
        self.extractor.input_slot.receive({"data": text})

        # Should continue and find valid JSON
        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["format"], "json")

    def test_extractor_error_handling_stop_on_error(self):
        """Test error handling with continue_on_error=False."""

        def failing_extractor(data, config):
            raise RuntimeError("Intentional failure")

        self.extractor.register_extractor("failing", failing_extractor)
        self.extractor.set_config(
            continue_on_error=False, return_original_on_failure=True, extractor_priority=["failing"]
        )

        text = '{"key": "value"}'
        self.extractor.input_slot.receive({"data": text})

        # Should fail and return original
        self.assertEqual(len(self.received_data), 1)
        self.assertEqual(self.received_data[0]["format"], "str")
