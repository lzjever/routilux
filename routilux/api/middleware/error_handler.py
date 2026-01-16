"""
Global exception handlers for API.

Provides standardized error responses for all exceptions.
"""

import logging
from datetime import datetime

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from routilux.api.models.error import ErrorResponse

logger = logging.getLogger(__name__)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors."""
    # Ensure all error details are JSON serializable
    errors = exc.errors()
    serializable_errors = []
    for error in errors:
        serializable_error = {}
        for key, value in error.items():
            # Convert non-serializable objects to strings
            if isinstance(value, (Exception, type)):
                serializable_error[key] = str(value)
            elif isinstance(value, (dict, list)):
                # Recursively convert nested structures
                serializable_error[key] = _make_serializable(value)
            else:
                serializable_error[key] = value
        serializable_errors.append(serializable_error)
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=ErrorResponse(
            error="validation_error",
            error_code="VALIDATION_ERROR",
            message="Request validation failed",
            details={"errors": serializable_errors},
            timestamp=int(datetime.now().timestamp()),
        ).model_dump(),
    )


def _make_serializable(obj):
    """Recursively convert non-serializable objects to strings."""
    if isinstance(obj, (Exception, type)):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: _make_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_make_serializable(item) for item in obj]
    else:
        return obj


async def http_exception_handler(request: Request, exc):
    """Handle HTTP exceptions."""
    # Extract error details from exception
    error_code = "http_error"
    message = str(exc.detail)
    details = None

    # Safely handle dict detail
    if isinstance(exc.detail, dict):
        error_code = exc.detail.get("error", "http_error")
        msg_val = exc.detail.get("message", exc.detail)
        # Convert to string if needed
        if not isinstance(msg_val, str):
            try:
                message = str(msg_val)
            except Exception:
                message = "Validation error"
        else:
            message = msg_val
        details = exc.detail.get("details")

    # Include both custom format and FastAPI's default 'detail' field for compatibility
    error_response = ErrorResponse(
        error=error_code,
        error_code=error_code.upper(),
        message=message,
        details=details,
        timestamp=int(datetime.now().timestamp()),
    ).model_dump()
    # Add 'detail' field for backward compatibility with FastAPI's default format
    error_response["detail"] = message
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response,
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.exception(f"Unhandled exception: {exc}")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="internal_server_error",
            error_code="INTERNAL_SERVER_ERROR",
            message="An internal server error occurred",
            details=None,
            timestamp=int(datetime.now().timestamp()),
        ).model_dump(),
    )
