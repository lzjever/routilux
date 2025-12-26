Features
========

This document provides a comprehensive overview of flowforge features.

Core Features
------------

Routine Base Class
~~~~~~~~~~~~~~~~~~~

* ✅ Support for defining 0-N slots (input slots)
* ✅ Support for defining 0-N events (output events)
* ✅ Provides ``stats()`` method returning state dictionary
* ✅ Supports serialization
* ✅ Automatically records emitted events to execution history

Slot (Input Slot)
~~~~~~~~~~~~~~~~~

* ✅ Can connect to multiple events (many-to-many relationship)
* ✅ Supports data reception and processing
* ✅ Supports merge strategies (override, append, custom)
* ✅ Intelligent parameter matching (supports various handler signatures)
* ✅ Exception handling (handler exceptions don't interrupt flow)

Event (Output Event)
~~~~~~~~~~~~~~~~~~~~

* ✅ Can connect to multiple slots (many-to-many relationship)
* ✅ Supports event triggering and data passing
* ✅ Passes data through Connection with parameter mapping
* ✅ Automatically recorded to execution history

Connection
~~~~~~~~~~

* ✅ Connects event to slot
* ✅ Supports parameter mapping
* ✅ Automatically applies parameter mapping

Flow (Workflow Manager)
~~~~~~~~~~~~~~~~~~~~~~~

* ✅ Manages multiple Routine nodes
* ✅ Manages connections between nodes
* ✅ Executes workflows (execute)
* ✅ Resumes execution (resume)
* ✅ Supports serialization/deserialization
* ✅ Execution tracking (ExecutionTracker)

JobState (Job State)
~~~~~~~~~~~~~~~~~~~~

* ✅ Records flow execution state
* ✅ Records state of each routine
* ✅ Records execution history (ExecutionRecord)
* ✅ Supports serialization/deserialization

ExecutionTracker
~~~~~~~~~~~~~~~~

* ✅ Tracks routine execution
* ✅ Tracks event flow
* ✅ Performance metrics (execution time, success rate, etc.)
* ✅ Supports getting routine and flow performance metrics

Advanced Features
-----------------

Event-Driven Execution
~~~~~~~~~~~~~~~~~~~~~~~

* ✅ Event-driven execution mechanism
* ✅ Flow context automatically passed
* ✅ Data passed through Connection with parameter mapping

Intelligent Parameter Matching
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ✅ Automatic handler parameter matching
* ✅ Supports ``**kwargs``, single parameter, multiple parameters
* ✅ Automatically extracts values from dictionaries

Execution Tracking
~~~~~~~~~~~~~~~~~~

* ✅ Automatically records all emitted events
* ✅ Records execution time
* ✅ Records start/end times
* ✅ Performance metrics statistics

Error Handling
~~~~~~~~~~~~~~

* ✅ Automatic error capture and recording
* ✅ Error information recorded to JobState
* ✅ Errors recorded to execution history
* ✅ Multiple error handling strategies (STOP, CONTINUE, RETRY, SKIP)

Persistence
~~~~~~~~~~~

* ✅ Complete JobState persistence (serialize/deserialize)
* ✅ Flow structure persistence (serialize/deserialize)
* ✅ Supports JSON format
* ✅ Full serialization support for all core classes

Error Handling Strategies
-------------------------

STOP Strategy
~~~~~~~~~~~~~

Stop execution immediately when an error occurs.

CONTINUE Strategy
~~~~~~~~~~~~~~~~

Continue execution despite errors, logging them for review.

RETRY Strategy
~~~~~~~~~~~~~~

Retry the failed routine with configurable:

* Maximum retry attempts
* Retry delay
* Retry backoff multiplier
* Retryable exception types

SKIP Strategy
~~~~~~~~~~~~~

Skip the failed routine and continue with the next routine.

Pause and Resume
----------------

* ✅ **Pause Functionality**: Flow.pause() supports pausing execution
* ✅ **Resume Functionality**: Flow.resume() supports resuming execution
* ✅ **Cancel Functionality**: Flow.cancel() supports cancelling execution
* ✅ **Pause Point Recording**: Automatically records pause points and checkpoint information to JobState
* ✅ **Design Optimization**: Execution control (pause/resume/cancel) handled by Flow, JobState only responsible for state recording

Concurrent Execution
--------------------

* ✅ **Concurrent Execution Strategy**: Support for parallel execution using thread pools
* ✅ **Automatic Parallelization**: Routines that can run in parallel are automatically executed concurrently
* ✅ **Thread Pool Management**: Configurable thread pool size (max_workers)
* ✅ **Dependency Handling**: Automatic dependency detection and waiting
* ✅ **Thread Safety**: All state updates are thread-safe
* ✅ **Performance Optimization**: Significant speedup for I/O-bound operations
* ✅ **Strategy Switching**: Dynamic switching between sequential and concurrent execution
* ✅ **Serialization Support**: Concurrent flows can be serialized and deserialized
* ✅ **Task Completion Tracking**: Automatic tracking of active concurrent tasks
* ✅ **Wait for Completion**: ``wait_for_completion()`` method to wait for all tasks with optional timeout
* ✅ **Resource Cleanup**: ``shutdown()`` method for proper thread pool cleanup

Concurrent Execution Details
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Execution Strategies:**
- ``sequential``: Routines execute one after another (default)
- ``concurrent``: Routines execute in parallel using thread pools

**Key Features:**
- Automatic detection of parallelizable routines
- Thread pool management with configurable size
- Thread-safe state management
- Error handling in concurrent scenarios
- Performance monitoring for concurrent execution

**Use Cases:**
- Multiple API calls that can run in parallel
- Concurrent data fetching from multiple sources
- Parallel processing of independent tasks
- I/O-bound operations that benefit from concurrency

