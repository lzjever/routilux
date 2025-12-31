Working with Routines
=====================

Routines are the core building blocks of routilux. This guide explains how to create and use routines in the new event queue architecture.

Routine Identifier (routine_id)
--------------------------------

Each routine in a flow has a ``routine_id`` that identifies it within the flow. When you add a routine to a flow using ``flow.add_routine()``, you can specify a custom ``routine_id`` or use the auto-generated one.

For details on how to use ``routine_id``, see :doc:`identifiers`.

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

Understanding Routine's Role
------------------------------

**Routine is responsible for function implementation**:

- **What each node does**: Define slots, events, and handler logic
- **Static Configuration**: Store in ``_config`` dictionary (set via ``set_config()``)
- **No Runtime State**: Routines **must not** modify instance variables during execution

**What Routine Does NOT Do**:

- ❌ Store runtime execution state (that's ``JobState``'s job)
- ❌ Store business data (that's ``JobState.shared_data``'s job)
- ❌ Define workflow structure (that's ``Flow``'s job)
- ❌ Handle execution-specific output (that's ``JobState.output_handler``'s job)

**Critical Constraint**: The same routine object can be used by multiple concurrent executions.
Modifying instance variables would cause data corruption. All execution-specific state
must be stored in ``JobState``.

Execution State Management
---------------------------

Use ``get_execution_context()`` for convenient access to execution handles:

.. code-block:: python

   def process_data(self, data):
       # Get execution context (flow, job_state, routine_id)
       ctx = self.get_execution_context()
       if ctx:
           # Store execution-specific state in JobState
           current_state = ctx.job_state.get_routine_state(ctx.routine_id) or {}
           processed_count = current_state.get("processed_count", 0) + 1
           ctx.job_state.update_routine_state(
               ctx.routine_id, {"processed_count": processed_count}
           )
           
           # Store business data in JobState
           ctx.job_state.update_shared_data("last_processed", data)
           ctx.job_state.append_to_shared_log({"action": "process", "data": data})
           
           # Send output via JobState
           self.send_output("user_data", message="Processing", value=data)

**Using get_execution_context()**:

The ``get_execution_context()`` method returns an ``ExecutionContext`` object containing
``flow``, ``job_state``, and ``routine_id``:

.. code-block:: python

   ctx = self.get_execution_context()
   if ctx:
       # Access flow, job_state, and routine_id
       ctx.flow
       ctx.job_state
       ctx.routine_id
       
       # Or unpack
       flow, job_state, routine_id = ctx

**Retrieve execution state after execution**:

.. code-block:: python

   # After execution
   routine_state = job_state.get_routine_state(routine_id)
   print(routine_state)  # {"processed_count": 1, ...}
   
   # Access shared data
   shared_data = job_state.get_shared_data("last_processed")
   shared_log = job_state.get_shared_log()

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
