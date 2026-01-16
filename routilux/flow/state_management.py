"""
State management for Flow execution.

Handles pause, resume, cancel, and task serialization/deserialization.
"""

import logging
import queue
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from routilux.flow.flow import Flow
    from routilux.job_state import JobState

logger = logging.getLogger(__name__)


def pause_flow(
    flow: "Flow",
    job_state: "JobState",
    reason: str = "",
    checkpoint: Optional[Dict[str, Any]] = None,
) -> None:
    """Pause execution.

    Args:
        flow: Flow object.
        job_state: JobState to pause.
        reason: Reason for pausing.
        checkpoint: Optional checkpoint data.

    Raises:
        ValueError: If job_state flow_id doesn't match.
    """
    if job_state.flow_id != flow.flow_id:
        raise ValueError(
            f"JobState flow_id '{job_state.flow_id}' does not match Flow flow_id '{flow.flow_id}'"
        )

    flow._paused = True

    wait_for_active_tasks(flow)

    # Drain task queue with timeout to avoid blocking indefinitely
    max_wait = 2.0
    start_time = time.time()
    while not flow._task_queue.empty():
        if time.time() - start_time > max_wait:
            logger.warning(
                f"pause_flow: Timeout draining task queue after {max_wait}s. "
                f"Queue size: {flow._task_queue.qsize()}. Proceeding with pause."
            )
            break
        try:
            task = flow._task_queue.get(timeout=0.1)
            flow._pending_tasks.append(task)
        except queue.Empty:
            # Queue is empty, we're done draining
            break

    pause_point = {
        "timestamp": datetime.now().isoformat(),
        "reason": reason,
        "checkpoint": checkpoint or {},
        "pending_tasks_count": len(flow._pending_tasks),
        "active_tasks_count": len(flow._active_tasks),
        "queue_size": flow._task_queue.qsize(),
    }

    job_state.pause_points.append(pause_point)
    job_state._set_paused(reason=reason, checkpoint=checkpoint)

    serialize_pending_tasks(flow, job_state)


def wait_for_active_tasks(flow: "Flow") -> None:
    """Wait for all active tasks to complete.

    Args:
        flow: Flow object.
    """
    check_interval = 0.05
    max_wait_time = 5.0
    start_time = time.time()

    while True:
        with flow._execution_lock:
            active = [f for f in flow._active_tasks if not f.done()]
            if not active:
                break

        elapsed = time.time() - start_time
        if elapsed > max_wait_time:
            # Timeout reached - log warning and try to cancel remaining futures
            logger.warning(
                f"wait_for_active_tasks timed out after {max_wait_time}s. "
                f"Active tasks: {len(active)}. Proceeding with pause."
            )
            # Try to cancel any remaining futures that can be cancelled
            with flow._execution_lock:
                for future in list(flow._active_tasks):
                    if not future.done():
                        try:
                            future.cancel()
                        except Exception:
                            pass
            break

        time.sleep(check_interval)


def serialize_pending_tasks(flow: "Flow", job_state: "JobState") -> None:
    """Serialize pending tasks to JobState.

    Args:
        flow: Flow object.
        job_state: JobState to serialize tasks to.
    """
    serialized_tasks = []
    for task in flow._pending_tasks:
        connection = task.connection
        serialized = {
            "slot_routine_id": task.slot.routine._id if task.slot.routine else None,
            "slot_name": task.slot.name,
            "data": task.data,
            "connection_source_routine_id": (
                connection.source_event.routine._id
                if connection and connection.source_event and connection.source_event.routine
                else None
            ),
            "connection_source_event_name": (
                connection.source_event.name if connection and connection.source_event else None
            ),
            "connection_target_routine_id": (
                connection.target_slot.routine._id
                if connection and connection.target_slot and connection.target_slot.routine
                else None
            ),
            "connection_target_slot_name": (
                connection.target_slot.name if connection and connection.target_slot else None
            ),
            "param_mapping": connection.param_mapping if connection else {},
            "priority": task.priority.value,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }
        serialized_tasks.append(serialized)

    job_state.pending_tasks = serialized_tasks


def deserialize_pending_tasks(flow: "Flow", job_state: "JobState") -> None:
    """Deserialize pending tasks from JobState.

    Args:
        flow: Flow object.
        job_state: JobState to deserialize tasks from.
    """
    if not hasattr(job_state, "pending_tasks") or not job_state.pending_tasks:
        return

    from routilux.flow.task import SlotActivationTask, TaskPriority

    flow._pending_tasks = []
    for serialized in job_state.pending_tasks:
        slot_routine_id = serialized.get("slot_routine_id")
        slot_name = serialized.get("slot_name")

        if not slot_routine_id or slot_routine_id not in flow.routines:
            continue

        routine = flow.routines[slot_routine_id]
        slot = routine.get_slot(slot_name)
        if not slot:
            continue

        connection = None
        if serialized.get("connection_source_routine_id"):
            source_routine_id = serialized.get("connection_source_routine_id")
            source_event_name = serialized.get("connection_source_event_name")
            target_routine_id = serialized.get("connection_target_routine_id")
            target_slot_name = serialized.get("connection_target_slot_name")

            if source_routine_id in flow.routines and target_routine_id in flow.routines:
                source_routine = flow.routines[source_routine_id]
                target_routine = flow.routines[target_routine_id]
                source_event = (
                    source_routine.get_event(source_event_name) if source_event_name else None
                )
                target_slot = (
                    target_routine.get_slot(target_slot_name) if target_slot_name else None
                )

                if source_event and target_slot:
                    connection = flow._find_connection(source_event, target_slot)

        task = SlotActivationTask(
            slot=slot,
            data=serialized.get("data", {}),
            connection=connection,
            priority=TaskPriority(serialized.get("priority", TaskPriority.NORMAL.value)),
            retry_count=serialized.get("retry_count", 0),
            max_retries=serialized.get("max_retries", 0),
            created_at=(
                datetime.fromisoformat(serialized["created_at"])
                if serialized.get("created_at")
                else None
            ),
            job_state=job_state,  # Pass JobState to deserialized task
        )

        flow._pending_tasks.append(task)


def _recover_slot_tasks(flow: "Flow", job_state: "JobState") -> None:
    """Recover tasks from slot data that wasn't serialized in pending_tasks.

    This handles the case where:
    - Slot has data but no pending_tasks (e.g., retry tasks were in queue during serialization)
    - Routine state indicates it should still be processing
    - Error handler indicates retries are still available

    This function automatically rebuilds SlotActivationTask objects from slot data
    and enqueues them for execution, ensuring seamless recovery.

    Args:
        flow: Flow object.
        job_state: JobState to recover tasks from.
    """
    from routilux.flow.error_handling import get_error_handler_for_routine
    from routilux.flow.task import SlotActivationTask, TaskPriority

    recovered_count = 0

    # Iterate through all routines in the flow
    for routine_id, routine in flow.routines.items():
        # Skip entry routines (they use trigger slots, not input slots)
        # We only recover tasks for non-entry routines that have input slots with data
        if not hasattr(routine, "get_slot"):
            continue

        # Get routine state from job_state
        routine_state = job_state.get_routine_state(routine_id)
        if not routine_state:
            # If no state, assume routine hasn't started yet
            routine_status = "pending"
        else:
            routine_status = routine_state.get("status", "pending")

        # Skip if routine is already completed or failed (no recovery needed)
        if routine_status in ["completed", "failed", "cancelled"]:
            continue

        # Check all slots in the routine
        # We need to check all slots, not just input_slot, because slots are stored in _slots dict
        if not hasattr(routine, "_slots"):
            continue

        for slot_name, slot in routine._slots.items():
            # Skip trigger slots (entry points)
            if slot_name == "trigger":
                continue

            # Check if slot has data
            if not hasattr(slot, "_data") or not slot._data:
                continue

            # Check if slot has a handler (otherwise no point in recovering)
            if not hasattr(slot, "handler") or not slot.handler:
                continue

            # Get error handler for this routine
            error_handler = get_error_handler_for_routine(routine, routine_id, flow)

            # Check if retry is still available
            should_recover = True
            retry_count = 0
            max_retries = 0

            if error_handler:
                # If error handler exists, check retry availability
                if error_handler.strategy.value == "retry":
                    retry_count = error_handler.retry_count
                    max_retries = error_handler.max_retries
                    # Only recover if retries are still available
                    if retry_count >= max_retries:
                        should_recover = False
                # For other strategies (CONTINUE, SKIP), we can still recover
                # to allow the routine to process the data

            if not should_recover:
                continue

            # Find connection for this slot
            # We need to find which event connects to this slot
            connection = None
            for conn in flow.connections:
                if conn.target_slot == slot:
                    connection = conn
                    break

            # If no connection found, try to find by slot's connected_events
            if connection is None and hasattr(slot, "connected_events"):
                for event in slot.connected_events:
                    found_conn = flow._find_connection(event, slot)
                    if found_conn:
                        connection = found_conn
                        break

            # Create task to process the slot data
            task = SlotActivationTask(
                slot=slot,
                data=slot._data.copy(),  # Use a copy to avoid modifying original
                connection=connection,
                priority=TaskPriority.NORMAL,
                retry_count=retry_count,
                max_retries=max_retries,
                job_state=job_state,
            )

            # Enqueue the task
            flow._enqueue_task(task)
            recovered_count += 1
            logger.debug(
                f"Recovered task for routine '{routine_id}', slot '{slot_name}', "
                f"retry_count={retry_count}/{max_retries}"
            )

    if recovered_count > 0:
        logger.info(f"Recovered {recovered_count} task(s) from slot data during resume")


def resume_flow(flow: "Flow", job_state: "JobState") -> "JobState":
    """Resume execution from paused or saved state.

    Args:
        flow: Flow object.
        job_state: JobState to resume.

    Returns:
        Updated JobState.

    Raises:
        ValueError: If job_state flow_id doesn't match or routine doesn't exist.
    """
    if job_state.flow_id != flow.flow_id:
        raise ValueError(
            f"JobState flow_id '{job_state.flow_id}' does not match Flow flow_id '{flow.flow_id}'"
        )

    if job_state.current_routine_id and job_state.current_routine_id not in flow.routines:
        raise ValueError(f"Current routine '{job_state.current_routine_id}' not found in flow")

    job_state._set_running()
    flow._paused = False

    # JobState is now passed directly via tasks, no need for thread-local storage

    for routine_id, routine_state in job_state.routine_states.items():
        if routine_id in flow.routines:
            routine = flow.routines[routine_id]
            # Routine state is restored to JobState, not routine._stats

    for r in flow.routines.values():
        r._current_flow = flow

    deserialize_pending_tasks(flow, job_state)

    # Recover tasks from slot data that wasn't serialized in pending_tasks
    # This handles cases where retry tasks were in queue during serialization
    _recover_slot_tasks(flow, job_state)

    # Process deferred events (emit them before processing pending tasks)
    # Critical fix: Only clear successfully processed events to prevent data loss
    processed_events = []
    for event_info in job_state.deferred_events:
        routine_id = event_info.get("routine_id")
        event_name = event_info.get("event_name")
        event_data = event_info.get("data", {})

        if routine_id in flow.routines:
            routine = flow.routines[routine_id]
            try:
                # Ensure routine has the corresponding event
                if routine.get_event(event_name):
                    routine.emit(event_name, flow=flow, **event_data)
                    processed_events.append(event_info)
                else:
                    import warnings

                    warnings.warn(
                        f"Deferred event '{event_name}' not found in routine '{routine_id}'. "
                        f"Event will remain in deferred_events for retry."
                    )
            except Exception as e:
                import warnings

                warnings.warn(
                    f"Failed to emit deferred event '{event_name}' from routine '{routine_id}': {e}. "
                    f"Event will remain in deferred_events for retry."
                )
        else:
            import warnings

            warnings.warn(
                f"Routine '{routine_id}' not found in flow for deferred event. "
                f"Event will remain in deferred_events for retry."
            )

    # Remove only successfully processed events (failed events are preserved for retry)
    for event_info in processed_events:
        job_state.deferred_events.remove(event_info)

    for task in flow._pending_tasks:
        flow._task_queue.put(task)
    flow._pending_tasks.clear()

    from routilux.flow.event_loop import start_event_loop

    # Check if event loop thread is still running
    # If thread has stopped but _running is still True, restart it
    if not flow._running or (
        flow._execution_thread is not None and not flow._execution_thread.is_alive()
    ):
        start_event_loop(flow)

    return job_state


def cancel_flow(flow: "Flow", job_state: "JobState", reason: str = "") -> None:
    """Cancel execution.

    Args:
        flow: Flow object.
        job_state: JobState to cancel.
        reason: Reason for cancellation.

    Raises:
        ValueError: If job_state flow_id doesn't match.
    """
    if job_state.flow_id != flow.flow_id:
        raise ValueError(
            f"JobState flow_id '{job_state.flow_id}' does not match Flow flow_id '{flow.flow_id}'"
        )

    job_state._set_cancelled(reason=reason)
    flow._paused = False

    # Stop event loop
    flow._running = False
    with flow._execution_lock:
        for future in flow._active_tasks.copy():
            future.cancel()
            flow._active_tasks.clear()
