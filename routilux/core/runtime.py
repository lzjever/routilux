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
from typing import TYPE_CHECKING, Any, Dict, Optional, Set, Tuple

if TYPE_CHECKING:
    from routilux.core.event import Event
    from routilux.core.flow import Flow
    from routilux.core.routine import Routine
    from routilux.core.worker import WorkerState

from routilux.core.context import JobContext, set_current_job
from routilux.core.slot import SlotQueueFullError
from routilux.core.status import ExecutionStatus

logger = logging.getLogger(__name__)


class Runtime:
    """Centralized execution manager for workflow execution.

    The Runtime manages all workflow executions with a shared thread pool,
    provides worker tracking, and handles event routing.

    Key Features:
        - Thread pool management (shared across all workers)
        - Worker registry (thread-safe tracking of active workers)
        - Non-blocking execution (exec() returns immediately)
        - Event routing (routes events to connected slots)
        - Routine activation checking (calls activation policies)
        - Job context binding (for per-task tracking)

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
            logger.warning(
                f"thread_pool_size {thread_pool_size} is unusually large"
            )

        self.thread_pool_size = thread_pool_size
        if thread_pool_size == 0:
            self.thread_pool: Optional[ThreadPoolExecutor] = None
        else:
            self.thread_pool = ThreadPoolExecutor(
                max_workers=thread_pool_size, thread_name_prefix="RoutiluxWorker"
            )

        self._active_workers: Dict[str, "WorkerState"] = {}
        self._worker_lock = threading.RLock()
        self._shutdown = False
        self._is_shutdown = False

        # Track active routines: worker_id -> set[routine_id]
        self._active_routines: Dict[str, Set[str]] = {}
        self._active_routines_lock = threading.RLock()

        # Track active jobs by worker: worker_id -> dict[job_id -> JobContext]
        self._active_jobs: Dict[str, Dict[str, JobContext]] = {}
        self._jobs_lock = threading.RLock()

    def __del__(self) -> None:
        """Cleanup thread pool when Runtime is garbage collected."""
        if not self._is_shutdown and getattr(self, "thread_pool", None) is not None:
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
        self, flow_name: str, worker_state: Optional["WorkerState"] = None
    ) -> "WorkerState":
        """Execute a flow and return immediately.

        This method starts flow execution in the background and returns
        immediately with a WorkerState that can be used to track progress.

        Args:
            flow_name: Name of the flow to execute (must be registered)
            worker_state: Optional existing WorkerState (for resuming)

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

            worker_state = WorkerState(flow_id=flow.flow_id)
        else:
            if worker_state.flow_id != flow.flow_id:
                raise ValueError(
                    f"WorkerState flow_id ({worker_state.flow_id}) does not match"
                )

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

        # Register in active workers
        with self._worker_lock:
            self._active_workers[worker_state.worker_id] = worker_state

        # Initialize jobs dict for this worker
        with self._jobs_lock:
            self._active_jobs[worker_state.worker_id] = {}

        return worker_state

    def post(
        self,
        flow_name: str,
        routine_name: str,
        slot_name: str,
        data: Dict[str, Any],
        worker_id: Optional[str] = None,
        job_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple["WorkerState", JobContext]:
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
            metadata=metadata or {},
        )
        job_context.start()

        # Register job
        with self._jobs_lock:
            if worker_state.worker_id not in self._active_jobs:
                self._active_jobs[worker_state.worker_id] = {}
            self._active_jobs[worker_state.worker_id][job_context.job_id] = job_context

        # Get routine and slot
        if routine_name not in flow.routines:
            raise ValueError(f"Routine '{routine_name}' not found in flow")
        routine = flow.routines[routine_name]
        slot = routine.get_slot(slot_name)
        if slot is None:
            raise ValueError(
                f"Slot '{slot_name}' not found in routine '{routine_name}'"
            )

        # Get WorkerExecutor
        worker_executor = getattr(worker_state, "_executor", None)
        if worker_executor is None:
            raise RuntimeError(
                f"WorkerExecutor not found for worker {worker_state.worker_id}"
            )

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
        event: "Event",
        event_data: Dict[str, Any],
        worker_state: "WorkerState",
    ) -> None:
        """Handle event emission and route to connected slots.

        This method routes event data to all connected slots.

        Args:
            event: Event that was emitted
            event_data: Event data with "data" and "metadata" keys
            worker_state: WorkerState for this execution
        """
        from routilux.core.hooks import get_execution_hooks
        from routilux.core.registry import FlowRegistry

        # Get flow to find connections
        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get(worker_state.flow_id)
        if flow is None:
            logger.warning(f"Flow {worker_state.flow_id} not found, cannot route event")
            return

        # Find connections for this event
        connections = flow.get_connections_for_event(event)
        if not connections:
            return  # No consumers - normal case

        # Track event emission
        source_routine_id = self._get_routine_id(event.routine, worker_state)
        hooks = get_execution_hooks()

        if source_routine_id:
            data = event_data.get("data", {}) if isinstance(event_data, dict) else {}
            worker_state.record_execution(
                source_routine_id,
                "event_emit",
                {"event_name": event.name, "data": data},
            )

            # Get job context
            from routilux.core.context import get_current_job

            job_context = get_current_job()

            should_continue = hooks.on_event_emit(
                event, source_routine_id, worker_state, job_context, data
            )
            if not should_continue:
                return

        # Route to all connected slots
        for connection in connections:
            slot = connection.target_slot
            if slot is None:
                continue

            try:
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

                slot.enqueue(
                    data=data,
                    emitted_from=emitted_from,
                    emitted_at=emitted_at,
                )

                # Trigger routine activation check
                routine = slot.routine
                if routine is not None:
                    self._check_routine_activation(routine, worker_state)

            except SlotQueueFullError as e:
                logger.warning(
                    f"Slot queue full, dropping event: {e}"
                )
            except Exception as e:
                logger.exception(f"Error routing event to slot: {e}")

    def _check_routine_activation(
        self, routine: "Routine", worker_state: "WorkerState"
    ) -> None:
        """Check if routine should be activated based on its policy.

        Args:
            routine: Routine to check
            worker_state: WorkerState for this execution
        """
        from routilux.core.hooks import get_execution_hooks

        activation_policy = getattr(routine, "_activation_policy", None)
        if activation_policy is None:
            return

        logic = getattr(routine, "_logic", None)
        if logic is None:
            return

        try:
            # Call activation policy
            should_activate, data_slice, policy_message = activation_policy(
                routine.slots, worker_state
            )

            if not should_activate:
                return

            # Get routine ID
            flow = getattr(routine, "_current_flow", None)
            routine_id = flow._get_routine_id(routine) if flow else None

            # Call routine start hook
            hooks = get_execution_hooks()
            from routilux.core.context import get_current_job

            job_context = get_current_job()

            if routine_id:
                should_continue = hooks.on_routine_start(
                    routine_id, worker_state, job_context
                )
                if not should_continue:
                    return

            # Execute logic
            try:
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
                    worker_state.record_execution(
                        routine_id, "logic_error", {"error": str(e)}
                    )
                    hooks.on_routine_end(
                        routine_id, worker_state, job_context, "failed", e
                    )

                # Handle error via error handler
                if routine_id and flow:
                    error_handler = flow._get_error_handler_for_routine(
                        routine, routine_id
                    )
                    if error_handler:
                        error_handler.handle_error(
                            e, routine, routine_id, flow, worker_state
                        )

        except Exception as e:
            logger.exception(f"Error checking routine activation: {e}")

    def _get_routine_id(
        self, routine: Optional["Routine"], worker_state: "WorkerState"
    ) -> Optional[str]:
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

    def get_job(self, job_id: str) -> Optional[JobContext]:
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
        self, job_id: str, status: str = "completed", error: Optional[str] = None
    ) -> bool:
        """Mark a job as completed.

        Args:
            job_id: Job identifier
            status: Final status
            error: Error message if failed

        Returns:
            True if job was found and completed, False otherwise
        """
        with self._jobs_lock:
            for worker_id, worker_jobs in self._active_jobs.items():
                if job_id in worker_jobs:
                    job = worker_jobs[job_id]
                    job.complete(status, error)

                    # Increment worker counter
                    worker = self._active_workers.get(worker_id)
                    if worker:
                        worker.increment_jobs_processed(status == "completed")

                    # Clear job output after completion (optional)
                    from routilux.core.output import clear_job_output

                    clear_job_output(job_id)

                    return True
        return False

    def list_jobs(self, worker_id: Optional[str] = None) -> list[JobContext]:
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

    def wait_until_all_workers_idle(self, timeout: float = 300.0) -> bool:
        """Wait until all workers are idle.

        Args:
            timeout: Maximum wait time in seconds

        Returns:
            True if all workers idle, False if timeout
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self._worker_lock:
                all_idle = all(
                    worker.status == ExecutionStatus.IDLE
                    for worker in self._active_workers.values()
                )
                if all_idle:
                    return True
            time.sleep(0.1)
        return False
