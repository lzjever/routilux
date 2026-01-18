"""
Comprehensive tests for MonitorService.

Tests all MonitorService methods:
- get_active_routines
- get_routine_execution_status
- get_routine_queue_status
- get_routine_info
- get_routine_monitoring_data
- get_job_monitoring_data
- get_all_routines_status
- get_all_queues_status
- Error handling
"""

import time
from datetime import datetime

import pytest

# Check if API dependencies are available
try:
    from routilux.server.models.monitor import (
        JobMonitoringData,
        RoutineExecutionStatus,
        RoutineInfo,
        RoutineMonitoringData,
        SlotQueueStatus,
    )
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False
    # Create dummy classes for type hints
    class SlotQueueStatus:
        pass

    class RoutineExecutionStatus:
        pass

    class RoutineInfo:
        pass

    class RoutineMonitoringData:
        pass

    class JobMonitoringData:
        pass

from routilux import Flow, Routine
from routilux.activation_policies import immediate_policy
from routilux.job_state import JobState
from routilux.monitoring.flow_registry import FlowRegistry
from routilux.monitoring.monitor_service import MonitorService, get_monitor_service
from routilux.monitoring.storage import job_store
from routilux.runtime import Runtime
from routilux.status import ExecutionStatus

# Mark tests that require API as integration tests
pytestmark = pytest.mark.skipif(not API_AVAILABLE, reason="API dependencies not installed")


class TestMonitorServiceBasic:
    """Test MonitorService basic functionality"""

    def test_get_monitor_service_singleton(self):
        """Test: get_monitor_service returns singleton instance"""
        service1 = get_monitor_service()
        service2 = get_monitor_service()
        assert service1 is service2

    def test_get_active_routines_non_existent_job(self):
        """Test: get_active_routines returns empty set for non-existent job"""
        service = MonitorService()
        active = service.get_active_routines("non_existent_job_id")
        assert isinstance(active, set)
        assert len(active) == 0

    def test_get_active_routines_returns_copy(self):
        """Test: get_active_routines returns a copy"""
        service = MonitorService()
        active1 = service.get_active_routines("job1")
        active2 = service.get_active_routines("job1")
        active1.add("test")
        assert "test" not in active2


class TestMonitorServiceRoutineExecutionStatus:
    """Test MonitorService routine execution status methods"""

    def test_get_routine_execution_status_non_existent_job(self):
        """Test: get_routine_execution_status raises ValueError for non-existent job"""
        service = MonitorService()
        with pytest.raises(ValueError, match="Job.*not found"):
            service.get_routine_execution_status("non_existent_job", "routine1")

    def test_get_routine_execution_status_pending_routine(self):
        """Test: get_routine_execution_status returns pending status for non-executed routine"""
        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("input")
        flow.add_routine(routine, "test_routine")

        FlowRegistry.get_instance().register(flow)

        runtime = Runtime()
        job_state = runtime.exec("test_flow")
        # Ensure job is in job_store for MonitorService to access
        job_store.add(job_state)
        runtime.wait_until_all_jobs_finished(timeout=5.0)

        service = MonitorService()
        status = service.get_routine_execution_status(job_state.job_id, "test_routine")

        assert status.routine_id == "test_routine"
        assert status.is_active is False
        # In new design, routines start as idle, not pending
        assert status.status == "idle"
        assert status.execution_count == 0
        assert status.error_count == 0
        
        # Cleanup
        runtime.shutdown(wait=True)
        job_store.remove(job_state.job_id)

    def test_get_routine_execution_status_executed_routine(self):
        """Test: get_routine_execution_status returns correct status for executed routine"""
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
        # Ensure job is in job_store for MonitorService to access
        job_store.add(job_state)
        runtime.wait_until_all_jobs_finished(timeout=5.0)

        service = MonitorService()
        status = service.get_routine_execution_status(job_state.job_id, "test_routine")

        assert status.routine_id == "test_routine"
        assert status.is_active is False
        # Status should be idle (new design), completed, or running depending on execution
        assert status.status in ["idle", "pending", "completed", "running"]
        
        # Cleanup
        runtime.shutdown(wait=True)
        job_store.remove(job_state.job_id)


class TestMonitorServiceQueueStatus:
    """Test MonitorService queue status methods"""

    def test_get_routine_queue_status_non_existent_job(self):
        """Test: get_routine_queue_status raises ValueError for non-existent job"""
        service = MonitorService()
        with pytest.raises(ValueError, match="Job.*not found"):
            service.get_routine_queue_status("non_existent_job", "routine1")

    def test_get_routine_queue_status_non_existent_routine(self):
        """Test: get_routine_queue_status raises ValueError for non-existent routine"""
        flow = Flow("test_flow")
        FlowRegistry.get_instance().register(flow)

        job_state = JobState("test_flow")
        job_store.add(job_state)

        service = MonitorService()
        with pytest.raises(ValueError, match="Routine.*not found"):
            service.get_routine_queue_status(job_state.job_id, "non_existent_routine")

    def test_get_routine_queue_status_empty_slots(self):
        """Test: get_routine_queue_status returns empty list for routine with no slots"""
        flow = Flow("test_flow")
        routine = Routine()
        flow.add_routine(routine, "test_routine")

        FlowRegistry.get_instance().register(flow)

        job_state = JobState("test_flow")
        job_store.add(job_state)

        service = MonitorService()
        queue_status = service.get_routine_queue_status(job_state.job_id, "test_routine")

        assert isinstance(queue_status, list)
        assert len(queue_status) == 0

    def test_get_routine_queue_status_with_slots(self):
        """Test: get_routine_queue_status returns status for all slots"""
        flow = Flow("test_flow")
        routine = Routine()
        slot1 = routine.define_slot("input1")
        slot2 = routine.define_slot("input2")
        flow.add_routine(routine, "test_routine")

        # Add some data to slots
        slot1.enqueue(data=1, emitted_from="test", emitted_at=datetime.now())
        slot2.enqueue(data=2, emitted_from="test", emitted_at=datetime.now())

        FlowRegistry.get_instance().register(flow)

        job_state = JobState("test_flow")
        job_store.add(job_state)

        service = MonitorService()
        queue_status = service.get_routine_queue_status(job_state.job_id, "test_routine")

        assert len(queue_status) == 2
        slot_names = {s.slot_name for s in queue_status}
        assert "input1" in slot_names
        assert "input2" in slot_names

        # Verify each slot has correct status
        for status in queue_status:
            assert status.routine_id == "test_routine"
            assert status.unconsumed_count >= 0
            assert status.total_count >= 0
            assert status.usage_percentage >= 0.0
            assert status.usage_percentage <= 1.0
            assert status.pressure_level in ["low", "medium", "high", "critical"]


class TestMonitorServiceRoutineInfo:
    """Test MonitorService routine info methods"""

    def test_get_routine_info_non_existent_flow(self):
        """Test: get_routine_info raises ValueError for non-existent flow"""
        service = MonitorService()
        with pytest.raises(ValueError, match="Flow.*not found"):
            service.get_routine_info("non_existent_flow", "routine1")

    def test_get_routine_info_non_existent_routine(self):
        """Test: get_routine_info raises ValueError for non-existent routine"""
        flow = Flow("test_flow")
        FlowRegistry.get_instance().register(flow)

        service = MonitorService()
        with pytest.raises(ValueError, match="Routine.*not found"):
            service.get_routine_info("test_flow", "non_existent_routine")

    def test_get_routine_info_basic(self):
        """Test: get_routine_info returns correct information"""
        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("input")
        routine.define_event("output", ["data"])
        routine.set_config(name="test", timeout=30)
        routine.set_activation_policy(immediate_policy())
        flow.add_routine(routine, "test_routine")

        FlowRegistry.get_instance().register(flow)

        service = MonitorService()
        info = service.get_routine_info("test_flow", "test_routine")

        assert info.routine_id == "test_routine"
        assert info.routine_type == "Routine"
        assert info.activation_policy["type"] == "immediate"
        assert info.config["name"] == "test"
        assert info.config["timeout"] == 30
        assert "input" in info.slots
        assert "output" in info.events


class TestMonitorServiceCompleteData:
    """Test MonitorService complete monitoring data methods"""

    def test_get_routine_monitoring_data(self):
        """Test: get_routine_monitoring_data returns complete data"""
        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("input")
        routine.define_event("output", ["data"])
        routine.set_activation_policy(immediate_policy())
        flow.add_routine(routine, "test_routine")

        FlowRegistry.get_instance().register(flow)

        job_state = JobState("test_flow")
        job_store.add(job_state)

        service = MonitorService()
        data = service.get_routine_monitoring_data(job_state.job_id, "test_routine")

        assert data.routine_id == "test_routine"
        assert data.execution_status is not None
        assert data.queue_status is not None
        assert data.info is not None

        # Verify execution status
        assert data.execution_status.routine_id == "test_routine"
        assert isinstance(data.execution_status.is_active, bool)

        # Verify queue status
        assert isinstance(data.queue_status, list)

        # Verify info
        assert data.info.routine_id == "test_routine"
        assert data.info.activation_policy is not None
        assert data.info.config is not None

    def test_get_job_monitoring_data(self):
        """Test: get_job_monitoring_data returns complete data for all routines"""
        flow = Flow("test_flow")
        routine1 = Routine()
        routine1.define_slot("input")
        routine2 = Routine()
        routine2.define_slot("input")
        flow.add_routine(routine1, "routine1")
        flow.add_routine(routine2, "routine2")

        FlowRegistry.get_instance().register(flow)

        job_state = JobState("test_flow")
        job_store.add(job_state)

        try:
            service = MonitorService()
            data = service.get_job_monitoring_data(job_state.job_id)

            assert data.job_id == job_state.job_id
            assert data.flow_id == "test_flow"
            assert len(data.routines) == 2
            assert "routine1" in data.routines
            assert "routine2" in data.routines

            # Verify each routine has complete data
            for routine_id, routine_data in data.routines.items():
                assert routine_data.routine_id == routine_id
                assert routine_data.execution_status is not None
                assert routine_data.queue_status is not None
                assert routine_data.info is not None
        finally:
            # Cleanup
            job_store.remove(job_state.job_id)

    def test_get_all_routines_status(self):
        """Test: get_all_routines_status returns status for all routines"""
        flow = Flow("test_flow")
        routine1 = Routine()
        routine2 = Routine()
        flow.add_routine(routine1, "routine1")
        flow.add_routine(routine2, "routine2")

        FlowRegistry.get_instance().register(flow)

        job_state = JobState("test_flow")
        job_store.add(job_state)

        try:
            service = MonitorService()
            statuses = service.get_all_routines_status(job_state.job_id)

            assert len(statuses) == 2
            assert "routine1" in statuses
            assert "routine2" in statuses

            for routine_id, status in statuses.items():
                assert status.routine_id == routine_id
                assert isinstance(status.is_active, bool)
                # Status can be any valid routine status (including "idle" in new design)
                assert status.status in ["pending", "running", "completed", "failed", "error_continued", "skipped", "idle"]
        finally:
            # Cleanup
            job_store.remove(job_state.job_id)

    def test_get_all_queues_status(self):
        """Test: get_all_queues_status returns queue status for all routines"""
        flow = Flow("test_flow")
        routine1 = Routine()
        routine1.define_slot("input1")
        routine2 = Routine()
        routine2.define_slot("input2")
        flow.add_routine(routine1, "routine1")
        flow.add_routine(routine2, "routine2")

        FlowRegistry.get_instance().register(flow)

        job_state = JobState("test_flow")
        job_store.add(job_state)

        service = MonitorService()
        queues = service.get_all_queues_status(job_state.job_id)

        assert len(queues) == 2
        assert "routine1" in queues
        assert "routine2" in queues
        assert len(queues["routine1"]) == 1
        assert len(queues["routine2"]) == 1
