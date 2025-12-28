"""
Data validator routine.

Validates data against schemas or validation rules.
"""

from __future__ import annotations
from typing import Dict, Any, Callable, Optional, Union, Tuple
from routilux.routine import Routine


class DataValidator(Routine):
    """Routine for validating data against schemas or rules.

    This routine validates input data against configurable validation
    rules, useful for data quality checks and schema validation.

    Features:
    - Configurable validation rules
    - Support for custom validation functions
    - Detailed validation error messages
    - Optional strict mode (stop on first error)

    Examples:
        >>> validator = DataValidator()
        >>> validator.set_config(
        ...     rules={"name": lambda x: isinstance(x, str) and len(x) > 0}
        ... )
        >>> validator.define_slot("input", handler=validator.validate)
        >>> validator.define_event("output", ["is_valid", "errors", "validated_data"])
    """

    def __init__(self):
        """Initialize DataValidator routine."""
        super().__init__()

        # Set default configuration
        self.set_config(
            rules={},  # Dict of field_name -> validation function
            strict_mode=False,  # Stop on first validation error
            required_fields=[],  # List of required field names
            allow_extra_fields=True,  # Allow fields not in rules
        )

        # Register built-in validators
        self._register_builtin_validators()

        # Define input slot
        self.input_slot = self.define_slot("input", handler=self._handle_input)

        # Define output events
        self.valid_event = self.define_event("valid", ["validated_data"])
        self.invalid_event = self.define_event("invalid", ["errors", "data"])

    def _register_builtin_validators(self):
        """Register built-in validation functions."""
        builtins = {
            "not_empty": lambda x: x is not None and x != "",
            "is_string": lambda x: isinstance(x, str),
            "is_int": lambda x: isinstance(x, int),
            "is_float": lambda x: isinstance(x, float),
            "is_number": lambda x: isinstance(x, (int, float)),
            "is_dict": lambda x: isinstance(x, dict),
            "is_list": lambda x: isinstance(x, list),
            "is_positive": lambda x: isinstance(x, (int, float)) and x > 0,
            "is_non_negative": lambda x: isinstance(x, (int, float)) and x >= 0,
        }

        # Store builtins for reference (not in config)
        # Initialize as instance attribute
        if not hasattr(self, "_builtin_validators"):
            self._builtin_validators = {}
        self._builtin_validators.update(builtins)

    def _handle_input(self, data: Any = None, rules: Optional[Dict] = None, **kwargs):
        """Handle input data and validate it.

        Args:
            data: Data to validate.
            rules: Optional validation rules dict. If not provided,
                uses _config["rules"].
            **kwargs: Additional data from slot. If 'data' is not provided,
                will use kwargs or the first value.
        """
        # Extract data using Routine helper method
        data = self._extract_input_data(data, **kwargs)

        # Track statistics
        self._track_operation("validations")

        # Get rules from input or config
        rules = rules or self.get_config("rules", {})
        required_fields = self.get_config("required_fields", [])
        strict_mode = self.get_config("strict_mode", False)
        allow_extra_fields = self.get_config("allow_extra_fields", True)

        errors = []

        # Validate required fields
        if isinstance(data, dict):
            for field in required_fields:
                if field not in data:
                    errors.append(f"Required field '{field}' is missing")
                    if strict_mode:
                        break

            # Validate fields against rules
            for field, value in data.items():
                if field in rules:
                    validator = rules[field]
                    is_valid, error_msg = self._validate_field(field, value, validator)
                    if not is_valid:
                        errors.append(error_msg)
                        if strict_mode:
                            break
                elif not allow_extra_fields:
                    errors.append(f"Unexpected field '{field}'")
                    if strict_mode:
                        break

        elif isinstance(data, (list, tuple)):
            # Validate list items
            for i, item in enumerate(data):
                if "items" in rules:
                    validator = rules["items"]
                    is_valid, error_msg = self._validate_field(f"items[{i}]", item, validator)
                    if not is_valid:
                        errors.append(error_msg)
                        if strict_mode:
                            break

        else:
            # Validate primitive value
            if "value" in rules:
                validator = rules["value"]
                is_valid, error_msg = self._validate_field("value", data, validator)
                if not is_valid:
                    errors.append(error_msg)

        # Emit result
        if errors:
            self._track_operation("validations", success=False, error_count=len(errors))
            self.emit("invalid", errors=errors, data=data)
        else:
            self._track_operation("validations", success=True)
            self.emit("valid", validated_data=data)

    def _validate_field(
        self, field_name: str, value: Any, validator: Union[Callable, str]
    ) -> Tuple[bool, Optional[str]]:
        """Validate a single field.

        Args:
            field_name: Name of the field being validated.
            value: Value to validate.
            validator: Validation function or builtin validator name.

        Returns:
            Tuple of (is_valid, error_message).
        """
        try:
            if isinstance(validator, str):
                # Look up builtin validator
                if validator in self._builtin_validators:
                    validator_func = self._builtin_validators[validator]
                    is_valid = validator_func(value)
                else:
                    return False, f"Unknown validator: {validator}"
            elif callable(validator):
                # Custom validation function
                result = validator(value)
                if isinstance(result, bool):
                    is_valid = result
                elif isinstance(result, tuple) and len(result) == 2:
                    is_valid, error_msg = result
                    if not is_valid:
                        return False, error_msg
                    return True, None
                else:
                    is_valid = bool(result)
            else:
                return False, f"Invalid validator for field '{field_name}'"

            if not is_valid:
                return False, f"Field '{field_name}' failed validation"

            return True, None

        except Exception as e:
            return False, f"Validation error for field '{field_name}': {str(e)}"

    def register_validator(self, name: str, func: Callable) -> None:
        """Register a custom validator function.

        Args:
            name: Validator name.
            func: Validation function that takes value and returns bool or (bool, error_msg).
        """
        if not hasattr(self, "_builtin_validators"):
            self._builtin_validators = {}
        self._builtin_validators[name] = func
