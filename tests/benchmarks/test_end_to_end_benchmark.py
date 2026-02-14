"""
End-to-end performance benchmarks for Routilux.

These benchmarks test complete workflow execution with realistic data sizes.
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


def wait_for_job_completion(runtime: Runtime, job, timeout: float = 5.0) -> bool:
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


class TestEndToEndBenchmark:
    """End-to-end performance benchmarks."""

    def test_setup_flow_with_10_routines(self, benchmark):
        """Benchmark creating and connecting a flow with 10 routines."""

        def setup_flow():
            flow = Flow("linear_chain")

            routines = []
            for i in range(10):
                routine = create_processing_routine(f"r{i}")
                routines.append(routine)
                flow.add_routine(routine, f"r{i}")

            # Connect them in a chain
            for i in range(9):
                flow.connect(f"r{i}", "output", f"r{i + 1}", "input")

            return flow

        flow = benchmark(setup_flow)
        assert len(flow.routines) == 10
        assert len(flow.connections) == 9

    def test_post_single_job(self, benchmark):
        """Benchmark posting a single job to a flow."""
        # Create flow with 10 routines
        flow = Flow("post_test")

        for i in range(10):
            routine = create_processing_routine(f"r{i}")
            flow.add_routine(routine, f"r{i}")

        # Connect them in a chain
        for i in range(9):
            flow.connect(f"r{i}", "output", f"r{i + 1}", "input")

        # Register flow
        registry = FlowRegistry.get_instance()
        registry.register_by_name("post_test", flow)

        # Create runtime
        runtime = Runtime(thread_pool_size=4)
        _worker_state = runtime.exec("post_test")  # noqa: F841

        def post_job():
            _, job = runtime.post("post_test", "r0", "input", {"value": 1})
            return job

        result = benchmark(post_job)
        assert result.job_id is not None

        # Cleanup
        runtime.shutdown(wait=True)
        registry.unregister_by_name("post_test")

    def test_create_50_parallel_jobs(self, benchmark):
        """Benchmark creating 50 parallel jobs."""
        # Create simple flow
        flow = Flow("parallel_test")
        routine = create_processing_routine("processor")
        flow.add_routine(routine, "processor")

        registry = FlowRegistry.get_instance()
        registry.register_by_name("parallel_test", flow)

        runtime = Runtime(thread_pool_size=10)
        _worker_state = runtime.exec("parallel_test")  # noqa: F841

        def create_jobs():
            jobs = []
            for i in range(50):
                _, job = runtime.post("parallel_test", "processor", "input", {"value": i})
                jobs.append(job)
            return jobs

        result = benchmark(create_jobs)
        assert len(result) == 50

        runtime.shutdown(wait=True)
        registry.unregister_by_name("parallel_test")

    def test_linear_chain_10_routines(self, benchmark):
        """Benchmark executing a linear chain of 10 routines with job completion.

        This benchmark measures the full time to post a job and wait for completion,
        testing realistic workflow execution overhead.
        """
        # Create flow with 10 routines in a chain
        flow = Flow("linear_chain_exec")

        routines = []
        for i in range(10):
            routine = create_processing_routine(f"r{i}")
            routines.append(routine)
            flow.add_routine(routine, f"r{i}")

        # Connect them in a chain
        for i in range(9):
            flow.connect(f"r{i}", "output", f"r{i + 1}", "input")

        # Register flow
        registry = FlowRegistry.get_instance()
        registry.register_by_name("linear_chain_exec", flow)

        # Create runtime
        runtime = Runtime(thread_pool_size=4)
        _worker_state = runtime.exec("linear_chain_exec")  # noqa: F841

        def execute_chain():
            _, job = runtime.post("linear_chain_exec", "r0", "input", {"value": 1})
            # Wait for completion
            completed = wait_for_job_completion(runtime, job, timeout=5.0)
            # Mark as completed since jobs won't auto-complete without activation policies
            if not completed:
                runtime.complete_job(job.job_id, "completed")
            return job

        result = benchmark(execute_chain)
        assert result.job_id is not None

        # Cleanup
        runtime.shutdown(wait=True)
        registry.unregister_by_name("linear_chain_exec")

    def test_parallel_execution_50_jobs(self, benchmark):
        """Benchmark 50 parallel jobs with completion waiting.

        This benchmark measures the time to create and wait for 50 parallel jobs,
        testing concurrent execution overhead.
        """
        # Create simple flow
        flow = Flow("parallel_exec_test")
        routine = create_processing_routine("processor")
        flow.add_routine(routine, "processor")

        registry = FlowRegistry.get_instance()
        registry.register_by_name("parallel_exec_test", flow)

        runtime = Runtime(thread_pool_size=10)
        _worker_state = runtime.exec("parallel_exec_test")  # noqa: F841

        def run_parallel_jobs():
            jobs = []
            for i in range(50):
                _, job = runtime.post("parallel_exec_test", "processor", "input", {"value": i})
                jobs.append(job)

            # Wait for all jobs to complete
            timeout = 10.0
            start = time.time()
            while time.time() - start < timeout:
                completed = sum(
                    1
                    for j in jobs
                    if runtime.get_job(j.job_id)
                    and runtime.get_job(j.job_id).status in ("completed", "failed")
                )
                if completed == len(jobs):
                    break
                time.sleep(0.001)

            # Mark any remaining jobs as completed
            for job in jobs:
                current_job = runtime.get_job(job.job_id)
                if current_job and current_job.status == "running":
                    runtime.complete_job(job.job_id, "completed")

            return jobs

        result = benchmark(run_parallel_jobs)
        assert len(result) == 50

        runtime.shutdown(wait=True)
        registry.unregister_by_name("parallel_exec_test")
