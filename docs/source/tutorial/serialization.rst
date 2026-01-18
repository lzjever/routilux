Serialization and Persistence with Runtime
======================================

In this tutorial, you'll learn how to serialize and deserialize flows for
persistence, recovery, and distributed execution.

.. note:: **New Architecture**

   This tutorial uses the Runtime-based architecture. All execution goes through
   Runtime, not direct Flow.execute() calls. Flow structure and JobState are
   serialized separately.

Learning Objectives
-------------------

By the end of this tutorial, you'll be able to:

- Serialize flows to JSON
- Deserialize flows from JSON
- Save and load JobState for recovery
- Understand serialization requirements
- Build persistent workflows
- Resume executions from saved state

Step 1: Basic Flow Serialization
---------------------------------

You can serialize a flow to JSON for persistence:

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry
   import json

   class SimpleProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")
           self.output = self.add_event("output", ["result"])

           def process(slot_data, policy_message, job_state):
               input_list = slot_data.get("input", [])
               data_value = input_list[0].get("data", "") if input_list else ""
               result = f"Processed: {data_value}"
               self.emit("output", result=result)

           self.set_logic(process)
           self.set_activation_policy(immediate_policy())

   # Create flow
   flow = Flow(flow_id="serializable_flow")
   processor = SimpleProcessor()
   flow.add_routine(processor, "processor")

   # Serialize flow structure (no execution state)
   flow_data = flow.serialize()

   # Save to file
   with open("flow.json", "w") as f:
       json.dump(flow_data, f, indent=2)

   print("Flow serialized to flow.json")
   print(f"Flow ID: {flow_data['flow_id']}")
   print(f"Routines: {list(flow_data['routines'].keys())}")

**Expected Output**:

.. code-block:: text

   Flow serialized to flow.json
   Flow ID: serializable_flow
   Routines: ['processor']

**Key Points**:

- ``flow.serialize()`` serializes flow structure only (no execution state)
- Only serializes routines, connections, and configuration
- Can be restored and executed on any host
- Use ``flow_id`` to identify workflows

Step 2: Deserializing Flows
----------------------------

Deserialize a flow from JSON:

.. code-block:: python
   :linenos:

   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry
   import json

   # Load from file
   with open("flow.json", "r") as f:
       flow_data = json.load(f)

   # Deserialize flow (create new instance and deserialize)
   restored_flow = Flow.deserialize(flow_data)

   print(f"Restored flow ID: {restored_flow.flow_id}")
   print(f"Routines: {list(restored_flow.routines.keys())}")

   # Register with FlowRegistry
   FlowRegistry.get_instance().register_by_name("restored_flow", restored_flow)

   # Execute restored flow
   with Runtime(thread_pool_size=5) as runtime:
       job_state = runtime.exec("restored_flow", entry_params={"data": "test"})
       runtime.wait_until_all_jobs_finished(timeout=5.0)

       print(f"Execution status: {job_state.status}")

**Expected Output**:

.. code-block:: text

   Restored flow ID: serializable_flow
   Routines: ['processor']
   Execution status: completed

**Key Points**:

- ``Flow.deserialize()`` recreates flow from serialized data
- All routines and connections are restored
- Flow must be registered with FlowRegistry before execution
- Routine instances are recreated (must have no-argument constructors)
- Creates a NEW execution, not a continuation of a previous one

Step 3: Serialization Requirements
-----------------------------------

For serialization to work, routines must meet certain requirements:

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy

   class ConfigurableProcessor(Routine):
       """Correct: Uses _config for configuration"""

       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")
           self.output = self.add_event("output", ["result"])
           # Configuration stored in _config (serializable)
           self.set_config(threshold=10, enabled=True)

           def process(slot_data, policy_message, job_state):
               threshold = self.get_config("threshold", default=5)
               enabled = self.get_config("enabled", default=False)

               if enabled:
                   input_list = slot_data.get("input", [])
                   data_value = input_list[0].get("data", 0) if input_list else 0
                   result = data_value * threshold
                   self.emit("output", result=result)

           self.set_logic(process)
           self.set_activation_policy(immediate_policy())

   # Create flow
   flow = Flow(flow_id="config_flow")
   processor = ConfigurableProcessor()
   flow.add_routine(processor, "processor")

   # Serialize (configuration is preserved)
   flow_data = flow.serialize()

   # Deserialize
   restored_flow = Flow.deserialize(flow_data)

   # Verify configuration preserved
   restored_processor = restored_flow.routines["processor"]
   threshold = restored_processor.get_config("threshold")
   enabled = restored_processor.get_config("enabled", False)

   print(f"Restored threshold: {threshold}")
   print(f"Restored enabled: {enabled}")

**Expected Output**:

.. code-block:: text

   Restored threshold: 10
   Restored enabled: True

**Key Requirements**:

- Routines must have no-argument constructors (except ``self``)
- Configuration must be stored in ``_config`` dictionary
- Use ``set_config()`` and ``get_config()`` for configuration
- All configuration is automatically serialized
- Custom routine classes must be registered with ``@register_serializable`` decorator
- Routilux's built-in routines are already registered

.. warning:: **Critical: No Constructor Parameters**

   Routines with constructor parameters cannot be serialized:

   .. code-block:: python

      # ❌ WRONG - Will break serialization
      class BadProcessor(Routine):
          def __init__(self, threshold=10):  # Don't do this!
              super().__init__()
              self.threshold = threshold  # Not serializable!

      # ✅ CORRECT - Use _config dictionary
      class GoodProcessor(Routine):
          def __init__(self):
              super().__init__()
              self.set_config(threshold=10)  # Serializable!

Step 4: Saving and Loading JobState
---------------------------------

You can save JobState for workflow recovery:

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger = self.add_slot("trigger")
           self.output = self.add_event("output", ["data"])

           def generate(slot_data, policy_message, job_state):
               trigger_list = slot_data.get("trigger", [])
               data = trigger_list[0].get("data", "test_data") if trigger_list else "test_data"
               self.emit("output", data=data)

           self.set_logic(generate)
           self.set_activation_policy(immediate_policy())

   class Processor(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")
           self.output = self.add_event("output", ["result"])

           def process(slot_data, policy_message, job_state):
               input_list = slot_data.get("input", [])
               data_value = input_list[0].get("data", "") if input_list else ""
               result = f"Processed: {data_value}"
               self.emit("output", result=result)

           self.set_logic(process)
           self.set_activation_policy(immediate_policy())

   # Create flow
   flow = Flow(flow_id="recovery_flow")

   source = DataSource()
   processor = Processor()

   flow.add_routine(source, "source")
   flow.add_routine(processor, "processor")
   flow.connect("source", "output", "processor", "input")

   # Register and execute
   FlowRegistry.get_instance().register_by_name("recovery_flow", flow)

   with Runtime(thread_pool_size=5) as runtime:
       job_state = runtime.exec("recovery_flow", entry_params={"data": "important_data"})

       # Save JobState to file
       job_state.save("workflow_state.json")
       print(f"JobState saved. Status: {job_state.status}")
       print(f"Job ID: {job_state.job_id}")

**Expected Output**:

.. code-block:: text

   JobState saved. Status: completed
   Job ID: <unique-job-id>

**Key Points**:

- ``job_state.save()`` saves JobState to a JSON file
- Includes execution status, routine states, execution history
- Can be loaded and resumed with ``runtime.exec(flow_id, job_state=loaded_state)``

Step 5: Resuming from Saved State
-------------------------------

Resume execution from a saved JobState:

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry
   import json

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger = self.add_slot("trigger")
           self.output = self.add_event("output", ["data"])

           def generate(slot_data, policy_message, job_state):
               trigger_list = slot_data.get("trigger", [])
               data = trigger_list[0].get("data", "default") if trigger_list else "default"
               self.emit("output", data=data)

           self.set_logic(generate)
           self.set_activation_policy(immediate_policy())

   class Processor(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")
           self.output = self.add_event("output", ["result"])

           def process(slot_data, policy_message, job_state):
               # Check if resuming from previous execution
               state = job_state.get_routine_state("processor", {})
               processed_count = state.get("count", 0)

               input_list = slot_data.get("input", [])
               data_value = input_list[0].get("data", "") if input_list else ""

               # Store new count
               job_state.update_routine_state("processor", {"count": processed_count + 1})

               result = f"Processed: {data_value} (attempt #{processed_count + 1})"
               print(result)

           self.set_logic(process)
           self.set_activation_policy(immediate_policy())

   # Create flow
   flow = Flow(flow_id="resume_flow")

   source = DataSource()
   processor = Processor()

   flow.add_routine(source, "source")
   flow.add_routine(processor, "processor")
   flow.connect("source", "output", "processor", "input")

   # Register
   FlowRegistry.get_instance().register_by_name("resume_flow", flow)

   # First execution
   with Runtime(thread_pool_size=5) as runtime:
       job_state1 = runtime.exec("resume_flow", entry_params={"data": "first_input"})

       # Save state
       job_state1.save("state1.json")
       print(f"First execution. Job ID: {job_state1.job_id}")

   # Later, load and resume
   with open("state1.json", "r") as f:
       state_data = json.load(f)

   # Restore JobState
   from routilux import JobState
   saved_state = JobState.deserialize(state_data)

   print(f"Loaded JobState. Status: {saved_state.status}")
   print(f"Original Job ID: {saved_state.job_id}")

   # Resume execution
   with Runtime(thread_pool_size=5) as runtime:
       # Resume with saved state
       job_state2 = runtime.exec("resume_flow", job_state=saved_state)

       runtime.wait_until_all_jobs_finished(timeout=5.0)

       print(f"Resumed execution. Status: {job_state2.status}")

**Expected Output**:

.. code-block:: text

   Processed: first_input (attempt #1)
   First execution. Job ID: <job-id-1>
   Loaded JobState. Status: completed
   Original Job ID: <job-id-1>
   Processed: first_input (attempt #2)
   Resumed execution. Status: completed

**Key Points**:

- Use ``JobState.deserialize()`` to restore from saved state
- Pass saved JobState to ``runtime.exec()`` to resume
   - Execution state is preserved, allowing workflows to resume
   - Each execution has a unique job_id

Step 6: Complete Example - Cross-Host Recovery
-----------------------------------------

Here's a complete example showing proper serialization for cross-host recovery:

.. code-block:: python
   :name: serialization_complete
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry
   import json

   class DataProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")
           self.output = self.add_event("output", ["result"])

           def process(slot_data, policy_message, job_state):
               input_list = slot_data.get("input", [])
               data_value = input_list[0].get("data", 0) if input_list else 0
               result = data_value * 2
               self.emit("output", result=result)

           # Store execution count
           state = job_state.get_routine_state("processor", {})
           count = state.get("count", 0)
           job_state.update_routine_state("processor", {"count": count + 1})

           self.set_logic(process)
           self.set_activation_policy(immediate_policy())

   def save_workflow_structure():
       """Save workflow structure for distribution"""
       flow = Flow(flow_id="distributed_workflow")

       processor = DataProcessor()
       flow.add_routine(processor, "processor")

       # Serialize flow structure only (no execution state)
       flow_data = flow.serialize()

       with open("workflow_structure.json", "w") as f:
           json.dump(flow_data, f, indent=2)

       print("Workflow structure saved to workflow_structure.json")
       return flow

   def execute_and_save_state():
       """Execute workflow and save execution state"""
       # Load workflow structure
       with open("workflow_structure.json", "r") as f:
           flow_data = json.load(f)

       flow = Flow.deserialize(flow_data)

       # Register
       FlowRegistry.get_instance().register_by_name("distributed_workflow", flow)

       # Execute
       with Runtime(thread_pool_size=5) as runtime:
           job_state = runtime.exec("distributed_workflow", entry_params={"data": 10})

           # Save execution state
           job_state_data = job_state.serialize()

           with open("execution_state.json", "w") as f:
               json.dump(job_state_data, f, indent=2)

           print(f"Execution state saved. Job ID: {job_state.job_id}")
           return job_state

   def restore_on_remote_host():
       """Simulate restoring on a remote host"""
       # Load workflow structure
       with open("workflow_structure.json", "r") as f:
           flow_data = json.load(f)

       # Load execution state
       with open("execution_state.json", "r") as f:
           job_state_data = json.load(f)

       # Restore both
       flow = Flow.deserialize(flow_data)
       saved_state = saved_state = job_state_data

       print(f"Restored flow: {flow.flow_id}")
       print(f"Restored Job ID: {saved_state.job_id}, Status: {saved_state.status}")

       # Verify state is preserved
       processor = flow.routines["processor"]
       state = saved_state.get_routine_state("processor", {})
       count = state.get("count", 0)

       print(f"Execution count: {count}")

       return flow, saved_state

   def main():
       # Step 1: Save workflow structure
       save_workflow_structure()

       # Step 2: Execute and save state
       job_state = execute_and_save_state()

       # Step 3: Simulate restoring on remote host
       restored_flow, restored_job_state = restore_on_remote_host()

   if __name__ == "__main__":
       main()

**Expected Output**:

.. code-block:: text

   Workflow structure saved to workflow_structure.json
   Execution state saved. Job ID: <job-id>
   Restored flow: distributed_workflow
   Restored Job ID: <job-id>, Status: completed
   Execution count: 1

**Key Points**:

- **Separate serialization**: Flow structure (flow.serialize()) and execution state (job_state.serialize()) are separate
- **Distribution**: Send both files to remote host
- **Recovery**: Restore both on remote host to resume execution
- **State Preservation**: JobState tracks execution count and other state

Common Pitfalls
---------------

**Pitfall 1: Using constructor parameters**

.. code-block:: python
   :emphasize-lines: 2

   # ❌ WRONG - Breaks serialization
   class BadRoutine(Routine):
       def __init__(self, threshold=10):
           super().__init__()
           self.threshold = threshold  # Not serializable!

**Solution**: Use ``_config`` dictionary: ``self.set_config(threshold=10)``

**Pitfall 2: Expecting single JobState across executions**

.. code-block:: python
   :emphasize-lines: 4

   job_state1 = runtime.exec("my_flow")
   job_state2 = runtime.exec("my_flow")  # Overwrites job_state1!

**Solution**: Each ``runtime.exec()`` creates a new JobState with unique job_id.

**Pitfall 3: Not saving JobState before serialization**

.. code-block:: python
   :emphasize-lines: 2

   # Don't do this
   flow_data = flow.serialize()  # Doesn't include job_state by default
   # If job_state is lost, can't resume execution!

**Solution**: Save JobState separately using ``job_state.serialize()``.

**Pitfall 4: Restoring wrong JobState for flow**

.. code-block:: python
   :emphasize-lines: 3-4

   # Don't do this - will fail if job_id doesn't match flow structure
   wrong_job_state = JobState()  # Empty state with wrong job_id
   runtime.exec("my_flow", job_state=wrong_job_state)

**Solution**: Only restore JobState that matches the flow structure.

Best Practices
--------------

1. **Separate Flow and JobState serialization**:
   - Serialize Flow with ``flow.serialize()`` (no execution state)
   - Serialize JobState with ``job_state.serialize()` for recovery
   - Send both files for cross-host recovery

2. **Use _config for configuration**: All configuration should be in ``_config``

3. **No constructor parameters**: Routines must have no-argument constructors

4. **Test serialization**: Always test that flows can be serialized/deserialized correctly

5. **Include version info**: Add version info in ``flow_id`` or ``_config``

6. **Track job_ids**: Save job_id along with JobState for proper recovery

7. **Clean up old JobState files**: Remove outdated saved state files

8. **Version your workflows**: Include version in ``flow_id`` to manage compatibility

Understanding Flow vs JobState
------------------------------

**Design Principle**: Flow = Workflow Definition, JobState = Execution State

- **Flow**: Contains routines, connections, configuration (static structure)
- **JobState**: Contains execution state, history, pending tasks (dynamic state)
- **Multiple Executions**: Each ``runtime.exec()`` creates a new JobState with unique job_id
- **Complete Decoupling**: Flow does NOT manage JobState - they are completely separate

**Best Practice for Cross-Host Execution**:

1. **Serialize Flow structure** (no execution state):
   .. code-block:: python

      flow_data = flow.serialize()  # Does NOT include job_state

2. **Serialize JobState separately**:
   .. code-block:: python

      job_state_data = job_state.serialize()

3. **Send both to target host**:
   - Send workflow_structure.json
   - Send execution_state.json

4. **Restore both on target host**:

   .. code-block:: python

      new_flow = Flow.deserialize(flow_data)
      new_job_state = JobState.deserialize(job_state_data)

5. **Resume if needed**:
   .. code-block:: python

      if new_job_state.status == "paused":
          # Resume from paused state
          pass  # Resume logic here

Next Steps
----------

Congratulations! You've completed the Routilux tutorial. You now understand:

- Creating routines and flows
- Connecting routines in various patterns
- Managing state and statistics
- Handling errors gracefully
- Executing workflows concurrently
- Serializing and persisting workflows

For more information, check out:

- :doc:`../user_guide/index` - Comprehensive user guide
- :doc:`../api_reference/index` - Complete API documentation
- :doc:`../user_guide/serialization` - Detailed serialization guide

Happy coding with Routilux! 🚀
