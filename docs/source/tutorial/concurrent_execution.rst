Concurrent Execution with Runtime
==================================

In this tutorial, you'll learn how to execute independent routines in parallel
using Routilux's Runtime-based concurrent execution for better performance.

.. note:: **New Architecture**

   This tutorial uses the Runtime-based architecture. Concurrent execution is managed
   by Runtime's shared thread pool, not by Flow-level configuration.

Learning Objectives
-------------------

By the end of this tutorial, you'll be able to:

- Understand when to use concurrent execution
- Configure Runtime for concurrent execution
- Handle thread-safe operations with JobState
- Execute multiple jobs concurrently
- Build high-performance workflows

Step 1: Understanding Runtime Thread Pool
-----------------------------------------

Runtime uses a shared thread pool for all jobs, allowing concurrent execution:

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry
   import time

   class SlowIOOperation(Routine):
       """Simulates a slow I/O operation"""

       def __init__(self):
           super().__init__()
           self.set_config(name="Operation", delay=0.2)
           self.trigger = self.add_slot("trigger")
           self.output = self.add_event("output", ["result"])

           def operate(slot_data, policy_message, job_state):
               delay = self.get_config("delay", 0.2)
               name = self.get_config("name", "Operation")
               time.sleep(delay)  # Simulate I/O
               result = f"{name} completed"
               print(f"[{time.time():.2f}] {result}")
               self.emit("output", result=result)

           self.set_logic(operate)
           self.set_activation_policy(immediate_policy())

   # Create flow
   flow = Flow(flow_id="io_flow")
   op1 = SlowIOOperation()
   op1.set_config(name="Operation1", delay=0.2)
   op1_id = flow.add_routine(op1, "op1")

   # Register
   FlowRegistry.get_instance().register_by_name("io_flow", flow)

   # Execute with Runtime (thread_pool_size=1 for sequential)
   print("=== Sequential-like Execution ===")
   with Runtime(thread_pool_size=1) as runtime:
       start = time.time()
       job_state1 = runtime.exec("io_flow")
       job_state2 = runtime.exec("io_flow")
       job_state3 = runtime.exec("io_flow")
       runtime.wait_until_all_jobs_finished(timeout=5.0)
       elapsed = time.time() - start
       print(f"Time with pool_size=1: {elapsed:.2f}s")

**Expected Output**:

.. code-block:: text

   === Sequential-like Execution ===
   [1234567890.12] Operation completed
   [1234567890.32] Operation completed
   [1234567890.52] Operation completed
   Time with pool_size=1: 0.60s

**Key Points**:

- ``thread_pool_size`` controls how many workers can run in parallel
- With ``thread_pool_size=1``, jobs execute sequentially
- All jobs share the same thread pool
- Runtime manages job queuing and execution

Step 2: Enabling Concurrent Execution
-------------------------------------

Increase ``thread_pool_size`` to enable concurrent execution:

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry
   import time

   class SlowIOOperation(Routine):
       def __init__(self):
           super().__init__()
           self.set_config(name="Operation", delay=0.2)
           self.trigger = self.add_slot("trigger")
           self.output = self.add_event("output", ["result"])

           def operate(slot_data, policy_message, job_state):
               delay = self.get_config("delay", 0.2)
               name = self.get_config("name", "Operation")
               time.sleep(delay)
               result = f"{name} completed"
               print(f"[{time.time():.2f}] {result}")
               self.emit("output", result=result)

           self.set_logic(operate)
           self.set_activation_policy(immediate_policy())

   # Create flow
   flow = Flow(flow_id="concurrent_flow")
   op = SlowIOOperation()
   flow.add_routine(op, "op")

   # Register
   FlowRegistry.get_instance().register_by_name("concurrent_flow", flow)

   # Execute with Runtime (thread_pool_size=5 for concurrent)
   print("=== Concurrent Execution ===")
   with Runtime(thread_pool_size=5) as runtime:
       start = time.time()
       job_state1 = runtime.exec("concurrent_flow")
       job_state2 = runtime.exec("concurrent_flow")
       job_state3 = runtime.exec("concurrent_flow")
       runtime.wait_until_all_jobs_finished(timeout=5.0)
       elapsed = time.time() - start
       print(f"Time with pool_size=5: {elapsed:.2f}s")

**Expected Output**:

.. code-block:: text

   === Concurrent Execution ===
   [1234567890.12] Operation completed
   [1234567890.12] Operation completed
   [1234567890.12] Operation completed
   Time with pool_size=5: 0.22s

**Key Points**:

- Larger ``thread_pool_size`` enables concurrent job execution
- Jobs execute in parallel when workers are available
- Total time ≈ longest single job time (not sum of all)
- Use context manager for automatic cleanup

Step 3: Parallel Data Fetching
------------------------------

A common pattern is fetching data from multiple sources in parallel:

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry
   import time

   class DataFetcher(Routine):
       """Fetches data from an external source"""

       def __init__(self):
           super().__init__()
           self.set_config(source_name="Source", delay=0.1)
           self.trigger = self.add_slot("trigger")
           self.output = self.add_event("output", ["data", "source"])

           def fetch(slot_data, policy_message, job_state):
               delay = self.get_config("delay", 0.1)
               source_name = self.get_config("source_name", "Source")
               time.sleep(delay)  # Simulate network delay
               data = f"Data from {source_name}"
               print(f"[{time.time():.2f}] Fetched: {data}")
               self.emit("output", data=data, source=source_name)

           self.set_logic(fetch)
           self.set_activation_policy(immediate_policy())

   class ResultCollector(Routine):
       """Collects results from multiple fetchers"""

       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")

           def collect(slot_data, policy_message, job_state):
               input_list = slot_data.get("input", [])
               for item in input_list:
                   data = item.get("data", "")
                   source = item.get("source", "unknown")
                   print(f"Collected: {data} from {source}")

           self.set_logic(collect)
           self.set_activation_policy(immediate_policy())

   # Create flow
   flow = Flow(flow_id="fetch_flow")

   # Add collector (will receive from all fetchers)
   collector = ResultCollector()
   collector_id = flow.add_routine(collector, "collector")

   # Create and add fetchers
   for i in range(3):
       fetcher = DataFetcher()
       fetcher.set_config(source_name=f"Source{i}", delay=0.1)
       fetcher_id = flow.add_routine(fetcher, f"fetcher{i}")
       # Connect each fetcher to the same collector
       flow.connect(f"fetcher{i}", "output", "collector", "input")

   # Register
   FlowRegistry.get_instance().register_by_name("fetch_flow", flow)

   # Execute all fetchers concurrently
   print("Starting parallel data fetching...")
   with Runtime(thread_pool_size=5) as runtime:
       start = time.time()

       # Execute the flow multiple times (one for each fetcher trigger)
       # All executions run concurrently in the thread pool
       job_states = [
           runtime.exec("fetch_flow"),
           runtime.exec("fetch_flow"),
           runtime.exec("fetch_flow")
       ]

       runtime.wait_until_all_jobs_finished(timeout=5.0)
       elapsed = time.time() - start
       print(f"Total time: {elapsed:.2f}s")

**Expected Output**:

.. code-block:: text

   Starting parallel data fetching...
   [1234567890.12] Fetched: Data from Source0
   [1234567890.12] Fetched: Data from Source1
   [1234567890.12] Fetched: Data from Source2
   Collected: Data from Source0 from Source0
   Collected: Data from Source1 from Source1
   Collected: Data from Source2 from Source2
   Total time: 0.12s

**Key Points**:

- Multiple calls to ``runtime.exec()`` execute concurrently
- Thread pool size limits maximum parallelism
- Independent jobs complete in parallel
- Connections work within each job independently

Step 4: Thread Safety with JobState
-----------------------------------

When using concurrent execution, use JobState for thread-safe state management:

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux.activation_policies import immediate_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry

   class ThreadSafeCounter(Routine):
       """Thread-safe counter using JobState"""

       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")

           def increment(slot_data, policy_message, job_state):
               # Get current routine state from JobState (thread-safe)
               routine_id = job_state.current_routine_id
               state = job_state.get_routine_state(routine_id, {})
               count = state.get("count", 0)

               # Update state in JobState (thread-safe)
               new_count = count + 1
               job_state.update_routine_state(routine_id, {"count": new_count})

               print(f"Count: {new_count}")

           self.set_logic(increment)
           self.set_activation_policy(immediate_policy())

   class DataTrigger(Routine):
       """Triggers the counter"""

       def __init__(self):
           super().__init__()
           self.trigger = self.add_slot("trigger")
           self.output = self.add_event("output", ["data"])

           def trigger_counter(slot_data, policy_message, job_state):
               self.emit("output", data="trigger")

           self.set_logic(trigger_counter)
           self.set_activation_policy(immediate_policy())

   # Create flow
   flow = Flow(flow_id="counter_flow")
   counter = ThreadSafeCounter()
   trigger = DataTrigger()

   counter_id = flow.add_routine(counter, "counter")
   trigger_id = flow.add_routine(trigger, "trigger")
   flow.connect("trigger", "output", "counter", "input")

   # Register
   FlowRegistry.get_instance().register_by_name("counter_flow", flow)

   # Execute multiple times concurrently
   with Runtime(thread_pool_size=5) as runtime:
       job_states = [runtime.exec("counter_flow") for _ in range(5)]
       runtime.wait_until_all_jobs_finished(timeout=5.0)

       # Check final counter state (from last job)
       final_state = job_states[-1].get_routine_state("counter", {})
       print(f"Final count: {final_state.get('count', 0)}")

**Expected Output**:

.. code-block:: text

   Count: 1
   Count: 1
   Count: 1
   Count: 1
   Count: 1
   Final count: 1

**Key Points**:

- Each job has its own JobState (state isolation)
- JobState operations are thread-safe
- Counter increments are per-job, not shared across jobs
- Use ``job_state.shared_data`` for cross-job communication

.. warning:: **State Isolation**

   Each ``runtime.exec()`` call creates a new JobState. State is NOT shared
   across jobs by default. Use ``job_state.shared_data`` for sharing
   data between jobs if needed.

Step 5: Complete Example - Parallel API Calls
--------------------------------------------

Here's a complete example of parallel API calls with error handling:

.. code-block:: python
   :name: concurrent_execution_complete
   :linenos:

   from routilux import Routine, ErrorHandler, ErrorStrategy
   from routilux.activation_policies import immediate_policy
   from routilux import Flow
   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry
   import time
   import random

   class APICaller(Routine):
       """Simulates an API call"""

       def __init__(self):
           super().__init__()
           self.set_config(api_name="API", delay=0.1)
           self.trigger = self.add_slot("trigger")
           self.output = self.add_event("output", ["response", "api_name"])

           def call_api(slot_data, policy_message, job_state):
               delay = self.get_config("delay", 0.1)
               api_name = self.get_config("api_name", "API")
               time.sleep(delay)  # Simulate network delay

               # Simulate occasional failures
               if random.random() < 0.1:  # 10% failure rate
                   raise Exception(f"{api_name} temporarily unavailable")

               response = f"Response from {api_name}"
               print(f"[{time.time():.2f}] {response}")
               self.emit("output", response=response, api_name=api_name)

           self.set_logic(call_api)
           self.set_activation_policy(immediate_policy())

       def get_error_handler(self):
           return ErrorHandler(strategy=ErrorStrategy.CONTINUE)

   class ResponseAggregator(Routine):
       """Aggregates API responses"""

       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")

           def aggregate(slot_data, policy_message, job_state):
               input_list = slot_data.get("input", [])
               for item in input_list:
                   response = item.get("response", "")
                   api_name = item.get("api_name", "unknown")

                   # Store in JobState
                   job_state.shared_log.append({
                       "api": api_name,
                       "response": response,
                       "timestamp": time.time()
                   })

                   print(f"Aggregated: {response} from {api_name}")

           self.set_logic(aggregate)
           self.set_activation_policy(immediate_policy())

   def main():
       # Create flow
       flow = Flow(flow_id="api_flow")

       # Set error handler at flow level
       flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))

       # Add aggregator
       aggregator = ResponseAggregator()
       aggregator_id = flow.add_routine(aggregator, "aggregator")

       # Create and add API callers
       api_names = ["UsersAPI", "OrdersAPI", "ProductsAPI", "InventoryAPI", "AnalyticsAPI"]
       for api_name in api_names:
           caller = APICaller()
           caller.set_config(api_name=api_name, delay=random.uniform(0.05, 0.15))
           caller_id = flow.add_routine(caller, api_name)
           flow.connect(api_name, "output", "aggregator", "input")

       # Register
       FlowRegistry.get_instance().register_by_name("api_flow", flow)

       # Execute all API calls concurrently
       print("Starting parallel API calls...")
       with Runtime(thread_pool_size=10) as runtime:
           start = time.time()

           # Execute multiple jobs (one for each API)
           job_states = [runtime.exec("api_flow") for _ in range(len(api_names))]

           runtime.wait_until_all_jobs_finished(timeout=10.0)
           elapsed = time.time() - start

           print(f"\nCompleted in {elapsed:.2f}s")

           # Check shared log from any job state
           print(f"Total responses: {len(job_states[0].shared_log)}")

   if __name__ == "__main__":
       main()

**Expected Output**:

.. code-block:: text

   Starting parallel API calls...
   [1234567890.12] Response from UsersAPI
   [1234567890.13] Response from OrdersAPI
   [1234567890.13] Response from ProductsAPI
   [1234567890.14] Response from InventoryAPI
   [1234567890.15] Response from AnalyticsAPI
   Aggregated: Response from UsersAPI from UsersAPI
   Aggregated: Response from OrdersAPI from OrdersAPI
   Aggregated: Response from ProductsAPI from ProductsAPI
   Aggregated: Response from InventoryAPI from InventoryAPI
   Aggregated: Response from AnalyticsAPI from AnalyticsAPI

   Completed in 0.18s
   Total responses: 5

**Key Points**:

- Multiple ``runtime.exec()`` calls execute concurrently
- Thread pool size controls parallelism
- Error handlers prevent one failure from stopping all jobs
- Use ``job_state.shared_log`` for collecting results

Common Pitfalls
---------------

**Pitfall 1: Not Waiting for Completion**

.. code-block:: python
   :emphasize-lines: 4

   job_state = runtime.exec("my_flow")
   print(f"Status: {job_state.status}")  # Likely "running"!
   # Missing: runtime.wait_until_all_jobs_finished()

**Solution**: Always wait for completion before checking status.

**Pitfall 2: Not Using Context Manager**

.. code-block:: python
   :emphasize-lines: 5

   runtime = Runtime(thread_pool_size=10)
   job_state = runtime.exec("my_flow")
   # Missing: runtime.shutdown(wait=True)
   # Thread pool leak!

**Solution**: Use ``with Runtime() as runtime:`` for automatic cleanup.

**Pitfall 3: Thread Pool Size Too Large**

.. code-block:: python
   :emphasize-lines: 2

   # Too many workers can cause resource exhaustion
   runtime = Runtime(thread_pool_size=1000)  # Excessive!

**Solution**: Choose thread pool size based on workload:
- I/O-bound: 10-20 workers
- CPU-bound: CPU count (or count - 1)
- Mixed: 5-10 workers

**Pitfall 4: Modifying Instance Variables**

.. code-block:: python
   :emphasize-lines: 6

   class BadRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.counter = 0  # Instance variable

       def process(self, slot_data, policy_message, job_state):
           self.counter += 1  # Data race in concurrent execution!

**Solution**: Always use JobState for execution state:

.. code-block:: python

   class GoodRoutine(Routine):
       def process(self, slot_data, policy_message, job_state):
           state = job_state.get_routine_state("my_routine", {})
           counter = state.get("count", 0)
           job_state.update_routine_state("my_routine", {"count": counter + 1})

Best Practices
--------------

1. **Use Runtime for all execution**: Never call ``Flow.execute()`` directly
2. **Set appropriate thread_pool_size**: Match your workload type
3. **Always use context manager**: ``with Runtime() as runtime:``
4. **Always wait for completion**: ``wait_until_all_jobs_finished()``
5. **Use JobState for state**: Never modify instance variables during execution
6. **Handle errors**: Set appropriate error handlers
7. **Register flows first**: Always register with FlowRegistry before execution

Performance Guidelines
----------------------

**Thread Pool Sizing**:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Workload Type
     - Recommended thread_pool_size
   * - I/O-bound (API calls, DB)
     - 10-20 workers
   * - CPU-bound (computation)
     - CPU count (or count - 1)
   * - Mixed workload
     - 5-10 workers
   * - Memory-constrained
     - 3-5 workers

**When to Use Concurrent Execution**:

- Multiple independent API calls
- Parallel data fetching
- Concurrent file processing
- Multiple database queries
- Any I/O-bound operations

**When NOT to Use**:

- CPU-intensive computation (Python GIL limits benefit)
- Strictly sequential dependencies
- Very small tasks (thread overhead > benefit)

Next Steps
----------

Now that you understand concurrent execution, let's move on to :doc:`advanced_patterns`
to learn about aggregation patterns, conditional routing, and other advanced features.
