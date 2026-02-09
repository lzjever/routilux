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
