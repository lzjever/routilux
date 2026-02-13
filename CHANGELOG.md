# Routilux Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.14.0] - 2026-02-13

### Fixed

#### Critical Thread Safety Fixes (P0)

- **SlotActivationTask task_done() not called** (executor.py): Added try-except wrapper around `global_thread_pool.submit()` to ensure `task_done()` is always called even when submit fails, preventing queue count errors
- **JobContext.start()/complete() thread safety** (context.py): Added lock protection to `start()` and `complete()` methods to ensure thread-safe modification of status, error, and completed_at fields
- **_clear_consumed_data() index error** (slot.py): Added boundary condition check when all data is consumed (`first_unconsumed >= len(queue)`) to properly clear the entire queue instead of leaving stale data
- **enqueue_task() race condition** (executor.py): Moved `_paused` check inside the lock to eliminate the race window between checking pause state and acquiring the lock

#### Stability Fixes (P1)

- **shutdown() duplicate call protection** (manager.py): Added early return check to prevent multiple shutdown calls from causing thread pool errors
- **emit() connected_slots iteration** (event.py): Analysis confirmed thread-safety is already ensured by `flow.get_connections_for_event()` which uses lock protection and returns a snapshot

### Changed

- **Removed unused _active_routines functionality** (runtime.py):
  - Removed `_active_routines` dictionary and `_active_routines_lock`
  - Removed `get_active_thread_count()` method (returned 0 or 1, never truly used)
  - Removed `get_all_active_thread_counts()` method
  - Updated Thread Safety documentation to reflect simplified lock order

### Tests

- Added `tests/concurrent/test_executor_cleanup.py` for executor cleanup tests
- Added `tests/concurrent/test_lock_ordering.py` for lock ordering verification
- Added `tests/concurrent/test_manager_registration.py` for manager registration timing tests

## [0.13.0] - 2026-02-13

### Added

#### CLI Improvements

- **Help information enhancement**: Added clear usage examples to all CLI commands (`init`, `run`, `list`, `validate`, `server`)
- **Parameter validation**: Comprehensive validation with helpful error messages and recovery suggestions
  - `run`: `--param` format validation (KEY=VALUE required), `--timeout` validation (must be positive)
  - `init`: Project name validation (valid characters, reserved names)
  - `server`: Port validation (0-65535, warning for privileged ports)
- **Configuration file support**: Full `routilux.toml` configuration support
  - Supports TOML, YAML, JSON formats
  - Auto-discovers `routilux.toml` or `pyproject.toml`
  - CLI options take precedence over config file values
  - New `routilux/cli/config.py` module with `ConfigLoader` class
- **Shell completion support**: Auto-completion for Bash, Zsh, and Fish shells
  - New `routilux completion <shell>` command
  - `--install` option for automatic installation
  - Comprehensive completion for all commands and options
- **Server management commands**: Full server lifecycle management
  - `server stop`: Stop running server with PID file management
  - `server status`: Check server status with JSON output option
  - PID file management in `server_wrapper.py`
- **Output beautification**: Rich library integration for better CLI output
  - `list`: Rich tables for routines and flows
  - `validate`: Colored output for validation results
  - Graceful fallback when rich is not installed

### Changed

- Added `rich>=13.0.0` as optional CLI dependency
- Updated `--config` option to actually load and use configuration files
- Improved error messages with actionable recovery suggestions

### Documentation

- Updated CLI documentation with new features and examples
- Added shell completion installation guide

### Tests

- Added `tests/cli/test_config.py` for configuration loading tests
- Added `tests/cli/commands/test_completion.py` for completion command tests
- Updated `tests/cli/commands/test_server.py` with stop/status tests
- Updated `tests/cli/commands/test_run.py` with parameter validation tests

## [0.12.0] - 2026-02-13

### Added

- **Built-in routines refactoring**: Reorganized and enhanced built-in routines
  - **Control Flow**: Aggregator, Batcher, Debouncer, Splitter
  - **Data Processing**: Filter, Mapper, SchemaValidator
  - **Reliability**: RetryHandler with configurable strategies
- **Simplified API**: New `pipeline`, `run_sync`, `run_async` functions for easier workflow creation
- **Decorators**: `@routine` and `@routine_class` decorators for easy routine definition
- **Analysis tools**: RoutineAnalyzer, WorkflowAnalyzer with formatters

### Changed

- Improved core architecture stability
- Enhanced error handling and recovery

## [0.11.1] - 2026-02-13

### Fixed

#### Critical Bug Fixes (P0)

- **Job memory leak** (runtime.py): Fixed `complete_job()` not removing completed jobs from `_active_jobs` dictionary, preventing OOM in long-running processes
- **Deadlock risk** (runtime.py): Fixed lock ordering in `get_active_thread_count()` and `get_all_active_thread_counts()` to prevent deadlocks from inconsistent lock acquisition order
- **Event loop race condition** (executor.py): Fixed `_is_complete()` race condition by using atomic counter instead of `Queue.empty()` check
- **Event loop resilience** (executor.py): Fixed event loop breaking on any unexpected exception - now only exits on fatal errors (SystemExit, KeyboardInterrupt)
- **JobContext thread safety** (context.py): Added thread lock to protect `data` and `trace_log` access, preventing data corruption in multi-threaded environments
- **resume() counter bug** (executor.py): Fixed `resume()` not updating `_pending_task_count` when moving pending tasks back to queue

#### Medium Priority Fixes (P1)

- **Dictionary shallow copy** (worker.py): Fixed shallow copy issue in `update_routine_state()` and `get_routine_state()` by using `deepcopy`
- **Routine data bypassing lock** (routine.py): Fixed `set_job_data()` and `get_job_data()` directly accessing `job.data` instead of thread-safe methods
- **Shutdown resource leak** (runtime.py): Fixed `shutdown()` not waiting for workers to stop, which could leave orphaned threads running

### Changed

- Improved thread safety across core modules (runtime.py, executor.py, context.py, worker.py, routine.py)
- Enhanced shutdown process to properly cancel workers before clearing

## [0.11.0] - 2026-02-07

### Changed
- Applied ruff formatting to all Python files for consistent code style
- Fixed lint issues including unused imports, unused variables, and import sorting
- All 823 tests passing with proper code quality standards

### Fixed
- Fixed F841 lint errors (unused local variables) by prefixing with underscore
- Fixed I001 errors (import block sorting) with ruff --fix
- Fixed F401 errors (unused imports) with ruff --fix

## [0.10.0] - 2026-01-03

### Changed
- Updated Python version support to 3.8-3.14
- Updated serilux dependency to >=0.3.1
- Integrated CI workflow with uv for automated testing and building

## [0.9.0] - 2025-01-XX

### 🚀 Major Architecture Overhaul: Event Queue Pattern + Complete Flow/JobState Decoupling

This is a **major version update** with significant architectural changes. The core execution model has been completely redesigned to use an event queue pattern, and Flow and JobState are now completely decoupled.

### Changed

#### Breaking Changes

- **Event Queue Architecture**: Complete redesign of execution model from call-stack-based to event-queue-based
  - `emit()` is now **always non-blocking** - returns immediately after enqueuing tasks
  - Both sequential and concurrent modes use the **same unified queue mechanism**
  - Execution order is now **fair scheduling** (queue order) instead of depth-first
  - Each `Flow.execute()` call is an **independent execution** - slot data is NOT shared between executions

- **Complete Flow/JobState Decoupling**: Flow and JobState are now completely separated
  - **Removed**: `flow.job_state` field - Flow no longer manages execution state
  - **Removed**: `flow._active_executions` - Flow does not track executions
  - **Removed**: `flow.get_execution()`, `flow.get_all_executions()`, etc. - Flow doesn't manage executions
  - **Changed**: `flow.pause()`, `flow.resume()`, `flow.cancel()` now require `JobState` as first argument
  - **Changed**: `flow.serialize()` no longer includes execution state (removed `include_execution_state` parameter)
  - **Added**: Thread-local storage for passing JobState during execution (internal mechanism)
  - **Added**: Task-level JobState passing for worker thread access
  - **Impact**: Each `execute()` returns a JobState that you must manage - Flow doesn't store it
  - **Benefit**: Proper separation of concerns, multiple independent executions, better serialization model

- **Automatic Flow Detection**: `emit()` now automatically detects flow from routine context
  - No need to manually pass `flow` parameter in most cases
  - Flow context is automatically set by `Flow.execute()` and `Flow.resume()`
  - Explicit `flow` parameter still supported for backward compatibility

- **Execution Behavior**: 
  - Removed depth-first execution guarantee
  - Tasks are processed in queue order (fair scheduling)
  - Long chains no longer block shorter ones
  - Multiple message chains can progress alternately

#### Non-Breaking Changes

- **Unified Execution Model**: Sequential and concurrent modes now use identical queue-based logic
  - Sequential mode: `max_workers=1` (one task at a time)
  - Concurrent mode: `max_workers>1` (multiple tasks in parallel)
  - Same event loop, same task queue, same execution logic

### Added

- **Event Queue Infrastructure**:
  - `SlotActivationTask` dataclass for representing slot activation tasks
  - `TaskPriority` enum for task prioritization (HIGH, NORMAL, LOW)
  - Task queue (`queue.Queue`) for storing pending tasks
  - Event loop running in background thread

- **Non-blocking emit()**:
  - `emit()` creates tasks and enqueues them immediately
  - Returns without waiting for downstream execution
  - All slot activations happen asynchronously

- **Enhanced pause/resume**:
  - Pending tasks are serialized to `JobState.pending_tasks`
  - Tasks can be precisely restored from serialized state
  - Resume continues from exact pause point

- **Fair Scheduling**:
  - Tasks processed in queue order
  - Multiple message chains progress alternately
  - Prevents long chains from blocking shorter ones

- **Task-level Error Handling**:
  - Error handling applied at task level
  - Retry logic works per task
  - Errors don't stop the event loop

- **Automatic Flow Detection**:
  - `emit()` automatically retrieves flow from `routine._current_flow`
  - Simplified API - no need to pass flow parameter
  - Backward compatible - explicit flow parameter still works

### Improved

- **Performance**:
  - Non-blocking emit() eliminates blocking waits
  - Fair scheduling improves overall throughput
  - Unified execution model reduces code duplication
  - Improved event loop task completion detection with consecutive empty checks

- **Execution Completion Detection**:
  - **Systematic completion mechanism**: New `routilux.flow.completion` module provides robust completion detection
  - **Multiple stability checks**: Avoids race conditions where tasks are enqueued after initial check
  - **Configurable timeout**: Default timeout increased from 10 seconds to 300 seconds (5 minutes) for long-running tasks
  - **Event loop management**: Automatic detection and restart of stopped event loops when tasks are pending
  - **Better error handling**: Proper handling of executor shutdown scenarios
  - **Progress monitoring**: Optional progress callback for monitoring execution status

- **Code Quality**:
  - Eliminated duplicate execution logic between sequential and concurrent modes
  - Centralized task execution in event loop
  - Better separation of concerns
  - **Flow Module Refactoring**: Refactored `flow.py` (1403 lines) into modular structure:
    - `flow/flow.py` - Main Flow class (459 lines)
    - `flow/task.py` - TaskPriority enum and SlotActivationTask dataclass
    - `flow/execution.py` - Execution logic (sequential/concurrent)
    - `flow/event_loop.py` - Event loop and task queue management
    - `flow/error_handling.py` - Error handling logic
    - `flow/state_management.py` - State management (pause/resume/cancel)
    - `flow/dependency.py` - Dependency graph building
    - `flow/serialization.py` - Serialization logic
    - Improved maintainability, testability, and code organization
    - Removed redundant code and backward compatibility wrappers
    - Fixed bugs in error handling retry logic and event loop

- **User Experience**:
  - Simpler API - automatic flow detection
  - More predictable behavior - fair scheduling
  - Better documentation of execution model

- **Defensive Programming**:
  - Clear documentation about independent executions
  - Examples showing correct aggregation patterns
  - Multiple independent executions are now explicitly supported

### Fixed

- **Execution Order**: Fixed issue where long chains could block shorter ones
- **Concurrent Execution**: Unified logic eliminates inconsistencies between modes
- **Event Loop Task Completion**: Fixed issue where event loop could exit before tasks were enqueued
  - Added consecutive empty checks to ensure tasks are truly complete
  - Improved task completion detection logic
- **Error Handling Retry Logic**: Fixed retry strategy to properly handle max retries reached
- **Task Serialization**: Improved null safety in task serialization/deserialization
- **Pause/Resume**: Fixed serialization of pending tasks for proper resume
- **Emit Blocking**: Fixed issue where second emit() had to wait for first to complete

### Documentation

- **Complete Rewrite**: Updated all documentation to reflect new architecture
  - Removed all historical content about old execution model
  - Added comprehensive event queue pattern documentation
  - Updated all examples to use automatic flow detection
  - Added migration guide and best practices

- **New Sections**:
  - Event queue architecture overview
  - Fair scheduling explanation
  - Automatic flow detection guide
  - Independent execution warnings
  - Correct aggregation patterns

### Migration Guide

**For emit() calls:**

Before (still works, but verbose):
```python
def _handle_trigger(self, **kwargs):
    flow = getattr(self, "_current_flow", None)
    self.emit("output", flow=flow, data="value")
```

After (recommended):
```python
def _handle_trigger(self, **kwargs):
    # Flow automatically detected!
    self.emit("output", data="value")
```

**For Aggregation Patterns:**

Before (won't work - slot data not shared):
```python
# Bad: Multiple executes don't share state
flow.execute(source1_id)  # Creates new JobState
flow.execute(source2_id)  # Creates another new JobState
# Aggregator won't see both messages!
```

After (correct way):
```python
# Good: Single execute with multiple emits
class MultiSourceRoutine(Routine):
    def _handle_trigger(self, **kwargs):
        for data in ["A", "B", "C"]:
            self.emit("output", data=data)  # All share same execution
flow.execute(multi_source_id)
```

**For Execution Order:**

Before (depth-first guaranteed):
- Downstream chains completed before next sibling
- Deterministic depth-first order

After (fair scheduling):
- Tasks processed in queue order
- Multiple chains progress alternately
- No depth-first guarantee (but better overall throughput)

**Note**: This is a **major version update**. Review your code for:
1. Aggregation patterns using multiple `execute()` calls
2. Code relying on depth-first execution order
3. Code that expects `emit()` to wait for completion

## [0.8.1] - 2025-12-29

### Added

- **GitHub Actions workflow**: Automated build and release workflow with automatic release notes generation
- **Release scripts**: Scripts for generating release notes from CHANGELOG.md or git commits

### Improved

- **Code cleanup**: Removed unused utils module
- **Code formatting**: Improved code formatting and linting configuration

### Documentation

- **Release automation**: Added scripts and documentation for automated releases
- **GitHub integration**: Integrated GitHub Actions for automated package building and publishing

## [0.8.0] - 2025-12-27

### Added

- **Routine-level error handling**: Support for setting independent error handling strategies per routine, with priority over flow-level handlers
- **Critical/Optional routine marking**: Added `set_as_critical()` and `set_as_optional()` convenience methods for marking routines
- **`is_critical` flag**: ErrorHandler now supports `is_critical` parameter to mark critical routines that must succeed
- **Error handling priority system**: Priority order is routine-level > flow-level > default (STOP)
- **Critical routine retry failure handling**: Critical routines that fail after all retries will cause the flow to fail

### Improved

- **Backward compatibility**: Maintained full compatibility with existing code; flow-level error handling remains effective
- **Error handler flexibility**: Enhanced error handler configuration with better support for routine-specific overrides
- **Documentation**: Updated error handling documentation with routine-level error handling examples
- **Critical routine semantics**: Clarified behavior when critical routines fail after retries

### Documentation

- Added comprehensive documentation for routine-level error handling
- Added examples for critical and optional routine usage patterns
- Clarified differences between CONTINUE and SKIP strategies
- Updated API reference with new error handling methods

## [0.7.0] - 2025-12-06

### Added

- **Concurrent execution mode**: Added support for parallel execution of independent routines using thread pools
- **Execution strategy configuration**: Flow now supports "sequential" and "concurrent" execution strategies
- **Thread pool management**: Added `wait_for_completion()` and `shutdown()` methods for managing concurrent execution
- **Dependency graph analysis**: Automatic dependency graph building for concurrent execution scheduling
- **Built-in routines package**: Comprehensive set of reusable routines for common tasks
  - **Text Processing**: TextClipper, TextRenderer, ResultExtractor
  - **Data Processing**: DataTransformer, DataValidator
  - **Control Flow**: ConditionalRouter, RetryHandler
  - **Utilities**: TimeProvider, DataFlattener
- **Built-in routine architecture**: Common base patterns for consistent routine implementation

### Improved

- **Event emission in concurrent mode**: Events now trigger parallel slot handler execution when in concurrent mode
- **Thread safety**: Added proper locking mechanisms for thread-safe state management
- **Future tracking**: Automatic tracking and cleanup of concurrent task futures
- **Performance**: Optimized concurrent execution with proper resource management

### Documentation

- Added concurrent execution guide
- Documented all built-in routines with examples
- Added best practices for concurrent workflow design
- Updated examples with concurrent execution patterns

## [0.6.0] - 2025-11-08

### Added

- **Full serialization support**: Complete serialization/deserialization for Flow, Routine, Slot, Event, Connection, and JobState
- **Persistence capabilities**: Flow and JobState can be saved to and loaded from files
- **Serializable base class**: New Serializable utility class with automatic field registration
- **Serialization validation**: Pre-serialization validation to catch issues early
- **Callable serialization**: Support for serializing and deserializing handler functions and merge strategies
- **Class information tracking**: Automatic tracking of routine class information for proper deserialization
- **JobState persistence**: `save()` and `load()` methods for JobState persistence

### Improved

- **Serialization robustness**: Enhanced error handling and validation in serialization process
- **Reference restoration**: Improved handling of object references during deserialization
- **Handler restoration**: Proper restoration of slot handlers and merge strategies after deserialization
- **Connection reconstruction**: Automatic rebuilding of event-slot connections from serialized data

### Fixed

- **Circular reference handling**: Proper handling of bidirectional connections during serialization
- **Datetime serialization**: Consistent datetime handling across all serializable objects
- **Routine instance restoration**: Fixed issues with routine instance recreation from serialized data

### Documentation

- Added serialization guide
- Documented persistence patterns
- Added examples for saving and loading flows
- Updated API reference with serialization methods

## [0.5.0] - 2025-10-11

### Added

- **ErrorHandler class**: Comprehensive error handling system with multiple strategies
- **Error handling strategies**: Support for STOP, CONTINUE, RETRY, and SKIP strategies
- **Retry mechanism**: Configurable retry logic with exponential backoff
- **Retryable exception filtering**: Support for specifying which exception types should be retried
- **Flow-level error handling**: `set_error_handler()` method for setting default error handler for all routines
- **Error recovery**: Automatic error recovery based on configured strategies
- **Error logging**: Comprehensive error logging and tracking

### Improved

- **Error handling integration**: Seamless integration of error handlers into Flow execution
- **Retry configuration**: Flexible retry configuration with delay and backoff parameters
- **Error state tracking**: Enhanced error state tracking in JobState
- **Exception handling**: Improved exception handling throughout the execution pipeline

### Documentation

- Added comprehensive error handling guide
- Documented all error handling strategies with examples
- Added retry configuration examples
- Updated troubleshooting guide

## [0.4.0] - 2025-09-06

### Added

- **ExecutionTracker class**: Comprehensive execution tracking and performance monitoring
- **Routine execution tracking**: Automatic tracking of routine start/end times, parameters, and results
- **Event flow tracking**: Complete event emission history with source, target, and data
- **Performance metrics**: Automatic calculation of execution times, success rates, and throughput
- **Routine performance analysis**: `get_routine_performance()` method for detailed routine metrics
- **Flow performance analysis**: `get_flow_performance()` method for overall flow metrics
- **Execution history integration**: Automatic recording of all events to JobState execution history

### Improved

- **Performance monitoring**: Enhanced performance tracking with detailed metrics
- **Execution time tracking**: Automatic calculation and recording of execution times
- **Event flow visibility**: Complete visibility into data flow through the workflow
- **Statistics integration**: Better integration between ExecutionTracker and Routine statistics

### Documentation

- Added execution tracking guide
- Documented performance analysis methods
- Added examples for monitoring workflow performance
- Updated API reference with tracking methods

## [0.3.0] - 2025-08-02

### Added

- **JobState class**: Comprehensive execution state management
- **ExecutionRecord class**: Individual execution record tracking
- **State persistence**: Support for saving and loading JobState
- **Pause and resume functionality**: Flow execution can be paused and resumed
- **Cancel functionality**: Flow execution can be cancelled with reason tracking
- **Execution history**: Complete history of all routine executions and event emissions
- **Routine state tracking**: Per-routine state tracking with status, errors, and results
- **Checkpoint support**: Checkpoint data can be saved during pause operations

### Improved

- **State management**: Unified state management across all routines
- **Execution control**: Better separation of concerns between Flow and JobState
- **State queries**: Enhanced methods for querying execution state
- **Timestamp tracking**: Automatic tracking of creation and update timestamps

### Documentation

- Added state management guide
- Documented pause/resume/cancel patterns
- Added examples for state persistence
- Updated API reference with JobState methods

## [0.2.0] - 2025-07-05

### Added

- **Flow class**: Workflow manager for orchestrating multiple routines
- **Routine management**: `add_routine()` method for registering routines in flows
- **Connection management**: `connect()` method for linking events to slots
- **Flow execution**: `execute()` method for running workflows from entry routines
- **Parameter mapping**: Support for parameter name transformation in connections
- **Flow context**: Automatic flow context passing to routines for event emission
- **Entry point execution**: Support for executing flows starting from any routine
- **Flow ID management**: Unique flow identification and tracking

### Improved

- **Event-driven execution**: Implemented event-driven execution mechanism
- **Parameter passing**: Enhanced parameter passing through connections
- **Flow organization**: Better structure for managing complex workflows
- **Error handling**: Basic error handling during flow execution

### Documentation

- Added flow orchestration guide
- Documented connection patterns
- Added examples for basic workflow creation
- Updated quick start guide

## [0.1.0] - 2025-06-13

### Added

- **Routine base class**: Core Routine class with slots and events support
- **Slot class**: Input slot mechanism for receiving data from other routines
- **Event class**: Output event mechanism for transmitting data to other routines
- **Connection class**: Connection object for linking events to slots with parameter mapping
- **Slot merge strategies**: Support for "override", "append", and custom merge strategies
- **Intelligent parameter matching**: Automatic parameter matching for slot handlers
- **Statistics tracking**: Built-in `stats()` method and statistics dictionary
- **Configuration management**: `_config` dictionary for routine configuration
- **Event emission**: `emit()` method for triggering events and transmitting data
- **Slot reception**: `receive()` method for receiving and processing data
- **Many-to-many connections**: Support for flexible connection patterns
- **Handler functions**: Support for flexible handler function signatures

### Improved

- **Event-driven architecture**: Foundation for event-driven workflow execution
- **Data flow**: Clear data flow mechanism through slots and events
- **Parameter mapping**: Parameter name transformation support in connections
- **Error tolerance**: Slot handlers are error-tolerant and don't interrupt flow execution

### Documentation

- Initial documentation structure
- Basic usage examples
- API reference for core classes

### Known Issues

- Flow persistence only saves structure, not routine instances (addressed in v0.6.0)
- Limited error handling (addressed in v0.5.0)
- No execution tracking (addressed in v0.4.0)
- Sequential execution only (addressed in v0.7.0)
