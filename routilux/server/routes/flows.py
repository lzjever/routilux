"""
Flow management API routes.
"""

from typing import Dict, List

from fastapi import APIRouter, HTTPException, Query

from routilux.flow import Flow
from routilux.monitoring.storage import flow_store
from routilux.server.middleware.auth import RequireAuth
from routilux.server.models.flow import (
    AddConnectionRequest,
    AddRoutineRequest,
    ConnectionInfo,
    FlowCreateRequest,
    FlowListResponse,
    FlowResponse,
    RoutineInfo,
)
from routilux.server.validators import (
    validate_dsl_size,
    validate_routine_id_conflict,
    validate_routine_instance,
)

router = APIRouter()


def _flow_to_response(flow: Flow) -> FlowResponse:
    """Convert Flow to response model with defensive checks."""
    import logging

    logger = logging.getLogger(__name__)
    routines = {}
    for routine_id, routine in flow.routines.items():
        # Defensive check: Ensure it's actually a Routine instance
        # This handles cases where corrupted data might exist (e.g., Flow added as Routine)
        from routilux.core.routine import Routine

        if not isinstance(routine, Routine):
            logger.error(
                f"Flow '{flow.flow_id}' contains non-Routine object at routine_id '{routine_id}': "
                f"{type(routine).__name__}. Skipping this entry."
            )
            continue

        # Safe access with error handling
        try:
            slots = list(routine._slots.keys()) if hasattr(routine, "_slots") else []
            events = list(routine._events.keys()) if hasattr(routine, "_events") else []
            config = routine._config.copy() if hasattr(routine, "_config") else {}
        except Exception as e:
            logger.error(
                f"Error extracting routine info for '{routine_id}' in flow '{flow.flow_id}': {e}"
            )
            slots, events, config = [], [], {}

        routines[routine_id] = RoutineInfo(
            routine_id=routine_id,
            class_name=routine.__class__.__name__,
            slots=slots,
            events=events,
            config=config,
        )

    connections = []
    for i, conn in enumerate(flow.connections):
        # Critical fix: Check if source_event and target_slot exist before accessing attributes
        if conn.source_event is None or conn.target_slot is None:
            continue  # Skip incomplete connections

        source_routine_id = (
            flow._get_routine_id(conn.source_event.routine) if conn.source_event.routine else None
        )
        target_routine_id = (
            flow._get_routine_id(conn.target_slot.routine) if conn.target_slot.routine else None
        )
        connections.append(
            ConnectionInfo(
                connection_id=f"conn_{i}",
                source_routine=source_routine_id or "",
                source_event=conn.source_event.name,
                target_routine=target_routine_id or "",
                target_slot=conn.target_slot.name,
            )
        )

    return FlowResponse(
        flow_id=flow.flow_id,
        routines=routines,
        connections=connections,
    )


@router.get("/flows", response_model=FlowListResponse, dependencies=[RequireAuth])
async def list_flows():
    """List all flows in the system.

    **Overview**:
    Returns a list of all flows registered in the system, including their routines and connections.
    Use this endpoint to discover available flows and their structure.

    **Response Example**:
    ```json
    {
      "flows": [
        {
          "flow_id": "data_processing_flow",
          "routines": {
            "data_source": {
              "routine_id": "data_source",
              "class_name": "DataSource",
              "slots": ["trigger"],
              "events": ["output"],
              "config": {"name": "Source"}
            }
          },
          "connections": [
            {
              "connection_id": "conn_0",
              "source_routine": "data_source",
              "source_event": "output",
              "target_routine": "processor",
              "target_slot": "input"
            }
          ],
          "created_at": "2025-01-15T10:00:00",
          "updated_at": "2025-01-15T10:05:00"
        }
      ],
      "total": 10
    }
    ```

    **Use Cases**:
    - Discover available flows
    - Build flow selection UI
    - Inspect flow structure
    - Verify flow registration

    **Performance Note**:
    - Returns complete flow information (routines + connections)
    - For large numbers of flows, consider pagination in future versions

    Returns:
        FlowListResponse: List of all flows with total count

    Raises:
        HTTPException: 500 if flow store is inaccessible
    """
    flows = flow_store.list_all()
    return FlowListResponse(
        flows=[_flow_to_response(flow) for flow in flows],
        total=len(flows),
    )


@router.get("/flows/{flow_id}", response_model=FlowResponse, dependencies=[RequireAuth])
async def get_flow(flow_id: str):
    """Get detailed information about a specific flow.

    **Overview**:
    Returns complete information about a flow including all routines, their configurations,
    slots, events, and all connections between routines.

    **Request Example**:
    ```
    GET /api/flows/data_processing_flow
    ```

    **Response Example**:
    ```json
    {
      "flow_id": "data_processing_flow",
      "routines": {
        "data_source": {
          "routine_id": "data_source",
          "class_name": "DataSource",
          "slots": ["trigger"],
          "events": ["output"],
          "config": {"name": "Source"}
        },
        "processor": {
          "routine_id": "processor",
          "class_name": "DataTransformer",
          "slots": ["input"],
          "events": ["output"],
          "config": {"name": "Processor", "transformation": "uppercase"}
        }
      },
      "connections": [
        {
          "connection_id": "conn_0",
          "source_routine": "data_source",
          "source_event": "output",
          "target_routine": "processor",
          "target_slot": "input"
        }
      ],
      "created_at": "2025-01-15T10:00:00",
      "updated_at": "2025-01-15T10:05:00"
    }
    ```

    **Use Cases**:
    - Inspect flow structure before execution
    - Build flow visualization UI
    - Verify flow configuration
    - Understand data flow paths

    **Error Responses**:
    - `404 Not Found`: Flow with this ID does not exist

    **Related Endpoints**:
    - GET /api/flows/{flow_id}/routines - Get just routines (lighter)
    - GET /api/flows/{flow_id}/connections - Get just connections (lighter)
    - GET /api/flows/{flow_id}/dsl - Export flow as DSL

    Args:
        flow_id: Unique flow identifier

    Returns:
        FlowResponse: Complete flow information

    Raises:
        HTTPException: 404 if flow not found
    """
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    return _flow_to_response(flow)


@router.post("/flows", response_model=FlowResponse, status_code=201, dependencies=[RequireAuth])
async def create_flow(request: FlowCreateRequest):
    """Create a new flow.

    **Overview**:
    Creates a new flow in the system. You can create a flow in three ways:
    1. **Empty flow**: Just provide a flow_id (or let system generate one)
    2. **From YAML DSL**: Provide flow definition as YAML string
    3. **From JSON DSL**: Provide flow definition as JSON object

    **Creation Methods**:

    **1. Empty Flow** (for dynamic building):
    ```json
    {
      "flow_id": "my_new_flow"
    }
    ```
    Then use POST /api/flows/{flow_id}/routines and POST /api/flows/{flow_id}/connections
    to build the flow dynamically.

    **2. From YAML DSL**:
    ```json
    {
      "flow_id": "my_flow",
      "dsl": "flow_id: my_flow\nroutines:\n  source:\n    class: data_source\n    config:\n      name: Source"
    }
    ```
    Note: `class` field must be a factory name (e.g., "data_source"), not a class path.

    **3. From JSON DSL**:
    ```json
    {
      "flow_id": "my_flow",
      "dsl_dict": {
        "flow_id": "my_flow",
        "routines": {
          "source": {
            "class": "data_source",
            "config": {"name": "Source"}
          }
        },
        "connections": []
      }
    }
    ```

    **Response Example**:
    ```json
    {
      "flow_id": "my_new_flow",
      "routines": {},
      "connections": [],
      "created_at": "2025-01-15T10:00:00",
      "updated_at": null
    }
    ```

    **Error Responses**:
    - `400 Bad Request`: Invalid DSL format, flow_id already exists, or creation failed
    - `422 Validation Error`: Invalid request parameters

    **Best Practices**:
    1. Use empty flow + dynamic building for interactive flow builders
    2. Use DSL for predefined/reusable flows
    3. Validate flow after creation: POST /api/flows/{flow_id}/validate
    4. **All routines in DSL must be registered in factory** - use factory names: `class: data_source`

    **Related Endpoints**:
    - POST /api/flows/{flow_id}/routines - Add routine to flow
    - POST /api/flows/{flow_id}/connections - Add connection to flow
    - POST /api/flows/{flow_id}/validate - Validate flow structure
    - GET /api/flows/{flow_id}/dsl - Export flow as DSL

    Args:
        request: FlowCreateRequest with flow_id and optional DSL

    Returns:
        FlowResponse: Created flow information

    Raises:
        HTTPException: 400 if creation fails
        HTTPException: 422 if request validation fails
    """
    try:
        from routilux.tools.factory.factory import ObjectFactory

        factory = ObjectFactory.get_instance()

        if request.dsl:
            # Validate DSL size
            validate_dsl_size(request.dsl)
            # Parse YAML and load from factory
            import yaml

            dsl_dict = yaml.safe_load(request.dsl)
            if not isinstance(dsl_dict, dict):
                raise ValueError("DSL YAML must parse to a dictionary")
            flow = factory.load_flow_from_dsl(dsl_dict)
        elif request.dsl_dict:
            # Load from factory using dict
            flow = factory.load_flow_from_dsl(request.dsl_dict)
        else:
            # Create empty flow
            flow = Flow(flow_id=request.flow_id)

        # Store flow
        flow_store.add(flow)

        return _flow_to_response(flow)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to create flow from DSL: {str(e)}"
        ) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create flow: {str(e)}") from e


@router.delete("/flows/{flow_id}", status_code=204, dependencies=[RequireAuth])
async def delete_flow(flow_id: str):
    """Delete a flow from the system.

    **Overview**:
    Permanently removes a flow from the system. This operation cannot be undone.
    The flow and all its routines/connections are deleted.

    **Warning**: This operation is **irreversible**. Make sure you don't need the flow
    before deleting it. Consider exporting the flow as DSL first for backup.

    **Request Example**:
    ```
    DELETE /api/flows/data_processing_flow
    ```

    **Response**: 204 No Content (successful deletion)

    **Error Responses**:
    - `404 Not Found`: Flow with this ID does not exist

    **Best Practices**:
    1. Export flow before deletion: GET /api/flows/{flow_id}/dsl
    2. Check for active jobs: GET /api/jobs?flow_id={flow_id}
    3. Consider archiving instead of deleting

    **Related Endpoints**:
    - GET /api/flows/{flow_id}/dsl - Export flow before deletion
    - GET /api/jobs?flow_id={flow_id} - Check for active jobs

    Args:
        flow_id: Unique flow identifier

    Returns:
        None (204 No Content)

    Raises:
        HTTPException: 404 if flow not found
    """
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    flow_store.remove(flow_id)


@router.get("/flows/{flow_id}/dsl", dependencies=[RequireAuth])
async def export_flow_dsl(
    flow_id: str,
    format: str = Query(
        "yaml",
        pattern="^(yaml|json)$",
        description="Export format: 'yaml' (human-readable) or 'json' (machine-readable). Default: yaml.",
        example="yaml",
    ),
):
    """Export flow as DSL (Domain Specific Language).

    **Overview**:
    Exports a flow to its DSL representation, which can be used to recreate the flow
    or store it as a template. The DSL includes all routines, their configurations,
    and all connections.

    **Use Cases**:
    - Backup flows before deletion
    - Share flows between systems
    - Version control flows
    - Create flow templates
    - Migrate flows

    **Request Examples**:
    ```
    # Export as YAML (human-readable)
    GET /api/flows/data_processing_flow/dsl?format=yaml

    # Export as JSON (machine-readable)
    GET /api/flows/data_processing_flow/dsl?format=json
    ```

    **Response Example (YAML)**:
    ```json
    {
      "format": "yaml",
      "dsl": "flow_id: data_processing_flow\nroutines:\n  source:\n    class: DataSource\n    config:\n      name: Source\nconnections:\n  - from: source.output\n    to: processor.input"
    }
    ```

    **Response Example (JSON)**:
    ```json
    {
      "format": "json",
      "dsl": "{\n  \"flow_id\": \"data_processing_flow\",\n  \"routines\": {\n    \"source\": {\n      \"class\": \"DataSource\",\n      \"config\": {\n        \"name\": \"Source\"\n      }\n    }\n  },\n  \"connections\": [\n    {\n      \"from\": \"source.output\",\n      \"to\": \"processor.input\"\n    }\n  ]\n}"
    }
    ```

    **DSL Format**:
    The DSL includes:
    - `flow_id`: Flow identifier
    - `routines`: Dictionary of routine_id -> routine specification
      - `class`: Factory name (must be registered in factory)
      - `config`: Routine configuration
    - `connections`: List of connections
      - `from`: "{routine_id}.{event_name}"
      - `to`: "{routine_id}.{slot_name}"

    **Factory-Only Requirement**:
    All routines in the flow must be registered in the factory for export to succeed.
    The exported DSL uses factory names instead of class paths for portability and security.

    **Recreating from DSL**:
    ```javascript
    // Export flow
    const export = await api.flows.exportDSL(flow_id, "yaml");

    // Later, recreate from DSL
    const newFlow = await api.flows.create({
      flow_id: "restored_flow",
      dsl: export.dsl
    });
    ```

    **Error Responses**:
    - `404 Not Found`: Flow not found

    **Related Endpoints**:
    - POST /api/flows - Create flow from DSL
    - DELETE /api/flows/{flow_id} - Delete flow (export first!)

    Args:
        flow_id: Unique flow identifier
        format: Export format: "yaml" or "json"

    Returns:
        dict: Format and DSL string

    Raises:
        HTTPException: 404 if flow not found
        HTTPException: 422 if format is invalid
    """
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    # Use factory to export DSL (factory-only components)
    from routilux.tools.factory.factory import ObjectFactory

    factory = ObjectFactory.get_instance()
    try:
        dsl = factory.export_flow_to_dsl(flow, format=format)
        return {"format": format, "dsl": dsl}
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot export flow: {str(e)}. All routines must be registered in factory.",
        ) from e


@router.post("/flows/{flow_id}/validate", dependencies=[RequireAuth])
async def validate_flow(flow_id: str):
    """Validate flow structure and configuration.

    **Overview**:
    Validates a flow's structure and returns a list of any issues found.
    This is useful before executing a flow to catch configuration errors early.

    **Validation Checks**:
    - Circular dependencies (errors)
    - Unconnected events (warnings)
    - Unconnected slots (warnings)
    - Invalid connections (errors)
    - Missing routines in connections
    - Invalid routine configurations

    **Request Example**:
    ```
    POST /api/flows/data_processing_flow/validate
    ```

    **Response Example (Valid Flow)**:
    ```json
    {
      "valid": true,
      "issues": []
    }
    ```

    **Response Example (Invalid Flow)**:
    ```json
    {
      "valid": false,
      "issues": [
        "Circular dependency detected: routine_A -> routine_B -> routine_A",
        "Event 'output' in routine 'source' is not connected to any slot",
        "Slot 'input' in routine 'processor' has no incoming connections"
      ]
    }
    ```

    **Issue Types**:
    - **Errors**: Must be fixed before flow can execute properly
    - **Warnings**: May indicate design issues but won't prevent execution

    **Use Cases**:
    - Validate flow before execution
    - Check flow after dynamic modifications
    - CI/CD pipeline validation
    - Flow builder validation

    **Best Practices**:
    1. Validate after creating/modifying flows
    2. Fix all errors before execution
    3. Review warnings for potential issues
    4. Re-validate after adding routines/connections

    **Error Responses**:
    - `404 Not Found`: Flow not found

    **Related Endpoints**:
    - POST /api/flows/{flow_id}/routines - Add routine (then validate)
    - POST /api/flows/{flow_id}/connections - Add connection (then validate)
    - POST /api/jobs - Start job (validates automatically)

    Args:
        flow_id: Unique flow identifier

    Returns:
        dict: Validation result with list of issues

    Raises:
        HTTPException: 404 if flow not found
    """
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    issues = flow.validate()
    return {
        "valid": len(issues) == 0,
        "issues": issues,
    }


@router.get(
    "/flows/{flow_id}/routines", response_model=Dict[str, RoutineInfo], dependencies=[RequireAuth]
)
async def list_flow_routines(flow_id: str):
    """List all routines in a flow with their interface information.

    **Overview**:
    Returns a dictionary of all routines in the flow, including their slots, events,
    configuration, and class information. This is essential for understanding flow
    structure and building connections.

    **Request Example**:
    ```
    GET /api/flows/data_processing_flow/routines
    ```

    **Response Example**:
    ```json
    {
      "data_source": {
        "routine_id": "data_source",
        "class_name": "DataSource",
        "slots": ["trigger"],
        "events": ["output"],
        "config": {"name": "Source"}
      },
      "processor": {
        "routine_id": "processor",
        "class_name": "DataTransformer",
        "slots": ["input"],
        "events": ["output"],
        "config": {"name": "Processor", "transformation": "uppercase"}
      }
    }
    ```

    **Use Cases**:
    - Discover flow structure
    - Build connection UI (see available slots/events)
    - Verify routine configuration
    - Understand data flow paths

    **Interface Information**:
    - `slots`: Input slots (use as target_slot in connections)
    - `events`: Output events (use as source_event in connections)
    - `config`: Current routine configuration

    **Error Responses**:
    - `404 Not Found`: Flow not found

    **Related Endpoints**:
    - GET /api/flows/{flow_id} - Get complete flow information
    - GET /api/flows/{flow_id}/connections - List connections
    - GET /api/factory/objects/{name}/interface - Get routine interface from factory

    Args:
        flow_id: Unique flow identifier

    Returns:
        Dict[str, RoutineInfo]: Dictionary mapping routine_id to routine information

    Raises:
        HTTPException: 404 if flow not found
    """
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    routines = {}
    for routine_id, routine in flow.routines.items():
        # Defensive check: Ensure it's actually a Routine instance
        from routilux.core.routine import Routine

        if not isinstance(routine, Routine):
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"Flow '{flow.flow_id}' contains non-Routine object at routine_id '{routine_id}': "
                f"{type(routine).__name__}. Skipping this entry."
            )
            continue

        # Safe access with error handling
        try:
            slots = list(routine._slots.keys()) if hasattr(routine, "_slots") else []
            events = list(routine._events.keys()) if hasattr(routine, "_events") else []
            config = routine._config.copy() if hasattr(routine, "_config") else {}
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"Error extracting routine info for '{routine_id}' in flow '{flow.flow_id}': {e}"
            )
            slots, events, config = [], [], []

        routines[routine_id] = RoutineInfo(
            routine_id=routine_id,
            class_name=routine.__class__.__name__,
            slots=slots,
            events=events,
            config=config,
        )

    return routines


@router.get(
    "/flows/{flow_id}/connections", response_model=List[ConnectionInfo], dependencies=[RequireAuth]
)
async def list_flow_connections(flow_id: str):
    """List all connections in a flow.

    **Overview**:
    Returns a list of all data flow connections in the flow, showing how routines
    are connected via events and slots.

    **Request Example**:
    ```
    GET /api/flows/data_processing_flow/connections
    ```

    **Response Example**:
    ```json
    [
      {
        "connection_id": "conn_0",
        "source_routine": "data_source",
        "source_event": "output",
        "target_routine": "processor",
        "target_slot": "input"
      },
      {
        "connection_id": "conn_1",
        "source_routine": "processor",
        "source_event": "output",
        "target_routine": "sink",
        "target_slot": "input"
      }
    ]
    ```

    **Connection Structure**:
    Each connection represents a data flow path:
    - `source_routine` emits `source_event`
    - Data flows to `target_routine`'s `target_slot`
    - `connection_id` is auto-generated (used for deletion)

    **Use Cases**:
    - Visualize flow structure
    - Verify connections
    - Build flow diagram
    - Debug data flow issues

    **Connection Order**:
    - Connections are returned in the order they were created
    - Connection index matches list index (for deletion)

    **Error Responses**:
    - `404 Not Found`: Flow not found

    **Related Endpoints**:
    - GET /api/flows/{flow_id}/routines - List routines (see what can be connected)
    - POST /api/flows/{flow_id}/connections - Add new connection
    - DELETE /api/flows/{flow_id}/connections/{connection_index} - Remove connection

    Args:
        flow_id: Unique flow identifier

    Returns:
        List[ConnectionInfo]: List of all connections in the flow

    Raises:
        HTTPException: 404 if flow not found
    """
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    connections = []
    for i, conn in enumerate(flow.connections):
        # Critical fix: Check if source_event and target_slot exist before accessing attributes
        if conn.source_event is None or conn.target_slot is None:
            continue  # Skip incomplete connections

        source_routine_id = (
            flow._get_routine_id(conn.source_event.routine) if conn.source_event.routine else None
        )
        target_routine_id = (
            flow._get_routine_id(conn.target_slot.routine) if conn.target_slot.routine else None
        )
        connections.append(
            ConnectionInfo(
                connection_id=f"conn_{i}",
                source_routine=source_routine_id or "",
                source_event=conn.source_event.name,
                target_routine=target_routine_id or "",
                target_slot=conn.target_slot.name,
            )
        )

    return connections


@router.post("/flows/{flow_id}/routines", dependencies=[RequireAuth])
async def add_routine_to_flow(flow_id: str, request: AddRoutineRequest):
    """Add a routine to an existing flow.

    **Overview**:
    Dynamically adds a routine to an existing flow. The routine can be created from:
    1. **Factory name** (recommended): Use a registered factory name like "data_source"
    2. **Class path**: Use full module path like "mymodule.DataProcessor"

    **Factory-Only Requirement**:
    - All routines must be registered in the factory before use
    - Use GET /api/factory/objects to see available factory names
    - Factory names are required - class paths are no longer supported

    **Request Example**:
    ```json
    {
      "routine_id": "data_processor",
      "object_name": "data_transformer",
      "config": {
        "name": "MyProcessor",
        "transformation": "uppercase",
        "timeout": 30
      }
    }
    ```

    **Response Example**:
    ```json
    {
      "routine_id": "data_processor",
      "status": "added"
    }
    ```

    **Configuration**:
    - `config` is optional and will be merged with factory defaults
    - Configuration is applied to the routine instance
    - Use GET /api/factory/objects/{name} to see example_config for reference

    **Error Responses**:
    - `404 Not Found`: Flow not found
    - `400 Bad Request`: Routine ID already exists, or object_name not found in factory
    - `422 Validation Error`: Invalid request parameters

    **Validation**:
    - Routine ID must be unique within the flow
    - Object name must exist in factory (factory-only, no class paths)
    - Config must be a valid dictionary

    **Best Practices**:
    1. Use factory names when possible (safer, discoverable)
    2. Check available objects first: GET /api/objects
    3. Verify routine interface: GET /api/objects/{name}/interface
    4. Validate flow after adding routines: POST /api/flows/{flow_id}/validate

    **Related Endpoints**:
    - GET /api/factory/objects - List available factory objects
    - GET /api/factory/objects/{name}/interface - Get routine interface (slots/events)
    - GET /api/flows/{flow_id}/routines - List routines in flow
    - DELETE /api/flows/{flow_id}/routines/{routine_id} - Remove routine

    Args:
        flow_id: Flow identifier
        request: AddRoutineRequest with routine_id, object_name, and optional config

    Returns:
        dict: Status confirmation with routine_id

    Raises:
        HTTPException: 404 if flow not found
        HTTPException: 400 if routine ID conflict or object_name invalid
        HTTPException: 422 if request validation fails
    """
    from routilux.server.validators import validate_flow_exists
    from routilux.tools.factory.factory import ObjectFactory

    flow = validate_flow_exists(flow_id)
    validate_routine_id_conflict(flow, request.routine_id)

    # Try factory first
    factory = ObjectFactory.get_instance()
    metadata = factory.get_metadata(request.object_name)

    if metadata is not None:
        # Use factory to create
        routine = factory.create(request.object_name, config=request.config)
    else:
        # Factory-only: reject if not found in factory
        available = factory.list_available(object_type="routine")
        available_names = [obj["name"] for obj in available]
        raise HTTPException(
            status_code=400,
            detail={
                "error": "object_not_found",
                "message": f"Object '{request.object_name}' not found in factory. "
                f"All routines must be registered in factory before use.",
                "object_name": request.object_name,
                "available_objects": available_names[:20],  # Limit to first 20 for response size
            },
        )

    # CRITICAL SECURITY FIX: Validate that the created object is actually a Routine instance
    # This prevents Flow instances or other non-Routine objects from being added to flows
    validate_routine_instance(routine, context=f"routine_id: {request.routine_id}")

    # Add to flow
    flow.add_routine(routine, request.routine_id)
    flow_store.add(flow)  # Update stored flow

    return {"routine_id": request.routine_id, "status": "added"}


@router.post("/flows/{flow_id}/connections", dependencies=[RequireAuth])
async def add_connection_to_flow(flow_id: str, request: AddConnectionRequest):
    """Add a connection between routines in a flow.

    **Overview**:
    Creates a data flow connection from a source routine's event to a target routine's slot.
    This defines how data flows through the workflow.

    **Connection Structure**:
    - **Source**: Routine that emits data (via event)
    - **Target**: Routine that receives data (via slot)
    - Data flows: source_routine.event → target_routine.slot

    **Request Example**:
    ```json
    {
      "source_routine": "data_source",
      "source_event": "output",
      "target_routine": "data_processor",
      "target_slot": "input"
    }
    ```

    **Response Example**:
    ```json
    {
      "status": "connected"
    }
    ```

    **Validation**:
    - Both source and target routines must exist in the flow
    - Source routine must have the specified event
    - Target routine must have the specified slot
    - Connection is validated for correctness

    **Error Responses**:
    - `404 Not Found`: Flow, source routine, or target routine not found
    - `400 Bad Request`: Event or slot doesn't exist, invalid connection

    **Discovering Interfaces**:
    Before creating connections, discover routine interfaces:
    1. Get routine info: GET /api/flows/{flow_id}/routines/{routine_id}
    2. Or get factory interface: GET /api/objects/{name}/interface
    3. Use the `events` list for source_event
    4. Use the `slots` list for target_slot

    **Best Practices**:
    1. Verify routines exist before connecting
    2. Check routine interfaces to ensure event/slot exist
    3. Validate flow after adding connections: POST /api/flows/{flow_id}/validate
    4. Use meaningful routine IDs for clarity

    **Related Endpoints**:
    - GET /api/flows/{flow_id}/routines - List routines (see slots/events)
    - GET /api/objects/{name}/interface - Get routine interface
    - GET /api/flows/{flow_id}/connections - List all connections
    - DELETE /api/flows/{flow_id}/connections/{connection_index} - Remove connection

    Args:
        flow_id: Flow identifier
        request: AddConnectionRequest with source and target information

    Returns:
        dict: Status confirmation

    Raises:
        HTTPException: 404 if flow or routines not found
        HTTPException: 400 if connection is invalid
        HTTPException: 422 if request validation fails
    """
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")

    # SECURITY FIX: Validate that source and target routines exist and are Routine instances
    from routilux.core.routine import Routine

    if request.source_routine not in flow.routines:
        raise HTTPException(
            status_code=404,
            detail=f"Source routine '{request.source_routine}' not found in flow",
        )
    source_routine = flow.routines[request.source_routine]
    if not isinstance(source_routine, Routine):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_source_routine_type",
                "message": f"Source routine '{request.source_routine}' is not a Routine instance",
                "object_type": type(source_routine).__name__,
            },
        )

    if request.target_routine not in flow.routines:
        raise HTTPException(
            status_code=404,
            detail=f"Target routine '{request.target_routine}' not found in flow",
        )
    target_routine = flow.routines[request.target_routine]
    if not isinstance(target_routine, Routine):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_target_routine_type",
                "message": f"Target routine '{request.target_routine}' is not a Routine instance",
                "object_type": type(target_routine).__name__,
            },
        )

    try:
        flow.connect(
            request.source_routine,
            request.source_event,
            request.target_routine,
            request.target_slot,
        )
        flow_store.add(flow)  # Update stored flow
        return {"status": "connected"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to add connection: {str(e)}") from e


@router.delete(
    "/flows/{flow_id}/routines/{routine_id}", status_code=204, dependencies=[RequireAuth]
)
async def remove_routine_from_flow(flow_id: str, routine_id: str):
    """Remove a routine from a flow.

    **Overview**:
    Removes a routine from a flow and automatically removes all connections
    involving that routine (both incoming and outgoing).

    **Warning**: This operation automatically removes all connections involving
    this routine. The routine and its connections cannot be recovered.

    **Request Example**:
    ```
    DELETE /api/flows/data_processing_flow/routines/processor
    ```

    **Response**: 204 No Content (successful deletion)

    **Automatic Cleanup**:
    When a routine is removed, the following are automatically removed:
    - All connections where this routine is the source
    - All connections where this routine is the target
    - The routine itself

    **Error Responses**:
    - `404 Not Found`: Flow or routine not found

    **Best Practices**:
    1. Check connections first: GET /api/flows/{flow_id}/connections
    2. Verify no active jobs: GET /api/jobs?flow_id={flow_id}
    3. Consider exporting flow: GET /api/flows/{flow_id}/dsl (for backup)

    **Related Endpoints**:
    - GET /api/flows/{flow_id}/routines - List routines
    - GET /api/flows/{flow_id}/connections - List connections (to see what will be removed)
    - POST /api/flows/{flow_id}/routines - Add routine

    Args:
        flow_id: Unique flow identifier
        routine_id: Routine identifier to remove

    Returns:
        None (204 No Content)

    Raises:
        HTTPException: 404 if flow or routine not found
    """
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


@router.delete(
    "/flows/{flow_id}/connections/{connection_index}", status_code=204, dependencies=[RequireAuth]
)
async def remove_connection_from_flow(flow_id: str, connection_index: int):
    """Remove a connection from a flow.

    **Overview**:
    Removes a specific connection from a flow by its index. The index corresponds
    to the connection's position in the list returned by GET /api/flows/{flow_id}/connections.

    **Warning**: This operation is **irreversible**. The connection cannot be recovered.

    **Request Example**:
    ```
    DELETE /api/flows/data_processing_flow/connections/0
    ```

    **Response**: 204 No Content (successful deletion)

    **Finding Connection Index**:
    1. Get all connections: GET /api/flows/{flow_id}/connections
    2. Find the connection you want to remove
    3. Use its index in the list (0-based)

    **Example**:
    ```javascript
    // Get connections
    const connections = await api.flows.getConnections(flow_id);
    // connections = [
    //   { connection_id: "conn_0", source_routine: "source", ... },  // index 0
    //   { connection_id: "conn_1", source_routine: "processor", ... }  // index 1
    // ]

    // Remove first connection (index 0)
    await api.flows.removeConnection(flow_id, 0);
    ```

    **Error Responses**:
    - `404 Not Found`: Flow not found or connection_index out of range

    **Best Practices**:
    1. List connections first to find the correct index
    2. Verify connection before deletion
    3. Validate flow after removal: POST /api/flows/{flow_id}/validate

    **Related Endpoints**:
    - GET /api/flows/{flow_id}/connections - List connections (to find index)
    - POST /api/flows/{flow_id}/connections - Add connection

    Args:
        flow_id: Unique flow identifier
        connection_index: Zero-based index of the connection to remove

    Returns:
        None (204 No Content)

    Raises:
        HTTPException: 404 if flow not found or index out of range
    """
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
