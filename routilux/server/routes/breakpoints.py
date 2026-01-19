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
        routine_id=bp.routine_id,
        slot_name=bp.slot_name,
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
    """
    Create a slot-level breakpoint for a job.

    **Overview**:
    Creates a breakpoint that pauses job execution when data is about to be
    enqueued to a specific slot. When a breakpoint is hit, the enqueue operation
    is skipped, effectively pausing execution at that point.

    **Endpoint**: `POST /api/v1/jobs/{job_id}/breakpoints`

    **Use Cases**:
    - Debug job execution issues
    - Inspect data at specific slots
    - Control execution flow
    - Step through job execution
    - Analyze data transformations

    **Request Example**:
    ```json
    {
      "routine_id": "data_processor",
      "slot_name": "input",
      "enabled": true,
      "condition": null
    }
    ```

    **Response Example**:
    ```json
    {
      "breakpoint_id": "bp_xyz789",
      "job_id": "job_abc123",
      "routine_id": "data_processor",
      "slot_name": "input",
      "condition": null,
      "enabled": true,
      "hit_count": 0
    }
    ```

    **Breakpoint Configuration**:
    - `routine_id` (required): Routine ID where the slot is located
    - `slot_name` (required): Slot name where breakpoint is set
    - `condition` (optional): Conditional expression (e.g., "data.get('value') > 10")
    - `enabled` (optional): Whether breakpoint is active (default: true)

    **Error Responses**:
    - `404 Not Found`: Job not found, flow not found, routine not found in flow, or slot not found in routine
    - `500 Internal Server Error`: Breakpoint manager not available

    **Best Practices**:
    1. Create breakpoints before job starts for best results
    2. Use slot breakpoints to intercept data at specific points
    3. Disable breakpoints when not debugging: PUT /api/workers/{worker_id}/breakpoints/{breakpoint_id}
    4. Remove breakpoints after debugging: DELETE /api/jobs/{job_id}/breakpoints/{breakpoint_id}

    **Related Endpoints**:
    - GET /api/v1/jobs/{job_id}/breakpoints - List all breakpoints
    - PUT /api/v1/workers/{worker_id}/breakpoints/{breakpoint_id} - Enable/disable breakpoint
    - DELETE /api/v1/jobs/{job_id}/breakpoints/{breakpoint_id} - Delete breakpoint

    Args:
        job_id: Unique job identifier
        request: BreakpointCreateRequest with breakpoint configuration

    Returns:
        BreakpointResponse: Created breakpoint information

    Raises:
        HTTPException: 404 if job, flow, routine, or slot not found
        HTTPException: 500 if breakpoint manager unavailable
    """
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

    # Verify routine and slot exist in flow
    from routilux.core.registry import FlowRegistry

    flow_registry = FlowRegistry.get_instance()
    flow = flow_registry.get(flow_id)

    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    if request.routine_id not in flow.routines:
        raise HTTPException(
            status_code=404,
            detail=f"Routine '{request.routine_id}' not found in flow"
        )

    routine = flow.routines[request.routine_id]
    slot = routine.get_slot(request.slot_name)

    if slot is None:
        raise HTTPException(
            status_code=404,
            detail=f"Slot '{request.slot_name}' not found in routine '{request.routine_id}'"
        )

    # Get breakpoint manager
    registry = MonitoringRegistry.get_instance()
    breakpoint_mgr = registry.breakpoint_manager

    if not breakpoint_mgr:
        raise HTTPException(status_code=500, detail="Breakpoint manager not available")

    # Create breakpoint (no policy manipulation needed)
    breakpoint = Breakpoint(
        job_id=job_id,
        routine_id=request.routine_id,
        slot_name=request.slot_name,
        condition=request.condition,
        enabled=request.enabled,
    )

    breakpoint_mgr.add_breakpoint(breakpoint)

    return _breakpoint_to_response(breakpoint)


@router.get(
    "/jobs/{job_id}/breakpoints", response_model=BreakpointListResponse, dependencies=[RequireAuth]
)
async def list_breakpoints(job_id: str):
    """
    List all breakpoints for a job.

    **Overview**:
    Returns a list of all breakpoints associated with a job. Use this to inspect active
    breakpoints, check breakpoint status, and manage debugging sessions.

    **Endpoint**: `GET /api/v1/jobs/{job_id}/breakpoints`

    **Use Cases**:
    - View all active breakpoints for a job
    - Check breakpoint status and hit counts
    - Manage debugging sessions
    - Verify breakpoint configuration

    **Request Example**:
    ```
    GET /api/jobs/job_abc123/breakpoints
    ```

    **Response Example**:
    ```json
    {
      "breakpoints": [
        {
          "breakpoint_id": "bp_xyz789",
          "job_id": "job_abc123",
          "routine_id": "data_processor",
          "slot_name": "input",
          "condition": null,
          "enabled": true,
          "hit_count": 3
        }
      ],
      "total": 1
    }
    ```

    **Response Fields**:
    - `breakpoints`: List of breakpoint objects
    - `total`: Total number of breakpoints

    **Breakpoint Information**:
    Each breakpoint includes:
    - `breakpoint_id`: Unique breakpoint identifier
    - `job_id`: Job ID this breakpoint is associated with
    - `routine_id`: Routine ID where the slot is located (required)
    - `slot_name`: Slot name where breakpoint is set (required)
    - `condition`: Optional conditional expression
    - `enabled`: Whether breakpoint is currently active
    - `hit_count`: Number of times breakpoint was hit

    **Error Responses**:
    - `404 Not Found`: Job with this ID does not exist

    **Related Endpoints**:
    - POST /api/v1/jobs/{job_id}/breakpoints - Create new breakpoint
    - PUT /api/v1/workers/{worker_id}/breakpoints/{breakpoint_id} - Enable/disable breakpoint
    - DELETE /api/v1/jobs/{job_id}/breakpoints/{breakpoint_id} - Delete breakpoint

    Args:
        job_id: Unique job identifier

    Returns:
        BreakpointListResponse: List of breakpoints with total count

    Raises:
        HTTPException: 404 if job not found
    """
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
    """
    Delete a breakpoint.

    **Overview**:
    Permanently removes a breakpoint from a job. After deletion, the breakpoint will no
    longer intercept slot enqueue operations.

    **Endpoint**: `DELETE /api/v1/jobs/{job_id}/breakpoints/{breakpoint_id}`

    **Use Cases**:
    - Remove breakpoints after debugging
    - Clean up breakpoints when no longer needed
    - Restore normal execution flow
    - Manage debugging sessions

    **Request Example**:
    ```
    DELETE /api/jobs/job_abc123/breakpoints/bp_xyz789
    ```

    **Response**: 204 No Content (successful deletion)

    **Behavior**:
    - Breakpoint is removed from the job
    - Execution continues normally after deletion
    - Breakpoint cannot be recovered after deletion

    **Error Responses**:
    - `404 Not Found`: Job or breakpoint not found, or breakpoint manager unavailable

    **Best Practices**:
    1. List breakpoints before deletion: GET /api/jobs/{job_id}/breakpoints
    2. Consider disabling instead of deleting: PUT /api/workers/{worker_id}/breakpoints/{breakpoint_id}
    3. Delete breakpoints when debugging is complete
    4. Verify deletion: GET /api/jobs/{job_id}/breakpoints

    **Related Endpoints**:
    - GET /api/v1/jobs/{job_id}/breakpoints - List breakpoints
    - POST /api/v1/jobs/{job_id}/breakpoints - Create breakpoint
    - PUT /api/v1/workers/{worker_id}/breakpoints/{breakpoint_id} - Enable/disable breakpoint

    Args:
        job_id: Unique job identifier
        breakpoint_id: Unique breakpoint identifier

    Returns:
        None (204 No Content)

    Raises:
        HTTPException: 404 if job or breakpoint not found
    """
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

    # Verify breakpoint exists
    breakpoints = breakpoint_mgr.get_breakpoints(job_id)
    breakpoint = next((bp for bp in breakpoints if bp.breakpoint_id == breakpoint_id), None)

    if not breakpoint:
        raise HTTPException(
            status_code=404,
            detail=f"Breakpoint '{breakpoint_id}' not found for job '{job_id}'"
        )

    # Remove breakpoint (no policy restoration needed)
    breakpoint_mgr.remove_breakpoint(breakpoint_id, job_id)


# Note: Breakpoint enable/disable has been moved to workers category
# Use PUT /api/workers/{worker_id}/breakpoints/{breakpoint_id} instead
