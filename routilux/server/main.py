"""
FastAPI main application.

This is the entry point for the Routilux monitoring and flow builder API.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from routilux.server.middleware.auth import RequireAuth
from routilux.server.routes import (
    breakpoints,
    discovery,
    execute,
    flows,
    health,
    jobs,
    objects,
    runtimes,
    websocket,
    workers,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    # Enable monitoring once at startup
    from routilux.monitoring.registry import MonitoringRegistry

    MonitoringRegistry.enable()

    # Initialize default runtime in registry
    from routilux.monitoring.runtime_registry import RuntimeRegistry

    runtime_registry = RuntimeRegistry.get_instance()
    # Create default runtime if it doesn't exist
    runtime_registry.get_or_create_default(thread_pool_size=0)
    
    # Initialize global event publisher for sync-to-async bridge
    # This ensures events from sync contexts can be published efficiently
    from routilux.monitoring.execution_hooks import _ensure_event_publisher
    _ensure_event_publisher()

    if os.getenv("ROUTILUX_DEBUGGER_MODE") == "true":
        print("🔧 Debugger mode enabled - registering test flows...")
        await register_debugger_flows()
        print("✓ Test flows registered")

    yield

    # Shutdown
    print("🛑 Application shutting down...")
    # Note: Event publisher thread is daemon, will exit with main process


def _setup_examples_path():
    """Setup examples directory in sys.path for DSL loading support.

    This allows flows to be created from DSL that references example routines.
    Should be called once during module initialization.
    """
    import sys
    from pathlib import Path

    examples_dir = str(Path(__file__).parent.parent.parent / "examples")
    if examples_dir not in sys.path:
        sys.path.insert(0, examples_dir)


# Setup examples path once at module level
_setup_examples_path()


async def register_debugger_flows():
    """Register test flows for debugger"""
    # Examples path already set up at module level

    # Import flow creators
    from debugger_test_app import (
        create_branching_flow,
        create_complex_flow,
        create_error_flow,
        create_linear_flow,
    )

    from routilux.server.dependencies import get_flow_registry

    flow_registry = get_flow_registry()

    # Monitoring already enabled in lifespan()
    # Create and register flows
    linear_flow, _ = create_linear_flow()
    flow_registry.register(linear_flow)
    flow_registry.register_by_name(linear_flow.flow_id, linear_flow)
    print(f"  ✓ Registered: {linear_flow.flow_id}")

    branch_flow, _ = create_branching_flow()
    flow_registry.register(branch_flow)
    flow_registry.register_by_name(branch_flow.flow_id, branch_flow)
    print(f"  ✓ Registered: {branch_flow.flow_id}")

    complex_flow, _ = create_complex_flow()
    flow_registry.register(complex_flow)
    flow_registry.register_by_name(complex_flow.flow_id, complex_flow)
    print(f"  ✓ Registered: {complex_flow.flow_id}")

    error_flow, _ = create_error_flow()
    flow_registry.register(error_flow)
    flow_registry.register_by_name(error_flow.flow_id, error_flow)
    print(f"  ✓ Registered: {error_flow.flow_id}")


app = FastAPI(
    title="Routilux API",
    description="Monitoring, debugging, and flow builder API for Routilux",
    version="0.11.0",
    lifespan=lifespan,
)

# CORS middleware for frontend access
# Security: Default to localhost-only, require explicit configuration for production
allowed_origins_env = os.getenv("ROUTILUX_CORS_ORIGINS", "")

if not allowed_origins_env:
    # Default: localhost only (development-friendly but secure)
    allow_origins_list = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]
elif allowed_origins_env == "*":
    # Explicit wildcard (user must set this intentionally)
    import warnings

    warnings.warn(
        "CORS is set to allow all origins (*). This is insecure for production. "
        "Consider restricting to specific origins.",
        UserWarning,
    )
    allow_origins_list = ["*"]
else:
    # Comma-separated list of allowed origins
    allow_origins_list = [
        origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip middleware for response compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Setup rate limiting
from routilux.server.middleware.rate_limit import setup_rate_limiting  # noqa: E402

setup_rate_limiting(app)

# Register exception handlers
from fastapi.exceptions import RequestValidationError  # noqa: E402
from starlette.exceptions import HTTPException  # noqa: E402

from routilux.server.middleware.error_handler import (  # noqa: E402
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# =============================================================================
# API v1 Routes (Unified Architecture)
# =============================================================================
# All API endpoints are under /api/v1 prefix for consistency and clarity

app.include_router(workers.router, prefix="/api/v1", tags=["workers"])
app.include_router(jobs.router, prefix="/api/v1", tags=["jobs"])
app.include_router(execute.router, prefix="/api/v1", tags=["execute"])
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(flows.router, prefix="/api/v1", tags=["flows"])
app.include_router(breakpoints.router, prefix="/api/v1", tags=["breakpoints"])
app.include_router(websocket.router, prefix="/api/v1", tags=["websocket"])
app.include_router(discovery.router, prefix="/api/v1", tags=["discovery"])
app.include_router(objects.router, prefix="/api/v1/factory", tags=["factory"])
app.include_router(runtimes.router, prefix="/api/v1", tags=["runtimes"])


@app.get("/", dependencies=[RequireAuth])
def root():
    """
    Root endpoint.

    **Overview**:
    Returns basic information about the Routilux API, including version, description,
    and key endpoint paths. Use this to verify API connectivity and discover available
    endpoints.

    **Endpoint**: `GET /`

    **Use Cases**:
    - Verify API connectivity
    - Check API version
    - Discover endpoint paths
    - Health check for API availability

    **Request Example**:
    ```
    GET /
    ```

    **Response Example**:
    ```json
    {
      "name": "Routilux API",
      "version": "0.11.0",
      "description": "Monitoring, debugging, and flow builder API",
      "api_version": "v1",
      "endpoints": {
        "v1": "/api/v1",
        "health": "/api/v1/health/live",
        "docs": "/docs"
      }
    }
    ```

    **Response Fields**:
    - `name`: API name
    - `version`: API version number
    - `description`: API description
    - `api_version`: Current API version identifier
    - `endpoints`: Key endpoint paths

    **Authentication**:
    - Requires API key if `ROUTILUX_API_KEY_ENABLED=true`
    - Use `X-API-Key` header for authentication

    **Related Endpoints**:
    - GET /api/v1/health/live - Liveness probe
    - GET /api/v1/health/ready - Readiness probe
    - GET /docs - Interactive API documentation (Swagger UI)

    Returns:
        dict: API information with version and endpoint paths

    Raises:
        HTTPException: 401 if authentication fails
    """




# OpenAPI: document X-API-Key so Swagger UI shows Authorize
_original_openapi = app.openapi


def _openapi_with_x_api_key():
    schema = _original_openapi()
    schema.setdefault("components", {})
    schema["components"].setdefault("securitySchemes", {})
    schema["components"]["securitySchemes"]["X-API-Key"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "API key. Required when ROUTILUX_API_KEY_ENABLED=true; ignored when false.",
    }
    return schema


app.openapi = _openapi_with_x_api_key


if __name__ == "__main__":
    import os

    import uvicorn

    # Read configuration from environment variables
    # Support both PORT (common convention) and ROUTILUX_API_PORT (specific)
    host = os.getenv("ROUTILUX_API_HOST", "0.0.0.0")
    port = int(os.getenv("ROUTILUX_API_PORT", os.getenv("PORT", "20555")))
    reload = os.getenv("ROUTILUX_API_RELOAD", "true").lower() == "true"

    uvicorn.run(
        "routilux.server.main:app",
        host=host,
        port=port,
        reload=reload,
    )
