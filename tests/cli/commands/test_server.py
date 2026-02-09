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
