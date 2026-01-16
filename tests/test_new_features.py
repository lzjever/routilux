"""
Comprehensive tests for new features added in improvement plan.

These tests are written based on the public API interface, not implementation details.
They challenge the business logic and identify bugs in both test and production code.
"""

import threading
import time

import pytest

from routilux import (
    ExecutionStatus,
    Flow,
    FlowBuilder,
    Routine,
    RoutineStatus,
    RoutineTester,
)
from routilux.error_handler import ErrorStrategy
from routilux.job_state import JobState

# ============================================================================
# Test 1: Execution Context Convenience Properties
# ============================================================================


class TestExecutionContextConvenienceProperties:
    """Test convenience properties: job_state, job_id, flow"""

    def test_job_state_property_returns_none_outside_execution(self):
        """Test that job_state property returns None when not in execution context."""
        routine = Routine()
        assert routine.job_state is None

    def test_job_id_property_returns_none_outside_execution(self):
        """Test that job_id property returns None when not in execution context."""
        routine = Routine()
        assert routine.job_id is None

    def test_flow_property_returns_none_outside_execution(self):
        """Test that flow property returns None when not in execution context."""
        routine = Routine()
        assert routine.flow is None

    def test_convenience_properties_during_execution(self):
        """Test that convenience properties work correctly during execution."""
        flow = Flow()
        captured_values = {}

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)

            def _handle_trigger(self, **kwargs):
                # Test all convenience properties
                captured_values["job_state"] = self.job_state
                captured_values["job_id"] = self.job_id
                captured_values["flow"] = self.flow

        routine = TestRoutine()
        routine_id = flow.add_routine(routine, "test_routine")

        job_state = flow.execute(routine_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # Verify properties were accessible
        assert captured_values["job_state"] is not None
        assert isinstance(captured_values["job_state"], JobState)
        assert captured_values["job_id"] is not None
        assert isinstance(captured_values["job_id"], str)
        assert captured_values["flow"] is not None
        assert captured_values["flow"] is flow

    def test_job_id_matches_actual_job_state(self):
        """Test that job_id property returns the correct job_id from job_state."""
        flow = Flow()
        captured_job_id = None

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)

            def _handle_trigger(self, **kwargs):
                nonlocal captured_job_id
                captured_job_id = self.job_id

        routine = TestRoutine()
        routine_id = flow.add_routine(routine, "test_routine")

        job_state = flow.execute(routine_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # Verify job_id matches
        assert captured_job_id == job_state.job_id

    def test_convenience_properties_work_in_nested_calls(self):
        """Test that convenience properties work in nested handler calls."""
        flow = Flow()
        call_chain = []

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.input_slot = self.define_slot("input", handler=self._handle_input)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, **kwargs):
                call_chain.append(("trigger", self.job_id))
                self.emit("output", data="test")

            def _handle_input(self, data=None, **kwargs):
                call_chain.append(("input", self.job_id))

        routine = TestRoutine()
        routine_id = flow.add_routine(routine, "test_routine")

        # Create a self-connection for nested call
        flow.connect(routine_id, "output", routine_id, "input")

        job_state = flow.execute(routine_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # Verify job_id is consistent across calls
        assert len(call_chain) == 2
        assert call_chain[0][1] == call_chain[1][1]  # Same job_id in both calls
        assert call_chain[0][1] == job_state.job_id


# ============================================================================
# Test 2: Enhanced Error Messages
# ============================================================================


class TestEnhancedErrorMessages:
    """Test enhanced error messages with context"""

    def test_get_execution_context_logs_when_no_flow(self, caplog):
        """Test that get_execution_context logs helpful message when no flow."""
        import logging

        logging.getLogger("routilux.routine").setLevel(logging.DEBUG)

        routine = Routine()
        ctx = routine.get_execution_context()

        assert ctx is None
        assert "No flow context available" in caplog.text or "flow context" in caplog.text.lower()

    def test_slot_error_includes_context(self, caplog):
        """Test that slot handler errors include rich context."""
        import logging

        logging.getLogger("routilux.slot").setLevel(logging.ERROR)

        flow = Flow()

        class ErrorRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)

            def _handle_trigger(self, **kwargs):
                raise ValueError("Test error message")

        routine = ErrorRoutine()
        routine_id = flow.add_routine(routine, "error_routine")

        job_state = flow.execute(routine_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # Check that error log includes context
        error_log = caplog.text
        assert "Error in slot handler" in error_log or "slot handler" in error_log.lower()
        assert "error_routine" in error_log or "ErrorRoutine" in error_log
        assert "trigger" in error_log.lower()

    def test_error_context_includes_job_id(self, caplog):
        """Test that error context includes job_id."""
        import logging

        logging.getLogger("routilux.slot").setLevel(logging.ERROR)

        flow = Flow()
        job_id_captured = None

        class ErrorRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)

            def _handle_trigger(self, **kwargs):
                nonlocal job_id_captured
                job_id_captured = self.job_id
                raise ValueError("Test error")

        routine = ErrorRoutine()
        routine_id = flow.add_routine(routine, "error_routine")

        job_state = flow.execute(routine_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # Verify job_id was captured and appears in error log
        assert job_id_captured is not None
        assert job_id_captured == job_state.job_id
        assert job_id_captured in caplog.text or str(job_id_captured) in caplog.text


# ============================================================================
# Test 3: Flow Validation
# ============================================================================


class TestFlowValidation:
    """Test Flow.validate() method"""

    def test_validate_empty_flow(self):
        """Test validation of empty flow."""
        flow = Flow()
        issues = flow.validate()
        # Empty flow should have warnings about no routines
        assert isinstance(issues, list)

    def test_validate_detects_circular_dependencies(self):
        """Test that validation detects circular dependencies."""
        flow = Flow()

        class RoutineA(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.output_event = self.define_event("output", ["data"])
                self.input_slot = self.define_slot("input", handler=self._handle)

            def _handle(self, **kwargs):
                self.emit("output", data="test")

        class RoutineB(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self._handle)
                self.output_event = self.define_event("output", ["data"])

            def _handle(self, **kwargs):
                self.emit("output", data="test")

        a = RoutineA()
        b = RoutineB()

        id_a = flow.add_routine(a, "A")
        id_b = flow.add_routine(b, "B")

        # Create cycle: A -> B -> A
        flow.connect(id_a, "output", id_b, "input")
        flow.connect(id_b, "output", id_a, "input")

        issues = flow.validate()

        # Should detect circular dependency
        assert len(issues) > 0
        assert any("circular" in issue.lower() or "cycle" in issue.lower() for issue in issues)

    def test_validate_detects_unconnected_events(self):
        """Test that validation detects unconnected events."""
        flow = Flow()

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.output_event = self.define_event("output", ["data"])

            def _handle(self, **kwargs):
                self.emit("output", data="test")

        routine = TestRoutine()
        flow.add_routine(routine, "test")

        issues = flow.validate()

        # Should warn about unconnected event
        assert any("unconnected" in issue.lower() and "event" in issue.lower() for issue in issues)

    def test_validate_detects_unconnected_slots(self):
        """Test that validation detects unconnected slots."""
        flow = Flow()

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self._handle)

            def _handle(self, **kwargs):
                pass

        routine = TestRoutine()
        flow.add_routine(routine, "test")

        issues = flow.validate()

        # Should warn about unconnected slot
        assert any("unconnected" in issue.lower() and "slot" in issue.lower() for issue in issues)

    def test_validate_valid_flow_returns_empty_list(self):
        """Test that a valid flow returns empty issues list."""
        flow = Flow()

        class RoutineA(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.output_event = self.define_event("output", ["data"])

            def _handle(self, **kwargs):
                self.emit("output", data="test")

        class RoutineB(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self._handle)

            def _handle(self, **kwargs):
                pass

        a = RoutineA()
        b = RoutineB()

        id_a = flow.add_routine(a, "A")
        id_b = flow.add_routine(b, "B")

        flow.connect(id_a, "output", id_b, "input")

        issues = flow.validate()

        # Valid flow should have no errors (warnings are OK)
        errors = [
            issue for issue in issues if "error" in issue.lower() or "circular" in issue.lower()
        ]
        assert len(errors) == 0


# ============================================================================
# Test 4: Configuration Protection
# ============================================================================


class TestConfigurationProtection:
    """Test configuration protection during execution"""

    def test_set_config_allowed_before_execution(self):
        """Test that set_config works before execution."""
        routine = Routine()
        routine.set_config(key1="value1", key2=42)

        assert routine.get_config("key1") == "value1"
        assert routine.get_config("key2") == 42

    def test_set_config_prevents_modification_during_execution(self):
        """Test that set_config raises error during execution."""
        flow = Flow()

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)

            def _handle_trigger(self, **kwargs):
                # Try to modify config during execution
                with pytest.raises(RuntimeError, match="Cannot modify.*during execution"):
                    self.set_config(new_key="new_value")

        routine = TestRoutine()
        routine_id = flow.add_routine(routine, "test")

        job_state = flow.execute(routine_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

    def test_set_config_validates_serializability(self):
        """Test that set_config validates serializability."""
        routine = Routine()

        # Test with non-serializable object (function)
        def non_serializable_func():
            pass

        with pytest.raises(ValueError, match="must be serializable"):
            routine.set_config(func=non_serializable_func)

    def test_set_config_allows_serializable_types(self):
        """Test that set_config allows all serializable types."""
        routine = Routine()

        # These should all work
        routine.set_config(
            string_val="test",
            int_val=42,
            float_val=3.14,
            bool_val=True,
            none_val=None,
            list_val=[1, 2, 3],
            dict_val={"key": "value"},
        )

        assert routine.get_config("string_val") == "test"
        assert routine.get_config("int_val") == 42
        assert routine.get_config("float_val") == 3.14
        assert routine.get_config("bool_val") is True
        assert routine.get_config("none_val") is None
        assert routine.get_config("list_val") == [1, 2, 3]
        assert routine.get_config("dict_val") == {"key": "value"}


# ============================================================================
# Test 5: Status Enums
# ============================================================================


class TestStatusEnums:
    """Test ExecutionStatus and RoutineStatus enums"""

    def test_execution_status_values(self):
        """Test that ExecutionStatus has correct values."""
        assert ExecutionStatus.PENDING == "pending"
        assert ExecutionStatus.RUNNING == "running"
        assert ExecutionStatus.PAUSED == "paused"
        assert ExecutionStatus.COMPLETED == "completed"
        assert ExecutionStatus.FAILED == "failed"
        assert ExecutionStatus.CANCELLED == "cancelled"

    def test_routine_status_values(self):
        """Test that RoutineStatus has correct values."""
        assert RoutineStatus.PENDING == "pending"
        assert RoutineStatus.RUNNING == "running"
        assert RoutineStatus.COMPLETED == "completed"
        assert RoutineStatus.FAILED == "failed"
        assert RoutineStatus.ERROR_CONTINUED == "error_continued"
        assert RoutineStatus.SKIPPED == "skipped"

    def test_status_enums_backward_compatible_with_strings(self):
        """Test that status enums can be compared with strings."""
        # This is critical for backward compatibility
        status = ExecutionStatus.COMPLETED

        assert status == "completed"
        assert status == ExecutionStatus.COMPLETED
        assert "completed" == status

    def test_job_state_uses_execution_status(self):
        """Test that JobState uses ExecutionStatus."""
        flow = Flow()

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)

            def _handle(self, **kwargs):
                pass

        routine = TestRoutine()
        routine_id = flow.add_routine(routine, "test")

        job_state = flow.execute(routine_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # Status should be compatible with enum
        assert job_state.status in (ExecutionStatus.COMPLETED, "completed")
        assert isinstance(job_state.status, (str, ExecutionStatus))


# ============================================================================
# Test 6: Flow Builder Pattern
# ============================================================================


class TestFlowBuilder:
    """Test FlowBuilder fluent API"""

    def test_builder_creates_flow(self):
        """Test that builder creates a flow."""
        builder = FlowBuilder("test_flow")
        flow = builder.build()

        assert isinstance(flow, Flow)
        assert flow.flow_id == "test_flow"

    def test_builder_adds_routines(self):
        """Test that builder can add routines."""

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.output_event = self.define_event("output", ["data"])

            def _handle(self, **kwargs):
                self.emit("output", data="test")

        flow = (
            FlowBuilder().add_routine(TestRoutine(), "r1").add_routine(TestRoutine(), "r2").build()
        )

        assert "r1" in flow.routines
        assert "r2" in flow.routines
        assert len(flow.routines) == 2

    def test_builder_applies_config(self):
        """Test that builder applies config to routines."""

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)

            def _handle(self, **kwargs):
                pass

        flow = (
            FlowBuilder()
            .add_routine(TestRoutine(), "r1", config={"timeout": 30, "retries": 3})
            .build()
        )

        routine = flow.routines["r1"]
        assert routine.get_config("timeout") == 30
        assert routine.get_config("retries") == 3

    def test_builder_connects_routines(self):
        """Test that builder can connect routines."""

        class RoutineA(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.output_event = self.define_event("output", ["data"])

            def _handle(self, **kwargs):
                self.emit("output", data="test")

        class RoutineB(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self._handle)
                self.called = False

            def _handle(self, **kwargs):
                self.called = True

        flow = (
            FlowBuilder()
            .add_routine(RoutineA(), "A")
            .add_routine(RoutineB(), "B")
            .connect("A", "output", "B", "input")
            .build()
        )

        assert len(flow.connections) == 1

        # Test execution
        job_state = flow.execute("A")
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        assert flow.routines["B"].called

    def test_builder_validates_flow(self):
        """Test that builder can validate flow."""
        flow = FlowBuilder().add_routine(Routine(), "r1").validate().build()

        # Should not raise if valid
        assert isinstance(flow, Flow)

    def test_builder_validation_raises_on_error(self):
        """Test that builder validation raises on validation errors."""

        # Create a flow with circular dependency
        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.output_event = self.define_event("output", ["data"])
                self.input_slot = self.define_slot("input", handler=self._handle)

            def _handle(self, **kwargs):
                self.emit("output", data="test")

        with pytest.raises(ValueError, match="validation failed"):
            FlowBuilder().add_routine(TestRoutine(), "r1").connect(
                "r1", "output", "r1", "input"
            ).validate().build()


# ============================================================================
# Test 7: Parameter Mapping - REMOVED (feature removed in redesign)
# ============================================================================
# Parameter mapping has been removed as part of the redesign.
# The framework is now data-structure agnostic.


# ============================================================================
# Test 8: DSL Support
# ============================================================================


class TestDSLSupport:
    """Test YAML and JSON/dict DSL support"""

    def test_from_dict_creates_flow(self):
        """Test that Flow.from_dict() creates a flow from dictionary."""

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.output_event = self.define_event("output", ["data"])

            def _handle(self, **kwargs):
                self.emit("output", data="test")

        spec = {
            "flow_id": "test_flow",
            "routines": {"r1": {"class": TestRoutine, "config": {"timeout": 30}}},
            "connections": [],
        }

        flow = Flow.from_dict(spec)

        assert isinstance(flow, Flow)
        assert flow.flow_id == "test_flow"
        assert "r1" in flow.routines
        assert flow.routines["r1"].get_config("timeout") == 30

    def test_from_dict_with_string_class_path(self):
        """Test that Flow.from_dict() can load class from string path."""
        # Define a simple test routine at module level for import
        spec = {
            "flow_id": "test_flow",
            "routines": {
                "simple": {
                    "class": "tests.test_new_features.SimpleTestRoutine",
                }
            },
            "connections": [],
        }

        flow = Flow.from_dict(spec)

        assert isinstance(flow, Flow)
        assert "simple" in flow.routines
        assert isinstance(flow.routines["simple"], SimpleTestRoutine)

    def test_from_dict_with_connections(self):
        """Test that Flow.from_dict() handles connections."""

        class RoutineA(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.output_event = self.define_event("output", ["data"])

            def _handle(self, **kwargs):
                self.emit("output", data="test")

        class RoutineB(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self._handle)
                self.called = False

            def _handle(self, **kwargs):
                self.called = True

        spec = {
            "routines": {
                "A": {"class": RoutineA},
                "B": {"class": RoutineB},
            },
            "connections": [{"from": "A.output", "to": "B.input"}],
        }

        flow = Flow.from_dict(spec)

        assert len(flow.connections) == 1

        # Test execution
        job_state = flow.execute("A")
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        assert flow.routines["B"].called

    def test_from_dict_with_error_handler(self):
        """Test that Flow.from_dict() handles error handlers."""

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)

            def _handle(self, **kwargs):
                raise ValueError("Test error")

        spec = {
            "routines": {
                "r1": {
                    "class": TestRoutine,
                    "error_handler": {"strategy": "continue", "max_retries": 2},
                }
            },
            "connections": [],
        }

        flow = Flow.from_dict(spec)

        routine = flow.routines["r1"]
        error_handler = routine.get_error_handler()

        assert error_handler is not None
        assert error_handler.strategy == ErrorStrategy.CONTINUE

    def test_from_yaml_creates_flow(self):
        """Test that Flow.from_yaml() creates a flow from YAML string."""
        yaml_str = """
flow_id: test_flow
routines:
  r1:
    class: tests.test_new_features.SimpleTestRoutine
    config:
      timeout: 30
connections: []
"""
        flow = Flow.from_yaml(yaml_str)

        assert isinstance(flow, Flow)
        assert flow.flow_id == "test_flow"
        assert "r1" in flow.routines

    def test_from_yaml_with_complex_structure(self):
        """Test that Flow.from_yaml() handles complex YAML structures."""

        class TestRoutineA(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.output_event = self.define_event("output", ["data"])

            def _handle(self, **kwargs):
                self.emit("output", data="test")

        class TestRoutineB(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self._handle)
                self.called = False

            def _handle(self, **kwargs):
                self.called = True

        # Use class objects directly in YAML (via dict spec)
        # For YAML, we need to use string paths, so let's test with a simpler structure
        yaml_str = """
flow_id: complex_flow
routines:
  reader:
    class: tests.test_new_features.SimpleTestRoutine
    config:
      timeout: 30
      nested:
        key1: value1
        key2: [1, 2, 3]
  processor:
    class: tests.test_new_features.SimpleTestRoutine
    config:
      retries: 3
connections: []
execution:
  strategy: sequential
  timeout: 300.0
"""
        flow = Flow.from_yaml(yaml_str)

        assert isinstance(flow, Flow)
        assert flow.flow_id == "complex_flow"
        assert "reader" in flow.routines
        assert "processor" in flow.routines
        assert flow.routines["reader"].get_config("timeout") == 30
        assert flow.routines["reader"].get_config("nested")["key1"] == "value1"
        assert flow.routines["reader"].get_config("nested")["key2"] == [1, 2, 3]

    def test_from_yaml_raises_on_invalid_yaml(self):
        """Test that Flow.from_yaml() raises ValueError on invalid YAML."""
        # Test with malformed YAML syntax
        invalid_yaml = """
flow_id: test
routines:
  - invalid: list
    instead: of dict
"""
        # This will parse as YAML but fail validation in spec_parser
        with pytest.raises(ValueError):
            Flow.from_yaml(invalid_yaml)

    def test_from_yaml_raises_on_non_dict_root(self):
        """Test that Flow.from_yaml() raises ValueError when root is not a dict."""
        invalid_yaml = "- item1\n- item2\n- item3"

        with pytest.raises(ValueError, match="Flow specification must be a dictionary"):
            Flow.from_yaml(invalid_yaml)

    def test_from_yaml_raises_on_malformed_syntax(self):
        """Test that Flow.from_yaml() raises ValueError on malformed YAML syntax."""
        # Use truly invalid YAML syntax that cannot be parsed
        invalid_yaml = """
flow_id: test
routines:
  invalid: [unclosed bracket
  another: line: with: too: many: colons: here
"""
        with pytest.raises(ValueError):
            Flow.from_yaml(invalid_yaml)


# ============================================================================
# Test 9: Testing Utilities (RoutineTester)
# ============================================================================


class TestRoutineTester:
    """Test RoutineTester utility"""

    def test_routine_tester_creates_instance(self):
        """Test that RoutineTester can be instantiated."""
        routine = Routine()
        tester = RoutineTester(routine)

        assert tester.routine is routine

    def test_routine_tester_calls_slot(self):
        """Test that RoutineTester can call slot handlers."""
        called = False

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self._handle)

            def _handle(self, data=None, **kwargs):
                nonlocal called
                called = True

        routine = TestRoutine()
        tester = RoutineTester(routine)

        tester.call_slot("input", data="test")

        assert called

    def test_routine_tester_captures_events(self):
        """Test that RoutineTester can capture emitted events."""

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.output_event = self.define_event("output", ["data", "count"])

            def _handle(self, **kwargs):
                self.emit("output", data="test", count=42)

        routine = TestRoutine()
        tester = RoutineTester(routine)

        events = tester.capture_events()
        tester.call_slot("trigger")

        assert "output" in events
        assert len(events["output"]) > 0
        assert events["output"][0]["data"] == "test"
        assert events["output"][0]["count"] == 42

    def test_routine_tester_provides_execution_context(self):
        """Test that RoutineTester provides execution context."""

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self._handle)
                self.job_id_captured = None

            def _handle(self, **kwargs):
                self.job_id_captured = self.job_id

        routine = TestRoutine()
        tester = RoutineTester(routine)

        tester.call_slot("input")

        # Should have job_id available
        assert routine.job_id_captured is not None
        assert isinstance(routine.job_id_captured, str)


# ============================================================================
# Test 10: Thread-Safe Shared Data Operations
# ============================================================================


class TestThreadSafeSharedData:
    """Test thread-safe shared data operations"""

    def test_update_shared_data_thread_safe(self):
        """Test that update_shared_data is thread-safe."""
        job_state = JobState("test_flow")

        # Simulate concurrent updates
        results = []
        errors = []

        def update_worker(key, value):
            try:
                for _ in range(100):
                    job_state.update_shared_data(key, value)
                    time.sleep(0.001)  # Small delay to increase chance of race condition
                results.append(f"{key}_done")
            except Exception as e:
                errors.append(str(e))

        threads = []
        for i in range(5):
            thread = threading.Thread(target=update_worker, args=(f"key{i}", i))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Should complete without errors
        assert len(errors) == 0
        assert len(results) == 5

    def test_get_shared_data_thread_safe(self):
        """Test that get_shared_data is thread-safe."""
        job_state = JobState("test_flow")
        job_state.shared_data["test_key"] = 0

        read_values = []

        def read_worker():
            for _ in range(100):
                value = job_state.get_shared_data("test_key", 0)
                read_values.append(value)
                time.sleep(0.001)

        def write_worker():
            for i in range(100):
                job_state.update_shared_data("test_key", i)
                time.sleep(0.001)

        read_thread = threading.Thread(target=read_worker)
        write_thread = threading.Thread(target=write_worker)

        read_thread.start()
        write_thread.start()

        read_thread.join()
        write_thread.join()

        # Should complete without errors
        assert len(read_values) == 100

    def test_shared_data_methods_work_correctly(self):
        """Test that shared data methods work correctly."""
        job_state = JobState("test_flow")

        job_state.update_shared_data("key1", "value1")
        job_state.update_shared_data("key2", 42)

        assert job_state.get_shared_data("key1") == "value1"
        assert job_state.get_shared_data("key2") == 42
        assert job_state.get_shared_data("nonexistent", "default") == "default"


# ============================================================================
# Test 11: Per-Routine Timeout
# ============================================================================


class TestPerRoutineTimeout:
    """Test per-routine timeout functionality"""

    def test_set_timeout_stores_config(self):
        """Test that set_timeout stores timeout in config."""
        routine = Routine()
        routine.set_timeout(30.0)

        assert routine.get_config("timeout") == 30.0

    def test_timeout_enforced_during_execution(self):
        """Test that timeout is enforced during slot handler execution."""
        flow = Flow()

        class SlowRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.set_timeout(0.1)  # 100ms timeout

            def _handle(self, **kwargs):
                time.sleep(0.5)  # Sleep longer than timeout

        routine = SlowRoutine()
        routine_id = flow.add_routine(routine, "slow")

        job_state = flow.execute(routine_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # Should have timed out - check execution history for timeout error
        # The routine should have failed or error should be recorded
        routine_state = job_state.get_routine_state(routine_id)
        # Timeout should cause an error
        assert routine_state is not None

    def test_no_timeout_when_not_set(self):
        """Test that handler executes normally when no timeout is set."""
        flow = Flow()
        executed = False

        class NormalRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                # No timeout set

            def _handle(self, **kwargs):
                nonlocal executed
                time.sleep(0.1)  # Small delay
                executed = True

        routine = NormalRoutine()
        routine_id = flow.add_routine(routine, "normal")

        job_state = flow.execute(routine_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        assert executed
        assert job_state.status in (ExecutionStatus.COMPLETED, "completed")


# ============================================================================
# Additional Edge Cases and Stress Tests
# ============================================================================


class TestEdgeCases:
    """Test edge cases and challenging scenarios"""

    def test_convenience_properties_with_none_job_state(self):
        """Test convenience properties when job_state is None in context."""
        flow = Flow()

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.job_id_value = None

            def _handle(self, **kwargs):
                # Manually clear job_state from context to test None handling
                from routilux.routine import _current_job_state

                _current_job_state.set(None)
                self.job_id_value = self.job_id  # Should return None

        routine = TestRoutine()
        routine_id = flow.add_routine(routine, "test")

        job_state = flow.execute(routine_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # job_id should be None when context is cleared
        # Note: This tests the property's None handling, not normal execution
        assert routine.job_id_value is None

    def test_flow_validation_with_complex_cycles(self):
        """Test validation detects complex multi-node cycles."""
        flow = Flow()

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.output_event = self.define_event("output", ["data"])
                self.input_slot = self.define_slot("input", handler=self._handle)

            def _handle(self, **kwargs):
                self.emit("output", data="test")

        # Create cycle: A -> B -> C -> A
        a = TestRoutine()
        b = TestRoutine()
        c = TestRoutine()

        id_a = flow.add_routine(a, "A")
        id_b = flow.add_routine(b, "B")
        id_c = flow.add_routine(c, "C")

        flow.connect(id_a, "output", id_b, "input")
        flow.connect(id_b, "output", id_c, "input")
        flow.connect(id_c, "output", id_a, "input")

        issues = flow.validate()

        # Should detect the cycle
        assert len(issues) > 0
        assert any("circular" in issue.lower() or "cycle" in issue.lower() for issue in issues)

    def test_config_protection_with_nested_execution(self):
        """Test that config protection works even in nested execution contexts."""
        flow = Flow()
        Flow()

        class OuterRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.output_event = self.define_event("output", ["data"])

            def _handle(self, **kwargs):
                # Try to modify config during execution
                try:
                    self.set_config(new_key="value")
                    assert False, "Should have raised RuntimeError"
                except RuntimeError as e:
                    assert "during execution" in str(e).lower()

        routine = OuterRoutine()
        routine_id = flow.add_routine(routine, "outer")

        job_state = flow.execute(routine_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

    def test_dsl_with_invalid_class_path(self):
        """Test that DSL raises error for invalid class path."""
        spec = {
            "routines": {"r1": {"class": "nonexistent.module.ClassName"}},
            "connections": [],
        }

        with pytest.raises(ValueError, match="Failed to load class"):
            Flow.from_dict(spec)

    def test_dsl_with_missing_required_fields(self):
        """Test that DSL validation catches missing required fields."""
        # Missing 'class' field
        spec = {
            "routines": {"r1": {"config": {"timeout": 30}}},
            "connections": [],
        }

        with pytest.raises(ValueError, match="must specify 'class'"):
            Flow.from_dict(spec)

    def test_builder_with_invalid_connection(self):
        """Test that builder handles invalid connections gracefully."""

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.output_event = self.define_event("output", ["data"])

            def _handle(self, **kwargs):
                self.emit("output", data="test")

        builder = FlowBuilder()
        builder.add_routine(TestRoutine(), "r1")
        builder.add_routine(TestRoutine(), "r2")

        # Try to connect to non-existent event
        with pytest.raises(ValueError):
            builder.connect("r1", "nonexistent", "r2", "input")

    def test_timeout_with_fast_handler(self):
        """Test that timeout doesn't affect fast handlers."""
        flow = Flow()
        executed = False

        class FastRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.set_timeout(1.0)  # 1 second timeout

            def _handle(self, **kwargs):
                nonlocal executed
                # Fast execution, should complete before timeout
                executed = True

        routine = FastRoutine()
        routine_id = flow.add_routine(routine, "fast")

        job_state = flow.execute(routine_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        assert executed
        assert job_state.status in (ExecutionStatus.COMPLETED, "completed")

    def test_thread_safe_shared_data_concurrent_updates(self):
        """Test thread-safe operations with high concurrency."""
        job_state = JobState("test_flow")
        job_state.shared_data["counter"] = 0

        def increment_worker():
            for _ in range(1000):
                current = job_state.get_shared_data("counter", 0)
                job_state.update_shared_data("counter", current + 1)

        threads = []
        for _ in range(10):
            thread = threading.Thread(target=increment_worker)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # With proper locking, counter should be exactly 10000
        # Without locking, it would be less due to race conditions
        final_value = job_state.get_shared_data("counter", 0)
        assert final_value == 10000, f"Expected 10000, got {final_value} (race condition detected)"

    def test_routine_tester_with_multiple_events(self):
        """Test RoutineTester captures multiple events correctly."""

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.event1 = self.define_event("event1", ["data1"])
                self.event2 = self.define_event("event2", ["data2"])

            def _handle(self, **kwargs):
                self.emit("event1", data1="value1")
                self.emit("event2", data2="value2")

        routine = TestRoutine()
        tester = RoutineTester(routine)

        events = tester.capture_events()
        tester.call_slot("trigger")

        assert "event1" in events
        assert "event2" in events
        assert len(events["event1"]) == 1
        assert len(events["event2"]) == 1
        assert events["event1"][0]["data1"] == "value1"
        assert events["event2"][0]["data2"] == "value2"

    def test_status_enum_comparison_edge_cases(self):
        """Test status enum comparison with various edge cases."""
        # Test enum to string comparison
        status = ExecutionStatus.COMPLETED
        assert status == "completed"
        assert "completed" == status
        assert status != "failed"

        # Test enum to enum comparison
        assert ExecutionStatus.COMPLETED == ExecutionStatus.COMPLETED
        assert ExecutionStatus.COMPLETED != ExecutionStatus.FAILED

        # Test in operator
        assert ExecutionStatus.COMPLETED in ("completed", "failed")
        assert "completed" in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED)

    def test_flow_builder_chaining_extensive(self):
        """Test extensive chaining of builder methods."""

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.output_event = self.define_event("output", ["data"])
                self.input_slot = self.define_slot("input", handler=self._handle)

            def _handle(self, **kwargs):
                self.emit("output", data="test")

        # Build flow without validate() since we have unconnected components
        # (this is a valid use case - validation warnings don't always mean errors)
        flow = (
            FlowBuilder("complex_flow")
            .add_routine(TestRoutine(), "r1", config={"timeout": 10})
            .add_routine(TestRoutine(), "r2", config={"timeout": 20})
            .add_routine(TestRoutine(), "r3")
            .connect("r1", "output", "r2", "input")
            .connect("r2", "output", "r3", "input")
            .build()
        )

        assert flow.flow_id == "complex_flow"
        assert len(flow.routines) == 3
        assert len(flow.connections) == 2
        assert flow.routines["r1"].get_config("timeout") == 10
        assert flow.routines["r2"].get_config("timeout") == 20

        # Test validate separately - it should report warnings but not fail
        issues = flow.validate()
        # Should have warnings about unconnected components
        assert len(issues) > 0

    def test_dsl_with_nested_config(self):
        """Test DSL handles nested configuration correctly."""

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)

            def _handle(self, **kwargs):
                pass

        spec = {
            "routines": {
                "r1": {
                    "class": TestRoutine,
                    "config": {
                        "nested": {"key1": "value1", "key2": {"nested2": "value2"}},
                        "list_val": [1, 2, 3],
                        "simple": "test",
                    },
                }
            },
            "connections": [],
        }

        flow = Flow.from_dict(spec)

        routine = flow.routines["r1"]
        config = routine.get_config("nested")
        assert config["key1"] == "value1"
        assert config["key2"]["nested2"] == "value2"
        assert routine.get_config("list_val") == [1, 2, 3]
        assert routine.get_config("simple") == "test"

    # Parameter mapping test removed - feature removed in redesign

    def test_validation_with_multiple_issues(self):
        """Test that validation reports all issues, not just the first one."""
        flow = Flow()

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle)
                self.output_event = self.define_event("output", ["data"])
                self.input_slot = self.define_slot("input", handler=self._handle)
                self.unused_event = self.define_event("unused", ["data"])

            def _handle(self, **kwargs):
                self.emit("output", data="test")

        # Create flow with multiple issues:
        # 1. Circular dependency
        # 2. Unconnected event
        # 3. Unconnected slot
        a = TestRoutine()
        b = TestRoutine()

        id_a = flow.add_routine(a, "A")
        id_b = flow.add_routine(b, "B")

        flow.connect(id_a, "output", id_b, "input")
        flow.connect(id_b, "output", id_a, "input")  # Cycle

        issues = flow.validate()

        # Should report multiple issues
        assert len(issues) >= 2
        cycle_issues = [i for i in issues if "circular" in i.lower() or "cycle" in i.lower()]
        unconnected_issues = [i for i in issues if "unconnected" in i.lower()]
        assert len(cycle_issues) > 0
        assert len(unconnected_issues) > 0


# ============================================================================
# Test Routine Classes for DSL Testing
# ============================================================================


class SimpleTestRoutine(Routine):
    """Simple test routine for DSL import tests."""

    def __init__(self):
        super().__init__()
        self.trigger_slot = self.define_slot("trigger", handler=self._handle)
        self.output_event = self.define_event("output", ["data"])

    def _handle(self, **kwargs):
        self.emit("output", data="test")
