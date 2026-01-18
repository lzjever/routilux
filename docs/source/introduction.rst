Introduction
============

Routilux is a powerful, event-driven workflow orchestration framework designed for building
flexible and maintainable data processing pipelines. With its intuitive slot-and-event mechanism,
Routilux makes it easy to connect routines, manage state, and orchestrate complex workflows
while maintaining clean separation of concerns.

Why Routilux?
--------------

Building workflow-based applications can be challenging. You need to:

* **Connect components** in flexible ways (one-to-many, many-to-one, many-to-many)
* **Manage state** across multiple processing steps
* **Handle errors** gracefully with retry, skip, or continue strategies
* **Track execution** for debugging and monitoring
* **Scale** with concurrent execution for I/O-bound operations
* **Persist** workflows for recovery and resumption

Routilux addresses all these needs with a clean, Pythonic API that feels natural to use.

What Makes Routilux Special?
------------------------------

**🎯 Event-Driven Architecture**

Routilux uses a clear slot-and-event mechanism where routines communicate through well-defined
interfaces. This makes your workflows easy to understand, test, and maintain.

.. code-block:: python

   from routilux import Routine
   from routilux.activation_policies import immediate_policy

   class DataProcessor(Routine):
       def __init__(self):
           super().__init__()
           # Define input slot
           self.input_slot = self.add_slot("input")
           # Define output event
           self.output_event = self.add_event("output", ["result"])

           def logic(slot_data, policy_message, job_state):
               data = slot_data.get("input", [{}])[0].get("data", "")
               result = f"Processed: {data}"
               self.emit("output", result=result)

           self.set_logic(logic)
           self.set_activation_policy(immediate_policy())

**🔗 Flexible Connections**

Connect routines in any pattern you need - one-to-many, many-to-one, or complex branching patterns.
Routilux handles the complexity while you focus on your business logic.

.. code-block:: python

   from routilux import Flow

   flow = Flow(flow_id="my_pipeline")

   # One event to multiple slots
   flow.connect("source", "output", "processor1", "input")
   flow.connect("source", "output", "processor2", "input")

   # Multiple events to one slot
   flow.connect("source1", "output", "aggregator", "input")
   flow.connect("source2", "output", "aggregator", "input")

**⚡ Runtime-Based Execution**

Routilux uses a centralized Runtime for all flow execution:

- **Shared Thread Pool**: Efficient resource utilization across all flows
- **Non-Blocking Execution**: ``runtime.exec()`` returns immediately
- **Job Tracking**: Thread-safe job registry for monitoring
- **Event Routing**: Automatic event delivery to connected slots

.. code-block:: python

   from routilux.runtime import Runtime
   from routilux.monitoring.flow_registry import FlowRegistry

   # Register flow
   registry = FlowRegistry.get_instance()
   registry.register_by_name("my_pipeline", flow)

   # Execute with Runtime
   runtime = Runtime(thread_pool_size=10)
   job_state = runtime.exec("my_pipeline", entry_params={"data": "hello"})
   runtime.wait_until_all_jobs_finished(timeout=5.0)

**🛡️ Robust Error Handling**

Multiple error handling strategies (STOP, CONTINUE, RETRY, SKIP) let you build resilient
workflows that handle failures gracefully.

.. code-block:: python

   from routilux import ErrorHandler, ErrorStrategy

   error_handler = ErrorHandler(
       strategy=ErrorStrategy.RETRY,
       max_retries=3,
       retry_delay=1.0
   )
   flow.set_error_handler(error_handler)

**💾 Full Serialization Support**

Serialize and deserialize entire flows for persistence, recovery, and distributed execution.

.. code-block:: python

   # Save job state
   job_state.save("state.json")

   # Resume from saved state
   from routilux.job_state import JobState
   saved_state = JobState.load("state.json")
   runtime.exec("my_flow", job_state=saved_state)

**📈 Comprehensive Tracking**

Built-in execution tracking provides insights into workflow performance, execution history,
and routine statistics.

Key Features
------------

* **Slots and Events Mechanism**: Clear distinction between input slots and output events
* **Many-to-Many Connections**: Flexible connection relationships between routines
* **State Management**: Unified ``JobState`` for tracking execution state
* **Flow Management**: Workflow orchestration, persistence, and recovery
* **Runtime Execution**: Centralized execution manager with thread pool
* **Error Handling**: Multiple error handling strategies (STOP, CONTINUE, RETRY, SKIP)
* **Execution Tracking**: Comprehensive execution tracking and performance monitoring
* **Concurrent Execution**: Thread pool-based parallel execution for I/O-bound operations
* **Serialization Support**: Full serialization/deserialization support for persistence
* **HTTP API & WebSocket**: Optional REST API and real-time WebSocket monitoring

Architecture and Responsibility Separation
------------------------------------------

Understanding the clear separation of responsibilities between ``Flow``, ``Routine``, ``Runtime``, and ``JobState``
is **crucial** for effectively using Routilux. This separation enables flexible, scalable, and maintainable
workflow applications.

**Core Components and Their Responsibilities**:

**Routine** - Function Implementation
   Routines define **what** each node does. They are pure function implementations:

   * **Slots** (0-N): Input mechanisms that receive data
   * **Events** (0-N): Output mechanisms that emit data
   * **Configuration** (``_config``): Static configuration parameters (set via ``set_config()``)
   * **Activation Policy**: When to execute the routine
   * **Logic Function**: What the routine does
   * **No Runtime State**: Routines **must not** modify instance variables during execution

   .. warning:: **Critical Constraint: Parameterless Constructor**

      Routines MUST have a parameterless constructor for serialization support:

      .. code-block:: python

         # ❌ WRONG - Will break serialization
         class MyRoutine(Routine):
             def __init__(self, name: str):
                 super().__init__()
                 self.name = name

         # ✅ CORRECT - Use _config dictionary
         class MyRoutine(Routine):
             def __init__(self):
                 super().__init__()
                 self.set_config(name="my_routine", timeout=30)

   .. warning:: **Critical Constraint: No Instance Variable Modification**

      During execution, routines MUST NOT modify instance variables. All execution state
      must be stored in JobState:

      .. code-block:: python

         # ❌ WRONG - Breaks execution isolation
         def logic(slot_data, policy_message, job_state):
             self.counter += 1  # Data race!

         # ✅ CORRECT - Use JobState
         def logic(slot_data, policy_message, job_state):
             counter = job_state.get_routine_state(routine_id, {}).get("count", 0)
             job_state.update_routine_state(routine_id, {"count": counter + 1})

**Flow** - Workflow Structure and Configuration
   Flows define **how** routines are connected and configured:

   * **Workflow Structure**: Defines which routines exist and how they're connected
   * **Static Configuration**: Flow-level parameters (error handler, timeout, etc.)
   * **Connection Management**: Links events to slots
   * **No Runtime State**: Flow does **not** store execution state or business data

   .. note:: **Flow is a Template**

      Flow is a **template** that can be executed multiple times, each with its own ``JobState``.
      Multiple executions = multiple independent ``JobState`` objects.

**Runtime** - Centralized Execution Manager
   Runtime manages all flow executions:

   * **Thread Pool**: Shared worker threads for all flows
   * **Job Registry**: Thread-safe tracking of active jobs
   * **Event Routing**: Delivers events to connected slots
   * **Non-Blocking Execution**: Returns immediately after starting

**JobState** - Runtime State and Business Data
   JobState stores **everything** related to a specific execution:

   * **Execution State**: Status (pending, running, completed, failed, cancelled)
   * **Routine States**: Per-routine execution state dictionaries
   * **Execution History**: Complete record of all routine executions with timestamps
   * **Business Data**: ``shared_data`` (read/write) and ``shared_log`` (append-only)
   * **Output Handling**: ``output_handler`` and ``output_log`` for execution-specific output

**Why This Separation Matters**:

1. **Multiple Executions**: The same flow can run multiple times concurrently, each with its own state
2. **Serialization**: Flow (structure) and JobState (state) are serialized separately
3. **State Isolation**: Each execution's state is completely isolated, preventing data corruption
4. **Reusability**: Routine objects can be reused across multiple executions without conflicts
5. **Clarity**: Clear boundaries make code easier to understand, test, and maintain

**Example - Correct Usage**:

.. code-block:: python

   from routilux import Routine, Flow
   from routilux.activation_policies import immediate_policy

   class Processor(Routine):
       def __init__(self):
           super().__init__()
           # Static configuration (set once)
           self.set_config(threshold=10, timeout=30)
           self.input_slot = self.add_slot("input")
           self.output_event = self.add_event("output", ["result"])

           def logic(slot_data, policy_message, job_state):
               # Read static config
               threshold = self.get_config("threshold", 0)

               # Store execution-specific state in JobState
               # (Assuming routine_id is available via context)
               job_state.update_routine_state("processor", {"processed": True})

               # Store business data in JobState
               job_state.shared_data["last_processed"] = slot_data
               job_state.shared_log.append({"action": "process", "data": slot_data})

           self.set_logic(logic)
           self.set_activation_policy(immediate_policy())

   # Flow defines structure (static)
   flow = Flow(flow_id="my_workflow")
   processor = Processor()
   flow.add_routine(processor, "processor")

Design Principles
-----------------

* **Separation of Concerns**: Clear separation between structure (Flow), execution (Runtime), and state (JobState)
* **Flexibility**: Support for various workflow patterns (linear, branching, converging)
* **Persistence**: Full support for serialization and state recovery
* **Error Resilience**: Multiple error handling strategies for robust applications
* **Observability**: Comprehensive tracking and monitoring capabilities
* **Simplicity**: Clean, Pythonic API that's easy to learn and use
* **Extensibility**: Easy to create custom routines and extend functionality

Real-World Use Cases
--------------------

Routilux is ideal for:

* **Data Processing Pipelines**: ETL workflows, data transformation, validation
* **API Orchestration**: Coordinating multiple API calls, handling responses
* **LLM Agent Workflows**: Complex agent interactions, tool calling, result processing
* **Event Processing**: Real-time event streams, filtering, routing
* **Batch Processing**: Large-scale data processing with error recovery
* **Workflow Automation**: Business process automation, task orchestration

Getting Started
---------------

Ready to get started? Check out the :doc:`quickstart` guide for a hands-on introduction,
or dive into the :doc:`user_guide/index` for detailed documentation.

.. code-block:: python

   from routilux import Routine, Flow, Runtime
   from routilux.activation_policies import immediate_policy
   from routilux.monitoring.flow_registry import FlowRegistry

   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")
           self.output = self.add_event("output", ["result"])

           def logic(slot_data, policy_message, job_state):
               data = slot_data.get("input", [{}])[0]
               self.emit("output", result=f"Processed: {data}")

           self.set_logic(logic)
           self.set_activation_policy(immediate_policy())

   # Create flow
   flow = Flow(flow_id="my_workflow")
   routine = MyRoutine()
   flow.add_routine(routine, "my_routine")

   # Register and execute
   FlowRegistry.get_instance().register_by_name("my_workflow", flow)
   runtime = Runtime(thread_pool_size=5)
   job_state = runtime.exec("my_workflow", entry_params={"data": "Hello"})
   runtime.wait_until_all_jobs_finished(timeout=5.0)

Next Steps
----------

* :doc:`installation` - Installation instructions
* :doc:`quickstart` - Get started in 5 minutes
* :doc:`http_api` - HTTP API and security configuration
* :doc:`user_guide/index` - Comprehensive user guide
* :doc:`api_reference/index` - Complete API documentation
* :doc:`examples/index` - Real-world examples
