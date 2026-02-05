#!/usr/bin/env python
"""Error Handling Patterns Example.

This example demonstrates:
1. Exception handling in routines
2. Retry logic
3. Fallback mechanisms
"""

from routilux import Flow, Routine
from routilux.exceptions import ExecutionError, RoutiluxError
from routilux.job_state import JobState
import random


class RiskyOperation(Routine):
    """A routine that may fail randomly."""

    def __init__(self):
        super().__init__()
        self.define_slot("trigger", handler=self.execute_risky)
        self.define_event("output", ["success", "value"])

    def execute_risky(self, input_value=None, **kwargs):
        """Handler that may fail."""
        input_value = input_value if input_value is not None else kwargs.get("input", 0)
        if random.random() < 0.3:  # 30% chance of failure
            raise ExecutionError("Random failure occurred", routine_id="risky_operation")
        result = input_value * 2 if isinstance(input_value, (int, float)) else 0
        self.emit("output", success=True, value=result)


class RetryOperation(Routine):
    """A routine that demonstrates retry behavior."""

    def __init__(self):
        super().__init__()
        self.define_slot("trigger", handler=self.execute_with_retry)
        self.attempt_count = 0

    def execute_with_retry(self, **kwargs):
        """Handler with built-in retry logic."""
        self.attempt_count += 1

        if self.attempt_count < 3:
            print(f"  Attempt {self.attempt_count} failed, retrying...")
            raise ExecutionError("Temporary failure", routine_id="retry_operation")

        print(f"  Attempt {self.attempt_count} succeeded!")
        return {"success": True, "attempts": self.attempt_count}


class PrimaryService(Routine):
    """Primary service that may fail."""

    def __init__(self):
        super().__init__()
        self.define_slot("trigger", handler=self.serve)
        self.define_event("output", ["source", "data"])

    def serve(self, **kwargs):
        """Primary service handler."""
        if random.random() < 0.5:
            raise ExecutionError("Primary service unavailable")
        self.emit("output", source="primary", data=kwargs)


class FallbackService(Routine):
    """Fallback service when primary fails."""

    def __init__(self):
        super().__init__()
        self.define_slot("trigger", handler=self.serve_fallback)
        self.define_event("output", ["source", "data"])

    def serve_fallback(self, **kwargs):
        """Fallback service handler."""
        print("  Using fallback service...")
        self.emit("output", source="fallback", data=kwargs)


class DataValidator(Routine):
    """Validates data before processing."""

    def __init__(self):
        super().__init__()
        self.define_slot("trigger", handler=self.validate)
        self.define_event("output", ["validated", "data"])
        self.validation_result = {"valid": False}

    def validate(self, data=None, **kwargs):
        """Validate input data."""
        data = data if data is not None else kwargs.get("data", None)
        if not data or not isinstance(data, dict):
            self.validation_result["valid"] = False
            raise RoutiluxError("Invalid data: must be a non-empty dictionary")
        self.validation_result["valid"] = True
        self.emit("output", validated=True, data=data)


class DataProcessor(Routine):
    """Processes validated data."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", handler=self.process)

    def process(self, validated=None, data=None, **kwargs):
        """Process validated data."""
        data = data if data is not None else kwargs.get("data", {})
        if not data or not isinstance(data, dict):
            raise RoutiluxError("Cannot process invalid data")
        return {"processed": True, "result": f"Processed {data}"}


def main():
    """Run the error handling example."""
    print("\n=== Error Handling Patterns Example ===\n")

    # Example 1: Basic error handling
    print("--- Example 1: Basic Error Handling ---")

    flow1 = Flow("error_handling_flow")
    risky = RiskyOperation()
    flow1.add_routine(risky, "risky")

    success_count = 0
    for attempt in range(5):
        try:
            job_state = flow1.execute("risky", entry_params={"input": attempt})
            JobState.wait_for_completion(flow1, job_state, timeout=10.0)

            if job_state.status == "completed":
                success_count += 1
                print(f"  Attempt {attempt + 1}: Success")
            else:
                print(f"  Attempt {attempt + 1}: Failed with status {job_state.status}")

        except RoutiluxError as e:
            print(f"  Attempt {attempt + 1}: Caught error - {type(e).__name__}")

    print(f"\n  Success rate: {success_count}/5")

    # Example 2: Retry pattern
    print("\n--- Example 2: Retry Pattern ---")

    flow2 = Flow("retry_flow")
    retry_op = RetryOperation()
    flow2.add_routine(retry_op, "retry")

    try:
        job_state2 = flow2.execute("retry", entry_params={})
        JobState.wait_for_completion(flow2, job_state2, timeout=30.0)

        print(f"  Final status: {job_state2.status}")
        print(f"  Execution history: {len(job_state2.execution_history)} entries")

    except RoutiluxError as e:
        print(f"  Final error after retries: {e}")

    # Example 3: Fallback mechanism
    print("\n--- Example 3: Fallback Mechanism ---")

    flow3 = Flow("fallback_flow")
    primary = PrimaryService()
    fallback = FallbackService()
    primary_id = flow3.add_routine(primary, "primary")
    fallback_id = flow3.add_routine(fallback, "fallback")

    service_result = {"value": None}

    # Try primary first
    try:
        job_state3 = flow3.execute(primary_id, entry_params={"test": True})
        JobState.wait_for_completion(flow3, job_state3, timeout=10.0)
        service_result["value"] = "primary"
        print(f"  Result from: primary")
    except ExecutionError:
        # Fall back to secondary
        print("  Primary failed, trying fallback...")
        try:
            job_state3 = flow3.execute(fallback_id, entry_params={"test": True})
            JobState.wait_for_completion(flow3, job_state3, timeout=10.0)
            service_result["value"] = "fallback"
            print(f"  Result from: fallback")
        except RoutiluxError as e:
            print(f"  Fallback also failed: {e}")

    # Example 4: Error recovery with validation
    print("\n--- Example 4: Error Recovery with Validation ---")

    flow4 = Flow("validation_flow")
    validator = DataValidator()
    processor = DataProcessor()
    validator_id = flow4.add_routine(validator, "validator")
    processor_id = flow4.add_routine(processor, "processor")
    flow4.connect(validator_id, "output", processor_id, "input")

    # Test with invalid data
    try:
        job_state4 = flow4.execute(validator_id, entry_params={"data": None})
        JobState.wait_for_completion(flow4, job_state4, timeout=10.0)
    except RoutiluxError as e:
        print(f"  Validation caught error: {e}")

    # Test with valid data
    try:
        job_state4 = flow4.execute(validator_id, entry_params={"data": {"key": "value"}})
        JobState.wait_for_completion(flow4, job_state4, timeout=10.0)
        print(f"  Valid data processed successfully")
    except RoutiluxError as e:
        print(f"  Unexpected error: {e}")


if __name__ == "__main__":
    main()
