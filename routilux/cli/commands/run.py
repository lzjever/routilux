"""Run workflow command implementation."""

import click
import yaml
import json
from pathlib import Path
from typing import Optional

from routilux.cli.discovery import discover_routines, get_default_routines_dirs
from routilux.tools.factory.factory import ObjectFactory


@click.command()
@click.option(
    "--workflow",
    "-w",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to workflow DSL file (JSON or YAML)",
)
@click.option(
    "--routines-dir",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Additional directories to scan for routines",
)
@click.option(
    "--param",
    "-p",
    multiple=True,
    help="Parameters to pass to workflow (KEY=VALUE format)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for results (default: stdout)",
)
@click.option(
    "--timeout",
    type=float,
    default=300.0,
    help="Execution timeout in seconds (default: 300)",
)
@click.pass_context
def run(ctx, workflow, routines_dir, param, output, timeout):
    """Run a workflow from a DSL file.

    Loads a workflow definition from a JSON or YAML file, discovers routines
    from specified directories, and executes the workflow.
    """
    quiet = ctx.obj.get("quiet", False)
    verbose = ctx.obj.get("verbose", False)

    # Gather routines directories
    routines_dirs = list(routines_dir)
    routines_dirs.extend(ctx.obj.get("routines_dirs", []))
    routines_dirs.extend(get_default_routines_dirs())

    if not quiet:
        click.echo(f"Loading workflow: {workflow}")
        if routines_dirs:
            click.echo(f"Scanning routines directories: {routines_dirs}")

    # Discover routines
    try:
        factory = discover_routines(routines_dirs, on_error="warn")
        if verbose:
            routines = factory.list_available()
            click.echo(f"Found {len(routines)} routines")
    except Exception as e:
        click.echo(f"Error discovering routines: {e}", err=True)
        raise click.Abort()

    # Load DSL file
    try:
        dsl_dict = _load_dsl(workflow)
    except Exception as e:
        click.echo(f"Error loading DSL: {e}", err=True)
        raise click.Abort()

    # Load flow from DSL
    try:
        flow = factory.load_flow_from_dsl(dsl_dict)
        if not quiet:
            click.echo(f"Loaded flow: {flow.flow_id}")
    except Exception as e:
        click.echo(f"Error loading flow from DSL: {e}", err=True)
        raise click.Abort()

    # Execute flow
    try:
        from routilux.core.runtime import Runtime

        runtime = Runtime()

        # Parse parameters
        params = _parse_params(param)

        if not quiet:
            click.echo(f"Executing flow...")

        # Create worker and submit job
        worker_state, job_context = runtime.post(
            flow_name=flow.flow_id,
            routine_name=list(flow.routines.keys())[0],  # Use first routine
            slot_name="input",
            data=params,
            timeout=timeout,
        )

        # Wait for completion
        import time
        start_time = time.time()

        while time.time() - start_time < timeout:
            job = runtime.get_job(job_context.job_id)
            if job and job.status in ("completed", "failed"):
                break
            time.sleep(0.1)

        if not quiet:
            elapsed = time.time() - start_time
            click.echo(f"Flow execution completed in {elapsed:.2f}s")
            click.echo(f"Status: {job.status if job else 'unknown'}")

        # Output results
        if job:
            if job.data:
                result_str = json.dumps(job.data, indent=2)
                if output:
                    output.write_text(result_str)
                    if not quiet:
                        click.echo(f"Results written to {output}")
                else:
                    if not quiet:
                        click.echo("\nResults:")
                    click.echo(result_str)

            if job.error and not quiet:
                click.echo(f"Error: {job.error}", err=True)

        # Exit with error code if job failed
        if job and job.status == "failed":
            raise click.Abort(1)

    except Exception as e:
        click.echo(f"Error executing flow: {e}", err=True)
        raise click.Abort(1)


def _load_dsl(file_path: Path) -> dict:
    """Load DSL from JSON or YAML file.

    Args:
        file_path: Path to DSL file

    Returns:
        Parsed DSL dictionary

    Raises:
        ValueError: If file format is invalid
    """
    content = file_path.read_text()

    if file_path.suffix in (".yaml", ".yml"):
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML: {e}")
    elif file_path.suffix == ".json":
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
    else:
        # Try YAML first, then JSON
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                raise ValueError(f"Unknown file format: {file_path.suffix}")


def _parse_params(param_list: tuple) -> dict:
    """Parse KEY=VALUE parameters into a dictionary.

    Args:
        param_list: Tuple of KEY=VALUE strings

    Returns:
        Dictionary of parameters
    """
    params = {}
    for param in param_list:
        if "=" not in param:
            continue
        key, value = param.split("=", 1)
        params[key] = value
    return params
