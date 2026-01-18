Error Handling
===============

In this tutorial, you'll learn how to build resilient workflows that handle
errors gracefully using Routilux's error handling strategies.

Learning Objectives
-------------------

By the end of this tutorial, you'll be able to:

- Understand different error handling strategies (STOP, CONTINUE, RETRY, SKIP)
- Configure error handlers at flow and routine levels
- Use retry mechanisms with exponential backoff
- Mark routines as critical or optional
- Build fault-tolerant workflows

Step 1: Understanding Error Strategies
---------------------------------------

Routilux provides four error handling strategies:

1. **STOP** (default): Stop execution immediately on error
2. **CONTINUE**: Log error but continue execution
3. **RETRY**: Automatically retry failed routines
4. **SKIP**: Skip failed routine and continue

Let's see each strategy in action:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class UnreliableRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.process)
           self.output_event = self.add_event("output", ["data"])
           self.call_count = 0
       
       def process(self, **kwargs):
           self.call_count += 1
           if self.call_count < 3:
               raise ValueError(f"Error on attempt {self.call_count}")
           self.emit("output", data=f"Success after {self.call_count} attempts")

   class SuccessRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.receive)
           self.executed = False
       
       def receive(self, data=None, **kwargs):
           data_value = data or kwargs.get("data", "")
           self.executed = True
           print(f"Success routine received: {data_value}")

   # Test with STOP strategy (default)
   print("=== STOP Strategy (default) ===")
   flow1 = Flow(flow_id="stop_test")
   unreliable1 = UnreliableRoutine()
   success1 = SuccessRoutine()
   
   u1_id = flow1.add_routine(unreliable1, "unreliable")
   s1_id = flow1.add_routine(success1, "success")
   
   flow1.connect(u1_id, "output", s1_id, "input")
   
   # No error handler set - uses default STOP
   job_state1 = flow1.execute(u1_id)
   print(f"Status: {job_state1.status}")
   print(f"Success executed: {success1.executed}")

**Expected Output**:

.. code-block:: text

   === STOP Strategy (default) ===
   Status: failed
   Success executed: False

**Key Points**:

- STOP is the default strategy
- Execution stops immediately on error
- Downstream routines don't execute
- Flow status is set to "failed"

Step 2: Using CONTINUE Strategy
--------------------------------

CONTINUE strategy logs errors but allows execution to continue:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class FailingRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.process)
           self.output_event = self.add_event("output", ["data"])
       
       def process(self, **kwargs):
           raise ValueError("This error will be logged but execution continues")

   class SuccessRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.receive)
       
       def receive(self, data=None, **kwargs):
           print("Success routine executed despite upstream error")

   flow = Flow(flow_id="continue_test")
   
   failing = FailingRoutine()
   success = SuccessRoutine()
   
   failing_id = flow.add_routine(failing, "failing")
   success_id = flow.add_routine(success, "success")
   
   flow.connect(failing_id, "output", success_id, "input")
   
   # Set CONTINUE strategy
   error_handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)
   flow.set_error_handler(error_handler)
   
   job_state = flow.execute(failing_id)
   print(f"Status: {job_state.status}")  # Still "completed" despite error

**Expected Output**:

.. code-block:: text

   Status: completed

**Key Points**:

- CONTINUE logs errors but doesn't stop execution
- Flow status remains "completed" (not "failed")
- Useful for non-critical operations
- Downstream routines still execute

Step 3: Using RETRY Strategy
------------------------------

RETRY strategy automatically retries failed routines:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy
   import time

   class UnreliableRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.process)
           self.output_event = self.add_event("output", ["data"])
           self.call_count = 0
       
       def process(self, **kwargs):
           self.call_count += 1
           print(f"Attempt {self.call_count}")
           
           if self.call_count < 3:
               raise ValueError(f"Error on attempt {self.call_count}")
           
           self.emit("output", data=f"Success after {self.call_count} attempts")

   flow = Flow(flow_id="retry_test")
   
   unreliable = UnreliableRoutine()
   unreliable_id = flow.add_routine(unreliable, "unreliable")
   
   # Set RETRY strategy with configuration
   error_handler = ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=5,
       retry_delay=0.1,  # Initial delay
       retry_backoff=2.0  # Exponential backoff multiplier
   )
   flow.set_error_handler(error_handler)
   
   job_state = flow.execute(unreliable_id)
   print(f"Status: {job_state.status}")
   print(f"Total attempts: {unreliable.call_count}")

**Expected Output**:

.. code-block:: text

   Attempt 1
   Attempt 2
   Attempt 3
   Status: completed
   Total attempts: 3

**Key Points**:

- RETRY automatically retries failed routines
- Uses exponential backoff: delay = retry_delay * (backoff ^ (retry_count - 1))
- Retries up to max_retries times
- Only retries retryable exceptions (ValueError, RuntimeError by default)

Step 4: Using SKIP Strategy
----------------------------

SKIP strategy skips failed routines and continues:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class OptionalRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.process)
           self.output_event = self.add_event("output", ["data"])
       
       def process(self, **kwargs):
           raise ValueError("This routine will be skipped")

   class RequiredRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.receive)
           self.executed = False
       
       def receive(self, data=None, **kwargs):
           self.executed = True
           print("Required routine executed")

   flow = Flow(flow_id="skip_test")
   
   optional = OptionalRoutine()
   required = RequiredRoutine()
   
   opt_id = flow.add_routine(optional, "optional")
   req_id = flow.add_routine(required, "required")
   
   flow.connect(opt_id, "output", req_id, "input")
   
   # Set SKIP strategy for optional routine
   skip_handler = ErrorHandler(strategy=ErrorStrategy.SKIP)
   optional.set_error_handler(skip_handler)
   
   job_state = flow.execute(opt_id)
   print(f"Status: {job_state.status}")
   print(f"Required executed: {required.executed}")

**Expected Output**:

.. code-block:: text

   Status: completed
   Required executed: False

**Key Points**:

- SKIP marks routine as "skipped" and continues
- Flow status remains "completed"
- Useful for optional processing steps
- Downstream routines don't receive data from skipped routine

Step 5: Routine-Level Error Handlers
--------------------------------------

You can set error handlers at the routine level to override flow-level handlers:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class CriticalRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.process)
           self.output_event = self.add_event("output", ["data"])
       
       def process(self, **kwargs):
           raise ValueError("Critical error")

   class OptionalRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.process)
           self.output_event = self.add_event("output", ["data"])
       
       def process(self, **kwargs):
           raise ValueError("Optional error")

   flow = Flow(flow_id="routine_level_test")
   
   critical = CriticalRoutine()
   optional = OptionalRoutine()
   
   crit_id = flow.add_routine(critical, "critical")
   opt_id = flow.add_routine(optional, "optional")
   
   # Flow-level: CONTINUE (non-critical default)
   flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
   
   # Routine-level: STOP for critical routine
   critical.set_error_handler(ErrorHandler(strategy=ErrorStrategy.STOP))
   
   # Routine-level: SKIP for optional routine
   optional.set_error_handler(ErrorHandler(strategy=ErrorStrategy.SKIP))
   
   # Test critical (should fail)
   job_state1 = flow.execute(crit_id)
   print(f"Critical status: {job_state1.status}")
   
   # Test optional (should complete)
   job_state2 = flow.execute(opt_id)
   print(f"Optional status: {job_state2.status}")

**Expected Output**:

.. code-block:: text

   Critical status: failed
   Optional status: completed

**Key Points**:

- Routine-level handlers override flow-level handlers
- Priority: Routine-level > Flow-level > Default (STOP)
- Use routine-level handlers for special cases
- Use flow-level handlers for default behavior

Step 6: Critical and Optional Routines
---------------------------------------

You can mark routines as critical (must succeed) or optional using convenience
methods:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class CriticalRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.process)
           self.output_event = self.add_event("output", ["data"])
           self.call_count = 0
       
       def process(self, **kwargs):
           self.call_count += 1
           if self.call_count < 3:
               raise ValueError("Critical error")
           self.emit("output", data="Critical success")

   class OptionalRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.process)
           self.output_event = self.add_event("output", ["data"])
       
       def process(self, **kwargs):
           raise ValueError("Optional error - will be skipped")

   flow = Flow(flow_id="critical_test")
   
   critical = CriticalRoutine()
   optional = OptionalRoutine()
   
   crit_id = flow.add_routine(critical, "critical")
   opt_id = flow.add_routine(optional, "optional")
   
   # Mark as critical with retry
   critical.set_as_critical(max_retries=5, retry_delay=0.1)
   
   # Mark as optional with skip
   optional.set_as_optional()
   
   # Test critical
   job_state1 = flow.execute(crit_id)
   print(f"Critical status: {job_state1.status}")
   print(f"Critical attempts: {critical.call_count}")
   
   # Test optional
   job_state2 = flow.execute(opt_id)
   print(f"Optional status: {job_state2.status}")

**Expected Output**:

.. code-block:: text

   Critical status: completed
   Critical attempts: 3
   Optional status: completed

**Key Points**:

- ``set_as_critical()`` marks routine as critical with retry
- ``set_as_optional()`` marks routine as optional with skip
- Critical routines that fail after retries cause flow to fail
- Optional routines that fail are skipped

Step 7: Complete Example - Resilient Workflow
-----------------------------------------------

Here's a complete example combining error handling strategies:

.. code-block:: python
   :name: error_handling_complete
   :linenos:

   from routilux import Flow, Routine, ErrorHandler, ErrorStrategy

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.generate)
           self.output_event = self.add_event("output", ["data"])
       
       def generate(self, **kwargs):
           self.emit("output", data="test_data")

   class UnreliableValidator(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.validate)
           self.output_event = self.add_event("output", ["data", "valid"])
           self.call_count = 0
       
       def validate(self, data=None, **kwargs):
           self.call_count += 1
           data_value = data or kwargs.get("data", "")
           
           if self.call_count < 2:
               raise ValueError("Validation failed")
           
           self.emit("output", data=data_value, valid=True)

   class Processor(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["result"])
       
       def process(self, data=None, valid=None, **kwargs):
           data_value = data or kwargs.get("data", "")
           is_valid = valid if valid is not None else kwargs.get("valid", False)
           
           if is_valid:
               result = f"Processed: {data_value}"
               self.emit("output", result=result)
           else:
               raise ValueError("Cannot process invalid data")

   class Sink(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.receive)
       
       def receive(self, result=None, **kwargs):
           result_value = result or kwargs.get("result", "")
           print(f"Final result: {result_value}")

   def main():
       flow = Flow(flow_id="resilient_workflow")
       
       source = DataSource()
       validator = UnreliableValidator()
       processor = Processor()
       sink = Sink()
       
       source_id = flow.add_routine(source, "source")
       validator_id = flow.add_routine(validator, "validator")
       processor_id = flow.add_routine(processor, "processor")
       sink_id = flow.add_routine(sink, "sink")
       
       flow.connect(source_id, "output", validator_id, "input")
       flow.connect(validator_id, "output", processor_id, "input")
       flow.connect(processor_id, "output", sink_id, "input")
       
       # Set retry for validator (transient failures)
       validator.set_as_critical(max_retries=3, retry_delay=0.1)
       
       # Set continue for processor (non-critical)
       processor.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
       
       job_state = flow.execute(source_id)
       
       print(f"\nExecution status: {job_state.status}")
       print(f"Validator attempts: {validator.call_count}")

   if __name__ == "__main__":
       main()

**Expected Output**:

.. code-block:: text

   Final result: Processed: test_data
   
   Execution status: completed
   Validator attempts: 2

**Key Points**:

- Combine different strategies for different routines
- Use retry for transient failures
- Use continue for non-critical operations
- Build resilient workflows that handle errors gracefully

Common Pitfalls
---------------

**Pitfall 1: Not setting error handlers**

.. code-block:: python
   :emphasize-lines: 1

   # No error handler - uses default STOP
   flow.execute(routine_id)  # Fails immediately on any error

**Solution**: Always set appropriate error handlers for production workflows.

**Pitfall 2: Too many retries**

.. code-block:: python
   :emphasize-lines: 2

   # Too many retries can cause long delays
   ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=100)

**Solution**: Use reasonable retry counts (3-5) with appropriate delays.

**Pitfall 3: Not handling retry exhaustion**

.. code-block:: python
   :emphasize-lines: 2

   # If all retries fail, flow still fails
   # Need to handle this case

**Solution**: Use ``is_critical=True`` to control behavior when retries are exhausted.

Best Practices
--------------

1. **Set error handlers for all workflows**: Don't rely on default STOP behavior
2. **Use RETRY for transient failures**: Network, timeouts, temporary issues
3. **Use CONTINUE for non-critical operations**: Logging, optional processing
4. **Use SKIP for optional steps**: Steps that can be safely skipped
5. **Mark critical routines**: Use ``set_as_critical()`` for must-succeed operations
6. **Use reasonable retry counts**: 3-5 retries with exponential backoff
7. **Test error scenarios**: Verify error handling works as expected

Next Steps
----------

Now that you understand error handling, let's move on to :doc:`concurrent_execution`
to learn how to execute independent routines in parallel for better performance.

