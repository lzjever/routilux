"""
Pydantic models for Job API.

Jobs are single tasks/requests processed by Workers.
Each Job tracks one execution path through the workflow.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class JobSubmitRequest(BaseModel):
    """Request to submit a Job to a Worker.
    
    A Job is a single task/request that flows through the workflow.
    If worker_id is not provided, a new Worker is created automatically.
    """
    
    flow_id: str = Field(
        ...,
        description="Flow ID (used to find or create Worker)"
    )
    worker_id: Optional[str] = Field(
        None,
        description="Target Worker ID. If None, creates new Worker."
    )
    routine_id: str = Field(
        ...,
        description="Target routine to receive data"
    )
    slot_name: str = Field(
        ...,
        description="Target slot on the routine"
    )
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Data to send to the slot"
    )
    job_id: Optional[str] = Field(
        None,
        description="Optional custom job ID. Auto-generated if not provided."
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Job metadata (user_id, source, trace_id, etc.)"
    )
    idempotency_key: Optional[str] = Field(
        None,
        description="Idempotency key to prevent duplicate submissions"
    )
    
    @field_validator("data")
    @classmethod
    def validate_data_size(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate data payload size."""
        try:
            size = len(json.dumps(v))
            MAX_SIZE = 10 * 1024 * 1024  # 10MB limit
            if size > MAX_SIZE:
                raise ValueError(
                    f"Data payload exceeds {MAX_SIZE / 1024 / 1024}MB limit "
                    f"(current size: {size / 1024 / 1024:.2f}MB)"
                )
        except (TypeError, ValueError) as e:
            if "exceeds" in str(e):
                raise
            # If JSON serialization fails, it's likely invalid data
            raise ValueError(f"Invalid data format: {str(e)}")
        return v
    
    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Validate metadata size and structure."""
        if v is None:
            return v
        try:
            size = len(json.dumps(v))
            MAX_SIZE = 1024 * 1024  # 1MB limit for metadata
            if size > MAX_SIZE:
                raise ValueError(
                    f"Metadata exceeds {MAX_SIZE / 1024}KB limit "
                    f"(current size: {size / 1024:.2f}KB)"
                )
        except (TypeError, ValueError) as e:
            if "exceeds" in str(e):
                raise
            raise ValueError(f"Invalid metadata format: {str(e)}")
        return v
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "flow_id": "data_processing_flow",
                    "routine_id": "data_source",
                    "slot_name": "input",
                    "data": {"value": 42, "type": "integer"}
                },
                {
                    "flow_id": "data_processing_flow",
                    "worker_id": "worker-prod-001",
                    "routine_id": "data_source",
                    "slot_name": "input",
                    "data": {"value": 42},
                    "metadata": {"user_id": "user-123", "source": "api"}
                }
            ]
        }
    }


class JobResponse(BaseModel):
    """Job details response.
    
    Contains information about a single Job's execution state.
    """
    
    job_id: str = Field(
        ..., 
        description="Unique Job identifier"
    )
    worker_id: str = Field(
        ..., 
        description="Worker processing this Job"
    )
    flow_id: str = Field(
        ..., 
        description="Flow being executed"
    )
    status: str = Field(
        ..., 
        description="Current status: pending|running|completed|failed"
    )
    created_at: Optional[int] = Field(
        None, 
        description="Unix timestamp of creation"
    )
    started_at: Optional[int] = Field(
        None, 
        description="Unix timestamp of start"
    )
    completed_at: Optional[int] = Field(
        None, 
        description="Unix timestamp of completion"
    )
    error: Optional[str] = Field(
        None, 
        description="Error message if failed"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, 
        description="Job metadata"
    )
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "job_id": "job-abc-123",
                    "worker_id": "worker-prod-001",
                    "flow_id": "data_processing_flow",
                    "status": "completed",
                    "created_at": 1705312800,
                    "started_at": 1705312801,
                    "completed_at": 1705312900,
                    "error": None,
                    "metadata": {"user_id": "user-123"}
                }
            ]
        }
    }


class JobListResponse(BaseModel):
    """Paginated list of Jobs."""
    
    jobs: List[JobResponse] = Field(
        ...,
        description="List of jobs"
    )
    total: int = Field(
        ...,
        description="Total number of jobs matching filters"
    )
    limit: int = Field(
        100,
        description="Maximum jobs per page",
        ge=1,
        le=1000
    )
    offset: int = Field(
        0,
        description="Number of jobs skipped",
        ge=0
    )


class JobOutputResponse(BaseModel):
    """Job stdout output response."""
    
    job_id: str = Field(
        ...,
        description="Job identifier"
    )
    output: str = Field(
        ..., 
        description="Captured stdout output"
    )
    is_complete: bool = Field(
        ..., 
        description="Whether job has completed"
    )
    truncated: bool = Field(
        False, 
        description="Whether output was truncated"
    )


class JobTraceResponse(BaseModel):
    """Job execution trace response."""
    
    job_id: str = Field(
        ...,
        description="Job identifier"
    )
    trace_log: List[Dict[str, Any]] = Field(
        ..., 
        description="Execution trace entries"
    )
    total_entries: int = Field(
        ...,
        description="Total number of trace entries"
    )


class JobFailRequest(BaseModel):
    """Request to mark a Job as failed."""
    
    error: str = Field(
        ..., 
        description="Error message"
    )


# Legacy models for backward compatibility (deprecated)

class JobStartRequest(BaseModel):
    """DEPRECATED: Use JobSubmitRequest instead.
    
    This model is kept for backward compatibility but will be removed.
    """
    
    flow_id: str = Field(
        ...,
        description="Flow ID to execute (DEPRECATED: use JobSubmitRequest)"
    )
    runtime_id: Optional[str] = Field(
        None,
        description="Runtime ID (DEPRECATED)"
    )
    timeout: Optional[float] = Field(
        None,
        description="Timeout in seconds (DEPRECATED)",
        ge=0.0,
        le=86400.0,
    )
    
    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if v < 0:
                raise ValueError("timeout must be non-negative")
            if v > 86400:
                raise ValueError("timeout must be <= 86400 seconds (24 hours)")
        return v


class PostToJobRequest(BaseModel):
    """DEPRECATED: Use JobSubmitRequest instead.
    
    This model is kept for backward compatibility but will be removed.
    """
    
    routine_id: str = Field(
        ...,
        description="Routine ID (DEPRECATED: use JobSubmitRequest)"
    )
    slot_name: str = Field(
        ...,
        description="Slot name (DEPRECATED: use JobSubmitRequest)"
    )
    data: Optional[Dict[str, Any]] = Field(
        None,
        description="Data to send (DEPRECATED: use JobSubmitRequest)"
    )
