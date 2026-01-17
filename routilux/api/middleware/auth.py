"""
Authentication middleware for API.

Provides API key authentication using FastAPI dependencies.

All-or-nothing: when ROUTILUX_API_KEY_ENABLED=true, every endpoint (REST and
WebSocket) requires a valid X-API-Key; when false, all are public. No mixed mode.
"""

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from routilux.api.config import get_config

# API Key header name (OpenAPI: X-API-Key, In: header)
API_KEY_HEADER = "X-API-Key"

# Security scheme
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """Verify API key from request header.

    When api_key_enabled is False: allows all (returns 'anonymous').
    When True: requires valid X-API-Key; 401 if missing, 403 if invalid.

    Args:
        api_key: API key from request header.

    Returns:
        API key if valid, or 'anonymous' when auth is disabled.

    Raises:
        HTTPException: If API key is invalid or missing when auth is enabled.
    """
    config = get_config()

    # Auth disabled: allow all requests (all-or-nothing: 全部放开)
    if not config.api_key_enabled:
        return api_key or "anonymous"

    # Check if API key is provided
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "authentication_required",
                "message": "API key is required. Provide it in the X-API-Key header.",
            },
        )

    # Validate API key
    if not config.is_api_key_valid(api_key):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "invalid_api_key",
                "message": "Invalid API key provided.",
            },
        )

    return api_key


# Dependency for endpoints that require authentication
RequireAuth = Depends(verify_api_key)
