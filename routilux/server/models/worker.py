"""
Pydantic models for Worker API.

Workers are long-running execution instances of Flows.
One Worker can process multiple Jobs.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class WorkerCreateRequest(BaseModel):
    """Request to create a new Worker.

    A Worker is a long-running execution instance of a Flow.
    """

    flow_id: str = Field(..., description="Flow ID to instantiate as a Worker")
    worker_id: Optional[str] = Field(
        None, description="Optional custom worker ID. Auto-generated if not provided."
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"flow_id": "data_processing_flow"},
                {"flow_id": "data_processing_flow", "worker_id": "worker-prod-001"},
            ]
        }
    }


class WorkerResponse(BaseModel):
    """Worker details response."""

    worker_id: str = Field(..., description="Unique Worker identifier")
    flow_id: str = Field(..., description="Flow this Worker is executing")
    status: str = Field(
        ..., description="Current status: pending|running|idle|paused|completed|failed|cancelled"
    )
    created_at: Optional[int] = Field(None, description="Unix timestamp of creation")
    started_at: Optional[int] = Field(None, description="Unix timestamp of start")
    jobs_processed: int = Field(0, description="Number of jobs successfully processed")
    jobs_failed: int = Field(0, description="Number of jobs that failed")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "worker_id": "worker-prod-001",
                    "flow_id": "data_processing_flow",
                    "status": "running",
                    "created_at": 1705312800,
                    "started_at": 1705312801,
                    "jobs_processed": 42,
                    "jobs_failed": 2,
                }
            ]
        }
    }


class WorkerListResponse(BaseModel):
    """Paginated list of Workers."""

    workers: List[WorkerResponse] = Field(..., description="List of workers")
    total: int = Field(..., description="Total number of workers matching filters")
    limit: int = Field(100, description="Maximum workers per page", ge=1, le=1000)
    offset: int = Field(0, description="Number of workers skipped", ge=0)
