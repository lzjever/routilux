"""Basic tests for Runtime class."""

import time

import pytest
from routilux.core import (
    ExecutionStatus,
    Flow,
    JobContext,
    JobStatus,
    Runtime,
    Routine,
)


class TestRuntimeCreation:
    """Test Runtime creation and initialization."""

    def test_runtime_creation_default(self):
        """Test creating a Runtime with default settings."""
        runtime = Runtime()
        
        assert runtime.thread_pool_size == 10
        assert runtime.thread_pool is not None
        assert not runtime._shutdown

    def test_runtime_creation_custom_size(self):
        """Test creating a Runtime with custom thread pool size."""
        runtime = Runtime(thread_pool_size=5)
        
        assert runtime.thread_pool_size == 5
        assert runtime.thread_pool is not None

    def test_runtime_creation_zero_size(self):
        """Test creating a Runtime with zero thread pool size (uses global)."""
        runtime = Runtime(thread_pool_size=0)
        
        assert runtime.thread_pool_size == 0
        assert runtime.thread_pool is None

    def test_runtime_creation_negative_size(self):
        """Test that negative thread pool size raises ValueError."""
        with pytest.raises(ValueError):
            Runtime(thread_pool_size=-1)


class TestRuntimeExec:
    """Test Runtime.exec() method."""

    def test_exec_creates_worker(self):
        """Test that exec() creates a worker."""
        from routilux.core import FlowRegistry, get_flow_registry
        
        class TestRoutine(Routine):
            def setup(self):
                self.add_slot("input")
        
        flow = Flow()
        flow.flow_id = "test_flow"
        routine = TestRoutine()
        routine.setup()
        flow.add_routine(routine, "test")
        
        # Register flow
        registry = get_flow_registry()
        registry.register_by_name("test_flow", flow)
        
        runtime = Runtime()
        worker_state = runtime.exec("test_flow")
        
        assert worker_state is not None
        assert worker_state.flow_id == flow.flow_id
        assert worker_state.worker_id is not None
        assert worker_state.status == ExecutionStatus.RUNNING

    def test_exec_registers_flow(self):
        """Test that exec() uses registered flow."""
        from routilux.core import get_flow_registry
        
        class TestRoutine(Routine):
            def setup(self):
                self.add_slot("input")
        
        flow = Flow()
        flow.flow_id = "test_flow"
        routine = TestRoutine()
        routine.setup()
        flow.add_routine(routine, "test")
        
        # Register flow first
        registry = get_flow_registry()
        registry.register_by_name("test_flow", flow)
        
        runtime = Runtime()
        worker_state = runtime.exec("test_flow")
        
        # Flow should be accessible
        assert registry.get_by_name("test_flow") == flow
        assert worker_state.flow_id == flow.flow_id

    def test_exec_with_existing_worker_id(self):
        """Test exec() creates new worker each time."""
        from routilux.core import get_flow_registry
        
        class TestRoutine(Routine):
            def setup(self):
                self.add_slot("input")
        
        flow = Flow()
        flow.flow_id = "test_flow"
        routine = TestRoutine()
        routine.setup()
        flow.add_routine(routine, "test")
        
        # Register flow
        registry = get_flow_registry()
        registry.register_by_name("test_flow", flow)
        
        runtime = Runtime()
        worker1 = runtime.exec("test_flow")
        
        # Exec again should create a new worker
        worker2 = runtime.exec("test_flow")
        
        assert worker1.worker_id != worker2.worker_id


class TestRuntimePost:
    """Test Runtime.post() method."""

    def test_post_creates_job(self):
        """Test that post() creates a job."""
        from routilux.core import get_flow_registry
        
        class TestRoutine(Routine):
            def setup(self):
                self.add_slot("input")
            
            def logic(self, input_data, **kwargs):
                return {"result": "processed"}
        
        flow = Flow()
        flow.flow_id = "test_flow"
        routine = TestRoutine()
        routine.setup()
        flow.add_routine(routine, "processor")
        
        # Register flow
        registry = get_flow_registry()
        registry.register_by_name("test_flow", flow)
        
        runtime = Runtime()
        runtime.exec("test_flow")
        
        worker_state, job = runtime.post(
            "test_flow", "processor", "input",
            {"data": "test"}
        )
        
        assert worker_state is not None
        assert job is not None
        assert isinstance(job, JobContext)
        assert job.job_id is not None
        assert job.worker_id == worker_state.worker_id
        assert job.status == JobStatus.RUNNING

    def test_post_with_metadata(self):
        """Test post() with metadata."""
        from routilux.core import get_flow_registry
        
        class TestRoutine(Routine):
            def setup(self):
                self.add_slot("input")
        
        flow = Flow()
        flow.flow_id = "test_flow"
        routine = TestRoutine()
        routine.setup()
        flow.add_routine(routine, "processor")
        
        # Register flow
        registry = get_flow_registry()
        registry.register_by_name("test_flow", flow)
        
        runtime = Runtime()
        runtime.exec("test_flow")
        
        metadata = {"user_id": "123", "source": "api"}
        worker_state, job = runtime.post(
            "test_flow", "processor", "input",
            {"data": "test"},
            metadata=metadata
        )
        
        assert job.metadata == metadata

    def test_post_with_custom_job_id(self):
        """Test post() with custom job ID."""
        from routilux.core import get_flow_registry
        
        class TestRoutine(Routine):
            def setup(self):
                self.add_slot("input")
        
        flow = Flow()
        flow.flow_id = "test_flow"
        routine = TestRoutine()
        routine.setup()
        flow.add_routine(routine, "processor")
        
        # Register flow
        registry = get_flow_registry()
        registry.register_by_name("test_flow", flow)
        
        runtime = Runtime()
        runtime.exec("test_flow")
        
        custom_job_id = "custom-job-123"
        worker_state, job = runtime.post(
            "test_flow", "processor", "input",
            {"data": "test"},
            job_id=custom_job_id
        )
        
        assert job.job_id == custom_job_id

    def test_post_nonexistent_flow(self):
        """Test post() with nonexistent flow."""
        runtime = Runtime()
        
        with pytest.raises(ValueError):
            runtime.post("nonexistent", "routine", "slot", {"data": "test"})

    def test_post_nonexistent_routine(self):
        """Test post() with nonexistent routine."""
        from routilux.core import get_flow_registry
        
        flow = Flow()
        flow.flow_id = "test_flow"
        
        # Register flow
        registry = get_flow_registry()
        registry.register_by_name("test_flow", flow)
        
        runtime = Runtime()
        runtime.exec("test_flow")
        
        with pytest.raises(ValueError):
            runtime.post("test_flow", "nonexistent", "slot", {"data": "test"})

    def test_post_nonexistent_slot(self):
        """Test post() with nonexistent slot."""
        from routilux.core import get_flow_registry
        
        class TestRoutine(Routine):
            def setup(self):
                self.add_slot("input")
        
        flow = Flow()
        flow.flow_id = "test_flow"
        routine = TestRoutine()
        routine.setup()
        flow.add_routine(routine, "processor")
        
        # Register flow
        registry = get_flow_registry()
        registry.register_by_name("test_flow", flow)
        
        runtime = Runtime()
        runtime.exec("test_flow")
        
        with pytest.raises(ValueError):
            runtime.post("test_flow", "processor", "nonexistent", {"data": "test"})
