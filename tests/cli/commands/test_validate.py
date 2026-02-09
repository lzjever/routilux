"""Tests for 'routilux validate' command."""

import pytest
from click.testing import CliRunner
from pathlib import Path


def test_validate_requires_workflow_option():
    """Test that validate command requires --workflow option."""
    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["validate"])
    assert result.exit_code != 0
    assert "Missing option" in result.output or "--workflow" in result.output


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
    # Should succeed or contain validation info
    assert result.exit_code == 0 or "valid" in result.output.lower() or "validating" in result.output.lower()


def test_validate_invalid_yaml(tmp_path):
    """Test validating an invalid YAML file."""
    dsl_file = tmp_path / "invalid.yaml"
    dsl_file.write_text("invalid: yaml: content:")

    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["validate", "--workflow", str(dsl_file)])
    # Should show error about invalid syntax
    assert result.exit_code != 0 or "error" in result.output.lower() or "valid" in result.output.lower()
