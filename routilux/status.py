"""
Status enums for Routilux execution and routine states.

Provides type-safe status values instead of magic strings.
"""

from enum import Enum


class ExecutionStatus(str, Enum):
    """Flow execution status.
    
    These values represent the overall status of a Flow execution.
    Use these enums instead of string literals for type safety and IDE support.
    
    Examples:
        >>> from routilux import ExecutionStatus
        >>> if job_state.status == ExecutionStatus.COMPLETED:
        ...     print("Flow completed successfully")
        
        >>> # Can still compare with strings (backward compatible)
        >>> if job_state.status == "completed":
        ...     print("Flow completed")
    """
    
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RoutineStatus(str, Enum):
    """Routine execution status.
    
    These values represent the status of individual routine execution.
    Use these enums instead of string literals for type safety and IDE support.
    
    Examples:
        >>> from routilux import RoutineStatus
        >>> state = job_state.get_routine_state("my_routine")
        >>> if state and state["status"] == RoutineStatus.COMPLETED:
        ...     print("Routine completed successfully")
        
        >>> # Can still compare with strings (backward compatible)
        >>> if state["status"] == "completed":
        ...     print("Routine completed")
    """
    
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ERROR_CONTINUED = "error_continued"
    SKIPPED = "skipped"

