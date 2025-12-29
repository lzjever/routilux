Working with Routines
=====================

Routines are the core building blocks of routilux. This guide explains how to create and use routines in the new event queue architecture.

Creating a Routine
------------------

To create a routine, inherit from ``Routine``:

.. code-block:: python

   from routilux import Routine

   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           # Define slots and events here

Defining Slots
--------------

Slots are input mechanisms for routines. Define a slot with a handler function:

.. code-block:: python

   def process_input(self, data=None, **kwargs):
       # Process the input data
       # Handler should accept **kwargs for flexibility
       pass

   self.input_slot = self.define_slot("input", handler=process_input)

You can also specify a merge strategy for slots that receive data from multiple events:

.. code-block:: python

   self.input_slot = self.define_slot(
       "input",
       handler=process_input,
       merge_strategy="append"  # or "override", or custom function
   )

**Merge Strategies**:
- ``"override"`` (default): New data replaces old data
- ``"append"``: Values are accumulated in lists
- Custom function: ``callable(old_data, new_data) -> merged_data``

Defining Events
---------------

Events are output mechanisms for routines. Define an event with output parameters:

.. code-block:: python

   self.output_event = self.define_event("output", ["result", "status"])

Emitting Events
---------------

Emit events to trigger connected slots. The flow context is automatically detected:

.. code-block:: python

   def _handle_trigger(self, **kwargs):
       # Flow is automatically detected from routine context
       # No need to pass flow parameter!
       self.emit("output", result="success", status="completed")

**Automatic Flow Detection**:

- When called within a Flow execution context, ``emit()`` automatically retrieves
  the flow from ``routine._current_flow``
- The flow context is set by ``Flow.execute()`` and ``Flow.resume()``
- You don't need to manually pass the flow parameter

**Explicit Flow Parameter** (optional):

- You can still explicitly pass flow for backward compatibility:

  .. code-block:: python

     flow = getattr(self, "_current_flow", None)
     self.emit("output", flow=flow, result="success")

**Non-blocking Behavior**:
- ``emit()`` returns immediately after enqueuing tasks
- Downstream execution happens asynchronously
- Don't expect handlers to complete before ``emit()`` returns

Entry Routines
--------------

Routines used as entry points in a Flow must define a "trigger" slot:

.. code-block:: python

   class MyEntryRoutine(Routine):
       def __init__(self):
           super().__init__()
           # Define trigger slot for entry routine
           self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
           self.output_event = self.define_event("output", ["result"])
       
       def _handle_trigger(self, **kwargs):
           # This will be called by Flow.execute()
           data = kwargs.get("data", "default")
           # Flow context is automatically set
           self.emit("output", result=f"Processed: {data}")

The ``Flow.execute()`` method will automatically call the "trigger" slot with the provided
entry_params. See :doc:`flows` for more details on executing flows.

Slot Handlers
-------------

**Handler Signature**

Slot handlers should accept ``**kwargs`` for flexibility:

.. code-block:: python

   def _handle_input(self, data=None, **kwargs):
       # Accept data parameter and any other kwargs
       # This works with various data formats
       pass

**Why ``**kwargs``?**
- Handlers receive data from events, which may have different parameter names
- Parameter mapping (via ``Flow.connect()``) may transform parameter names
- ``**kwargs`` ensures handlers work with any data format

**Data Extraction Helper**

Use ``_extract_input_data()`` to simplify data extraction:

.. code-block:: python

   def process_input(self, data=None, **kwargs):
       # Extract data using the helper method
       extracted_data = self._extract_input_data(data, **kwargs)
       
       # Process the extracted data
       result = self.process(extracted_data)
       self.emit("output", result=result)

This method handles various input patterns:
- Direct parameter: ``_extract_input_data("text")`` → ``"text"``
- 'data' key: ``_extract_input_data(None, data="text")`` → ``"text"``
- Single value: ``_extract_input_data(None, text="value")`` → ``"value"``
- Multiple values: ``_extract_input_data(None, a=1, b=2)`` → ``{"a": 1, "b": 2}``

Multiple Slots
--------------

A routine can have multiple slots, each connected to different upstream routines.
When an upstream routine emits data, it triggers the handler of the connected slot.

**Important**: Each slot has its own handler and is triggered independently.

**Example**:

.. code-block:: python

   class TargetRoutine(Routine):
       def __init__(self):
           super().__init__()
           # Define three slots, each with its own handler
           self.slot1 = self.define_slot("input1", handler=self._handle_input1)
           self.slot2 = self.define_slot("input2", handler=self._handle_input2)
           self.slot3 = self.define_slot("input3", handler=self._handle_input3)
       
       def _handle_input1(self, data1=None, **kwargs):
           # This handler is called when slot1 receives data
           pass
       
       def _handle_input2(self, data2=None, **kwargs):
           # This handler is called when slot2 receives data
           pass
       
       def _handle_input3(self, data3=None, **kwargs):
           # This handler is called when slot3 receives data
           pass

If three upstream routines each emit once:
- **Source1** emits → **slot1** receives → **handler1** is called
- **Source2** emits → **slot2** receives → **handler2** is called
- **Source3** emits → **slot3** receives → **handler3** is called

**Result**: The target routine's handlers are called **3 times** (once per slot).

**Slot Independence**:
- Each slot maintains its own ``_data`` state
- Each slot's merge_strategy applies independently
- Each slot's handler is called when data is received
- Each emission triggers the handler once

Execution Behavior
------------------

**Event Queue Processing**

When a routine emits an event:
1. Tasks are created for each connected slot
2. Tasks are enqueued (non-blocking)
3. ``emit()`` returns immediately
4. Event loop processes tasks asynchronously

**Handler Execution**

Slot handlers execute in the event loop's thread pool:
- Sequential mode: One handler at a time (``max_workers=1``)
- Concurrent mode: Multiple handlers in parallel (``max_workers>1``)

**Fair Scheduling**

Tasks are processed in queue order:
- Multiple message chains progress alternately
- Long chains don't block shorter ones
- Fair progress for all active chains

Statistics
----------

Track routine statistics using the ``_stats`` dictionary:

.. code-block:: python

   self._stats["processed_count"] = self._stats.get("processed_count", 0) + 1

Or use the convenient ``_track_operation()`` method for consistent tracking:

.. code-block:: python

   def process_data(self, data):
       try:
           # Process the data
           result = self.process(data)
           # Track successful operation
           self._track_operation("processing", success=True, items_processed=1)
           return result
       except Exception as e:
           # Track failed operation
           self._track_operation("processing", success=False, error=str(e))
           raise

Retrieve statistics:

.. code-block:: python

   stats = routine.stats()
   print(stats)  # {"processed_count": 1, "total_processing": 1, "successful_processing": 1, ...}

Getting Slots and Events
------------------------

Retrieve slots and events by name:

.. code-block:: python

   slot = routine.get_slot("input")
   event = routine.get_event("output")

Error Handling
--------------

Set error handlers at the routine level:

.. code-block:: python

   from routilux import ErrorHandler, ErrorStrategy

   routine.set_error_handler(
       ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=3)
   )

Error handling priority:
1. Routine-level error handler (if set)
2. Flow-level error handler (if set)
3. Default behavior (STOP)

See :doc:`error_handling` for more details.

Configuration
-------------

Store configuration in ``_config`` dictionary:

.. code-block:: python

   routine.set_config(timeout=30, retries=3)
   timeout = routine.get_config("timeout", default=10)

All configuration values are automatically serialized.

Best Practices
--------------

1. **Always use ``**kwargs`` in handlers**:

   .. code-block:: python

      def _handle_input(self, data=None, **kwargs):
          # Flexible handler signature

2. **Define trigger slot for entry routines**:

   .. code-block:: python

      self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)

3. **Don't rely on emit() waiting**:

   .. code-block:: python

      self.emit("output", data="value")
      # Handler may not have executed yet!
      # Use wait_for_completion() if needed

4. **Use merge_strategy="append" for aggregation**:

   .. code-block:: python

      self.input_slot = self.define_slot("input", merge_strategy="append")

5. **Track operations consistently**:

   .. code-block:: python

      self._track_operation("processing", success=True, items=10)
