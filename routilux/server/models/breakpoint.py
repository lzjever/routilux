"""
Pydantic models for Breakpoint API.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class BreakpointUpdateRequest(BaseModel):
    """Request model for updating a breakpoint (enable/disable)."""

    enabled: bool


class BreakpointCreateRequest(BaseModel):
    """Request model for creating a slot-level breakpoint."""

    routine_id: str = Field(..., description="Routine ID where the slot is located")
    slot_name: str = Field(..., description="Slot name where breakpoint is set")
    condition: Optional[str] = Field(
        None,
        description="Optional Python expression to evaluate (e.g., \"data.get('value') > 10\")"
    )
    enabled: bool = Field(True, description="Whether breakpoint is active")


class BreakpointResponse(BaseModel):
    """Response model for breakpoint details."""

    breakpoint_id: str = Field(..., description="Unique breakpoint identifier")
    job_id: str = Field(..., description="Job ID this breakpoint applies to")
    routine_id: str = Field(..., description="Routine ID where the slot is located")
    slot_name: str = Field(..., description="Slot name where breakpoint is set")
    condition: Optional[str] = Field(None, description="Optional condition expression")
    enabled: bool = Field(..., description="Whether breakpoint is active")
    hit_count: int = Field(..., description="Number of times breakpoint has been hit")


class BreakpointListResponse(BaseModel):
    """Response model for breakpoint list."""

    breakpoints: List[BreakpointResponse]
    total: int
