"""
API tests for breakpoint endpoints.

Tests the breakpoint API endpoints with the new slot-level breakpoint design.
"""

import pytest
import time
from fastapi.testclient import TestClient

from routilux.monitoring.registry import MonitoringRegistry
from routilux.server.main import app


@pytest.fixture(scope="function")
def client():
    """Create test client with clean state."""
    MonitoringRegistry.enable()
    return TestClient(app)


@pytest.fixture(scope="function")
def setup_test_flow(client):
    """Setup a simple test flow for breakpoint testing."""
    from routilux.core.flow import Flow
    from routilux.core.routine import Routine
    from routilux.core.registry import FlowRegistry
    from routilux.monitoring.storage import flow_store
    from routilux import immediate_policy
    from routilux.tools.factory import ObjectFactory, ObjectMetadata

    # Create a simple test routine
    class TestSource(Routine):
        def setup(self):
            self.trigger = self.add_slot("trigger")
            self.output = self.add_event("output")
            self.set_activation_policy(immediate_policy())

        def logic(self, trigger_data_list, **kwargs):
            worker_state = kwargs.get("worker_state")
            runtime = getattr(worker_state, "_runtime", None)
            for data in trigger_data_list:
                self.emit("output", runtime=runtime, worker_state=worker_state, **data)

    class TestTarget(Routine):
        def setup(self):
            self.input = self.add_slot("input")
            self.set_activation_policy(immediate_policy())

        def logic(self, input_data_list, **kwargs):
            pass  # Just receive data

    # Register routines in factory (skip if already registered)
    factory = ObjectFactory.get_instance()
    try:
        factory.register("test_source_bp", TestSource, metadata=ObjectMetadata(
            name="test_source_bp", description="Test source", category="test", tags=["test"], version="1.0.0"
        ))
    except ValueError:
        pass  # Already registered
    
    try:
        factory.register("test_target_bp", TestTarget, metadata=ObjectMetadata(
            name="test_target_bp", description="Test target", category="test", tags=["test"], version="1.0.0"
        ))
    except ValueError:
        pass  # Already registered

    # Create flow
    flow = Flow("test_breakpoint_flow")
    source = factory.create("test_source_bp")
    source.setup()  # Ensure setup is called
    target = factory.create("test_target_bp")
    target.setup()  # Ensure setup is called
    
    source_id = flow.add_routine(source, "source")
    target_id = flow.add_routine(target, "target")
    flow.connect("source", "output", "target", "input")

    # Register flow
    flow_registry = FlowRegistry.get_instance()
    flow_registry.register(flow)
    flow_store.add(flow)

    yield flow

    # Cleanup
    if "test_breakpoint_flow" in flow_store._flows:
        del flow_store._flows["test_breakpoint_flow"]


class TestBreakpointAPICreate:
    """Test breakpoint creation API."""

    def test_create_breakpoint_success(self, client, setup_test_flow):
        """Test successfully creating a breakpoint."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "test_breakpoint_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"value": 42},
            },
        )
        assert response.status_code == 201
        job_id = response.json()["job_id"]

        # Create breakpoint
        response = client.post(
            f"/api/v1/jobs/{job_id}/breakpoints",
            json={
                "routine_id": "target",
                "slot_name": "input",
                "enabled": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        
        # Verify response structure (new API design)
        assert "breakpoint_id" in data
        assert data["job_id"] == job_id
        assert data["routine_id"] == "target"
        assert data["slot_name"] == "input"
        assert data["enabled"] is True
        assert data["hit_count"] == 0
        assert "condition" in data  # May be None
        
        # Verify no deprecated fields
        assert "type" not in data, "Response should not contain deprecated 'type' field"

    def test_create_breakpoint_with_condition(self, client, setup_test_flow):
        """Test creating breakpoint with condition."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "test_breakpoint_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"value": 42},
            },
        )
        job_id = response.json()["job_id"]

        # Create breakpoint with condition
        response = client.post(
            f"/api/jobs/{job_id}/breakpoints",
            json={
                "routine_id": "target",
                "slot_name": "input",
                "condition": "value > 40",
                "enabled": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["condition"] == "value > 40"
        assert data["routine_id"] == "target"
        assert data["slot_name"] == "input"

    def test_create_breakpoint_missing_routine_id(self, client, setup_test_flow):
        """Test creating breakpoint without routine_id (validation error)."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "test_breakpoint_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"value": 42},
            },
        )
        job_id = response.json()["job_id"]

        # Try to create breakpoint without routine_id
        response = client.post(
            f"/api/jobs/{job_id}/breakpoints",
            json={
                "slot_name": "input",
            },
        )
        assert response.status_code == 422  # Validation error

    def test_create_breakpoint_missing_slot_name(self, client, setup_test_flow):
        """Test creating breakpoint without slot_name (validation error)."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "test_breakpoint_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"value": 42},
            },
        )
        job_id = response.json()["job_id"]

        # Try to create breakpoint without slot_name
        response = client.post(
            f"/api/jobs/{job_id}/breakpoints",
            json={
                "routine_id": "target",
            },
        )
        assert response.status_code == 422  # Validation error

    def test_create_breakpoint_invalid_routine(self, client, setup_test_flow):
        """Test creating breakpoint with invalid routine_id."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "test_breakpoint_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"value": 42},
            },
        )
        job_id = response.json()["job_id"]

        # Try to create breakpoint with non-existent routine
        response = client.post(
            f"/api/jobs/{job_id}/breakpoints",
            json={
                "routine_id": "nonexistent_routine",
                "slot_name": "input",
            },
        )
        assert response.status_code == 404
        error_data = response.json()
        # Error response may be string or dict
        error_msg = error_data.get("detail", str(error_data)).lower()
        assert "not found" in error_msg or "routine" in error_msg

    def test_create_breakpoint_invalid_slot(self, client, setup_test_flow):
        """Test creating breakpoint with invalid slot_name."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "test_breakpoint_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"value": 42},
            },
        )
        job_id = response.json()["job_id"]

        # Try to create breakpoint with non-existent slot
        response = client.post(
            f"/api/jobs/{job_id}/breakpoints",
            json={
                "routine_id": "target",
                "slot_name": "nonexistent_slot",
            },
        )
        assert response.status_code == 404
        error_data = response.json()
        # Error response may be string or dict
        error_msg = error_data.get("detail", str(error_data)).lower()
        assert "not found" in error_msg or "slot" in error_msg

    def test_create_breakpoint_nonexistent_job(self, client, setup_test_flow):
        """Test creating breakpoint for non-existent job."""
        response = client.post(
            "/api/v1/jobs/nonexistent_job_id/breakpoints",
            json={
                "routine_id": "target",
                "slot_name": "input",
            },
        )
        assert response.status_code == 404
        error_data = response.json()
        # Error response may be string or dict
        error_msg = error_data.get("detail", str(error_data)).lower()
        assert "not found" in error_msg or "job" in error_msg


class TestBreakpointAPIList:
    """Test breakpoint listing API."""

    def test_list_breakpoints_empty(self, client, setup_test_flow):
        """Test listing breakpoints when none exist."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "test_breakpoint_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"value": 42},
            },
        )
        job_id = response.json()["job_id"]

        # List breakpoints
        response = client.get(f"/api/v1/jobs/{job_id}/breakpoints")
        assert response.status_code == 200
        data = response.json()
        assert "breakpoints" in data
        assert "total" in data
        assert data["total"] == 0
        assert len(data["breakpoints"]) == 0

    def test_list_breakpoints_with_breakpoints(self, client, setup_test_flow):
        """Test listing breakpoints when they exist."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "test_breakpoint_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"value": 42},
            },
        )
        job_id = response.json()["job_id"]

        # Create multiple breakpoints
        bp1_response = client.post(
            f"/api/jobs/{job_id}/breakpoints",
            json={"routine_id": "target", "slot_name": "input"},
        )
        assert bp1_response.status_code == 201

        # List breakpoints
        response = client.get(f"/api/v1/jobs/{job_id}/breakpoints")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["breakpoints"]) == 1
        
        bp = data["breakpoints"][0]
        assert bp["routine_id"] == "target"
        assert bp["slot_name"] == "input"
        assert "type" not in bp, "Response should not contain deprecated 'type' field"

    def test_list_breakpoints_nonexistent_job(self, client):
        """Test listing breakpoints for non-existent job."""
        response = client.get("/api/v1/jobs/nonexistent_job_id/breakpoints")
        assert response.status_code == 404


class TestBreakpointAPIDelete:
    """Test breakpoint deletion API."""

    def test_delete_breakpoint_success(self, client, setup_test_flow):
        """Test successfully deleting a breakpoint."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "test_breakpoint_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"value": 42},
            },
        )
        job_id = response.json()["job_id"]

        # Create breakpoint
        bp_response = client.post(
            f"/api/jobs/{job_id}/breakpoints",
            json={"routine_id": "target", "slot_name": "input"},
        )
        breakpoint_id = bp_response.json()["breakpoint_id"]

        # Delete breakpoint
        response = client.delete(f"/api/v1/jobs/{job_id}/breakpoints/{breakpoint_id}")
        assert response.status_code == 204

        # Verify breakpoint is deleted
        list_response = client.get(f"/api/jobs/{job_id}/breakpoints")
        assert list_response.json()["total"] == 0

    def test_delete_breakpoint_nonexistent(self, client, setup_test_flow):
        """Test deleting non-existent breakpoint."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "test_breakpoint_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"value": 42},
            },
        )
        job_id = response.json()["job_id"]

        # Try to delete non-existent breakpoint
        response = client.delete(f"/api/jobs/{job_id}/breakpoints/nonexistent_bp_id")
        assert response.status_code == 404

    def test_delete_breakpoint_nonexistent_job(self, client):
        """Test deleting breakpoint for non-existent job."""
        response = client.delete("/api/v1/jobs/nonexistent_job_id/breakpoints/bp_123")
        assert response.status_code == 404


class TestBreakpointAPIResponseFormat:
    """Test breakpoint API response format matches new design."""

    def test_breakpoint_response_format(self, client, setup_test_flow):
        """Test that breakpoint response matches new API design."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "test_breakpoint_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"value": 42},
            },
        )
        job_id = response.json()["job_id"]

        # Create breakpoint
        response = client.post(
            f"/api/v1/jobs/{job_id}/breakpoints",
            json={
                "routine_id": "target",
                "slot_name": "input",
                "condition": "value > 40",
                "enabled": True,
            },
        )
        assert response.status_code == 201
        data = response.json()

        # Verify all required fields are present
        required_fields = ["breakpoint_id", "job_id", "routine_id", "slot_name", "enabled", "hit_count"]
        for field in required_fields:
            assert field in data, f"Response missing required field: {field}"

        # Verify optional fields
        assert "condition" in data

        # Verify no deprecated fields
        deprecated_fields = ["type", "event_name", "source_routine_id", "source_event_name", 
                           "target_routine_id", "target_slot_name"]
        for field in deprecated_fields:
            assert field not in data, f"Response should not contain deprecated field: {field}"

        # Verify field types
        assert isinstance(data["breakpoint_id"], str)
        assert isinstance(data["job_id"], str)
        assert isinstance(data["routine_id"], str)
        assert isinstance(data["slot_name"], str)
        assert isinstance(data["enabled"], bool)
        assert isinstance(data["hit_count"], int)
        assert data["condition"] is None or isinstance(data["condition"], str)
