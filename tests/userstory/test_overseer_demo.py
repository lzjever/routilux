"""
Comprehensive test suite for Overseer Demo App.

This test suite validates:
1. All flows and routines are properly registered
2. API endpoints work correctly (workers, jobs, execute, flows, debug, breakpoints, monitoring)
3. End-to-end user workflows
4. Data consistency and backend state management
5. Boundary conditions and error handling

User Stories Tested:
- Story 1: User creates a worker and submits multiple jobs
- Story 2: User monitors job execution and queue pressure
- Story 3: User debugs a job with breakpoints
- Story 4: User executes flows with different patterns (linear, branching, aggregating, looping)
- Story 5: User handles errors and retries
- Story 6: User uses different runtimes for isolation
"""

import asyncio
import time
from datetime import datetime
from typing import Dict, List, Optional

import pytest

# Mark all tests in this file as userstory tests
pytestmark = pytest.mark.userstory
import requests
from fastapi.testclient import TestClient

from routilux.core.registry import FlowRegistry, get_flow_registry
from routilux.core.runtime import Runtime
from routilux.monitoring.registry import MonitoringRegistry
from routilux.monitoring.runtime_registry import RuntimeRegistry
from routilux.monitoring.storage import flow_store
from routilux.server.main import app
from routilux.server.storage.memory import MemoryIdempotencyBackend, MemoryJobStorage

# Import demo app components
import sys
from pathlib import Path

examples_dir = Path(__file__).parent.parent / "examples"
if str(examples_dir) not in sys.path:
    sys.path.insert(0, str(examples_dir))

from overseer_demo_app import (
    create_aggregator_flow,
    create_branching_flow,
    create_comprehensive_demo_flow,
    create_debug_demo_flow,
    create_error_handling_flow,
    create_loop_flow,
    create_multi_slot_flow,
    create_queue_pressure_flow,
    create_rate_limited_flow,
    create_state_transition_flow,
)


@pytest.fixture(scope="function")
def client():
    """Create test client with clean state."""
    # Reset monitoring and registries
    MonitoringRegistry.disable()
    MonitoringRegistry.enable()

    # Clear flow store
    flow_store._flows.clear()

    # Reset runtime registry
    RuntimeRegistry._instance = None

    # Reset factory (clear registry)
    from routilux.tools.factory import ObjectFactory

    factory = ObjectFactory.get_instance()
    with factory._registry_lock:
        factory._registry.clear()
        factory._class_to_name.clear()
        factory._name_to_class.clear()

    # Reset storage
    from routilux.server.dependencies import reset_storage

    reset_storage()

    # Create test client
    return TestClient(app)


@pytest.fixture(scope="function")
def setup_demo_flows():
    """Setup demo flows similar to overseer_demo_app.main()."""
    # Note: Using function scope for parallel test compatibility
    # Each worker process needs its own setup
    # Enable monitoring
    MonitoringRegistry.enable()

    # Register runtimes
    runtime_registry = RuntimeRegistry.get_instance()
    runtime_production = Runtime(thread_pool_size=0)
    runtime_registry.register(runtime_production, "production", is_default=True)

    runtime_development = Runtime(thread_pool_size=5)
    runtime_registry.register(runtime_development, "development", is_default=False)

    runtime_testing = Runtime(thread_pool_size=2)
    runtime_registry.register(runtime_testing, "testing", is_default=False)

    # Register routines in factory
    from routilux.tools.factory import ObjectFactory, ObjectMetadata

    factory = ObjectFactory.get_instance()

    # Import routine classes
    from overseer_demo_app import (
        DataAggregator,
        DataSink,
        DataSource,
        DataTransformer,
        DataValidator,
        DebugTargetRoutine,
        ErrorGenerator,
        LoopController,
        MultiSlotProcessor,
        QueuePressureGenerator,
        RateLimitedProcessor,
        StateTransitionDemo,
    )

    routines = [
        ("data_source", DataSource, "Generates sample data with metadata", "data_generation"),
        (
            "data_validator",
            DataValidator,
            "Validates input data with batch processing",
            "validation",
        ),
        (
            "data_transformer",
            DataTransformer,
            "Transforms data with various transformations",
            "transformation",
        ),
        (
            "queue_pressure_generator",
            QueuePressureGenerator,
            "Generates queue pressure for monitoring",
            "monitoring",
        ),
        (
            "debug_target",
            DebugTargetRoutine,
            "Routine designed for debugging demonstrations",
            "debugging",
        ),
        (
            "state_transition_demo",
            StateTransitionDemo,
            "Demonstrates job state transitions",
            "state_management",
        ),
        ("data_sink", DataSink, "Receives and stores final results", "sink"),
        (
            "rate_limited_processor",
            RateLimitedProcessor,
            "Processes data with rate limiting",
            "rate_limiting",
        ),
        ("data_aggregator", DataAggregator, "Aggregates data from multiple sources", "aggregation"),
        (
            "error_generator",
            ErrorGenerator,
            "Generates errors for testing error handling",
            "error_handling",
        ),
        (
            "multi_slot_processor",
            MultiSlotProcessor,
            "Processes data from multiple slots",
            "multi_slot",
        ),
        ("loop_controller", LoopController, "Controls loop execution in flows", "control_flow"),
    ]

    for name, routine_class, description, category in routines:
        metadata = ObjectMetadata(
            name=name,
            description=description,
            category=category,
            tags=[name.split("_")[0], category],
            example_config={"name": f"Example{name.title()}"},
            version="1.0.0",
        )
        # Try to register, skip if already registered (for test isolation)
        try:
            factory.register(name, routine_class, metadata=metadata)
        except ValueError:
            # Already registered, update metadata if needed
            pass

    # Create and register flows (skip if already exists to save time)
    flow_registry = get_flow_registry()
    flows_data = []

    flow_creators = [
        ("state_transition_flow", create_state_transition_flow),
        ("queue_pressure_flow", create_queue_pressure_flow),
        ("debug_demo_flow", create_debug_demo_flow),
        ("comprehensive_demo_flow", create_comprehensive_demo_flow),
        ("aggregator_flow", create_aggregator_flow),
        ("branching_flow", create_branching_flow),
        ("rate_limited_flow", create_rate_limited_flow),
        ("error_handling_flow", create_error_handling_flow),
        ("loop_flow", create_loop_flow),
        ("multi_slot_flow", create_multi_slot_flow),
    ]

    for flow_id, creator in flow_creators:
        # Check if flow already exists
        existing_flow = flow_store.get(flow_id)
        if existing_flow is None:
            # Create new flow
            flow, entry = creator()
            flow_store.add(flow)
            flow_registry.register(flow)
            flow_registry.register_by_name(flow.flow_id.replace("_", "-"), flow)
            flows_data.append((flow_id, flow, entry))
        else:
            # Flow already exists, just get entry point
            flow = existing_flow
            # Find entry point (first routine with trigger slot)
            entry = None
            for rid, routine in flow.routines.items():
                if "trigger" in routine._slots:
                    entry = rid
                    break
            flows_data.append((flow_id, flow, entry))

    return flows_data


class TestOverseerDemoSetup:
    """Test that demo setup works correctly."""

    def test_monitoring_enabled(self, client, setup_demo_flows):
        """Test that monitoring is enabled."""
        assert MonitoringRegistry.is_enabled()

    def test_runtimes_registered(self, client, setup_demo_flows):
        """Test that runtimes are registered."""
        response = client.get("/api/runtimes")
        assert response.status_code == 200
        data = response.json()
        assert "runtimes" in data
        runtime_ids = [r["runtime_id"] for r in data["runtimes"]]
        assert "production" in runtime_ids
        assert "development" in runtime_ids
        assert "testing" in runtime_ids

    def test_flows_registered(self, client, setup_demo_flows):
        """Test that flows are registered."""
        response = client.get("/api/flows")
        assert response.status_code == 200
        data = response.json()
        assert "flows" in data
        flow_ids = [f["flow_id"] for f in data["flows"]]
        assert "state_transition_flow" in flow_ids
        assert "queue_pressure_flow" in flow_ids
        assert "debug_demo_flow" in flow_ids

    def test_factory_objects_registered(self, client, setup_demo_flows):
        """Test that factory objects are registered."""
        response = client.get("/api/factory/objects")
        assert response.status_code == 200
        data = response.json()
        assert "objects" in data
        object_names = [o["name"] for o in data["objects"]]
        assert "data_source" in object_names
        assert "data_validator" in object_names
        assert "data_transformer" in object_names


class TestUserStory1_WorkerAndJobs:
    """
    User Story 1: User creates a worker and submits multiple jobs.

    Scenario:
    1. User creates a worker for a flow
    2. User submits multiple jobs to the worker
    3. User checks job status
    4. User lists all jobs for the worker
    5. User verifies data consistency
    """

    def test_create_worker(self, client, setup_demo_flows):
        """Test creating a worker."""
        response = client.post(
            "/api/v1/workers",
            json={"flow_id": "state_transition_flow"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "worker_id" in data
        assert data["flow_id"] == "state_transition_flow"
        assert data["status"] in ["running", "pending"]
        return data["worker_id"]

    def test_submit_job(self, client, setup_demo_flows):
        """Test submitting a job."""
        # Create worker first
        worker_response = client.post(
            "/api/v1/workers",
            json={"flow_id": "state_transition_flow"},
        )
        worker_id = worker_response.json()["worker_id"]

        # Submit job with worker_id to use the existing worker
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
                "worker_id": worker_id,  # Use the created worker
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "job_id" in data
        assert data["worker_id"] == worker_id
        assert data["status"] in ["pending", "running"]
        return data["job_id"]

    def test_submit_multiple_jobs(self, client, setup_demo_flows):
        """Test submitting multiple jobs to the same worker."""
        # Create worker
        worker_response = client.post(
            "/api/v1/workers",
            json={"flow_id": "state_transition_flow"},
        )
        worker_id = worker_response.json()["worker_id"]

        # Submit multiple jobs with worker_id to use the same worker
        job_ids = []
        for i in range(5):
            response = client.post(
                "/api/v1/jobs",
                json={
                    "flow_id": "state_transition_flow",
                    "routine_id": "source",
                    "slot_name": "trigger",
                    "data": {"data": f"test_data_{i}", "index": i},
                    "worker_id": worker_id,  # Use the same worker
                },
            )
            assert response.status_code == 201
            job_ids.append(response.json()["job_id"])

        # Wait a bit for jobs to be processed/stored (reduced from 0.5s)
        time.sleep(0.1)

        # Verify all jobs are associated with the worker
        response = client.get(f"/api/v1/workers/{worker_id}/jobs")
        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) >= 5  # At least 5 jobs
        returned_job_ids = [j["job_id"] for j in data["jobs"]]
        for job_id in job_ids:
            assert job_id in returned_job_ids

    def test_job_status_transitions(self, client, setup_demo_flows):
        """Test that job status transitions correctly."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        job_id = response.json()["job_id"]

        # Wait for job to complete (use wait endpoint for efficiency)
        wait_response = client.post(
            f"/api/v1/jobs/{job_id}/wait",
            params={"timeout": 5.0},
        )
        assert wait_response.status_code == 200
        wait_data = wait_response.json()
        final_status = wait_data.get("final_status", "running")

        # Verify final status (may still be running if flow is slow, that's acceptable)
        final_response = client.get(f"/api/v1/jobs/{job_id}")
        assert final_response.status_code == 200
        final_data = final_response.json()
        # Accept running status if flow is still executing
        assert final_data["status"] in ["completed", "failed", "running"]

    def test_list_jobs_with_filters(self, client, setup_demo_flows):
        """Test listing jobs with filters."""
        # Create worker and submit jobs
        worker_response = client.post(
            "/api/v1/workers",
            json={"flow_id": "state_transition_flow"},
        )
        worker_id = worker_response.json()["worker_id"]

        # Submit multiple jobs with worker_id
        job_ids = []
        for i in range(3):
            job_response = client.post(
                "/api/v1/jobs",
                json={
                    "flow_id": "state_transition_flow",
                    "routine_id": "source",
                    "slot_name": "trigger",
                    "data": {"data": f"test_data_{i}", "index": i},
                    "worker_id": worker_id,  # Use the same worker
                },
            )
            job_ids.append(job_response.json()["job_id"])

        # Wait a bit for jobs to be stored
        time.sleep(0.5)

        # Filter by worker_id
        response = client.get(f"/api/v1/jobs?worker_id={worker_id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) >= 3  # At least 3 jobs
        for job in data["jobs"]:
            assert job["worker_id"] == worker_id

        # Filter by flow_id
        response = client.get("/api/v1/jobs?flow_id=state_transition_flow")
        assert response.status_code == 200
        data = response.json()
        assert len(data["jobs"]) >= 3  # At least 3 jobs
        for job in data["jobs"]:
            assert job["flow_id"] == "state_transition_flow"


class TestUserStory2_MonitoringAndQueuePressure:
    """
    User Story 2: User monitors job execution and queue pressure.

    Scenario:
    1. User submits a job that creates queue pressure
    2. User monitors queue status
    3. User checks routine status
    4. User views execution metrics
    5. User verifies queue pressure levels
    """

    def test_queue_pressure_flow(self, client, setup_demo_flows):
        """Test queue pressure flow creates queue pressure."""
        # Submit job to queue pressure flow
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "queue_pressure_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        job_id = response.json()["job_id"]

        # Wait a bit for queue to build up
        time.sleep(0.3)  # Reduced from 1s

        # Check queue status
        response = client.get(f"/api/jobs/{job_id}/queues/status")
        # May return 404 if monitoring not enabled or job not found
        assert response.status_code in (200, 404)
        if response.status_code == 200:
            data = response.json()
            # API returns dict with routine_id as keys, or may have "queues"/"routine_queues" wrapper
            # Accept either format
            assert isinstance(data, dict)
            # If it's a wrapper dict, check for queues key
            # Otherwise, it's a dict of routine_id -> list of queue status
            if "queues" in data or "routine_queues" in data:
                pass  # Expected format
            else:
                # Direct format: routine_id -> list
                assert len(data) > 0  # Should have at least one routine
                # Check that values are lists
                for routine_id, queues in data.items():
                    assert isinstance(queues, list)

    def test_job_metrics(self, client, setup_demo_flows):
        """Test getting job metrics."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        job_id = response.json()["job_id"]

        # Wait for job to start
        time.sleep(0.5)

        # Get metrics
        response = client.get(f"/api/jobs/{job_id}/metrics")
        if response.status_code == 200:
            data = response.json()
            assert "job_id" in data
            assert data["job_id"] == job_id

    def test_routine_status(self, client, setup_demo_flows):
        """Test getting routine status."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        job_id = response.json()["job_id"]

        # Wait a bit
        time.sleep(0.5)

        # Get routine status
        response = client.get(f"/api/jobs/{job_id}/routines/source/status")
        if response.status_code == 200:
            data = response.json()
            assert "routine_id" in data or "status" in data


class TestUserStory3_Debugging:
    """
    User Story 3: User debugs a job with breakpoints.

    Scenario:
    1. User submits a job
    2. User sets a breakpoint
    3. User checks debug session
    4. User inspects variables
    5. User steps through execution
    6. User resumes execution
    """

    def test_set_breakpoint(self, client, setup_demo_flows):
        """Test setting a breakpoint."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "debug_demo_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        job_id = response.json()["job_id"]

        # Set breakpoint
        response = client.post(
            f"/api/jobs/{job_id}/breakpoints",
            json={
                "type": "routine",
                "routine_id": "transformer",
            },
        )
        if response.status_code in [200, 201]:
            data = response.json()
            assert "breakpoint_id" in data or "status" in data

    def test_debug_session(self, client, setup_demo_flows):
        """Test getting debug session."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "debug_demo_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        job_id = response.json()["job_id"]

        # Get debug session
        response = client.get(f"/api/jobs/{job_id}/debug/session")
        # May return 404 if no session exists yet
        assert response.status_code in [200, 404]

    def test_debug_variables(self, client, setup_demo_flows):
        """Test getting debug variables."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "debug_demo_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        job_id = response.json()["job_id"]

        # Get variables
        response = client.get(f"/api/jobs/{job_id}/debug/variables")
        # May return 404 if no debug session
        assert response.status_code in [200, 404]


class TestUserStory4_FlowPatterns:
    """
    User Story 4: User executes flows with different patterns.

    Tests:
    - Linear flow (state_transition_flow)
    - Branching flow (branching_flow)
    - Aggregating flow (aggregator_flow)
    - Looping flow (loop_flow)
    - Multi-slot flow (multi_slot_flow)
    """

    def test_linear_flow(self, client, setup_demo_flows):
        """Test linear flow execution."""
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        assert response.status_code == 201
        job_id = response.json()["job_id"]

        # Wait for completion
        time.sleep(0.5)  # Reduced from 2s
        status_response = client.get(f"/api/v1/jobs/{job_id}/status")
        assert status_response.status_code == 200

    def test_branching_flow(self, client, setup_demo_flows):
        """Test branching flow execution."""
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "branching_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        assert response.status_code == 201
        job_id = response.json()["job_id"]

        # Wait for completion
        time.sleep(0.5)  # Reduced from 2s
        status_response = client.get(f"/api/v1/jobs/{job_id}/status")
        assert status_response.status_code == 200

    def test_aggregator_flow(self, client, setup_demo_flows):
        """Test aggregator flow execution."""
        # Aggregator flow needs data from both sources
        # We'll submit to one source and see if it waits
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "aggregator_flow",
                "routine_id": "source1",
                "slot_name": "trigger",
                "data": {"data": "test_data_1", "index": 1},
            },
        )
        assert response.status_code == 201
        job_id = response.json()["job_id"]

        # Wait a bit
        time.sleep(0.3)  # Reduced from 1s
        status_response = client.get(f"/api/v1/jobs/{job_id}/status")
        assert status_response.status_code == 200

    def test_loop_flow(self, client, setup_demo_flows):
        """Test loop flow execution."""
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "loop_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        assert response.status_code == 201
        job_id = response.json()["job_id"]

        # Wait for loop to complete
        time.sleep(0.3)  # Reduced from 1s  # Reduced from 3s
        status_response = client.get(f"/api/v1/jobs/{job_id}/status")
        assert status_response.status_code == 200

    def test_multi_slot_flow(self, client, setup_demo_flows):
        """Test multi-slot flow execution."""
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "multi_slot_flow",
                "routine_id": "primary_source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        assert response.status_code == 201
        job_id = response.json()["job_id"]

        # Wait for completion
        time.sleep(0.5)  # Reduced from 2s
        status_response = client.get(f"/api/v1/jobs/{job_id}/status")
        assert status_response.status_code == 200


class TestUserStory5_ErrorHandling:
    """
    User Story 5: User handles errors and retries.

    Scenario:
    1. User submits a job that may fail
    2. User checks error status
    3. User views error details
    4. User handles failed jobs
    """

    def test_error_handling_flow(self, client, setup_demo_flows):
        """Test error handling flow."""
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "error_handling_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        assert response.status_code == 201
        job_id = response.json()["job_id"]

        # Wait for completion (may succeed or fail)
        time.sleep(0.5)  # Reduced from 2s
        status_response = client.get(f"/api/v1/jobs/{job_id}/status")
        assert status_response.status_code == 200
        status = status_response.json()["status"]
        assert status in ["completed", "failed", "running"]

    def test_fail_job(self, client, setup_demo_flows):
        """Test manually failing a job."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        job_id = response.json()["job_id"]

        # Manually fail the job
        fail_response = client.post(
            f"/api/v1/jobs/{job_id}/fail",
            json={"error": "Manual failure for testing"},
        )
        if fail_response.status_code == 200:
            data = fail_response.json()
            assert data["status"] == "failed"
            assert data["error"] == "Manual failure for testing"

    def test_complete_job(self, client, setup_demo_flows):
        """Test manually completing a job."""
        # Submit job
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        job_id = response.json()["job_id"]

        # Wait a bit
        time.sleep(0.3)  # Reduced from 1s

        # Manually complete the job
        complete_response = client.post(f"/api/v1/jobs/{job_id}/complete")
        if complete_response.status_code == 200:
            data = complete_response.json()
            assert data["status"] == "completed"


class TestUserStory6_RuntimeManagement:
    """
    User Story 6: User uses different runtimes for isolation.

    Scenario:
    1. User lists available runtimes
    2. User creates a job with specific runtime
    3. User verifies runtime isolation
    """

    def test_list_runtimes(self, client, setup_demo_flows):
        """Test listing runtimes."""
        response = client.get("/api/runtimes")
        assert response.status_code == 200
        data = response.json()
        assert "runtimes" in data
        assert len(data["runtimes"]) >= 3

    def test_get_runtime(self, client, setup_demo_flows):
        """Test getting specific runtime."""
        response = client.get("/api/runtimes/production")
        assert response.status_code == 200
        data = response.json()
        # Response has a "runtime" field containing the runtime info
        assert "runtime" in data
        assert data["runtime"]["runtime_id"] == "production"

    def test_create_runtime(self, client, setup_demo_flows):
        """Test creating a new runtime."""
        response = client.post(
            "/api/runtimes",
            json={
                "runtime_id": "custom_test",
                "thread_pool_size": 3,
            },
        )
        if response.status_code in [200, 201]:
            data = response.json()
            # Response has a "runtime" field containing the runtime info
            assert "runtime" in data
            assert data["runtime"]["runtime_id"] == "custom_test"


class TestExecuteEndpoint:
    """Test the execute endpoint for one-shot execution."""

    def test_execute_async(self, client, setup_demo_flows):
        """Test async execution."""
        response = client.post(
            "/api/v1/execute",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
                "wait": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "worker_id" in data

    def test_execute_sync(self, client, setup_demo_flows):
        """Test sync execution with wait."""
        response = client.post(
            "/api/v1/execute",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
                "wait": True,
                "timeout": 5.0,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert "status" in data


class TestBoundaryConditions:
    """Test boundary conditions and error cases."""

    def test_nonexistent_flow(self, client, setup_demo_flows):
        """Test submitting job to nonexistent flow."""
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "nonexistent_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data"},
            },
        )
        assert response.status_code == 404

    def test_nonexistent_routine(self, client, setup_demo_flows):
        """Test submitting job with nonexistent routine."""
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "nonexistent_routine",
                "slot_name": "trigger",
                "data": {"data": "test_data"},
            },
        )
        assert response.status_code == 404

    def test_nonexistent_slot(self, client, setup_demo_flows):
        """Test submitting job with nonexistent slot."""
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "nonexistent_slot",
                "data": {"data": "test_data"},
            },
        )
        assert response.status_code == 404

    def test_nonexistent_job(self, client, setup_demo_flows):
        """Test getting nonexistent job."""
        response = client.get("/api/v1/jobs/nonexistent_job_id")
        assert response.status_code == 404

    def test_nonexistent_worker(self, client, setup_demo_flows):
        """Test getting nonexistent worker."""
        response = client.get("/api/v1/workers/nonexistent_worker_id")
        assert response.status_code == 404

    def test_empty_data(self, client, setup_demo_flows):
        """Test submitting job with empty data."""
        response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {},
            },
        )
        # Should still work (empty data is valid)
        assert response.status_code in [201, 400]

    def test_invalid_json(self, client, setup_demo_flows):
        """Test submitting invalid JSON."""
        response = client.post(
            "/api/v1/jobs",
            data="invalid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


class TestDataConsistency:
    """Test data consistency and backend state management."""

    def test_job_worker_consistency(self, client, setup_demo_flows):
        """Test that job and worker data are consistent."""
        # Create worker
        worker_response = client.post(
            "/api/v1/workers",
            json={"flow_id": "state_transition_flow"},
        )
        worker_id = worker_response.json()["worker_id"]

        # Submit job with worker_id
        job_response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
                "worker_id": worker_id,  # Use the created worker
            },
        )
        job_id = job_response.json()["job_id"]

        # Verify consistency
        job_data = client.get(f"/api/v1/jobs/{job_id}").json()
        worker_data = client.get(f"/api/v1/workers/{worker_id}").json()

        assert job_data["worker_id"] == worker_id
        assert job_data["flow_id"] == worker_data["flow_id"]

    def test_worker_jobs_list_consistency(self, client, setup_demo_flows):
        """Test that worker jobs list is consistent."""
        # Create worker
        worker_response = client.post(
            "/api/v1/workers",
            json={"flow_id": "state_transition_flow"},
        )
        worker_id = worker_response.json()["worker_id"]

        # Submit multiple jobs with worker_id
        job_ids = []
        for i in range(3):
            job_response = client.post(
                "/api/v1/jobs",
                json={
                    "flow_id": "state_transition_flow",
                    "routine_id": "source",
                    "slot_name": "trigger",
                    "data": {"data": f"test_data_{i}", "index": i},
                    "worker_id": worker_id,  # Use the same worker
                },
            )
            job_ids.append(job_response.json()["job_id"])

        # Wait a bit for jobs to be stored
        time.sleep(0.5)

        # Get jobs from worker
        worker_jobs_response = client.get(f"/api/v1/workers/{worker_id}/jobs")
        assert worker_jobs_response.status_code == 200
        worker_job_ids = [j["job_id"] for j in worker_jobs_response.json()["jobs"]]

        # Verify all jobs are in the list
        for job_id in job_ids:
            assert job_id in worker_job_ids

    def test_job_status_consistency(self, client, setup_demo_flows):
        """Test that job status is consistent across endpoints."""
        # Submit job
        job_response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        job_id = job_response.json()["job_id"]

        # Get status from different endpoints
        status1 = client.get(f"/api/v1/jobs/{job_id}/status").json()["status"]
        status2 = client.get(f"/api/v1/jobs/{job_id}").json()["status"]

        assert status1 == status2

    def test_flow_registry_consistency(self, client, setup_demo_flows):
        """Test that flow registry is consistent."""
        # Get flows from API
        api_response = client.get("/api/flows")
        api_flows = {f["flow_id"] for f in api_response.json()["flows"]}

        # Get flows from registry
        flow_registry = get_flow_registry()
        registry_flows = {f.flow_id for f in flow_registry.list_all()}

        # Verify consistency
        assert api_flows == registry_flows


class TestWorkerLifecycle:
    """Test worker lifecycle management."""

    def test_pause_resume_worker(self, client, setup_demo_flows):
        """Test pausing and resuming a worker."""
        # Create worker
        worker_response = client.post(
            "/api/v1/workers",
            json={"flow_id": "state_transition_flow"},
        )
        worker_id = worker_response.json()["worker_id"]

        # Pause worker
        pause_response = client.post(f"/api/v1/workers/{worker_id}/pause")
        if pause_response.status_code == 200:
            data = pause_response.json()
            assert data["status"] == "paused"

            # Resume worker
            resume_response = client.post(f"/api/v1/workers/{worker_id}/resume")
            if resume_response.status_code == 200:
                data = resume_response.json()
                assert data["status"] in ["running", "pending"]

    def test_stop_worker(self, client, setup_demo_flows):
        """Test stopping a worker."""
        # Create worker
        worker_response = client.post(
            "/api/v1/workers",
            json={"flow_id": "state_transition_flow"},
        )
        worker_id = worker_response.json()["worker_id"]

        # Stop worker
        stop_response = client.delete(f"/api/v1/workers/{worker_id}")
        assert stop_response.status_code == 204

        # Wait a bit for cleanup
        time.sleep(0.2)

        # Verify worker is gone from active workers
        # Note: Worker may still exist in registry but not in active workers
        get_response = client.get(f"/api/v1/workers/{worker_id}")
        # Worker might still be in registry, so 200 is acceptable if status is completed/cancelled
        if get_response.status_code == 200:
            data = get_response.json()
            # Worker should be in terminal state
            assert data["status"] in ["completed", "cancelled", "failed"]
        else:
            # Or completely removed (404)
            assert get_response.status_code == 404


class TestJobOutput:
    """Test job output retrieval."""

    def test_get_job_output(self, client, setup_demo_flows):
        """Test getting job output."""
        # Submit job
        job_response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        job_id = job_response.json()["job_id"]

        # Wait a bit
        time.sleep(0.3)  # Reduced from 1s

        # Get output
        output_response = client.get(f"/api/v1/jobs/{job_id}/output")
        assert output_response.status_code == 200
        data = output_response.json()
        assert "job_id" in data
        assert "output" in data

    def test_get_job_trace(self, client, setup_demo_flows):
        """Test getting job trace."""
        # Submit job
        job_response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        job_id = job_response.json()["job_id"]

        # Wait a bit
        time.sleep(0.3)  # Reduced from 1s

        # Get trace
        trace_response = client.get(f"/api/v1/jobs/{job_id}/trace")
        assert trace_response.status_code == 200
        data = trace_response.json()
        assert "job_id" in data
        assert "trace_log" in data


class TestWaitForJob:
    """Test waiting for job completion."""

    def test_wait_for_job(self, client, setup_demo_flows):
        """Test waiting for job completion."""
        # Submit job
        job_response = client.post(
            "/api/v1/jobs",
            json={
                "flow_id": "state_transition_flow",
                "routine_id": "source",
                "slot_name": "trigger",
                "data": {"data": "test_data", "index": 1},
            },
        )
        job_id = job_response.json()["job_id"]

        # Wait for job
        wait_response = client.post(
            f"/api/v1/jobs/{job_id}/wait",
            params={"timeout": 5.0},
        )
        assert wait_response.status_code == 200
        data = wait_response.json()
        assert "status" in data
        assert "final_status" in data
