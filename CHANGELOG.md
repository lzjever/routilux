# Routilux Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
