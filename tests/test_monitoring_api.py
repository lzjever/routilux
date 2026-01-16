"""
Comprehensive tests for monitoring API endpoints.

These tests require the 'api' extra to be installed (pip install routilux[api]).
Tests are written against the API interfaces, challenging the business logic.
"""

import pytest

# Check if FastAPI and httpx are available
try:
    import httpx  # noqa: F401
    from fastapi.testclient import TestClient

    from routilux.api.main import app

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    pytest.skip(
        "FastAPI or httpx not available. Install with: pip install routilux[api] or uv sync --group dev",
        allow_module_level=True
    )

from routilux import Flow, Routine
from routilux.monitoring import MonitoringRegistry
from routilux.monitoring.storage import flow_store, job_store


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def cleanup():
    """Cleanup after tests."""
    yield
    flow_store.clear()
    job_store.clear()
    MonitoringRegistry.disable()


class TestFlowAPI:
    """Test Flow management API endpoints."""

    def test_list_flows_empty(self, client, cleanup):
        """Test listing flows when none exist."""
        response = client.get("/api/flows")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["flows"]) == 0

    def test_create_flow_empty(self, client, cleanup):
        """Test creating an empty flow."""
        response = client.post("/api/flows", json={"flow_id": "test_flow"})
        assert response.status_code == 201
        data = response.json()
        assert data["flow_id"] == "test_flow"
        assert len(data["routines"]) == 0
        assert len(data["connections"]) == 0

    def test_create_flow_from_dsl_dict(self, client, cleanup):
        """Test creating flow from DSL dict."""
        dsl_dict = {
            "flow_id": "dsl_flow",
            "routines": {
                "r1": {
                    "class": "routilux.routine.Routine",
                }
            },
            "connections": [],
        }
        response = client.post("/api/flows", json={"dsl_dict": dsl_dict})
        assert response.status_code == 201
        data = response.json()
        assert data["flow_id"] == "dsl_flow"
        assert "r1" in data["routines"]

    def test_get_flow_not_found(self, client, cleanup):
        """Test getting non-existent flow."""
        response = client.get("/api/flows/nonexistent")
        assert response.status_code == 404

    def test_get_flow(self, client, cleanup):
        """Test getting existing flow."""
        # Create flow
        response = client.post("/api/flows", json={"flow_id": "test_flow"})
        assert response.status_code == 201

        # Get flow
        response = client.get("/api/flows/test_flow")
        assert response.status_code == 200
        data = response.json()
        assert data["flow_id"] == "test_flow"

    def test_delete_flow(self, client, cleanup):
        """Test deleting a flow."""
        # Create flow
        response = client.post("/api/flows", json={"flow_id": "test_flow"})
        assert response.status_code == 201

        # Delete flow
        response = client.delete("/api/flows/test_flow")
        assert response.status_code == 204

        # Verify deleted
        response = client.get("/api/flows/test_flow")
        assert response.status_code == 404

    def test_export_flow_dsl_yaml(self, client, cleanup):
        """Test exporting flow as YAML DSL."""
        # Create flow
        response = client.post("/api/flows", json={"flow_id": "test_flow"})
        assert response.status_code == 201

        # Export as YAML
        response = client.get("/api/flows/test_flow/dsl?format=yaml")
        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "yaml"
        assert "dsl" in data
        assert "flow_id" in data["dsl"] or "test_flow" in data["dsl"]

    def test_export_flow_dsl_json(self, client, cleanup):
        """Test exporting flow as JSON DSL."""
        # Create flow
        response = client.post("/api/flows", json={"flow_id": "test_flow"})
        assert response.status_code == 201

        # Export as JSON
        response = client.get("/api/flows/test_flow/dsl?format=json")
        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "json"
        assert "dsl" in data

    def test_validate_flow(self, client, cleanup):
        """Test validating a flow."""
        # Create flow
        response = client.post("/api/flows", json={"flow_id": "test_flow"})
        assert response.status_code == 201

        # Validate
        response = client.post("/api/flows/test_flow/validate")
        assert response.status_code == 200
        data = response.json()
        assert "valid" in data
        assert "issues" in data


class TestJobAPI:
    """Test Job management API endpoints."""

    def test_start_job_flow_not_found(self, client, cleanup):
        """Test starting job with non-existent flow."""
        response = client.post(
            "/api/jobs",
            json={"flow_id": "nonexistent", "entry_routine_id": "r1"},
        )
        assert response.status_code == 404

    def test_start_job(self, client, cleanup):
        """Test starting a job."""

        # Create flow with routine
        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.define_slot("trigger", handler=lambda **kwargs: None)

        flow = Flow("test_flow")
        routine = TestRoutine()
        flow.add_routine(routine, "r1")
        flow_store.add(flow)

        # Start job
        response = client.post(
            "/api/jobs",
            json={"flow_id": "test_flow", "entry_routine_id": "r1"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["flow_id"] == "test_flow"
        assert "job_id" in data
        assert "status" in data

    def test_list_jobs(self, client, cleanup):
        """Test listing jobs."""
        response = client.get("/api/jobs")
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert "total" in data

    def test_get_job_not_found(self, client, cleanup):
        """Test getting non-existent job."""
        response = client.get("/api/jobs/nonexistent")
        assert response.status_code == 404


class TestBreakpointAPI:
    """Test Breakpoint management API endpoints."""

    def test_create_breakpoint_job_not_found(self, client, cleanup):
        """Test creating breakpoint for non-existent job."""
        response = client.post(
            "/api/jobs/nonexistent/breakpoints",
            json={"type": "routine", "routine_id": "r1"},
        )
        assert response.status_code == 404

    def test_create_breakpoint(self, client, cleanup):
        """Test creating a breakpoint."""

        # Create flow and start job
        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.define_slot("trigger", handler=lambda **kwargs: None)

        flow = Flow("test_flow")
        routine = TestRoutine()
        flow.add_routine(routine, "r1")
        flow_store.add(flow)

        job_response = client.post(
            "/api/jobs",
            json={"flow_id": "test_flow", "entry_routine_id": "r1"},
        )
        job_id = job_response.json()["job_id"]

        # Create breakpoint
        response = client.post(
            f"/api/jobs/{job_id}/breakpoints",
            json={"type": "routine", "routine_id": "r1"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "routine"
        assert data["routine_id"] == "r1"
        assert data["enabled"] is True

    def test_list_breakpoints(self, client, cleanup):
        """Test listing breakpoints."""

        # Create flow and start job
        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.define_slot("trigger", handler=lambda **kwargs: None)

        flow = Flow("test_flow")
        routine = TestRoutine()
        flow.add_routine(routine, "r1")
        flow_store.add(flow)

        job_response = client.post(
            "/api/jobs",
            json={"flow_id": "test_flow", "entry_routine_id": "r1"},
        )
        job_id = job_response.json()["job_id"]

        # List breakpoints (should be empty initially)
        response = client.get(f"/api/jobs/{job_id}/breakpoints")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0


class TestMonitorAPI:
    """Test Monitoring API endpoints."""

    def test_get_job_metrics_not_found(self, client, cleanup):
        """Test getting metrics for non-existent job."""
        response = client.get("/api/jobs/nonexistent/metrics")
        assert response.status_code == 404

    def test_get_job_metrics(self, client, cleanup):
        """Test getting job metrics."""

        # Create flow and start job
        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.define_slot("trigger", handler=lambda **kwargs: None)

        flow = Flow("test_flow")
        routine = TestRoutine()
        flow.add_routine(routine, "r1")
        flow_store.add(flow)

        job_response = client.post(
            "/api/jobs",
            json={"flow_id": "test_flow", "entry_routine_id": "r1"},
        )
        job_id = job_response.json()["job_id"]

        # Get metrics
        response = client.get(f"/api/jobs/{job_id}/metrics")
        # May be 404 if no metrics collected yet, or 200 if metrics exist
        assert response.status_code in (200, 404)

    def test_get_job_trace(self, client, cleanup):
        """Test getting job execution trace."""

        # Create flow and start job
        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.define_slot("trigger", handler=lambda **kwargs: None)

        flow = Flow("test_flow")
        routine = TestRoutine()
        flow.add_routine(routine, "r1")
        flow_store.add(flow)

        job_response = client.post(
            "/api/jobs",
            json={"flow_id": "test_flow", "entry_routine_id": "r1"},
        )
        job_id = job_response.json()["job_id"]

        # Get trace
        response = client.get(f"/api/jobs/{job_id}/trace")
        # May be 404 if no trace collected yet, or 200 if trace exists
        assert response.status_code in (200, 404)


class TestDebugAPI:
    """Test Debug operations API endpoints."""

    def test_get_debug_session_no_session(self, client, cleanup):
        """Test getting debug session when none exists."""

        # Create flow and start job
        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.define_slot("trigger", handler=lambda **kwargs: None)

        flow = Flow("test_flow")
        routine = TestRoutine()
        flow.add_routine(routine, "r1")
        flow_store.add(flow)

        job_response = client.post(
            "/api/jobs",
            json={"flow_id": "test_flow", "entry_routine_id": "r1"},
        )
        job_id = job_response.json()["job_id"]

        # Get debug session (may not exist if no breakpoint hit)
        response = client.get(f"/api/jobs/{job_id}/debug/session")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


class TestHealthAPI:
    """Test health check endpoints."""

    def test_root_endpoint(self, client):
        """Test root endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert data["name"] == "Routilux API"

    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
