Working with Flows
==================

Flows orchestrate multiple routines and manage their execution. This guide explains how to create and use flows.

Creating a Flow
---------------

Create a flow with an optional flow ID:

.. code-block:: python

   from flowforge import Flow

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

The execute method returns a ``JobState`` object that tracks the execution status.

Concurrent Execution
--------------------

FlowForge supports concurrent execution of routines using thread pools. This is especially useful for I/O-bound operations where multiple routines can execute in parallel.

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

Example: Concurrent Data Fetching
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from flowforge import Flow, Routine
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

   from flowforge import ErrorHandler, ErrorStrategy
   
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

   from flowforge import ErrorHandler, ErrorStrategy

   error_handler = ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=3)
   flow.set_error_handler(error_handler)

See :doc:`error_handling` for more details.

