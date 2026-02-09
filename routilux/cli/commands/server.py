"""Server command implementation."""

import click
from pathlib import Path


@click.group()
def server():
    """Manage the routilux HTTP server."""
    pass


@server.command("start")
@click.option(
    "--host",
    default="0.0.0.0",
    help="Host to bind to (default: 0.0.0.0)",
)
@click.option(
    "--port",
    default=8080,
    type=int,
    help="Port to bind to (default: 8080)",
)
@click.option(
    "--routines-dir",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Additional directories to scan for routines",
)
@click.option(
    "--reload",
    is_flag=True,
    help="Enable auto-reload for development",
)
@click.option(
    "--log-level",
    default="info",
    type=click.Choice(["debug", "info", "warning", "error", "critical"]),
    help="Log level for uvicorn (default: info)",
)
@click.pass_context
def start(ctx, host, port, routines_dir, reload, log_level):
    """Start the routilux HTTP server.

    Starts the FastAPI server with REST and WebSocket endpoints.
    Routines are automatically discovered from specified directories.
    """
    quiet = ctx.obj.get("quiet", False)
    verbose = ctx.obj.get("verbose", False)

    # Gather routines directories
    routines_dirs = list(routines_dir)
    routines_dirs.extend(ctx.obj.get("routines_dirs", []))

    if not quiet:
        click.echo(f"Starting routilux server on {host}:{port}")
        if routines_dirs:
            click.echo(f"Routines directories: {routines_dirs}")

    from routilux.cli.server_wrapper import start_server

    try:
        start_server(
            host=host,
            port=port,
            routines_dirs=routines_dirs if routines_dirs else None,
            reload=reload,
            log_level=log_level,
        )
    except KeyboardInterrupt:
        if not quiet:
            click.echo("\nServer stopped")
    except Exception as e:
        click.echo(f"Error starting server: {e}", err=True)
        raise click.Abort(1)


@server.command("stop")
def stop():
    """Stop the running routilux server (not yet implemented)."""
    click.echo("Stop command not yet implemented. Use Ctrl+C to stop the server.")


@server.command("status")
def status():
    """Check server status (not yet implemented)."""
    click.echo("Status command not yet implemented.")
