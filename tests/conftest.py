"""
Pytest configuration and fixtures for routilux tests.
"""

import pytest

from routilux.monitoring.flow_registry import FlowRegistry


@pytest.fixture(autouse=True)
def clear_flow_registry():
    """Clear flow registry before each test to avoid conflicts."""
    registry = FlowRegistry.get_instance()
    registry.clear()
    yield
    # Cleanup after test
    registry.clear()


# Add timeout marker to all tests by default
def pytest_collection_modifyitems(config, items):
    """Add timeout marker to all tests if not already present."""
    for item in items:
        # Add timeout if not already set
        # Use shorter timeout for faster feedback on hanging tests
        if not any(marker.name == "timeout" for marker in item.iter_markers()):
            # Default 30 seconds, but can be overridden per test
            item.add_marker(pytest.mark.timeout(30))
