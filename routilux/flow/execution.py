"""
Execution logic for Flow.

Handles sequential and concurrent execution of workflows.
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from routilux.flow.flow import Flow
    from routilux.job_state import JobState


def execute_flow(
    flow: "Flow",
    entry_routine_id: str,
    entry_params: Optional[Dict[str, Any]] = None,
    execution_strategy: Optional[str] = None,
    timeout: Optional[float] = None,
) -> "JobState":
    """Execute the flow starting from the specified entry routine.

    Args:
        flow: Flow object.
        entry_routine_id: Identifier of the routine to start execution from.
        entry_params: Optional dictionary of parameters to pass to the entry routine's trigger slot.
        execution_strategy: Optional execution strategy override.
        timeout: Optional timeout for execution completion in seconds.
            If None, uses flow.execution_timeout (default: 300.0 seconds).

    Returns:
        JobState object.

    Raises:
        ValueError: If entry_routine_id does not exist in the flow.
    """
    if entry_routine_id not in flow.routines:
        raise ValueError(f"Entry routine '{entry_routine_id}' not found in flow")

    strategy = execution_strategy or flow.execution_strategy
    execution_timeout = timeout if timeout is not None else flow.execution_timeout

    if strategy == "concurrent":
        return execute_concurrent(flow, entry_routine_id, entry_params, timeout=execution_timeout)
    else:
        return execute_sequential(flow, entry_routine_id, entry_params, timeout=execution_timeout)


def execute_sequential(
    flow: "Flow",
    entry_routine_id: str,
    entry_params: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
) -> "JobState":
    """Execute Flow using unified queue-based mechanism.

    Args:
        flow: Flow object.
        entry_routine_id: Entry routine identifier.
        entry_params: Entry parameters.

    Returns:
        JobState object.
    """
    from routilux.execution_tracker import ExecutionTracker
    from routilux.flow.error_handling import get_error_handler_for_routine
    from routilux.flow.event_loop import start_event_loop
    from routilux.job_state import JobState

    job_state = JobState(flow.flow_id)
    job_state.status = "running"
    job_state.current_routine_id = entry_routine_id

    flow.execution_tracker = ExecutionTracker(flow.flow_id)

    entry_params = entry_params or {}
    entry_routine = flow.routines[entry_routine_id]

    try:
        for routine in flow.routines.values():
            routine._current_flow = flow

        start_time = datetime.now()
        job_state.record_execution(entry_routine_id, "start", entry_params)
        flow.execution_tracker.record_routine_start(entry_routine_id, entry_params)

        start_event_loop(flow)

        trigger_slot = entry_routine.get_slot("trigger")
        if trigger_slot is None:
            raise ValueError(
                f"Entry routine '{entry_routine_id}' must have a 'trigger' slot. "
                f"Define it using: routine.define_slot('trigger', handler=your_handler)"
            )

        # Set job_state in context variable for entry routine execution
        from routilux.routine import _current_job_state

        old_job_state = _current_job_state.get(None)
        _current_job_state.set(job_state)

        try:
            trigger_slot.call_handler(entry_params or {}, propagate_exceptions=True)
        finally:
            # Restore previous job_state
            if old_job_state is not None:
                _current_job_state.set(old_job_state)
            else:
                _current_job_state.set(None)

        from routilux.flow.completion import ensure_event_loop_running

        ensure_event_loop_running(flow)

        # Update routine state for successful execution
        job_state.update_routine_state(
            entry_routine_id,
            {
                "status": "completed",
            },
        )

        return job_state

    except Exception as e:
        error_handler = get_error_handler_for_routine(entry_routine, entry_routine_id, flow)
        if error_handler:
            should_continue = error_handler.handle_error(
                e, entry_routine, entry_routine_id, flow, job_state=job_state
            )

            if error_handler.strategy.value == "continue":
                job_state.status = "completed"
                job_state.update_routine_state(
                    entry_routine_id,
                    {
                        "status": "error_continued",
                        "error": str(e),
                    },
                )
                return job_state

            if error_handler.strategy.value == "skip":
                job_state.status = "completed"
                return job_state

            if should_continue and error_handler.strategy.value == "retry":
                retry_success = False
                remaining_retries = error_handler.max_retries
                trigger_slot = entry_routine.get_slot("trigger")
                if trigger_slot is None:
                    raise ValueError(
                        f"Entry routine '{entry_routine_id}' must have a 'trigger' slot. "
                        f"Define it using: routine.define_slot('trigger', handler=your_handler)"
                    )
                for attempt in range(remaining_retries):
                    try:
                        trigger_slot.call_handler(entry_params or {}, propagate_exceptions=True)
                        retry_success = True
                        break
                    except Exception as retry_error:
                        should_continue_retry = error_handler.handle_error(
                            retry_error, entry_routine, entry_routine_id, flow, job_state=job_state
                        )
                        if not should_continue_retry:
                            e = retry_error
                            break
                        if attempt >= remaining_retries - 1:
                            e = retry_error
                            break

                if retry_success:
                    end_time = datetime.now()
                    execution_time = (end_time - start_time).total_seconds()
                    job_state.update_routine_state(
                        entry_routine_id,
                        {
                            "status": "completed",
                            "execution_time": execution_time,
                            "retry_count": error_handler.retry_count,
                        },
                    )
                    job_state.record_execution(
                        entry_routine_id,
                        "completed",
                        {"execution_time": execution_time, "retried": True},
                    )
                    if flow.execution_tracker:
                        flow.execution_tracker.record_routine_end(entry_routine_id, "completed")
                    job_state.status = "completed"
                    return job_state

        error_time = datetime.now()
        job_state.status = "failed"
        job_state.update_routine_state(
            entry_routine_id,
            {"status": "failed", "error": str(e), "error_time": error_time.isoformat()},
        )
        job_state.record_execution(
            entry_routine_id, "error", {"error": str(e), "error_type": type(e).__name__}
        )
        if flow.execution_tracker:
            flow.execution_tracker.record_routine_end(entry_routine_id, "failed", error=str(e))

        logging.exception(f"Error executing flow: {e}")

    return job_state


def execute_concurrent(
    flow: "Flow",
    entry_routine_id: str,
    entry_params: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
) -> "JobState":
    """Execute Flow concurrently using unified queue-based mechanism.

    In concurrent mode, max_workers > 1, allowing parallel task execution.
    The queue-based mechanism handles concurrency automatically.

    Args:
        flow: Flow object.
        entry_routine_id: Entry routine identifier.
        entry_params: Entry parameters.
        timeout: Optional timeout for execution completion in seconds.

    Returns:
        JobState object.
    """
    return execute_sequential(flow, entry_routine_id, entry_params, timeout=timeout)
