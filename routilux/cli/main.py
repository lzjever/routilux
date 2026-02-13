"""Main CLI entry point using click framework."""

from pathlib import Path

import click

from routilux import __version__

# Import commands
from routilux.cli.commands.completion import completion
from routilux.cli.commands.init import initialize
from routilux.cli.commands.job import job
from routilux.cli.commands.list import list_cmd
from routilux.cli.commands.run import run
from routilux.cli.commands.server import server
from routilux.cli.commands.validate import validate
from routilux.cli.config import get_config_value, load_config


@click.group()
@click.version_option(version=__version__)
@click.option(
    "--routines-dir",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Additional directories to scan for routines (can be specified multiple times)",
)
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to configuration file (supports TOML, YAML, JSON)",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output")
@click.pass_context
def cli(ctx, routines_dir, config, verbose, quiet):
    """Routilux workflow CLI for running and managing routines and flows.

    \b
    Examples:
        # Run a workflow
        $ routilux run --workflow flows/my_flow.yaml

        # Initialize a new project
        $ routilux init

        # Start the HTTP server
        $ routilux server start

        # List available routines
        $ routilux list routines

        # Use a config file
        $ routilux --config routilux.toml run -w flow.yaml
    """
    ctx.ensure_object(dict)

    # Load configuration file
    config_data = {}
    try:
        config_data = load_config(config)
    except Exception as e:
        if verbose:
            click.echo(f"Warning: Could not load config: {e}", err=True)

    # Get routines directories from config if not specified on CLI
    config_routines_dirs = get_config_value(config_data, "routines", "directories", default=[])

    # CLI options take precedence over config file
    routines_dirs = list(routines_dir) if routines_dir else config_routines_dirs

    ctx.obj["routines_dirs"] = routines_dirs
    ctx.obj["config"] = config
    ctx.obj["config_data"] = config_data
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet


# Add commands to CLI
cli.add_command(run)
cli.add_command(server)
cli.add_command(list_cmd)
cli.add_command(validate)
cli.add_command(initialize, name="init")
cli.add_command(completion)
cli.add_command(job)


def main():
    """Entry point for console script."""
    cli(obj={})


if __name__ == "__main__":
    main()
