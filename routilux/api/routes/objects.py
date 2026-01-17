"""
Object discovery API routes.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from routilux.api.middleware.auth import RequireAuth
from routilux.api.models.object import ObjectListResponse, ObjectMetadataResponse
from routilux.factory.factory import ObjectFactory

router = APIRouter()


@router.get("/objects", response_model=ObjectListResponse, dependencies=[RequireAuth])
async def list_objects(category: Optional[str] = Query(None, description="Filter by category")):
    """List all available objects in the factory.

    Args:
        category: Optional category filter.

    Returns:
        List of available objects.
    """
    factory = ObjectFactory.get_instance()
    objects = factory.list_available(category=category)
    return ObjectListResponse(objects=objects, total=len(objects))


@router.get("/objects/{name}", response_model=ObjectMetadataResponse, dependencies=[RequireAuth])
async def get_object_metadata(name: str):
    """Get metadata for a specific object.

    Args:
        name: Object name.

    Returns:
        Object metadata.

    Raises:
        HTTPException: If object not found.
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
