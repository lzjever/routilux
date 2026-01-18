Monitoring and Debugging
========================

Routilux provides comprehensive monitoring and debugging capabilities for production workflows.
All monitoring features are **disabled by default** with **zero overhead** when not enabled.

.. note:: **Zero Overhead**

   When monitoring is disabled (default), there is **no performance impact** on your
   workflows. Monitoring only activates when explicitly enabled.

.. warning:: **Production Security**

   If using the HTTP API for monitoring/debugging in production, **always enable API key
   authentication**. See :doc:`../http_api` for security configuration.

Enabling Monitoring
-------------------

**Method 1: Environment Variable**

.. code-block:: bash

   export ROUTILUX_ENABLE_MONITORING=true
   python your_app.py

**Method 2: Programmatic Enable**

.. code-block:: python

   from routilux.monitoring import MonitoringRegistry

   MonitoringRegistry.enable()

**Method 3: API Server (Auto-Enables)**

.. code-block:: bash

   # API server automatically enables monitoring on startup
   python -m routilux.api.main

Monitoring Features
-------------------

Once enabled, monitoring provides:

* **Execution Tracking**: Automatic tracking of all routine executions
* **Event Collection**: Real-time event streaming
* **Metrics Collection**: Performance metrics per routine and job
* **Breakpoint Support**: Conditional breakpoints for debugging
* **Debug Sessions**: Interactive debugging with step/control
* **WebSocket Streaming**: Real-time event push notifications

Execution Metrics
-----------------

Access execution metrics for jobs and routines:

.. code-block:: python

   from routilux.monitoring import MonitoringRegistry

   registry = MonitoringRegistry.get_instance()
   collector = registry.monitor_collector

   # Get job metrics
   metrics = collector.get_metrics(job_id)
   if metrics:
       print(f"Duration: {metrics.duration}")
       print(f"Total events: {metrics.total_events}")
       print(f"Slot calls: {metrics.total_slot_calls}")
       print(f"Event emits: {metrics.total_event_emits}")

   # Get routine metrics
   routine_metrics = collector.get_routine_metrics(job_id, routine_id)
   if routine_metrics:
       print(f"Executions: {routine_metrics.execution_count}")
       print(f"Errors: {routine_metrics.error_count}")

Execution Events
----------------

Monitor execution events in real-time:

.. code-block:: python

   from routilux.monitoring import get_event_manager

   event_manager = get_event_manager()

   # Subscribe to job events
   subscriber_id = await event_manager.subscribe(job_id)

   # Iterate over events
   async for event in event_manager.iter_events(subscriber_id):
       print(f"Event: {event['event_type']}")
       print(f"Data: {event}")

   # Unsubscribe when done
   await event_manager.unsubscribe(subscriber_id)

**Event Types**:

* ``routine_start`` - Routine execution started
* ``routine_end`` - Routine execution completed
* ``slot_call`` - Slot was called with data
* ``event_emit`` - Event was emitted
* ``error`` - Error occurred during execution

Breakpoints
-----------

Set conditional breakpoints to pause execution:

.. code-block:: python

   from routilux.monitoring import BreakpointManager

   manager = BreakpointManager.get_instance()

   # Set breakpoint on routine with condition
   breakpoint = manager.set_breakpoint(
       job_id="your-job-id",
       routine_id="processor",
       condition="data.value > 100"  # Python expression
   )

   # Remove breakpoint
   manager.remove_breakpoint(breakpoint.breakpoint_id)

   # List all breakpoints for a job
   breakpoints = manager.get_breakpoints("your-job-id")

.. note:: **Breakpoint Conditions**

   Breakpoint conditions are Python expressions evaluated in a secure sandbox.
   Available variables include:
   - ``slot_data`` - Current slot data
   - ``job_state`` - Current JobState
   - Any variables in slot_data

Debug Sessions
--------------

Interactive debugging with step/control:

.. code-block:: python

   from routilux.monitoring import DebugSessionStore

   store = DebugSessionStore.get_instance()

   # Get or create debug session
   session = store.get_or_create(job_id)

   # Step to next routine
   session.step()

   # Continue execution
   session.continue()

   # Get current call frame
   frame = session.get_current_frame()
   if frame:
       print(f"Current routine: {frame.routine_id}")
       print(f"Slot data: {frame.slot_data}")

   # Evaluate expression in current context
   result = session.evaluate("slot_data['input'][0] * 2")

WebSocket Monitoring
--------------------

Use WebSocket for real-time event streaming:

.. code-block:: python

   import asyncio
   import websockets

   async def monitor_job(job_id, api_key=None):
       uri = f"ws://localhost:20555/api/ws/jobs/{job_id}/monitor"
       if api_key:
           uri += f"?api_key={api_key}"

       async with websockets.connect(uri) as ws:
           while True:
               event = await ws.recv()
               print(f"Event: {event}")

   # Run monitor
   asyncio.run(monitor_job("job-id-here", "your-api-key"))

.. warning:: **WebSocket Authentication**

   When ``ROUTILUX_API_KEY_ENABLED=true``, WebSocket connections require
   ``api_key`` query parameter: ``ws://host/ws?api_key=your-key``

HTTP API Monitoring
-------------------

Use the REST API for monitoring:

.. code-block:: python

   import requests

   headers = {"X-API-Key": "your-api-key"}
   base_url = "http://localhost:20555/api"

   # Get job metrics
   response = requests.get(
       f"{base_url}/monitor/jobs/{job_id}/metrics",
       headers=headers
   )
   metrics = response.json()

   # Get flow metrics
   response = requests.get(
       f"{base_url}/monitor/flows/{flow_id}/metrics",
       headers=headers
   )
   flow_metrics = response.json()

Performance Considerations
---------------------------

Monitoring overhead depends on enabled features:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Feature
     - Overhead
   * - Disabled (default)
     - Zero overhead, no impact
   * - Metrics Collection
     - ~1-2% CPU, minimal memory
   * - Event Streaming
     - ~2-5% CPU, moderate memory for event buffer
   * - Breakpoints
     - ~5-10% CPU when active, minimal when inactive
   * - Debug Sessions
     - ~10-20% CPU when debugging, minimal otherwise

.. warning:: **High-Frequency Events**

   For workflows with high event frequency (>1000 events/second), event buffering
   can consume significant memory. Consider:
   - Reducing event frequency
   - Using sampling/filtering
   - Disabling full event tracking for production

Security Considerations
-----------------------

When exposing monitoring endpoints:

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Risk
     - Mitigation
   * - Unauthorized access
     - Enable ``ROUTILUX_API_KEY_ENABLED=true``
   * - Data exposure
     - Use HTTPS in production
   * - DoS attacks
     - Enable ``ROUTILUX_RATE_LIMIT_ENABLED=true``
   * - Resource exhaustion
     - Monitor memory usage, set limits

Production Checklist
---------------------

Before deploying monitoring to production:

1. **Enable Authentication**: ``ROUTILUX_API_KEY_ENABLED=true``
2. **Use Strong API Keys**: Generate cryptographically random keys
3. **Enable Rate Limiting**: ``ROUTILUX_RATE_LIMIT_ENABLED=true``
4. **Restrict CORS**: Set ``ROUTILUX_CORS_ORIGINS`` to specific origins
5. **Use HTTPS**: Always use HTTPS in production
6. **Monitor Resources**: Set up alerts for memory/CPU usage
7. **Limit Retention**: Configure event data retention policies
8. **Sample Events**: Consider event sampling for high-frequency workflows

Example: Complete Monitoring Setup
------------------------------------

.. code-block:: python

   from routilux import Flow, Routine, Runtime
   from routilux.monitoring import MonitoringRegistry, get_event_manager
   from routilux.monitoring.flow_registry import FlowRegistry
   import asyncio

   # Enable monitoring
   MonitoringRegistry.enable()

   # Define a simple routine
   class Processor(Routine):
       def __init__(self):
           super().__init__()
           self.input = self.add_slot("input")
           self.output = self.add_event("output", ["result"])

           def logic(slot_data, policy_message, job_state):
               data = slot_data.get("input", [{}])[0].get("data", "")
               result = f"Processed: {data}"
               self.emit("output", result=result)

           self.set_logic(logic)
           self.set_activation_policy(immediate_policy())

   # Create and register flow
   flow = Flow(flow_id="monitored_flow")
   processor = Processor()
   flow.add_routine(processor, "processor")
   flow.connect("processor", "output", "processor", "input")

   FlowRegistry.get_instance().register_by_name("monitored_flow", flow)

   # Execute
   runtime = Runtime(thread_pool_size=5)
   job_state = runtime.exec("monitored_flow", entry_params={"data": "test"})

   # Monitor execution
   async def monitor_execution():
       event_manager = get_event_manager()
       subscriber_id = await event_manager.subscribe(job_state.job_id)

       print("Monitoring execution...")
       async for event in event_manager.iter_events(subscriber_id):
           print(f"  {event['event_type']}: {event.get('routine_id', 'N/A')}")
           if event['event_type'] == 'routine_end':
               # Check if job is complete
               job = runtime.get_job(job_state.job_id)
               if job.is_completed():
                   break

       await event_manager.unsubscribe(subscriber_id)

   # Run monitoring
   asyncio.run(monitor_execution())

   # Get final metrics
   registry = MonitoringRegistry.get_instance()
   collector = registry.monitor_collector
   metrics = collector.get_metrics(job_state.job_id)

   if metrics:
       print(f"\nFinal Metrics:")
       print(f"  Duration: {metrics.duration}s")
       print(f"  Total events: {metrics.total_events}")
       print(f"  Slot calls: {metrics.total_slot_calls}")

   runtime.shutdown(wait=True)

See Also
--------

* :doc:`../http_api` - HTTP API and WebSocket monitoring
* :doc:`job_state` - JobState and execution tracking
* :doc:`runtime` - Runtime execution management
