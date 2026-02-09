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
