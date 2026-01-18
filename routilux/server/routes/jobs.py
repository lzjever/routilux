"""
Job management API routes.

Jobs are single tasks/requests processed by Workers.
Each Job tracks one execution path through the workflow.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from routilux.core.context import JobContext
from routilux.monitoring.monitor_service import get_monitor_service
from routilux.monitoring.registry import MonitoringRegistry
from routilux.server.dependencies import (
    get_idempotency_backend,
    get_job_storage,
    get_runtime,
    get_worker_registry,
)
from routilux.server.errors import ErrorCode, create_error_response
from routilux.server.middleware.auth import RequireAuth
from routilux.server.models.job import (
    JobFailRequest,
    JobListResponse,
    JobOutputResponse,
    JobResponse,
    JobSubmitRequest,
    JobTraceResponse,
)
from routilux.server.models.monitor import (
    ExecutionEventResponse,
    ExecutionMetricsResponse,
    ExecutionTraceResponse,
    JobMonitoringData,
    RoutineExecutionStatus,
    RoutineMetricsResponse,
    SlotQueueStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _dt_to_int(dt: Optional[datetime]) -> Optional[int]:
    """Convert datetime to Unix timestamp."""
    if dt is None:
        return None
    return int(dt.timestamp())


def _job_to_response(job_context: JobContext, flow_id: str = "") -> JobResponse:
    """Convert JobContext to API response."""
    # Get flow_id from worker if not provided
    if not flow_id:
        try:
            worker_registry = get_worker_registry()
            worker = worker_registry.get(job_context.worker_id)
            if worker:
                flow_id = worker.flow_id
        except Exception:
            pass

    return JobResponse(
        job_id=job_context.job_id,
        worker_id=job_context.worker_id,
        flow_id=flow_id,
        status=job_context.status,
        created_at=_dt_to_int(getattr(job_context, "created_at", None)),
        started_at=_dt_to_int(getattr(job_context, "created_at", None))
        if job_context.status != "pending"
        else None,
        completed_at=_dt_to_int(getattr(job_context, "completed_at", None)),
        error=job_context.error,
        metadata=job_context.metadata,
    )


@router.post("/jobs", response_model=JobResponse, status_code=201, dependencies=[RequireAuth])
async def submit_job(request: JobSubmitRequest):
    """
    Submit a new Job to a Worker.

    If worker_id is not provided, a new Worker is created automatically.
    Each Job submission creates a new JobContext that tracks this specific task.

    **Example Request**:
    ```json
    {
      "flow_id": "data_processing_flow",
      "routine_id": "data_source",
      "slot_name": "input",
      "data": {"value": 42}
    }
    ```
    """
    runtime = get_runtime()
    job_storage = get_job_storage()
    idempotency = get_idempotency_backend()

    # Check idempotency key
    if request.idempotency_key:
        cached = idempotency.get(request.idempotency_key)
        if cached is not None:
            return JobResponse(**cached)

    try:
        # Submit via Runtime.post()
        worker_state, job_context = runtime.post(
            flow_name=request.flow_id,
            routine_name=request.routine_id,
            slot_name=request.slot_name,
            data=request.data,
            worker_id=request.worker_id,
            job_id=request.job_id,
            metadata=request.metadata,
        )

        # Store job for API access
        job_storage.save_job(job_context, flow_id=worker_state.flow_id)

        response = _job_to_response(job_context, flow_id=worker_state.flow_id)

        # Update idempotency cache
        if request.idempotency_key:
            idempotency.set(request.idempotency_key, response.model_dump(), ttl_seconds=86400)

        logger.info(f"Submitted job {job_context.job_id} to worker {worker_state.worker_id}")
        return response

    except ValueError as e:
        error_msg = str(e)
        if "Flow" in error_msg:
            error_code = ErrorCode.FLOW_NOT_FOUND
        elif "Routine" in error_msg:
            error_code = ErrorCode.ROUTINE_NOT_FOUND
        elif "Slot" in error_msg:
            error_code = ErrorCode.SLOT_NOT_FOUND
        elif "Worker" in error_msg:
            error_code = ErrorCode.WORKER_NOT_FOUND
        else:
            error_code = ErrorCode.JOB_SUBMISSION_FAILED

        raise HTTPException(status_code=404, detail=create_error_response(error_code, error_msg))
    except RuntimeError as e:
        if "shutdown" in str(e).lower():
            raise HTTPException(
                status_code=503, detail=create_error_response(ErrorCode.RUNTIME_SHUTDOWN, str(e))
            )
        raise HTTPException(
            status_code=400, detail=create_error_response(ErrorCode.JOB_SUBMISSION_FAILED, str(e))
        )


@router.get("/jobs", response_model=JobListResponse, dependencies=[RequireAuth])
async def list_jobs(
    worker_id: Optional[str] = Query(None, description="Filter by worker ID"),
    flow_id: Optional[str] = Query(None, description="Filter by flow ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum jobs to return"),
    offset: int = Query(0, ge=0, description="Number of jobs to skip"),
):
    """
    List all Jobs with optional filters.

    **Query Parameters**:
    - `worker_id`: Filter by specific worker
    - `flow_id`: Filter by flow being executed
    - `status`: Filter by job status (pending, running, completed, failed)
    - `limit`: Maximum results (1-1000, default 100)
    - `offset`: Skip first N results (for pagination)
    """
    job_storage = get_job_storage()

    all_jobs = job_storage.list_jobs(
        worker_id=worker_id,
        flow_id=flow_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    total = job_storage.count_jobs(
        worker_id=worker_id,
        flow_id=flow_id,
        status=status,
    )

    # Get flow_id for each job
    responses = []
    for job in all_jobs:
        flow = job_storage.get_flow_id(job.job_id) or ""
        responses.append(_job_to_response(job, flow_id=flow))

    return JobListResponse(
        jobs=responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/jobs/{job_id}", response_model=JobResponse, dependencies=[RequireAuth])
async def get_job(job_id: str):
    """
    Get Job details by ID.
    """
    runtime = get_runtime()
    job_storage = get_job_storage()

    # Check storage first
    job_context = job_storage.get_job(job_id)

    # Fall back to Runtime
    if job_context is None:
        job_context = runtime.get_job(job_id)

    if job_context is None:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, f"Job '{job_id}' not found"),
        )

    flow_id = job_storage.get_flow_id(job_id) or ""
    return _job_to_response(job_context, flow_id=flow_id)


@router.get("/jobs/{job_id}/output", response_model=JobOutputResponse, dependencies=[RequireAuth])
async def get_job_output(
    job_id: str,
    incremental: bool = Query(False, description="Return only new output since last call"),
):
    """
    Get captured stdout output for a Job.

    Use `incremental=true` to get only new output since the last call.
    """
    runtime = get_runtime()
    job_storage = get_job_storage()

    # Get job
    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)

    if job_context is None:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, f"Job '{job_id}' not found"),
        )

    # Get output from RoutedStdout
    try:
        from routilux.core.output import get_job_output as core_get_output

        output = core_get_output(job_id, incremental=incremental)
    except ImportError:
        output = ""
    except Exception as e:
        logger.warning(f"Failed to get output for job {job_id}: {e}")
        output = ""

    return JobOutputResponse(
        job_id=job_id,
        output=output,
        is_complete=job_context.status in ("completed", "failed"),
        truncated=len(output) >= 200000,
    )


@router.get("/jobs/{job_id}/trace", response_model=JobTraceResponse, dependencies=[RequireAuth])
async def get_job_trace(job_id: str):
    """
    Get execution trace for a Job.

    Returns the trace_log entries recorded during job execution.
    """
    runtime = get_runtime()
    job_storage = get_job_storage()

    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)

    if job_context is None:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, f"Job '{job_id}' not found"),
        )

    return JobTraceResponse(
        job_id=job_id,
        trace_log=job_context.trace_log,
        total_entries=len(job_context.trace_log),
    )


@router.get(
    "/jobs/{job_id}/metrics", response_model=ExecutionMetricsResponse, dependencies=[RequireAuth]
)
async def get_job_metrics(job_id: str):
    """Get execution metrics for a job."""
    from routilux.server.dependencies import get_job_storage, get_runtime

    job_storage = get_job_storage()
    runtime = get_runtime()
    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
    if not job_context:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, f"Job '{job_id}' not found"),
        )

    registry = MonitoringRegistry.get_instance()
    collector = registry.monitor_collector

    if not collector:
        raise HTTPException(status_code=500, detail="Monitor collector not available")

    metrics = collector.get_metrics(job_id)
    if not metrics:
        raise HTTPException(status_code=404, detail=f"No metrics found for job '{job_id}'")

    # Convert to response model
    routine_metrics = {
        rid: RoutineMetricsResponse(
            routine_id=rm.routine_id,
            execution_count=rm.execution_count,
            total_duration=rm.total_duration,
            avg_duration=rm.avg_duration,
            min_duration=rm.min_duration,
            max_duration=rm.max_duration,
            error_count=rm.error_count,
            last_execution=rm.last_execution,
        )
        for rid, rm in metrics.routine_metrics.items()
    }

    # Convert ErrorRecord objects to dictionaries
    errors = [
        {
            "error_id": err.error_id,
            "job_id": err.job_id,
            "routine_id": err.routine_id,
            "timestamp": err.timestamp.isoformat(),
            "error_type": err.error_type,
            "error_message": err.error_message,
            "traceback": err.traceback,
        }
        for err in metrics.errors
    ]

    return ExecutionMetricsResponse(
        job_id=metrics.job_id,
        flow_id=metrics.flow_id,
        start_time=metrics.start_time if metrics.start_time else datetime.now(),
        end_time=metrics.end_time,
        duration=metrics.duration,
        routine_metrics=routine_metrics,
        total_events=metrics.total_events,
        total_slot_calls=metrics.total_slot_calls,
        total_event_emits=metrics.total_event_emits,
        errors=errors,
    )


@router.get(
    "/jobs/{job_id}/execution-trace",
    response_model=ExecutionTraceResponse,
    dependencies=[RequireAuth],
)
async def get_job_execution_trace(
    job_id: str,
    limit: Optional[int] = Query(
        None,
        ge=1,
        le=10000,
        description="Maximum number of trace events to return. Range: 1-10000.",
    ),
):
    """Get execution trace for a job (from MonitorCollector)."""
    from routilux.server.dependencies import get_job_storage, get_runtime

    job_storage = get_job_storage()
    runtime = get_runtime()
    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
    if not job_context:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, f"Job '{job_id}' not found"),
        )

    registry = MonitoringRegistry.get_instance()
    collector = registry.monitor_collector

    if not collector:
        raise HTTPException(status_code=500, detail="Monitor collector not available")

    events = collector.get_execution_trace(job_id, limit)

    event_responses = [
        ExecutionEventResponse(
            event_id=event.event_id,
            job_id=event.job_id,
            routine_id=event.routine_id,
            event_type=event.event_type,
            timestamp=event.timestamp,
            data=event.data,
            duration=event.duration,
            status=event.status,
        )
        for event in events
    ]

    return ExecutionTraceResponse(
        events=event_responses,
        total=len(event_responses),
    )


@router.get("/jobs/{job_id}/logs", dependencies=[RequireAuth])
async def get_job_logs(job_id: str):
    """Get execution logs for a job."""
    from routilux.server.dependencies import get_job_storage, get_runtime

    job_storage = get_job_storage()
    runtime = get_runtime()
    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
    if not job_context:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, f"Job '{job_id}' not found"),
        )

    logs = getattr(job_context, "trace_log", [])

    return {
        "job_id": job_id,
        "logs": logs,
        "total": len(logs),
    }


@router.get("/jobs/{job_id}/data", dependencies=[RequireAuth])
async def get_job_data(job_id: str):
    """Get job-level data."""
    from routilux.server.dependencies import get_job_storage, get_runtime

    job_storage = get_job_storage()
    runtime = get_runtime()
    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
    if not job_context:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, f"Job '{job_id}' not found"),
        )

    return {
        "job_id": job_id,
        "data": job_context.data,
    }


@router.get(
    "/jobs/{job_id}/monitoring",
    response_model=JobMonitoringData,
    dependencies=[RequireAuth],
)
async def get_job_monitoring_data(job_id: str):
    """Get complete monitoring data for a job."""
    from routilux.server.dependencies import get_job_storage, get_runtime

    job_storage = get_job_storage()
    runtime = get_runtime()
    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
    if not job_context:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, f"Job '{job_id}' not found"),
        )

    service = get_monitor_service()
    try:
        return service.get_job_monitoring_data(job_id)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, str(e)),
        )


@router.get(
    "/jobs/{job_id}/routines/status",
    response_model=Dict[str, RoutineExecutionStatus],
    dependencies=[RequireAuth],
)
async def get_routines_status(job_id: str):
    """Get execution status for all routines in a job."""
    from routilux.server.dependencies import get_job_storage, get_runtime

    job_storage = get_job_storage()
    runtime = get_runtime()
    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
    if not job_context:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, f"Job '{job_id}' not found"),
        )

    service = get_monitor_service()
    try:
        return service.get_all_routines_status(job_id)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, str(e)),
        )


@router.get(
    "/jobs/{job_id}/routines/{routine_id}/queue-status",
    response_model=List[SlotQueueStatus],
    dependencies=[RequireAuth],
)
async def get_routine_queue_status(job_id: str, routine_id: str):
    """Get queue status for all slots in a specific routine."""
    from routilux.server.dependencies import get_job_storage, get_runtime

    job_storage = get_job_storage()
    runtime = get_runtime()
    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
    if not job_context:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, f"Job '{job_id}' not found"),
        )

    service = get_monitor_service()
    try:
        return service.get_routine_queue_status(job_id, routine_id)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, str(e)),
        )


@router.get(
    "/jobs/{job_id}/queues/status",
    response_model=Dict[str, List[SlotQueueStatus]],
    dependencies=[RequireAuth],
)
async def get_job_queues_status(job_id: str):
    """Get queue status for all routines in a job."""
    from routilux.server.dependencies import get_job_storage, get_runtime

    job_storage = get_job_storage()
    runtime = get_runtime()
    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
    if not job_context:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, f"Job '{job_id}' not found"),
        )

    service = get_monitor_service()
    try:
        return service.get_all_queues_status(job_id)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, str(e)),
        )


@router.post("/jobs/{job_id}/complete", response_model=JobResponse, dependencies=[RequireAuth])
async def complete_job(job_id: str):
    """
    Mark a Job as completed.

    Use this to explicitly mark a job as done when all processing is complete.
    """
    runtime = get_runtime()
    job_storage = get_job_storage()

    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)

    if job_context is None:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, f"Job '{job_id}' not found"),
        )

    if job_context.status in ("completed", "failed"):
        raise HTTPException(
            status_code=400,
            detail=create_error_response(
                ErrorCode.JOB_ALREADY_COMPLETED,
                f"Job '{job_id}' is already in terminal state: {job_context.status}",
            ),
        )

    # Try Runtime.complete_job first
    success = runtime.complete_job(job_id, status="completed")

    if not success:
        # Job not in Runtime, update directly
        job_context.complete(status="completed")
        job_storage.save_job(job_context)

    # Refresh job context
    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
    flow_id = job_storage.get_flow_id(job_id) or ""

    logger.info(f"Completed job {job_id}")
    return _job_to_response(job_context, flow_id=flow_id)


@router.post("/jobs/{job_id}/fail", response_model=JobResponse, dependencies=[RequireAuth])
async def fail_job(job_id: str, request: JobFailRequest):
    """
    Mark a Job as failed.

    Use this to explicitly mark a job as failed with an error message.
    """
    runtime = get_runtime()
    job_storage = get_job_storage()

    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)

    if job_context is None:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, f"Job '{job_id}' not found"),
        )

    if job_context.status in ("completed", "failed"):
        raise HTTPException(
            status_code=400,
            detail=create_error_response(
                ErrorCode.JOB_ALREADY_COMPLETED,
                f"Job '{job_id}' is already in terminal state: {job_context.status}",
            ),
        )

    # Try Runtime.complete_job first
    success = runtime.complete_job(job_id, status="failed", error=request.error)

    if not success:
        # Job not in Runtime, update directly
        job_context.complete(status="failed", error=request.error)
        job_storage.save_job(job_context)

    # Refresh job context
    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
    flow_id = job_storage.get_flow_id(job_id) or ""

    logger.info(f"Failed job {job_id}: {request.error}")
    return _job_to_response(job_context, flow_id=flow_id)


@router.get("/jobs/{job_id}/status", dependencies=[RequireAuth])
async def get_job_status(job_id: str):
    """
    Get current status of a Job (lightweight endpoint).

    Use this for frequent polling - returns minimal data.
    """
    runtime = get_runtime()
    job_storage = get_job_storage()

    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)

    if job_context is None:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, f"Job '{job_id}' not found"),
        )

    flow_id = job_storage.get_flow_id(job_id) or ""

    return {
        "job_id": job_id,
        "worker_id": job_context.worker_id,
        "status": job_context.status,
        "flow_id": flow_id,
    }


@router.post("/jobs/{job_id}/wait", dependencies=[RequireAuth])
async def wait_for_job(
    job_id: str,
    timeout: float = Query(60.0, ge=1.0, le=3600.0, description="Timeout in seconds"),
):
    """
    Wait for a Job to complete (blocking endpoint).

    Blocks until the job reaches a terminal state (completed/failed) or timeout.
    """
    runtime = get_runtime()
    job_storage = get_job_storage()

    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)

    if job_context is None:
        raise HTTPException(
            status_code=404,
            detail=create_error_response(ErrorCode.JOB_NOT_FOUND, f"Job '{job_id}' not found"),
        )

    # Check if already complete
    if job_context.status in ("completed", "failed"):
        return {
            "status": "already_complete",
            "job_id": job_id,
            "final_status": job_context.status,
            "waited_seconds": 0.0,
        }

    # Wait for completion
    start_time = time.time()
    poll_interval = 0.5

    while True:
        elapsed = time.time() - start_time
        if elapsed >= timeout:
            current_job = job_storage.get_job(job_id) or runtime.get_job(job_id)
            return {
                "status": "timeout",
                "job_id": job_id,
                "final_status": current_job.status if current_job else "unknown",
                "waited_seconds": elapsed,
                "message": f"Job did not complete within {timeout} seconds",
            }

        # Check job status
        current_job = job_storage.get_job(job_id) or runtime.get_job(job_id)
        if current_job and current_job.status in ("completed", "failed"):
            return {
                "status": "completed",
                "job_id": job_id,
                "final_status": current_job.status,
                "waited_seconds": time.time() - start_time,
            }

        await asyncio.sleep(poll_interval)
