"""
Rate limiting middleware for API.

Uses slowapi to implement rate limiting per IP address.
"""

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from fastapi import Request
from fastapi.responses import JSONResponse

from routilux.api.config import get_config

# Create limiter instance
limiter = Limiter(key_func=get_remote_address)


def setup_rate_limiting(app):
    """Setup rate limiting for FastAPI app.
    
    Args:
        app: FastAPI application instance.
    """
    config = get_config()
    
    if not config.rate_limit_enabled:
        return  # Rate limiting disabled
    
    # Add rate limit exception handler
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def get_rate_limit():
    """Get rate limit string from config.
    
    Returns:
        Rate limit string (e.g., "60/minute").
    """
    config = get_config()
    return f"{config.rate_limit_per_minute}/minute"
