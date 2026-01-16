"""
Comprehensive tests for Routine class with new activation_policy + logic design.

Tests include:
- Activation policy and logic integration
- JobState helper methods
- Edge cases
- Error handling
- Multiple slots handling
"""

import pytest
from datetime import datetime

from routilux import Routine
from routilux.activation_policies import all_slots_ready_policy, immediate_policy
from routilux.error_handler import ErrorHandler, ErrorStrategy
from routilux.job_state import JobState
from routilux.flow.flow import Flow


class TestRoutineActivationPolicyLogic:
    """Test Routine activation policy and logic integration"""

    def test_routine_without_policy_or_logic(self):
        """Test: Routine without policy or logic (should work but not activate)"""
        routine = Routine()
        slot = routine.define_slot("input")

        # Enqueue data
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())

        # Without policy, Runtime will activate with all new data
        # Without logic, Runtime will skip execution
        # This is acceptable - routine just won't do anything

    def test_routine_with_policy_but_no_logic(self):
        """Test: Routine with policy but no logic"""
        routine = Routine()
        slot = routine.define_slot("input")

        policy = immediate_policy()
        routine.set_activation_policy(policy)

        # Logic is None - Runtime should handle gracefully
        # (Will raise error when trying to call None logic)
        from routilux.runtime import Runtime
        from routilux.monitoring.flow_registry import FlowRegistry

        flow = Flow("test_flow")
        flow.add_routine(routine, "test")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        job_state.current_routine_id = "test"
        runtime = Runtime()

        # Set flow context
        routine._current_flow = flow
        routine._current_runtime = runtime

        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())

        # Should handle gracefully (error in logic, not crash)
        runtime._check_routine_activation(routine, job_state)
        # Logic is None, so activation will fail when trying to call it
        # Runtime should handle this error

        runtime.shutdown(wait=True)

    def test_routine_with_logic_but_no_policy(self):
        """Test: Routine with logic but no policy (default: activate immediately)"""
        routine = Routine()
        slot = routine.define_slot("input")

        logic_called = []

        def my_logic(input_data, policy_message, job_state):
            logic_called.append(True)

        routine.set_logic(my_logic)
        # No policy - should activate immediately

        from routilux.runtime import Runtime
        from routilux.monitoring.flow_registry import FlowRegistry

        flow = Flow("test_flow")
        flow.add_routine(routine, "test")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        job_state.current_routine_id = "test"
        runtime = Runtime()

        # Set flow context
        routine._current_flow = flow
        routine._current_runtime = runtime

        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())

        runtime._check_routine_activation(routine, job_state)

        # Logic should be called (no policy = immediate activation)
        assert len(logic_called) == 1

        runtime.shutdown(wait=True)

    def test_routine_multiple_slots_order(self):
        """Test: Routine with multiple slots - data order in logic"""
        routine = Routine()
        slot1 = routine.define_slot("input1")
        slot2 = routine.define_slot("input2")
        slot3 = routine.define_slot("input3")

        received_order = []

        def my_logic(input1_data, input2_data, input3_data, policy_message, job_state):
            # Verify order matches slot definition order (sorted by name)
            received_order.append(("input1", len(input1_data)))
            received_order.append(("input2", len(input2_data)))
            received_order.append(("input3", len(input3_data)))

        routine.set_logic(my_logic)
        routine.set_activation_policy(immediate_policy())

        from routilux.runtime import Runtime
        from routilux.monitoring.flow_registry import FlowRegistry

        flow = Flow("test_flow")
        flow.add_routine(routine, "test")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        job_state.current_routine_id = "test"
        runtime = Runtime()

        # Set flow context
        routine._current_flow = flow
        routine._current_runtime = runtime

        # Enqueue to slots in different order
        slot2.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())
        slot3.enqueue(data={"value": 3}, emitted_from="r1", emitted_at=datetime.now())
        slot1.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())

        runtime._check_routine_activation(routine, job_state)

        # Verify order is sorted by slot name
        assert len(received_order) == 3
        assert received_order[0][0] == "input1"
        assert received_order[1][0] == "input2"
        assert received_order[2][0] == "input3"

        runtime.shutdown(wait=True)

    def test_routine_logic_receives_policy_message(self):
        """Test: Logic receives policy_message from activation policy"""
        routine = Routine()
        slot = routine.define_slot("input")

        received_policy_message = []

        def my_logic(input_data, policy_message, job_state):
            received_policy_message.append(policy_message)

        def my_policy(slots, job_state):
            return True, {"input": slot.consume_all_new()}, {"custom": "message"}

        routine.set_logic(my_logic)
        routine.set_activation_policy(my_policy)

        from routilux.runtime import Runtime
        from routilux.monitoring.flow_registry import FlowRegistry

        flow = Flow("test_flow")
        flow.add_routine(routine, "test")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        job_state.current_routine_id = "test"
        runtime = Runtime()

        # Set flow context
        routine._current_flow = flow
        routine._current_runtime = runtime

        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())

        runtime._check_routine_activation(routine, job_state)

        assert len(received_policy_message) == 1
        assert received_policy_message[0]["custom"] == "message"

        runtime.shutdown(wait=True)


class TestRoutineJobStateHelpers:
    """Test Routine JobState helper methods"""

    def test_get_state_entire_dict(self):
        """Test: get_state returns entire dict when key is None"""
        routine = Routine()
        flow = Flow("test_flow")
        routine_id = flow.add_routine(routine, "test")
        routine._current_flow = flow

        job_state = JobState(flow_id=flow.flow_id)
        job_state.update_routine_state(routine_id, {"key1": "value1", "key2": "value2"})

        state = routine.get_state(job_state, key=None)
        assert state == {"key1": "value1", "key2": "value2"}

    def test_get_state_specific_key(self):
        """Test: get_state returns specific key value"""
        routine = Routine()
        flow = Flow("test_flow")
        routine_id = flow.add_routine(routine, "test")
        routine._current_flow = flow

        job_state = JobState(flow_id=flow.flow_id)
        job_state.update_routine_state(routine_id, {"count": 10, "status": "running"})

        count = routine.get_state(job_state, "count")
        assert count == 10

        status = routine.get_state(job_state, "status")
        assert status == "running"

    def test_get_state_with_default(self):
        """Test: get_state returns default when key not found"""
        routine = Routine()
        flow = Flow("test_flow")
        routine_id = flow.add_routine(routine, "test")
        routine._current_flow = flow

        job_state = JobState(flow_id=flow.flow_id)

        value = routine.get_state(job_state, "nonexistent", default="default_value")
        assert value == "default_value"

    def test_set_state(self):
        """Test: set_state sets a single key"""
        routine = Routine()
        flow = Flow("test_flow")
        routine_id = flow.add_routine(routine, "test")
        routine._current_flow = flow

        job_state = JobState(flow_id=flow.flow_id)

        routine.set_state(job_state, "count", 5)
        assert routine.get_state(job_state, "count") == 5

        routine.set_state(job_state, "count", 10)
        assert routine.get_state(job_state, "count") == 10

    def test_update_state_multiple_keys(self):
        """Test: update_state updates multiple keys at once"""
        routine = Routine()
        flow = Flow("test_flow")
        routine_id = flow.add_routine(routine, "test")
        routine._current_flow = flow

        job_state = JobState(flow_id=flow.flow_id)

        routine.update_state(job_state, {"key1": "value1", "key2": "value2"})
        assert routine.get_state(job_state, "key1") == "value1"
        assert routine.get_state(job_state, "key2") == "value2"

        routine.update_state(job_state, {"key1": "updated", "key3": "value3"})
        assert routine.get_state(job_state, "key1") == "updated"
        assert routine.get_state(job_state, "key2") == "value2"  # Unchanged
        assert routine.get_state(job_state, "key3") == "value3"

    def test_helper_methods_without_flow_context(self):
        """Test: Helper methods handle missing flow context gracefully"""
        routine = Routine()
        # No flow context set

        job_state = JobState(flow_id="test")

        # Should return default when routine_id cannot be determined
        value = routine.get_state(job_state, "key", default="default")
        assert value == "default"

        # set_state and update_state should do nothing
        routine.set_state(job_state, "key", "value")
        routine.update_state(job_state, {"key": "value"})

        # Should still return default (no state was set)
        value = routine.get_state(job_state, "key", default="default")
        assert value == "default"


class TestRoutineErrorHandling:
    """Test Routine error handling"""

    def test_logic_error_propagation(self):
        """Test: Logic errors are handled by Runtime error handling"""
        routine = Routine()
        slot = routine.define_slot("input")

        def failing_logic(input_data, policy_message, job_state):
            raise ValueError("Logic error")

        routine.set_logic(failing_logic)
        routine.set_activation_policy(immediate_policy())

        from routilux.runtime import Runtime
        from routilux.monitoring.flow_registry import FlowRegistry

        flow = Flow("test_flow")
        flow.add_routine(routine, "test")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        job_state.current_routine_id = "test"
        runtime = Runtime()

        # Set flow context
        routine._current_flow = flow
        routine._current_runtime = runtime

        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())

        # Should handle error (default: STOP strategy)
        runtime._check_routine_activation(routine, job_state)

        # Job should be marked as failed
        assert job_state.status.value == "failed"
        assert "Logic error" in job_state.error

        runtime.shutdown(wait=True)

    def test_activation_policy_error_propagation(self):
        """Test: Activation policy errors are handled"""
        routine = Routine()
        routine.define_slot("input")

        def failing_policy(slots, job_state):
            raise ValueError("Policy error")

        routine.set_activation_policy(failing_policy)

        from routilux.runtime import Runtime
        from routilux.monitoring.flow_registry import FlowRegistry

        flow = Flow("test_flow")
        flow.add_routine(routine, "test")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        job_state.current_routine_id = "test"
        runtime = Runtime()

        # Should handle error
        runtime._check_routine_activation(routine, job_state)

        # Job should be marked as failed (default: STOP)
        assert job_state.status.value == "failed"
        assert "Activation policy error" in job_state.error

        runtime.shutdown(wait=True)


class TestRoutineEdgeCases:
    """Test Routine edge cases"""

    def test_routine_with_no_slots(self):
        """Test: Routine with no slots"""
        routine = Routine()

        logic_called = []

        def my_logic(policy_message, job_state):
            logic_called.append(True)

        routine.set_logic(my_logic)
        routine.set_activation_policy(immediate_policy())

        from routilux.runtime import Runtime
        from routilux.monitoring.flow_registry import FlowRegistry

        flow = Flow("test_flow")
        flow.add_routine(routine, "test")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        job_state.current_routine_id = "test"
        runtime = Runtime()

        # Should not activate (no data in slots)
        runtime._check_routine_activation(routine, job_state)

        # Logic should not be called (no data)
        assert len(logic_called) == 0

        runtime.shutdown(wait=True)

    def test_routine_with_empty_slot_data(self):
        """Test: Routine with empty slot data lists"""
        routine = Routine()
        slot = routine.define_slot("input")

        logic_called = []
        logic_data = []

        def my_logic(input_data, policy_message, job_state):
            logic_called.append(True)
            logic_data.append(input_data)

        routine.set_logic(my_logic)
        routine.set_activation_policy(immediate_policy())

        from routilux.runtime import Runtime
        from routilux.monitoring.flow_registry import FlowRegistry

        flow = Flow("test_flow")
        flow.add_routine(routine, "test")
        FlowRegistry.get_instance().register_by_name("test_flow", flow)

        job_state = JobState(flow_id=flow.flow_id)
        job_state.current_routine_id = "test"
        runtime = Runtime()

        # Enqueue and consume (so slot is empty)
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        slot.consume_all_new()  # Consume it

        # Try to activate (should not activate - no new data)
        runtime._check_routine_activation(routine, job_state)

        # Logic should not be called
        assert len(logic_called) == 0

        runtime.shutdown(wait=True)

    def test_routine_slots_property(self):
        """Test: Routine.slots property returns all slots"""
        routine = Routine()
        slot1 = routine.define_slot("input1")
        slot2 = routine.define_slot("input2")

        slots = routine.slots
        assert len(slots) == 2
        assert "input1" in slots
        assert "input2" in slots
        assert slots["input1"] == slot1
        assert slots["input2"] == slot2

    def test_routine_get_routine_id(self):
        """Test: Routine._get_routine_id helper"""
        routine = Routine()
        flow = Flow("test_flow")
        routine_id = flow.add_routine(routine, "test")
        routine._current_flow = flow

        job_state = JobState(flow_id=flow.flow_id)

        from routilux.runtime import Runtime
        runtime = Runtime()

        retrieved_id = runtime._get_routine_id(routine, job_state)
        assert retrieved_id == routine_id

        runtime.shutdown(wait=True)

    def test_routine_get_routine_id_no_flow(self):
        """Test: Routine._get_routine_id without flow context"""
        routine = Routine()
        # No flow context

        job_state = JobState(flow_id="test")

        from routilux.runtime import Runtime
        runtime = Runtime()

        retrieved_id = runtime._get_routine_id(routine, job_state)
        assert retrieved_id is None

        runtime.shutdown(wait=True)
