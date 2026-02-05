"""Benchmarks for concurrent execution performance."""

import pytest

from routilux import Flow, JobState, Routine


class TestConcurrentBenchmark:
    """Benchmarks for concurrent workflow execution."""

    def test_sequential_execution_baseline(self, benchmark):
        """Baseline benchmark for sequential execution."""
        flow = Flow("test", execution_strategy="sequential")

        for i in range(5):
            routine = Routine()
            flow.add_routine(routine, f"routine_{i}")
            routine.define_slot("input", handler=lambda d: None)

        job_state = flow.execute("routine_0", entry_params={})
        JobState.wait_for_completion(flow, job_state, timeout=10.0)

        # Benchmark setup
        flow2 = Flow("test2", execution_strategy="sequential")
        for i in range(5):
            routine = Routine()
            flow2.add_routine(routine, f"routine_{i}")
            routine.define_slot("input", handler=lambda d: None)

        def execute_sequential():
            js = flow2.execute("routine_0", entry_params={})
            JobState.wait_for_completion(flow2, js, timeout=10.0)

        benchmark(execute_sequential)

    def test_concurrent_execution_speedup(self, benchmark):
        """Benchmark for concurrent execution."""
        flow = Flow("test", execution_strategy="concurrent", max_workers=4)

        for i in range(5):
            routine = Routine()
            flow.add_routine(routine, f"routine_{i}")
            routine.define_slot("input", handler=lambda d: None)

        job_state = flow.execute("routine_0", entry_params={})
        JobState.wait_for_completion(flow, job_state, timeout=10.0)

        # Benchmark setup
        flow2 = Flow("test2", execution_strategy="concurrent", max_workers=4)
        for i in range(5):
            routine = Routine()
            flow2.add_routine(routine, f"routine_{i}")
            routine.define_slot("input", handler=lambda d: None)

        def execute_concurrent():
            js = flow2.execute("routine_0", entry_params={})
            JobState.wait_for_completion(flow2, js, timeout=10.0)

        benchmark(execute_concurrent)
