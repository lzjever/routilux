"""
Register test flows for the debugger

This module is imported by the API server to register test flows on startup.
"""

from routilux.monitoring.registry import MonitoringRegistry
from routilux.monitoring.storage import flow_store


def register_test_flows():
    """Register all test flows to flow_store"""
    from debugger_test_app import (
        create_branching_flow,
        create_complex_flow,
        create_error_flow,
        create_linear_flow,
    )

    print("Registering test flows...")

    # Create and register flows
    linear_flow, _ = create_linear_flow()
    flow_store.add(linear_flow)
    print(f"  ✓ Registered: {linear_flow.flow_id}")

    branch_flow, _ = create_branching_flow()
    flow_store.add(branch_flow)
    print(f"  ✓ Registered: {branch_flow.flow_id}")

    complex_flow, _ = create_complex_flow()
    flow_store.add(complex_flow)
    print(f"  ✓ Registered: {complex_flow.flow_id}")

    error_flow, _ = create_error_flow()
    flow_store.add(error_flow)
    print(f"  ✓ Registered: {error_flow.flow_id}")

    print(f"Total flows registered: {len(flow_store.list_all())}")


# Auto-register on import
if MonitoringRegistry.is_enabled():
    register_test_flows()
