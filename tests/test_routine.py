"""
Routine test cases for new activation_policy + logic design.
"""

import pytest

from routilux import Routine
from routilux.activation_policies import all_slots_ready_policy, immediate_policy
from routilux.job_state import JobState


class TestRoutineBasic:
    """Routine basic functionality tests"""

    def test_create_routine(self):
        """Test: Create Routine object"""
        routine = Routine()
        assert routine._id is not None
        assert isinstance(routine._config, dict)
        assert len(routine._config) == 0

    def test_define_slot(self):
        """Test: Define Slot (new API - no handler)"""
        routine = Routine()

        slot = routine.define_slot("input")
        assert slot.name == "input"
        assert slot.routine == routine
        assert "input" in routine._slots

    def test_define_event(self):
        """Test: Define Event"""
        routine = Routine()

        event = routine.define_event("output", ["result", "status"])
        assert event.name == "output"
        assert event.routine == routine
        assert event.output_params == ["result", "status"]
        assert "output" in routine._events

    def test_set_activation_policy(self):
        """Test: Set activation policy"""
        routine = Routine()

        policy = immediate_policy()
        routine.set_activation_policy(policy)

        assert routine._activation_policy == policy

    def test_set_logic(self):
        """Test: Set logic function"""
        routine = Routine()

        def my_logic(*slot_data_lists, policy_message, job_state):
            pass

        routine.set_logic(my_logic)

        assert routine._logic == my_logic

    def test_config_method(self):
        """Test: Config methods"""
        routine = Routine()

        # Initial state is empty
        config = routine.config()
        assert isinstance(config, dict)
        assert len(config) == 0

        # Update config
        routine.set_config(count=1, result="success")

        # Verify config() returns copy
        config = routine.config()
        assert config["count"] == 1
        assert config["result"] == "success"

        # Modifying returned dict should not affect internal state
        config["new_key"] = "new_value"
        assert "new_key" not in routine._config

    def test_routine_helper_methods(self):
        """Test: Routine helper methods for JobState access"""
        from routilux.flow.flow import Flow

        routine = Routine()
        flow = Flow("test_flow")
        routine_id = flow.add_routine(routine, "test_routine")

        # Create job_state
        job_state = JobState(flow_id=flow.flow_id)
        routine._current_flow = flow

        # Test set_state
        routine.set_state(job_state, "count", 10)
        assert routine.get_state(job_state, "count") == 10

        # Test update_state
        routine.update_state(job_state, {"count": 20, "status": "running"})
        assert routine.get_state(job_state, "count") == 20
        assert routine.get_state(job_state, "status") == "running"

        # Test get_state with default
        assert routine.get_state(job_state, "nonexistent", "default") == "default"


class TestRoutineEdgeCases:
    """Routine edge case tests"""

    def test_empty_routine(self):
        """Test: Empty Routine"""
        routine = Routine()

        # Routine without slots and events should work
        assert len(routine._slots) == 0
        assert len(routine._events) == 0

    def test_duplicate_slot_name(self):
        """Test: Duplicate slot name"""
        routine = Routine()

        routine.define_slot("input")

        # Duplicate slot name should raise error
        with pytest.raises(ValueError):
            routine.define_slot("input")

    def test_duplicate_event_name(self):
        """Test: Duplicate event name"""
        routine = Routine()

        routine.define_event("output")

        # Duplicate event name should raise error
        with pytest.raises(ValueError):
            routine.define_event("output")


class TestRoutineActivationPolicy:
    """Routine activation policy tests"""

    def test_activation_policy_all_slots_ready(self):
        """Test: Activation policy - all slots ready"""
        routine = Routine()
        slot1 = routine.define_slot("input1")
        slot2 = routine.define_slot("input2")

        # Set activation policy
        policy = all_slots_ready_policy()
        routine.set_activation_policy(policy)

        from datetime import datetime
        from routilux.job_state import JobState

        # Create job_state
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test_routine"

        # Enqueue data to both slots
        slot1.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        slot2.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())

        # Check activation
        should_activate, data_slice, policy_message = routine._activation_policy(
            routine.slots, job_state
        )

        assert should_activate is True
        assert "input1" in data_slice
        assert "input2" in data_slice
        assert len(data_slice["input1"]) == 1
        assert len(data_slice["input2"]) == 1

    def test_activation_policy_not_ready(self):
        """Test: Activation policy - not ready"""
        routine = Routine()
        slot1 = routine.define_slot("input1")
        slot2 = routine.define_slot("input2")

        # Set activation policy
        policy = all_slots_ready_policy()
        routine.set_activation_policy(policy)

        from datetime import datetime
        from routilux.job_state import JobState

        # Create job_state
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test_routine"

        # Enqueue data to only one slot
        slot1.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())

        # Check activation (should be False)
        should_activate, data_slice, policy_message = routine._activation_policy(
            routine.slots, job_state
        )

        assert should_activate is False


class TestRoutineLogic:
    """Routine logic tests"""

    def test_logic_execution(self):
        """Test: Logic execution with slot data"""
        routine = Routine()
        slot1 = routine.define_slot("input1")
        slot2 = routine.define_slot("input2")

        # Track calls
        logic_calls = []

        def my_logic(input1_data, input2_data, policy_message, job_state):
            logic_calls.append((input1_data, input2_data, policy_message))

        routine.set_logic(my_logic)

        from datetime import datetime
        from routilux.job_state import JobState

        # Create job_state
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test_routine"

        # Enqueue data
        slot1.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        slot2.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())

        # Manually call logic (normally called by Runtime)
        data_slice = {
            "input1": slot1.consume_all_new(),
            "input2": slot2.consume_all_new(),
        }
        slot_data_lists = [data_slice["input1"], data_slice["input2"]]

        routine._logic(*slot_data_lists, policy_message=None, job_state=job_state)

        # Verify logic was called
        assert len(logic_calls) == 1
        assert len(logic_calls[0][0]) == 1
        assert len(logic_calls[0][1]) == 1
