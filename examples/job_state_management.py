#!/usr/bin/env python
"""
JobState Management Example

This example demonstrates:
- Multiple independent executions
- JobState serialization and persistence
- Pause/resume with JobState
- Cross-host execution simulation
"""

import json
import tempfile

from serilux import register_serializable

from routilux import Flow, JobState, Routine


@register_serializable
class DataSource(Routine):
    def __init__(self):
        super().__init__()
        self.trigger_slot = self.define_slot("trigger", handler=self.send)
        self.output_event = self.define_event("output", ["data"])

    def send(self, value=None, **kwargs):
        value = value or kwargs.get("value", "default")
        self.emit("output", data=value)


@register_serializable
class DataProcessor(Routine):
    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self.process)
        self.output_event = self.define_event("output", ["result"])

    def process(self, data=None, **kwargs):
        data_value = data or kwargs.get("data", "")
        result = f"Processed: {data_value}"
        self.emit("output", result=result)


def test_multiple_independent_executions():
    """Test multiple independent executions"""
    print("=" * 70)
    print("Test 1: Multiple Independent Executions")
    print("=" * 70)

    flow = Flow(flow_id="multi_execution_test")
    source = DataSource()
    processor = DataProcessor()
    source_id = flow.add_routine(source, "source")
    processor_id = flow.add_routine(processor, "processor")
    flow.connect(source_id, "output", processor_id, "input")

    # Execute multiple times
    js1 = flow.execute(source_id, entry_params={"value": "A"})
    js2 = flow.execute(source_id, entry_params={"value": "B"})
    js3 = flow.execute(source_id, entry_params={"value": "C"})

    print(f"Execution 1: {js1.job_id[:8]}... - Status: {js1.status}")
    print(f"Execution 2: {js2.job_id[:8]}... - Status: {js2.status}")
    print(f"Execution 3: {js3.job_id[:8]}... - Status: {js3.status}")

    assert js1.job_id != js2.job_id
    assert js2.job_id != js3.job_id
    assert js1 is not js2

    print(f"Execution 1 history: {len(js1.execution_history)} records")
    print(f"Execution 2 history: {len(js2.execution_history)} records")
    print(f"Execution 3 history: {len(js3.execution_history)} records")

    print("✓ Multiple independent executions verified")


def test_job_state_serialization():
    """Test JobState serialization"""
    print("\n" + "=" * 70)
    print("Test 2: JobState Serialization")
    print("=" * 70)

    flow = Flow(flow_id="serialization_test")
    source = DataSource()
    source_id = flow.add_routine(source, "source")

    # Execute and serialize
    job_state = flow.execute(source_id, entry_params={"value": "test_data"})

    # Serialize separately
    flow_data = flow.serialize()
    job_state_data = job_state.serialize()

    print(f"Flow serialized: {len(flow_data)} fields")
    print(f"JobState serialized: {len(job_state_data)} fields")
    print(f"Flow contains job_state: {'job_state' in flow_data}")

    assert "job_state" not in flow_data
    assert "job_id" in job_state_data
    assert job_state_data["job_id"] == job_state.job_id

    # Save to temporary file
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
        json.dump({"flow": flow_data, "job_state": job_state_data}, f, indent=2)
        temp_file = f.name

    print(f"Saved to: {temp_file}")

    # Load and verify
    with open(temp_file) as f:
        loaded = json.load(f)

    new_flow = Flow()
    new_flow.deserialize(loaded["flow"])

    new_job_state = JobState()
    new_job_state.deserialize(loaded["job_state"])

    assert new_flow.flow_id == flow.flow_id
    assert new_job_state.job_id == job_state.job_id
    assert new_job_state.status == job_state.status

    print("✓ Serialization/deserialization verified")


def test_pause_resume_with_job_state():
    """Test pause/resume with JobState"""
    print("\n" + "=" * 70)
    print("Test 3: Pause/Resume with JobState")
    print("=" * 70)

    flow = Flow(flow_id="pause_resume_test")
    source = DataSource()
    source_id = flow.add_routine(source, "source")

    # Execute
    job_state = flow.execute(source_id, entry_params={"value": "pause_test"})

    # Pause (if still running)
    if job_state.status == "running":
        flow.pause(job_state, reason="Test pause")
        print(f"Paused: {job_state.status}")

        # Resume
        from routilux.job_state import JobState

        resumed = flow.resume(job_state)
        JobState.wait_for_completion(flow, resumed, timeout=2.0)
        print(f"Resumed status: {resumed.status}")
    else:
        print(f"Execution completed immediately: {job_state.status}")

    print("✓ Pause/resume tested")


def test_cross_host_simulation():
    """Simulate cross-host execution"""
    print("\n" + "=" * 70)
    print("Test 4: Cross-Host Execution Simulation")
    print("=" * 70)

    # Host A: Create and execute
    print("Host A: Creating flow and executing...")
    flow_a = Flow(flow_id="cross_host_flow")
    source_a = DataSource()
    processor_a = DataProcessor()
    source_id = flow_a.add_routine(source_a, "source")
    processor_id = flow_a.add_routine(processor_a, "processor")
    flow_a.connect(source_id, "output", processor_id, "input")

    job_state_a = flow_a.execute(source_id, entry_params={"value": "cross_host_data"})

    # Serialize for transfer
    flow_data = flow_a.serialize()
    job_state_data = job_state_a.serialize()

    print(f"Host A: Flow serialized ({len(json.dumps(flow_data))} bytes)")
    print(f"Host A: JobState serialized ({len(json.dumps(job_state_data))} bytes)")

    # Host B: Receive and deserialize
    print("\nHost B: Receiving and deserializing...")
    flow_b = Flow()
    flow_b.deserialize(flow_data)

    job_state_b = JobState()
    job_state_b.deserialize(job_state_data)

    print(f"Host B: Flow ID: {flow_b.flow_id}")
    print(f"Host B: JobState ID: {job_state_b.job_id[:8]}...")
    print(f"Host B: Status: {job_state_b.status}")

    # Verify
    assert flow_b.flow_id == flow_a.flow_id
    assert job_state_b.job_id == job_state_a.job_id

    print("✓ Cross-host execution simulation successful")


def main():
    """Main function"""
    test_multiple_independent_executions()
    test_job_state_serialization()
    test_pause_resume_with_job_state()
    test_cross_host_simulation()

    print("\n" + "=" * 70)
    print("All JobState management examples completed!")
    print("=" * 70)


if __name__ == "__main__":
    main()
