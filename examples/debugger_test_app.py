#!/usr/bin/env python
"""
Debugger Test App for Routilux

This application creates multiple flows with various patterns to test the debugger:
- Linear flow (A -> B -> C)
- Branching flow (A -> B, A -> C)
- Aggregating flow (A -> C, B -> C)
- Complex flow with multiple patterns
"""

import time

from routilux import Flow, Routine
from routilux.monitoring.registry import MonitoringRegistry

# ===== Routines =====


class DataSource(Routine):
    """Generates sample data"""

    def __init__(self, name="DataSource"):
        super().__init__()
        self.name = name
        self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
        self.output_event = self.define_event("output", ["data", "index"])

    def _handle_trigger(self, data=None, **kwargs):
        output_data = data or kwargs.get("data", "test_data")
        index = kwargs.get("index", 0)
        print(f"[{self.name}] Emitting data: {output_data} (index: {index})")
        self.emit("output", data=output_data, index=index)


class DataValidator(Routine):
    """Validates input data"""

    def __init__(self, name="Validator"):
        super().__init__()
        self.name = name
        self.input_slot = self.define_slot("input", handler=self.validate)
        self.valid_event = self.define_event("valid", ["data", "index"])
        self.invalid_event = self.define_event("invalid", ["error", "index"])

    def validate(self, data, index=0):
        print(f"[{self.name}] Validating: {data}")
        time.sleep(0.2)  # Simulate processing

        if data and len(str(data)) > 0:
            self.emit("valid", data=data, index=index)
        else:
            self.emit("invalid", error="Invalid data", index=index)


class DataTransformer(Routine):
    """Transforms data to uppercase"""

    def __init__(self, name="Transformer"):
        super().__init__()
        self.name = name
        self.input_slot = self.define_slot("input", handler=self.transform)
        self.output_event = self.define_event("output", ["result", "index"])

    def transform(self, data, index=0):
        print(f"[{self.name}] Transforming: {data}")
        time.sleep(0.3)  # Simulate processing

        result = str(data).upper()
        self.emit("output", result=result, index=index)


class DataMultiplier(Routine):
    """Multiplies/duplicates data"""

    def __init__(self, name="Multiplier"):
        super().__init__()
        self.name = name
        self.input_slot = self.define_slot("input", handler=self.multiply)
        self.output_event = self.define_event("output", ["result", "index"])

    def multiply(self, data, index=0):
        print(f"[{self.name}] Multiplying: {data}")
        time.sleep(0.2)  # Simulate processing

        result = f"{data} x {data}"
        self.emit("output", result=result, index=index)


class DataAggregator(Routine):
    """Aggregates multiple inputs"""

    def __init__(self, name="Aggregator"):
        super().__init__()
        self.name = name
        self.input_slot = self.define_slot("input", handler=self.aggregate, merge_strategy="append")
        self.output_event = self.define_event("output", ["results"])

    def aggregate(self, **kwargs):
        print(f"[{self.name}] Aggregating data from multiple sources")
        time.sleep(0.3)  # Simulate processing

        # Collect all data
        results = []
        for key, value in kwargs.items():
            if key not in ["flow", "job_state"]:
                results.append(f"{key}: {value}")

        result = " | ".join(results)
        self.emit("output", results=result)


class DataSink(Routine):
    """Receives and stores final result"""

    def __init__(self, name="Sink"):
        super().__init__()
        self.name = name
        self.input_slot = self.define_slot("input", handler=self.receive)
        self.final_result = None

    def receive(self, **kwargs):
        print(f"[{self.name}] Receiving final data")
        time.sleep(0.1)  # Simulate processing

        self.final_result = kwargs
        print(f"[{self.name}] Final result: {self.final_result}")


class ErrorGenerator(Routine):
    """A routine that can generate errors for testing"""

    def __init__(self, name="ErrorGenerator"):
        super().__init__()
        self.name = name
        self.input_slot = self.define_slot("input", handler=self.process)
        self.output_event = self.define_event("output", ["result"])
        self.error_event = self.define_event("error", ["error"])

    def process(self, data, should_fail=False):
        print(f"[{self.name}] Processing: {data} (should_fail={should_fail})")
        time.sleep(0.2)

        if should_fail:
            raise ValueError("Intentional error for testing!")
        else:
            self.emit("output", result=f"Success: {data}")


class SlowProcessor(Routine):
    """A routine that processes slowly (for testing timing)"""

    def __init__(self, name="SlowProcessor"):
        super().__init__()
        self.name = name
        self.input_slot = self.define_slot("input", handler=self.process)
        self.output_event = self.define_event("output", ["result"])

    def process(self, data, index=0):
        print(f"[{self.name}] Slow processing: {data}")
        time.sleep(1.0)  # Slow processing
        self.emit("output", result=f"Slowly processed: {data}")


# ===== Flows =====


def create_linear_flow():
    """Simple linear flow: Source -> Validator -> Transformer -> Sink"""
    flow = Flow(flow_id="linear_flow")

    source = DataSource(name="LinearSource")
    validator = DataValidator(name="LinearValidator")
    transformer = DataTransformer(name="LinearTransformer")
    sink = DataSink(name="LinearSink")

    src_id = flow.add_routine(source, "source")
    val_id = flow.add_routine(validator, "validator")
    trans_id = flow.add_routine(transformer, "transformer")
    sink_id = flow.add_routine(sink, "sink")

    flow.connect(src_id, "output", val_id, "input")
    flow.connect(val_id, "valid", trans_id, "input")
    flow.connect(trans_id, "output", sink_id, "input")

    return flow, src_id


def create_branching_flow():
    """Branching flow: Source -> Validator -> (Transformer, Multiplier)"""
    flow = Flow(flow_id="branching_flow")

    source = DataSource(name="BranchSource")
    validator = DataValidator(name="BranchValidator")
    transformer = DataTransformer(name="BranchTransformer")
    multiplier = DataMultiplier(name="BranchMultiplier")
    sink = DataSink(name="BranchSink")

    src_id = flow.add_routine(source, "source")
    val_id = flow.add_routine(validator, "validator")
    trans_id = flow.add_routine(transformer, "transformer")
    mult_id = flow.add_routine(multiplier, "multiplier")
    sink_id = flow.add_routine(sink, "sink")

    flow.connect(src_id, "output", val_id, "input")
    # Branch: validator -> transformer AND validator -> multiplier
    flow.connect(val_id, "valid", trans_id, "input")
    flow.connect(val_id, "valid", mult_id, "input")
    # Both outputs go to sink (fan-in)
    flow.connect(trans_id, "output", sink_id, "input")
    flow.connect(mult_id, "output", sink_id, "input")

    return flow, src_id


def create_complex_flow():
    """Complex flow with multiple patterns"""
    flow = Flow(flow_id="complex_flow")

    # Multiple sources
    source1 = DataSource(name="Source1")
    source2 = DataSource(name="Source2")

    # Processing
    validator1 = DataValidator(name="Validator1")
    validator2 = DataValidator(name="Validator2")
    transformer = DataTransformer(name="Transformer")
    multiplier = DataMultiplier(name="Multiplier")
    slow = SlowProcessor(name="SlowProcessor")
    aggregator = DataAggregator(name="Aggregator")
    sink = DataSink(name="Sink")

    # Add routines
    src1_id = flow.add_routine(source1, "source1")
    src2_id = flow.add_routine(source2, "source2")
    val1_id = flow.add_routine(validator1, "validator1")
    val2_id = flow.add_routine(validator2, "validator2")
    trans_id = flow.add_routine(transformer, "transformer")
    mult_id = flow.add_routine(multiplier, "multiplier")
    slow_id = flow.add_routine(slow, "slow")
    agg_id = flow.add_routine(aggregator, "aggregator")
    sink_id = flow.add_routine(sink, "sink")

    # Connect: source1 -> validator1 -> transformer -> aggregator
    flow.connect(src1_id, "output", val1_id, "input")
    flow.connect(val1_id, "valid", trans_id, "input")
    flow.connect(trans_id, "output", agg_id, "input")

    # Connect: source2 -> validator2 -> multiplier -> aggregator
    flow.connect(src2_id, "output", val2_id, "input")
    flow.connect(val2_id, "valid", mult_id, "input")
    flow.connect(mult_id, "output", agg_id, "input")

    # Connect: transformer -> slow -> aggregator (another path)
    flow.connect(trans_id, "output", slow_id, "input")
    flow.connect(slow_id, "output", agg_id, "input")

    # Aggregator -> sink
    flow.connect(agg_id, "output", sink_id, "input")

    return flow, src1_id


def create_error_flow():
    """Flow with error handling"""
    flow = Flow(flow_id="error_flow")

    source = DataSource(name="ErrorSource")
    processor = ErrorGenerator(name="ErrorProcessor")
    sink = DataSink(name="ErrorSink")

    src_id = flow.add_routine(source, "source")
    proc_id = flow.add_routine(processor, "processor")
    sink_id = flow.add_routine(sink, "sink")

    flow.connect(src_id, "output", proc_id, "input")
    flow.connect(proc_id, "output", sink_id, "input")

    return flow, src_id


# ===== Main =====


def main():
    """Create and register all test flows"""
    print("=" * 60)
    print("Creating Routilux Debugger Test Flows")
    print("=" * 60)

    # Enable monitoring BEFORE importing flow_store
    MonitoringRegistry.enable()

    # Import AFTER enabling monitoring
    from routilux.monitoring.storage import flow_store

    flows = []

    # Create linear flow
    print("\n1. Creating linear flow...")
    linear_flow, linear_entry = create_linear_flow()
    flow_store.add(linear_flow)
    flows.append(("linear_flow", linear_flow, linear_entry))
    print(f"   ✓ Created: {linear_flow.flow_id}")
    print(f"     Routines: {list(linear_flow.routines.keys())}")

    # Create branching flow
    print("\n2. Creating branching flow...")
    branch_flow, branch_entry = create_branching_flow()
    flow_store.add(branch_flow)
    flows.append(("branching_flow", branch_flow, branch_entry))
    print(f"   ✓ Created: {branch_flow.flow_id}")
    print(f"     Routines: {list(branch_flow.routines.keys())}")

    # Create complex flow
    print("\n3. Creating complex flow...")
    complex_flow, complex_entry = create_complex_flow()
    flow_store.add(complex_flow)
    flows.append(("complex_flow", complex_flow, complex_entry))
    print(f"   ✓ Created: {complex_flow.flow_id}")
    print(f"     Routines: {list(complex_flow.routines.keys())}")

    # Create error flow
    print("\n4. Creating error flow...")
    error_flow, error_entry = create_error_flow()
    flow_store.add(error_flow)
    flows.append(("error_flow", error_flow, error_entry))
    print(f"   ✓ Created: {error_flow.flow_id}")
    print(f"     Routines: {list(error_flow.routines.keys())}")

    print("\n" + "=" * 60)
    print("All flows created successfully!")
    print("=" * 60)
    print(f"\nTotal flows: {len(flows)}")
    print("\nFlow Details:")
    for name, flow, entry in flows:
        print(f"  - {name}:")
        print(f"      Routines: {len(flow.routines)}")
        print(f"      Connections: {len(flow.connections)}")
        print(f"      Entry: {entry}")

    print("\n" + "=" * 60)
    print("Starting API Server...")
    print("=" * 60)
    print("\nYou can now:")
    print("1. Connect to the debugger at: http://localhost:3000")
    print("2. Enter server URL: http://localhost:20555")
    print("3. View and monitor the flows")
    print("\nAPI Server will start on http://localhost:20555")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 60)

    # Start API server
    import uvicorn

    uvicorn.run(
        "routilux.api.main:app",
        host="0.0.0.0",
        port=20555,
        reload=True,
    )


if __name__ == "__main__":
    main()
