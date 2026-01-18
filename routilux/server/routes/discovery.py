"""
Flow and job discovery API routes.

Provides endpoints to discover and register flows/jobs created outside the API.
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException

from routilux.server.middleware.auth import RequireAuth
from routilux.server.models.flow import FlowListResponse
from routilux.server.models.job import JobListResponse, JobResponse
from routilux.server.routes.flows import _flow_to_response
from routilux.server.routes.jobs import _job_to_response
from routilux.server.dependencies import (
    get_runtime,
    get_flow_registry,
    get_worker_registry,
    get_job_storage,
)
from routilux.core.registry import FlowRegistry, WorkerRegistry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/discovery/flows/sync", response_model=FlowListResponse, dependencies=[RequireAuth])
async def sync_flows():
    """Sync flows from global registry to API store.

    Discovers all flows from the global registry and adds them to the API store.
    This allows the API to monitor flows created outside the API.

    Returns:
        List of discovered flows.
    """
    try:
        flow_registry = get_flow_registry()
        registry_flows = flow_registry.list_all()

        return FlowListResponse(
            flows=[_flow_to_response(flow) for flow in registry_flows],
            total=len(registry_flows),
        )
    except Exception as e:
        logger.exception(f"Failed to sync flows: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to sync flows: {str(e)}") from e


@router.get("/discovery/flows", response_model=FlowListResponse, dependencies=[RequireAuth])
async def discover_flows():
    """Discover flows from global registry.

    Returns flows from the global registry that may not be in the API store.
    Does not modify the API store.

    Returns:
        List of discovered flows.
    """
    try:
        flow_registry = get_flow_registry()
        registry_flows = flow_registry.list_all()

        return FlowListResponse(
            flows=[_flow_to_response(flow) for flow in registry_flows],
            total=len(registry_flows),
        )
    except Exception as e:
        logger.exception(f"Failed to discover flows: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to discover flows: {str(e)}") from e


@router.post("/discovery/jobs/sync", response_model=JobListResponse, dependencies=[RequireAuth])
async def sync_jobs():
    """Sync jobs from Runtime to API storage.

    Discovers all jobs from the Runtime and syncs them to the job storage.
    This allows the API to monitor jobs started outside the API.

    Returns:
        List of discovered jobs.
    """
    try:
        runtime = get_runtime()
        job_storage = get_job_storage()
        worker_registry = get_worker_registry()
        
        # Get all jobs from Runtime
        all_jobs = runtime.list_jobs()
        
        # Sync to storage
        for job in all_jobs:
            # Get flow_id from worker
            flow_id = ""
            worker = worker_registry.get(job.worker_id)
            if worker:
                flow_id = worker.flow_id
            job_storage.save_job(job, flow_id=flow_id)

        return JobListResponse(
            jobs=[_job_to_response(job, flow_id=job_storage.get_flow_id(job.job_id) or "") for job in all_jobs],
            total=len(all_jobs),
            limit=len(all_jobs),
            offset=0,
        )
    except Exception as e:
        logger.exception(f"Failed to sync jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to sync jobs: {str(e)}") from e


@router.get("/discovery/jobs", response_model=JobListResponse, dependencies=[RequireAuth])
async def discover_jobs():
    """Discover jobs from Runtime.

    Returns jobs from the Runtime that may not be in the API storage.
    Does not modify the storage.

    Returns:
        List of discovered jobs.
    """
    try:
        runtime = get_runtime()
        worker_registry = get_worker_registry()
        job_storage = get_job_storage()
        
        all_jobs = runtime.list_jobs()

        responses = []
        for job in all_jobs:
            flow_id = ""
            worker = worker_registry.get(job.worker_id)
            if worker:
                flow_id = worker.flow_id
            responses.append(_job_to_response(job, flow_id=flow_id))

        return JobListResponse(
            jobs=responses,
            total=len(all_jobs),
            limit=len(all_jobs),
            offset=0,
        )
    except Exception as e:
        logger.exception(f"Failed to discover jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to discover jobs: {str(e)}") from e


@router.post("/discovery/workers/sync", dependencies=[RequireAuth])
async def sync_workers():
    """Sync workers from Runtime to WorkerRegistry.

    Discovers all active workers from Runtime and ensures they are registered.

    Returns:
        List of discovered workers.
    """
    try:
        runtime = get_runtime()
        worker_registry = get_worker_registry()
        
        workers = []
        with runtime._worker_lock:
            for worker_state in runtime._active_workers.values():
                # Register in WorkerRegistry if not already
                if worker_registry.get(worker_state.worker_id) is None:
                    worker_registry.register(worker_state)
                
                workers.append({
                    "worker_id": worker_state.worker_id,
                    "flow_id": worker_state.flow_id,
                    "status": worker_state.status.value if hasattr(worker_state.status, "value") else str(worker_state.status),
                })
        
        return {
            "workers": workers,
            "total": len(workers),
        }
    except Exception as e:
        logger.exception(f"Failed to sync workers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to sync workers: {str(e)}") from e
