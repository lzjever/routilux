Working with Connections
========================

Connections link events to slots, enabling data flow between routines.

Multiple Slots and Multiple Connections
----------------------------------------

A routine can have multiple slots, and each slot can be connected to different
upstream routines. When an upstream routine emits data, it triggers the handler
of the connected slot.

**Key Behavior**:
* Each slot has its own handler function
* Each slot maintains its own data state (``_data``)
* Each slot's merge_strategy applies independently
* When an event emits, it triggers **all** connected slots
* Each slot's handler is called **immediately** when data is received

**Example Scenario**:

If a routine has 3 slots connected to 3 different upstream routines:

.. code-block:: python

   # Target routine with 3 slots
   target = TargetRoutine()
   target.slot1 = target.add_slot("input1", handler=handle1)
   target.slot2 = target.add_slot("input2", handler=handle2)
   target.slot3 = target.add_slot("input3", handler=handle3)
   
   # Connect to 3 different sources
   flow.connect(source1_id, "output", target_id, "input1")
   flow.connect(source2_id, "output", target_id, "input2")
   flow.connect(source3_id, "output", target_id, "input3")

When all 3 sources emit:
* **Source1** emits → **slot1.receive()** → **handle1()** called (1st call)
* **Source2** emits → **slot2.receive()** → **handle2()** called (2nd call)
* **Source3** emits → **slot3.receive()** → **handle3()** called (3rd call)

**Result**: The target routine's handlers are called **3 times** (once per slot).

**Multiple Emissions**:

If each upstream routine emits multiple times, the downstream routine is called
for each emission:

.. code-block:: python

   # Each source emits 3 times
   source1()  # Emits 3 times → slot1 handler called 3 times
   source2()  # Emits 3 times → slot2 handler called 3 times
   source3()  # Emits 3 times → slot3 handler called 3 times
   
   # Total: 3 sources × 3 emissions = 9 handler calls

**Note on Execution Strategy**:

The behavior described above applies regardless of the Flow's execution strategy
(sequential or concurrent). The key point is that each slot's handler is called
once for each emission it receives. For details on how execution strategy affects
the order and timing of handler execution, see :doc:`flows`.

This is the expected behavior - each slot operates independently and triggers
its handler **once for each emission** it receives from its connected event.

See Also
--------

* :doc:`flows` - Flow execution strategies and execution order
* :doc:`routines` - Defining slots and events
* :doc:`../api_reference/event` - Event API documentation
* :doc:`../api_reference/slot` - Slot API documentation

Merge Strategy
---------------

The ``merge_strategy`` parameter controls how new data is merged with existing
data in a slot when ``receive()`` is called. This is crucial when a slot
receives data from multiple events or multiple times from the same event.

Understanding Merge Strategy
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a slot receives data via ``receive()``, the following happens:

1. New data is merged with existing ``slot._data`` according to ``merge_strategy``
2. ``slot._data`` is updated with the merged result
3. Handler is called with the merged data (if handler is defined)

The merge strategy determines:
* How new data combines with existing data
* What data is stored in ``slot._data``
* What data is passed to the handler

Available Strategies
--------------------

**1. "override" (Default)**

The default strategy completely replaces existing data with new data.

**Behavior**:
* Each ``receive()`` call completely replaces ``slot._data``
* Previous data is completely discarded
* Handler receives only the latest data
* No data accumulation

**Example**:

.. code-block:: python

   from routilux import Routine
   
   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self._handle, merge_strategy="override")
       
       def _handle(self, **kwargs):
           print(f"Received: {kwargs}")
   
   routine = MyRoutine()
   
   # First receive
   routine.input_slot.receive({"a": 1, "b": 2})
   # slot._data = {"a": 1, "b": 2}
   # Handler receives: {"a": 1, "b": 2}
   
   # Second receive
   routine.input_slot.receive({"a": 10, "c": 3})
   # slot._data = {"a": 10, "c": 3}  # "b" is lost
   # Handler receives: {"a": 10, "c": 3}
   
   # Third receive
   routine.input_slot.receive({"d": 4})
   # slot._data = {"d": 4}  # "a" and "c" are lost
   # Handler receives: {"d": 4}

**Use Cases**:
* When you only need the latest data
* When previous data is irrelevant
* Simple data passing scenarios

**2. "append"**

Accumulates values in lists, preserving all received data.

**Behavior**:
* Each ``receive()`` call appends values to lists
* All historical data is preserved in lists
* Handler receives accumulated data (lists) each time
* Non-list values are converted to lists on first append

**Example**:

.. code-block:: python

   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self._handle, merge_strategy="append")
       
       def _handle(self, **kwargs):
           print(f"Received: {kwargs}")
           print(f"slot._data: {self.input_slot._data}")
   
   routine = MyRoutine()
   
   # First receive
   routine.input_slot.receive({"task": "task1", "data": "data1"})
   # slot._data = {"task": ["task1"], "data": ["data1"]}
   # Handler receives: {"task": ["task1"], "data": ["data1"]}
   
   # Second receive
   routine.input_slot.receive({"task": "task2", "data": "data2"})
   # slot._data = {"task": ["task1", "task2"], "data": ["data1", "data2"]}
   # Handler receives: {"task": ["task1", "task2"], "data": ["data1", "data2"]}
   
   # Third receive (only "task" key)
   routine.input_slot.receive({"task": "task3"})
   # slot._data = {"task": ["task1", "task2", "task3"], "data": ["data1", "data2"]}
   # Handler receives: {"task": ["task1", "task2", "task3"]}
   # Note: "data" key not in handler kwargs (only keys from new_data are passed)

**Important Notes for "append"**:
* Handler receives only keys present in the current ``receive()`` call
* But ``slot._data`` contains all accumulated data
* To access all accumulated data, check ``slot._data`` directly in handler
* Values are always lists (even single values become ``[value]``)

**Use Cases**:
* Aggregating data from multiple sources (see :doc:`aggregation_pattern`)
* Collecting results over time
* Building up datasets incrementally

**3. Custom Function**

A callable that implements custom merge logic.

**Behavior**:
* Function receives ``(old_data: Dict, new_data: Dict)``
* Function returns merged result ``Dict``
* ``slot._data`` is updated with the return value
* Handler receives the merged result

**Example**:

.. code-block:: python

   def custom_merge(old_data, new_data):
       """Custom merge: add numeric values, concatenate strings."""
       result = old_data.copy()
       for key, value in new_data.items():
           if key in result:
               if isinstance(result[key], (int, float)) and isinstance(value, (int, float)):
                   result[key] = result[key] + value  # Add numbers
               elif isinstance(result[key], str) and isinstance(value, str):
                   result[key] = result[key] + " " + value  # Concatenate strings
               else:
                   result[key] = value  # Override for other types
           else:
               result[key] = value
       return result
   
   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self._handle, merge_strategy=custom_merge)
       
       def _handle(self, **kwargs):
           print(f"Received: {kwargs}")
   
   routine = MyRoutine()
   
   routine.input_slot.receive({"count": 10, "name": "Alice"})
   # slot._data = {"count": 10, "name": "Alice"}
   
   routine.input_slot.receive({"count": 5, "name": "Bob"})
   # slot._data = {"count": 15, "name": "Alice Bob"}
   
   routine.input_slot.receive({"count": 3, "status": "active"})
   # slot._data = {"count": 18, "name": "Alice Bob", "status": "active"}

**Use Cases**:
* Deep merging nested dictionaries
* Averaging numeric values
* Domain-specific merge logic
* Complex data transformations

Key Behaviors
~~~~~~~~~~~~~

**Handler Invocation**:
* Handler is called **immediately** after each ``receive()`` call
* Handler receives the **merged data** (not just new data)
* In "append" strategy, handler receives lists containing accumulated values

**Multiple Events**:
* When multiple events connect to the same slot, all emissions are merged
* Each event's data follows the same merge_strategy
* Order of emissions affects the final merged result

**Data Persistence**:
* ``slot._data`` persists across multiple ``receive()`` calls
* Data accumulates according to merge_strategy
* To reset, manually clear: ``slot._data = {}``

**Edge Cases**:
* Empty dict: "override" replaces with empty dict; "append" ignores empty dict
* None values: "append" accumulates None values in lists
* Nested structures: "override" replaces entire nested dict; "append" appends nested dicts as separate list items

Comparison Table
----------------

+------------------+------------------+------------------+------------------+
| Aspect           | override         | append           | custom           |
+==================+==================+==================+==================+
| Data retention   | None (replaced)  | All (in lists)   | Custom           |
+------------------+------------------+------------------+------------------+
| Handler receives | Latest data only | Accumulated      | Merged result    |
|                  |                  | lists            |                  |
+------------------+------------------+------------------+------------------+
| Use case         | Latest data only | Aggregation      | Complex logic    |
+------------------+------------------+------------------+------------------+
| Performance      | Fastest          | Moderate         | Depends on func  |
+------------------+------------------+------------------+------------------+

Best Practices
--------------

1. **Use "override"** when you only need the latest data (most common case)

2. **Use "append"** when aggregating from multiple sources (see :doc:`aggregation_pattern`)

3. **Use custom function** for complex merge requirements

4. **Access slot._data directly** in handler if you need all accumulated data (especially with "append")

5. **Reset slot._data** after processing if you need to start a new accumulation cycle

6. **Be aware of concurrency**: In concurrent execution, merge operations are not atomic and may have race conditions

See Also
--------

* :doc:`aggregation_pattern` - Using "append" strategy for aggregation
* :doc:`routines` - Defining slots with merge_strategy
* :doc:`../api_reference/slot` - Slot API documentation

Creating Connections
--------------------

Connections are typically created through Flow's connect method:

.. code-block:: python

   connection = flow.connect(
       source_routine_id="routine1",
       source_event="output",
       target_routine_id="routine",
       target_slot="input"
   )

You can also create connections directly:

.. code-block:: python

   from routilux import Connection

   connection = Connection(event, slot, param_mapping={"param1": "param2"})

Parameter Mapping
-----------------

Parameter mapping allows you to transform parameter names when data flows through a connection:

.. code-block:: python

   # Source event emits "source_param"
   event = routine1.add_event("output", ["source_param"])
   
   # Target slot expects "target_param"
   slot = routine.add_slot("input", handler=lambda target_param: ...)
   
   # Map source_param to target_param
   connection = Connection(
       event, slot,
       param_mapping={"source_param": "target_param"}
   )

Activating Connections
----------------------

Connections are automatically activated when events are emitted. You can also activate them manually:

.. code-block:: python

   connection.activate({"data": "test"})

Disconnecting
-------------

Disconnect an event from a slot:

.. code-block:: python

   connection.disconnect()

Or disconnect through the event or slot:

.. code-block:: python

   event.disconnect(slot)
   slot.disconnect(event)

