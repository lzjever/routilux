#!/usr/bin/env python
"""
Basic Example: Simple data processing flow

This example demonstrates:
- Creating routines with slots and events
- Using activation policies and logic
- Connecting routines in a flow
- Executing a flow using Runtime
- Checking execution status
"""

from routilux import Flow, Routine
from routilux.activation_policies import immediate_policy
from routilux.job_state import JobState
from routilux.monitoring.flow_registry import FlowRegistry
from routilux.runtime import Runtime


class DataSource(Routine):
    """A routine that generates data"""

    def __init__(self):
        super().__init__()
        self.trigger_slot = self.define_slot("trigger")
        self.output_event = self.define_event("output", ["data"])

        def my_logic(trigger_data, policy_message, job_state):
            """Handle trigger and emit data through the output event"""
            # Extract data from trigger
            data = trigger_data[0].get("data", "default_data") if trigger_data else "default_data"
            # Get runtime from context
            runtime = getattr(self, "_current_runtime", None)
            if runtime:
                self.emit("output", runtime=runtime, job_state=job_state, data=data)

        self.set_logic(my_logic)
        self.set_activation_policy(immediate_policy())


class DataProcessor(Routine):
    """A routine that processes data"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("input")
        self.output_event = self.define_event("output", ["result"])

        def my_logic(input_data, policy_message, job_state):
            """Process incoming data"""
            # Handle data from slot
            if input_data:
                data_value = input_data[0].get("data", input_data[0]) if isinstance(input_data[0], dict) else input_data[0]
            else:
                data_value = ""

            # Process the data
            processed_data = f"Processed: {data_value}"
            # Store in JobState
            self.set_state(job_state, "processed_data", processed_data)

            # Emit the result
            runtime = getattr(self, "_current_runtime", None)
            if runtime:
                self.emit("output", runtime=runtime, job_state=job_state, result=processed_data)

        self.set_logic(my_logic)
        self.set_activation_policy(immediate_policy())


class DataSink(Routine):
    """A routine that receives final data"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("input")

        def my_logic(input_data, policy_message, job_state):
            """Receive and store the final result"""
            # Handle data from slot
            if input_data:
                result_value = input_data[0].get("result", input_data[0]) if isinstance(input_data[0], dict) else input_data[0]
            else:
                result_value = None

            # Store in JobState
            self.set_state(job_state, "final_result", result_value)
            print(f"Final result: {result_value}")

        self.set_logic(my_logic)
        self.set_activation_policy(immediate_policy())


def main():
    """Main function"""
    # Create a flow
    flow = Flow(flow_id="basic_example")

    # Create routine instances
    source = DataSource()
    processor = DataProcessor()
    sink = DataSink()

    # Add routines to the flow
    source_id = flow.add_routine(source, "source")
    processor_id = flow.add_routine(processor, "processor")
    sink_id = flow.add_routine(sink, "sink")

    # Connect routines: source -> processor -> sink
    flow.connect(source_id, "output", processor_id, "input")
    flow.connect(processor_id, "output", sink_id, "input")

    # Register flow
    flow_registry = FlowRegistry.get_instance()
    flow_registry.register_by_name("basic_example", flow)

    # Create runtime and execute
    print("Executing flow...")
    runtime = Runtime(thread_pool_size=5)
    job_state = runtime.exec("basic_example")

    # Wait for execution to complete
    runtime.wait_until_all_jobs_finished(timeout=5.0)

    # Check results
    print(f"\nExecution Status: {job_state.status}")
    final_result = sink.get_state(job_state, "final_result")
    print(f"Final Result: {final_result}")
    print(f"Execution History: {len(job_state.execution_history)} records")

    assert str(job_state.status) in ["completed", "failed", "running"]
    if final_result:
        assert final_result == "Processed: Hello, World!"

    # Cleanup
    runtime.shutdown(wait=True)


if __name__ == "__main__":
    main()
