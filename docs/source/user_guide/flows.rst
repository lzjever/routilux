Working with Flows
==================

Flows orchestrate multiple routines and manage their execution. This guide explains how to create and use flows.

Creating a Flow
---------------

Create a flow with an optional flow ID:

.. code-block:: python

   from routilux import Flow

   flow = Flow(flow_id="my_flow")
   # Or let it auto-generate an ID
   flow = Flow()

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

**Important**: The entry routine must have a "trigger" slot defined. Flow.execute()
will call this slot with the provided entry_params. If the entry routine doesn't have
a "trigger" slot, a ValueError will be raised.

Example entry routine:

.. code-block:: python

   class EntryRoutine(Routine):
       def __init__(self):
           super().__init__()
           # Define trigger slot - required for entry routines
           self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
           self.output_event = self.define_event("output", ["data"])
       
       def _handle_trigger(self, **kwargs):
           # This will be called by Flow.execute()
           data = kwargs.get("data", "default")
           self.emit("output", data=data)

The execute method returns a ``JobState`` object that tracks the execution status.

Concurrent Execution
--------------------

Routilux supports concurrent execution of routines using thread pools. This is especially useful for I/O-bound operations where multiple routines can execute in parallel.

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
- ``"sequential"`` (default): Routines execute one after another
- ``"concurrent"``: Routines execute in parallel using a thread pool

The ``max_workers`` parameter controls the maximum number of concurrent threads (default: 5).

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

How Concurrent Execution Works
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a flow is set to concurrent execution mode:

1. **Event Emission**: When an event is emitted, all connected slots are activated concurrently using a thread pool
2. **Automatic Parallelization**: Routines that can run in parallel (no dependencies) are automatically executed concurrently
3. **Dependency Handling**: Routines wait for their dependencies to complete before executing
4. **Thread Safety**: All state updates are thread-safe

Concurrent Execution Thread Model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Understanding the thread model is crucial for effectively using concurrent execution mode.
This section explains how routines are scheduled and executed in concurrent mode.

Thread Pool Architecture
^^^^^^^^^^^^^^^^^^^^^^^^

Routilux uses a thread pool executor to manage concurrent routine execution:

.. code-block:: python

   flow = Flow(execution_strategy="concurrent", max_workers=5)
   # Creates a ThreadPoolExecutor with 5 worker threads

**Key Components**:

1. **Thread Pool**: A pool of worker threads (controlled by ``max_workers``)
2. **Task Queue**: Internal queue in the thread pool for pending tasks
3. **Active Futures Tracking**: Flow maintains a set of active futures to track running tasks
4. **Execution Lock**: A lock protecting the ``_active_futures`` set for thread-safe updates

Non-Blocking Event Emission
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In concurrent mode, ``Event.emit()`` is **non-blocking**:

.. code-block:: python

   # Routine A's handler
   def _handle_trigger(self, **kwargs):
       print("Before emit")
       self.emit("output", data="test")
       print("After emit")  # ← Executes immediately, doesn't wait for handlers

When an event is emitted:

1. **Task Submission**: Each connected slot's activation is submitted to the thread pool as a separate task
2. **Immediate Return**: ``emit()`` returns immediately after submitting all tasks (typically < 1ms)
3. **Background Execution**: Slot handlers execute in background threads independently

**Important**: ``emit()`` does **not** wait for handlers to complete. Handlers continue executing
asynchronously in background threads.

Parallel Slot Execution
^^^^^^^^^^^^^^^^^^^^^^^^

When an event emits to multiple connected slots, all slots execute **in parallel**:

.. code-block:: python

   # Routine A emits to 3 slots
   self.emit("output", data="test")
   # ↓
   # All 3 slots execute concurrently:
   # - Thread-1: Routine B.handler()
   # - Thread-2: Routine C.handler()
   # - Thread-3: Routine D.handler()

**Execution Timeline**:

.. code-block:: text

   T0: Routine A.emit() starts
   T1: Submit slot_B task → Thread-1 starts Routine B.handler()
   T2: Submit slot_C task → Thread-2 starts Routine C.handler()
   T3: Submit slot_D task → Thread-3 starts Routine D.handler()
   T4: emit() returns (~1ms)  ← Doesn't wait for handlers
   
   Meanwhile:
   T1-T6: Thread-1 executes Routine B.handler() (5 seconds)
   T2-T5: Thread-2 executes Routine C.handler() (3 seconds)
   T3-T4: Thread-3 executes Routine D.handler() (1 second)

**Key Points**:

* All connected slots start executing **almost simultaneously** (within milliseconds)
* Each slot's handler runs in a **separate thread**
* ``emit()`` returns **before** any handler completes
* Total execution time = **max(handler_times)**, not sum(handler_times)

Nested Event Emission and Call Stack Behavior
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When a handler emits further events, the execution continues in the same thread until the
task is submitted to the thread pool:

.. code-block:: python

   # Routine B's handler (executing in Thread-1)
   def _handle_slot1(self, data, **kwargs):
       result = self.process(data)
       self.emit("result", data=result)  # ← Executes in Thread-1
       self._cleanup()  # ← Must wait for emit() to return

**Call Stack in Thread-1**:

.. code-block:: text

   Thread-1:
     activate_slot()
       → slot_B.receive()
         → Routine B.handler()
           → emit("result")
             → Event.emit()
               → executor.submit()  # Submit Routine C task
               → with _execution_lock:  # Update tracking set
                 → _active_futures.add()
               → return
           → _cleanup()  # Must wait for emit() to return
           → return
       → return

**Important Observations**:

1. **Handler execution is synchronous within its thread**: The handler must wait for
   ``emit()`` to complete (including task submission and lock operations) before continuing
2. **Downstream routines execute in different threads**: Routine C will execute in Thread-3,
   but Routine B's handler is still running in Thread-1
3. **Lock operations are fast**: Lock acquisition and set updates typically take < 0.1ms,
   which is negligible compared to handler execution time (seconds or minutes)

**Why This Design**:

* Lock operations are necessary for thread-safe tracking of active futures
* The time spent on locks (~0.1ms) is negligible compared to handler execution time
* The real performance benefit comes from **parallel handler execution**, not from avoiding locks

Multiple Event Emissions
^^^^^^^^^^^^^^^^^^^^^^^^^

When a routine emits multiple events sequentially, each ``emit()`` must complete before
the next one starts:

.. code-block:: python

   # Routine A's handler
   def _handle_trigger(self, **kwargs):
       self.emit("output", msg="1#")  # Must complete before next emit
       self.emit("output", msg="2#")  # Waits for first emit to finish

**Execution Timeline**:

.. code-block:: text

   T0: emit("1#") starts
   T1: Submit slot_B task (acquire lock, update set)
   T2: Submit slot_C task (acquire lock, update set)
   T3: Submit slot_D task (acquire lock, update set)
   T4: emit("1#") returns (~1ms)
   
   T5: emit("2#") starts  ← Must wait for emit("1#") to complete
   T6: Submit slot_B task
   T7: Submit slot_C task
   T8: Submit slot_D task
   T9: emit("2#") returns

**Key Points**:

* Each ``emit()`` must complete (all tasks submitted, all locks released) before the next
  ``emit()`` can start
* If an event has many connected slots, the emit operation takes longer (more task
  submissions and lock operations)
* Lock contention may occur if handlers from the first emit are also emitting events

**Performance Impact**:

* Lock operations: ~0.1ms per slot
* Task submission: ~0.1ms per slot
* **Total emit() time**: ~0.2ms × number_of_slots
* This is still very fast compared to handler execution time

Thread Safety and Lock Usage
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Locks are used **only for metadata management**, not for blocking handler execution:

.. code-block:: python

   # Lock usage in Event.emit()
   with flow._execution_lock:
       flow._active_futures.add(future)  # Update tracking set

**Lock Purpose**:

* **Protect shared state**: The ``_active_futures`` set is shared across all threads
* **Thread-safe updates**: Ensure atomic add/remove operations
* **Very fast operations**: Set updates take < 0.1ms

**Lock Does NOT**:

* Block handler execution (handlers run in separate threads)
* Serialize routine execution (routines execute in parallel)
* Impact performance significantly (lock time << handler time)

**Time Comparison**:

* Lock operation: **0.1ms**
* Handler execution: **5000ms**
* **Lock time percentage: 0.002%** (negligible)

Waiting for Completion
^^^^^^^^^^^^^^^^^^^^^^^

Since ``emit()`` returns immediately without waiting for handlers, you must explicitly
wait for completion when needed:

.. code-block:: python

   flow = Flow(execution_strategy="concurrent")
   job_state = flow.execute("entry_routine")
   
   # emit() has returned, but handlers may still be running
   # Wait for all handlers to complete
   flow.wait_for_completion(timeout=10.0)
   
   # Now all handlers are guaranteed to be finished

**How ``wait_for_completion()`` Works**:

1. Checks the ``_active_futures`` set for incomplete tasks
2. Waits in a loop, periodically checking completion status
3. Returns when all futures are done (or timeout occurs)
4. Thread-safe: Uses locks to safely check the futures set

**Best Practice**:

Always call ``wait_for_completion()`` before accessing results or shutting down:

.. code-block:: python

   flow = Flow(execution_strategy="concurrent")
   try:
       job_state = flow.execute("entry_routine")
       flow.wait_for_completion(timeout=10.0)
       # Now safe to access results
   finally:
       flow.shutdown(wait=True)

Thread Model Summary
^^^^^^^^^^^^^^^^^^^^^

**Key Characteristics**:

1. **Non-blocking emit()**: Returns immediately after task submission (~1ms)
2. **Parallel handler execution**: All connected slots execute concurrently in separate threads
3. **Fast lock operations**: Metadata updates take < 0.1ms (negligible)
4. **True parallelism**: Multiple routines execute simultaneously, providing real performance benefits
5. **Explicit waiting**: Must call ``wait_for_completion()`` to wait for handlers

**Performance Benefits**:

* **Sequential mode**: Total time = sum(all_handler_times)
* **Concurrent mode**: Total time ≈ max(handler_times)
* **Speedup**: Up to N× for N independent routines (limited by thread pool size)

**When to Use Concurrent Mode**:

* I/O-bound operations (network requests, file I/O)
* Independent routines that can run in parallel
* High-throughput scenarios
* When performance is critical

**When to Use Sequential Mode**:

* Execution order matters
* Deterministic behavior is required
* Handlers share non-thread-safe state
* Easier debugging

Event Execution Order
~~~~~~~~~~~~~~~~~~~~~

When an event emits data, it may be connected to multiple slots. The execution
order of these slots depends on the execution strategy and whether downstream
routines emit further events.

Sequential Execution Mode (Depth-First)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In sequential execution mode (default), when an event emits:

1. **Connection Order**: Slots are processed in the order they were connected
   to the event (the order in ``event.connected_slots`` list)

2. **Synchronous Processing**: Each slot's ``receive()`` method is called
   synchronously and immediately

3. **Handler Execution**: The slot's handler is called immediately after data
   is merged (synchronously)

4. **Depth-First Behavior**: If a handler emits a new event, the downstream
   slots connected to that event are processed **immediately and completely**
   before continuing to the next sibling slot

**Key Behavior**:
    * Slots execute in connection order (first connected = first executed)
    * Each slot's handler completes fully before moving to the next slot
    * If a handler emits events, the entire downstream chain executes before
      returning to process the next sibling slot
    * This creates a **depth-first execution pattern**

**Example: Sequential Execution Order**

.. code-block:: python

   from routilux import Flow, Routine
   
   class SourceRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.output_event = self.define_event("output")
       
       def __call__(self, **kwargs):
           # Emit to 3 connected slots
           self.emit("output", data="test")
   
   class IntermediateRoutine(Routine):
       def __init__(self, name):
           super().__init__()
           self.name = name
           self.input_slot = self.define_slot("input", handler=self._handle)
           self.output_event = self.define_event("output")
       
       def _handle(self, data=None, **kwargs):
           print(f"{self.name} received data")
           # Emit to downstream
           self.emit("output", data="downstream")
   
   class LeafRoutine(Routine):
       def __init__(self, name):
           super().__init__()
           self.name = name
           self.input_slot = self.define_slot("input", handler=self._handle)
       
       def _handle(self, data=None, **kwargs):
           print(f"{self.name} received data")
   
   # Create flow
   flow = Flow()  # Sequential mode (default)
   
   source = SourceRoutine()
   intermediate1 = IntermediateRoutine("Intermediate1")
   intermediate2 = IntermediateRoutine("Intermediate2")
   leaf1 = LeafRoutine("Leaf1")
   leaf2 = LeafRoutine("Leaf2")
   leaf3 = LeafRoutine("Leaf3")
   
   flow.add_routine(source, "source")
   flow.add_routine(intermediate1, "intermediate1")
   flow.add_routine(intermediate2, "intermediate2")
   flow.add_routine(leaf1, "leaf1")
   flow.add_routine(leaf2, "leaf2")
   flow.add_routine(leaf3, "leaf3")
   
   # Connect: source -> intermediate1, intermediate2, leaf3
   flow.connect("source", "output", "intermediate1", "input")
   flow.connect("source", "output", "intermediate2", "input")
   flow.connect("source", "output", "leaf3", "input")
   
   # Connect intermediates to their leaves
   flow.connect("intermediate1", "output", "leaf1", "input")
   flow.connect("intermediate2", "output", "leaf2", "input")
   
   flow.execute("source")
   
   # Execution order (depth-first):
   # 1. source emits
   # 2. intermediate1 receives (first connected slot)
   # 3. intermediate1 emits -> leaf1 receives (complete chain before next sibling)
   # 4. intermediate2 receives (second connected slot)
   # 5. intermediate2 emits -> leaf2 receives
   # 6. leaf3 receives (third connected slot)

**Execution Flow Diagram**:

.. code-block:: text

   Source emits
   │
   ├─> Intermediate1 (1st slot)
   │   │
   │   └─> Leaf1 (downstream of Intermediate1)
   │       (entire chain completes)
   │
   ├─> Intermediate2 (2nd slot)
   │   │
   │   └─> Leaf2 (downstream of Intermediate2)
   │       (entire chain completes)
   │
   └─> Leaf3 (3rd slot)
       (executes last)

**Important Notes for Sequential Mode**:
* Execution is **deterministic** - same connection order = same execution order
* Downstream chains complete **before** moving to next sibling
* No parallelism - everything executes in a single thread
* Blocking operations in handlers will block the entire flow

Concurrent Execution Mode (Event Order)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In concurrent execution mode (``execution_strategy="concurrent"``), when an
event emits:

1. **Concurrent Submission**: All connected slots are submitted to a thread
   pool **immediately** (non-blocking)

2. **Parallel Execution**: Slots execute concurrently in separate threads

3. **No Order Guarantee**: Execution order is **not guaranteed** - slots may
   execute in any order

4. **Independent Execution**: Each slot's handler executes independently
   without waiting for siblings

5. **Downstream Concurrency**: If a handler emits events, those downstream
   slots also execute concurrently (not blocked by sibling slots)

**Key Behavior**:
* All sibling slots start executing concurrently (as soon as tasks are submitted)
* Downstream slots also execute concurrently (not blocked by siblings)
* Execution order is **non-deterministic** - may vary between runs
* Thread-safe operations are required if handlers share state

**Example: Concurrent Execution Order**

.. code-block:: python

   flow = Flow(execution_strategy="concurrent", max_workers=5)
   
   # Same setup as above
   # ...
   
   flow.execute("source")
   flow.wait_for_completion()  # Wait for all tasks to complete
   flow.shutdown()  # Clean up thread pool
   
   # Execution order (non-deterministic):
   # All slots may execute in any order:
   # - intermediate1, intermediate2, leaf3 may execute concurrently
   # - leaf1, leaf2 may execute concurrently with their parents or siblings
   # - No guarantee on order

**Important Notes for Concurrent Mode**:
* Execution order is **non-deterministic**
* All slots execute concurrently (siblings and downstream)
* Must call ``wait_for_completion()`` to ensure all tasks complete
* Must call ``shutdown()`` to clean up thread pool
* Use thread-safe operations for shared state
* Exception handling is per-thread (exceptions don't stop other threads)

Comparison: Sequential vs Concurrent
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

+------------------+------------------+------------------+
| Aspect           | Sequential       | Concurrent       |
+==================+==================+==================+
| Execution order  | Deterministic    | Non-deterministic|
|                  | (connection      | (may vary)       |
|                  | order)           |                  |
+------------------+------------------+------------------+
| Sibling slots    | Execute one by   | Execute          |
|                  | one              | concurrently     |
+------------------+------------------+------------------+
| Downstream slots | Complete before  | Execute          |
|                  | next sibling     | concurrently     |
+------------------+------------------+------------------+
| Threading        | Single thread    | Thread pool      |
+------------------+------------------+------------------+
| Blocking ops     | Blocks entire    | Blocks only      |
|                  | flow             | that thread      |
+------------------+------------------+------------------+
| State sharing    | Safe (single     | Requires thread  |
|                  | thread)          | safety           |
+------------------+------------------+------------------+
| Performance      | Slower (one at   | Faster (parallel)|
|                  | a time)          |                  |
+------------------+------------------+------------------+

Best Practices for Execution Strategy
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

1. **Use Sequential Mode** when:
   * Execution order matters
   * You need deterministic behavior
   * Handlers share non-thread-safe state
   * Debugging is easier with sequential execution

2. **Use Concurrent Mode** when:
   * Routines are independent and can run in parallel
   * Performance is critical
   * Handlers perform I/O operations (network, disk)
   * You need to handle high throughput

3. **Connection Order Matters** (in sequential mode):
   * Connect slots in the order you want them to execute
   * First connected = first executed
   * Use this to control execution order

4. **Thread Safety** (in concurrent mode):
   * Use locks for shared state
   * Avoid modifying shared objects without synchronization
   * Use thread-safe data structures when needed

5. **Wait for Completion** (in concurrent mode):
   * Always call ``wait_for_completion()`` before accessing results
   * Always call ``shutdown()`` to clean up resources

Example: Concurrent Data Fetching
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from routilux import Flow, Routine
   import time

   class DataFetcher(Routine):
       def __init__(self, source_name):
           super().__init__()
           self.source_name = source_name
           self.input_slot = self.define_slot("trigger", handler=self.fetch)
           self.output_event = self.define_event("data_ready", ["data"])
       
       def fetch(self, **kwargs):
           # Simulate network I/O
           time.sleep(0.2)
           self.emit("data_ready", data=f"Data from {self.source_name}")

   # Create concurrent flow
   flow = Flow(execution_strategy="concurrent", max_workers=5)
   
   # Create multiple fetchers
   fetcher1 = DataFetcher("API_1")
   fetcher2 = DataFetcher("API_2")
   fetcher3 = DataFetcher("Database")
   
   f1_id = flow.add_routine(fetcher1, "fetcher_1")
   f2_id = flow.add_routine(fetcher2, "fetcher_2")
   f3_id = flow.add_routine(fetcher3, "fetcher_3")
   
   # Connect to aggregator
   class Aggregator(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.define_slot("input", handler=self.aggregate, merge_strategy="append")
       
       def aggregate(self, data):
           print(f"Received: {data}")
   
   agg = Aggregator()
   agg_id = flow.add_routine(agg, "aggregator")
   
   # All fetchers connect to aggregator (will execute concurrently)
   flow.connect(f1_id, "data_ready", agg_id, "input")
   flow.connect(f2_id, "data_ready", agg_id, "input")
   flow.connect(f3_id, "data_ready", agg_id, "input")
   
   # Execute - all fetchers run in parallel
   job_state = flow.execute("fetcher_1")
   # Execution time: ~0.2s (concurrent) vs ~0.6s (sequential)

Performance Benefits
~~~~~~~~~~~~~~~~~~~~

Concurrent execution provides significant performance improvements for I/O-bound operations:

- **Sequential**: If 5 routines each take 0.2s, total time = 1.0s
- **Concurrent**: Same 5 routines execute in parallel, total time ≈ 0.2s

The actual speedup depends on:
- Number of parallel routines
- I/O wait time
- Thread pool size (max_workers)
- System resources

Thread Safety
~~~~~~~~~~~~~

All state updates in concurrent execution are thread-safe:
- Routine stats updates are protected
- JobState updates are synchronized
- Execution tracking is thread-safe

Error Handling in Concurrent Execution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Error handling works the same way in concurrent execution:

.. code-block:: python

   from routilux import ErrorHandler, ErrorStrategy
   
   flow = Flow(execution_strategy="concurrent")
   flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
   
   # Errors in one routine don't block others
   job_state = flow.execute("entry_routine")

See :doc:`error_handling` for more details on error handling strategies.

Waiting for Completion
~~~~~~~~~~~~~~~~~~~~~~

In concurrent execution mode, tasks run asynchronously. To wait for all tasks to complete, use ``wait_for_completion()``:

.. code-block:: python

   flow = Flow(execution_strategy="concurrent")
   job_state = flow.execute("entry_routine")
   
   # Wait for all concurrent tasks to complete
   flow.wait_for_completion(timeout=10.0)  # Optional timeout in seconds
   
   # Now all tasks are guaranteed to be finished
   print("All tasks completed!")

The ``wait_for_completion()`` method:
- Waits for all active concurrent tasks to finish
- Supports an optional timeout parameter
- Returns ``True`` if all tasks completed, ``False`` if timeout occurred
- Is thread-safe and automatically cleans up completed futures

Shutting Down Concurrent Flows
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When you're done with a concurrent flow, properly shut it down to clean up resources:

.. code-block:: python

   flow = Flow(execution_strategy="concurrent")
   
   try:
       job_state = flow.execute("entry_routine")
       flow.wait_for_completion(timeout=10.0)
   finally:
       # Always shut down to clean up the thread pool
       flow.shutdown(wait=True)

The ``shutdown()`` method:
- Waits for all tasks to complete (if ``wait=True``)
- Closes the thread pool executor
- Cleans up all resources
- Should be called when done with the flow

Best Practice: Always use ``try/finally`` to ensure proper cleanup:

.. code-block:: python

   flow = Flow(execution_strategy="concurrent")
   try:
       job_state = flow.execute("entry_routine")
       flow.wait_for_completion(timeout=10.0)
       # Process results...
   finally:
       flow.shutdown(wait=True)  # Ensures cleanup even if errors occur

Pausing Execution
-----------------

Pause execution at any point:

.. code-block:: python

   flow.pause(reason="User requested pause", checkpoint={"step": 1})

Resuming Execution
------------------

Resume from a paused state:

.. code-block:: python

   flow.resume(job_state)

Cancelling Execution
--------------------

Cancel execution:

.. code-block:: python

   flow.cancel(reason="User cancelled")

Error Handling
--------------

Set an error handler for the flow:

.. code-block:: python

   from routilux import ErrorHandler, ErrorStrategy

   error_handler = ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=3)
   flow.set_error_handler(error_handler)

See :doc:`error_handling` for more details.

