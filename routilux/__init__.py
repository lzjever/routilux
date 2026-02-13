"""
Routilux - Event-driven workflow orchestration framework

Provides flexible workflow orchestration capabilities using the new core architecture.
For the core workflow engine, import from routilux.core:

    from routilux.core import Flow, Routine, Runtime
"""

# Import from new core architecture - only what's exported
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
    # Core Patterns
    Aggregator,
    Batcher,
    ConditionalRouter,
    # Data Processing
    DataTransformer,
    DataValidator,
    Debouncer,
    Filter,
    Mapper,
    ResultExtractor,
    # Reliability
    RetryHandler,
    SchemaValidator,
    Splitter,
)
from routilux.core import (
    Connection,
    # Error handling
    ErrorHandler,
    ErrorStrategy,
    Event,
    EventRoutingTask,
    ExecutionContext,
    ExecutionHooksInterface,
    ExecutionRecord,
    ExecutionStatus,
    Flow,
    FlowRegistry,
    JobContext,
    JobStatus,
    NullExecutionHooks,
    RoutedStdout,
    Routine,
    RoutineConfig,
    RoutineStatus,
    Runtime,
    Slot,
    SlotActivationTask,
    SlotDataPoint,
    SlotQueueFullError,
    TaskPriority,
    WorkerExecutor,
    WorkerManager,
    WorkerNotRunningError,
    WorkerRegistry,
    WorkerState,
    # Functions
    clear_job_output,
    get_current_job,
    get_current_job_id,
    get_current_worker_state,
    get_execution_hooks,
    get_flow_registry,
    get_job_output,
    get_routed_stdout,
    get_worker_manager,
    get_worker_registry,
    install_routed_stdout,
    reset_execution_hooks,
    reset_worker_manager,
    set_current_job,
    set_current_worker_state,
    set_execution_hooks,
    uninstall_routed_stdout,
)

# Import decorators
from routilux.decorators import routine, routine_class

# Import exceptions (these are still useful utilities)
from routilux.exceptions import (
    ConfigurationError,
    RoutiluxError,
    SerializationError,
    SlotHandlerError,
    StateError,
)

# Import metrics (still useful)
from routilux.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsCollector,
    MetricTimer,
)

# Import simplified API
from routilux.simple import pipeline, run_async, run_sync

# Import validators (still useful)
from routilux.validators import ValidationError, Validator

__all__ = [
    # Core classes (from new core architecture)
    "Routine",
    "ExecutionContext",
    "JobContext",
    "Slot",
    "Event",
    "Connection",
    "Flow",
    "RoutineConfig",
    "Runtime",
    "WorkerState",
    "ExecutionRecord",
    "WorkerExecutor",
    "WorkerManager",
    "FlowRegistry",
    "WorkerRegistry",
    # Status enums
    "ExecutionStatus",
    "RoutineStatus",
    "JobStatus",
    # Task classes
    "TaskPriority",
    "SlotActivationTask",
    "EventRoutingTask",
    # Slot utilities
    "SlotDataPoint",
    "SlotQueueFullError",
    # Error handling
    "ErrorHandler",
    "ErrorStrategy",
    # Hooks
    "ExecutionHooksInterface",
    "NullExecutionHooks",
    # Output handling
    "RoutedStdout",
    # Worker management
    "WorkerNotRunningError",
    # Convenience functions
    "get_current_job",
    "get_current_job_id",
    "get_current_worker_state",
    "set_current_job",
    "set_current_worker_state",
    "get_execution_hooks",
    "set_execution_hooks",
    "reset_execution_hooks",
    "get_flow_registry",
    "get_worker_registry",
    "get_worker_manager",
    "reset_worker_manager",
    "install_routed_stdout",
    "uninstall_routed_stdout",
    "get_routed_stdout",
    "get_job_output",
    "clear_job_output",
    # Exceptions (utility module)
    "RoutiluxError",
    "SerializationError",
    "ConfigurationError",
    "StateError",
    "SlotHandlerError",
    "ValidationError",
    "Validator",
    # Metrics (utility module)
    "MetricsCollector",
    "Counter",
    "Gauge",
    "Histogram",
    "MetricTimer",
    # Decorators
    "routine",
    "routine_class",
    # Simplified API
    "pipeline",
    "run_sync",
    "run_async",
    # Built-in routines - Core Patterns
    "ConditionalRouter",
    "Aggregator",
    "Batcher",
    "Debouncer",
    "Splitter",
    # Built-in routines - Data Processing
    "ResultExtractor",
    "Mapper",
    "SchemaValidator",
    "Filter",
    "DataTransformer",  # Backward compatibility alias
    "DataValidator",  # Backward compatibility alias
    # Built-in routines - Reliability
    "RetryHandler",
    # Analysis tools
    "RoutineAnalyzer",
    "analyze_routine_file",
    "WorkflowAnalyzer",
    "analyze_workflow",
    "BaseFormatter",
    "RoutineMarkdownFormatter",
    "WorkflowD2Formatter",
]

__version__ = "0.14.3"
