"""Custom exception hierarchy for Routilux.

This module defines the exception hierarchy used throughout Routilux.
All framework exceptions inherit from RoutiluxError, allowing users
to catch all framework errors with a single except clause.

Exception Hierarchy:
    RoutiluxError (base)
    ├── ExecutionError      # Runtime errors during workflow execution
    ├── SerializationError  # Serialization/deserialization failures
    ├── ConfigurationError  # Invalid setup/parameters
    ├── StateError          # JobState/Flow state inconsistencies
    └── SlotHandlerError    # User slot handler failures
"""


class RoutiluxError(Exception):
    """Base exception for all Routilux framework errors.

    Users can catch RoutiluxError to handle any framework-related error.
    This allows for selective error handling without catching bare Exception.

    Examples:
        Catch all framework errors:
            >>> try:
            ...     flow.execute(entry_id)
            ... except RoutiluxError as e:
            ...     logger.error(f"Framework error: {e}")
    """

    pass


class ExecutionError(RoutiluxError):
    """Error that occurs during workflow execution.

    Raised when a routine or workflow fails to execute properly.
    This includes runtime errors, task execution failures, and
    event processing errors.

    Attributes:
        routine_id: ID of the routine that failed (optional).

    Examples:
        Basic execution error:
            >>> raise ExecutionError("Failed to execute routine")

        With routine context:
            >>> raise ExecutionError("Timeout", routine_id="processor")
    """

    def __init__(self, message: str, routine_id: str = ""):
        """Initialize ExecutionError.

        Args:
            message: Error message.
            routine_id: Optional routine identifier for context.
        """
        super().__init__(message)
        self.routine_id = routine_id
        if routine_id:
            self.args = (f"{message} (routine_id={routine_id})",)


class SerializationError(RoutiluxError):
    """Error that occurs during serialization or deserialization.

    Raised when an object cannot be serialized for persistence or
    transmitted across process boundaries.

    Attributes:
        object_type: Type name of the object that failed (optional).

    Examples:
        Basic serialization error:
            >>> raise SerializationError("Cannot serialize lambda functions")

        With object type context:
            >>> raise SerializationError("Missing serializer", object_type="CustomClass")
    """

    def __init__(self, message: str, object_type: str = ""):
        """Initialize SerializationError.

        Args:
            message: Error message.
            object_type: Optional type name for context.
        """
        super().__init__(message)
        self.object_type = object_type
        if object_type:
            self.args = (f"{message} (type={object_type})",)


class ConfigurationError(RoutiluxError):
    """Error that occurs due to invalid configuration.

    Raised when the framework is misconfigured, such as invalid
    parameters, missing required settings, or incompatible options.

    Examples:
        >>> raise ConfigurationError("Flow cannot have duplicate routine IDs")
    """

    pass


class StateError(RoutiluxError):
    """Error that occurs due to inconsistent or invalid state.

    Raised when JobState or Flow state is inconsistent, such as
    attempting to resume a completed workflow or accessing
    non-existent state.

    Examples:
        >>> raise StateError("Cannot resume completed workflow")
    """

    pass


class SlotHandlerError(RoutiluxError):
    """Error that occurs in a user-defined slot handler.

    Wraps user code exceptions to distinguish framework errors
    from user code errors.

    Attributes:
        slot_name: Name of the slot whose handler failed (optional).
        original_exception: The original exception from user code (optional).

    Examples:
        Basic handler error:
            >>> raise SlotHandlerError("Handler raised ValueError")

        With slot context:
            >>> raise SlotHandlerError("Division by zero", slot_name="input")
    """

    def __init__(self, message: str, slot_name: str = ""):
        """Initialize SlotHandlerError.

        Args:
            message: Error message.
            slot_name: Optional slot name for context.
        """
        super().__init__(message)
        self.slot_name = slot_name
        if slot_name:
            self.args = (f"{message} (slot={slot_name})",)


__all__ = [
    "RoutiluxError",
    "ExecutionError",
    "SerializationError",
    "ConfigurationError",
    "StateError",
    "SlotHandlerError",
]
