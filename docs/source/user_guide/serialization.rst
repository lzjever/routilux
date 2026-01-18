Serialization
=============

routilux provides full serialization support for persistence and state recovery.

Serializing Objects
-------------------

All core classes support serialization:

.. code-block:: python

   # Serialize a flow
   data = flow.serialize()
   
   # Serialize a routine
   data = routine.serialize()
   
   # Serialize a job state
   data = job_state.serialize()

   # Serialize an error handler
   data = error_handler.serialize()

Deserializing Objects
---------------------

Deserialize objects:

.. code-block:: python

   # Deserialize a flow
   flow = Flow()
   flow.deserialize(data)
   
   # Deserialize a routine
   routine = Routine()
   routine.deserialize(data)
   
   # Deserialize a job state
   job_state = JobState()
   job_state.deserialize(data)
   
   # Deserialize an error handler
   error_handler = ErrorHandler()
   error_handler.deserialize(data)

Saving to JSON
--------------

Save serialized data to JSON:

.. code-block:: python

   import json
   
   data = flow.serialize()
   with open("flow.json", "w") as f:
       json.dump(data, f, indent=2)

Loading from JSON
-----------------

Load from JSON:

.. code-block:: python

   import json
   
   with open("flow.json", "r") as f:
       data = json.load(f)
   
   flow = Flow()
   flow.deserialize(data)

Serializable Fields
-------------------

Classes register fields for serialization:

.. code-block:: python

   self.add_serializable_fields(["field1", "field2", "field3"])

Only registered fields are serialized. Complex objects (lists, dicts, other Serializable objects) are automatically handled.

Serialization Validation
-------------------------

Before serializing a Flow, the system automatically validates that all
Serializable objects (routines, connections, slots, events, etc.) can be
constructed without arguments. This ensures that deserialization will succeed.

**Why This Matters**:

When deserializing, the system needs to create new instances of all Serializable
objects. It does this by calling ``Class()`` with no arguments. If a class
requires constructor parameters, deserialization will fail.

**Automatic Validation**:

When you call ``flow.serialize()``, the system:

1. Recursively traverses all Serializable objects in the Flow
2. Checks that each object's class can be instantiated without arguments
3. Raises a clear error if any object fails validation

**Example Error**:

.. code-block:: python

   # ❌ This will fail during serialization
   class BadRoutine(Routine):
       def __init__(self, required_param):
           super().__init__()
           self.param = required_param
   
   flow = Flow()
   routine = BadRoutine("value")  # This works
   flow.add_routine(routine, "bad_routine")
   
   # This will raise TypeError with clear error message
   data = flow.serialize()
   # TypeError: Routine 'bad_routine' (BadRoutine) cannot be serialized:
   # BadRoutine cannot be deserialized because its __init__ method requires
   # parameters: required_param
   # Serializable classes must support initialization with no arguments.
   # For Routine subclasses, use _config dictionary instead of constructor parameters.

**Correct Pattern**:

.. code-block:: python

   # ✅ Correct: Use _config dictionary
   class GoodRoutine(Routine):
       def __init__(self):
           super().__init__()
           # Configuration is set after creation
       
       def configure(self, param1, param2):
           self.set_config(param1=param1, param2=param2)
   
   flow = Flow()
   routine = GoodRoutine()
   routine.configure(param1="value1", param2="value2")
   flow.add_routine(routine, "good_routine")
   
   # This will succeed
   data = flow.serialize()

**What Gets Validated**:

* All routines in the Flow
* All connections
* All slots and events within routines
* All nested Serializable objects
* Error handlers, job states, and other Serializable fields

**Error Messages**:

The validation provides detailed error messages that include:

* Which object failed (routine ID, connection index, field name, etc.)
* Which class has the problem
* What parameters are required
* How to fix the issue

This allows you to catch serialization issues early, before attempting to
save or transfer the Flow.

Constructor Requirements
-------------------------

**Critical Rule**: All Serializable classes (including Routine subclasses)
must support initialization with no arguments.

**For Routine Subclasses**:

* ❌ **Don't**: Accept constructor parameters
* ✅ **Do**: Use ``_config`` dictionary for configuration

**Example**:

.. code-block:: python

   # ❌ Wrong: Constructor with parameters
   class MyRoutine(Routine):
       def __init__(self, max_items: int, timeout: float):
           super().__init__()
           self.max_items = max_items
           self.timeout = timeout
   
   # ✅ Correct: No constructor parameters, use _config
   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           # Configuration is set after creation
       
       def setup(self, max_items: int, timeout: float):
           self.set_config(max_items=max_items, timeout=timeout)
   
   # Usage
   routine = MyRoutine()
   routine.setup(max_items=10, timeout=5.0)
   flow.add_routine(routine, "my_routine")

**Why This Constraint Exists**:

During deserialization, the system needs to:

1. Load the class from the registry
2. Create an instance: ``routine = RoutineClass()``
3. Restore state: ``routine.deserialize(data)``

If the class requires constructor parameters, step 2 will fail because the
system doesn't know what values to pass.

**Validation Timing**:

* **At Class Definition**: The ``@register_serializable`` decorator checks
  the class definition when it's first loaded
* **At Serialization**: ``flow.serialize()`` validates all objects in the
  Flow before serialization, providing early error detection

This two-stage validation ensures that:

1. Classes are correctly defined from the start
2. Runtime issues are caught before serialization

Special Handling
----------------

Some classes have special serialization behavior:

* **ErrorHandler**: The ``ErrorStrategy`` enum is automatically converted to/from strings during serialization/deserialization.

Handler Method Validation
--------------------------

When serializing slot handlers and merge strategies, the system validates that
methods belong to the routine being serialized. This ensures cross-process
serialization safety.

**Why This Matters**:

When serialized data is transferred to another process (e.g., for distributed
execution), only methods of the serialized routine itself can be properly
restored. Methods from other routines cannot be deserialized because their
object instances don't exist in the new process.

**Validation Rules**:

* ✅ **Allowed**: Methods of the routine being serialized
* ✅ **Allowed**: Module-level functions (can be imported in any process)
* ✅ **Allowed**: Builtin functions
* ❌ **Not Allowed**: Methods from other routine instances

**Example - Correct Usage**:

.. code-block:: python

   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           # ✅ Correct: Use method from this routine
           self.input_slot = self.add_slot("input", handler=self.process_data)
       
       def process_data(self, data):
           return {"processed": data}

**Example - Incorrect Usage**:

.. code-block:: python

   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           other_routine = OtherRoutine()
           # ❌ Wrong: Using method from another routine
           # This will raise ValueError during serialization
           self.input_slot = self.add_slot("input", handler=other_routine.process)

**Error Message**:

If you try to serialize a method from another routine, you'll get a clear error:

.. code-block:: python

   ValueError: Cannot serialize method 'process' from OtherRoutine[other_id]. 
   Only methods of the serialized object itself (MyRoutine[my_id]) 
   can be serialized for cross-process execution.

**What Gets Validated**:

* Slot handlers (in ``Routine.add_slot()``)
* Merge strategies (if they are callable methods)
* Conditional router conditions (if they are callable methods)

**Note**: Functions (not methods) are always allowed because they can be
imported by module name in any process.

Flow and JobState Separation
------------------------------

**Critical Design Principle**: Flow and JobState are **completely decoupled**.

- **Flow**: Contains only the workflow definition (routines, connections, configuration)
- **JobState**: Contains execution state (execution history, routine states, status)

**Why This Matters**:

- Flow serialization does **NOT** include execution state
- JobState must be serialized **separately** for recovery
- This allows multiple independent executions of the same flow
- Enables proper cross-host execution and recovery

**Serialization Pattern**:

.. code-block:: python

   # Serialize Flow (workflow definition only)
   flow_data = flow.serialize()
   # flow_data does NOT contain job_state
   
   # Serialize JobState separately (execution state)
   job_state_data = job_state.serialize()
   
   # Save both for recovery
   save_flow(flow_data)
   save_job_state(job_state_data)

**Deserialization Pattern**:

.. code-block:: python

   # Deserialize Flow
   new_flow = Flow()
   new_flow.deserialize(flow_data)
   
   # Deserialize JobState separately
   new_job_state = JobState()
   new_job_state.deserialize(job_state_data)
   
   # Resume execution
   resumed = new_flow.resume(new_job_state)

Cross-Host Serialization and Execution
---------------------------------------

routilux supports transferring workflows and execution state across different hosts
for distributed execution and recovery.

**Use Cases**:

- **Distributed Execution**: Execute workflow on one host, transfer to another
- **Recovery**: Resume execution on a different host after failure
- **Load Balancing**: Move execution to a less loaded host
- **Persistence**: Save execution state for later recovery

**Complete Example: Cross-Host Execution**:

.. code-block:: python
   :linenos:

   # ============================================
   # Host A: Execute and Prepare for Transfer
   # ============================================
   
   from routilux import Flow, Routine, JobState
   from serilux import register_serializable
   import json
   
   @register_serializable
   class DataSource(Routine):
       def __init__(self):
           super().__init__()
           self.trigger_slot = self.add_slot("trigger", handler=self.send)
           self.output_event = self.add_event("output", ["data"])
       
       def send(self, **kwargs):
           self.emit("output", data="initial_data")
   
   @register_serializable
   class DataProcessor(Routine):
       def __init__(self):
           super().__init__()
           self.input_slot = self.add_slot("input", handler=self.process)
           self.output_event = self.add_event("output", ["result"])
       
       def process(self, data=None, **kwargs):
           result = f"Processed: {data}"
           self.emit("output", result=result)
   
   # Create flow on Host A
   flow = Flow(flow_id="cross_host_flow")
   source = DataSource()
   processor = DataProcessor()
   source_id = flow.add_routine(source, "source")
   processor_id = flow.add_routine(processor, "processor")
   flow.connect(source_id, "output", processor_id, "input")
   
   # Execute and pause (simulating transfer point)
   job_state = flow.execute(source_id)
   flow.pause(job_state, reason="Transfer to Host B")
   
   # Serialize both Flow and JobState
   flow_data = flow.serialize()
   job_state_data = job_state.serialize()
   
   # Prepare for transfer (JSON format)
   transfer_data = {
       "flow": flow_data,
       "job_state": job_state_data
   }
   
   # Save to file (or send over network)
   with open("transfer.json", "w") as f:
       json.dump(transfer_data, f, indent=2)
   
   print("✅ Host A: Flow and JobState serialized and ready for transfer")
   
   # ============================================
   # Host B: Receive and Resume Execution
   # ============================================
   
   # Load from file (or receive from network)
   with open("transfer.json", "r") as f:
       transfer_data = json.load(f)
   
   # Deserialize Flow
   new_flow = Flow()
   new_flow.deserialize(transfer_data["flow"])
   
   # Deserialize JobState
   new_job_state = JobState()
   new_job_state.deserialize(transfer_data["job_state"])
   
   # Verify deserialization
   assert new_flow.flow_id == flow.flow_id
   assert new_job_state.job_id == job_state.job_id
   assert new_job_state.status == "paused"
   
   # Resume execution on Host B
   resumed_job_state = new_flow.resume(new_job_state)
   
   # Wait for completion
   from routilux.job_state import JobState
   JobState.wait_for_completion(new_flow, resumed_job_state, timeout=10.0)
   
   print(f"✅ Host B: Execution resumed and completed")
   print(f"   Final status: {resumed_job_state.status}")
   print(f"   Execution history: {len(resumed_job_state.execution_history)} records")

**Expected Output**:

::

   ✅ Host A: Flow and JobState serialized and ready for transfer
   ✅ Host B: Execution resumed and completed
      Final status: completed
      Execution history: 4 records

**Key Points**:

1. **Flow and JobState are serialized separately** - This is required
2. **Both must be transferred** - Flow (definition) + JobState (execution state)
3. **Routines must be registered** - Use ``@register_serializable`` decorator
4. **Deserialization order matters** - Deserialize Flow first, then JobState
5. **Resume uses deserialized JobState** - Pass the deserialized JobState to ``resume()``

**Network Transfer Example**:

.. code-block:: python
   :linenos:

   import socket
   import json
   import pickle
   
   # Host A: Send
   def send_to_host_b(flow_data, job_state_data, host_b_address):
       transfer_data = {
           "flow": flow_data,
           "job_state": job_state_data
       }
       
       # Serialize to JSON
       json_data = json.dumps(transfer_data)
       
       # Send over network
       sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
       sock.connect(host_b_address)
       sock.sendall(json_data.encode())
       sock.close()
   
   # Host B: Receive
   def receive_from_host_a(port):
       sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
       sock.bind(("", port))
       sock.listen(1)
       conn, addr = sock.accept()
       
       # Receive data
       data = b""
       while True:
           chunk = conn.recv(4096)
           if not chunk:
               break
           data += chunk
       
       conn.close()
       sock.close()
       
       # Deserialize
       transfer_data = json.loads(data.decode())
       return transfer_data["flow"], transfer_data["job_state"]

**Database Storage Example**:

.. code-block:: python
   :linenos:

   import sqlite3
   import json
   
   # Host A: Save to database
   def save_execution_to_db(flow_data, job_state_data, execution_id):
       conn = sqlite3.connect("executions.db")
       cursor = conn.cursor()
       
       cursor.execute("""
           CREATE TABLE IF NOT EXISTS executions (
               execution_id TEXT PRIMARY KEY,
               flow_data TEXT,
               job_state_data TEXT,
               created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
           )
       """)
       
       cursor.execute("""
           INSERT INTO executions (execution_id, flow_data, job_state_data)
           VALUES (?, ?, ?)
       """, (execution_id, json.dumps(flow_data), json.dumps(job_state_data)))
       
       conn.commit()
       conn.close()
   
   # Host B: Load from database
   def load_execution_from_db(execution_id):
       conn = sqlite3.connect("executions.db")
       cursor = conn.cursor()
       
       cursor.execute("""
           SELECT flow_data, job_state_data
           FROM executions
           WHERE execution_id = ?
       """, (execution_id,))
       
       row = cursor.fetchone()
       conn.close()
       
       if row:
           flow_data = json.loads(row[0])
           job_state_data = json.loads(row[1])
           return flow_data, job_state_data
       else:
           return None, None

**Best Practices for Cross-Host Execution**:

1. **Always serialize Flow and JobState separately**:

   .. code-block:: python

      # ✅ Correct
      flow_data = flow.serialize()
      job_state_data = job_state.serialize()
      
      # ❌ Wrong: Flow doesn't include JobState
      # flow_data = flow.serialize(include_execution_state=True)  # This doesn't exist!

2. **Register all custom Routine classes**:

   .. code-block:: python

      from serilux import register_serializable
      
      @register_serializable
      class MyRoutine(Routine):
          def __init__(self):
              super().__init__()
              # ...

3. **Use no-argument constructors**:

   .. code-block:: python

      # ✅ Correct
      class MyRoutine(Routine):
          def __init__(self):
              super().__init__()
              self.set_config(param1="value1")
      
      # ❌ Wrong: Constructor with parameters
      class MyRoutine(Routine):
          def __init__(self, param1):  # Will fail during deserialization!
              super().__init__()
              self.param1 = param1

4. **Validate before transfer**:

   .. code-block:: python

      # Serialize and validate
      flow_data = flow.serialize()  # Validates automatically
      job_state_data = job_state.serialize()
      
      # Test deserialization locally before transfer
      test_flow = Flow()
      test_flow.deserialize(flow_data)
      
      test_job_state = JobState()
      test_job_state.deserialize(job_state_data)
      
      # If this works, safe to transfer

5. **Handle errors gracefully**:

   .. code-block:: python

      try:
          new_flow = Flow()
          new_flow.deserialize(flow_data)
          
          new_job_state = JobState()
          new_job_state.deserialize(job_state_data)
          
          resumed = new_flow.resume(new_job_state)
      except Exception as e:
          print(f"Failed to resume execution: {e}")
          # Handle error (retry, log, notify, etc.)

**Common Pitfalls**:

1. **Forgetting to serialize JobState**:

   .. code-block:: python

      # ❌ Wrong: Only serializing Flow
      flow_data = flow.serialize()
      # JobState is lost!
      
      # ✅ Correct: Serialize both
      flow_data = flow.serialize()
      job_state_data = job_state.serialize()

2. **Assuming Flow includes execution state**:

   .. code-block:: python

      # ❌ Wrong: Flow doesn't have job_state
      flow_data = flow.serialize()
      # flow_data["job_state"]  # KeyError!
      
      # ✅ Correct: JobState is separate
      job_state_data = job_state.serialize()

3. **Not registering custom routines**:

   .. code-block:: python

      # ❌ Wrong: Not registered
      class MyRoutine(Routine):
          def __init__(self):
              super().__init__()
      
      # Will fail during deserialization on Host B
      
      # ✅ Correct: Registered
      @register_serializable
      class MyRoutine(Routine):
          def __init__(self):
              super().__init__()

4. **Using constructor parameters**:

   .. code-block:: python

      # ❌ Wrong: Constructor with parameters
      class MyRoutine(Routine):
          def __init__(self, max_items):
              super().__init__()
              self.max_items = max_items
      
      # Will fail during deserialization
      
      # ✅ Correct: Use _config
      class MyRoutine(Routine):
          def __init__(self):
              super().__init__()
          
          def setup(self, max_items):
              self.set_config(max_items=max_items)

Serialization Best Practices
----------------------------

This section covers best practices for serializing and deserializing flows,
including when to use pause vs direct serialization, and what to expect after recovery.

When to Use Pause vs Direct Serialization
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Option 1: Pause Before Serialization (Recommended for Active Executions)**

Use ``flow.pause()`` when you want to capture the exact execution state at a specific point:

.. code-block:: python

   # Execute flow
   job_state = flow.execute(entry_id)
   
   # Pause to capture state
   flow.pause(job_state, reason="Saving checkpoint")
   
   # Serialize (pending tasks are already captured)
   flow_data = flow.serialize()
   job_state_data = job_state.serialize()
   
   # Save to file
   save_data = {
       "flow": flow_data,
       "job_state": job_state_data
   }

**Benefits of Pausing**:

- ✅ **Captures all pending tasks**: Tasks in the queue are moved to ``pending_tasks``
- ✅ **Clean state**: Active tasks complete before serialization
- ✅ **Predictable recovery**: Exact state is preserved
- ✅ **Better for debugging**: Clear pause points in execution history

**When to Use**:

- Saving checkpoints during long-running executions
- Transferring execution to another host at a known point
- Debugging and inspection of execution state
- When you need guaranteed consistency

**Option 2: Direct Serialization (For Quick Saves)**

You can serialize directly without pausing, especially useful for:

.. code-block:: python

   # Execute flow
   job_state = flow.execute(entry_id)
   
   # Serialize immediately (without pausing)
   flow_data = flow.serialize()
   job_state_data = job_state.serialize()
   
   # Save to file
   save_data = {
       "flow": flow_data,
       "job_state": job_state_data
   }

**Benefits of Direct Serialization**:

- ✅ **Faster**: No need to wait for active tasks
- ✅ **Non-blocking**: Can save state while execution continues
- ✅ **Simpler**: Fewer steps in the code

**When to Use**:

- Quick state snapshots
- Background persistence
- When execution can continue after save
- When you don't need to capture queue tasks

**Important Note**: When using direct serialization, tasks that are in the execution queue
may not be captured in ``pending_tasks``. However, **routilux automatically recovers tasks
from slot data** during ``resume()``, so execution will continue correctly even if some
tasks weren't in ``pending_tasks``.

Automatic Task Recovery
~~~~~~~~~~~~~~~~~~~~~~~

**New Feature**: Starting from version 0.1.0, routilux automatically recovers tasks from
slot data during ``resume()``. This means:

- ✅ **Slot data is preserved**: Data in routine slots is serialized with the flow
- ✅ **Automatic recovery**: Tasks are automatically rebuilt from slot data if needed
- ✅ **Retry state preserved**: Error handler retry counts are correctly restored
- ✅ **Connection recovery**: Connection information is automatically restored

**How It Works**:

When you call ``flow.resume(job_state)``, the system:

1. Deserializes pending tasks from ``job_state.pending_tasks``
2. **Automatically scans all routine slots for data**
3. **Rebuilds tasks** for slots that have data but no pending tasks
4. **Preserves retry state** from error handlers
5. **Restores connections** automatically

**Example**:

.. code-block:: python

   # Host A: Save state (without pausing)
   job_state = flow.execute(entry_id)
   flow_data = flow.serialize()
   job_state_data = job_state.serialize()
   # Some tasks may be in queue, not in pending_tasks
   
   # Host B: Restore and resume
   new_flow = Flow()
   new_flow.deserialize(flow_data)
   
   new_job_state = JobState()
   new_job_state.deserialize(job_state_data)
   
   # Resume automatically recovers tasks from slot data
   resumed = new_flow.resume(new_job_state)
   # ✅ Execution continues correctly, even if some tasks weren't in pending_tasks

**What Gets Recovered**:

- Tasks for slots with data
- Retry state (retry_count, max_retries)
- Connection information
- Task priority and metadata

**What Doesn't Get Recovered**:

- Tasks that were already completed
- Tasks for routines that are already failed/cancelled
- Tasks that exceed max_retries

Expected Behavior After Recovery
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Status Transitions**:

When you resume a flow, the status transitions as follows:

.. code-block:: python

   # Before resume
   assert job_state.status == "paused"  # or "running"
   
   # After resume
   resumed = flow.resume(job_state)
   assert resumed.status == "running"  # Always becomes "running"
   
   # After completion
   # Wait for completion...
   assert resumed.status in ["completed", "failed", "cancelled"]

**Execution Continuation**:

- ✅ **Pending tasks are restored**: Tasks from ``pending_tasks`` are enqueued
- ✅ **Slot data tasks are recovered**: Tasks are automatically rebuilt from slot data
- ✅ **Retry state is preserved**: Error handler retry counts continue from saved state
- ✅ **Execution history continues**: New events are appended to existing history

**Retry Behavior**:

When resuming a flow with retry-enabled routines:

.. code-block:: python

   # Host A: Save after 2 retries
   # error_handler.retry_count = 2
   # error_handler.max_retries = 4
   
   # Host B: Resume
   resumed = flow.resume(job_state)
   
   # Retry state is preserved
   assert error_handler.retry_count == 2  # ✅ Preserved
   assert error_handler.max_retries == 4   # ✅ Preserved
   
   # Remaining retries will execute
   # (2 more retries available: 3 and 4)

**Routine State**:

- ✅ **Completed routines**: Remain completed, don't re-execute
- ✅ **Failed routines**: Remain failed (unless retries are available)
- ✅ **Pending/running routines**: Will continue execution
- ✅ **Skipped routines**: Remain skipped

**Data Integrity**:

- ✅ **Slot data**: Preserved and used for task recovery
- ✅ **Shared data**: Preserved in ``job_state.shared_data``
- ✅ **Execution history**: Preserved and continues
- ✅ **Connection information**: Automatically restored

**Error Handling**:

If recovery encounters issues:

.. code-block:: python

   try:
       resumed = flow.resume(job_state)
   except ValueError as e:
       # Flow ID mismatch, routine not found, etc.
       print(f"Recovery failed: {e}")
   except Exception as e:
       # Other errors during recovery
       print(f"Unexpected error: {e}")

**Common Scenarios**:

1. **Normal Recovery**:

   .. code-block:: python

      # Pause and save
      flow.pause(job_state, reason="Checkpoint")
      flow_data = flow.serialize()
      job_state_data = job_state.serialize()
      
      # Restore and resume
      new_flow = Flow()
      new_flow.deserialize(flow_data)
      new_job_state = JobState()
      new_job_state.deserialize(job_state_data)
      
      resumed = new_flow.resume(new_job_state)
      # ✅ All pending tasks restored
      # ✅ Execution continues from pause point

2. **Recovery with Slot Data**:

   .. code-block:: python

      # Save without pausing (some tasks in queue)
      flow_data = flow.serialize()
      job_state_data = job_state.serialize()
      
      # Restore and resume
      new_flow = Flow()
      new_flow.deserialize(flow_data)
      new_job_state = JobState()
      new_job_state.deserialize(job_state_data)
      
      resumed = new_flow.resume(new_job_state)
      # ✅ Tasks automatically recovered from slot data
      # ✅ Execution continues correctly

3. **Recovery with Retries**:

   .. code-block:: python

      # Save after 2 retries (retry_count=2, max_retries=4)
      flow_data = flow.serialize()
      job_state_data = job_state.serialize()
      
      # Restore and resume
      new_flow = Flow()
      new_flow.deserialize(flow_data)
      new_job_state = JobState()
      new_job_state.deserialize(job_state_data)
      
      resumed = new_flow.resume(new_job_state)
      # ✅ Retry state preserved (retry_count=2)
      # ✅ Remaining retries will execute (3 and 4)

Best Practices Summary
~~~~~~~~~~~~~~~~~~~~~~

1. **Always serialize Flow and JobState separately**:

   .. code-block:: python

      flow_data = flow.serialize()
      job_state_data = job_state.serialize()
      # Never assume flow.serialize() includes job_state

2. **Use pause() for checkpoints**:

   .. code-block:: python

      flow.pause(job_state, reason="Checkpoint")
      # Ensures all pending tasks are captured

3. **Direct serialization is fine for quick saves**:

   .. code-block:: python

      # Can serialize without pausing
      # Automatic recovery handles slot data

4. **Register all custom routines**:

   .. code-block:: python

      @register_serializable
      class MyRoutine(Routine):
          def __init__(self):
              super().__init__()

5. **Test deserialization locally**:

   .. code-block:: python

      # Validate before transfer
      test_flow = Flow()
      test_flow.deserialize(flow_data)
      test_job_state = JobState()
      test_job_state.deserialize(job_state_data)

6. **Handle errors gracefully**:

   .. code-block:: python

      try:
          resumed = flow.resume(job_state)
      except Exception as e:
          # Log and handle error
          logger.error(f"Recovery failed: {e}")

7. **Trust automatic recovery**:

   .. code-block:: python

      # Don't manually check slot data or create tasks
      # Routilux handles this automatically
      resumed = flow.resume(job_state)
      # ✅ Tasks are automatically recovered

Related Topics
--------------

- :doc:`job_state` - Detailed JobState guide
- :doc:`state_management` - Pause, resume, and checkpoint management
- :doc:`flows` - Flow execution and management

