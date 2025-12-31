Routine API
============

The ``Routine`` class is the base class for all routines in Routilux. It provides
core functionality for slots, events, and configuration management.

Key Features
------------

* **Input Data Extraction**: Use ``_extract_input_data()`` to simplify slot handler data extraction
* **Configuration Management**: Store configuration in ``_config`` dictionary
* **Execution State**: Store execution state in JobState (not routine instance variables)

.. automodule:: routilux.routine
   :members:
   :undoc-members:
   :show-inheritance:
   :exclude-members: ExecutionContext

.. py:class:: ExecutionContext
   :no-index:

   Execution context containing flow, job_state, and routine_id.

   This is returned by :meth:`Routine.get_execution_context` to provide convenient
   access to execution-related handles during routine execution.

   .. py:attribute:: flow
      :no-index:

      The Flow object managing this execution.

   .. py:attribute:: job_state
      :no-index:

      The JobState object tracking this execution's state.

   .. py:attribute:: routine_id
      :no-index:

      The string ID of this routine in the flow.

Helper Methods
--------------

The ``Routine`` class provides helper methods for common operations:

* ``_extract_input_data(data, **kwargs)``: Extract and normalize input data from slot parameters

These methods are available to all routines that inherit from ``Routine``.

Important Constraints
---------------------

* **During execution, routines MUST NOT modify any instance variables**
* **All execution-related state should be stored in JobState**
* Routines can only READ from ``_config`` during execution
* Routines can WRITE to JobState (via ``job_state.update_routine_state()``, etc.)

