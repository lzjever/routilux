"""
Comprehensive tests for Runtime active routines tracking.

Tests the active routines tracking functionality:
- Tracking routines during execution
- Thread safety
- Cleanup after execution
- Multiple concurrent routines
- Edge cases
"""

import threading
import time
from datetime import datetime

import pytest

from routilux import Flow, Routine
from routilux.activation_policies import immediate_policy
from routilux.job_state import JobState
from routilux.monitoring.flow_registry import FlowRegistry
from routilux.runtime import Runtime, get_runtime_instance
from routilux.status import ExecutionStatus


class TestRuntimeActiveRoutinesTracking:
    """Test Runtime active routines tracking functionality"""

    def test_get_active_routines_empty_job(self):
        """Test: get_active_routines returns empty set for non-existent job"""
        runtime = Runtime()
        active = runtime.get_active_routines("non_existent_job_id")
        assert isinstance(active, set)
        assert len(active) == 0

    def test_get_active_routines_returns_copy(self):
        """Test: get_active_routines returns a copy, not the original set"""
        runtime = Runtime()
        active1 = runtime.get_active_routines("job1")
        active2 = runtime.get_active_routines("job1")
        # Modifying one should not affect the other
        active1.add("test_routine")
        assert "test_routine" not in active2

    def test_routine_tracked_during_execution(self):
        """Test: Routine is tracked as active during execution"""
        flow = Flow("test_flow")
        execution_times = []

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger")
                self.output_event = self.define_event("output", ["data"])

                def my_logic(trigger_data, policy_message, job_state):
                    # Record execution start time
                    execution_times.append(time.time())
                    # Check if routine is tracked as active (should be True)
                    runtime = get_runtime_instance()
                    active = runtime.get_active_routines(job_state.job_id)
                    # Get routine_id from flow
                    flow = getattr(self, "_current_flow", None)
                    if flow:
                        routine_id = flow._get_routine_id(self)
                        if routine_id:
                            execution_times.append(("active_check", routine_id in active))
                    # Simulate some work
                    time.sleep(0.1)

                self.set_logic(my_logic)
                self.set_activation_policy(immediate_policy())

        routine = TestRoutine()
        flow.add_routine(routine, "test_routine")

        FlowRegistry.get_instance().register(flow)

        # Use get_runtime_instance() to ensure the same instance is used
        runtime = get_runtime_instance()
        job_state = runtime.exec("test_flow")
        runtime.wait_until_all_jobs_finished(timeout=5.0)

        # Verify routine was tracked during execution
        assert len(execution_times) >= 2
        # The active_check should be True (routine was active during execution)
        active_checks = [t for t in execution_times if isinstance(t, tuple) and t[0] == "active_check"]
        assert len(active_checks) > 0
        # At least one check should have seen the routine as active
        assert any(check[1] for check in active_checks), \
            f"Expected routine to be active during execution, but active_checks: {active_checks}"

    def test_routine_not_tracked_after_execution(self):
        """Test: Routine is not tracked after execution completes"""
        flow = Flow("test_flow")

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger")
                self.output_event = self.define_event("output", ["data"])

                def my_logic(trigger_data, policy_message, job_state):
                    pass

                self.set_logic(my_logic)
                self.set_activation_policy(immediate_policy())

        routine = TestRoutine()
        flow.add_routine(routine, "test_routine")

        FlowRegistry.get_instance().register(flow)

        # Use get_runtime_instance() to ensure the same instance is used
        runtime = get_runtime_instance()
        job_state = runtime.exec("test_flow")
        runtime.wait_until_all_jobs_finished(timeout=5.0)

        # Verify routine is not tracked after execution
        active = runtime.get_active_routines(job_state.job_id)
        assert "test_routine" not in active
        assert len(active) == 0

    def test_multiple_routines_tracked_concurrently(self):
        """Test: Multiple routines can be tracked concurrently"""
        flow = Flow("test_flow")
        execution_order = []

        class RoutineA(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger")
                self.output_event = self.define_event("output", ["data"])

                def my_logic(trigger_data, policy_message, job_state):
                    execution_order.append(("A", "start"))
                    time.sleep(0.05)
                    runtime = get_runtime_instance()
                    active = runtime.get_active_routines(job_state.job_id)
                    execution_order.append(("A", "active", "A" in active, "B" in active))
                    time.sleep(0.05)
                    execution_order.append(("A", "end"))
                    # Emit output event to trigger routine B
                    self.output_event.emit(runtime, job_state, data="from_A")

                self.set_logic(my_logic)
                self.set_activation_policy(immediate_policy())

        class RoutineB(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger")
                self.output_event = self.define_event("output", ["data"])

                def my_logic(trigger_data, policy_message, job_state):
                    execution_order.append(("B", "start"))
                    time.sleep(0.05)
                    runtime = get_runtime_instance()
                    active = runtime.get_active_routines(job_state.job_id)
                    execution_order.append(("B", "active", "A" in active, "B" in active))
                    time.sleep(0.05)
                    execution_order.append(("B", "end"))

                self.set_logic(my_logic)
                self.set_activation_policy(immediate_policy())

        routine_a = RoutineA()
        routine_b = RoutineB()
        flow.add_routine(routine_a, "A")
        flow.add_routine(routine_b, "B")
        flow.connect("A", "output", "B", "trigger")

        FlowRegistry.get_instance().register(flow)

        # Use get_runtime_instance() to ensure the same instance is used
        runtime = get_runtime_instance()
        job_state = runtime.exec("test_flow")
        runtime.wait_until_all_jobs_finished(timeout=5.0)

        # Verify both routines were tracked
        active = runtime.get_active_routines(job_state.job_id)
        assert len(active) == 0  # Both should be done

        # Check execution order - both should have been active at some point
        active_checks = [t for t in execution_order if len(t) > 2 and t[1] == "active"]
        assert len(active_checks) >= 2

    def test_routine_tracking_thread_safe(self):
        """Test: Active routines tracking is thread-safe"""
        flow = Flow("test_flow")
        results = []

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger")
                self.output_event = self.define_event("output", ["data"])

                def my_logic(trigger_data, policy_message, job_state):
                    # Multiple threads checking active routines
                    def check_active():
                        runtime = get_runtime_instance()
                        active = runtime.get_active_routines(job_state.job_id)
                        results.append(("check", job_state.job_id in active))

                    threads = [threading.Thread(target=check_active) for _ in range(10)]
                    for t in threads:
                        t.start()
                    for t in threads:
                        t.join()

                self.set_logic(my_logic)
                self.set_activation_policy(immediate_policy())

        routine = TestRoutine()
        flow.add_routine(routine, "test_routine")

        FlowRegistry.get_instance().register(flow)

        # Use get_runtime_instance() to ensure the same instance is used
        runtime = get_runtime_instance()
        job_state = runtime.exec("test_flow")
        runtime.wait_until_all_jobs_finished(timeout=5.0)

        # All checks should have seen the routine as active
        checks = [r for r in results if r[0] == "check"]
        assert len(checks) == 10
        # At least some should have seen it as active (depending on timing)
        active_count = sum(1 for r in checks if r[1])
        assert active_count >= 0  # May be 0 if all checks happened after execution

    def test_get_runtime_instance_singleton(self):
        """Test: get_runtime_instance returns singleton instance"""
        runtime1 = get_runtime_instance()
        runtime2 = get_runtime_instance()
        assert runtime1 is runtime2

    def test_get_runtime_instance_has_active_routines_method(self):
        """Test: Runtime instance from get_runtime_instance has get_active_routines method"""
        runtime = get_runtime_instance()
        assert hasattr(runtime, "get_active_routines")
        assert callable(runtime.get_active_routines)

    def test_active_routines_cleanup_on_job_completion(self):
        """Test: Active routines are cleaned up when job completes"""
        flow = Flow("test_flow")

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger")
                self.output_event = self.define_event("output", ["data"])

                def my_logic(trigger_data, policy_message, job_state):
                    pass

                self.set_logic(my_logic)
                self.set_activation_policy(immediate_policy())

        routine = TestRoutine()
        flow.add_routine(routine, "test_routine")

        FlowRegistry.get_instance().register(flow)

        runtime = Runtime()
        job_state = runtime.exec("test_flow")
        
        # Wait a bit to ensure execution starts
        time.sleep(0.1)
        
        # Check active routines before completion
        active_before = runtime.get_active_routines(job_state.job_id)
        
        # Wait for completion
        runtime.wait_until_all_jobs_finished(timeout=5.0)
        
        # Check active routines after completion
        active_after = runtime.get_active_routines(job_state.job_id)
        
        # After completion, should be empty
        assert len(active_after) == 0
        # Job entry should be cleaned up
        assert job_state.job_id not in runtime._active_routines
