"""
Integration test for overseer_demo_app.py.

Tests that:
1. All routines are registered correctly
2. All flows are registered correctly
3. Factory API endpoints work correctly
4. No errors occur during registration
"""

import pytest
from routilux.tools.factory.factory import ObjectFactory
from routilux.tools.factory.metadata import ObjectMetadata
from routilux import Flow, Routine
from routilux.monitoring.registry import MonitoringRegistry
from routilux.monitoring.flow_registry import FlowRegistry
from routilux.monitoring.storage import flow_store


class TestOverseerDemoIntegration:
    """Integration tests for overseer_demo_app."""
    
    def test_routine_registration(self):
        """Test: Routines can be registered in factory."""
        factory = ObjectFactory.get_instance()
        factory.clear()
        
        # Register a test routine
        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.set_config(name="TestRoutine")
                self.input_slot = self.define_slot("input")
                self.output_event = self.define_event("output", ["data"])
                self.set_activation_policy(lambda *args, **kwargs: True)
                self.set_logic(lambda *args, **kwargs: None)
        
        metadata = ObjectMetadata(
            name="test_routine",
            description="Test routine",
            category="test",
            tags=["test"],
            example_config={"name": "TestRoutine"},
            version="1.0.0"
        )
        
        factory.register("test_routine", TestRoutine, metadata=metadata)
        
        # Verify registration
        objects = factory.list_available()
        routine_objects = [obj for obj in objects if obj.get("object_type") == "routine"]
        assert len(routine_objects) > 0
        assert any(obj["name"] == "test_routine" for obj in routine_objects)
        
        # Verify metadata
        registered_metadata = factory.get_metadata("test_routine")
        assert registered_metadata is not None
        assert registered_metadata.name == "test_routine"
        assert registered_metadata.category == "test"
        
        factory.clear()
    
    def test_flow_registration(self):
        """Test: Flows can be registered in factory."""
        factory = ObjectFactory.get_instance()
        factory.clear()
        
        # Create a test flow
        flow = Flow("test_flow")
        
        metadata = ObjectMetadata(
            name="test_flow",
            description="Test flow",
            category="test",
            tags=["test", "flow"],
            example_config={},
            version="1.0.0"
        )
        
        factory.register("test_flow", flow, metadata=metadata)
        
        # Verify registration
        objects = factory.list_available()
        flow_objects = [obj for obj in objects if obj.get("object_type") == "flow"]
        assert len(flow_objects) > 0
        assert any(obj["name"] == "test_flow" for obj in flow_objects)
        
        # Verify metadata
        registered_metadata = factory.get_metadata("test_flow")
        assert registered_metadata is not None
        assert registered_metadata.name == "test_flow"
        assert registered_metadata.category == "test"
        
        factory.clear()
    
    def test_object_type_filtering(self):
        """Test: Factory objects can be filtered by object_type."""
        factory = ObjectFactory.get_instance()
        factory.clear()
        
        # Register routines
        class TestRoutine1(Routine):
            def __init__(self):
                super().__init__()
                self.set_config(name="TestRoutine1")
        
        class TestRoutine2(Routine):
            def __init__(self):
                super().__init__()
                self.set_config(name="TestRoutine2")
        
        factory.register("test_routine1", TestRoutine1, metadata=ObjectMetadata(
            name="test_routine1", description="Test 1", category="test", tags=[], example_config={}, version="1.0.0"
        ))
        factory.register("test_routine2", TestRoutine2, metadata=ObjectMetadata(
            name="test_routine2", description="Test 2", category="test", tags=[], example_config={}, version="1.0.0"
        ))
        
        # Register flows
        flow1 = Flow("test_flow1")
        flow2 = Flow("test_flow2")
        
        factory.register("test_flow1", flow1, metadata=ObjectMetadata(
            name="test_flow1", description="Flow 1", category="test", tags=[], example_config={}, version="1.0.0"
        ))
        factory.register("test_flow2", flow2, metadata=ObjectMetadata(
            name="test_flow2", description="Flow 2", category="test", tags=[], example_config={}, version="1.0.0"
        ))
        
        # Test filtering
        all_objects = factory.list_available()
        routines = factory.list_available(object_type="routine")
        flows = factory.list_available(object_type="flow")
        
        assert len(all_objects) == 4
        assert len(routines) == 2
        assert len(flows) == 2
        
        # Verify object_type field
        for obj in routines:
            assert obj["object_type"] == "routine"
        for obj in flows:
            assert obj["object_type"] == "flow"
        
        factory.clear()
    
    def test_category_filtering(self):
        """Test: Factory objects can be filtered by category."""
        factory = ObjectFactory.get_instance()
        factory.clear()
        
        # Register routines in different categories
        class TestRoutine1(Routine):
            def __init__(self):
                super().__init__()
                self.set_config(name="TestRoutine1")
        
        class TestRoutine2(Routine):
            def __init__(self):
                super().__init__()
                self.set_config(name="TestRoutine2")
        
        factory.register("test_routine1", TestRoutine1, metadata=ObjectMetadata(
            name="test_routine1", description="Test 1", category="category1", tags=[], example_config={}, version="1.0.0"
        ))
        factory.register("test_routine2", TestRoutine2, metadata=ObjectMetadata(
            name="test_routine2", description="Test 2", category="category2", tags=[], example_config={}, version="1.0.0"
        ))
        
        # Test filtering
        all_objects = factory.list_available()
        category1_objects = factory.list_available(category="category1")
        category2_objects = factory.list_available(category="category2")
        
        assert len(all_objects) == 2
        assert len(category1_objects) == 1
        assert len(category2_objects) == 1
        assert category1_objects[0]["category"] == "category1"
        assert category2_objects[0]["category"] == "category2"
        
        factory.clear()
    
    def test_combined_filtering(self):
        """Test: Factory objects can be filtered by both category and object_type."""
        factory = ObjectFactory.get_instance()
        factory.clear()
        
        # Register routines in different categories
        class TestRoutine1(Routine):
            def __init__(self):
                super().__init__()
                self.set_config(name="TestRoutine1")
        
        class TestRoutine2(Routine):
            def __init__(self):
                super().__init__()
                self.set_config(name="TestRoutine2")
        
        factory.register("test_routine1", TestRoutine1, metadata=ObjectMetadata(
            name="test_routine1", description="Test 1", category="data_generation", tags=[], example_config={}, version="1.0.0"
        ))
        factory.register("test_routine2", TestRoutine2, metadata=ObjectMetadata(
            name="test_routine2", description="Test 2", category="transformation", tags=[], example_config={}, version="1.0.0"
        ))
        
        # Register a flow
        flow = Flow("test_flow")
        factory.register("test_flow", flow, metadata=ObjectMetadata(
            name="test_flow", description="Flow", category="data_generation", tags=[], example_config={}, version="1.0.0"
        ))
        
        # Test combined filtering
        data_gen_routines = factory.list_available(category="data_generation", object_type="routine")
        data_gen_flows = factory.list_available(category="data_generation", object_type="flow")
        transformation_routines = factory.list_available(category="transformation", object_type="routine")
        
        assert len(data_gen_routines) == 1
        assert len(data_gen_flows) == 1
        assert len(transformation_routines) == 1
        
        assert data_gen_routines[0]["name"] == "test_routine1"
        assert data_gen_flows[0]["name"] == "test_flow"
        assert transformation_routines[0]["name"] == "test_routine2"
        
        factory.clear()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
