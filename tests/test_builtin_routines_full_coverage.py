"""
Comprehensive tests for builtin routines to achieve 95%+ coverage.

These tests cover the uncovered lines in:
- data_processing/data_transformer.py
- data_processing/data_validator.py
- text_processing/result_extractor.py
- text_processing/text_clipper.py
- text_processing/text_renderer.py
- utils/data_flattener.py
- utils/time_provider.py
"""


from routilux.builtin_routines.data_processing import (
    DataTransformer,
    DataValidator,
)
from routilux.builtin_routines.text_processing import (
    ResultExtractor,
    TextClipper,
    TextRenderer,
)
from routilux.builtin_routines.utils import (
    DataFlattener,
    TimeProvider,
)
from routilux.slot import Slot


class TestDataTransformerCoverage:
    """Test cases for DataTransformer uncovered lines."""

    def test_transform_with_unknown_transformation(self):
        """Test transformation with unknown transformation name."""
        transformer = DataTransformer()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        transformer.output_event.connect(output_slot)

        # Set unknown transformation
        transformer.set_config(transformations=["unknown_transform"])

        # Trigger transformation
        transformer.input_slot.receive({"data": "test"})

        # Should emit with errors
        assert len(received) == 1
        assert received[0]["errors"] is not None
        assert "Unknown transformation" in received[0]["errors"][0]

    def test_transform_with_invalid_transformation(self):
        """Test transformation with invalid transformation type."""
        transformer = DataTransformer()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        transformer.output_event.connect(output_slot)

        # Set invalid transformation (not string or callable)
        transformer.set_config(transformations=[123])

        # Trigger transformation
        transformer.input_slot.receive({"data": "test"})

        # Should emit with errors
        assert len(received) == 1
        assert received[0]["errors"] is not None
        assert "Invalid transformation" in received[0]["errors"][0]

    def test_transform_with_callable_error(self):
        """Test transformation with callable that raises error."""
        transformer = DataTransformer()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        transformer.output_event.connect(output_slot)

        # Set failing transformation
        def failing_transform(x):
            raise ValueError("Simulated failure")

        transformer.set_config(transformations=[failing_transform])

        # Trigger transformation
        transformer.input_slot.receive({"data": "test"})

        # Should emit with errors
        assert len(received) == 1
        assert received[0]["errors"] is not None
        assert "Error applying" in received[0]["errors"][0]

    def test_transform_with_lambda(self):
        """Test transformation with lambda."""
        transformer = DataTransformer()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        transformer.output_event.connect(output_slot)

        # Set lambda as transformation
        transformer.set_config(transformations=[lambda x: str(x).upper()])

        # Trigger transformation
        transformer.input_slot.receive({"data": "test"})

        # Should emit with lambda's name
        assert len(received) == 1
        assert received[0]["transformed_data"] == "TEST"

    def test_register_custom_transformation(self):
        """Test registering custom transformation."""
        transformer = DataTransformer()

        def double_string(x):
            if isinstance(x, str):
                return x + x
            return x

        transformer.register_transformation("double", double_string)

        # Check it's registered
        transformation_map = transformer.get_config("transformation_map")
        assert "double" in transformation_map
        assert transformation_map["double"] is double_string


class TestDataValidatorCoverage:
    """Test cases for DataValidator uncovered lines."""

    def test_validate_with_all_rules_passing(self):
        """Test validation with all rules passing."""
        validator = DataValidator()
        received_valid = []

        valid_slot = Slot("valid", None, lambda **kwargs: received_valid.append(kwargs))
        validator.valid_event.connect(valid_slot)

        # Set validation rules
        validator.set_config(rules={"name": "is_string", "age": "is_int"})

        # Valid data
        validator.input_slot.receive({"data": {"name": "John", "age": 30}})

        # Should pass validation
        assert len(received_valid) == 1
        assert received_valid[0]["validated_data"] == {"name": "John", "age": 30}

    def test_validate_with_required_field_missing(self):
        """Test validation with required field missing."""
        validator = DataValidator()
        received_invalid = []

        invalid_slot = Slot("invalid", None, lambda **kwargs: received_invalid.append(kwargs))
        validator.invalid_event.connect(invalid_slot)

        # Set validation rules with required fields
        validator.set_config(required_fields=["name"])

        # Invalid data (missing required field)
        validator.input_slot.receive({"data": {"age": 30}})

        # Should fail validation
        assert len(received_invalid) == 1
        assert "required" in received_invalid[0]["errors"][0].lower()

    def test_validate_with_unknown_validator(self):
        """Test validation with unknown validator."""
        validator = DataValidator()
        received_invalid = []

        invalid_slot = Slot("invalid", None, lambda **kwargs: received_invalid.append(kwargs))
        validator.invalid_event.connect(invalid_slot)

        # Set validation rules with unknown validator
        validator.set_config(rules={"age": "unknown_validator"})

        # Input data
        validator.input_slot.receive({"data": {"age": 30}})

        # Should fail validation with unknown validator error
        assert len(received_invalid) == 1
        assert "Unknown validator" in received_invalid[0]["errors"][0]

    def test_validate_with_custom_validator_returning_tuple(self):
        """Test validation with custom validator returning (bool, error_msg)."""
        validator = DataValidator()
        received_valid = []

        valid_slot = Slot("valid", None, lambda **kwargs: received_valid.append(kwargs))
        validator.valid_event.connect(valid_slot)

        # Set validation rules with custom validator that returns tuple
        def range_validator(value):
            if isinstance(value, int) and 0 <= value <= 120:
                return True, None
            return False, "Age must be between 0 and 120"

        validator.set_config(rules={"age": range_validator})

        # Valid data
        validator.input_slot.receive({"data": {"age": 30}})

        # Should pass validation
        assert len(received_valid) == 1

    def test_validate_list_items(self):
        """Test validation of list items."""
        validator = DataValidator()
        received_valid = []

        valid_slot = Slot("valid", None, lambda **kwargs: received_valid.append(kwargs))
        validator.valid_event.connect(valid_slot)

        # Set validation rules for list items
        validator.set_config(rules={"items": "is_int"})

        # Valid list data
        validator.input_slot.receive({"data": [1, 2, 3, 4]})

        # Should pass validation
        assert len(received_valid) == 1

    def test_validate_primitive_value(self):
        """Test validation of primitive value."""
        validator = DataValidator()
        received_valid = []

        valid_slot = Slot("valid", None, lambda **kwargs: received_valid.append(kwargs))
        validator.valid_event.connect(valid_slot)

        # Set validation rules for primitive value
        validator.set_config(rules={"value": "is_positive"})

        # Valid primitive data
        validator.input_slot.receive({"data": 42})

        # Should pass validation
        assert len(received_valid) == 1

    def test_register_custom_validator(self):
        """Test registering custom validator."""
        validator = DataValidator()

        def is_even(value):
            return value % 2 == 0

        validator.register_validator("is_even", is_even)

        # Check it's registered
        assert "is_even" in validator._builtin_validators


class TestResultExtractorCoverage:
    """Test cases for ResultExtractor uncovered lines."""

    def test_extract_with_strategy_all(self):
        """Test extraction with 'all' strategy."""
        extractor = ResultExtractor()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        extractor.output_event.connect(output_slot)

        # Set strategy to all
        extractor.set_config(strategy="all")

        # Input that's a dict
        extractor.input_slot.receive({"data": {"key": "value"}})

        # Should extract
        assert len(received) == 1

    def test_extract_with_custom_priority(self):
        """Test extraction with custom priority order."""
        extractor = ResultExtractor()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        extractor.output_event.connect(output_slot)

        # Set custom priority
        extractor.set_config(
            strategy="priority", extractor_priority=["dict_extractor", "json_string"]
        )

        # Input that's both dict and potentially JSON
        extractor.input_slot.receive({"data": {"key": "value"}})

        # Should use dict_extractor first
        assert len(received) == 1
        assert received[0]["format"] == "dict"

    def test_extract_json_code_blocks(self):
        """Test extracting JSON from code blocks."""
        extractor = ResultExtractor()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        extractor.output_event.connect(output_slot)

        # Input with JSON code block
        extractor.input_slot.receive(
            {"data": 'Some text\n```json\n{"key": "value"}\n```\nMore text'}
        )

        # Should extract JSON
        assert len(received) == 1
        assert received[0]["format"] == "json"
        assert received[0]["extracted_result"]["key"] == "value"

    def test_extract_from_interpreter_output(self):
        """Test extraction from interpreter output format."""
        extractor = ResultExtractor()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        extractor.output_event.connect(output_slot)

        # Input with interpreter output format
        interpreter_data = [
            {"format": "output", "content": "Line 1"},
            {"format": "output", "content": "Line 2"},
        ]

        extractor.input_slot.receive({"data": interpreter_data})

        # Should extract as interpreter output
        assert len(received) == 1
        assert received[0]["format"] == "interpreter_output"
        assert "Line 1" in received[0]["extracted_result"]
        assert "Line 2" in received[0]["extracted_result"]

    def test_extract_returns_original_on_failure(self):
        """Test that original data is returned when all extractors fail."""
        extractor = ResultExtractor()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        extractor.output_event.connect(output_slot)

        # Input that can't be extracted
        extractor.input_slot.receive({"data": "plain text with no structure"})

        # Should return original
        assert len(received) == 1
        assert received[0]["extracted_result"] == "plain text with no structure"
        assert received[0]["format"] == "str"

    def test_extract_with_continue_on_error_false(self):
        """Test extraction with continue_on_error=False."""
        extractor = ResultExtractor()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        extractor.output_event.connect(output_slot)

        # Set continue_on_error to False
        extractor.set_config(continue_on_error=False)

        # Input that will cause first extractor to fail
        extractor.input_slot.receive({"data": "```json\ninvalid json\n```"})

        # Should still return something (dict/list extractors might work)
        assert len(received) >= 1

    def test_extract_calculate_confidence(self):
        """Test confidence calculation."""
        extractor = ResultExtractor()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        extractor.output_event.connect(output_slot)

        # Input with well-formed JSON
        extractor.input_slot.receive({"data": '{"key": "value"}'})

        # Should have high confidence
        assert len(received) == 1
        assert received[0]["confidence"] > 0.5

    def test_register_custom_extractor(self):
        """Test registering custom extractor."""
        extractor = ResultExtractor()

        def custom_extractor(data, config):
            if isinstance(data, str) and data.startswith("CUSTOM:"):
                return data[7:], "custom", {"method": "prefix"}
            return None

        extractor.register_extractor("custom_prefix", custom_extractor)

        # Check it's registered
        assert "custom_prefix" in extractor._extractors

        # Test it works
        received = []
        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        extractor.output_event.connect(output_slot)

        extractor.input_slot.receive({"data": "CUSTOM:test_data"})

        assert len(received) == 1
        assert received[0]["format"] == "custom"
        assert received[0]["extracted_result"] == "test_data"


class TestTextClipperCoverage:
    """Test cases for TextClipper uncovered lines."""

    def test_clip_with_max_length(self):
        """Test clipping with max_length."""
        clipper = TextClipper()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        clipper.output_event.connect(output_slot)

        # Set max length
        clipper.set_config(max_length=10)

        # Input text longer than max - use {"text": ...} format
        clipper.input_slot.receive({"text": "This is a very long text that should be clipped"})

        # Should clip
        assert len(received) == 1
        assert received[0]["was_clipped"] is True

    def test_clip_with_traceback_preserved(self):
        """Test that tracebacks are preserved when preserve_tracebacks=True."""
        clipper = TextClipper()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        clipper.output_event.connect(output_slot)

        # Set max length and preserve tracebacks
        clipper.set_config(max_length=10, preserve_tracebacks=True)

        # Input text with traceback
        clipper.input_slot.receive(
            {"text": "Some text\nTraceback (most recent call last):\n  Error here"}
        )

        # Should not clip because of traceback
        assert len(received) == 1
        assert received[0]["was_clipped"] is False
        assert "Traceback" in received[0]["clipped_text"]

    def test_clip_text_under_limit(self):
        """Test clipping when text is under max_length."""
        clipper = TextClipper()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        clipper.output_event.connect(output_slot)

        # Set max length
        clipper.set_config(max_length=1000)

        # Input text shorter than max
        clipper.input_slot.receive({"text": "Short text"})

        # Should not clip
        assert len(received) == 1
        assert received[0]["was_clipped"] is False
        assert received[0]["clipped_text"] == "Short text"

    def test_clip_with_dict_input(self):
        """Test clipping with dict input containing text."""
        clipper = TextClipper()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        clipper.output_event.connect(output_slot)

        # Input dict with text key
        clipper.input_slot.receive({"text": "This is text content"})

        # Should extract and clip if needed
        assert len(received) == 1
        assert "text content" in received[0]["clipped_text"]


class TestTextRendererCoverage:
    """Test cases for TextRenderer uncovered lines."""

    def test_render_dict_with_xml_format(self):
        """Test rendering dict with XML format."""
        renderer = TextRenderer()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        renderer.output_event.connect(output_slot)

        # Input dict
        renderer.input_slot.receive({"data": {"name": "World", "value": 42}})

        # Should render as XML
        assert len(received) == 1
        assert "<name>World</name>" in received[0]["rendered_text"]
        assert "<value>42</value>" in received[0]["rendered_text"]

    def test_render_list(self):
        """Test rendering list."""
        renderer = TextRenderer()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        renderer.output_event.connect(output_slot)

        # Input list
        renderer.input_slot.receive({"data": ["a", "b", "c"]})

        # Should render as XML items
        assert len(received) == 1
        assert "<item_0>a</item_0>" in received[0]["rendered_text"]

    def test_render_with_circular_reference(self):
        """Test rendering with circular reference detection."""
        renderer = TextRenderer()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        renderer.output_event.connect(output_slot)

        # Create circular reference
        data = {"key": "value"}
        data["self"] = data

        # Input with circular reference
        renderer.input_slot.receive({"data": data})

        # Should detect and handle circular reference
        assert len(received) == 1
        assert "[Circular Reference]" in received[0]["rendered_text"]


class TestDataFlattenerCoverage:
    """Test cases for DataFlattener uncovered lines."""

    def test_flatten_nested_dict(self):
        """Test flattening nested dictionary."""
        flattener = DataFlattener()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        flattener.output_event.connect(output_slot)

        # Input nested dict
        flattener.input_slot.receive(
            {"data": {"user": {"name": "John", "age": 30}, "address": {"city": "NYC"}}}
        )

        # Should flatten
        assert len(received) == 1
        assert "user.name" in received[0]["flattened_data"]
        assert "address.city" in received[0]["flattened_data"]


class TestTimeProviderCoverage:
    """Test cases for TimeProvider uncovered lines."""

    def test_provide_current_time_iso(self):
        """Test providing current time in ISO format."""
        provider = TimeProvider()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        provider.output_event.connect(output_slot)

        # Get current time (default ISO format)
        provider.trigger_slot.receive({})

        # Should provide time
        assert len(received) == 1
        assert "timestamp" in received[0]
        assert "time_string" in received[0]

    def test_provide_formatted_time_chinese_locale(self):
        """Test providing formatted time with Chinese locale."""
        provider = TimeProvider()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        provider.output_event.connect(output_slot)

        # Set format to formatted with Chinese locale
        provider.set_config(format="formatted", locale="zh_CN", include_weekday=True)

        # Get formatted time
        provider.trigger_slot.receive({})

        # Should provide formatted time
        assert len(received) == 1
        assert "formatted" in received[0]
        # Chinese format should contain Chinese characters
        assert any(c in received[0]["time_string"] for c in "年月日星期")

    def test_provide_formatted_time_english_locale(self):
        """Test providing formatted time with English locale."""
        provider = TimeProvider()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        provider.output_event.connect(output_slot)

        # Set format to formatted with English locale
        provider.set_config(format="formatted", locale="en_US", include_weekday=True)

        # Get formatted time
        provider.trigger_slot.receive({})

        # Should provide formatted time
        assert len(received) == 1
        assert "formatted" in received[0]
        # English format should contain weekday name
        assert any(
            day in received[0]["time_string"]
            for day in [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
        )

    def test_provide_timestamp_format(self):
        """Test providing time as timestamp."""
        provider = TimeProvider()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        provider.output_event.connect(output_slot)

        # Set format to timestamp
        provider.set_config(format="timestamp")

        # Get timestamp
        provider.trigger_slot.receive({})

        # Should provide timestamp as string
        assert len(received) == 1
        assert received[0]["time_string"].replace(".", "").isdigit()

    def test_provide_custom_format(self):
        """Test providing time with custom format."""
        provider = TimeProvider()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        provider.output_event.connect(output_slot)

        # Set custom format
        provider.set_config(format="custom", custom_format="%Y-%m-%d %H:%M:%S")

        # Get formatted time
        provider.trigger_slot.receive({})

        # Should provide formatted time
        assert len(received) == 1
        assert len(received[0]["time_string"]) == 19  # YYYY-MM-DD HH:MM:SS

    def test_provide_time_with_format_override(self):
        """Test providing time with format override in data."""
        provider = TimeProvider()
        received = []

        output_slot = Slot("output", None, lambda **kwargs: received.append(kwargs))
        provider.output_event.connect(output_slot)

        # Override format in request data
        provider.trigger_slot.receive({"format": "timestamp"})

        # Should use override format
        assert len(received) == 1
        assert received[0]["time_string"].replace(".", "").isdigit()
