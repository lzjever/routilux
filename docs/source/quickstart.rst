Quick Start Guide
==================

This guide will help you get started with Routilux quickly using the new
Runtime-based architecture.

Installation
------------

Install Routilux using pip:

.. code-block:: bash

   pip install routilux

For development with all dependencies:

.. code-block:: bash

   pip install routilux[dev]

Basic Concepts
--------------

Routilux is built around a few simple concepts:

* **Routine**: A unit of work that can receive input through slots and emit output through events
* **Flow**: A manager that orchestrates multiple routines and their connections
* **Runtime**: Centralized execution manager with thread pool
* **Event**: An output mechanism that can be connected to slots
* **Slot**: An input mechanism that can receive data from events
* **Connection**: A link between an event and a slot
* **Activation Policy**: Controls when a routine executes based on slot data
* **JobState**: Tracks execution state and history

Creating Your First Workflow
----------------------------

Step 1: Define Routines
~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from routilux import Routine
   from routilux.activation_policies import immediate_policy

   class DataSource(Routine):
       """Generates data for processing"""

       def __init__(self):
           super().__init__()
           self.trigger = self.define_slot("trigger")
           self.output = self.define_event("output", ["data"])

           def logic(trigger_data, policy_message, job_state):
               # Extract data
               data = trigger_data[0].get("data", "default") if trigger_data else "default"
               # Emit result
               self.emit("output", data=data)

           self.set_logic(logic)
           self.set_activation_policy(immediate_policy())

   class DataProcessor(Routine):
       """Processes incoming data"""

       def __init__(self):
           super().__init__()
           self.input = self.define_slot("input")
           self.output = self.define_event("output", ["result"])

           def logic(input_data, policy_message, job_state):
               # Extract and process
               if input_data:
                   value = input_data[0].get("data", input_data[0])
               else:
                   value = ""
               result = f"Processed: {value}"
               self.emit("output", result=result)

           self.set_logic(logic)
           self.set_activation_policy(immediate_policy())

.. note:: **Activation Policies**

   Routines must have an activation policy set. Without it, the
   routine will never execute.

Step 2: Create Flow and Connect Routines
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from routilux import Flow

   # Create flow
   flow = Flow(flow_id="quickstart_flow")

   # Create routine instances
   source = DataSource()
   processor = DataProcessor()

   # Add routines to flow
   flow.add_routine(source, "source")
   flow.add_routine(processor, "processor")

   # Connect: source's output → processor's input
   flow.connect("source", "output", "processor", "input")

Step 3: Register and Execute with Runtime
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry

   # Register flow
   registry = FlowRegistry.get_instance()
   registry.register_by_name("quickstart_flow", flow)

   # Create Runtime
   runtime = Runtime(thread_pool_size=5)

   # Execute flow
   job_state = runtime.exec("quickstart_flow", entry_params={"data": "Hello"})

   # Wait for completion
   runtime.wait_until_all_jobs_finished(timeout=5.0)

   # Check results
   print(f"Execution Status: {job_state.status}")

   # Cleanup
   runtime.shutdown(wait=True)

.. warning:: **Always Wait for Completion**

   ``runtime.exec()`` returns immediately. Always wait for completion
   using ``wait_until_all_jobs_finished()`` or ``job.wait()`` before
   assuming execution is done.

Complete Example
----------------

Here's a complete working example:

.. code-block:: python

   from routilux import Flow, Routine
   from routilux.activation_policies import immediate_policy
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry

   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger = self.define_slot("trigger")
           self.output = self.define_event("output", ["data"])

           def logic(trigger_data, policy_message, job_state):
               data = trigger_data[0].get("data", "default") if trigger_data else "default"
               self.emit("output", data=data)

           self.set_logic(logic)
           self.set_activation_policy(immediate_policy())

   class DataProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.define_slot("input")
           self.output = self.define_event("output", ["result"])

           def logic(input_data, policy_message, job_state):
               if input_data:
                   value = input_data[0].get("data", input_data[0])
               else:
                   value = ""
               processed = f"Processed: {value}"
               self.emit("output", result=processed)

           self.set_logic(logic)
           self.set_activation_policy(immediate_policy())

   # Setup
   flow = Flow(flow_id="quickstart_demo")
   source = DataSource()
   processor = DataProcessor()

   flow.add_routine(source, "source")
   flow.add_routine(processor, "processor")
   flow.connect("source", "output", "processor", "input")

   # Register
   FlowRegistry.get_instance().register_by_name("quickstart_demo", flow)

   # Execute
   with Runtime(thread_pool_size=5) as runtime:
       job_state = runtime.exec("quickstart_demo", entry_params={"data": "Hello, Routilux"})
       job = runtime.get_job(job_state.job_id)
       job.wait(timeout=10.0)

       print(f"Final Status: {job_state.status}")
       if job_state.status == "completed":
           print("Workflow completed successfully!")

Common Pitfalls
----------------

.. warning:: **Forgetting Activation Policy**

   Routines without activation policies will never execute:

   .. code-block:: python

      # ❌ WRONG
      routine.set_logic(my_logic)  # Missing activation policy!

      # ✅ CORRECT
      routine.set_activation_policy(immediate_policy())
      routine.set_logic(my_logic)

.. warning:: **Not Registering Flow**

   Flows must be registered in FlowRegistry before execution:

   .. code-block:: python

      # ❌ WRONG
      runtime = Runtime()
      job_state = runtime.exec("my_flow")  # ValueError!

      # ✅ CORRECT
      FlowRegistry.get_instance().register_by_name("my_flow", flow)
      job_state = runtime.exec("my_flow")  # Works

.. warning:: **Not Waiting for Completion**

   Execution is asynchronous. Don't assume it's complete:

   .. code-block:: python

      # ❌ WRONG
      job_state = runtime.exec("my_flow")
      print(job_state.status)  # Likely "running", not "completed"!

      # ✅ CORRECT
      job_state = runtime.exec("my_flow")
      job = runtime.get_job(job_state.job_id)
      job.wait(timeout=10.0)  # Wait for actual completion
      print(job_state.status)  # Now "completed" or "failed"

Next Steps
----------

* :doc:`user_guide/index` - Comprehensive user guide with detailed explanations
* :doc:`user_guide/routines` - Deep dive into routines and logic functions
* :doc:`user_guide/activation_policies` - Learn about activation policies
* :doc:`user_guide/runtime` - Runtime execution management
* :doc:`user_guide/flows` - Flow orchestration and connections
* :doc:`user_guide/state_management` - State management with JobState
* :doc:`user_guide/error_handling` - Error handling strategies
* :doc:`api_reference/index` - Complete API documentation
* :doc:`examples/index` - Real-world examples and use cases

Tips for Success
----------------

* **Start Simple**: Begin with basic routines and immediate_policy, then add complexity
* **Use Context Manager**: Always use ``with Runtime() as runtime:`` for automatic cleanup
* **Wait for Completion**: Always wait for jobs to finish before checking results
* **Handle Errors**: Always configure error handling for production workflows
* **Monitor State**: Use JobState to track execution history and routine states
* **Read Documentation**: Check user guide for advanced features

Happy coding with Routilux! 🚀
