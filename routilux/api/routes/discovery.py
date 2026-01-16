"""
Flow and job discovery API routes.

Provides endpoints to discover and register flows/jobs created outside the API.
"""

from fastapi import APIRouter, HTTPException

from routilux.api.middleware.auth import RequireAuth
from routilux.api.models.flow import FlowListResponse, FlowResponse
from routilux.api.models.job import JobListResponse, JobResponse
from routilux.api.routes.flows import _flow_to_response
from routilux.api.routes.jobs import _job_to_response
from routilux.monitoring.flow_registry import FlowRegistry
from routilux.monitoring.job_registry import JobRegistry
from routilux.monitoring.storage import flow_store, job_store

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
        registry = FlowRegistry.get_instance()
        registry_flows = registry.list_all()
        
        # Add to API store
        for flow in registry_flows:
            flow_store.add(flow)
        
        return FlowListResponse(
            flows=[_flow_to_response(flow) for flow in registry_flows],
            total=len(registry_flows),
        )
    except Exception as e:
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
        registry = FlowRegistry.get_instance()
        registry_flows = registry.list_all()
        
        return FlowListResponse(
            flows=[_flow_to_response(flow) for flow in registry_flows],
            total=len(registry_flows),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to discover flows: {str(e)}") from e


@router.post("/discovery/jobs/sync", response_model=JobListResponse, dependencies=[RequireAuth])
async def sync_jobs():
    """Sync jobs from global registry to API store.
    
    Discovers all jobs from the global registry and adds them to the API store.
    This allows the API to monitor jobs started outside the API.
    
    Returns:
        List of discovered jobs.
    """
    try:
        registry = JobRegistry.get_instance()
        registry_jobs = registry.list_all()
        
        # Add to API store
        for job_state in registry_jobs:
            job_store.add(job_state)
        
        return JobListResponse(
            jobs=[_job_to_response(job_state) for job_state in registry_jobs],
            total=len(registry_jobs),
            limit=len(registry_jobs),
            offset=0,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync jobs: {str(e)}") from e


@router.get("/discovery/jobs", response_model=JobListResponse, dependencies=[RequireAuth])
async def discover_jobs():
    """Discover jobs from global registry.
    
    Returns jobs from the global registry that may not be in the API store.
    Does not modify the API store.
    
    Returns:
        List of discovered jobs.
    """
    try:
        registry = JobRegistry.get_instance()
        registry_jobs = registry.list_all()
        
        return JobListResponse(
            jobs=[_job_to_response(job_state) for job_state in registry_jobs],
            total=len(registry_jobs),
            limit=len(registry_jobs),
            offset=0,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to discover jobs: {str(e)}") from e
