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
✓ State Management - Job state persistence (using JobState, not instance variables)
✓ Real-time Events - WebSocket event streaming
✓ Long-Running Flows - Extended execution with progress tracking
✓ Loop Flows - Circular flow patterns with iteration control

Key Improvements:
- All routines use JobState for execution state (no instance variable modifications)
- Long-running flow demonstrates extended execution times (60+ seconds)
- Loop flow demonstrates circular connections and iteration tracking
- Proper state management following Routilux best practices

Author: Routilux Overseer Team
Date: 2025-01-15
"""

import time
from datetime import datetime

from routilux import Flow, Routine
from routilux.activation_policies import immediate_policy
from routilux.monitoring.registry import MonitoringRegistry

# ===== Comprehensive Routines =====


class DataSource(Routine):
    """Generates sample data with metadata"""

    def __init__(self, name="DataSource"):
        super().__init__()
        self.set_config(name=name)
        self.trigger_slot = self.define_slot("trigger")
        self.output_event = self.define_event("output", ["data", "index", "timestamp", "metadata"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self._handle_trigger)

    def _handle_trigger(self, *slot_data_lists, policy_message, job_state):
        # Extract data from trigger slot (slot_data_lists[0] is a list of data dicts)
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
    """Validates input data with detailed logging"""

    def __init__(self, name="Validator"):
        super().__init__()
        self.set_config(name=name)
        self.input_slot = self.define_slot("input")
        self.valid_event = self.define_event("valid", ["data", "index", "validation_details"])
        self.invalid_event = self.define_event("invalid", ["error", "index", "original_data"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.validate)

    def validate(self, *slot_data_lists, policy_message, job_state):
        # Extract data from input slot (slot_data_lists[0] is a list of data dicts)
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = input_data[0] if input_data else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None
        index = data_dict.get("index", 0) if isinstance(data_dict, dict) else 0
        
        name = self.get_config("name", "Validator")

        print(f"[{name}] Validating: {data}")
        time.sleep(0.2)

        # Validation logic
        is_valid = self._validate_data(data)

        # Update counts in JobState
        routine_state = job_state.get_routine_state(self._id) or {}
        if is_valid:
            valid_count = routine_state.get("valid_count", 0) + 1
            job_state.update_routine_state(self._id, {"valid_count": valid_count})
        else:
            invalid_count = routine_state.get("invalid_count", 0) + 1
            job_state.update_routine_state(self._id, {"invalid_count": invalid_count})

        validation_details = {
            "timestamp": datetime.now().isoformat(),
            "validator": name,
            "data_length": len(str(data)),
        }

        if is_valid:
            routine_state = job_state.get_routine_state(self._id) or {}
            valid_count = routine_state.get("valid_count", 0)
            print(f"[{name}] ✓ Valid (total valid: {valid_count})")
            self.emit("valid", job_state=job_state, data=data, index=index, validation_details=validation_details)
        else:
            routine_state = job_state.get_routine_state(self._id) or {}
            invalid_count = routine_state.get("invalid_count", 0)
            print(f"[{name}] ✗ Invalid (total invalid: {invalid_count})")
            self.emit("invalid", job_state=job_state, error="Validation failed", index=index, original_data=data)

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
        self.set_config(name=name, transformation=transformation)
        self.input_slot = self.define_slot("input")
        self.output_event = self.define_event("output", ["result", "index", "transformation_type"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.transform)

    def transform(self, *slot_data_lists, policy_message, job_state):
        # Extract data from input slot
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = input_data[0] if input_data else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None
        index = data_dict.get("index", 0) if isinstance(data_dict, dict) else 0
        
        name = self.get_config("name", "Transformer")
        transformation = self.get_config("transformation", "uppercase")

        print(f"[{name}] Transforming: {data} (mode: {transformation})")
        time.sleep(0.3)

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


class DataMultiplier(Routine):
    """Multiplies/duplicates data with count"""

    def __init__(self, name="Multiplier"):
        super().__init__()
        self.set_config(name=name)
        self.input_slot = self.define_slot("input")
        self.output_event = self.define_event("output", ["result", "index", "multiplier"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.multiply)

    def multiply(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = input_data[0] if input_data else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None
        index = data_dict.get("index", 0) if isinstance(data_dict, dict) else 0
        multiplier = data_dict.get("multiplier", 2) if isinstance(data_dict, dict) else 2
        
        name = self.get_config("name", "Multiplier")
        print(f"[{name}] Multiplying: {data} (x{multiplier})")
        time.sleep(0.2)

        result = f"{data} " * multiplier
        print(f"[{name}] → Result: {result.strip()}")
        self.emit("output", job_state=job_state, result=result.strip(), index=index, multiplier=multiplier)


class DataAggregator(Routine):
    """Aggregates multiple inputs with detailed tracking"""

    def __init__(self, name="Aggregator"):
        super().__init__()
        self.set_config(name=name)
        self.input_slot = self.define_slot("input")
        self.output_event = self.define_event("output", ["results", "count", "sources"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.aggregate)

    def aggregate(self, *slot_data_lists, policy_message, job_state):
        name = self.get_config("name", "Aggregator")
        print(f"[{name}] Aggregating data...")
        time.sleep(0.3)

        # Collect all data from slot (slot_data_lists[0] is a list of data dicts)
        results = []
        sources = []
        if slot_data_lists and slot_data_lists[0]:
            for data_dict in slot_data_lists[0]:
                if isinstance(data_dict, dict):
                    # Extract all values from the data dict
                    for key, value in data_dict.items():
                        results.append(str(value))
                        sources.append(key)

        result = " | ".join(results) if results else ""
        print(f"[{name}] → Aggregated {len(results)} items: {result}")
        self.emit("output", job_state=job_state, results=result, count=len(results), sources=sources)


class DataSink(Routine):
    """Receives and stores final result with state"""

    def __init__(self, name="Sink"):
        super().__init__()
        self.set_config(name=name)
        self.input_slot = self.define_slot("input")
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.receive)

    def receive(self, *slot_data_lists, policy_message, job_state):
        name = self.get_config("name", "Sink")

        # Collect all received data (slot_data_lists[0] is a list of data dicts)
        received_data = {}
        if slot_data_lists and slot_data_lists[0]:
            for data_dict in slot_data_lists[0]:
                if isinstance(data_dict, dict):
                    received_data.update(data_dict)

        # Update received count in JobState
        routine_state = job_state.get_routine_state(self._id) or {}
        received_count = routine_state.get("received_count", 0) + 1
        job_state.update_routine_state(
            self._id, {"received_count": received_count, "final_result": received_data}
        )
        print(f"[{name}] Receiving data (#{received_count})")

        time.sleep(0.1)
        print(f"[{name}] ✓ Final result: {received_data}")


class ErrorGenerator(Routine):
    """Generates different types of errors for testing"""

    def __init__(self, name="ErrorGenerator"):
        super().__init__()
        self.set_config(name=name)
        self.input_slot = self.define_slot("input")
        self.output_event = self.define_event("output", ["result"])
        self.error_event = self.define_event("error", ["error_type", "error_message"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.process)

    def process(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = input_data[0] if input_data else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None
        error_type = data_dict.get("error_type", "none") if isinstance(data_dict, dict) else "none"
        
        name = self.get_config("name", "ErrorGenerator")
        print(f"[{name}] Processing: {data} (error_type={error_type})")
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
            self.emit("output", job_state=job_state, result=f"Success: {data}")


class SlowProcessor(Routine):
    """Slow processing for testing timing and patience"""

    def __init__(self, name="SlowProcessor"):
        super().__init__()
        self.set_config(name=name)
        self.input_slot = self.define_slot("input")
        self.output_event = self.define_event("output", ["result", "processing_time"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.process)

    def process(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = input_data[0] if input_data else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None
        
        name = self.get_config("name", "SlowProcessor")
        print(f"[{name}] Starting slow processing: {data}")
        start_time = time.time()
        time.sleep(2.0)  # Very slow processing
        processing_time = time.time() - start_time

        result = f"Slowly processed: {data}"
        print(f"[{name}] → Done in {processing_time:.2f}s")
        self.emit("output", job_state=job_state, result=result, processing_time=processing_time)


class FastProcessor(Routine):
    """Fast processing for performance testing"""

    def __init__(self, name="FastProcessor"):
        super().__init__()
        self.set_config(name=name)
        self.input_slot = self.define_slot("input")
        self.output_event = self.define_event("output", ["result", "count"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.process)

    def process(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = input_data[0] if input_data else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None
        
        name = self.get_config("name", "FastProcessor")

        # Update processed count in JobState
        routine_state = job_state.get_routine_state(self._id) or {}
        processed_count = routine_state.get("processed_count", 0) + 1
        job_state.update_routine_state(self._id, {"processed_count": processed_count})

        # Very fast processing
        time.sleep(0.01)
        self.emit("output", job_state=job_state, result=f"Fast: {data}", count=processed_count)


class ConditionalProcessor(Routine):
    """Processes data conditionally - great for breakpoint testing"""

    def __init__(self, name="ConditionalProcessor"):
        super().__init__()
        self.set_config(name=name)
        self.input_slot = self.define_slot("input")
        self.output_event = self.define_event("output", ["result", "condition"])
        self.branch_a_event = self.define_event("branch_a", ["result"])
        self.branch_b_event = self.define_event("branch_b", ["result"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.process)

    def process(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = input_data[0] if input_data else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None
        condition = data_dict.get("condition", "default") if isinstance(data_dict, dict) else "default"
        
        name = self.get_config("name", "ConditionalProcessor")
        print(f"[{name}] Processing with condition: {condition}")

        if condition == "branch_a":
            result = f"Branch A processed: {data}"
            print(f"[{name}] → Taking Branch A")
            self.emit("branch_a", job_state=job_state, result=result)
            self.emit("output", job_state=job_state, result=result, condition="branch_a")
        elif condition == "branch_b":
            result = f"Branch B processed: {data}"
            print(f"[{name}] → Taking Branch B")
            self.emit("branch_b", job_state=job_state, result=result)
            self.emit("output", job_state=job_state, result=result, condition="branch_b")
        else:
            result = f"Default processed: {data}"
            print(f"[{name}] → Default path")
            self.emit("output", job_state=job_state, result=result, condition="default")


class Counter(Routine):
    """Counter routine for breakpoint testing"""

    def __init__(self, name="Counter"):
        super().__init__()
        self.set_config(name=name)
        self.input_slot = self.define_slot("input")
        self.output_event = self.define_event("output", ["count", "message"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.increment)

    def increment(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = input_data[0] if input_data else {}
        steps = data_dict.get("steps", 1) if isinstance(data_dict, dict) else 1
        
        name = self.get_config("name", "Counter")

        print(f"[{name}] Incrementing by {steps}")
        time.sleep(0.1)

        # Update count in JobState
        routine_state = job_state.get_routine_state(self._id) or {}
        count = routine_state.get("count", 0) + steps
        job_state.update_routine_state(self._id, {"count": count})

        message = f"Count is now {count}"
        print(f"[{name}] → {message}")
        self.emit("output", job_state=job_state, count=count, message=message)


class LongRunningProcessor(Routine):
    """Long-running processor for testing extended execution times"""

    def __init__(self, name="LongRunningProcessor", duration=60):
        super().__init__()
        self.set_config(name=name, duration=duration)
        self.input_slot = self.define_slot("input")
        self.progress_event = self.define_event("progress", ["progress", "elapsed", "message"])
        self.output_event = self.define_event("output", ["result", "total_time", "iterations"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.process)

    def process(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = input_data[0] if input_data else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None
        
        name = self.get_config("name", "LongRunningProcessor")
        duration = self.get_config("duration", 60)

        print(f"[{name}] Starting long-running process: {data} (duration: {duration}s)")
        start_time = time.time()
        iteration = 0

        # Process in chunks with progress updates
        chunk_duration = 5.0  # Report progress every 5 seconds

        while time.time() - start_time < duration:
            iteration += 1
            elapsed = time.time() - start_time
            progress = min(100, (elapsed / duration) * 100)

            # Emit progress event
            self.emit(
                "progress",
                job_state=job_state,
                progress=progress,
                elapsed=elapsed,
                message=f"Processing iteration {iteration}...",
            )

            # Update state in JobState
            job_state.update_routine_state(
                self._id,
                {"iteration": iteration, "elapsed": elapsed, "progress": progress},
            )

            print(f"[{name}] Progress: {progress:.1f}% ({elapsed:.1f}s / {duration}s)")
            time.sleep(chunk_duration)

        total_time = time.time() - start_time
        result = f"Long-running process completed: {data}"
        print(f"[{name}] → Done in {total_time:.2f}s ({iteration} iterations)")

        self.emit("output", job_state=job_state, result=result, total_time=total_time, iterations=iteration)


class LoopController(Routine):
    """Controls loop execution with iteration tracking"""

    def __init__(self, name="LoopController", max_iterations=5):
        super().__init__()
        self.set_config(name=name, max_iterations=max_iterations)
        self.input_slot = self.define_slot("input")
        self.continue_loop_event = self.define_event(
            "continue_loop", ["iteration", "data", "reason"]
        )
        self.exit_loop_event = self.define_event(
            "exit_loop", ["final_data", "iterations", "reason"]
        )
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.control_loop)

    def control_loop(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = input_data[0] if input_data else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None
        iteration = data_dict.get("iteration") if isinstance(data_dict, dict) else None
        
        name = self.get_config("name", "LoopController")
        max_iterations = self.get_config("max_iterations", 5)

        # Get current iteration from JobState or parameter
        routine_state = job_state.get_routine_state(self._id) or {}
        current_iteration = iteration or routine_state.get("iteration", 0)

        print(f"[{name}] Loop control: iteration {current_iteration}/{max_iterations}")

        # Check if we should continue or exit
        # Continue if: iteration < max_iterations AND (data is invalid or needs retry)
        should_continue = current_iteration < max_iterations

        # Simple validation: continue if data doesn't contain "COMPLETE"
        needs_retry = data and "COMPLETE" not in str(data).upper()

        if should_continue and needs_retry:
            next_iteration = current_iteration + 1
            job_state.update_routine_state(self._id, {"iteration": next_iteration})

            print(f"[{name}] → Continuing loop (iteration {next_iteration})")
            self.emit("continue_loop", job_state=job_state, iteration=next_iteration, data=data, reason="needs_retry")
        else:
            reason = "max_iterations_reached" if not should_continue else "validation_passed"
            job_state.update_routine_state(
                self._id, {"iteration": current_iteration, "completed": True}
            )

            print(f"[{name}] → Exiting loop (reason: {reason})")
            self.emit("exit_loop", job_state=job_state, final_data=data, iterations=current_iteration + 1, reason=reason)


class LoopProcessor(Routine):
    """Processes data in a loop, simulating work that may need retries"""

    def __init__(self, name="LoopProcessor"):
        super().__init__()
        self.set_config(name=name)
        self.input_slot = self.define_slot("input")
        self.output_event = self.define_event("output", ["result", "iteration", "status"])
        self.set_activation_policy(immediate_policy())
        self.set_logic(self.process)

    def process(self, *slot_data_lists, policy_message, job_state):
        input_data = slot_data_lists[0] if slot_data_lists and slot_data_lists[0] else []
        data_dict = input_data[0] if input_data else {}
        data = data_dict.get("data") if isinstance(data_dict, dict) else None
        iteration = data_dict.get("iteration", 0) if isinstance(data_dict, dict) else 0
        
        name = self.get_config("name", "LoopProcessor")

        print(f"[{name}] Processing (iteration {iteration}): {data}")
        time.sleep(0.5)  # Simulate processing time

        # Simulate: sometimes processing succeeds, sometimes needs retry
        # Success probability increases with iteration
        import random

        success_probability = min(0.9, 0.3 + (iteration * 0.15))
        is_success = random.random() < success_probability

        if is_success:
            result = f"COMPLETE: {data} (processed in {iteration} iterations)"
            status = "success"
        else:
            result = f"RETRY: {data} (iteration {iteration})"
            status = "retry_needed"

        print(f"[{name}] → {result}")
        self.emit("output", job_state=job_state, result=result, iteration=iteration, status=status)


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


def create_long_running_flow():
    """Long-running flow for testing extended execution times"""
    flow = Flow(flow_id="long_running_flow", execution_timeout=600.0)  # 10 minute timeout

    source = DataSource(name="LongRunningSource")
    long_processor = LongRunningProcessor(name="LongProcessor", duration=60)  # 60 seconds
    sink = DataSink(name="LongRunningSink")

    src_id = flow.add_routine(source, "source")
    processor_id = flow.add_routine(long_processor, "processor")
    sink_id = flow.add_routine(sink, "sink")

    # Connect: source -> processor -> sink
    flow.connect(src_id, "output", processor_id, "input")
    flow.connect(processor_id, "output", sink_id, "input")

    return flow, src_id


def create_loop_flow():
    """Flow with a loop pattern: Source -> Processor -> LoopController -> (back to Processor or exit) -> Sink"""
    flow = Flow(flow_id="loop_flow")

    source = DataSource(name="LoopSource")
    processor = LoopProcessor(name="LoopProcessor")
    loop_controller = LoopController(name="LoopController", max_iterations=5)
    sink = DataSink(name="LoopSink")

    src_id = flow.add_routine(source, "source")
    proc_id = flow.add_routine(processor, "processor")
    controller_id = flow.add_routine(loop_controller, "loop_controller")
    sink_id = flow.add_routine(sink, "sink")

    # Initial path: source -> processor -> loop_controller
    flow.connect(src_id, "output", proc_id, "input")
    flow.connect(proc_id, "output", controller_id, "input")

    # Loop: loop_controller.continue_loop -> processor (creates a cycle)
    flow.connect(
        controller_id,
        "continue_loop",
        proc_id,
        "input",
        param_mapping={"data": "data", "iteration": "iteration"},
    )

    # Exit: loop_controller.exit_loop -> sink
    flow.connect(controller_id, "exit_loop", sink_id, "input", param_mapping={"final_data": "data"})

    return flow, src_id


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


def demo_long_running_flow(flow_store, duration=60):
    """Start a long-running flow job"""
    flow = flow_store.get("long_running_flow")
    if flow:
        # Update processor duration if needed
        processor = flow.routines.get("processor")
        if processor:
            processor.set_config(duration=duration)
        job_id = flow.start(
            entry_routine_id="source", entry_params={"data": f"Long Running Test ({duration}s)"}
        )
        print(f"\n✓ Started long-running flow job: {job_id} (duration: {duration}s)")
        return job_id


def demo_loop_flow(flow_store, max_iterations=5):
    """Start a loop flow job"""
    flow = flow_store.get("loop_flow")
    if flow:
        # Update loop controller max_iterations if needed
        controller = flow.routines.get("loop_controller")
        if controller:
            controller.set_config(max_iterations=max_iterations)
        job_id = flow.start(entry_routine_id="source", entry_params={"data": "Loop Test"})
        print(f"\n✓ Started loop flow job: {job_id} (max_iterations: {max_iterations})")
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
        ("Long Running Flow", create_long_running_flow),
        ("Loop Flow", create_loop_flow),
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
    print("\n7️⃣  Long Running Flow - Extended execution testing")
    print("   Start job from: source")
    print("   Expected: Flow runs for 60+ seconds with progress updates")
    print("   Use for: Testing monitoring, job persistence, timeout handling")
    print("\n8️⃣  Loop Flow - Circular flow pattern")
    print("   Start job from: source")
    print("   Expected: Processor loops back through LoopController until completion")
    print("   Use for: Testing loop detection, iteration tracking, cycle handling")

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
