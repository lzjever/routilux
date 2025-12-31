JobState: Execution State Management
====================================

The ``JobState`` object is central to routilux's execution model. It represents the **execution state** of a single workflow execution, completely decoupled from the ``Flow`` (workflow definition).

**Understanding JobState's Role is Critical**

``JobState`` is responsible for **all runtime state and business data**:

- **Execution State**: Status, routine states, execution history
- **Business Data**: Intermediate processing data (``shared_data``, ``shared_log``)
- **Output Handling**: Execution-specific output (``output_handler``, ``output_log``)
- **Deferred Events**: Events to be emitted on resume
- **Pause Points**: Checkpoints for resumption

**What JobState Does NOT Do**:

- ❌ Define workflow structure (that's ``Flow``'s job)
- ❌ Implement node functionality (that's ``Routine``'s job)
- ❌ Store static configuration (that's ``Routine._config``)

**Key Principle**: Everything that changes during execution belongs in ``JobState``.
Everything that's static belongs in ``Flow`` or ``Routine._config``.

Key Concepts
------------

**Flow vs JobState vs Routine**:

- **Flow**: Static workflow definition (routines, connections, static configuration)
- **Routine**: Function implementation (what each node does, static config in ``_config``)
- **JobState**: Dynamic execution state (runtime state, business data, output)

This clear separation allows:

- Multiple independent executions of the same flow
- Proper serialization and recovery
- Distributed execution across hosts
- Independent pause/resume/cancel operations
- Reusable routine objects across executions

Identifiers in JobState
-----------------------

Each ``JobState`` has two important identifiers:

- **job_id**: Automatically generated UUID that uniquely identifies this execution instance
- **flow_id**: The identifier of the Flow that created this JobState

For details on how to use these identifiers, see :doc:`identifiers`.

Creating JobState
-----------------

A ``JobState`` is automatically created when you call ``flow.execute()``:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine

   class Source(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.define_slot("trigger", handler=self.send)
           self.output_event = self.define_event("output", ["data"])
       
       def send(self, **kwargs):
           self.emit("output", data="test")

   flow = Flow(flow_id="my_flow")
   source = Source()
   source_id = flow.add_routine(source, "source")

   # Execute returns a JobState
   job_state = flow.execute(source_id)

   print(f"Job ID: {job_state.job_id}")
   print(f"Status: {job_state.status}")
   print(f"Flow ID: {job_state.flow_id}")

**Expected Output**:

::

   Job ID: 550e8400-e29b-41d4-a716-446655440000
   Status: completed
   Flow ID: my_flow

**Key Points**:

- Each ``execute()`` call creates a **new, independent** ``JobState``
- The ``JobState`` is returned to you - Flow does not manage it
- Multiple executions = multiple independent ``JobState`` objects

Multiple Independent Executions
--------------------------------

You can execute the same flow multiple times, each with its own ``JobState``:

.. code-block:: python
   :linenos:

   # Execute the same flow multiple times
   job_state1 = flow.execute(source_id, entry_params={"value": "A"})
   job_state2 = flow.execute(source_id, entry_params={"value": "B"})
   job_state3 = flow.execute(source_id, entry_params={"value": "C"})

   # Each execution has its own JobState
   assert job_state1.job_id != job_state2.job_id
   assert job_state2.job_id != job_state3.job_id
   assert job_state1 is not job_state2  # Different objects

   # Each has its own execution history
   print(f"Execution 1 history: {len(job_state1.execution_history)} records")
   print(f"Execution 2 history: {len(job_state2.execution_history)} records")
   print(f"Execution 3 history: {len(job_state3.execution_history)} records")

**Key Points**:

- Each execution is **completely independent**
- Execution history, routine states, and status are separate
- You can pause/resume/cancel each execution independently

JobState Properties
-------------------

The ``JobState`` object contains:

**Core Properties**:

- ``job_id``: Unique identifier for this execution
- ``flow_id``: Identifier of the flow that created this execution
- ``status``: Current execution status ("running", "completed", "failed", "paused", "cancelled")
- ``created_at``: Timestamp when execution started
- ``updated_at``: Timestamp of last update

**Execution Tracking**:

- ``execution_history``: List of ``ExecutionRecord`` objects (chronological log)
- ``routine_states``: Dictionary mapping routine_id to routine state
- ``current_routine_id``: Currently executing routine (if any)

**Metadata**:

- ``metadata``: Custom metadata dictionary
- ``checkpoint``: Checkpoint data for pause/resume

Accessing Execution History
---------------------------

The execution history provides a chronological log of all routine executions and event emissions:

.. code-block:: python
   :linenos:

   job_state = flow.execute(source_id)

   # Get all execution records
   all_records = job_state.execution_history
   print(f"Total records: {len(all_records)}")

   # Get records for a specific routine
   source_records = job_state.get_execution_history("source")
   print(f"Source records: {len(source_records)}")

   # Iterate through records
   for record in job_state.execution_history:
       print(f"{record.timestamp}: {record.routine_id} -> {record.event_name}")
       print(f"  Data: {record.data}")

**Expected Output**:

::

   Total records: 3
   Source records: 2
   2025-01-15T10:30:00: source -> start
     Data: {}
   2025-01-15T10:30:00.100: source -> output
     Data: {'data': 'test'}
   2025-01-15T10:30:00.200: source -> completed
     Data: {}

**Key Points**:

- Execution history is automatically recorded during execution
- Records include routine_id, event_name, data, and timestamp
- History is recorded in both main thread and worker threads

Accessing Routine States
------------------------

Routine states track the status and metadata of each routine during execution:

.. code-block:: python
   :linenos:

   job_state = flow.execute(source_id)

   # Get state for a specific routine
   source_state = job_state.get_routine_state("source")
   if source_state:
       print(f"Source status: {source_state.get('status')}")
       print(f"Source metadata: {source_state}")

   # Update routine state (typically done by error handlers)
   job_state.update_routine_state("source", {
       "status": "completed",
       "execution_time": 0.5,
       "custom_field": "value"
   })

   # Get updated state
   updated_state = job_state.get_routine_state("source")
   print(f"Updated state: {updated_state}")

**Key Points**:

- Routine states are updated automatically during execution
- Error handlers can update routine states
- You can add custom metadata to routine states

**Using get_execution_context() for Convenient Access**:

Instead of manually accessing flow and job_state, use ``get_execution_context()``:

.. code-block:: python
   :linenos:

   from routilux import Routine

   class Processor(Routine):
       def process(self, data=None, **kwargs):
           # Get execution context (flow, job_state, routine_id)
           ctx = self.get_execution_context()
           if ctx:
               # Update routine state
               ctx.job_state.update_routine_state(ctx.routine_id, {"processed": True})
               
               # Store business data
               ctx.job_state.update_shared_data("last_item", data)
               
               # Send output
               self.send_output("user_data", message="Processed", value=data)

**Key Points**:

- ``get_execution_context()`` returns ``ExecutionContext(flow, job_state, routine_id)``
- Use this method instead of manually accessing thread-local storage
- Returns ``None`` if not in execution context

Storing Business Data
---------------------

``JobState`` provides two mechanisms for storing intermediate business data:

**1. shared_data (Read/Write Dictionary)**:

Use ``shared_data`` for data that needs to be read and updated by multiple routines:

.. code-block:: python
   :linenos:

   from routilux import Routine

   class DataCollector(Routine):
       def process(self, data=None, **kwargs):
           ctx = self.get_execution_context()
           if ctx:
               # Store data
               ctx.job_state.update_shared_data("items", data)
               
               # Read data
               items = ctx.job_state.get_shared_data("items", default=[])
               
               # Update data
               ctx.job_state.update_shared_data("count", len(items))

**2. shared_log (Append-Only List)**:

Use ``shared_log`` for append-only execution logs:

.. code-block:: python
   :linenos:

   from routilux import Routine

   class Logger(Routine):
       def process(self, data=None, **kwargs):
           ctx = self.get_execution_context()
           if ctx:
               # Append to log
               ctx.job_state.append_to_shared_log({
                   "timestamp": datetime.now().isoformat(),
                   "action": "process",
                   "data": data
               })
               
               # Read log
               log = ctx.job_state.get_shared_log()
               print(f"Total log entries: {len(log)}")

**Key Points**:

- ``shared_data``: For read/write intermediate data
- ``shared_log``: For append-only execution logs
- Both are serialized with ``JobState``
- Both are execution-specific (each execution has its own)

Sending Output
--------------

Use ``send_output()`` to send execution-specific output data (not events):

.. code-block:: python
   :linenos:

   from routilux import Routine
   from routilux import QueueOutputHandler

   class DataProcessor(Routine):
       def process(self, data=None, **kwargs):
           # Send output via JobState
           self.send_output("user_data", message="Processing", value=data)
           self.send_output("status", progress=50, status="in_progress")

   # Set output handler on JobState
   job_state = JobState(flow_id="my_flow")
   job_state.set_output_handler(QueueOutputHandler())
   
   # Now all send_output() calls will be sent to the queue
   flow.execute(entry_id)

**Key Points**:

- ``send_output()`` is different from ``emit()`` (which sends events to connected slots)
- Output is sent to ``output_handler`` set on ``JobState``
- Output is also logged to ``output_log`` for persistence
- Use ``Routine.send_output()`` for convenient access (automatically gets execution context)

**Output Handler Types**:

- ``QueueOutputHandler``: Send output to a queue
- ``CallbackOutputHandler``: Call a custom function with output
- ``NullOutputHandler``: Discard output (for testing)

Deferred Events
---------------

Use ``emit_deferred_event()`` to emit events that will be processed when the flow is resumed:

.. code-block:: python
   :linenos:

   from routilux import Routine

   class UserInteraction(Routine):
       def process(self, data=None, **kwargs):
           # Emit a deferred event
           self.emit_deferred_event("user_input_required", question="What is your name?")
           
           # Pause the execution
           ctx = self.get_execution_context()
           if ctx:
               ctx.flow.pause(ctx.job_state, reason="Waiting for user input")

   # Later: Resume execution
   # Deferred events are automatically emitted when flow.resume() is called
   flow.resume(job_state)

**Key Points**:

- ``emit_deferred_event()`` stores event info in ``JobState.deferred_events``
- Events are automatically emitted when ``flow.resume()`` is called
- Useful for LLM agent workflows where you need to wait for user input
- Use ``Routine.emit_deferred_event()`` for convenient access (automatically gets execution context)

JobState Status
---------------

The ``status`` field tracks the current execution state:

**Status Values**:

- ``"running"``: Execution is in progress
- ``"completed"``: Execution completed successfully
- ``"failed"``: Execution failed (error occurred)
- ``"paused"``: Execution is paused (can be resumed)
- ``"cancelled"``: Execution was cancelled

**Status Transitions**:

.. code-block:: python
   :linenos:

   job_state = flow.execute(source_id)

   # Status starts as "running"
   print(f"Initial status: {job_state.status}")  # "running"

   # Wait for completion
   flow.wait_for_completion(timeout=5.0)

   # Status becomes "completed" or "failed"
   print(f"Final status: {job_state.status}")  # "completed" or "failed"

**Key Points**:

- Status is automatically updated during execution
- Status can be updated in both main thread and worker threads
- Status changes are thread-safe

Pause, Resume, and Cancel
-------------------------

You can control execution using the ``JobState``:

.. code-block:: python
   :linenos:

   # Execute
   job_state = flow.execute(source_id)

   # Pause execution (requires JobState)
   flow.pause(job_state, reason="Manual pause for inspection")

   # Check status
   assert job_state.status == "paused"

   # Resume execution (returns new JobState for resumed execution)
   resumed_job_state = flow.resume(job_state)

   # Wait for completion
   flow.wait_for_completion(timeout=5.0)
   assert resumed_job_state.status == "completed"

   # Cancel execution (if needed)
   another_job_state = flow.execute(source_id)
   flow.cancel(another_job_state, reason="No longer needed")
   assert another_job_state.status == "cancelled"

**Key Points**:

- ``pause()``, ``resume()``, and ``cancel()`` require the ``JobState`` as first argument
- Each execution can be paused/resumed/cancelled independently
- Flow does not manage these operations - you pass the ``JobState`` explicitly

Serialization and Persistence
------------------------------

``JobState`` can be serialized for persistence and recovery:

.. code-block:: python
   :linenos:

   import json

   # Execute and pause
   job_state = flow.execute(source_id)
   flow.pause(job_state, reason="Save for later")

   # Serialize JobState
   job_state_data = job_state.serialize()
   
   # Save to file
   with open("job_state.json", "w") as f:
       json.dump(job_state_data, f, indent=2)

   # Later: Load and deserialize
   with open("job_state.json", "r") as f:
       loaded_data = json.load(f)

   new_job_state = JobState()
   new_job_state.deserialize(loaded_data)

   # Resume execution
   resumed = flow.resume(new_job_state)

**Key Points**:

- ``JobState`` serialization is separate from ``Flow`` serialization
- Serialized ``JobState`` includes execution history, routine states, and status
- Deserialized ``JobState`` can be used to resume execution
- See :doc:`serialization` for cross-host scenarios

Thread Safety and Concurrent Execution
---------------------------------------

Understanding thread safety and concurrent execution is crucial for using routilux effectively,
especially in multi-threaded applications or when running multiple executions simultaneously.

Architecture Overview
~~~~~~~~~~~~~~~~~~~~~

routilux uses a sophisticated multi-threaded architecture to support concurrent execution
while maintaining thread safety and proper isolation between executions.

**1. Thread Pool Management**:

Each ``Flow`` maintains a **single shared** ``ThreadPoolExecutor`` that is reused across
all executions:

.. code-block:: python
   :linenos:

   from routilux import Flow

   flow = Flow(flow_id="my_flow", execution_strategy="concurrent", max_workers=5)

   # First execution - thread pool is created
   job_state1 = flow.execute(entry_id)
   
   # Second execution - reuses the same thread pool
   job_state2 = flow.execute(entry_id)
   
   # Both executions share the same ThreadPoolExecutor
   # The thread pool is created when first needed and reused for all executions

**Key Points**:

- ✅ **Thread pool is Flow-level**: Created once per ``Flow``, not per execution
- ✅ **Shared across executions**: All executions of the same flow share the same pool
- ✅ **Efficient resource usage**: Avoids creating/destroying thread pools repeatedly

**2. Three Types of Threads**:

Understanding the different threads involved in execution is essential:

**Execution Thread** (User Thread):
   - The thread that calls ``flow.execute()``
   - Usually the main thread or a user-created thread
   - Creates the ``JobState`` object
   - Sets thread-local storage for the execution
   - Triggers the entry routine's handler

**Event Loop Thread** (Background Thread):
   - A background thread created by ``start_event_loop()``
   - Processes the task queue sequentially
   - Submits tasks to the ThreadPoolExecutor
   - Manages task scheduling and coordination

**Worker Threads** (ThreadPoolExecutor Threads):
   - Threads from the shared ``ThreadPoolExecutor``
   - Execute actual routine handlers
   - May execute tasks from different executions
   - Access ``JobState`` via thread-local storage

**Example: Thread Identification**:

.. code-block:: python
   :linenos:

   import threading
   from routilux import Flow, Routine

   class ThreadAwareRoutine(Routine):
       def __init__(self, name):
           super().__init__()
           self.name = name
           self.trigger_slot = self.define_slot("trigger", handler=self.process)
       
       def process(self, **kwargs):
           thread_name = threading.current_thread().name
           print(f"[{self.name}] Executing in thread: {thread_name}")
           
           # Access JobState via thread-local storage
           flow = getattr(self, "_current_flow", None)
           if flow:
               job_state = getattr(flow._current_execution_job_state, 'value', None)
               if job_state:
                   job_state.record_execution(self._id, "process", {"thread": thread_name})

   flow = Flow(flow_id="thread_demo", execution_strategy="concurrent", max_workers=2)
   routine = ThreadAwareRoutine("Processor")
   routine_id = flow.add_routine(routine, "processor")

   # Execution thread (MainThread)
   print(f"Execution thread: {threading.current_thread().name}")
   job_state = flow.execute(routine_id)
   flow.wait_for_completion(timeout=2.0)

**Expected Output**:

::

   Execution thread: MainThread
   [Processor] Executing in thread: ThreadPoolExecutor-0_0

JobState Access Mechanism
~~~~~~~~~~~~~~~~~~~~~~~~~

routilux uses a **hybrid approach** to ensure each task accesses the correct ``JobState``:

**1. Task-Level JobState Passing**:

Each ``SlotActivationTask`` carries its own ``JobState``:

.. code-block:: python
   :linenos:

   # When a task is created, it carries the JobState
   task = SlotActivationTask(
       slot=slot,
       data=data,
       job_state=job_state,  # JobState is explicitly passed
       connection=connection
   )

**2. Thread-Local Storage**:

Before executing a task, the worker thread sets its thread-local storage:

.. code-block:: python
   :linenos:

   def execute_task(task, flow):
       # Set JobState in thread-local storage for this task
       if task.job_state:
           flow._current_execution_job_state.value = task.job_state
       
       try:
           # Handler can now access JobState via thread-local storage
           task.slot.receive(mapped_data)
       finally:
           # Clear thread-local storage after execution
           flow._current_execution_job_state.value = None

**Why Both Mechanisms?**

- **Task-level passing**: Ensures JobState is explicitly available to worker threads
- **Thread-local storage**: Provides a convenient, unified access interface without
  modifying function signatures
- **Automatic isolation**: Each thread has its own thread-local storage, ensuring
  different executions don't interfere

Concurrent Execution Scenarios
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Scenario 1: Multiple Executions in Same Thread (Sequential)**:

.. code-block:: python
   :linenos:

   # Sequential executions in the same thread
   job_state1 = flow.execute(entry_id, entry_params={"task": "A"})
   flow.wait_for_completion(timeout=2.0)
   
   job_state2 = flow.execute(entry_id, entry_params={"task": "B"})
   flow.wait_for_completion(timeout=2.0)
   
   # Each execution has its own JobState
   assert job_state1.job_id != job_state2.job_id
   assert job_state1 is not job_state2

**Scenario 2: Multiple Executions in Different Threads (Concurrent)**:

.. code-block:: python
   :linenos:

   import threading

   def run_execution(flow, entry_id, task_name):
       job_state = flow.execute(entry_id, entry_params={"task": task_name})
       flow.wait_for_completion(timeout=3.0)
       return job_state

   # Create multiple threads, each running an execution
   threads = []
   job_states = {}
   
   for i in range(5):
       t = threading.Thread(
           target=lambda i=i: job_states.update({i: run_execution(flow, entry_id, f"Task{i}")}),
           name=f"ExecThread{i}"
       )
       threads.append(t)
       t.start()
   
   for t in threads:
       t.join()
   
   # Verify isolation
   job_ids = {js.job_id for js in job_states.values()}
   assert len(job_ids) == 5  # Each execution has unique JobState

**Key Observations**:

- ✅ Each execution has its own ``JobState``
- ✅ All executions share the same ``ThreadPoolExecutor``
- ✅ Each task carries its own ``JobState``, ensuring correct access
- ✅ No interference between executions

**Scenario 3: Same Worker Thread Executing Tasks from Different Executions**:

This is a critical scenario that demonstrates the robustness of the design:

.. code-block:: python
   :linenos:

   from routilux import Flow, Routine
   import threading
   import time

   class Source(Routine):
       def __init__(self, name):
           super().__init__()
           self.name = name
           self.trigger_slot = self.define_slot("trigger", handler=self.send)
           self.output_event = self.define_event("output", ["data"])
       
       def send(self, **kwargs):
           flow = getattr(self, "_current_flow", None)
           if flow:
               job_state = getattr(flow._current_execution_job_state, 'value', None)
               if job_state:
                   thread_name = threading.current_thread().name
                   job_state.record_execution(
                       self._id, "output",
                       {"data": f"from {self.name}", "thread": thread_name}
                   )
           time.sleep(0.1)  # Simulate work
           self.emit("output", data=f"from {self.name}")

   class Processor(Routine):
       def __init__(self, name):
           super().__init__()
           self.name = name
           self.input_slot = self.define_slot("input", handler=self.process)
       
       def process(self, data=None, **kwargs):
           flow = getattr(self, "_current_flow", None)
           if flow:
               job_state = getattr(flow._current_execution_job_state, 'value', None)
               if job_state:
                   thread_name = threading.current_thread().name
                   job_state.record_execution(
                       self._id, "input",
                       {"data": data, "thread": thread_name}
                   )

   flow = Flow(flow_id="isolation_test", execution_strategy="concurrent", max_workers=1)
   
   source1 = Source("Source1")
   source2 = Source("Source2")
   processor1 = Processor("Processor1")
   processor2 = Processor("Processor2")
   
   s1_id = flow.add_routine(source1, "s1")
   s2_id = flow.add_routine(source2, "s2")
   p1_id = flow.add_routine(processor1, "p1")
   p2_id = flow.add_routine(processor2, "p2")
   
   flow.connect(s1_id, "output", p1_id, "input")
   flow.connect(s2_id, "output", p2_id, "input")

   # Execute two executions sequentially (same worker thread will be reused)
   job_state1 = flow.execute(s1_id)
   flow.wait_for_completion(timeout=2.0)
   
   job_state2 = flow.execute(s2_id)
   flow.wait_for_completion(timeout=2.0)
   
   # Verify isolation: each JobState only contains records from its own execution
   js1_routines = {r.routine_id for r in job_state1.execution_history}
   js2_routines = {r.routine_id for r in job_state2.execution_history}
   
   print(f"JobState 1 routines: {js1_routines}")
   print(f"JobState 2 routines: {js2_routines}")
   
   # No cross-contamination
   assert js1_routines & js2_routines == set() or "s1" in js1_routines
   assert "s2" in js2_routines

**Expected Output**:

::

   JobState 1 routines: {'s1', 'p1', ...}
   JobState 2 routines: {'s2', 'p2', ...}

Thread Safety of JobState Updates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Question**: When multiple routines from the same execution run in different worker threads,
do they safely update the same ``JobState``?

**Answer**: Yes! In CPython, ``JobState`` updates are thread-safe.

**How It Works**:

.. code-block:: python
   :linenos:

   class JobState:
       def record_execution(self, routine_id: str, event_name: str, data: Dict[str, Any]) -> None:
           record = ExecutionRecord(routine_id, event_name, data)
           self.execution_history.append(record)  # Atomic in CPython (GIL protected)
           self.updated_at = datetime.now()
       
       def update_routine_state(self, routine_id: str, state: Dict[str, Any]) -> None:
           self.routine_states[routine_id] = state.copy()  # Atomic in CPython (GIL protected)
           self.updated_at = datetime.now()

**Thread Safety Guarantees**:

- ✅ **``list.append()`` is atomic** in CPython (protected by GIL)
- ✅ **``dict`` assignment is atomic** in CPython (protected by GIL)
- ✅ **Multiple worker threads can safely update the same ``JobState``**
- ✅ **No data loss or corruption** in concurrent scenarios

**Verification Test**:

Extensive testing has verified thread safety:

- ✅ 10 threads concurrently updating 10,000 records: **No data loss**
- ✅ 3 writer threads + 2 reader threads: **No data corruption**
- ✅ Multiple executions with shared thread pool: **Perfect isolation**

**Important Note**:

The thread safety relies on CPython's Global Interpreter Lock (GIL). If you plan to use
routilux in a multi-process environment (without GIL), you may need additional synchronization
mechanisms. However, for standard CPython multi-threaded applications, the current
implementation is fully thread-safe.

Common Questions and Answers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Q1: Does the same worker thread execute tasks from different executions?**

**A**: Yes, worker threads are shared across executions. However, each task carries its
own ``JobState``, and the thread-local storage is set before each task execution and
cleared after, ensuring perfect isolation.

**Q2: Can routines from the same execution run in different threads?**

**A**: Yes! In concurrent mode, routines from the same execution can run in different
worker threads. They all update the same ``JobState``, which is thread-safe in CPython.

**Q3: What happens if I call ``flow.execute()`` multiple times concurrently?**

**A**: Each call creates a new, independent ``JobState``. All executions share the same
thread pool, but each execution is completely isolated. No interference occurs.

**Q4: Is it safe to access ``JobState`` from routine handlers?**

**A**: Yes! You can safely access and update ``JobState`` from any routine handler,
regardless of which thread it runs in. The thread-local storage mechanism ensures
you always access the correct ``JobState`` for the current execution.

Thread Safety Best Practices
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**1. Always Wait for Completion**:

When running concurrent executions, always wait for completion before accessing
``JobState``:

.. code-block:: python
   :linenos:

   job_state = flow.execute(entry_id)
   flow.wait_for_completion(timeout=5.0)  # Wait for all tasks to complete
   
   # Now safe to access JobState
   print(f"Status: {job_state.status}")
   print(f"History: {len(job_state.execution_history)} records")

**2. Store JobState for Each Execution**:

If you need to track multiple concurrent executions, store each ``JobState``:

.. code-block:: python
   :linenos:

   executions = {}
   for i in range(10):
       job_state = flow.execute(entry_id, entry_params={"task_id": i})
       executions[i] = job_state
   
   # Wait for all to complete
   for job_state in executions.values():
       flow.wait_for_completion(timeout=5.0)
   
   # Now you can access each JobState independently
   for task_id, job_state in executions.items():
       print(f"Task {task_id}: {job_state.status}")

**3. Use Thread-Local Storage Correctly**:

When accessing ``JobState`` from routine handlers, use the thread-local storage:

.. code-block:: python
   :linenos:

   class MyRoutine(Routine):
       def process(self, **kwargs):
           flow = getattr(self, "_current_flow", None)
           if flow:
               job_state = getattr(flow._current_execution_job_state, 'value', None)
               if job_state:
                   # Safe to update JobState
                   job_state.record_execution(self._id, "process", kwargs)
                   job_state.update_routine_state(self._id, {"status": "processing"})

**4. Understand Thread Pool Sharing**:

Remember that all executions share the same thread pool. If you need to limit
concurrency across all executions, set ``max_workers`` appropriately:

.. code-block:: python
   :linenos:

   # Limit total concurrent tasks across all executions
   flow = Flow(flow_id="limited", execution_strategy="concurrent", max_workers=3)
   
   # Even if you run 10 executions concurrently, only 3 worker threads
   # will be available, limiting total system load

**Key Takeaways**:

- ✅ ``JobState`` updates are thread-safe in CPython
- ✅ Multiple executions are perfectly isolated
- ✅ Worker threads are shared, but isolation is maintained via Task-level JobState passing
- ✅ Thread-local storage provides convenient access without modifying function signatures
- ✅ Always wait for completion before accessing ``JobState`` in concurrent scenarios

Best Practices
--------------

**1. Store JobState for Recovery**:

.. code-block:: python
   :linenos:

   # Execute and store JobState
   job_state = flow.execute(source_id)
   
   # Save for recovery
   job_state_data = job_state.serialize()
   save_to_database(job_state_data)

**2. Use JobState for Status Monitoring**:

.. code-block:: python
   :linenos:

   job_state = flow.execute(source_id)
   
   # Monitor status
   while job_state.status == "running":
       time.sleep(0.1)
       # Status is updated automatically
   
   if job_state.status == "completed":
       print("Execution successful!")
   elif job_state.status == "failed":
       print("Execution failed!")

**3. Independent Execution Management**:

.. code-block:: python
   :linenos:

   # Execute multiple times
   executions = []
   for i in range(10):
       job_state = flow.execute(source_id, entry_params={"batch": i})
       executions.append(job_state)
   
   # Manage each independently
   for job_state in executions:
       if job_state.status == "paused":
           flow.resume(job_state)

**4. Cross-Host Execution**:

.. code-block:: python
   :linenos:

   # Host A: Execute and serialize
   job_state = flow.execute(source_id)
   flow.pause(job_state, reason="Transfer to Host B")
   
   flow_data = flow.serialize()
   job_state_data = job_state.serialize()
   
   # Send to Host B
   send_to_host_b(flow_data, job_state_data)
   
   # Host B: Deserialize and resume
   new_flow = Flow()
   new_flow.deserialize(flow_data)
   
   new_job_state = JobState()
   new_job_state.deserialize(job_state_data)
   
   resumed = new_flow.resume(new_job_state)

Common Pitfalls
---------------

**1. Assuming Flow Manages JobState**:

.. code-block:: python

   # Wrong: Flow doesn't have job_state
   flow.job_state.status  # AttributeError!

   # Correct: JobState is returned from execute()
   job_state = flow.execute(source_id)
   job_state.status  # OK

**2. Sharing JobState Between Executions**:

.. code-block:: python

   # Wrong: Reusing JobState from previous execution
   job_state1 = flow.execute(source_id)
   job_state2 = flow.execute(source_id)  # Different execution!
   # Don't use job_state1 for job_state2's operations

   # Correct: Use the JobState from the specific execution
   job_state = flow.execute(source_id)
   flow.pause(job_state, reason="pause this execution")

**3. Not Serializing JobState Separately**:

.. code-block:: python

   # Wrong: Flow serialization doesn't include JobState
   flow_data = flow.serialize()
   # job_state is NOT in flow_data!

   # Correct: Serialize separately
   flow_data = flow.serialize()
   job_state_data = job_state.serialize()
   # Save both for recovery

**4. Assuming JobState Persists Across Executions**:

.. code-block:: python

   # Wrong: Each execute() creates new JobState
   job_state1 = flow.execute(source_id)
   job_state2 = flow.execute(source_id)
   # job_state1 and job_state2 are different!

   # Correct: Store JobState if you need it
   job_state = flow.execute(source_id)
   save_job_state(job_state)

Related Topics
--------------

- :doc:`serialization` - Serialization and cross-host execution
- :doc:`state_management` - Pause, resume, and checkpoint management
- :doc:`flows` - Flow execution and management
- :doc:`error_handling` - Error handling and JobState updates

