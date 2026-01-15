#!/usr/bin/env python
"""
Overseer Comprehensive Demo App for Routilux

This comprehensive demo showcases ALL features of Routilux Overseer:
✓ Flow Visualization - Linear, Branching, Aggregating, Complex patterns
✓ Job Monitoring - Real-time status, event logs, metrics
✓ Debugging - Breakpoints, variables, step execution
✓ Error Handling - Multiple error scenarios
✓ Concurrent Execution - Parallel routines
✓ Performance Testing - Fast and slow routines
✓ State Management - Job state persistence
✓ Real-time Events - WebSocket event streaming

Author: Routilux Overseer Team
Date: 2025-01-15
"""

import time
from datetime import datetime

from routilux import Flow, Routine
from routilux.monitoring.registry import MonitoringRegistry

# ===== Comprehensive Routines =====


class DataSource(Routine):
    """Generates sample data with metadata"""

    def __init__(self, name="DataSource"):
        super().__init__()
        self.name = name
        self.counter = 0
        self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
        self.output_event = self.define_event("output", ["data", "index", "timestamp", "metadata"])

    def _handle_trigger(self, data=None, **kwargs):
        self.counter += 1
        output_data = data or kwargs.get("data", f"test_data_{self.counter}")
        index = kwargs.get("index", self.counter)
        timestamp = datetime.now().isoformat()
        metadata = {
            "source": self.name,
            "counter": self.counter,
        }

        print(f"[{self.name}] Emitting: {output_data} (#{index}) at {timestamp}")
        self.emit("output", data=output_data, index=index, timestamp=timestamp, metadata=metadata)


class DataValidator(Routine):
    """Validates input data with detailed logging"""

    def __init__(self, name="Validator"):
        super().__init__()
        self.name = name
        self.valid_count = 0
        self.invalid_count = 0
        self.input_slot = self.define_slot("input", handler=self.validate)
        self.valid_event = self.define_event("valid", ["data", "index", "validation_details"])
        self.invalid_event = self.define_event("invalid", ["error", "index", "original_data"])

    def validate(self, data, index=0, **kwargs):
        print(f"[{self.name}] Validating: {data}")
        time.sleep(0.2)

        # Validation logic
        is_valid = self._validate_data(data)

        validation_details = {
            "timestamp": datetime.now().isoformat(),
            "validator": self.name,
            "data_length": len(str(data)),
        }

        if is_valid:
            self.valid_count += 1
            print(f"[{self.name}] ✓ Valid (total valid: {self.valid_count})")
            self.emit("valid", data=data, index=index, validation_details=validation_details)
        else:
            self.invalid_count += 1
            print(f"[{self.name}] ✗ Invalid (total invalid: {self.invalid_count})")
            self.emit("invalid", error="Validation failed", index=index, original_data=data)

    def _validate_data(self, data):
        """Custom validation logic"""
        if not data:
            return False
        if str(data).startswith("INVALID"):
            return False
        return len(str(data)) > 0


class DataTransformer(Routine):
    """Transforms data with configurable options"""

    def __init__(self, name="Transformer", transformation="uppercase"):
        super().__init__()
        self.name = name
        self.transformation = transformation
        self.processed_count = 0
        self.input_slot = self.define_slot("input", handler=self.transform)
        self.output_event = self.define_event("output", ["result", "index", "transformation_type"])

    def transform(self, data, index=0, **kwargs):
        print(f"[{self.name}] Transforming: {data} (mode: {self.transformation})")
        time.sleep(0.3)

        # Apply transformation
        if self.transformation == "uppercase":
            result = str(data).upper()
        elif self.transformation == "lowercase":
            result = str(data).lower()
        elif self.transformation == "reverse":
            result = str(data)[::-1]
        elif self.transformation == "prefix":
            result = f"TRANSFORMED_{data}"
        else:
            result = str(data)

        self.processed_count += 1
        print(f"[{self.name}] → Result: {result}")
        self.emit("output", result=result, index=index, transformation_type=self.transformation)


class DataMultiplier(Routine):
    """Multiplies/duplicates data with count"""

    def __init__(self, name="Multiplier"):
        super().__init__()
        self.name = name
        self.input_slot = self.define_slot("input", handler=self.multiply)
        self.output_event = self.define_event("output", ["result", "index", "multiplier"])

    def multiply(self, data, index=0, multiplier=2, **kwargs):
        print(f"[{self.name}] Multiplying: {data} (x{multiplier})")
        time.sleep(0.2)

        result = f"{data} " * multiplier
        print(f"[{self.name}] → Result: {result.strip()}")
        self.emit("output", result=result.strip(), index=index, multiplier=multiplier)


class DataAggregator(Routine):
    """Aggregates multiple inputs with detailed tracking"""

    def __init__(self, name="Aggregator"):
        super().__init__()
        self.name = name
        self.input_slot = self.define_slot("input", handler=self.aggregate, merge_strategy="append")
        self.output_event = self.define_event("output", ["results", "count", "sources"])

    def aggregate(self, **kwargs):
        print(f"[{self.name}] Aggregating data...")
        time.sleep(0.3)

        # Collect all data
        results = []
        sources = []
        for key, value in kwargs.items():
            if key not in ["flow", "job_state"]:
                results.append(f"{value}")
                sources.append(key)

        result = " | ".join(results)
        print(f"[{self.name}] → Aggregated {len(results)} items: {result}")
        self.emit("output", results=result, count=len(results), sources=sources)


class DataSink(Routine):
    """Receives and stores final result with state"""

    def __init__(self, name="Sink"):
        super().__init__()
        self.name = name
        self.input_slot = self.define_slot("input", handler=self.receive)
        self.final_result = None
        self.received_count = 0

    def receive(self, **kwargs):
        self.received_count += 1
        print(f"[{self.name}] Receiving data (#{self.received_count})")
        time.sleep(0.1)

        self.final_result = kwargs
        print(f"[{self.name}] ✓ Final result: {self.final_result}")


class ErrorGenerator(Routine):
    """Generates different types of errors for testing"""

    def __init__(self, name="ErrorGenerator"):
        super().__init__()
        self.name = name
        self.input_slot = self.define_slot("input", handler=self.process)
        self.output_event = self.define_event("output", ["result"])
        self.error_event = self.define_event("error", ["error_type", "error_message"])

    def process(self, data, error_type="none", **kwargs):
        print(f"[{self.name}] Processing: {data} (error_type={error_type})")
        time.sleep(0.2)

        if error_type == "value_error":
            raise ValueError("Intentional ValueError for testing!")
        elif error_type == "runtime_error":
            raise RuntimeError("Intentional RuntimeError for testing!")
        elif error_type == "key_error":
            raise KeyError("Intentional KeyError for testing!")
        elif error_type == "custom":
            raise Exception("Custom error for debugging!")
        else:
            self.emit("output", result=f"Success: {data}")


class SlowProcessor(Routine):
    """Slow processing for testing timing and patience"""

    def __init__(self, name="SlowProcessor"):
        super().__init__()
        self.name = name
        self.input_slot = self.define_slot("input", handler=self.process)
        self.output_event = self.define_event("output", ["result", "processing_time"])

    def process(self, data, index=0, **kwargs):
        print(f"[{self.name}] Starting slow processing: {data}")
        start_time = time.time()
        time.sleep(2.0)  # Very slow processing
        processing_time = time.time() - start_time

        result = f"Slowly processed: {data}"
        print(f"[{self.name}] → Done in {processing_time:.2f}s")
        self.emit("output", result=result, processing_time=processing_time)


class FastProcessor(Routine):
    """Fast processing for performance testing"""

    def __init__(self, name="FastProcessor"):
        super().__init__()
        self.name = name
        self.processed_count = 0
        self.input_slot = self.define_slot("input", handler=self.process)
        self.output_event = self.define_event("output", ["result", "count"])

    def process(self, data, index=0, **kwargs):
        self.processed_count += 1
        # Very fast processing
        time.sleep(0.01)
        self.emit("output", result=f"Fast: {data}", count=self.processed_count)


class ConditionalProcessor(Routine):
    """Processes data conditionally - great for breakpoint testing"""

    def __init__(self, name="ConditionalProcessor"):
        super().__init__()
        self.name = name
        self.input_slot = self.define_slot("input", handler=self.process)
        self.output_event = self.define_event("output", ["result", "condition"])
        self.branch_a_event = self.define_event("branch_a", ["result"])
        self.branch_b_event = self.define_event("branch_b", ["result"])

    def process(self, data, condition="default", **kwargs):
        print(f"[{self.name}] Processing with condition: {condition}")

        if condition == "branch_a":
            result = f"Branch A processed: {data}"
            print(f"[{self.name}] → Taking Branch A")
            self.emit("branch_a", result=result)
            self.emit("output", result=result, condition="branch_a")
        elif condition == "branch_b":
            result = f"Branch B processed: {data}"
            print(f"[{self.name}] → Taking Branch B")
            self.emit("branch_b", result=result)
            self.emit("output", result=result, condition="branch_b")
        else:
            result = f"Default processed: {data}"
            print(f"[{self.name}] → Default path")
            self.emit("output", result=result, condition="default")


class Counter(Routine):
    """Counter routine for breakpoint testing"""

    def __init__(self, name="Counter"):
        super().__init__()
        self.name = name
        self.count = 0
        self.input_slot = self.define_slot("input", handler=self.increment)
        self.output_event = self.define_event("output", ["count", "message"])

    def increment(self, steps=1, **kwargs):
        print(f"[{self.name}] Incrementing by {steps}")
        time.sleep(0.1)

        self.count += steps
        message = f"Count is now {self.count}"
        print(f"[{self.name}] → {message}")
        self.emit("output", count=self.count, message=message)


# ===== Flows =====


def create_linear_flow():
    """Linear flow: Source -> Validator -> Transformer -> Sink"""
    flow = Flow(flow_id="linear_flow")

    source = DataSource(name="LinearSource")
    validator = DataValidator(name="LinearValidator")
    transformer = DataTransformer(name="LinearTransformer", transformation="uppercase")
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
    """Branching flow: Source -> Validator -> (Transformer, Multiplier) -> Sink"""
    flow = Flow(flow_id="branching_flow")

    source = DataSource(name="BranchSource")
    validator = DataValidator(name="BranchValidator")
    transformer = DataTransformer(name="BranchTransformer", transformation="uppercase")
    multiplier = DataMultiplier(name="BranchMultiplier")
    sink = DataSink(name="BranchSink")

    src_id = flow.add_routine(source, "source")
    val_id = flow.add_routine(validator, "validator")
    trans_id = flow.add_routine(transformer, "transformer")
    mult_id = flow.add_routine(multiplier, "multiplier")
    sink_id = flow.add_routine(sink, "sink")

    flow.connect(src_id, "output", val_id, "input")
    flow.connect(val_id, "valid", trans_id, "input")
    flow.connect(val_id, "valid", mult_id, "input")
    flow.connect(trans_id, "output", sink_id, "input")
    flow.connect(mult_id, "output", sink_id, "input")

    return flow, src_id


def create_aggregating_flow():
    """Aggregating flow: Two sources -> Aggregator -> Sink"""
    flow = Flow(flow_id="aggregating_flow")

    source1 = DataSource(name="Source1")
    source2 = DataSource(name="Source2")
    aggregator = DataAggregator(name="Aggregator")
    sink = DataSink(name="Sink")

    src1_id = flow.add_routine(source1, "source1")
    src2_id = flow.add_routine(source2, "source2")
    agg_id = flow.add_routine(aggregator, "aggregator")
    sink_id = flow.add_routine(sink, "sink")

    flow.connect(src1_id, "output", agg_id, "input")
    flow.connect(src2_id, "output", agg_id, "input")
    flow.connect(agg_id, "output", sink_id, "input")

    return flow, src1_id


def create_conditional_flow():
    """Conditional flow for breakpoint testing"""
    flow = Flow(flow_id="conditional_flow")

    source = DataSource(name="Source")
    counter = Counter(name="Counter")
    processor = ConditionalProcessor(name="ConditionalProcessor")
    sink = DataSink(name="Sink")

    src_id = flow.add_routine(source, "source")
    counter_id = flow.add_routine(counter, "counter")
    proc_id = flow.add_routine(processor, "processor")
    sink_id = flow.add_routine(sink, "sink")

    flow.connect(src_id, "output", counter_id, "input")
    flow.connect(counter_id, "output", proc_id, "input")
    flow.connect(proc_id, "output", sink_id, "input")

    return flow, src_id


def create_performance_flow():
    """Performance testing flow with fast and slow routines"""
    flow = Flow(flow_id="performance_flow")

    source = DataSource(name="PerfSource")
    fast1 = FastProcessor(name="Fast1")
    fast2 = FastProcessor(name="Fast2")
    fast3 = FastProcessor(name="Fast3")
    slow = SlowProcessor(name="Slow")
    aggregator = DataAggregator(name="Aggregator")
    sink = DataSink(name="Sink")

    src_id = flow.add_routine(source, "source")
    fast1_id = flow.add_routine(fast1, "fast1")
    fast2_id = flow.add_routine(fast2, "fast2")
    fast3_id = flow.add_routine(fast3, "fast3")
    slow_id = flow.add_routine(slow, "slow")
    agg_id = flow.add_routine(aggregator, "aggregator")
    sink_id = flow.add_routine(sink, "sink")

    # Fast path
    flow.connect(src_id, "output", fast1_id, "input")
    flow.connect(fast1_id, "output", fast2_id, "input")
    flow.connect(fast2_id, "output", fast3_id, "input")

    # Split: fast -> slow AND fast -> aggregator
    flow.connect(fast3_id, "output", slow_id, "input")
    flow.connect(fast3_id, "output", agg_id, "input")
    flow.connect(slow_id, "output", agg_id, "input")

    flow.connect(agg_id, "output", sink_id, "input")

    return flow, src_id


def create_error_flow():
    """Flow with multiple error scenarios"""
    flow = Flow(flow_id="error_flow")

    source = DataSource(name="ErrorSource")
    error_gen = ErrorGenerator(name="ErrorGenerator")
    sink = DataSink(name="ErrorSink")

    src_id = flow.add_routine(source, "source")
    err_id = flow.add_routine(error_gen, "error_gen")
    sink_id = flow.add_routine(sink, "sink")

    flow.connect(src_id, "output", err_id, "input")
    flow.connect(err_id, "output", sink_id, "input")

    return flow, src_id


def create_complex_flow():
    """Complex flow combining all patterns"""
    flow = Flow(flow_id="complex_flow")

    # Multiple sources
    source1 = DataSource(name="MainSource")
    source2 = DataSource(name="SecondarySource")

    # Processing pipeline
    validator = DataValidator(name="Validator")
    transformer = DataTransformer(name="Transformer", transformation="uppercase")
    multiplier = DataMultiplier(name="Multiplier")

    # Conditional branching
    counter = Counter(name="Counter")
    conditional = ConditionalProcessor(name="Conditional")

    # Performance mix
    fast = FastProcessor(name="Fast")
    slow = SlowProcessor(name="Slow")

    # Aggregation
    aggregator = DataAggregator(name="Aggregator")

    # Final sink
    sink = DataSink(name="FinalSink")

    # Add routines
    src1_id = flow.add_routine(source1, "main_source")
    src2_id = flow.add_routine(source2, "secondary_source")
    val_id = flow.add_routine(validator, "validator")
    trans_id = flow.add_routine(transformer, "transformer")
    mult_id = flow.add_routine(multiplier, "multiplier")
    counter_id = flow.add_routine(counter, "counter")
    cond_id = flow.add_routine(conditional, "conditional")
    fast_id = flow.add_routine(fast, "fast")
    slow_id = flow.add_routine(slow, "slow")
    agg_id = flow.add_routine(aggregator, "aggregator")
    sink_id = flow.add_routine(sink, "sink")

    # Complex connections
    # Main path: source1 -> validator -> transformer -> (counter, multiplier)
    flow.connect(src1_id, "output", val_id, "input")
    flow.connect(val_id, "valid", trans_id, "input")
    flow.connect(trans_id, "output", counter_id, "input")
    flow.connect(trans_id, "output", mult_id, "input")

    # Counter -> conditional -> aggregator
    flow.connect(counter_id, "output", cond_id, "input")
    flow.connect(cond_id, "output", agg_id, "input")

    # Multiplier -> fast -> aggregator
    flow.connect(mult_id, "output", fast_id, "input")
    flow.connect(fast_id, "output", agg_id, "input")

    # Secondary path: source2 -> slow -> aggregator
    flow.connect(src2_id, "output", slow_id, "input")
    flow.connect(slow_id, "output", agg_id, "input")

    # Aggregator -> sink
    flow.connect(agg_id, "output", sink_id, "input")

    return flow, src1_id


# ===== Demo Job Starters =====


def demo_linear_flow(flow_store):
    """Start a linear flow job"""
    flow = flow_store.get("linear_flow")
    if flow:
        job_id = flow.start(entry_routine_id="source", entry_params={"data": "Hello Overseer!"})
        print(f"\n✓ Started linear flow job: {job_id}")
        return job_id


def demo_branching_flow(flow_store):
    """Start a branching flow job"""
    flow = flow_store.get("branching_flow")
    if flow:
        job_id = flow.start(entry_routine_id="source", entry_params={"data": "Branching Test"})
        print(f"\n✓ Started branching flow job: {job_id}")
        return job_id


def demo_conditional_flow(flow_store, condition="branch_a"):
    """Start a conditional flow job with specified condition"""
    flow = flow_store.get("conditional_flow")
    if flow:
        job_id = flow.start(
            entry_routine_id="source",
            entry_params={"data": "Conditional Test", "steps": 5, "condition": condition},
        )
        print(f"\n✓ Started conditional flow job ({condition}): {job_id}")
        return job_id


def demo_error_flow(flow_store, error_type="value_error"):
    """Start an error flow job"""
    flow = flow_store.get("error_flow")
    if flow:
        job_id = flow.start(
            entry_routine_id="source", entry_params={"data": "Error Test", "error_type": error_type}
        )
        print(f"\n✓ Started error flow job ({error_type}): {job_id}")
        return job_id


def demo_performance_flow(flow_store):
    """Start a performance testing flow"""
    flow = flow_store.get("performance_flow")
    if flow:
        job_id = flow.start(entry_routine_id="source", entry_params={"data": "Performance Test"})
        print(f"\n✓ Started performance flow job: {job_id}")
        return job_id


# ===== Main =====


def main():
    """Create and register all demo flows"""
    print("=" * 80)
    print(" " * 15 + "Routilux Overseer - Comprehensive Demo")
    print("=" * 80)
    print("\nThis demo showcases ALL features of Routilux Overseer:")
    print("  ✓ Flow Visualization - Multiple flow patterns")
    print("  ✓ Job Monitoring - Real-time status and metrics")
    print("  ✓ Debugging - Breakpoints, variables, step execution")
    print("  ✓ Error Handling - Various error scenarios")
    print("  ✓ Performance Testing - Fast and slow routines")
    print("  ✓ Real-time Events - WebSocket event streaming")
    print("\n" + "=" * 80)

    # Enable monitoring BEFORE importing flow_store
    print("\n[1/5] Enabling monitoring...")
    MonitoringRegistry.enable()

    # Import AFTER enabling monitoring
    from routilux.monitoring.storage import flow_store

    flows = []

    # Create all flows
    print("\n[2/5] Creating demo flows...")

    flows_to_create = [
        ("Linear Flow", create_linear_flow),
        ("Branching Flow", create_branching_flow),
        ("Aggregating Flow", create_aggregating_flow),
        ("Conditional Flow", create_conditional_flow),
        ("Performance Flow", create_performance_flow),
        ("Error Flow", create_error_flow),
        ("Complex Flow", create_complex_flow),
    ]

    for i, (name, creator) in enumerate(flows_to_create, 1):
        print(f"\n  {i}. Creating {name}...")
        flow, entry = creator()
        flow_store.add(flow)
        flows.append((name, flow, entry))
        print(f"     ✓ Flow ID: {flow.flow_id}")
        print(f"     ✓ Routines: {len(flow.routines)} ({', '.join(flow.routines.keys())})")
        print(f"     ✓ Connections: {len(flow.connections)}")
        print(f"     ✓ Entry Point: {entry}")

    print("\n" + "=" * 80)
    print("[3/5] All flows created successfully!")
    print("=" * 80)
    print(f"\nTotal flows created: {len(flows)}")
    print("\nFlow Summary:")
    for name, flow, entry in flows:
        print(f"  • {name:20s} ({flow.flow_id})")
        print(f"    Routines: {len(flow.routines):2d} | Connections: {len(flow.connections):2d}")

    # Print testing suggestions
    print("\n" + "=" * 80)
    print("[4/5] Testing Scenarios")
    print("=" * 80)
    print("\nRecommended testing order:")
    print("\n1️⃣  Linear Flow - Basic flow visualization")
    print("   Start job from: source")
    print("   Expected: Straight-line execution")
    print("\n2️⃣  Branching Flow - Branching patterns")
    print("   Start job from: source")
    print("   Expected: Parallel execution paths")
    print("\n3️⃣  Conditional Flow - Breakpoint testing")
    print("   Start job with: condition='branch_a' or condition='branch_b'")
    print("   Set breakpoints on: ConditionalProcessor")
    print("   Expected: Different execution paths")
    print("\n4️⃣  Performance Flow - Speed comparison")
    print("   Start job from: source")
    print("   Expected: Mix of fast and slow routines")
    print("\n5️⃣  Error Flow - Error handling")
    print("   Start job with: error_type='value_error'")
    print("   Expected: Job failure with error details")
    print("\n6️⃣  Complex Flow - All features combined")
    print("   Start job from: main_source")
    print("   Expected: Complex execution with aggregation")

    # Start API server
    print("\n" + "=" * 80)
    print("[5/5] Starting API Server...")
    print("=" * 80)
    print("\n📡 Server will start on: http://localhost:20555")
    print("🌐 Connect Overseer to: http://localhost:20555")
    print("\n💡 Quick Start:")
    print("   1. Open Overseer: http://localhost:3000")
    print("   2. Click 'Connect to Server'")
    print("   3. Enter: http://localhost:20555")
    print("   4. Click 'Connect'")
    print("   5. Explore Flows and start Jobs!")
    print("\n" + "=" * 80)
    print("Press Ctrl+C to stop the server")
    print("=" * 80 + "\n")

    # Start API server
    import uvicorn

    uvicorn.run(
        "routilux.api.main:app",
        host="0.0.0.0",
        port=20555,
        reload=False,  # Disable reload for stability
        log_level="info",
    )


if __name__ == "__main__":
    main()
