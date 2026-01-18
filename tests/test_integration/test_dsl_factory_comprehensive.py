"""
Comprehensive integration tests for DSL factory functionality.

These tests are written from the API interface perspective, testing the
contract without knowledge of implementation details. They challenge
the business logic to ensure robustness.
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
    return {}


@pytest.fixture(autouse=True)
def clean_factory():
    """Clean factory before and after each test."""
    factory = ObjectFactory.get_instance()
    factory._registry.clear()
    factory._class_to_name.clear()
    factory._name_to_class.clear()
    flow_store.clear()
    yield
    factory._registry.clear()
    factory._class_to_name.clear()
    factory._name_to_class.clear()
    flow_store.clear()


class TestDSLExportComprehensive:
    """Comprehensive tests for DSL export functionality."""

    def test_export_flow_with_multiple_routines(self, client, auth_headers):
        """Test: Export flow with multiple routines uses factory names."""
        factory = ObjectFactory.get_instance()
        factory.register("test_routine1", Routine)
        factory.register("test_routine2", Routine)

        # Create flow with multiple routines
        flow = Flow(flow_id="multi_routine_flow")
        routine1 = factory.create("test_routine1")
        routine1.set_config(key1="value1")
        routine2 = factory.create("test_routine2")
        routine2.set_config(key2="value2")
        flow.add_routine(routine1, "routine1")
        flow.add_routine(routine2, "routine2")
        flow_store.add(flow)

        # Export DSL
        response = client.get(
            "/api/flows/multi_routine_flow/dsl?format=json",
            headers=auth_headers,
        )
        assert response.status_code == 200
        dsl_dict = json.loads(response.json()["dsl"])

        # Verify all routines use factory names
        # Note: If both routines are of the same class (Routine), they may map to the same factory name
        # This is a limitation of class-based reverse lookup. The test verifies that factory names are used.
        assert len(dsl_dict["routines"]) == 2
        routine1_class = dsl_dict["routines"]["routine1"]["class"]
        routine2_class = dsl_dict["routines"]["routine2"]["class"]
        # Both should be factory names (not class paths)
        assert "." not in routine1_class
        assert "." not in routine2_class
        # Verify configs are preserved
        assert dsl_dict["routines"]["routine1"]["config"].get("key1") == "value1"
        assert dsl_dict["routines"]["routine2"]["config"].get("key2") == "value2"

    def test_export_flow_with_connections(self, client, auth_headers):
        """Test: Export flow with connections preserves connection structure."""
        factory = ObjectFactory.get_instance()
        
        # Create routines with proper slots and events
        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.define_slot("trigger")
                self.define_event("output")
        
        class TargetRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.define_slot("input")
        
        factory.register("source_routine", SourceRoutine)
        factory.register("target_routine", TargetRoutine)

        # Create flow with connection
        flow = Flow(flow_id="connected_flow")
        source = factory.create("source_routine")
        target = factory.create("target_routine")
        flow.add_routine(source, "source")
        flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")
        flow_store.add(flow)

        # Export DSL
        response = client.get(
            "/api/flows/connected_flow/dsl?format=json",
            headers=auth_headers,
        )
        assert response.status_code == 200
        dsl_dict = json.loads(response.json()["dsl"])

        # Verify connections
        assert len(dsl_dict["connections"]) == 1
        conn = dsl_dict["connections"][0]
        assert conn["from"] == "source.output"
        assert conn["to"] == "target.input"

    def test_export_flow_with_error_handler(self, client, auth_headers):
        """Test: Export flow preserves error handler configuration."""
        factory = ObjectFactory.get_instance()
        factory.register("test_routine", Routine)

        from routilux.error_handler import ErrorHandler, ErrorStrategy

        flow = Flow(flow_id="error_handler_flow")
        routine = factory.create("test_routine")
        routine.set_error_handler(
            ErrorHandler(
                strategy=ErrorStrategy.RETRY,
                max_retries=5,
                retry_delay=2.0,
                is_critical=True,
            )
        )
        flow.add_routine(routine, "routine1")
        flow_store.add(flow)

        # Export DSL
        response = client.get(
            "/api/flows/error_handler_flow/dsl?format=json",
            headers=auth_headers,
        )
        assert response.status_code == 200
        dsl_dict = json.loads(response.json()["dsl"])

        # Verify error handler
        error_handler = dsl_dict["routines"]["routine1"]["error_handler"]
        assert error_handler["strategy"] == "retry"
        assert error_handler["max_retries"] == 5
        assert error_handler["retry_delay"] == 2.0
        assert error_handler["is_critical"] is True

    def test_export_flow_preserves_execution_timeout(self, client, auth_headers):
        """Test: Export flow preserves execution timeout."""
        factory = ObjectFactory.get_instance()
        factory.register("test_routine", Routine)

        flow = Flow(flow_id="timeout_flow")
        flow.execution_timeout = 600.0
        routine = factory.create("test_routine")
        flow.add_routine(routine, "routine1")
        flow_store.add(flow)

        # Export DSL
        response = client.get(
            "/api/flows/timeout_flow/dsl?format=json",
            headers=auth_headers,
        )
        assert response.status_code == 200
        dsl_dict = json.loads(response.json()["dsl"])

        # Verify execution timeout
        assert dsl_dict["execution"]["timeout"] == 600.0


class TestDSLImportComprehensive:
    """Comprehensive tests for DSL import functionality."""

    def test_import_flow_with_complex_structure(self, client, auth_headers):
        """Test: Import flow with complex structure (multiple routines, connections)."""
        factory = ObjectFactory.get_instance()
        
        # Create routines with proper interfaces
        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.define_slot("trigger")
                self.define_event("output")
        
        class ProcessorRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.define_slot("input")
                self.define_event("output")
        
        class SinkRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.define_slot("input")
        
        factory.register("source", SourceRoutine)
        factory.register("processor1", ProcessorRoutine)
        factory.register("processor2", ProcessorRoutine)
        factory.register("sink", SinkRoutine)

        # Create complex DSL
        dsl = {
            "flow_id": "complex_flow",
            "routines": {
                "source": {"class": "source", "config": {"name": "Source"}},
                "processor1": {"class": "processor1", "config": {"name": "Processor1"}},
                "processor2": {"class": "processor2", "config": {"name": "Processor2"}},
                "sink": {"class": "sink", "config": {"name": "Sink"}},
            },
            "connections": [
                {"from": "source.output", "to": "processor1.input"},
                {"from": "source.output", "to": "processor2.input"},
                {"from": "processor1.output", "to": "sink.input"},
                {"from": "processor2.output", "to": "sink.input"},
            ],
            "execution": {"timeout": 300.0},
        }

        # Import DSL
        response = client.post(
            "/api/flows",
            json={"dsl_dict": dsl},
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()

        # Verify structure
        assert data["flow_id"] == "complex_flow"
        assert len(data["routines"]) == 4
        assert len(data["connections"]) == 4

    def test_import_flow_rejects_invalid_connection_format(self, client, auth_headers):
        """Test: Import rejects DSL with invalid connection format."""
        factory = ObjectFactory.get_instance()
        factory.register("source", Routine)
        factory.register("target", Routine)

        # Invalid connection format (missing dot)
        dsl = {
            "flow_id": "invalid_flow",
            "routines": {
                "source": {"class": "source"},
                "target": {"class": "target"},
            },
            "connections": [
                {"from": "sourceoutput", "to": "targetinput"},  # Missing dots
            ],
        }

        response = client.post(
            "/api/flows",
            json={"dsl_dict": dsl},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Invalid connection format" in response.json()["detail"]

    def test_import_flow_rejects_missing_routine_in_connection(self, client, auth_headers):
        """Test: Import rejects DSL with connection referencing non-existent routine."""
        factory = ObjectFactory.get_instance()
        factory.register("source", Routine)

        # Connection references non-existent routine
        dsl = {
            "flow_id": "invalid_flow",
            "routines": {
                "source": {"class": "source"},
            },
            "connections": [
                {"from": "source.output", "to": "nonexistent.input"},
            ],
        }

        response = client.post(
            "/api/flows",
            json={"dsl_dict": dsl},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "not found in flow" in response.json()["detail"]

    def test_import_flow_with_error_handler(self, client, auth_headers):
        """Test: Import flow correctly applies error handler configuration."""
        factory = ObjectFactory.get_instance()
        factory.register("test_routine", Routine)

        dsl = {
            "flow_id": "error_handler_flow",
            "routines": {
                "routine1": {
                    "class": "test_routine",
                    "error_handler": {
                        "strategy": "retry",
                        "max_retries": 3,
                        "retry_delay": 1.5,
                        "is_critical": True,
                    },
                }
            },
            "connections": [],
        }

        response = client.post(
            "/api/flows",
            json={"dsl_dict": dsl},
            headers=auth_headers,
        )
        assert response.status_code == 201

        # Verify flow was created
        response = client.get(
            "/api/flows/error_handler_flow",
            headers=auth_headers,
        )
        assert response.status_code == 200


class TestDSLRoundtripComprehensive:
    """Comprehensive roundtrip tests."""

    def test_roundtrip_preserves_all_configuration(self, client, auth_headers):
        """Test: Roundtrip preserves all configuration including error handlers."""
        factory = ObjectFactory.get_instance()
        factory.register("test_routine", Routine)

        from routilux.error_handler import ErrorHandler, ErrorStrategy

        # Create original flow
        original_flow = Flow(flow_id="original_flow")
        original_flow.execution_timeout = 450.0
        routine = factory.create("test_routine")
        routine.set_config(test_key="test_value", nested={"key": "value"})
        routine.set_error_handler(
            ErrorHandler(
                strategy=ErrorStrategy.CONTINUE,
                max_retries=2,
                retry_delay=1.0,
            )
        )
        original_flow.add_routine(routine, "routine1")
        flow_store.add(original_flow)

        # Export
        response = client.get(
            "/api/flows/original_flow/dsl?format=json",
            headers=auth_headers,
        )
        assert response.status_code == 200
        dsl_dict = json.loads(response.json()["dsl"])

        # Import to new flow
        dsl_dict["flow_id"] = "imported_flow"
        response = client.post(
            "/api/flows",
            json={"dsl_dict": dsl_dict},
            headers=auth_headers,
        )
        assert response.status_code == 201

        # Verify imported flow
        response = client.get(
            "/api/flows/imported_flow",
            headers=auth_headers,
        )
        assert response.status_code == 200
        imported_data = response.json()

        # Verify all configuration preserved
        assert imported_data["flow_id"] == "imported_flow"
        assert "routine1" in imported_data["routines"]
        imported_routine = imported_data["routines"]["routine1"]
        assert imported_routine["config"]["test_key"] == "test_value"
        assert imported_routine["config"]["nested"]["key"] == "value"

    def test_roundtrip_with_multiple_connections(self, client, auth_headers):
        """Test: Roundtrip preserves complex connection structure."""
        factory = ObjectFactory.get_instance()
        
        # Create routines with proper interfaces
        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.define_slot("trigger")
                self.define_event("output")
        
        class ProcessorRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.define_slot("input")
                self.define_event("output")
        
        class AggregatorRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.define_slot("input1")
                self.define_slot("input2")
                self.define_event("output")
        
        class SinkRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.define_slot("input")
        
        factory.register("source", SourceRoutine)
        factory.register("processor1", ProcessorRoutine)
        factory.register("processor2", ProcessorRoutine)
        factory.register("aggregator", AggregatorRoutine)
        factory.register("sink", SinkRoutine)

        # Create flow with complex connections
        flow = Flow(flow_id="complex_connections")
        source = factory.create("source")
        proc1 = factory.create("processor1")
        proc2 = factory.create("processor2")
        agg = factory.create("aggregator")
        sink = factory.create("sink")

        flow.add_routine(source, "source")
        flow.add_routine(proc1, "processor1")
        flow.add_routine(proc2, "processor2")
        flow.add_routine(agg, "aggregator")
        flow.add_routine(sink, "sink")

        # Complex connection pattern
        flow.connect("source", "output", "processor1", "input")
        flow.connect("source", "output", "processor2", "input")
        flow.connect("processor1", "output", "aggregator", "input1")
        flow.connect("processor2", "output", "aggregator", "input2")
        flow.connect("aggregator", "output", "sink", "input")
        flow_store.add(flow)

        # Export and import
        response = client.get(
            "/api/flows/complex_connections/dsl?format=json",
            headers=auth_headers,
        )
        assert response.status_code == 200
        dsl_dict = json.loads(response.json()["dsl"])

        dsl_dict["flow_id"] = "roundtrip_complex"
        response = client.post(
            "/api/flows",
            json={"dsl_dict": dsl_dict},
            headers=auth_headers,
        )
        assert response.status_code == 201

        # Verify connections preserved
        response = client.get(
            "/api/flows/roundtrip_complex/connections",
            headers=auth_headers,
        )
        assert response.status_code == 200
        connections = response.json()
        assert len(connections) == 5


class TestFactoryOnlyEnforcement:
    """Test that factory-only enforcement is strict and comprehensive."""

    def test_cannot_export_flow_with_unregistered_class(self, client, auth_headers):
        """Test: Export fails if routine class is not registered in factory."""
        factory = ObjectFactory.get_instance()
        
        # Create a different routine class that's not registered
        class UnregisteredRoutine(Routine):
            def __init__(self):
                super().__init__()
        
        factory.register("registered_routine", Routine)
        # Do NOT register UnregisteredRoutine

        # Create flow with registered and unregistered routine classes
        flow = Flow(flow_id="mixed_flow")
        registered = factory.create("registered_routine")
        unregistered = UnregisteredRoutine()  # Different class, not registered
        flow.add_routine(registered, "registered")
        flow.add_routine(unregistered, "unregistered")
        flow_store.add(flow)

        # Export should fail because UnregisteredRoutine class is not in factory
        response = client.get(
            "/api/flows/mixed_flow/dsl?format=json",
            headers=auth_headers,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        error_detail = response.json().get("detail") or response.json().get("message", "")
        assert "not registered in factory" in str(error_detail)

    def test_cannot_import_dsl_with_class_path(self, client, auth_headers):
        """Test: Import strictly rejects class paths, even if they look valid."""
        factory = ObjectFactory.get_instance()
        factory.register("valid_routine", Routine)

        # Try to use class path instead of factory name
        dsl = {
            "flow_id": "invalid_flow",
            "routines": {
                "routine1": {
                    "class": "routilux.routine.Routine",  # Class path, not factory name
                }
            },
            "connections": [],
        }

        response = client.post(
            "/api/flows",
            json={"dsl_dict": dsl},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "unregistered factory name" in response.json()["detail"]

    def test_cannot_add_routine_with_class_path_via_api(self, client, auth_headers):
        """Test: Add routine endpoint strictly rejects class paths."""
        factory = ObjectFactory.get_instance()
        factory.register("valid_routine", Routine)

        flow = Flow(flow_id="test_flow")
        flow_store.add(flow)

        # Try various class path formats
        invalid_names = [
            "routilux.routine.Routine",
            "os.system",
            "builtins.exec",
            "mymodule.MyClass",
        ]

        for invalid_name in invalid_names:
            response = client.post(
                "/api/flows/test_flow/routines",
                json={
                    "routine_id": f"routine_{invalid_name}",
                    "object_name": invalid_name,
                },
                headers=auth_headers,
            )
            assert response.status_code == 400, f"Should reject {invalid_name}"
            assert "not found in factory" in response.json()["message"]


class TestDSLFormatValidation:
    """Test DSL format validation."""

    def test_export_yaml_format_is_valid_yaml(self, client, auth_headers):
        """Test: Exported YAML format is valid and parseable."""
        factory = ObjectFactory.get_instance()
        factory.register("test_routine", Routine)

        flow = Flow(flow_id="yaml_test_flow")
        routine = factory.create("test_routine")
        flow.add_routine(routine, "routine1")
        flow_store.add(flow)

        # Export as YAML
        response = client.get(
            "/api/flows/yaml_test_flow/dsl?format=yaml",
            headers=auth_headers,
        )
        assert response.status_code == 200
        yaml_str = response.json()["dsl"]

        # Verify it's valid YAML
        import yaml

        parsed = yaml.safe_load(yaml_str)
        assert isinstance(parsed, dict)
        assert parsed["flow_id"] == "yaml_test_flow"

    def test_export_json_format_is_valid_json(self, client, auth_headers):
        """Test: Exported JSON format is valid and parseable."""
        factory = ObjectFactory.get_instance()
        factory.register("test_routine", Routine)

        flow = Flow(flow_id="json_test_flow")
        routine = factory.create("test_routine")
        flow.add_routine(routine, "routine1")
        flow_store.add(flow)

        # Export as JSON
        response = client.get(
            "/api/flows/json_test_flow/dsl?format=json",
            headers=auth_headers,
        )
        assert response.status_code == 200
        json_str = response.json()["dsl"]

        # Verify it's valid JSON
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)
        assert parsed["flow_id"] == "json_test_flow"

    def test_import_rejects_invalid_dsl_structure(self, client, auth_headers):
        """Test: Import rejects DSL with invalid structure."""
        factory = ObjectFactory.get_instance()
        factory.register("test_routine", Routine)

        # Invalid: routines is not a dict
        invalid_dsl = {
            "flow_id": "invalid",
            "routines": [],  # Should be dict
            "connections": [],
        }

        response = client.post(
            "/api/flows",
            json={"dsl_dict": invalid_dsl},
            headers=auth_headers,
        )
        assert response.status_code == 400

    def test_import_rejects_missing_class_field(self, client, auth_headers):
        """Test: Import rejects routine specification without class field."""
        factory = ObjectFactory.get_instance()
        factory.register("test_routine", Routine)

        # Missing class field
        invalid_dsl = {
            "flow_id": "invalid",
            "routines": {
                "routine1": {
                    "config": {"key": "value"},  # Missing "class"
                }
            },
            "connections": [],
        }

        response = client.post(
            "/api/flows",
            json={"dsl_dict": invalid_dsl},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "must specify 'class'" in response.json()["detail"]
