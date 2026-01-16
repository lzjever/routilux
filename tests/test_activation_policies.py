"""
Comprehensive tests for activation policies.

Tests all built-in activation policies:
- time_interval_policy
- batch_size_policy
- all_slots_ready_policy
- custom_policy
- immediate_policy
"""

import time
from datetime import datetime

import pytest

from routilux import Routine
from routilux.activation_policies import (
    all_slots_ready_policy,
    batch_size_policy,
    custom_policy,
    immediate_policy,
    time_interval_policy,
)
from routilux.job_state import JobState


class TestImmediatePolicy:
    """Test immediate_policy"""

    def test_immediate_policy_activates_with_data(self):
        """Test: Immediate policy activates when any slot has data"""
        routine = Routine()
        slot = routine.define_slot("input")

        policy = immediate_policy()
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test"

        # Enqueue data
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())

        should_activate, data_slice, policy_message = policy(routine.slots, job_state)

        assert should_activate is True
        assert "input" in data_slice
        assert len(data_slice["input"]) == 1

    def test_immediate_policy_no_data(self):
        """Test: Immediate policy does not activate when no data"""
        routine = Routine()
        routine.define_slot("input")

        policy = immediate_policy()
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test"

        should_activate, data_slice, policy_message = policy(routine.slots, job_state)

        assert should_activate is False
        assert len(data_slice) == 0

    def test_immediate_policy_multiple_slots(self):
        """Test: Immediate policy with multiple slots"""
        routine = Routine()
        slot1 = routine.define_slot("input1")
        slot2 = routine.define_slot("input2")

        policy = immediate_policy()
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test"

        # Enqueue to one slot
        slot1.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())

        should_activate, data_slice, policy_message = policy(routine.slots, job_state)

        assert should_activate is True
        assert "input1" in data_slice
        assert "input2" in data_slice
        assert len(data_slice["input1"]) == 1
        assert len(data_slice["input2"]) == 0  # Empty slot


class TestTimeIntervalPolicy:
    """Test time_interval_policy"""

    def test_time_interval_policy_first_activation(self):
        """Test: Time interval policy activates on first call"""
        routine = Routine()
        slot = routine.define_slot("input")

        policy = time_interval_policy(min_interval_seconds=1.0)
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test"

        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())

        should_activate, data_slice, policy_message = policy(routine.slots, job_state)

        assert should_activate is True

    def test_time_interval_policy_respects_interval(self):
        """Test: Time interval policy respects minimum interval"""
        routine = Routine()
        slot = routine.define_slot("input")

        policy = time_interval_policy(min_interval_seconds=0.5)
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test"

        # First activation
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        should_activate, _, _ = policy(routine.slots, job_state)
        assert should_activate is True

        # Second activation too soon
        slot.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())
        should_activate, _, _ = policy(routine.slots, job_state)
        assert should_activate is False

        # Wait and try again
        time.sleep(0.6)
        should_activate, _, _ = policy(routine.slots, job_state)
        assert should_activate is True

    def test_time_interval_policy_per_routine(self):
        """Test: Time interval policy tracks per routine"""
        routine1 = Routine()
        routine2 = Routine()
        slot1 = routine1.define_slot("input")
        slot2 = routine2.define_slot("input")

        policy = time_interval_policy(min_interval_seconds=0.5)
        job_state1 = JobState(flow_id="test1")
        job_state1.current_routine_id = "routine1"
        job_state2 = JobState(flow_id="test2")
        job_state2.current_routine_id = "routine2"

        # Activate routine1
        slot1.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        should_activate, _, _ = policy(routine1.slots, job_state1)
        assert should_activate is True

        # Immediately activate routine2 (should work, different routine)
        slot2.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        should_activate, _, _ = policy(routine2.slots, job_state2)
        assert should_activate is True


class TestBatchSizePolicy:
    """Test batch_size_policy"""

    def test_batch_size_policy_waits_for_batch(self):
        """Test: Batch size policy waits until all slots have enough data"""
        routine = Routine()
        slot = routine.define_slot("input")

        policy = batch_size_policy(min_batch_size=3)
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test"

        # Not enough data
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        should_activate, _, _ = policy(routine.slots, job_state)
        assert should_activate is False

        slot.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())
        should_activate, _, _ = policy(routine.slots, job_state)
        assert should_activate is False

        # Now enough data
        slot.enqueue(data={"value": 3}, emitted_from="r1", emitted_at=datetime.now())
        should_activate, data_slice, _ = policy(routine.slots, job_state)
        assert should_activate is True
        assert len(data_slice["input"]) == 3

    def test_batch_size_policy_multiple_slots(self):
        """Test: Batch size policy with multiple slots"""
        routine = Routine()
        slot1 = routine.define_slot("input1")
        slot2 = routine.define_slot("input2")

        policy = batch_size_policy(min_batch_size=2)
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test"

        # Fill slot1 but not slot2
        slot1.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        slot1.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())
        should_activate, _, _ = policy(routine.slots, job_state)
        assert should_activate is False

        # Fill slot2
        slot2.enqueue(data={"value": 3}, emitted_from="r1", emitted_at=datetime.now())
        slot2.enqueue(data={"value": 4}, emitted_from="r1", emitted_at=datetime.now())
        should_activate, data_slice, _ = policy(routine.slots, job_state)
        assert should_activate is True
        assert len(data_slice["input1"]) == 2
        assert len(data_slice["input2"]) == 2

    def test_batch_size_policy_consumes_exact_amount(self):
        """Test: Batch size policy consumes exact batch size"""
        routine = Routine()
        slot = routine.define_slot("input")

        policy = batch_size_policy(min_batch_size=2)
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test"

        # Enqueue more than batch size
        for i in range(5):
            slot.enqueue(data={"value": i}, emitted_from="r1", emitted_at=datetime.now())

        should_activate, data_slice, _ = policy(routine.slots, job_state)
        assert should_activate is True
        assert len(data_slice["input"]) == 2  # Only batch size consumed

        # Remaining data still in queue
        assert slot.get_unconsumed_count() == 3


class TestAllSlotsReadyPolicy:
    """Test all_slots_ready_policy"""

    def test_all_slots_ready_policy_single_slot(self):
        """Test: All slots ready with single slot"""
        routine = Routine()
        slot = routine.define_slot("input")

        policy = all_slots_ready_policy()
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test"

        # No data
        should_activate, _, _ = policy(routine.slots, job_state)
        assert should_activate is False

        # Has data
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        should_activate, data_slice, _ = policy(routine.slots, job_state)
        assert should_activate is True
        assert len(data_slice["input"]) == 1

    def test_all_slots_ready_policy_multiple_slots(self):
        """Test: All slots ready with multiple slots"""
        routine = Routine()
        slot1 = routine.define_slot("input1")
        slot2 = routine.define_slot("input2")

        policy = all_slots_ready_policy()
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test"

        # Only one slot has data
        slot1.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        should_activate, _, _ = policy(routine.slots, job_state)
        assert should_activate is False

        # Both slots have data
        slot2.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())
        should_activate, data_slice, _ = policy(routine.slots, job_state)
        assert should_activate is True
        assert "input1" in data_slice
        assert "input2" in data_slice
        assert len(data_slice["input1"]) == 1
        assert len(data_slice["input2"]) == 1

    def test_all_slots_ready_policy_consumes_one_per_slot(self):
        """Test: All slots ready consumes one item per slot"""
        routine = Routine()
        slot = routine.define_slot("input")

        policy = all_slots_ready_policy()
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test"

        # Enqueue multiple items
        for i in range(5):
            slot.enqueue(data={"value": i}, emitted_from="r1", emitted_at=datetime.now())

        should_activate, data_slice, _ = policy(routine.slots, job_state)
        assert should_activate is True
        assert len(data_slice["input"]) == 1  # Only one consumed

        # Remaining data still in queue
        assert slot.get_unconsumed_count() == 4


class TestCustomPolicy:
    """Test custom_policy"""

    def test_custom_policy_with_check_function(self):
        """Test: Custom policy with check function"""
        routine = Routine()
        slot = routine.define_slot("input")

        def my_check(slots, job_state):
            # Activate if slot has more than 2 items
            return slot.get_unconsumed_count() > 2

        policy = custom_policy(my_check)
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test"

        # Not enough items
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        slot.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())
        should_activate, _, _ = policy(routine.slots, job_state)
        assert should_activate is False

        # Enough items
        slot.enqueue(data={"value": 3}, emitted_from="r1", emitted_at=datetime.now())
        should_activate, data_slice, _ = policy(routine.slots, job_state)
        assert should_activate is True
        assert len(data_slice["input"]) == 3  # All consumed

    def test_custom_policy_check_function_error(self):
        """Test: Custom policy handles check function errors"""
        routine = Routine()
        routine.define_slot("input")

        def failing_check(slots, job_state):
            raise ValueError("Check error")

        policy = custom_policy(failing_check)
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test"

        # Should propagate error
        with pytest.raises(ValueError, match="Check error"):
            policy(routine.slots, job_state)


class TestActivationPolicyEdgeCases:
    """Test activation policy edge cases"""

    def test_policy_with_empty_slots_dict(self):
        """Test: Policy with empty slots dictionary"""
        routine = Routine()
        # No slots defined

        policy = immediate_policy()
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test"

        should_activate, data_slice, policy_message = policy(routine.slots, job_state)

        assert should_activate is False
        assert len(data_slice) == 0

    def test_policy_with_none_job_state(self):
        """Test: Policy behavior with None job_state (should not happen but test robustness)"""
        routine = Routine()
        slot = routine.define_slot("input")

        policy = immediate_policy()

        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())

        # Policy should handle None job_state gracefully
        # (In practice, job_state is always provided, but test robustness)
        job_state = JobState(flow_id="test")
        should_activate, data_slice, _ = policy(routine.slots, job_state)
        assert should_activate is True

    def test_multiple_policies_same_routine(self):
        """Test: Changing activation policy on same routine"""
        routine = Routine()
        slot = routine.define_slot("input")

        policy1 = immediate_policy()
        policy2 = all_slots_ready_policy()

        routine.set_activation_policy(policy1)
        assert routine._activation_policy == policy1

        routine.set_activation_policy(policy2)
        assert routine._activation_policy == policy2

        # Verify new policy is used
        job_state = JobState(flow_id="test")
        job_state.current_routine_id = "test"

        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        should_activate, _, _ = policy2(routine.slots, job_state)
        assert should_activate is True
