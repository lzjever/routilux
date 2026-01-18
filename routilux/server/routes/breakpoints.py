"""
Breakpoint management API routes.
"""

from fastapi import APIRouter, HTTPException

from routilux.monitoring.breakpoint_manager import Breakpoint
from routilux.monitoring.registry import MonitoringRegistry

# Note: job_store (old system) removed - use get_job_storage() instead
from routilux.server.middleware.auth import RequireAuth
from routilux.server.models.breakpoint import (
    BreakpointCreateRequest,
    BreakpointListResponse,
    BreakpointResponse,
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
    # Verify job exists (use new job storage)
    from routilux.server.dependencies import get_job_storage, get_runtime

    job_storage = get_job_storage()
    runtime = get_runtime()

    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
    if not job_context:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    # JobContext now contains flow_id directly
    flow_id = job_context.flow_id
    if not flow_id:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' has no flow_id")

    registry = MonitoringRegistry.get_instance()
    breakpoint_mgr = registry.breakpoint_manager

    if not breakpoint_mgr:
        raise HTTPException(status_code=500, detail="Breakpoint manager not available")

    # For routine-level breakpoints, use job-specific activation policy
    if request.type == "routine" and request.routine_id:
        # Get flow and routine to save original policy
        from routilux.core.registry import FlowRegistry

        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get(flow_id)

        if not flow:
            raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

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
        # Set policy on worker for the new system
        from routilux.core.registry import WorkerRegistry

        worker_registry = WorkerRegistry.get_instance()
        worker = worker_registry.get(job_context.worker_id)
        if worker:
            # Store policy in worker state
            if not hasattr(worker, "_job_activation_policies"):
                worker._job_activation_policies = {}
            worker._job_activation_policies[job_id] = {request.routine_id: bp_policy}

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
    # Verify job exists (use new job storage)
    from routilux.server.dependencies import get_job_storage, get_runtime

    job_storage = get_job_storage()
    runtime = get_runtime()

    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
    if not job_context:
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
    # Verify job exists (use new job storage)
    from routilux.server.dependencies import get_job_storage, get_runtime

    job_storage = get_job_storage()
    runtime = get_runtime()

    job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
    if not job_context:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    # JobContext now contains flow_id directly
    flow_id = job_context.flow_id
    if not flow_id:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' has no flow_id")

    registry = MonitoringRegistry.get_instance()
    breakpoint_mgr = registry.breakpoint_manager

    if not breakpoint_mgr:
        raise HTTPException(status_code=404, detail="Breakpoint manager not available")

    # Get breakpoint to check if it's a routine-level breakpoint
    breakpoints = breakpoint_mgr.get_breakpoints(job_id)
    breakpoint = next((bp for bp in breakpoints if bp.breakpoint_id == breakpoint_id), None)

    if breakpoint and breakpoint.type == "routine" and breakpoint.routine_id:
        # Policy restoration handled at worker level
        # Note: Breakpoint policies are managed by BreakpointManager
        # The original policy restoration logic may need to be implemented
        # based on how breakpoints are stored and managed
        pass  # TODO: Implement policy restoration if needed

    breakpoint_mgr.remove_breakpoint(breakpoint_id, job_id)


# Note: Breakpoint enable/disable has been moved to workers category
# Use PUT /api/workers/{worker_id}/breakpoints/{breakpoint_id} instead
