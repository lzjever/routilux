Runtime Execution Manager
========================

The Runtime class provides centralized execution management for workflows. It manages a thread pool and job registry, allowing you to execute multiple flows concurrently and manage their lifecycles.

.. note:: **New Architecture**

   Runtime replaces direct ``Flow.execute()`` calls. All execution now
   goes through Runtime, which manages thread pools and job tracking.

When to Use Runtime
--------------------

Use Runtime when:

* You need to execute multiple flows concurrently
* You want centralized job management across flows
* You need to track and manage running jobs
* You want to control thread pool resources globally

Basic Usage
------------

Creating a Runtime:

.. code-block:: python

   from routilux import Runtime

   # Create runtime with shared thread pool (recommended, default)
   runtime = Runtime(thread_pool_size=0)  # Uses GlobalJobManager's shared pool

   # Create runtime with independent thread pool
   runtime = Runtime(thread_pool_size=10)  # Has its own 10-thread pool

   # Use context manager for automatic cleanup
   with Runtime(thread_pool_size=0) as runtime:
       # Execute flows here
       pass

.. note:: **Thread Pool Size**

   **Recommended: thread_pool_size=0** (uses GlobalJobManager's shared pool)
   
   When ``thread_pool_size=0``, Runtime uses the GlobalJobManager's shared thread pool
   (100 threads by default). This is the recommended configuration for most scenarios
   as it provides better resource utilization and avoids thread pool fragmentation.
   
   See :ref:`thread-pool-sizing` for detailed guidance on choosing thread pool size.

Registering Flows
-----------------

Flows must be registered in FlowRegistry before execution:

.. code-block:: python

   from routilux import Flow, Routine
   from routilux.monitoring.flow_registry import FlowRegistry

   # Create flow
   flow = Flow(flow_id="my_flow")
   # ... add routines and connections ...

   # Register flow
   registry = FlowRegistry.get_instance()
   registry.register_by_name("my_flow", flow)

Executing Flows
---------------

Execute registered flows using Runtime:

.. code-block:: python

   # Execute flow by name
   job_state = runtime.exec("my_flow", entry_params={"data": "test"})

   # Execute with existing JobState (resume)
   saved_state = JobState.load("saved_state.json")
   job_state = runtime.exec("my_flow", job_state=saved_state)

   # Entry parameters are passed to entry routine's trigger slot
   job_state = runtime.exec("my_flow", entry_params={"key": "value"})

.. note:: **Non-Blocking Execution**

   ``runtime.exec()`` returns immediately with JobState in "running"
   status. Actual execution happens asynchronously in background threads.

   Use ``wait_until_all_jobs_finished()`` or ``job.wait()`` to wait
   for completion.

Job Management
--------------

Listing Jobs:

.. code-block:: python

   # List all jobs
   all_jobs = runtime.list_jobs()
   print(f"Total jobs: {len(all_jobs)}")

   # Filter by status
   running_jobs = runtime.list_jobs(status="running")
   completed_jobs = runtime.list_jobs(status="completed")
   failed_jobs = runtime.list_jobs(status="failed")

   # Filter by flow name
   flow_jobs = runtime.list_jobs(flow_name="my_flow")

Getting a Specific Job:

.. code-block:: python

   job = runtime.get_job(job_id)
   if job:
       print(f"Job ID: {job.job_id}")
       print(f"Status: {job.job_state.status}")
       print(f"Is running: {job.is_running()}")
       print(f"Is paused: {job.is_paused()}")

Waiting for Jobs
-----------------

.. code-block:: python

   # Wait for all jobs to finish
   runtime.wait_until_all_jobs_finished(timeout=30.0)

   # Wait for specific job
   job = runtime.get_job(job_id)
   job.wait(timeout=10.0)

   # Check if job completed
   if job.is_completed():
       print("Job completed successfully")

Cancelling Jobs
-----------------

.. code-block:: python

   job = runtime.get_job(job_id)
   job.cancel()

   # Or cancel all jobs
   runtime.cancel_all_jobs()

Resource Management
-----------------

Runtime can use either a shared thread pool or an independent thread pool:

.. code-block:: python

   # Option 1: Use shared thread pool (recommended)
   # All Runtime instances with thread_pool_size=0 share GlobalJobManager's pool
   runtime = Runtime(thread_pool_size=0)  # Uses shared pool (100 threads)

   # Option 2: Use independent thread pool
   # Each Runtime has its own thread pool
   runtime = Runtime(thread_pool_size=10)  # Has its own 10-thread pool

   # Execute multiple jobs concurrently
   job1 = runtime.exec("flow1")
   job2 = runtime.exec("flow2")
   job3 = runtime.exec("flow3")

   # All jobs use the same thread pool (shared or independent)
   runtime.wait_until_all_jobs_finished()

.. note:: **Shared vs Independent Thread Pools**

   * **thread_pool_size=0**: Uses GlobalJobManager's shared thread pool (100 threads).
     All Runtime instances with this setting share the same pool. Recommended for
     most scenarios.
   
   * **thread_pool_size>0**: Creates an independent thread pool for this Runtime.
     Useful when you need resource isolation between different Runtime instances.

.. warning:: **Runtime Shutdown**

   Always call ``shutdown()`` or use context manager to clean up thread
   pool:

   .. code-block:: python

      # ✅ CORRECT - Automatic cleanup
      with Runtime(thread_pool_size=10) as runtime:
          job_state = runtime.exec("my_flow")
          # Thread pool cleaned up automatically

      # ❌ WRONG - Manual cleanup needed
      runtime = Runtime(thread_pool_size=10)
      job_state = runtime.exec("my_flow")
      # Must call runtime.shutdown(wait=True) before exiting!

Common Pitfalls
----------------

.. warning:: **Not Registering Flows**

   Flows must be registered before execution:

   .. code-block:: python

      # ❌ WRONG - Flow not registered
      runtime = Runtime()
      flow = Flow(flow_id="my_flow")
      job_state = runtime.exec("my_flow")  # ValueError!

      # ✅ CORRECT - Register first
      registry = FlowRegistry.get_instance()
      registry.register_by_name("my_flow", flow)
      job_state = runtime.exec("my_flow")  # Works

.. warning:: **Ignoring Job State After exec()**

   ``exec()`` returns immediately. Job status is "running", not
   "completed":

   .. code-block:: python

      # ❌ WRONG - Assumes execution finished
      job_state = runtime.exec("my_flow")
      if job_state.status == "completed":  # Likely false!
          print("Done")

      # ✅ CORRECT - Wait for completion
      job_state = runtime.exec("my_flow")
      job_state = runtime.get_job(job_state.job_id)
      job.wait(timeout=10.0)
      if job_state.status == "completed":
          print("Done")

.. warning:: **Forgetting to Shutdown Runtime**

   Not shutting down Runtime leaves thread pool running:

   .. code-block:: python

      # ❌ WRONG - Thread leak
      runtime = Runtime()
      # Execute jobs...
      # Exit without cleanup

      # ✅ CORRECT - Proper cleanup
      with Runtime() as runtime:
          # Execute jobs...
          pass  # Automatic cleanup

Performance Considerations
-------------------------

Thread Pool Sizing
~~~~~~~~~~~~~~~~~~~~

.. _thread-pool-sizing:

Choose thread pool size based on workload:

.. list-table::
   :header-rows: 1
   :widths: 25, 50, 25

   * - Workload Type
     - Recommended Workers
     - Reason

   * - **Shared pool (recommended)**
     - **0 (uses GlobalJobManager's pool)**
     - **All Runtime instances share one pool (100 threads by default)**

   * - I/O-bound (API calls, DB queries)
     - 10-20 workers
     - Wait time dominates CPU

   * - CPU-bound (computation, encryption)
     - CPU count (or count - 1)
     - CPU time dominates

   * - Mixed workload
     - 5-10 workers
     - Balance CPU and I/O

   * - Memory-constrained
     - 3-5 workers
     - Limit memory usage

.. important:: **thread_pool_size=0 (Recommended)**

   When ``thread_pool_size=0``, Runtime does **not** create its own thread pool.
   Instead, it uses the **GlobalJobManager's shared thread pool** (100 threads by default).

   **Benefits:**
   
   * ✅ **Resource efficiency**: All Runtime instances share one thread pool
   * ✅ **No thread pool fragmentation**: Avoids creating multiple pools
   * ✅ **Unified management**: Thread pool managed by GlobalJobManager
   * ✅ **Recommended for most scenarios**: Default configuration

   **How it works:**
   
   .. code-block:: python
      
      # Runtime with shared thread pool (recommended)
      runtime = Runtime(thread_pool_size=0)  # Uses GlobalJobManager's pool
      
      # All Runtime instances with thread_pool_size=0 share the same pool
      runtime1 = Runtime(thread_pool_size=0)
      runtime2 = Runtime(thread_pool_size=0)
      # Both use GlobalJobManager.global_thread_pool (100 threads)
      
      # Runtime with independent thread pool
      runtime3 = Runtime(thread_pool_size=20)  # Has its own 20-thread pool
      runtime4 = Runtime(thread_pool_size=10)  # Has its own 10-thread pool

   **When to use thread_pool_size=0:**
   
   * Default configuration (recommended for most cases)
   * Multiple Runtime instances that can share resources
   * Simple deployments without resource isolation requirements
   * Resource-constrained environments

   **When to use thread_pool_size>0:**
   
   * Need resource isolation between different Runtime instances
   * Performance tuning for specific Runtime with dedicated threads
   * Multi-tenant scenarios requiring isolation
   * Testing environments with small thread pools

   **Default Runtime:**
   
   The default Runtime created by the system uses ``thread_pool_size=0``:
   
   .. code-block:: python
      
      from routilux.runtime import get_runtime_instance
      
      # Default runtime uses shared thread pool
      runtime = get_runtime_instance()  # thread_pool_size=0

Context Switching
~~~~~~~~~~~~~~~~

Each job has its own event loop thread, minimizing contention:

.. code-block:: python

   # Job1 and Job2 run in parallel with independent event loops
   # Each processes its own task queue
   job1 = runtime.exec("flow1")
   job2 = runtime.exec("flow2")

   # Independent execution reduces lock contention
   runtime.wait_until_all_jobs_finished()

Monitoring and Debugging
----------------------

Track job progress:

.. code-block:: python

   job = runtime.get_job(job_id)

   # Monitor status
   while job.is_running():
       print(f"Status: {job.job_state.status}")
       time.sleep(1.0)

   # Access execution history
   history = job.job_state.get_execution_history()
   print(f"Total records: {len(history)}")

Complete Example
----------------

.. code-block:: python

   from routilux import Flow, Routine
   from routilux.activation_policies import immediate_policy
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry

   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")
           self.output = self.add_event("output", ["result"])

           def logic(input_data, policy_message, job_state):
               if input_data:
                   result = f"Processed: {input_data[0]}"
                   self.emit("output", result=result)

           self.set_logic(logic)
           self.set_activation_policy(immediate_policy())

   # Create and register flow
   flow = Flow(flow_id="demo")
   routine = MyRoutine()
   flow.add_routine(routine, "routine")
   flow.connect("routine", "output", "routine", "input")

   registry = FlowRegistry.get_instance()
   registry.register_by_name("demo", flow)

   # Execute with Runtime
   with Runtime(thread_pool_size=5) as runtime:
       job_state = runtime.exec("demo", entry_params={"data": "test"})
       job_state = runtime.get_job(job_state.job_id)
       job.wait(timeout=10.0)

       print(f"Final status: {job_state.status}")

See Also
--------

* :doc:`routines` - Routine class documentation
* :doc:`flows` - Flow class documentation
* :doc:`job_state` - JobState and job management
* :doc:`../api_reference/runtime` - Runtime API reference
