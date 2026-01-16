"""
Job executor for managing individual job execution context.

Each job has its own JobExecutor instance with:
- Independent task queue
- Independent event loop thread
- Reference to global thread pool
- Bound to a specific JobState
"""

import logging
import queue
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from concurrent.futures import Future, ThreadPoolExecutor

    from routilux.execution_tracker import ExecutionTracker
    from routilux.flow.flow import Flow
    from routilux.flow.task import SlotActivationTask
    from routilux.job_state import JobState

logger = logging.getLogger(__name__)


class JobExecutor:
    """Manages execution context for a single job.

    Each job has its own JobExecutor with:
    - Independent task queue (tasks are processed in order)
    - Independent event loop thread (processes tasks from queue)
    - Reference to global thread pool (shared by all jobs)
    - Bound to a specific JobState (tracks execution state)

    The JobExecutor is responsible for:
    - Starting job execution
    - Processing tasks via event loop
    - Handling timeouts
    - Detecting completion
    - Cleaning up resources

    Attributes:
        flow: Flow being executed.
        job_state: JobState for this execution.
        global_thread_pool: Global thread pool for task execution.
        timeout: Execution timeout in seconds.
        task_queue: Queue of tasks to execute.
        pending_tasks: Tasks that are paused/pending serialization.
        event_loop_thread: Thread running the event loop.
        active_tasks: Set of currently executing futures.
        execution_tracker: Tracks execution history for this job.
    """

    def __init__(
        self,
        flow: "Flow",
        job_state: "JobState",
        global_thread_pool: "ThreadPoolExecutor",
        timeout: float | None = None,
    ):
        """Initialize job executor.

        Args:
            flow: Flow to execute.
            job_state: JobState for this execution.
            global_thread_pool: Global thread pool to use.
            timeout: Execution timeout in seconds.
        """
        self.flow = flow
        self.job_state = job_state
        self.global_thread_pool = global_thread_pool
        self.timeout = timeout

        # Independent execution context
        self.task_queue: queue.Queue["SlotActivationTask"] = queue.Queue()
        self.pending_tasks: list["SlotActivationTask"] = []
        self.event_loop_thread: Optional[threading.Thread] = None
        self.active_tasks: set["Future"] = set()
        self._running = False
        self._paused = False
        self._lock = threading.Lock()
        self._start_time: Optional[float] = None

        # Execution tracker (one per job)
        self.execution_tracker: Optional["ExecutionTracker"] = None

        # Set flow context for all routines
        for routine in flow.routines.values():
            routine._current_flow = flow

    def start(self, entry_routine_id: str, entry_params: dict[str, Any]) -> None:
        """Start job execution.

        This method starts the event loop thread and triggers the entry routine.
        It returns immediately without waiting for execution to complete.

        Args:
            entry_routine_id: Entry routine identifier.
            entry_params: Entry parameters.

        Raises:
            ValueError: If entry routine not found or no trigger slot.
            RuntimeError: If job is already running.
        """
        if self._running:
            raise RuntimeError(f"Job {self.job_state.job_id} is already running")

        # Critical fix: Reset flow._paused when starting a new job
        # This handles the case where resume() starts a new executor after pause()
        self.flow._paused = False

        if entry_routine_id not in self.flow.routines:
            raise ValueError(f"Entry routine '{entry_routine_id}' not found")

        entry_routine = self.flow.routines[entry_routine_id]
        trigger_slot = entry_routine.get_slot("trigger")

        if trigger_slot is None:
            raise ValueError(
                f"Entry routine '{entry_routine_id}' must have 'trigger' slot. "
                f"Define it using: routine.define_slot('trigger', handler=your_handler)"
            )

        from routilux.execution_tracker import ExecutionTracker
        from routilux.status import ExecutionStatus

        # Update job state
        self.job_state.status = ExecutionStatus.RUNNING
        self.job_state.current_routine_id = entry_routine_id
        self._start_time = time.time()

        # Record execution start
        self.job_state.record_execution(entry_routine_id, "start", entry_params)

        # Create execution tracker (one per job)
        self.execution_tracker = ExecutionTracker(self.flow.flow_id)
        self.execution_tracker.record_routine_start(entry_routine_id, entry_params)

        # Monitoring hook: Flow start
        from routilux.monitoring.hooks import execution_hooks

        execution_hooks.on_flow_start(self.flow, self.job_state)

        # Start event loop
        self._running = True
        self.event_loop_thread = threading.Thread(
            target=self._event_loop,
            daemon=True,
            name=f"JobExecutor-{self.job_state.job_id[:8]}"
        )
        self.event_loop_thread.start()

        # Trigger entry routine
        self._trigger_entry(entry_routine_id, entry_params)

        logger.debug(f"Started job {self.job_state.job_id}")

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
                if self._paused:
                    time.sleep(0.01)
                    continue

                # Get task from queue
                try:
                    task = self.task_queue.get(timeout=0.1)
                except queue.Empty:
                    # Check if complete
                    if self._is_complete():
                        self._handle_completion()
                        break
                    continue

                # Submit to global thread pool
                future = self.global_thread_pool.submit(
                    self._execute_task, task
                )

                with self._lock:
                    self.active_tasks.add(future)

                def on_done(fut: "Future" = future) -> None:
                    with self._lock:
                        self.active_tasks.discard(fut)
                    try:
                        self.task_queue.task_done()
                    except ValueError:
                        # task_done() called more times than put()
                        pass

                future.add_done_callback(on_done)

            except Exception as e:
                logger.exception(f"Error in event loop for job {self.job_state.job_id}: {e}")
                self._handle_error(e)
                break

        # Cleanup
        self._cleanup()

    def _execute_task(self, task: "SlotActivationTask") -> None:
        """Execute a single task.

        Args:
            task: SlotActivationTask to execute.
        """
        from routilux.routine import _current_job_state

        # Set job_state in context variable
        old_job_state = _current_job_state.get(None)
        _current_job_state.set(self.job_state)

        try:
            # Apply parameter mapping if connection exists
            if task.connection:
                mapped_data = task.connection._apply_mapping(task.data)
            else:
                mapped_data = task.data

            # Set routine._current_flow for slot.receive()
            if task.slot.routine:
                task.slot.routine._current_flow = self.flow

            # Execute slot handler
            # Note: slot.receive() internally calls monitoring hooks
            # (on_routine_start, on_slot_call, on_routine_end)
            task.slot.receive(
                mapped_data,
                job_state=self.job_state,
                flow=self.flow
            )

        except Exception as e:
            from routilux.flow.error_handling import handle_task_error

            handle_task_error(task, e, self.flow)
        finally:
            # Restore context
            if old_job_state is not None:
                _current_job_state.set(old_job_state)
            else:
                _current_job_state.set(None)

    def _trigger_entry(self, entry_routine_id: str, entry_params: dict[str, Any]) -> None:
        """Trigger entry routine.

        Args:
            entry_routine_id: Entry routine identifier.
            entry_params: Entry parameters.
        """
        entry_routine = self.flow.routines[entry_routine_id]
        trigger_slot = entry_routine.get_slot("trigger")

        from routilux.flow.task import SlotActivationTask

        task = SlotActivationTask(
            slot=trigger_slot,
            data=entry_params,
            job_state=self.job_state,
            connection=None,
        )

        self.enqueue_task(task)

    def enqueue_task(self, task: "SlotActivationTask") -> None:
        """Enqueue a task for execution.

        If the job is paused, the task is added to pending_tasks instead.

        Args:
            task: SlotActivationTask to enqueue.
        """
        if self._paused:
            self.pending_tasks.append(task)
        else:
            self.task_queue.put(task)

    def _check_timeout(self) -> bool:
        """Check if job has timed out.

        Returns:
            True if timed out, False otherwise.
        """
        if self.timeout is not None and self._start_time is not None:
            elapsed = time.time() - self._start_time
            if elapsed >= self.timeout:
                logger.warning(
                    f"Job {self.job_state.job_id} timed out after {self.timeout}s"
                )
                self._handle_timeout()
                return True
        return False

    def _is_complete(self) -> bool:
        """Check if job is complete.

        A job is complete when:
        - Task queue is empty
        - No active tasks are running

        Returns:
            True if queue is empty and no active tasks.
        """
        if not self.task_queue.empty():
            return False

        with self._lock:
            active = [f for f in self.active_tasks if not f.done()]
            return len(active) == 0

    def _handle_completion(self) -> None:
        """Handle job completion."""
        from routilux.monitoring.hooks import execution_hooks
        from routilux.status import ExecutionStatus

        # Only mark as completed if not already failed
        if self.job_state.status != ExecutionStatus.FAILED:
            self.job_state.status = ExecutionStatus.COMPLETED

            # Record execution end
            if self.execution_tracker:
                entry_routine_id = self.job_state.current_routine_id
                if entry_routine_id:
                    self.execution_tracker.record_routine_end(entry_routine_id, "completed")

            execution_hooks.on_flow_end(self.flow, self.job_state, "completed")
            logger.debug(f"Job {self.job_state.job_id} completed")

    def _handle_timeout(self) -> None:
        """Handle job timeout."""
        from routilux.monitoring.hooks import execution_hooks
        from routilux.status import ExecutionStatus

        self.job_state.status = ExecutionStatus.FAILED
        self.job_state.shared_data["error"] = f"Job timed out after {self.timeout}s"

        # Record execution end
        if self.execution_tracker:
            entry_routine_id = self.job_state.current_routine_id
            if entry_routine_id:
                self.execution_tracker.record_routine_end(
                    entry_routine_id, "failed", error=f"Timeout after {self.timeout}s"
                )

        execution_hooks.on_flow_end(self.flow, self.job_state, "failed")
        logger.warning(f"Job {self.job_state.job_id} failed due to timeout")

    def _handle_error(self, error: Exception) -> None:
        """Handle job error.

        Args:
            error: Exception that occurred.
        """
        from routilux.monitoring.hooks import execution_hooks
        from routilux.status import ExecutionStatus

        self.job_state.status = ExecutionStatus.FAILED
        if "error" not in self.job_state.shared_data:
            self.job_state.shared_data["error"] = str(error)

        # Record execution end
        if self.execution_tracker:
            entry_routine_id = self.job_state.current_routine_id
            if entry_routine_id:
                self.execution_tracker.record_routine_end(
                    entry_routine_id, "failed", error=str(error)
                )

        execution_hooks.on_flow_end(self.flow, self.job_state, "failed")
        logger.error(f"Job {self.job_state.job_id} failed with error: {error}")

    def _cleanup(self) -> None:
        """Cleanup job executor."""
        self._running = False

        # Remove from global job manager
        from routilux.job_manager import get_job_manager

        job_manager = get_job_manager()
        job_manager.remove_job(self.job_state.job_id)

        logger.debug(f"Cleaned up job {self.job_state.job_id}")

    def pause(self, reason: str = "", checkpoint: dict[str, Any] | None = None) -> None:
        """Pause job execution.

        Args:
            reason: Reason for pausing.
            checkpoint: Optional checkpoint data.
        """
        from routilux.flow.job_state_management import pause_job_executor

        pause_job_executor(self, reason, checkpoint)

    def resume(self) -> "JobState":
        """Resume job execution.

        Returns:
            Updated JobState.
        """
        from routilux.flow.job_state_management import resume_job_executor

        return resume_job_executor(self)

    def cancel(self, reason: str = "") -> None:
        """Cancel job execution.

        Args:
            reason: Reason for cancellation.
        """
        from routilux.flow.job_state_management import cancel_job_executor

        cancel_job_executor(self, reason)

    def is_running(self) -> bool:
        """Check if job is running.

        Returns:
            True if running, False otherwise.
        """
        return self._running and not self._paused

    def is_paused(self) -> bool:
        """Check if job is paused.

        Returns:
            True if paused, False otherwise.
        """
        return self._paused

    def stop(self) -> None:
        """Stop job execution.

        This immediately stops the event loop and cleans up resources.
        """
        self._running = False

        # Cancel active tasks
        with self._lock:
            for future in list(self.active_tasks):
                if not future.done():
                    future.cancel()
            self.active_tasks.clear()

        # Wait for event loop thread
        if self.event_loop_thread and self.event_loop_thread.is_alive():
            self.event_loop_thread.join(timeout=1.0)

        logger.debug(f"Stopped job {self.job_state.job_id}")

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for job to complete.

        Args:
            timeout: Maximum time to wait in seconds. None for infinite wait.

        Returns:
            True if job completed, False if timeout.
        """
        if self.event_loop_thread is None:
            return True

        self.event_loop_thread.join(timeout=timeout)
        return not self.event_loop_thread.is_alive()
