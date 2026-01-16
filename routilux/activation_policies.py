"""
Built-in activation policies for routines.

Activation policies determine when a routine's logic should be executed
based on slot data availability and conditions.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple

if TYPE_CHECKING:
    from routilux.job_state import JobState
    from routilux.slot import Slot


def time_interval_policy(min_interval_seconds: float):
    """Create an activation policy that activates when minimum time interval has passed.

    This policy ensures the routine is activated at most once every
    min_interval_seconds, regardless of how many events arrive.

    Args:
        min_interval_seconds: Minimum time interval in seconds between activations.

    Returns:
        Activation policy function.

    Examples:
        >>> policy = time_interval_policy(5.0)  # Activate at most once every 5 seconds
        >>> routine.set_activation_policy(policy)
    """
    last_activation: Dict[str, float] = {}

    def policy(slots: Dict[str, Slot], job_state: JobState) -> Tuple[bool, Dict[str, List[Any]], Any]:
        """Time interval activation policy.

        Args:
            slots: Dictionary of slot_name -> Slot object.
            job_state: Current job state.

        Returns:
            Tuple of (should_activate, data_slice, policy_message).
        """
        routine_id = job_state.current_routine_id or "unknown"
        now = time.time()

        # Check if enough time has passed
        if routine_id in last_activation:
            if now - last_activation[routine_id] < min_interval_seconds:
                return False, {}, None

        # Extract data from all slots
        data_slice = {}
        for slot_name, slot in slots.items():
            data_slice[slot_name] = slot.consume_all_new()

        last_activation[routine_id] = now
        policy_message = {
            "reason": "time_interval_met",
            "interval": min_interval_seconds,
            "last_activation": last_activation.get(routine_id),
        }
        return True, data_slice, policy_message

    return policy


def batch_size_policy(min_batch_size: int):
    """Create an activation policy that activates when all slots have at least N data points.

    This policy waits until all slots have accumulated at least min_batch_size
    unconsumed items before activating the routine.

    Args:
        min_batch_size: Minimum number of items required in each slot.

    Returns:
        Activation policy function.

    Examples:
        >>> policy = batch_size_policy(10)  # Activate when all slots have 10+ items
        >>> routine.set_activation_policy(policy)
    """
    def policy(slots: Dict[str, Slot], job_state: JobState) -> Tuple[bool, Dict[str, List[Any]], Any]:
        """Batch size activation policy.

        Args:
            slots: Dictionary of slot_name -> Slot object.
            job_state: Current job state.

        Returns:
            Tuple of (should_activate, data_slice, policy_message).
        """
        # Check all slots have enough data
        for slot_name, slot in slots.items():
            if slot.get_unconsumed_count() < min_batch_size:
                return False, {}, None

        # Extract batch from all slots
        data_slice = {}
        for slot_name, slot in slots.items():
            # Consume exactly min_batch_size items
            batch = []
            for _ in range(min_batch_size):
                item = slot.consume_one_new()
                if item is not None:
                    batch.append(item)
            data_slice[slot_name] = batch

        policy_message = {
            "reason": "batch_ready",
            "batch_size": min_batch_size,
        }
        return True, data_slice, policy_message

    return policy


def all_slots_ready_policy():
    """Create an activation policy that activates when all slots have at least 1 new data point.

    This policy ensures the routine is only activated when all slots have
    received at least one new data point since the last activation.

    Returns:
        Activation policy function.

    Examples:
        >>> policy = all_slots_ready_policy()
        >>> routine.set_activation_policy(policy)
    """
    def policy(slots: Dict[str, Slot], job_state: JobState) -> Tuple[bool, Dict[str, List[Any]], Any]:
        """All slots ready activation policy.

        Args:
            slots: Dictionary of slot_name -> Slot object.
            job_state: Current job state.

        Returns:
            Tuple of (should_activate, data_slice, policy_message).
        """
        # Check all slots have data
        for slot_name, slot in slots.items():
            if slot.get_unconsumed_count() == 0:
                return False, {}, None

        # Extract one item from each slot
        data_slice = {}
        for slot_name, slot in slots.items():
            item = slot.consume_one_new()
            if item is not None:
                data_slice[slot_name] = [item]

        policy_message = {"reason": "all_slots_ready"}
        return True, data_slice, policy_message

    return policy


def custom_policy(check_function: Callable[[Dict[str, Slot], JobState], bool]):
    """Create a custom activation policy from a check function.

    The check function should return True if the routine should be activated,
    False otherwise. The policy will consume all new data from all slots
    when activating.

    Args:
        check_function: Function that takes (slots, job_state) and returns bool.
            Should return True to activate, False to skip.

    Returns:
        Activation policy function.

    Examples:
        >>> def my_check(slots, job_state):
        ...     # Custom logic
        ...     return slots["input"].get_unconsumed_count() > 5
        >>> policy = custom_policy(my_check)
        >>> routine.set_activation_policy(policy)
    """
    def policy(slots: Dict[str, Slot], job_state: JobState) -> Tuple[bool, Dict[str, List[Any]], Any]:
        """Custom activation policy.

        Args:
            slots: Dictionary of slot_name -> Slot object.
            job_state: Current job state.

        Returns:
            Tuple of (should_activate, data_slice, policy_message).
        """
        # Call custom check function
        if not check_function(slots, job_state):
            return False, {}, None

        # Extract data from all slots
        data_slice = {}
        for slot_name, slot in slots.items():
            data_slice[slot_name] = slot.consume_all_new()

        policy_message = {"reason": "custom_policy_met"}
        return True, data_slice, policy_message

    return policy


def immediate_policy():
    """Create an activation policy that activates immediately when any slot receives data.

    This is the default behavior - activate as soon as any slot has new data.

    Returns:
        Activation policy function.

    Examples:
        >>> policy = immediate_policy()
        >>> routine.set_activation_policy(policy)
    """
    def policy(slots: Dict[str, Slot], job_state: JobState) -> Tuple[bool, Dict[str, List[Any]], Any]:
        """Immediate activation policy.

        Args:
            slots: Dictionary of slot_name -> Slot object.
            job_state: Current job state.

        Returns:
            Tuple of (should_activate, data_slice, policy_message).
        """
        # Check if any slot has data
        has_data = any(slot.get_unconsumed_count() > 0 for slot in slots.values())
        if not has_data:
            return False, {}, None

        # Extract all new data from all slots
        data_slice = {}
        for slot_name, slot in slots.items():
            data_slice[slot_name] = slot.consume_all_new()

        policy_message = {"reason": "immediate"}
        return True, data_slice, policy_message

    return policy
