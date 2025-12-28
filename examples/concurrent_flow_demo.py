#!/usr/bin/env python
"""
Concurrent Flow Execution Demo

This demo demonstrates Routilux's concurrent execution capabilities.
It shows how multiple routines can execute in parallel using thread pools,
significantly improving performance for I/O-bound operations.

Features demonstrated:
- Concurrent execution strategy
- Multiple parallel routines
- Dependency handling
- Performance comparison (sequential vs concurrent)
- Thread-safe state management
- Error handling in concurrent execution
- Serialization of concurrent flows
"""

import time
import json
from typing import Dict, Any
from routilux import Flow, Routine, ErrorHandler, ErrorStrategy


# ============================================================================
# Routine Definitions
# ============================================================================


class DataFetcher(Routine):
    """Fetch data from multiple sources concurrently"""

    def __init__(self, source_name: str = None, delay: float = 0.2):
        super().__init__()
        self.source_name = source_name or "unknown"
        self.delay = delay
        self.input_slot = self.define_slot("trigger", handler=self.fetch_data)
        self.output_event = self.define_event("data_fetched", ["data", "source", "timestamp"])
        self._stats["fetch_count"] = 0

        # Register for serialization
        self.add_serializable_fields(["source_name", "delay"])

    def fetch_data(self, **kwargs):
        """Simulate fetching data from a source (I/O operation)"""
        self._stats["fetch_count"] = self._stats.get("fetch_count", 0) + 1

        # Simulate network delay
        time.sleep(self.delay)

        # Simulate fetching data
        data = {
            "source": self.source_name,
            "content": f"Data from {self.source_name}",
            "size": len(self.source_name) * 10,
            "fetched_at": time.time(),
        }

        self.emit(
            "data_fetched",
            data=data,
            source=self.source_name,
            timestamp=time.time(),
            flow=self._current_flow,
        )


class DataProcessor(Routine):
    """Process fetched data"""

    def __init__(self, processor_id: str = None):
        super().__init__()
        self.processor_id = processor_id or "unknown"
        self.input_slot = self.define_slot("data_input", handler=self.process_data)
        self.output_event = self.define_event(
            "data_processed", ["result", "processor_id", "processing_time"]
        )
        self._stats["process_count"] = 0

        # Register for serialization
        self.add_serializable_fields(["processor_id"])

    def process_data(self, data: Dict[str, Any], source: str, timestamp: float):
        """Process the fetched data"""
        self._stats["process_count"] = self._stats.get("process_count", 0) + 1

        start_time = time.time()

        # Simulate processing (CPU-bound operation)
        processed = {
            "original": data,
            "processed_by": self.processor_id,
            "processing_time": time.time() - start_time,
            "enhanced": True,
            "metadata": {"source": source, "timestamp": timestamp, "processor": self.processor_id},
        }

        processing_time = time.time() - start_time

        self.emit(
            "data_processed",
            result=processed,
            processor_id=self.processor_id,
            processing_time=processing_time,
            flow=self._current_flow,
        )


class DataAggregator(Routine):
    """Aggregate results from multiple processors"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot(
            "processed_data", handler=self.aggregate, merge_strategy="append"
        )
        self.output_event = self.define_event("aggregated", ["final_result", "total_count"])
        self._stats["aggregation_count"] = 0
        self._collected_results = []

    def aggregate(self, result: Dict[str, Any], processor_id: str, processing_time: float):
        """Aggregate processed results"""
        self._stats["aggregation_count"] = self._stats.get("aggregation_count", 0) + 1

        self._collected_results.append(
            {"result": result, "processor_id": processor_id, "processing_time": processing_time}
        )

        # Emit aggregated result when all expected results are collected
        # In a real scenario, you might wait for a specific count
        if len(self._collected_results) >= 3:  # Expecting 3 processors
            final_result = {
                "results": self._collected_results,
                "total_count": len(self._collected_results),
                "aggregated_at": time.time(),
            }

            self.emit(
                "aggregated",
                final_result=final_result,
                total_count=len(self._collected_results),
                flow=self._current_flow,
            )


class ResultFormatter(Routine):
    """Format the final aggregated result"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("aggregated_input", handler=self.format_result)
        self.final_output = None

    def format_result(self, final_result: Dict[str, Any], total_count: int):
        """Format the final result for output"""
        self.final_output = {
            "summary": {
                "total_results": total_count,
                "formatted_at": time.time(),
                "status": "success",
            },
            "data": final_result,
        }


class TriggerRoutine(Routine):
    """Trigger the concurrent data fetching process"""

    def __init__(self):
        super().__init__()
        self.output_event = self.define_event("trigger_fetch", ["task_id"])

    def __call__(self, task_id: str = "default_task"):
        """Trigger the concurrent fetching"""
        self.emit("trigger_fetch", task_id=task_id, flow=self._current_flow)


# ============================================================================
# Flow Creation Functions
# ============================================================================


def create_concurrent_flow(max_workers: int = 5) -> Flow:
    """Create a flow with concurrent execution strategy"""
    flow = Flow(
        flow_id="concurrent_data_processing",
        execution_strategy="concurrent",
        max_workers=max_workers,
    )

    # Create routines
    trigger = TriggerRoutine()
    fetcher1 = DataFetcher("API_Server_1", delay=0.2)
    fetcher2 = DataFetcher("API_Server_2", delay=0.2)
    fetcher3 = DataFetcher("Database", delay=0.25)
    processor1 = DataProcessor("processor_1")
    processor2 = DataProcessor("processor_2")
    processor3 = DataProcessor("processor_3")
    aggregator = DataAggregator()
    formatter = ResultFormatter()

    # Add routines to flow
    trigger_id = flow.add_routine(trigger, "trigger")
    f1_id = flow.add_routine(fetcher1, "fetcher_1")
    f2_id = flow.add_routine(fetcher2, "fetcher_2")
    f3_id = flow.add_routine(fetcher3, "fetcher_3")
    p1_id = flow.add_routine(processor1, "processor_1")
    p2_id = flow.add_routine(processor2, "processor_2")
    p3_id = flow.add_routine(processor3, "processor_3")
    agg_id = flow.add_routine(aggregator, "aggregator")
    fmt_id = flow.add_routine(formatter, "formatter")

    # Connect routines
    # Trigger -> All fetchers (concurrent)
    flow.connect(trigger_id, "trigger_fetch", f1_id, "trigger")
    flow.connect(trigger_id, "trigger_fetch", f2_id, "trigger")
    flow.connect(trigger_id, "trigger_fetch", f3_id, "trigger")

    # Fetchers -> Processors (concurrent)
    flow.connect(f1_id, "data_fetched", p1_id, "data_input")
    flow.connect(f2_id, "data_fetched", p2_id, "data_input")
    flow.connect(f3_id, "data_fetched", p3_id, "data_input")

    # Processors -> Aggregator (concurrent)
    flow.connect(p1_id, "data_processed", agg_id, "processed_data")
    flow.connect(p2_id, "data_processed", agg_id, "processed_data")
    flow.connect(p3_id, "data_processed", agg_id, "processed_data")

    # Aggregator -> Formatter
    flow.connect(agg_id, "aggregated", fmt_id, "aggregated_input")

    return flow


def create_sequential_flow() -> Flow:
    """Create a flow with sequential execution strategy for comparison"""
    flow = Flow(
        flow_id="sequential_data_processing", execution_strategy="sequential", max_workers=1
    )

    # Same structure as concurrent flow
    trigger = TriggerRoutine()
    fetcher1 = DataFetcher("API_Server_1", delay=0.2)
    fetcher2 = DataFetcher("API_Server_2", delay=0.2)
    fetcher3 = DataFetcher("Database", delay=0.25)
    processor1 = DataProcessor("processor_1")
    processor2 = DataProcessor("processor_2")
    processor3 = DataProcessor("processor_3")
    aggregator = DataAggregator()
    formatter = ResultFormatter()

    trigger_id = flow.add_routine(trigger, "trigger")
    f1_id = flow.add_routine(fetcher1, "fetcher_1")
    f2_id = flow.add_routine(fetcher2, "fetcher_2")
    f3_id = flow.add_routine(fetcher3, "fetcher_3")
    p1_id = flow.add_routine(processor1, "processor_1")
    p2_id = flow.add_routine(processor2, "processor_2")
    p3_id = flow.add_routine(processor3, "processor_3")
    agg_id = flow.add_routine(aggregator, "aggregator")
    fmt_id = flow.add_routine(formatter, "formatter")

    flow.connect(trigger_id, "trigger_fetch", f1_id, "trigger")
    flow.connect(trigger_id, "trigger_fetch", f2_id, "trigger")
    flow.connect(trigger_id, "trigger_fetch", f3_id, "trigger")
    flow.connect(f1_id, "data_fetched", p1_id, "data_input")
    flow.connect(f2_id, "data_fetched", p2_id, "data_input")
    flow.connect(f3_id, "data_fetched", p3_id, "data_input")
    flow.connect(p1_id, "data_processed", agg_id, "processed_data")
    flow.connect(p2_id, "data_processed", agg_id, "processed_data")
    flow.connect(p3_id, "data_processed", agg_id, "processed_data")
    flow.connect(agg_id, "aggregated", fmt_id, "aggregated_input")

    return flow


# ============================================================================
# Test Functions
# ============================================================================


def test_concurrent_execution():
    """Test concurrent execution"""
    print("=" * 70)
    print("Test 1: Concurrent Execution")
    print("=" * 70)

    flow = create_concurrent_flow(max_workers=5)

    print(f"Flow ID: {flow.flow_id}")
    print(f"Execution Strategy: {flow.execution_strategy}")
    print(f"Max Workers: {flow.max_workers}")
    print(f"Routines: {len(flow.routines)}")
    print(f"Connections: {len(flow.connections)}")
    print()

    # Execute
    start_time = time.time()
    job_state = flow.execute("trigger", entry_params={"task_id": "concurrent_task_1"})
    execution_time = time.time() - start_time

    print(f"Execution Time: {execution_time:.3f} seconds")
    print(f"Job Status: {job_state.status}")
    print()

    # Wait for all concurrent tasks to complete
    # In concurrent mode, tasks run asynchronously, so we need to wait
    # Using Flow.wait_for_completion() is the proper way to wait
    if flow.execution_strategy == "concurrent":
        flow.wait_for_completion(timeout=2.0)

    # Check results
    formatter = flow.routines["formatter"]
    if formatter.final_output:
        print("Final Output:")
        print(json.dumps(formatter.final_output, indent=2, default=str))
    else:
        print("Final output not yet available (concurrent execution may still be running)")

    print()


def test_sequential_vs_concurrent():
    """Compare sequential vs concurrent execution performance"""
    print("=" * 70)
    print("Test 2: Sequential vs Concurrent Performance Comparison")
    print("=" * 70)

    results = {}

    for strategy in ["sequential", "concurrent"]:
        print(f"\n--- {strategy.upper()} Execution ---")

        if strategy == "concurrent":
            flow = create_concurrent_flow(max_workers=5)
        else:
            flow = create_sequential_flow()

        start_time = time.time()
        job_state = flow.execute("trigger", entry_params={"task_id": f"{strategy}_task"})
        execution_time = time.time() - start_time

        # Wait for completion (concurrent tasks run asynchronously)
        if strategy == "concurrent":
            flow.wait_for_completion(timeout=2.0)  # Elegant way to wait for concurrent tasks

        results[strategy] = execution_time
        print(f"Execution Time: {execution_time:.3f} seconds")
        print(f"Job Status: {job_state.status}")

        # Clean up: shutdown concurrent flows
        if strategy == "concurrent":
            flow.shutdown(wait=False)  # Tasks already completed

    print("\n" + "=" * 70)
    print("Performance Comparison:")
    print("=" * 70)
    sequential_time = results["sequential"]
    concurrent_time = results["concurrent"]
    speedup = sequential_time / concurrent_time if concurrent_time > 0 else 0

    print(f"Sequential: {sequential_time:.3f} seconds")
    print(f"Concurrent: {concurrent_time:.3f} seconds")
    print(f"Speedup: {speedup:.2f}x")
    print(
        f"Time Saved: {sequential_time - concurrent_time:.3f} seconds ({((sequential_time - concurrent_time) / sequential_time * 100):.1f}%)"
    )
    print()


def test_concurrent_with_error_handling():
    """Test concurrent execution with error handling"""
    print("=" * 70)
    print("Test 3: Concurrent Execution with Error Handling")
    print("=" * 70)

    flow = create_concurrent_flow(max_workers=5)
    flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))

    # Create a failing fetcher
    class FailingFetcher(DataFetcher):
        def fetch_data(self, **kwargs):
            if self.source_name == "API_Server_2":
                raise ValueError("Simulated network error")
            super().fetch_data(**kwargs)

    failing_fetcher = FailingFetcher("API_Server_2", delay=0.1)
    flow.routines["fetcher_2"] = failing_fetcher

    start_time = time.time()
    job_state = flow.execute("trigger", entry_params={"task_id": "error_test_task"})
    execution_time = time.time() - start_time

    # Wait for concurrent tasks to complete
    if flow.execution_strategy == "concurrent":
        flow.wait_for_completion(timeout=2.0)

    print(f"Execution Time: {execution_time:.3f} seconds")
    print(f"Job Status: {job_state.status}")

    # Check error stats
    if "errors" in failing_fetcher._stats:
        print(f"Errors recorded: {len(failing_fetcher._stats['errors'])}")

    print()


def test_serialization():
    """Test serialization of concurrent flow"""
    print("=" * 70)
    print("Test 4: Serialization of Concurrent Flow")
    print("=" * 70)

    flow = create_concurrent_flow(max_workers=8)

    # Serialize
    data = flow.serialize()
    print(f"Serialized data size: {len(json.dumps(data))} bytes")
    print(f"Execution strategy in data: {data.get('execution_strategy')}")
    print(f"Max workers in data: {data.get('max_workers')}")

    # Deserialize
    new_flow = Flow()
    new_flow.deserialize(data)

    print(f"Deserialized Flow ID: {new_flow.flow_id}")
    print(f"Deserialized Execution Strategy: {new_flow.execution_strategy}")
    print(f"Deserialized Max Workers: {new_flow.max_workers}")
    print(f"Deserialized Routines: {len(new_flow.routines)}")
    print(f"Deserialized Connections: {len(new_flow.connections)}")

    # Verify it still works
    start_time = time.time()
    job_state = new_flow.execute("trigger", entry_params={"task_id": "deserialized_task"})
    execution_time = time.time() - start_time

    # Wait for concurrent tasks to complete
    if new_flow.execution_strategy == "concurrent":
        new_flow.wait_for_completion(timeout=2.0)

    print(f"Execution Time (after deserialization): {execution_time:.3f} seconds")
    print(f"Job Status: {job_state.status}")
    print()


def test_dynamic_strategy_switch():
    """Test dynamically switching execution strategy"""
    print("=" * 70)
    print("Test 5: Dynamic Strategy Switching")
    print("=" * 70)

    flow = Flow()

    # Start with sequential
    flow.set_execution_strategy("sequential")
    print(f"Initial Strategy: {flow.execution_strategy}")

    # Switch to concurrent
    flow.set_execution_strategy("concurrent", max_workers=10)
    print(f"After Switch: {flow.execution_strategy}, Max Workers: {flow.max_workers}")

    # Switch back
    flow.set_execution_strategy("sequential")
    print(f"After Switch Back: {flow.execution_strategy}")
    print()


# ============================================================================
# Main
# ============================================================================


def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("Routilux Concurrent Execution Demo")
    print("=" * 70)
    print()

    try:
        test_concurrent_execution()
        test_sequential_vs_concurrent()
        test_concurrent_with_error_handling()
        test_serialization()
        test_dynamic_strategy_switch()

        print("=" * 70)
        print("All tests completed successfully!")
        print("=" * 70)

        # Best Practice: Properly manage Flow lifecycle
        # In production code, you should:
        # 1. Call flow.wait_for_completion() after execution to wait for all tasks
        # 2. Call flow.shutdown() when done to clean up resources
        # 3. Use context managers or try/finally blocks to ensure cleanup
        #
        # Example:
        #   flow = Flow(execution_strategy="concurrent")
        #   try:
        #       job_state = flow.execute(...)
        #       flow.wait_for_completion(timeout=10.0)
        #   finally:
        #       flow.shutdown(wait=True)
        #
        # For this demo, all flows are local variables and will be cleaned up
        # when they go out of scope. The ThreadPoolExecutor will be shut down
        # when the Flow object is garbage collected, but it's better to explicitly
        # call shutdown() for proper resource management.

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
