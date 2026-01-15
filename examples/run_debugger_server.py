#!/usr/bin/env python
"""
Launch script for Routilux API Server with test flows pre-registered

This script:
1. Creates and registers test flows
2. Starts the API server with those flows available

Usage:
    python run_debugger_server.py
"""

import os
import sys

# Add examples directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Import flow creators
from debugger_test_app import (
    create_branching_flow,
    create_complex_flow,
    create_error_flow,
    create_linear_flow,
)

from routilux.monitoring.registry import MonitoringRegistry
from routilux.monitoring.storage import flow_store


def register_flows():
    """Create and register all test flows"""
    print("=" * 60)
    print("Registering Test Flows")
    print("=" * 60)

    # Enable monitoring
    MonitoringRegistry.enable()

    flows_info = []

    # Linear flow
    print("\n[1/4] Creating linear flow...")
    linear_flow, linear_entry = create_linear_flow()
    flow_store.add(linear_flow)
    flows_info.append(
        {
            "id": linear_flow.flow_id,
            "routines": len(linear_flow.routines),
            "connections": len(linear_flow.connections),
            "entry": linear_entry,
        }
    )
    print(
        f"     ✓ {linear_flow.flow_id}: {flows_info[0]['routines']} routines, {flows_info[0]['connections']} connections"
    )

    # Branching flow
    print("\n[2/4] Creating branching flow...")
    branch_flow, branch_entry = create_branching_flow()
    flow_store.add(branch_flow)
    flows_info.append(
        {
            "id": branch_flow.flow_id,
            "routines": len(branch_flow.routines),
            "connections": len(branch_flow.connections),
            "entry": branch_entry,
        }
    )
    print(
        f"     ✓ {branch_flow.flow_id}: {flows_info[1]['routines']} routines, {flows_info[1]['connections']} connections"
    )

    # Complex flow
    print("\n[3/4] Creating complex flow...")
    complex_flow, complex_entry = create_complex_flow()
    flow_store.add(complex_flow)
    flows_info.append(
        {
            "id": complex_flow.flow_id,
            "routines": len(complex_flow.routines),
            "connections": len(complex_flow.connections),
            "entry": complex_entry,
        }
    )
    print(
        f"     ✓ {complex_flow.flow_id}: {flows_info[2]['routines']} routines, {flows_info[2]['connections']} connections"
    )

    # Error flow
    print("\n[4/4] Creating error flow...")
    error_flow, error_entry = create_error_flow()
    flow_store.add(error_flow)
    flows_info.append(
        {
            "id": error_flow.flow_id,
            "routines": len(error_flow.routines),
            "connections": len(error_flow.connections),
            "entry": error_entry,
        }
    )
    print(
        f"     ✓ {error_flow.flow_id}: {flows_info[3]['routines']} routines, {flows_info[3]['connections']} connections"
    )

    print("\n" + "=" * 60)
    print(f"✓ Successfully registered {len(flows_info)} flows")
    print("=" * 60)

    return flows_info


def print_instructions(flows_info):
    """Print usage instructions"""
    print("\n" + "=" * 60)
    print("Routilux Debugger Server Ready!")
    print("=" * 60)
    print("\n📊 Available Flows:")
    for info in flows_info:
        print(f"\n  • {info['id']}")
        print(f"    - Routines: {info['routines']}")
        print(f"    - Connections: {info['connections']}")
        print(f"    - Entry Point: {info['entry']}")

    print("\n" + "=" * 60)
    print("🚀 Getting Started:")
    print("=" * 60)
    print("\n1. Start the debugger web interface:")
    print("   cd /home/percy/works/mygithub/routilux-debugger")
    print("   npm run dev")
    print("\n2. Open browser: http://localhost:3000")
    print("   (You'll be redirected to /connect)")
    print("\n3. Enter server URL: http://localhost:20555")
    print("   Click 'Connect'")
    print("\n4. View and monitor flows in real-time!")
    print("\n" + "=" * 60)
    print("API Server Information:")
    print("=" * 60)
    print("Server URL: http://localhost:20555")
    print("Health Check: http://localhost:20555/api/health")
    print("API Docs: http://localhost:20555/docs")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 60 + "\n")


def main():
    """Main entry point"""
    try:
        # Register flows
        flows_info = register_flows()

        # Print instructions
        print_instructions(flows_info)

        # Start API server
        import uvicorn

        uvicorn.run(
            "routilux.api.main:app",
            host="0.0.0.0",
            port=20555,
            reload=True,
            log_level="info",
        )

    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
