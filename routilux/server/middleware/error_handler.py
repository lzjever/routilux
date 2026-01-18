"""
Global exception handlers for API.

Provides standardized error responses for all exceptions.
"""

import logging

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from routilux.server.errors import ErrorCode, create_error_response

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
        content=create_error_response(
            ErrorCode.VALIDATION_ERROR,
            "Request validation failed",
            details={"errors": serializable_errors},
        ),
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
    # If detail is already a structured error dict (from create_error_response), use it
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        error_dict = exc.detail

        # Check if it's the new format (error.code, error.message)
        if isinstance(error_dict.get("error"), dict):
            return JSONResponse(
                status_code=exc.status_code,
                content=error_dict,
            )

        # Old format - convert to new format
        error_code = error_dict.get("error", "http_error")
        message = error_dict.get("message", str(exc.detail))
        details = error_dict.get("details")

        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_response(
                ErrorCode.INTERNAL_ERROR,
                message,
                details=details,
            ),
        )

    # Plain string detail
    message = str(exc.detail) if exc.detail else "An error occurred"

    # Map status codes to error codes
    error_code_map = {
        400: ErrorCode.VALIDATION_ERROR,
        401: ErrorCode.INTERNAL_ERROR,  # AUTH error not defined, use internal
        403: ErrorCode.INTERNAL_ERROR,
        404: ErrorCode.INTERNAL_ERROR,
        409: ErrorCode.INTERNAL_ERROR,
        500: ErrorCode.INTERNAL_ERROR,
        503: ErrorCode.RUNTIME_SHUTDOWN,
    }
    error_code = error_code_map.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

    return JSONResponse(
        status_code=exc.status_code,
        content=create_error_response(error_code, message),
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.exception(f"Unhandled exception: {exc}")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=create_error_response(
            ErrorCode.INTERNAL_ERROR,
            "An internal server error occurred",
        ),
    )
