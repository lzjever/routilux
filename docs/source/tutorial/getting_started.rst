Getting Started with Runtime
=============================

In this first tutorial, you'll learn the basics of Routilux by creating a simple
routine, connecting it in a flow, and executing it with Runtime. By the end, you'll
understand the core concepts of routines, slots, events, flows, and Runtime.

.. note:: **New Architecture**

   This tutorial uses the new Runtime-based architecture with activation policies
   and logic functions. This is the current recommended way to use Routilux.

Learning Objectives
-------------------

By the end of this tutorial, you'll be able to:

- Create a custom routine with slots and events
- Set activation policies to control when routines execute
- Define logic functions for processing data
- Create a flow and connect routines together
- Register flows with FlowRegistry
- Execute flows with Runtime
- Wait for completion and check results

Step 1: Understanding Routines, Slots, and Events
--------------------------------------------------

Routilux is built around four core concepts:

- **Routine**: A unit of work that processes data
- **Slot**: An input mechanism that receives data (think of it as a "receiver")
- **Event**: An output mechanism that sends data (think of it as a "sender")
- **Activation Policy**: Controls when a routine executes
- **Logic Function**: Contains the actual processing logic

Let's create a simple routine that receives data through a slot and emits it
through an event:

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy

   class Greeter(Routine):
       """A simple routine that greets someone"""

       def __init__(self):
           super().__init__()
           # Define an input slot
           self.input_slot = self.add_slot("input")
           # Define an output event
           self.output_event = self.add_event("output", ["message"])

           # Define logic function
           def greet(slot_data, policy_message, job_state):
               # Extract data from slot_data
               input_list = slot_data.get("input", [])
               name = input_list[0].get("name", "World") if input_list else "World"

               # Create a greeting message
               message = f"Hello, {name}!"

               # Emit the message through the output event
               self.emit("output", message=message)

           # Set logic and activation policy
           self.set_logic(greet)
           self.set_activation_policy(immediate_policy())

**Key Points**:

- All routines inherit from ``Routine`` base class
- Slots are defined with ``add_slot()`` (no handler needed)
- Events are defined with ``add_event()`` with parameter names
- Logic functions receive ``slot_data``, ``policy_message``, and ``job_state``
- Activation policies control when the routine executes
- **Routines MUST have an activation policy set, or they will never execute**

.. warning:: **Required: Activation Policy**

   Routines without activation policies will never execute. Always set
   ``set_activation_policy()`` after defining your logic function.

Step 2: Creating Your First Flow
---------------------------------

A Flow is a container that manages multiple routines and their connections.
Let's create a flow and add our Greeter routine:

.. code-block:: python
   :linenos:

   from routilux import Flow

   # Create a flow with a unique ID
   flow = Flow(flow_id="greeting_flow")

   # Create a routine instance
   greeter = Greeter()

   # Add the routine to the flow with an ID
   greeter_id = flow.add_routine(greeter, "greeter")

   print(f"Added routine with ID: {greeter_id}")

**Expected Output**:

.. code-block:: text

   Added routine with ID: greeter

**Key Points**:

- Each flow has a unique ``flow_id`` (required parameter)
- Routines are added to flows with ``add_routine()``
- The routine ID is a string you provide (not auto-generated)
- You use the routine ID when making connections

Step 3: Registering and Executing with Runtime
----------------------------------------------

To execute a flow, we need to:
1. Register it with FlowRegistry
2. Create a Runtime
3. Execute using Runtime

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry

   # Define routine
   class Greeter(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input")
           self.output_event = self.add_event("output", ["message"])

           def greet(slot_data, policy_message, job_state):
               input_list = slot_data.get("input", [])
               name = input_list[0].get("name", "World") if input_list else "World"
               message = f"Hello, {name}!"
               self.emit("output", message=message)

           self.set_logic(greet)
           self.set_activation_policy(immediate_policy())

   # Create flow
   flow = Flow(flow_id="greeting_flow")
   greeter = Greeter()
   greeter_id = flow.add_routine(greeter, "greeter")

   # Register flow with FlowRegistry (REQUIRED!)
   registry = FlowRegistry.get_instance()
   registry.register_by_name("greeting_flow", flow)

   # Create Runtime and execute
   runtime = Runtime(thread_pool_size=5)
   job_state = runtime.exec("greeting_flow", entry_params={"name": "Routilux"})

   # Wait for completion
   runtime.wait_until_all_jobs_finished(timeout=5.0)

   # Check execution status
   print(f"Execution status: {job_state.status}")

   # Cleanup
   runtime.shutdown(wait=True)

**Expected Output**:

.. code-block:: text

   Execution status: completed

**Key Points**:

- **Flows MUST be registered** with FlowRegistry before execution
- ``runtime.exec()`` returns immediately with a ``JobState`` object
- Use ``wait_until_all_jobs_finished()`` to wait for completion
- Always call ``runtime.shutdown()`` or use context manager for cleanup

.. warning:: **Common Pitfall: Not Registering Flow**

   Forgetting to register the flow will cause a ``ValueError`` when calling
   ``runtime.exec()``. Always register flows before execution.

Step 4: Connecting Two Routines
--------------------------------

Now let's create two routines and connect them. The first routine will send data
to the second:

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry

   class DataSource(Routine):
       """A routine that generates data"""

       def __init__(self):
           super().__init__()
           self.trigger = self.add_slot("trigger")
           self.output = self.add_event("output", ["data"])

           def generate(slot_data, policy_message, job_state):
               trigger_list = slot_data.get("trigger", [])
               value = trigger_list[0].get("value", "default") if trigger_list else "default"
               self.emit("output", data=value)

           self.set_logic(generate)
           self.set_activation_policy(immediate_policy())

   class DataProcessor(Routine):
       """A routine that processes data"""

       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")
           self.output = self.add_event("output", ["result"])

           def process(slot_data, policy_message, job_state):
               input_list = slot_data.get("input", [])
               data_value = input_list[0].get("data", "no data") if input_list else "no data"
               result = f"Processed: {data_value}"
               print(f"Processor received: {data_value}, produced: {result}")
               self.emit("output", result=result)

           self.set_logic(process)
           self.set_activation_policy(immediate_policy())

   # Create flow
   flow = Flow(flow_id="data_flow")

   # Create routines
   source = DataSource()
   processor = DataProcessor()

   # Add to flow
   flow.add_routine(source, "source")
   flow.add_routine(processor, "processor")

   # Connect: source's output event -> processor's input slot
   flow.connect("source", "output", "processor", "input")

   # Register and execute
   FlowRegistry.get_instance().register_by_name("data_flow", flow)

   with Runtime(thread_pool_size=5) as runtime:
       job_state = runtime.exec("data_flow", entry_params={"value": "Hello"})
       runtime.wait_until_all_jobs_finished(timeout=5.0)

       print(f"Status: {job_state.status}")

**Expected Output**:

.. code-block:: text

   Processor received: Hello, produced: Processed: Hello
   Status: completed

**Key Points**:

- ``connect()`` links an event from one routine to a slot in another
- The connection format is: ``flow.connect("source_id", "event_name", "target_id", "slot_name")``
- Use routine IDs (strings) instead of UUID objects
- When the source emits an event, connected slots automatically receive the data
- Use context manager (``with Runtime()``) for automatic cleanup

Step 5: Complete Example - A Simple Pipeline
--------------------------------------------

Let's create a complete example with three routines connected in a pipeline:

.. code-block:: python
   :name: getting_started_complete
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry

   class DataSource(Routine):
       """Generate data"""

       def __init__(self):
           super().__init__()
           self.trigger = self.add_slot("trigger")
           self.output = self.add_event("output", ["data"])

           def generate(slot_data, policy_message, job_state):
               trigger_list = slot_data.get("trigger", [])
               text = trigger_list[0].get("text", "default") if trigger_list else "default"
               self.emit("output", data=text)

           self.set_logic(generate)
           self.set_activation_policy(immediate_policy())

   class Transformer(Routine):
       """Transform data to uppercase"""

       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")
           self.output = self.add_event("output", ["transformed"])

           def transform(slot_data, policy_message, job_state):
               input_list = slot_data.get("input", [])
               data_value = input_list[0].get("data", "") if input_list else ""
               transformed = data_value.upper()
               self.emit("output", transformed=transformed)

           self.set_logic(transform)
           self.set_activation_policy(immediate_policy())

   class Printer(Routine):
       """Print the final result"""

       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")

           def print_result(slot_data, policy_message, job_state):
               input_list = slot_data.get("input", [])
               result = input_list[0].get("transformed", "") if input_list else ""
               print(f"Final result: {result}")

           self.set_logic(print_result)
           self.set_activation_policy(immediate_policy())

   def main():
       # Create flow
       flow = Flow(flow_id="pipeline")

       # Create routines
       source = DataSource()
       transformer = Transformer()
       printer = Printer()

       # Add to flow
       flow.add_routine(source, "source")
       flow.add_routine(transformer, "transformer")
       flow.add_routine(printer, "printer")

       # Connect: source -> transformer -> printer
       flow.connect("source", "output", "transformer", "input")
       flow.connect("transformer", "output", "printer", "input")

       # Register
       FlowRegistry.get_instance().register_by_name("pipeline", flow)

       # Execute
       print("Executing pipeline...")
       with Runtime(thread_pool_size=5) as runtime:
           job_state = runtime.exec("pipeline", entry_params={"text": "hello, routilux!"})
           runtime.wait_until_all_jobs_finished(timeout=5.0)

           print(f"Pipeline status: {job_state.status}")

   if __name__ == "__main__":
       main()

**Expected Output**:

.. code-block:: text

   Executing pipeline...
   Final result: HELLO, ROUTILUX!
   Pipeline status: completed

**Key Points**:

- Routines can be connected in chains (pipelines)
- Data flows automatically from one routine to the next
- Each routine processes data and passes it along
- The flow executes all connected routines automatically
- Use context manager for automatic Runtime cleanup

Common Pitfalls
---------------

**Pitfall 1: Forgetting to call super().__init__()**

.. code-block:: python
   :emphasize-lines: 4

   class MyRoutine(Routine):
       def __init__(self):
           # Missing super().__init__()!
           self.input_slot = self.add_slot("input")
           # This will fail because _slots and _events are not initialized

**Solution**: Always call ``super().__init__()`` first in your ``__init__`` method.

**Pitfall 2: Not Setting Activation Policy**

.. code-block:: python
   :emphasize-lines: 11

   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")
           self.output = self.add_event("output", ["result"])

           def process(slot_data, policy_message, job_state):
               self.emit("output", result="done")

           self.set_logic(process)
           # Missing: self.set_activation_policy(immediate_policy())!

**Solution**: Always set an activation policy, or the routine will never execute.

**Pitfall 3: Not Registering Flow**

.. code-block:: python
   :emphasize-lines: 4

   flow = Flow(flow_id="my_flow")
   # ... add routines ...

   # Missing: FlowRegistry.get_instance().register_by_name("my_flow", flow)
   runtime = Runtime()
   job_state = runtime.exec("my_flow")  # ValueError: Flow not found!

**Solution**: Always register flows with FlowRegistry before execution.

**Pitfall 4: Not Waiting for Completion**

.. code-block:: python
   :emphasize-lines: 3

   job_state = runtime.exec("my_flow")
   print(f"Status: {job_state.status}")  # Likely "running", not "completed"!

**Solution**: Always wait for completion before checking status:

.. code-block:: python

   job_state = runtime.exec("my_flow")
   runtime.wait_until_all_jobs_finished(timeout=5.0)
   print(f"Status: {job_state.status}")  # Now "completed" or "failed"

**Pitfall 5: Not Using Context Manager**

.. code-block:: python
   :emphasize-lines: 5

   runtime = Runtime(thread_pool_size=10)
   job_state = runtime.exec("my_flow")
   # Missing: runtime.shutdown(wait=True)
   # Thread pool not cleaned up!

**Solution**: Use context manager for automatic cleanup:

.. code-block:: python

   with Runtime(thread_pool_size=10) as runtime:
       job_state = runtime.exec("my_flow")
       runtime.wait_until_all_jobs_finished(timeout=5.0)
   # Thread pool automatically cleaned up

Best Practices
--------------

1. **Use descriptive names**: Choose clear names for routines, slots, and events
2. **Define events with parameter names**: Always specify parameter names in ``add_event()``
3. **Always set activation policy**: Routines won't execute without it
4. **Always register flows**: Use FlowRegistry before execution
5. **Always wait for completion**: Use ``wait_until_all_jobs_finished()`` or ``job.wait()``
6. **Use context manager**: ``with Runtime() as runtime:`` for automatic cleanup
7. **Check job_state.status**: Verify execution completed successfully

Next Steps
----------

Now that you understand the basics, let's move on to :doc:`connecting_routines`
to learn about more complex connection patterns, multiple connections, and
understanding the event flow.
