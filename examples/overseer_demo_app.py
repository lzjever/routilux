#!/usr/bin/env python
"""
Overseer Comprehensive Demo App for Routilux

This comprehensive demo showcases ALL features of Routilux Overseer:
✓ Flow Visualization - Linear, Branching, Aggregating, Complex patterns
✓ Job State Transitions - pending -> running -> completed/failed/paused/cancelled
✓ Queue Pressure Monitoring - Real-time queue status, pressure levels, usage percentages
✓ Debugging - Breakpoints, variables, step execution, call stack
✓ Error Handling - Multiple error scenarios
✓ Concurrent Execution - Parallel routines
✓ Performance Testing - Fast and slow routines
✓ Real-time Events - WebSocket event streaming
✓ Long-Running Flows - Extended execution with progress tracking
✓ Loop Flows - Circular flow patterns with iteration control

Key Features Demonstrated:
- State Transitions: Jobs move through states (pending -> running -> completed)
- Queue Pressure: Routines with varying queue loads show pressure levels (low/medium/high/critical)
- Debug Process: Breakpoints can be set, jobs paused, variables inspected, step execution
- Comprehensive Monitoring: Metrics, traces, logs, queue status, routine status

Author: Routilux Overseer Team
Date: 2025-01-15
"""

import time
from datetime import datetime

from routilux import Flow, Routine
from routilux.activation_policies import (
    all_slots_ready_policy,
    batch_size_policy,
    immediate_policy,
    time_interval_policy,
)
from routilux.monitoring.registry import MonitoringRegistry

# ===== Comprehensive Routines =====


class DataSource(Routine):
    """Generates sample data with metadata - demonstrates state transitions"""

    def __init__(self, name="DataSource"):
        super().__init__()
        self.set_config(name=name)
        self.trigger_slot = self.define_slot("trigger")
        self.output_event = self.define_event("output", ["data", "index", "timestamp", "metadata"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self._handle_trigger)

    def _handle_trigger(self, *slot_data_lists, policy_message, job_state):
        trigger_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = trigger_data[0] if trigger_data else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None

        name = self.get_config("name", "DataSource")

        # Get counter from JobState
        routine_state = job_state.get_routine_state(self._id) or {}
        counter = routine_state.get("counter", 0) + 1
        job_state.update_routine_state(self._id, {"counter": counter})

        output_data = data or f"test_data_{counter}"
        index = data_dict.get("index", counter) if isinstance(data_dict, dict) else counter
        timestamp = datetime.now().isoformat()
        metadata = {
            "source": name,
            "counter": counter,
        }

        print(f"[{name}] Emitting: {output_data} (#{index}) at {timestamp}")
        self.emit(
            "output",
            job_state=job_state,
            data=output_data,
            index=index,
            timestamp=timestamp,
            metadata=metadata,
        )


class DataValidator(Routine):
    """Validates input data - demonstrates queue pressure when processing multiple items"""

    def __init__(self, name="Validator"):
        super().__init__()
        self.set_config(name=name)
        self.input_slot = self.define_slot("input")
        self.valid_event = self.define_event("valid", ["data", "index", "validation_details"])
        self.invalid_event = self.define_event("invalid", ["error", "index", "original_data"])
        # Use batch policy to create queue pressure scenarios
        self.set_activation_policy(batch_size_policy(3))  # Process in batches of 3
        self.set_logic(self.validate)

    def validate(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []

        name = self.get_config("name", "Validator")
        print(f"[{name}] Validating batch of {len(input_data)} items...")
        time.sleep(0.3)  # Simulate processing time

        valid_count = 0
        invalid_count = 0

        for data_dict in input_data[:3]:  # Process batch
            if not isinstance(data_dict, dict):
                continue
            data = data_dict.get("data")
            index = data_dict.get("index", 0)

            is_valid = self._validate_data(data)

            if is_valid:
                valid_count += 1
                validation_details = {
                    "timestamp": datetime.now().isoformat(),
                    "validator": name,
                    "data_length": len(str(data)),
                }
                self.emit(
                    "valid",
                    job_state=job_state,
                    data=data,
                    index=index,
                    validation_details=validation_details,
                )
            else:
                invalid_count += 1
                self.emit(
                    "invalid",
                    job_state=job_state,
                    error="Validation failed",
                    index=index,
                    original_data=data,
                )

        # Update counts in JobState
        routine_state = job_state.get_routine_state(self._id) or {}
        total_valid = routine_state.get("valid_count", 0) + valid_count
        total_invalid = routine_state.get("invalid_count", 0) + invalid_count
        job_state.update_routine_state(
            self._id, {"valid_count": total_valid, "invalid_count": total_invalid}
        )

        print(
            f"[{name}] ✓ Validated: {valid_count} valid, {invalid_count} invalid (total: {total_valid}/{total_invalid})"
        )

    def _validate_data(self, data):
        """Custom validation logic"""
        if not data:
            return False
        if str(data).startswith("INVALID"):
            return False
        return len(str(data)) > 0


class DataTransformer(Routine):
    """Transforms data - good for debug breakpoint testing"""

    def __init__(self, name="Transformer", transformation="uppercase"):
        super().__init__()
        self.set_config(name=name, transformation=transformation)
        self.input_slot = self.define_slot("input")
        self.output_event = self.define_event("output", ["result", "index", "transformation_type"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.transform)

    def transform(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = input_data[0] if input_data else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None
        index = data_dict.get("index", 0) if isinstance(data_dict, dict) else 0

        name = self.get_config("name", "Transformer")
        transformation = self.get_config("transformation", "uppercase")

        print(f"[{name}] Transforming: {data} (mode: {transformation})")
        time.sleep(0.2)  # Simulate processing - good for breakpoint testing

        # Apply transformation
        if transformation == "uppercase":
            result = str(data).upper()
        elif transformation == "lowercase":
            result = str(data).lower()
        elif transformation == "reverse":
            result = str(data)[::-1]
        elif transformation == "prefix":
            result = f"TRANSFORMED_{data}"
        else:
            result = str(data)

        # Update processed count in JobState
        routine_state = job_state.get_routine_state(self._id) or {}
        processed_count = routine_state.get("processed_count", 0) + 1
        job_state.update_routine_state(self._id, {"processed_count": processed_count})

        print(f"[{name}] → Result: {result}")
        self.emit(
            "output",
            job_state=job_state,
            result=result,
            index=index,
            transformation_type=transformation,
        )


class QueuePressureGenerator(Routine):
    """Generates queue pressure by processing items slowly - showcases queue monitoring"""

    def __init__(self, name="QueuePressureGenerator", processing_delay=0.5):
        super().__init__()
        self.set_config(name=name, processing_delay=processing_delay)
        self.input_slot = self.define_slot("input")
        self.output_event = self.define_event("output", ["result", "index", "processed_at"])
        # Use immediate policy but slow processing to build up queue
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.process)

    def process(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = input_data[0] if input_data else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None
        index = data_dict.get("index", 0) if isinstance(data_dict, dict) else 0

        name = self.get_config("name", "QueuePressureGenerator")
        delay = self.get_config("processing_delay", 0.5)

        print(f"[{name}] Processing: {data} (delay: {delay}s)")
        time.sleep(delay)  # Slow processing creates queue pressure

        result = f"Processed: {data}"
        processed_at = datetime.now().isoformat()

        print(f"[{name}] → {result}")
        self.emit(
            "output", job_state=job_state, result=result, index=index, processed_at=processed_at
        )


class DebugTargetRoutine(Routine):
    """Routine designed for debugging - has variables that can be inspected"""

    def __init__(self, name="DebugTarget"):
        super().__init__()
        self.set_config(name=name)
        self.input_slot = self.define_slot("input")
        self.output_event = self.define_event("output", ["result", "computed_value", "step"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.process)

    def process(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = input_data[0] if input_data else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None

        name = self.get_config("name", "DebugTarget")

        # These variables will be visible in debug session
        step = 1
        intermediate_value = str(data) if data else "default"
        step = 2
        computed_value = intermediate_value.upper() + "_PROCESSED"
        step = 3

        # Store in job_state for debugging
        routine_state = job_state.get_routine_state(self._id) or {}
        routine_state["step"] = step
        routine_state["intermediate_value"] = intermediate_value
        routine_state["computed_value"] = computed_value
        job_state.update_routine_state(self._id, routine_state)

        print(f"[{name}] Step {step}: {intermediate_value} -> {computed_value}")
        self.emit(
            "output",
            job_state=job_state,
            result=f"Debug result: {computed_value}",
            computed_value=computed_value,
            step=step,
        )


class StateTransitionDemo(Routine):
    """Demonstrates state transitions - can be paused/resumed/cancelled"""

    def __init__(self, name="StateTransitionDemo"):
        super().__init__()
        self.set_config(name=name)
        self.input_slot = self.define_slot("input")
        self.output_event = self.define_event("output", ["result", "state_info"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.process)

    def process(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = input_data[0] if input_data else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None

        name = self.get_config("name", "StateTransitionDemo")

        # Update state info
        routine_state = job_state.get_routine_state(self._id) or {}
        routine_state["processing_started"] = datetime.now().isoformat()
        routine_state["status"] = "processing"
        job_state.update_routine_state(self._id, routine_state)

        print(f"[{name}] Processing: {data} (state: processing)")
        time.sleep(0.5)

        routine_state["status"] = "completed"
        routine_state["processing_completed"] = datetime.now().isoformat()
        job_state.update_routine_state(self._id, routine_state)

        state_info = {
            "started": routine_state["processing_started"],
            "completed": routine_state["processing_completed"],
            "status": "completed",
        }

        print(f"[{name}] → Completed")
        self.emit("output", job_state=job_state, result=f"Processed: {data}", state_info=state_info)


class DataSink(Routine):
    """Receives and stores final result"""

    def __init__(self, name="Sink"):
        super().__init__()
        self.set_config(name=name)
        self.input_slot = self.define_slot("input")
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.receive)

    def receive(self, *slot_data_lists, policy_message, job_state):
        name = self.get_config("name", "Sink")

        received_data = {}
        if slot_data_lists and slot_data_lists[0]:
            for data_dict in slot_data_lists[0]:
                if isinstance(data_dict, dict):
                    received_data.update(data_dict)

        routine_state = job_state.get_routine_state(self._id) or {}
        received_count = routine_state.get("received_count", 0) + 1
        job_state.update_routine_state(
            self._id, {"received_count": received_count, "final_result": received_data}
        )
        print(f"[{name}] Receiving data (#{received_count})")
        time.sleep(0.1)
        print(f"[{name}] ✓ Final result: {received_data}")


class RateLimitedProcessor(Routine):
    """Processes data with rate limiting - demonstrates time_interval_policy"""

    def __init__(self, name="RateLimitedProcessor", interval_seconds=2.0):
        super().__init__()
        self.set_config(name=name, interval_seconds=interval_seconds)
        self.input_slot = self.define_slot("input")
        self.output_event = self.define_event("output", ["result", "index", "rate_limited_at"])
        self.set_activation_policy(time_interval_policy(interval_seconds))
        self.set_logic(self.process)

    def process(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        name = self.get_config("name", "RateLimitedProcessor")

        print(f"[{name}] Processing {len(input_data)} items (rate-limited)...")

        # Process all items in the batch
        for data_dict in input_data:
            if not isinstance(data_dict, dict):
                continue
            data = data_dict.get("data")
            index = data_dict.get("index", 0)

            result = f"Rate-limited: {data}"
            rate_limited_at = datetime.now().isoformat()

            self.emit(
                "output",
                job_state=job_state,
                result=result,
                index=index,
                rate_limited_at=rate_limited_at,
            )

        print(f"[{name}] ✓ Processed {len(input_data)} items")


class DataAggregator(Routine):
    """Aggregates data from multiple sources - demonstrates all_slots_ready_policy"""

    def __init__(self, name="Aggregator"):
        super().__init__()
        self.set_config(name=name)
        self.input1_slot = self.define_slot("input1")
        self.input2_slot = self.define_slot("input2")
        self.output_event = self.define_event("output", ["aggregated_data", "sources", "count"])
        # Wait for both inputs before processing
        self.set_activation_policy(all_slots_ready_policy())
        self.set_logic(self.aggregate)

    def aggregate(self, *slot_data_lists, policy_message, job_state):
        input1_data = (
            slot_data_lists[0]
            if slot_data_lists and len(slot_data_lists) > 0 and slot_data_lists[0]
            else []
        )
        input2_data = (
            slot_data_lists[1]
            if slot_data_lists and len(slot_data_lists) > 1 and slot_data_lists[1]
            else []
        )

        name = self.get_config("name", "Aggregator")

        # Extract data from both inputs
        data1 = input1_data[0] if input1_data and isinstance(input1_data[0], dict) else {}
        data2 = input2_data[0] if input2_data and isinstance(input2_data[0], dict) else {}

        # Aggregate
        aggregated = {
            "from_input1": data1.get("data") if isinstance(data1, dict) else None,
            "from_input2": data2.get("data") if isinstance(data2, dict) else None,
            "timestamp": datetime.now().isoformat(),
        }

        sources = []
        if data1:
            sources.append("input1")
        if data2:
            sources.append("input2")

        print(f"[{name}] Aggregating from {len(sources)} sources: {aggregated}")

        self.emit(
            "output",
            job_state=job_state,
            aggregated_data=aggregated,
            sources=sources,
            count=len(sources),
        )


class ErrorGenerator(Routine):
    """Generates errors for testing error handling - demonstrates error scenarios"""

    def __init__(self, name="ErrorGenerator", error_rate=0.3):
        super().__init__()
        self.set_config(name=name, error_rate=error_rate)
        self.input_slot = self.define_slot("input")
        self.success_event = self.define_event("success", ["result", "index"])
        self.error_event = self.define_event("error", ["error", "index", "original_data"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.process)

    def process(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        name = self.get_config("name", "ErrorGenerator")
        error_rate = self.get_config("error_rate", 0.3)

        import random

        for data_dict in input_data:
            if not isinstance(data_dict, dict):
                continue
            data = data_dict.get("data")
            index = data_dict.get("index", 0)

            # Randomly generate errors based on error_rate
            if random.random() < error_rate:
                error_msg = f"Simulated error processing: {data}"
                print(f"[{name}] ✗ Error: {error_msg}")
                self.emit(
                    "error", job_state=job_state, error=error_msg, index=index, original_data=data
                )
            else:
                result = f"Successfully processed: {data}"
                print(f"[{name}] ✓ {result}")
                self.emit("success", job_state=job_state, result=result, index=index)


class MultiSlotProcessor(Routine):
    """Processes data from multiple slots with different logic"""

    def __init__(self, name="MultiSlotProcessor"):
        super().__init__()
        self.set_config(name=name)
        self.primary_slot = self.define_slot("primary")
        self.secondary_slot = self.define_slot("secondary")
        self.output_event = self.define_event(
            "output", ["result", "primary_data", "secondary_data"]
        )
        # Process when primary has data (secondary is optional)
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.process)

    def process(self, *slot_data_lists, policy_message, job_state):
        primary_data = (
            slot_data_lists[0]
            if slot_data_lists and len(slot_data_lists) > 0 and slot_data_lists[0]
            else []
        )
        secondary_data = (
            slot_data_lists[1]
            if slot_data_lists and len(slot_data_lists) > 1 and slot_data_lists[1]
            else []
        )

        name = self.get_config("name", "MultiSlotProcessor")

        primary = primary_data[0] if primary_data and isinstance(primary_data[0], dict) else {}
        secondary = (
            secondary_data[0] if secondary_data and isinstance(secondary_data[0], dict) else {}
        )

        primary_value = primary.get("data") if isinstance(primary, dict) else None
        secondary_value = secondary.get("data") if isinstance(secondary, dict) else None

        result = f"Processed primary: {primary_value}, secondary: {secondary_value}"
        print(f"[{name}] {result}")

        self.emit(
            "output",
            job_state=job_state,
            result=result,
            primary_data=primary_value,
            secondary_data=secondary_value,
        )


class LoopController(Routine):
    """Controls loop execution - can emit to create loops in flows"""

    def __init__(self, name="LoopController", max_iterations=5):
        super().__init__()
        self.set_config(name=name, max_iterations=max_iterations)
        self.input_slot = self.define_slot("input")
        self.continue_event = self.define_event(
            "continue", ["iteration", "data", "should_continue"]
        )
        self.done_event = self.define_event("done", ["final_data", "iterations"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.control)

    def control(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        name = self.get_config("name", "LoopController")
        max_iterations = self.get_config("max_iterations", 5)

        routine_state = job_state.get_routine_state(self._id) or {}
        iteration = routine_state.get("iteration", 0) + 1
        routine_state["iteration"] = iteration
        job_state.update_routine_state(self._id, routine_state)

        data_dict = input_data[0] if input_data and isinstance(input_data[0], dict) else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None

        if iteration < max_iterations:
            should_continue = True
            print(f"[{name}] Iteration {iteration}/{max_iterations}: Continuing loop with {data}")
            self.emit(
                "continue",
                job_state=job_state,
                iteration=iteration,
                data=data,
                should_continue=should_continue,
            )
        else:
            should_continue = False
            print(f"[{name}] Iteration {iteration}/{max_iterations}: Loop complete")
            self.emit("done", job_state=job_state, final_data=data, iterations=iteration)


# ===== Flows =====


def create_state_transition_flow():
    """Flow demonstrating state transitions: pending -> running -> completed"""
    from routilux.factory.factory import ObjectFactory

    factory = ObjectFactory.get_instance()
    flow = Flow(flow_id="state_transition_flow")

    # Use factory to create routines (required for DSL export)
    source = factory.create("data_source", config={"name": "Source"})
    processor = factory.create("state_transition_demo", config={"name": "Processor"})
    sink = factory.create("data_sink", config={"name": "Sink"})

    src_id = flow.add_routine(source, "source")
    proc_id = flow.add_routine(processor, "processor")
    sink_id = flow.add_routine(sink, "sink")

    flow.connect(src_id, "output", proc_id, "input")
    flow.connect(proc_id, "output", sink_id, "input")

    return flow, src_id


def create_queue_pressure_flow():
    """Flow demonstrating queue pressure monitoring"""
    from routilux.factory.factory import ObjectFactory

    factory = ObjectFactory.get_instance()
    flow = Flow(flow_id="queue_pressure_flow")

    # Use factory to create routines (required for DSL export)
    source = factory.create("data_source", config={"name": "FastSource"})
    # Validator uses batch policy - will create queue pressure
    validator = factory.create("data_validator", config={"name": "BatchValidator"})
    # Slow processor creates more pressure
    processor = factory.create(
        "queue_pressure_generator", config={"name": "SlowProcessor", "processing_delay": 0.8}
    )
    sink = factory.create("data_sink", config={"name": "Sink"})

    src_id = flow.add_routine(source, "source")
    val_id = flow.add_routine(validator, "validator")
    proc_id = flow.add_routine(processor, "processor")
    sink_id = flow.add_routine(sink, "sink")

    flow.connect(src_id, "output", val_id, "input")
    flow.connect(val_id, "valid", proc_id, "input")
    flow.connect(proc_id, "output", sink_id, "input")

    return flow, src_id


def create_debug_demo_flow():
    """Flow designed for debugging demonstrations"""
    from routilux.factory.factory import ObjectFactory

    factory = ObjectFactory.get_instance()
    flow = Flow(flow_id="debug_demo_flow")

    # Use factory to create routines (required for DSL export)
    source = factory.create("data_source", config={"name": "Source"})
    transformer = factory.create(
        "data_transformer", config={"name": "Transformer", "transformation": "uppercase"}
    )
    debug_target = factory.create("debug_target", config={"name": "DebugTarget"})
    sink = factory.create("data_sink", config={"name": "Sink"})

    src_id = flow.add_routine(source, "source")
    trans_id = flow.add_routine(transformer, "transformer")
    debug_id = flow.add_routine(debug_target, "debug_target")
    sink_id = flow.add_routine(sink, "sink")

    flow.connect(src_id, "output", trans_id, "input")
    flow.connect(trans_id, "output", debug_id, "input")
    flow.connect(debug_id, "output", sink_id, "input")

    return flow, src_id


def create_comprehensive_demo_flow():
    """Comprehensive flow showcasing all features"""
    from routilux.factory.factory import ObjectFactory

    factory = ObjectFactory.get_instance()
    flow = Flow(flow_id="comprehensive_demo_flow")

    # Use factory to create routines (required for DSL export)
    source1 = factory.create("data_source", config={"name": "Source1"})
    source2 = factory.create("data_source", config={"name": "Source2"})
    validator = factory.create("data_validator", config={"name": "Validator"})
    transformer = factory.create(
        "data_transformer", config={"name": "Transformer", "transformation": "uppercase"}
    )
    queue_processor = factory.create(
        "queue_pressure_generator", config={"name": "QueueProcessor", "processing_delay": 0.3}
    )
    debug_target = factory.create("debug_target", config={"name": "DebugTarget"})
    sink = factory.create("data_sink", config={"name": "Sink"})

    src1_id = flow.add_routine(source1, "source1")
    src2_id = flow.add_routine(source2, "source2")
    val_id = flow.add_routine(validator, "validator")
    trans_id = flow.add_routine(transformer, "transformer")
    queue_id = flow.add_routine(queue_processor, "queue_processor")
    debug_id = flow.add_routine(debug_target, "debug_target")
    sink_id = flow.add_routine(sink, "sink")

    # Multiple sources -> validator (creates queue pressure)
    flow.connect(src1_id, "output", val_id, "input")
    flow.connect(src2_id, "output", val_id, "input")
    # Validator -> transformer -> queue processor -> debug target -> sink
    flow.connect(val_id, "valid", trans_id, "input")
    flow.connect(trans_id, "output", queue_id, "input")
    flow.connect(queue_id, "output", debug_id, "input")
    flow.connect(debug_id, "output", sink_id, "input")

    return flow, src1_id


def create_aggregator_flow():
    """Flow demonstrating aggregator pattern with all_slots_ready_policy"""
    from routilux.factory.factory import ObjectFactory

    factory = ObjectFactory.get_instance()
    flow = Flow(flow_id="aggregator_flow")

    # Use factory to create routines (required for DSL export)
    source1 = factory.create("data_source", config={"name": "Source1"})
    source2 = factory.create("data_source", config={"name": "Source2"})
    aggregator = factory.create("data_aggregator", config={"name": "Aggregator"})
    sink = factory.create("data_sink", config={"name": "Sink"})

    src1_id = flow.add_routine(source1, "source1")
    src2_id = flow.add_routine(source2, "source2")
    agg_id = flow.add_routine(aggregator, "aggregator")
    sink_id = flow.add_routine(sink, "sink")

    # Both sources -> aggregator (waits for both)
    flow.connect(src1_id, "output", agg_id, "input1")
    flow.connect(src2_id, "output", agg_id, "input2")
    flow.connect(agg_id, "output", sink_id, "input")

    return flow, src1_id


def create_branching_flow():
    """Flow demonstrating branching pattern - one source to multiple processors"""
    from routilux.factory.factory import ObjectFactory

    factory = ObjectFactory.get_instance()
    flow = Flow(flow_id="branching_flow")

    # Use factory to create routines (required for DSL export)
    source = factory.create("data_source", config={"name": "Source"})
    transformer1 = factory.create(
        "data_transformer", config={"name": "Transformer1", "transformation": "uppercase"}
    )
    transformer2 = factory.create(
        "data_transformer", config={"name": "Transformer2", "transformation": "lowercase"}
    )
    transformer3 = factory.create(
        "data_transformer", config={"name": "Transformer3", "transformation": "reverse"}
    )
    aggregator = factory.create("data_aggregator", config={"name": "FinalAggregator"})
    sink = factory.create("data_sink", config={"name": "Sink"})

    src_id = flow.add_routine(source, "source")
    trans1_id = flow.add_routine(transformer1, "transformer1")
    trans2_id = flow.add_routine(transformer2, "transformer2")
    trans3_id = flow.add_routine(transformer3, "transformer3")
    agg_id = flow.add_routine(aggregator, "aggregator")
    sink_id = flow.add_routine(sink, "sink")

    # Source branches to three transformers
    flow.connect(src_id, "output", trans1_id, "input")
    flow.connect(src_id, "output", trans2_id, "input")
    flow.connect(src_id, "output", trans3_id, "input")
    # Two transformers -> aggregator, one goes directly to sink
    flow.connect(trans1_id, "output", agg_id, "input1")
    flow.connect(trans2_id, "output", agg_id, "input2")
    flow.connect(trans3_id, "output", sink_id, "input")  # Direct path
    flow.connect(agg_id, "output", sink_id, "input")  # Aggregated path

    return flow, src_id


def create_rate_limited_flow():
    """Flow demonstrating rate limiting with time_interval_policy"""
    from routilux.factory.factory import ObjectFactory

    factory = ObjectFactory.get_instance()
    flow = Flow(flow_id="rate_limited_flow")

    # Use factory to create routines (required for DSL export)
    source = factory.create("data_source", config={"name": "FastSource"})
    rate_limited = factory.create(
        "rate_limited_processor", config={"name": "RateLimited", "interval_seconds": 2.0}
    )
    sink = factory.create("data_sink", config={"name": "Sink"})

    src_id = flow.add_routine(source, "source")
    rate_id = flow.add_routine(rate_limited, "rate_limited")
    sink_id = flow.add_routine(sink, "sink")

    flow.connect(src_id, "output", rate_id, "input")
    flow.connect(rate_id, "output", sink_id, "input")

    return flow, src_id


def create_error_handling_flow():
    """Flow demonstrating error handling scenarios"""
    from routilux.factory.factory import ObjectFactory

    factory = ObjectFactory.get_instance()
    flow = Flow(flow_id="error_handling_flow")

    # Use factory to create routines (required for DSL export)
    source = factory.create("data_source", config={"name": "Source"})
    error_gen = factory.create(
        "error_generator", config={"name": "ErrorGenerator", "error_rate": 0.4}
    )
    transformer = factory.create(
        "data_transformer", config={"name": "Transformer", "transformation": "uppercase"}
    )
    sink = factory.create("data_sink", config={"name": "Sink"})

    src_id = flow.add_routine(source, "source")
    err_id = flow.add_routine(error_gen, "error_generator")
    trans_id = flow.add_routine(transformer, "transformer")
    sink_id = flow.add_routine(sink, "sink")

    # Source -> error generator -> transformer (success path) -> sink
    flow.connect(src_id, "output", err_id, "input")
    flow.connect(err_id, "success", trans_id, "input")
    flow.connect(trans_id, "output", sink_id, "input")
    # Error path goes directly to sink
    flow.connect(err_id, "error", sink_id, "input")

    return flow, src_id


def create_loop_flow():
    """Flow demonstrating loop pattern with LoopController"""
    from routilux.factory.factory import ObjectFactory

    factory = ObjectFactory.get_instance()
    flow = Flow(flow_id="loop_flow")

    # Use factory to create routines (required for DSL export)
    source = factory.create("data_source", config={"name": "Source"})
    loop_controller = factory.create(
        "loop_controller", config={"name": "LoopController", "max_iterations": 5}
    )
    processor = factory.create(
        "data_transformer", config={"name": "Processor", "transformation": "uppercase"}
    )
    sink = factory.create("data_sink", config={"name": "Sink"})

    src_id = flow.add_routine(source, "source")
    loop_id = flow.add_routine(loop_controller, "loop_controller")
    proc_id = flow.add_routine(processor, "processor")
    sink_id = flow.add_routine(sink, "sink")

    # Source -> loop controller -> processor -> loop controller (loop) or sink (done)
    flow.connect(src_id, "output", loop_id, "input")
    flow.connect(loop_id, "continue", proc_id, "input")
    flow.connect(proc_id, "output", loop_id, "input")  # Loop back
    flow.connect(loop_id, "done", sink_id, "input")

    return flow, src_id


def create_multi_slot_flow():
    """Flow demonstrating multi-slot processing"""
    from routilux.factory.factory import ObjectFactory

    factory = ObjectFactory.get_instance()
    flow = Flow(flow_id="multi_slot_flow")

    # Use factory to create routines (required for DSL export)
    source1 = factory.create("data_source", config={"name": "PrimarySource"})
    source2 = factory.create("data_source", config={"name": "SecondarySource"})
    multi_processor = factory.create("multi_slot_processor", config={"name": "MultiSlotProcessor"})
    sink = factory.create("data_sink", config={"name": "Sink"})

    src1_id = flow.add_routine(source1, "primary_source")
    src2_id = flow.add_routine(source2, "secondary_source")
    multi_id = flow.add_routine(multi_processor, "multi_processor")
    sink_id = flow.add_routine(sink, "sink")

    flow.connect(src1_id, "output", multi_id, "primary")
    flow.connect(src2_id, "output", multi_id, "secondary")
    flow.connect(multi_id, "output", sink_id, "input")

    return flow, src1_id


# ===== Main =====


def main():
    """Create and register all demo flows"""
    print("=" * 80)
    print(" " * 15 + "Routilux Overseer - Comprehensive Demo")
    print("=" * 80)
    print("\nThis demo showcases ALL features of Routilux Overseer:")
    print("  ✓ Flow Visualization - Multiple flow patterns")
    print("  ✓ Job State Transitions - pending -> running -> completed/failed/paused/cancelled")
    print("  ✓ Queue Pressure Monitoring - Real-time queue status, pressure levels")
    print("  ✓ Debugging - Breakpoints, variables, step execution, call stack")
    print("  ✓ Error Handling - Various error scenarios")
    print("  ✓ Performance Testing - Fast and slow routines")
    print("  ✓ Real-time Events - WebSocket event streaming")
    print("\n" + "=" * 80)

    # Enable monitoring BEFORE importing flow_store
    print("\n[1/6] Enabling monitoring...")
    MonitoringRegistry.enable()

    # Import AFTER enabling monitoring
    from routilux.factory.factory import ObjectFactory
    from routilux.factory.metadata import ObjectMetadata
    from routilux.monitoring.flow_registry import FlowRegistry
    from routilux.runtime import Runtime

    from routilux.monitoring.runtime_registry import RuntimeRegistry
    from routilux.monitoring.storage import flow_store

    # Register runtimes in RuntimeRegistry
    print("\n[2/6] Registering runtimes in RuntimeRegistry...")
    runtime_registry = RuntimeRegistry.get_instance()

    # Create and register three runtimes for testing
    runtimes_to_create = [
        ("production", 0, True, "Production runtime using shared thread pool (recommended)"),
        ("development", 5, False, "Development runtime with small independent thread pool"),
        ("testing", 2, False, "Testing runtime with minimal thread pool for isolation"),
    ]

    for runtime_id, thread_pool_size, is_default, description in runtimes_to_create:
        runtime = Runtime(thread_pool_size=thread_pool_size)
        runtime_registry.register(runtime, runtime_id, is_default=is_default)
        pool_info = "shared pool" if thread_pool_size == 0 else f"{thread_pool_size} threads"
        default_info = " (default)" if is_default else ""
        print(f"  ✓ Registered: {runtime_id} ({pool_info}){default_info}")
        print(f"    {description}")

    # Register routines in factory
    print("\n[3/6] Registering routines in factory...")
    factory = ObjectFactory.get_instance()

    routine_registrations = [
        (
            "data_source",
            DataSource,
            "Generates sample data with metadata",
            "data_generation",
            ["source", "generator"],
        ),
        (
            "data_validator",
            DataValidator,
            "Validates input data with batch processing",
            "validation",
            ["validator", "batch"],
        ),
        (
            "data_transformer",
            DataTransformer,
            "Transforms data with various transformations",
            "transformation",
            ["transformer", "processor"],
        ),
        (
            "queue_pressure_generator",
            QueuePressureGenerator,
            "Generates queue pressure for monitoring",
            "monitoring",
            ["queue", "pressure"],
        ),
        (
            "debug_target",
            DebugTargetRoutine,
            "Routine designed for debugging demonstrations",
            "debugging",
            ["debug", "inspection"],
        ),
        (
            "state_transition_demo",
            StateTransitionDemo,
            "Demonstrates job state transitions",
            "state_management",
            ["state", "transition"],
        ),
        ("data_sink", DataSink, "Receives and stores final results", "sink", ["sink", "collector"]),
        (
            "rate_limited_processor",
            RateLimitedProcessor,
            "Processes data with rate limiting",
            "rate_limiting",
            ["rate_limit", "throttle"],
        ),
        (
            "data_aggregator",
            DataAggregator,
            "Aggregates data from multiple sources",
            "aggregation",
            ["aggregator", "merge"],
        ),
        (
            "error_generator",
            ErrorGenerator,
            "Generates errors for testing error handling",
            "error_handling",
            ["error", "testing"],
        ),
        (
            "multi_slot_processor",
            MultiSlotProcessor,
            "Processes data from multiple slots",
            "multi_slot",
            ["multi_slot", "parallel"],
        ),
        (
            "loop_controller",
            LoopController,
            "Controls loop execution in flows",
            "control_flow",
            ["loop", "control"],
        ),
    ]

    for name, routine_class, description, category, tags in routine_registrations:
        metadata = ObjectMetadata(
            name=name,
            description=description,
            category=category,
            tags=tags,
            example_config={"name": f"Example{name.title()}"},
            version="1.0.0",
        )
        factory.register(name, routine_class, metadata=metadata)
        print(f"  ✓ Registered: {name} ({category})")

    flows = []

    # Create all flows
    print("\n[4/6] Creating demo flows...")

    flows_to_create = [
        ("State Transition Flow", create_state_transition_flow),
        ("Queue Pressure Flow", create_queue_pressure_flow),
        ("Debug Demo Flow", create_debug_demo_flow),
        ("Comprehensive Demo Flow", create_comprehensive_demo_flow),
        ("Aggregator Flow", create_aggregator_flow),
        ("Branching Flow", create_branching_flow),
        ("Rate Limited Flow", create_rate_limited_flow),
        ("Error Handling Flow", create_error_handling_flow),
        ("Loop Flow", create_loop_flow),
        ("Multi Slot Flow", create_multi_slot_flow),
    ]

    for i, (name, creator) in enumerate(flows_to_create, 1):
        print(f"\n  {i}. Creating {name}...")
        flow, entry = creator()
        flow_store.add(flow)
        FlowRegistry.get_instance().register(flow)
        flows.append((name, flow, entry))

        # Register flow in factory for API discovery
        flow_metadata = ObjectMetadata(
            name=flow.flow_id,
            description=f"{name} - {flow.flow_id}",
            category="demo",
            tags=["demo", "flow", flow.flow_id.split("_")[0]],
            example_config={},
            version="1.0.0",
        )
        factory.register(flow.flow_id, flow, metadata=flow_metadata)

        print(f"     ✓ Flow ID: {flow.flow_id}")
        print(f"     ✓ Routines: {len(flow.routines)} ({', '.join(flow.routines.keys())})")
        print(f"     ✓ Connections: {len(flow.connections)}")
        print(f"     ✓ Entry Point: {entry}")
        print("     ✓ Registered in factory")

    print("\n" + "=" * 80)
    print("[6/6] All flows created successfully!")
    print("=" * 80)
    print(f"\nTotal flows created: {len(flows)}")
    print("\nFlow Summary:")
    for name, flow, entry in flows:
        print(f"  • {name:25s} ({flow.flow_id})")
        print(f"    Routines: {len(flow.routines):2d} | Connections: {len(flow.connections):2d}")

    # Register flows in registry by name
    print("\n[5/6] Registering flows in registry...")
    registry = FlowRegistry.get_instance()
    for name, flow, entry in flows:
        # Use a clean name for registry
        registry_name = flow.flow_id.replace("_", "-")
        try:
            registry.register_by_name(registry_name, flow)
            print(f"  ✓ Registered flow: {registry_name}")
        except ValueError:
            # Already registered, skip
            pass

    # Print testing suggestions
    print("\n" + "=" * 80)
    print("Testing Scenarios")
    print("=" * 80)
    print("\n1️⃣  State Transition Flow - Job state transitions")
    print("   Start job from: source")
    print("   Monitor: Job status changes (pending -> running -> completed)")
    print("   API: GET /api/jobs/{job_id} to see status transitions")
    print("   Start with runtime:")
    print("     POST /api/jobs")
    print('     {"flow_id": "state_transition_flow", "runtime_id": "production"}')
    print("\n2️⃣  Queue Pressure Flow - Queue monitoring")
    print("   Start job from: source")
    print("   Monitor: Queue status, pressure levels (low/medium/high/critical)")
    print("   API: GET /api/jobs/{job_id}/queues/status")
    print("   API: GET /api/jobs/{job_id}/routines/{routine_id}/queue-status")
    print("\n3️⃣  Debug Demo Flow - Debugging features")
    print("   Start job from: source")
    print("   Set breakpoint: POST /api/jobs/{job_id}/breakpoints")
    print("   Debug: GET /api/jobs/{job_id}/debug/variables")
    print("   Step: POST /api/jobs/{job_id}/debug/step-over")
    print("\n4️⃣  Comprehensive Demo Flow - All features combined")
    print("   Start job from: source1 or source2")
    print("   Monitor: State transitions, queue pressure, debug capabilities")
    print("   API: GET /api/jobs/{job_id}/monitoring (complete monitoring data)")
    print("\n5️⃣  Aggregator Flow - Multiple sources aggregation")
    print("   Start job from: source1 or source2")
    print("   Monitor: Aggregator waits for both inputs (all_slots_ready_policy)")
    print("   API: GET /api/jobs/{job_id}/routines/aggregator/status")
    print("\n6️⃣  Branching Flow - One source to multiple processors")
    print("   Start job from: source")
    print("   Monitor: Parallel processing in multiple transformers")
    print("   API: GET /api/jobs/{job_id}/routines to see all routine statuses")
    print("\n7️⃣  Rate Limited Flow - Rate limiting demonstration")
    print("   Start job from: source")
    print("   Monitor: Rate-limited processing (time_interval_policy)")
    print("   API: GET /api/jobs/{job_id}/routines/rate-limited/status")
    print("\n8️⃣  Error Handling Flow - Error scenarios")
    print("   Start job from: source")
    print("   Monitor: Success and error paths")
    print("   API: GET /api/jobs/{job_id}/routines/error-generator/status")
    print("\n9️⃣  Loop Flow - Loop pattern demonstration")
    print("   Start job from: source")
    print("   Monitor: Loop controller iterations")
    print("   API: GET /api/jobs/{job_id}/routines/loop-controller/status")
    print("\n🔟  Multi Slot Flow - Multi-slot processing")
    print("   Start job from: primary-source or secondary-source")
    print("   Monitor: Processing from multiple input slots")
    print("   API: GET /api/jobs/{job_id}/routines/multi-processor/status")
    print("\n📦 Factory Objects - Registered routines")
    print("   List: GET /api/factory/objects")
    print("   Details: GET /api/factory/objects/{name}")
    print("   Interface: GET /api/factory/objects/{name}/interface")
    print("   Filter by category: GET /api/factory/objects?category=data_generation")
    print("   Filter by type: GET /api/factory/objects?object_type=routine")
    print(
        "   Combined filter: GET /api/factory/objects?category=data_generation&object_type=routine"
    )

    print("\n⚙️  Runtime Management - Registered runtimes")
    print("   List: GET /api/runtimes")
    print("   Details: GET /api/runtimes/{runtime_id}")
    print("   Create: POST /api/runtimes")
    print("   Available runtimes:")
    for runtime_id, thread_pool_size, is_default, description in runtimes_to_create:
        default_marker = " (default)" if is_default else ""
        pool_info = "shared pool" if thread_pool_size == 0 else f"{thread_pool_size} threads"
        print(f"     • {runtime_id}: {description} ({pool_info}){default_marker}")
    print("\n   Start job with specific runtime:")
    print("     POST /api/jobs")
    print("     {")
    print('       "flow_id": "state_transition_flow",')
    print('       "runtime_id": "production"  // or "development", "testing", or omit for default')
    print("     }")
    print("\n   Test different runtimes:")
    print("     • Production: Uses shared thread pool (recommended)")
    print("     • Development: Small independent thread pool (5 threads)")
    print("     • Testing: Minimal thread pool (2 threads) for isolation")

    # Start API server
    print("\n" + "=" * 80)
    print("Starting API Server...")
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
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
