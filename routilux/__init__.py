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
from routilux.connection import Connection
from routilux.error_handler import ErrorHandler, ErrorStrategy
from routilux.event import Event
from routilux.execution_tracker import ExecutionTracker
from routilux.flow import Flow
from routilux.flow.builder import FlowBuilder
from routilux.job_state import ExecutionRecord, JobState
from routilux.output_handler import (
    CallbackOutputHandler,
    NullOutputHandler,
    OutputHandler,
    QueueOutputHandler,
)
from routilux.routine import ExecutionContext, Routine
from routilux.slot import Slot
from routilux.status import ExecutionStatus, RoutineStatus

# Import job management
from routilux.job_executor import JobExecutor
from routilux.job_manager import GlobalJobManager, get_job_manager, reset_job_manager

# Import testing utilities
from routilux.testing import RoutineTester

__all__ = [
    # Core classes
    "Routine",
    "ExecutionContext",
    "Slot",
    "Event",
    "Connection",
    "Flow",
    "FlowBuilder",
    "JobState",
    "ExecutionRecord",
    "ExecutionTracker",
    "ErrorHandler",
    "ErrorStrategy",
    # Job management
    "GlobalJobManager",
    "JobExecutor",
    "get_job_manager",
    "reset_job_manager",
    # Status enums
    "ExecutionStatus",
    "RoutineStatus",
    # Output handlers
    "OutputHandler",
    "QueueOutputHandler",
    "CallbackOutputHandler",
    "NullOutputHandler",
    # Analysis tools
    "RoutineAnalyzer",
    "analyze_routine_file",
    "WorkflowAnalyzer",
    "analyze_workflow",
    "BaseFormatter",
    "RoutineMarkdownFormatter",
    "WorkflowD2Formatter",
    # Testing utilities
    "RoutineTester",
]

__version__ = "0.10.0"
