"""
Routilux Core - Core workflow engine.

Only depends on serilux, can be used standalone without monitoring or API.

Example:
    >>> from routilux.core import Flow, Routine, Runtime
    >>> from routilux.core import install_routed_stdout, get_job_output
    >>>
    >>> # Install stdout routing at program startup
    >>> install_routed_stdout()
    >>>
    >>> class MyRoutine(Routine):
    ...     def setup(self):
    ...         self.add_slot("input")
    ...         self.add_event("output")
    ...
    ...     def logic(self, input_data, **kwargs):
    ...         print(f"Processing: {input_data}")  # Auto-routed to job
    ...         self.emit("output", {"result": "processed"})
    >>>
    >>> flow = Flow()
    >>> flow.add_routine(MyRoutine(), "processor")
    >>>
    >>> runtime = Runtime()
    >>> worker, job = runtime.post("my_flow", "processor", "input", {"data": "test"})
    >>>
    >>> # Get job's stdout output
    >>> output = get_job_output(job.job_id)
"""

# Status enums
from routilux.core.connection import Connection

# Context management
from routilux.core.context import (
    JobContext,
    get_current_job,
    get_current_job_id,
    get_current_worker_state,
    set_current_job,
    set_current_worker_state,
)

# Error handling
from routilux.core.error import ErrorHandler, ErrorStrategy
from routilux.core.event import Event

# Worker executor and manager
from routilux.core.executor import WorkerExecutor

# Flow
from routilux.core.flow import Flow, RoutineConfig, WorkerNotRunningError

# Hooks interface
from routilux.core.hooks import (
    ExecutionHooksInterface,
    NullExecutionHooks,
    get_execution_hooks,
    reset_execution_hooks,
    set_execution_hooks,
)
from routilux.core.manager import WorkerManager, get_worker_manager, reset_worker_manager

# Output capture
from routilux.core.output import (
    RoutedStdout,
    clear_job_output,
    get_job_output,
    get_routed_stdout,
    install_routed_stdout,
    uninstall_routed_stdout,
)
from routilux.core.registry import (
    FlowRegistry,
    WorkerRegistry,
    get_flow_registry,
    get_worker_registry,
)

# Routine
from routilux.core.routine import (
    ExecutionContext,
    Routine,
    get_current_worker_state,
    set_current_worker_state,
)

# Runtime
from routilux.core.runtime import Runtime

# Core classes
from routilux.core.slot import Slot, SlotDataPoint, SlotQueueFullError
from routilux.core.status import ExecutionStatus, JobStatus, RoutineStatus
from routilux.core.task import EventRoutingTask, SlotActivationTask, TaskPriority

# Worker state and registry
from routilux.core.worker import ExecutionRecord, WorkerState

__all__ = [
    # Status enums
    "ExecutionStatus",
    "RoutineStatus",
    "JobStatus",
    # Context management
    "JobContext",
    "get_current_job",
    "get_current_job_id",
    "get_current_worker_state",
    "set_current_job",
    "set_current_worker_state",
    # Output capture
    "RoutedStdout",
    "install_routed_stdout",
    "uninstall_routed_stdout",
    "get_routed_stdout",
    "get_job_output",
    "clear_job_output",
    # Error handling
    "ErrorHandler",
    "ErrorStrategy",
    # Hooks
    "ExecutionHooksInterface",
    "NullExecutionHooks",
    "get_execution_hooks",
    "set_execution_hooks",
    "reset_execution_hooks",
    # Core classes
    "Slot",
    "SlotDataPoint",
    "SlotQueueFullError",
    "Event",
    "Connection",
    "TaskPriority",
    "SlotActivationTask",
    "EventRoutingTask",
    # Worker state and registry
    "WorkerState",
    "ExecutionRecord",
    "FlowRegistry",
    "WorkerRegistry",
    "get_flow_registry",
    "get_worker_registry",
    # Routine
    "Routine",
    "ExecutionContext",
    "get_current_worker_state",
    "set_current_worker_state",
    # Flow
    "Flow",
    "RoutineConfig",
    "WorkerNotRunningError",
    # Worker executor and manager
    "WorkerExecutor",
    "WorkerManager",
    "get_worker_manager",
    "reset_worker_manager",
    # Runtime
    "Runtime",
]
