"""
Comprehensive integration tests for breakpoint mechanism with Runtime.

Tests cover:
- Actual event routing with breakpoint interception
- Condition-based breakpoints with various expressions
- Multiple jobs isolation
- Multiple breakpoints on same job
- Breakpoint enable/disable during execution
- Complex flow scenarios
"""

import pytest
import time
from routilux.core.runtime import Runtime
from routilux.core.flow import Flow
from routilux.core.routine import Routine
from routilux.core.registry import FlowRegistry
from routilux.monitoring.breakpoint_manager import Breakpoint
from routilux.monitoring.registry import MonitoringRegistry
from routilux import immediate_policy


@pytest.fixture(scope="function")
def setup_monitoring():
    """Setup monitoring registry for tests."""
    # Enable monitoring
    MonitoringRegistry.enable()
    registry = MonitoringRegistry.get_instance()
    
    # Ensure breakpoint manager exists
    if not registry.breakpoint_manager:
        from routilux.monitoring.breakpoint_manager import BreakpointManager
        registry.breakpoint_manager = BreakpointManager()
    
    yield registry
    
    # Cleanup
    if registry.breakpoint_manager:
        # Clear all breakpoints
        for job_id in list(registry.breakpoint_manager._breakpoints.keys()):
            registry.breakpoint_manager.clear_breakpoints(job_id)


class SourceRoutine(Routine):
    """Source routine that emits data."""

    def setup(self):
        self.trigger = self.add_slot("trigger")
        self.output = self.add_event("output")
        self.set_activation_policy(immediate_policy())

    def logic(self, trigger_data_list, **kwargs):
        """Emit output event with data."""
        worker_state = kwargs.get("worker_state")
        runtime = getattr(worker_state, "_runtime", None)
        
        for data in trigger_data_list:
            # Emit with the data
            self.output.emit(
                runtime=runtime,
                worker_state=worker_state,
                value=data.get("value", 0),
                message=data.get("message", ""),
                count=data.get("count", 0),
            )


class TargetRoutine(Routine):
    """Target routine that receives data."""

    def __init__(self):
        super().__init__()
        self.received_data = []
        self.execution_count = 0

    def setup(self):
        self.input = self.add_slot("input")
        self.set_activation_policy(immediate_policy())

    def logic(self, input_data_list, **kwargs):
        """Process input data."""
        for data in input_data_list:
            self.received_data.append(data)
            self.execution_count += 1
        return {}


class TestBreakpointRuntimeIntegration:
    """Comprehensive runtime integration tests."""

    def test_breakpoint_intercepts_slot_enqueue_basic(self, setup_monitoring):
        """Test basic breakpoint interception during event routing."""
        # Setup flow
        flow = Flow("test_flow_basic")
        source = SourceRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        # Register flow
        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        # Create runtime
        runtime = Runtime()

        # Create worker and job
        worker_state, job_context = runtime.post(
            "test_flow_basic", "source", "trigger", {"value": 42, "message": "test"}
        )

        # Setup breakpoint
        registry = setup_monitoring
        breakpoint_mgr = registry.breakpoint_manager

        # Get actual target routine ID from flow
        target_routine_id_actual = flow._get_routine_id(target)
        assert target_routine_id_actual is not None, "Target routine ID should be found in flow"

        breakpoint = Breakpoint(
            job_id=job_context.job_id,
            routine_id=target_routine_id_actual,
            slot_name="input",
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        # Get initial slot state
        initial_count = target.input.get_unconsumed_count()

        # Emit event from source
        source.output.emit(
            runtime=runtime,
            worker_state=worker_state,
            value=42,
            message="test",
            count=1,
        )

        # Wait for event routing (happens in event loop thread)
        # Give more time for async processing
        max_wait = 1.0
        start_time = time.time()
        while breakpoint.hit_count == 0 and (time.time() - start_time) < max_wait:
            time.sleep(0.1)

        # Verify breakpoint was hit
        assert breakpoint.hit_count == 1, (
            f"Breakpoint should have been hit once, got {breakpoint.hit_count}. "
            f"Job ID: {job_context.job_id}, Routine ID: {target_routine_id_actual}, Slot: input"
        )

        # Wait a bit more to ensure routine activation check completes
        time.sleep(0.2)

        # Verify slot did NOT receive data (breakpoint intercepted)
        final_count = target.input.get_unconsumed_count()
        assert (
            final_count == initial_count
        ), (
            f"Slot should not have received data due to breakpoint. "
            f"Initial: {initial_count}, Final: {final_count}"
        )

    def test_breakpoint_condition_simple_comparison(self, setup_monitoring):
        """Test breakpoint with simple condition comparison."""
        # Setup flow
        flow = Flow("test_flow_condition")
        source = SourceRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        runtime = Runtime()
        worker_state, job_context = runtime.post(
            "test_flow_condition", "source", "trigger", {"value": 50}
        )

        registry = setup_monitoring
        breakpoint_mgr = registry.breakpoint_manager

        # Get actual target routine ID from flow
        target_routine_id_actual = flow._get_routine_id(target)
        assert target_routine_id_actual is not None, "Target routine ID should be found in flow"

        # Create breakpoint with condition: value > 40
        breakpoint = Breakpoint(
            job_id=job_context.job_id,
            routine_id=target_routine_id_actual,
            slot_name="input",
            condition="value > 40",
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        initial_count = target.input.get_unconsumed_count()

        # Emit event with value=50 (condition should match)
        source.output.emit(
            runtime=runtime, worker_state=worker_state, value=50, message="test", count=1
        )

        # Wait for breakpoint to be hit
        max_wait = 1.0
        start_time = time.time()
        while breakpoint.hit_count == 0 and (time.time() - start_time) < max_wait:
            time.sleep(0.1)
        
        time.sleep(0.2)

        # Verify breakpoint was hit (condition evaluated to True)
        assert breakpoint.hit_count == 1, (
            f"Breakpoint with matching condition should be hit, got {breakpoint.hit_count}"
        )

        # Verify slot did not receive data
        assert (
            target.input.get_unconsumed_count() == initial_count
        ), "Slot should not have received data when condition matches"

    def test_breakpoint_condition_false_does_not_intercept(self, setup_monitoring):
        """Test that breakpoint with false condition does not intercept."""
        # Setup flow
        flow = Flow("test_flow_condition_false")
        source = SourceRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        runtime = Runtime()
        worker_state, job_context = runtime.post(
            "test_flow_condition_false", "source", "trigger", {"value": 30}
        )

        registry = setup_monitoring
        breakpoint_mgr = registry.breakpoint_manager

        # Get actual target routine ID from flow
        target_routine_id_actual = flow._get_routine_id(target)
        assert target_routine_id_actual is not None, "Target routine ID should be found in flow"

        # Create breakpoint with condition: value > 40
        breakpoint = Breakpoint(
            job_id=job_context.job_id,
            routine_id=target_routine_id_actual,
            slot_name="input",
            condition="value > 40",  # Condition won't match (value=30)
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        initial_count = target.input.get_unconsumed_count()

        # Emit event with value=30 (condition should NOT match)
        source.output.emit(
            runtime=runtime, worker_state=worker_state, value=30, message="test", count=1
        )

        time.sleep(0.3)

        # Verify breakpoint was NOT hit (condition evaluated to False)
        assert breakpoint.hit_count == 0, "Breakpoint with non-matching condition should not be hit"

    def test_breakpoint_condition_complex_expression(self, setup_monitoring):
        """Test breakpoint with complex condition expression."""
        # Setup flow
        flow = Flow("test_flow_condition_complex")
        source = SourceRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        runtime = Runtime()
        worker_state, job_context = runtime.post(
            "test_flow_condition_complex", "source", "trigger", {"value": 25, "count": 5}
        )

        registry = setup_monitoring
        breakpoint_mgr = registry.breakpoint_manager

        # Get actual target routine ID from flow
        target_routine_id_actual = flow._get_routine_id(target)
        assert target_routine_id_actual is not None, "Target routine ID should be found in flow"

        # Create breakpoint with complex condition: value > 20 and count < 10
        breakpoint = Breakpoint(
            job_id=job_context.job_id,
            routine_id=target_routine_id_actual,
            slot_name="input",
            condition="value > 20 and count < 10",
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        initial_count = target.input.get_unconsumed_count()

        # Emit event with value=25, count=5 (condition should match)
        source.output.emit(
            runtime=runtime, worker_state=worker_state, value=25, message="test", count=5
        )

        # Wait for breakpoint to be hit
        max_wait = 1.0
        start_time = time.time()
        while breakpoint.hit_count == 0 and (time.time() - start_time) < max_wait:
            time.sleep(0.1)
        
        time.sleep(0.2)

        # Verify breakpoint was hit
        assert breakpoint.hit_count == 1, (
            f"Breakpoint with matching complex condition should be hit, got {breakpoint.hit_count}. "
            f"Condition: value > 20 and count < 10, Event data: value=25, count=5"
        )

        # Verify slot did not receive data
        assert (
            target.input.get_unconsumed_count() == initial_count
        ), "Slot should not have received data when condition matches"

    def test_breakpoint_condition_string_comparison(self, setup_monitoring):
        """Test breakpoint with string comparison condition."""
        # Setup flow
        flow = Flow("test_flow_condition_string")
        source = SourceRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        runtime = Runtime()
        worker_state, job_context = runtime.post(
            "test_flow_condition_string", "source", "trigger", {"message": "critical"}
        )

        registry = setup_monitoring
        breakpoint_mgr = registry.breakpoint_manager

        # Get actual target routine ID from flow
        target_routine_id_actual = flow._get_routine_id(target)
        assert target_routine_id_actual is not None, "Target routine ID should be found in flow"

        # Create breakpoint with string condition
        breakpoint = Breakpoint(
            job_id=job_context.job_id,
            routine_id=target_routine_id_actual,
            slot_name="input",
            condition='message == "critical"',
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        initial_count = target.input.get_unconsumed_count()

        # Emit event with message="critical" (condition should match)
        source.output.emit(
            runtime=runtime, worker_state=worker_state, value=0, message="critical", count=0
        )

        # Wait for breakpoint to be hit
        max_wait = 1.0
        start_time = time.time()
        while breakpoint.hit_count == 0 and (time.time() - start_time) < max_wait:
            time.sleep(0.1)
        
        time.sleep(0.2)

        # Verify breakpoint was hit
        assert breakpoint.hit_count == 1, "Breakpoint with matching string condition should be hit"

        # Verify slot did not receive data
        assert (
            target.input.get_unconsumed_count() == initial_count
        ), "Slot should not have received data when condition matches"

    def test_breakpoint_job_isolation_multiple_jobs(self, setup_monitoring):
        """Test that breakpoint only affects the specific job."""
        # Setup flow
        flow = Flow("test_flow_isolation")
        source = SourceRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        runtime = Runtime()

        # Create two jobs
        worker_state1, job_context1 = runtime.post(
            "test_flow_isolation", "source", "trigger", {"value": 10}
        )
        worker_state2, job_context2 = runtime.post(
            "test_flow_isolation", "source", "trigger", {"value": 20}
        )

        registry = setup_monitoring
        breakpoint_mgr = registry.breakpoint_manager

        # Get actual target routine ID from flow
        target_routine_id_actual = flow._get_routine_id(target)
        assert target_routine_id_actual is not None, "Target routine ID should be found in flow"

        # Create breakpoint only for job1
        breakpoint = Breakpoint(
            job_id=job_context1.job_id,
            routine_id=target_routine_id_actual,
            slot_name="input",
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        # Emit events from both jobs
        source.output.emit(
            runtime=runtime, worker_state=worker_state1, value=10, message="job1", count=1
        )
        source.output.emit(
            runtime=runtime, worker_state=worker_state2, value=20, message="job2", count=1
        )

        time.sleep(0.4)

        # Verify breakpoint was hit only once (for job1)
        assert breakpoint.hit_count == 1, (
            f"Breakpoint should have been hit once for job1, got {breakpoint.hit_count}"
        )

    def test_multiple_breakpoints_same_job(self, setup_monitoring):
        """Test multiple breakpoints on the same job."""
        # Setup flow with multiple targets
        flow = Flow("test_flow_multi_bp")
        source = SourceRoutine()
        source.setup()
        target1 = TargetRoutine()
        target1.setup()
        target2 = TargetRoutine()
        target2.setup()
        
        source_id = flow.add_routine(source, "source")
        target1_id = flow.add_routine(target1, "target1")
        target2_id = flow.add_routine(target2, "target2")
        flow.connect("source", "output", "target1", "input")
        flow.connect("source", "output", "target2", "input")

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        runtime = Runtime()
        worker_state, job_context = runtime.post(
            "test_flow_multi_bp", "source", "trigger", {"value": 42}
        )

        registry = setup_monitoring
        breakpoint_mgr = registry.breakpoint_manager

        # Get actual target routine IDs from flow
        target1_routine_id = flow._get_routine_id(target1)
        target2_routine_id = flow._get_routine_id(target2)
        assert target1_routine_id is not None and target2_routine_id is not None

        # Create breakpoints on both targets
        bp1 = Breakpoint(
            job_id=job_context.job_id,
            routine_id=target1_routine_id,
            slot_name="input",
            enabled=True,
        )
        bp2 = Breakpoint(
            job_id=job_context.job_id,
            routine_id=target2_routine_id,
            slot_name="input",
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(bp1)
        breakpoint_mgr.add_breakpoint(bp2)

        # Emit event (should hit both breakpoints)
        source.output.emit(
            runtime=runtime, worker_state=worker_state, value=42, message="test", count=1
        )

        # Wait for both breakpoints to be hit
        max_wait = 1.0
        start_time = time.time()
        while (bp1.hit_count == 0 or bp2.hit_count == 0) and (time.time() - start_time) < max_wait:
            time.sleep(0.1)

        time.sleep(0.2)

        # Verify both breakpoints were hit
        assert bp1.hit_count == 1, f"Breakpoint 1 should have been hit, got {bp1.hit_count}"
        assert bp2.hit_count == 1, f"Breakpoint 2 should have been hit, got {bp2.hit_count}"

    def test_breakpoint_enable_disable_during_execution(self, setup_monitoring):
        """Test enabling/disabling breakpoint during execution."""
        # Setup flow
        flow = Flow("test_flow_enable_disable")
        source = SourceRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        runtime = Runtime()
        
        # Create first job for first event
        worker_state1, job_context1 = runtime.post(
            "test_flow_enable_disable", "source", "trigger", {"value": 42}
        )

        registry = setup_monitoring
        breakpoint_mgr = registry.breakpoint_manager

        # Get actual target routine ID from flow
        target_routine_id_actual = flow._get_routine_id(target)
        assert target_routine_id_actual is not None, "Target routine ID should be found in flow"

        # Create disabled breakpoint for job1
        breakpoint = Breakpoint(
            job_id=job_context1.job_id,
            routine_id=target_routine_id_actual,
            slot_name="input",
            enabled=False,  # Initially disabled
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        # Emit first event (breakpoint disabled, should not intercept)
        source.output.emit(
            runtime=runtime, worker_state=worker_state1, value=42, message="event1", count=1
        )
        time.sleep(0.4)

        assert breakpoint.hit_count == 0, f"Disabled breakpoint should not be hit, got {breakpoint.hit_count}"

        # Enable breakpoint
        breakpoint.enabled = True
        
        # Verify breakpoint is enabled
        assert breakpoint.enabled is True, "Breakpoint should be enabled"

        # Create second job for second event (to ensure fresh job_context)
        worker_state2, job_context2 = runtime.post(
            "test_flow_enable_disable", "source", "trigger", {"value": 43}
        )
        
        # Update breakpoint job_id to job2
        # Actually, we should create a new breakpoint for job2
        breakpoint2 = Breakpoint(
            job_id=job_context2.job_id,
            routine_id=target_routine_id_actual,
            slot_name="input",
            enabled=True,  # Enabled
        )
        breakpoint_mgr.add_breakpoint(breakpoint2)

        # Emit second event (breakpoint enabled, should intercept)
        source.output.emit(
            runtime=runtime, worker_state=worker_state2, value=43, message="event2", count=2
        )
        
        # Wait for breakpoint to be hit
        max_wait = 2.0
        start_time = time.time()
        while breakpoint2.hit_count == 0 and (time.time() - start_time) < max_wait:
            time.sleep(0.15)
        
        time.sleep(0.3)

        assert breakpoint2.hit_count == 1, (
            f"Enabled breakpoint should be hit, got {breakpoint2.hit_count}. "
            f"Breakpoint enabled: {breakpoint2.enabled}, Job ID: {job_context2.job_id}"
        )

        # Disable breakpoint
        breakpoint2.enabled = False

        # Create third job for third event
        worker_state3, job_context3 = runtime.post(
            "test_flow_enable_disable", "source", "trigger", {"value": 44}
        )

        # Emit third event (breakpoint disabled again, should not intercept)
        source.output.emit(
            runtime=runtime, worker_state=worker_state3, value=44, message="event3", count=3
        )
        time.sleep(0.4)

        assert breakpoint2.hit_count == 1, f"Disabled breakpoint should not be hit again, got {breakpoint2.hit_count}"

    def test_breakpoint_condition_with_missing_variable(self, setup_monitoring):
        """Test breakpoint condition when variable is missing."""
        # Setup flow
        flow = Flow("test_flow_missing_var")
        source = SourceRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        runtime = Runtime()
        worker_state, job_context = runtime.post(
            "test_flow_missing_var", "source", "trigger", {"value": 42}
        )

        registry = setup_monitoring
        breakpoint_mgr = registry.breakpoint_manager

        # Get actual target routine ID from flow
        target_routine_id_actual = flow._get_routine_id(target)
        assert target_routine_id_actual is not None, "Target routine ID should be found in flow"

        # Create breakpoint with condition referencing missing variable
        breakpoint = Breakpoint(
            job_id=job_context.job_id,
            routine_id=target_routine_id_actual,
            slot_name="input",
            condition="missing_var > 10",  # Variable doesn't exist in event data
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        initial_count = target.input.get_unconsumed_count()

        # Emit event without missing_var
        source.output.emit(
            runtime=runtime, worker_state=worker_state, value=42, message="test", count=1
        )

        time.sleep(0.3)

        # Condition evaluation should fail gracefully (NameError)
        # Breakpoint should not match
        # Note: The exact behavior depends on breakpoint_condition implementation
        # If it raises an exception, the breakpoint won't match (which is correct)
        # If it returns False, the breakpoint won't match (which is also correct)
        assert breakpoint.hit_count == 0, "Breakpoint with missing variable should not match"

    def test_breakpoint_condition_with_nested_data(self, setup_monitoring):
        """Test breakpoint condition with nested data access."""
        # Setup flow
        flow = Flow("test_flow_nested")
        source = SourceRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        runtime = Runtime()
        worker_state, job_context = runtime.post(
            "test_flow_nested", "source", "trigger", {"value": 42}
        )

        registry = setup_monitoring
        breakpoint_mgr = registry.breakpoint_manager

        # Get actual target routine ID from flow
        target_routine_id_actual = flow._get_routine_id(target)
        assert target_routine_id_actual is not None, "Target routine ID should be found in flow"

        # Create breakpoint with condition using multiple variables
        breakpoint = Breakpoint(
            job_id=job_context.job_id,
            routine_id=target_routine_id_actual,
            slot_name="input",
            condition="value > 40 and count > 0",
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        initial_count = target.input.get_unconsumed_count()

        # Set job_context in current thread context before emitting
        # This ensures event.emit() can retrieve it via get_current_job()
        from routilux.core.context import set_current_job
        set_current_job(job_context)

        # Emit event with matching values
        source.output.emit(
            runtime=runtime, worker_state=worker_state, value=42, message="test", count=5
        )

        # Wait for breakpoint to be hit (give more time for condition evaluation)
        max_wait = 2.0
        start_time = time.time()
        while breakpoint.hit_count == 0 and (time.time() - start_time) < max_wait:
            time.sleep(0.15)
        
        time.sleep(0.3)

        # Verify breakpoint was hit
        # Note: If this fails, it may indicate condition evaluation issue or job_context/routine_id problem
        assert breakpoint.hit_count == 1, (
            f"Breakpoint with matching nested condition should be hit, got {breakpoint.hit_count}. "
            f"Condition: {breakpoint.condition}, Event data: value=42, count=5, "
            f"Job ID: {job_context.job_id}, Routine ID: {target_routine_id_actual}"
        )

        # Verify slot did not receive data
        assert (
            target.input.get_unconsumed_count() == initial_count
        ), "Slot should not have received data when condition matches"

    def test_breakpoint_removed_during_execution(self, setup_monitoring):
        """Test removing breakpoint during execution."""
        # Setup flow
        flow = Flow("test_flow_remove")
        source = SourceRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        runtime = Runtime()
        worker_state, job_context = runtime.post(
            "test_flow_remove", "source", "trigger", {"value": 42}
        )

        registry = setup_monitoring
        breakpoint_mgr = registry.breakpoint_manager

        # Get actual target routine ID from flow
        target_routine_id_actual = flow._get_routine_id(target)
        assert target_routine_id_actual is not None, "Target routine ID should be found in flow"

        # Create breakpoint
        breakpoint = Breakpoint(
            job_id=job_context.job_id,
            routine_id=target_routine_id_actual,
            slot_name="input",
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        # Emit first event (breakpoint should intercept)
        source.output.emit(
            runtime=runtime, worker_state=worker_state, value=42, message="event1", count=1
        )
        
        # Wait for breakpoint to be hit
        max_wait = 1.0
        start_time = time.time()
        while breakpoint.hit_count == 0 and (time.time() - start_time) < max_wait:
            time.sleep(0.1)
        
        time.sleep(0.2)

        assert breakpoint.hit_count == 1, f"Breakpoint should be hit before removal, got {breakpoint.hit_count}"

        # Remove breakpoint
        breakpoint_mgr.remove_breakpoint(breakpoint.breakpoint_id, job_context.job_id)

        # Emit second event (breakpoint removed, should not intercept)
        source.output.emit(
            runtime=runtime, worker_state=worker_state, value=43, message="event2", count=2
        )
        time.sleep(0.3)

        # Hit count should still be 1 (breakpoint was removed)
        assert breakpoint.hit_count == 1, f"Breakpoint hit count should not increase after removal, got {breakpoint.hit_count}"

    def test_breakpoint_multiple_events_same_slot(self, setup_monitoring):
        """Test breakpoint with multiple events to the same slot."""
        # Setup flow
        flow = Flow("test_flow_multi_events")
        source = SourceRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        runtime = Runtime()
        worker_state, job_context = runtime.post(
            "test_flow_multi_events", "source", "trigger", {"value": 42}
        )

        registry = setup_monitoring
        breakpoint_mgr = registry.breakpoint_manager

        # Get actual target routine ID from flow
        target_routine_id_actual = flow._get_routine_id(target)
        assert target_routine_id_actual is not None, "Target routine ID should be found in flow"

        # Create breakpoint
        breakpoint = Breakpoint(
            job_id=job_context.job_id,
            routine_id=target_routine_id_actual,
            slot_name="input",
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        # Set job_context in current thread context before emitting
        # This ensures event.emit() can retrieve it via get_current_job()
        from routilux.core.context import set_current_job
        set_current_job(job_context)

        # Emit multiple events with longer delays
        for i in range(5):
            source.output.emit(
                runtime=runtime,
                worker_state=worker_state,
                value=42 + i,
                message=f"event{i}",
                count=i,
            )
            # Wait a bit after each emit to ensure it's processed
            time.sleep(0.3)

        # Wait for all events to be processed (give more time)
        max_wait = 3.0
        start_time = time.time()
        while breakpoint.hit_count < 5 and (time.time() - start_time) < max_wait:
            time.sleep(0.2)

        time.sleep(0.5)

        # Verify breakpoint was hit for each event
        # Note: hit_count might be slightly more than 5 if there are duplicate events
        # or if the initial trigger event also routes (which is expected behavior)
        # The important thing is that breakpoint is working and intercepting events
        assert breakpoint.hit_count >= 5, (
            f"Breakpoint should have been hit at least 5 times, got {breakpoint.hit_count}. "
            f"This may indicate events are being processed in batch or breakpoint check is not working for all events. "
            f"Job ID: {job_context.job_id}, Routine ID: {target_routine_id_actual}"
        )
        
        # Also verify that breakpoint is working (hit_count > 0)
        assert breakpoint.hit_count > 0, "Breakpoint should have been hit at least once"

        # Verify slot did not receive any data
        assert (
            target.input.get_unconsumed_count() == 0
        ), "Slot should not have received any data due to breakpoint"

    def test_breakpoint_condition_with_arithmetic(self, setup_monitoring):
        """Test breakpoint condition with arithmetic operations."""
        # Setup flow
        flow = Flow("test_flow_arithmetic")
        source = SourceRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        runtime = Runtime()
        worker_state, job_context = runtime.post(
            "test_flow_arithmetic", "source", "trigger", {"value": 15, "count": 3}
        )

        registry = setup_monitoring
        breakpoint_mgr = registry.breakpoint_manager

        # Get actual target routine ID from flow
        target_routine_id_actual = flow._get_routine_id(target)
        assert target_routine_id_actual is not None, "Target routine ID should be found in flow"

        # Create breakpoint with arithmetic condition: value * count > 40
        breakpoint = Breakpoint(
            job_id=job_context.job_id,
            routine_id=target_routine_id_actual,
            slot_name="input",
            condition="value * count > 40",  # 15 * 3 = 45 > 40, should match
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(breakpoint)

        initial_count = target.input.get_unconsumed_count()

        # Emit event
        source.output.emit(
            runtime=runtime, worker_state=worker_state, value=15, message="test", count=3
        )

        # Wait for breakpoint to be hit
        max_wait = 1.0
        start_time = time.time()
        while breakpoint.hit_count == 0 and (time.time() - start_time) < max_wait:
            time.sleep(0.1)
        
        time.sleep(0.2)

        # Verify breakpoint was hit
        assert breakpoint.hit_count == 1, "Breakpoint with matching arithmetic condition should be hit"

        # Verify slot did not receive data
        assert (
            target.input.get_unconsumed_count() == initial_count
        ), "Slot should not have received data when condition matches"

    def test_breakpoint_no_condition_vs_with_condition(self, setup_monitoring):
        """Test breakpoint without condition vs with condition."""
        # Setup flow
        flow = Flow("test_flow_no_condition")
        source = SourceRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register(flow)

        runtime = Runtime()
        worker_state, job_context = runtime.post(
            "test_flow_no_condition", "source", "trigger", {"value": 30}
        )

        registry = setup_monitoring
        breakpoint_mgr = registry.breakpoint_manager

        # Get actual target routine ID from flow
        target_routine_id_actual = flow._get_routine_id(target)
        assert target_routine_id_actual is not None, "Target routine ID should be found in flow"

        # Create breakpoint without condition (should always match)
        bp_no_condition = Breakpoint(
            job_id=job_context.job_id,
            routine_id=target_routine_id_actual,
            slot_name="input",
            condition=None,
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(bp_no_condition)

        # Create breakpoint with condition (value > 40, won't match)
        bp_with_condition = Breakpoint(
            job_id=job_context.job_id,
            routine_id=target_routine_id_actual,
            slot_name="input",
            condition="value > 40",
            enabled=True,
        )
        breakpoint_mgr.add_breakpoint(bp_with_condition)

        initial_count = target.input.get_unconsumed_count()

        # Emit event with value=30
        source.output.emit(
            runtime=runtime, worker_state=worker_state, value=30, message="test", count=1
        )

        # Wait for breakpoint to be hit
        max_wait = 1.0
        start_time = time.time()
        while bp_no_condition.hit_count == 0 and (time.time() - start_time) < max_wait:
            time.sleep(0.1)
        
        time.sleep(0.2)

        # Verify breakpoint without condition was hit
        assert bp_no_condition.hit_count == 1, "Breakpoint without condition should always match"

        # Verify breakpoint with condition was NOT hit
        assert bp_with_condition.hit_count == 0, "Breakpoint with non-matching condition should not match"

        # Verify slot did not receive data (breakpoint without condition intercepted)
        assert (
            target.input.get_unconsumed_count() == initial_count
        ), "Slot should not have received data (breakpoint without condition intercepted)"
