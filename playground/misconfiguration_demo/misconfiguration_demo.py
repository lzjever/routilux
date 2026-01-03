"""
Misconfiguration demonstration for routilux.

This demo shows potential issues when users incorrectly configure routine connections:
1. Circular connections (A -> B -> A) that may cause infinite loops
2. Unconnected events (events emitted but no slots connected)
3. Unconnected slots (slots defined but no events connected)
4. Memory leaks from excessive event emissions without handlers

Scenario:
    A data processing workflow where:
    - Processor processes data and sends to Validator
    - Validator validates and may send back to Processor (circular)
    - Some routines emit events that are never connected
    - Some routines have slots that are never connected
    - The loop continues until a condition is met (or doesn't stop if misconfigured)
"""

import time
import threading
from typing import Dict, Any, Optional, Tuple
from routilux import Flow, Routine
from routilux.job_state import JobState


class DataProcessor(Routine):
    """Processor that processes data and sends to validator.
    
    This routine:
    - Processes data and increments a counter
    - Emits 'output' event (connected to validator)
    - Emits 'unconnected_event' (NOT connected to anything - potential memory leak)
    - Has an 'unconnected_slot' (defined but never connected - unused)
    """
    
    def __init__(self, max_iterations: int = 10):
        """Initialize processor.
        
        Args:
            max_iterations: Maximum number of processing iterations before stopping.
        """
        super().__init__()
        self.max_iterations = max_iterations
        self.iteration_count = 0
        
        # Define slots
        self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)  # Entry point
        self.loopback_slot = self.define_slot("loopback", handler=self._handle_loopback)
        self.unconnected_slot = self.define_slot("unconnected", handler=self._handle_unconnected)
        
        # Define events
        self.output_event = self.define_event("output", ["data", "iteration"])
        self.unconnected_event = self.define_event("unconnected_event", ["data"])
        self.loopback_event = self.define_event("loopback", ["data", "iteration"])
    
    def _handle_trigger(self, data: Any = None, **kwargs):
        """Handle trigger (entry point)."""
        print(f"  [Processor] Triggered with initial input: {data}")
        self._process_and_emit(data)
    
    def _handle_loopback(self, data: Any = None, **kwargs):
        """Handle loopback data from validator."""
        self.iteration_count += 1
        print(f"  [Processor] Received loopback (iteration {self.iteration_count}/{self.max_iterations}): {data}")
        
        if self.iteration_count >= self.max_iterations:
            print(f"  [Processor] ⚠️  Max iterations reached! Stopping loop.")
            # Emit final event to stop the loop
            self.emit("output", data=f"final_{data}", iteration=self.iteration_count)
            return
        
        # Continue processing
        self._process_and_emit(data)
    
    def _handle_unconnected(self, data: Any = None, **kwargs):
        """Handle unconnected slot (should never be called)."""
        print(f"  [Processor] ⚠️  UNEXPECTED: Unconnected slot received data: {data}")
    
    def _process_and_emit(self, data: Any):
        """Process data and emit events."""
        processed_data = f"processed_{data}_{self.iteration_count}"
        
        # Emit to connected validator
        print(f"  [Processor] Emitting 'output' event: {processed_data}")
        self.emit("output", data=processed_data, iteration=self.iteration_count)
        
        # Emit to UNCONNECTED event (potential memory leak if not handled)
        print(f"  [Processor] ⚠️  Emitting 'unconnected_event' (no slots connected): {processed_data}")
        self.emit("unconnected_event", data=processed_data)
        
        # Small delay to make output readable
        time.sleep(0.1)


class DataValidator(Routine):
    """Validator that validates data and may send back to processor.
    
    This routine:
    - Validates data
    - If validation fails, sends back to processor (creating a loop)
    - If validation passes, sends to finalizer
    - Also has an unconnected event
    """
    
    def __init__(self, validation_threshold: int = 5):
        """Initialize validator.
        
        Args:
            validation_threshold: Number of iterations before validation passes.
        """
        super().__init__()
        self.validation_threshold = validation_threshold
        self.validation_count = 0
        
        # Define slots
        self.input_slot = self.define_slot("input", handler=self._handle_input)
        
        # Define events
        self.output_event = self.define_event("output", ["data", "validated"])
        self.loopback_event = self.define_event("loopback", ["data", "iteration"])
        self.unconnected_event = self.define_event("unconnected_validator_event", ["data"])
    
    def _handle_input(self, data: Any = None, **kwargs):
        """Handle input data from processor."""
        iteration = kwargs.get("iteration", 0)
        self.validation_count += 1
        
        print(f"  [Validator] Validating data: {data} (validation count: {self.validation_count})")
        
        # Simulate validation logic
        if "final_" in str(data):
            # Final data, send to output
            print(f"  [Validator] ✅ Validation passed (final data), sending to output")
            self.emit("output", data=data, validated=True)
        elif iteration < self.validation_threshold:
            # Validation fails, send back to processor (LOOP!)
            print(f"  [Validator] ⚠️  Validation failed (iteration {iteration} < {self.validation_threshold}), sending back to processor (LOOP)")
            self.emit("loopback", data=data, iteration=iteration)
            
            # Also emit unconnected event (potential memory leak)
            print(f"  [Validator] ⚠️  Emitting 'unconnected_validator_event' (no slots connected)")
            self.emit("unconnected_validator_event", data=data)
        else:
            # Validation passes, send to output
            print(f"  [Validator] ✅ Validation passed, sending to output")
            self.emit("output", data=data, validated=True)
        
        time.sleep(0.1)


class DataFinalizer(Routine):
    """Final routine that receives validated data."""
    
    def __init__(self):
        """Initialize finalizer."""
        super().__init__()
        self.received_data = []
        
        # Define slots
        self.input_slot = self.define_slot("input", handler=self._handle_input)
    
    def _handle_input(self, data: Any = None, **kwargs):
        """Handle final input."""
        validated = kwargs.get("validated", False)
        print(f"  [Finalizer] ✅ Received validated data: {data} (validated={validated})")
        self.received_data.append(data)


class MemoryMonitor:
    """Monitor memory usage and task queue size."""
    
    def __init__(self, flow: Flow):
        """Initialize monitor.
        
        Args:
            flow: Flow object to monitor.
        """
        self.flow = flow
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.max_queue_size = 0
        self.max_active_tasks = 0
    
    def start(self):
        """Start monitoring."""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop(self):
        """Stop monitoring."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
    
    def _monitor_loop(self):
        """Monitor loop."""
        while self.monitoring:
            try:
                queue_size = self.flow._task_queue.qsize()
                with self.flow._execution_lock:
                    active_tasks = len([f for f in self.flow._active_tasks if not f.done()])
                
                self.max_queue_size = max(self.max_queue_size, queue_size)
                self.max_active_tasks = max(self.max_active_tasks, active_tasks)
                
                if queue_size > 0 or active_tasks > 0:
                    print(f"    [Monitor] Queue size: {queue_size}, Active tasks: {active_tasks}")
                
                time.sleep(0.2)
            except Exception as e:
                print(f"    [Monitor] Error: {e}")
                break
    
    def get_stats(self) -> Dict[str, int]:
        """Get monitoring statistics.
        
        Returns:
            Dictionary with max_queue_size and max_active_tasks.
        """
        return {
            "max_queue_size": self.max_queue_size,
            "max_active_tasks": self.max_active_tasks,
        }


def create_misconfigured_flow(
    max_iterations: int = 10,
    validation_threshold: int = 5,
) -> Tuple[Flow, str]:
    """Create a flow with misconfigurations.
    
    Misconfigurations:
    1. Circular connection: Processor -> Validator -> Processor (loopback)
    2. Unconnected events: Processor.unconnected_event, Validator.unconnected_validator_event
    3. Unconnected slot: Processor.unconnected_slot
    
    Args:
        max_iterations: Maximum iterations before processor stops.
        validation_threshold: Validation threshold for validator.
    
    Returns:
        Tuple of (Flow, entry_routine_id).
    """
    print("=" * 80)
    print("Creating Misconfigured Flow")
    print("=" * 80)
    
    flow = Flow(flow_id="misconfiguration_demo", execution_strategy="sequential")
    
    # Create routines
    processor = DataProcessor(max_iterations=max_iterations)
    validator = DataValidator(validation_threshold=validation_threshold)
    finalizer = DataFinalizer()
    
    # Add routines to flow
    processor_id = flow.add_routine(processor, "processor")
    validator_id = flow.add_routine(validator, "validator")
    finalizer_id = flow.add_routine(finalizer, "finalizer")
    
    print(f"\nRoutines added:")
    print(f"  - Processor: {processor_id}")
    print(f"  - Validator: {validator_id}")
    print(f"  - Finalizer: {finalizer_id}")
    
    # ⚠️ MISCONFIGURATION 1: Circular connection
    print(f"\n⚠️  MISCONFIGURATION 1: Creating circular connection")
    print(f"  Processor.output -> Validator.input")
    flow.connect(processor_id, "output", validator_id, "input")
    
    print(f"  Validator.loopback -> Processor.loopback (CIRCULAR!)")
    flow.connect(validator_id, "loopback", processor_id, "loopback")
    
    # Normal connection to finalizer
    print(f"  Validator.output -> Finalizer.input")
    flow.connect(validator_id, "output", finalizer_id, "input")
    
    # ⚠️ MISCONFIGURATION 2: Unconnected events
    print(f"\n⚠️  MISCONFIGURATION 2: Unconnected events (will emit but no one receives)")
    print(f"  - Processor.unconnected_event (NOT connected)")
    print(f"  - Validator.unconnected_validator_event (NOT connected)")
    
    # ⚠️ MISCONFIGURATION 3: Unconnected slot
    print(f"\n⚠️  MISCONFIGURATION 3: Unconnected slot (defined but never used)")
    print(f"  - Processor.unconnected_slot (NOT connected)")
    
    print(f"\nFlow structure:")
    print(f"  Processor -> Validator -> Processor (LOOP)")
    print(f"  Validator -> Finalizer (when validation passes)")
    print(f"  Processor.unconnected_event -> (nothing)")
    print(f"  Validator.unconnected_validator_event -> (nothing)")
    print(f"  Processor.unconnected_slot <- (nothing)")
    
    return flow, processor_id


def test_scenario_1_controlled_loop():
    """Test scenario 1: Controlled loop that stops after max_iterations."""
    print("\n" + "=" * 80)
    print("Scenario 1: Controlled Loop (Should Stop)")
    print("=" * 80)
    print("\nThis scenario tests a circular connection that should stop after max_iterations.")
    print("The loop: Processor -> Validator -> Processor (loopback)")
    print("Expected: Loop continues until max_iterations, then stops and sends to Finalizer")
    
    flow, entry_id = create_misconfigured_flow(max_iterations=5, validation_threshold=10)
    
    # Start monitoring
    monitor = MemoryMonitor(flow)
    monitor.start()
    
    try:
        print(f"\nStarting execution...")
        job_state = flow.execute(entry_id, entry_params={"data": "initial_data"})
        
        print(f"\nJob ID: {job_state.job_id}")
        print(f"Waiting for completion...")
        
        # Wait for completion with timeout
        completed = JobState.wait_for_completion(flow, job_state, timeout=10.0, check_interval=0.2)
        
        if completed:
            print(f"\n✅ Execution completed!")
            print(f"  Status: {job_state.status}")
            print(f"  Execution history: {len(job_state.execution_history)} records")
        else:
            print(f"\n⚠️  Execution timed out or didn't complete")
            print(f"  Status: {job_state.status}")
        
        # Check finalizer
        finalizer = flow.routines["finalizer"]
        if hasattr(finalizer, "received_data") and finalizer.received_data:
            print(f"\n✅ Finalizer received {len(finalizer.received_data)} data items")
            for i, data in enumerate(finalizer.received_data, 1):
                print(f"  {i}. {data}")
        else:
            print(f"\n⚠️  Finalizer did not receive any data")
        
        # Monitor stats
        stats = monitor.get_stats()
        print(f"\n📊 Memory Monitor Stats:")
        print(f"  Max queue size: {stats['max_queue_size']}")
        print(f"  Max active tasks: {stats['max_active_tasks']}")
        
        if stats['max_queue_size'] > 100:
            print(f"  ⚠️  WARNING: Queue size exceeded 100! Potential memory leak!")
        if stats['max_active_tasks'] > 50:
            print(f"  ⚠️  WARNING: Active tasks exceeded 50! Potential resource leak!")
        
    finally:
        monitor.stop()
    
    return flow, job_state


def test_scenario_2_potential_infinite_loop():
    """Test scenario 2: Potential infinite loop (high threshold)."""
    print("\n" + "=" * 80)
    print("Scenario 2: Potential Infinite Loop")
    print("=" * 80)
    print("\nThis scenario tests a circular connection with high validation threshold.")
    print("The loop: Processor -> Validator -> Processor (loopback)")
    print("Expected: Loop continues until max_iterations, then stops")
    print("⚠️  If max_iterations is too high, this could run for a long time!")
    
    flow, entry_id = create_misconfigured_flow(max_iterations=3, validation_threshold=100)
    
    # Start monitoring
    monitor = MemoryMonitor(flow)
    monitor.start()
    
    try:
        print(f"\nStarting execution...")
        job_state = flow.execute(entry_id, entry_params={"data": "initial_data"})
        
        print(f"\nJob ID: {job_state.job_id}")
        print(f"Waiting for completion (with timeout to prevent infinite loop)...")
        
        # Wait with shorter timeout to prevent infinite loop
        completed = JobState.wait_for_completion(flow, job_state, timeout=5.0, check_interval=0.2)
        
        if completed:
            print(f"\n✅ Execution completed!")
            print(f"  Status: {job_state.status}")
        else:
            print(f"\n⚠️  Execution timed out (this is expected if loop doesn't stop)")
            print(f"  Status: {job_state.status}")
        
        # Monitor stats
        stats = monitor.get_stats()
        print(f"\n📊 Memory Monitor Stats:")
        print(f"  Max queue size: {stats['max_queue_size']}")
        print(f"  Max active tasks: {stats['max_active_tasks']}")
        
        if stats['max_queue_size'] > 100:
            print(f"  ⚠️  WARNING: Queue size exceeded 100! Potential memory leak!")
        
    finally:
        monitor.stop()
    
    return flow, job_state


def test_scenario_3_unconnected_events():
    """Test scenario 3: Unconnected events (should not cause memory leak)."""
    print("\n" + "=" * 80)
    print("Scenario 3: Unconnected Events")
    print("=" * 80)
    print("\nThis scenario tests if emitting to unconnected events causes memory leaks.")
    print("Expected: Events are emitted but no tasks are created (no slots connected)")
    print("          This should NOT cause memory leaks if framework handles it correctly")
    
    flow, entry_id = create_misconfigured_flow(max_iterations=3, validation_threshold=2)
    
    # Start monitoring
    monitor = MemoryMonitor(flow)
    monitor.start()
    
    try:
        print(f"\nStarting execution...")
        job_state = flow.execute(entry_id, entry_params={"data": "initial_data"})
        
        print(f"\nJob ID: {job_state.job_id}")
        print(f"Waiting for completion...")
        
        completed = JobState.wait_for_completion(flow, job_state, timeout=5.0, check_interval=0.2)
        
        if completed:
            print(f"\n✅ Execution completed!")
            print(f"  Status: {job_state.status}")
        else:
            print(f"\n⚠️  Execution timed out")
            print(f"  Status: {job_state.status}")
        
        # Monitor stats
        stats = monitor.get_stats()
        print(f"\n📊 Memory Monitor Stats:")
        print(f"  Max queue size: {stats['max_queue_size']}")
        print(f"  Max active tasks: {stats['max_active_tasks']}")
        
        if stats['max_queue_size'] == 0:
            print(f"  ✅ Good: Queue size stayed at 0 (unconnected events don't create tasks)")
        else:
            print(f"  ⚠️  Queue size > 0: {stats['max_queue_size']} tasks were created")
        
    finally:
        monitor.stop()
    
    return flow, job_state


def analyze_results(flows_and_states):
    """Analyze results from all scenarios.
    
    Args:
        flows_and_states: List of (flow, job_state) tuples.
    """
    print("\n" + "=" * 80)
    print("Analysis Summary")
    print("=" * 80)
    
    print("\nKey Findings:")
    print("1. Circular Connections:")
    print("   - Framework should handle controlled loops (with termination condition)")
    print("   - Infinite loops can occur if termination condition is never met")
    print("   - Framework should provide timeout protection")
    
    print("\n2. Unconnected Events:")
    print("   - Events emitted to unconnected slots should NOT create tasks")
    print("   - This prevents memory leaks from orphaned events")
    print("   - Framework should handle this gracefully")
    
    print("\n3. Unconnected Slots:")
    print("   - Slots that are never connected simply don't receive data")
    print("   - This is not a problem, just unused functionality")
    
    print("\n4. Memory Leak Prevention:")
    print("   - Framework should limit queue size")
    print("   - Framework should provide timeout mechanisms")
    print("   - Framework should detect and prevent infinite loops")
    
    print("\nRecommendations:")
    print("1. Always set max_iterations or termination conditions for loops")
    print("2. Use timeouts when executing flows with potential loops")
    print("3. Monitor queue size and active tasks during execution")
    print("4. Remove or connect unused events/slots to avoid confusion")


def main():
    """Main demonstration function."""
    print("=" * 80)
    print("Misconfiguration Demonstration")
    print("=" * 80)
    print("\nThis demo shows potential issues when users incorrectly configure routine connections:")
    print("  1. Circular connections (A -> B -> A) that may cause infinite loops")
    print("  2. Unconnected events (events emitted but no slots connected)")
    print("  3. Unconnected slots (slots defined but no events connected)")
    print("  4. Memory leaks from excessive event emissions without handlers")
    print()
    
    results = []
    
    # Run scenarios
    try:
        flow1, state1 = test_scenario_1_controlled_loop()
        results.append((flow1, state1))
    except Exception as e:
        print(f"\n❌ Scenario 1 failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        flow2, state2 = test_scenario_2_potential_infinite_loop()
        results.append((flow2, state2))
    except Exception as e:
        print(f"\n❌ Scenario 2 failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        flow3, state3 = test_scenario_3_unconnected_events()
        results.append((flow3, state3))
    except Exception as e:
        print(f"\n❌ Scenario 3 failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Analyze results
    if results:
        analyze_results(results)
    
    print("\n" + "=" * 80)
    print("✅ Demonstration completed!")
    print("=" * 80)


if __name__ == "__main__":
    main()

