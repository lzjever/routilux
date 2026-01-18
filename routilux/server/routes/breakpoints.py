"""
Breakpoint management API routes.
"""

from fastapi import APIRouter, HTTPException

from routilux.monitoring.breakpoint_manager import Breakpoint
from routilux.monitoring.registry import MonitoringRegistry
from routilux.monitoring.storage import job_store
from routilux.server.middleware.auth import RequireAuth
from routilux.server.models.breakpoint import (
    BreakpointCreateRequest,
    BreakpointListResponse,
    BreakpointResponse,
    BreakpointUpdateRequest,
)

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
        source_routine_id=bp.source_routine_id,
        source_event_name=bp.source_event_name,
        target_routine_id=bp.target_routine_id,
        target_slot_name=bp.target_slot_name,
        condition=bp.condition,
        enabled=bp.enabled,
        hit_count=bp.hit_count,
    )


@router.post(
    "/jobs/{job_id}/breakpoints",
    response_model=BreakpointResponse,
    status_code=201,
    dependencies=[RequireAuth],
)
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

    # For routine-level breakpoints, use job-specific activation policy
    if request.type == "routine" and request.routine_id:
        # Get flow and routine to save original policy
        from routilux.core.registry import FlowRegistry

        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get(job_state.flow_id)

        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow '{job_state.flow_id}' not found")

        if request.routine_id not in flow.routines:
            raise HTTPException(
                status_code=404, detail=f"Routine '{request.routine_id}' not found in flow"
            )

        routine = flow.routines[request.routine_id]

        # Save original policy (if exists)
        original_policy = routine._activation_policy

        # Create breakpoint policy and set as job-specific policy
        from routilux.activation_policies import breakpoint_policy

        bp_policy = breakpoint_policy(request.routine_id)
        job_state.set_routine_activation_policy(request.routine_id, bp_policy)

        # Store original policy in breakpoint for restoration
        # Note: We'll store it in a way that can be retrieved later
        # Since Callable can't be serialized, we'll handle this in remove_breakpoint

    # Create breakpoint
    breakpoint = Breakpoint(
        job_id=job_id,
        type=request.type,
        routine_id=request.routine_id,
        slot_name=request.slot_name,
        event_name=request.event_name,
        source_routine_id=request.source_routine_id,
        source_event_name=request.source_event_name,
        target_routine_id=request.target_routine_id,
        target_slot_name=request.target_slot_name,
        condition=request.condition,
        enabled=request.enabled,
    )

    # Store original policy reference in breakpoint (non-serializable)
    if request.type == "routine" and request.routine_id:
        # We'll need to get the original policy when removing
        # For now, we store a reference that we can use
        breakpoint._original_policy = original_policy  # type: ignore

    breakpoint_mgr.add_breakpoint(breakpoint)

    return _breakpoint_to_response(breakpoint)


@router.get(
    "/jobs/{job_id}/breakpoints", response_model=BreakpointListResponse, dependencies=[RequireAuth]
)
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


@router.delete(
    "/jobs/{job_id}/breakpoints/{breakpoint_id}", status_code=204, dependencies=[RequireAuth]
)
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

    # Get breakpoint to check if it's a routine-level breakpoint
    breakpoints = breakpoint_mgr.get_breakpoints(job_id)
    breakpoint = next((bp for bp in breakpoints if bp.breakpoint_id == breakpoint_id), None)

    if breakpoint and breakpoint.type == "routine" and breakpoint.routine_id:
        # Restore original policy
        from routilux.core.registry import FlowRegistry

        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get(job_state.flow_id)

        if flow and breakpoint.routine_id in flow.routines:
            routine = flow.routines[breakpoint.routine_id]
            # Get original policy from breakpoint or routine
            original_policy = getattr(breakpoint, "_original_policy", None)

            if original_policy:
                # Restore original policy
                job_state.set_routine_activation_policy(breakpoint.routine_id, original_policy)
            elif routine._activation_policy:
                # Use routine's current policy
                job_state.set_routine_activation_policy(
                    breakpoint.routine_id, routine._activation_policy
                )
            else:
                # Remove job-specific policy to use routine's default (immediate activation)
                job_state.remove_routine_activation_policy(breakpoint.routine_id)

    breakpoint_mgr.remove_breakpoint(breakpoint_id, job_id)


@router.put(
    "/jobs/{job_id}/breakpoints/{breakpoint_id}",
    response_model=BreakpointResponse,
    dependencies=[RequireAuth],
)
async def update_breakpoint(job_id: str, breakpoint_id: str, request: BreakpointUpdateRequest):
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

    breakpoint.enabled = request.enabled

    return _breakpoint_to_response(breakpoint)
