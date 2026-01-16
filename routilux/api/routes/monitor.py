"""
Monitoring API routes.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from routilux.api.models.monitor import (
    ExecutionEventResponse,
    ExecutionMetricsResponse,
    ExecutionTraceResponse,
    RoutineMetricsResponse,
)
from routilux.monitoring.registry import MonitoringRegistry
from routilux.monitoring.storage import flow_store, job_store

router = APIRouter()


@router.get("/jobs/{job_id}/metrics", response_model=ExecutionMetricsResponse)
async def get_job_metrics(job_id: str):
    """Get execution metrics for a job."""
    # Verify job exists
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    MonitoringRegistry.enable()
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


@router.get("/jobs/{job_id}/trace", response_model=ExecutionTraceResponse)
async def get_job_trace(job_id: str, limit: Optional[int] = Query(None, ge=1, le=10000)):
    """Get execution trace for a job."""
    # Verify job exists
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    MonitoringRegistry.enable()
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


@router.get("/jobs/{job_id}/logs")
async def get_job_logs(job_id: str):
    """Get execution logs for a job."""
    # Verify job exists
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    # Get logs from job state
    logs = job_state.shared_log if hasattr(job_state, "shared_log") else []

    return {
        "job_id": job_id,
        "logs": logs,
        "total": len(logs),
    }


@router.get("/flows/{flow_id}/metrics")
async def get_flow_metrics(flow_id: str):
    """Get aggregated metrics for all jobs of a flow."""
    # Verify flow exists
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    MonitoringRegistry.enable()
    registry = MonitoringRegistry.get_instance()
    collector = registry.monitor_collector

    if not collector:
        raise HTTPException(status_code=500, detail="Monitor collector not available")

    # Get all jobs for this flow
    jobs = job_store.get_by_flow(flow_id)

    # Aggregate metrics
    total_jobs = len(jobs)
    completed_jobs = sum(1 for job in jobs if str(job.status) in ("completed", "COMPLETED"))
    failed_jobs = sum(1 for job in jobs if str(job.status) in ("failed", "FAILED"))

    # Get metrics for each job
    job_metrics = []
    for job in jobs:
        metrics = collector.get_metrics(job.job_id)
        if metrics:
            job_metrics.append(
                {
                    "job_id": job.job_id,
                    "duration": metrics.duration,
                    "status": str(job.status),
                }
            )

    return {
        "flow_id": flow_id,
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "job_metrics": job_metrics,
    }
