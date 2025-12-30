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
    from routilux.flow.task import SlotActivationTask, TaskPriority


def pause_flow(
    flow: "Flow",
    reason: str = "",
    checkpoint: Optional[Dict[str, Any]] = None,
) -> None:
    """Pause execution.

    Args:
        flow: Flow object.
        reason: Reason for pausing.
        checkpoint: Optional checkpoint data.

    Raises:
        ValueError: If there is no active job_state.
    """
    if not flow.job_state:
        raise ValueError("No active job_state to pause. Flow must be executing.")

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

    flow.job_state.pause_points.append(pause_point)
    flow.job_state._set_paused(reason=reason, checkpoint=checkpoint)

    serialize_pending_tasks(flow)


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


def serialize_pending_tasks(flow: "Flow") -> None:
    """Serialize pending tasks to JobState.

    Args:
        flow: Flow object.
    """
    if not flow.job_state:
        return

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

    flow.job_state.pending_tasks = serialized_tasks


def deserialize_pending_tasks(flow: "Flow") -> None:
    """Deserialize pending tasks from JobState.

    Args:
        flow: Flow object.
    """
    if not flow.job_state or not hasattr(flow.job_state, "pending_tasks"):
        return

    from routilux.flow.task import SlotActivationTask, TaskPriority

    flow._pending_tasks = []
    for serialized in flow.job_state.pending_tasks:
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
        )

        flow._pending_tasks.append(task)


def resume_flow(flow: "Flow", job_state: Optional["JobState"] = None) -> "JobState":
    """Resume execution from paused or saved state.

    Args:
        flow: Flow object.
        job_state: JobState to resume (uses current job_state if None).

    Returns:
        Updated JobState.

    Raises:
        ValueError: If job_state flow_id doesn't match or routine doesn't exist.
    """
    if job_state is None:
        job_state = flow.job_state

    if job_state is None:
        raise ValueError("No JobState to resume")

    if job_state.flow_id != flow.flow_id:
        raise ValueError(
            f"JobState flow_id '{job_state.flow_id}' does not match Flow flow_id '{flow.flow_id}'"
        )

    if job_state.current_routine_id and job_state.current_routine_id not in flow.routines:
        raise ValueError(f"Current routine '{job_state.current_routine_id}' not found in flow")

    job_state._set_running()
    flow._paused = False
    flow.job_state = job_state

    for routine_id, routine_state in job_state.routine_states.items():
        if routine_id in flow.routines:
            routine = flow.routines[routine_id]
            if "stats" in routine_state:
                routine._stats.update(routine_state["stats"])

    for r in flow.routines.values():
        r._current_flow = flow

    deserialize_pending_tasks(flow)

    for task in flow._pending_tasks:
        flow._task_queue.put(task)
    flow._pending_tasks.clear()

    from routilux.flow.event_loop import start_event_loop

    if not flow._running:
        start_event_loop(flow)

    return job_state


def cancel_flow(flow: "Flow", reason: str = "") -> None:
    """Cancel execution.

    Args:
        flow: Flow object.
        reason: Reason for cancellation.

    Raises:
        ValueError: If there is no active job_state.
    """
    if not flow.job_state:
        raise ValueError("No active job_state to cancel. Flow must be executing.")

    flow.job_state._set_cancelled(reason=reason)
    flow._paused = False

    flow._running = False
    with flow._execution_lock:
        for future in flow._active_tasks.copy():
            future.cancel()
        flow._active_tasks.clear()
