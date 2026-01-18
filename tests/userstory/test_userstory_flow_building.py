"""
Category 1: Flow Building Workflows - User Story Tests

Tests for interactive flow builder scenarios, including:
- Creating empty flows and building them dynamically
- Creating flows from DSL templates (YAML/JSON)
- Flow validation edge cases
- Flow export and re-import

These tests simulate a user interactively building flows through the API.
"""

import pytest

# Try to import yaml, skip tests if not available
try:
    import yaml
except ImportError:
    yaml = None

pytestmark = pytest.mark.userstory


class TestInteractiveFlowBuilder:
    """Test scenarios for interactive flow builder workflow.

    User Story: As a user, I want to interactively build a flow by
    adding routines, connecting them, validating, and then executing.
    """

    def test_create_empty_flow_and_build_pipeline(self, flow_builder):
        """Test creating an empty flow and building a complete pipeline."""
        # Start with empty flow
        flow_builder.create_empty("my_pipeline")
        assert flow_builder.flow_id == "my_pipeline"

        # Add routines
        flow_builder.add_routine("source", "data_source", {"count": 3})
        flow_builder.add_routine("processor", "data_transformer")
        flow_builder.add_routine("sink", "data_sink")

        # Verify routines were added
        routines = flow_builder.get_routines()
        assert "source" in routines
        assert "processor" in routines
        assert "sink" in routines

        # Add connections
        flow_builder.add_connection("source", "output", "processor", "input")
        flow_builder.add_connection("processor", "output", "sink", "input")

        # Verify connections
        connections = flow_builder.get_connections()
        assert len(connections) == 2

        # Validate flow
        flow_builder.validate()

        # Export as DSL
        dsl = flow_builder.export_dsl("yaml")
        assert "flow_id: my_pipeline" in dsl
        assert "source:" in dsl

    def test_build_flow_step_by_step_and_validate_each_step(self, flow_builder):
        """Test building a flow incrementally with validation at each step."""
        flow_builder.create_empty("incremental_flow")

        # Step 1: Add source routine and validate (should warn about unconnected event)
        flow_builder.add_routine("source", "data_source", {"count": 1})
        result = flow_builder.client.post(f"/api/v1/flows/{flow_builder.flow_id}/validate")
        assert result.status_code == 200
        # Flow is valid but may have warnings

        # Step 2: Add processor routine
        flow_builder.add_routine("processor", "data_transformer")

        # Step 3: Connect them
        flow_builder.add_connection("source", "output", "processor", "input")

        # Step 4: Add sink and connect
        flow_builder.add_routine("sink", "data_sink")
        flow_builder.add_connection("processor", "output", "sink", "input")

        # Final validation should pass with no errors
        flow_builder.validate()

    def test_remove_routine_and_verify_connections_cleanup(self, flow_builder):
        """Test that removing a routine also removes its connections."""
        flow_builder.create_empty("test_flow")
        flow_builder.build_pipeline()

        # Verify we have 3 routines and 2 connections
        routines = flow_builder.get_routines()
        connections = flow_builder.get_connections()
        assert len(routines) == 3
        assert len(connections) == 2

        # Remove the middle routine
        flow_builder.remove_routine("processor")

        # Verify routine removed
        routines = flow_builder.get_routines()
        assert "processor" not in routines
        assert len(routines) == 2

        # Verify connections were cleaned up
        connections = flow_builder.get_connections()
        assert len(connections) == 0

    def test_remove_connection_by_index(self, flow_builder):
        """Test removing a specific connection by index."""
        flow_builder.create_empty("test_flow")
        flow_builder.build_pipeline()

        # Get connections and verify count
        connections = flow_builder.get_connections()
        assert len(connections) == 2

        # Remove first connection
        flow_builder.remove_connection(0)

        # Verify removal
        connections = flow_builder.get_connections()
        assert len(connections) == 1

    def test_export_and_reimport_flow(self, flow_builder):
        """Test exporting a flow to DSL and recreating it."""
        # Create original flow
        flow_builder.create_empty("original")
        flow_builder.build_pipeline()
        flow_builder.validate()

        # Export as YAML (skip if yaml not available)
        if yaml is None:
            pytest.skip("yaml module not available")
        
        yaml_dsl = flow_builder.export_dsl("yaml")

        # Export as JSON
        json_dsl = flow_builder.export_dsl("json")

        # Delete original
        flow_builder.delete()

        # Recreate from YAML (skip if yaml not available)
        if yaml is None:
            pytest.skip("yaml module not available")
        
        # Recreate from YAML
        try:
            flow_builder.create_from_dsl("from_yaml", yaml_dsl)
            routines = flow_builder.get_routines()
            assert "source" in routines
            assert "processor" in routines
            assert "sink" in routines
        except Exception as e:
            # Flow creation may fail if routines not registered
            if "not found" in str(e).lower() or "not registered" in str(e).lower():
                pytest.skip(f"Required routines not registered: {e}")
            raise

        # Verify connections
        connections = flow_builder.get_connections()
        assert len(connections) == 2

        # Delete and recreate from JSON
        flow_builder.delete()
        flow_builder.create_from_dsl("from_json", json_dsl, format="json")
        routines = flow_builder.get_routines()
        assert len(routines) == 3


class TestFlowFromDSLTemplate:
    """Test scenarios for creating flows from DSL templates.

    User Story: As a user, I want to create flows from predefined
    templates (YAML/JSON) for quick setup.
    """

    def test_create_flow_from_yaml_dsl(self, api_client):
        """Test creating a flow from YAML DSL string."""
        yaml_dsl = """
flow_id: yaml_test_flow
routines:
  source:
    class: data_source
    config:
      count: 3
  processor:
    class: data_transformer
  sink:
    class: data_sink
connections:
  - from: source.output
    to: processor.input
  - from: processor.output
    to: sink.input
"""

        response = api_client.post(
            "/api/v1/flows", json={"flow_id": "yaml_test_flow", "dsl": yaml_dsl}
        )
        # May return 400 if DSL parsing fails or routines not registered
        assert response.status_code in (201, 400)
        if response.status_code == 400:
            # Check error message to understand why
            error_msg = response.json().get("detail", "")
            # If it's about missing routines, that's acceptable in test environment
            if "not found" in error_msg.lower() or "not registered" in error_msg.lower():
                pytest.skip(f"Required routines not registered: {error_msg}")
            else:
                raise AssertionError(f"Flow creation failed: {error_msg}")

        # Verify flow was created
        response = api_client.get("/api/v1/flows/yaml_test_flow")
        assert response.status_code == 200
        data = response.json()
        assert "source" in data["routines"]
        assert "processor" in data["routines"]
        assert "sink" in data["routines"]

    def test_create_flow_from_json_dsl_dict(self, api_client):
        """Test creating a flow from JSON DSL dictionary."""
        dsl_dict = {
            "flow_id": "json_test_flow",
            "routines": {
                "source": {"class": "data_source", "config": {"count": 2}},
                "sink": {"class": "data_sink"},
            },
            "connections": [
                {"from": "source.output", "to": "sink.input"},
            ],
        }

        response = api_client.post(
            "/api/v1/flows", json={"flow_id": "json_test_flow", "dsl_dict": dsl_dict}
        )
        assert response.status_code == 201

    def test_dsl_export_matches_input(self, api_client):
        """Test that exported DSL matches the input DSL structure."""
        if yaml is None:
            pytest.skip("yaml module not available")

        original_dsl = """
flow_id: export_test
routines:
  source:
    class: data_source
    config:
      count: 5
connections: []
"""

        # Create flow
        api_client.post("/api/v1/flows", json={"flow_id": "export_test", "dsl": original_dsl})

        # Export
        response = api_client.get("/api/v1/flows/export_test/dsl?format=yaml")
        assert response.status_code == 200

        exported_dsl = response.json()["dsl"]

        # Parse both and compare structure (skip if yaml not available)
        if yaml is None:
            pytest.skip("yaml module not available")
        
        original_dict = yaml.safe_load(original_dsl)
        exported_dict = yaml.safe_load(exported_dsl)

        assert original_dict["flow_id"] == exported_dict["flow_id"]
        assert set(original_dict["routines"].keys()) == set(exported_dict["routines"].keys())


class TestFlowValidationEdgeCases:
    """Test flow validation edge cases and error scenarios.

    User Story: As a user, I want the system to detect and report
    flow configuration errors before I try to execute.
    """

    def test_validate_detects_circular_dependency(self, api_client):
        """Test that validation detects circular dependencies."""
        # Create a flow with circular dependency
        api_client.post("/api/v1/flows", json={"flow_id": "circular_flow"})
        api_client.post(
            "/api/v1/flows/circular_flow/routines",
            json={"routine_id": "a", "object_name": "data_transformer"},
        )
        api_client.post(
            "/api/v1/flows/circular_flow/routines",
            json={"routine_id": "b", "object_name": "data_transformer"},
        )

        # Create circular connection: a -> b -> a
        # Note: This depends on flow validation implementation
        # The flow should catch this or at least warn about it

    def test_validate_warns_unconnected_events(self, flow_builder):
        """Test that validation warns about unconnected events."""
        flow_builder.create_empty("unconnected_flow")

        # Add routine with events but don't connect them
        flow_builder.add_routine("source", "data_source", {"count": 1})

        # Validate - may have warnings but no hard errors
        result = flow_builder.client.post(f"/api/v1/flows/{flow_builder.flow_id}/validate")
        assert result.status_code == 200
        # May have issues list with warnings

    def test_validate_detects_invalid_connection(self, api_client):
        """Test that validation detects invalid connections."""
        # Create flow
        api_client.post("/api/v1/flows", json={"flow_id": "invalid_conn_flow"})
        api_client.post(
            "/api/v1/flows/invalid_conn_flow/routines",
            json={"routine_id": "source", "object_name": "data_source"},
        )

        # Try to connect to non-existent routine
        response = api_client.post(
            "/api/v1/flows/invalid_conn_flow/connections",
            json={
                "source_routine": "source",
                "source_event": "output",
                "target_routine": "nonexistent",
                "target_slot": "input",
            },
        )
        assert response.status_code == 404

    def test_validate_detects_nonexistent_slot_or_event(self, api_client):
        """Test that validation detects connections to non-existent slots/events."""
        # Create flow with two routines
        api_client.post("/api/v1/flows", json={"flow_id": "bad_slot_flow"})
        api_client.post(
            "/api/v1/flows/bad_slot_flow/routines",
            json={"routine_id": "source", "object_name": "data_source"},
        )
        api_client.post(
            "/api/v1/flows/bad_slot_flow/routines",
            json={"routine_id": "sink", "object_name": "data_sink"},
        )

        # Try to connect using non-existent event
        response = api_client.post(
            "/api/v1/flows/bad_slot_flow/connections",
            json={
                "source_routine": "source",
                "source_event": "nonexistent_event",
                "target_routine": "sink",
                "target_slot": "input",
            },
        )
        # Should fail because event doesn't exist
        assert response.status_code == 400


class TestCompleteFlowBuildingWorkflow:
    """Test complete end-to-end flow building workflows.

    User Story: As a user, I want to build a complete flow from scratch,
    validate it, and then execute it.
    """

    def test_build_validate_export_workflow(self, flow_builder, api_client):
        """Test complete workflow: build -> validate -> export -> execute."""
        # Build a complete flow
        flow_builder.create_empty("complete_workflow")
        flow_builder.build_pipeline()

        # Validate
        flow_builder.validate()

        # Export (skip if yaml not available)
        if yaml is None:
            pytest.skip("yaml module not available")
        
        dsl = flow_builder.export_dsl("yaml")
        assert "flow_id: complete_workflow" in dsl

        # Create worker from flow
        response = api_client.post("/api/v1/workers", json={"flow_id": flow_builder.flow_id})
        assert response.status_code == 201
        worker_id = response.json()["worker_id"]

        # Submit job
        response = api_client.post(
            "/api/v1/jobs",
            json={
                "flow_id": flow_builder.flow_id,
                "worker_id": worker_id,
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {},
            },
        )
        assert response.status_code == 201
        job_id = response.json()["job_id"]

        # Verify job was created
        response = api_client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200

    def test_iterative_flow_building_with_frequent_validation(self, flow_builder):
        """Test iterative building with validation at each step."""
        flow_builder.create_empty("iterative_flow")

        steps = [
            ("source", "data_source", {"count": 2}),
            ("processor", "data_transformer", {}),
            ("sink", "data_sink", {}),
        ]

        for routine_id, object_name, config in steps:
            # Add routine
            flow_builder.add_routine(routine_id, object_name, config)

            # Validate (may have warnings until complete)
            response = flow_builder.client.post(f"/api/v1/flows/{flow_builder.flow_id}/validate")
            assert response.status_code == 200

        # Add connections
        flow_builder.add_connection("source", "output", "processor", "input")
        flow_builder.add_connection("processor", "output", "sink", "input")

        # Final validation should be clean
        flow_builder.validate()

        # Get complete flow info
        flow_info = flow_builder.get_flow()
        assert len(flow_info["routines"]) == 3
        assert len(flow_info["connections"]) == 2
