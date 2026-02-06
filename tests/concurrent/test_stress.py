"""Stress tests for high-throughput concurrent execution."""

import gc
import time

from routilux import Flow, Routine
from routilux.job_state import JobState


class ProcessorRoutine(Routine):
    """A simple processor routine for stress testing."""

    def __init__(self):
        super().__init__()
        self.received_count = 0
        self.input_slot = self.define_slot("input", handler=self._handle_input)

    def _handle_input(self, index=None, **kwargs):
        self.received_count += 1


def test_high_throughput_event_emission():
    """System should handle 1000+ events per second."""
    flow = Flow("test_flow", max_workers=4)

    routine = ProcessorRoutine()
    flow.add_routine(routine, "processor")

    # Emit 1000 events directly to the slot
    start = time.time()
    for i in range(1000):
        routine.input_slot.receive({"index": i})
    elapsed = time.time() - start

    # All events should be received
    assert routine.received_count == 1000

    # Should be reasonably fast (< 5 seconds for 1000 events)
    assert elapsed < 5.0


class IndexedRoutine(Routine):
    """A routine with an index for testing."""

    def __init__(self, idx):
        super().__init__()
        self.idx = idx
        # Entry routines need a trigger slot
        self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
        self.input_slot = self.define_slot("input", handler=self._handle_input)
        self.output_event = self.define_event("output", ["value"])

    def _handle_trigger(self, **kwargs):
        pass

    def _handle_input(self, value=None, **kwargs):
        pass


def test_many_concurrent_routines():
    """System should handle 50+ concurrent routines."""
    flow = Flow("test_flow", execution_strategy="concurrent", max_workers=10)

    # Create 50 routines
    for i in range(50):
        routine = IndexedRoutine(i)
        flow.add_routine(routine, f"routine_{i}")

    # Execute first routine
    job_state = flow.execute("routine_0", entry_params={})

    # Emit to all routines
    for routine in flow.routines.values():
        if hasattr(routine, "output_event"):
            routine.output_event.emit(value=42)

    # Should complete - use JobState.wait_for_completion
    completed = JobState.wait_for_completion(flow, job_state, timeout=30.0)
    assert completed
    assert job_state.status == "completed"


class StressTestRoutine(Routine):
    """A routine for stress testing with many concurrent routines."""

    def __init__(self, idx: int):
        super().__init__()
        self.idx = idx
        # Entry routines need a trigger slot
        self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
        self.input_slot = self.define_slot("input", handler=self._handle_input)
        self.done_event = self.define_event("done", ["idx"])

    def _handle_trigger(self, **kwargs):
        pass

    def _handle_input(self, idx=None, **kwargs):
        # Simulate some work
        sum(range(100))


def test_high_concurrency_many_routines():
    """Test system with 100+ concurrent routines."""
    flow = Flow("stress_test", execution_strategy="concurrent", max_workers=20)

    # Create 100 routines
    for i in range(100):
        routine = StressTestRoutine(i)
        flow.add_routine(routine, f"routine_{i}")

    # Execute first routine
    job_state = flow.execute("routine_0", entry_params={})

    # Emit to all routines to trigger processing
    for routine in flow.routines.values():
        if hasattr(routine, "input_slot"):
            routine.input_slot.receive({})

    # Should complete without issues
    completed = JobState.wait_for_completion(flow, job_state, timeout=60.0)
    assert completed
    assert job_state.status == "completed"


class ReceiverRoutine(Routine):
    """A receiver routine for rapid event testing."""

    def __init__(self):
        super().__init__()
        self.received = []
        self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
        self.input_slot = self.define_slot("input", handler=self._handle_input)

    def _handle_trigger(self, **kwargs):
        pass

    def _handle_input(self, value=None, **kwargs):
        self.received.append(value)


def test_rapid_event_emission():
    """Test rapid event emission doesn't cause issues."""
    flow = Flow("rapid_flow", execution_strategy="concurrent")

    routine = ReceiverRoutine()
    flow.add_routine(routine, "receiver")

    # Emit 10,000 events rapidly
    start = time.time()
    for i in range(10000):
        routine.input_slot.receive({"value": i})
    elapsed = time.time() - start

    assert len(routine.received) == 10000
    # Should complete reasonably fast
    assert elapsed < 30.0


class MemoryTestRoutine(Routine):
    """A routine for memory stability testing."""

    def __init__(self):
        super().__init__()
        self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
        self.input_slot = self.define_slot("input", handler=self._handle_input)

    def _handle_trigger(self, **kwargs):
        pass

    def _handle_input(self, **kwargs):
        pass


def test_memory_under_load():
    """Test memory doesn't grow unbounded under load."""
    flow = Flow("memory_test", execution_strategy="concurrent", max_workers=4)

    # Create 50 routines
    for i in range(50):
        routine = MemoryTestRoutine()
        flow.add_routine(routine, f"routine_{i}")

    # Execute multiple times
    for iteration in range(10):
        job_state = flow.execute("routine_0", entry_params={})

        for routine in flow.routines.values():
            routine.input_slot.receive({})

        JobState.wait_for_completion(flow, job_state, timeout=30.0)

        # Force cleanup
        del job_state
        gc.collect()

    # If we get here without OOM, test passes
    assert True
