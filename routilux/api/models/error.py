"""
Standardized error response models.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standardized error response format."""
    
    error: str
    error_code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = datetime.now()
    request_id: Optional[str] = None
