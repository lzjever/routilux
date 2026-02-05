"""Benchmarks for event emission performance."""

import pytest

from routilux import Flow, Routine


class TestEventEmissionBenchmark:
    """Benchmarks for event emission throughput."""

    def test_event_emission_single_event(self, benchmark):
        """Benchmark emitting a single event."""
        flow = Flow("test")
        routine = Routine()
        flow.add_routine(routine)
        routine.define_event("output")

        def emit_single():
            routine.emit("output", value=42)

        benchmark(emit_single)

    def test_event_emission_100_events(self, benchmark):
        """Benchmark emitting 100 events sequentially."""
        flow = Flow("test")
        routine = Routine()
        flow.add_routine(routine)
        routine.define_event("output")

        def emit_100():
            for i in range(100):
                routine.emit("output", value=i)

        benchmark(emit_100)

    def test_event_emission_1000_events(self, benchmark):
        """Benchmark emitting 1000 events sequentially."""
        flow = Flow("test")
        routine = Routine()
        flow.add_routine(routine)
        routine.define_event("output")

        def emit_1000():
            for i in range(1000):
                routine.emit("output", value=i)

        benchmark(emit_1000)

    def test_event_emission_multiple_data_fields(self, benchmark):
        """Benchmark emitting events with multiple data fields."""
        flow = Flow("test")
        routine = Routine()
        flow.add_routine(routine)
        routine.define_event("output")

        def emit_complex():
            for i in range(100):
                routine.emit("output", value=i, status=f"step_{i}", data={"nested": True})

        benchmark(emit_complex)
