"""List command implementation."""

import click
from pathlib import Path
from typing import Optional

from routilux.cli.discovery import discover_routines, get_default_routines_dirs
from routilux.tools.factory.factory import ObjectFactory


@click.command()
@click.argument("resource", type=click.Choice(["routines", "flows"]))
@click.option(
    "--category",
    "-c",
    help="Filter by category",
)
@click.option(
    "--routines-dir",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Additional directories to scan for routines",
)
@click.option(
    "--dir",
    type=click.Path(exists=True, path_type=Path),
    help="Directory to scan for flows",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json", "plain"]),
    default="table",
    help="Output format (default: table)",
)
@click.pass_context
def list_cmd(ctx, resource, category, routines_dir, dir, output_format):
    """List available resources.

    List either discovered routines or available flow DSL files.
    """
    quiet = ctx.obj.get("quiet", False)

    if resource == "routines":
        _list_routines(category, routines_dir, output_format, quiet)
    elif resource == "flows":
        _list_flows(dir, output_format, quiet)


def _list_routines(category: Optional[str], routines_dirs: tuple, output_format: str, quiet: bool):
    """List discovered routines."""
    from routilux.tools.factory.factory import ObjectFactory

    # Gather routines directories
    all_dirs = list(routines_dirs)
    all_dirs.extend(get_default_routines_dirs())

    # Discover routines
    if all_dirs:
        discover_routines(all_dirs, on_error="warn")

    # List routines
    factory = ObjectFactory.get_instance()
    routines = factory.list_available(category=category)

    if output_format == "json":
        import json
        click.echo(json.dumps(routines, indent=2))
    elif output_format == "plain":
        for routine in routines:
            click.echo(routine["name"])
    else:  # table
        if not routines:
            if not quiet:
                click.echo("No routines found.")
            return

        # Table format
        click.echo(f"{'Name':<30} {'Type':<10} {'Category':<15} {'Description'}")
        click.echo("-" * 100)
        for routine in routines:
            name = routine["name"][:30]
            obj_type = routine["object_type"][:10]
            cat = (routine.get("category") or "")[:15]
            desc = (routine.get("description") or "")[:40]
            click.echo(f"{name:<30} {obj_type:<10} {cat:<15} {desc}")


def _list_flows(directory: Optional[Path], output_format: str, quiet: bool):
    """List available flow DSL files."""
    import yaml

    dirs = []
    if directory:
        dirs.append(directory)

    # Add default locations
    dirs.append(Path.cwd() / "flows")
    dirs.append(Path.cwd())

    flows = []
    for flow_dir in dirs:
        if not flow_dir.exists():
            continue
        for ext in ("*.yaml", "*.yml", "*.json"):
            for flow_file in flow_dir.glob(ext):
                try:
                    # Parse to get flow_id
                    content = flow_file.read_text()
                    if flow_file.suffix in (".yaml", ".yml"):
                        data = yaml.safe_load(content)
                    else:
                        import json
                        data = json.loads(content)

                    flow_id = data.get("flow_id", flow_file.stem)
                    flows.append({
                        "flow_id": flow_id,
                        "file": str(flow_file),
                    })
                except Exception:
                    # Skip invalid files
                    flows.append({
                        "flow_id": f"<parse error: {flow_file.stem}>",
                        "file": str(flow_file),
                    })

    if output_format == "json":
        import json
        click.echo(json.dumps(flows, indent=2))
    elif output_format == "plain":
        for flow in flows:
            click.echo(flow["flow_id"])
    else:  # table
        if not flows:
            if not quiet:
                click.echo("No flows found.")
            return

        click.echo(f"{'Flow ID':<30} {'File'}")
        click.echo("-" * 80)
        for flow in flows:
            flow_id = flow["flow_id"][:30]
            file_path = flow["file"]
            click.echo(f"{flow_id:<30} {file_path}")
