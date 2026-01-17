"""
FastAPI main application.

This is the entry point for the Routilux monitoring and flow builder API.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from routilux.api.middleware.auth import RequireAuth
from routilux.api.routes import breakpoints, debug, discovery, flows, jobs, monitor, objects, websocket


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    # Enable monitoring once at startup
    from routilux.monitoring.registry import MonitoringRegistry

    MonitoringRegistry.enable()

    if os.getenv("ROUTILUX_DEBUGGER_MODE") == "true":
        print("🔧 Debugger mode enabled - registering test flows...")
        await register_debugger_flows()
        print("✓ Test flows registered")

    yield

    # Shutdown
    print("🛑 Application shutting down...")


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

    from routilux.monitoring.storage import flow_store

    # Monitoring already enabled in lifespan()
    # Create and register flows
    linear_flow, _ = create_linear_flow()
    flow_store.add(linear_flow)
    print(f"  ✓ Registered: {linear_flow.flow_id}")

    branch_flow, _ = create_branching_flow()
    flow_store.add(branch_flow)
    print(f"  ✓ Registered: {branch_flow.flow_id}")

    complex_flow, _ = create_complex_flow()
    flow_store.add(complex_flow)
    print(f"  ✓ Registered: {complex_flow.flow_id}")

    error_flow, _ = create_error_flow()
    flow_store.add(error_flow)
    print(f"  ✓ Registered: {error_flow.flow_id}")


app = FastAPI(
    title="Routilux API",
    description="Monitoring, debugging, and flow builder API for Routilux",
    version="0.10.0",
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
from routilux.api.middleware.rate_limit import setup_rate_limiting  # noqa: E402

setup_rate_limiting(app)

# Register exception handlers
from starlette.exceptions import HTTPException  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402

from routilux.api.middleware.error_handler import (  # noqa: E402
    general_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Include routers
app.include_router(flows.router, prefix="/api", tags=["flows"])
app.include_router(jobs.router, prefix="/api", tags=["jobs"])
app.include_router(breakpoints.router, prefix="/api", tags=["breakpoints"])
app.include_router(debug.router, prefix="/api", tags=["debug"])
app.include_router(monitor.router, prefix="/api", tags=["monitor"])
app.include_router(websocket.router, prefix="/api", tags=["websocket"])
app.include_router(discovery.router, prefix="/api", tags=["discovery"])
app.include_router(objects.router, prefix="/api", tags=["objects"])


@app.get("/", dependencies=[RequireAuth])
def root():
    """Root endpoint."""
    return {
        "name": "Routilux API",
        "version": "0.10.0",
        "description": "Monitoring, debugging, and flow builder API",
    }


@app.get("/api/health", dependencies=[RequireAuth])
def health():
    """Health check endpoint.

    Returns detailed health information including:
    - Overall status
    - Monitoring status
    - Store accessibility
    - Version information
    """
    from routilux.monitoring.registry import MonitoringRegistry
    from routilux.monitoring.storage import flow_store, job_store

    # Check monitoring status
    monitoring_enabled = MonitoringRegistry.is_enabled()

    # Check store accessibility
    try:
        flow_count = len(flow_store.list_all())
        job_count = len(job_store.list_all())
        stores_accessible = True
    except Exception:
        flow_count = None
        job_count = None
        stores_accessible = False

    from routilux.api.config import get_config

    config = get_config()
    return {
        "status": "healthy",
        "auth_required": config.api_key_enabled,
        "monitoring": {
            "enabled": monitoring_enabled,
        },
        "stores": {
            "accessible": stores_accessible,
            "flow_count": flow_count,
            "job_count": job_count,
        },
        "version": "0.10.0",
    }


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
        "routilux.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )
