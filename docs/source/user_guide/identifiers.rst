Identifiers: job_id, flow_id, and routine_id
=============================================

Overview
--------

Routilux uses three types of identifiers to manage workflows and executions:

- **job_id**: Unique identifier for each execution instance (UUID)
- **flow_id**: Identifier for workflow definition (string, can be custom)
- **routine_id**: Identifier for a routine within a flow (string, can be custom)

Understanding these identifiers is crucial for:
- State persistence and recovery
- Cross-host execution
- Execution tracking and logging
- Workflow version management

Quick Reference
---------------

.. list-table:: Identifier Summary
   :header-rows: 1
   :widths: 20 15 15 20 30

   * - ID
     - Type
     - Default Format
     - Scope
     - Importance
   * - ``job_id``
     - UUID
     - UUID v4
     - Single execution
     - ⭐⭐⭐ Critical
   * - ``flow_id``
     - String
     - UUID v4 (customizable)
     - Workflow definition
     - ⭐⭐ Important
   * - ``routine_id``
     - String
     - ``hex(id(self))`` (customizable)
     - Workflow node
     - ⭐⭐ Important

job_id: Execution Instance Identifier
--------------------------------------

**Purpose**: Uniquely identifies each execution instance of a workflow.

**Characteristics**:
- ✅ **Auto-generated**: Automatically created as UUID when ``JobState`` is instantiated
- ✅ **Globally unique**: Uses UUID v4, ensuring global uniqueness
- ✅ **Not customizable**: Users cannot modify it
- ✅ **Execution-level**: Each ``flow.execute()`` call creates a new ``job_id``

Use Cases
~~~~~~~~~

1. **State Persistence and Recovery**

   Use ``job_id`` as the storage key for execution state:

   .. code-block:: python

      # Save execution state
      job_state = flow.execute(entry_id)
      storage_key = f"execution_state/{job_state.job_id}"
      storage.put(storage_key, {
          "flow": flow.serialize(),
          "job_state": job_state.serialize(),
      })

      # Restore execution state
      transfer_data = storage.get(storage_key)
      job_state = JobState()
      job_state.deserialize(transfer_data["job_state"])

2. **Execution Tracking and Logging**

   Associate logs and monitoring data with specific executions:

   .. code-block:: python

      logger.info(f"Execution started: {job_state.job_id}")
      
      # Query specific execution state
      execution_state = storage.get(f"execution_state/{job_id}")

3. **Multiple Execution Instances**

   The same Flow can execute multiple times, each with a unique ``job_id``:

   .. code-block:: python

      flow = Flow(flow_id="my_workflow")
      
      job1 = flow.execute(entry_id, entry_params={"task": "A"})  # job_id: xxx-1
      job2 = flow.execute(entry_id, entry_params={"task": "B"})  # job_id: xxx-2
      
      assert job1.job_id != job2.job_id  # Different execution instances

Importance for Client Code
~~~~~~~~~~~~~~~~~~~~~~~~~~

**⭐⭐⭐ Critical - Must Use**

- **Required for**: Cross-host recovery, state persistence
- **Storage key**: Recommended to use ``job_id`` as cloud storage key
- **Tracking**: Used to track and query specific execution instances
- **Log correlation**: Associate logs with execution instances

Example from Demo
~~~~~~~~~~~~~~~~~

In ``cross_host_demo.py``:

.. code-block:: python

   storage_key = f"execution_state/{job_state.job_id}"
   # Output: "execution_state/3a46aec8-363c-4487-b842-3ea38a0e9c99"

flow_id: Workflow Definition Identifier
---------------------------------------

**Purpose**: Identifies the workflow definition (template).

**Characteristics**:
- ✅ **Customizable**: Can be specified when creating Flow, or auto-generated as UUID
- ✅ **Workflow-level**: Same ``flow_id`` can execute multiple times (each with different ``job_id``)
- ✅ **Recovery validation**: Used to verify that restored Flow and JobState match

Use Cases
~~~~~~~~~

1. **Workflow Version Management**

   Use meaningful ``flow_id`` to identify workflow versions:

   .. code-block:: python

      # Use meaningful flow_id for version management
      flow_v1 = Flow(flow_id="data_processing_v1")
      flow_v2 = Flow(flow_id="data_processing_v2")
      
      # Multiple versions can coexist

2. **Recovery Validation**

   System automatically validates ``flow_id`` match during recovery:

   .. code-block:: python

      flow = Flow()
      flow.deserialize(transfer_data["flow"])
      
      job_state = JobState()
      job_state.deserialize(transfer_data["job_state"])
      
      # System automatically validates flow_id match
      if job_state.flow_id != flow.flow_id:
          raise ValueError("Flow ID mismatch!")

3. **Workflow Classification and Querying**

   Query all executions of a specific workflow:

   .. code-block:: python

      # Query all executions of a specific workflow
      all_executions = [
          job for job in all_job_states 
          if job.flow_id == "my_workflow"
      ]

Importance for Client Code
~~~~~~~~~~~~~~~~~~~~~~~~~~

**⭐⭐ Important - Recommended to Customize**

- **Recommended**: Use meaningful names for easier management
- **Version control**: Can be used for workflow version management
- **Recovery validation**: System validates automatically, but understanding helps with debugging
- **Query filtering**: Can be used to query executions of specific workflows

Example from Demo
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Custom flow_id
   flow = Flow(flow_id="llm_agent_workflow")
   # Output: "llm_agent_workflow"
   
   # Auto-generated
   flow = Flow()  # flow_id auto-generated as UUID
   # Output: "9867d45c-1b5f-4af2-87c0-6e73c93df14d"

routine_id: Workflow Node Identifier
--------------------------------------

**Purpose**: Identifies a routine (node) within a flow.

**Characteristics**:
- ✅ **Customizable**: Can be specified when adding Routine, or uses auto-generated ``hex(id(self))``
- ✅ **Flow-level**: Must be unique within the same Flow
- ✅ **Execution access**: Available via ``get_execution_context()`` during execution

Use Cases
~~~~~~~~~

1. **Adding and Connecting Routines**

   Specify ``routine_id`` when adding routines to flow:

   .. code-block:: python

      # Add Routine with custom routine_id
      flow = Flow()
      processor = DataProcessor()
      processor_id = flow.add_routine(processor, "processor")  # Custom routine_id
      
      validator = DataValidator()
      validator_id = flow.add_routine(validator, "validator")  # Custom routine_id
      
      # Connect Routines using routine_id
      flow.connect(processor_id, "output", validator_id, "input")

2. **Execution Entry Point**

   Specify which routine to start execution from:

   .. code-block:: python

      # Specify entry routine using routine_id
      job_state = flow.execute(processor_id, entry_params={"data": "test"})

3. **State Query and Update**

   Query and update routine-specific state:

   .. code-block:: python

      # Update routine state using routine_id
      def process(self, data):
          ctx = self.get_execution_context()
          if ctx:
              # Use routine_id to update state
              ctx.job_state.update_routine_state(ctx.routine_id, {
                  "status": "processing",
                  "processed_count": 10
              })
      
      # Query specific routine state
      routine_state = job_state.get_routine_state("processor")

4. **Execution History Query**

   Query execution history for a specific routine:

   .. code-block:: python

      # Query execution history for specific routine
      history = job_state.get_execution_history(routine_id="processor")
      for record in history:
          print(f"{record.routine_id} emitted {record.event_name}")

Importance for Client Code
~~~~~~~~~~~~~~~~~~~~~~~~~~

**⭐⭐ Important - Recommended to Customize**

- **Required for**: Adding routines, connections, execution entry points
- **Recommended**: Use meaningful names for easier understanding and maintenance
- **State management**: Needed for updating and querying routine state
- **Debugging**: Used in execution history and logs

Example from Demo
~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Custom routine_id
   agent = LLMAgentRoutine()
   agent_id = flow.add_routine(agent, "llm_agent")  # Custom routine_id
   # Output: "llm_agent"
   
   # Execute using routine_id
   job_state = flow.execute(agent_id, entry_params={"task": "..."})
   
   # Query state using routine_id
   routine_state = job_state.get_routine_state(agent_id)

Best Practices
--------------

Using job_id
~~~~~~~~~~~~

**✅ Recommended**:

.. code-block:: python

   # Use job_id as storage key
   storage_key = f"execution_state/{job_state.job_id}"
   
   # Record job_id in logs
   logger.info(f"Execution {job_state.job_id} started")
   
   # Use for querying specific execution
   execution = storage.get(f"execution_state/{job_id}")

**❌ Common Mistakes**:

.. code-block:: python

   # ❌ Wrong: Using flow_id as storage key (multiple executions will overwrite)
   storage_key = f"execution_state/{flow.flow_id}"  # Wrong!

   # ✅ Correct: Use job_id as storage key
   storage_key = f"execution_state/{job_state.job_id}"  # Correct

Using flow_id
~~~~~~~~~~~~~

**✅ Recommended**:

.. code-block:: python

   # Use meaningful names
   flow = Flow(flow_id="llm_agent_workflow_v1")
   
   # Can be used for version management
   flow_v1 = Flow(flow_id="data_processing_v1")
   flow_v2 = Flow(flow_id="data_processing_v2")

**⚠️ Alternative**:

.. code-block:: python

   # Auto-generated (if version management not needed)
   flow = Flow()  # Auto-generates UUID

Using routine_id
~~~~~~~~~~~~~~~~

**✅ Recommended**:

.. code-block:: python

   # Use meaningful names
   processor_id = flow.add_routine(processor, "data_processor")
   validator_id = flow.add_routine(validator, "data_validator")

**⚠️ Alternative**:

.. code-block:: python

   # Auto-generated (not recommended, hard to understand)
   routine_id = flow.add_routine(routine)  # Uses hex(id(self))

Summary
-------

Importance Ranking
~~~~~~~~~~~~~~~~~~

1. **job_id** ⭐⭐⭐ - **Must Use**
   - Unique identifier for each execution
   - Critical for state persistence and recovery
   - Execution tracking and log correlation

2. **flow_id** ⭐⭐ - **Recommended to Customize**
   - Workflow definition identifier
   - Version management and classification
   - Recovery validation (automatic)

3. **routine_id** ⭐⭐ - **Recommended to Customize**
   - Workflow node identifier
   - Adding, connecting, execution entry
   - State management and history query

Client Code Recommendations
~~~~~~~~~~~~~~~~~~~~~~~~~~~

- **Must use job_id**: All state persistence and recovery scenarios
- **Recommended to customize flow_id**: Easier version management and querying
- **Recommended to customize routine_id**: Easier to understand and maintain
- **Understand their roles**: Helps with debugging and troubleshooting

Related Topics
--------------

- :doc:`job_state` - Learn more about JobState and execution state management
- :doc:`flows` - Learn more about Flow and workflow definition
- :doc:`routines` - Learn more about Routine and workflow nodes
- :doc:`serialization` - Learn about state serialization and recovery

