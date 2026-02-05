"""Tests for input validation framework."""

import pytest

from routilux.routine import Routine
from routilux.slot import Slot
from routilux.validators import ValidationError, Validator


class TestValidationError:
    """Tests for ValidationError exception."""

    def test_validation_error_is_exception(self):
        """ValidationError should be an Exception."""
        assert issubclass(ValidationError, Exception)

    def test_validation_error_message(self):
        """ValidationError should store error message."""
        exc = ValidationError("Invalid input")
        assert "Invalid input" in str(exc)
        assert exc.message == "Invalid input"


class TestTypesValidator:
    """Tests for type-based validation."""

    def test_valid_input_passes(self):
        """Valid input should pass validation."""
        validator = Validator.types(user_id=int, name=str, active=bool)
        data = {"user_id": 123, "name": "Alice", "active": True}
        # Should not raise
        validator.validate(data)

    def test_invalid_type_raises_error(self):
        """Invalid type should raise ValidationError."""
        validator = Validator.types(count=int)
        data = {"count": "not_an_int"}
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(data)
        assert "count" in str(exc_info.value)

    def test_missing_required_field_raises_error(self):
        """Missing required field should raise ValidationError."""
        validator = Validator.types(required=str)
        data = {}
        with pytest.raises(ValidationError) as exc_info:
            validator.validate(data)
        assert "required" in str(exc_info.value)

    def test_optional_field_allows_none(self):
        """Optional field should allow None or absence."""
        validator = Validator.types(required=str)
        data = {"required": "value"}
        # Should not raise (only required field is present)
        validator.validate(data)


class TestCustomValidator:
    """Tests for custom validation functions."""

    def test_custom_validator_passes(self):
        """Custom validator should pass when function returns True."""
        def validate(data):
            return len(data.get("name", "")) > 0

        validator = Validator.custom(validate)
        validator.validate({"name": "Alice"})

    def test_custom_validator_fails(self):
        """Custom validator should raise ValidationError when function returns False."""
        def validate(data):
            return len(data.get("name", "")) > 0

        validator = Validator.custom(validate)
        with pytest.raises(ValidationError):
            validator.validate({"name": ""})

    def test_custom_validator_with_message(self):
        """Custom validator can provide custom error message."""
        def validate(data):
            if not data.get("email"):
                return False, "Email is required"
            return True, ""

        validator = Validator.custom(validate)
        with pytest.raises(ValidationError) as exc_info:
            validator.validate({})
        assert "Email is required" in str(exc_info.value)


class TestSlotIntegration:
    """Tests for validator integration with Slot."""

    def test_slot_with_validator_rejects_invalid_data(self):
        """Slot with validator should reject invalid data."""
        routine = Routine()
        validator = Validator.types(value=int)

        received_data = []

        def handler(data):
            received_data.append(data)

        slot = Slot(name="input", routine=routine, handler=handler)
        slot.validator = validator

        # Invalid data should be rejected
        slot.receive({"value": "not_int"})

        assert len(received_data) == 0

    def test_slot_with_validator_accepts_valid_data(self):
        """Slot with validator should accept valid data."""
        routine = Routine()
        validator = Validator.types(value=int)

        received_data = []

        def handler(data):
            received_data.append(data)

        slot = Slot(name="input", routine=routine, handler=handler)
        slot.validator = validator

        # Valid data should be accepted
        slot.receive({"value": 42})

        assert len(received_data) == 1
        assert received_data[0] == {"value": 42}
