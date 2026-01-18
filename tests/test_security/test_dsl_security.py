"""
Security tests for DSL factory integration.

Tests verify that:
1. No dynamic class loading occurs
2. Malicious DSL with class paths is rejected
3. Unregistered components are rejected
4. Factory-only loading is enforced
"""

import pytest

from routilux import Flow, Routine
from routilux.tools.factory.factory import ObjectFactory
from routilux.monitoring.storage import flow_store


class TestNoDynamicClassLoading:
    """Test that dynamic class loading is prevented."""

    def test_dsl_with_class_path_rejected(self):
        """Test: DSL with class path (not factory name) is rejected."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        # Try to load DSL with class path instead of factory name
        dsl = {
            "flow_id": "test_flow",
            "routines": {
                "routine1": {
                    "class": "routilux.routine.Routine",  # Class path, not factory name
                }
            },
            "connections": [],
        }

        # Should fail - class path not allowed
        with pytest.raises(ValueError, match="unregistered factory name"):
            factory.load_flow_from_dsl(dsl)

    def test_dsl_with_malicious_module_path_rejected(self):
        """Test: DSL with malicious module path is rejected."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        # Try malicious class path
        dsl = {
            "flow_id": "test_flow",
            "routines": {
                "routine1": {
                    "class": "os.system",  # Attempt to execute system commands
                }
            },
            "connections": [],
        }

        # Should fail - not a factory name
        with pytest.raises(ValueError, match="unregistered factory name"):
            factory.load_flow_from_dsl(dsl)

    def test_add_routine_class_path_rejected(self):
        """Test: Adding routine with class path is rejected."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        flow = Flow(flow_id="test_flow")
        flow_store.add(flow)

        # This would be done via API, but we test the underlying logic
        # Class path should not work
        dsl = {
            "flow_id": "test_flow",
            "routines": {
                "routine1": {
                    "class": "routilux.routine.Routine",
                }
            },
            "connections": [],
        }

        with pytest.raises(ValueError, match="unregistered factory name"):
            factory.load_flow_from_dsl(dsl)


class TestFactoryOnlyEnforcement:
    """Test that factory-only loading is strictly enforced."""

    def test_unregistered_component_rejected_with_clear_error(self):
        """Test: Unregistered components are rejected with helpful error."""
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

        with pytest.raises(ValueError) as exc_info:
            factory.load_flow_from_dsl(dsl)

        error_msg = str(exc_info.value)
        assert "unregistered factory name" in error_msg
        assert "nonexistent_routine" in error_msg
        assert "Available factory names" in error_msg

    def test_export_unregistered_routine_rejected(self):
        """Test: Export fails for flows with unregistered routines."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        # Create flow with unregistered routine
        flow = Flow(flow_id="test_flow")
        unregistered_routine = Routine()
        flow.add_routine(unregistered_routine, "routine1")

        with pytest.raises(ValueError) as exc_info:
            factory.export_flow_to_dsl(flow)

        error_msg = str(exc_info.value)
        assert "not registered in factory" in error_msg
        assert "routine1" in error_msg

    def test_only_factory_names_accepted(self):
        """Test: Only factory names are accepted, no other formats."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

        factory.register("valid_routine", Routine)

        # Test various invalid formats
        invalid_classes = [
            "module.ClassName",  # Class path
            "os.system",  # System function
            "builtins.exec",  # Builtin function
            "routilux.routine.Routine",  # Full class path
        ]

        for invalid_class in invalid_classes:
            dsl = {
                "flow_id": "test_flow",
                "routines": {
                    "routine1": {
                        "class": invalid_class,
                    }
                },
                "connections": [],
            }

            with pytest.raises(ValueError, match="unregistered factory name"):
                factory.load_flow_from_dsl(dsl)

        # Valid factory name should work
        valid_dsl = {
            "flow_id": "test_flow",
            "routines": {
                "routine1": {
                    "class": "valid_routine",
                }
            },
            "connections": [],
        }
        flow = factory.load_flow_from_dsl(valid_dsl)
        assert isinstance(flow, Flow)
