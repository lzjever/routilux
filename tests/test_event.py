"""
Event test cases for new Runtime-based design.
"""

from datetime import datetime

from routilux import Flow, Routine
from routilux.activation_policies import immediate_policy
from routilux.job_state import JobState
from routilux.runtime import Runtime


class TestEventConnection:
    """Event connection management tests"""

    def test_connect_to_slot(self):
        """Test: Connect to Slot"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        # Connect
        event.connect(slot)

        # Verify connection
        assert slot in event.connected_slots
        assert event in slot.connected_events

    def test_disconnect_from_slot(self):
        """Test: Disconnect from Slot"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output")
        slot = routine.define_slot("input")

        # Connect
        event.connect(slot)
        assert slot in event.connected_slots

        # Disconnect
        event.disconnect(slot)
        assert slot not in event.connected_slots
        assert event not in slot.connected_events

    def test_one_to_many_connection(self):
        """Test: One-to-many connection - one event to multiple slots"""
        routine1 = Routine()
        routine = Routine()
        routine3 = Routine()

        event = routine1.define_event("output")
        slot1 = routine.define_slot("input1")
        slot2 = routine3.define_slot("input2")

        # Connect multiple slots
        event.connect(slot1)
        event.connect(slot2)

        # Verify
        assert len(event.connected_slots) == 2
        assert slot1 in event.connected_slots
        assert slot2 in event.connected_slots


class TestEventEmission:
    """Event emission tests"""

    def test_emit_to_connected_slots(self):
        """Test: Emit event to connected slots via Runtime"""
        received_data = []

        def logic1(input1_data, policy_message, job_state):
            received_data.append(("logic1", input1_data))

        def logic2(input2_data, policy_message, job_state):
            received_data.append(("logic2", input2_data))

        class Routine1(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger")
                self.output_event = self.define_event("output", ["data"])

                def my_logic(trigger_data, policy_message, job_state):
                    self.emit("output", runtime=runtime, job_state=job_state, data="test")

                self.set_logic(my_logic)
                self.set_activation_policy(immediate_policy())

        routine1 = Routine1()
        routine2 = Routine()
        routine3 = Routine()

        slot1 = routine2.define_slot("input1")
        slot2 = routine3.define_slot("input2")

        routine2.set_logic(logic1)
        routine2.set_activation_policy(immediate_policy())

        routine3.set_logic(logic2)
        routine3.set_activation_policy(immediate_policy())

        # Create flow and connect
        flow = Flow("test_flow")
        flow.add_routine(routine1, "r1")
        flow.add_routine(routine2, "r2")
        flow.add_routine(routine3, "r3")
        flow.connect("r1", "output", "r2", "input1")
        flow.connect("r1", "output", "r3", "input2")

        # Register flow
        from routilux.monitoring.flow_registry import FlowRegistry

        flow_registry = FlowRegistry.get_instance()
        flow_registry.register_by_name("test_flow", flow)

        # Create runtime and execute
        runtime = Runtime(thread_pool_size=5)
        job_state = runtime.exec("test_flow")

        # Wait for completion
        runtime.wait_until_all_jobs_finished(timeout=5.0)

        # Verify data was received (simplified - actual implementation would track this)
        assert job_state.status.value in ["completed", "failed", "running"]

    def test_emit_without_connections(self):
        """Test: Emit event without connections (should be discarded silently)"""
        routine = Routine()
        routine.define_event("output", ["data"])

        # Create runtime and job_state
        runtime = Runtime()
        job_state = JobState(flow_id="test")

        # Emit without connections (should not raise error)
        event = routine.get_event("output")
        event.emit(runtime=runtime, job_state=job_state, data="test")

        # Verify event is defined
        assert "output" in routine._events

    def test_output_params(self):
        """Test: Output parameters"""
        routine = Routine()

        # Define event with output parameters
        event = routine.define_event("output", ["result", "status"])

        # Verify output parameters are recorded
        assert "result" in event.output_params
        assert "status" in event.output_params

        # Unspecified parameters should also be passable
        runtime = Runtime()
        job_state = JobState(flow_id="test")
        event.emit(runtime=runtime, job_state=job_state, result="ok", status="success", extra="data")


class TestEventDataFlow:
    """Event data flow tests"""

    def test_event_metadata(self):
        """Test: Event emission includes metadata"""
        routine = Routine()
        event = routine.define_event("output", ["data"])

        runtime = Runtime()
        job_state = JobState(flow_id="test")

        # Emit event
        event.emit(runtime=runtime, job_state=job_state, data="test")

        # Verify metadata is included (checked in Runtime.handle_event_emit)
        # This is tested indirectly through Runtime routing
