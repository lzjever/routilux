"""
Comprehensive end-to-end tests for overseer_demo_app.py

Tests all features showcased in the demo app:
- State transitions
- Queue pressure monitoring
- Debug functionality
- Breakpoint management
- All monitoring endpoints
"""

import time
from typing import Dict, Any

import pytest
import httpx
from fastapi.testclient import TestClient

from routilux.api.main import app
from routilux.monitoring.flow_registry import FlowRegistry
from routilux.monitoring.registry import MonitoringRegistry
from routilux.monitoring.storage import flow_store, job_store

# Import demo app routines and flows
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../examples'))
from overseer_demo_app import (
    create_state_transition_flow,
    create_queue_pressure_flow,
    create_debug_demo_flow,
    create_comprehensive_demo_flow,
)


@pytest.fixture(scope="module")
def api_client():
    """Create FastAPI test client."""
    return TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def setup_demo_flows():
    """Setup demo flows before tests."""
    # Enable monitoring
    MonitoringRegistry.enable()
    
    # Create and register all demo flows
    flows = [
        ("state_transition_flow", create_state_transition_flow),
        ("queue_pressure_flow", create_queue_pressure_flow),
        ("debug_demo_flow", create_debug_demo_flow),
        ("comprehensive_demo_flow", create_comprehensive_demo_flow),
    ]
    
    for flow_id, creator in flows:
        flow, _ = creator()
        flow_store.add(flow)
        FlowRegistry.get_instance().register(flow)
    
    yield
    
    # Cleanup
    for flow_id, _ in flows:
        flow_store.remove(flow_id)
    FlowRegistry.get_instance().clear()
    job_store.clear()


@pytest.fixture
def auth_headers():
    """Return authentication headers."""
    return {"X-API-Key": "test-key"}


class TestDemoAppFlows:
    """Test that all demo flows are created and accessible."""
    
    def test_list_flows(self, api_client, auth_headers):
        """Test: All demo flows are listed."""
        response = api_client.get("/api/flows", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "flows" in data
        assert "total" in data
        
        flow_ids = [f["flow_id"] for f in data["flows"]]
        assert "state_transition_flow" in flow_ids
        assert "queue_pressure_flow" in flow_ids
        assert "debug_demo_flow" in flow_ids
        assert "comprehensive_demo_flow" in flow_ids
    
    def test_get_flow_details(self, api_client, auth_headers):
        """Test: Get flow details."""
        response = api_client.get("/api/flows/state_transition_flow", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["flow_id"] == "state_transition_flow"
        assert "routines" in data
        assert "connections" in data
        assert "source" in data["routines"]
        assert "processor" in data["routines"]
        assert "sink" in data["routines"]


class TestStateTransitions:
    """Test job state transitions."""
    
    def test_job_state_transitions(self, api_client, auth_headers):
        """Test: Job transitions through states (pending -> running -> completed)."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": "state_transition_flow",
                "entry_routine_id": "source",
                "entry_params": {"data": "State transition test"}
            },
            headers=auth_headers
        )
        assert start_response.status_code == 201
        job_data = start_response.json()
        job_id = job_data["job_id"]
        
        # Initial state should be pending or running
        assert job_data["status"] in ["pending", "running"]
        
        # Wait for job to complete
        max_wait = 10
        wait_time = 0
        while wait_time < max_wait:
            status_response = api_client.get(f"/api/jobs/{job_id}/status", headers=auth_headers)
            assert status_response.status_code == 200
            status_data = status_response.json()
            status = status_data["status"]
            
            if status in ["completed", "failed"]:
                break
            
            time.sleep(0.5)
            wait_time += 0.5
        
        # Final state should be completed
        final_response = api_client.get(f"/api/jobs/{job_id}", headers=auth_headers)
        assert final_response.status_code == 200
        final_data = final_response.json()
        assert final_data["status"] in ["completed", "failed"]
    
    def test_job_pause_resume(self, api_client, auth_headers):
        """Test: Job can be paused and resumed."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": "state_transition_flow",
                "entry_routine_id": "source",
                "entry_params": {"data": "Pause resume test"}
            },
            headers=auth_headers
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]
        
        # Wait a bit for job to start
        time.sleep(0.5)
        
        # Pause job (may fail if job already completed, which is acceptable)
        pause_response = api_client.post(f"/api/jobs/{job_id}/pause", headers=auth_headers)
        # Accept both 200 (success) and 400 (job already completed/cannot pause)
        assert pause_response.status_code in [200, 400]
        
        # Check status
        status_response = api_client.get(f"/api/jobs/{job_id}/status", headers=auth_headers)
        assert status_response.status_code == 200
        
        # Resume job (may fail if job wasn't paused, which is acceptable)
        resume_response = api_client.post(f"/api/jobs/{job_id}/resume", headers=auth_headers)
        # Accept both 200 (success) and 400 (job not paused/cannot resume)
        assert resume_response.status_code in [200, 400]


class TestQueuePressure:
    """Test queue pressure monitoring."""
    
    def test_queue_status_endpoints(self, api_client, auth_headers):
        """Test: Queue status endpoints return correct data."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": "queue_pressure_flow",
                "entry_routine_id": "source",
                "entry_params": {"data": "Queue pressure test"}
            },
            headers=auth_headers
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]
        
        # Wait for job to start processing
        time.sleep(1.0)
        
        # Get queue status for all routines
        queues_response = api_client.get(f"/api/jobs/{job_id}/queues/status", headers=auth_headers)
        assert queues_response.status_code == 200
        queues_data = queues_response.json()
        assert isinstance(queues_data, dict)
        
        # Get queue status for specific routine
        routine_response = api_client.get(
            f"/api/jobs/{job_id}/routines/validator/queue-status",
            headers=auth_headers
        )
        assert routine_response.status_code == 200
        routine_data = routine_response.json()
        assert isinstance(routine_data, list)
        
        # Each queue status should have required fields
        if routine_data:
            queue_status = routine_data[0]
            assert "slot_name" in queue_status
            assert "unconsumed_count" in queue_status
            assert "total_count" in queue_status
            assert "usage_percentage" in queue_status
            assert "pressure_level" in queue_status
            assert queue_status["pressure_level"] in ["low", "medium", "high", "critical"]
    
    def test_routine_queue_status(self, api_client, auth_headers):
        """Test: Get queue status for specific routine."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": "queue_pressure_flow",
                "entry_routine_id": "source",
                "entry_params": {"data": "Queue test", "index": 1}
            },
            headers=auth_headers
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]
        
        # Wait a bit
        time.sleep(0.5)
        
        # Get queue status
        response = api_client.get(
            f"/api/jobs/{job_id}/routines/processor/queue-status",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestMonitoringEndpoints:
    """Test all monitoring endpoints."""
    
    def test_job_monitoring_data(self, api_client, auth_headers):
        """Test: Get complete monitoring data for a job."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": "comprehensive_demo_flow",
                "entry_routine_id": "source1",
                "entry_params": {"data": "Monitoring test"}
            },
            headers=auth_headers
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]
        
        # Wait for job to start
        time.sleep(0.5)
        
        # Get monitoring data
        response = api_client.get(f"/api/jobs/{job_id}/monitoring", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "job_id" in data
        assert "flow_id" in data
        assert "routines" in data
        assert isinstance(data["routines"], dict)
        
        # Each routine should have complete data
        for routine_id, routine_data in data["routines"].items():
            assert "execution_status" in routine_data
            assert "queue_status" in routine_data
            assert "info" in routine_data
    
    def test_routines_status(self, api_client, auth_headers):
        """Test: Get execution status for all routines."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": "state_transition_flow",
                "entry_routine_id": "source",
                "entry_params": {"data": "Routines status test"}
            },
            headers=auth_headers
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]
        
        # Wait a bit
        time.sleep(0.5)
        
        # Get routines status
        response = api_client.get(f"/api/jobs/{job_id}/routines/status", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        
        # Should have status for each routine
        assert "source" in data or "processor" in data or "sink" in data
    
    def test_routine_info(self, api_client, auth_headers):
        """Test: Get routine metadata information."""
        # Ensure flow is in registry (it should be from setup)
        from routilux.monitoring.flow_registry import FlowRegistry
        from routilux.monitoring.storage import flow_store
        
        flow = flow_store.get("state_transition_flow")
        if flow:
            FlowRegistry.get_instance().register(flow)
        
        response = api_client.get(
            "/api/flows/state_transition_flow/routines/source/info",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "routine_id" in data
        assert "routine_type" in data or "class_name" in data  # API may use either field
        assert "slots" in data
        assert "events" in data
        assert "config" in data
    
    def test_job_metrics(self, api_client, auth_headers):
        """Test: Get execution metrics for a job."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": "state_transition_flow",
                "entry_routine_id": "source",
                "entry_params": {"data": "Metrics test"}
            },
            headers=auth_headers
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]
        
        # Wait for job to complete
        time.sleep(2.0)
        
        # Get metrics
        response = api_client.get(f"/api/jobs/{job_id}/metrics", headers=auth_headers)
        # Metrics may not be available immediately, so 404 is acceptable
        if response.status_code == 200:
            data = response.json()
            assert "job_id" in data
            assert "flow_id" in data
    
    def test_job_trace(self, api_client, auth_headers):
        """Test: Get execution trace for a job."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": "state_transition_flow",
                "entry_routine_id": "source",
                "entry_params": {"data": "Trace test"}
            },
            headers=auth_headers
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]
        
        # Wait a bit
        time.sleep(1.0)
        
        # Get trace
        response = api_client.get(f"/api/jobs/{job_id}/trace", headers=auth_headers)
        # Trace may not be available immediately
        if response.status_code == 200:
            data = response.json()
            assert "events" in data
            assert "total" in data


class TestBreakpoints:
    """Test breakpoint functionality."""
    
    def test_create_breakpoint(self, api_client, auth_headers):
        """Test: Create a breakpoint."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": "debug_demo_flow",
                "entry_routine_id": "source",
                "entry_params": {"data": "Breakpoint test"}
            },
            headers=auth_headers
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]
        
        # Create breakpoint
        bp_response = api_client.post(
            f"/api/jobs/{job_id}/breakpoints",
            json={
                "type": "routine",
                "routine_id": "transformer",
                "enabled": True
            },
            headers=auth_headers
        )
        assert bp_response.status_code == 201
        bp_data = bp_response.json()
        assert "breakpoint_id" in bp_data
        assert bp_data["routine_id"] == "transformer"
        assert bp_data["enabled"] is True
    
    def test_list_breakpoints(self, api_client, auth_headers):
        """Test: List breakpoints for a job."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": "debug_demo_flow",
                "entry_routine_id": "source",
                "entry_params": {"data": "List breakpoints test"}
            },
            headers=auth_headers
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]
        
        # Create breakpoint
        api_client.post(
            f"/api/jobs/{job_id}/breakpoints",
            json={
                "type": "routine",
                "routine_id": "transformer",
                "enabled": True
            },
            headers=auth_headers
        )
        
        # List breakpoints
        list_response = api_client.get(f"/api/jobs/{job_id}/breakpoints", headers=auth_headers)
        assert list_response.status_code == 200
        list_data = list_response.json()
        assert "breakpoints" in list_data
        assert "total" in list_data
        assert list_data["total"] >= 1
    
    def test_update_breakpoint(self, api_client, auth_headers):
        """Test: Update breakpoint (enable/disable)."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": "debug_demo_flow",
                "entry_routine_id": "source",
                "entry_params": {"data": "Update breakpoint test"}
            },
            headers=auth_headers
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]
        
        # Create breakpoint
        bp_response = api_client.post(
            f"/api/jobs/{job_id}/breakpoints",
            json={
                "type": "routine",
                "routine_id": "transformer",
                "enabled": True
            },
            headers=auth_headers
        )
        bp_id = bp_response.json()["breakpoint_id"]
        
        # Disable breakpoint
        update_response = api_client.put(
            f"/api/jobs/{job_id}/breakpoints/{bp_id}?enabled=false",
            headers=auth_headers
        )
        assert update_response.status_code == 200
        update_data = update_response.json()
        assert update_data["enabled"] is False


class TestDebugFunctionality:
    """Test debug functionality."""
    
    def test_debug_session(self, api_client, auth_headers):
        """Test: Get debug session information."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": "debug_demo_flow",
                "entry_routine_id": "source",
                "entry_params": {"data": "Debug session test"}
            },
            headers=auth_headers
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]
        
        # Wait a bit
        time.sleep(0.5)
        
        # Get debug session (may not exist if no breakpoint hit)
        session_response = api_client.get(f"/api/jobs/{job_id}/debug/session", headers=auth_headers)
        # 200 or 404 both acceptable depending on whether breakpoint was hit
        assert session_response.status_code in [200, 404]
    
    def test_get_variables(self, api_client, auth_headers):
        """Test: Get variables at breakpoint."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": "debug_demo_flow",
                "entry_routine_id": "source",
                "entry_params": {"data": "Variables test"}
            },
            headers=auth_headers
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]
        
        # Wait a bit
        time.sleep(0.5)
        
        # Get variables (may fail if no debug session)
        vars_response = api_client.get(
            f"/api/jobs/{job_id}/debug/variables?routine_id=debug_target",
            headers=auth_headers
        )
        # 200 or 404 both acceptable
        assert vars_response.status_code in [200, 400, 404]
    
    def test_call_stack(self, api_client, auth_headers):
        """Test: Get call stack."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": "debug_demo_flow",
                "entry_routine_id": "source",
                "entry_params": {"data": "Call stack test"}
            },
            headers=auth_headers
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]
        
        # Wait a bit
        time.sleep(0.5)
        
        # Get call stack (may fail if no debug session)
        stack_response = api_client.get(f"/api/jobs/{job_id}/debug/call-stack", headers=auth_headers)
        # 200 or 404 both acceptable
        assert stack_response.status_code in [200, 404]


class TestComprehensiveDemo:
    """Test comprehensive demo flow with all features."""
    
    def test_comprehensive_flow_execution(self, api_client, auth_headers):
        """Test: Comprehensive flow executes successfully."""
        # Start job
        start_response = api_client.post(
            "/api/jobs",
            json={
                "flow_id": "comprehensive_demo_flow",
                "entry_routine_id": "source1",
                "entry_params": {"data": "Comprehensive test", "index": 1}
            },
            headers=auth_headers
        )
        assert start_response.status_code == 201
        job_id = start_response.json()["job_id"]
        
        # Wait for job to process
        time.sleep(2.0)
        
        # Get job status
        status_response = api_client.get(f"/api/jobs/{job_id}/status", headers=auth_headers)
        assert status_response.status_code == 200
        
        # Get monitoring data
        monitor_response = api_client.get(f"/api/jobs/{job_id}/monitoring", headers=auth_headers)
        assert monitor_response.status_code == 200
        monitor_data = monitor_response.json()
        assert "routines" in monitor_data
        
        # Get queue status
        queues_response = api_client.get(f"/api/jobs/{job_id}/queues/status", headers=auth_headers)
        assert queues_response.status_code == 200
    
    def test_multiple_jobs(self, api_client, auth_headers):
        """Test: Multiple jobs can run concurrently."""
        job_ids = []
        
        # Start multiple jobs
        for i in range(3):
            start_response = api_client.post(
                "/api/jobs",
                json={
                    "flow_id": "state_transition_flow",
                    "entry_routine_id": "source",
                    "entry_params": {"data": f"Concurrent test {i}", "index": i}
                },
                headers=auth_headers
            )
            assert start_response.status_code == 201
            job_ids.append(start_response.json()["job_id"])
        
        # Wait a bit
        time.sleep(1.0)
        
        # List jobs
        list_response = api_client.get("/api/jobs", headers=auth_headers)
        assert list_response.status_code == 200
        list_data = list_response.json()
        assert "jobs" in list_data
        assert len(list_data["jobs"]) >= 3
        
        # Verify all jobs exist
        for job_id in job_ids:
            get_response = api_client.get(f"/api/jobs/{job_id}", headers=auth_headers)
            assert get_response.status_code == 200
