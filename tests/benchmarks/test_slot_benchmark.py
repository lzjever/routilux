"""Benchmarks for slot receive performance."""

import pytest

from routilux import Routine


class TestSlotReceiveBenchmark:
    """Benchmarks for slot data reception throughput."""

    def test_slot_receive_single(self, benchmark):
        """Benchmark receiving a single event."""
        routine = Routine()

        received = []

        def handler(data):
            received.append(data)

        slot = routine.define_slot("input", handler=handler)

        def receive_single():
            slot.receive({"value": 42})

        benchmark(receive_single)

    def test_slot_receive_100_events(self, benchmark):
        """Benchmark receiving 100 events."""
        routine = Routine()

        received = []

        def handler(data):
            received.append(data)

        slot = routine.define_slot("input", handler=handler)

        def receive_100():
            for i in range(100):
                slot.receive({"value": i})

        benchmark(receive_100)

    def test_slot_receive_with_merge_append(self, benchmark):
        """Benchmark receiving with append merge strategy."""
        routine = Routine()

        received = []

        def handler(data):
            received.append(data)

        slot = routine.define_slot("input", handler=handler, merge_strategy="append")

        def receive_with_append():
            for i in range(100):
                slot.receive({"value": i})

        benchmark(receive_with_append)

    def test_slot_receive_with_merge_override(self, benchmark):
        """Benchmark receiving with override merge strategy."""
        routine = Routine()

        received = []

        def handler(data):
            received.append(data)

        slot = routine.define_slot("input", handler=handler, merge_strategy="override")

        def receive_with_override():
            for i in range(100):
                slot.receive({"value": i})

        benchmark(receive_with_override)
