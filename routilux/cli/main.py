"""Main CLI entry point using click framework."""

import click
from pathlib import Path

# Import commands
from routilux.cli.commands.run import run
from routilux.cli.commands.server import server
# from routilux.cli.commands.list import list_cmd
# from routilux.cli.commands.validate import validate
# from routilux.cli.commands.init import initialize


@click.group()
@click.version_option(version="0.1.0")
@click.option(
    "--routines-dir",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Additional directories to scan for routines (can be specified multiple times)",
)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to configuration file",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output")
@click.pass_context
def cli(ctx, routines_dir, config, verbose, quiet):
    """Routilux workflow CLI for running and managing routines and flows."""
    ctx.ensure_object(dict)
    ctx.obj["routines_dirs"] = list(routines_dir) if routines_dir else []
    ctx.obj["config"] = config
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet


# Add commands to CLI
cli.add_command(run)
cli.add_command(server)


@cli.command()
def list_cmd():
    """List available routines or flows."""
    click.echo("list command - to be implemented")


@cli.command()
def validate():
    """Validate a workflow DSL file."""
    click.echo("validate command - to be implemented")


@cli.command()
def init():
    """Initialize a new routilux project."""
    click.echo("init command - to be implemented")


def main():
    """Entry point for console script."""
    cli(obj={})


if __name__ == "__main__":
    main()
