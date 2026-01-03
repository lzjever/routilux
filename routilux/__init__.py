"""
Routilux - Event-driven workflow orchestration framework

Provides flexible connection, state management, and workflow orchestration capabilities.
"""

from routilux.routine import Routine, ExecutionContext
from routilux.slot import Slot
from routilux.event import Event
from routilux.connection import Connection
from routilux.flow import Flow
from routilux.job_state import JobState, ExecutionRecord
from routilux.execution_tracker import ExecutionTracker
from routilux.error_handler import ErrorHandler, ErrorStrategy
from routilux.output_handler import (
    OutputHandler,
    QueueOutputHandler,
    CallbackOutputHandler,
    NullOutputHandler,
)

# Import analyzers
from routilux.routine_analyzer import RoutineAnalyzer, analyze_routine_file
from routilux.workflow_analyzer import WorkflowAnalyzer, analyze_workflow

# Import formatters
from routilux.analysis_formatters import (
    BaseFormatter,
    RoutineMarkdownFormatter,
    WorkflowD2Formatter,
)

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
    "ExecutionContext",
    "Slot",
    "Event",
    "Connection",
    "Flow",
    "JobState",
    "ExecutionRecord",
    "ExecutionTracker",
    "ErrorHandler",
    "ErrorStrategy",
    # Output handlers
    "OutputHandler",
    "QueueOutputHandler",
    "CallbackOutputHandler",
    "NullOutputHandler",
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
    # Analyzers
    "RoutineAnalyzer",
    "analyze_routine_file",
    "WorkflowAnalyzer",
    "analyze_workflow",
    # Formatters
    "BaseFormatter",
    "RoutineMarkdownFormatter",
    "WorkflowD2Formatter",
]

__version__ = "0.10.0"
