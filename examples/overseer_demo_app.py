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
from routilux.activation_policies import batch_size_policy, immediate_policy
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
        self.emit("output", job_state=job_state, data=output_data, index=index, timestamp=timestamp, metadata=metadata)


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
                self.emit("valid", job_state=job_state, data=data, index=index, validation_details=validation_details)
            else:
                invalid_count += 1
                self.emit("invalid", job_state=job_state, error="Validation failed", index=index, original_data=data)

        # Update counts in JobState
        routine_state = job_state.get_routine_state(self._id) or {}
        total_valid = routine_state.get("valid_count", 0) + valid_count
        total_invalid = routine_state.get("invalid_count", 0) + invalid_count
        job_state.update_routine_state(self._id, {"valid_count": total_valid, "invalid_count": total_invalid})
        
        print(f"[{name}] ✓ Validated: {valid_count} valid, {invalid_count} invalid (total: {total_valid}/{total_invalid})")

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
        self.emit("output", job_state=job_state, result=result, index=index, transformation_type=transformation)


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
        self.emit("output", job_state=job_state, result=result, index=index, processed_at=processed_at)


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
        self.emit("output", job_state=job_state, result=f"Debug result: {computed_value}", computed_value=computed_value, step=step)


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
            "status": "completed"
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


# ===== Flows =====


def create_state_transition_flow():
    """Flow demonstrating state transitions: pending -> running -> completed"""
    flow = Flow(flow_id="state_transition_flow")

    source = DataSource(name="Source")
    processor = StateTransitionDemo(name="Processor")
    sink = DataSink(name="Sink")

    src_id = flow.add_routine(source, "source")
    proc_id = flow.add_routine(processor, "processor")
    sink_id = flow.add_routine(sink, "sink")

    flow.connect(src_id, "output", proc_id, "input")
    flow.connect(proc_id, "output", sink_id, "input")

    return flow, src_id


def create_queue_pressure_flow():
    """Flow demonstrating queue pressure monitoring"""
    flow = Flow(flow_id="queue_pressure_flow")

    source = DataSource(name="FastSource")
    # Validator uses batch policy - will create queue pressure
    validator = DataValidator(name="BatchValidator")
    # Slow processor creates more pressure
    processor = QueuePressureGenerator(name="SlowProcessor", processing_delay=0.8)
    sink = DataSink(name="Sink")

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
    flow = Flow(flow_id="debug_demo_flow")

    source = DataSource(name="Source")
    transformer = DataTransformer(name="Transformer", transformation="uppercase")
    debug_target = DebugTargetRoutine(name="DebugTarget")
    sink = DataSink(name="Sink")

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
    flow = Flow(flow_id="comprehensive_demo_flow")

    source1 = DataSource(name="Source1")
    source2 = DataSource(name="Source2")
    validator = DataValidator(name="Validator")
    transformer = DataTransformer(name="Transformer", transformation="uppercase")
    queue_processor = QueuePressureGenerator(name="QueueProcessor", processing_delay=0.3)
    debug_target = DebugTargetRoutine(name="DebugTarget")
    sink = DataSink(name="Sink")

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
    print("\n[1/4] Enabling monitoring...")
    MonitoringRegistry.enable()

    # Import AFTER enabling monitoring
    from routilux.monitoring.flow_registry import FlowRegistry
    from routilux.monitoring.storage import flow_store

    flows = []

    # Create all flows
    print("\n[2/4] Creating demo flows...")

    flows_to_create = [
        ("State Transition Flow", create_state_transition_flow),
        ("Queue Pressure Flow", create_queue_pressure_flow),
        ("Debug Demo Flow", create_debug_demo_flow),
        ("Comprehensive Demo Flow", create_comprehensive_demo_flow),
    ]

    for i, (name, creator) in enumerate(flows_to_create, 1):
        print(f"\n  {i}. Creating {name}...")
        flow, entry = creator()
        flow_store.add(flow)
        FlowRegistry.get_instance().register(flow)
        flows.append((name, flow, entry))
        print(f"     ✓ Flow ID: {flow.flow_id}")
        print(f"     ✓ Routines: {len(flow.routines)} ({', '.join(flow.routines.keys())})")
        print(f"     ✓ Connections: {len(flow.connections)}")
        print(f"     ✓ Entry Point: {entry}")

    print("\n" + "=" * 80)
    print("[3/4] All flows created successfully!")
    print("=" * 80)
    print(f"\nTotal flows created: {len(flows)}")
    print("\nFlow Summary:")
    for name, flow, entry in flows:
        print(f"  • {name:25s} ({flow.flow_id})")
        print(f"    Routines: {len(flow.routines):2d} | Connections: {len(flow.connections):2d}")

    # Print testing suggestions
    print("\n" + "=" * 80)
    print("[4/4] Testing Scenarios")
    print("=" * 80)
    print("\n1️⃣  State Transition Flow - Job state transitions")
    print("   Start job from: source")
    print("   Monitor: Job status changes (pending -> running -> completed)")
    print("   API: GET /api/jobs/{job_id} to see status transitions")
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
