"""
Job management API routes.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from routilux.api.models.job import JobListResponse, JobResponse, JobStartRequest
from routilux.job_state import JobState
from routilux.monitoring.registry import MonitoringRegistry
from routilux.monitoring.storage import flow_store, job_store
from routilux.status import ExecutionStatus

logger = logging.getLogger(__name__)

router = APIRouter()


def _job_to_response(job_state: JobState) -> JobResponse:
    """Convert JobState to response model."""
    return JobResponse(
        job_id=job_state.job_id,
        flow_id=job_state.flow_id,
        status=job_state.status.value
        if hasattr(job_state.status, "value")
        else str(job_state.status),
        created_at=datetime.now(),  # JobState doesn't track creation time
        started_at=None,  # Would need to track this
        completed_at=None,  # Would need to track this
        error=None,  # Would need to extract from execution history
    )


@router.post("/jobs", response_model=JobResponse, status_code=201)
async def start_job(request: JobStartRequest):
    """Start a new job from a flow.
    
    This endpoint immediately returns a job_id and executes the flow asynchronously
    in the background. Use the job status endpoint to check execution progress.
    """
    # Get flow
    flow = flow_store.get(request.flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{request.flow_id}' not found")

    # Enable monitoring if not already enabled
    MonitoringRegistry.enable()

    # Create job state immediately (before execution)
    job_state = JobState(flow.flow_id)
    
    # Store job immediately so it can be queried
    job_store.add(job_state)
    
    # Start flow execution asynchronously using the new start() method
    # This returns immediately without blocking
    try:
        started_job_state = flow.start(
            entry_routine_id=request.entry_routine_id,
            entry_params=request.entry_params,
            timeout=request.timeout,
            job_state=job_state,  # Use our pre-created job_state
        )
        
        # Update stored job with the started state
        job_store.add(started_job_state)
        
        return _job_to_response(started_job_state)
    except Exception as e:
        # If start() fails, mark job as failed
        job_state.status = ExecutionStatus.FAILED
        job_state.shared_data["error"] = str(e)
        job_store.add(job_state)
        raise HTTPException(status_code=400, detail=f"Failed to start job: {str(e)}") from e


@router.get(
    "/jobs",
    response_model=JobListResponse,
    summary="List all jobs",
    description="Retrieve a paginated list of jobs with optional filters",
)
async def list_jobs(
    flow_id: Optional[str] = Query(None, description="Filter by flow ID"),
    status: Optional[str] = Query(None, description="Filter by job status"),
    limit: int = Query(100, ge=1, le=1000, description="Number of jobs per page"),
    offset: int = Query(0, ge=0, description="Number of jobs to skip"),
):
    """List jobs with optional filters and pagination.

    Returns a paginated list of jobs that match the specified criteria.
    The response includes total count for pagination controls.

    Args:
        flow_id: Filter jobs by flow ID
        status: Filter jobs by status (pending, running, completed, failed, paused, cancelled)
        limit: Maximum number of jobs to return (1-1000, default 100)
        offset: Number of jobs to skip for pagination (default 0)

    Returns:
        JobListResponse: Paginated list of jobs with total count
    """
    all_jobs = job_store.list_all()

    # Apply filters
    filtered_jobs = all_jobs
    if flow_id:
        filtered_jobs = [j for j in filtered_jobs if j.flow_id == flow_id]
    if status:
        filtered_jobs = [
            j
            for j in filtered_jobs
            if (j.status.value == status if hasattr(j.status, "value") else str(j.status) == status)
        ]

    # Get total before pagination
    total = len(filtered_jobs)

    # Apply pagination
    jobs = filtered_jobs[offset : offset + limit]

    return JobListResponse(
        jobs=[_job_to_response(job) for job in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """Get job details."""
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return _job_to_response(job_state)


@router.post("/jobs/{job_id}/pause", status_code=200)
async def pause_job(job_id: str):
    """Pause job execution."""
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    flow = flow_store.get(job_state.flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{job_state.flow_id}' not found")

    try:
        flow.pause(job_state, reason="Paused via API")
        return {"status": "paused", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to pause job: {str(e)}") from e


@router.post("/jobs/{job_id}/resume", status_code=200)
async def resume_job(job_id: str):
    """Resume job execution."""
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    flow = flow_store.get(job_state.flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{job_state.flow_id}' not found")

    try:
        job_state = flow.resume(job_state)
        job_store.add(job_state)  # Update stored job
        return {"status": "resumed", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to resume job: {str(e)}") from e


@router.post("/jobs/{job_id}/cancel", status_code=200)
async def cancel_job(job_id: str):
    """Cancel job execution."""
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    flow = flow_store.get(job_state.flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{job_state.flow_id}' not found")

    try:
        flow.cancel(job_state, reason="Cancelled via API")
        return {"status": "cancelled", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to cancel job: {str(e)}") from e


@router.get("/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    """Get job status."""
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    return {
        "job_id": job_id,
        "status": job_state.status.value
        if hasattr(job_state.status, "value")
        else str(job_state.status),
        "flow_id": job_state.flow_id,
    }


@router.get("/jobs/{job_id}/state")
async def get_job_state(job_id: str):
    """Get full job state."""
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    # Serialize job state
    return job_state.serialize()
