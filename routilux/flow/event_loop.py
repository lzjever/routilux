"""
Event loop and task queue management for Flow execution.

Handles task queuing, event loop execution, and task execution.
"""

import logging
import queue
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from routilux.flow.flow import Flow
    from routilux.flow.task import SlotActivationTask


def start_event_loop(flow: "Flow") -> None:
    """Start the event loop thread.

    Args:
        flow: Flow object.
    """
    # Check if event loop thread is already running
    if flow._running and flow._execution_thread is not None and flow._execution_thread.is_alive():
        return

    # If thread exists but is not alive, reset _running flag
    if flow._execution_thread is not None and not flow._execution_thread.is_alive():
        flow._running = False

    flow._running = True
    flow._execution_thread = threading.Thread(target=event_loop, args=(flow,), daemon=True)
    flow._execution_thread.start()


def event_loop(flow: "Flow") -> None:
    """Event loop main logic.

    Args:
        flow: Flow object.
    """
    while flow._running:
        try:
            if flow._paused:
                time.sleep(0.01)
                continue

            try:
                task = flow._task_queue.get(timeout=0.1)
            except queue.Empty:
                # Check if all tasks are complete
                # Since tasks carry JobState, we check completion by examining active tasks
                # If queue is empty and no active tasks, execution is complete
                queue_empty = flow._task_queue.empty()
                with flow._execution_lock:
                    active_tasks = [f for f in flow._active_tasks if not f.done()]
                    active_count = len(active_tasks)

                if queue_empty and active_count == 0:
                    # All tasks completed, break event loop
                    break
                continue

            # Check if executor is still available (not shut down)
            executor = flow._get_executor()
            if executor is None:
                # Executor was shut down, stop event loop
                logging.warning("Executor was shut down, stopping event loop")
                flow._running = False
                break

            try:
                future = executor.submit(execute_task, task, flow)
            except RuntimeError as e:
                # Executor was shut down, stop event loop
                if "cannot schedule new futures after shutdown" in str(e):
                    logging.warning("Executor was shut down, stopping event loop")
                    flow._running = False
                    break
                raise

            with flow._execution_lock:
                flow._active_tasks.add(future)

            def on_task_done(fut=future):
                with flow._execution_lock:
                    flow._active_tasks.discard(fut)
                flow._task_queue.task_done()

            future.add_done_callback(on_task_done)

        except Exception as e:
            logging.exception(f"Error in event loop: {e}")


def execute_task(task: "SlotActivationTask", flow: "Flow") -> None:
    """Execute a single task.

    Args:
        task: SlotActivationTask to execute.
        flow: Flow object.
    """
    try:
        # Data is passed directly without transformation
        data = task.data

        # Set routine._current_flow for slot.receive() to find routine_id
        if task.slot.routine:
            task.slot.routine._current_flow = flow

        task.slot.receive(data, job_state=task.job_state, flow=flow)

    except Exception as e:
        from routilux.flow.error_handling import handle_task_error

        handle_task_error(task, e, flow)


def enqueue_task(task: "SlotActivationTask", flow: "Flow") -> None:
    """Enqueue a task for execution.

    Args:
        task: SlotActivationTask to enqueue.
        flow: Flow object.
    """
    if flow._paused:
        flow._pending_tasks.append(task)
    else:
        flow._task_queue.put(task)


def is_all_tasks_complete(flow: "Flow") -> bool:
    """Check if all tasks are complete.

    Args:
        flow: Flow object.

    Returns:
        True if queue is empty and no active tasks.
    """
    if not flow._task_queue.empty():
        return False

    with flow._execution_lock:
        active = [f for f in flow._active_tasks if not f.done()]
        return len(active) == 0
