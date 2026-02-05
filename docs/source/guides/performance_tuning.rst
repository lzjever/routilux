Performance Tuning Guide
========================

This guide explains how to optimize Routilux workflow performance
for different workload types.

Understanding Execution Modes
------------------------------

Routilux supports two execution modes:

Sequential Mode
~~~~~~~~~~~~~~~
Executes routines one at a time in order.

- **Best for:** CPU-intensive tasks, simple workflows
- **Limitations:** No parallelism, slower for independent tasks
- **GIL Impact:** Minimal (single thread anyway)

Example::

    flow = Flow("my_flow", execution_mode="sequential")

Concurrent Mode
~~~~~~~~~~~~~~~
Executes routines using ThreadPoolExecutor.

- **Best for:** I/O-intensive tasks (network, disk, database)
- **Limitations:** Limited by Python GIL for CPU-bound work
- **GIL Impact:** Significant for CPU tasks, minimal for I/O tasks

Example::

    flow = Flow("my_flow", execution_mode="concurrent", max_workers=4)

GIL Limitations
---------------

Python's Global Interpreter Lock (GIL) means that **CPU-bound tasks
will not see significant speedup from concurrent execution**.

For CPU-intensive workflows, expect:
- **Sequential:** Baseline performance
- **Concurrent:** ~1.0-1.2x speedup (minimal improvement due to GIL)

For I/O-intensive workflows (network calls, file operations):
- **Sequential:** Limited by I/O wait time
- **Concurrent:** 2-4x speedup possible (I/O happens in parallel)

Performance Optimization Strategies
------------------------------------

1. Identify Your Bottleneck
   ~~~~~~~~~~~~~~~~~~~~~~~~~

   Use the execution tracker to measure routine execution times::

    from routilux import Flow

    flow = Flow("my_flow", execution_mode="concurrent")
    flow.execution_tracker = flow.ExecutionTracker(flow_id="my_flow")

    job_state = flow.execute("entry_routine", entry_params={})
    metrics = flow.execution_tracker.get_performance_metrics()

    # Find slow routines
    for routine_id, execs in tracker.routine_executions.items():
        avg_time = sum(e.get("execution_time", 0) for e in execs) / len(execs)
        print(f"{routine_id}: {avg_time:.3f}s average")

2. Choose the Right Execution Mode
   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

   - **I/O bound (network, database):** Use ``concurrent``
   - **CPU bound (data processing):** Use ``sequential``
   - **Mixed:** Split workflows by type

3. Tune Worker Count
   ~~~~~~~~~~~~~~~~~~

   For concurrent mode, set ``max_workers`` based on workload::

    # I/O bound: More workers help
    flow = Flow("my_flow", execution_mode="concurrent", max_workers=10)

    # CPU bound: Fewer workers (GIL limits benefit)
    flow = Flow("my_flow", execution_mode="concurrent", max_workers=2)

4. Optimize Routine Handlers
   ~~~~~~~~~~~~~~~~~~~~~~~~~~~

   - Use async libraries (requests, httpx) for I/O
   - Release GIL with NumPy/pandas for CPU work
   - Batch small operations

5. Memory Management
   ~~~~~~~~~~~~~~~~~~

   Configure history retention for long-running flows::

    flow.execute(
        "entry_routine",
        entry_params={},
        max_history_size=100,      # Reduce from default 1000
        history_ttl_seconds=300    # Reduce from default 3600
    )

Production Recommendations
---------------------------

For Production Deployments:

1. **Monitoring:** Always enable execution tracking
2. **History Limits:** Set appropriate retention based on flow duration
3. **Error Handling:** Use appropriate error strategies
4. **Testing:** Load test concurrent flows before production

Future Directions
-----------------

We are evaluating the following enhancements:

- **asyncio support:** For native async/await workflows
- **multiprocessing mode:** For CPU-bound parallelism
- **Distributed execution:** For cross-machine workflows

See `GitHub Issues <https://github.com/lzjever/routilux/issues>`_ for status.
