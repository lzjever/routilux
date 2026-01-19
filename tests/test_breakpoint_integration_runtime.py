"""
Integration tests for breakpoint mechanism with actual Runtime and Flow.

These tests verify that breakpoints actually intercept slot enqueue operations
during event routing.
"""

import pytest
import time
from routilux.core.runtime import Runtime
from routilux.core.flow import Flow
from routilux.core.routine import Routine
from routilux.core.event import Event
from routilux.monitoring.breakpoint_manager import Breakpoint
from routilux.monitoring.registry import MonitoringRegistry


class SourceRoutine(Routine):
    """Simple source routine that emits data."""

    def __init__(self):
        super().__init__()
        self.trigger = self.add_slot("trigger")
        self.output = self.add_event("output")

    def logic(self, **kwargs):
        """Emit output event."""
        self.output.emit(result="test_data")


class TargetRoutine(Routine):
    """Simple target routine that receives data."""

    def __init__(self):
        super().__init__()
        self.input = self.add_slot("input")

    def logic(self, **kwargs):
        """Process input data."""
        data = self.input.consume_all_new()
        return {"processed": data}


class TestBreakpointRuntimeIntegration:
    """Integration tests with Runtime and Flow."""

    def test_breakpoint_intercepts_slot_enqueue(self):
        """Test that breakpoint intercepts slot enqueue during event routing."""
        # Setup flow
        flow = Flow("test_flow")
        source = SourceRoutine()
        target = TargetRoutine()
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        # Create runtime
        runtime = Runtime()

        # Register flow
        from routilux.core.registry import FlowRegistry

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        # Create worker and job
        worker_state, job_context = runtime.post(
            "test_flow", "source", "trigger", {"data": "test"}
        )

        # Setup breakpoint manager
        registry = MonitoringRegistry.get_instance()
        if not registry.breakpoint_manager:
            pytest.skip("Breakpoint manager not available")

        breakpoint_mgr = registry.breakpoint_manager

        # Create breakpoint on target slot
        breakpoint = Breakpoint(
            job_id=job_context.job_id,
            routine_id="target",
            slot_name="input",
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        # Emit event from source
        source.output.emit(runtime=runtime, worker_state=worker_state, result="test_data")

        # Wait for event routing (happens in event loop thread)
        time.sleep(0.2)

        # Verify breakpoint was hit
        assert breakpoint.hit_count == 1, "Breakpoint should have been hit once"

        # Verify slot did NOT receive data (breakpoint intercepted)
        assert (
            target.input.get_unconsumed_count() == 0
        ), "Slot should not have received data due to breakpoint"

    def test_breakpoint_does_not_affect_other_jobs(self):
        """Test that breakpoint only affects the specific job."""
        # Setup flow
        flow = Flow("test_flow")
        source = SourceRoutine()
        target = TargetRoutine()
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        # Create runtime
        runtime = Runtime()

        # Register flow
        from routilux.core.registry import FlowRegistry

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        # Create two jobs
        worker_state1, job_context1 = runtime.post(
            "test_flow", "source", "trigger", {"data": "test1"}
        )
        worker_state2, job_context2 = runtime.post(
            "test_flow", "source", "trigger", {"data": "test2"}
        )

        # Setup breakpoint manager
        registry = MonitoringRegistry.get_instance()
        if not registry.breakpoint_manager:
            pytest.skip("Breakpoint manager not available")

        breakpoint_mgr = registry.breakpoint_manager

        # Create breakpoint only for job1
        breakpoint = Breakpoint(
            job_id=job_context1.job_id,
            routine_id="target",
            slot_name="input",
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        # Emit events from both sources
        source.output.emit(runtime=runtime, worker_state=worker_state1, result="test_data1")
        source.output.emit(runtime=runtime, worker_state=worker_state2, result="test_data2")

        # Wait for event routing
        time.sleep(0.3)

        # Verify breakpoint was hit only once (for job1)
        assert breakpoint.hit_count == 1, "Breakpoint should have been hit once for job1"

        # Note: We can't easily verify that job2's data reached the slot
        # because we're using the same flow instance. But the breakpoint
        # hit count confirms it only matched job1.

    def test_disabled_breakpoint_does_not_intercept(self):
        """Test that disabled breakpoint does not intercept."""
        # Setup flow
        flow = Flow("test_flow")
        source = SourceRoutine()
        target = TargetRoutine()
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        # Create runtime
        runtime = Runtime()

        # Register flow
        from routilux.core.registry import FlowRegistry

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        # Create worker and job
        worker_state, job_context = runtime.post(
            "test_flow", "source", "trigger", {"data": "test"}
        )

        # Setup breakpoint manager
        registry = MonitoringRegistry.get_instance()
        if not registry.breakpoint_manager:
            pytest.skip("Breakpoint manager not available")

        breakpoint_mgr = registry.breakpoint_manager

        # Create disabled breakpoint
        breakpoint = Breakpoint(
            job_id=job_context.job_id,
            routine_id="target",
            slot_name="input",
            enabled=False,  # Disabled
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        # Emit event from source
        source.output.emit(runtime=runtime, worker_state=worker_state, result="test_data")

        # Wait for event routing
        time.sleep(0.2)

        # Verify breakpoint was NOT hit
        assert breakpoint.hit_count == 0, "Disabled breakpoint should not be hit"

        # Note: We can't easily verify that data reached the slot in this test
        # because we need to check slot state, but the hit_count confirms
        # the breakpoint didn't match.

    def test_breakpoint_condition_evaluation(self):
        """Test breakpoint with condition during event routing."""
        # Setup flow
        flow = Flow("test_flow")
        source = SourceRoutine()
        target = TargetRoutine()
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        # Create runtime
        runtime = Runtime()

        # Register flow
        from routilux.core.registry import FlowRegistry

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        # Create worker and job
        worker_state, job_context = runtime.post(
            "test_flow", "source", "trigger", {"data": "test"}
        )

        # Setup breakpoint manager
        registry = MonitoringRegistry.get_instance()
        if not registry.breakpoint_manager:
            pytest.skip("Breakpoint manager not available")

        breakpoint_mgr = registry.breakpoint_manager

        # Create breakpoint with condition
        breakpoint = Breakpoint(
            job_id=job_context.job_id,
            routine_id="target",
            slot_name="input",
            condition='result == "test_data"',  # Condition matches
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        # Emit event from source
        source.output.emit(runtime=runtime, worker_state=worker_state, result="test_data")

        # Wait for event routing
        time.sleep(0.2)

        # Verify breakpoint was hit (condition evaluated to True)
        assert breakpoint.hit_count == 1, "Breakpoint with matching condition should be hit"

    def test_breakpoint_condition_false_does_not_intercept(self):
        """Test that breakpoint with false condition does not intercept."""
        # Setup flow
        flow = Flow("test_flow")
        source = SourceRoutine()
        target = TargetRoutine()
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        # Create runtime
        runtime = Runtime()

        # Register flow
        from routilux.core.registry import FlowRegistry

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        # Create worker and job
        worker_state, job_context = runtime.post(
            "test_flow", "source", "trigger", {"data": "test"}
        )

        # Setup breakpoint manager
        registry = MonitoringRegistry.get_instance()
        if not registry.breakpoint_manager:
            pytest.skip("Breakpoint manager not available")

        breakpoint_mgr = registry.breakpoint_manager

        # Create breakpoint with condition that won't match
        breakpoint = Breakpoint(
            job_id=job_context.job_id,
            routine_id="target",
            slot_name="input",
            condition='result == "different_data"',  # Condition doesn't match
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        # Emit event from source
        source.output.emit(runtime=runtime, worker_state=worker_state, result="test_data")

        # Wait for event routing
        time.sleep(0.2)

        # Verify breakpoint was NOT hit (condition evaluated to False)
        assert breakpoint.hit_count == 0, "Breakpoint with non-matching condition should not be hit"
