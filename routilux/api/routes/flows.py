"""
Flow management API routes.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from routilux.api.models.flow import (
    ConnectionInfo,
    FlowCreateRequest,
    FlowListResponse,
    FlowResponse,
    RoutineInfo,
)
from routilux.flow import Flow
from routilux.monitoring.storage import flow_store

router = APIRouter()


def _flow_to_response(flow: Flow) -> FlowResponse:
    """Convert Flow to response model."""
    routines = {}
    for routine_id, routine in flow.routines.items():
        routines[routine_id] = RoutineInfo(
            routine_id=routine_id,
            class_name=routine.__class__.__name__,
            slots=list(routine._slots.keys()),
            events=list(routine._events.keys()),
            config=routine._config.copy(),
        )

    connections = []
    for i, conn in enumerate(flow.connections):
        # Critical fix: Check if source_event and target_slot exist before accessing attributes
        if conn.source_event is None or conn.target_slot is None:
            continue  # Skip incomplete connections

        source_routine_id = flow._get_routine_id(conn.source_event.routine) if conn.source_event.routine else None
        target_routine_id = flow._get_routine_id(conn.target_slot.routine) if conn.target_slot.routine else None
        connections.append(
            ConnectionInfo(
                connection_id=f"conn_{i}",
                source_routine=source_routine_id or "",
                source_event=conn.source_event.name,
                target_routine=target_routine_id or "",
                target_slot=conn.target_slot.name,
                param_mapping=conn.param_mapping,
            )
        )

    return FlowResponse(
        flow_id=flow.flow_id,
        routines=routines,
        connections=connections,
        execution_strategy=flow.execution_strategy,
        max_workers=flow.max_workers,
    )


@router.get("/flows", response_model=FlowListResponse)
async def list_flows():
    """List all flows."""
    flows = flow_store.list_all()
    return FlowListResponse(
        flows=[_flow_to_response(flow) for flow in flows],
        total=len(flows),
    )


@router.get("/flows/{flow_id}", response_model=FlowResponse)
async def get_flow(flow_id: str):
    """Get flow details."""
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    return _flow_to_response(flow)


@router.post("/flows", response_model=FlowResponse, status_code=201)
async def create_flow(request: FlowCreateRequest):
    """Create a new flow."""
    try:
        if request.dsl:
            # Create from YAML
            flow = Flow.from_yaml(request.dsl)
        elif request.dsl_dict:
            # Create from dict
            flow = Flow.from_dict(request.dsl_dict)
        else:
            # Create empty flow
            flow = Flow(flow_id=request.flow_id)

        # Set execution strategy if provided
        if request.execution_strategy:
            flow.set_execution_strategy(
                request.execution_strategy, max_workers=request.max_workers or 5
            )

        # Store flow
        flow_store.add(flow)

        return _flow_to_response(flow)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create flow: {str(e)}") from e


@router.delete("/flows/{flow_id}", status_code=204)
async def delete_flow(flow_id: str):
    """Delete a flow."""
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    flow_store.remove(flow_id)


@router.get("/flows/{flow_id}/dsl")
async def export_flow_dsl(flow_id: str, format: str = Query("yaml", pattern="^(yaml|json)$")):
    """Export flow as DSL."""
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    # Build DSL dict
    dsl_dict = {
        "flow_id": flow.flow_id,
        "routines": {},
        "connections": [],
        "execution": {
            "strategy": flow.execution_strategy,
            "max_workers": flow.max_workers,
            "timeout": flow.execution_timeout,
        },
    }

    # Add routines
    for routine_id, routine in flow.routines.items():
        routine_spec = {
            "class": f"{routine.__class__.__module__}.{routine.__class__.__name__}",
        }
        if routine._config:
            routine_spec["config"] = routine._config.copy()

        error_handler = routine.get_error_handler()
        if error_handler:
            routine_spec["error_handler"] = {
                "strategy": error_handler.strategy.value,
                "max_retries": error_handler.max_retries,
                "retry_delay": error_handler.retry_delay,
            }

        dsl_dict["routines"][routine_id] = routine_spec

    # Add connections
    for conn in flow.connections:
        # Critical fix: Check for None before accessing connection attributes
        if conn.source_event is None or conn.source_event.routine is None:
            continue  # Skip incomplete connections
        if conn.target_slot is None or conn.target_slot.routine is None:
            continue  # Skip incomplete connections

        source_routine_id = flow._get_routine_id(conn.source_event.routine)
        target_routine_id = flow._get_routine_id(conn.target_slot.routine)
        conn_spec = {
            "from": f"{source_routine_id}.{conn.source_event.name}",
            "to": f"{target_routine_id}.{conn.target_slot.name}",
        }
        if conn.param_mapping:
            conn_spec["param_mapping"] = conn.param_mapping
        dsl_dict["connections"].append(conn_spec)

    # Return in requested format
    if format == "yaml":
        import yaml

        return {"format": "yaml", "dsl": yaml.dump(dsl_dict, default_flow_style=False)}
    else:
        import json

        return {"format": "json", "dsl": json.dumps(dsl_dict, indent=2)}


@router.post("/flows/{flow_id}/validate")
async def validate_flow(flow_id: str):
    """Validate flow structure."""
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    issues = flow.validate()
    return {
        "valid": len(issues) == 0,
        "issues": issues,
    }


@router.get("/flows/{flow_id}/routines", response_model=Dict[str, RoutineInfo])
async def list_flow_routines(flow_id: str):
    """List all routines in a flow."""
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    routines = {}
    for routine_id, routine in flow.routines.items():
        routines[routine_id] = RoutineInfo(
            routine_id=routine_id,
            class_name=routine.__class__.__name__,
            slots=list(routine._slots.keys()),
            events=list(routine._events.keys()),
            config=routine._config.copy(),
        )

    return routines


@router.get("/flows/{flow_id}/connections", response_model=List[ConnectionInfo])
async def list_flow_connections(flow_id: str):
    """List all connections in a flow."""
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    connections = []
    for i, conn in enumerate(flow.connections):
        # Critical fix: Check if source_event and target_slot exist before accessing attributes
        if conn.source_event is None or conn.target_slot is None:
            continue  # Skip incomplete connections

        source_routine_id = flow._get_routine_id(conn.source_event.routine) if conn.source_event.routine else None
        target_routine_id = flow._get_routine_id(conn.target_slot.routine) if conn.target_slot.routine else None
        connections.append(
            ConnectionInfo(
                connection_id=f"conn_{i}",
                source_routine=source_routine_id or "",
                source_event=conn.source_event.name,
                target_routine=target_routine_id or "",
                target_slot=conn.target_slot.name,
                param_mapping=conn.param_mapping,
            )
        )

    return connections


@router.post("/flows/{flow_id}/routines")
async def add_routine_to_flow(
    flow_id: str, routine_id: str, class_path: str, config: Optional[Dict[str, Any]] = None
):
    """Add a routine to an existing flow."""
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    # Fix: Validate class_path format before using
    if "." not in class_path or class_path.startswith(".") or class_path.endswith("."):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid class_path format: '{class_path}'. Expected format: 'module.path.ClassName'"
        )

    # Load routine class
    try:
        from importlib import import_module

        module_path, class_name = class_path.rsplit(".", 1)
        if not module_path or not class_name:
            raise ValueError("Both module_path and class_name must be non-empty")
        module = import_module(module_path)
        routine_class = getattr(module, class_name)
        routine = routine_class()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to load routine class: {str(e)}") from e

    # Apply config
    if config:
        routine.set_config(**config)

    # Add to flow
    flow.add_routine(routine, routine_id)
    flow_store.add(flow)  # Update stored flow

    return {"routine_id": routine_id, "status": "added"}


@router.post("/flows/{flow_id}/connections")
async def add_connection_to_flow(
    flow_id: str,
    source_routine: str,
    source_event: str,
    target_routine: str,
    target_slot: str,
    param_mapping: Optional[Dict[str, str]] = None,
):
    """Add a connection to an existing flow."""
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    try:
        flow.connect(source_routine, source_event, target_routine, target_slot, param_mapping)
        flow_store.add(flow)  # Update stored flow
        return {"status": "connected"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to add connection: {str(e)}") from e


@router.delete("/flows/{flow_id}/routines/{routine_id}", status_code=204)
async def remove_routine_from_flow(flow_id: str, routine_id: str):
    """Remove a routine from a flow."""
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    if routine_id not in flow.routines:
        raise HTTPException(status_code=404, detail=f"Routine '{routine_id}' not found in flow")

    # Fix: Remove dead code - line 306 did nothing (flow.routines[routine_id] accessed but didn't use result)
    # Remove connections involving this routine
    connections_to_remove = []
    for conn in flow.connections:
        # Critical fix: Check for None before accessing connection attributes
        if conn.source_event is None or conn.source_event.routine is None:
            continue  # Skip incomplete connections
        if conn.target_slot is None or conn.target_slot.routine is None:
            continue  # Skip incomplete connections

        source_routine_id = flow._get_routine_id(conn.source_event.routine)
        target_routine_id = flow._get_routine_id(conn.target_slot.routine)
        if source_routine_id == routine_id or target_routine_id == routine_id:
            connections_to_remove.append(conn)

    for conn in connections_to_remove:
        flow.connections.remove(conn)
        # Also remove from _event_slot_connections
        key = (conn.source_event, conn.target_slot)
        flow._event_slot_connections.pop(key, None)

    # Remove routine
    del flow.routines[routine_id]
    flow_store.add(flow)  # Update stored flow


@router.delete("/flows/{flow_id}/connections/{connection_index}", status_code=204)
async def remove_connection_from_flow(flow_id: str, connection_index: int):
    """Remove a connection from a flow."""
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    if connection_index < 0 or connection_index >= len(flow.connections):
        raise HTTPException(
            status_code=404, detail=f"Connection index {connection_index} out of range"
        )

    conn = flow.connections[connection_index]
    flow.connections.remove(conn)

    # Remove from _event_slot_connections
    key = (conn.source_event, conn.target_slot)
    flow._event_slot_connections.pop(key, None)

    flow_store.add(flow)  # Update stored flow
