"""
Event loop management utilities.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from routilux.core.flow import Flow

logger = logging.getLogger(__name__)


def ensure_event_loop_running(flow: "Flow") -> bool:
    """Ensure event loop is running, restart if needed.

    This function checks if the event loop is running and restarts it if:
    - Event loop thread is not alive
    - There are tasks in the queue

    Args:
        flow: Flow object to check.

    Returns:
        True if event loop is running (or was restarted), False otherwise.
    """
    # TODO: Update to use JobExecutor instead of Flow runtime state
    # Flow no longer has _task_queue, _execution_thread, etc.
    # This function should check JobExecutor's event loop thread instead
    # For now, return True as JobExecutor manages its own event loop
    return True


def wait_for_event_loop_completion(flow: "Flow", timeout: float | None = None) -> bool:
    """Wait for the event loop to complete all tasks.

    This function blocks until the event loop thread terminates or the timeout expires.
    The event loop terminates when:
    - The task queue is empty
    - All active tasks are completed
    - flow._running is set to False
    - flow._execution_thread terminates

    Args:
        flow: Flow object to wait for.
        timeout: Maximum time to wait in seconds. If None, waits indefinitely.

    Returns:
        True if event loop completed within timeout, False if timeout expired.
    """
    import time

    # CRITICAL fix: Validate required attributes exist
    required_attrs = [
        "_execution_thread",
        "_running",
        "_execution_lock",
        "_active_tasks",
        "_task_queue",
    ]
    for attr in required_attrs:
        if not hasattr(flow, attr):
            raise AttributeError(
                f"Flow is missing required attribute: {attr}. Ensure Flow.__init__() has been called properly."
            )

    start_time = time.time()

    # Wait for event loop thread to terminate AND all active tasks to complete
    while True:
        # Check timeout
        if timeout is not None:
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                logger.warning(
                    f"Timeout waiting for event loop to complete after {timeout} seconds"
                )
                return False

        # Check if event loop thread is still alive
        event_loop_alive = flow._execution_thread is not None and flow._execution_thread.is_alive()

        # Check if flow is still running (might have been stopped by error handler)
        flow_running = flow._running

        # Check if there are any active tasks
        with flow._execution_lock:
            active_tasks = [f for f in flow._active_tasks if not f.done()]
            active_count = len(active_tasks)

        # Check if task queue is empty
        queue_empty = flow._task_queue.empty()

        # MEDIUM fix: Improved condition to prevent early exit
        # Only exit if:
        # 1. Event loop is terminated (not just temporarily stopped)
        # 2. AND queue is empty
        # 3. AND no active tasks
        # The flow_running check alone could cause early exit if flag transiently changes
        if (not event_loop_alive) and queue_empty and active_count == 0:
            # Additional check: only exit if flow is actually done (not just paused)
            if not flow_running:
                break
            # Event loop terminated but flow says it's running - this is inconsistent
            # Log and exit to prevent infinite loop
            logging.getLogger(__name__).warning(
                "Event loop terminated but flow._running=True. "
                "This may indicate inconsistent state. Exiting wait loop."
            )
            break

        time.sleep(0.01)  # Small sleep to avoid busy waiting

    return True
