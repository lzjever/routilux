"""
Error handling logic for Flow execution.

Handles task errors and error handler resolution.
"""

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from routilux.error_handler import ErrorHandler
    from routilux.flow.flow import Flow
    from routilux.flow.task import SlotActivationTask
    from routilux.routine import Routine


def get_error_handler_for_routine(
    routine: "Routine", routine_id: str, flow: "Flow"
) -> Optional["ErrorHandler"]:
    """Get error handler for a routine.

    Priority order:
    1. Routine-level error handler (if set)
    2. Flow-level error handler (if set)
    3. None (default STOP behavior)

    Args:
        routine: Routine object.
        routine_id: Routine ID.
        flow: Flow object.

    Returns:
        ErrorHandler instance or None.
    """
    if routine.get_error_handler() is not None:
        return routine.get_error_handler()

    return flow.error_handler


def handle_task_error(
    task: "SlotActivationTask",
    error: Exception,
    flow: "Flow",
) -> None:
    """Handle task execution error.

    Args:
        task: The task that failed.
        error: The exception that occurred.
        flow: Flow object.
    """
    # Critical fix: Check if task.slot is None to prevent AttributeError
    if task.slot is None:
        error_msg = f"Cannot handle task error: task.slot is None. Error: {error}"
        logging.getLogger(__name__).error(error_msg)
        # Still update job state if available
        if task.job_state:
            from routilux.status import ExecutionStatus

            task.job_state.status = ExecutionStatus.FAILED
            task.job_state.record_execution("unknown", "error", {"error": error_msg})
        _stop_execution(task.job_state, flow)
        return

    routine = task.slot.routine

    # Find routine_id in flow (this is the correct routine_id, not routine._id)
    routine_id = None
    if routine:
        for rid, r in flow.routines.items():
            if r is routine:
                routine_id = rid
                break
        # Fallback to routine._id if not found in flow (shouldn't happen in normal cases)
        if routine_id is None:
            routine_id = routine._id if hasattr(routine, "_id") else None

    error_handler = (
        get_error_handler_for_routine(routine, routine_id, flow) if routine_id and routine else None
    )

    if error_handler:
        should_retry = error_handler.handle_error(
            error, routine, routine_id, flow, job_state=task.job_state
        )

        if error_handler.strategy.value == "retry":
            if should_retry:
                max_retries = (
                    error_handler.max_retries if error_handler.max_retries > 0 else task.max_retries
                )
                if task.retry_count < max_retries:
                    from routilux.flow.task import SlotActivationTask

                    retry_task = SlotActivationTask(
                        slot=task.slot,
                        data=task.data,
                        connection=task.connection,
                        priority=task.priority,
                        retry_count=task.retry_count + 1,
                        max_retries=max_retries,
                        job_state=task.job_state,  # Preserve JobState in retry task
                    )
                    # Route to JobExecutor if available, otherwise use flow._enqueue_task()
                    if not _enqueue_to_executor(retry_task, task.job_state):
                        flow._enqueue_task(retry_task)
                    return
            # Max retries reached or non-retryable exception, fall through to default
            # Record error in execution history before marking as failed
            if task.job_state and routine_id:
                task.job_state.record_execution(
                    routine_id, "error", {"slot": task.slot.name, "error": str(error)}
                )

        elif error_handler.strategy.value == "continue":
            if task.job_state and routine_id:
                # Record error in execution history
                task.job_state.record_execution(
                    routine_id, "error", {"slot": task.slot.name, "error": str(error)}
                )
            return

        elif error_handler.strategy.value == "skip":
            if task.job_state and routine_id:
                task.job_state.update_routine_state(routine_id, {"status": "skipped"})
            return

    # Update JobState on failure
    if task.job_state:
        from routilux.status import ExecutionStatus

        task.job_state.status = ExecutionStatus.FAILED
        if routine_id:
            task.job_state.update_routine_state(
                routine_id, {"status": "failed", "error": str(error)}
            )

    _stop_execution(task.job_state, flow)


def _enqueue_to_executor(task: "SlotActivationTask", job_state) -> bool:
    """Enqueue task to JobExecutor if available.

    Args:
        task: SlotActivationTask to enqueue.
        job_state: JobState for finding the executor.

    Returns:
        True if enqueued to executor, False otherwise.
    """
    if job_state is None:
        return False

    from routilux.job_manager import get_job_manager

    job_manager = get_job_manager()
    executor = job_manager.get_job(job_state.job_id)

    if executor is not None:
        executor.enqueue_task(task)
        return True

    return False


def _stop_execution(job_state, flow: "Flow") -> None:
    """Stop execution - either JobExecutor or Flow.

    Args:
        job_state: JobState for finding the executor.
        flow: Flow object (fallback).
    """
    if job_state is not None:
        from routilux.job_manager import get_job_manager

        job_manager = get_job_manager()
        executor = job_manager.get_job(job_state.job_id)

        if executor is not None:
            executor._running = False
            return

    # Fallback: stop flow (legacy mode)
    if hasattr(flow, "_running"):
        flow._running = False
