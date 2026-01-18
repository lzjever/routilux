State Management
=================

In this tutorial, you'll learn how to track execution state and monitor your
workflows using Routilux's built-in state management features.

Learning Objectives
-------------------

By the end of this tutorial, you'll be able to:

- Track execution state using JobState
- Store routine-specific state in JobState
- Access execution history
- Monitor workflow performance
- Use shared data areas for execution-wide state

Step 1: Understanding JobState
-------------------------------

JobState is the central mechanism for tracking execution state. Each execution
creates a unique JobState that tracks:

- Execution status (pending, running, completed, failed, etc.)
- Execution history (all routine executions)
- Routine states (per-routine execution information)
- Shared data (execution-wide data storage)

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine

   class SimpleProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["result"])
       
       def process(self, data=None, **kwargs):
           data_value = data or kwargs.get("data", "")
           result = f"Processed: {data_value}"
           
           # Store execution state in JobState using get_execution_context()
           ctx = self.get_execution_context()
           if ctx:
               ctx.job_state.update_routine_state(
                   ctx.routine_id, {"last_processed": data_value, "processed": True}
               )
           
           self.emit("output", result=result)

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.send)
           self.output_event = self.add_event("output", ["data"])
       
       def send(self, **kwargs):
           self.emit("output", data="test")

   flow = Flow(flow_id="jobstate_flow")
   
   source = DataSource()
   processor = SimpleProcessor()
   
   source_id = flow.add_routine(source, "source")
   processor_id = flow.add_routine(processor, "processor")
   
   flow.connect(source_id, "output", processor_id, "input")
   
   job_state = flow.execute(source_id)
   
   # Access JobState information
   print(f"Status: {job_state.status}")
   print(f"Flow ID: {job_state.flow_id}")
   print(f"Created at: {job_state.created_at}")
   
   # Get execution history
   history = job_state.get_execution_history()
   print(f"Execution records: {len(history)}")
   
   # Check routine states
   processor_state = job_state.get_routine_state(processor_id)
   print(f"Processor state: {processor_state}")

**Expected Output**:

.. code-block:: text

   Status: completed
   Flow ID: jobstate_flow
   Created at: 2024-01-01 12:00:00
   Execution records: 2
   Processor state: {'last_processed': 'test', 'processed': True}

**Key Points**:

- JobState is created for each execution
- Execution state should be stored in JobState, not routine instance variables
- ``update_routine_state()`` stores routine-specific state
- ``get_routine_state()`` retrieves routine state
- Execution history records all routine executions

Step 2: Storing Routine State
-------------------------------

Routines should store execution-specific state in JobState:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine

   class StatefulProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["result"])
       
       def process(self, data=None, **kwargs):
           data_value = data or kwargs.get("data", "")
           
           # Get execution context
           ctx = self.get_execution_context()
           if not ctx:
               return
           
           # Get current state
           current_state = ctx.job_state.get_routine_state(ctx.routine_id) or {}
           processed_count = current_state.get("processed_count", 0) + 1
           
           try:
               # Process data
               result = data_value.upper()
               
               # Update state in JobState
               ctx.job_state.update_routine_state(
                   ctx.routine_id,
                   {
                       "processed_count": processed_count,
                       "last_processed": data_value,
                       "last_result": result,
                       "status": "success",
                   },
               )
               
               self.emit("output", result=result)
               
           except Exception as e:
               # Update error state in JobState
               error_count = current_state.get("error_count", 0) + 1
               ctx.job_state.update_routine_state(
                   ctx.routine_id,
                   {
                       "processed_count": processed_count,
                       "error_count": error_count,
                       "last_error": str(e),
                       "status": "error",
                   },
               )
               raise

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.send)
           self.output_event = self.add_event("output", ["data"])
       
       def send(self, **kwargs):
           for item in ["hello", "world", "routilux"]:
               self.emit("output", data=item)

   flow = Flow(flow_id="stateful_flow")
   
   source = DataSource()
   processor = StatefulProcessor()
   
   source_id = flow.add_routine(source, "source")
   processor_id = flow.add_routine(processor, "processor")
   
   flow.connect(source_id, "output", processor_id, "input")
   
   from routilux.job_state import JobState
   job_state = flow.execute(source_id)
   JobState.wait_for_completion(flow, job_state, timeout=2.0)
   
   # Check routine state
   processor_state = job_state.get_routine_state(processor_id)
   print(f"Processed: {processor_state.get('processed_count', 0)}")
   print(f"Errors: {processor_state.get('error_count', 0)}")
   print(f"Last processed: {processor_state.get('last_processed', 'none')}")

**Expected Output**:

.. code-block:: text

   Processed: 3
   Errors: 0
   Last processed: routilux

**Key Points**:

- Always get flow and job_state at the start of handler
- Use ``get_routine_state()`` to get current state
- Use ``update_routine_state()`` to update state
- State is execution-specific and isolated per execution

Step 3: Using Shared Data
--------------------------

JobState provides shared data areas for execution-wide state:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine

   class DataCollector(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.collect)
       
       def collect(self, data=None, **kwargs):
           data_value = data or kwargs.get("data", "")
           
           # Use get_execution_context() for convenient access
           ctx = self.get_execution_context()
           if ctx:
               # Append to shared log
               ctx.job_state.append_to_shared_log(
                   {"action": "collected", "data": data_value, "routine": "collector"}
               )
               
               # Update shared data
               collected_items = ctx.job_state.get_shared_data("collected_items", [])
               collected_items.append(data_value)
               ctx.job_state.update_shared_data("collected_items", collected_items)

   class DataProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["result"])
       
       def process(self, data=None, **kwargs):
           data_value = data or kwargs.get("data", "")
           
           # Use get_execution_context() for convenient access
           ctx = self.get_execution_context()
           if ctx:
               # Read shared data
               collected_items = ctx.job_state.get_shared_data("collected_items", [])
               
               # Process with context
               result = f"Processed {len(collected_items)} items, current: {data_value}"
               
               # Append to shared log
               ctx.job_state.append_to_shared_log(
                   {"action": "processed", "data": data_value, "result": result}
               )
               
               self.emit("output", result=result)

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.send)
           self.output_event = self.add_event("output", ["data"])
       
       def send(self, **kwargs):
           for item in ["a", "b", "c"]:
               self.emit("output", data=item)

   flow = Flow(flow_id="shared_data_flow")
   
   source = DataSource()
   collector = DataCollector()
   processor = DataProcessor()
   
   source_id = flow.add_routine(source, "source")
   collector_id = flow.add_routine(collector, "collector")
   processor_id = flow.add_routine(processor, "processor")
   
   flow.connect(source_id, "output", collector_id, "input")
   flow.connect(source_id, "output", processor_id, "input")
   
   from routilux.job_state import JobState
   job_state = flow.execute(source_id)
   JobState.wait_for_completion(flow, job_state, timeout=2.0)
   
   # Check shared data
   collected_items = job_state.get_shared_data("collected_items", [])
   print(f"Collected items: {collected_items}")
   
   # Check shared log
   log = job_state.get_shared_log()
   print(f"Log entries: {len(log)}")
   for entry in log:
       print(f"  {entry}")

**Expected Output**:

.. code-block:: text

   Collected items: ['a', 'b', 'c']
   Log entries: 6
     {'action': 'collected', 'data': 'a', 'routine': 'collector', 'timestamp': '...'}
     {'action': 'collected', 'data': 'b', 'routine': 'collector', 'timestamp': '...'}
     {'action': 'collected', 'data': 'c', 'routine': 'collector', 'timestamp': '...'}
     {'action': 'processed', 'data': 'a', 'result': '...', 'timestamp': '...'}
     {'action': 'processed', 'data': 'b', 'result': '...', 'timestamp': '...'}
     {'action': 'processed', 'data': 'c', 'result': '...', 'timestamp': '...'}

**Key Points**:

- ``update_shared_data()`` stores execution-wide data
- ``get_shared_data()`` retrieves shared data
- ``append_to_shared_log()`` appends to execution log
- ``get_shared_log()`` retrieves log entries
- Shared data is execution-specific and isolated

Step 4: Accessing Execution History
------------------------------------

Execution history records all routine executions:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine

   class SimpleProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["result"])
       
       def process(self, data=None, **kwargs):
           data_value = data or kwargs.get("data", "")
           result = f"Processed: {data_value}"
           self.emit("output", result=result)

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.send)
           self.output_event = self.add_event("output", ["data"])
       
       def send(self, **kwargs):
           for item in ["a", "b", "c"]:
               self.emit("output", data=item)

   flow = Flow(flow_id="history_flow")
   
   source = DataSource()
   processor = SimpleProcessor()
   
   source_id = flow.add_routine(source, "source")
   processor_id = flow.add_routine(processor, "processor")
   
   flow.connect(source_id, "output", processor_id, "input")
   
   from routilux.job_state import JobState
   job_state = flow.execute(source_id)
   JobState.wait_for_completion(flow, job_state, timeout=2.0)
   
   # Get all execution history
   history = job_state.get_execution_history()
   print(f"Total records: {len(history)}")
   
   # Get history for specific routine
   processor_history = job_state.get_execution_history(processor_id)
   print(f"Processor executions: {len(processor_history)}")
   
   # Print history
   for record in history:
       print(f"  {record.routine_id}: {record.event_name} at {record.timestamp}")

**Expected Output**:

.. code-block:: text

   Total records: 4
   Processor executions: 3
     source: output at 2024-01-01 12:00:00
     processor: output at 2024-01-01 12:00:00.001
     source: output at 2024-01-01 12:00:00.002
     processor: output at 2024-01-01 12:00:00.003

**Key Points**:

- ``get_execution_history()`` returns all execution records
- ``get_execution_history(routine_id)`` filters by routine
- Each record contains routine_id, event_name, data, and timestamp
- History is automatically recorded for all event emissions

Step 5: Complete Example - Stateful Workflow
---------------------------------------------

Here's a complete example combining state management features:

.. code-block:: python
   :name: state_management_complete
   :linenos:

   from routilux import Flow, Routine

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.generate)
           self.output_event = self.add_event("output", ["data"])
       
       def generate(self, count=3, **kwargs):
           count = count or kwargs.get("count", 3)
           
           # Use get_execution_context() for convenient access
           ctx = self.get_execution_context()
           if ctx:
               ctx.job_state.update_routine_state(ctx.routine_id, {"generated_count": count})
           
           for i in range(count):
               self.emit("output", data=f"item_{i}")

   class Validator(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.validate)
           self.output_event = self.add_event("output", ["data", "valid"])
       
       def validate(self, data=None, **kwargs):
           data_value = data or kwargs.get("data", "")
           
           # Use get_execution_context() for convenient access
           ctx = self.get_execution_context()
           if not ctx:
               return
           
           current_state = ctx.job_state.get_routine_state(ctx.routine_id) or {}
           
           # Simple validation: must contain "item"
           is_valid = "item" in str(data_value)
           
           if is_valid:
               valid_count = current_state.get("valid_count", 0) + 1
               ctx.job_state.update_routine_state(
                   ctx.routine_id, {"valid_count": valid_count, "last_valid": data_value}
               )
           else:
               invalid_count = current_state.get("invalid_count", 0) + 1
               ctx.job_state.update_routine_state(
                   ctx.routine_id, {"invalid_count": invalid_count, "last_invalid": data_value}
               )
           
           self.emit("output", data=data_value, valid=is_valid)

   class Aggregator(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.aggregate)
       
       def aggregate(self, data=None, valid=None, **kwargs):
           data_value = data or kwargs.get("data", "")
           is_valid = valid if valid is not None else kwargs.get("valid", False)
           
           # Use get_execution_context() for convenient access
           ctx = self.get_execution_context()
           if ctx:
               current_state = ctx.job_state.get_routine_state(ctx.routine_id) or {}
               
               total_received = current_state.get("total_received", 0) + 1
               total_valid = current_state.get("total_valid", 0)
               if is_valid:
                   total_valid += 1
               
               ctx.job_state.update_routine_state(
                   ctx.routine_id, {"total_received": total_received, "total_valid": total_valid}
               )
           
           print(f"Aggregated: {data_value} (valid={is_valid})")

   def main():
       flow = Flow(flow_id="stateful_workflow")
       
       source = DataSource()
       validator = Validator()
       aggregator = Aggregator()
       
       source_id = flow.add_routine(source, "source")
       validator_id = flow.add_routine(validator, "validator")
       agg_id = flow.add_routine(aggregator, "aggregator")
       
       flow.connect(source_id, "output", validator_id, "input")
       flow.connect(validator_id, "output", agg_id, "input")
       
       from routilux.job_state import JobState
       job_state = flow.execute(source_id, entry_params={"count": 5})
       JobState.wait_for_completion(flow, job_state, timeout=2.0)
       
       print("\n=== Execution State ===")
       source_state = job_state.get_routine_state(source_id)
       validator_state = job_state.get_routine_state(validator_id)
       aggregator_state = job_state.get_routine_state(agg_id)
       
       print(f"Source generated: {source_state.get('generated_count', 0)}")
       print(
           f"Validator - Valid: {validator_state.get('valid_count', 0)}, "
           f"Invalid: {validator_state.get('invalid_count', 0)}"
       )
       print(
           f"Aggregator - Total: {aggregator_state.get('total_received', 0)}, "
           f"Valid: {aggregator_state.get('total_valid', 0)}"
       )
       print(f"\nExecution status: {job_state.status}")

   if __name__ == "__main__":
       main()

**Expected Output**:

.. code-block:: text

   Aggregated: item_0 (valid=True)
   Aggregated: item_1 (valid=True)
   Aggregated: item_2 (valid=True)
   Aggregated: item_3 (valid=True)
   Aggregated: item_4 (valid=True)

   === Execution State ===
   Source generated: 5
   Validator - Valid: 5, Invalid: 0
   Aggregator - Total: 5, Valid: 5

   Execution status: completed

**Key Points**:

- Store all execution state in JobState
- Use ``update_routine_state()`` to update state
- Use ``get_routine_state()`` to retrieve state
- State is execution-specific and isolated per execution

Common Pitfalls
---------------

**Pitfall 1: Modifying routine instance variables during execution**

.. code-block:: python
   :emphasize-lines: 3

   def process(self, **kwargs):
       # ❌ Don't do this - breaks execution isolation
       self.counter += 1
       self.data.append(kwargs)

**Solution**: Store execution state in JobState:

.. code-block:: python

   def process(self, **kwargs):
       # Use get_execution_context() for convenient access
       ctx = self.get_execution_context()
       if ctx:
           current_state = ctx.job_state.get_routine_state(ctx.routine_id) or {}
           counter = current_state.get("counter", 0) + 1
           ctx.job_state.update_routine_state(ctx.routine_id, {"counter": counter})

**Pitfall 2: Not checking for flow and job_state**

.. code-block:: python
   :emphasize-lines: 2

   def process(self, **kwargs):
       job_state = getattr(self, "_current_job_state", None)  # Set by slot.receive()

**Solution**: Use ``get_execution_context()`` which handles all checks:

.. code-block:: python

   def process(self, **kwargs):
       ctx = self.get_execution_context()
       if ctx:
           # Safe to use ctx.job_state here
           ctx.job_state.update_routine_state(ctx.routine_id, {"processed": True})

**Pitfall 3: Using wrong routine_id**

.. code-block:: python
   :emphasize-lines: 3

   def process(self, **kwargs):
       # ❌ Wrong - self._id is memory address, not routine_id in flow
       job_state.update_routine_state(self._id, {"processed": True})

**Solution**: Use ``get_execution_context()`` which provides the correct routine_id:

.. code-block:: python

   def process(self, **kwargs):
       ctx = self.get_execution_context()
       if ctx:
           # ctx.routine_id is the correct routine_id from flow
           ctx.job_state.update_routine_state(ctx.routine_id, {"processed": True})

Best Practices
--------------

1. **Always store execution state in JobState**: Never modify routine instance variables during execution
2. **Use get_execution_context()**: Use ``get_execution_context()`` for convenient access to flow, job_state, and routine_id
3. **Use send_output() for output**: Use ``send_output()`` to send execution-specific output (not events)
4. **Use emit_deferred_event() for pause/resume**: Use ``emit_deferred_event()`` to emit events that will be processed on resume
5. **Use get_routine_state() first**: Get current state before updating to avoid overwriting
6. **Use shared data for execution-wide state**: Use ``update_shared_data()`` and ``append_to_shared_log()``
7. **Access execution history**: Use ``get_execution_history()`` to track all executions

Next Steps
----------

Now that you understand state management, let's move on to :doc:`error_handling`
to learn how to build resilient workflows that handle errors gracefully.
