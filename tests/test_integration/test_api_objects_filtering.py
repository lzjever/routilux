"""
Tests for object filtering by object_type and category.

Tests the enhanced /api/factory/objects endpoint with object_type filtering.
"""

import pytest
from fastapi.testclient import TestClient
from routilux.server.main import app
from routilux import Flow, Routine
from routilux.tools.factory.factory import ObjectFactory
from routilux.tools.factory.metadata import ObjectMetadata
from routilux.monitoring.storage import flow_store

pytestmark = pytest.mark.integration


@pytest.fixture
def api_client():
    """Create FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def registered_objects():
    """Register test routines and flows in factory."""
    factory = ObjectFactory.get_instance()
    factory.clear()

    # Register routines
    routine1_meta = ObjectMetadata(
        name="data_source",
        description="Data source routine",
        category="data_generation",
        tags=["source"],
        example_config={"name": "DataSource"},
        version="1.0.0",
    )
    factory.register("data_source", Routine, metadata=routine1_meta)

    routine2_meta = ObjectMetadata(
        name="data_processor",
        description="Data processor routine",
        category="transformation",
        tags=["processor"],
        example_config={"name": "Processor"},
        version="1.0.0",
    )
    factory.register("data_processor", Routine, metadata=routine2_meta)

    # Register flows
    flow1 = Flow("template_flow_1")
    flow1_meta = ObjectMetadata(
        name="template_flow_1",
        description="Template flow 1",
        category="template",
        tags=["template"],
        example_config={},
        version="1.0.0",
    )
    factory.register("template_flow_1", flow1, metadata=flow1_meta)

    flow2 = Flow("template_flow_2")
    flow2_meta = ObjectMetadata(
        name="template_flow_2",
        description="Template flow 2",
        category="template",
        tags=["template"],
        example_config={},
        version="1.0.0",
    )
    factory.register("template_flow_2", flow2, metadata=flow2_meta)

    yield

    # Cleanup
    factory.clear()


class TestObjectTypeFiltering:
    """Test object_type filtering functionality."""

    def test_list_all_objects_includes_object_type(self, api_client, registered_objects):
        """Test: All objects include object_type field."""
        response = api_client.get("/api/factory/objects")
        assert response.status_code == 200
        data = response.json()

        assert "objects" in data
        assert len(data["objects"]) == 4  # 2 routines + 2 flows

        # All objects should have object_type field
        for obj in data["objects"]:
            assert "object_type" in obj, f"Object {obj['name']} missing object_type field"
            assert obj["object_type"] in ("routine", "flow"), f"Invalid object_type: {obj['object_type']}"

    def test_filter_by_routine(self, api_client, registered_objects):
        """Test: Filter to get only routines."""
        response = api_client.get("/api/factory/objects?object_type=routine")
        assert response.status_code == 200
        data = response.json()

        assert len(data["objects"]) == 2
        for obj in data["objects"]:
            assert obj["object_type"] == "routine"
            assert obj["name"] in ("data_source", "data_processor")

    def test_filter_by_flow(self, api_client, registered_objects):
        """Test: Filter to get only flows."""
        response = api_client.get("/api/factory/objects?object_type=flow")
        assert response.status_code == 200
        data = response.json()

        assert len(data["objects"]) == 2
        for obj in data["objects"]:
            assert obj["object_type"] == "flow"
            assert obj["name"] in ("template_flow_1", "template_flow_2")

    def test_filter_by_category(self, api_client, registered_objects):
        """Test: Filter by category still works."""
        response = api_client.get("/api/factory/objects?category=data_generation")
        assert response.status_code == 200
        data = response.json()

        assert len(data["objects"]) == 1
        assert data["objects"][0]["name"] == "data_source"
        assert data["objects"][0]["category"] == "data_generation"

    def test_combine_category_and_object_type(self, api_client, registered_objects):
        """Test: Combine category and object_type filters."""
        # Get routines in data_generation category
        response = api_client.get("/api/factory/objects?category=data_generation&object_type=routine")
        assert response.status_code == 200
        data = response.json()

        assert len(data["objects"]) == 1
        assert data["objects"][0]["name"] == "data_source"
        assert data["objects"][0]["object_type"] == "routine"
        assert data["objects"][0]["category"] == "data_generation"

        # Get flows in template category
        response = api_client.get("/api/factory/objects?category=template&object_type=flow")
        assert response.status_code == 200
        data = response.json()

        assert len(data["objects"]) == 2
        for obj in data["objects"]:
            assert obj["object_type"] == "flow"
            assert obj["category"] == "template"

    def test_invalid_object_type(self, api_client, registered_objects):
        """Test: 422 error for invalid object_type."""
        response = api_client.get("/api/factory/objects?object_type=invalid")
        assert response.status_code == 422
        assert "Invalid object_type" in response.json()["detail"]

    def test_object_type_field_values(self, api_client, registered_objects):
        """Test: object_type field has correct values."""
        response = api_client.get("/api/factory/objects")
        assert response.status_code == 200
        data = response.json()

        # Check routines have object_type="routine"
        routines = [obj for obj in data["objects"] if obj["object_type"] == "routine"]
        assert len(routines) == 2
        for routine in routines:
            assert routine["name"] in ("data_source", "data_processor")

        # Check flows have object_type="flow"
        flows = [obj for obj in data["objects"] if obj["object_type"] == "flow"]
        assert len(flows) == 2
        for flow in flows:
            assert flow["name"] in ("template_flow_1", "template_flow_2")

    def test_type_vs_object_type_distinction(self, api_client, registered_objects):
        """Test: type and object_type are different fields."""
        response = api_client.get("/api/factory/objects")
        assert response.status_code == 200
        data = response.json()

        for obj in data["objects"]:
            # type is prototype type (class/instance)
            assert obj["type"] in ("class", "instance")
            # object_type is object type (routine/flow)
            assert obj["object_type"] in ("routine", "flow")
            # They are different concepts
            assert obj["type"] != obj["object_type"]


class TestObjectTypeClientUsage:
    """Test realistic client usage scenarios."""

    def test_client_can_separate_routines_and_flows(self, api_client, registered_objects):
        """Test: Client can easily separate routines and flows."""
        # Get all objects
        response = api_client.get("/api/factory/objects")
        assert response.status_code == 200
        data = response.json()

        # Client-side filtering
        routines = [obj for obj in data["objects"] if obj["object_type"] == "routine"]
        flows = [obj for obj in data["objects"] if obj["object_type"] == "flow"]

        assert len(routines) == 2
        assert len(flows) == 2

        # Client can now build UI:
        # - "Available Routines" section with routines
        # - "Flow Templates" section with flows

    def test_client_can_filter_server_side(self, api_client, registered_objects):
        """Test: Client can filter server-side for better performance."""
        # Get only routines (server-side filter)
        routines_response = api_client.get("/api/factory/objects?object_type=routine")
        assert routines_response.status_code == 200
        routines = routines_response.json()["objects"]

        # Get only flows (server-side filter)
        flows_response = api_client.get("/api/factory/objects?object_type=flow")
        assert flows_response.status_code == 200
        flows = flows_response.json()["objects"]

        # No client-side filtering needed
        assert len(routines) == 2
        assert len(flows) == 2
        assert all(obj["object_type"] == "routine" for obj in routines)
        assert all(obj["object_type"] == "flow" for obj in flows)

    def test_client_can_build_routine_selector(self, api_client, registered_objects):
        """Test: Client can build routine selector UI."""
        # Get all routines for selector
        response = api_client.get("/api/factory/objects?object_type=routine")
        assert response.status_code == 200
        routines = response.json()["objects"]

        # Build selector options
        selector_options = [
            {"value": r["name"], "label": f"{r['name']} - {r['description']}"}
            for r in routines
        ]

        assert len(selector_options) == 2
        assert all("value" in opt and "label" in opt for opt in selector_options)

    def test_client_can_build_flow_template_selector(self, api_client, registered_objects):
        """Test: Client can build flow template selector UI."""
        # Get all flows for template selector
        response = api_client.get("/api/factory/objects?object_type=flow")
        assert response.status_code == 200
        flows = response.json()["objects"]

        # Build template selector
        template_options = [
            {"value": f["name"], "label": f["description"]} for f in flows
        ]

        assert len(template_options) == 2
        assert all("value" in opt and "label" in opt for opt in template_options)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
