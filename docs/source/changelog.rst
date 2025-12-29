Changelog
=========

Version 0.9.0
-------------

Released: 2025-01-XX

Breaking Changes
~~~~~~~~~~~~~~~~

* ⚠️ **Unified Slot-Based Invocation**: Entry routines must now use a "trigger" slot instead of direct ``__call__`` invocation
  * All entry routines must define a "trigger" slot: ``self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)``
  * ``Flow.execute()`` now triggers entry routines via their "trigger" slot
  * Direct ``__call__`` invocation is deprecated for entry routines

New Features
~~~~~~~~~~~~

* ✅ **Slot.call_handler() method**: New method for direct handler invocation with exception propagation control
  * Supports all handler parameter matching patterns
  * Includes data merging according to slot's merge_strategy
  * Used internally by Flow for entry routine trigger slots

Improvements
~~~~~~~~~~~~

* ✅ **Code Organization**: Eliminated ~70 lines of duplicate code by centralizing handler invocation logic in ``Slot.call_handler()``
* ✅ **Error Handling**: Entry routine exceptions now properly propagate to Flow's error handling strategies
* ✅ **Consistency**: All entry routine invocations use the same unified mechanism
* ✅ **Maintainability**: Single source of truth for handler invocation logic

Fixed
~~~~~

* ✅ **Error Handling in Entry Routines**: Fixed issue where entry routine exceptions were not properly handled by Flow's error handling strategies

Documentation
~~~~~~~~~~~~~

* ✅ Updated user guide to reflect unified slot-based invocation pattern
* ✅ Added examples showing how to define trigger slots for entry routines
* ✅ Updated API documentation for ``Slot.call_handler()`` method

Migration Guide
~~~~~~~~~~~~~~~

**For Entry Routines:**

Before (deprecated):

.. code-block:: python

   class MyEntryRoutine(Routine):
       def __call__(self, **kwargs):
           # Entry logic here
           self.emit("output", data="result")

After (required):

.. code-block:: python

   class MyEntryRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
           self.output_event = self.define_event("output", ["data"])
       
       def _handle_trigger(self, **kwargs):
           # Entry logic here
           self.emit("output", data="result")

**Note**: This is a breaking change. All entry routines must be updated to use trigger slots.

Version 0.1.2
-------------

Released: 2024-12-26

New Features
~~~~~~~~~~~~

* ✅ **ErrorHandler**: Error handler supporting multiple error handling strategies (stop, continue, retry, skip)
* ✅ **Error Recovery Strategies**: Support for configuring error handling strategies and retry mechanisms
* ✅ **Pause and Resume**: Flow supports pause and resume functionality
* ✅ **Cancel Functionality**: Flow supports canceling execution

Improvements
~~~~~~~~~~~~

* ✅ **Error Handling Integration**: Flow.execute integrates error handler
* ✅ **Retry Mechanism**: Supports automatic retry with configurable retry count and delay
* ✅ **Pause Point Recording**: Records pause points and checkpoint information
* ✅ **Design Optimization**: Optimized responsibility separation for pause/resume/cancel
  * Flow responsible for execution control (pause/resume/cancel)
  * JobState only responsible for state recording and queries
  * Removed public pause/resume/cancel methods from JobState, changed to internal methods

Version 0.1.1
-------------

Released: 2024-12-26

New Features
~~~~~~~~~~~~

* ✅ **ExecutionTracker**: Execution tracker that tracks flow execution state, performance, and event flow
* ✅ **Execution History Recording**: Automatically records all emitted events to JobState
* ✅ **Performance Metrics**: Supports getting routine and flow performance metrics
* ✅ **Detailed State Tracking**: Records execution time, start/end times, and other detailed information

Improvements
~~~~~~~~~~~~

* ✅ **Error Handling**: More comprehensive error recording and handling
* ✅ **Execution Time Tracking**: Automatically calculates and records execution time for each routine
* ✅ **Event Flow Tracking**: Records all event triggers and passes

Version 0.1.0
-------------

Released: 2024-01-XX

Initial release with core functionality:

New Features
~~~~~~~~~~~~

* ✅ **Routine Base Class**: Supports defining slots and events, provides stats() method
* ✅ **Slot Class**: Input slot supporting connection to multiple events, data reception and processing
* ✅ **Event Class**: Output event supporting connection to multiple slots, event triggering
* ✅ **Connection Class**: Connection object supporting parameter mapping
* ✅ **Flow Class**: Flow manager supporting workflow orchestration, execution, and recovery
* ✅ **JobState Class**: Job state management supporting state recording and persistence
* ✅ **ExecutionRecord Class**: Execution record

Improvements
~~~~~~~~~~~~

* ✅ **Event-Driven Execution**: Implemented event-driven execution mechanism
* ✅ **Parameter Mapping**: Improved Connection parameter mapping functionality
* ✅ **Intelligent Parameter Matching**: Slot.receive can now intelligently match handler parameters
* ✅ **Flow Context**: Routine.emit can automatically get Flow context

Testing
~~~~~~~

* ✅ Basic functionality tests passed
* ✅ Flow execution tests passed (linear flow, branch flow, parameter mapping)

Known Issues
~~~~~~~~~~~~

* ⚠️ Flow persistence only saves structure, not routine instances
* ⚠️ Need to improve asynchronous execution support
* ⚠️ Need to implement complete test cases

