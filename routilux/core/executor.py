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
from concurrent.futures import ALL_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from routilux.core.flow import Flow
    from routilux.core.task import SlotActivationTask
    from routilux.core.worker import WorkerState

from routilux.core.context import (
    ExecutionContext,
    _current_job,
    _current_worker_state,
    get_current_execution_context,
    set_current_execution_context,
    set_current_job,
    set_current_worker_state,
)
from routilux.core.status import ExecutionStatus, RoutineStatus

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
        flow: Flow,
        worker_state: WorkerState,
        global_thread_pool: ThreadPoolExecutor,
        timeout: float | None = None,
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
        self.pending_tasks: list[SlotActivationTask] = []
        self.event_loop_thread: threading.Thread | None = None
        self.active_tasks: set[Future] = set()
        self._running = False
        self._paused = False
        self._lock = threading.Lock()
        self._start_time: float | None = None
        # Counter for queued tasks (avoids race condition with Queue.empty())
        self._pending_task_count: int = 0

        # Set executor reference in WorkerState
        worker_state._executor = self

        # NOTE: No longer set routine._current_flow
        # Flow context is now provided via ExecutionContext in _execute_task()

    def start(self) -> None:
        """Start worker execution.

        This method starts the event loop thread. All routines start in IDLE state,
        waiting for external events via Runtime.post().

        Raises:
            RuntimeError: If worker is already running
        """
        with self._lock:
            if self._running:
                raise RuntimeError(f"Worker {self.worker_state.worker_id} is already running")

        # Update worker state
        self.worker_state.status = ExecutionStatus.RUNNING
        self.worker_state.started_at = datetime.now()
        self._start_time = time.time()

        # Initialize all routines to IDLE state
        for routine_id in self.flow.routines.keys():
            self.worker_state.update_routine_state(routine_id, {"status": RoutineStatus.IDLE.value})

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

        logger.debug(f"Started worker {self.worker_state.worker_id}, all routines in IDLE state")

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
                    with self._lock:
                        self._pending_task_count -= 1
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
                    try:
                        future = self.global_thread_pool.submit(self._execute_task, task)
                    except Exception as e:
                        # If submit fails, we must still call task_done() to avoid queue count error
                        logger.error(f"Failed to submit task: {e}")
                        self.task_queue.task_done()
                        continue

                    # CRITICAL: Register callback BEFORE adding to active_tasks
                    # This prevents race condition where future completes between
                    # adding to set and registering callback
                    def on_done(fut: Future = future) -> None:
                        with self._lock:
                            self.active_tasks.discard(fut)
                        try:
                            self.task_queue.task_done()
                        except ValueError:
                            pass

                    future.add_done_callback(on_done)

                    # Now safe to add to active_tasks - callback is already registered
                    with self._lock:
                        self.active_tasks.add(future)
                else:
                    logger.warning(f"Unknown task type: {type(task).__name__}")
                    self.task_queue.task_done()

            except Exception as e:
                # Only break on fatal errors, continue on non-fatal exceptions
                if isinstance(e, (SystemExit, KeyboardInterrupt)):
                    raise
                logger.exception(
                    f"Error in event loop for worker {self.worker_state.worker_id}: {e}"
                )
                # Continue running - don't break the loop for transient errors

        # Cleanup
        self._cleanup()

    def _execute_task(self, task: SlotActivationTask) -> None:
        """Execute a routine task with data from a slot.

        This is the core execution method that processes SlotActivationTask objects.
        It sets up the unified execution context (ExecutionContext) in context variables
        before executing the task, providing a single source of truth for all execution
        context information.

        Execution Flow:
            1. Save current context variables (for restoration after execution)
            2. Build unified ExecutionContext with flow, worker_state, routine_id, job_context
            3. Set context variables (execution_context, worker_state, job_context)
            4. Enqueue data to the target slot
            5. Trigger routine activation check (may execute routine logic)
            6. Check if routine should be marked IDLE (no pending data)
            7. Handle any errors via error handler
            8. Restore previous context variables

        Context Management:
            - Uses contextvars to provide thread-local execution context
            - ExecutionContext provides unified access to flow, worker_state, routine_id, job_context
            - Context is properly restored after execution (even on error)

        Args:
            task: SlotActivationTask containing slot, data, and job_context

        Raises:
            Exception: Propagates exceptions from slot enqueue or activation check
                       (logged and handled by error handler if available)

        Note:
            - This method is called from the global thread pool (not event loop thread)
            - Event routing is handled separately via EventRoutingTask in event loop
            - Routine logic execution happens during activation check, not here
        """
        # Step 1: Save old context for restoration (ensures isolation)
        old_execution_context = get_current_execution_context()
        old_worker_state = _current_worker_state.get(None)
        old_job = _current_job.get(None)

        try:
            # Step 2: Get routine_id before setting context (needed for ExecutionContext)
            routine_id = ""
            if task.slot.routine:
                routine_id = self.flow._get_routine_id(task.slot.routine) or ""

            # Step 3: Build complete ExecutionContext (single source of truth)
            ctx = ExecutionContext(
                flow=self.flow,
                worker_state=self.worker_state,
                routine_id=routine_id,
                job_context=task.job_context,
            )

            # Step 4: Set unified execution context (thread-local via contextvars)
            set_current_execution_context(ctx)
            set_current_worker_state(self.worker_state)
            if task.job_context:
                set_current_job(task.job_context)

            mapped_data = task.data

            # NOTE: No longer set routine._current_flow or routine._current_runtime
            # All context information is now available via ExecutionContext

            # Step 5: Enqueue data to slot (triggers downstream processing)
            from datetime import datetime

            task.slot.enqueue(
                data=mapped_data,
                emitted_from=(
                    "external"
                    if task.connection is None
                    else (getattr(task.connection, "_source_routine_id", None) or "external")
                ),
                emitted_at=datetime.now(),
            )

            # Step 6: Trigger routine activation check
            # This may execute the routine's logic() if activation policy allows
            routine = task.slot.routine
            if routine is not None:
                runtime = getattr(self.worker_state, "_runtime", None)
                if runtime:
                    runtime._check_routine_activation(routine, self.worker_state)

            # Step 7: Check if routine should be marked as IDLE
            # A routine is IDLE when all its slots have no unconsumed data
            if task.slot.routine:
                routine_id = self.flow._get_routine_id(task.slot.routine)
                if routine_id:
                    # Check all slots for pending data
                    has_pending_data = False
                    for slot in task.slot.routine.slots.values():
                        if slot.get_unconsumed_count() > 0:
                            has_pending_data = True
                            break

                    # Mark as IDLE if no pending data
                    if not has_pending_data:
                        self.worker_state.update_routine_state(
                            routine_id, {"status": RoutineStatus.IDLE.value}
                        )

                        # Check if entire worker is idle (all routines idle + no pending tasks)
                        if self._all_routines_idle() and self._is_complete():
                            self._handle_idle()

        except Exception as e:
            # Step 8: Handle errors via error handler if available
            logger.exception(f"Error executing task: {e}")
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
            # Step 9: Always restore old context (even on error)
            # This prevents context leakage between tasks
            set_current_execution_context(old_execution_context)
            if old_worker_state:
                set_current_worker_state(old_worker_state)
            else:
                set_current_worker_state(None)
            if old_job:
                set_current_job(old_job)
            else:
                set_current_job(None)

    def enqueue_task(self, task: Any) -> None:
        """Enqueue a task for execution.

        Supports both SlotActivationTask and EventRoutingTask.

        Args:
            task: Task to enqueue
        """
        with self._lock:
            if self._paused:
                self.pending_tasks.append(task)
                return
            self._pending_task_count += 1
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

        Uses counter instead of Queue.empty() to avoid race condition.

        Returns:
            True if queue is empty and no active tasks
        """
        with self._lock:
            if self._pending_task_count > 0:
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
                    logger.debug(f"Worker {self.worker_state.worker_id} is now IDLE")

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
        """Cleanup resources with proper task completion wait.

        Uses concurrent.futures.wait() to ensure all tasks complete or timeout,
        preventing resource leaks from incomplete task tracking.
        """
        logger.debug(f"Cleaning up worker {self.worker_state.worker_id}")

        # Get all pending tasks
        with self._lock:
            pending = list(self.active_tasks)

        if not pending:
            return

        # Use wait() to ensure all tasks complete or timeout (30s total)
        # This is more reliable than per-task 1s timeout
        try:
            done, not_done = wait(pending, timeout=30.0, return_when=ALL_COMPLETED)
            if not_done:
                logger.warning(
                    f"{len(not_done)} tasks did not complete within 30s timeout, cancelling"
                )
                # Cancel any tasks that didn't complete
                for future in not_done:
                    future.cancel()
        except Exception as e:
            logger.warning(f"Error waiting for tasks to complete: {e}")

        # Clear active tasks
        with self._lock:
            self.active_tasks.clear()

        # Note: We cannot join the event loop thread from within itself
        # The thread will naturally terminate when _running becomes False
        # External shutdown should call cancel() or stop() which sets _running = False

    def pause(self, reason: str = "", checkpoint: dict | None = None) -> None:
        """Pause worker execution.

        Args:
            reason: Reason for pausing
            checkpoint: Optional checkpoint data
        """
        with self._lock:
            self._paused = True
            self.worker_state._set_paused(reason, checkpoint)

    def resume(self) -> WorkerState:
        """Resume worker execution.

        Returns:
            Updated WorkerState
        """
        with self._lock:
            self._paused = False
            self.worker_state._set_running()

            # Move pending tasks back to queue (update counter for each)
            for task in self.pending_tasks:
                self._pending_task_count += 1
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
