Architecture Details
====================

This document provides detailed architecture information for routilux.

Class Hierarchy
---------------

.. code-block:: text

   Serializable (base)
   ├── Routine
   ├── Flow
   ├── JobState
   │   └── ExecutionRecord
   ├── Event
   ├── Slot
   ├── Connection
   ├── ErrorHandler
   └── ExecutionTracker

Data Flow
---------

Event-Driven Execution
~~~~~~~~~~~~~~~~~~~~~~~

The system uses an event-driven execution model:

1. **Routine Execution**: A routine is called with entry parameters
2. **Event Emission**: The routine emits events through ``emit()``
3. **Connection Activation**: Events trigger connections to slots
4. **Data Processing**: Slots receive data and call handlers
5. **State Update**: Execution state is updated in JobState

Parameter Mapping
~~~~~~~~~~~~~~~~~

Connections support parameter mapping to transform parameter names:

.. code-block:: python

   # Source event emits "source_param"
   event = routine1.add_event("output", ["source_param"])
   
   # Target slot expects "target_param"
   slot = routine.add_slot("input", handler=lambda target_param: ...)
   
   # Map source_param to target_param
   connection = Connection(
       event, slot,
       param_mapping={"source_param": "target_param"}
   )

State Management
----------------

JobState Structure
~~~~~~~~~~~~~~~~~~

JobState maintains:

* **Status**: Current execution status (pending, running, paused, completed, failed, cancelled)
* **Routine States**: State dictionary for each routine
* **Execution History**: List of ExecutionRecord objects
* **Pause Points**: List of pause points with checkpoints

Execution Tracking
~~~~~~~~~~~~~~~~~~

ExecutionTracker provides:

* **Routine Executions**: Execution records for each routine
* **Event Flow**: Complete event flow history
* **Performance Metrics**: Execution time, success rate, etc.

Error Handling
--------------

ErrorHandler supports multiple strategies:

* **STOP**: Stop execution immediately
* **CONTINUE**: Continue execution despite errors
* **RETRY**: Retry the failed routine
* **SKIP**: Skip the failed routine and continue

Serialization
-------------

All core classes support serialization:

* **Flow**: Serializes routines, connections, and state
* **Routine**: Serializes slots, events, and stats
* **JobState**: Serializes execution state and history
* **Connection**: Serializes event-slot relationships and mappings

The serialization system uses the Serializable base class and supports:

* Automatic field registration
* Nested object serialization
* Type preservation
* Reference reconstruction

