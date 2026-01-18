"""
Error codes and structured error response utilities for Routilux API.

This module provides:
- Standardized error codes (ErrorCode enum)
- Utility function to create structured error responses
"""

from enum import Enum
from typing import Any, Dict, Optional


class ErrorCode(str, Enum):
    """Error codes for API responses.

    All API errors should use one of these codes for machine-readable
    error identification.
    """

    # Flow errors
    FLOW_NOT_FOUND = "FLOW_NOT_FOUND"
    FLOW_ALREADY_EXISTS = "FLOW_ALREADY_EXISTS"
    FLOW_VALIDATION_FAILED = "FLOW_VALIDATION_FAILED"

    # Worker errors
    WORKER_NOT_FOUND = "WORKER_NOT_FOUND"
    WORKER_ALREADY_EXISTS = "WORKER_ALREADY_EXISTS"
    WORKER_NOT_RUNNING = "WORKER_NOT_RUNNING"
    WORKER_ALREADY_COMPLETED = "WORKER_ALREADY_COMPLETED"

    # Job errors
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    JOB_ALREADY_COMPLETED = "JOB_ALREADY_COMPLETED"
    JOB_SUBMISSION_FAILED = "JOB_SUBMISSION_FAILED"

    # Routine/Slot errors
    ROUTINE_NOT_FOUND = "ROUTINE_NOT_FOUND"
    SLOT_NOT_FOUND = "SLOT_NOT_FOUND"
    SLOT_QUEUE_FULL = "SLOT_QUEUE_FULL"

    # System errors
    RUNTIME_SHUTDOWN = "RUNTIME_SHUTDOWN"
    TIMEOUT_EXCEEDED = "TIMEOUT_EXCEEDED"
    INTERNAL_ERROR = "INTERNAL_ERROR"

    # Validation errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"


def create_error_response(
    code: ErrorCode,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create structured error response.

    Args:
        code: Error code from ErrorCode enum
        message: Human-readable error message
        details: Optional additional context
        request_id: Optional request ID for tracing

    Returns:
        Structured error response dict

    Example:
        >>> create_error_response(
        ...     ErrorCode.FLOW_NOT_FOUND,
        ...     "Flow 'my_flow' not found",
        ...     details={"flow_id": "my_flow"}
        ... )
        {
            "error": {
                "code": "FLOW_NOT_FOUND",
                "message": "Flow 'my_flow' not found",
                "details": {"flow_id": "my_flow"},
                "request_id": None
            }
        }
    """
    return {
        "error": {
            "code": code.value,
            "message": message,
            "details": details,
            "request_id": request_id,
        }
    }


def error_detail(
    code: ErrorCode,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Alias for create_error_response for cleaner usage in HTTPException.

    This is a convenience function that returns just the inner error dict,
    suitable for use with FastAPI's HTTPException detail parameter.

    Args:
        code: Error code from ErrorCode enum
        message: Human-readable error message
        details: Optional additional context
        request_id: Optional request ID for tracing

    Returns:
        Error detail dict (the inner "error" object)
    """
    return create_error_response(code, message, details, request_id)
