"""
Global exception handlers for API.

Provides standardized error responses for all exceptions.
"""

import logging
from datetime import datetime

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from routilux.api.models.error import ErrorResponse

logger = logging.getLogger(__name__)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error="validation_error",
            error_code="VALIDATION_ERROR",
            message="Request validation failed",
            details={"errors": exc.errors()},
            timestamp=datetime.now(),
        ).dict(),
    )


async def http_exception_handler(request: Request, exc):
    """Handle HTTP exceptions."""
    # Extract error details from exception
    if isinstance(exc.detail, dict):
        error_code = exc.detail.get("error", "http_error")
        message = exc.detail.get("message", str(exc.detail))
        details = exc.detail.get("details")
    else:
        error_code = "http_error"
        message = str(exc.detail)
        details = None
    
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=error_code,
            error_code=error_code.upper(),
            message=message,
            details=details,
            timestamp=datetime.now(),
        ).dict(),
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
            timestamp=datetime.now(),
        ).dict(),
    )
