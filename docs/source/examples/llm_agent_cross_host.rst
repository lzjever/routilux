LLM Agent Cross-Host Interrupt and Recovery Demo
==================================================

Overview
--------

This demo demonstrates a complete LLM agent workflow system with cross-host interrupt and recovery capabilities using routilux. It showcases how an LLM agent can pause execution when user input is needed, save state to cloud storage, and resume execution on a different host.

Features
--------

- **Active Interruption**: LLM Agent Routine can pause execution from within its handler when user input is needed
- **State Persistence**: Execution state is automatically saved to cloud storage (simulated)
- **Cross-Host Recovery**: Load state from cloud storage and continue execution on a different host
- **Deferred Events**: Use ``emit_deferred_event()`` to ensure events are emitted on resume
- **Shared Data**: Use ``shared_data`` and ``shared_log`` to store execution data
- **Comprehensive Logging**: Detailed logging system to help understand execution flow

Quick Start
-----------

Run the demo:

.. code-block:: bash

   cd /home/developer/workspace/routilux
   conda activate mbos
   python -m playground.llm_agent_cross_host.cross_host_demo

Architecture
------------

Directory Structure
~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   playground/llm_agent_cross_host/
   ├── __init__.py              # Package initialization
   ├── logger.py                # Logging utility
   ├── mock_llm.py              # Mock LLM service
   ├── mock_storage.py          # Mock cloud storage service
   ├── enhanced_routine.py      # Enhanced Routine base class
   ├── llm_agent_routine.py     # LLM Agent Routine implementation
   ├── cross_host_demo.py       # Complete demonstration
   └── README.md                # Complete documentation

Component Diagram
~~~~~~~~~~~~~~~~~

.. code-block:: text

   ┌─────────────────┐
   │  Cross-Host     │
   │     Demo        │
   └────────┬────────┘
            │
       ┌────┴────┐
       │         │
   ┌───▼───┐ ┌──▼────┐
   │ Host A│ │Host B │
   └───┬───┘ └──┬────┘
       │        │
   ┌───▼────────▼───┐
   │  Flow +        │
   │  JobState      │
   └───┬────────────┘
       │
   ┌───▼────────────┐
   │ LLM Agent      │
   │   Routine      │
   └───┬────────────┘
       │
   ┌───▼────┐  ┌──────▼──────┐
   │  LLM   │  │   Storage    │
   │Service │  │   Service    │
   └────────┘  └──────────────┘

Design Patterns
---------------

Enhanced Routine Pattern
~~~~~~~~~~~~~~~~~~~~~~~~

The ``EnhancedRoutine`` class extends the base ``Routine`` class with convenience methods without modifying the core routilux library:

- ``pause_execution()``: Convenient method to pause execution from within a routine
- ``save_execution_state()``: Convenient method to save execution state to cloud storage

This pattern allows extending functionality without core library changes.

Deferred Event Pattern
~~~~~~~~~~~~~~~~~~~~~~~

Instead of directly emitting events before pausing, use ``emit_deferred_event()``:

.. code-block:: python

   # ✅ Correct: Deferred event
   self.emit_deferred_event("user_input_required", question=question)
   self.pause_execution(reason="Waiting for user input")

   # ❌ Wrong: Direct emit
   self.emit("user_input_required", question=question)  # May execute immediately
   self.pause_execution(reason="Waiting for user input")

This ensures events are emitted when execution resumes, not before pausing.

State Persistence Pattern
~~~~~~~~~~~~~~~~~~~~~~~~~

Execution state is serialized and saved to cloud storage:

1. Serialize Flow (workflow definition)
2. Serialize JobState (execution state)
3. Save both to cloud storage
4. Load and deserialize on another host
5. Resume execution

Shared Data Pattern
~~~~~~~~~~~~~~~~~~~

Use ``JobState.shared_data`` and ``JobState.shared_log`` to store execution-wide data:

- **shared_data**: Key-value store for shared data
- **shared_log**: Append-only log for execution history

This allows routines to share data without modifying routine instance variables.

Code Overview
-------------

Core Components
~~~~~~~~~~~~~~~

PlaygroundLogger (``logger.py``)
   Structured logging system with log levels, categories, timestamps, and step numbering.

MockLLMService (``mock_llm.py``)
   Simulates LLM API calls. Replace with actual LLM API (OpenAI, Anthropic, etc.) in production.

MockCloudStorage (``mock_storage.py``)
   Simulates cloud storage. Replace with actual cloud storage (S3, Redis, database, etc.) in production.

EnhancedRoutine (``enhanced_routine.py``)
   Extended Routine base class with convenience methods for pausing and saving state.

LLMAgentRoutine (``llm_agent_routine.py``)
   LLM Agent Routine implementation with slots (trigger, user_input, continue) and events (output, question, completed).

Cross-Host Demo (``cross_host_demo.py``)
   Complete demonstration showing Host A execution and Host B recovery.

Execution Flow
--------------

Phase 1: Initialization
~~~~~~~~~~~~~~~~~~~~~~~~

1. Initialize logger
2. Initialize LLM service
3. Initialize cloud storage
4. Create workflow

Phase 2: Host A Execution
~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Start execution with task
2. LLM Agent processes task
3. LLM generates question, needs user input
4. Routine pauses execution
5. Execution state saved to cloud storage
6. JobState status = "paused"

Phase 3: Host B Recovery
~~~~~~~~~~~~~~~~~~~~~~~~~

1. Load Flow and JobState from cloud storage
2. Deserialize both objects
3. Resume execution (``flow.resume()``)
4. Deferred events are automatically emitted
5. Trigger user input handler with user response
6. LLM processes user response
7. Workflow completes
8. JobState status = "completed"

Usage Examples
--------------

Basic Usage
~~~~~~~~~~~

.. code-block:: python

   from routilux import Flow, JobState
   from playground.llm_agent_cross_host.llm_agent_routine import LLMAgentRoutine
   from playground.llm_agent_cross_host.mock_storage import get_storage

   # Create flow
   flow = Flow(flow_id="my_workflow")
   agent = LLMAgentRoutine()
   agent_id = flow.add_routine(agent, "agent")

   # Execute
   job_state = flow.execute(agent_id, entry_params={"task": "Analyze data"})

   # If paused, save state
   if job_state.status == "paused":
       storage_key = f"execution_state/{job_state.job_id}"
       flow_data = flow.serialize()
       job_state_data = job_state.serialize()
       storage = get_storage()
       storage.put(storage_key, {
           "flow": flow_data,
           "job_state": job_state_data,
       })

Resume Execution
~~~~~~~~~~~~~~~~

.. code-block:: python

   from routilux import Flow, JobState
   from playground.llm_agent_cross_host.mock_storage import get_storage

   # Load from cloud storage
   storage = get_storage()
   transfer_data = storage.get(storage_key)

   # Deserialize
   flow = Flow()
   flow.deserialize(transfer_data["flow"])
   job_state = JobState()
   job_state.deserialize(transfer_data["job_state"])

   # Set user response
   job_state.update_shared_data("user_response", "I choose option A")

   # Resume execution
   resumed = flow.resume(job_state)

   # Trigger user input handler
   agent_routine = flow.routines[agent_id]
   user_input_slot = agent_routine.get_slot("user_input")
   user_input_slot.call_handler({"user_response": "I choose option A"})

Performance Analysis
--------------------

Performance Metrics
~~~~~~~~~~~~~~~~~~~

Based on actual measurements:

- **Flow serialization**: 0.214ms (~1.4KB data)
- **JobState serialization**: 0.011ms (~1.1KB data)
- **Flow deserialization**: 0.257ms
- **JobState deserialization**: 0.027ms
- **Single LLM call**: 50.086ms (simulated delay)
- **Pause execution**: ~1ms
- **Resume execution**: <1ms

Performance Timeline
~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   Timeline (seconds)    Operation                      Duration
   ─────────────────────────────────────────────────────────────
   0.000                 Initialize services            <1ms
   0.001 → 0.051         LLM process task              50ms ⭐
   0.051 → 0.052         Serialize and save state      1ms
   0.052 → 0.053         Pause execution               1ms
   0.151                 Load from cloud storage        <1ms
   0.151 → 0.152         Deserialize                   1ms
   0.152 → 0.202         LLM process user input        50ms ⭐
   ─────────────────────────────────────────────────────────────
   Total actual execution: ~200ms

Performance Bottlenecks
~~~~~~~~~~~~~~~~~~~~~~~~

1. **LLM Call Delay** ⭐⭐⭐
   - Each LLM call takes 50ms (simulated)
   - Total: 100ms (2 calls)
   - **Optimization**: Use async LLM calls, implement request batching

2. **execute() Return Delay** ⚠️
   - execute() returns after 98ms
   - **Optimization**: Optimize event_loop wait logic

3. **Wait for Completion Timeout** ⚠️⚠️
   - Wait logic takes 10 seconds (timeout)
   - **Optimization**: Improve completion detection logic

Performance Advantages
~~~~~~~~~~~~~~~~~~~~~~

- ✅ Serialization/Deserialization: <0.5ms, excellent
- ✅ Pause/Resume: <2ms, very fast
- ✅ Initialization: <1ms, fast startup
- ✅ Data Size: <2KB, fast transmission

Extension Guide
---------------

Integrate Real LLM Service
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Replace ``mock_llm.py`` implementation with actual LLM API calls (OpenAI, Anthropic, etc.).

Integrate Real Cloud Storage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Replace ``mock_storage.py`` implementation with actual cloud storage (S3, Redis, database, etc.).

Custom Routine
~~~~~~~~~~~~~~

Inherit from ``EnhancedRoutine`` or ``LLMAgentRoutine`` to create custom routines.

Key Design Points
------------------

1. **Deferred Events**: Use ``emit_deferred_event()`` instead of ``emit()`` before pausing
2. **State Persistence**: Both Flow and JobState must be serialized for cross-host recovery
3. **Routine Registration**: All custom Routines must use ``@register_serializable`` decorator
4. **Shared Data**: Use ``JobState.shared_data`` and ``JobState.shared_log`` for execution-wide data

For complete documentation, see: ``playground/llm_agent_cross_host/README.md``

