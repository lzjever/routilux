"""Pytest configuration and fixtures for Routilux tests."""

import pytest
from fastapi.testclient import TestClient

from routilux.core import (
    Flow,
    Runtime,
    get_flow_registry,
    get_worker_manager,
    reset_worker_manager,
)
from routilux.core.output import uninstall_routed_stdout
from routilux.server.dependencies import reset_storage
from routilux.server.main import app


@pytest.fixture(autouse=True)
def register_basic_factory_objects():
    """Register basic factory objects for user story tests.

    This fixture registers the common factory objects needed by
    worker lifecycle and monitoring tests.
    """
    import sys
    from pathlib import Path

    # Add examples directory to path to access overseer_demo_app
    examples_dir = Path(__file__).parent / "examples"
    if str(examples_dir) not in sys.path:
        sys.path.insert(0, str(examples_dir))

    from routilux.tools.factory import ObjectFactory, ObjectMetadata

    factory = ObjectFactory.get_instance()

    # Import routine classes from overseer_demo_app
    try:
        from overseer_demo_app import (
            DataSink,
            DataSource,
            DataTransformer,
        )

        routines = [
            ("data_source", DataSource, "Generates sample data", "data_generation"),
            (
                "data_transformer",
                DataTransformer,
                "Transforms data",
                "transformation",
            ),
            ("data_sink", DataSink, "Receives and stores results", "sink"),
        ]

        for name, routine_class, description, category in routines:
            metadata = ObjectMetadata(
                name=name,
                description=description,
                category=category,
                tags=[category],
                example_config={},
                version="1.0.0",
            )
            try:
                factory.register(name, routine_class, metadata=metadata)
            except ValueError:
                # Already registered
                pass
    except ImportError:
        # overseer_demo_app not available, skip registration
        pass

    yield

    # Cleanup is handled by factory reset between tests


def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers",
        "userstory: User story integration tests (multi-API workflows that simulate real user scenarios)",
    )


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state before each test."""
    # Reset worker manager
    reset_worker_manager()

    # Clear flow registry
    registry = get_flow_registry()
    registry.clear()

    # Reset storage
    reset_storage()

    # Reset RoutedStdout to ensure clean state for each test
    uninstall_routed_stdout()

    yield

    # Cleanup after test
    reset_worker_manager()
    registry.clear()
    reset_storage()
    uninstall_routed_stdout()


@pytest.fixture
def runtime():
    """Create a Runtime instance for testing."""
    return Runtime(thread_pool_size=5)


@pytest.fixture
def empty_flow():
    """Create an empty Flow for testing."""
    return Flow()


@pytest.fixture
def worker_manager():
    """Get the global WorkerManager instance."""
    return get_worker_manager()


# ==============================================================================
# User Story Test Fixtures
# ==============================================================================


@pytest.fixture
def api_client():
    """Create a test API client for user story tests."""
    return TestClient(app)


@pytest.fixture
def registered_pipeline_flow(api_client):
    """Create and register a simple pipeline flow for testing.

    Creates a flow with: data_source -> data_transformer -> data_sink
    """
    from tests.helpers.flow_builder import FlowBuilder

    builder = FlowBuilder(api_client)
    builder.create_empty("registered_pipeline_flow")
    builder.build_pipeline()

    yield builder

    # Cleanup
    try:
        builder.delete()
    except Exception:
        pass


@pytest.fixture
def registered_branching_flow(api_client):
    """Create and register a branching flow for testing.

    Creates a flow with: data_source -> (data_transformer1, data_transformer2) -> data_sink
    """
    from tests.helpers.flow_builder import FlowBuilder

    builder = FlowBuilder(api_client)
    builder.create_empty("registered_branching_flow")
    builder.build_branching_flow()

    yield builder

    # Cleanup
    try:
        builder.delete()
    except Exception:
        pass


@pytest.fixture
def flow_builder(api_client):
    """Create a FlowBuilder instance for dynamic flow construction."""
    from tests.helpers.flow_builder import FlowBuilder

    return FlowBuilder(api_client)


@pytest.fixture
def job_monitor(api_client):
    """Create a JobMonitor instance for monitoring job execution."""
    from tests.helpers.job_monitor import JobMonitor

    return JobMonitor(api_client)


@pytest.fixture
def debug_client(api_client):
    """Create a DebugClient instance for debugging jobs."""
    from tests.helpers.debug_client import DebugClient

    return DebugClient(api_client)
