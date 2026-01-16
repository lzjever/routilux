"""
FastAPI main application.

This is the entry point for the Routilux monitoring and flow builder API.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from routilux.api.routes import breakpoints, debug, flows, jobs, monitor, websocket


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    if os.getenv("ROUTILUX_DEBUGGER_MODE") == "true":
        print("🔧 Debugger mode enabled - registering test flows...")
        await register_debugger_flows()
        print("✓ Test flows registered")

    yield

    # Shutdown
    print("🛑 Application shutting down...")


async def register_debugger_flows():
    """Register test flows for debugger"""
    import sys
    from pathlib import Path

    # Add examples directory to path
    examples_dir = str(Path(__file__).parent.parent.parent / "examples")
    if examples_dir not in sys.path:
        sys.path.insert(0, examples_dir)

    # Import flow creators
    from debugger_test_app import (
        create_branching_flow,
        create_complex_flow,
        create_error_flow,
        create_linear_flow,
    )

    from routilux.monitoring.registry import MonitoringRegistry
    from routilux.monitoring.storage import flow_store

    # Enable monitoring
    MonitoringRegistry.enable()

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

# Add examples directory to sys.path for DSL loading support
# This allows flows to be created from DSL that references example routines
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

examples_dir = str(Path(__file__).parent.parent.parent / "examples")
if examples_dir not in sys.path:
    sys.path.insert(0, examples_dir)

# CORS middleware for frontend access
allowed_origins = os.getenv("ROUTILUX_CORS_ORIGINS", "*")

if allowed_origins == "*":
    allow_origins_list = ["*"]
else:
    allow_origins_list = [origin.strip() for origin in allowed_origins.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip middleware for response compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Include routers
app.include_router(flows.router, prefix="/api", tags=["flows"])
app.include_router(jobs.router, prefix="/api", tags=["jobs"])
app.include_router(breakpoints.router, prefix="/api", tags=["breakpoints"])
app.include_router(debug.router, prefix="/api", tags=["debug"])
app.include_router(monitor.router, prefix="/api", tags=["monitor"])
app.include_router(websocket.router, prefix="/api", tags=["websocket"])


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "name": "Routilux API",
        "version": "0.10.0",
        "description": "Monitoring, debugging, and flow builder API",
    }


@app.get("/api/health")
def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import os

    import uvicorn

    # Default configuration
    # Disable reload in test environment
    reload = os.getenv("ROUTILUX_API_RELOAD", "true").lower() == "true"

    uvicorn.run(
        "routilux.api.main:app",
        host="0.0.0.0",
        port=20555,
        reload=reload,  # Enable auto-reload in development
    )
