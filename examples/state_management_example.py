#!/usr/bin/env python
"""
State Management Example: Demonstrating JobState and ExecutionTracker

This example demonstrates:
- JobState for tracking execution state
- ExecutionTracker for performance monitoring
- State persistence and recovery
"""
import json


from routilux import Flow, Routine


class ProcessingRoutine(Routine):
    """A routine that processes data"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self.process)
        self.output_event = self.define_event("output", ["result"])

    def process(self, data):
        """Process the data"""
        if isinstance(data, dict):
            data_value = data.get("data", data)
        else:
            data_value = data

        result = f"Processed: {data_value}"
        self._stats["processed_count"] = self._stats.get("processed_count", 0) + 1
        self.emit("output", result=result)


def main():
    """Main function"""
    # Create a flow
    flow = Flow(flow_id="state_management_example")

    # Create routine instances
    processor1 = ProcessingRoutine()
    processor2 = ProcessingRoutine()

    # Add routines to the flow
    id1 = flow.add_routine(processor1, "processor1")
    id2 = flow.add_routine(processor2, "processor2")

    # Connect routines
    flow.connect(id1, "output", id2, "input")

    # Execute the flow
    print("Executing flow...")
    job_state = flow.execute(id1, entry_params={"data": "test"})

    # Check JobState
    print("\nJobState Information:")
    print(f"  Status: {job_state.status}")
    print(f"  Flow ID: {job_state.flow_id}")
    print(f"  Job ID: {job_state.job_id}")
    print(f"  Execution History Count: {len(job_state.execution_history)}")

    # Check routine states
    print("\nRoutine States:")
    for routine_id in job_state.routine_states:
        state = job_state.get_routine_state(routine_id)
        print(f"  {routine_id}: {state}")

    # Check ExecutionTracker
    if flow.execution_tracker:
        print("\nExecutionTracker Information:")
        print(f"  Flow ID: {flow.execution_tracker.flow_id}")
        print(f"  Routines Executed: {len(flow.execution_tracker.routine_executions)}")
        print(f"  Events Recorded: {len(flow.execution_tracker.event_flow)}")

        # Get performance metrics
        for routine_id in flow.execution_tracker.routine_executions:
            perf = flow.execution_tracker.get_routine_performance(routine_id)
            if perf:
                print(f"\n  Performance for {routine_id}:")
                print(f"    Total Executions: {perf['total_executions']}")
                print(f"    Success Rate: {perf['success_rate']:.2%}")
                print(f"    Avg Execution Time: {perf['avg_execution_time']:.4f}s")

        flow_perf = flow.execution_tracker.get_flow_performance()
        print("\n  Overall Flow Performance:")
        print(f"    Total Routines: {flow_perf['total_routines']}")
        print(f"    Total Events: {flow_perf['total_events']}")
        print(f"    Total Execution Time: {flow_perf['total_execution_time']:.4f}s")

    # Demonstrate serialization
    print("\nSerialization Example:")
    flow_data = flow.serialize()
    print(f"  Serialized Flow: {len(flow_data)} fields")

    job_state_data = job_state.serialize()
    print(f"  Serialized JobState: {len(job_state_data)} fields")

    # Save to JSON (example)
    with open("/tmp/flow_example.json", "w") as f:
        json.dump(flow_data, f, indent=2, default=str)
    print("  Saved flow to /tmp/flow_example.json")

    assert job_state.status == "completed"
    print("\n✓ State management example completed!")


if __name__ == "__main__":
    main()
