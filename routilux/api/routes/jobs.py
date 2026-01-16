"""
Job management API routes.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from routilux.api.middleware.auth import RequireAuth
from routilux.api.models.job import JobListResponse, JobResponse, JobStartRequest
from routilux.api.validators import validate_flow_exists, validate_routine_exists
from routilux.job_state import JobState
from routilux.monitoring.flow_registry import FlowRegistry
from routilux.monitoring.storage import flow_store, job_store
from routilux.runtime import Runtime
from routilux.status import ExecutionStatus

logger = logging.getLogger(__name__)

router = APIRouter()


def _job_to_response(job_state: JobState) -> JobResponse:
    """Convert JobState to response model."""
    # Extract error from job_state.error or execution history
    error = None
    if hasattr(job_state, "error") and job_state.error:
        error = job_state.error
    elif job_state.status in (ExecutionStatus.FAILED, ExecutionStatus.CANCELLED):
        # Try to extract from execution history
        for record in reversed(job_state.execution_history):
            if hasattr(record, "error") and record.error:
                error = record.error
                break
        # Fall back to shared_data
        if not error:
            error = job_state.shared_data.get("error")

    return JobResponse(
        job_id=job_state.job_id,
        flow_id=job_state.flow_id,
        status=job_state.status.value
        if hasattr(job_state.status, "value")
        else str(job_state.status),
        created_at=int(datetime.now().timestamp()),
        started_at=getattr(job_state, "started_at", None),
        completed_at=getattr(job_state, "completed_at", None),
        error=error,
    )


@router.post("/jobs", response_model=JobResponse, status_code=201, dependencies=[RequireAuth])
async def start_job(request: JobStartRequest):
    """Start a new job from a flow.

    This endpoint immediately returns a job_id and executes the flow asynchronously
    in the background. Use the job status endpoint to check execution progress.
    """
    # Validate flow exists
    flow = validate_flow_exists(request.flow_id)
    # Validate entry routine exists
    validate_routine_exists(flow, request.entry_routine_id)

    # Create job state immediately (before execution)
    job_state = JobState(flow.flow_id)

    # Store job immediately so it can be queried
    job_store.add(job_state)

    # Ensure flow is registered in FlowRegistry (required for Runtime)
    flow_registry = FlowRegistry.get_instance()
    if not flow_registry.get(flow.flow_id) and not flow_registry.get_by_name(flow.flow_id):
        # Register by both ID and name for flexibility
        flow_registry.register(flow.flow_id, flow)
        if hasattr(flow, "name") and flow.name:
            flow_registry.register_by_name(flow.name, flow)

    # Get or create Runtime instance
    # For API, we use a module-level Runtime instance for efficiency
    # This allows sharing thread pool across requests
    if not hasattr(start_job, "_runtime"):
        start_job._runtime = Runtime(thread_pool_size=10)

    runtime = start_job._runtime

    # Start flow execution asynchronously using Runtime.exec()
    # This returns immediately without blocking
    try:
        # Store entry_params in job_state for later use by entry routine
        if request.entry_params:
            job_state.shared_data["entry_params"] = request.entry_params
            job_state.shared_data["entry_routine_id"] = request.entry_routine_id

        # Execute via Runtime
        started_job_state = runtime.exec(
            flow_name=flow.flow_id,  # Use flow_id as flow_name
            job_state=job_state,
        )

        # Update stored job with the started state
        job_store.add(started_job_state)

        return _job_to_response(started_job_state)
    except Exception as e:
        # If exec() fails, mark job as failed
        job_state.status = ExecutionStatus.FAILED
        job_state.shared_data["error"] = str(e)
        job_store.add(job_state)
        raise HTTPException(status_code=400, detail=f"Failed to start job: {str(e)}") from e


@router.get(
    "/jobs",
    response_model=JobListResponse,
    summary="List all jobs",
    description="Retrieve a paginated list of jobs with optional filters",
    dependencies=[RequireAuth],
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


@router.get("/jobs/{job_id}", response_model=JobResponse, dependencies=[RequireAuth])
async def get_job(job_id: str):
    """Get job details."""
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return _job_to_response(job_state)


@router.post("/jobs/{job_id}/pause", status_code=200, dependencies=[RequireAuth])
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


@router.post("/jobs/{job_id}/resume", status_code=200, dependencies=[RequireAuth])
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


@router.post("/jobs/{job_id}/cancel", status_code=200, dependencies=[RequireAuth])
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


@router.get("/jobs/{job_id}/state", dependencies=[RequireAuth])
async def get_job_state(job_id: str):
    """Get full job state."""
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    # Serialize job state
    return job_state.serialize()


@router.post("/jobs/cleanup", dependencies=[RequireAuth])
async def cleanup_jobs(
    max_age_hours: int = Query(24, ge=1, le=720, description="Maximum age in hours"),
    status: Optional[List[str]] = Query(None, description="Status filter"),
):
    """Clean up old jobs.

    Removes jobs older than specified age, optionally filtered by status.

    Args:
        max_age_hours: Maximum age in hours (1-720, default: 24).
        status: Optional list of statuses to clean up.

    Returns:
        Number of jobs removed.
    """
    max_age_seconds = max_age_hours * 3600
    removed_count = job_store.cleanup_old_jobs(
        max_age_seconds=max_age_seconds,
        status_filter=status,
    )

    return {
        "removed_count": removed_count,
        "max_age_hours": max_age_hours,
        "status_filter": status,
    }
