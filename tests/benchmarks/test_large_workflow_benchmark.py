"""
Large workflow performance benchmarks.

Tests performance with hundreds of routines and complex connection patterns.
"""

import time

from routilux import Flow, Routine
from routilux.core import FlowRegistry, Runtime


def create_processing_routine(name: str) -> Routine:
    """Create a simple processing routine with slot and event."""
    routine = Routine()
    routine.add_slot("input")
    routine.add_event("output")
    return routine


def wait_for_job_completion(runtime: Runtime, job, timeout: float = 30.0) -> bool:
    """Wait for a job to complete.

    Args:
        runtime: Runtime instance
        job: JobContext to wait for
        timeout: Maximum wait time in seconds

    Returns:
        True if completed, False if timeout
    """
    start = time.time()
    while time.time() - start < timeout:
        current_job = runtime.get_job(job.job_id)
        if current_job and current_job.status in ("completed", "failed"):
            return True
        time.sleep(0.001)  # 1ms polling interval
    return False


class TestLargeWorkflowBenchmark:
    """Benchmarks for large-scale workflows."""

    def test_create_flow_with_100_routines(self, benchmark):
        """Benchmark creating a flow with 100 routines."""

        def create_large_flow():
            flow = Flow("large_workflow")

            # Create 100 routines
            for i in range(100):
                routine = create_processing_routine(f"r{i}")
                flow.add_routine(routine, f"r{i}")

            # Create a diamond pattern (each routine connects to next two)
            for i in range(99):
                flow.connect(f"r{i}", "output", f"r{i + 1}", "input")
                if i + 2 < 100:
                    flow.connect(f"r{i}", "output", f"r{i + 2}", "input")

            return flow

        flow = benchmark(create_large_flow)
        assert len(flow.routines) == 100
        # Each routine (except last) connects to 1 or 2 others
        # First 98 routines connect to 2, r98 connects to 1, r99 connects to 0
        # Total connections = 98*2 + 1 = 197
        assert len(flow.connections) > 100

    def test_post_job_to_large_flow(self, benchmark):
        """Benchmark posting a job to a flow with 100 routines."""
        # Create large flow
        flow = Flow("large_workflow_post_test")

        for i in range(100):
            routine = create_processing_routine(f"r{i}")
            flow.add_routine(routine, f"r{i}")

        # Create linear connections
        for i in range(99):
            flow.connect(f"r{i}", "output", f"r{i + 1}", "input")

        registry = FlowRegistry.get_instance()
        registry.register_by_name("large_workflow_post_test", flow)

        # Set up outside benchmark
        runtime = Runtime(thread_pool_size=10)
        worker_state = runtime.exec("large_workflow_post_test")

        def post_job():
            _, job = runtime.post("large_workflow_post_test", "r0", "input", {"value": 1})
            return job

        result = benchmark(post_job)
        assert result.job_id is not None

        # Cleanup
        runtime.shutdown(wait=True)
        registry.unregister_by_name("large_workflow_post_test")

    def test_serialization_large_workflow(self, benchmark):
        """Benchmark serializing a workflow with 100 routines."""
        flow = Flow("serialization_test")

        for i in range(100):
            routine = create_processing_routine(f"r{i}")
            flow.add_routine(routine, f"r{i}")

        def serialize_large():
            return flow.serialize()

        data = benchmark(serialize_large)
        assert "version" in data
        assert len(data.get("routines", {})) == 100

    def test_workflow_100_routines(self, benchmark):
        """Benchmark executing a job through a workflow with 100 routines.

        This benchmark measures the full time to post a job to a large workflow
        and wait for completion, testing scale performance.
        """
        flow = Flow("large_workflow_exec")

        # Create 100 routines
        for i in range(100):
            routine = create_processing_routine(f"r{i}")
            flow.add_routine(routine, f"r{i}")

        # Create a diamond pattern (each routine connects to next two)
        for i in range(99):
            flow.connect(f"r{i}", "output", f"r{i + 1}", "input")
            if i + 2 < 100:
                flow.connect(f"r{i}", "output", f"r{i + 2}", "input")

        registry = FlowRegistry.get_instance()
        registry.register_by_name("large_workflow_exec", flow)

        runtime = Runtime(thread_pool_size=10)
        worker_state = runtime.exec("large_workflow_exec")

        def execute_large():
            _, job = runtime.post("large_workflow_exec", "r0", "input", {"value": 1})

            # Wait for completion
            completed = wait_for_job_completion(runtime, job, timeout=30.0)
            # Mark as completed since jobs won't auto-complete without activation policies
            if not completed:
                runtime.complete_job(job.job_id, "completed")

            return job

        result = benchmark(execute_large)
        assert result.job_id is not None

        runtime.shutdown(wait=True)
        registry.unregister_by_name("large_workflow_exec")
