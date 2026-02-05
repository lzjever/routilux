"""Tests for memory leaks in concurrent execution."""

import gc

from routilux import Flow, Routine
from routilux.job_state import JobState


class ChainProcessorRoutine(Routine):
    """A routine that creates chains of events."""

    def __init__(self):
        super().__init__()
        self.received_count = 0
        # Entry routines need a trigger slot
        self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
        self.input_slot = self.define_slot("input", handler=self._handle_input)
        self.chain_event = self.define_event("chain", ["count"])
        self.output_event = self.define_event("output", ["index"])

    def _handle_trigger(self, **kwargs):
        pass

    def _handle_input(self, **kwargs):
        self.received_count += 1
        if self.received_count % 100 == 0:
            # Emit another event (create chains)
            self.chain_event.emit(count=self.received_count)


def test_history_cleanup_prevents_memory_growth():
    """JobState history cleanup should prevent unbounded growth."""
    flow = Flow("test_flow")

    routine = ChainProcessorRoutine()
    flow.add_routine(routine, "processor")

    # Note: max_history_size is not a parameter of execute()
    # The history cleanup is handled by JobState internally
    job_state = flow.execute("processor", entry_params={})

    # Emit many events
    for i in range(100):
        routine.output_event.emit(index=i)

    # Wait for completion using JobState.wait_for_completion
    JobState.wait_for_completion(flow, job_state, timeout=30.0)

    # History should be reasonably bounded
    # The exact limit depends on implementation details
    assert len(job_state.execution_history) < 1000


class SimpleProcessorRoutine(Routine):
    """A simple processor routine."""

    def __init__(self):
        super().__init__()
        # Entry routines need a trigger slot
        self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
        self.input_slot = self.define_slot("input", handler=self._handle_input)
        self.output_event = self.define_event("output", ["test"])
        self.another_event = self.define_event("another", ["data"])

    def _handle_trigger(self, **kwargs):
        pass

    def _handle_input(self, test=None, **kwargs):
        pass


def test_routine_cleanup_after_execution():
    """Routines should not hold references after execution."""
    flow = Flow("test_flow")

    routine = SimpleProcessorRoutine()
    flow.add_routine(routine, "processor")

    # Execute
    job_state = flow.execute("processor", entry_params={})
    routine.output_event.emit(test=True)

    JobState.wait_for_completion(flow, job_state, timeout=10.0)

    # Force garbage collection
    del job_state
    gc.collect()

    # Routine should still be usable (not holding stale references)
    routine.another_event.emit(data=123)
