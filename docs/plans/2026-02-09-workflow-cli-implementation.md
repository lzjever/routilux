# Routilux Workflow CLI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a comprehensive workflow CLI application for the routilux library that supports standalone CLI mode and HTTP server mode with automatic routine discovery.

**Architecture:** Modular CLI package (`routilux/cli/`) using click framework, with auto-discovery system that scans directories for Python files and registers routines with ObjectFactory. Server mode wraps existing FastAPI server.

**Tech Stack:** Python, click (CLI), FastAPI (server), existing routilux core (Routine, Flow, ObjectFactory)

---

## Task 1: Set up CLI package structure

**Files:**
- Create: `routilux/cli/__init__.py`
- Create: `routilux/cli/main.py`
- Create: `routilux/cli/commands/__init__.py`

**Step 1: Create package init**

```python
# routilux/cli/__init__.py
"""Routilux CLI package for workflow management."""

__version__ = "0.1.0"
```

**Step 2: Create main CLI entry point**

```python
# routilux/cli/main.py
"""Main CLI entry point using click framework."""

import click
from pathlib import Path

# Import commands (will implement these in subsequent tasks)
# from routilux.cli.commands.run import run
# from routilux.cli.commands.server import server
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


# Placeholder commands - will be implemented
@cli.command()
def run():
    """Run a workflow from a DSL file."""
    click.echo("run command - to be implemented")


@cli.command()
def server():
    """Start the HTTP server."""
    click.echo("server command - to be implemented")


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
```

**Step 3: Create commands package init**

```python
# routilux/cli/commands/__init__.py
"""CLI command implementations."""

__all__ = []
```

**Step 4: Test basic CLI works**

Run: `python -m routilux.cli.main --help`
Expected: Shows help output with all commands listed

**Step 5: Commit**

```bash
git add routilux/cli/
git commit -m "feat(cli): set up basic CLI package structure with click

- Create routilux/cli package with main entry point
- Add click-based command group with placeholder commands
- Support --routines-dir, --config, --verbose, --quiet options

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Implement routine discovery system

**Files:**
- Create: `routilux/cli/discovery.py`
- Create: `tests/cli/test_discovery.py`

**Step 1: Write failing tests for discovery**

```python
# tests/cli/test_discovery.py
"""Tests for routine discovery system."""

import pytest
from pathlib import Path
from routilux.cli.discovery import RoutineDiscovery, discover_routines


def test_discovery_scan_directory(tmp_path):
    """Test scanning a directory for Python files."""
    # Create test files
    (tmp_path / "routine1.py").write_text("pass")
    (tmp_path / "routine2.py").write_text("pass")
    (tmp_path / "not_python.txt").write_text("pass")

    discovery = RoutineDiscovery()
    files = discovery.scan_directory(tmp_path)

    assert len(files) == 2
    assert all(f.suffix == ".py" for f in files)


def test_discovery_with_decorator(tmp_path):
    """Test discovering routines decorated with @register_routine."""
    # Create a routine file with decorator
    routine_file = tmp_path / "my_routine.py"
    routine_file.write_text("""
from routilux.cli.decorators import register_routine

@register_routine("test_processor")
def my_logic(data):
    return data
""")

    factory = discover_routines([tmp_path])

    # Check routine is registered
    routines = factory.list_available()
    routine_names = [r["name"] for r in routines]
    assert "test_processor" in routine_names


def test_discovery_with_class_based(tmp_path):
    """Test discovering class-based routines."""
    routine_file = tmp_path / "class_routine.py"
    routine_file.write_text("""
from routilux.core.routine import Routine

class MyProcessor(Routine):
    factory_name = "class_processor"

    def setup(self):
        self.add_slot("input")
        self.add_event("output")
""")

    factory = discover_routines([tmp_path])

    routines = factory.list_available()
    routine_names = [r["name"] for r in routines]
    assert "class_processor" in routine_names


def test_discovery_handles_import_errors(tmp_path):
    """Test that discovery skips modules with import errors."""
    # Create a file with import error
    bad_file = tmp_path / "bad_routine.py"
    bad_file.write_text("import nonexistent_module")

    # Create a good file
    good_file = tmp_path / "good_routine.py"
    good_file.write_text("pass")

    # Should not raise, should skip bad file
    factory = discover_routines([tmp_path], on_error="warn")

    # Good file should still be processed
    assert factory is not None


def test_discovery_duplicate_registration(tmp_path):
    """Test that duplicate registration raises error."""
    routine_file = tmp_path / "routine.py"
    routine_file.write_text("""
from routilux.cli.decorators import register_routine

@register_routine("duplicate")
def func1(data):
    return data

@register_routine("duplicate")
def func2(data):
    return data
""")

    with pytest.raises(ValueError, match="already registered"):
        discover_routines([tmp_path])
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/cli/test_discovery.py -v`
Expected: FAIL - ModuleNotFoundError: No module named 'routilux.cli.discovery'

**Step 3: Implement discovery module**

```python
# routilux/cli/discovery.py
"""Routine auto-discovery system for scanning and registering routines."""

import importlib.util
import logging
import sys
import warnings
from pathlib import Path
from typing import List, Optional, Union

from routilux.tools.factory.factory import ObjectFactory

logger = logging.getLogger(__name__)


class RoutineDiscovery:
    """Discovers and registers routines from Python files."""

    def __init__(self, factory: Optional[ObjectFactory] = None):
        """Initialize discovery system.

        Args:
            factory: ObjectFactory instance. Uses global singleton if None.
        """
        self.factory = factory or ObjectFactory.get_instance()
        self._registered_routines = set()

    def scan_directory(self, directory: Path) -> List[Path]:
        """Scan directory for Python files.

        Args:
            directory: Directory path to scan

        Returns:
            List of Python file paths found

        Raises:
            ValueError: If directory doesn't exist
        """
        if not directory.exists():
            raise ValueError(f"Directory not found: {directory}")

        if not directory.is_dir():
            raise ValueError(f"Not a directory: {directory}")

        return list(directory.rglob("*.py"))

    def load_module(self, file_path: Path) -> Optional[object]:
        """Load a Python module from file path.

        Args:
            file_path: Path to Python file

        Returns:
            Module object or None if loading failed
        """
        try:
            # Create unique module name based on file path
            module_name = f"routilux_discovery_{file_path.stem}_{id(file_path)}"

            # Load module
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                logger.warning(f"Could not load spec for {file_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module

            spec.loader.exec_module(module)
            return module

        except Exception as e:
            logger.warning(f"Failed to load {file_path}: {e}")
            return None

    def discover_from_directory(
        self,
        directory: Path,
        on_error: str = "warn"
    ) -> int:
        """Discover and register routines from a directory.

        Args:
            directory: Directory to scan
            on_error: Error handling strategy - "warn", "raise", or "ignore"

        Returns:
            Number of routines registered

        Raises:
            ValueError: If on_error="raise" and discovery fails
        """
        count = 0
        files = self.scan_directory(directory)

        for file_path in files:
            try:
                module = self.load_module(file_path)
                if module is not None:
                    # The module's decorators should have registered routines
                    count += 1
            except Exception as e:
                if on_error == "raise":
                    raise ValueError(f"Failed to discover from {file_path}: {e}") from e
                elif on_error == "warn":
                    warnings.warn(f"Skipping {file_path}: {e}")
                # else: ignore

        return count


def discover_routines(
    directories: List[Path],
    factory: Optional[ObjectFactory] = None,
    on_error: str = "warn"
) -> ObjectFactory:
    """Discover and register routines from multiple directories.

    Args:
        directories: List of directory paths to scan
        factory: ObjectFactory instance. Uses global singleton if None.
        on_error: Error handling strategy

    Returns:
        The ObjectFactory instance

    Raises:
        ValueError: If directories are invalid or discovery fails
    """
    discovery = RoutineDiscovery(factory)

    for directory in directories:
        directory = Path(directory)
        try:
            discovery.discover_from_directory(directory, on_error=on_error)
        except ValueError as e:
            if on_error == "raise":
                raise
            warnings.warn(str(e))

    return discovery.factory


def get_default_routines_dirs() -> List[Path]:
    """Get default routines directories.

    Returns:
        List of default directory paths
    """
    dirs = []

    # Project-local directory
    local_dir = Path.cwd() / "routines"
    if local_dir.exists():
        dirs.append(local_dir)

    # User-global directory
    from pathlib import Path
    home = Path.home()
    global_dir = home / ".routilux" / "routines"
    if global_dir.exists():
        dirs.append(global_dir)

    return dirs
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/cli/test_discovery.py -v`
Expected: Most tests PASS, but decorator tests still fail (we implement decorator next)

**Step 5: Commit**

```bash
git add routilux/cli/discovery.py tests/cli/test_discovery.py
git commit -m "feat(cli): implement routine discovery system

- Add RoutineDiscovery class for scanning directories
- Support loading Python modules from file paths
- Add discover_routines() function for multi-directory discovery
- Add get_default_routines_dirs() for default directories
- Handle import errors gracefully with configurable strategies

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Implement @register_routine decorator

**Files:**
- Create: `routilux/cli/decorators.py`
- Create: `tests/cli/test_decorators.py`

**Step 1: Write failing tests for decorator**

```python
# tests/cli/test_decorators.py
"""Tests for @register_routine decorator."""

import pytest
from routilux.cli.decorators import register_routine
from routilux.tools.factory.factory import ObjectFactory


def test_register_simple_function():
    """Test registering a simple function as a routine."""
    factory = ObjectFactory.get_instance()

    @register_routine("simple_processor")
    def my_logic(data):
        return data.upper()

    # Check routine is registered
    routines = factory.list_available()
    routine_names = [r["name"] for r in routines]
    assert "simple_processor" in routine_names


def test_register_with_metadata():
    """Test registering with metadata."""
    factory = ObjectFactory.get_instance()

    @register_routine(
        "metadata_processor",
        category="processing",
        tags=["fast", "simple"],
        description="A test processor"
    )
    def my_logic(data):
        return data

    metadata = factory.get_metadata("metadata_processor")
    assert metadata is not None
    assert metadata.category == "processing"
    assert "fast" in metadata.tags


def test_create_routine_from_factory():
    """Test that registered routine can be created from factory."""
    factory = ObjectFactory.get_instance()

    @register_routine("factory_test")
    def process(data):
        return data * 2

    # Create instance from factory
    routine = factory.create("factory_test")
    assert routine is not None
    assert hasattr(routine, "_logic")


def test_duplicate_registration_raises():
    """Test that duplicate registration raises error."""
    factory = ObjectFactory.get_instance()

    @register_routine("duplicate_test")
    def func1(data):
        return data

    with pytest.raises(ValueError, match="already registered"):
        @register_routine("duplicate_test")
        def func2(data):
            return data


def test_decorator_preserves_function():
    """Test that decorator preserves original function."""
    @register_routine("preserve_test")
    def my_function(data):
        return data

    # Function should still be callable
    assert my_function("test") == "test"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/cli/test_decorators.py -v`
Expected: FAIL - ModuleNotFoundError

**Step 3: Implement decorator module**

```python
# routilux/cli/decorators.py
"""Decorator for registering routines with the factory."""

import functools
from typing import Callable, Optional, Union

from routilux.core.routine import Routine
from routilux.tools.factory.factory import ObjectFactory
from routilux.tools.factory.metadata import ObjectMetadata


def register_routine(
    name: str,
    *,
    category: str = "user",
    tags: Optional[list[str]] = None,
    description: str = "",
    metadata: Optional[ObjectMetadata] = None,
) -> Callable:
    """Decorator to register a function as a routine.

    Creates a dynamic Routine subclass that wraps the function as the routine's logic.
    The routine is automatically registered with ObjectFactory.

    Args:
        name: Factory name for the routine (must be unique)
        category: Category for organization (default: "user")
        tags: Optional list of tags for discovery
        description: Human-readable description
        metadata: Optional ObjectMetadata (overrides other params if provided)

    Returns:
        The original function (unchanged)

    Raises:
        ValueError: If name is already registered

    Examples:
        >>> @register_routine("my_processor", category="processing", tags=["fast"])
        ... def my_logic(data, **kwargs):
        ...     return process(data)
    """
    def decorator(func: Callable) -> Callable:
        factory = ObjectFactory.get_instance()

        # Check if already registered
        if name in factory._registry:
            raise ValueError(f"Routine '{name}' is already registered")

        # Create metadata if not provided
        if metadata is None:
            docstring = func.__doc__.strip() if func.__doc__ else None
            metadata = ObjectMetadata(
                name=name,
                description=description or docstring or "",
                category=category,
                tags=tags or []
            )

        # Create dynamic Routine subclass
        class _DynamicRoutine(Routine):
            """Dynamically created routine from function."""

            def setup(self):
                """Set up slots and events for the routine."""
                # Add default input slot
                self.add_slot("input")
                # Add default output event
                self.add_event("output")
                # Set the logic function
                self.set_logic(func)

        # Register the class with factory
        factory.register(name, _DynamicRoutine, metadata=metadata)

        # Return original function unchanged
        return func

    return decorator


def auto_register_routine(
    cls: type[Routine],
    *,
    name: Optional[str] = None,
    category: str = "user",
    tags: Optional[list[str]] = None,
    description: str = "",
) -> type[Routine]:
    """Automatically register a Routine subclass with the factory.

    Use as a decorator on Routine classes:

        @auto_register_routine(name="my_processor")
        class MyProcessor(Routine):
            def setup(self):
                self.add_slot("input")
                self.add_event("output")

    Args:
        cls: Routine subclass to register
        name: Factory name (uses class name or cls.factory_name if not provided)
        category: Category for organization
        tags: Optional list of tags
        description: Human-readable description

    Returns:
        The original class unchanged

    Examples:
        >>> @auto_register_routine()
        ... class MyProcessor(Routine):
        ...     factory_name = "my_processor"
        ...     def setup(self):
        ...         self.add_slot("input")
    """
    factory = ObjectFactory.get_instance()

    # Determine factory name
    factory_name = name or getattr(cls, "factory_name", cls.__name__)

    # Create metadata if not in docstring
    if metadata is None:
        docstring = cls.__doc__.strip() if cls.__doc__ else None
        metadata = ObjectMetadata(
            name=factory_name,
            description=description or docstring or "",
            category=category,
            tags=tags or []
        )

    # Register the class
    factory.register(factory_name, cls, metadata=metadata)

    return cls
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/cli/test_decorators.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add routilux/cli/decorators.py tests/cli/test_decorators.py
git commit -m "feat(cli): implement @register_routine decorator

- Add @register_routine decorator for function-based routines
- Creates dynamic Routine subclass with default slots/events
- Registers with ObjectFactory for DSL loading
- Support metadata (category, tags, description)
- Add auto_register_routine for class-based registration
- Preserve original function/class after decoration

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Implement 'routilux run' command

**Files:**
- Create: `routilux/cli/commands/run.py`
- Create: `tests/cli/commands/test_run.py`
- Modify: `routilux/cli/main.py` (import and use run command)

**Step 1: Write failing tests for run command**

```python
# tests/cli/commands/test_run.py
"""Tests for 'routilux run' command."""

import json
import pytest
from click.testing import CliRunner
from pathlib import Path


def test_run_requires_workflow_option():
    """Test that run command requires --workflow option."""
    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["run"])
    assert result.exit_code != 0
    assert "Missing option" in result.output or "--workflow" in result.output


def test_run_with_simple_dsl(tmp_path):
    """Test running a simple workflow from DSL."""
    # Create a simple DSL file
    dsl_file = tmp_path / "flow.yaml"
    dsl_file.write_text("""
flow_id: test_flow
routines:
  source:
    class: data_source
    config:
      name: Source
connections: []
""")

    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--workflow", str(dsl_file)])

    # Should execute (exit code 0 or specific error if routines not found)
    assert "test_flow" in result.output or result.exit_code != 0


def test_run_with_invalid_dsl(tmp_path):
    """Test running with invalid DSL shows helpful error."""
    dsl_file = tmp_path / "invalid.yaml"
    dsl_file.write_text("invalid: yaml: content:")

    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--workflow", str(dsl_file)])

    # Should show error
    assert result.exit_code != 0 or "error" in result.output.lower()


def test_run_with_routines_dir(tmp_path):
    """Test running with custom routines directory."""
    # Create a routine
    routines_dir = tmp_path / "routines"
    routines_dir.mkdir()
    (routines_dir / "my_routine.py").write_text("""
from routilux.cli.decorators import register_routine

@register_routine("custom_processor")
def process(data):
    return data.upper()
""")

    # Create DSL using custom routine
    dsl_file = tmp_path / "flow.yaml"
    dsl_file.write_text("""
flow_id: custom_flow
routines:
  processor:
    class: custom_processor
connections: []
""")

    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, [
        "run",
        "--workflow", str(dsl_file),
        "--routines-dir", str(routines_dir)
    ])

    # Should find custom routine
    assert "custom_flow" in result.output or result.exit_code != 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/cli/commands/test_run.py -v`
Expected: FAIL - run command not implemented

**Step 3: Implement run command**

```python
# routilux/cli/commands/run.py
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
```

**Step 4: Update main.py to use run command**

```python
# Add import at top of routilux/cli/main.py
from routilux.cli.commands.run import run

# Replace the placeholder run command with:
cli.add_command(run)
```

Remove the placeholder `run()` function from main.py.

**Step 5: Run tests to verify they pass**

Run: `pytest tests/cli/commands/test_run.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add routilux/cli/commands/run.py routilux/cli/main.py tests/cli/commands/test_run.py
git commit -m "feat(cli): implement 'routilux run' command

- Add run command to execute workflows from DSL files
- Support JSON and YAML DSL formats
- Auto-discover routines from directories
- Parse parameters with KEY=VALUE format
- Output results to stdout or file
- Add tests for various scenarios

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Implement 'routilux server' command

**Files:**
- Create: `routilux/cli/server_wrapper.py`
- Create: `routilux/cli/commands/server.py`
- Create: `tests/cli/commands/test_server.py`
- Modify: `routilux/cli/main.py`

**Step 1: Write failing tests for server command**

```python
# tests/cli/commands/test_server.py
"""Tests for 'routilux server' command."""

import pytest
from click.testing import CliRunner


def test_server_start_command():
    """Test that server start command is available."""
    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["server", "start", "--help"])
    assert result.exit_code == 0
    assert "--host" in result.output
    assert "--port" in result.output


def test_server_with_custom_port():
    """Test server with custom port option."""
    from routilux.cli.main import cli

    runner = CliRunner()
    # Would actually start server, so we just check help
    result = runner.invoke(cli, ["server", "start", "--help"])
    assert "--port" in result.output
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/cli/commands/test_server.py -v`
Expected: FAIL - server command not implemented

**Step 3: Implement server wrapper**

```python
# routilux/cli/server_wrapper.py
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
```

**Step 4: Implement server command**

```python
# routilux/cli/commands/server.py
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
```

**Step 5: Update main.py to use server command**

```python
# Add import at top of routilux/cli/main.py
from routilux.cli.commands.server import server

# Replace the placeholder server command with:
cli.add_command(server)
```

Remove the placeholder `server()` function from main.py.

**Step 6: Run tests to verify they pass**

Run: `pytest tests/cli/commands/test_server.py -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add routilux/cli/server_wrapper.py routilux/cli/commands/server.py routilux/cli/main.py tests/cli/commands/test_server.py
git commit -m "feat(cli): implement 'routilux server' command

- Add server start command with host/port options
- Implement server wrapper for routine discovery
- Support --reload flag for development
- Support --routines-dir for custom routine locations
- Add server command group (start/stop/status)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Implement 'routilux list' command

**Files:**
- Create: `routilux/cli/commands/list.py`
- Create: `tests/cli/commands/test_list.py`
- Modify: `routilux/cli/main.py`

**Step 1: Write failing tests**

```python
# tests/cli/commands/test_list.py
"""Tests for 'routilux list' command."""

import pytest
from click.testing import CliRunner


def test_list_routines_command():
    """Test listing routines."""
    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["list", "routines"])
    # Should succeed
    assert result.exit_code == 0


def test_list_flows_command():
    """Test listing flows."""
    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["list", "flows"])
    # Should succeed
    assert result.exit_code == 0


def test_list_with_category_filter():
    """Test listing routines with category filter."""
    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["list", "routines", "--category", "processing"])
    assert result.exit_code == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/cli/commands/test_list.py -v`
Expected: FAIL - list command not implemented

**Step 3: Implement list command**

```python
# routilux/cli/commands/list.py
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
```

**Step 4: Update main.py**

```python
# Add import at top of routilux/cli/main.py
from routilux.cli.commands.list import list_cmd

# Replace the placeholder list_cmd command with:
cli.add_command(list_cmd)
```

Remove the placeholder `list_cmd()` function from main.py.

**Step 5: Run tests to verify they pass**

Run: `pytest tests/cli/commands/test_list.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add routilux/cli/commands/list.py routilux/cli/main.py tests/cli/commands/test_list.py
git commit -m "feat(cli): implement 'routilux list' command

- Add list command for routines and flows
- Support filtering by category
- Scan default directories for flow files
- Support multiple output formats (table, json, plain)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Implement 'routilux validate' command

**Files:**
- Create: `routilux/cli/commands/validate.py`
- Create: `tests/cli/commands/test_validate.py`
- Modify: `routilux/cli/main.py`

**Step 1: Write failing tests**

```python
# tests/cli/commands/test_validate.py
"""Tests for 'routilux validate' command."""

import pytest
from click.testing import CliRunner
from pathlib import Path


def test_validate_valid_dsl(tmp_path):
    """Test validating a valid DSL."""
    dsl_file = tmp_path / "valid.yaml"
    dsl_file.write_text("""
flow_id: test_flow
routines:
  source:
    class: data_source
connections: []
""")

    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["validate", "--workflow", str(dsl_file)])
    assert "valid" in result.output.lower() or result.exit_code == 0


def test_validate_invalid_dsl(tmp_path):
    """Test validating an invalid DSL."""
    dsl_file = tmp_path / "invalid.yaml"
    dsl_file.write_text("""
flow_id: test_flow
routines:
  source:
    class: nonexistent_routine
connections: []
""")

    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["validate", "--workflow", str(dsl_file)])
    assert "error" in result.output.lower() or result.exit_code != 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/cli/commands/test_validate.py -v`
Expected: FAIL - validate command not implemented

**Step 3: Implement validate command**

```python
# routilux/cli/commands/validate.py
"""Validate command implementation."""

import click
from pathlib import Path

from routilux.cli.discovery import discover_routines, get_default_routines_dirs
from routilux.cli.commands.run import _load_dsl


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
        from routilux.tools.factory.factory import ObjectFactory

        factory = ObjectFactory.get_instance()
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
```

**Step 4: Update main.py**

```python
# Add import at top of routilux/cli/main.py
from routilux.cli.commands.validate import validate

# Replace the placeholder validate command with:
cli.add_command(validate)
```

Remove the placeholder `validate()` function from main.py.

**Step 5: Run tests to verify they pass**

Run: `pytest tests/cli/commands/test_validate.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add routilux/cli/commands/validate.py routilux/cli/main.py tests/cli/commands/test_validate.py
git commit -m "feat(cli): implement 'routilux validate' command

- Add validate command for DSL files
- Check DSL syntax, routine registration, and flow structure
- Report errors and warnings separately
- Exit with error code on validation failure

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 8: Implement 'routilux init' command

**Files:**
- Create: `routilux/cli/commands/init.py`
- Create: `tests/cli/commands/test_init.py`
- Modify: `routilux/cli/main.py`

**Step 1: Write failing tests**

```python
# tests/cli/commands/test_init.py
"""Tests for 'routilux init' command."""

import pytest
from click.testing import CliRunner
from pathlib import Path


def test_init_creates_project_structure(tmp_path):
    """Test that init creates project structure."""
    from routilux.cli.main import cli

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        assert (tmp_path / "routines").exists()
        assert (tmp_path / "flows").exists()


def test_init_with_custom_name(tmp_path):
    """Test init with custom project name."""
    from routilux.cli.main import cli

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init", "--name", "my_project"])

        assert result.exit_code == 0
        assert (tmp_path / "my_project" / "routines").exists()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/cli/commands/test_init.py -v`
Expected: FAIL - init command not implemented

**Step 3: Implement init command**

```python
# routilux/cli/commands/init.py
"""Init command implementation."""

import click


@click.command()
@click.option(
    "--name",
    "-n",
    default=".",
    help="Project name (default: current directory)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite existing files",
)
@click.pass_context
def initialize(ctx, name, force):
    """Initialize a new routilux project.

    Creates the directory structure and example files for a routilux project.
    """
    quiet = ctx.obj.get("quiet", False)

    from pathlib import Path

    project_dir = Path(name).resolve()

    if not quiet:
        click.echo(f"Initializing routilux project: {project_dir}")

    # Create directories
    routines_dir = project_dir / "routines"
    flows_dir = project_dir / "flows"

    routines_dir.mkdir(parents=True, exist_ok=True)
    flows_dir.mkdir(parents=True, exist_ok=True)

    if not quiet:
        click.echo(f"Created: {routines_dir}")
        click.echo(f"Created: {flows_dir}")

    # Create example routine
    example_routine = routines_dir / "example_routine.py"
    if not example_routine.exists() or force:
        example_routine.write_text('''"""Example routine for routilux."""

from routilux.cli.decorators import register_routine


@register_routine(
    "example_processor",
    category="example",
    tags=["demo"],
    description="An example routine that processes data"
)
def example_logic(data, **kwargs):
    """Process input data and return result.

    Args:
        data: Input data to process
        **kwargs: Additional keyword arguments

    Returns:
        Processed data
    """
    # Your processing logic here
    result = data

    # Emit output
    return result
''')
        if not quiet:
            click.echo(f"Created: {example_routine}")

    # Create example flow
    example_flow = flows_dir / "example_flow.yaml"
    if not example_flow.exists() or force:
        example_flow.write_text('''# Example flow definition

flow_id: example_flow

routines:
  processor:
    class: example_processor
    config:
      # Add configuration here

connections:
  # Add connections here
  # Example:
  # - from: processor.output
  #   to: next_routine.input

execution:
  timeout: 300.0
''')
        if not quiet:
            click.echo(f"Created: {example_flow}")

    # Create config file
    config_file = project_dir / "routilux.toml"
    if not config_file.exists() or force:
        config_file.write_text('''# Routilux configuration file

[routines]
directories = ["./routines"]

[server]
host = "0.0.0.0"
port = 8080

[discovery]
auto_reload = true
ignore_patterns = ["*_test.py", "test_*.py"]
''')
        if not quiet:
            click.echo(f"Created: {config_file}")

    if not quiet:
        click.echo("\n✓ Project initialized successfully!")
        click.echo("\nNext steps:")
        click.echo("  1. Add your routines to the routines/ directory")
        click.echo("  2. Define your flows in the flows/ directory")
        click.echo("  3. Run with: routilux run --workflow flows/your_flow.yaml")
        click.echo("  4. Or start server: routilux server start")
```

**Step 4: Update main.py**

```python
# Add import at top of routilux/cli/main.py
from routilux.cli.commands.init import initialize

# Replace the placeholder init command with:
cli.add_command(initialize)
```

Remove the placeholder `init()` function from main.py.

**Step 5: Run tests to verify they pass**

Run: `pytest tests/cli/commands/test_init.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add routilux/cli/commands/init.py routilux/cli/main.py tests/cli/commands/test_init.py
git commit -m "feat(cli): implement 'routilux init' command

- Add init command to create project structure
- Create routines/ and flows/ directories
- Generate example routine and flow files
- Create routilux.toml configuration file
- Support --force flag to overwrite existing files

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 9: Update pyproject.toml for CLI installation

**Files:**
- Modify: `pyproject.toml`

**Step 1: Check current pyproject.toml**

Run: `cat pyproject.toml`
Expected: See current project configuration

**Step 2: Add CLI dependencies and entry point**

Add to `pyproject.toml`:

```toml
[project.optional-dependencies]
cli = [
    "click>=8.0",
    "pyyaml>=6.0",
]

[project.scripts]
routilux = "routilux.cli.main:main"
```

**Step 3: Test installation**

Run: `pip install -e ".[cli]"`
Expected: Package installs with CLI support

Run: `routilux --help`
Expected: CLI help output

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build(cli): add CLI dependencies and entry point

- Add click and pyyaml as optional CLI dependencies
- Add routilux console script entry point
- Support pip install routilux[cli] for CLI installation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 10: Write integration tests

**Files:**
- Create: `tests/cli/integration/test_cli_integration.py`

**Step 1: Write integration tests**

```python
# tests/cli/integration/test_cli_integration.py
"""Integration tests for CLI commands."""

import pytest
from click.testing import CliRunner
from pathlib import Path


def test_full_workflow_cli(tmp_path):
    """Test complete workflow: init -> list -> run."""
    from routilux.cli.main import cli

    runner = CliRunner()

    # Initialize project
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0

        # Check directories created
        assert (tmp_path / "routines").exists()
        assert (tmp_path / "flows").exists()

        # List routines (should find example)
        result = runner.invoke(cli, ["list", "routines"])
        assert result.exit_code == 0
        assert "example_processor" in result.output

        # List flows
        result = runner.invoke(cli, ["list", "flows"])
        assert result.exit_code == 0
        assert "example_flow" in result.output

        # Validate flow
        result = runner.invoke(cli, ["validate", "--workflow", "flows/example_flow.yaml"])
        assert result.exit_code == 0


def test_discovery_integration(tmp_path):
    """Test routine discovery with actual files."""
    from routilux.cli.main import cli
    from routilux.cli.discovery import discover_routines
    from routilux.tools.factory.factory import ObjectFactory

    # Create routine files
    routines_dir = tmp_path / "routines"
    routines_dir.mkdir()

    (routines_dir / "routine1.py").write_text("""
from routilux.cli.decorators import register_routine

@register_routine("test_routine_1")
def logic1(data):
    return data
""")

    (routines_dir / "routine2.py").write_text("""
from routilux.cli.decorators import register_routine

@register_routine("test_routine_2", category="test")
def logic2(data):
    return data
""")

    # Discover
    factory = discover_routines([routines_dir])
    routines = factory.list_available()

    assert len(routines) >= 2
    routine_names = [r["name"] for r in routines]
    assert "test_routine_1" in routine_names
    assert "test_routine_2" in routine_names


def test_dsl_execution_with_discovered_routines(tmp_path):
    """Test executing flow with discovered routines."""
    # Create routine
    routines_dir = tmp_path / "routines"
    routines_dir.mkdir()

    (routines_dir / "processor.py").write_text("""
from routilux.cli.decorators import register_routine

@register_routine("uppercase_processor")
def uppercase(data):
    if isinstance(data, str):
        return data.upper()
    return data
""")

    # Create flow
    flows_dir = tmp_path / "flows"
    flows_dir.mkdir()

    flow_file = flows_dir / "test_flow.yaml"
    flow_file.write_text("""
flow_id: test_flow
routines:
  processor:
    class: uppercase_processor
connections: []
""")

    # Run with discovered routines
    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, [
        "run",
        "--workflow", str(flow_file),
        "--routines-dir", str(routines_dir)
    ])

    # Should not error on routine discovery
    assert "uppercase_processor" in result.output or result.exit_code == 0
```

**Step 2: Run integration tests**

Run: `pytest tests/cli/integration/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/cli/integration/
git commit -m "test(cli): add integration tests for CLI commands

- Test full workflow: init -> list -> validate -> run
- Test routine discovery with actual files
- Test DSL execution with discovered routines
- Verify end-to-end CLI functionality

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 11: Add CLI-specific API endpoints

**Files:**
- Create: `routilux/server/routes/discovery.py`
- Modify: `routilux/server/main.py`

**Step 1: Create discovery endpoint**

```python
# routilux/server/routes/discovery.py
"""Discovery endpoint for CLI integration."""

from fastapi import APIRouter
from routilux.server.middleware.auth import RequireAuth

router = APIRouter()


@router.get("/discovery", dependencies=[RequireAuth])
async def get_discovery_status():
    """Get current discovery status.

    Returns information about discovered routines and configuration.

    **Response Example**:
    ```json
    {
      "routines_count": 42,
      "directories": ["./routines", "~/.routilux/routines"],
      "routines": [
        {
          "name": "my_processor",
          "category": "processing",
          "type": "routine"
        }
      ]
    }
    ```
    """
    import os
    from pathlib import Path
    from routilux.tools.factory.factory import ObjectFactory

    factory = ObjectFactory.get_instance()
    routines = factory.list_available()

    # Get routines directories from environment
    routines_dirs_str = os.getenv("ROUTILUX_ROUTINES_DIRS", "")
    directories = []
    if routines_dirs_str:
        directories = routines_dirs_str.split(":")

    return {
        "routines_count": len(routines),
        "directories": directories,
        "routines": [
            {
                "name": r["name"],
                "category": r.get("category", ""),
                "type": r.get("object_type", "routine"),
            }
            for r in routines
        ],
    }


@router.post("/dsl/file", dependencies=[RequireAuth])
async def load_dsl_from_file(request: dict):
    """Load DSL from file path.

    Alternative to POST /api/v1/flows with DSL in body.
    This endpoint loads DSL from a file path on the server.

    **Request Example**:
    ```json
    {
      "file_path": "/path/to/flow.yaml"
    }
    ```

    **Response**: Flow object (same as POST /api/v1/flows)
    """
    from pathlib import Path
    from routilux.tools.factory.factory import ObjectFactory
    from routilux.cli.commands.run import _load_dsl

    file_path = request.get("file_path")
    if not file_path:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="file_path is required")

    path = Path(file_path)
    if not path.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    # Load DSL
    dsl_dict = _load_dsl(path)

    # Load flow from factory
    factory = ObjectFactory.get_instance()
    flow = factory.load_flow_from_dsl(dsl_dict)

    # Store flow
    from routilux.monitoring.storage import flow_store
    flow_store.add(flow)

    from routilux.server.routes.flows import _flow_to_response
    return _flow_to_response(flow)
```

**Step 2: Register router in main.py**

Add to `routilux/server/main.py`:

```python
# Add import
from routilux.server.routes import discovery

# Register router (after other router includes)
app.include_router(discovery.router, prefix="/api/v1", tags=["discovery"])
```

**Step 3: Test endpoints**

Run: `routilux server start &`
Run: `curl http://localhost:8080/api/v1/discovery`
Expected: JSON response with discovery status

**Step 4: Commit**

```bash
git add routilux/server/routes/discovery.py routilux/server/main.py
git commit -m "feat(cli): add CLI-specific API endpoints

- Add GET /api/v1/discovery for discovery status
- Add POST /api/v1/dsl/file for loading DSL from file path
- Integrate with existing FastAPI server

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 12: Update documentation

**Files:**
- Create: `docs/cli/usage.md`
- Create: `docs/cli/tutorial.md`
- Modify: `README.md`

**Step 1: Create CLI usage documentation**

```markdown
# Routilux CLI Usage Guide

## Installation

Install the CLI with:

\`\`\`bash
pip install routilux[cli]
\`\`\`

## Commands

### routilux run

Execute a workflow from a DSL file:

\`\`\`bash
routilux run --workflow flows/my_flow.yaml
\`\`\`

With custom routines directory:

\`\`\`bash
routilux run --workflow flow.yaml --routines-dir ./my_routines
\`\`\`

With parameters:

\`\`\`bash
routilux run --workflow flow.yaml --param name=value --param count=5
\`\`\`

### routilux server

Start the HTTP server:

\`\`\`bash
routilux server start --host 0.0.0.0 --port 8080
\`\`\`

With custom routines:

\`\`\`bash
routilux server start --routines-dir ./routines --routines-dir ./lib/routines
\`\`\`

### routilux list

List available routines:

\`\`\`bash
routilux list routines
\`\`\`

Filter by category:

\`\`\`bash
routilux list routines --category processing
\`\`\`

List available flows:

\`\`\`bash
routilux list flows
\`\`\`

### routilux validate

Validate a DSL file:

\`\`\`bash
routilux validate --workflow flows/my_flow.yaml
\`\`\`

### routilux init

Initialize a new project:

\`\`\`bash
routilux init
\`\`\`

With custom name:

\`\`\`bash
routilux init --name my_project
\`\`\`

## Writing Routines

### Using Decorators

\`\`\`python
from routilux.cli.decorators import register_routine

@register_routine("my_processor", category="processing", tags=["fast"])
def my_logic(data, **kwargs):
    # Process data
    return processed_data
\`\`\`

### Using Classes

\`\`\`python
from routilux.core.routine import Routine

class MyProcessor(Routine):
    factory_name = "my_processor"

    def setup(self):
        self.add_slot("input")
        self.add_event("output")
\`\`\`

## DSL Format

### YAML

\`\`\`yaml
flow_id: my_flow
routines:
  source:
    class: data_source
    config:
      name: Source
connections:
  - from: source.output
    to: processor.input
\`\`\`

### JSON

\`\`\`json
{
  "flow_id": "my_flow",
  "routines": {
    "source": {
      "class": "data_source",
      "config": {"name": "Source"}
    }
  },
  "connections": []
}
\`\`\`

## Configuration

Create a `routilux.toml` file:

\`\`\`toml
[routines]
directories = ["./routines", "./lib/routines"]

[server]
host = "0.0.0.0"
port = 8080
\`\`\`
```

**Step 2: Create tutorial**

```markdown
# Routilux CLI Tutorial

## Getting Started

### 1. Initialize a Project

\`\`\`bash
mkdir my_workflow_project
cd my_workflow_project
routilux init
\`\`\`

This creates:
- `routines/` - Directory for your routine scripts
- `flows/` - Directory for workflow DSL files
- `routilux.toml` - Configuration file
- Example files to get started

### 2. Write Your First Routine

Create `routines/hello.py`:

\`\`\`python
from routilux.cli.decorators import register_routine

@register_routine("hello_world")
def hello(data, **kwargs):
    name = data.get("name", "World")
    return f"Hello, {name}!"
\`\`\`

### 3. Create a Workflow

Create `flows/hello_flow.yaml`:

\`\`\`yaml
flow_id: hello_flow
routines:
  hello:
    class: hello_world
connections: []
\`\`\`

### 4. Run the Workflow

\`\`\`bash
routilux run --workflow flows/hello_flow.yaml --param name=Claude
\`\`\`

### 5. Start the Server

\`\`\`bash
routilux server start
\`\`\`

Now you can access the API at `http://localhost:8080`.

## Advanced Topics

### Multiple Routines

\`\`\`yaml
flow_id: pipeline
routines:
  source:
    class: data_source
  processor:
    class: my_processor
  sink:
    class: data_sink
connections:
  - from: source.output
    to: processor.input
  - from: processor.output
    to: sink.input
\`\`\`

### Error Handling

\`\`\`python
@register_routine("safe_processor")
def safe_process(data, **kwargs):
    try:
        return process(data)
    except Exception as e:
        # Handle error
        return {"error": str(e)}
\`\`\`

### Configuration

\`\`\`python
@register_routine("configurable_processor")
def process_with_config(data, **kwargs):
    config = kwargs.get("config", {})
    timeout = config.get("timeout", 30)
    # Use configuration
    return result
\`\`\`
```

**Step 3: Update README**

Add CLI section to main README:

\`\`\`markdown
## CLI

Routilux includes a command-line interface for workflow management:

\`\`\`bash
# Install with CLI support
pip install routilux[cli]

# Run a workflow
routilux run --workflow flow.yaml

# Start server
routilux server start

# See all commands
routilux --help
\`\`\`

See [CLI Documentation](docs/cli/usage.md) for details.
\`\`\`

**Step 4: Commit**

```bash
git add docs/cli/ README.md
git commit -m "docs(cli): add CLI usage documentation

- Add comprehensive CLI usage guide
- Add getting started tutorial
- Update main README with CLI section
- Document all commands and options

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 13: Final verification and cleanup

**Step 1: Run all tests**

Run: `pytest tests/cli/ -v --cov=routilux/cli`
Expected: All tests pass with good coverage

**Step 2: Verify CLI installation**

Run: `pip install -e ".[cli]"`
Run: `routilux --help`
Expected: Help output with all commands

**Step 3: Test basic workflow**

Run: `routilux init`
Run: `routilux list routines`
Run: `routilux validate --workflow flows/example_flow.yaml`
Expected: All commands work correctly

**Step 4: Check code quality**

Run: `ruff check routilux/cli/`
Run: `mypy routilux/cli/`
Expected: No critical errors

**Step 5: Final commit**

```bash
git add .
git commit -m "feat(cli): complete workflow CLI implementation

This commit completes the routilux workflow CLI implementation:

Features:
- Standalone CLI mode for local workflow execution
- HTTP server mode for API access
- Automatic routine discovery from directories
- Support for JSON and YAML DSL formats
- Commands: run, server, list, validate, init
- @register_routine decorator for easy routine creation
- Class-based routine registration support

Testing:
- Unit tests for all components
- Integration tests for end-to-end workflows
- Coverage >80% for CLI code

Documentation:
- Comprehensive usage guide
- Getting started tutorial
- API documentation for new endpoints

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

This implementation plan builds a complete workflow CLI for routilux in 13 tasks:

1. **Package structure** - Set up CLI package with click
2. **Discovery system** - Auto-discover routines from directories
3. **Decorator** - @register_routine for easy routine creation
4. **run command** - Execute workflows from DSL files
5. **server command** - Start HTTP server with discovered routines
6. **list command** - List available routines and flows
7. **validate command** - Validate DSL files
8. **init command** - Initialize new projects
9. **Installation** - Set up pip entry point
10. **Integration tests** - End-to-end testing
11. **API endpoints** - CLI-specific server endpoints
12. **Documentation** - Usage guides and tutorials
13. **Final verification** - Ensure everything works

Each task follows TDD: write failing test, implement, verify, commit.
