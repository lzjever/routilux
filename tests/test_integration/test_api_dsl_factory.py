"""
Integration tests for DSL factory integration.

Tests verify that:
1. DSL export uses factory names
2. DSL import validates factory registration
3. API endpoints enforce factory-only usage
4. End-to-end flow creation/export/import works
"""

import json

import pytest
from fastapi.testclient import TestClient

from routilux import Flow, Routine
from routilux.server.main import app
from routilux.tools.factory.factory import ObjectFactory
from routilux.monitoring.storage import flow_store

# Integration tests marker
pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    """Create FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create auth headers for API requests."""
    # Assuming auth is handled via middleware - adjust if needed
    return {}


class TestDSLExportAPI:
    """Test DSL export via API endpoints."""

    def test_export_flow_dsl_uses_factory_names(self, client, auth_headers):
        """Test: DSL export endpoint returns factory names."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        # Register routine
        factory.register("test_routine", Routine)

        # Create flow via API
        flow = Flow(flow_id="test_flow")
        routine = factory.create("test_routine")
        flow.add_routine(routine, "routine1")
        flow_store.add(flow)

        # Export DSL
        response = client.get(
            "/api/flows/test_flow/dsl?format=json",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "dsl" in data

        import json

        dsl_dict = json.loads(data["dsl"])
        assert dsl_dict["flow_id"] == "test_flow"
        assert "routine1" in dsl_dict["routines"]
        # Verify factory name is used, not class path
        assert dsl_dict["routines"]["routine1"]["class"] == "test_routine"
        assert "." not in dsl_dict["routines"]["routine1"]["class"]  # No class path

    def test_export_flow_unregistered_routine_fails(self, client, auth_headers):
        """Test: Export fails if flow contains unregistered routine."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        # Create flow with unregistered routine
        flow = Flow(flow_id="test_flow")
        unregistered_routine = Routine()
        flow.add_routine(unregistered_routine, "routine1")
        flow_store.add(flow)

        # Export should fail
        response = client.get(
            "/api/flows/test_flow/dsl?format=json",
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "not registered in factory" in response.json()["detail"]


class TestDSLImportAPI:
    """Test DSL import via API endpoints."""

    def test_create_flow_from_dsl_with_factory_names(self, client, auth_headers):
        """Test: Can create flow from DSL with factory names."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        # Register routine
        factory.register("test_routine", Routine)

        # Create flow from DSL
        dsl_dict = {
            "flow_id": "test_flow",
            "routines": {
                "routine1": {
                    "class": "test_routine",
                    "config": {"test": "value"},
                }
            },
            "connections": [],
        }

        import json

        response = client.post(
            "/api/flows",
            json={"dsl_dict": dsl_dict},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["flow_id"] == "test_flow"
        assert "routine1" in data["routines"]

    def test_create_flow_unregistered_component_fails(self, client, auth_headers):
        """Test: Flow creation fails if DSL references unregistered component."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        # Try to create flow with unregistered component
        dsl_dict = {
            "flow_id": "test_flow",
            "routines": {
                "routine1": {
                    "class": "nonexistent_routine",
                }
            },
            "connections": [],
        }

        response = client.post(
            "/api/flows",
            json={"dsl_dict": dsl_dict},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "unregistered factory name" in response.json()["detail"]


class TestDSLRoundtrip:
    """Test end-to-end DSL roundtrip."""

    def test_create_export_import_roundtrip(self, client, auth_headers):
        """Test: Create flow → Export DSL → Import DSL → Verify."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        # Register routine
        factory.register("test_routine", Routine)

        # Step 1: Create flow via API
        flow = Flow(flow_id="original_flow")
        routine = factory.create("test_routine")
        routine.set_config(test_key="test_value")
        flow.add_routine(routine, "routine1")
        flow_store.add(flow)

        # Step 2: Export DSL
        response = client.get(
            "/api/flows/original_flow/dsl?format=json",
            headers=auth_headers,
        )
        assert response.status_code == 200
        dsl_data = response.json()["dsl"]
        dsl_dict = json.loads(dsl_data)

        # Step 3: Import DSL to create new flow
        # Update flow_id in DSL dict
        dsl_dict["flow_id"] = "imported_flow"
        response = client.post(
            "/api/flows",
            json={"dsl_dict": dsl_dict},
            headers=auth_headers,
        )
        assert response.status_code == 201, f"Failed to create flow: {response.text}"

        # Step 4: Verify imported flow
        response = client.get(
            "/api/flows/imported_flow",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["flow_id"] == "imported_flow"
        assert "routine1" in data["routines"]
        assert data["routines"]["routine1"]["config"]["test_key"] == "test_value"


class TestAddRoutineFactoryOnly:
    """Test add routine endpoint enforces factory-only."""

    def test_add_routine_with_factory_name_succeeds(self, client, auth_headers):
        """Test: Can add routine using factory name."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        # Register routine
        factory.register("test_routine", Routine)

        # Create empty flow
        flow = Flow(flow_id="test_flow")
        flow_store.add(flow)

        # Add routine via API
        response = client.post(
            "/api/flows/test_flow/routines",
            json={
                "routine_id": "routine1",
                "object_name": "test_routine",
                "config": {"test": "value"},
            },
            headers=auth_headers,
        )
        assert response.status_code == 200

    def test_add_routine_unregistered_fails(self, client, auth_headers):
        """Test: Adding unregistered routine fails."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        # Create empty flow
        flow = Flow(flow_id="test_flow")
        flow_store.add(flow)

        # Try to add unregistered routine
        response = client.post(
            "/api/flows/test_flow/routines",
            json={
                "routine_id": "routine1",
                "object_name": "nonexistent_routine",
            },
            headers=auth_headers,
        )
        assert response.status_code == 400
        response_data = response.json()
        # Error handler middleware formats response with 'message' and 'detail' fields
        # detail is a string, message is also a string
        message = response_data.get("message") or response_data.get("detail", "")
        assert "not found in factory" in message
