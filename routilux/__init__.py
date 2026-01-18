"""
Routilux - Event-driven workflow orchestration framework

Provides flexible connection, state management, and workflow orchestration capabilities.
"""

# Core classes from core module
# Activation policies
from routilux.activation_policies import (
    all_slots_ready_policy,
    batch_size_policy,
    breakpoint_policy,
    custom_policy,
    immediate_policy,
    time_interval_policy,
)
from routilux.core.connection import Connection
from routilux.core.context import JobContext
from routilux.core.error import ErrorHandler, ErrorStrategy
from routilux.core.event import Event

# Worker management (renamed from Job*)
from routilux.core.executor import WorkerExecutor
from routilux.core.flow import Flow
from routilux.core.manager import WorkerManager, get_worker_manager, reset_worker_manager

# Output handling
from routilux.core.output import (
    RoutedStdout,
    clear_job_output,
    get_job_output,
    install_routed_stdout,
    uninstall_routed_stdout,
)
from routilux.core.registry import (
    FlowRegistry,
    WorkerRegistry,
    get_flow_registry,
    get_worker_registry,
)
from routilux.core.routine import ExecutionContext, Routine
from routilux.core.runtime import Runtime
from routilux.core.slot import Slot
from routilux.core.status import ExecutionStatus, JobStatus, RoutineStatus
from routilux.core.worker import ExecutionRecord, WorkerState

# Flow builder (still in flow/ for now)
from routilux.flow.builder import FlowBuilder

# Factory
from routilux.tools.factory import ObjectFactory, ObjectMetadata

# Testing utilities
from routilux.tools.testing import RoutineTester

# Analysis tools (optional)
try:
    from routilux.tools.analysis import (  # noqa: F401
        BaseFormatter,
        RoutineAnalyzer,
        RoutineMarkdownFormatter,
        WorkflowAnalyzer,
        WorkflowD2Formatter,
        analyze_routine_file,
        analyze_workflow,
    )

    _analysis_available = True
except ImportError:
    _analysis_available = False

__all__ = [
    # Core classes
    "Routine",
    "ExecutionContext",
    "Slot",
    "Event",
    "Connection",
    "Flow",
    "FlowBuilder",
    # Worker/Job state (renamed)
    "WorkerState",
    "ExecutionRecord",
    "JobContext",
    # Error handling
    "ErrorHandler",
    "ErrorStrategy",
    # Worker management (renamed from Job*)
    "WorkerManager",
    "WorkerExecutor",
    "get_worker_manager",
    "reset_worker_manager",
    # Status enums
    "ExecutionStatus",
    "RoutineStatus",
    "JobStatus",
    # Runtime
    "Runtime",
    # Registry
    "FlowRegistry",
    "WorkerRegistry",
    "get_flow_registry",
    "get_worker_registry",
    # Output handling
    "RoutedStdout",
    "install_routed_stdout",
    "uninstall_routed_stdout",
    "get_job_output",
    "clear_job_output",
    # Factory
    "ObjectFactory",
    "ObjectMetadata",
    # Testing utilities
    "RoutineTester",
    # Activation policies
    "immediate_policy",
    "all_slots_ready_policy",
    "batch_size_policy",
    "time_interval_policy",
    "custom_policy",
    "breakpoint_policy",
]

# Add analysis tools if available
if _analysis_available:
    __all__.extend(
        [
            "RoutineAnalyzer",
            "analyze_routine_file",
            "WorkflowAnalyzer",
            "analyze_workflow",
            "BaseFormatter",
            "RoutineMarkdownFormatter",
            "WorkflowD2Formatter",
        ]
    )

# Note: All backward compatibility aliases removed
# Use WorkerState, WorkerManager, WorkerExecutor, get_worker_manager instead

__version__ = "0.10.0"
