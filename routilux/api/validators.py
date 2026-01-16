"""
Request validators for API endpoints.

Provides validation functions for common request patterns.
"""

from fastapi import HTTPException
from typing import Dict, Any, Optional

from routilux.flow import Flow
from routilux.monitoring.storage import flow_store


def validate_flow_exists(flow_id: str) -> Flow:
    """Validate that flow exists.
    
    Args:
        flow_id: Flow identifier.
        
    Returns:
        Flow instance.
        
    Raises:
        HTTPException: If flow not found.
    """
    flow = flow_store.get(flow_id)
    if not flow:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "flow_not_found",
                "message": f"Flow '{flow_id}' not found",
                "flow_id": flow_id,
            },
        )
    return flow


def validate_routine_exists(flow: Flow, routine_id: str) -> None:
    """Validate that routine exists in flow.
    
    Args:
        flow: Flow instance.
        routine_id: Routine identifier.
        
    Raises:
        HTTPException: If routine not found.
    """
    if routine_id not in flow.routines:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "routine_not_found",
                "message": f"Routine '{routine_id}' not found in flow '{flow.flow_id}'",
                "flow_id": flow.flow_id,
                "routine_id": routine_id,
            },
        )


def validate_dsl_size(dsl: str, max_size: int = 1024 * 1024) -> None:
    """Validate DSL size.
    
    Args:
        dsl: DSL string.
        max_size: Maximum size in bytes (default: 1MB).
        
    Raises:
        HTTPException: If DSL too large.
    """
    if len(dsl.encode("utf-8")) > max_size:
        raise HTTPException(
            status_code=413,
            detail={
                "error": "dsl_too_large",
                "message": f"DSL size exceeds maximum of {max_size} bytes",
                "max_size": max_size,
            },
        )


def validate_routine_id_conflict(flow: Flow, routine_id: str) -> None:
    """Validate that routine_id doesn't conflict with existing routine.
    
    Args:
        flow: Flow instance.
        routine_id: Routine identifier to check.
        
    Raises:
        HTTPException: If routine_id already exists.
    """
    if routine_id in flow.routines:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "routine_id_conflict",
                "message": f"Routine '{routine_id}' already exists in flow '{flow.flow_id}'",
                "flow_id": flow.flow_id,
                "routine_id": routine_id,
            },
        )
