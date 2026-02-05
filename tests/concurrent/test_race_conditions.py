"""Tests for concurrent race condition scenarios."""

import threading
import time

from routilux import Flow, Routine


class ProcessorRoutine(Routine):
    """A simple processor routine for testing."""

    def __init__(self):
        super().__init__()
        self.received_data = []
        self.lock = threading.Lock()
        self.input_slot = self.define_slot("input", handler=self._handle_input)

    def _handle_input(self, **kwargs):
        with self.lock:
            self.received_data.append(dict(kwargs))


def test_concurrent_slot_receives_merges_correctly():
    """Concurrent receives to same slot should merge correctly."""
    flow = Flow("test_flow")

    routine = ProcessorRoutine()
    flow.add_routine(routine, "processor")

    # Simulate concurrent emits to the slot
    threads = []
    for i in range(10):
        def emit_func(idx=i):
            time.sleep(0.001)  # Slight delay to encourage interleaving
            routine.input_slot.receive({"value": idx})

        thread = threading.Thread(target=emit_func)
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    # All data should be received
    assert len(routine.received_data) == 10
    values = [d.get("value") for d in routine.received_data]
    assert set(values) == set(range(10))


class EmitterRoutine(Routine):
    """An emitter routine for testing."""

    def __init__(self):
        super().__init__()
        self.output_event = self.define_event("output", ["value"])


class ReceiverRoutine(Routine):
    """A receiver routine for testing."""

    def __init__(self):
        super().__init__()
        self.received_count = 0
        self.lock = threading.Lock()
        self.input_slot = self.define_slot("input", handler=self._handle_input)

    def _handle_input(self, value=None, **kwargs):
        with self.lock:
            self.received_count += 1


def test_concurrent_emit_to_same_slot():
    """Multiple routines emitting to same slot concurrently."""
    flow = Flow("test_flow")

    # Create multiple emitter routines
    emitters = []
    emitter_ids = []
    for i in range(5):
        routine = EmitterRoutine()
        rid = flow.add_routine(routine, f"emitter_{i}")
        emitters.append(routine)
        emitter_ids.append(rid)

    # Create receiver routine
    receiver = ReceiverRoutine()
    receiver_id = flow.add_routine(receiver, "receiver")

    # Connect all emitters to receiver
    for emitter_id in emitter_ids:
        flow.connect(emitter_id, "output", receiver_id, "input")

    # Emit concurrently
    threads = []
    for emitter in emitters:
        def emit_func(e=emitter):
            e.output_event.emit(value=42)

        thread = threading.Thread(target=emit_func)
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    # Should receive all emissions
    assert receiver.received_count == 5
