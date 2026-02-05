"""
Routilux - Event-driven workflow orchestration framework

Provides flexible connection, state management, and workflow orchestration capabilities.
"""

# Import analysis tools
from routilux.analysis import (
    BaseFormatter,
    RoutineAnalyzer,
    RoutineMarkdownFormatter,
    WorkflowAnalyzer,
    WorkflowD2Formatter,
    analyze_routine_file,
    analyze_workflow,
)

# Import built-in routines
from routilux.builtin_routines import (
    # Control flow
    ConditionalRouter,
    DataFlattener,
    # Data processing
    DataTransformer,
    DataValidator,
    ResultExtractor,
    # Text processing
    TextClipper,
    TextRenderer,
    # Utils
    TimeProvider,
)
from routilux.connection import Connection
from routilux.error_handler import ErrorHandler, ErrorStrategy
from routilux.event import Event

# Import exceptions
from routilux.exceptions import (
    ConfigurationError,
    ExecutionError,
    RoutiluxError,
    SerializationError,
    SlotHandlerError,
    StateError,
)
from routilux.execution_tracker import ExecutionTracker
from routilux.flow import Flow
from routilux.job_state import ExecutionRecord, JobState
from routilux.output_handler import (
    CallbackOutputHandler,
    NullOutputHandler,
    OutputHandler,
    QueueOutputHandler,
)
from routilux.routine import ExecutionContext, Routine
from routilux.slot import Slot
from routilux.validators import ValidationError, Validator

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
    # Exceptions
    "RoutiluxError",
    "ExecutionError",
    "SerializationError",
    "ConfigurationError",
    "StateError",
    "SlotHandlerError",
    "ValidationError",
    # Validators
    "Validator",
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
    # Analysis tools
    "RoutineAnalyzer",
    "analyze_routine_file",
    "WorkflowAnalyzer",
    "analyze_workflow",
    "BaseFormatter",
    "RoutineMarkdownFormatter",
    "WorkflowD2Formatter",
]

__version__ = "0.10.0"
