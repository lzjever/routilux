HTTP API and WebSocket
======================

Routilux provides a comprehensive HTTP REST API and WebSocket interface for monitoring,
debugging, and building workflows. This optional feature requires the API extras:

.. code-block:: bash

   pip install routilux[api]

.. warning:: **Production Security Required**

   **ALWAYS enable API key authentication in production environments.** Without authentication,
   anyone can access, modify, or delete your flows and jobs. See the Security section below.

Quick Start
-----------

Start the API server:

.. code-block:: bash

   # Development mode (with authentication)
   ROUTILUX_API_KEY_ENABLED=true \
   ROUTILUX_API_KEY=your-secret-key-here \
   python -m routilux.api.main

The API will be available at:

* **HTTP API**: ``http://localhost:20555/api``
* **Interactive docs (Swagger UI)**: ``http://localhost:20555/docs``
* **Alternative docs (ReDoc)**: ``http://localhost:20555/redoc``

.. note:: **Default Port**

   The API server runs on port **20555** by default. You can change this with the
   ``ROUTILUX_API_PORT`` environment variable.

Security Configuration
----------------------

API Key Authentication
~~~~~~~~~~~~~~~~~~~~~~

.. warning:: **CRITICAL: Enable Authentication in Production**

   The API server supports **all-or-nothing authentication**:
   - When ``ROUTILUX_API_KEY_ENABLED=true``, **ALL endpoints** (REST and WebSocket) require a valid API key
   - When ``ROUTILUX_API_KEY_ENABLED=false``, **ALL endpoints are public**

   There is **no mixed mode**. For production, **always** set ``ROUTILUX_API_KEY_ENABLED=true``.

Enable API key authentication with environment variables:

.. code-block:: bash

   # Enable with a single API key
   export ROUTILUX_API_KEY_ENABLED=true
   export ROUTILUX_API_KEY=your-secret-key-here

   # Or enable with multiple API keys (comma-separated)
   export ROUTILUX_API_KEY_ENABLED=true
   export ROUTILUX_API_KEYS=key1,key2,key3

   python -m routilux.api.main

Using API Keys
~~~~~~~~~~~~~~

Once authentication is enabled, clients must provide the API key:

**For REST API (HTTP)**:

.. code-block:: bash

   # Using curl
   curl -H "X-API-Key: your-secret-key-here" http://localhost:20555/api/flows

   # Using Python requests
   import requests
   headers = {"X-API-Key": "your-secret-key-here"}
   response = requests.get("http://localhost:20555/api/flows", headers=headers)

**For WebSocket**:

.. code-block:: javascript

   // JavaScript/WebSocket API
   const ws = new WebSocket("ws://localhost:20555/api/ws/jobs/{job_id}/monitor?api_key=your-secret-key-here");

.. code-block:: python

   # Python with websockets library
   import asyncio
   import websockets

   async def monitor_job():
       uri = "ws://localhost:20555/api/ws/jobs/{job_id}/monitor?api_key=your-secret-key-here"
       async with websockets.connect(uri) as websocket:
           while True:
               data = await websocket.recv()
               print(data)

   asyncio.run(monitor_job())

Authentication Errors
~~~~~~~~~~~~~~~~~~~~~~

If authentication fails:

* **401 Unauthorized** - API key is missing when ``ROUTILUX_API_KEY_ENABLED=true``
* **403 Forbidden** - API key is invalid
* **WebSocket close code 1008** - API key is missing or invalid (WebSocket only)

Example error response:

.. code-block:: json

   {
     "detail": {
       "error": "authentication_required",
       "message": "API key is required. Provide it in the X-API-Key header."
     }
   }

.. danger:: **Never Commit API Keys to Version Control**

   Use environment variables or secret management systems. Never hardcode API keys
   in your source code or commit them to git.

   Add to your ``.gitignore``:

   .. code-block:: text

      .env
      .env.local

CORS Configuration
~~~~~~~~~~~~~~~~~~

By default, CORS is restricted to localhost only for security. To allow other origins:

.. code-block:: bash

   # Allow specific origins
   export ROUTILUX_CORS_ORIGINS="https://example.com,https://app.example.com"

   # Development only: Allow all origins (WARNING: INSECURE!)
   export ROUTILUX_CORS_ORIGINS="*"

.. warning:: **CORS Wildcard is Insecure**

   Setting ``ROUTILUX_CORS_ORIGINS="*"`` allows any website to make requests to your API.
   Only use this for local development. Never use in production.

Rate Limiting
~~~~~~~~~~~~

Enable rate limiting to prevent abuse:

.. code-block:: bash

   export ROUTILUX_RATE_LIMIT_ENABLED=true
   export ROUTILUX_RATE_LIMIT_PER_MINUTE=60

Rate limiting is applied per IP address. When the limit is exceeded, clients receive
a ``429 Too Many Requests`` response.

REST API Endpoints
------------------

All REST endpoints are prefixed with ``/api`` and require authentication when enabled.

Health Check
~~~~~~~~~~~~

.. code-block:: http

   GET /api/health

Returns API health status:

.. code-block:: json

   {
     "status": "healthy",
     "auth_required": true,
     "monitoring": {
       "enabled": true
     },
     "stores": {
       "accessible": true,
       "flow_count": 3,
       "job_count": 15
     },
     "version": "0.10.0"
   }

Flow Management
~~~~~~~~~~~~~~~

List all flows:

.. code-block:: http

   GET /api/flows
   X-API-Key: your-secret-key-here

Get flow details:

.. code-block:: http

   GET /api/flows/{flow_id}
   X-API-Key: your-secret-key-here

Create a flow:

.. code-block:: http

   POST /api/flows
   X-API-Key: your-secret-key-here
   Content-Type: application/json

   {
     "flow_id": "my_flow",
     "dsl": "flow_id: my_flow\nroutines:\n  source:\n    class: DataSource",
     "dsl_dict": {...}
   }

Export flow as DSL:

.. code-block:: http

   GET /api/flows/{flow_id}/dsl?format=yaml
   X-API-Key: your-secret-key-here

Delete a flow:

.. code-block:: http

   DELETE /api/flows/{flow_id}
   X-API-Key: your-secret-key-here

Job Management
~~~~~~~~~~~~~~

List all jobs:

.. code-block:: http

   GET /api/jobs
   X-API-Key: your-secret-key-here

Get job details:

.. code-block:: http

   GET /api/jobs/{job_id}
   X-API-Key: your-secret-key-here

Start a job:

.. code-block:: http

   POST /api/jobs
   X-API-Key: your-secret-key-here
   Content-Type: application/json

   {
     "flow_id": "my_flow",
     "runtime_id": "production",
     "timeout": 3600.0
   }

.. note:: **Runtime Selection**

   The ``runtime_id`` field is optional. If not specified, the default runtime is used.
   Use ``GET /api/runtimes`` to see available runtimes. See :ref:`runtime-management` for details.

Pause a job:

.. code-block:: http

   POST /api/jobs/{job_id}/pause
   X-API-Key: your-secret-key-here

Resume a job:

.. code-block:: http

   POST /api/jobs/{job_id}/resume
   X-API-Key: your-secret-key-here

Cancel a job:

.. code-block:: http

   POST /api/jobs/{job_id}/cancel
   X-API-Key: your-secret-key-here

Breakpoint Management
~~~~~~~~~~~~~~~~~~~~~

List breakpoints for a job:

.. code-block:: http

   GET /api/breakpoints/{job_id}
   X-API-Key: your-secret-key-here

Set a breakpoint:

.. code-block:: http

   POST /api/breakpoints/{job_id}
   X-API-Key: your-secret-key-here
   Content-Type: application/json

   {
     "routine_id": "processor",
     "condition": "data.value > 100"
   }

Clear a breakpoint:

.. code-block:: http

   DELETE /api/breakpoints/{job_id}/{breakpoint_id}
   X-API-Key: your-secret-key-here

Debug Operations
~~~~~~~~~~~~~~~~

Get debug session state:

.. code-block:: http

   GET /api/debug/{job_id}
   X-API-Key: your-secret-key-here

Step execution:

.. code-block:: http

   POST /api/debug/{job_id}/step
   X-API-Key: your-secret-key-here

Continue execution:

.. code-block:: http

   POST /api/debug/{job_id}/continue
   X-API-Key: your-secret-key-here

Evaluate expression:

.. code-block:: http

   POST /api/debug/{job_id}/evaluate
   X-API-Key: your-secret-key-here
   Content-Type: application/json

   {
     "expression": "data.value * 2",
     "variables": {"data": {"value": 42}}
   }

Runtime Management
~~~~~~~~~~~~~~~~~~~

.. _runtime-management:

List all runtimes:

.. code-block:: http

   GET /api/runtimes
   X-API-Key: your-secret-key-here

Get runtime details:

.. code-block:: http

   GET /api/runtimes/{runtime_id}
   X-API-Key: your-secret-key-here

Create a new runtime:

.. code-block:: http

   POST /api/runtimes
   X-API-Key: your-secret-key-here
   Content-Type: application/json

   {
     "runtime_id": "production",
     "thread_pool_size": 20,
     "is_default": false
   }

.. important:: **thread_pool_size Parameter**

   * **thread_pool_size=0** (recommended): Uses GlobalJobManager's shared thread pool
     (100 threads by default). All Runtime instances with this setting share the same pool.
     This is the default and recommended configuration for most scenarios.

   * **thread_pool_size>0**: Creates an independent thread pool for this Runtime.
     Useful when you need resource isolation between different Runtime instances.

   See :doc:`user_guide/runtime` for detailed guidance on thread pool sizing.

Monitoring Endpoints
~~~~~~~~~~~~~~~~~~~~

Get flow metrics:

.. code-block:: http

   GET /api/monitor/flows/{flow_id}/metrics
   X-API-Key: your-secret-key-here

Get job metrics:

.. code-block:: http

   GET /api/monitor/jobs/{job_id}/metrics
   X-API-Key: your-secret-key-here

WebSocket Endpoints
-------------------

WebSocket endpoints provide real-time event streaming. All require API key via
query parameter when authentication is enabled.

Job Monitor WebSocket
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   WS /api/ws/jobs/{job_id}/monitor?api_key=your-secret-key-here

Streams real-time events for a specific job:

.. code-block:: json

   {
     "type": "routine_start",
     "job_id": "...",
     "routine_id": "processor",
     "timestamp": "2024-01-18T12:00:00Z"
   }

Job Debug WebSocket
~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   WS /api/ws/jobs/{job_id}/debug?api_key=your-secret-key-here

Streams debug-relevant events (routine_start, routine_end, slot_call).

Flow Monitor WebSocket
~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   WS /api/ws/flows/{flow_id}/monitor?api_key=your-secret-key-here

Aggregates events from all jobs belonging to a flow.

Generic WebSocket
~~~~~~~~~~~~~~~~~

.. code-block:: text

   WS /api/ws?api_key=your-secret-key-here

Allows dynamic subscription to multiple jobs/flows.

Client messages:

.. code-block:: json

   // Subscribe to a job
   {"type": "subscribe", "job_id": "..."}

   // Unsubscribe from a job
   {"type": "unsubscribe", "job_id": "..."}

Environment Variables Reference
--------------------------------

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Variable
     - Description
   * - ``ROUTILUX_API_HOST``
     - API server host (default: ``0.0.0.0``)
   * - ``ROUTILUX_API_PORT``
     - API server port (default: ``20555``)
   * - ``ROUTILUX_API_RELOAD``
     - Enable auto-reload (default: ``true``)
   * - ``ROUTILUX_API_KEY_ENABLED``
     - **Enable API key authentication** (default: ``false``)
   * - ``ROUTILUX_API_KEY``
     - Single API key for authentication
   * - ``ROUTILUX_API_KEYS``
     - Comma-separated list of API keys
   * - ``ROUTILUX_CORS_ORIGINS``
     - CORS allowed origins (default: localhost only)
   * - ``ROUTILUX_RATE_LIMIT_ENABLED``
     - Enable rate limiting (default: ``false``)
   * - ``ROUTILUX_RATE_LIMIT_PER_MINUTE``
     - Rate limit per minute (default: ``60``)
   * - ``ROUTILUX_DEBUGGER_MODE``
     - Enable debugger mode with test flows (default: ``false``)

Production Deployment
----------------------

.. warning:: **Production Checklist**

   Before deploying to production:

   1. **Enable Authentication**: Set ``ROUTILUX_API_KEY_ENABLED=true``
   2. **Use Strong API Keys**: Generate cryptographically random keys
   3. **Restrict CORS**: Set ``ROUTILUX_CORS_ORIGINS`` to specific origins
   4. **Enable Rate Limiting**: Set ``ROUTILUX_RATE_LIMIT_ENABLED=true``
   5. **Use HTTPS**: Always use HTTPS in production
   6. **Disable Reload**: Set ``ROUTILUX_API_RELOAD=false``
   7. **Bind to Specific Host**: Use ``ROUTILUX_API_HOST`` appropriately
   8. **Use Reverse Proxy**: Put API behind nginx/traefik for SSL termination

Example production startup:

.. code-block:: bash

   export ROUTILUX_API_KEY_ENABLED=true
   export ROUTILUX_API_KEY="generate-strong-random-key-here"
   export ROUTILUX_CORS_ORIGINS="https://your-domain.com"
   export ROUTILUX_RATE_LIMIT_ENABLED=true
   export ROUTILUX_RATE_LIMIT_PER_MINUTE=60
   export ROUTILUX_API_RELOAD=false
   export ROUTILUX_API_HOST=127.0.0.1

   gunicorn -w 4 -k uvicorn.workers.UvicornWorker \
       --bind 127.0.0.1:20555 \
       --access-logfile - \
       --error-logfile - \
       routilux.api.main:app

Docker Deployment Example
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: dockerfile

   FROM python:3.11-slim

   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt

   COPY . .

   # Non-root user for security
   RUN useradd -m -u 1000 routilux && \
       chown -R routilux:routilux /app
   USER routilux

   # Expose port (use reverse proxy for HTTPS)
   EXPOSE 20555

   # Health check
   HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
       CMD curl -f http://localhost:20555/api/health || exit 1

   CMD ["python", "-m", "routilux.api.main"]

.. code-block:: yaml

   # docker-compose.yml
   version: '3.8'
   services:
     routilux-api:
       build: .
       ports:
         - "127.0.0.1:20555:20555"  # Bind to localhost only
       environment:
         - ROUTILUX_API_KEY_ENABLED=true
         - ROUTILUX_API_KEY=${ROUTILUX_API_KEY}  # From .env file
         - ROUTILUX_CORS_ORIGINS=https://your-domain.com
         - ROUTILUX_RATE_LIMIT_ENABLED=true
         - ROUTILUX_API_RELOAD=false
       restart: unless-stopped

Next Steps
----------

* :doc:`quickstart` - Get started with Routilux
* :doc:`user_guide/monitoring` - Monitoring and debugging guide
* :doc:`user_guide/index` - Complete user guide
