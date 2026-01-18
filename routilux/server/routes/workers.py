"""
Worker management API routes.

Workers are long-running execution instances of Flows.
One Worker can process multiple Jobs.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from routilux.server.errors import ErrorCode, create_error_response
from routilux.server.middleware.auth import RequireAuth
from routilux.server.models.worker import (
    WorkerCreateRequest,
    WorkerListResponse,
    WorkerResponse,
)
from routilux.server.models.job import JobListResponse, JobResponse
from routilux.server.dependencies import (
    get_runtime,
    get_flow_registry,
    get_worker_registry,
    get_job_storage,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _dt_to_int(dt: Optional[datetime]) -> Optional[int]:
    """Convert datetime to Unix timestamp."""
    if dt is None:
        return None
    return int(dt.timestamp())


def _worker_to_response(worker_state) -> WorkerResponse:
    """Convert WorkerState to API response."""
    return WorkerResponse(
        worker_id=worker_state.worker_id,
        flow_id=worker_state.flow_id,
        status=worker_state.status.value if hasattr(worker_state.status, "value") else str(worker_state.status),
        created_at=_dt_to_int(getattr(worker_state, "created_at", None)),
        started_at=_dt_to_int(getattr(worker_state, "started_at", None)),
        jobs_processed=getattr(worker_state, "jobs_processed", 0),
        jobs_failed=getattr(worker_state, "jobs_failed", 0),
    )


def _job_to_response(job_context, flow_id: str = "") -> JobResponse:
    """Convert JobContext to API response."""
    return JobResponse(
        job_id=job_context.job_id,
        worker_id=job_context.worker_id,
        flow_id=flow_id,
        status=job_context.status,
        created_at=_dt_to_int(getattr(job_context, "created_at", None)),
        started_at=_dt_to_int(getattr(job_context, "created_at", None)) if job_context.status != "pending" else None,
        completed_at=_dt_to_int(getattr(job_context, "completed_at", None)),
        error=job_context.error,
        metadata=job_context.metadata,
    )


@router.post("/workers", response_model=WorkerResponse, status_code=201, dependencies=[RequireAuth])
async def create_worker(request: WorkerCreateRequest):
    """
    Create and start a new Worker for a Flow.
    
    A Worker is a long-running execution instance that can process multiple Jobs.
    Use this when you need persistent processing capacity for a Flow.
    """
    runtime = get_runtime()
    flow_registry = get_flow_registry()
    
    # Validate flow exists
    flow = flow_registry.get_by_name(request.flow_id)
    if flow is None:
        flow = flow_registry.get(request.flow_id)
    if flow is None:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(
                ErrorCode.FLOW_NOT_FOUND,
                f"Flow '{request.flow_id}' not found"
            )
        )
    
    try:
        # Create worker via Runtime.exec()
        # Note: Runtime.exec() doesn't support custom worker_id yet
        # If request.worker_id is provided, we could validate it doesn't exist
        worker_state = runtime.exec(flow_name=request.flow_id)
        
        logger.info(f"Created worker {worker_state.worker_id} for flow {request.flow_id}")
        return _worker_to_response(worker_state)
        
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.FLOW_NOT_FOUND, str(e))
        )
    except Exception as e:
        logger.exception(f"Failed to create worker: {e}")
        raise HTTPException(
            status_code=500,
            detail=create_error_response(
                ErrorCode.INTERNAL_ERROR,
                f"Failed to create worker: {str(e)}"
            )
        )


@router.get("/workers", response_model=WorkerListResponse, dependencies=[RequireAuth])
async def list_workers(
    flow_id: Optional[str] = Query(None, description="Filter by flow ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum workers to return"),
    offset: int = Query(0, ge=0, description="Number of workers to skip"),
):
    """
    List all Workers with optional filters.
    
    Returns Workers from the Runtime's active workers list.
    """
    runtime = get_runtime()
    
    # Get all active workers from Runtime
    with runtime._worker_lock:
        all_workers = list(runtime._active_workers.values())
    
    # Also check WorkerRegistry for workers not in active list
    worker_registry = get_worker_registry()
    for worker in worker_registry.list_all():
        if worker.worker_id not in [w.worker_id for w in all_workers]:
            all_workers.append(worker)
    
    # Apply filters
    if flow_id:
        all_workers = [w for w in all_workers if w.flow_id == flow_id]
    if status:
        all_workers = [
            w for w in all_workers 
            if (w.status.value if hasattr(w.status, "value") else str(w.status)) == status
        ]
    
    total = len(all_workers)
    workers = all_workers[offset:offset + limit]
    
    return WorkerListResponse(
        workers=[_worker_to_response(w) for w in workers],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/workers/{worker_id}", response_model=WorkerResponse, dependencies=[RequireAuth])
async def get_worker(worker_id: str):
    """
    Get Worker details by ID.
    """
    runtime = get_runtime()
    worker_registry = get_worker_registry()
    
    # Check active workers first
    with runtime._worker_lock:
        worker_state = runtime._active_workers.get(worker_id)
    
    # Fall back to registry
    if worker_state is None:
        worker_state = worker_registry.get(worker_id)
    
    if worker_state is None:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(
                ErrorCode.WORKER_NOT_FOUND,
                f"Worker '{worker_id}' not found"
            )
        )
    
    return _worker_to_response(worker_state)


@router.delete("/workers/{worker_id}", status_code=204, dependencies=[RequireAuth])
async def stop_worker(worker_id: str):
    """
    Stop and remove a Worker.
    
    This stops the Worker's execution and removes it from the active list.
    Jobs in progress may be interrupted.
    """
    runtime = get_runtime()
    
    with runtime._worker_lock:
        worker_state = runtime._active_workers.get(worker_id)
    
    if worker_state is None:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(
                ErrorCode.WORKER_NOT_FOUND,
                f"Worker '{worker_id}' not found"
            )
        )
    
    # Get executor and stop it
    executor = getattr(worker_state, "_executor", None)
    if executor:
        try:
            executor.stop(status="completed")
        except Exception as e:
            logger.warning(f"Error stopping executor for worker {worker_id}: {e}")
    
    # Remove from active workers
    with runtime._worker_lock:
        runtime._active_workers.pop(worker_id, None)
    
    # Also remove from jobs tracking
    with runtime._jobs_lock:
        runtime._active_jobs.pop(worker_id, None)
    
    logger.info(f"Stopped worker {worker_id}")
    return None


@router.post("/workers/{worker_id}/pause", response_model=WorkerResponse, dependencies=[RequireAuth])
async def pause_worker(worker_id: str):
    """
    Pause a running Worker.
    
    Paused workers can receive new jobs but won't process them until resumed.
    """
    from routilux.core.status import ExecutionStatus
    
    runtime = get_runtime()
    
    with runtime._worker_lock:
        worker_state = runtime._active_workers.get(worker_id)
    
    if worker_state is None:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(
                ErrorCode.WORKER_NOT_FOUND,
                f"Worker '{worker_id}' not found"
            )
        )
    
    # Validate worker state
    status_value = worker_state.status.value if hasattr(worker_state.status, "value") else str(worker_state.status)
    
    if status_value == "paused":
        raise HTTPException(
            status_code=400,
            detail=create_error_response(
                ErrorCode.WORKER_NOT_RUNNING,
                f"Worker '{worker_id}' is already paused"
            )
        )
    
    if status_value in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=create_error_response(
                ErrorCode.WORKER_ALREADY_COMPLETED,
                f"Worker '{worker_id}' is in terminal state: {status_value}"
            )
        )
    
    executor = getattr(worker_state, "_executor", None)
    if executor is None:
        raise HTTPException(
            status_code=400,
            detail=create_error_response(
                ErrorCode.WORKER_NOT_RUNNING,
                f"Worker '{worker_id}' has no executor"
            )
        )
    
    try:
        executor.pause()
        logger.info(f"Paused worker {worker_id}")
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=create_error_response(
                ErrorCode.INTERNAL_ERROR,
                f"Failed to pause worker: {str(e)}"
            )
        )
    
    # Refresh state
    with runtime._worker_lock:
        worker_state = runtime._active_workers.get(worker_id)
    
    return _worker_to_response(worker_state)


@router.post("/workers/{worker_id}/resume", response_model=WorkerResponse, dependencies=[RequireAuth])
async def resume_worker(worker_id: str):
    """
    Resume a paused Worker.
    
    Queued jobs will be processed after resuming.
    """
    from routilux.core.status import ExecutionStatus
    
    runtime = get_runtime()
    
    with runtime._worker_lock:
        worker_state = runtime._active_workers.get(worker_id)
    
    if worker_state is None:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(
                ErrorCode.WORKER_NOT_FOUND,
                f"Worker '{worker_id}' not found"
            )
        )
    
    # Validate worker state
    status_value = worker_state.status.value if hasattr(worker_state.status, "value") else str(worker_state.status)
    
    if status_value != "paused":
        if status_value in ("completed", "failed", "cancelled"):
            raise HTTPException(
                status_code=400,
                detail=create_error_response(
                    ErrorCode.WORKER_ALREADY_COMPLETED,
                    f"Worker '{worker_id}' is in terminal state: {status_value}"
                )
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=create_error_response(
                    ErrorCode.WORKER_NOT_RUNNING,
                    f"Worker '{worker_id}' is not paused (current status: {status_value})"
                )
            )
    
    executor = getattr(worker_state, "_executor", None)
    if executor is None:
        raise HTTPException(
            status_code=400,
            detail=create_error_response(
                ErrorCode.WORKER_NOT_RUNNING,
                f"Worker '{worker_id}' has no executor"
            )
        )
    
    try:
        executor.resume()
        logger.info(f"Resumed worker {worker_id}")
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=create_error_response(
                ErrorCode.INTERNAL_ERROR,
                f"Failed to resume worker: {str(e)}"
            )
        )
    
    # Refresh state
    with runtime._worker_lock:
        worker_state = runtime._active_workers.get(worker_id)
    
    return _worker_to_response(worker_state)


@router.get("/workers/{worker_id}/jobs", response_model=JobListResponse, dependencies=[RequireAuth])
async def list_worker_jobs(
    worker_id: str,
    status: Optional[str] = Query(None, description="Filter by job status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum jobs to return"),
    offset: int = Query(0, ge=0, description="Number of jobs to skip"),
):
    """
    List all Jobs for a specific Worker.
    """
    runtime = get_runtime()
    job_storage = get_job_storage()
    
    # Validate worker exists
    with runtime._worker_lock:
        worker_state = runtime._active_workers.get(worker_id)
    
    if worker_state is None:
        worker_registry = get_worker_registry()
        worker_state = worker_registry.get(worker_id)
    
    if worker_state is None:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(
                ErrorCode.WORKER_NOT_FOUND,
                f"Worker '{worker_id}' not found"
            )
        )
    
    # Get jobs for this worker
    all_jobs = runtime.list_jobs(worker_id=worker_id)
    
    # Also check storage
    storage_jobs = job_storage.list_jobs(worker_id=worker_id)
    for job in storage_jobs:
        if job.job_id not in [j.job_id for j in all_jobs]:
            all_jobs.append(job)
    
    # Apply status filter
    if status:
        all_jobs = [j for j in all_jobs if j.status == status]
    
    total = len(all_jobs)
    jobs = all_jobs[offset:offset + limit]
    
    return JobListResponse(
        jobs=[_job_to_response(j, flow_id=worker_state.flow_id) for j in jobs],
        total=total,
        limit=limit,
        offset=offset,
    )
