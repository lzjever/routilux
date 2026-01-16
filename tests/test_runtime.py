"""
Comprehensive tests for Runtime class.

Tests Runtime functionality including:
- Job execution and management
- Event routing
- Routine activation
- Thread safety
- Error handling
- Edge cases
"""

import threading
import time
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from routilux import Flow, Routine
from routilux.activation_policies import immediate_policy
from routilux.job_state import JobState
from routilux.monitoring.flow_registry import FlowRegistry
from routilux.runtime import Runtime
from routilux.slot import SlotQueueFullError
from routilux.status import ExecutionStatus


class TestRuntimeInitialization:
    """Test Runtime initialization"""

    def test_create_runtime(self):
        """Test: Create Runtime with default thread pool size"""
        runtime = Runtime()
        assert runtime.thread_pool_size == 10
        assert runtime._shutdown is False
        assert len(runtime._active_jobs) == 0

    def test_create_runtime_custom_size(self):
        """Test: Create Runtime with custom thread pool size"""
        runtime = Runtime(thread_pool_size=20)
        assert runtime.thread_pool_size == 20

    def test_runtime_shutdown_state(self):
        """Test: Runtime shutdown state management"""
        runtime = Runtime()
        assert runtime._shutdown is False

        runtime.shutdown(wait=False)
        assert runtime._shutdown is True

        # Should raise error when trying to exec after shutdown
        with pytest.raises(RuntimeError, match="Runtime is shut down"):
            runtime.exec("test_flow")


class TestRuntimeJobExecution:
    """Test Runtime job execution"""

    def test_exec_flow_not_found(self):
        """Test: Exec with non-existent flow name"""
        runtime = Runtime()

        with pytest.raises(ValueError, match="Flow 'nonexistent' not found"):
            runtime.exec("nonexistent")

    def test_exec_with_new_job_state(self):
        """Test: Exec creates new JobState if not provided"""
        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("trigger")

        def my_logic(trigger_data, policy_message, job_state):
            pass

        routine.set_logic(my_logic)
        routine.set_activation_policy(immediate_policy())

        flow.add_routine(routine, "entry")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        runtime = Runtime()
        job_state = runtime.exec("test_flow")

        assert job_state is not None
        assert job_state.flow_id == flow.flow_id
        assert job_state.status == ExecutionStatus.RUNNING
        assert job_state.job_id in runtime._active_jobs

        runtime.shutdown(wait=True)

    def test_exec_with_existing_job_state(self):
        """Test: Exec with existing JobState (resume scenario)"""
        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("trigger")

        def my_logic(trigger_data, policy_message, job_state):
            pass

        routine.set_logic(my_logic)
        routine.set_activation_policy(immediate_policy())

        flow.add_routine(routine, "entry")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        # Create existing job_state
        existing_job_state = JobState(flow_id=flow.flow_id)
        existing_job_state.status = ExecutionStatus.PENDING

        runtime = Runtime()
        job_state = runtime.exec("test_flow", job_state=existing_job_state)

        assert job_state is existing_job_state
        assert job_state.status == ExecutionStatus.RUNNING

        runtime.shutdown(wait=True)

    def test_exec_job_state_flow_id_mismatch(self):
        """Test: Exec with JobState flow_id mismatch"""
        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("trigger")

        def my_logic(trigger_data, policy_message, job_state):
            pass

        routine.set_logic(my_logic)
        routine.set_activation_policy(immediate_policy())

        flow.add_routine(routine, "entry")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        # Create job_state with wrong flow_id
        wrong_job_state = JobState(flow_id="wrong_flow_id")

        runtime = Runtime()
        with pytest.raises(ValueError, match="flow_id.*does not match"):
            runtime.exec("test_flow", job_state=wrong_job_state)

        runtime.shutdown(wait=True)


class TestRuntimeEventRouting:
    """Test Runtime event routing"""

    def test_handle_event_emit_no_consumers(self):
        """Test: Event with no consumers is silently discarded"""
        flow = Flow("test_flow")
        routine = Routine()
        event = routine.define_event("output", ["data"])
        flow.add_routine(routine, "source")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        runtime = Runtime()

        # Should not raise error, just discard
        event_data = {
            "data": {"value": "test"},
            "metadata": {
                "emitted_at": datetime.now(),
                "emitted_from": "source",
                "event_name": "output",
            },
        }
        runtime.handle_event_emit(event, event_data, job_state)

        runtime.shutdown(wait=True)

    def test_handle_event_emit_with_consumers(self):
        """Test: Event routed to connected slots"""
        flow = Flow("test_flow")
        source_routine = Routine()
        target_routine = Routine()

        source_event = source_routine.define_event("output", ["data"])
        target_slot = target_routine.define_slot("input")

        flow.add_routine(source_routine, "source")
        flow.add_routine(target_routine, "target")
        flow.connect("source", "output", "target", "input")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        runtime = Runtime()

        event_data = {
            "data": {"value": "test"},
            "metadata": {
                "emitted_at": datetime.now(),
                "emitted_from": "source",
                "event_name": "output",
            },
        }
        runtime.handle_event_emit(source_event, event_data, job_state)

        # Verify data was enqueued
        assert target_slot.get_unconsumed_count() == 1
        data = target_slot.consume_all_new()
        assert len(data) == 1
        assert data[0]["value"] == "test"

        runtime.shutdown(wait=True)

    def test_handle_event_emit_slot_queue_full(self):
        """Test: Slot queue full error is logged and ignored"""
        flow = Flow("test_flow")
        source_routine = Routine()
        target_routine = Routine()

        source_event = source_routine.define_event("output", ["data"])
        target_slot = target_routine.define_slot("input", max_queue_length=1)

        flow.add_routine(source_routine, "source")
        flow.add_routine(target_routine, "target")
        flow.connect("source", "output", "target", "input")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        runtime = Runtime()

        # Fill queue to capacity
        target_slot.enqueue(
            data={"value": 1}, emitted_from="other", emitted_at=datetime.now()
        )
        assert target_slot.get_total_count() == 1

        event_data = {
            "data": {"value": 2},
            "metadata": {
                "emitted_at": datetime.now(),
                "emitted_from": "source",
                "event_name": "output",
            },
        }

        # Should log warning but not crash (Runtime catches SlotQueueFullError)
        with patch("routilux.runtime.logger") as mock_logger:
            runtime.handle_event_emit(source_event, event_data, job_state)
            # Verify warning was logged
            assert mock_logger.warning.called
            # Verify queue is still at capacity (new data was not added)
            assert target_slot.get_total_count() == 1

        runtime.shutdown(wait=True)

    def test_handle_event_emit_flow_not_found(self):
        """Test: Event routing when flow not in registry"""
        event = Mock()
        event_data = {"data": {}, "metadata": {}}
        job_state = JobState(flow_id="nonexistent_flow")

        runtime = Runtime()

        with patch("routilux.runtime.logger") as mock_logger:
            runtime.handle_event_emit(event, event_data, job_state)
            # Should log warning
            assert mock_logger.warning.called

        runtime.shutdown(wait=True)


class TestRuntimeRoutineActivation:
    """Test Runtime routine activation checking"""

    def test_check_routine_activation_no_policy(self):
        """Test: Activation without policy activates immediately"""
        flow = Flow("test_flow")
        routine = Routine()
        slot = routine.define_slot("input")

        logic_called = []

        def my_logic(input_data, policy_message, job_state):
            logic_called.append(True)

        routine.set_logic(my_logic)
        # No activation policy set

        flow.add_routine(routine, "test")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        job_state.current_routine_id = "test"
        runtime = Runtime()

        # Set flow context (required for routine_id lookup)
        routine._current_flow = flow
        routine._current_runtime = runtime

        # Enqueue data
        slot.enqueue(data={"value": 1}, emitted_from="source", emitted_at=datetime.now())

        # Check activation
        runtime._check_routine_activation(routine, job_state)

        # Logic should be called
        assert len(logic_called) == 1

        runtime.shutdown(wait=True)

    def test_check_routine_activation_with_policy(self):
        """Test: Activation with policy respects policy decision"""
        flow = Flow("test_flow")
        routine = Routine()
        slot = routine.define_slot("input")

        logic_called = []

        def my_logic(input_data, policy_message, job_state):
            logic_called.append(True)

        def my_policy(slots, job_state):
            # Only activate if slot has data
            if slot.get_unconsumed_count() > 0:
                return True, {"input": slot.consume_all_new()}, None
            return False, {}, None

        routine.set_logic(my_logic)
        routine.set_activation_policy(my_policy)

        flow.add_routine(routine, "test")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        job_state.current_routine_id = "test"
        runtime = Runtime()

        # Set flow context
        routine._current_flow = flow
        routine._current_runtime = runtime

        # Enqueue data
        slot.enqueue(data={"value": 1}, emitted_from="source", emitted_at=datetime.now())

        # Check activation
        runtime._check_routine_activation(routine, job_state)

        # Logic should be called
        assert len(logic_called) == 1

        runtime.shutdown(wait=True)

    def test_check_routine_activation_policy_error_stop(self):
        """Test: Activation policy error with STOP strategy"""
        from routilux.error_handler import ErrorHandler, ErrorStrategy

        flow = Flow("test_flow")
        routine = Routine()
        routine.set_error_handler(ErrorHandler(strategy=ErrorStrategy.STOP))

        def failing_policy(slots, job_state):
            raise ValueError("Policy error")

        routine.set_activation_policy(failing_policy)

        flow.add_routine(routine, "test")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        job_state.current_routine_id = "test"
        runtime = Runtime()

        # Set flow context
        routine._current_flow = flow
        routine._current_runtime = runtime

        runtime._check_routine_activation(routine, job_state)

        # Job should be marked as failed
        assert job_state.status == ExecutionStatus.FAILED
        assert "Activation policy error" in job_state.error

        runtime.shutdown(wait=True)

    def test_check_routine_activation_policy_error_continue(self):
        """Test: Activation policy error with CONTINUE strategy"""
        from routilux.error_handler import ErrorHandler, ErrorStrategy

        flow = Flow("test_flow")
        routine = Routine()
        routine.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))

        def failing_policy(slots, job_state):
            raise ValueError("Policy error")

        routine.set_activation_policy(failing_policy)

        flow.add_routine(routine, "test")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        job_state.current_routine_id = "test"
        runtime = Runtime()

        # Set flow context
        routine._current_flow = flow
        routine._current_runtime = runtime

        runtime._check_routine_activation(routine, job_state)

        # Job should continue (not failed)
        assert job_state.status != ExecutionStatus.FAILED

        runtime.shutdown(wait=True)


class TestRuntimeLogicExecution:
    """Test Runtime logic execution"""

    def test_activate_routine_logic_success(self):
        """Test: Successful logic execution"""
        flow = Flow("test_flow")
        routine = Routine()
        slot = routine.define_slot("input")

        logic_called = []
        logic_data = []

        def my_logic(input_data, policy_message, job_state):
            logic_called.append(True)
            logic_data.append(input_data)

        routine.set_logic(my_logic)

        flow.add_routine(routine, "test")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        job_state.current_routine_id = "test"
        runtime = Runtime()

        # Set flow context
        routine._current_flow = flow
        routine._current_runtime = runtime

        # Prepare data
        slot.enqueue(data={"value": 1}, emitted_from="source", emitted_at=datetime.now())
        data_slice = {"input": slot.consume_all_new()}

        runtime._activate_routine(routine, job_state, data_slice, None)

        assert len(logic_called) == 1
        assert len(logic_data) == 1

        runtime.shutdown(wait=True)

    def test_activate_routine_logic_error_stop(self):
        """Test: Logic error with STOP strategy"""
        from routilux.error_handler import ErrorHandler, ErrorStrategy

        flow = Flow("test_flow")
        routine = Routine()
        routine.set_error_handler(ErrorHandler(strategy=ErrorStrategy.STOP))

        def failing_logic(input_data, policy_message, job_state):
            raise ValueError("Logic error")

        routine.set_logic(failing_logic)

        flow.add_routine(routine, "test")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        job_state.current_routine_id = "test"
        runtime = Runtime()

        # Set flow context
        routine._current_flow = flow
        routine._current_runtime = runtime

        runtime._activate_routine(routine, job_state, {}, None)

        # Job should be marked as failed
        assert job_state.status == ExecutionStatus.FAILED
        assert "Logic error" in job_state.error

        runtime.shutdown(wait=True)

    def test_activate_routine_logic_error_continue(self):
        """Test: Logic error with CONTINUE strategy"""
        from routilux.error_handler import ErrorHandler, ErrorStrategy

        flow = Flow("test_flow")
        routine = Routine()
        routine.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))

        def failing_logic(input_data, policy_message, job_state):
            raise ValueError("Logic error")

        routine.set_logic(failing_logic)

        flow.add_routine(routine, "test")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        job_state.current_routine_id = "test"
        runtime = Runtime()

        # Set flow context
        routine._current_flow = flow
        routine._current_runtime = runtime

        runtime._activate_routine(routine, job_state, {}, None)

        # Job should continue
        assert job_state.status != ExecutionStatus.FAILED
        # Error should be recorded
        assert len(job_state.execution_history) > 0

        runtime.shutdown(wait=True)


class TestRuntimeJobManagement:
    """Test Runtime job management"""

    def test_get_job(self):
        """Test: Get job by ID"""
        runtime = Runtime()
        job_state = JobState(flow_id="test")
        runtime._active_jobs[job_state.job_id] = job_state

        retrieved = runtime.get_job(job_state.job_id)
        assert retrieved is job_state

        retrieved = runtime.get_job("nonexistent")
        assert retrieved is None

        runtime.shutdown(wait=True)

    def test_list_jobs(self):
        """Test: List all jobs"""
        runtime = Runtime()
        job1 = JobState(flow_id="test1")
        job1.status = ExecutionStatus.RUNNING
        job2 = JobState(flow_id="test2")
        job2.status = ExecutionStatus.COMPLETED

        runtime._active_jobs[job1.job_id] = job1
        runtime._active_jobs[job2.job_id] = job2

        all_jobs = runtime.list_jobs()
        assert len(all_jobs) == 2

        running_jobs = runtime.list_jobs(status="running")
        assert len(running_jobs) == 1
        assert running_jobs[0].job_id == job1.job_id
        
        # Test with status enum value
        running_jobs2 = runtime.list_jobs(status=ExecutionStatus.RUNNING.value)
        assert len(running_jobs2) == 1

        runtime.shutdown(wait=True)

    def test_cancel_job(self):
        """Test: Cancel a running job"""
        runtime = Runtime()
        job_state = JobState(flow_id="test")
        job_state.status = ExecutionStatus.RUNNING
        runtime._active_jobs[job_state.job_id] = job_state

        result = runtime.cancel_job(job_state.job_id)
        assert result is True
        assert job_state.status == ExecutionStatus.CANCELLED

        # Cancel non-existent job
        result = runtime.cancel_job("nonexistent")
        assert result is False

        # Cancel already completed job
        job_state.status = ExecutionStatus.COMPLETED
        result = runtime.cancel_job(job_state.job_id)
        assert result is False

        runtime.shutdown(wait=True)

    def test_wait_until_all_jobs_finished(self):
        """Test: Wait for all jobs to finish"""
        runtime = Runtime()
        job1 = JobState(flow_id="test1")
        job1.status = ExecutionStatus.RUNNING
        job2 = JobState(flow_id="test2")
        job2.status = ExecutionStatus.COMPLETED

        runtime._active_jobs[job1.job_id] = job1
        runtime._active_jobs[job2.job_id] = job2

        # With running job, should timeout
        result = runtime.wait_until_all_jobs_finished(timeout=0.1)
        assert result is False

        # Mark job as completed
        job1.status = ExecutionStatus.COMPLETED
        result = runtime.wait_until_all_jobs_finished(timeout=1.0)
        assert result is True

        runtime.shutdown(wait=True)


class TestRuntimeThreadSafety:
    """Test Runtime thread safety"""

    def test_concurrent_job_execution(self):
        """Test: Concurrent job execution"""
        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("trigger")

        def my_logic(trigger_data, policy_message, job_state):
            time.sleep(0.1)  # Simulate work

        routine.set_logic(my_logic)
        routine.set_activation_policy(immediate_policy())
        flow.add_routine(routine, "entry")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        runtime = Runtime(thread_pool_size=5)

        # Start multiple jobs concurrently
        job_states = []
        for i in range(5):
            job_state = runtime.exec("test_flow")
            job_states.append(job_state)

        # All should be registered
        assert len(runtime._active_jobs) == 5

        # Wait for completion
        runtime.wait_until_all_jobs_finished(timeout=5.0)

        runtime.shutdown(wait=True)

    def test_concurrent_event_routing(self):
        """Test: Concurrent event routing to same slot"""
        flow = Flow("test_flow")
        source = Routine()
        target = Routine()

        event = source.define_event("output", ["data"])
        slot = target.define_slot("input")

        flow.add_routine(source, "source")
        flow.add_routine(target, "target")
        flow.connect("source", "output", "target", "input")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        runtime = Runtime()

        # Route events concurrently
        def route_event(i):
            event_data = {
                "data": {"value": i},
                "metadata": {
                    "emitted_at": datetime.now(),
                    "emitted_from": "source",
                    "event_name": "output",
                },
            }
            runtime.handle_event_emit(event, event_data, job_state)

        threads = []
        for i in range(10):
            t = threading.Thread(target=route_event, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All events should be enqueued
        assert slot.get_total_count() == 10

        runtime.shutdown(wait=True)


class TestRuntimeEdgeCases:
    """Test Runtime edge cases"""

    def test_exec_empty_flow(self):
        """Test: Exec with empty flow"""
        flow = Flow("empty_flow")
        FlowRegistry.get_instance().register_by_name("empty_flow", flow)

        runtime = Runtime()

        # Empty flow will fail when trying to find entry routine
        # Runtime catches the exception and marks job as failed
        job_state = runtime.exec("empty_flow")
        
        # Wait a bit for execution to complete
        runtime.wait_until_all_jobs_finished(timeout=1.0)
        
        # Job should be marked as failed
        assert job_state.status == ExecutionStatus.FAILED

        runtime.shutdown(wait=True)

    def test_activate_routine_no_routine_id(self):
        """Test: Activate routine when routine_id cannot be determined"""
        flow = Flow("test_flow")
        routine = Routine()
        routine._current_flow = None  # No flow context

        job_state = JobState(flow_id=flow.flow_id)
        runtime = Runtime()

        with patch("routilux.runtime.logger") as mock_logger:
            runtime._activate_routine(routine, job_state, {}, None)
            # Should log warning
            assert mock_logger.warning.called

        runtime.shutdown(wait=True)

    def test_shutdown_with_running_jobs(self):
        """Test: Shutdown with running jobs"""
        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("trigger")

        def my_logic(trigger_data, policy_message, job_state):
            time.sleep(1.0)  # Long running

        routine.set_logic(my_logic)
        routine.set_activation_policy(immediate_policy())
        flow.add_routine(routine, "entry")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        runtime = Runtime()
        job_state = runtime.exec("test_flow")

        # Shutdown with timeout (should not wait for long-running job)
        start = time.time()
        runtime.shutdown(wait=True, timeout=0.5)
        elapsed = time.time() - start

        # Should timeout and return quickly (within 1.2 seconds, allowing for overhead)
        # The timeout is 0.5s, but there's overhead from thread pool shutdown
        assert elapsed < 1.2
        # Should be at least close to timeout (0.5s) but allow some overhead
        assert elapsed >= 0.4
