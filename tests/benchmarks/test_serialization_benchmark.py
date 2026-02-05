"""Benchmarks for serialization performance."""

import pytest

from routilux.job_state import JobState


class TestSerializationBenchmark:
    """Benchmarks for JobState serialization."""

    def test_empty_jobstate_serialization(self, benchmark):
        """Benchmark serializing an empty JobState."""
        job_state = JobState("test_flow")

        def serialize():
            job_state.serialize()

        benchmark(serialize)

    def test_jobstate_with_history_serialization(self, benchmark):
        """Benchmark serializing JobState with execution history."""
        job_state = JobState("test_flow")

        # Add some history
        for i in range(100):
            job_state.record_execution(f"routine_{i}", "event", {"index": i})

        def serialize():
            job_state.serialize()

        benchmark(serialize)

    def test_jobstate_deserialization(self, benchmark):
        """Benchmark deserializing JobState."""
        job_state = JobState("test_flow")

        # Add some history
        for i in range(100):
            job_state.record_execution(f"routine_{i}", "event", {"index": i})

        serialized = job_state.serialize()

        # Create a new instance for deserialization
        def deserialize():
            new_job_state = JobState("test_flow")
            new_job_state.deserialize(serialized)

        benchmark(deserialize)
