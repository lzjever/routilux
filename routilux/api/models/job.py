"""
Pydantic models for Job API.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator


class JobStartRequest(BaseModel):
    """Request model for starting a job."""

    flow_id: str
    entry_routine_id: str
    entry_params: Optional[Dict[str, Any]] = None
    timeout: Optional[float] = None

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: Optional[float]) -> Optional[float]:
        """Validate timeout parameter.

        Args:
            v: Timeout value in seconds.

        Returns:
            Validated timeout value.

        Raises:
            ValueError: If timeout is negative or too large.
        """
        if v is not None:
            # MEDIUM fix: Add timeout validation
            if v < 0:
                raise ValueError(f"timeout must be non-negative, got {v}")
            if v > 86400:  # 24 hours
                raise ValueError(f"timeout must be <= 86400 seconds (24 hours), got {v}")
        return v


class JobResponse(BaseModel):
    """Response model for job details."""

    job_id: str
    flow_id: str
    status: str
    created_at: int
    started_at: Optional[int] = None
    completed_at: Optional[int] = None
    error: Optional[str] = None


class JobListResponse(BaseModel):
    """Response model for job list with pagination support."""

    jobs: List[JobResponse]
    total: int
    limit: int = 100
    offset: int = 0
