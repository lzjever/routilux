"""
WorkerExecutor for managing individual worker execution context.

Each worker has its own WorkerExecutor instance with:
- Independent task queue
- Independent event loop thread
- Reference to global thread pool
- Bound to a specific WorkerState
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional, Set

if TYPE_CHECKING:
    from routilux.core.flow import Flow
    from routilux.core.task import EventRoutingTask, SlotActivationTask
    from routilux.core.worker import WorkerState
    from routilux.core.context import JobContext

from routilux.core.status import ExecutionStatus, RoutineStatus
from routilux.core.context import (
    _current_worker_state,
    _current_job,
    set_current_worker_state,
    set_current_job,
)

logger = logging.getLogger(__name__)


class WorkerExecutor:
    """Manages execution context for a single worker.

    Each worker has its own WorkerExecutor with:
    - Independent task queue (tasks are processed in order)
    - Independent event loop thread (processes tasks from queue)
    - Reference to global thread pool (shared by all workers)
    - Bound to a specific WorkerState (tracks execution state)

    The WorkerExecutor is responsible for:
    - Starting worker execution
    - Processing tasks via event loop
    - Handling timeouts
    - Detecting completion
    - Cleaning up resources
    - Binding JobContext for each task

    Attributes:
        flow: Flow being executed
        worker_state: WorkerState for this execution
        global_thread_pool: Global thread pool for task execution
        timeout: Execution timeout in seconds
        task_queue: Queue of tasks to execute
        pending_tasks: Tasks that are paused/pending
        event_loop_thread: Thread running the event loop
        active_tasks: Set of currently executing futures
    """

    def __init__(
        self,
        flow: "Flow",
        worker_state: "WorkerState",
        global_thread_pool: ThreadPoolExecutor,
        timeout: Optional[float] = None,
    ):
        """Initialize worker executor.

        Args:
            flow: Flow to execute
            worker_state: WorkerState for this execution
            global_thread_pool: Global thread pool to use
            timeout: Execution timeout in seconds
        """
        self.flow = flow
        self.worker_state = worker_state
        self.global_thread_pool = global_thread_pool
        self.timeout = timeout

        # Independent execution context
        self.task_queue: queue.Queue = queue.Queue()
        self.pending_tasks: List["SlotActivationTask"] = []
        self.event_loop_thread: Optional[threading.Thread] = None
        self.active_tasks: Set[Future] = set()
        self._running = False
        self._paused = False
        self._lock = threading.Lock()
        self._start_time: Optional[float] = None

        # Set executor reference in WorkerState
        worker_state._executor = self

        # Set flow context for all routines
        for routine in flow.routines.values():
            routine._current_flow = flow

    def start(self) -> None:
        """Start worker execution.

        This method starts the event loop thread. All routines start in IDLE state,
        waiting for external events via Runtime.post().

        Raises:
            RuntimeError: If worker is already running
        """
        with self._lock:
            if self._running:
                raise RuntimeError(
                    f"Worker {self.worker_state.worker_id} is already running"
                )

        # Update worker state
        self.worker_state.status = ExecutionStatus.RUNNING
        self.worker_state.started_at = datetime.now()
        self._start_time = time.time()

        # Initialize all routines to IDLE state
        for routine_id in self.flow.routines.keys():
            self.worker_state.update_routine_state(
                routine_id, {"status": RoutineStatus.IDLE.value}
            )

        # Call hooks if available
        from routilux.core.hooks import get_execution_hooks

        try:
            hooks = get_execution_hooks()
            hooks.on_worker_start(self.flow, self.worker_state)
        except Exception as e:
            logger.warning(f"Exception in on_worker_start hook: {e}", exc_info=True)

        # Start event loop
        with self._lock:
            self._running = True
        self.event_loop_thread = threading.Thread(
            target=self._event_loop,
            daemon=True,
            name=f"WorkerExecutor-{self.worker_state.worker_id[:8]}",
        )
        self.event_loop_thread.start()

        logger.debug(
            f"Started worker {self.worker_state.worker_id}, all routines in IDLE state"
        )

    def _event_loop(self) -> None:
        """Event loop main logic.

        This runs in a separate thread and processes tasks from the queue.
        Tasks are submitted to the global thread pool for execution.
        """
        while self._running:
            try:
                # Check timeout
                if self._check_timeout():
                    break

                # Check if paused
                if getattr(self, "_paused", False):
                    time.sleep(0.01)
                    continue

                # Get task from queue
                try:
                    task = self.task_queue.get(timeout=0.1)
                except queue.Empty:
                    # Check if complete
                    if self._is_complete():
                        self._handle_idle()
                    continue

                # Check task type
                from routilux.core.task import EventRoutingTask, SlotActivationTask

                if isinstance(task, EventRoutingTask):
                    # Route event in event loop thread
                    # Set job_context in context before routing
                    old_job = _current_job.get(None)
                    try:
                        if task.job_context:
                            set_current_job(task.job_context)
                        task.runtime.handle_event_emit(
                            task.event, task.event_data, task.worker_state
                        )
                    except Exception as e:
                        logger.exception(
                            f"Error routing event for worker {self.worker_state.worker_id}: {e}"
                        )
                    finally:
                        set_current_job(old_job)
                        self.task_queue.task_done()
                elif isinstance(task, SlotActivationTask):
                    # Submit routine execution to global thread pool
                    future = self.global_thread_pool.submit(self._execute_task, task)

                    with self._lock:
                        self.active_tasks.add(future)

                    def on_done(fut: Future = future) -> None:
                        with self._lock:
                            self.active_tasks.discard(fut)
                        try:
                            self.task_queue.task_done()
                        except ValueError:
                            pass

                    future.add_done_callback(on_done)
                else:
                    logger.warning(f"Unknown task type: {type(task).__name__}")
                    self.task_queue.task_done()

            except Exception as e:
                logger.exception(
                    f"Error in event loop for worker {self.worker_state.worker_id}: {e}"
                )
                self._handle_error(e)
                break

        # Cleanup
        self._cleanup()

    def _execute_task(self, task: "SlotActivationTask") -> None:
        """Execute a single task.

        This method sets the worker_state and job_context in context variables
        before executing the task.

        Args:
            task: SlotActivationTask to execute
        """
        # Save old context
        old_worker_state = _current_worker_state.get(None)
        old_job = _current_job.get(None)

        try:
            # Set context variables
            set_current_worker_state(self.worker_state)
            if task.job_context:
                set_current_job(task.job_context)

            mapped_data = task.data

            # Set routine context
            if task.slot.routine:
                task.slot.routine._current_flow = self.flow
                runtime = getattr(self.worker_state, "_runtime", None)
                if runtime:
                    task.slot.routine._current_runtime = runtime

            # Enqueue data to slot
            from datetime import datetime

            task.slot.enqueue(
                data=mapped_data,
                emitted_from=(
                    "external"
                    if task.connection is None
                    else (
                        getattr(task.connection, "_source_routine_id", None)
                        or "external"
                    )
                ),
                emitted_at=datetime.now(),
            )

            # Trigger routine activation check
            routine = task.slot.routine
            if routine is not None:
                runtime = getattr(self.worker_state, "_runtime", None)
                if runtime:
                    runtime._check_routine_activation(routine, self.worker_state)

            # Check if routine should be marked as IDLE
            if task.slot.routine:
                routine_id = self.flow._get_routine_id(task.slot.routine)
                if routine_id:
                    has_pending_data = False
                    for slot in task.slot.routine.slots.values():
                        if slot.get_unconsumed_count() > 0:
                            has_pending_data = True
                            break

                    if not has_pending_data:
                        self.worker_state.update_routine_state(
                            routine_id, {"status": RoutineStatus.IDLE.value}
                        )

                        if self._all_routines_idle() and self._is_complete():
                            self._handle_idle()

        except Exception as e:
            logger.exception(f"Error executing task: {e}")
            # Handle error via error handler if available
            if task.slot.routine:
                routine_id = self.flow._get_routine_id(task.slot.routine)
                if routine_id:
                    error_handler = self.flow._get_error_handler_for_routine(
                        task.slot.routine, routine_id
                    )
                    if error_handler:
                        error_handler.handle_error(
                            e,
                            task.slot.routine,
                            routine_id,
                            self.flow,
                            self.worker_state,
                        )
        finally:
            # Restore context
            try:
                set_current_worker_state(old_worker_state)
                set_current_job(old_job)
            except Exception:
                logger.exception("Failed to restore context variables")

    def enqueue_task(self, task: Any) -> None:
        """Enqueue a task for execution.

        Supports both SlotActivationTask and EventRoutingTask.

        Args:
            task: Task to enqueue
        """
        if getattr(self, "_paused", False):
            with self._lock:
                self.pending_tasks.append(task)
        else:
            self.task_queue.put(task)

    def _check_timeout(self) -> bool:
        """Check if worker has timed out.

        Returns:
            True if timed out, False otherwise
        """
        if self.timeout is not None and self._start_time is not None:
            elapsed = time.time() - self._start_time
            if elapsed >= self.timeout:
                logger.warning(
                    f"Worker {self.worker_state.worker_id} timed out after {self.timeout}s"
                )
                self._handle_timeout()
                return True
        return False

    def _is_complete(self) -> bool:
        """Check if worker has no pending work.

        Returns:
            True if queue is empty and no active tasks
        """
        with self._lock:
            if not self.task_queue.empty():
                return False
            active = [f for f in self.active_tasks if not f.done()]
            return len(active) == 0

    def _all_routines_idle(self) -> bool:
        """Check if all routines are in IDLE state.

        Returns:
            True if all routines are IDLE
        """
        for routine_id in self.flow.routines.keys():
            routine_state = self.worker_state.get_routine_state(routine_id)
            if routine_state is None:
                return False
            status = routine_state.get("status")
            if status not in (
                RoutineStatus.IDLE.value,
                RoutineStatus.COMPLETED.value,
                "idle",
                "completed",
            ):
                return False
        return True

    def _handle_idle(self) -> None:
        """Handle worker going idle (all routines completed, waiting for new tasks)."""
        if self.worker_state.status not in (
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
            ExecutionStatus.COMPLETED,
        ):
            if self._all_routines_idle() and self._is_complete():
                if self.worker_state.status != ExecutionStatus.IDLE:
                    self.worker_state.status = ExecutionStatus.IDLE
                    logger.debug(
                        f"Worker {self.worker_state.worker_id} is now IDLE"
                    )

    def _handle_timeout(self) -> None:
        """Handle worker timeout."""
        self.worker_state.status = ExecutionStatus.FAILED
        self.worker_state.error = "Execution timed out"
        self._running = False

        # Call hooks
        from routilux.core.hooks import get_execution_hooks

        try:
            hooks = get_execution_hooks()
            hooks.on_worker_stop(self.flow, self.worker_state, "failed")
        except Exception as e:
            logger.warning(f"Exception in on_worker_stop hook: {e}", exc_info=True)

    def _handle_error(self, error: Exception) -> None:
        """Handle worker error."""
        self.worker_state.status = ExecutionStatus.FAILED
        self.worker_state.error = str(error)
        self._running = False

        # Call hooks
        from routilux.core.hooks import get_execution_hooks

        try:
            hooks = get_execution_hooks()
            hooks.on_worker_stop(self.flow, self.worker_state, "failed")
        except Exception as e:
            logger.warning(f"Exception in on_worker_stop hook: {e}", exc_info=True)

    def _cleanup(self) -> None:
        """Cleanup resources."""
        logger.debug(f"Cleaning up worker {self.worker_state.worker_id}")

        # Wait for active tasks
        with self._lock:
            for future in list(self.active_tasks):
                try:
                    future.result(timeout=1.0)
                except Exception:
                    pass
            self.active_tasks.clear()

    def pause(self, reason: str = "", checkpoint: Optional[dict] = None) -> None:
        """Pause worker execution.

        Args:
            reason: Reason for pausing
            checkpoint: Optional checkpoint data
        """
        with self._lock:
            self._paused = True
            self.worker_state._set_paused(reason, checkpoint)

    def resume(self) -> "WorkerState":
        """Resume worker execution.

        Returns:
            Updated WorkerState
        """
        with self._lock:
            self._paused = False
            self.worker_state._set_running()

            # Move pending tasks back to queue
            for task in self.pending_tasks:
                self.task_queue.put(task)
            self.pending_tasks.clear()

        return self.worker_state

    def cancel(self, reason: str = "") -> None:
        """Cancel worker execution.

        Args:
            reason: Reason for cancellation
        """
        with self._lock:
            self._running = False
            self.worker_state._set_cancelled(reason)

        # Call hooks
        from routilux.core.hooks import get_execution_hooks

        try:
            hooks = get_execution_hooks()
            hooks.on_worker_stop(self.flow, self.worker_state, "cancelled")
        except Exception as e:
            logger.warning(f"Exception in on_worker_stop hook: {e}", exc_info=True)

    def stop(self, status: str = "completed") -> None:
        """Stop worker execution.

        Args:
            status: Final status
        """
        with self._lock:
            self._running = False

            if status == "completed":
                self.worker_state.status = ExecutionStatus.COMPLETED
            elif status == "failed":
                self.worker_state.status = ExecutionStatus.FAILED
            else:
                self.worker_state.status = ExecutionStatus.CANCELLED

            self.worker_state.completed_at = datetime.now()

        # Call hooks
        from routilux.core.hooks import get_execution_hooks

        try:
            hooks = get_execution_hooks()
            hooks.on_worker_stop(self.flow, self.worker_state, status)
        except Exception as e:
            logger.warning(f"Exception in on_worker_stop hook: {e}", exc_info=True)
