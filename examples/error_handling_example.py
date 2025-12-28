#!/usr/bin/env python
"""
Error Handling Example: Demonstrating different error handling strategies

This example demonstrates:
- Error handling strategies (STOP, CONTINUE, RETRY, SKIP)
- Error handler configuration
- Error recovery
"""
from routilux import Flow, Routine, ErrorHandler, ErrorStrategy


class UnreliableRoutine(Routine):
    """A routine that may fail"""

    def __init__(self):
        super().__init__()
        self.output_event = self.define_event("output", ["data"])
        self.call_count = 0

    def __call__(self):
        """May fail on first few calls"""
        self.call_count += 1
        if self.call_count < 3:
            raise ValueError(f"Simulated error (attempt {self.call_count})")
        self.emit("output", data=f"Success after {self.call_count} attempts")


class SuccessRoutine(Routine):
    """A routine that always succeeds"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self.process)
        self.executed = False

    def process(self, data):
        """Process the data"""
        self.executed = True
        print(f"Success routine received: {data}")


def test_retry_strategy():
    """Test RETRY strategy"""
    print("\n" + "=" * 50)
    print("Testing RETRY Strategy")
    print("=" * 50)

    flow = Flow(flow_id="retry_test")

    unreliable = UnreliableRoutine()
    success = SuccessRoutine()

    unreliable_id = flow.add_routine(unreliable, "unreliable")
    success_id = flow.add_routine(success, "success")

    flow.connect(unreliable_id, "output", success_id, "input")

    # Set retry strategy
    error_handler = ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=5, retry_delay=0.1)
    flow.set_error_handler(error_handler)

    # Execute
    job_state = flow.execute(unreliable_id)

    print(f"Job Status: {job_state.status}")
    print(f"Call Count: {unreliable.call_count}")
    print(f"Success Routine Executed: {success.executed}")

    assert job_state.status == "completed"
    assert unreliable.call_count == 3
    assert success.executed is True


def test_continue_strategy():
    """Test CONTINUE strategy"""
    print("\n" + "=" * 50)
    print("Testing CONTINUE Strategy")
    print("=" * 50)

    flow = Flow(flow_id="continue_test")

    class FailingRoutine(Routine):
        def __call__(self):
            raise ValueError("This will be logged but execution continues")

    failing = FailingRoutine()
    failing_id = flow.add_routine(failing, "failing")

    # Set continue strategy
    error_handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)
    flow.set_error_handler(error_handler)

    # Execute
    job_state = flow.execute(failing_id)

    print(f"Job Status: {job_state.status}")
    print(f"Execution History: {len(job_state.execution_history)}")

    assert job_state.status == "completed"


def test_skip_strategy():
    """Test SKIP strategy"""
    print("\n" + "=" * 50)
    print("Testing SKIP Strategy")
    print("=" * 50)

    flow = Flow(flow_id="skip_test")

    class FailingRoutine(Routine):
        def __init__(self):
            super().__init__()
            self.output_event = self.define_event("output", ["data"])

        def __call__(self):
            raise ValueError("This routine will be skipped")

    failing = FailingRoutine()
    failing_id = flow.add_routine(failing, "failing")

    # Set skip strategy
    error_handler = ErrorHandler(strategy=ErrorStrategy.SKIP)
    flow.set_error_handler(error_handler)

    # Execute
    job_state = flow.execute(failing_id)

    print(f"Job Status: {job_state.status}")
    routine_state = job_state.get_routine_state("failing")
    print(f"Routine State: {routine_state}")

    assert job_state.status == "completed"
    assert routine_state.get("status") == "skipped"


def main():
    """Main function"""
    test_retry_strategy()
    test_continue_strategy()
    test_skip_strategy()
    print("\n" + "=" * 50)
    print("All error handling examples completed!")
    print("=" * 50)


if __name__ == "__main__":
    main()
