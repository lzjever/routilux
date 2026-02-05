Concurrency Guide
================

Understanding Routilux's concurrent execution model and its limitations.

How Concurrent Execution Works
-------------------------------

When you create a Flow with ``execution_mode="concurrent"``, Routilux
uses Python's :class:`concurrent.futures.ThreadPoolExecutor` to execute
routines in parallel.

The execution flow:

1. Flow builds dependency graph
2. Ready routines (dependencies satisfied) are submitted to thread pool
3. Each routine runs in a separate thread
4. Events are queued and dispatched to target routines
5. Process repeats until all routines complete

GIL Impact
----------

**Important:** Python's Global Interpreter Lock (GIL) means that only
one thread executes Python bytecode at a time.

This impacts:

* **CPU-bound tasks:** Minimal speedup (threads compete for GIL)
* **I/O-bound tasks:** Good speedup (threads release GIL during I/O)

Benchmark Results
~~~~~~~~~~~~~~~~~

Based on ``tests/benchmarks/test_concurrent_benchmark.py``:

- **Sequential:** 100 routines in ~5.0s
- **Concurrent (4 workers):** 100 routines in ~4.8s (~1.04x speedup)
- **I/O-bound:** Concurrent can achieve 2-3x speedup

When to Use Concurrent Mode
-----------------------------

**Use concurrent for:**

* Network API calls (requests, httpx)
* File I/O operations
* Database queries
* Waiting on external services

**Use sequential for:**

* Data processing (NumPy, pandas release GIL, so may still benefit)
* Computationally intensive tasks
* Simple workflows
* When order must be strictly preserved

Best Practices
--------------

1. **Profile First:** Measure before optimizing
2. **Test Both Modes:** Some workflows perform better sequentially
3. **Set Appropriate max_workers:** Usually 2-4x CPU core count for I/O
4. **Handle Errors:** Decide on error strategies for concurrent failures
5. **Monitor Memory:** More workers = more memory usage

Example
-------

::

    from routilux import Flow, Routine

    # I/O-bound workflow: good for concurrent
    flow = Flow(
        "data_pipeline",
        execution_mode="concurrent",
        max_workers=8  # More workers for I/O
    )

    fetcher = Routine("fetch")
    processor = Routine("process")
    saver = Routine("save")

    flow.add_routine(fetcher, processor, saver)

    # Configure for production
    job_state = flow.execute(
        "fetch",
        entry_params={"urls": [...]},
        max_history_size=500,      # Reasonable limit
        history_ttl_seconds=1800   # 30 minutes
    )
