"""
Pydantic models for Flow API.

All models include detailed field descriptions and examples for frontend developers.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FlowCreateRequest(BaseModel):
    """Request model for creating a new flow.

    You can create a flow in three ways:
    1. **Empty flow**: Provide only `flow_id` (or let system generate one)
    2. **From YAML DSL**: Provide `dsl` as a YAML string
    3. **From JSON DSL**: Provide `dsl_dict` as a JSON object

    **Example 1: Create Empty Flow**:
    ```json
    {
      "flow_id": "my_new_flow"
    }
    ```

    **Example 2: Create from YAML DSL**:
    ```json
    {
      "flow_id": "my_flow",
      "dsl": "flow_id: my_flow\nroutines:\n  source:\n    class: DataSource\n    config:\n      name: Source"
    }
    ```

    **Example 3: Create from JSON DSL**:
    ```json
    {
      "flow_id": "my_flow",
      "dsl_dict": {
        "flow_id": "my_flow",
        "routines": {
          "source": {
            "class": "DataSource",
            "config": {"name": "Source"}
          }
        },
        "connections": []
      }
    }
    ```

    **Note**: Only one of `dsl` or `dsl_dict` should be provided. If both are provided, `dsl` takes precedence.
    """

    flow_id: Optional[str] = Field(
        None,
        description="Optional flow identifier. If not provided, a UUID will be automatically generated. "
        "Must be unique across all flows. Use this ID to reference the flow in subsequent API calls.",
        examples=["my_data_processing_flow"],
    )
    dsl: Optional[str] = Field(
        None,
        description="YAML DSL string defining the flow structure. "
        "If provided, the flow will be created from this YAML definition. "
        "See DSL documentation for format details. "
        "Mutually exclusive with `dsl_dict` - if both are provided, `dsl` takes precedence.",
        examples=[
            """flow_id: my_flow
routines:
  source:
    class: DataSource
    config:
      name: Source
connections: []"""
        ],
    )
    dsl_dict: Optional[Dict[str, Any]] = Field(
        None,
        description="JSON dictionary defining the flow structure. "
        "If provided, the flow will be created from this JSON definition. "
        "Mutually exclusive with `dsl` - if both are provided, `dsl` takes precedence. "
        "This is useful when building flows programmatically.",
        examples=[
            {
                "flow_id": "my_flow",
                "routines": {
                    "source": {
                        "class": "DataSource",
                        "config": {"name": "Source"},
                    }
                },
                "connections": [],
            }
        ],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"flow_id": "my_new_flow"},
                {
                    "flow_id": "my_flow",
                    "dsl": "flow_id: my_flow\nroutines:\n  source:\n    class: DataSource",
                },
                {
                    "flow_id": "my_flow",
                    "dsl_dict": {
                        "flow_id": "my_flow",
                        "routines": {"source": {"class": "DataSource"}},
                        "connections": [],
                    },
                },
            ]
        }
    }


class AddRoutineRequest(BaseModel):
    """Request model for adding a routine to an existing flow.

    This endpoint allows you to dynamically add routines to a flow after it's been created.
    The routine can be created from:
    1. **Factory name**: Use a registered factory name (e.g., "data_source")
    2. **Class path**: Use a full class path (e.g., "mymodule.DataProcessor")

    **Factory names are preferred** because they're safer and don't require knowing internal class paths.

    **Example Request**:
    ```json
    {
      "routine_id": "my_processor",
      "object_name": "data_transformer",
      "config": {
        "name": "MyProcessor",
        "transformation": "uppercase"
      }
    }
    ```

    **Error Cases**:
    - 404: Flow not found
    - 400: Routine ID already exists in flow
    - 400: Invalid object_name (not in factory and invalid class path)
    - 400: Failed to load routine class
    """

    routine_id: str = Field(
        ...,
        description="Unique identifier for this routine within the flow. "
        "Must be unique within the flow. Use this ID to reference the routine in connections and other operations.",
        examples=["data_processor"],
    )
    object_name: str = Field(
        ...,
        description="Name of the routine to create. Can be either: "
        "1. A factory name (recommended): Registered name in ObjectFactory (e.g., 'data_source', 'data_transformer') "
        "2. A class path: Full module path to the class (e.g., 'mymodule.DataProcessor') "
        "Factory names are checked first, then class paths. Use factory names when possible for better security and discoverability.",
        examples=["data_transformer"],
    )
    config: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional configuration dictionary to pass to the routine. "
        "These values will be merged with any default configuration from the factory prototype. "
        "The exact configuration options depend on the routine type. "
        "Common options include: 'name', 'timeout', 'processing_delay', etc.",
        examples=[{"name": "MyProcessor", "transformation": "uppercase", "timeout": 30}],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "routine_id": "data_source",
                    "object_name": "data_source",
                    "config": {"name": "Source"},
                },
                {
                    "routine_id": "processor",
                    "object_name": "data_transformer",
                    "config": {"transformation": "uppercase"},
                },
                {
                    "routine_id": "custom_processor",
                    "object_name": "mymodule.CustomProcessor",
                    "config": {"custom_param": "value"},
                },
            ]
        }
    }


class AddConnectionRequest(BaseModel):
    """Request model for adding a connection between routines in a flow.

    Connections define how data flows from one routine to another:
    - **Source**: The routine that emits the event
    - **Target**: The routine that receives data in its slot

    **Example Request**:
    ```json
    {
      "source_routine": "data_source",
      "source_event": "output",
      "target_routine": "data_processor",
      "target_slot": "input"
    }
    ```

    **Validation**:
    - Both source and target routines must exist in the flow
    - Source routine must have the specified event
    - Target routine must have the specified slot
    - Event output parameters must be compatible with slot expectations

    **Error Cases**:
    - 404: Flow, source routine, or target routine not found
    - 400: Source event doesn't exist
    - 400: Target slot doesn't exist
    - 400: Invalid connection (e.g., circular dependency)
    """

    source_routine: str = Field(
        ...,
        description="ID of the routine that emits the event (source of data). "
        "Must be a routine that exists in the flow.",
        examples=["data_source"],
    )
    source_event: str = Field(
        ...,
        description="Name of the event emitted by the source routine. "
        "Must be an event defined in the source routine. "
        "Use GET /api/factory/objects/{name}/interface to discover available events.",
        examples=["output"],
    )
    target_routine: str = Field(
        ...,
        description="ID of the routine that receives the data (target). "
        "Must be a routine that exists in the flow.",
        examples=["data_processor"],
    )
    target_slot: str = Field(
        ...,
        description="Name of the input slot in the target routine that receives the data. "
        "Must be a slot defined in the target routine. "
        "Use GET /api/factory/objects/{name}/interface to discover available slots.",
        examples=["input"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "source_routine": "data_source",
                    "source_event": "output",
                    "target_routine": "data_processor",
                    "target_slot": "input",
                },
                {
                    "source_routine": "validator",
                    "source_event": "valid",
                    "target_routine": "processor",
                    "target_slot": "input",
                },
            ]
        }
    }


class RoutineInfo(BaseModel):
    """Information about a routine in a flow.

    Contains all metadata about a routine including its interface (slots and events),
    configuration, and class information.

    **Example Response**:
    ```json
    {
      "routine_id": "data_processor",
      "class_name": "DataTransformer",
      "slots": ["input", "secondary"],
      "events": ["output", "error"],
      "config": {
        "name": "DataProcessor",
        "transformation": "uppercase"
      }
    }
    ```
    """

    routine_id: str = Field(
        ...,
        description="Unique identifier of this routine within the flow.",
        examples=["data_processor"],
    )
    class_name: str = Field(
        ...,
        description="Name of the routine class (e.g., 'DataTransformer', 'DataSource'). "
        "This is the Python class name, useful for debugging and logging.",
        examples=["DataTransformer"],
    )
    slots: List[str] = Field(
        ...,
        description="List of input slot names defined in this routine. "
        "These are the slots that can receive data from other routines' events. "
        "Use these names when creating connections (target_slot).",
        examples=[["input", "secondary"]],
    )
    events: List[str] = Field(
        ...,
        description="List of output event names defined in this routine. "
        "These are the events that this routine can emit to send data to other routines. "
        "Use these names when creating connections (source_event).",
        examples=[["output", "error"]],
    )
    config: Dict[str, Any] = Field(
        ...,
        description="Configuration dictionary for this routine. "
        "Contains all configuration parameters set on the routine instance. "
        "This is a read-only snapshot of the routine's configuration.",
        examples=[{"name": "DataProcessor", "transformation": "uppercase", "timeout": 30}],
    )


class ConnectionInfo(BaseModel):
    """Information about a connection between routines in a flow.

    Represents a data flow path from one routine's event to another routine's slot.

    **Example Response**:
    ```json
    {
      "connection_id": "conn_0",
      "source_routine": "data_source",
      "source_event": "output",
      "target_routine": "data_processor",
      "target_slot": "input"
    }
    ```

    **Connection ID**: Auto-generated identifier for this connection.
    Used when deleting connections by index.
    """

    connection_id: str = Field(
        ...,
        description="Auto-generated identifier for this connection. "
        "Format: 'conn_{index}'. Used when deleting connections.",
        examples=["conn_0"],
    )
    source_routine: str = Field(
        ...,
        description="ID of the routine that emits data (source).",
        examples=["data_source"],
    )
    source_event: str = Field(
        ...,
        description="Name of the event that emits data from the source routine.",
        examples=["output"],
    )
    target_routine: str = Field(
        ...,
        description="ID of the routine that receives data (target).",
        examples=["data_processor"],
    )
    target_slot: str = Field(
        ...,
        description="Name of the slot that receives data in the target routine.",
        examples=["input"],
    )


class FlowResponse(BaseModel):
    """Response model for flow details.

    Contains complete information about a flow including all routines and connections.

    **Example Response**:
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
        "data_processor": {
          "routine_id": "data_processor",
          "class_name": "DataTransformer",
          "slots": ["input"],
          "events": ["output"],
          "config": {"name": "Processor"}
        }
      },
      "connections": [
        {
          "connection_id": "conn_0",
          "source_routine": "data_source",
          "source_event": "output",
          "target_routine": "data_processor",
          "target_slot": "input"
        }
      ],
      "created_at": "2025-01-15T10:00:00",
      "updated_at": "2025-01-15T10:05:00"
    }
    ```
    """

    flow_id: str = Field(
        ...,
        description="Unique identifier for this flow. Use this ID to reference the flow in API calls.",
        examples=["data_processing_flow"],
    )
    routines: Dict[str, RoutineInfo] = Field(
        ...,
        description="Dictionary mapping routine IDs to routine information. "
        "Keys are routine IDs, values are RoutineInfo objects containing slots, events, and config.",
        examples=[
            {
                "data_source": {
                    "routine_id": "data_source",
                    "class_name": "DataSource",
                    "slots": ["trigger"],
                    "events": ["output"],
                    "config": {"name": "Source"},
                }
            }
        ],
    )
    connections: List[ConnectionInfo] = Field(
        ...,
        description="List of all connections in the flow. "
        "Each connection represents a data flow path from a source routine's event to a target routine's slot.",
        examples=[
            [
                {
                    "connection_id": "conn_0",
                    "source_routine": "data_source",
                    "source_event": "output",
                    "target_routine": "data_processor",
                    "target_slot": "input",
                }
            ]
        ],
    )
    created_at: Optional[datetime] = Field(
        None,
        description="Timestamp when the flow was created. ISO 8601 format.",
        examples=["2025-01-15T10:00:00"],
    )
    updated_at: Optional[datetime] = Field(
        None,
        description="Timestamp when the flow was last updated. ISO 8601 format.",
        examples=["2025-01-15T10:05:00"],
    )


class FlowListResponse(BaseModel):
    """Response model for flow list.

    Returns a list of all flows with total count.

    **Example Response**:
    ```json
    {
      "flows": [
        {
          "flow_id": "flow_1",
          "routines": {...},
          "connections": [...]
        }
      ],
      "total": 10
    }
    ```
    """

    flows: List[FlowResponse] = Field(
        ...,
        description="List of all flows in the system. Each flow contains complete information about routines and connections.",
    )
    total: int = Field(
        ...,
        description="Total number of flows in the system.",
        examples=[10],
    )
