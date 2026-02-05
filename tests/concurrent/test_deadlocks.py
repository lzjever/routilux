"""Tests for potential deadlock scenarios."""

import time

from routilux import Flow, Routine


class SimpleRoutine(Routine):
    """A simple routine for deadlock testing."""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self._handle_input)
        self.output_event = self.define_event("output", ["data"])

    def _handle_input(self, data=None, **kwargs):
        pass


def test_circular_dependency_no_deadlock():
    """Circular connections should not cause deadlock."""
    flow = Flow("test_flow", execution_strategy="concurrent")

    routine_a = SimpleRoutine()
    routine_b = SimpleRoutine()

    id_a = flow.add_routine(routine_a, "A")
    id_b = flow.add_routine(routine_b, "B")

    # Create circular connection: A -> B, B -> A
    flow.connect(id_a, "output", id_b, "input")
    flow.connect(id_b, "output", id_a, "input")

    # Execute should complete without deadlock
    job_state = flow.execute("A", entry_params={})

    # Timeout after 5 seconds if deadlocked
    start = time.time()
    while job_state.status == "running" and time.time() - start < 5:
        time.sleep(0.1)

    assert job_state.status != "running"  # Not deadlocked


def test_deep_nesting_no_deadlock():
    """Deeply nested routine chains should not deadlock."""
    flow = Flow("test_flow", execution_strategy="concurrent")

    # Create chain of 10 routines
    routines = []
    routine_ids = []
    for i in range(10):
        routine = SimpleRoutine()
        rid = flow.add_routine(routine, f"routine_{i}")
        routines.append(routine)
        routine_ids.append(rid)

    # Connect in chain: 0 -> 1 -> 2 -> ... -> 9
    for i in range(len(routine_ids) - 1):
        flow.connect(routine_ids[i], "output", routine_ids[i + 1], "input")

    # Execute first routine
    job_state = flow.execute("routine_0", entry_params={})

    # Should complete without deadlock
    start = time.time()
    while job_state.status == "running" and time.time() - start < 5:
        time.sleep(0.1)

    assert job_state.status != "running"
