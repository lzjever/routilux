"""
Breakpoint management API routes.
"""

from fastapi import APIRouter, HTTPException

from routilux.api.middleware.auth import RequireAuth
from routilux.api.models.breakpoint import (
    BreakpointCreateRequest,
    BreakpointListResponse,
    BreakpointResponse,
)
from routilux.monitoring.breakpoint_manager import Breakpoint
from routilux.monitoring.registry import MonitoringRegistry
from routilux.monitoring.storage import job_store

router = APIRouter()


def _breakpoint_to_response(bp: Breakpoint) -> BreakpointResponse:
    """Convert Breakpoint to response model."""
    return BreakpointResponse(
        breakpoint_id=bp.breakpoint_id,
        job_id=bp.job_id,
        type=bp.type,
        routine_id=bp.routine_id,
        slot_name=bp.slot_name,
        event_name=bp.event_name,
        condition=bp.condition,
        enabled=bp.enabled,
        hit_count=bp.hit_count,
    )


@router.post("/jobs/{job_id}/breakpoints", response_model=BreakpointResponse, status_code=201, dependencies=[RequireAuth])
async def create_breakpoint(job_id: str, request: BreakpointCreateRequest):
    """Create a breakpoint for a job."""
    # Verify job exists
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    registry = MonitoringRegistry.get_instance()
    breakpoint_mgr = registry.breakpoint_manager

    if not breakpoint_mgr:
        raise HTTPException(status_code=500, detail="Breakpoint manager not available")

    # Create breakpoint
    breakpoint = Breakpoint(
        job_id=job_id,
        type=request.type,
        routine_id=request.routine_id,
        slot_name=request.slot_name,
        event_name=request.event_name,
        condition=request.condition,
        enabled=request.enabled,
    )

    breakpoint_mgr.add_breakpoint(breakpoint)

    return _breakpoint_to_response(breakpoint)


@router.get("/jobs/{job_id}/breakpoints", response_model=BreakpointListResponse, dependencies=[RequireAuth])
async def list_breakpoints(job_id: str):
    """List all breakpoints for a job."""
    # Verify job exists
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    registry = MonitoringRegistry.get_instance()
    breakpoint_mgr = registry.breakpoint_manager

    if not breakpoint_mgr:
        return BreakpointListResponse(breakpoints=[], total=0)

    breakpoints = breakpoint_mgr.get_breakpoints(job_id)

    return BreakpointListResponse(
        breakpoints=[_breakpoint_to_response(bp) for bp in breakpoints],
        total=len(breakpoints),
    )


@router.delete("/jobs/{job_id}/breakpoints/{breakpoint_id}", status_code=204, dependencies=[RequireAuth])
async def delete_breakpoint(job_id: str, breakpoint_id: str):
    """Delete a breakpoint."""
    # Verify job exists
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    registry = MonitoringRegistry.get_instance()
    breakpoint_mgr = registry.breakpoint_manager

    if not breakpoint_mgr:
        raise HTTPException(status_code=404, detail="Breakpoint manager not available")

    breakpoint_mgr.remove_breakpoint(breakpoint_id, job_id)


@router.put("/jobs/{job_id}/breakpoints/{breakpoint_id}", response_model=BreakpointResponse, dependencies=[RequireAuth])
async def update_breakpoint(job_id: str, breakpoint_id: str, enabled: bool):
    """Update breakpoint (enable/disable)."""
    # Verify job exists
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    registry = MonitoringRegistry.get_instance()
    breakpoint_mgr = registry.breakpoint_manager

    if not breakpoint_mgr:
        raise HTTPException(status_code=404, detail="Breakpoint manager not available")

    breakpoints = breakpoint_mgr.get_breakpoints(job_id)
    breakpoint = next((bp for bp in breakpoints if bp.breakpoint_id == breakpoint_id), None)

    if not breakpoint:
        raise HTTPException(status_code=404, detail=f"Breakpoint '{breakpoint_id}' not found")

    breakpoint.enabled = enabled

    return _breakpoint_to_response(breakpoint)
