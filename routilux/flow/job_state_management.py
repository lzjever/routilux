"""
State management for JobExecutor (pause, resume, cancel).

This module handles job-level state management, providing functions
for pausing, resuming, and cancelling job execution.
"""

import logging
import queue
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from routilux.job_executor import JobExecutor
    from routilux.job_state import JobState

logger = logging.getLogger(__name__)


def pause_job_executor(
    executor: "JobExecutor",
    reason: str = "",
    checkpoint: Optional[dict[str, Any]] = None,
) -> None:
    """Pause job execution.

    This function:
    1. Sets the paused flag
    2. Waits for active tasks to complete
    3. Drains the task queue to pending_tasks
    4. Records the pause point in JobState
    5. Serializes pending tasks

    Args:
        executor: JobExecutor to pause.
        reason: Reason for pausing.
        checkpoint: Optional checkpoint data.
    """
    executor._paused = True
    # Critical fix: Keep flow._paused in sync with executor._paused
    executor.flow._paused = True

    # Wait for active tasks to complete
    _wait_for_active_tasks(executor)

    # Drain task queue to pending_tasks
    max_wait = 2.0
    start_time = time.time()
    while not executor.task_queue.empty():
        if time.time() - start_time > max_wait:
            logger.warning(
                f"pause_job_executor: Timeout draining task queue. "
                f"Queue size: {executor.task_queue.qsize()}"
            )
            break
        try:
            task = executor.task_queue.get(timeout=0.1)
            executor.pending_tasks.append(task)
        except queue.Empty:
            break

    # Record pause point
    pause_point = {
        "timestamp": datetime.now().isoformat(),
        "reason": reason,
        "checkpoint": checkpoint or {},
        "pending_tasks_count": len(executor.pending_tasks),
        "active_tasks_count": len(executor.active_tasks),
        "queue_size": executor.task_queue.qsize(),
    }

    executor.job_state.pause_points.append(pause_point)
    executor.job_state._set_paused(reason=reason, checkpoint=checkpoint)

    # Serialize pending tasks
    _serialize_pending_tasks(executor)

    logger.info(f"Paused job {executor.job_state.job_id}: {reason}")


def resume_job_executor(executor: "JobExecutor") -> "JobState":
    """Resume job execution.

    This function:
    1. Validates flow_id match
    2. Updates JobState status
    3. Deserializes pending tasks
    4. Restarts event loop if needed
    5. Re-enqueues pending tasks

    Args:
        executor: JobExecutor to resume.

    Returns:
        Updated JobState.

    Raises:
        ValueError: If job_state flow_id doesn't match.
    """
    if executor.job_state.flow_id != executor.flow.flow_id:
        raise ValueError(
            f"JobState flow_id '{executor.job_state.flow_id}' "
            f"does not match Flow flow_id '{executor.flow.flow_id}'"
        )

    executor.job_state._set_running()
    executor._paused = False
    # Critical fix: Keep flow._paused in sync with executor._paused
    executor.flow._paused = False

    # Deserialize pending tasks if any
    _deserialize_pending_tasks(executor)

    # Re-enqueue pending tasks
    for task in executor.pending_tasks:
        executor.task_queue.put(task)
    executor.pending_tasks.clear()

    # Restart event loop if needed
    if not executor._running or (
        executor.event_loop_thread is not None
        and not executor.event_loop_thread.is_alive()
    ):
        executor._running = True
        executor.event_loop_thread = threading.Thread(
            target=executor._event_loop,
            daemon=True,
            name=f"JobExecutor-{executor.job_state.job_id[:8]}"
        )
        executor.event_loop_thread.start()

    logger.info(f"Resumed job {executor.job_state.job_id}")

    return executor.job_state


def cancel_job_executor(executor: "JobExecutor", reason: str = "") -> None:
    """Cancel job execution.

    This function:
    1. Stops the event loop
    2. Cancels active tasks
    3. Updates JobState status

    Args:
        executor: JobExecutor to cancel.
        reason: Reason for cancellation.
    """
    executor._running = False
    executor._paused = False

    # Cancel active tasks
    with executor._lock:
        for future in list(executor.active_tasks):
            if not future.done():
                future.cancel()
        executor.active_tasks.clear()

    executor.job_state._set_cancelled(reason=reason)

    logger.info(f"Cancelled job {executor.job_state.job_id}: {reason}")


def _wait_for_active_tasks(executor: "JobExecutor") -> None:
    """Wait for all active tasks to complete.

    Args:
        executor: JobExecutor to wait for.
    """
    check_interval = 0.05
    max_wait_time = 5.0
    start_time = time.time()

    while True:
        with executor._lock:
            active = [f for f in executor.active_tasks if not f.done()]
            if not active:
                break

        elapsed = time.time() - start_time
        if elapsed > max_wait_time:
            logger.warning(
                f"wait_for_active_tasks timed out after {max_wait_time}s. "
                f"Active tasks: {len(active)}"
            )
            # Try to cancel remaining tasks
            with executor._lock:
                for future in list(executor.active_tasks):
                    if not future.done():
                        future.cancel()
            break

        time.sleep(check_interval)


def _serialize_pending_tasks(executor: "JobExecutor") -> None:
    """Serialize pending tasks to JobState.

    Args:
        executor: JobExecutor to serialize tasks from.
    """
    from routilux.flow.task import TaskPriority

    serialized_tasks = []
    for task in executor.pending_tasks:
        # Find routine_id in flow (not routine._id)
        routine_id = None
        if task.slot.routine:
            for rid, r in executor.flow.routines.items():
                if r is task.slot.routine:
                    routine_id = rid
                    break

        connection = task.connection
        serialized = {
            "routine_id": routine_id,  # Flow's routine_id
            "slot_name": task.slot.name,
            "data": task.data,
            "connection_source_routine_id": (
                _get_routine_id_from_flow(
                    executor.flow, connection.source_event.routine
                )
                if connection and connection.source_event and connection.source_event.routine
                else None
            ),
            "connection_source_event_name": (
                connection.source_event.name
                if connection and connection.source_event
                else None
            ),
            "connection_target_routine_id": (
                _get_routine_id_from_flow(
                    executor.flow, connection.target_slot.routine
                )
                if connection and connection.target_slot and connection.target_slot.routine
                else None
            ),
            "connection_target_slot_name": (
                connection.target_slot.name
                if connection and connection.target_slot
                else None
            ),
            "param_mapping": connection.param_mapping if connection else {},
            "priority": task.priority.value if task.priority else TaskPriority.NORMAL.value,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }
        serialized_tasks.append(serialized)

    executor.job_state.pending_tasks = serialized_tasks


def _deserialize_pending_tasks(executor: "JobExecutor") -> None:
    """Deserialize pending tasks from JobState.

    Args:
        executor: JobExecutor to deserialize tasks to.
    """
    if not hasattr(executor.job_state, "pending_tasks") or not executor.job_state.pending_tasks:
        return

    from routilux.flow.task import SlotActivationTask, TaskPriority

    # Clear existing pending tasks
    executor.pending_tasks = []

    for serialized in executor.job_state.pending_tasks:
        routine_id = serialized.get("routine_id")
        slot_name = serialized.get("slot_name")

        if not routine_id or routine_id not in executor.flow.routines:
            logger.warning(f"Routine {routine_id} not found, skipping task")
            continue

        routine = executor.flow.routines[routine_id]
        slot = routine.get_slot(slot_name)
        if not slot:
            logger.warning(f"Slot {slot_name} not found in routine {routine_id}, skipping task")
            continue

        # Reconstruct connection
        connection = None
        if serialized.get("connection_source_routine_id"):
            source_routine_id = serialized.get("connection_source_routine_id")
            source_event_name = serialized.get("connection_source_event_name")
            target_routine_id = serialized.get("connection_target_routine_id")
            target_slot_name = serialized.get("connection_target_slot_name")

            if (
                source_routine_id in executor.flow.routines
                and target_routine_id in executor.flow.routines
            ):
                source_routine = executor.flow.routines[source_routine_id]
                target_routine = executor.flow.routines[target_routine_id]
                source_event = (
                    source_routine.get_event(source_event_name)
                    if source_event_name
                    else None
                )
                target_slot = (
                    target_routine.get_slot(target_slot_name)
                    if target_slot_name
                    else None
                )

                if source_event and target_slot:
                    connection = executor.flow._find_connection(source_event, target_slot)

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
            job_state=executor.job_state,
        )

        executor.pending_tasks.append(task)

    # Clear serialized tasks from job_state after deserialization
    executor.job_state.pending_tasks = []

    logger.info(f"Deserialized {len(executor.pending_tasks)} pending tasks")


def _get_routine_id_from_flow(flow: "Flow", routine: Any) -> Optional[str]:
    """Get routine_id from flow.routines dictionary.

    Args:
        flow: Flow object.
        routine: Routine object to find.

    Returns:
        Routine ID if found, None otherwise.
    """
    if routine is None:
        return None

    for rid, r in flow.routines.items():
        if r is routine:
            return rid

    return None
