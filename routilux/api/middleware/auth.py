"""
Authentication middleware for API.

Provides API key authentication using FastAPI dependencies.
"""

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from routilux.api.config import get_config

# API Key header name
API_KEY_HEADER = "X-API-Key"

# Security scheme
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """Verify API key from request header.
    
    Args:
        api_key: API key from request header.
        
    Returns:
        API key if valid.
        
    Raises:
        HTTPException: If API key is invalid or missing.
    """
    config = get_config()
    
    # If authentication is disabled, allow all requests
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
