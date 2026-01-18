"""
Pydantic models for one-shot execution API.

The execute endpoint provides a simple way to run a flow
with optional waiting for completion.
"""

import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, field_validator


class ExecuteRequest(BaseModel):
    """One-shot execution request.

    This endpoint creates a Worker, submits a Job, and optionally
    waits for completion before returning.
    """

    flow_id: str = Field(..., description="Flow to execute")
    routine_id: str = Field(..., description="Initial routine to trigger")
    slot_name: str = Field(..., description="Initial slot to send data")
    data: Dict[str, Any] = Field(default_factory=dict, description="Initial data to send")

    wait: bool = Field(False, description="If true, wait for job completion before returning")
    timeout: float = Field(
        60.0, ge=1.0, le=3600.0, description="Timeout in seconds (only used if wait=true)"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Job metadata (user_id, source, etc.)"
    )
    idempotency_key: Optional[str] = Field(
        None, description="Idempotency key to prevent duplicate executions"
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
            raise ValueError(f"Invalid data format: {str(e)}")
        return v

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Validate metadata size."""
        if v is None:
            return v
        try:
            size = len(json.dumps(v))
            MAX_SIZE = 1024 * 1024  # 1MB limit
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
                    "data": {"value": 42},
                    "wait": False,
                },
                {
                    "flow_id": "data_processing_flow",
                    "routine_id": "data_source",
                    "slot_name": "input",
                    "data": {"value": 42},
                    "wait": True,
                    "timeout": 30.0,
                },
            ]
        }
    }


class ExecuteResponse(BaseModel):
    """One-shot execution response."""

    job_id: str = Field(..., description="Job identifier")
    worker_id: str = Field(..., description="Worker identifier")
    status: str = Field(..., description="Job status")
    output: Optional[str] = Field(None, description="Captured stdout output (only if wait=true)")
    result: Optional[Dict[str, Any]] = Field(
        None, description="Job result data (only if wait=true and completed)"
    )
    error: Optional[str] = Field(None, description="Error message (only if wait=true and failed)")
    elapsed_seconds: Optional[float] = Field(None, description="Execution time (only if wait=true)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"job_id": "job-abc-123", "worker_id": "worker-xyz-789", "status": "running"},
                {
                    "job_id": "job-abc-123",
                    "worker_id": "worker-xyz-789",
                    "status": "completed",
                    "output": "Processing complete\n",
                    "result": {"count": 10},
                    "elapsed_seconds": 2.5,
                },
            ]
        }
    }
