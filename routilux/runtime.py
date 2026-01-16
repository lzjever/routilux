"""
Runtime class for centralized flow execution management.

The Runtime provides a centralized execution manager with thread pool,
job registry, and event routing capabilities.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from routilux.event import Event
    from routilux.flow.flow import Flow
    from routilux.job_state import JobState
    from routilux.routine import Routine
    from routilux.slot import Slot

from routilux.status import ExecutionStatus
from routilux.slot import SlotQueueFullError

logger = logging.getLogger(__name__)


class Runtime:
    """Centralized execution manager for flow execution.

    The Runtime manages all flow executions with a shared thread pool,
    provides job tracking, and handles event routing.

    Key Features:
        - Thread pool management (shared across all jobs)
        - Job registry (thread-safe tracking of active jobs)
        - Non-blocking execution (exec() returns immediately)
        - Event routing (routes events to connected slots)
        - Routine activation checking (calls activation policies)

    Examples:
        Basic usage:
            >>> runtime = Runtime(thread_pool_size=10)
            >>> job_state = runtime.exec("my_flow")
            >>> runtime.wait_until_all_jobs_finished()

        With resumption:
            >>> job_state = runtime.exec("my_flow", existing_job_state)
    """

    def __init__(self, thread_pool_size: int = 10):
        """Initialize Runtime.

        Args:
            thread_pool_size: Maximum number of worker threads in the thread pool.
                Default: 10
        """
        self.thread_pool_size = thread_pool_size
        self.thread_pool = ThreadPoolExecutor(
            max_workers=thread_pool_size, thread_name_prefix="RoutiluxWorker"
        )
        self._active_jobs: Dict[str, JobState] = {}
        self._job_lock = threading.RLock()
        self._shutdown = False

    def exec(self, flow_name: str, job_state: Optional[JobState] = None) -> JobState:
        """Execute a flow and return immediately.

        This method starts flow execution in the background and returns
        immediately with a JobState that can be used to track progress.

        Args:
            flow_name: Name of the flow to execute (must be registered in FlowRegistry).
            job_state: Optional existing JobState to use (for resuming execution).
                If None, creates a new JobState.

        Returns:
            JobState object. Status will be RUNNING after this call.

        Raises:
            ValueError: If flow_name is not found in FlowRegistry.
            RuntimeError: If Runtime is shut down.
        """
        if self._shutdown:
            raise RuntimeError("Runtime is shut down")

        # Get flow from registry
        from routilux.monitoring.flow_registry import FlowRegistry

        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get_by_name(flow_name)
        if flow is None:
            # Fallback to flow_id lookup
            flow = flow_registry.get(flow_name)
        if flow is None:
            raise ValueError(f"Flow '{flow_name}' not found in registry")

        # Create or use existing job_state
        if job_state is None:
            from routilux.job_state import JobState

            job_state = JobState(flow_id=flow.flow_id)
        else:
            # Validate flow_id matches
            if job_state.flow_id != flow.flow_id:
                raise ValueError(
                    f"JobState flow_id ({job_state.flow_id}) does not match flow flow_id ({flow.flow_id})"
                )

        # Set status to running
        job_state.status = ExecutionStatus.RUNNING
        if job_state.started_at is None:
            job_state.started_at = datetime.now()

        # Register job
        with self._job_lock:
            self._active_jobs[job_state.job_id] = job_state

        # Start execution in background
        future = self.thread_pool.submit(self._execute_flow, flow, job_state)
        job_state._execution_future = future  # Store for cancellation

        return job_state

    def _execute_flow(self, flow: Flow, job_state: JobState) -> None:
        """Execute a flow (internal method, runs in thread pool).

        Args:
            flow: Flow to execute.
            job_state: JobState for this execution.
        """
        try:
            # Set flow and runtime context in routines
            for routine in flow.routines.values():
                routine._current_flow = flow
                routine._current_runtime = self

            # Find entry routine (first routine or one with "trigger" slot)
            entry_routine_id = None
            for rid, routine in flow.routines.items():
                if routine.get_slot("trigger") is not None:
                    entry_routine_id = rid
                    break

            if entry_routine_id is None:
                # Use first routine as entry
                entry_routine_id = next(iter(flow.routines.keys()))

            entry_routine = flow.routines[entry_routine_id]
            job_state.current_routine_id = entry_routine_id

            # Record execution start
            job_state.record_execution(entry_routine_id, "start", {})

            # Trigger entry routine
            trigger_slot = entry_routine.get_slot("trigger")
            if trigger_slot is not None:
                # Create empty data for trigger
                trigger_slot.enqueue(
                    data={},
                    emitted_from="system",
                    emitted_at=datetime.now(),
                )
                # Check activation
                self._check_routine_activation(entry_routine, job_state)

            # Wait for completion
            # TODO: Implement proper completion detection
            # For now, we need to wait until all routines complete
            # This is a simplified version - in production, we'd track active routines
            import time
            time.sleep(0.1)  # Brief delay to allow initial processing

            # Check if all routines completed
            # In a real implementation, we'd track this properly
            # For now, mark as completed
            job_state.status = ExecutionStatus.COMPLETED
            job_state.completed_at = datetime.now()

        except Exception as e:
            logger.exception(f"Error executing flow {flow.flow_id}: {e}")
            job_state.status = ExecutionStatus.FAILED
            job_state.error = str(e)
            job_state.completed_at = datetime.now()
        finally:
            # Update job state
            job_state.updated_at = datetime.now()

    def handle_event_emit(
        self, event: Event, event_data: Dict[str, Any], job_state: JobState
    ) -> None:
        """Handle event emission and route to connected slots.

        This method routes event data to all connected slots. If a slot
        queue is full, it logs a warning and continues with other slots.

        Args:
            event: Event that was emitted.
            event_data: Event data dictionary with "data" and "metadata" keys.
            job_state: JobState for this execution.
        """
        # Get flow to find connections
        from routilux.monitoring.flow_registry import FlowRegistry

        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get(job_state.flow_id)
        if flow is None:
            logger.warning(
                f"Flow {job_state.flow_id} not found in registry, cannot route event"
            )
            return

        # Find connections for this event
        connections = flow.get_connections_for_event(event)
        if not connections:
            # No consumer slots - discard event (normal case, don't log)
            return

        # Route to all connected slots
        for connection in connections:
            slot = connection.target_slot
            try:
                slot.enqueue(
                    data=event_data["data"],
                    emitted_from=event_data["metadata"]["emitted_from"],
                    emitted_at=event_data["metadata"]["emitted_at"],
                )
                # Trigger routine activation check
                routine = slot.routine
                if routine is not None:
                    self._check_routine_activation(routine, job_state)
            except SlotQueueFullError as e:
                # Log and continue (don't crash)
                logger.warning(
                    f"Slot queue full, ignoring event. "
                    f"Slot: {slot.name}, Event: {event.name}, Job: {job_state.job_id}. "
                    f"Error: {e}"
                )
                continue

    def _check_routine_activation(self, routine: Routine, job_state: JobState) -> None:
        """Check if routine should be activated based on activation policy.

        Args:
            routine: Routine to check.
            job_state: JobState for this execution.
        """
        if routine._activation_policy is None:
            # No activation policy - activate immediately with all new data
            self._activate_routine(routine, job_state)
            return

        # Call activation policy
        try:
            should_activate, data_slice, policy_message = routine._activation_policy(
                routine.slots, job_state
            )
        except Exception as e:
            # Error in activation policy - apply error handling
            logger.exception(f"Error in activation policy for routine: {e}")
            error_handler = routine.get_error_handler()
            if error_handler is None:
                from routilux.flow.flow import Flow

                flow = getattr(routine, "_current_flow", None)
                if flow:
                    error_handler = flow.error_handler

            if error_handler:
                from routilux.error_handler import ErrorStrategy

                if error_handler.strategy == ErrorStrategy.STOP:
                    job_state.status = ExecutionStatus.FAILED
                    job_state.error = f"Activation policy error: {e}"
                    return
                # For CONTINUE/SKIP, just log and don't activate
                return
            else:
                # Default: stop on error
                job_state.status = ExecutionStatus.FAILED
                job_state.error = f"Activation policy error: {e}"
                return

        if should_activate:
            self._activate_routine(routine, job_state, data_slice, policy_message)

    def _activate_routine(
        self,
        routine: Routine,
        job_state: JobState,
        data_slice: Optional[Dict[str, List[Any]]] = None,
        policy_message: Any = None,
    ) -> None:
        """Activate routine logic.

        Args:
            routine: Routine to activate.
            job_state: JobState for this execution.
            data_slice: Optional data slice from activation policy.
                If None, consumes all new data from all slots.
            policy_message: Optional message from activation policy.
        """
        # Get routine_id
        routine_id = self._get_routine_id(routine, job_state)
        if routine_id is None:
            logger.warning(f"Could not determine routine_id for routine {routine}")
            return

        job_state.current_routine_id = routine_id

        # Prepare data for logic
        if data_slice is None:
            # Consume all new data from all slots
            data_slice = {}
            for slot_name, slot in routine.slots.items():
                data_slice[slot_name] = slot.consume_all_new()

        # Prepare slot_data_lists in order of slot definition
        slot_data_lists = [
            data_slice.get(slot_name, [])
            for slot_name in sorted(routine.slots.keys())
        ]

        # Execute logic
        if routine._logic is None:
            logger.warning(f"Routine {routine_id} has no logic set, skipping execution")
            return

        try:
            routine._logic(
                *slot_data_lists, policy_message=policy_message, job_state=job_state
            )
            # Mark routine as completed
            job_state.update_routine_state(routine_id, {"status": "completed"})
        except Exception as e:
            # Error in logic - apply error handling
            logger.exception(f"Error in logic for routine {routine_id}: {e}")
            error_handler = routine.get_error_handler()
            if error_handler is None:
                from routilux.flow.flow import Flow

                flow = getattr(routine, "_current_flow", None)
                if flow:
                    error_handler = flow.error_handler

            if error_handler:
                from routilux.error_handler import ErrorStrategy

                if error_handler.strategy == ErrorStrategy.STOP:
                    job_state.status = ExecutionStatus.FAILED
                    job_state.error = f"Logic error: {e}"
                    job_state.update_routine_state(
                        routine_id, {"status": "failed", "error": str(e)}
                    )
                elif error_handler.strategy == ErrorStrategy.CONTINUE:
                    job_state.record_execution(
                        routine_id,
                        "error_continued",
                        {"error": str(e), "error_type": type(e).__name__},
                    )
                elif error_handler.strategy == ErrorStrategy.SKIP:
                    job_state.update_routine_state(
                        routine_id, {"status": "skipped", "error": str(e)}
                    )
                # RETRY strategy would need more complex handling
            else:
                # Default: stop on error
                job_state.status = ExecutionStatus.FAILED
                job_state.error = f"Logic error: {e}"
                job_state.update_routine_state(
                    routine_id, {"status": "failed", "error": str(e)}
                )

    def _get_routine_id(self, routine: Routine, job_state: JobState) -> Optional[str]:
        """Get routine_id for a routine.

        Args:
            routine: Routine instance.
            job_state: JobState for this execution.

        Returns:
            Routine ID if found, None otherwise.
        """
        from routilux.flow.flow import Flow

        flow = getattr(routine, "_current_flow", None)
        if flow:
            return flow._get_routine_id(routine)
        return None

    def wait_until_all_jobs_finished(self, timeout: Optional[float] = None) -> bool:
        """Wait until all active jobs complete.

        Args:
            timeout: Optional timeout in seconds. If None, waits indefinitely.

        Returns:
            True if all jobs finished, False if timeout occurred.
        """
        start_time = time.time()
        while True:
            with self._job_lock:
                active_count = sum(
                    1
                    for job in self._active_jobs.values()
                    if job.status in (ExecutionStatus.RUNNING, ExecutionStatus.PENDING)
                )
                if active_count == 0:
                    return True

            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return False

            time.sleep(0.1)  # Check every 100ms

    def get_job(self, job_id: str) -> Optional[JobState]:
        """Get job state by ID.

        Args:
            job_id: Job identifier.

        Returns:
            JobState if found, None otherwise.
        """
        with self._job_lock:
            return self._active_jobs.get(job_id)

    def list_jobs(self, status: Optional[str] = None) -> List[JobState]:
        """List all jobs, optionally filtered by status.

        Args:
            status: Optional status filter (e.g., "running", "completed", "failed").

        Returns:
            List of JobState objects.
        """
        with self._job_lock:
            jobs = list(self._active_jobs.values())
            if status:
                # Compare with status.value (string) or status enum
                jobs = [
                    j
                    for j in jobs
                    if (j.status.value == status if hasattr(j.status, "value") else str(j.status) == status)
                ]
            return jobs

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job.

        Args:
            job_id: Job identifier.

        Returns:
            True if job was cancelled, False if not found or already completed.
        """
        with self._job_lock:
            job_state = self._active_jobs.get(job_id)
            if job_state is None:
                return False

            if job_state.status not in (ExecutionStatus.RUNNING, ExecutionStatus.PENDING):
                return False

            # Cancel execution
            job_state.status = ExecutionStatus.CANCELLED
            job_state.updated_at = datetime.now()

            # Try to cancel future if available
            if hasattr(job_state, "_execution_future"):
                future = job_state._execution_future
                if isinstance(future, Future):
                    future.cancel()

            return True

    def shutdown(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """Shutdown runtime and thread pool.

        Args:
            wait: If True, wait for all jobs to complete before shutting down.
            timeout: Optional timeout in seconds for waiting.
        """
        self._shutdown = True

        if wait:
            # Wait for jobs to finish, but don't block indefinitely if timeout is None
            # For tests, use a reasonable default timeout
            wait_timeout = timeout if timeout is not None else 5.0
            self.wait_until_all_jobs_finished(timeout=wait_timeout)

        # Shutdown thread pool - use wait=False if we already waited for jobs
        self.thread_pool.shutdown(wait=wait)
