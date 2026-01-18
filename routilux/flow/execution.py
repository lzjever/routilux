"""
Execution logic for Flow.

Handles sequential and concurrent execution of workflows.
"""

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from routilux.core.flow import Flow
    from routilux.core.worker import JobState


def execute_flow(
    flow: "Flow",
    entry_routine_id: str,
    entry_params: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
    job_state: Optional["JobState"] = None,
) -> "JobState":
    """Execute the flow starting from the specified entry routine.

    This is a synchronous execution that waits for completion.

    Args:
        flow: Flow object.
        entry_routine_id: Identifier of the routine to start execution from.
        entry_params: Optional dictionary of parameters to pass to the entry routine's trigger slot.
        timeout: Optional timeout for execution completion in seconds.
            If None, uses flow.execution_timeout (default: 300.0 seconds).
        job_state: Optional existing JobState to use. If None, creates a new one.

    Returns:
        JobState object (completed or failed).

    Raises:
        ValueError: If entry_routine_id does not exist in the flow.
    """
    if entry_routine_id not in flow.routines:
        raise ValueError(f"Entry routine '{entry_routine_id}' not found in flow")

    execution_timeout = timeout if timeout is not None else flow.execution_timeout

    return execute_flow_unified(
        flow, entry_routine_id, entry_params, timeout=execution_timeout, job_state=job_state
    )


def start_flow_execution(
    flow: "Flow",
    entry_routine_id: str,
    entry_params: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
    job_state: Optional["JobState"] = None,
) -> "JobState":
    """Start flow execution asynchronously without waiting for completion.

    This method starts the execution and returns immediately with a JobState.
    The execution continues in the background. Use JobState.wait_for_completion()
    if you need to wait for the result.

    Args:
        flow: Flow object.
        entry_routine_id: Identifier of the routine to start execution from.
        entry_params: Optional dictionary of parameters to pass to the entry routine's trigger slot.
        timeout: Optional timeout for execution completion in seconds.
        job_state: Optional existing JobState to use. If None, creates a new one.

    Returns:
        JobState object (status will be RUNNING initially).

    Raises:
        ValueError: If entry_routine_id does not exist in the flow.
    """
    if entry_routine_id not in flow.routines:
        raise ValueError(f"Entry routine '{entry_routine_id}' not found in flow")

    from routilux.core.status import ExecutionStatus
    from routilux.core.worker import JobState

    # Create or use provided job_state
    if job_state is None:
        job_state = JobState(flow.flow_id)

    job_state.status = ExecutionStatus.RUNNING
    job_state.current_routine_id = entry_routine_id

    # Start execution in background thread
    import threading

    def _run_execution():
        """Run execution in background thread."""
        try:
            # Use the synchronous execute, but we won't wait for it
            # The execution will complete in the background
            execution_timeout = timeout if timeout is not None else flow.execution_timeout

            execute_flow_unified(
                flow,
                entry_routine_id,
                entry_params,
                timeout=execution_timeout,
                job_state=job_state,
            )
        except Exception as e:
            import logging

            logging.exception(f"Error in background execution for job {job_state.job_id}: {e}")
            job_state.status = ExecutionStatus.FAILED
            if "error" not in job_state.shared_data:
                job_state.shared_data["error"] = str(e)

    # Start background thread
    # HIGH fix: Use daemon=False to ensure proper cleanup, but track thread for cleanup
    # Changed from daemon=True to prevent abrupt termination
    thread = threading.Thread(
        target=_run_execution, daemon=False, name=f"FlowExecution-{job_state.job_id[:8]}"
    )
    thread.start()

    # HIGH fix: Store thread reference for cleanup and monitoring
    # This allows proper shutdown instead of abrupt daemon termination
    if not hasattr(job_state, "_execution_thread"):
        job_state._execution_thread = thread
    else:
        # If thread already exists, the previous one should be done
        # This prevents memory leaks from multiple execute() calls
        old_thread = job_state._execution_thread
        if old_thread is not None and old_thread.is_alive():
            logging.getLogger(__name__).warning(
                f"Previous execution thread still running for job {job_state.job_id}"
            )
        job_state._execution_thread = thread

    return job_state


def execute_flow_unified(
    flow: "Flow",
    entry_routine_id: str,
    entry_params: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
    job_state: Optional["JobState"] = None,
) -> "JobState":
    """Execute Flow using unified queue-based mechanism.

    All execution uses the same event queue mechanism. Tasks are executed
    using Runtime's thread pool for non-blocking concurrent execution.

    Args:
        flow: Flow object.
        entry_routine_id: Entry routine identifier.
        entry_params: Entry parameters.
        timeout: Optional timeout for execution completion in seconds.
        job_state: Optional existing JobState to use. If None, creates a new one.

    Returns:
        JobState object.
    """
    from routilux.core.status import ExecutionStatus
    from routilux.core.worker import JobState
    from routilux.execution_tracker import ExecutionTracker
    from routilux.flow.error_handling import get_error_handler_for_routine

    # Use provided job_state or create new one
    if job_state is None:
        job_state = JobState(flow.flow_id)
        job_state.status = ExecutionStatus.RUNNING
        job_state.current_routine_id = entry_routine_id
    else:
        # Update existing job_state
        job_state.status = ExecutionStatus.RUNNING
        job_state.current_routine_id = entry_routine_id

    flow.execution_tracker = ExecutionTracker(flow.flow_id)

    entry_params = entry_params or {}
    # CRITICAL fix: Use .get() with proper error handling to prevent KeyError
    entry_routine = flow.routines.get(entry_routine_id)
    if entry_routine is None:
        raise ValueError(
            f"Entry routine '{entry_routine_id}' not found in flow. "
            f"Available routines: {list(flow.routines.keys())}"
        )

    try:
        for routine in flow.routines.values():
            routine._current_flow = flow

        start_time = datetime.now()
        job_state.record_execution(entry_routine_id, "start", entry_params)
        flow.execution_tracker.record_routine_start(entry_routine_id, entry_params)

        # Monitoring hook: Flow start
        from routilux.monitoring.execution_hooks import execution_hooks

        execution_hooks.on_flow_start(flow, job_state)

        # Note: Flow no longer has its own event loop
        # Execution is handled by JobExecutor via Runtime

        trigger_slot = entry_routine.get_slot("trigger")
        if trigger_slot is None:
            raise ValueError(
                f"Entry routine '{entry_routine_id}' must have a 'trigger' slot. "
                f"Define it using: routine.define_slot('trigger', handler=your_handler)"
            )

        # Set job_state in context variable for entry routine execution
        from routilux.core.routine import _current_job_state

        old_job_state = _current_job_state.get(None)
        _current_job_state.set(job_state)

        try:
            trigger_slot.call_handler(entry_params or {}, propagate_exceptions=True)
        except Exception:
            # CRITICAL fix: Ensure context is restored even if handler raises exception
            raise
        finally:
            # Restore previous job_state
            # Use try-except to ensure cleanup even if set() fails
            try:
                if old_job_state is not None:
                    _current_job_state.set(old_job_state)
                else:
                    _current_job_state.set(None)
            except Exception:
                # Log but don't raise - cleanup is critical
                pass

        # Entry routine's trigger handler completed successfully
        # Update its state regardless of downstream routine failures
        job_state.update_routine_state(
            entry_routine_id,
            {
                "status": "completed",
            },
        )

        from routilux.flow.completion import (
            ensure_event_loop_running,
            wait_for_event_loop_completion,
        )

        ensure_event_loop_running(flow)

        # Wait for event loop to complete all tasks
        # This is critical for timeout tasks that may emit new events
        wait_for_event_loop_completion(flow, timeout=timeout)

        # MEDIUM fix: Make status check and update atomic using job_state's lock
        # Only update job status to completed if it hasn't already failed
        with job_state._status_lock:
            if job_state.status != ExecutionStatus.FAILED:
                # Set job state to completed
                job_state.status = ExecutionStatus.COMPLETED

                # Monitoring hook: Flow end
                execution_hooks.on_flow_end(flow, job_state, "completed")

        return job_state

    except Exception as e:
        error_handler = get_error_handler_for_routine(entry_routine, entry_routine_id, flow)
        if error_handler:
            should_continue = error_handler.handle_error(
                e, entry_routine, entry_routine_id, flow, job_state=job_state
            )

            if error_handler.strategy.value == "continue":
                job_state.status = ExecutionStatus.COMPLETED
                job_state.update_routine_state(
                    entry_routine_id,
                    {
                        "status": "error_continued",
                        "error": str(e),
                    },
                )
                return job_state

            if error_handler.strategy.value == "skip":
                job_state.status = ExecutionStatus.COMPLETED
                return job_state

            if should_continue and error_handler.strategy.value == "retry":
                retry_success = False
                remaining_retries = error_handler.max_retries
                trigger_slot = entry_routine.get_slot("trigger")
                if trigger_slot is None:
                    raise ValueError(
                        f"Entry routine '{entry_routine_id}' must have a 'trigger' slot. "
                        f"Define it using: routine.define_slot('trigger', handler=your_handler)"
                    ) from e
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
                    job_state.status = ExecutionStatus.COMPLETED
                    return job_state

        error_time = datetime.now()
        job_state.status = ExecutionStatus.FAILED
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

        # Monitoring hook: Flow end (failed)
        from routilux.monitoring.execution_hooks import execution_hooks

        execution_hooks.on_flow_end(flow, job_state, "failed")

    return job_state
