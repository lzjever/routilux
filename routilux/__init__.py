"""
Routilux - Event-driven workflow orchestration framework

Provides flexible connection, state management, and workflow orchestration capabilities.
"""

from routilux.routine import Routine
from routilux.slot import Slot
from routilux.event import Event
from routilux.connection import Connection
from routilux.flow import Flow
from routilux.job_state import JobState, ExecutionRecord
from routilux.execution_tracker import ExecutionTracker
from routilux.error_handler import ErrorHandler, ErrorStrategy

# Import built-in routines
from routilux.builtin_routines import (
    # Text processing
    TextClipper,
    TextRenderer,
    ResultExtractor,
    # Utils
    TimeProvider,
    DataFlattener,
    # Data processing
    DataTransformer,
    DataValidator,
    # Control flow
    ConditionalRouter,
)

__all__ = [
    # Core classes
    "Routine",
    "Slot",
    "Event",
    "Connection",
    "Flow",
    "JobState",
    "ExecutionRecord",
    "ExecutionTracker",
    "ErrorHandler",
    "ErrorStrategy",
    # Built-in routines - Text processing
    "TextClipper",
    "TextRenderer",
    "ResultExtractor",
    # Built-in routines - Utils
    "TimeProvider",
    "DataFlattener",
    # Built-in routines - Data processing
    "DataTransformer",
    "DataValidator",
    # Built-in routines - Control flow
    "ConditionalRouter",
]

__version__ = "0.8.1"
