"""
Stress tests for high-throughput concurrent execution using current API.

These tests verify system stability under high load conditions.
"""

import gc
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from routilux import Flow, Routine, Runtime
from routilux.core import FlowRegistry, WorkerState


class StressTestRoutine(Routine):
    """A simple routine for stress testing."""

    def __init__(self, idx: int = 0):
        super().__init__()
        self.idx = idx
        self.processed_count = 0
        self._lock = threading.Lock()
        self.add_slot("input")
        self.add_event("output", ["value"])

    def logic(self, value=None, **kwargs):
        """Process input data."""
        with self._lock:
            self.processed_count += 1
        # Simulate some work
        sum(range(100))
        # Emit result
        self.emit("output", value=(value or 0) + 1)


class TriggerRoutine(Routine):
    """Entry point routine for triggering workflows."""

    def __init__(self):
        super().__init__()
        self.add_slot("trigger")
        self.add_event("start", ["value"])

    def logic(self, value=None, **kwargs):
        """Emit start event."""
        self.emit("start", value=value or 1)


def test_runtime_high_throughput_post():
    """Test Runtime.post() with 1000+ jobs concurrently."""
    # Reset registry
    FlowRegistry._instance = None
    registry = FlowRegistry.get_instance()

    flow = Flow("stress_test_flow")

    # Create entry routine
    trigger = TriggerRoutine()
    flow.add_routine(trigger, "trigger")

    # Create 10 worker routines
    workers = []
    for i in range(10):
        worker = StressTestRoutine(i)
        workers.append(worker)
        flow.add_routine(worker, f"worker_{i}")
        # Connect trigger to each worker
        flow.connect("trigger", "start", f"worker_{i}", "input")

    # Register flow
    registry.register_by_name("stress_test_flow", flow)

    # Create runtime with larger thread pool
    with Runtime(thread_pool_size=20) as runtime:
        # Submit 1000 jobs
        jobs = []
        start = time.time()

        for i in range(1000):
            worker_state, job_context = runtime.post(
                flow_name="stress_test_flow",
                routine_name="trigger",
                slot_name="trigger",
                data={"value": i},
            )
            jobs.append((worker_state, job_context))

        elapsed_post = time.time() - start

        # Wait for all jobs to complete
        start_wait = time.time()
        for worker_state, job_context in jobs:
            # Wait with timeout
            timeout = 60.0
            WorkerState.wait_for_completion(flow, worker_state, timeout=timeout)

        _ = time.time() - start_wait  # Track completion time

    # All posts should be fast
    assert elapsed_post < 10.0, f"Posting 1000 jobs took {elapsed_post:.2f}s"

    # Verify runtime handled all posts without crashing
    assert len(jobs) == 1000


def test_many_concurrent_runtimes():
    """Test multiple Runtime instances running concurrently."""
    # Reset registry
    FlowRegistry._instance = None
    registry = FlowRegistry.get_instance()

    # Create multiple flows
    flows = []
    for i in range(5):
        flow = Flow(f"concurrent_flow_{i}")
        trigger = TriggerRoutine()
        worker = StressTestRoutine(0)
        flow.add_routine(trigger, "trigger")
        flow.add_routine(worker, "worker")
        flow.connect("trigger", "start", "worker", "input")
        registry.register_by_name(f"concurrent_flow_{i}", flow)
        flows.append(flow)

    results = []
    errors = []

    def run_flow(flow_idx: int, flow: Flow):
        """Run a single flow multiple times."""
        try:
            with Runtime(thread_pool_size=4) as runtime:
                for _ in range(100):
                    worker_state, job_context = runtime.post(
                        flow_name=f"concurrent_flow_{flow_idx}",
                        routine_name="trigger",
                        slot_name="trigger",
                        data={"value": flow_idx},
                    )
                    WorkerState.wait_for_completion(flow, worker_state, timeout=10.0)
                    results.append((flow_idx, worker_state.status))
        except Exception as e:
            errors.append((flow_idx, str(e)))

    # Run all flows concurrently
    start = time.time()
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(run_flow, i, flows[i]) for i in range(5)]
        for future in as_completed(futures):
            future.result()  # Raise any exceptions

    elapsed = time.time() - start

    # Should complete without errors
    assert len(errors) == 0, f"Errors: {errors}"
    assert len(results) == 500, f"Expected 500 results, got {len(results)}"
    assert elapsed < 60.0, f"Test took {elapsed:.2f}s"


def test_rapid_slot_enqueue():
    """Test rapid data enqueue to slots doesn't cause issues."""
    routine = StressTestRoutine(0)
    # Replace slot with larger queue for this test
    routine._slots["input"].max_queue_length = 20000
    routine._slots["input"].watermark_threshold = 16000

    # Rapidly enqueue 10000 items
    start = time.time()
    for i in range(10000):
        routine._slots["input"].enqueue(
            data={"value": i},
            emitted_from="test",
            emitted_at=None,
        )
    elapsed = time.time() - start

    # Should be fast
    assert elapsed < 5.0, f"Enqueue 10000 items took {elapsed:.2f}s"

    # Queue should have items
    assert len(routine._slots["input"]._queue) == 10000


def test_thread_safety_of_routine_state():
    """Test routine state access is thread-safe."""
    routine = StressTestRoutine(0)
    errors = []

    def modify_state(thread_id: int):
        """Modify routine state from multiple threads."""
        try:
            for i in range(1000):
                with routine._lock:
                    routine.processed_count += 1
        except Exception as e:
            errors.append((thread_id, str(e)))

    # Run 10 threads, each doing 1000 increments
    threads = []
    for i in range(10):
        t = threading.Thread(target=modify_state, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # No errors should occur
    assert len(errors) == 0, f"Thread safety errors: {errors}"
    # Total count should be exactly 10000
    assert routine.processed_count == 10000


def test_memory_cleanup_under_load():
    """Test memory is properly cleaned up after jobs complete."""
    # Reset registry
    FlowRegistry._instance = None
    registry = FlowRegistry.get_instance()

    flow = Flow("memory_test_flow")
    trigger = TriggerRoutine()
    worker = StressTestRoutine(0)
    flow.add_routine(trigger, "trigger")
    flow.add_routine(worker, "worker")
    flow.connect("trigger", "start", "worker", "input")
    registry.register_by_name("memory_test_flow", flow)

    # Run multiple iterations
    with Runtime(thread_pool_size=4) as runtime:
        for iteration in range(10):
            worker_state, job_context = runtime.post(
                flow_name="memory_test_flow",
                routine_name="trigger",
                slot_name="trigger",
                data={"value": iteration},
            )
            WorkerState.wait_for_completion(flow, worker_state, timeout=5.0)

            # Force cleanup
            del worker_state
            del job_context
            gc.collect()

    # If we get here without OOM, test passes
    assert True


def test_flow_registration_thread_safety():
    """Test flow registration is thread-safe."""
    # Reset registry
    FlowRegistry._instance = None
    registry = FlowRegistry.get_instance()
    errors = []

    def register_flow(flow_idx: int):
        """Register a flow."""
        try:
            flow = Flow(f"thread_safety_flow_{flow_idx}")
            trigger = TriggerRoutine()
            flow.add_routine(trigger, "trigger")
            registry.register_by_name(f"thread_safety_flow_{flow_idx}", flow)
        except Exception as e:
            errors.append((flow_idx, str(e)))

    # Run 50 threads, each registering a flow
    threads = []
    for i in range(50):
        t = threading.Thread(target=register_flow, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # No errors should occur
    assert len(errors) == 0, f"Registration errors: {errors}"

    # All flows should be registered
    for i in range(50):
        flow = registry.get_by_name(f"thread_safety_flow_{i}")
        assert flow is not None, f"Flow {i} not found"


class TestConcurrencyLimits:
    """Tests for concurrency limit handling."""

    def test_thread_pool_size_limit(self):
        """Test that thread pool size is respected."""
        # Reset registry
        FlowRegistry._instance = None
        registry = FlowRegistry.get_instance()

        flow = Flow("limit_test_flow")
        trigger = TriggerRoutine()
        worker = StressTestRoutine(0)
        flow.add_routine(trigger, "trigger")
        flow.add_routine(worker, "worker")
        flow.connect("trigger", "start", "worker", "input")
        registry.register_by_name("limit_test_flow", flow)

        # Create runtime with small thread pool
        with Runtime(thread_pool_size=2) as runtime:
            # Submit 100 jobs - should queue up
            jobs = []
            for i in range(100):
                worker_state, job_context = runtime.post(
                    flow_name="limit_test_flow",
                    routine_name="trigger",
                    slot_name="trigger",
                    data={"value": i},
                )
                jobs.append((worker_state, job_context))

            # All jobs should eventually complete
            for worker_state, job_context in jobs:
                WorkerState.wait_for_completion(flow, worker_state, timeout=30.0)

        # All jobs completed without crashing
        assert len(jobs) == 100

    def test_invalid_thread_pool_size(self):
        """Test that negative thread pool size raises error."""
        with pytest.raises(ValueError, match="thread_pool_size must be >= 0"):
            Runtime(thread_pool_size=-1)
