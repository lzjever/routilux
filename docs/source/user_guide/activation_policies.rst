Activation Policies
=================

Activation policies control when routines execute based on slot data availability and
conditions. This is a core concept in Routilux's new architecture.

.. note:: **Separation of Concerns**

   Slots hold data, activation policies decide when to execute, and logic
   functions perform the actual processing. This separation provides flexible
   and declarative control over routine execution.

Policy Function Signature
------------------------

All activation policies have the same signature:

.. code-block:: python

   def my_policy(slots, job_state):
       """
       Args:
           slots: Dict[str, Slot] - Dictionary of slot name to Slot object
           job_state: JobState - Current job state

       Returns:
           Tuple[bool, Dict[str, list[Any]], Any]
           - should_activate: Whether routine should execute
           - data_slice: Dictionary of slot name to list of data points
           - policy_message: Optional policy metadata
       """
       # Check conditions
       should_activate = True
       data_slice = {}
       policy_message = {"reason": "custom"}

       # Extract data from slots if activating
       if should_activate:
           for slot_name, slot in slots.items():
               data_slice[slot_name] = slot.consume_all_new()

       return should_activate, data_slice, policy_message

   routine.set_activation_policy(my_policy)

Built-in Policies
-----------------

Immediate Policy
~~~~~~~~~~~~~~~

Activate immediately when any slot receives new data.

.. code-block:: python

   from routilux.activation_policies import immediate_policy

   routine.set_activation_policy(immediate_policy())

**Use Case:** Simple processing where routine should execute as soon as data arrives.

All Slots Ready Policy
~~~~~~~~~~~~~~~~~~~~~~~

Activate when all slots have at least one new data point.

.. code-block:: python

   from routilux.activation_policies import all_slots_ready_policy

   routine.set_activation_policy(all_slots_ready_policy())

**Use Case:** Routines that need data from all inputs before processing.

**Example:**

.. code-block:: python

   class Aggregator(Routine):
       def __init__(self):
           super().__init__()
           self.input1 = self.define_slot("input1")
           self.input2 = self.define_slot("input2")

           # Wait for both inputs
           routine.set_activation_policy(all_slots_ready_policy())

Batch Size Policy
~~~~~~~~~~~~~~~~

Activate when all slots have at least N unconsumed data points.

.. code-block:: python

   from routilux.activation_policies import batch_size_policy

   routine.set_activation_policy(batch_size_policy(min_batch_size=10))

**Use Case:** Batching data before processing (e.g., batch API calls, bulk inserts).

**Example:**

.. code-block:: python

   class BatchProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.define_slot("input", max_queue_length=1000)

           # Wait for batch of 10 items
           routine.set_activation_policy(batch_size_policy(min_batch_size=10))

Time Interval Policy
~~~~~~~~~~~~~~~~~~

Activate at most once every N seconds, regardless of how many events arrive.

.. code-block:: python

   from routilux.activation_policies import time_interval_policy

   # Activate at most once every 5 seconds
   routine.set_activation_policy(time_interval_policy(min_interval_seconds=5.0))

**Use Case:** Rate limiting, throttling, or preventing excessive activations.

**Example:**

.. code-block:: python

   class RateLimitedProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.define_slot("input")

           # Limit to one activation every 10 seconds
           routine.set_activation_policy(time_interval_policy(min_interval_seconds=10.0))

Custom Policy
~~~~~~~~~~~~~

Define your own activation logic.

.. code-block:: python

   from routilux.activation_policies import custom_policy

   def my_custom_policy(slots, job_state):
       # Only activate if input slot has > 5 items
       if slots.get("input"):
           should_activate = slots["input"].get_unconsumed_count() > 5
       else:
           should_activate = False

       if should_activate:
           data_slice = {}
           for slot_name, slot in slots.items():
               data_slice[slot_name] = slot.consume_all_new()
           policy_message = {"reason": "batch_ready", "threshold": 5}
       else:
           data_slice = {}
           policy_message = None

       return should_activate, data_slice, policy_message

   routine.set_activation_policy(custom_policy(my_custom_policy))

**Use Case:** Complex activation conditions not covered by built-in policies.

Common Patterns
----------------

Fan-Out (One to Many)
~~~~~~~~~~~~~~~~~~~~~

One routine's output triggers multiple routines:

.. code-block:: python

   # All use immediate_policy
   source.set_activation_policy(immediate_policy())
   consumer1.set_activation_policy(immediate_policy())
   consumer2.set_activation_policy(immediate_policy())

   # Connect source to multiple consumers
   flow.connect("source", "output", "consumer1", "input")
   flow.connect("source", "output", "consumer2", "input")

   # Result: Both consumers activate when source emits

Fan-In (Many to One)
~~~~~~~~~~~~~~~~~~~~~

Multiple routines' outputs trigger one routine:

.. code-block:: python

   # Sources use immediate_policy
   source1.set_activation_policy(immediate_policy())
   source2.set_activation_policy(immediate_policy())

   # Aggregator waits for both sources
   aggregator.set_activation_policy(all_slots_ready_policy())

   flow.connect("source1", "output", "aggregator", "input1")
   flow.connect("source2", "output", "aggregator", "input2")

   # Result: Aggregator activates only when both sources have data

Conditional Activation
~~~~~~~~~~~~~~~~~~~~~~

Activate based on custom conditions:

.. code-block:: python

   from routilux.activation_policies import custom_policy

   def conditional_policy(slots, job_state):
       # Only activate between business hours
       from datetime import datetime
       now = datetime.now()
       is_business_hours = 9 <= now.hour < 18

       if is_business_hours:
           # Check data availability
           if slots.get("input").get_unconsumed_count() > 0:
               data_slice = {"input": slots["input"].consume_all_new()}
               return True, data_slice, {"time": "business_hours"}

       return False, {}, None

   routine.set_activation_policy(custom_policy(conditional_policy))

Pitfalls and Best Practices
---------------------------

.. warning:: **Forgetting to consume data**

   Activation policies MUST consume data from slots. If you return
   ``True`` but don't consume data, the routine will activate
   repeatedly with the same data:

   .. code-block:: python

      # ❌ WRONG - Doesn't consume data
      def bad_policy(slots, job_state):
          has_data = slots["input"].get_unconsumed_count() > 0
          return has_data, {}, None  # No data slice!

      # ✅ CORRECT - Consumes data
      def good_policy(slots, job_state):
          has_data = slots["input"].get_unconsumed_count() > 0
          if has_data:
              data_slice = {"input": slots["input"].consume_all_new()}
              return True, data_slice, None
          return False, {}, None

.. warning:: **Returning inconsistent should_activate and data_slice**

   If you return ``should_activate=True``, you must also return a data_slice:

   .. code-block:: python

      # ❌ WRONG - Inconsistent
      def bad_policy(slots, job_state):
          return True, {}, None  # Activate but no data?

      # ✅ CORRECT - Consistent
      def good_policy(slots, job_state):
          if slots["input"].get_unconsumed_count() > 0:
              data_slice = {"input": slots["input"].consume_all_new()}
              return True, data_slice, None
          return False, {}, None

.. note:: **Policy Message Metadata**

   The ``policy_message`` return value is optional but useful for debugging
   and monitoring. Include relevant metadata:

   .. code-block:: python

   policy_message = {
       "reason": "batch_ready",
       "batch_size": min_batch_size,
       "threshold": threshold_value,
       "timestamp": datetime.now().isoformat()
   }

   # This message is available in job_state and monitoring

Performance Considerations
------------------------

.. note:: **Policy Execution Frequency**

   Activation policies are called frequently (every time a slot receives data).
   Keep policy logic efficient to avoid performance bottlenecks.

   **Best Practices:**
   - Avoid I/O operations in policies
   - Keep calculations simple
   - Use built-in policies when possible (optimized)
   - Cache expensive calculations in JobState if needed

.. note:: **Queue Watermark Efficiency**

   Slots automatically clear consumed data when reaching watermark (default 80%).
   This prevents unbounded queue growth. Adjust watermark based on your use case:

   - High-throughput: Lower watermark (0.6-0.7) for more frequent clearing
   - Low-latency: Higher watermark (0.8-0.9) for fewer allocations
   - Memory-constrained: Lower watermark to prevent OOM
