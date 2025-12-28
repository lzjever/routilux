#!/usr/bin/env python
"""
Basic Example: Simple data processing flow

This example demonstrates:
- Creating routines with slots and events
- Connecting routines in a flow
- Executing a flow
- Checking execution status
"""

from routilux import Flow, Routine


class DataSource(Routine):
    """A routine that generates data"""

    def __init__(self):
        super().__init__()
        self.output_event = self.define_event("output", ["data"])

    def __call__(self, data=None):
        """Emit data through the output event"""
        output_data = data or "default_data"
        self._stats["emitted_count"] = self._stats.get("emitted_count", 0) + 1
        self.emit("output", data=output_data)


class DataProcessor(Routine):
    """A routine that processes data"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self.process)
        self.output_event = self.define_event("output", ["result"])
        self.processed_data = None

    def process(self, data):
        """Process incoming data"""
        # Handle both dict and direct value
        if isinstance(data, dict):
            data_value = data.get("data", data)
        else:
            data_value = data

        # Process the data
        self.processed_data = f"Processed: {data_value}"
        self._stats["processed_count"] = self._stats.get("processed_count", 0) + 1

        # Emit the result
        self.emit("output", result=self.processed_data)


class DataSink(Routine):
    """A routine that receives final data"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self.receive)
        self.final_result = None

    def receive(self, result):
        """Receive and store the final result"""
        # Handle both dict and direct value
        if isinstance(result, dict):
            result_value = result.get("result", result)
        else:
            result_value = result

        self.final_result = result_value
        self._stats["received_count"] = self._stats.get("received_count", 0) + 1
        print(f"Final result: {self.final_result}")


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

    # Execute the flow
    print("Executing flow...")
    job_state = flow.execute(source_id, entry_params={"data": "Hello, World!"})

    # Check results
    print(f"\nExecution Status: {job_state.status}")
    print(f"Source Stats: {source.stats()}")
    print(f"Processor Stats: {processor.stats()}")
    print(f"Sink Stats: {sink.stats()}")
    print(f"Final Result: {sink.final_result}")

    assert job_state.status == "completed"
    assert sink.final_result == "Processed: Hello, World!"


if __name__ == "__main__":
    main()
