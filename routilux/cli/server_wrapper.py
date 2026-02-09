"""Server wrapper for CLI mode.

Wraps the existing FastAPI server with CLI-specific configuration
including routine discovery and registration.
"""

import os
from pathlib import Path
from typing import List, Optional

from routilux.cli.discovery import discover_routines, get_default_routines_dirs
from routilux.tools.factory.factory import ObjectFactory


def start_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    routines_dirs: Optional[List[Path]] = None,
    reload: bool = False,
    log_level: str = "info",
):
    """Start the routilux HTTP server.

    Discovers routines from specified directories and starts the FastAPI server.

    Args:
        host: Host to bind to
        port: Port to bind to
        routines_dirs: Additional directories to scan for routines
        reload: Enable auto-reload for development
        log_level: Log level for uvicorn
    """
    # Gather routines directories
    all_dirs = list(routines_dirs or [])
    all_dirs.extend(get_default_routines_dirs())

    # Discover routines before starting server
    if all_dirs:
        print(f"Discovering routines from: {all_dirs}")
        factory = discover_routines(all_dirs, on_error="warn")
        routines = factory.list_available()
        print(f"Registered {len(routines)} routines")

    # Set environment variables for server
    os.environ["ROUTILUX_API_HOST"] = host
    os.environ["ROUTILUX_API_PORT"] = str(port)
    os.environ["ROUTILUX_API_RELOAD"] = str(reload).lower()

    # Store routines directories for server endpoints
    if all_dirs:
        os.environ["ROUTILUX_ROUTINES_DIRS"] = ":".join(str(d) for d in all_dirs)

    # Import and start server
    import uvicorn

    uvicorn.run(
        "routilux.server.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
    )
