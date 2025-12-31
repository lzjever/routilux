"""
State management for Flow execution.

Handles pause, resume, cancel, and task serialization/deserialization.
"""

import time
from datetime import datetime
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from routilux.flow.flow import Flow
    from routilux.job_state import JobState


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

    while not flow._task_queue.empty():
        task = flow._task_queue.get()
        flow._pending_tasks.append(task)

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

        if time.time() - start_time > max_wait_time:
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

    # Store JobState in thread-local storage for access during execution
    flow._current_execution_job_state.value = job_state

    for routine_id, routine_state in job_state.routine_states.items():
        if routine_id in flow.routines:
            routine = flow.routines[routine_id]
            # Routine state is restored to JobState, not routine._stats

    for r in flow.routines.values():
        r._current_flow = flow

    deserialize_pending_tasks(flow, job_state)

    # Process deferred events (emit them before processing pending tasks)
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
                else:
                    import warnings

                    warnings.warn(
                        f"Deferred event '{event_name}' not found in routine '{routine_id}'"
                    )
            except Exception as e:
                import warnings

                warnings.warn(
                    f"Failed to emit deferred event '{event_name}' from routine '{routine_id}': {e}"
                )
        else:
            import warnings

            warnings.warn(f"Routine '{routine_id}' not found in flow for deferred event")

    # Clear deferred events (they have been processed)
    job_state.deferred_events.clear()

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

    # Stop event loop if cancelling current execution
    current_job_state = getattr(flow._current_execution_job_state, "value", None)
    if job_state == current_job_state:
        flow._running = False
        with flow._execution_lock:
            for future in flow._active_tasks.copy():
                future.cancel()
            flow._active_tasks.clear()
