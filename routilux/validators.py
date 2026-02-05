"""Input validation framework for Routilux.

This module provides an opt-in validation framework for slot handler
input validation. Users can validate incoming data before it reaches
their handlers, preventing type errors and invalid data.

Features:
    - Type-based validation (similar to type hints)
    - Custom validation functions
    - Composable validators
    - Clear error messages

Usage:
    >>> from routilux.validators import Validator
    >>>
    >>> # Type-based validation
    >>> validator = Validator.types(user_id=int, name=str, active=bool)
    >>>
    >>> # Custom validation
    >>> def validate(data):
    ...     if not data.get("api_key"):
    ...         return False, "API key required"
    ...     return True, ""
    >>> validator = Validator.custom(validate)
    >>>
    >>> # Use with slot
    >>> slot = routine.define_slot("input", handler=process, validator=validator)
"""

from typing import Any, Callable, Dict, Tuple, Type, Union


class ValidationError(Exception):
    """Raised when input validation fails.

    Attributes:
        message: Human-readable error message.
        field: Name of the field that failed validation (optional).
    """

    def __init__(self, message: str, field: str = ""):
        """Initialize ValidationError.

        Args:
            message: Error message.
            field: Optional field name that failed.
        """
        super().__init__(message)
        self.message = message
        self.field = field

    def __str__(self) -> str:
        """Return string representation."""
        if self.field:
            return f"Validation failed for '{self.field}': {self.message}"
        return f"Validation failed: {self.message}"


class Validator:
    """Base class for validators.

    Provides factory methods for creating different validator types:
    - types(): Type-based validation
    - custom(): Custom function-based validation
    """

    @staticmethod
    def types(**type_map: Type) -> "TypesValidator":
        """Create a type-based validator.

        Validates that data fields match expected types.

        Args:
            **type_map: Mapping of field names to expected types.

        Returns:
            TypesValidator instance.

        Examples:
            >>> validator = Validator.types(user_id=int, name=str, active=bool)
            >>> validator.validate({"user_id": 123, "name": "Alice", "active": True})
        """
        return TypesValidator(type_map)

    @staticmethod
    def custom(
        func: Callable[[Dict[str, Any]], bool],
    ) -> "CustomValidator":
        """Create a custom function-based validator.

        The function should return True if validation passes,
        or raise/return False if it fails.

        Args:
            func: Validation function that takes data dict and returns bool.

        Returns:
            CustomValidator instance.

        Examples:
            >>> def validate(data):
            ...     return len(data.get("name", "")) > 0
            >>> validator = Validator.custom(validate)
        """
        return CustomValidator(func)

    def validate(self, data: Dict[str, Any]) -> None:
        """Validate data.

        Args:
            data: Data dictionary to validate.

        Raises:
            ValidationError: If validation fails.
        """
        raise NotImplementedError("Subclasses must implement validate()")


class TypesValidator(Validator):
    """Validates data field types.

    Checks that each specified field exists and matches the expected type.
    """

    def __init__(self, type_map: Dict[str, Type]):
        """Initialize TypesValidator.

        Args:
            type_map: Mapping of field names to expected types.
        """
        self.type_map = type_map

    def validate(self, data: Dict[str, Any]) -> None:
        """Validate data field types.

        Args:
            data: Data dictionary to validate.

        Raises:
            ValidationError: If any field is missing or wrong type.
        """
        for field, expected_type in self.type_map.items():
            if field not in data:
                raise ValidationError(f"Missing required field: {field}", field=field)

            value = data[field]
            if not isinstance(value, expected_type):
                actual_type = type(value).__name__
                expected_name = expected_type.__name__
                raise ValidationError(
                    f"Field '{field}' must be {expected_name}, got {actual_type}",
                    field=field,
                )


class CustomValidator(Validator):
    """Validates data using a custom function.

    The validation function receives the data dict and should:
    - Return True if validation passes
    - Return False or raise ValidationError if validation fails
    - Optionally return (True, "") or (False, "error message")
    """

    def __init__(
        self,
        func: Callable[[Dict[str, Any]], Union[bool, Tuple[bool, str]]],
    ):
        """Initialize CustomValidator.

        Args:
            func: Validation function.
        """
        self.func = func

    def validate(self, data: Dict[str, Any]) -> None:
        """Validate data using custom function.

        Args:
            data: Data dictionary to validate.

        Raises:
            ValidationError: If validation function returns False or raises.
        """
        try:
            result = self.func(data)

            # Handle (bool, str) return format
            if isinstance(result, tuple):
                passed, message = result
                if not passed:
                    raise ValidationError(message)
            elif not result:
                raise ValidationError("Custom validation failed")

        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"Custom validation error: {e}") from e


__all__ = [
    "ValidationError",
    "Validator",
    "TypesValidator",
    "CustomValidator",
]
