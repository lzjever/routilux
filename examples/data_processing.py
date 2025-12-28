#!/usr/bin/env python
"""
Data Processing Example: Multi-stage data processing pipeline

This example demonstrates:
- Complex data flow with multiple stages
- Parameter mapping
- Statistics tracking
"""
from routilux import Flow, Routine


class InputReader(Routine):
    """Reads input data"""

    def __init__(self):
        super().__init__()
        self.output_event = self.define_event("output", ["raw_data"])

    def __call__(self, filename=None):
        """Simulate reading from a file"""
        raw_data = filename or "sample_data.txt"
        self._stats["files_read"] = self._stats.get("files_read", 0) + 1
        self.emit("output", raw_data=raw_data)


class DataValidator(Routine):
    """Validates input data"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self.validate)
        self.output_event = self.define_event("output", ["validated_data"])
        self.error_event = self.define_event("error", ["error_message"])

    def validate(self, raw_data):
        """Validate the data"""
        if isinstance(raw_data, dict):
            data = raw_data.get("raw_data", raw_data)
        else:
            data = raw_data

        if data and len(str(data)) > 0:
            self._stats["validated_count"] = self._stats.get("validated_count", 0) + 1
            self.emit("output", validated_data=data)
        else:
            self._stats["validation_errors"] = self._stats.get("validation_errors", 0) + 1
            self.emit("error", error_message="Invalid data")


class DataTransformer(Routine):
    """Transforms validated data"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self.transform)
        self.output_event = self.define_event("output", ["transformed_data"])

    def transform(self, validated_data):
        """Transform the data"""
        if isinstance(validated_data, dict):
            data = validated_data.get("validated_data", validated_data)
        else:
            data = validated_data

        transformed = f"TRANSFORMED_{data.upper()}"
        self._stats["transformed_count"] = self._stats.get("transformed_count", 0) + 1
        self.emit("output", transformed_data=transformed)


class DataWriter(Routine):
    """Writes processed data"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self.write)
        self.written_data = []

    def write(self, transformed_data):
        """Write the data"""
        if isinstance(transformed_data, dict):
            data = transformed_data.get("transformed_data", transformed_data)
        else:
            data = transformed_data

        self.written_data.append(data)
        self._stats["written_count"] = self._stats.get("written_count", 0) + 1
        print(f"Written: {data}")


def main():
    """Main function"""
    # Create a flow
    flow = Flow(flow_id="data_processing")

    # Create routine instances
    reader = InputReader()
    validator = DataValidator()
    transformer = DataTransformer()
    writer = DataWriter()

    # Add routines to the flow
    reader_id = flow.add_routine(reader, "reader")
    validator_id = flow.add_routine(validator, "validator")
    transformer_id = flow.add_routine(transformer, "transformer")
    writer_id = flow.add_routine(writer, "writer")

    # Connect the pipeline
    flow.connect(reader_id, "output", validator_id, "input")
    flow.connect(validator_id, "output", transformer_id, "input")
    flow.connect(transformer_id, "output", writer_id, "input")

    # Execute the flow
    print("Executing data processing pipeline...")
    job_state = flow.execute(reader_id, entry_params={"filename": "data.txt"})

    # Check results
    print(f"\nExecution Status: {job_state.status}")
    print(f"Reader Stats: {reader.stats()}")
    print(f"Validator Stats: {validator.stats()}")
    print(f"Transformer Stats: {transformer.stats()}")
    print(f"Writer Stats: {writer.stats()}")
    print(f"Written Data: {writer.written_data}")

    assert job_state.status == "completed"
    assert len(writer.written_data) > 0


if __name__ == "__main__":
    main()
