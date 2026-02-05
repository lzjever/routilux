# P2 Improvements Implementation Plan (A02)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete all P2 (medium priority) improvements from code review: delete unused features, improve documentation, add benchmarks.

**Architecture:** Systematic cleanup and enhancement across connection logic (remove parameter mapping), routine API (remove __call__), documentation (real-world examples), architecture design (diagrams), and performance (pytest-benchmark).

**Tech Stack:** Python 3.8+, pytest, pytest-benchmark, Sphinx, Graphviz

---

## Overview

This plan addresses 5 P2 issues from the code review:

| Task | Issue | Effort |
|------|-------|--------|
| 1 | Delete complex parameter mapping (P2-1) | 2 hours |
| 2 | Delete `__call__` method (P2-2) | 1 hour |
| 3 | Add performance benchmarks (P2-5) | 3 hours |
| 4 | Write real-world examples (P2-3) | 3 hours |
| 5 | Create architecture docs (P2-4) | 4 hours |

**Total Estimated Time:** ~13 hours

**Execution Order:** Tasks 1 → 2 → 5 → 3 → 4 (code cleanup first, then benchmarks, then docs)

---

# Phase 1: Code Cleanup (P2-1 + P2-2)

## Task 1: Delete Complex Parameter Mapping (P2-1)

**Issue:** P2-1 - Complex parameter mapping logic in connection.py:249-266

**Files:**
- Modify: `routilux/connection.py`
- Test: `tests/test_connection.py`

**Step 1: Read current connection.py to understand parameter mapping**

Run: `cat routilux/connection.py`

Observe: Look for `_map_parameters` method around lines 249-266

**Step 2: Write test for simplified connection (without parameter mapping)**

First, run existing tests to see current behavior:

Run: `uv run pytest tests/test_connection.py -v`

Expected: All current tests pass

**Step 3: Identify code to delete**

Look for the parameter mapping pattern:

```python
# This pattern should be deleted:
def _map_parameters(self, data: Dict[str, Any], signature: inspect.Signure) -> Dict[str, Any]:
    # ... complex mapping logic ...
```

**Step 4: Delete _map_parameters method and its usage**

Edit `routilux/connection.py`:

1. Remove the `_map_parameters` method entirely
2. Remove any calls to `_map_parameters` in the `connect` or `emit` logic
3. Simplify the connection logic to pass data directly

**Step 5: Update connection logic to simple data pass-through**

The simplified `connect` method should look like:

```python
def connect(self, event: Event, slot: Slot) -> "Connection":
    """Connect an event to a slot.

    Args:
        event: Source event.
        slot: Target slot.

    Returns:
        Connection object.

    Raises:
        ConfigurationError: If connecting across different Flows.
    """
    from routilux.exceptions import ConfigurationError

    if slot.routine and slot.routine._flow != self._flow:
        raise ConfigurationError(
            "Cannot connect events across different Flows: "
            f"{event.routine._flow.flow_id} != {slot.routine._flow.flow_id}"
        )

    connection = Connection(event, slot)
    self._connections.append(connection)
    return connection
```

**Step 6: Run tests to ensure nothing broke**

Run: `uv run pytest tests/test_connection.py -v --tb=short`

Expected: All tests pass (or update tests that relied on parameter mapping)

**Step 7: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`

Expected: All tests pass

**Step 8: Commit**

```bash
git add routilux/connection.py tests/test_connection.py
git commit -m "refactor(p2-1): remove complex parameter mapping

Delete _map_parameters method and simplify connection logic.
Data now passes directly from events to slots without
complex parameter transformation.

Simplifies codebase and removes unused complexity.
Follows YAGNI principle.

Fixes: P2-1"
```

---

## Task 2: Delete `__call__` Method from Routine (P2-2)

**Issue:** P2-2 - Deprecated `__call__` method in routine.py causes user confusion

**Files:**
- Modify: `routilux/routine.py`
- Test: `tests/test_routine.py`

**Step 1: Locate `__call__` method in routine.py**

Run: `grep -n "__call__" routilux/routine.py`

Observe: Line number and content of `__call__` method

**Step 2: Read the `__call__` method to understand what it does**

Run: `sed -n '<start_line>,<end_line>p' routilux/routine.py`

Observe: What the method does (likely calls Flow.execute internally)

**Step 3: Check if any tests use `__call__`**

Run: `grep -r "routine(" tests/ | grep -v "define_routine\|Routine("`

Observe: Which tests might be calling routines directly

**Step 4: Delete the `__call__` method**

Edit `routilux/routine.py`:

Remove the entire `__call__` method block, including its docstring.

**Step 5: Update any tests that used `__call__`**

If tests were calling `routine()`, update them to use `flow.execute()`:

```python
# Before (if found):
result = routine(**params)

# After:
job_state = flow.execute(routine_id, entry_params=params)
result = job_state.get_output() if job_state.status == "completed" else None
```

**Step 6: Run tests**

Run: `uv run pytest tests/test_routine.py -v --tb=short`

Expected: All tests pass

**Step 7: Run full test suite**

Run: `uv run pytest tests/ -v --tb=short`

Expected: All tests pass

**Step 8: Commit**

```bash
git add routilux/routine.py tests/test_routine.py
git commit -m "refactor(p2-2): remove deprecated __call__ method

Delete Routine.__call__ to enforce proper usage via Flow.execute().
This prevents user confusion and aligns with architecture:
- Flow is the execution controller
- Routines are components, not executable units

Users must now use:
    flow.execute(routine_id, entry_params={})

Fixes: P2-2"
```

---

# Phase 2: Performance Benchmarks (P2-5)

## Task 3: Add Performance Benchmark Suite (P2-5)

**Issue:** P2-5 - No performance benchmarks to detect regression

**Files:**
- Create: `tests/benchmarks/__init__.py`
- Create: `tests/benchmarks/test_emit_benchmark.py`
- Create: `tests/benchmarks/test_slot_benchmark.py`
- Create: `tests/benchmarks/test_concurrent_benchmark.py`
- Create: `tests/benchmarks/test_serialization_benchmark.py`
- Modify: `pyproject.toml`
- Create: `.github/workflows/benchmark.yml`

**Step 1: Add pytest-benchmark dependency**

Edit `pyproject.toml`, add to `[dependency-groups].dev`:

```toml
[dependency-groups]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
    "mypy>=0.991",
    "build>=0.10.0",
    "pip-audit>=2.6.0",
    "bandit>=1.7.5",
    "safety>=2.3.0",
    "pytest-benchmark>=4.0.0",  # Add this line
]
```

**Step 2: Install new dependency**

Run: `uv sync --group dev`

Expected: No errors

**Step 3: Create benchmarks directory**

Run: `mkdir -p tests/benchmarks`

**Step 4: Create __init__.py for benchmarks**

Create `tests/benchmarks/__init__.py`:

```python
"""Performance benchmarks for Routilux."""
```

**Step 5: Create event emission benchmark**

Create `tests/benchmarks/test_emit_benchmark.py`:

```python
"""Benchmarks for event emission performance."""

import pytest

from routilux import Flow, Routine


class TestEventEmissionBenchmark:
    """Benchmarks for event emission throughput."""

    def test_event_emission_single_event(self, benchmark):
        """Benchmark emitting a single event."""
        flow = Flow("test")
        routine = Routine("emitter")
        flow.add_routine(routine)

        def emit_single():
            routine.emit("output", value=42)

        benchmark(emit_single)

    def test_event_emission_100_events(self, benchmark):
        """Benchmark emitting 100 events sequentially."""
        flow = Flow("test")
        routine = Routine("emitter")
        flow.add_routine(routine)

        def emit_100():
            for i in range(100):
                routine.emit("output", value=i)

        benchmark(emit_100)

    def test_event_emission_1000_events(self, benchmark):
        """Benchmark emitting 1000 events sequentially."""
        flow = Flow("test")
        routine = Routine("emitter")
        flow.add_routine(routine)

        def emit_1000():
            for i in range(1000):
                routine.emit("output", value=i)

        benchmark(emit_1000)

    def test_event_emission_with_data_update(self, benchmark):
        """Benchmark emitting and updating event data."""
        flow = Flow("test")
        routine = Routine("emitter")
        flow.add_routine(routine)

        event = routine.emit("output")

        def update_event():
            for i in range(100):
                event.update_data(value=i, status=f"step_{i}")

        benchmark(update_event)
```

**Step 6: Create slot receive benchmark**

Create `tests/benchmarks/test_slot_benchmark.py`:

```python
"""Benchmarks for slot receive performance."""

import pytest

from routilux import Routine


class TestSlotReceiveBenchmark:
    """Benchmarks for slot data reception throughput."""

    def test_slot_receive_single(self, benchmark):
        """Benchmark receiving a single event."""
        routine = Routine("receiver")

        received = []

        def handler(data):
            received.append(data)

        slot = routine.define_slot("input", handler=handler)

        def receive_single():
            slot.receive({"value": 42})

        benchmark(receive_single)

    def test_slot_receive_100_events(self, benchmark):
        """Benchmark receiving 100 events."""
        routine = Routine("receiver")

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
        routine = Routine("receiver")

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
        routine = Routine("receiver")

        received = []

        def handler(data):
            received.append(data)

        slot = routine.define_slot("input", handler=handler, merge_strategy="override")

        def receive_with_override():
            for i in range(100):
                slot.receive({"value": i})

        benchmark(receive_with_override)
```

**Step 7: Create concurrent execution benchmark**

Create `tests/benchmarks/test_concurrent_benchmark.py`:

```python
"""Benchmarks for concurrent execution performance."""

import pytest

from routilux import Flow, Routine


class TestConcurrentBenchmark:
    """Benchmarks for concurrent workflow execution."""

    def test_sequential_execution_baseline(self, benchmark):
        """Baseline benchmark for sequential execution."""
        flow = Flow("test", execution_mode="sequential")

        for i in range(5):
            routine = Routine(f"routine_{i}")
            flow.add_routine(routine)
            routine.define_slot("input", handler=lambda d: None)

        job_state = flow.execute("routine_0", entry_params={})
        flow.wait_for_completion(job_state, timeout=10.0)

        # Benchmark setup
        flow2 = Flow("test2", execution_mode="sequential")
        for i in range(5):
            routine = Routine(f"routine_{i}")
            flow2.add_routine(routine)
            routine.define_slot("input", handler=lambda d: None)

        def execute_sequential():
            js = flow2.execute("routine_0", entry_params={})
            flow2.wait_for_completion(js, timeout=10.0)

        benchmark(execute_sequential)

    def test_concurrent_execution_speedup(self, benchmark):
        """Benchmark for concurrent execution."""
        flow = Flow("test", execution_mode="concurrent", max_workers=4)

        for i in range(5):
            routine = Routine(f"routine_{i}")
            flow.add_routine(routine)
            routine.define_slot("input", handler=lambda d: None)

        job_state = flow.execute("routine_0", entry_params={})
        flow.wait_for_completion(job_state, timeout=10.0)

        # Benchmark setup
        flow2 = Flow("test2", execution_mode="concurrent", max_workers=4)
        for i in range(5):
            routine = Routine(f"routine_{i}")
            flow2.add_routine(routine)
            routine.define_slot("input", handler=lambda d: None)

        def execute_concurrent():
            js = flow2.execute("routine_0", entry_params={})
            flow2.wait_for_completion(js, timeout=10.0)

        benchmark(execute_concurrent)
```

**Step 8: Create serialization benchmark**

Create `tests/benchmarks/test_serialization_benchmark.py`:

```python
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

        def deserialize():
            JobState.deserialize(serialized)

        benchmark(deserialize)
```

**Step 9: Run benchmarks**

Run: `uv run pytest tests/benchmarks/ -v --benchmark-only`

Expected: All benchmarks run successfully with timing output

**Step 10: Create GitHub workflow for benchmarks**

Create `.github/workflows/benchmark.yml`:

```yaml
name: Benchmark

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  benchmark:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install uv
        uses: astral-sh/setup-uv@v4
        with:
          version: "latest"

      - name: Install dependencies
        run: |
          uv sync --group dev

      - name: Run benchmarks
        run: |
          uv run pytest tests/benchmarks/ \
            --benchmark-only \
            --benchmark-json=benchmark-results.json

      - name: Upload benchmark results
        uses: actions/upload-artifact@v4
        with:
          name: benchmark-results
          path: benchmark-results.json
          retention-days: 30
```

**Step 11: Run full test suite to ensure no conflicts**

Run: `uv run pytest tests/ -v --tb=short`

Expected: All tests pass

**Step 12: Commit**

```bash
git add tests/benchmarks/ pyproject.toml .github/workflows/benchmark.yml
git commit -m "feat(p2-5): add performance benchmark suite

Add pytest-benchmark tests for key operations:
- Event emission throughput
- Slot receive performance
- Concurrent execution speedup
- JobState serialization/deserialization

Includes CI workflow to track performance over time.

Fixes: P2-5"
```

---

# Phase 3: Documentation (P2-3 + P2-4)

## Task 4: Write Real-World Examples (P2-3)

**Issue:** P2-3 - Documentation examples too simple (hello world only)

**Files:**
- Create: `examples/data_pipeline.py`
- Create: `examples/async_orchestration.py`
- Create: `examples/long_running_workflow.py`
- Create: `examples/error_handling.py`
- Modify: `README.md`

**Step 1: Create examples directory structure**

Run: `mkdir -p examples`

**Step 2: Create data pipeline example**

Create `examples/data_pipeline.py`:

```python
"""Data Processing Pipeline Example.

This example demonstrates a realistic data processing workflow:
1. Ingest data from multiple sources
2. Validate and clean data
3. Transform data
4. Branch based on data quality
5. Aggregate results
"""

from routilux import Flow, Routine
from routilux.exceptions import RoutiluxError


def main():
    """Run the data pipeline example."""
    # Create flow with error handling
    flow = Flow("data_pipeline", execution_mode="sequential")

    # 1. Data Ingestion Routine
    ingestor = Routine("ingest_data")
    flow.add_routine(ingestor)

    @ingestor.after_execution
    def log_ingestion(job_state):
        print(f"Ingested {job_state.shared_data.get('record_count', 0)} records")

    # 2. Validation Routine
    validator = Routine("validate_data")
    flow.add_routine(validator)

    validation_errors = []

    def validate_handler(data):
        """Validate incoming data."""
        errors = []
        if not data.get("records"):
            errors.append("No records provided")
        if not isinstance(data.get("records"), list):
            errors.append("Records must be a list")

        if errors:
            validation_errors.extend(errors)
            raise RoutiluxError(f"Validation failed: {errors}")

        return {"valid": True, "record_count": len(data["records"])}

    validator.define_slot("input", handler=validate_handler)

    # 3. Transformation Routine
    transformer = Routine("transform_data")
    flow.add_routine(transformer)

    def transform_handler(data):
        """Transform validated data."""
        records = data.get("records", [])
        transformed = []

        for record in records:
            # Example transformation: normalize and enrich
            transformed_record = {
                "id": record.get("id"),
                "name": record.get("name", "").strip().lower(),
                "value": float(record.get("value", 0)),
                "processed": True,
            }
            transformed.append(transformed_record)

        return {"transformed": transformed}

    transformer.define_slot("input", handler=transform_handler)

    # 4. Quality Check Routine (with branching)
    quality_checker = Routine("check_quality")
    flow.add_routine(quality_checker)

    quality_results = []

    def quality_check_handler(data):
        """Check data quality and route accordingly."""
        transformed = data.get("transformed", [])

        # Calculate quality metrics
        valid_count = sum(1 for r in transformed if r.get("value", 0) > 0)
        quality_score = valid_count / len(transformed) if transformed else 0

        quality_results.append({
            "score": quality_score,
            "total": len(transformed),
            "valid": valid_count,
        })

        # Emit to different paths based on quality
        if quality_score >= 0.8:
            return {"quality": "high", "route": "publish"}
        elif quality_score >= 0.5:
            return {"quality": "medium", "route": "review"}
        else:
            return {"quality": "low", "route": "reject"}

    quality_checker.define_slot("input", handler=quality_check_handler)

    # 5. Aggregation Routine
    aggregator = Routine("aggregate_results")
    flow.add_routine(aggregator)

    def aggregate_handler(data):
        """Aggregate final results."""
        print(f"Quality: {data.get('quality')}, Route: {data.get('route')}")
        return {"aggregated": True}

    aggregator.define_slot("input", handler=aggregate_handler)

    # Connect the pipeline
    raw_data = {
        "records": [
            {"id": 1, "name": "  Alice  ", "value": "100"},
            {"id": 2, "name": "BOB", "value": "200"},
            {"id": 3, "name": "Charlie", "value": "invalid"},
        ]
    }

    # Execute pipeline
    try:
        job_state = flow.execute("ingest_data", entry_params=raw_data)
        flow.wait_for_completion(job_state, timeout=30.0)

        print(f"Pipeline status: {job_state.status}")
        print(f"Quality results: {quality_results}")

    except RoutiluxError as e:
        print(f"Pipeline error: {e}")


if __name__ == "__main__":
    main()
```

**Step 3: Create async orchestration example**

Create `examples/async_orchestration.py`:

```python
"""Async Task Orchestration Example.

This example demonstrates concurrent task execution:
1. Execute multiple independent tasks in parallel
2. Aggregate results from concurrent tasks
3. Handle timeouts and retries
"""

from routilux import Flow, Routine
import time


def main():
    """Run the async orchestration example."""
    # Create flow with concurrent execution
    flow = Flow("async_orchestration", execution_mode="concurrent", max_workers=4)

    # Task 1: Fetch user data (simulated)
    fetch_user = Routine("fetch_user")
    flow.add_routine(fetch_user)

    def fetch_user_handler(data):
        user_id = data.get("user_id")
        time.sleep(0.5)  # Simulate API call
        return {"user_id": user_id, "name": f"User_{user_id}", "email": f"user{user_id}@example.com"}

    fetch_user.define_slot("input", handler=fetch_user_handler)

    # Task 2: Fetch user orders (simulated)
    fetch_orders = Routine("fetch_orders")
    flow.add_routine(fetch_orders)

    def fetch_orders_handler(data):
        user_id = data.get("user_id")
        time.sleep(0.7)  # Simulate API call
        return {"user_id": user_id, "orders": [1, 2, 3], "total": 150.0}

    fetch_orders.define_slot("input", handler=fetch_orders_handler)

    # Task 3: Fetch user preferences (simulated)
    fetch_preferences = Routine("fetch_preferences")
    flow.add_routine(fetch_preferences)

    def fetch_preferences_handler(data):
        user_id = data.get("user_id")
        time.sleep(0.3)  # Simulate API call
        return {"user_id": user_id, "notifications": True, "theme": "dark"}

    fetch_preferences.define_slot("input", handler=fetch_preferences_handler)

    # Task 4: Aggregator
    aggregator = Routine("aggregate_profile")
    flow.add_routine(aggregator)

    profile_data = {}

    def aggregate_handler(data):
        # Collect data from all sources
        if "name" in data:
            profile_data["user"] = data
        elif "orders" in data:
            profile_data["orders"] = data
        elif "notifications" in data:
            profile_data["preferences"] = data

        # Check if we have all data
        if len(profile_data) == 3:
            print("Profile complete!")
            print(f"User: {profile_data.get('user', {}).get('name')}")
            print(f"Orders: {len(profile_data.get('orders', {}).get('orders', []))}")
            print(f"Theme: {profile_data.get('preferences', {}).get('theme')}")

        return profile_data

    aggregator.define_slot("input", handler=aggregate_handler, merge_strategy="append")

    # Start execution
    user_id = 12345
    job_state = flow.execute("fetch_user", entry_params={"user_id": user_id})

    # Wait for completion
    flow.wait_for_completion(job_state, timeout=10.0)

    print(f"Execution status: {job_state.status}")
    print(f"Final profile: {profile_data}")


if __name__ == "__main__":
    main()
```

**Step 4: Create long-running workflow example**

Create `examples/long_running_workflow.py`:

```python
"""Long-Running Workflow Example.

This example demonstrates:
1. Pause and resume workflow execution
2. State persistence
3. Checkpoints for recovery
"""

from routilux import Flow, Routine, JobState
import json


def main():
    """Run the long-running workflow example."""
    # Create flow
    flow = Flow("long_running_process")

    # Step 1: Initialize
    initializer = Routine("initialize")
    flow.add_routine(initializer)

    def init_handler(data):
        print("Initializing long-running process...")
        return {"step": 1, "total_steps": 5, "data": []}

    initializer.define_slot("input", handler=init_handler)

    # Step 2-4: Processing steps
    for i in range(2, 5):
        processor = Routine(f"process_step_{i}")
        flow.add_routine(processor)

        def make_handler(step_num):
            def handler(data):
                print(f"Processing step {step_num}...")
                current_data = data.get("data", [])
                current_data.append(f"result_step_{step_num}")
                return {"step": step_num, "data": current_data}
            return handler

        processor.define_slot("input", handler=make_handler(i))

    # Step 5: Finalize
    finalizer = Routine("finalize")
    flow.add_routine(finalizer)

    def finalize_handler(data):
        print("Finalizing process...")
        results = data.get("data", [])
        print(f"Complete! Processed {len(results)} steps")
        return {"complete": True, "results": results}

    finalizer.define_slot("input", handler=finalize_handler)

    # Option 1: Execute with persistence
    print("\n=== Example 1: Execute and pause ===")
    job_state = flow.execute("initialize", entry_params={})

    # Save state after first step
    serialized = job_state.serialize()
    print(f"Saved state: {len(json.dumps(serialized))} bytes")

    # Simulate system restart by loading state
    print("\n=== Example 2: Resume from saved state ===")
    restored = JobState.deserialize(serialized)
    print(f"Restored job state: {restored.job_id}")
    print(f"Current step: {restored.shared_data.get('step')}")

    # Continue execution
    flow.wait_for_completion(job_state, timeout=30.0)

    print(f"\nFinal status: {job_state.status}")
    print(f"Results: {job_state.shared_data}")


if __name__ == "__main__":
    main()
```

**Step 5: Create error handling example**

Create `examples/error_handling.py`:

```python
"""Error Handling Patterns Example.

This example demonstrates:
1. Exception handling in routines
2. Retry logic
3. Fallback mechanisms
"""

from routilux import Flow, Routine
from routilux.exceptions import ExecutionError, RoutiluxError
import random


def main():
    """Run the error handling example."""
    # Example 1: Basic error handling
    print("\n=== Example 1: Basic Error Handling ===")

    flow1 = Flow("error_handling_flow")

    risky_routine = Routine("risky_operation")
    flow1.add_routine(risky_routine)

    def risky_handler(data):
        """Handler that may fail."""
        if random.random() < 0.3:  # 30% chance of failure
            raise ExecutionError("Random failure occurred", routine_id="risky_operation")
        return {"success": True, "value": data.get("input", 0) * 2}

    risky_routine.define_slot("input", handler=risky_handler)

    # Execute multiple times to show error handling
    for attempt in range(5):
        try:
            job_state = flow1.execute("risky_operation", entry_params={"input": attempt})
            flow1.wait_for_completion(job_state, timeout=10.0)

            if job_state.status == "completed":
                print(f"Attempt {attempt + 1}: Success")
            else:
                print(f"Attempt {attempt + 1}: Failed with status {job_state.status}")

        except RoutiluxError as e:
            print(f"Attempt {attempt + 1}: Caught error - {e}")

    # Example 2: Retry pattern with counter
    print("\n=== Example 2: Retry Pattern ===")

    flow2 = Flow("retry_flow")

    retry_routine = Routine("retry_operation")
    flow2.add_routine(retry_routine)

    attempt_count = {"value": 0}
    max_retries = 3

    def retry_handler(data):
        """Handler with built-in retry logic."""
        attempt_count["value"] += 1

        if attempt_count["value"] < max_retries:
            print(f"Attempt {attempt_count['value']} failed, retrying...")
            raise ExecutionError("Temporary failure", routine_id="retry_operation")

        print(f"Attempt {attempt_count['value']} succeeded!")
        return {"success": True, "attempts": attempt_count["value"]}

    retry_routine.define_slot("input", handler=retry_handler)

    job_state2 = flow2.execute("retry_operation", entry_params={})
    flow2.wait_for_completion(job_state2, timeout=30.0)

    print(f"Final status: {job_state2.status}")
    print(f"Execution history: {len(job_state2.get_execution_history())} entries")

    # Example 3: Fallback mechanism
    print("\n=== Example 3: Fallback Mechanism ===")

    flow3 = Flow("fallback_flow")

    primary = Routine("primary_service")
    fallback = Routine("fallback_service")
    flow3.add_routine(primary)
    flow3.add_routine(fallback)

    service_result = {"value": None}

    def primary_handler(data):
        """Primary service that may fail."""
        if random.random() < 0.5:
            raise ExecutionError("Primary service unavailable")
        service_result["value"] = "primary"
        return {"source": "primary", "data": data}

    def fallback_handler(data):
        """Fallback service."""
        service_result["value"] = "fallback"
        print("Using fallback service...")
        return {"source": "fallback", "data": data}

    primary.define_slot("input", handler=primary_handler)
    fallback.define_slot("input", handler=fallback_handler)

    # Try primary first
    try:
        job_state3 = flow3.execute("primary_service", entry_params={"test": True})
        flow3.wait_for_completion(job_state3, timeout=10.0)
    except ExecutionError:
        # Fall back to secondary
        print("Primary failed, trying fallback...")
        job_state3 = flow3.execute("fallback_service", entry_params={"test": True})
        flow3.wait_for_completion(job_state3, timeout=10.0)

    print(f"Result from: {service_result['value']}")


if __name__ == "__main__":
    main()
```

**Step 6: Update README with new examples**

Edit `README.md`, add "Examples" section after "Quick Start":

```markdown
## Examples

The `examples/` directory contains real-world usage patterns:

### Data Processing Pipeline
Multi-stage data processing with validation, transformation, and quality checks.

```bash
python examples/data_pipeline.py
```

### Async Task Orchestration
Concurrent execution of independent tasks with result aggregation.

```bash
python examples/async_orchestration.py
```

### Long-Running Workflow
Pause/resume execution with state persistence and recovery.

```bash
python examples/long_running_workflow.py
```

### Error Handling Patterns
Exception handling, retry logic, and fallback mechanisms.

```bash
python examples/error_handling.py
```

Each example is fully executable and demonstrates practical Routilux patterns.
```

**Step 7: Test all examples**

Run each example to ensure they work:

```bash
uv run python examples/data_pipeline.py
uv run python examples/async_orchestration.py
uv run python examples/long_running_workflow.py
uv run python examples/error_handling.py
```

Expected: All examples run without errors

**Step 8: Commit**

```bash
git add examples/ README.md
git commit -m "docs(p2-3): add real-world usage examples

Add comprehensive examples demonstrating practical patterns:
- data_pipeline.py: Multi-stage data processing with validation
- async_orchestration.py: Concurrent task execution
- long_running_workflow.py: Pause/resume with state persistence
- error_handling.py: Retry patterns and fallback mechanisms

Update README with examples section.

Fixes: P2-3"
```

---

## Task 5: Create Architecture Design Documentation (P2-4)

**Issue:** P2-4 - Missing architecture design documentation

**Files:**
- Create: `docs/source/design/architecture.rst`
- Create: `docs/source/diagrams/` (for Graphviz diagrams)

**Step 1: Create diagrams directory**

Run: `mkdir -p docs/source/diagrams`

**Step 2: Create architecture documentation**

Create `docs/source/design/architecture.rst`:

```rst
Architecture Design
===================

This document describes the architecture of Routilux, including
component relationships, data flow, and design decisions.

Overview
--------

Routilux is an **event-driven workflow orchestration framework** for Python.
It enables developers to compose complex workflows from reusable components
called Routines, connected via Events and Slots.

Key Design Principles:

- **Event-Driven**: Components communicate through events, not direct calls
- **Serializable**: All state can be serialized for pause/resume
- **Concurrent**: Built-in support for parallel execution
- **Explicit**: Data flow and dependencies are visible

Core Abstractions
-----------------

Flow
~~~~

The Flow is the **orchestration container** that manages:

- Routine lifecycle and registration
- Event-to-Slot connections
- Execution mode (sequential/concurrent)
- JobState creation and management

**Responsibilities:**

- Add/remove routines
- Create event-to-slot connections
- Execute workflows
- Wait for completion

**Invariants:**

- A Flow has a unique flow_id
- All routines in a Flow share the same Flow reference
- Events cannot cross Flow boundaries

Routine
~~~~~~~

A Routine is a **reusable workflow component** that:

- Defines input Slots and output Events
- Contains business logic via Slot handlers
- Can be configured with parameters

**Responsibilities:**

- Emit events with data
- Define input slots with handlers
- Store configuration parameters
- Register lifecycle hooks

**Invariants:**

- A Routine belongs to exactly one Flow
- Routine IDs are unique within a Flow
- Events are uniquely named per Routine

Event
~~~~~

An Event represents a **data emission point** in a Routine.

**Responsibilities:**

- Store event name and data
- Maintain reference to parent Routine
- Support data updates

Slot
~~~~

A Slot represents a **data consumption point** in a Routine.

**Responsibilities:**

- Receive data from connected Events
- Merge data based on strategy (override/append)
- Invoke handler function
- Record execution in JobState

**Merge Strategies:**

- **override**: Last write wins (default)
- **append**: Accumulate all values in a list

JobState
~~~~~~~~

JobState is the **execution state container** for a workflow run.

**Responsibilities:**

- Track current status (running/completed/failed/paused)
- Store Routine execution states
- Maintain execution history
- Support pause/resume
- Serializable for persistence

**Retention Policies:**

- ``max_history_size``: Limit history entries (default: 1000)
- ``history_ttl_seconds``: Remove old entries (default: 3600)

Component Diagram
-----------------

.. graphviz::
   :name: component-diagram
   :caption: Routilux Component Relationships

   digraph components {
       rankdir=TB;
       node [shape=box, style=rounded];

       Flow [label="Flow\n(Orchestrator)", shape=doublebox];
       Routine [label="Routine\n(Component)"];
       Event [label="Event\n(Emission)"];
       Slot [label="Slot\n(Reception)"];
       JobState [label="JobState\n(Execution State)"];
       Connection [label="Connection\n(Wiring)"];

       Flow -> Routine [label="1..*"];
       Flow -> JobState [label="creates"];
       Routine -> Event [label="0..*"];
       Routine -> Slot [label="0..*"];
       Event -> Connection [label="source"];
       Slot -> Connection [label="target"];
       Connection -> Flow [label="owned by"];
       JobState -> Routine [label="tracks state"];
   }

Data Flow
---------

.. graphviz::
   :name: data-flow-diagram
   :caption: Event Data Flow Through Connection

   digraph dataflow {
       rankdir=LR;
       node [shape=box];

       subgraph source_routine {
           SourceRoutine [label="Source Routine"];
           SourceEvent [label="Event.emit()"];
           SourceRoutine -> SourceEvent;
       }

       subgraph connection {
           Connection [label="Connection"];
           SourceEvent -> Connection [label="data"];
       }

       subgraph target_routine {
           TargetSlot [label="Slot.receive()"];
           Handler [label="Handler Function"];
           TargetRoutine [label="Target Routine"];
           JobState [label="JobState.record()"];

           Connection -> TargetSlot [label="merged data"];
           TargetSlot -> Handler;
           Handler -> JobState;
           JobState -> TargetRoutine [label="state update"];
       }
   }

Execution Flow
--------------

.. graphviz::
   :name: execution-sequence
   :caption: Workflow Execution Sequence

   digraph sequence {
       rankdir=LR;
       node [shape=box];

       User [label="User", shape=ellipse];
       Flow [label="Flow.execute()"];
       JobState [label="JobState"];
       Routine [label="Routine"];
       Slot [label="Slot.receive()"];
       Handler [label="Handler"];
       Event [label="Event.emit()"];
       Connection [label="Connection"];

       User -> Flow [label="call execute()"];
       Flow -> JobState [label="create"];
       Flow -> Routine [label="find entry routine"];
       Routine -> Slot [label="get input slots"];
       Slot -> Handler [label="call with data"];
       Handler -> JobState [label="record execution"];
       Handler -> Event [label="may emit"];
       Event -> Connection [label="propagate"];
       Connection -> Slot [label="deliver to target"];
       Flow -> Flow [label="continue until complete"];
   }

Design Decisions
----------------

Why Event-Driven?
~~~~~~~~~~~~~~~~~

**Decision:** Use events and slots instead of direct function calls.

**Rationale:**

1. **Decoupling**: Routines don't need direct references to each other
2. **Visibility**: Data flow is explicit through connections
3. **Flexibility**: Easy to reconfigure connections
4. **Serialization**: Event-based state is easier to persist

**Trade-offs:**

- Pro: Easier to test and reason about
- Pro: Natural for async/concurrent execution
- Con: More verbose than direct calls
- Con: Slight performance overhead

Why Slots Instead of Direct Handlers?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Decision:** Introduce Slot abstraction between Event and Handler.

**Rationale:**

1. **Merge Strategies**: Slots control how data is combined
2. **Multiple Sources**: Many events can connect to one slot
3. **Validation**: Slot can validate before calling handler
4. **Recording**: Slot automatically records to JobState

**Trade-offs:**

- Pro: Flexible data combination
- Pro: Consistent execution tracking
- Con: Additional abstraction layer
- Con: More concepts to learn

Why Serializable JobState?
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Decision:** All workflow state must be serializable.

**Rationale:**

1. **Pause/Resume**: Users can pause long workflows and resume later
2. **Crash Recovery**: State can be restored after failure
3. **Distributed**: Potential for cross-machine execution
4. **Debugging**: Full execution history available

**Trade-offs:**

- Pro: Resilient to failures
- Pro: Supports long-running workflows
- Con: Cannot use lambdas/closures in handlers
- Con: Serialization overhead

Concurrency Model
-----------------

Routilux supports two execution modes:

**Sequential Mode** (default):

- Routines execute one at a time
- Deterministic execution order
- Easier debugging
- Lower throughput

**Concurrent Mode**:

- Multiple routines execute in parallel
- Thread pool based (configurable workers)
- Higher throughput
- Requires thread-safe handlers

Choosing Between Modes:

.. list-table::
   :header-rows: 1
   :widths: 40 30 30

   * - Scenario
     - Use Sequential
     - Use Concurrent
   * - I/O-bound tasks
     - No
     - Yes (big speedup)
   * - CPU-bound tasks
     - Yes (GIL limitation)
     - Maybe with multiprocessing
   * - Debugging
     - Yes
     - No (harder to trace)
   * - Simple dependencies
     - Either
     - Either
   * - Complex dependencies
     - Yes (avoid deadlocks)
     - No (risk of deadlocks)

Error Handling
--------------

Routilux provides a structured exception hierarchy:

```
RoutiluxError (base)
├── ExecutionError      # Runtime failures
├── SerializationError  # Serialize/deserialize failures
├── ConfigurationError  # Invalid setup
├── StateError          # State inconsistencies
└── SlotHandlerError    # User handler failures
```

Users can:

- Catch ``RoutiluxError`` for all framework errors
- Catch specific types for selective handling
- Inspect ``JobState.execution_history`` for errors

Performance Considerations
---------------------------

**Event Emission**: O(1) - creates Event object, looks up connections

**Slot Receive**: O(n) where n = number of connections to slot

**JobState Serialization**: O(h) where h = history size (use retention policies!)

**Concurrent Speedup**: Up to N workers for I/O-bound tasks

Bottlenecks to avoid:

1. **Unbounded history growth**: Use ``max_history_size`` and ``history_ttl_seconds``
2. **Large data in events**: Keep event data small, use references
3. **Slow handlers**: Profile handlers, optimize hot paths

Future Enhancements
-------------------

Potential improvements (not currently planned):

1. **Distributed execution**: Cross-machine workflow execution
2. **Event versioning**: Schema evolution for event data
3. **Visual debugger**: GUI for workflow visualization
4. **Metrics integration**: OpenTelemetry/Prometheus support

References
----------

- `Code Review <code_review.rst>`_
- `Design Overview <design_overview.rst>`_
- `Optimization Strategies <design_optimization.rst>`_
```

**Step 3: Update design index**

Edit `docs/source/design/index.rst`:

```rst
Design Documentation
====================

.. toctree::
   :maxdepth: 2

   overview
   architecture
   optimization
   code_review
```

**Step 4: Build documentation to verify**

Run: `cd docs && make html`

Expected: No errors, architecture.rst included in output

**Step 5: Commit**

```bash
git add docs/source/design/architecture.rst docs/source/design/index.rst
git commit -m "docs(p2-4): add architecture design documentation

Add comprehensive architecture documentation including:
- Component diagrams (Flow, Routine, Event, Slot, JobState)
- Data flow diagrams
- Execution sequence diagrams
- Design decisions and trade-offs
- Concurrency model comparison
- Error handling patterns
- Performance considerations

Includes Graphviz diagrams for visual understanding.

Fixes: P2-4"
```

---

# Final Phase: Verification

## Task 6: Final Verification

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -v --cov=routilux --cov-report=term-missing`

Expected: All tests pass, coverage maintained

**Step 2: Run linting**

Run: `uv run ruff check routilux/ tests/ examples/`

Expected: No new linting errors

**Step 3: Run type checking**

Run: `uv run mypy routilux/`

Expected: No new type errors

**Step 4: Run benchmarks**

Run: `uv run pytest tests/benchmarks/ --benchmark-only`

Expected: All benchmarks run successfully

**Step 5: Test all examples**

Run: `for f in examples/*.py; do uv run python "$f"; done`

Expected: All examples run without errors

**Step 6: Build documentation**

Run: `cd docs && make clean && make html`

Expected: Documentation builds without errors

**Step 7: Update code review status**

Edit `docs/source/design/code_review.rst`, add P2 completion status:

```rst
P2 Implementation Status (2026-02-05)
-------------------------------------

All P2 issues have been addressed:

.. list-table::
   :widths: 20 30 20 30
   :header-rows: 1

   * - Priority
     - Issue
     - Status
     - Commit
   * - P2-1
     - Complex parameter mapping
     - ✅ Complete
     - refactor(p2-1): remove complex parameter mapping
   * - P2-2
     - Deprecated __call__ method
     - ✅ Complete
     - refactor(p2-2): remove deprecated __call__ method
   * - P2-3
     - Documentation examples too simple
     - ✅ Complete
     - docs(p2-3): add real-world usage examples
   * - P2-4
     - Missing architecture docs
     - ✅ Complete
     - docs(p2-4): add architecture design documentation
   * - P2-5
     - No performance benchmarks
     - ✅ Complete
     - feat(p2-5): add performance benchmark suite

**Overall P2 Completion: 5/5 (100%)**
```

**Step 8: Create summary document**

Create `docs/plans/2026-02-05-p2-improvements-summary.md`:

```markdown
# P2 Improvements Summary

**Date:** 2026-02-05
**Scope:** All P2 (Medium Priority) Issues
**Status:** ✅ Complete (5/5 issues addressed)

## Changes Made

### Code Cleanup (P2-1, P2-2)
- **P2-1**: Removed complex parameter mapping logic from connection.py
- **P2-2**: Deleted deprecated `__call__` method from Routine

### Documentation (P2-3, P2-4)
- **P2-3**: Added 4 real-world examples:
  - data_pipeline.py: Multi-stage processing with validation
  - async_orchestration.py: Concurrent task execution
  - long_running_workflow.py: Pause/resume patterns
  - error_handling.py: Retry and fallback mechanisms
- **P2-4**: Created comprehensive architecture documentation with diagrams

### Performance (P2-5)
- **P2-5**: Added pytest-benchmark suite covering:
  - Event emission throughput
  - Slot receive performance
  - Concurrent execution speedup
  - Serialization/deserialization

## Impact

- **Code Quality**: Removed ~100 lines of unused complex code
- **Maintainability**: Clearer API without confusing `__call__`
- **Documentation**: Real-world examples for practical learning
- **Architecture**: Visual diagrams and design rationale documented
- **Performance**: Baseline metrics for regression detection

## Total Effort

~13 hours across 6 tasks
- Code cleanup: ~3 hours
- Benchmarks: ~3 hours
- Examples: ~3 hours
- Architecture docs: ~4 hours

All following YAGNI, KISS, SOLID principles.
```

**Step 9: Final commit**

```bash
git add docs/source/design/code_review.rst docs/plans/2026-02-05-p2-improvements-summary.md
git commit -m "docs: update code review with P2 completion status

Document completion of all P2 issues from code review.
All 5 issues addressed with 100% completion.

Summary:
- Code cleanup: removed unused features (parameter mapping, __call__)
- Documentation: real-world examples and architecture diagrams
- Performance: benchmark suite for regression detection

Total: ~13 hours, following YAGNI/KISS/SOLID principles."
```

---

## Summary

This implementation plan addresses all P2 issues in ~13 hours:

| Phase | Tasks | Time |
|-------|-------|------|
| Phase 1: Code Cleanup | 2 tasks | ~3 hours |
| Phase 2: Benchmarks | 1 task | ~3 hours |
| Phase 3: Documentation | 2 tasks | ~7 hours |

All changes follow TDD, are committed atomically, and maintain backward compatibility where applicable (though breaking changes are acceptable since project is unreleased).
