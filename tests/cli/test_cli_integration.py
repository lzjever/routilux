"""Integration tests for CLI commands - ensures basic functionality works."""

import os
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        old_cwd = os.getcwd()
        os.chdir(tmpdir)
        yield Path(tmpdir)
        os.chdir(old_cwd)


class TestCLIInit:
    """Tests for 'routilux init' command."""

    def test_init_no_args_creates_in_current_dir(self, runner, temp_dir):
        """Test that 'routilux init' creates project in current directory."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert (temp_dir / "routines").exists()
        assert (temp_dir / "flows").exists()
        assert (temp_dir / "routilux.toml").exists()

    def test_init_with_positional_arg(self, runner, temp_dir):
        """Test that 'routilux init my-project' works with positional argument."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["init", "my-project"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert (temp_dir / "my-project").exists()
        assert (temp_dir / "my-project" / "routines").exists()
        assert (temp_dir / "my-project" / "flows").exists()

    def test_init_with_nested_path(self, runner, temp_dir):
        """Test that 'routilux init path/to/project' works."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["init", "projects/my-project"])

        assert result.exit_code == 0, f"Output: {result.output}"
        assert (temp_dir / "projects" / "my-project").exists()
        assert (temp_dir / "projects" / "my-project" / "routines").exists()

    def test_init_with_force(self, runner, temp_dir):
        """Test that --force flag works."""
        from routilux.cli.main import cli

        # First init
        result1 = runner.invoke(cli, ["init", "test-project"])
        assert result1.exit_code == 0

        # Modify a file
        config_file = temp_dir / "test-project" / "routilux.toml"
        original_content = config_file.read_text()
        config_file.write_text("modified")

        # Second init without force - should not overwrite
        result2 = runner.invoke(cli, ["init", "test-project"])
        assert result2.exit_code == 0
        assert config_file.read_text() == "modified"

        # Third init with force - should overwrite
        result3 = runner.invoke(cli, ["init", "test-project", "--force"])
        assert result3.exit_code == 0
        assert config_file.read_text() == original_content

    def test_init_invalid_name(self, runner, temp_dir):
        """Test that invalid project names are rejected."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["init", "invalid name!"])

        assert result.exit_code != 0
        assert "invalid characters" in result.output.lower()


class TestCLIHelp:
    """Tests for CLI help and version."""

    def test_version(self, runner):
        """Test that --version works."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["--version"])

        assert result.exit_code == 0
        assert "version" in result.output
        assert "0.15" in result.output  # Check for version number

    def test_help(self, runner):
        """Test that --help works."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "init" in result.output
        assert "run" in result.output
        assert "server" in result.output

    def test_init_help(self, runner):
        """Test that 'init --help' shows usage."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["init", "--help"])

        assert result.exit_code == 0
        assert "Initialize" in result.output

    def test_run_help(self, runner):
        """Test that 'run --help' shows usage."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["run", "--help"])

        assert result.exit_code == 0
        assert "workflow" in result.output.lower()

    def test_server_help(self, runner):
        """Test that 'server --help' shows usage."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["server", "--help"])

        assert result.exit_code == 0
        assert "start" in result.output


class TestCLIList:
    """Tests for 'routilux list' command."""

    def test_list_routines(self, runner, temp_dir):
        """Test that 'list routines' works."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["list", "routines"])

        # Should not error even if no routines
        assert result.exit_code == 0

    def test_list_flows(self, runner, temp_dir):
        """Test that 'list flows' works."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["list", "flows"])

        # Should not error even if no flows
        assert result.exit_code == 0


class TestCLIRun:
    """Tests for 'routilux run' command."""

    def test_run_missing_workflow(self, runner, temp_dir):
        """Test that run without workflow file shows error."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["run"])

        # Should show error about missing required option
        assert result.exit_code != 0

    def test_run_nonexistent_file(self, runner, temp_dir):
        """Test that run with nonexistent file shows error."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["run", "--workflow", "nonexistent.yaml"])

        assert result.exit_code != 0


class TestCLIServer:
    """Tests for 'routilux server' command."""

    def test_server_start_help(self, runner):
        """Test that 'server start --help' works."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["server", "start", "--help"])

        assert result.exit_code == 0
        assert "host" in result.output.lower()
        assert "port" in result.output.lower()

    def test_server_status(self, runner):
        """Test that 'server status' works."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["server", "status"])

        # Should work even if no server running
        assert result.exit_code == 0


class TestCLIValidate:
    """Tests for 'routilux validate' command."""

    def test_validate_missing_file(self, runner, temp_dir):
        """Test that validate without file shows error."""
        from routilux.cli.main import cli

        result = runner.invoke(cli, ["validate"])

        # Should show error about missing required option
        assert result.exit_code != 0
