"""
Runtime class for centralized workflow execution management.

The Runtime provides a centralized execution manager with thread pool,
worker registry, and event routing capabilities.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from routilux.core.event import Event
    from routilux.core.routine import Routine
    from routilux.core.worker import WorkerState

from routilux.core.context import JobContext
from routilux.core.interfaces import IEventHandler
from routilux.core.slot import SlotQueueFullError
from routilux.core.status import ExecutionStatus

logger = logging.getLogger(__name__)


class Runtime(IEventHandler):
    """Centralized execution manager for workflow execution.

    The Runtime manages all workflow executions with a shared thread pool,
    provides worker tracking, and handles event routing.

    Implements IEventHandler for processing emitted events.

    Key Features:
        - Thread pool management (shared across all workers)
        - Worker registry (thread-safe tracking of active workers)
        - Non-blocking execution (exec() returns immediately)
        - Event routing (routes events to connected slots)
        - Routine activation checking (calls activation policies)
        - Job context binding (for per-task tracking)

    Thread Safety:
        This class uses multiple locks to protect shared state. To prevent deadlock,
        locks MUST be acquired in the following order:

        1. _worker_lock (protects _active_workers)
        2. _jobs_lock (protects _active_jobs)

        NEVER acquire these locks in a different order. When multiple locks are
        needed, always use nested `with` statements in the correct order.

    Examples:
        >>> runtime = Runtime(thread_pool_size=10)
        >>> worker_state = runtime.exec("my_flow")
        >>>
        >>> # Send external data and create a job
        >>> worker_state, job = runtime.post(
        ...     "my_flow", "processor", "input",
        ...     {"data": "test"},
        ...     metadata={"user_id": "123"}
        ... )
        >>>
        >>> # Get job output
        >>> from routilux.core import get_job_output
        >>> output = get_job_output(job.job_id)
    """

    def __init__(self, thread_pool_size: int = 10):
        """Initialize Runtime.

        Args:
            thread_pool_size: Maximum number of worker threads.
                Use 0 to use global WorkerManager's pool.

        Raises:
            ValueError: If thread_pool_size is negative
        """
        if thread_pool_size < 0:
            raise ValueError(f"thread_pool_size must be >= 0, got {thread_pool_size}")
        if thread_pool_size > 1000:
            logger.warning(f"thread_pool_size {thread_pool_size} is unusually large")

        self.thread_pool_size = thread_pool_size
        if thread_pool_size == 0:
            self.thread_pool: ThreadPoolExecutor | None = None
        else:
            self.thread_pool = ThreadPoolExecutor(
                max_workers=thread_pool_size, thread_name_prefix="RoutiluxWorker"
            )

        self._active_workers: dict[str, WorkerState] = {}
        self._worker_lock = threading.RLock()
        self._shutdown = False
        self._is_shutdown = False

        # Track active jobs by worker: worker_id -> dict[job_id -> JobContext]
        self._active_jobs: dict[str, dict[str, JobContext]] = {}
        self._jobs_lock = threading.RLock()

    def __del__(self) -> None:
        """Cleanup thread pool when Runtime is garbage collected."""
        if (
            not getattr(self, "_is_shutdown", False)
            and getattr(self, "thread_pool", None) is not None
        ):
            try:
                self.thread_pool.shutdown(wait=False)
            except Exception:
                pass

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown(wait=True)
        return False

    def exec(
        self, flow_name: str, worker_state: WorkerState | None = None, worker_id: str | None = None
    ) -> WorkerState:
        """Execute a flow and return immediately.

        This method starts flow execution in the background and returns
        immediately with a WorkerState that can be used to track progress.

        Args:
            flow_name: Name of the flow to execute (must be registered)
            worker_state: Optional existing WorkerState (for resuming)
            worker_id: Optional custom worker ID. Ignored if worker_state is provided.

        Returns:
            WorkerState object (status will be RUNNING)

        Raises:
            ValueError: If flow_name not found in registry
            RuntimeError: If Runtime is shut down
        """
        if self._shutdown:
            raise RuntimeError("Runtime is shut down")

        # Get flow from registry
        from routilux.core.registry import FlowRegistry

        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get_by_name(flow_name)
        if flow is None:
            flow = flow_registry.get(flow_name)
        if flow is None:
            raise ValueError(f"Flow '{flow_name}' not found in registry")

        # Create or use existing worker_state
        if worker_state is None:
            from routilux.core.worker import WorkerState

            worker_state = WorkerState(flow_id=flow.flow_id, worker_id=worker_id)
        else:
            if worker_state.flow_id != flow.flow_id:
                raise ValueError(f"WorkerState flow_id ({worker_state.flow_id}) does not match")

        # Set status and runtime reference
        worker_state.status = ExecutionStatus.RUNNING
        if worker_state.started_at is None:
            worker_state.started_at = datetime.now()
        worker_state._runtime = self

        # Use WorkerManager to start worker
        from routilux.core.manager import get_worker_manager

        worker_manager = get_worker_manager()
        worker_state = worker_manager.start_worker(
            flow=flow,
            timeout=flow.execution_timeout,
            worker_state=worker_state,
        )

        # Register in active workers and initialize jobs dict
        # Acquire locks in correct order: _worker_lock -> _jobs_lock
        with self._worker_lock:
            self._active_workers[worker_state.worker_id] = worker_state
            with self._jobs_lock:
                self._active_jobs[worker_state.worker_id] = {}

        return worker_state

    def post(
        self,
        flow_name: str,
        routine_name: str,
        slot_name: str,
        data: dict[str, Any],
        worker_id: str | None = None,
        job_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[WorkerState, JobContext]:
        """Send external event to a specific routine's slot.

        This method allows external systems to inject data into a running worker
        or create a new worker if worker_id is None.

        Each call creates a new JobContext to track this specific task.

        Args:
            flow_name: Name of the flow (must be registered)
            routine_name: Name of the routine to receive the data
            slot_name: Name of the slot to send data to
            data: Data dictionary to send to the slot
            worker_id: Optional worker ID (None = create new worker)
            job_id: Optional job ID (None = auto-generate)
            metadata: Optional job metadata (user_id, source, etc.)

        Returns:
            Tuple of (WorkerState, JobContext)

        Raises:
            ValueError: If flow_name, routine_name, or slot_name not found
            RuntimeError: If Runtime is shut down or worker is COMPLETED
        """
        if self._shutdown:
            raise RuntimeError("Runtime is shut down")

        # Get flow from registry
        from routilux.core.registry import FlowRegistry

        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get_by_name(flow_name)
        if flow is None:
            flow = flow_registry.get(flow_name)
        if flow is None:
            raise ValueError(f"Flow '{flow_name}' not found in registry")

        # Get or create worker
        if worker_id:
            worker_state = None
            with self._worker_lock:
                worker_state = self._active_workers.get(worker_id)

            # Try registry if not found
            if worker_state is None:
                from routilux.core.registry import WorkerRegistry

                registry = WorkerRegistry.get_instance()
                worker_state = registry.get(worker_id)

            if worker_state is None:
                raise ValueError(f"Worker '{worker_id}' not found")
            if worker_state.status == ExecutionStatus.COMPLETED:
                raise RuntimeError(f"Worker '{worker_id}' is already completed")
            worker_state._runtime = self
        else:
            # Create new worker
            worker_state = self.exec(flow_name)

        # Create JobContext for this task
        job_context = JobContext(
            job_id=job_id or str(uuid.uuid4()),
            worker_id=worker_state.worker_id,
            flow_id=flow.flow_id,  # Store flow_id directly in JobContext
            metadata=metadata or {},
        )
        job_context.start()

        # Register job
        with self._jobs_lock:
            if worker_state.worker_id not in self._active_jobs:
                self._active_jobs[worker_state.worker_id] = {}
            self._active_jobs[worker_state.worker_id][job_context.job_id] = job_context

        # Call on_job_start hook
        from routilux.core.hooks import get_execution_hooks

        try:
            hooks = get_execution_hooks()
            logger.debug(f"Calling on_job_start hook for job {job_context.job_id}")
            hooks.on_job_start(job_context, worker_state)
            logger.debug(f"on_job_start hook completed for job {job_context.job_id}")
        except Exception as e:
            logger.warning(f"Exception in on_job_start hook: {e}", exc_info=True)

        # Get routine and slot
        if routine_name not in flow.routines:
            raise ValueError(f"Routine '{routine_name}' not found in flow")
        routine = flow.routines[routine_name]
        slot = routine.get_slot(slot_name)
        if slot is None:
            raise ValueError(f"Slot '{slot_name}' not found in routine '{routine_name}'")

        # Get WorkerExecutor
        worker_executor = getattr(worker_state, "_executor", None)
        if worker_executor is None:
            raise RuntimeError(f"WorkerExecutor not found for worker {worker_state.worker_id}")

        # Create task and submit with job_context
        from routilux.core.task import SlotActivationTask

        task = SlotActivationTask(
            slot=slot,
            data=data,
            worker_state=worker_state,
            job_context=job_context,
            connection=None,
        )

        worker_executor.enqueue_task(task)

        return worker_state, job_context

    def handle_event_emit(
        self,
        event: Event,
        event_data: dict[str, Any],
        worker_state: WorkerState,
    ) -> None:
        """Handle event emission and route data to all connected slots.

        This method implements the core event routing mechanism, dispatching event
        data to all slots connected to the emitted event. It is called by
        WorkerExecutor's event loop thread when processing EventRoutingTask.

        Dispatching Strategy:
            1. Get flow from registry and find all connections for this event
            2. Get current JobContext from thread-local context (for hooks)
            3. Record event emission in worker_state execution history
            4. Call on_event_emit hook (may cancel further processing)
            5. For each connected slot:
               a. Validate event_data structure (must have "data" and "metadata")
               b. Call on_slot_before_enqueue hook (may skip enqueue)
               c. Enqueue data to slot (non-blocking, may raise SlotQueueFullError)
               d. Trigger routine activation check
            6. Handle SlotQueueFullError with warning (drops event)
            7. Handle other exceptions with error logging

        Context Variable (contextvar) Requirements:
            This method retrieves the current JobContext from thread-local context
            using get_current_job(). The job_context is used for:

            1. Hook-based interception: on_slot_before_enqueue hook can control
               whether data is enqueued (used for breakpoints)
            2. Execution hooks: Hooks receive job_context for tracking/monitoring
            3. Event tracking: Event emissions recorded with job_id for debugging

        Important:
            - This method is called from WorkerExecutor's event loop thread
            - WorkerExecutor sets job_context in context before calling this method
            - The job_context comes from EventRoutingTask.job_context, captured
              when Event.emit() was called

        Hook-Based Interception:
            Before enqueueing, on_slot_before_enqueue hook is called. If the hook
            returns should_enqueue=False, the enqueue is skipped. This mechanism
            is used by monitoring to implement breakpoints, but can be used for
            other interception purposes.

        Args:
            event: Event object that was emitted (contains name, routine ref)
            event_data: Dictionary with "data" (payload) and "metadata" keys
            worker_state: WorkerState for tracking execution history

        Raises:
            No exceptions raised (errors are logged and handled internally)

        Example Context Setup (for testing):
            When testing event routing directly, ensure job_context is set:

            .. code-block:: python

                from routilux.core.context import set_current_job

                worker_state, job_context = runtime.post(...)
                set_current_job(job_context)

                # Now event routing has access to job_context
                source.output.emit(runtime=runtime, worker_state=worker_state, data="test")
        """
        from routilux.core.hooks import get_execution_hooks
        from routilux.core.registry import FlowRegistry

        # Step 1: Get flow from registry to find connections
        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get(worker_state.flow_id)
        if flow is None:
            logger.warning(f"Flow {worker_state.flow_id} not found, cannot route event")
            return

        # Step 2: Find all connections for this event
        connections = flow.get_connections_for_event(event)
        if not connections:
            logger.debug(
                f"No connections found for event {event.name} from routine {event.routine}"
            )
            return  # No consumers - normal case

        # Step 3: Get job context early (needed for hooks)
        from routilux.core.context import get_current_job

        job_context = get_current_job()

        logger.debug(
            f"Event routing: event={event.name}, connections={len(connections)}, "
            f"job_context={job_context.job_id if job_context else None}"
        )

        # Step 4: Track event emission and call on_event_emit hook
        source_routine_id = self._get_routine_id(event.routine, worker_state)
        hooks = get_execution_hooks()

        if source_routine_id:
            data = event_data.get("data", {}) if isinstance(event_data, dict) else {}
            worker_state.record_execution(
                source_routine_id,
                "event_emit",
                {"event_name": event.name, "data": data},
            )

            # Hook may cancel event routing
            should_continue = hooks.on_event_emit(
                event, source_routine_id, worker_state, job_context, data
            )
            if not should_continue:
                return

        # Step 5: Route to all connected slots
        for connection in connections:
            slot = connection.target_slot
            if slot is None:
                continue

            try:
                # Validate event_data structure
                if not isinstance(event_data, dict):
                    logger.error(f"Invalid event_data type: {type(event_data).__name__}")
                    continue

                metadata = event_data.get("metadata")
                if not isinstance(metadata, dict):
                    logger.error("Invalid or missing metadata in event_data")
                    continue

                data = event_data.get("data", {})
                emitted_from = metadata.get("emitted_from", "unknown")
                emitted_at = metadata.get("emitted_at", datetime.now())

                # Get target routine and slot information for hook
                target_routine = slot.routine
                target_routine_id = None
                if target_routine is not None:
                    target_routine_id = flow._get_routine_id(target_routine)

                # Call on_slot_before_enqueue hook (may skip enqueue)
                # This is used for breakpoints and other interception
                if target_routine_id is None:
                    # If we can't find routine_id, allow enqueue (backward compatibility)
                    logger.debug(f"Skipping hook call: routine_id not found for slot {slot.name}")
                else:
                    should_enqueue, reason = hooks.on_slot_before_enqueue(
                        slot=slot,
                        routine_id=target_routine_id,
                        job_context=job_context,
                        data=data,
                        flow_id=flow.flow_id,
                    )

                    if not should_enqueue:
                        # Hook indicates we should skip enqueue (e.g., breakpoint hit)
                        if reason:
                            logger.info(f"Skipping slot enqueue: {reason}")
                        continue

                # Enqueue data to slot (non-blocking, may raise SlotQueueFullError)
                slot.enqueue(
                    data=data,
                    emitted_from=emitted_from,
                    emitted_at=emitted_at,
                )

                # Trigger routine activation check
                # This may execute the routine's logic() if activation policy allows
                routine = slot.routine
                if routine is not None:
                    self._check_routine_activation(routine, worker_state)

            except SlotQueueFullError as e:
                # Step 6: Handle backpressure (slot queue full)
                logger.warning(f"Slot queue full, dropping event: {e}")
            except Exception as e:
                # Step 7: Handle other errors
                logger.exception(f"Error routing event to slot: {e}")

    def _check_routine_activation(self, routine: Routine, worker_state: WorkerState) -> None:
        """Check if routine should be activated based on its policy.

        This method checks the activation policy and if activation is needed,
        creates SlotActivationTask(s) for each slot with data and submits them
        to the WorkerExecutor. This ensures proper context binding and thread
        execution.

        Args:
            routine: Routine to check
            worker_state: WorkerState for this execution
        """
        activation_policy = getattr(routine, "_activation_policy", None)
        if activation_policy is None:
            return

        # Get logic - try _logic attribute first, then check for logic method
        logic = getattr(routine, "_logic", None)
        if logic is None:
            # Check if routine has a logic method defined
            if hasattr(routine, "logic") and callable(getattr(routine, "logic", None)):
                logic = routine.logic
            else:
                return

        try:
            # Call activation policy
            should_activate, data_slice, policy_message = activation_policy(
                routine.slots, worker_state
            )

            if not should_activate:
                return

            # Get routine ID from execution context
            from routilux.core.context import get_current_execution_context

            ctx = get_current_execution_context()
            routine_id = ctx.routine_id if ctx else None
            flow = ctx.flow if ctx else None

            # Get job context from current context (should be set by EventRoutingTask)
            from routilux.core.context import get_current_job
            from routilux.core.hooks import get_execution_hooks

            job_context = get_current_job()

            # Call routine start hook
            hooks = get_execution_hooks()
            if routine_id:
                should_continue = hooks.on_routine_start(routine_id, worker_state, job_context)
                if not should_continue:
                    return

            # Execute logic directly in this thread (we're already in WorkerExecutor's event loop)
            # This ensures job_context is already bound from EventRoutingTask processing
            try:
                # Set runtime context on routine for emit() to work
                # NOTE: No longer set routine._current_runtime
                # Runtime is now accessible via worker_state._runtime

                # Prepare arguments
                slot_data_lists = []
                for slot_name in routine.slots.keys():
                    slot_data = data_slice.get(slot_name, [])
                    slot_data_lists.append(slot_data)

                # Call logic function
                logic(
                    *slot_data_lists,
                    policy_message=policy_message,
                    worker_state=worker_state,
                )

                # Record execution
                if routine_id:
                    worker_state.record_execution(
                        routine_id, "logic_executed", {"policy_message": str(policy_message)}
                    )
                    hooks.on_routine_end(routine_id, worker_state, job_context)

            except Exception as e:
                logger.exception(f"Error in routine logic: {e}")
                if routine_id:
                    worker_state.record_execution(routine_id, "logic_error", {"error": str(e)})
                    hooks.on_routine_end(routine_id, worker_state, job_context, "failed", e)

                # Handle error via error handler
                if routine_id and flow:
                    error_handler = flow._get_error_handler_for_routine(routine, routine_id)
                    if error_handler:
                        error_handler.handle_error(e, routine, routine_id, flow, worker_state)

        except Exception as e:
            logger.exception(f"Error checking routine activation: {e}")

    def _get_routine_id(self, routine: Routine | None, worker_state: WorkerState) -> str | None:
        """Get routine ID from worker's flow.

        Args:
            routine: Routine object
            worker_state: WorkerState for this execution

        Returns:
            Routine ID if found, None otherwise
        """
        if routine is None:
            return None

        from routilux.core.registry import FlowRegistry

        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get(worker_state.flow_id)
        if flow:
            return flow._get_routine_id(routine)
        return None

    def get_job(self, job_id: str) -> JobContext | None:
        """Get job by ID.

        Args:
            job_id: Job identifier

        Returns:
            JobContext if found, None otherwise
        """
        with self._jobs_lock:
            for worker_jobs in self._active_jobs.values():
                if job_id in worker_jobs:
                    return worker_jobs[job_id]
        return None

    def complete_job(
        self, job_id: str, status: str = "completed", error: str | None = None
    ) -> bool:
        """Mark a job as completed.

        Args:
            job_id: Job identifier
            status: Final status
            error: Error message if failed

        Returns:
            True if job was found and completed, False otherwise
        """
        # Acquire locks in correct order: _worker_lock -> _jobs_lock
        # This prevents deadlock when combined with other methods
        with self._worker_lock:
            with self._jobs_lock:
                for worker_id, worker_jobs in self._active_jobs.items():
                    if job_id in worker_jobs:
                        job = worker_jobs[job_id]
                        job.complete(status, error)

                        # Increment worker counter - safe to access _active_workers
                        # since we hold _worker_lock
                        worker = self._active_workers.get(worker_id)
                        if worker:
                            worker.increment_jobs_processed(status == "completed")

                        # Clear job output after completion (optional)
                        from routilux.core.output import clear_job_output

                        clear_job_output(job_id)

                        # Remove job from active jobs to prevent memory leak
                        del worker_jobs[job_id]

                        return True
        return False

    def list_jobs(self, worker_id: str | None = None) -> list[JobContext]:
        """List active jobs.

        Args:
            worker_id: Optional filter by worker

        Returns:
            List of JobContext objects
        """
        with self._jobs_lock:
            if worker_id:
                worker_jobs = self._active_jobs.get(worker_id, {})
                return list(worker_jobs.values())
            else:
                all_jobs = []
                for worker_jobs in self._active_jobs.values():
                    all_jobs.extend(worker_jobs.values())
                return all_jobs

    def shutdown(self, wait: bool = True, timeout: float = 30.0) -> None:
        """Shutdown the Runtime.

        Args:
            wait: Whether to wait for completion
            timeout: Timeout for waiting
        """
        self._shutdown = True
        self._is_shutdown = True

        # Cancel all active workers first
        with self._worker_lock:
            workers_to_stop = list(self._active_workers.items())

        for worker_id, worker_state in workers_to_stop:
            try:
                executor = getattr(worker_state, "_executor", None)
                if executor is not None:
                    executor.cancel(reason="Runtime shutdown")
            except Exception as e:
                logger.warning(f"Error cancelling worker {worker_id}: {e}")

        if self.thread_pool is not None:
            try:
                self.thread_pool.shutdown(wait=wait)
            except Exception as e:
                logger.warning(f"Error shutting down thread pool: {e}")

        # Clear active workers
        with self._worker_lock:
            self._active_workers.clear()

        # Clear active jobs
        with self._jobs_lock:
            self._active_jobs.clear()

    def wait_until_all_workers_idle(
        self, timeout: float | None = None, check_interval: float = 0.1
    ) -> bool:
        """Wait until all workers are idle.

        Args:
            timeout: Maximum wait time in seconds. None means wait indefinitely (not recommended).
                Default is 300 seconds (5 minutes).
            check_interval: Time between status checks in seconds (default: 0.1).

        Returns:
            True if all workers idle, False if timeout

        Note:
            If timeout is None, this method will wait indefinitely.
            Use with caution as it may block forever if workers never become idle.
        """
        if timeout is None:
            timeout = 300.0  # Default 5 minutes
        elif timeout <= 0:
            raise ValueError(f"timeout must be positive or None, got {timeout}")

        start_time = time.time()
        while time.time() - start_time < timeout:
            with self._worker_lock:
                all_idle = all(
                    worker.status == ExecutionStatus.IDLE
                    for worker in self._active_workers.values()
                )
                if all_idle:
                    return True
            time.sleep(check_interval)
        return False
