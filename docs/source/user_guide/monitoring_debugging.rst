Monitoring and Debugging
========================

Routilux provides comprehensive monitoring and debugging capabilities through a built-in HTTP API and WebSocket interface. This allows you to monitor workflow execution, set breakpoints, inspect variables, and debug flows in real-time.

.. contents::
   :local:
   :depth: 2

Overview
--------

The monitoring system consists of several key components:

* **Monitor Collector**: Collects execution events, metrics, and traces
* **Breakpoint Manager**: Manages breakpoints for debugging
* **Debug Session Manager**: Handles interactive debugging sessions
* **HTTP API**: RESTful endpoints for monitoring and control
* **WebSocket API**: Real-time event streaming and debug interaction

All monitoring features are **optional** - when disabled, they have zero overhead on workflow execution.

Enabling Monitoring
-------------------

By default, monitoring is disabled. You can enable it globally:

.. code-block:: python

   from routilux.monitoring import MonitoringRegistry

   # Enable monitoring globally
   MonitoringRegistry.enable()

   # Disable monitoring when not needed
   MonitoringRegistry.disable()

   # Check if monitoring is enabled
   if MonitoringRegistry.is_enabled():
       print("Monitoring is active")

.. note::
   Monitoring must be enabled **before** starting workflow execution to collect data from that execution.

HTTP API Server
---------------

Starting the Server
~~~~~~~~~~~~~~~~~~~

The HTTP API server provides REST endpoints for monitoring and debugging. Start it using uvicorn:

.. code-block:: bash

   # Start the API server
   uvicorn routilux.api.main:app --host 127.0.0.1 --port 8765

The server will be available at ``http://127.0.0.1:8765``

API Endpoints
~~~~~~~~~~~~~

Health Check
^^^^^^^^^^^^

Check if the API server is running:

.. code-block:: bash

   GET /api/health

Response:

.. code-block:: json

   {
     "status": "healthy"
   }

Flow Management
^^^^^^^^^^^^^^^

List all flows:

.. code-block:: bash

   GET /api/flows

Get a specific flow:

.. code-block:: bash

   GET /api/flows/{flow_id}

Create a flow:

.. code-block:: bash

   POST /api/flows
   Content-Type: application/json

   {
     "flow_id": "my_flow"
   }

Job Execution
^^^^^^^^^^^^^

Start a job execution:

.. code-block:: bash

   POST /api/jobs
   Content-Type: application/json

   {
     "flow_id": "my_flow",
     "entry_routine_id": "start",
     "entry_slot": "trigger",
     "entry_params": {
       "data": "value"
     }
   }

Response:

.. code-block:: json

   {
     "job_id": "job_abc123",
     "flow_id": "my_flow",
     "status": "running"
   }

List all jobs:

.. code-block:: bash

   GET /api/jobs

Get job details:

.. code-block:: bash

   GET /api/jobs/{job_id}

Get job metrics:

.. code-block:: bash

   GET /api/jobs/{job_id}/metrics

Response:

.. code-block:: json

   {
     "job_id": "job_abc123",
     "flow_id": "my_flow",
     "status": "completed",
     "start_time": "2025-01-15T10:30:00Z",
     "end_time": "2025-01-15T10:30:05Z",
     "total_routines": 5,
     "completed_routines": 5,
     "failed_routines": 0,
     "total_events": 12,
     "duration_ms": 5234
   }

Get execution trace:

.. code-block:: bash

   GET /api/jobs/{job_id}/trace?limit=100

Response:

.. code-block:: json

   {
     "total": 12,
     "events": [
       {
         "event_id": "evt_1",
         "job_id": "job_abc123",
         "routine_id": "start",
         "event_type": "routine_start",
         "timestamp": "2025-01-15T10:30:00.123Z",
         "data": {},
         "duration": null,
         "status": "running"
       },
       ...
     ]
   }

Breakpoints
^^^^^^^^^^^

List breakpoints for a job:

.. code-block:: bash

   GET /api/jobs/{job_id}/breakpoints

Set a breakpoint:

.. code-block:: bash

   POST /api/jobs/{job_id}/breakpoints
   Content-Type: application/json

   {
     "routine_id": "process_data",
     "slot_name": "trigger",
     "condition": "data['value'] > 100"
   }

Delete a breakpoint:

.. code-block:: bash

   DELETE /api/jobs/{job_id}/breakpoints/{breakpoint_id}

Debug Controls
^^^^^^^^^^^^^^

Pause a running job:

.. code-block:: bash

   POST /api/jobs/{job_id}/pause

Resume a paused job:

.. code-block:: bash

   POST /api/jobs/{job_id}/resume

Cancel a job:

.. code-block:: bash

   POST /api/jobs/{job_id}/cancel

Step over next routine:

.. code-block:: bash

   POST /api/jobs/{job_id}/debug/step_over

Step into routine:

.. code-block:: bash

   POST /api/jobs/{job_id}/debug/step_into

Get debug variables:

.. code-block:: bash

   GET /api/jobs/{job_id}/debug/variables

Response:

.. code-block:: json

   {
     "variables": {
       "local": {
         "input_data": "value",
         "processed": true
       },
       "shared": {
         "counter": 5
       }
     }
   }

Get call stack:

.. code-block:: bash

   GET /api/jobs/{job_id}/debug/call_stack

Response:

.. code-block:: json

   {
     "frames": [
       {
         "routine_id": "process_data",
         "slot_name": "trigger",
         "line": 42
       },
       {
         "routine_id": "validate",
         "slot_name": "trigger",
         "line": 15
       }
     ]
   }

WebSocket API
-------------

The WebSocket API provides real-time event streaming and interactive debugging.

Job Monitoring
~~~~~~~~~~~~~~

Connect to monitor job events:

.. code-block:: javascript

   const ws = new WebSocket('ws://127.0.0.1:8765/api/ws/jobs/{job_id}/monitor');

   ws.onmessage = (event) => {
     const data = JSON.parse(event.data);
     console.log('Event:', data);

     // Event types:
     // - routine_start: A routine started execution
     // - routine_complete: A routine completed successfully
     // - routine_error: A routine encountered an error
     // - breakpoint_hit: A breakpoint was triggered
     // - job_paused: Job was paused
     // - job_resumed: Job was resumed
     // - job_completed: Job finished execution
   };

Event types include:

* ``routine_start``: A routine started execution
* ``routine_complete``: A routine completed successfully
* ``routine_error``: A routine encountered an error
* ``breakpoint_hit``: A breakpoint was triggered
* ``job_paused``: Job was paused
* ``job_resumed``: Job was resumed
* ``job_completed``: Job finished execution

Debug Session
~~~~~~~~~~~~~

Connect to an interactive debug session:

.. code-block:: javascript

   const ws = new WebSocket('ws://127.0.0.1:8765/api/ws/jobs/{job_id}/debug');

   // Send debug commands
   ws.send(JSON.stringify({
     command: 'step_over'
   }));

   ws.send(JSON.stringify({
     command: 'get_variables'
   }));

   ws.send(JSON.stringify({
     command: 'set_variable',
     variable: 'counter',
     value: 10
   }));

Available debug commands:

* ``step_over``: Step over the next routine
* ``step_into``: Step into the next routine
* ``continue``: Continue execution
* ``get_variables``: Get current variables
* ``set_variable``: Set a variable value
* ``get_call_stack``: Get the current call stack

Flow Monitoring
~~~~~~~~~~~~~~~

Monitor all jobs in a flow:

.. code-block:: javascript

   const ws = new WebSocket('ws://127.0.0.1:8765/api/ws/flows/{flow_id}/monitor');

   ws.onmessage = (event) => {
     const data = JSON.parse(event.data);
     console.log('Flow event:', data);
   };

Using Monitoring in Python
---------------------------

Direct API Access
~~~~~~~~~~~~~~~~~

You can also access monitoring features directly from Python:

.. code-block:: python

   from routilux.monitoring import MonitoringRegistry
   from routilux import Flow, Routine

   # Enable monitoring
   MonitoringRegistry.enable()

   # Create and execute a flow
   flow = Flow("my_flow")

   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.add_slot("trigger", handler=self.process)

       def process(self, **kwargs):
           # This execution will be monitored
           return {"result": "success"}

   flow.add_routine(MyRoutine(), "r1")
   job_state = flow.execute("r1")

   # Access monitoring data
   registry = MonitoringRegistry.get_instance()
   collector = registry.monitor_collector

   # Get metrics
   metrics = collector.get_metrics(job_state.job_id)
   print(f"Duration: {metrics['duration_ms']}ms")
   print(f"Events: {metrics['total_events']}")

   # Get execution trace
   trace = collector.get_execution_trace(job_state.job_id)
   for event in trace:
       print(f"{event['event_type']}: {event['routine_id']}")

   # Get per-routine metrics
   routine_metrics = collector.get_routine_metrics(job_state.job_id, "r1")
   print(f"R1 duration: {routine_metrics['duration_ms']}ms")

Breakpoint Conditions
~~~~~~~~~~~~~~~~~~~~~

Breakpoints support conditional expressions:

.. code-block:: python

   from routilux.monitoring import MonitoringRegistry

   MonitoringRegistry.enable()
   registry = MonitoringRegistry.get_instance()
   breakpoint_manager = registry.breakpoint_manager

   # Set a breakpoint with a condition
   breakpoint_manager.set_breakpoint(
       job_id="job_abc123",
       routine_id="process_data",
       slot_name="trigger",
       condition="data.get('value', 0) > 100"  # Only break if value > 100
   )

   # Set a breakpoint on any error
   breakpoint_manager.set_breakpoint(
       job_id="job_abc123",
       routine_id="risky_operation",
       slot_name="trigger",
       condition="True"  # Always break
   )

Performance Considerations
--------------------------

Memory Management
~~~~~~~~~~~~~~~~~

The monitoring system uses ring buffers to prevent unbounded memory growth:

.. code-block:: python

   from routilux.monitoring import MonitoringRegistry

   MonitoringRegistry.enable()
   registry = MonitoringRegistry.get_instance()
   collector = registry.monitor_collector

   # Configure maximum events per job (default: 1000)
   collector.set_max_events_per_job(500)

When the buffer is full, oldest events are automatically dropped.

Event Queue Management
~~~~~~~~~~~~~~~~~~~~~~

WebSocket connections use bounded queues (max 100 events) to prevent memory issues:

.. code-block:: python

   from routilux.monitoring.event_manager import get_event_manager

   event_manager = get_event_manager()

   # Check queue status
   status = event_manager.get_status("job_abc123")
   print(f"Subscribers: {status['subscriber_count']}")
   print(f"Queue size: {status['queue_size']}")
   print(f"Queue capacity: {status['max_size']}")

Best Practices
--------------

1. **Enable monitoring only when needed**: Disable monitoring in production unless you're debugging
2. **Use conditional breakpoints**: Set conditions to break only on specific scenarios
3. **Limit event retention**: Configure ``max_events_per_job`` based on your needs
4. **Clean up old jobs**: Periodically remove old job data to prevent memory growth
5. **Use WebSocket for real-time monitoring**: More efficient than polling HTTP endpoints
6. **Handle connection failures**: Implement reconnection logic for WebSocket clients

Example: Complete Monitoring Setup
-----------------------------------

.. code-block:: python

   from routilux import Flow, Routine
   from routilux.monitoring import MonitoringRegistry
   import httpx
   import asyncio

   async def monitor_workflow():
       # Enable monitoring
       MonitoringRegistry.enable()

       # Create workflow
       flow = Flow("data_processing")

       class Ingest(Routine):
           def __init__(self):
               super().__init__()
               self.add_slot("trigger", handler=self.process)

           def process(self, data, **kwargs):
               self.emit("data_ingested", count=len(data))
               return {"data": data}

       class Process(Routine):
           def __init__(self):
               super().__init__()
               self.add_slot("data_ingested", handler=self.process)

           def process(self, data, **kwargs):
               result = [x * 2 for x in data]
               self.emit("data_processed", result=result)
               return {"result": result}

       class Validate(Routine):
           def __init__(self):
               super().__init__()
               self.add_slot("data_processed", handler=self.validate)

           def validate(self, result, **kwargs):
               is_valid = all(x > 0 for x in result)
               return {"valid": is_valid}

       flow.add_routine(Ingest(), "ingest")
       flow.add_routine(Process(), "process")
       flow.add_routine(Validate(), "validate")

       flow.connect("ingest", "data_ingested", "process", "data_ingested")
       flow.connect("process", "data_processed", "validate", "data_processed")

       # Start API server (in production, use uvicorn directly)
       # In a separate terminal: uvicorn routilux.api.main:app --port 8765

       # Use HTTP API to start job
       async with httpx.AsyncClient() as client:
           # Start job
           response = await client.post(
               "http://127.0.0.1:8765/api/jobs",
               json={
                   "flow_id": "data_processing",
                   "entry_routine_id": "ingest",
                   "entry_slot": "trigger",
                   "entry_params": {"data": [1, 2, 3, 4, 5]}
               }
           )
           job_id = response.json()["job_id"]
           print(f"Started job: {job_id}")

           # Wait for execution
           await asyncio.sleep(2)

           # Get metrics
           response = await client.get(
               f"http://127.0.0.1:8765/api/jobs/{job_id}/metrics"
           )
           metrics = response.json()
           print(f"Status: {metrics['status']}")
           print(f"Duration: {metrics['duration_ms']}ms")
           print(f"Events: {metrics['total_events']}")

           # Get trace
           response = await client.get(
               f"http://127.0.0.1:8765/api/jobs/{job_id}/trace"
           )
           trace_data = response.json()
           print(f"Trace events: {len(trace_data['events'])}")

   # Run the monitoring example
   asyncio.run(monitor_workflow())

Troubleshooting
---------------

Monitoring Not Collecting Data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem**: No metrics or traces are being collected.

**Solution**: Ensure monitoring is enabled **before** executing the flow:

.. code-block:: python

   MonitoringRegistry.enable()  # Enable first
   job_state = flow.execute("r1")  # Then execute

Breakpoints Not Triggering
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem**: Breakpoints are not being hit.

**Solutions**:

1. Check the breakpoint condition syntax
2. Ensure the routine_id and slot_name match exactly
3. Verify the job is still running when breakpoints are set

WebSocket Connection Fails
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem**: Cannot connect to WebSocket endpoint.

**Solutions**:

1. Ensure the API server is running
2. Check the job_id exists
3. Verify WebSocket support is enabled in your HTTP client

High Memory Usage
~~~~~~~~~~~~~~~~~

**Problem**: Memory usage grows over time.

**Solutions**:

1. Reduce ``max_events_per_job`` limit
2. Clear old job data periodically
3. Disable monitoring when not needed
4. Use WebSocket instead of polling for better efficiency

.. code-block:: python

   # Reduce memory usage
   collector = registry.monitor_collector
   collector.set_max_events_per_job(100)

   # Clear old job data
   job_store.remove_old_jobs(max_age_seconds=3600)
