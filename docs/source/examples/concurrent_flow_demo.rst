Concurrent Flow Demo
====================

This example demonstrates FlowForge's concurrent execution capabilities, showing how multiple routines can execute in parallel to improve performance.

Overview
--------

The demo simulates a real-world scenario where data needs to be fetched from multiple sources, processed, and aggregated. Using concurrent execution, all data fetching operations run in parallel, significantly reducing total execution time.

Key Features Demonstrated
-------------------------

* Concurrent execution strategy
* Multiple parallel routines
* Performance comparison (sequential vs concurrent)
* Thread-safe state management
* Error handling in concurrent execution
* Serialization of concurrent flows
* Dynamic strategy switching

Example Code
------------

.. literalinclude:: ../../../examples/concurrent_flow_demo.py
   :language: python
   :lines: 1-100
   :linenos:

Running the Example
-------------------

.. code-block:: bash

   python examples/concurrent_flow_demo.py

Expected Output
---------------

The demo will show:

1. **Concurrent Execution Test**: Demonstrates parallel execution of multiple data fetchers
2. **Performance Comparison**: Shows execution time difference between sequential and concurrent modes
3. **Error Handling**: Demonstrates error handling in concurrent scenarios
4. **Serialization**: Shows that concurrent flows can be serialized and deserialized
5. **Strategy Switching**: Demonstrates dynamic strategy changes

Performance Results
-------------------

Typical performance improvements:

* **Sequential Execution**: ~0.65-0.75 seconds for 3 parallel tasks
* **Concurrent Execution**: ~0.25-0.30 seconds for the same tasks
* **Speedup**: 2-3x faster with concurrent execution

The actual speedup depends on:
- Number of parallel routines
- I/O wait time
- System resources
- Thread pool size

Key Concepts
------------

Concurrent Execution Strategy
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a flow is created with ``execution_strategy="concurrent"``, routines that can run in parallel are automatically executed concurrently:

.. code-block:: python

   flow = Flow(
       execution_strategy="concurrent",
       max_workers=5
   )

Thread Pool Management
~~~~~~~~~~~~~~~~~~~~~~

The ``max_workers`` parameter controls the maximum number of concurrent threads:

.. code-block:: python

   flow = Flow(execution_strategy="concurrent", max_workers=10)

Thread Safety
~~~~~~~~~~~~~

All state updates are thread-safe:
- Routine stats are protected
- JobState updates are synchronized
- Execution tracking is safe

Error Handling
~~~~~~~~~~~~~~

Errors in concurrent execution are handled the same way as sequential execution:

.. code-block:: python

   flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
   # Errors in one routine don't block others

Serialization
~~~~~~~~~~~~~

Concurrent flows can be serialized and deserialized:

.. code-block:: python

   # Serialize
   data = flow.serialize()
   
   # Deserialize
   new_flow = Flow()
   new_flow.deserialize(data)
   # Execution strategy and max_workers are preserved

Waiting for Completion
~~~~~~~~~~~~~~~~~~~~~~

In concurrent execution, tasks run asynchronously. Use ``wait_for_completion()`` to wait for all tasks:

.. code-block:: python

   flow = Flow(execution_strategy="concurrent")
   job_state = flow.execute("entry_routine")
   
   # Wait for all concurrent tasks to complete
   flow.wait_for_completion(timeout=10.0)
   
   # Now all tasks are guaranteed to be finished

Resource Cleanup
~~~~~~~~~~~~~~~~

Always properly shut down concurrent flows to clean up resources:

.. code-block:: python

   flow = Flow(execution_strategy="concurrent")
   try:
       job_state = flow.execute("entry_routine")
       flow.wait_for_completion(timeout=10.0)
   finally:
       flow.shutdown(wait=True)  # Clean up thread pool

Use Cases
---------

Concurrent execution is ideal for:

* **Multiple API Calls**: Fetching data from multiple APIs simultaneously
* **Database Queries**: Running multiple independent queries in parallel
* **File Processing**: Processing multiple files concurrently
* **Network Operations**: Any I/O-bound operations that can run in parallel
* **Data Aggregation**: Collecting data from multiple sources simultaneously

Best Practices
--------------

1. **Choose Appropriate max_workers**: Too many threads can cause overhead
2. **Use for I/O-bound Operations**: Concurrent execution is most beneficial for I/O-bound tasks
3. **Handle Errors Properly**: Use appropriate error handling strategies
4. **Monitor Performance**: Use ExecutionTracker to monitor concurrent execution performance
5. **Test Both Strategies**: Compare sequential and concurrent performance for your use case
6. **Wait for Completion**: Always call ``wait_for_completion()`` after execution to ensure all tasks finish
7. **Clean Up Resources**: Always call ``shutdown()`` when done with a concurrent flow, preferably in a ``try/finally`` block

See Also
--------

* :doc:`../user_guide/flows` - Flow usage guide
* :doc:`../user_guide/error_handling` - Error handling strategies
* :doc:`../api_reference/flow` - Flow API reference

