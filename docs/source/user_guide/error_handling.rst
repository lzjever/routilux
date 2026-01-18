Error Handling and Exception Management
========================================

Routilux provides comprehensive error handling mechanisms to help you build robust
workflows that can gracefully handle failures. This guide explains how errors are
handled in different scenarios and how to configure error handling strategies.

**Key Features**:
* **Multi-level error handling**: Set error handlers at both flow and routine levels
* **Flexible strategies**: STOP, CONTINUE, RETRY, and SKIP strategies
* **Critical/Optional routines**: Mark routines as critical (must succeed) or optional (failures tolerated)
* **Intelligent retry**: Configurable retry with exponential backoff and exception filtering
* **Priority system**: Routine-level handlers override flow-level handlers

Understanding Error Handling in Routilux
------------------------------------------

Errors can occur in different places in a Routilux workflow:

1. **Entry Routine Execution Errors**: Errors raised in an entry routine's trigger
   slot handler (when called by ``Flow.execute()``). These errors propagate to Flow's
   error handling mechanisms and can trigger error handling strategies.

2. **Slot Handler Errors**: Errors raised in slot handler functions when processing
   received data from upstream routines. These errors are always caught and logged
   to the routine's ``_stats["errors"]`` list without interrupting the flow.

3. **Event Emission Errors**: Errors during event emission (rare, usually indicates
   a configuration issue)

**Key Point**: Error handling strategies (STOP, CONTINUE, RETRY, SKIP) only apply
to **entry routine execution errors** (errors in trigger slot handlers called by
``Flow.execute()``). Regular slot handler errors are always caught and logged
without interrupting the flow.

Error Handling Strategies
-------------------------

Routilux provides four error handling strategies:

**STOP** (Default)
   Stop execution immediately when an error occurs. The flow status is set to
   "failed" and execution stops.

**CONTINUE**
   Log the error but continue execution. The flow status is set to "completed"
   even if errors occurred. Useful for workflows where some failures are acceptable.

**RETRY**
   Automatically retry the failed routine up to a maximum number of times with
   configurable delays. If all retries fail, execution stops.

**SKIP**
   Skip the failed routine and continue with the next routine. The routine is
   marked as "skipped" in the job state.

Creating an Error Handler
--------------------------

Create an error handler with a strategy:

.. code-block:: python

   from routilux import ErrorHandler, ErrorStrategy

   # Stop on error (default)
   error_handler = ErrorHandler(strategy=ErrorStrategy.STOP)
   
   # Continue on error
   error_handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)
   
   # Retry on error
   error_handler = ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=3,
       retry_delay=1.0,
       retry_backoff=2.0
   )
   
   # Skip on error
   error_handler = ErrorHandler(strategy=ErrorStrategy.SKIP)

Setting Error Handler
----------------------

Error handlers can be set at two levels:

1. **Flow Level**: Default error handler for all routines in the flow
2. **Routine Level**: Error handler specific to a single routine

**Priority Order**:
   - Routine-level error handler (if set)
   - Flow-level error handler (if set)
   - Default behavior (STOP)

Setting Error Handler on Flow
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Set the default error handler for a flow:

.. code-block:: python

   from routilux import Flow, ErrorHandler, ErrorStrategy

   flow = Flow()
   
   error_handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)
   flow.set_error_handler(error_handler)
   
   # Execute flow - errors will be handled according to strategy
   job_state = flow.execute(entry_routine_id)

Setting Error Handler on Routine
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Set an error handler for a specific routine. This allows different routines to have
different error handling strategies:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy
   import random

   class UnreliableRoutine(Routine):
       def __call__(self):
           # May fail sometimes
           if random.random() < 0.5:
               raise ValueError("Random failure")
           print("Success!")

   flow = Flow()
   routine = UnreliableRoutine()
   
   # Set routine-level error handler
   routine.set_error_handler(ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=3))
   routine_id = flow.add_routine(routine, "my_routine")
   
   # Flow-level error handler (used as fallback for routines without their own handler)
   flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.STOP))
   
   job_state = flow.execute(routine_id)
   
   # This routine will retry on failure (routine-level handler)
   # Other routines will stop on failure (flow-level handler)

**Complete Example: Mixed Error Handling**:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.output_event = self.add_event("output", ["data"])
       
       def __call__(self):
           self.emit("output", data="important data")

   class OptionalProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["result"])
       
       def __call__(self):
           # This may fail, but it's optional
           raise ValueError("Optional processing failed")
       
       def process(self, data):
           # This won't be called if __call__ fails
           pass

   class CriticalProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.processed = False
       
       def __call__(self):
           # Must succeed
           raise ConnectionError("Critical operation failed")
       
       def process(self, data):
           self.processed = True

   flow = Flow()
   
   # Source routine - no special error handling needed
   source = DataSource()
   source_id = flow.add_routine(source, "source")
   
   # Optional processor - failures are tolerated
   optional = OptionalProcessor()
   optional.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
   optional_id = flow.add_routine(optional, "optional")
   
   # Critical processor - must succeed, retry on failure
   critical = CriticalProcessor()
   critical.set_error_handler(ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=5,
       retry_delay=0.5,
       is_critical=True
   ))
   critical_id = flow.add_routine(critical, "critical")
   
   # Flow-level handler for routines without their own handler
   flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.STOP))
   
   # Connect routines
   flow.connect(source_id, "output", optional_id, "input")
   flow.connect(source_id, "output", critical_id, "input")
   
   job_state = flow.execute(source_id)
   
   # Optional processor failure is tolerated
   # Critical processor will retry, and if all retries fail, flow fails

Strategy Details
----------------

STOP Strategy
~~~~~~~~~~~~~

**Behavior**:
* Execution stops immediately when an error occurs
* Flow status is set to "failed"
* Error is logged
* No retry attempts

**Use Cases**:
* Critical workflows where any error is unacceptable
* When you need to know immediately if something failed
* Default behavior for safety

**Example**:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class FailingRoutine(Routine):
       def __call__(self):
           raise ValueError("Critical error")

   flow = Flow()
   routine_id = flow.add_routine(FailingRoutine(), "failing")
   
   # Default behavior (STOP)
   job_state = flow.execute(routine_id)
   assert job_state.status == "failed"

CONTINUE Strategy
~~~~~~~~~~~~~~~~~

**Behavior**:
* Error is logged and recorded in execution history
* Flow status is set to "completed" (not "failed")
* Execution continues (if there are downstream routines)
* Routine state is marked as "error_continued"

**Use Cases**:
* Non-critical workflows where some failures are acceptable
* When you want to process as much as possible despite errors
* Logging and monitoring scenarios

**Example**:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class UnreliableRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.output_event = self.add_event("output", ["data"])
       
       def __call__(self):
           # May fail sometimes, but that's OK
           if random.random() < 0.5:
               raise ValueError("Temporary failure")
           self.emit("output", data="success")

   flow = Flow()
   routine_id = flow.add_routine(UnreliableRoutine(), "unreliable")
   
   error_handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)
   flow.set_error_handler(error_handler)
   
   job_state = flow.execute(routine_id)
   # Status is "completed" even if error occurred
   assert job_state.status == "completed"
   
   # Check execution history for errors
   errors = [r for r in job_state.execution_history if r.action == "error_continued"]
   if errors:
       print(f"Errors occurred but execution continued: {len(errors)}")

RETRY Strategy
~~~~~~~~~~~~~~

**Behavior**:
* When an error occurs, the routine is automatically retried
* Retry happens with exponential backoff delay
* Maximum number of retries is configurable
* Only retries if exception type is in ``retryable_exceptions``
* If all retries fail, execution stops and routine state is set to ``"failed"``
* If retry succeeds, routine state is set to ``"completed"``

**Configuration**:
* ``max_retries``: Maximum number of retry attempts (default: 3)
* ``retry_delay``: Initial delay in seconds before first retry (default: 1.0)
* ``retry_backoff``: Multiplier for delay between retries (default: 2.0)
* ``retryable_exceptions``: Tuple of exception types that can be retried (default: all exceptions)

**Retry Delay Calculation**:
* First retry: ``retry_delay * (retry_backoff ** 0) = retry_delay``
* Second retry: ``retry_delay * (retry_backoff ** 1) = retry_delay * retry_backoff``
* Third retry: ``retry_delay * (retry_backoff ** 2) = retry_delay * retry_backoff ** 2``
* And so on...

**Use Cases**:
* Network operations that may fail temporarily
* External API calls that may be rate-limited
* Database operations that may timeout
* Any operation that may succeed on retry

**Example: Basic Retry**:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy
   import time

   class NetworkRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.attempts = 0
           self.output_event = self.add_event("output", ["data"])
       
       def __call__(self):
           self.attempts += 1
           # Simulate network failure on first 2 attempts
           if self.attempts < 3:
               raise ConnectionError(f"Network error (attempt {self.attempts})")
           self.emit("output", data=f"Success after {self.attempts} attempts")

   flow = Flow()
   routine_id = flow.add_routine(NetworkRoutine(), "network")
   
   error_handler = ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=5,
       retry_delay=0.5,      # Start with 0.5s delay
       retry_backoff=2.0,    # Double delay each time
       retryable_exceptions=(ConnectionError, TimeoutError)  # Only retry these
   )
   flow.set_error_handler(error_handler)
   
   job_state = flow.execute(routine_id)
   
   # Should succeed after retries
   assert job_state.status == "completed"
   assert routine.attempts == 3  # Initial + 2 retries

**Example: Retry with Exponential Backoff**:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy
   import time

   class APIClient(Routine):
       def __init__(self):
           super().__init__()
           self.attempts = 0
           self.output_event = self.add_event("output", ["response"])
       
       def __call__(self):
           self.attempts += 1
           # Simulate API rate limiting - fails first 3 times
           if self.attempts < 4:
               raise ConnectionError(f"Rate limited (attempt {self.attempts})")
           
           # Success on 4th attempt
           self.emit("output", response={"status": "ok", "attempts": self.attempts})

   flow = Flow()
   api_client = APIClient()
   api_client.set_error_handler(ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=5,
       retry_delay=1.0,      # Start with 1 second
       retry_backoff=2.0     # Exponential backoff: 1s, 2s, 4s, 8s, 16s
   ))
   api_id = flow.add_routine(api_client, "api_client")
   
   start_time = time.time()
   job_state = flow.execute(api_id)
   elapsed = time.time() - start_time
   
   # Should succeed after retries
   assert job_state.status == "completed"
   assert api_client.attempts == 4
   # Total time should include retry delays: ~1s + 2s + 4s = ~7s (plus execution time)
   assert elapsed > 6.0  # At least 6 seconds due to retry delays

**Example: Retry Only Specific Exceptions**:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class MixedErrorRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.call_count = 0
       
       def __call__(self):
           self.call_count += 1
           if self.call_count == 1:
               # First call: retryable error
               raise ConnectionError("Network error")
           elif self.call_count == 2:
               # Second call: non-retryable error
               raise ValueError("Invalid data")
           # Should not reach here

   flow = Flow()
   routine = MixedErrorRoutine()
   routine.set_error_handler(ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=3,
       retry_delay=0.1,
       retryable_exceptions=(ConnectionError,)  # Only retry ConnectionError
   ))
   routine_id = flow.add_routine(routine, "mixed")
   
   job_state = flow.execute(routine_id)
   
   # ConnectionError should trigger retry
   # ValueError should stop immediately (not retryable)
   assert job_state.status == "failed"
   assert routine.call_count == 2  # Initial call + 1 retry (then ValueError stops)

**Status After Retry**:

* If retry succeeds: routine state is ``"completed"``, JobState status is ``"completed"``
* If all retries fail: routine state is ``"failed"``, JobState status is ``"failed"``
* ``wait_for_completion()`` will detect the ``"failed"`` routine state and set JobState status accordingly

**Retryable Exceptions**:

By default, all exceptions are retryable. You can restrict retries to specific
exception types to avoid retrying errors that won't succeed on retry:

.. code-block:: python

   # Only retry on network-related errors
   error_handler = ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=3,
       retryable_exceptions=(ConnectionError, TimeoutError, OSError)
   )
   
   # If a ValueError occurs, it won't be retried (execution stops immediately)
   # If a ConnectionError occurs, it will be retried

**Why Restrict Retryable Exceptions?**:

Some errors indicate permanent failures that won't succeed on retry:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class DatabaseRoutine(Routine):
       def __call__(self):
           # This might raise different types of errors
           if some_condition:
               raise ConnectionError("Database connection lost")  # Retryable
           else:
               raise ValueError("Invalid SQL query")  # Not retryable

   flow = Flow()
   routine = DatabaseRoutine()
   
   # Only retry connection errors, not validation errors
   routine.set_error_handler(ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=3,
       retry_delay=1.0,
       retryable_exceptions=(ConnectionError, TimeoutError)  # Only network errors
   ))
   routine_id = flow.add_routine(routine, "database")
   
   # ConnectionError will be retried
   # ValueError will stop immediately (saves time on permanent failures)

SKIP Strategy
~~~~~~~~~~~~~

**Behavior**:
* When an error occurs, the routine is skipped
* Flow status is set to "completed"
* Routine state is marked as "skipped"
* Execution continues with downstream routines (if any)

**Use Cases**:
* Optional processing steps that can be safely skipped
* When some routines are not critical
* Fallback scenarios where skipping is acceptable
* Conditional processing that may not be needed

**Difference from CONTINUE**:

* **CONTINUE**: Routine attempted but failed - marked as "error_continued"

  * Use when: You tried to do something but it failed, and that's OK
  * Example: Logging attempt failed, but we continue anyway
  * Semantic: "We tried but failed, continue anyway"

* **SKIP**: Routine was skipped - marked as "skipped"

  * Use when: The operation wasn't needed or shouldn't be attempted
  * Example: Optional enhancement service unavailable, skip it
  * Semantic: "We didn't need this, skip it"

* Both allow the flow to continue, but the semantic meaning is different
* Both result in "completed" flow status
* Both are useful for optional operations, but express different intents

**Example**:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class OptionalRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.output_event = self.add_event("output", ["data"])
       
       def __call__(self):
           # This may fail, but it's optional
           raise ValueError("Optional step failed")

   class MainRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
       
       def process(self, data):
           print(f"Processing: {data}")

   flow = Flow()
   optional_id = flow.add_routine(OptionalRoutine(), "optional")
   main_id = flow.add_routine(MainRoutine(), "main")
   
   flow.connect(optional_id, "output", main_id, "input")
   
   error_handler = ErrorHandler(strategy=ErrorStrategy.SKIP)
   flow.set_error_handler(error_handler)
   
   job_state = flow.execute(optional_id)
   
   # Status is "completed" even though optional routine failed
   assert job_state.status == "completed"
   
   # Optional routine is marked as skipped
   optional_state = job_state.get_routine_state("optional")
   assert optional_state.get("status") == "skipped"

**Example: When to Use SKIP vs CONTINUE**:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class EnhancementRoutine(Routine):
       """Optional enhancement - use SKIP if it fails"""
       def __init__(self):
           super().__init__()
           # Define trigger slot for entry routine
           self.trigger_slot = self.add_slot("trigger", handler=self._handle_trigger)
           self.output_event = self.add_event("output", ["enhanced_data"])
       
       def _handle_trigger(self, **kwargs):
           # Enhancement service unavailable - skip this step
           raise ValueError("Enhancement service down")

   class LoggingRoutine(Routine):
       """Logging - use CONTINUE if it fails (we tried but logging failed)"""
       def __init__(self):
           super().__init__()
           # Define trigger slot for entry routine
           self.trigger_slot = self.add_slot("trigger", handler=self._handle_trigger)
           self.output_event = self.add_event("output", ["logged_data"])
       
       def _handle_trigger(self, **kwargs):
           # We tried to log but it failed - continue anyway
           raise ValueError("Logging service error")

   flow = Flow()
   
   # Enhancement: Use SKIP (we didn't need it anyway)
   enhancement = EnhancementRoutine()
   enhancement.set_error_handler(ErrorHandler(strategy=ErrorStrategy.SKIP))
   enhancement_id = flow.add_routine(enhancement, "enhancement")
   
   # Logging: Use CONTINUE (we tried but it failed)
   logging = LoggingRoutine()
   logging.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
   logging_id = flow.add_routine(logging, "logging")
   
   job_state1 = flow.execute(enhancement_id)
   assert job_state1.get_routine_state("enhancement")["status"] == "skipped"
   
   job_state2 = flow.execute(logging_id)
   assert job_state2.get_routine_state("logging")["status"] == "error_continued"

Slot Handler Errors
-------------------

**Important**: Errors in slot handlers are handled differently from entry routine
execution errors.

**Behavior**:
    * Regular slot handler errors are **always caught** and logged
    * Errors are recorded in ``JobState.execution_history`` (not ``routine._stats["errors"]``)
    * Flow execution **continues** (does not stop)
    * Error handling strategies (STOP, CONTINUE, RETRY, SKIP) **do not directly apply** to
      regular slot handler errors (errors don't propagate to ``handle_task_error``)
    
    * **Exception**: Entry routine trigger slot handlers use ``call_handler(propagate_exceptions=True)``,
      so their errors **do propagate** and trigger Flow's error handling strategies
    
    * **Special Case**: If a routine has an error handler with STOP strategy, slot handler
      errors will cause the routine state to be marked as ``"failed"``, which will be
      detected by ``wait_for_completion()`` and result in JobState status being set to ``"failed"``

**Why This Design?**:
* Slot handlers process data from events, which may arrive asynchronously
* Stopping the entire flow for a single slot handler error would be too disruptive
* Errors are logged for debugging and monitoring
* However, critical failures can still be detected through routine state checking

**Error Recording**:
* Slot handler errors are recorded in ``JobState.execution_history`` with event_name ``"error"``
* If routine has STOP strategy error handler, routine state is also updated to ``{"status": "failed"}``
* This allows ``wait_for_completion()`` to detect critical failures even for slot handler errors

**Example**:

.. code-block:: python

   from routilux import Flow, Routine

   class DataProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["result"])
       
       def process(self, data):
           # This error will be caught and logged, but won't stop the flow
           if data < 0:
               raise ValueError("Negative data not allowed")
           self.emit("output", result=data * 2)

   flow = Flow()
   processor_id = flow.add_routine(DataProcessor(), "processor")
   
   # Even with STOP strategy, slot handler errors don't stop the flow
   error_handler = ErrorHandler(strategy=ErrorStrategy.STOP)
   flow.set_error_handler(error_handler)
   
   # Trigger slot handler with invalid data
   processor.input_slot.receive({"data": -1})
   
   # Check for errors in stats
   errors = processor.get_stat("errors", [])
   assert len(errors) > 0
   print(f"Errors in slot handler: {errors}")

**Accessing Slot Handler Errors**:

.. code-block:: python

   # After execution, check routine stats for errors
   stats = routine.stats()
   if "errors" in stats:
       for error_info in stats["errors"]:
           print(f"Error in slot '{error_info['slot']}': {error_info['error']}")

Routine-Level Error Handling
------------------------------

You can set error handlers at the routine level, allowing different routines
to have different error handling strategies. Routine-level error handlers take
priority over flow-level error handlers.

**Priority Order**:
1. Routine-level error handler (if set)
2. Flow-level error handler (if set)
3. Default behavior (STOP)

**Example**:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class OptionalRoutine(Routine):
       def __call__(self):
           # May fail, but that's OK
           if random.random() < 0.5:
               raise ValueError("Optional operation failed")

   class CriticalRoutine(Routine):
       def __call__(self):
           # Must succeed
           if random.random() < 0.3:
               raise ConnectionError("Critical operation failed")

   flow = Flow()
   
   # Optional routine - failures are tolerated
   optional = OptionalRoutine()
   optional.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
   optional_id = flow.add_routine(optional, "optional")
   
   # Critical routine - must succeed, retry on failure
   critical = CriticalRoutine()
   critical.set_error_handler(ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=5,
       retry_delay=1.0,
       is_critical=True
   ))
   critical_id = flow.add_routine(critical, "critical")
   
   # Flow-level handler (used as fallback)
   flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.STOP))

Critical and Optional Routines
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Routilux provides convenience methods to mark routines as critical or optional,
making it easy to express the importance of different routines in your workflow.

**Optional Routines**:
   - Failures are tolerated - the flow continues even if they fail
   - Use ``routine.set_as_optional()`` to mark a routine as optional
   - Default strategy is CONTINUE (can be changed to SKIP)
   - Perfect for non-critical operations like logging, metrics collection, or optional enhancements

**Critical Routines**:
   - Must succeed - if they fail after all retries, the flow fails
   - Use ``routine.set_as_critical()`` to mark a routine as critical
   - Uses RETRY strategy with ``is_critical=True``
   - If all retries fail, the flow will fail
   - Perfect for operations that are essential to the workflow

**Basic Example**:

.. code-block:: python

   from routilux import Flow, Routine, ErrorStrategy

   class OptionalRoutine(Routine):
       def __call__(self):
           raise ValueError("Optional failed")

   class CriticalRoutine(Routine):
       def __call__(self):
           raise ConnectionError("Critical failed")

   flow = Flow()
   
   # Mark as optional (failures tolerated)
   optional = OptionalRoutine()
   optional.set_as_optional()  # Uses CONTINUE by default
   # or: optional.set_as_optional(ErrorStrategy.SKIP)
   optional_id = flow.add_routine(optional, "optional")
   
   # Mark as critical (must succeed, retry on failure)
   critical = CriticalRoutine()
   critical.set_as_critical(max_retries=5, retry_delay=2.0)
   critical_id = flow.add_routine(critical, "critical")
   
   job_state = flow.execute(optional_id)
   
   # Optional routine failure is tolerated
   # Critical routine will retry, and if all retries fail, flow fails

**Real-World Example: Data Processing Pipeline**:

.. code-block:: python

   from routilux import Flow, Routine, ErrorStrategy

   class DataFetcher(Routine):
       """Critical: Must fetch data successfully"""
       def __init__(self):
           super().__init__()
           self.output_event = self.add_event("output", ["data"])
       
       def __call__(self):
           # Simulate network operation that may fail
           import random
           if random.random() < 0.3:
               raise ConnectionError("Network timeout")
           self.emit("output", data={"value": 42})

   class DataEnricher(Routine):
       """Optional: Enhancement that can fail"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["enriched_data"])
       
       def __call__(self):
           # This may fail, but it's optional
           raise ValueError("Enrichment service unavailable")
       
       def process(self, data):
           # Process data if available
           pass

   class DataValidator(Routine):
       """Critical: Must validate data"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.validated = False
       
       def __call__(self):
           # Critical validation that must succeed
           raise ValueError("Validation failed")
       
       def process(self, data):
           self.validated = True

   class MetricsCollector(Routine):
       """Optional: Metrics collection"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
       
       def __call__(self):
           # Optional metrics - failure is OK
           raise ValueError("Metrics service down")
       
       def process(self, data):
           # Collect metrics
           pass

   flow = Flow()
   
   # Critical: Data fetching - must succeed
   fetcher = DataFetcher()
   fetcher.set_as_critical(max_retries=3, retry_delay=1.0)
   fetcher_id = flow.add_routine(fetcher, "fetcher")
   
   # Optional: Data enrichment - failure is OK
   enricher = DataEnricher()
   enricher.set_as_optional()  # Uses CONTINUE
   enricher_id = flow.add_routine(enricher, "enricher")
   
   # Critical: Data validation - must succeed
   validator = DataValidator()
   validator.set_as_critical(max_retries=2, retry_delay=0.5)
   validator_id = flow.add_routine(validator, "validator")
   
   # Optional: Metrics collection - failure is OK
   metrics = MetricsCollector()
   metrics.set_as_optional(ErrorStrategy.SKIP)  # Use SKIP instead of CONTINUE
   metrics_id = flow.add_routine(metrics, "metrics")
   
   # Build pipeline
   flow.connect(fetcher_id, "output", enricher_id, "input")
   flow.connect(fetcher_id, "output", validator_id, "input")
   flow.connect(fetcher_id, "output", metrics_id, "input")
   
   job_state = flow.execute(fetcher_id)
   
   # If fetcher or validator fail after retries, flow fails
   # If enricher or metrics fail, flow continues

**When to Use Optional vs Critical**:

Use **Optional** for:
* Logging and monitoring operations
* Non-essential data enrichment
* Optional feature flags
* Metrics collection
* Caching operations
* Any operation where failure doesn't impact core functionality

Use **Critical** for:
* Data fetching that the workflow depends on
* Payment processing
* Database writes that must succeed
* Authentication/authorization
* Any operation where failure should stop the workflow

The ``is_critical`` Flag
~~~~~~~~~~~~~~~~~~~~~~~~~

The ``is_critical`` flag in ErrorHandler indicates whether a routine is critical.
For RETRY strategy:
- If ``is_critical=False``: Retry failures follow normal RETRY behavior
- If ``is_critical=True``: Retry failures cause the flow to fail

**Example**:

.. code-block:: python

   from routilux import ErrorHandler, ErrorStrategy

   # Non-critical routine - retry failures may be tolerated depending on strategy
   handler1 = ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=3,
       is_critical=False
   )
   
   # Critical routine - retry failures cause flow to fail
   handler2 = ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=3,
       is_critical=True
   )

Error Handling in Concurrent Execution
----------------------------------------

In concurrent execution mode, error handling works the same way, but with some
important considerations:

**Behavior**:
* Each routine executes in its own thread
* Errors in one routine don't stop other routines
* Error handler is called per-routine (not per-thread)
* Retry delays happen in the thread where the error occurred
* Routine-level error handlers are respected in concurrent mode

**Example**:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class UnreliableRoutine(Routine):
       def __init__(self, name):
           super().__init__()
           self.name = name
           self.output_event = self.add_event("output", ["data"])
       
       def __call__(self):
           # May fail
           if random.random() < 0.3:
               raise ValueError(f"{self.name} failed")
           self.emit("output", data=f"{self.name} succeeded")

   flow = Flow(execution_strategy="concurrent", max_workers=5)
   
   # Add multiple routines
   for i in range(5):
       routine = UnreliableRoutine(f"routine_{i}")
       flow.add_routine(routine, f"routine_{i}")
   
   error_handler = ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=2,
       retry_delay=0.1
   )
   flow.set_error_handler(error_handler)
   
   # Execute - routines run concurrently
   from routilux.job_state import JobState
   job_state = flow.execute("routine_0")
   JobState.wait_for_completion(flow, job_state)
   flow.shutdown()
   
   # Each routine's errors are handled independently

Error Context and Information
------------------------------

When an error occurs, the error handler receives context information:

* **error**: The exception object that occurred
* **routine**: The routine where the error occurred
* **routine_id**: ID of the routine
* **flow**: The flow object managing execution
* **context**: Optional context dictionary (currently not used by default)

**Accessing Error Information**:

.. code-block:: python

   # From job_state
   job_state = flow.execute(entry_routine_id)
   
   # Check execution history for errors
   for record in job_state.execution_history:
       if record.action in ["error", "error_continued"]:
           print(f"Error in {record.routine_id}: {record.data.get('error')}")
   
   # Check routine state
   routine_state = job_state.get_routine_state(routine_id)
   if "error" in routine_state:
       print(f"Error: {routine_state['error']}")

Resetting Error Handler
-----------------------

Reset the retry count for a new execution:

.. code-block:: python

   error_handler = ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=3
   )
   
   # After some retries
   error_handler.retry_count = 2
   
   # Reset for new execution
   error_handler.reset()
   assert error_handler.retry_count == 0

Best Practices
--------------

1. **Choose the Right Strategy**:
   * Use **STOP** for critical workflows where any error is unacceptable
   * Use **CONTINUE** for non-critical workflows where partial success is acceptable
   * Use **RETRY** for transient failures (network, timeouts, rate limits)
   * Use **SKIP** for optional processing steps that can be safely skipped

2. **Use Routine-Level Handlers for Flexibility**:
   * Set flow-level handler as default
   * Override with routine-level handlers for special cases
   * Use ``set_as_critical()`` and ``set_as_optional()`` for common patterns

3. **Configure Retry Carefully**:
   * Set appropriate ``max_retries`` based on your use case (3-5 is usually good)
   * Use exponential backoff for network operations (backoff=2.0)
   * Restrict ``retryable_exceptions`` to avoid retrying non-retryable errors
   * Consider total retry time: ``retry_delay * (backoff ** max_retries)``

4. **Distinguish Critical from Optional**:
   * Mark truly critical operations with ``set_as_critical()``
   * Mark non-essential operations with ``set_as_optional()``
   * This makes your workflow's error handling intent clear

5. **Monitor Errors**:
   * Check ``job_state.execution_history`` for error records
   * Check ``routine.stats()["errors"]`` for slot handler errors
   * Log errors appropriately for debugging and monitoring
   * Set up alerts for critical routine failures

6. **Handle Slot Handler Errors**:
   * Always check ``routine.stats()["errors"]`` after execution
   * Implement validation in slot handlers to prevent errors
   * Use try-except in slot handlers if you need custom error handling
   * Remember: slot handler errors don't trigger error handling strategies

7. **Test Error Scenarios**:
   * Test all error handling strategies
   * Test retry logic with various failure patterns
   * Test concurrent execution error handling
   * Test mixed critical/optional scenarios

8. **Understand CONTINUE vs SKIP**:
   * Use **CONTINUE** when you attempted the operation but it failed
   * Use **SKIP** when the operation wasn't needed or shouldn't be attempted
   * Both allow flow to continue, but have different semantic meanings

Real-World Examples
-------------------

**Example 1: E-Commerce Order Processing**

.. code-block:: python

   from routilux import Flow, Routine

   class PaymentProcessor(Routine):
       """Critical: Payment must succeed"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("order", handler=self.process)
           self.output_event = self.add_event("payment_complete", ["order_id"])
       
       def __call__(self):
           # Critical payment operation
           raise ConnectionError("Payment gateway timeout")
       
       def process(self, order):
           # Process payment
           pass

   class InventoryUpdater(Routine):
       """Critical: Inventory must be updated"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("order", handler=self.process)
       
       def __call__(self):
           raise ConnectionError("Inventory service error")
       
       def process(self, order):
           # Update inventory
           pass

   class EmailNotifier(Routine):
       """Optional: Email notification"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("order", handler=self.process)
       
       def __call__(self):
           raise ValueError("Email service unavailable")
       
       def process(self, order):
           # Send email
           pass

   class AnalyticsLogger(Routine):
       """Optional: Analytics logging"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("order", handler=self.process)
       
       def __call__(self):
           raise ValueError("Analytics service down")
       
       def process(self, order):
           # Log analytics
           pass

   flow = Flow()
   
   # Critical operations - must succeed
   payment = PaymentProcessor()
   payment.set_as_critical(max_retries=5, retry_delay=1.0)
   payment_id = flow.add_routine(payment, "payment")
   
   inventory = InventoryUpdater()
   inventory.set_as_critical(max_retries=3, retry_delay=0.5)
   inventory_id = flow.add_routine(inventory, "inventory")
   
   # Optional operations - failures tolerated
   email = EmailNotifier()
   email.set_as_optional()  # Use CONTINUE
   email_id = flow.add_routine(email, "email")
   
   analytics = AnalyticsLogger()
   analytics.set_as_optional(ErrorStrategy.SKIP)  # Use SKIP
   analytics_id = flow.add_routine(analytics, "analytics")
   
   # Connect: payment -> inventory, and both -> email/analytics
   flow.connect(payment_id, "payment_complete", inventory_id, "order")
   flow.connect(payment_id, "payment_complete", email_id, "order")
   flow.connect(payment_id, "payment_complete", analytics_id, "order")
   
   # If payment or inventory fail after retries, order fails
   # If email or analytics fail, order still succeeds

**Example 2: Data Pipeline with Multiple Sources**

.. code-block:: python

   from routilux import Flow, Routine, ErrorStrategy

   class PrimaryDataSource(Routine):
       """Critical: Primary data source"""
       def __init__(self):
           super().__init__()
           self.output_event = self.add_event("output", ["data"])
       
       def __call__(self):
           raise ConnectionError("Primary source unavailable")

   class SecondaryDataSource(Routine):
       """Optional: Secondary data source for enrichment"""
       def __init__(self):
           super().__init__()
           self.output_event = self.add_event("output", ["enrichment"])
       
       def __call__(self):
           raise ValueError("Secondary source unavailable")

   class DataAggregator(Routine):
       """Critical: Must aggregate data"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("primary", handler=self.process_primary)
           self.input_slot2 = self.add_slot("secondary", handler=self.process_secondary)
           self.aggregated = False
       
       def __call__(self):
           raise ConnectionError("Aggregation service error")
       
       def process_primary(self, data):
           self.primary_data = data
       
       def process_secondary(self, data):
           self.secondary_data = data

   flow = Flow()
   
   # Primary source - critical, retry on failure
   primary = PrimaryDataSource()
   primary.set_as_critical(max_retries=3, retry_delay=1.0)
   primary_id = flow.add_routine(primary, "primary")
   
   # Secondary source - optional, failures tolerated
   secondary = SecondaryDataSource()
   secondary.set_as_optional()
   secondary_id = flow.add_routine(secondary, "secondary")
   
   # Aggregator - critical, must succeed
   aggregator = DataAggregator()
   aggregator.set_as_critical(max_retries=2, retry_delay=0.5)
   aggregator_id = flow.add_routine(aggregator, "aggregator")
   
   flow.connect(primary_id, "output", aggregator_id, "primary")
   flow.connect(secondary_id, "output", aggregator_id, "secondary")
   
   # Primary source failure after retries -> pipeline fails
   # Secondary source failure -> pipeline continues (optional)
   # Aggregator failure after retries -> pipeline fails

**Example 3: API Gateway with Rate Limiting**

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class APIGateway(Routine):
       def __init__(self):
           super().__init__()
           self.attempts = 0
           self.output_event = self.add_event("output", ["response"])
       
       def __call__(self):
           self.attempts += 1
           # Simulate rate limiting
           if self.attempts < 4:
               raise ConnectionError(f"Rate limited (attempt {self.attempts})")
           self.emit("output", response={"status": "ok"})

   flow = Flow()
   gateway = APIGateway()
   
   # Retry with exponential backoff for rate limiting
   gateway.set_error_handler(ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=5,
       retry_delay=2.0,      # Start with 2 seconds
       retry_backoff=2.0,    # Double each time: 2s, 4s, 8s, 16s, 32s
       retryable_exceptions=(ConnectionError,)  # Only retry connection errors
   ))
   gateway_id = flow.add_routine(gateway, "gateway")
   
   job_state = flow.execute(gateway_id)
   
   # Should succeed after retries with exponential backoff
   assert job_state.status == "completed"
   assert gateway.attempts == 4

Common Patterns
---------------

This section provides practical patterns for common error handling scenarios.

**Pattern 1: Retry with Exponential Backoff**

Use exponential backoff for network operations or rate-limited APIs:

.. code-block:: python

   from routilux import ErrorHandler, ErrorStrategy

   error_handler = ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=5,
       retry_delay=1.0,      # Start with 1 second
       retry_backoff=2.0     # Double each time: 1s, 2s, 4s, 8s, 16s
   )
   
   # Retry delays: 1s, 2s, 4s, 8s, 16s
   # Total wait time if all retries fail: ~31 seconds

**Pattern 2: Continue on Non-Critical Errors**

Allow workflow to complete even if some operations fail:

.. code-block:: python

   from routilux import Flow, ErrorHandler, ErrorStrategy

   error_handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)
   flow.set_error_handler(error_handler)
   
   job_state = flow.execute(entry_routine_id)
   
   # After execution, check for errors
   errors = [r for r in job_state.execution_history if "error" in r.action]
   if errors:
       # Handle errors but don't fail the workflow
       print(f"Workflow completed with {len(errors)} errors")
       for error_record in errors:
           print(f"  - {error_record.routine_id}: {error_record.data.get('error')}")

**Pattern 3: Skip Optional Steps**

Skip optional processing steps that aren't critical:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class MainProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.output_event = self.add_event("output", ["result"])
       
       def __call__(self):
           self.emit("output", result="processed")

   class OptionalEnhancer(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["enhanced"])
       
       def __call__(self):
           # Optional enhancement - can be skipped
           raise ValueError("Enhancement unavailable")

   flow = Flow()
   main_id = flow.add_routine(MainProcessor(), "main")
   optional_id = flow.add_routine(OptionalEnhancer(), "optional")
   
   flow.connect(main_id, "output", optional_id, "input")
   
   # Use SKIP for optional steps
   optional.set_error_handler(ErrorHandler(strategy=ErrorStrategy.SKIP))
   
   job_state = flow.execute(main_id)
   # If optional fails, it's skipped and execution continues

**Pattern 4: Retry Only Specific Exceptions**

Only retry errors that might succeed on retry:

.. code-block:: python

   from routilux import ErrorHandler, ErrorStrategy

   error_handler = ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=3,
       retryable_exceptions=(ConnectionError, TimeoutError, OSError)
   )
   
   # Network errors will be retried
   # Validation errors (ValueError, TypeError) will stop immediately

**Pattern 5: Mixed Critical and Optional Routines**

Combine critical and optional routines in a single workflow:

.. code-block:: python

   from routilux import Flow, Routine

   class DataFetcher(Routine):
       def __init__(self):
           super().__init__()
           self.output_event = self.add_event("output", ["data"])
       
       def __call__(self):
           self.emit("output", data="important data")

   class CriticalProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.processed = False
       
       def __call__(self):
           raise ConnectionError("Critical operation failed")
       
       def process(self, data):
           self.processed = True

   class OptionalLogger(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
       
       def __call__(self):
           raise ValueError("Logging failed")

   flow = Flow()
   
   fetcher = DataFetcher()
   fetcher_id = flow.add_routine(fetcher, "fetcher")
   
   critical = CriticalProcessor()
   critical.set_as_critical(max_retries=3, retry_delay=0.5)
   critical_id = flow.add_routine(critical, "critical")
   
   optional = OptionalLogger()
   optional.set_as_optional()  # Failures tolerated
   optional_id = flow.add_routine(optional, "optional")
   
   flow.connect(fetcher_id, "output", critical_id, "input")
   flow.connect(fetcher_id, "output", optional_id, "input")
   
   job_state = flow.execute(fetcher_id)
   
   # Critical must succeed (retries on failure)
   # Optional failures are tolerated

**Pattern 6: Routine-Level Override**

Override flow-level handler for specific routines:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class NetworkRoutine(Routine):
       def __call__(self):
           raise ConnectionError("Network error")

   class ValidationRoutine(Routine):
       def __call__(self):
           raise ValueError("Validation error")

   flow = Flow()
   
   # Flow-level: Stop on all errors
   flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.STOP))
   
   # Network routine: Retry on failure (overrides flow-level)
   network = NetworkRoutine()
   network.set_error_handler(ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=3,
       retry_delay=1.0
   ))
   network_id = flow.add_routine(network, "network")
   
   # Validation routine: Use flow-level handler (STOP)
   validation = ValidationRoutine()
   validation_id = flow.add_routine(validation, "validation")
   
   # Network routine will retry
   # Validation routine will stop immediately (uses flow-level handler)

Complete Examples
-----------------

**Example 1: Complete E-Commerce Workflow**

This example shows a complete e-commerce order processing workflow with proper error handling:

.. code-block:: python

   from routilux import Flow, Routine, ErrorStrategy
   import random

   class OrderValidator(Routine):
       """Critical: Must validate order"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("order", handler=self.process)
           self.output_event = self.add_event("validated", ["order"])
       
       def __call__(self):
           # Critical validation
           if random.random() < 0.2:
               raise ValueError("Invalid order data")
           self.emit("validated", order={"id": 123, "total": 99.99})
       
       def process(self, order):
           # Process validated order
           pass

   class PaymentProcessor(Routine):
       """Critical: Payment must succeed"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("order", handler=self.process)
           self.output_event = self.add_event("paid", ["order_id"])
       
       def __call__(self):
           # Critical payment operation
           if random.random() < 0.3:
               raise ConnectionError("Payment gateway timeout")
           self.emit("paid", order_id=123)
       
       def process(self, order):
           # Process payment
           pass

   class InventoryManager(Routine):
       """Critical: Inventory must be updated"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("order", handler=self.process)
           self.output_event = self.add_event("reserved", ["order_id"])
       
       def __call__(self):
           # Critical inventory operation
           if random.random() < 0.25:
               raise ConnectionError("Inventory service error")
           self.emit("reserved", order_id=123)
       
       def process(self, order):
           # Reserve inventory
           pass

   class EmailService(Routine):
       """Optional: Email notification"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("order", handler=self.process)
       
       def __call__(self):
           # Optional email - failure is OK
           if random.random() < 0.5:
               raise ValueError("Email service unavailable")
       
       def process(self, order):
           # Send confirmation email
           pass

   class AnalyticsService(Routine):
       """Optional: Analytics tracking"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("order", handler=self.process)
       
       def __call__(self):
           # Optional analytics - failure is OK
           if random.random() < 0.4:
               raise ValueError("Analytics service down")
       
       def process(self, order):
           # Track order analytics
           pass

   # Build workflow
   flow = Flow()
   
   # Critical operations - must succeed
   validator = OrderValidator()
   validator.set_as_critical(max_retries=3, retry_delay=0.5)
   validator_id = flow.add_routine(validator, "validator")
   
   payment = PaymentProcessor()
   payment.set_as_critical(max_retries=5, retry_delay=1.0)
   payment_id = flow.add_routine(payment, "payment")
   
   inventory = InventoryManager()
   inventory.set_as_critical(max_retries=3, retry_delay=0.5)
   inventory_id = flow.add_routine(inventory, "inventory")
   
   # Optional operations - failures tolerated
   email = EmailService()
   email.set_as_optional()  # Use CONTINUE
   email_id = flow.add_routine(email, "email")
   
   analytics = AnalyticsService()
   analytics.set_as_optional(ErrorStrategy.SKIP)  # Use SKIP
   analytics_id = flow.add_routine(analytics, "analytics")
   
   # Connect workflow
   flow.connect(validator_id, "validated", payment_id, "order")
   flow.connect(payment_id, "paid", inventory_id, "order")
   flow.connect(payment_id, "paid", email_id, "order")
   flow.connect(payment_id, "paid", analytics_id, "order")
   
   # Execute
   job_state = flow.execute(validator_id)
   
   # Critical operations (validator, payment, inventory) must succeed
   # Optional operations (email, analytics) failures are tolerated
   # If any critical operation fails after retries, order fails
   # If optional operations fail, order still succeeds

**Example 2: Data Pipeline with Fallback**

This example shows a data pipeline with primary and fallback data sources:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class PrimaryDataSource(Routine):
       """Critical: Primary data source"""
       def __init__(self):
           super().__init__()
           self.output_event = self.add_event("output", ["data"])
       
       def __call__(self):
           # Primary source may fail
           raise ConnectionError("Primary source unavailable")

   class FallbackDataSource(Routine):
       """Critical: Fallback if primary fails"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("trigger", handler=self.process)
           self.output_event = self.add_event("output", ["data"])
       
       def __call__(self):
           # Fallback source
           self.emit("output", data={"source": "fallback", "value": 100})
       
       def process(self, trigger):
           # Triggered when primary fails
           pass

   class DataProcessor(Routine):
       """Critical: Must process data"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("data", handler=self.process)
           self.processed = False
       
       def __call__(self):
           # Critical processing
           raise ValueError("Processing error")
       
       def process(self, data):
           self.processed = True
           self.data = data

   flow = Flow()
   
   # Primary source - critical, retry on failure
   primary = PrimaryDataSource()
   primary.set_as_critical(max_retries=2, retry_delay=1.0)
   primary_id = flow.add_routine(primary, "primary")
   
   # Fallback source - critical, used if primary fails
   fallback = FallbackDataSource()
   fallback.set_as_critical(max_retries=1, retry_delay=0.5)
   fallback_id = flow.add_routine(fallback, "fallback")
   
   # Processor - critical, must process data
   processor = DataProcessor()
   processor.set_as_critical(max_retries=3, retry_delay=0.5)
   processor_id = flow.add_routine(processor, "processor")
   
   # Connect: primary -> processor, fallback -> processor
   flow.connect(primary_id, "output", processor_id, "data")
   flow.connect(fallback_id, "output", processor_id, "data")
   
   # If primary fails, fallback provides data
   # Processor must succeed with data from either source

**Example 3: Microservices Integration**

This example shows error handling in a microservices architecture:

.. code-block:: python

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class UserService(Routine):
       """Critical: User authentication"""
       def __init__(self):
           super().__init__()
           self.output_event = self.add_event("authenticated", ["user"])
       
       def __call__(self):
           # Critical authentication
           raise ConnectionError("User service timeout")

   class ProductService(Routine):
       """Critical: Product information"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("user", handler=self.process)
           self.output_event = self.add_event("products", ["product_list"])
       
       def __call__(self):
           # Critical product fetch
           raise ConnectionError("Product service error")
       
       def process(self, user):
           # Process user context
           pass

   class RecommendationService(Routine):
       """Optional: Product recommendations"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("products", handler=self.process)
       
       def __call__(self):
           # Optional recommendations
           raise ValueError("Recommendation service unavailable")
       
       def process(self, products):
           # Generate recommendations
           pass

   class CacheService(Routine):
       """Optional: Caching"""
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("data", handler=self.process)
       
       def __call__(self):
           # Optional caching
           raise ValueError("Cache service down")
       
       def process(self, data):
           # Cache data
           pass

   flow = Flow()
   
   # Critical services - must succeed
   user_service = UserService()
   user_service.set_error_handler(ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=3,
       retry_delay=1.0,
       retryable_exceptions=(ConnectionError, TimeoutError),
       is_critical=True
   ))
   user_id = flow.add_routine(user_service, "user_service")
   
   product_service = ProductService()
   product_service.set_error_handler(ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=3,
       retry_delay=1.0,
       retryable_exceptions=(ConnectionError,),
       is_critical=True
   ))
   product_id = flow.add_routine(product_service, "product_service")
   
   # Optional services - failures tolerated
   recommendation_service = RecommendationService()
   recommendation_service.set_as_optional()
   recommendation_id = flow.add_routine(recommendation_service, "recommendation")
   
   cache_service = CacheService()
   cache_service.set_as_optional(ErrorStrategy.SKIP)
   cache_id = flow.add_routine(cache_service, "cache")
   
   # Connect services
   flow.connect(user_id, "authenticated", product_id, "user")
   flow.connect(product_id, "products", recommendation_id, "products")
   flow.connect(product_id, "products", cache_id, "data")
   
   # Critical services must succeed (user, product)
   # Optional services can fail (recommendation, cache)

Decision Guide
--------------

Use this guide to choose the right error handling strategy:

**When to Use STOP**:
* Any error is unacceptable
* You need immediate failure notification
* Data integrity is critical
* Default behavior for safety

**When to Use CONTINUE**:
* Some failures are acceptable
* You want to process as much as possible
* Non-critical operations
* Logging and monitoring scenarios

**When to Use RETRY**:
* Transient failures (network, timeouts)
* Rate-limited operations
* Operations that may succeed on retry
* Network operations
* External API calls

**When to Use SKIP**:
* Optional processing steps
* Operations that aren't needed
* Fallback scenarios
* Conditional processing

**When to Use Routine-Level Handlers**:
* Different routines need different strategies
* Some routines are critical, others optional
* Fine-grained control needed
* Override flow-level defaults

**When to Use Critical Routines**:
* Operation must succeed for workflow to succeed
* Payment processing
* Data persistence
* Authentication/authorization
* Core business logic

**When to Use Optional Routines**:
* Operation failure doesn't impact core functionality
* Logging and metrics
* Optional enhancements
* Caching operations
* Non-essential features

JobState Status Transitions and Error Strategy Impact
======================================================

Understanding how error handling strategies affect JobState status is crucial for
building robust workflows. This section provides detailed tables showing all possible
status transitions.

JobState Status Values
----------------------

The ``JobState.status`` field can have the following values:

* ``"pending"``: Flow created but not yet started
* ``"running"``: Flow execution in progress
* ``"completed"``: Flow execution completed successfully
* ``"failed"``: Flow execution failed due to error
* ``"paused"``: Flow execution paused (can be resumed)
* ``"cancelled"``: Flow execution cancelled by user

Routine State Status Values
---------------------------

Each routine's state (in ``job_state.routine_states[routine_id]``) can have:

* ``"pending"``: Routine not yet executed
* ``"running"``: Routine execution in progress
* ``"completed"``: Routine executed successfully
* ``"failed"``: Routine execution failed (critical failure)
* ``"error_continued"``: Routine failed but execution continued (CONTINUE strategy)
* ``"skipped"``: Routine was skipped (SKIP strategy)

Status Transition Table: Error Strategies
------------------------------------------

The following table shows how different error handling strategies affect both
JobState status and routine state status:

+------------------+------------------+------------------+------------------+------------------+
| Strategy         | When             | JobState Status  | Routine Status   | Notes            |
+==================+==================+==================+==================+==================+
| STOP             | Error occurs     | failed           | failed           | Immediate stop   |
+------------------+------------------+------------------+------------------+------------------+
| CONTINUE         | Error occurs     | completed        | error_continued  | Error logged,    |
|                  |                  |                  |                  | execution        |
|                  |                  |                  |                  | continues        |
+------------------+------------------+------------------+------------------+------------------+
| RETRY            | Retry succeeds   | completed        | completed        | After successful |
|                  |                  |                  |                  | retry            |
+------------------+------------------+------------------+------------------+------------------+
| RETRY            | All retries fail | failed           | failed           | Max retries      |
|                  |                  |                  |                  | exceeded         |
+------------------+------------------+------------------+------------------+------------------+
| RETRY            | Non-retryable    | failed           | failed           | Exception not in |
|                  | exception        |                  |                  | retryable_exc... |
+------------------+------------------+------------------+------------------+------------------+
| SKIP             | Error occurs     | completed        | skipped          | Routine skipped, |
|                  |                  |                  |                  | flow continues   |
+------------------+------------------+------------------+------------------+------------------+

**Key Points**:

* **STOP**: Always results in ``failed`` status for both JobState and routine
* **CONTINUE**: JobState is ``completed``, routine is ``error_continued``
* **RETRY**: Status depends on whether retries succeed or all fail
* **SKIP**: JobState is ``completed``, routine is ``skipped``

Status Transition Table: Slot Handler Errors
---------------------------------------------

Slot handler errors are handled differently from entry routine errors:

+------------------+------------------+------------------+------------------+------------------+
| Scenario         | Error Handler    | JobState Status  | Routine Status   | Notes            |
+==================+==================+==================+==================+==================+
| Slot handler     | None             | completed        | (not set)        | Error logged to  |
| error            |                  |                  |                  | execution        |
|                  |                  |                  |                  | history only     |
+------------------+------------------+------------------+------------------+------------------+
| Slot handler     | STOP strategy    | completed        | failed           | Error logged,    |
| error            |                  |                  |                  | routine marked   |
|                  |                  |                  |                  | as failed        |
+------------------+------------------+------------------+------------------+------------------+
| Slot handler     | CONTINUE/RETRY/  | completed        | (not set)        | Error logged to  |
| error            | SKIP strategy    |                  |                  | execution        |
|                  |                  |                  |                  | history only     |
+------------------+------------------+------------------+------------------+------------------+

**Important**: Slot handler errors are **always caught** and do not stop flow execution.
However, if the routine has an error handler with STOP strategy, the routine state
will be marked as ``failed``, which will be detected by ``wait_for_completion()``.

Status Detection in wait_for_completion()
------------------------------------------

The ``JobState.wait_for_completion()`` method intelligently detects failures by
checking routine states, not just execution history:

**Detection Logic**:

1. **Checks routine states** for ``"failed"`` or ``"error"`` status (not ``"error_continued"``)
2. **Does NOT check execution history** alone (slot handler errors are logged but tolerated)
3. **Distinguishes critical failures** from tolerated errors:
   - Critical: routine status is ``"failed"`` or ``"error"`` → JobState becomes ``"failed"``
   - Tolerated: routine status is ``"error_continued"`` → JobState becomes ``"completed"``
   - Slot errors: only in execution history, routine status not ``"failed"`` → JobState becomes ``"completed"``

**Example**:

.. code-block:: python

   from routilux.job_state import JobState
   
   # Wait for completion - automatically detects failures
   completed = JobState.wait_for_completion(flow, job_state, timeout=60.0)
   
   # If routine states contain "failed" status, job_state.status will be "failed"
   # If only "error_continued" or no routine failures, job_state.status will be "completed"

**Why This Design?**:

The distinction between routine state checking and execution history checking is crucial:

* **Execution history** contains all events, including tolerated errors (slot handler errors,
  CONTINUE strategy errors). Checking execution history alone would incorrectly mark
  many successful workflows as failed.

* **Routine state** reflects the actual outcome of each routine:
  - ``"failed"`` or ``"error"`` = critical failure that should fail the workflow
  - ``"error_continued"`` = tolerated error, workflow should be marked as completed
  - ``"skipped"`` = intentionally skipped, workflow should be marked as completed
  - ``"completed"`` = successful execution

* **Result**: Only critical failures (routine state ``"failed"``) cause JobState to be
  marked as ``"failed"``. Tolerated errors and slot handler errors don't cause workflow
  failure.

**Migration Note**:

The old ``Flow.wait_for_completion()`` method only waited for the event loop thread
to finish, without checking for errors. This could result in workflows with errors
being marked as ``"completed"``. The new ``JobState.wait_for_completion()`` method
provides comprehensive error detection and is the recommended approach.

**Deprecation**:

``Flow.wait_for_completion()`` is deprecated. Use ``JobState.wait_for_completion()``
instead for proper error detection and status management.

Quick Reference Table
---------------------

**Error Handling Strategies**:

+------------------+------------------+------------------+------------------+
| Strategy         | Flow Status      | Routine Status   | Use Case         |
+==================+==================+==================+==================+
| STOP             | failed           | failed           | Critical errors  |
+------------------+------------------+------------------+------------------+
| CONTINUE         | completed        | error_continued  | Tolerable errors |
+------------------+------------------+------------------+------------------+
| RETRY            | completed/failed | completed/failed | Transient errors |
+------------------+------------------+------------------+------------------+
| SKIP             | completed        | skipped          | Optional steps   |
+------------------+------------------+------------------+------------------+

**Priority Order**:
1. Routine-level error handler (if set)
2. Flow-level error handler (if set)
3. Default behavior (STOP)

**CONTINUE vs SKIP Comparison**:

+------------------+------------------+------------------+
| Aspect           | CONTINUE         | SKIP             |
+==================+==================+==================+
| Semantic         | Tried but failed | Skipped          |
+------------------+------------------+------------------+
| Routine Status   | error_continued  | skipped          |
+------------------+------------------+------------------+
| Use When         | Attempted op     | Optional op      |
+------------------+------------------+------------------+
| Example          | Logging failed   | Enhancement skip |
+------------------+------------------+------------------+
| Flow Continues   | Yes              | Yes              |
+------------------+------------------+------------------+

**Critical vs Optional Routines**:

+------------------+------------------+------------------+
| Aspect           | Critical         | Optional         |
+==================+==================+==================+
| Method           | set_as_critical()| set_as_optional()|
+------------------+------------------+------------------+
| Strategy         | RETRY            | CONTINUE/SKIP    |
+------------------+------------------+------------------+
| is_critical      | True              | False           |
+------------------+------------------+------------------+
| Retry Failure    | Flow fails       | Flow continues   |
+------------------+------------------+------------------+
| Use Case         | Must succeed     | Failures OK      |
+------------------+------------------+------------------+

**Retry Configuration**:

+------------------+------------------+-------------------+
| Parameter        | Default          | Description       |
+==================+==================+===================+
| max_retries      | 3                | Max retry attempts|
+------------------+-------------------+------------------+
| retry_delay      | 1.0              | Initial delay (s) |
+------------------+-------------------+------------------+
| retry_backoff    | 2.0              | Backoff multiplier|
+------------------+-------------------+------------------+
| retryable_exc... | (Exception,)     | Retryable types   |
+------------------+-------------------+------------------+

See Also
--------

* :doc:`flows` - Flow execution and error handling in flows
* :doc:`state_management` - Accessing error information in routine stats
* :doc:`routines` - Routine-level error handling configuration
* :doc:`../api_reference/error_handler` - ErrorHandler API documentation
