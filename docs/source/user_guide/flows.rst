Working with Flows
==================

Flows orchestrate multiple routines and manage their execution using a unified event queue mechanism. This guide explains the new architecture and how to create and use flows.

**Understanding Flow's Role is Critical**

``Flow`` is responsible for **workflow structure and static configuration**:

- **Workflow Structure**: Which routines exist and how they're connected
- **Static Configuration**: Node-level static parameters (execution strategy, max_workers, error handlers)
- **Connection Management**: Links events to slots with parameter mapping
- **Execution Orchestration**: Manages event queue, task scheduling, and thread pool

**What Flow Does NOT Do**:

- ❌ Store runtime execution state (that's ``JobState``'s job)
- ❌ Store business data (that's ``JobState.shared_data``'s job)
- ❌ Implement node functionality (that's ``Routine``'s job)
- ❌ Handle execution-specific output (that's ``JobState.output_handler``'s job)

**Key Principle**: Flow is a **template** that can be executed multiple times.
Each execution creates a new, independent ``JobState`` for runtime state.

Architecture Overview
---------------------

Routilux uses an **event queue pattern** for workflow execution:

1. **Non-blocking emit()**: When a routine emits an event, tasks are enqueued immediately and ``emit()`` returns without waiting
2. **Unified execution model**: Both sequential and concurrent modes use the same queue-based mechanism
3. **Fair scheduling**: Tasks are processed fairly, preventing long chains from blocking shorter ones
4. **Event loop**: A background thread processes tasks from the queue using a thread pool

Key Concepts
------------

**Event Queue**
    All slot activations are queued as ``SlotActivationTask`` objects. The event loop processes these tasks asynchronously.

**Non-blocking Execution**
    ``emit()`` calls return immediately after enqueuing tasks. Downstream execution happens asynchronously in background threads.

**Unified Model**
    Sequential mode (``max_workers=1``) and concurrent mode (``max_workers>1``) use the same queue mechanism. The only difference is the thread pool size.

**Fair Scheduling**
    Tasks are processed in queue order, allowing multiple message chains to progress alternately rather than one chain blocking others.

Flow Identifier (flow_id)
--------------------------

Each ``Flow`` has a ``flow_id`` that identifies the workflow definition. You can specify it when creating the Flow, or let it auto-generate as a UUID.

For details on how to use ``flow_id``, see :doc:`identifiers`.

Creating a Flow
---------------

Create a flow with an optional flow ID and execution timeout:

.. code-block:: python

   from routilux import Flow

   flow = Flow(flow_id="my_flow")
   # Or let it auto-generate an ID
   flow = Flow()
   
   # Create flow with custom execution timeout (default: 300.0 seconds)
   flow = Flow(execution_timeout=600.0)  # 10 minutes

Adding Routines
---------------

Add routines to a flow:

.. code-block:: python

   routine = MyRoutine()
   routine_id = flow.add_routine(routine, routine_id="my_routine")
   # Or use the routine's auto-generated ID
   routine_id = flow.add_routine(routine)

Connecting Routines
-------------------

Connect routines by linking events to slots:

.. code-block:: python

   flow.connect(
       source_routine_id="routine1",
       source_event="output",
       target_routine_id="routine",
       target_slot="input"
   )

You can also specify parameter mapping:

.. code-block:: python

   flow.connect(
       source_routine_id="routine1",
       source_event="output",
       target_routine_id="routine",
       target_slot="input",
       param_mapping={"source_param": "target_param"}
   )

Executing Flows
---------------

Execute a flow starting from an entry routine:

.. code-block:: python

   job_state = flow.execute(
       entry_routine_id="routine1",
       entry_params={"data": "test"}
   )

**Important**: The entry routine must have a "trigger" slot defined. ``Flow.execute()``
will call this slot with the provided entry_params. If the entry routine doesn't have
a "trigger" slot, a ``ValueError`` will be raised.

Execution Timeout
-----------------

By default, Flow execution has a timeout of 300 seconds (5 minutes) to accommodate
long-running tasks such as LLM calls. You can customize this timeout in two ways:

**1. Set default timeout when creating Flow:**

.. code-block:: python

   # Create Flow with custom default timeout (10 minutes)
   flow = Flow(execution_timeout=600.0)
   
   # All execute() calls will use this timeout
   job_state = flow.execute(entry_routine_id="routine1")

**2. Override timeout per execution:**

.. code-block:: python

   flow = Flow()  # Uses default 300.0 seconds
   
   # Override timeout for this specific execution
   job_state = flow.execute(
       entry_routine_id="routine1",
       timeout=600.0  # 10 minutes for this execution
   )

**Timeout Behavior:**

- **Primary completion detection**: Execution completes when the task queue is empty and
  there are no active tasks. This happens automatically and is the normal completion path.
- **Timeout as safety mechanism**: The timeout serves as a safety limit to prevent infinite
  waiting. If execution doesn't complete within the timeout period:
  - The event loop is forcefully stopped
  - ``job_state.status`` is set to ``"failed"``
  - A timeout error is recorded in the job state
- The timeout applies to the entire execution, including all downstream routines
- For very long-running tasks (e.g., LLM calls), increase the timeout accordingly
- **Note**: In normal operation, execution completes as soon as all tasks are done, without
  waiting for the timeout. The timeout only triggers if something goes wrong.

Execution Completion Detection
------------------------------

Routilux uses a systematic completion detection mechanism to ensure all tasks are
processed before ``execute()`` returns. This mechanism:

- **Completion criteria**: Execution is considered complete when:
  - The task queue is empty (no pending tasks)
  - There are no active tasks (all running tasks have finished)
  - This check is performed even if ``job_state.status`` is still ``"running"``
- **Multiple stability checks**: Verifies completion multiple times to avoid race conditions
  where tasks might be enqueued between checks
- **Queue monitoring**: Continuously monitors the task queue size
- **Active task tracking**: Tracks all active tasks in the thread pool executor
- **Event loop management**: Automatically restarts event loop if it stops prematurely
  while tasks are still pending

**Completion Flow:**

1. When ``execute()`` is called, it starts the event loop and triggers the entry routine
2. The completion detection mechanism continuously checks if the queue is empty and
   there are no active tasks
3. Once both conditions are met (verified multiple times for stability), execution is
   considered complete
4. The event loop is stopped (``flow._running = False``)
5. The event loop thread is joined and cleaned up
6. ``job_state.status`` is updated to ``"completed"``

The completion detection is automatic and transparent - you don't need to do anything
special. However, for advanced use cases, you can use the completion detection API:

.. code-block:: python

   from routilux.job_state import JobState
   
   job_state = flow.execute(entry_routine_id="routine1")
   
   # Manually wait for completion with progress callback
   def progress_callback(queue_size, active_count, status):
       print(f"Queue: {queue_size}, Active: {active_count}, Status: {status}")
   
   completed = JobState.wait_for_completion(
       flow=flow,
       job_state=job_state,
       timeout=300.0,
       progress_callback=progress_callback
   )
   
   if completed:
       print("Execution completed successfully")
   else:
       print("Execution timed out")

Example entry routine:

.. code-block:: python

   class EntryRoutine(Routine):
       def __init__(self):
           super().__init__()
           # Define trigger slot - required for entry routines
           self.trigger_slot = self.add_slot("trigger", handler=self._handle_trigger)
           self.output_event = self.add_event("output", ["data"])
       
       def _handle_trigger(self, **kwargs):
           # This will be called by Flow.execute()
           data = kwargs.get("data", "default")
           # Flow is automatically detected from routine context
           self.emit("output", data=data)

The execute method returns a ``JobState`` object that tracks the execution status.

**Important**: Each ``execute()`` call is an independent execution:

- Each ``execute()`` creates a new ``JobState`` and starts a new event loop
- Slot data (``_data``) is **NOT shared** between different ``execute()`` calls
- If you need to aggregate data from multiple sources, use a single ``execute()``
  that triggers multiple emits, not multiple ``execute()`` calls

Example - Correct way to aggregate:

.. code-block:: python

   class MultiSourceRoutine(Routine):
       def _handle_trigger(self, **kwargs):
           # Emit multiple messages in a single execute()
           for data in ["A", "B", "C"]:
               self.emit("output", data=data)  # All share same execution
   
   flow.execute(multi_source_id)  # Single execute, multiple emits

Example - Wrong way (won't share state):

.. code-block:: python

   # Bad: Multiple executes don't share slot state
   flow.execute(source1_id)  # Creates new JobState
   flow.execute(source2_id)  # Creates another new JobState
   # Aggregator won't see both messages!

Event Emission and Flow Context
---------------------------------

**Automatic Flow Detection**

The ``emit()`` method automatically detects the flow from the routine's context:

.. code-block:: python

   class MyRoutine(Routine):
       def _handle_trigger(self, **kwargs):
           # No need to pass flow - automatically detected!
           self.emit("output", data="value")
           # Flow is automatically retrieved from routine._current_flow

The flow context is automatically set by ``Flow.execute()`` and ``Flow.resume()``, so you
don't need to manually pass the flow parameter in most cases.

**Explicit Flow Parameter**

You can still explicitly pass the flow parameter for backward compatibility or special cases:

.. code-block:: python

   flow_obj = getattr(self, "_current_flow", None)
   self.emit("output", flow=flow_obj, data="value")

**Fallback Behavior**

If no flow context is available, ``emit()`` falls back to direct slot calls (legacy mode):

.. code-block:: python

   # Without flow context
   routine.emit("output", data="value")  # Direct slot.receive() call

Execution Modes
---------------

Routilux supports two execution modes, both using the same queue-based mechanism:

**Sequential Mode** (default)
    - ``max_workers=1``: Only one task executes at a time
    - Tasks are processed in queue order
    - Deterministic execution order
    - Suitable when order matters or for easier debugging

**Concurrent Mode**
    - ``max_workers>1``: Multiple tasks execute in parallel
    - Tasks are processed concurrently up to the thread pool limit
    - Non-deterministic execution order
    - Suitable for independent operations that can run simultaneously

Creating a Concurrent Flow
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Create a flow with concurrent execution strategy:

.. code-block:: python

   flow = Flow(
       flow_id="my_flow",
       execution_strategy="concurrent",
       max_workers=5
   )

The ``execution_strategy`` parameter can be:
- ``"sequential"`` (default): ``max_workers=1``, tasks execute one at a time
- ``"concurrent"``: ``max_workers>1``, tasks execute in parallel

The ``max_workers`` parameter controls the maximum number of concurrent threads (default: 5 for concurrent mode, 1 for sequential mode).

Setting Execution Strategy
~~~~~~~~~~~~~~~~~~~~~~~~~~

You can also set the execution strategy after creating the flow:

.. code-block:: python

   flow = Flow()
   flow.set_execution_strategy("concurrent", max_workers=10)

Or override the strategy when executing:

.. code-block:: python

   job_state = flow.execute(
       entry_routine_id="routine1",
       entry_params={"data": "test"},
       execution_strategy="concurrent"
   )

How Execution Works
--------------------

**Event Queue Pattern**

All execution uses a unified event queue:

1. **Event Emission**: When ``emit()`` is called, tasks are created for each connected slot and enqueued
2. **Event Loop**: A background thread continuously processes tasks from the queue
3. **Task Execution**: Tasks are submitted to a thread pool (size controlled by ``max_workers``)
4. **Fair Scheduling**: Tasks are processed in queue order, allowing fair progress

**Non-blocking emit()**

``emit()`` is always non-blocking:

.. code-block:: python

   def _handle_trigger(self, **kwargs):
       print("Before emit")
       self.emit("output", data="test")
       print("After emit")  # ← Executes immediately, doesn't wait for handlers

When an event is emitted:

1. **Task Creation**: Each connected slot's activation is wrapped in a ``SlotActivationTask``
2. **Enqueue**: Tasks are added to the queue (non-blocking)
3. **Immediate Return**: ``emit()`` returns immediately (typically < 1ms)
4. **Background Processing**: The event loop processes tasks asynchronously

**Event Loop**

The event loop runs in a background thread and is automatically started by ``Flow.execute()``.
It continuously processes tasks from the queue:

1. Gets tasks from the queue (with timeout to allow checking completion)
2. Submits tasks to the thread pool executor
3. Tracks active tasks for completion monitoring
4. Handles pause/resume and error conditions

The event loop implementation is in the ``routilux.flow.event_loop`` module, but you don't need to interact with it directly.

**Task Execution**

Tasks are executed by the thread pool executor:

1. Parameter mapping is applied if a connection exists
2. The slot's ``receive()`` method is called with the mapped data
3. Errors are handled according to the configured error handler strategy

The task execution implementation is in the ``routilux.flow.event_loop`` module.

Execution Order
---------------

**Fair Scheduling**

Tasks are processed in queue order, providing fair scheduling:

- Multiple message chains can progress alternately
- Long chains don't block shorter ones
- Tasks from different sources are interleaved

**Sequential Mode**

In sequential mode (``max_workers=1``):

- Tasks execute one at a time in queue order
- Execution order is deterministic (queue order)
- No parallelism, but fair scheduling still applies

**Concurrent Mode**

In concurrent mode (``max_workers>1``):

- Multiple tasks execute in parallel (up to ``max_workers``)
- Execution order is non-deterministic
- Tasks may complete in any order

**Important**: Unlike the old architecture, there is no depth-first execution guarantee.
Tasks are processed fairly in queue order, allowing better overall throughput.

Waiting for Completion
-----------------------

Since ``emit()`` returns immediately without waiting for handlers, you must explicitly
wait for completion when needed:

.. code-block:: python

   flow = Flow(execution_strategy="concurrent")
   job_state = flow.execute("entry_routine")
   
   # emit() has returned, but handlers may still be running
   # Wait for all handlers to complete
   from routilux.job_state import JobState
   JobState.wait_for_completion(flow, job_state, timeout=10.0)
   
   # Now all handlers are guaranteed to be finished

**How ``JobState.wait_for_completion()`` Works**:

1. Waits for the event loop thread to finish
2. Checks that all active tasks are complete
3. Returns when all tasks are done (or timeout occurs)

**Note**: The ``execute()`` method automatically uses a systematic completion detection
mechanism that waits for all tasks to complete. For most use cases, you don't need to
call ``JobState.wait_for_completion()`` manually. However, for concurrent execution or when you
need explicit control, you can use it.

**Best Practice**:

For concurrent execution, always call ``JobState.wait_for_completion()`` before accessing results or shutting down:

.. code-block:: python

   flow = Flow(execution_strategy="concurrent")
   try:
       job_state = flow.execute("entry_routine")
       JobState.wait_for_completion(flow, job_state, timeout=10.0)
       # Now safe to access results
   finally:
       flow.shutdown(wait=True)

Shutting Down Flows
-------------------

When you're done with a flow, properly shut it down to clean up resources:

.. code-block:: python

   flow = Flow(execution_strategy="concurrent")
   
   try:
       job_state = flow.execute("entry_routine")
       JobState.wait_for_completion(flow, job_state, timeout=10.0)
   finally:
       # Always shut down to clean up the thread pool
       flow.shutdown(wait=True)

The ``shutdown()`` method:
- Stops the event loop
- Waits for all tasks to complete (if ``wait=True``)
- Closes the thread pool executor
- Cleans up all resources

Pausing and Resuming Execution
--------------------------------

**Pausing Execution**

Pause execution at any point:

.. code-block:: python

   flow.pause(reason="User requested pause", checkpoint={"step": 1})

When paused:
- Active tasks complete
- Pending tasks are moved to ``_pending_tasks``
- Task state is serialized to ``JobState.pending_tasks``
- Event loop waits (doesn't process new tasks)

**Resuming Execution**

Resume from a paused state:

.. code-block:: python

   resumed_job_state = flow.resume(job_state)

When resumed:
- Pending tasks are deserialized and restored from ``job_state.pending_tasks``
- **Tasks are automatically recovered from slot data** (if not in pending_tasks)
- Tasks are moved back to the queue
- Event loop restarts if needed
- Execution continues from where it paused
- Retry state is preserved and continues correctly

**Automatic Task Recovery**

Starting from version 0.1.0, routilux automatically recovers tasks from slot data
during ``resume()``. This means:

- ✅ If a slot has data but no pending task, a task is automatically created
- ✅ Retry state (retry_count, max_retries) is preserved
- ✅ Connection information is automatically restored
- ✅ You don't need to manually check slot data or create tasks

**Example**:

.. code-block:: python

   # Host A: Save state (with or without pausing)
   flow_data = flow.serialize()
   job_state_data = job_state.serialize()
   
   # Host B: Restore and resume
   new_flow = Flow()
   new_flow.deserialize(flow_data)
   new_job_state = JobState()
   new_job_state.deserialize(job_state_data)
   
   # Resume automatically recovers tasks from slot data
   resumed = new_flow.resume(new_job_state)
   # ✅ Execution continues correctly, even if some tasks weren't in pending_tasks

**Serialization Support**

Pending tasks are automatically serialized when pausing and deserialized when resuming:

.. code-block:: python

   # Pause (captures pending tasks)
   flow.pause(job_state, reason="checkpoint")
   
   # Serialize flow and job_state separately
   flow_data = flow.serialize()
   job_state_data = job_state.serialize()
   
   # Later: Deserialize and resume
   new_flow = Flow()
   new_flow.deserialize(flow_data)
   new_job_state = JobState()
   new_job_state.deserialize(job_state_data)
   
   # Resume (automatically recovers tasks from slot data if needed)
   resumed = new_flow.resume(new_job_state)

**Note**: You can also serialize without pausing. Routilux will automatically recover
tasks from slot data during resume. See :doc:`serialization` for best practices.

Cancelling Execution
--------------------

Cancel execution:

.. code-block:: python

   flow.cancel(reason="User cancelled")

When cancelled:
- Event loop stops
- Active tasks are cancelled
- JobState status is set to "cancelled"

Error Handling
---------------

Set an error handler for the flow:

.. code-block:: python

   from routilux import ErrorHandler, ErrorStrategy

   error_handler = ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=3)
   flow.set_error_handler(error_handler)

Error handling works at the task level:
- Each task execution is wrapped in error handling
- Retry logic is applied per task
- Errors don't stop the event loop

See :doc:`error_handling` for more details.

Performance Characteristics
----------------------------

**Sequential Mode**
    - Total time = sum of all task execution times
    - Deterministic execution order
    - Single thread, no parallelism

**Concurrent Mode**
    - Total time ≈ max(task execution times) for independent tasks
    - Parallel execution up to ``max_workers``
    - Speedup up to N× for N independent tasks (limited by thread pool size)

**When to Use Sequential Mode**:
- Execution order matters
- Deterministic behavior is required
- Easier debugging
- Handlers share non-thread-safe state

**When to Use Concurrent Mode**:
- Independent routines that can run in parallel
- I/O-bound operations (network requests, file I/O)
- Performance is critical
- High-throughput scenarios

Best Practices
--------------

1. **Always wait for completion** in concurrent mode:

   .. code-block:: python

      from routilux.job_state import JobState
      job_state = flow.execute("entry")
      JobState.wait_for_completion(flow, job_state, timeout=10.0)

2. **Always shut down** flows when done:

   .. code-block:: python

      try:
          # Use flow
      finally:
          flow.shutdown(wait=True)

3. **Use single execute() for aggregation**:

   .. code-block:: python

      # Good: Single execute with multiple emits
      class MultiSource(Routine):
          def _handle_trigger(self, **kwargs):
              for data in ["A", "B", "C"]:
                  self.emit("output", data=data)
      flow.execute(multi_source_id)

4. **Don't rely on execution order** in concurrent mode:
   - Execution order is non-deterministic
   - Use synchronization if order matters

5. **Use thread-safe operations** in concurrent mode:
   - Protect shared state with locks
   - Use thread-safe data structures when needed
