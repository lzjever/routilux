"""
Pydantic models for Monitoring API.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RoutineMetricsResponse(BaseModel):
    """Response model for routine metrics."""

    routine_id: str
    execution_count: int
    total_duration: float
    avg_duration: float
    min_duration: Optional[float]
    max_duration: Optional[float]
    error_count: int
    last_execution: Optional[datetime]


class ExecutionMetricsResponse(BaseModel):
    """Response model for execution metrics."""

    job_id: str
    flow_id: str
    start_time: datetime
    end_time: Optional[datetime]
    duration: Optional[float]
    routine_metrics: Dict[str, RoutineMetricsResponse]
    total_events: int
    total_slot_calls: int
    total_event_emits: int
    errors: List[Dict[str, Any]]


class ExecutionEventResponse(BaseModel):
    """Response model for execution event."""

    event_id: str
    job_id: str
    routine_id: str
    event_type: str
    timestamp: datetime
    data: Dict[str, Any]
    duration: Optional[float]
    status: Optional[str]


class ExecutionTraceResponse(BaseModel):
    """Response model for execution trace."""

    events: List[ExecutionEventResponse]
    total: int


class SlotQueueStatus(BaseModel):
    """Slot queue status for monitoring."""

    slot_name: str = Field(..., description="Slot name")
    routine_id: str = Field(..., description="Routine ID that owns this slot")
    unconsumed_count: int = Field(..., description="Number of unconsumed data points")
    total_count: int = Field(..., description="Total number of data points in queue")
    max_length: int = Field(..., description="Maximum queue length")
    watermark_threshold: int = Field(..., description="Watermark threshold for auto-shrink")
    usage_percentage: float = Field(
        ..., ge=0.0, le=1.0, description="Queue usage percentage (0.0-1.0)"
    )
    pressure_level: str = Field(..., description="Pressure level: low, medium, high, critical")
    is_full: bool = Field(..., description="Whether queue is full")
    is_near_full: bool = Field(..., description="Whether queue is near full (above watermark)")


class RoutineExecutionStatus(BaseModel):
    """Routine execution status for monitoring."""

    routine_id: str = Field(..., description="Routine ID")
    is_active: bool = Field(..., description="Whether routine is currently executing")
    status: str = Field(..., description="Execution status: pending, running, completed, failed")
    last_execution_time: Optional[datetime] = Field(None, description="Last execution timestamp")
    execution_count: int = Field(0, description="Total number of executions")
    error_count: int = Field(0, description="Total number of errors")
    active_thread_count: int = Field(
        0, description="Number of active threads executing this routine"
    )


class RoutineInfo(BaseModel):
    """Routine metadata information."""

    routine_id: str = Field(..., description="Routine ID")
    routine_type: str = Field(..., description="Routine class name")
    activation_policy: Dict[str, Any] = Field(
        ..., description="Activation policy type and configuration"
    )
    config: Dict[str, Any] = Field(..., description="Routine configuration (_config)")
    slots: List[str] = Field(..., description="List of slot names")
    events: List[str] = Field(..., description="List of event names")


class RoutineMonitoringData(BaseModel):
    """Complete monitoring data for a routine."""

    routine_id: str = Field(..., description="Routine ID")
    execution_status: RoutineExecutionStatus = Field(..., description="Execution status")
    queue_status: List[SlotQueueStatus] = Field(..., description="Queue status for all slots")
    info: RoutineInfo = Field(..., description="Routine metadata information")


class JobMonitoringData(BaseModel):
    """Complete monitoring data for a job."""

    job_id: str = Field(..., description="Job ID")
    flow_id: str = Field(..., description="Flow ID")
    job_status: str = Field(..., description="Job execution status")
    routines: Dict[str, RoutineMonitoringData] = Field(
        ..., description="Monitoring data for all routines"
    )
    updated_at: datetime = Field(..., description="Last update timestamp")
