"""
Pydantic models for Object API.

All models include detailed field descriptions and examples for frontend developers.
"""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ObjectMetadataResponse(BaseModel):
    """Response model for object metadata.

    Contains metadata about a registered object in the factory.
    Use this to understand what an object does and how to configure it.

    **Example Response**:
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

    **Note**: This endpoint returns metadata only. To get interface information (slots, events),
    use GET /api/factory/objects/{name}/interface. To get object_type (routine/flow), use GET /api/factory/objects.
    """

    name: str = Field(
        ...,
        description="Unique name of the object in the factory. Use this name when creating routines from factory.",
        examples=["data_source"],
    )
    description: str = Field(
        ...,
        description="Human-readable description of what this object does.",
        examples=["Generates sample data with metadata"],
    )
    category: str = Field(
        ...,
        description="Category grouping for this object. Useful for filtering and organization. "
        "Common categories: 'data_generation', 'validation', 'transformation', 'monitoring', etc.",
        examples=["data_generation"],
    )
    tags: List[str] = Field(
        ...,
        description="List of tags associated with this object. Useful for searching and filtering. "
        "Tags are lowercase and typically describe the object's purpose or features.",
        examples=[["source", "generator"]],
    )
    example_config: Dict[str, Any] = Field(
        ...,
        description="Example configuration dictionary showing how to configure this object. "
        "Use this as a reference when creating routines. "
        "The actual config you provide will be merged with defaults.",
        examples=[{"name": "MyDataSource"}],
    )
    version: str = Field(
        ...,
        description="Version string for this object. Useful for tracking object versions.",
        examples=["1.0.0"],
    )


class ObjectInfo(BaseModel):
    """Information about an available object in the factory.

    This is a summary view used in the object list endpoint.
    For detailed metadata, use GET /api/factory/objects/{name}.
    For interface information (slots/events), use GET /api/factory/objects/{name}/interface.

    **Example Response**:
    ```json
    {
      "name": "data_source",
      "type": "class",
      "description": "Generates sample data with metadata",
      "category": "data_generation",
      "tags": ["source", "generator"],
      "example_config": {"name": "Exampledata_source"},
      "version": "1.0.0"
    }
    ```
    """

    name: str = Field(
        ...,
        description="Unique name of the object in the factory.",
        examples=["data_source"],
    )
    type: str = Field(
        ...,
        description="Type of prototype: 'class' (class-based prototype) or 'instance' (instance-based prototype). "
        "Class prototypes create new instances each time. Instance prototypes clone a configured instance. "
        "This describes HOW the object is stored, not WHAT it is.",
        examples=["class"],
    )
    object_type: str = Field(
        ...,
        description="Type of object: 'routine' or 'flow'. "
        "This distinguishes between Routines (executable components) and Flows (workflow definitions). "
        "Use this field to filter objects by type. "
        "Routines can be added to flows. Flows can be used as templates to create new flows.",
        examples=["routine"],
    )
    description: str = Field(
        ...,
        description="Human-readable description of what this object does.",
        examples=["Generates sample data with metadata"],
    )
    category: str = Field(
        ...,
        description="Category grouping for this object.",
        examples=["data_generation"],
    )
    tags: List[str] = Field(
        ...,
        description="List of tags for searching and filtering.",
        examples=[["source", "generator"]],
    )
    example_config: Dict[str, Any] = Field(
        ...,
        description="Example configuration dictionary.",
        examples=[{"name": "MyDataSource"}],
    )
    version: str = Field(
        ...,
        description="Version string for this object.",
        examples=["1.0.0"],
    )


class ObjectListResponse(BaseModel):
    """Response model for object list.

    Returns a list of all objects registered in the factory, optionally filtered by category.

    **Example Response**:
    ```json
    {
      "objects": [
        {
          "name": "data_source",
          "type": "class",
          "description": "Generates sample data",
          "category": "data_generation",
          "tags": ["source"],
          "example_config": {},
          "version": "1.0.0"
        }
      ],
      "total": 12
    }
    ```

    **Filtering**: Use the `category` query parameter to filter objects by category.
    Example: GET /api/factory/objects?category=data_generation
    """

    objects: List[ObjectInfo] = Field(
        ...,
        description="List of objects matching the filter criteria (if category filter is applied). "
        "Each object contains metadata about a registered factory prototype.",
    )
    total: int = Field(
        ...,
        description="Total number of objects in the list (after filtering, if applied).",
        examples=[12],
    )
