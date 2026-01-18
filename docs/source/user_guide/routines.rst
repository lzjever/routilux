Working with Routines
====================

Routines are the core building blocks of Routilux. This guide explains how to create
and use routines with the new activation policy system.

.. warning:: **Architecture Change**

   Routines no longer use slot handlers. Instead, they use activation
   policies and separate logic functions. See :doc:`activation_policies` for details.

Creating a Routine
-------------------

To create a routine, inherit from ``Routine``:

.. code-block:: python

   from routilux import Routine

   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           # Define slots, events, policy, and logic here

Defining Slots
---------------

Slots are input mechanisms for routines. Define slots to receive data from events:

.. code-block:: python

   # Basic slot
   self.input_slot = self.add_slot("input")

   # Custom queue size
   self.input_slot = self.add_slot("input", max_queue_length=100, watermark=0.8)

.. note:: **No Handlers in Slots**

   Slots do NOT have handlers anymore. Data processing is handled
   by the routine's logic function instead.

Defining Events
---------------

Events are output mechanisms for routines. Define an event with output parameters:

.. code-block:: python

   # Basic event
   self.output_event = self.add_event("output", ["result", "status"])

Setting Activation Policy
------------------------

Activation policies control when a routine executes. Set a policy:

.. code-block:: python

   from routilux.activation_policies import immediate_policy

   routine.set_activation_policy(immediate_policy())

See :doc:`activation_policies` for all available policies.

Setting Logic Function
-----------------------

Logic functions contain the actual processing logic:

.. code-block:: python

   def my_logic(slot_data, policy_message, job_state):
       """
       Args:
           slot_data: Dict[str, list] - Slot name to list of data points
           policy_message: Policy-specific metadata
           job_state: Current JobState for this execution
       """
       # Process data from slot_data
       # Emit events using self.emit()
       pass

   routine.set_logic(my_logic)

Complete Example
----------------

.. code-block:: python

   from routilux import Routine
   from routilux.activation_policies import immediate_policy

   class DataProcessor(Routine):
       def __init__(self):
           super().__init__()
           # Define input slot
           self.input = self.add_slot("input")
           # Define output event
           self.output = self.add_event("output", ["result"])

           # Define logic function
           def process(input_data, policy_message, job_state):
               # Extract data
               if input_data:
                   value = input_data[0].get("data", input_data[0])
               else:
                   value = ""

               # Process
               result = f"Processed: {value}"

               # Store state in JobState
               job_state.update_routine_state(
                   job_state.current_routine_id,
                   {"processed": True}
               )

               # Emit result
               self.emit("output", result=result)

           # Set logic and policy
           self.set_logic(process)
           self.set_activation_policy(immediate_policy())

Critical Constraints
-------------------

.. warning:: **DO NOT Accept Constructor Parameters**

   Routines MUST have a parameterless constructor:

   .. code-block:: python

      # ❌ WRONG - Will break serialization
      class BadRoutine(Routine):
          def __init__(self, name: str):  # Don't do this!
              super().__init__()
              self.name = name

      # ✅ CORRECT - Use _config dictionary
      class GoodRoutine(Routine):
          def __init__(self):
              super().__init__()
              self.set_config(name="my_routine")

.. warning:: **DO NOT Modify Instance Variables During Execution**

   All execution state MUST be stored in JobState:

   .. code-block:: python

      # ❌ WRONG - Breaks execution isolation
      class BadRoutine(Routine):
          def __init__(self):
              super().__init__()
              self.counter = 0  # Instance variable

          def process(self, slot_data, policy_message, job_state):
              self.counter += 1  # Don't modify during execution!

      # ✅ CORRECT - Use JobState
      class GoodRoutine(Routine):
          def __init__(self):
              super().__init__()

          def process(self, slot_data, policy_message, job_state):
              # Get state from JobState
              state = job_state.get_routine_state(
                  job_state.current_routine_id, {}
              )
              counter = state.get("counter", 0)

              # Update state in JobState
              job_state.update_routine_state(
                  job_state.current_routine_id,
                  {"counter": counter + 1}
              )

   **Why?** The same routine object can execute concurrently in multiple threads.
   Modifying instance variables causes data races and state corruption.

   **Solution:** Always store execution state in JobState, which is unique per
   execution and thread-safe.

Configuration Management
-----------------------

Use ``_config`` dictionary for storing routine-specific configuration:

.. code-block:: python

   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           # Set configuration
           self.set_config(name="my_routine", timeout=30)

       def process(self, slot_data, policy_message, job_state):
           # Read configuration (read-only during execution)
           timeout = self.get_config("timeout", 10)
           pass

   # Get all configuration
   config = routine.config()  # Returns copy of _config

   # Get specific value
   value = routine.get_config("key", default=None)

   # Set configuration
   routine.set_config(key1="value1", key2="value2")

.. note:: **Thread-Safe Configuration**

   The ``_config`` dictionary is protected by a lock, making it safe to
   access from multiple threads.

Slot Queue Management
---------------------

Slots have queue-based data storage:

.. code-block:: python

   # Default: max_queue_length=1000, watermark=0.8
   slot = self.add_slot("input")

   # Custom queue size
   slot = self.add_slot(
       "input",
       max_queue_length=100,
       watermark=0.7
   )

.. note:: **Queue Behavior**

   - Data is enqueued when events are emitted
   - Activation policies consume data from slots
   - When queue reaches watermark (default 80%), consumed data is cleared
   - If queue is full and can't clear, raises ``SlotQueueFullError``

Emitting Events
---------------

Emit events to trigger connected routines:

.. code-block:: python

   # Emit basic data
   self.emit("output", result="success", status=200)

   # Emit with JobState context
   self.emit(
       "output",
       job_state=job_state,
       result=processed_data
   )

.. note:: **Non-Blocking Emit**

   ``emit()`` returns immediately after enqueuing tasks. Downstream
   execution happens asynchronously. Do not assume handlers complete before
   ``emit()`` returns.

   **Flow Detection:** The flow is automatically detected from the current
   execution context. No need to pass flow parameter.

Common Pitfalls
----------------

.. warning:: **Forgetting to set activation policy**

   Without an activation policy, the routine will never execute:

   .. code-block:: python

      # ❌ WRONG
      routine.set_logic(my_logic)  # No activation policy!

      # ✅ CORRECT
      routine.set_activation_policy(immediate_policy())
      routine.set_logic(my_logic)

.. warning:: **Accessing slot data directly**

   Activation policies consume data from slots. Do not access slot data
   directly in logic function - use the ``slot_data`` parameter instead:

   .. code-block:: python

      # ❌ WRONG - Policy may have already consumed data
      def process(self, slot_data, policy_message, job_state):
          data = self.input_slot.consume_all_new()  # Don't do this!

      # ✅ CORRECT - Use slot_data from policy
      def process(self, slot_data, policy_message, job_state):
          data = slot_data.get("input", [])  # Use this

.. warning:: **Modifying slot_data parameter**

   The ``slot_data`` parameter is a dictionary of lists. Do not
   modify it directly:

   .. code-block:: python

      # ❌ WRONG
      def process(self, slot_data, policy_message, job_state):
          slot_data["input"].append(new_data)  # Don't modify!

      # ✅ CORRECT
      def process(self, slot_data, policy_message, job_state):
          data_list = list(slot_data.get("input", []))
          data_list.append(new_data)
