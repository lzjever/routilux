"""Tests for job CLI commands."""

from click.testing import CliRunner


def test_job_command_group_exists():
    """Test that job command group exists."""
    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["job", "--help"])

    assert result.exit_code == 0
    assert "submit" in result.output


def test_job_submit_help():
    """Test job submit help."""
    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["job", "submit", "--help"])

    assert result.exit_code == 0
    assert "--flow" in result.output
    assert "--routine" in result.output


def test_job_status_help():
    """Test job status help."""
    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["job", "status", "--help"])

    assert result.exit_code == 0


def test_job_list_help():
    """Test job list help."""
    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["job", "list", "--help"])

    assert result.exit_code == 0
    assert "--flow" in result.output or "flow" in result.output.lower()


def test_job_submit_requires_flow():
    """Test that job submit requires --flow option."""
    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["job", "submit", "--routine", "test", "--data", "{}"])

    # Should fail because --flow is required
    assert result.exit_code != 0


def test_job_submit_requires_routine():
    """Test that job submit requires --routine option."""
    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["job", "submit", "--flow", "test", "--data", "{}"])

    # Should fail because --routine is required
    assert result.exit_code != 0


def test_job_submit_requires_data():
    """Test that job submit requires --data option."""
    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["job", "submit", "--flow", "test", "--routine", "proc"])

    # Should fail because --data is required
    assert result.exit_code != 0


def test_job_submit_validates_json():
    """Test that job submit validates JSON data."""
    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["job", "submit", "--flow", "test", "--routine", "proc", "--data", "not-json"],
    )

    # Should fail because data is not valid JSON
    assert result.exit_code != 0
    assert "JSON" in result.output or "json" in result.output.lower()
