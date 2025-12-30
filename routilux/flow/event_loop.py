"""
Event loop and task queue management for Flow execution.

Handles task queuing, event loop execution, and task execution.
"""

import queue
import threading
import time
import logging
from typing import Set, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor, Future

if TYPE_CHECKING:
    from routilux.flow.task import SlotActivationTask
    from routilux.flow.flow import Flow


def start_event_loop(flow: "Flow") -> None:
    """Start the event loop thread.

    Args:
        flow: Flow object.
    """
    if flow._running:
        return

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
                # Wait a bit more to ensure no new tasks are being enqueued
                time.sleep(0.05)
                if is_all_tasks_complete(flow):
                    if flow.job_state and flow.job_state.status == "running":
                        flow.job_state.status = "completed"
                    break
                continue

            executor = flow._get_executor()
            future = executor.submit(execute_task, task, flow)

            with flow._execution_lock:
                flow._active_tasks.add(future)

            def on_task_done(fut=future):
                with flow._execution_lock:
                    flow._active_tasks.discard(fut)
                flow._task_queue.task_done()

            future.add_done_callback(on_task_done)

        except Exception as e:
            logging.exception(f"Error in event loop: {e}")
            # Continue loop even on error to prevent silent failures


def execute_task(task: "SlotActivationTask", flow: "Flow") -> None:
    """Execute a single task.

    Args:
        task: SlotActivationTask to execute.
        flow: Flow object.
    """
    try:
        if task.connection:
            mapped_data = task.connection._apply_mapping(task.data)
        else:
            mapped_data = task.data

        task.slot.receive(mapped_data)

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
