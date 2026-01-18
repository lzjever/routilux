"""
Object discovery API routes.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from routilux.server.middleware.auth import RequireAuth
from routilux.server.models.object import ObjectListResponse, ObjectMetadataResponse
from routilux.tools.factory.factory import ObjectFactory

router = APIRouter()


@router.get("/objects", response_model=ObjectListResponse, dependencies=[RequireAuth])
async def list_factory_objects(
    category: Optional[str] = Query(
        None,
        description="Optional category filter. Only objects in this category will be returned. "
        "Common categories: 'data_generation', 'validation', 'transformation', 'monitoring', 'debugging', etc. "
        "Leave empty to get all objects regardless of category.",
        examples=["data_generation"],
    ),
    object_type: Optional[str] = Query(
        None,
        description="Optional object type filter. Filter by object type: 'routine' or 'flow'. "
        "Use 'routine' to get only Routines (executable components that can be added to flows). "
        "Use 'flow' to get only Flows (workflow templates that can be cloned). "
        "Leave empty to get all objects regardless of type.",
        examples=["routine"],
    ),
):
    """List all available objects registered in the factory.

    **Overview**:
    Returns a list of all routines and flows registered in the ObjectFactory.
    These are the building blocks you can use to create flows dynamically.

    **Endpoint**: `GET /api/factory/objects`

    **Use Cases**:
    - Discover available routines for flow building
    - Build routine selection UI
    - Filter routines by category and object type
    - Understand what's available in the system

    **Request Examples**:
    ```
    # Get all objects
    GET /api/factory/objects

    # Get only routines
    GET /api/factory/objects?object_type=routine

    # Get only flows
    GET /api/factory/objects?object_type=flow

    # Get routines in a specific category
    GET /api/factory/objects?category=data_generation&object_type=routine

    # Get all objects in a specific category
    GET /api/factory/objects?category=data_generation
    ```

    **Response Example**:
    ```json
    {
      "objects": [
        {
          "name": "data_source",
          "type": "class",
          "object_type": "routine",
          "description": "Generates sample data with metadata",
          "category": "data_generation",
          "tags": ["source", "generator"],
          "example_config": {"name": "Exampledata_source"},
          "version": "1.0.0"
        },
        {
          "name": "data_transformer",
          "type": "class",
          "object_type": "routine",
          "description": "Transforms data with various transformations",
          "category": "transformation",
          "tags": ["transformer", "processor"],
          "example_config": {"name": "Exampledata_transformer"},
          "version": "1.0.0"
        },
        {
          "name": "template_flow",
          "type": "instance",
          "object_type": "flow",
          "description": "A template flow for data processing",
          "category": "template",
          "tags": ["template", "workflow"],
          "example_config": {},
          "version": "1.0.0"
        }
      ],
      "total": 12
    }
    ```

    **Object Types**:
    - `type`: Prototype type - "class" (class-based) or "instance" (instance-based)
    - `object_type`: Object type - "routine" (executable component) or "flow" (workflow template)

    **Filtering**:
    - Use `category` to filter by functional category (e.g., "data_generation")
    - Use `object_type` to filter by object type (e.g., "routine" or "flow")
    - Combine both filters: `?category=data_generation&object_type=routine`

    **Categories**:
    Common categories include:
    - `data_generation`: Routines that generate data
    - `validation`: Routines that validate data
    - `transformation`: Routines that transform data
    - `monitoring`: Routines for monitoring
    - `debugging`: Routines for debugging
    - `sink`: Routines that consume data

    **Next Steps**:
    1. Browse objects: GET /api/factory/objects
    2. Get object details: GET /api/factory/objects/{name}
    3. Get interface info: GET /api/factory/objects/{name}/interface (to see slots/events)
    4. Use in flow: POST /api/flows/{flow_id}/routines with object_name

    **Related Endpoints**:
    - GET /api/factory/objects/{name} - Get object metadata
    - GET /api/factory/objects/{name}/interface - Get routine interface (slots/events)

    Args:
        category: Optional category filter (e.g., 'data_generation')
        object_type: Optional object type filter ('routine' or 'flow')

    Returns:
        ObjectListResponse: List of objects with total count. Each object includes:
        - `object_type`: "routine" or "flow" to distinguish object types
        - `type`: "class" or "instance" (prototype type)
        - `category`: Functional category for filtering

    Raises:
        HTTPException: 422 if object_type is invalid (not 'routine' or 'flow')
        HTTPException: 500 if factory is not accessible
    """
    # Validate object_type if provided
    if object_type and object_type not in ("routine", "flow"):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid object_type: '{object_type}'. Must be 'routine' or 'flow'.",
        )
    factory = ObjectFactory.get_instance()
    objects = factory.list_available(category=category, object_type=object_type)
    return ObjectListResponse(objects=objects, total=len(objects))


@router.get("/objects/{name}", response_model=ObjectMetadataResponse, dependencies=[RequireAuth])
async def get_factory_object_metadata(name: str):
    """Get metadata for a specific factory object.

    **Overview**:
    Returns detailed metadata about a registered object in the factory, including description,
    category, tags, example configuration, and version. Use this to understand what an object
    does and how to configure it.

    **Endpoint**: `GET /api/factory/objects/{name}`

    **Request Example**:
    ```
    GET /api/factory/objects/data_source
    ```

    **Response Example**:
    ```json
    {
      "name": "data_source",
      "description": "Generates sample data with metadata",
      "category": "data_generation",
      "tags": ["source", "generator"],
      "example_config": {
        "name": "Exampledata_source"
      },
      "version": "1.0.0"
    }
    ```

    **Use Cases**:
    - Understand what an object does
    - See example configuration
    - Check object version
    - Build configuration UI

    **Note**: This endpoint returns metadata only. To get interface information
    (slots and events), use GET /api/factory/objects/{name}/interface.

    **Error Responses**:
    - `404 Not Found`: Object with this name is not registered in factory

    **Related Endpoints**:
    - GET /api/factory/objects - List all factory objects
    - GET /api/factory/objects/{name}/interface - Get routine interface (slots/events)

    Args:
        name: Object name (factory registration name)

    Returns:
        ObjectMetadataResponse: Object metadata

    Raises:
        HTTPException: 404 if object not found
    """
    factory = ObjectFactory.get_instance()
    metadata = factory.get_metadata(name)
    if metadata is None:
        raise HTTPException(status_code=404, detail=f"Object '{name}' not found")
    return ObjectMetadataResponse(
        name=metadata.name,
        description=metadata.description,
        category=metadata.category,
        tags=metadata.tags,
        example_config=metadata.example_config,
        version=metadata.version,
    )


@router.get("/objects/{name}/interface", dependencies=[RequireAuth])
async def get_factory_object_interface(name: str):
    """Get interface information for a routine (slots, events, activation policy).

    **Overview**:
    Returns detailed interface information for a routine registered in the factory,
    including all input slots, output events, activation policy, and configuration.
    This is essential for understanding how to connect routines in a flow.

    **Endpoint**: `GET /api/factory/objects/{name}/interface`

    **Why This Endpoint**:
    - You need to know which slots a routine has (for connections)
    - You need to know which events a routine emits (for connections)
    - You need to understand the activation policy
    - You're building a flow dynamically and need interface details

    **Request Example**:
    ```
    GET /api/factory/objects/data_source/interface
    ```

    **Response Example**:
    ```json
    {
      "name": "data_source",
      "type": "routine",
      "slots": [
        {
          "name": "trigger",
          "max_queue_length": 100,
          "watermark": 80
        }
      ],
      "events": [
        {
          "name": "output",
          "output_params": ["data", "index", "timestamp", "metadata"]
        }
      ],
      "activation_policy": {
        "type": "immediate",
        "config": {},
        "description": "Activate immediately when any slot receives data"
      },
      "config": {
        "name": "DataSource"
      }
    }
    ```

    **Slot Information**:
    - `name`: Slot name (use as target_slot in connections)
    - `max_queue_length`: Maximum queue capacity
    - `watermark`: Queue watermark threshold

    **Event Information**:
    - `name`: Event name (use as source_event in connections)
    - `output_params`: List of parameter names this event emits

    **Activation Policy**:
    - `type`: Policy type (immediate, batch_size, time_interval, all_slots_ready)
    - `config`: Policy configuration parameters
    - `description`: Human-readable description

    **Use Case: Building a Connection**:
    1. Get source routine interface: GET /api/factory/objects/data_source/interface
    2. Get target routine interface: GET /api/factory/objects/data_processor/interface
    3. Find matching event/slot
    4. Create connection: POST /api/flows/{flow_id}/connections
       ```json
       {
         "source_routine": "data_source",
         "source_event": "output",  // from source interface
         "target_routine": "data_processor",
         "target_slot": "input"  // from target interface
       }
       ```

    **Error Responses**:
    - `404 Not Found`: Object not found in factory
    - `400 Bad Request`: Object is not a Routine (e.g., it's a Flow)
    - `500 Internal Server Error`: Failed to inspect object interface

    **Performance Note**:
    - This endpoint creates a temporary instance to inspect the interface
    - The instance is discarded after inspection
    - Response is cached-friendly (interface doesn't change)

    **Related Endpoints**:
    - GET /api/factory/objects/{name} - Get object metadata
    - GET /api/factory/objects - List all factory objects
    - POST /api/flows/{flow_id}/routines - Add routine to flow
    - POST /api/flows/{flow_id}/connections - Create connection

    Args:
        name: Object name (factory registration name)

    Returns:
        dict: Interface information including slots, events, and activation policy

    Raises:
        HTTPException: 404 if object not found
        HTTPException: 400 if object is not a Routine
        HTTPException: 500 if interface inspection fails
    """
    factory = ObjectFactory.get_instance()

    # Check if object exists
    metadata = factory.get_metadata(name)
    if metadata is None:
        raise HTTPException(status_code=404, detail=f"Object '{name}' not found")

    # Create temporary instance to inspect interface
    try:
        instance = factory.create(name)

        # Check if it's a Routine
        from routilux.core.routine import Routine

        if not isinstance(instance, Routine):
            raise HTTPException(
                status_code=400,
                detail=f"Object '{name}' is not a Routine. Interface info only available for Routines. "
                f"Got type: {type(instance).__name__}",
            )

        # Extract interface information
        slots_info = []
        for slot_name, slot in instance.slots.items():
            slots_info.append(
                {
                    "name": slot_name,
                    "max_queue_length": slot.max_queue_length,
                    "watermark": slot.watermark,
                }
            )

        events_info = []
        for event_name, event in instance.events.items():
            events_info.append(
                {
                    "name": event_name,
                    "output_params": list(event.output_params) if event.output_params else [],
                }
            )

        # Get activation policy info
        policy_info = instance.get_activation_policy_info()

        return {
            "name": name,
            "type": "routine",
            "slots": slots_info,
            "events": events_info,
            "activation_policy": policy_info,
            "config": instance.get_all_config(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to inspect object interface: {str(e)}",
        ) from e
