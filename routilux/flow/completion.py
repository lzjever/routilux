"""
Event loop management utilities.
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from routilux.flow.flow import Flow

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
    from routilux.flow.event_loop import start_event_loop

    queue_size = flow._task_queue.qsize()
    is_running = flow._execution_thread is not None and flow._execution_thread.is_alive()

    # If there are tasks but event loop is not running, restart it
    if queue_size > 0 and not is_running:
        logger.warning(
            f"Event loop stopped but {queue_size} tasks in queue. Restarting event loop."
        )
        start_event_loop(flow)
        return True

    return is_running


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

        # Done if: event loop terminated OR flow stopped AND queue empty AND no active tasks
        if ((not event_loop_alive) or (not flow_running)) and queue_empty and active_count == 0:
            break

        time.sleep(0.01)  # Small sleep to avoid busy waiting

    return True
