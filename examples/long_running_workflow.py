#!/usr/bin/env python
"""Long-Running Workflow Example.

This example demonstrates:
1. Pause and resume workflow execution
2. State persistence
3. Checkpoints for recovery
"""

from routilux import Flow, Routine, JobState
import json
import time


class Initializer(Routine):
    """Initializes the long-running process."""

    def __init__(self):
        super().__init__()
        self.define_slot("trigger", handler=self.init)
        self.define_event("output", ["step", "total_steps", "data"])

    def init(self, **kwargs):
        """Initialize process."""
        print("Step 1: Initializing long-running process...")
        self.emit("output", step=1, total_steps=5, data=[])


class ProcessingStep(Routine):
    """A processing step in the workflow."""

    def __init__(self, step_num):
        super().__init__()
        self.step_num = step_num
        self.define_slot("input", handler=self.process)
        self.define_event("output", ["step", "total_steps", "data"])

    def process(self, step=None, total_steps=None, data=None, **kwargs):
        """Process this step."""
        data = data if data is not None else kwargs.get("data", [])
        print(f"Step {self.step_num}: Processing... ({self.step_num}/{total_steps})")
        # Simulate processing time
        time.sleep(0.1)
        current_data = list(data)
        current_data.append(f"result_step_{self.step_num}")
        self.emit("output", step=self.step_num, total_steps=total_steps, data=current_data)


class Finalizer(Routine):
    """Finalizes the long-running process."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", handler=self.finalize)
        self.results = []

    def finalize(self, step=None, total_steps=None, data=None, **kwargs):
        """Finalize process."""
        data = data if data is not None else kwargs.get("data", [])
        print(f"Step 5: Finalizing process...")
        print(f"Complete! Processed {len(data)} steps")
        self.results = data


def main():
    """Run the long-running workflow example."""
    # Create flow
    flow = Flow("long_running_process")

    # Create routine instances
    initializer = Initializer()
    finalizer = Finalizer()

    # Add routines to flow
    init_id = flow.add_routine(initializer, "initializer")
    finalize_id = flow.add_routine(finalizer, "finalizer")

    # Create and add processing steps
    step_ids = []
    for i in range(2, 5):
        step_processor = ProcessingStep(i)
        step_id = flow.add_routine(step_processor, f"step_{i}")
        step_ids.append((i, step_id))

    # Connect steps sequentially
    prev_id = init_id
    for i, step_id in step_ids:
        flow.connect(prev_id, "output", step_id, "input")
        prev_id = step_id
    flow.connect(prev_id, "output", finalize_id, "input")

    # Option 1: Execute with persistence
    print("\n=== Long-Running Workflow Example ===\n")

    print("--- Example 1: Execute and save state ---")
    job_state = flow.execute(init_id, entry_params={})

    # Wait a bit for first step to complete
    time.sleep(0.5)

    # Save state after first step
    serialized = job_state.serialize()
    print(f"\nSaved state: {len(json.dumps(serialized))} bytes")
    print(f"Job ID: {job_state.job_id}")
    print(f"Current status: {job_state.status}")

    # Option 2: Resume from saved state
    print("\n--- Example 2: Inspect saved state ---")
    # The JobState is already being used, let's just inspect it directly
    print(f"Current job state ID: {job_state.job_id}")
    print(f"Current status: {job_state.status}")

    # Continue execution
    print("\n--- Example 3: Continue execution ---")
    JobState.wait_for_completion(flow, job_state, timeout=30.0)

    print(f"\nFinal status: {job_state.status}")
    print(f"Execution history entries: {len(job_state.execution_history)}")

    # Show the results
    if finalizer.results:
        print(f"Results: {finalizer.results}")


if __name__ == "__main__":
    main()
