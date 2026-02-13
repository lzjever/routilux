"""Integration tests for server flow loading."""

import tempfile
from pathlib import Path

import yaml


def test_server_loads_flows_and_registers_builtins():
    """Test that server loads flows and built-in routines work together."""
    from routilux.builtin_routines import register_all_builtins
    from routilux.cli.server_wrapper import load_flows_from_directory
    from routilux.tools.factory.factory import ObjectFactory

    factory = ObjectFactory()
    register_all_builtins(factory)

    with tempfile.TemporaryDirectory() as tmpdir:
        flows_dir = Path(tmpdir)

        # Create flow using built-in routine
        flow_data = {
            "flow_id": "builtin_test",
            "routines": {"mapper": {"class": "Mapper"}},
            "connections": [],
        }
        (flows_dir / "test.yaml").write_text(yaml.dump(flow_data))

        flows = load_flows_from_directory(flows_dir, factory)

        assert "builtin_test" in flows
        # Verify the Mapper routine was used
        assert "mapper" in flows["builtin_test"].routines


def test_builtin_routines_are_registered():
    """Test that all builtin routines can be created via factory."""
    from routilux.builtin_routines import register_all_builtins
    from routilux.tools.factory.factory import ObjectFactory

    factory = ObjectFactory()
    register_all_builtins(factory)

    # Test creating a few key routines
    mapper = factory.create("Mapper")
    assert mapper is not None

    filter_routine = factory.create("Filter")
    assert filter_routine is not None

    aggregator = factory.create("Aggregator")
    assert aggregator is not None


def test_load_multiple_flows_from_directory():
    """Test loading multiple flows from a directory."""
    from routilux.builtin_routines import register_all_builtins
    from routilux.cli.server_wrapper import load_flows_from_directory
    from routilux.tools.factory.factory import ObjectFactory

    factory = ObjectFactory()
    register_all_builtins(factory)

    with tempfile.TemporaryDirectory() as tmpdir:
        flows_dir = Path(tmpdir)

        # Create multiple flows
        flow1 = {
            "flow_id": "flow_one",
            "routines": {"m1": {"class": "Mapper"}},
            "connections": [],
        }
        (flows_dir / "flow1.yaml").write_text(yaml.dump(flow1))

        flow2 = {
            "flow_id": "flow_two",
            "routines": {"f1": {"class": "Filter"}},
            "connections": [],
        }
        (flows_dir / "flow2.yaml").write_text(yaml.dump(flow2))

        flows = load_flows_from_directory(flows_dir, factory)

        assert len(flows) == 2
        assert "flow_one" in flows
        assert "flow_two" in flows


def test_flow_with_conditional_router():
    """Test loading flow with ConditionalRouter builtin."""
    from routilux.builtin_routines import register_all_builtins
    from routilux.cli.server_wrapper import load_flows_from_directory
    from routilux.tools.factory.factory import ObjectFactory

    factory = ObjectFactory()
    register_all_builtins(factory)

    with tempfile.TemporaryDirectory() as tmpdir:
        flows_dir = Path(tmpdir)

        # Create flow using ConditionalRouter
        flow_data = {
            "flow_id": "router_test",
            "routines": {
                "router": {
                    "class": "ConditionalRouter",
                    "config": {
                        "conditions": [
                            {"condition": "x > 0", "target": "positive"},
                            {"condition": "x < 0", "target": "negative"},
                        ]
                    },
                }
            },
            "connections": [],
        }
        (flows_dir / "router.yaml").write_text(yaml.dump(flow_data))

        flows = load_flows_from_directory(flows_dir, factory)

        assert "router_test" in flows
        assert "router" in flows["router_test"].routines


def test_cli_job_command_exists():
    """Test that job CLI command is available."""
    from click.testing import CliRunner

    from routilux.cli.main import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "job" in result.output
