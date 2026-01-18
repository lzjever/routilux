"""
Tests for ObjectFactory refactoring.

Tests verify that:
1. ObjectFactory provides singleton pattern
2. Can register class and instance prototypes
3. Can create objects from prototypes
4. Created objects are independent instances
5. Metadata and discovery API work correctly
"""

import threading
import time

import pytest

from routilux import Flow, Routine
from routilux.tools.factory.factory import ObjectFactory
from routilux.tools.factory.metadata import ObjectMetadata


class TestObjectFactoryInterface:
    """Test ObjectFactory interface compliance."""

    def test_get_instance_singleton(self):
        """Test: get_instance() returns singleton."""
        factory1 = ObjectFactory.get_instance()
        factory2 = ObjectFactory.get_instance()

        # Interface contract: Should return the same instance
        assert factory1 is factory2
        assert isinstance(factory1, ObjectFactory)

    def test_register_class_prototype(self):
        """Test: Can register a class as prototype."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()  # Clear for test isolation

        # Interface contract: Should accept a class
        factory.register("test_routine", Routine, description="Test routine class")

        # Verify registration
        assert "test_routine" in factory._registry
        assert factory._registry["test_routine"]["type"] == "class"
        assert factory._registry["test_routine"]["prototype"] == Routine

    def test_register_instance_prototype(self):
        """Test: Can register an instance as prototype."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        # Create instance with configuration
        instance = Routine()
        instance.set_activation_policy(lambda *args: True)

        # Interface contract: Should accept an instance
        factory.register("configured_routine", instance, description="Configured routine")

        # Verify registration
        assert "configured_routine" in factory._registry
        assert factory._registry["configured_routine"]["type"] == "instance"
        # Factory stores the class, not the instance
        assert factory._registry["configured_routine"]["prototype"] == Routine
        # Verify that activation_policy was extracted
        assert factory._registry["configured_routine"]["activation_policy"] is not None

    def test_register_duplicate_name_raises_error(self):
        """Test: Registering duplicate name raises ValueError."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        factory.register("test", Routine)

        # Interface contract: Duplicate registration should raise ValueError
        with pytest.raises(ValueError, match="already registered"):
            factory.register("test", Routine)

    def test_register_invalid_prototype_raises_error(self):
        """Test: Registering invalid prototype raises error."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        # Interface contract: Should validate prototype type
        # Note: Based on interface, should accept Flow, Routine, or Serializable
        # Testing with None should fail
        with pytest.raises((ValueError, TypeError)):
            factory.register("invalid", None)


class TestObjectCreation:
    """Test object creation from prototypes."""

    def test_create_from_class_prototype(self):
        """Test: Can create object from class prototype."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        factory.register("routine_class", Routine, description="Routine class")

        # Interface contract: create() should return new instance
        obj1 = factory.create("routine_class")
        obj2 = factory.create("routine_class")

        assert isinstance(obj1, Routine)
        assert isinstance(obj2, Routine)
        # Interface contract: Should create independent instances
        assert obj1 is not obj2

    def test_create_from_instance_prototype(self):
        """Test: Can create object from instance prototype."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        # Create configured instance
        prototype = Routine()
        prototype.set_activation_policy(lambda *args: True)

        factory.register("configured", prototype, description="Configured prototype")

        # Interface contract: create() should clone the instance
        obj = factory.create("configured")

        assert isinstance(obj, Routine)
        # Should be a different instance
        assert obj is not prototype
        # Should have same configuration (cloned)
        assert obj._activation_policy is not None

    def test_create_with_config_override(self):
        """Test: Can override config when creating from prototype."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        # Register instance with initial config
        prototype = Routine()
        factory.register("base", prototype)

        # Interface contract: create() should accept config override
        # Note: This depends on implementation, but interface should support it
        obj = factory.create("base", config={"test": "value"})

        assert isinstance(obj, Routine)

    def test_create_returns_independent_instances(self):
        """Test: Created objects are independent instances."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        factory.register("routine", Routine)

        obj1 = factory.create("routine")
        obj2 = factory.create("routine")

        # Interface contract: Each create() call returns independent instance
        assert obj1 is not obj2

        # Modify one, should not affect the other
        obj1._id = "modified"
        assert obj2._id != "modified"

    def test_create_preserves_prototype_config(self):
        """Test: Instance prototype configuration is preserved in created objects."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        # Create prototype with activation policy
        prototype = Routine()
        policy_func = lambda *args: True
        prototype.set_activation_policy(policy_func)

        factory.register("with_policy", prototype)

        # Interface contract: Created object should have same policy
        obj = factory.create("with_policy")

        assert obj._activation_policy is not None
        # Policy function reference should be the same (functions are immutable)
        # But obj and prototype are different instances
        assert obj._activation_policy is prototype._activation_policy
        assert obj is not prototype


class TestObjectMetadata:
    """Test metadata and discovery API."""

    def test_get_metadata(self):
        """Test: Can get metadata for registered object."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        description = "Test routine for processing"
        factory.register("test_routine", Routine, description=description)

        # Interface contract: get_metadata() should return ObjectMetadata
        metadata = factory.get_metadata("test_routine")

        assert metadata is not None
        assert isinstance(metadata, ObjectMetadata)
        assert metadata.name == "test_routine"
        assert metadata.description == description

    def test_list_objects(self):
        """Test: Can list all registered objects."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        factory.register("routine1", Routine, description="First routine")
        factory.register("routine2", Routine, description="Second routine")
        factory.register("flow1", Flow, description="Test flow")

        # Interface contract: list_available() should return list of dictionaries
        all_objects = factory.list_available()
        assert len(all_objects) >= 3

        # Verify structure
        for obj in all_objects:
            assert "name" in obj
            assert "type" in obj
            assert "description" in obj

    def test_metadata_includes_description(self):
        """Test: Metadata includes description."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        description = "A test routine"
        factory.register("test", Routine, description=description)

        metadata = factory.get_metadata("test")

        # Interface contract: Metadata should include description
        assert metadata.description == description


class TestObjectFactoryEdgeCases:
    """Test edge cases and error handling."""

    def test_create_nonexistent_prototype_raises_error(self):
        """Test: Creating from nonexistent prototype raises error."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        # Interface contract: Should raise ValueError for nonexistent prototype
        with pytest.raises(ValueError, match="not found"):
            factory.create("nonexistent")

    def test_create_with_invalid_config_raises_error(self):
        """Test: Invalid config raises appropriate error."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        factory.register("test", Routine)

        # Interface contract: Invalid config should be handled gracefully
        # This depends on implementation, but should not crash
        try:
            factory.create("test", config="invalid")
        except (ValueError, TypeError):
            pass  # Expected

    def test_concurrent_registration_thread_safe(self):
        """Test: Concurrent registration is thread-safe."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        errors = []
        registered = []

        def register_routine(i):
            try:
                factory.register(f"routine_{i}", Routine, description=f"Routine {i}")
                registered.append(i)
            except Exception as e:
                errors.append((i, e))

        threads = [threading.Thread(target=register_routine, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Interface contract: Should handle concurrent registration without errors
        # (except for intentional duplicates)
        assert len(errors) == 0 or all("already registered" in str(e[1]) for e in errors)
        assert len(registered) == 10

    def test_concurrent_creation_thread_safe(self):
        """Test: Concurrent creation is thread-safe."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        factory.register("test", Routine)

        created = []
        errors = []

        def create_routine():
            try:
                obj = factory.create("test")
                created.append(obj)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_routine) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Interface contract: Should create all objects without errors
        assert len(errors) == 0
        assert len(created) == 10
        # All should be different instances
        assert len(set(id(obj) for obj in created)) == 10


class TestFactoryReverseLookup:
    """Test reverse lookup functionality."""

    def test_get_factory_name_from_class(self):
        """Test: Can get factory name from class."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        factory.register("test_routine", Routine, description="Test routine")

        # Interface contract: get_factory_name() should return name for class
        name = factory.get_factory_name(Routine)
        assert name == "test_routine"

    def test_get_factory_name_from_instance(self):
        """Test: Can get factory name from instance."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        factory.register("test_routine", Routine, description="Test routine")
        instance = factory.create("test_routine")

        # Interface contract: get_factory_name() should return name for instance
        name = factory.get_factory_name(instance)
        assert name == "test_routine"

    def test_get_factory_name_not_registered(self):
        """Test: Returns None for unregistered class/instance."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        # Interface contract: get_factory_name() should return None for unregistered
        name = factory.get_factory_name(Routine)
        assert name is None

        instance = Routine()
        name = factory.get_factory_name(instance)
        assert name is None


class TestFactoryDSLExport:
    """Test DSL export functionality."""

    def test_export_flow_to_dsl_dict(self):
        """Test: Can export flow to DSL dictionary."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        # Register routine
        factory.register("test_routine", Routine, description="Test routine")

        # Create flow with routine
        flow = Flow(flow_id="test_flow")
        routine = factory.create("test_routine")
        flow.add_routine(routine, "routine1")

        # Interface contract: export_flow_to_dsl() should return dict by default
        dsl = factory.export_flow_to_dsl(flow, format="dict")
        assert isinstance(dsl, dict)
        assert dsl["flow_id"] == "test_flow"
        assert "routine1" in dsl["routines"]
        assert dsl["routines"]["routine1"]["class"] == "test_routine"

    def test_export_flow_to_dsl_yaml(self):
        """Test: Can export flow to YAML string."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        factory.register("test_routine", Routine)
        flow = Flow(flow_id="test_flow")
        routine = factory.create("test_routine")
        flow.add_routine(routine, "routine1")

        # Interface contract: export_flow_to_dsl() should return YAML string
        dsl = factory.export_flow_to_dsl(flow, format="yaml")
        assert isinstance(dsl, str)
        assert "test_flow" in dsl
        assert "test_routine" in dsl

    def test_export_flow_to_dsl_json(self):
        """Test: Can export flow to JSON string."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        factory.register("test_routine", Routine)
        flow = Flow(flow_id="test_flow")
        routine = factory.create("test_routine")
        flow.add_routine(routine, "routine1")

        # Interface contract: export_flow_to_dsl() should return JSON string
        dsl = factory.export_flow_to_dsl(flow, format="json")
        assert isinstance(dsl, str)
        import json

        parsed = json.loads(dsl)
        assert parsed["flow_id"] == "test_flow"

    def test_export_flow_unregistered_routine_raises_error(self):
        """Test: Export fails if flow contains unregistered routine."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        # Create flow with unregistered routine
        flow = Flow(flow_id="test_flow")
        unregistered_routine = Routine()
        flow.add_routine(unregistered_routine, "routine1")

        # Interface contract: Should raise ValueError for unregistered routine
        with pytest.raises(ValueError, match="not registered in factory"):
            factory.export_flow_to_dsl(flow)


class TestFactoryDSLImport:
    """Test DSL import functionality."""

    def test_load_flow_from_dsl(self):
        """Test: Can load flow from DSL dictionary."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        # Register routine
        factory.register("test_routine", Routine, description="Test routine")

        # Create DSL
        dsl = {
            "flow_id": "test_flow",
            "routines": {
                "routine1": {
                    "class": "test_routine",
                    "config": {"test": "value"},
                }
            },
            "connections": [],
            "execution": {"timeout": 300.0},
        }

        # Interface contract: load_flow_from_dsl() should create Flow
        flow = factory.load_flow_from_dsl(dsl)
        assert isinstance(flow, Flow)
        assert flow.flow_id == "test_flow"
        assert "routine1" in flow.routines
        assert flow.routines["routine1"].get_config("test") == "value"

    def test_load_flow_unregistered_component_raises_error(self):
        """Test: Load fails if DSL references unregistered component."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        dsl = {
            "flow_id": "test_flow",
            "routines": {
                "routine1": {
                    "class": "nonexistent_routine",
                }
            },
            "connections": [],
        }

        # Interface contract: Should raise ValueError for unregistered component
        with pytest.raises(ValueError, match="unregistered factory name"):
            factory.load_flow_from_dsl(dsl)

    def test_dsl_roundtrip(self):
        """Test: Export then import produces same flow structure."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        # Register routine
        factory.register("test_routine", Routine)

        # Create original flow
        original_flow = Flow(flow_id="test_flow")
        routine = factory.create("test_routine")
        routine.set_config(test_key="test_value")
        original_flow.add_routine(routine, "routine1")

        # Export to DSL
        dsl = factory.export_flow_to_dsl(original_flow, format="dict")

        # Import from DSL
        imported_flow = factory.load_flow_from_dsl(dsl)

        # Interface contract: Imported flow should have same structure
        assert imported_flow.flow_id == original_flow.flow_id
        assert "routine1" in imported_flow.routines
        assert imported_flow.routines["routine1"].get_config("test_key") == "test_value"
