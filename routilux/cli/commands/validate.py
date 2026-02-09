"""Validate command implementation."""

from pathlib import Path

import click

from routilux.cli.commands.run import _load_dsl
from routilux.cli.discovery import discover_routines, get_default_routines_dirs


@click.command()
@click.option(
    "--workflow",
    "-w",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to workflow DSL file to validate",
)
@click.option(
    "--routines-dir",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Additional directories to scan for routines",
)
@click.pass_context
def validate(ctx, workflow, routines_dir):
    """Validate a workflow DSL file.

    Checks DSL syntax, verifies all routines are registered, and validates connections.
    """
    quiet = ctx.obj.get("quiet", False)
    verbose = ctx.obj.get("verbose", False)

    # Gather routines directories
    routines_dirs = list(routines_dir)
    routines_dirs.extend(ctx.obj.get("routines_dirs", []))
    routines_dirs.extend(get_default_routines_dirs())

    errors = []
    warnings = []

    if not quiet:
        click.echo(f"Validating: {workflow}")

    # Load DSL
    try:
        dsl_dict = _load_dsl(workflow)
        if verbose:
            click.echo("✓ DSL syntax is valid")
    except Exception as e:
        errors.append(f"DSL syntax error: {e}")
        _print_validation_result(errors, warnings, quiet)
        raise click.Abort(1)

    # Discover routines
    try:
        from routilux.tools.factory.factory import ObjectFactory

        factory = discover_routines(routines_dirs, on_error="warn") if routines_dirs else ObjectFactory.get_instance()
        if verbose:
            routines = factory.list_available()
            click.echo(f"✓ Found {len(routines)} routines")
    except Exception as e:
        errors.append(f"Routine discovery error: {e}")

    # Validate flow
    try:
        flow = factory.load_flow_from_dsl(dsl_dict)

        # Validate flow structure
        issues = flow.validate()

        for issue in issues:
            if issue.startswith("Error:"):
                errors.append(issue)
            else:
                warnings.append(issue)

        if not issues and not quiet:
            click.echo("✓ Flow structure is valid")

    except ValueError as e:
        errors.append(str(e))
    except Exception as e:
        errors.append(f"Flow validation error: {e}")

    # Print results
    _print_validation_result(errors, warnings, quiet)

    # Exit with error if validation failed
    if errors:
        raise click.Abort(1)


def _print_validation_result(errors: list, warnings: list, quiet: bool):
    """Print validation results."""
    if quiet:
        return

    if not errors and not warnings:
        click.echo("✓ Validation passed")
        return

    if warnings:
        click.echo("\nWarnings:")
        for warning in warnings:
            click.echo(f"  ⚠ {warning}")

    if errors:
        click.echo("\nErrors:")
        for error in errors:
            click.echo(f"  ✗ {error}")
        click.echo("\n✗ Validation failed")
    else:
        click.echo("\n✓ Validation passed (with warnings)")
