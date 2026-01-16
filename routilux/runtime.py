"""
Runtime class for centralized flow execution management.

The Runtime provides a centralized execution manager with thread pool,
job registry, and event routing capabilities.
"""

from __future__ import annotations

import logging
import threading
import time
import warnings
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Set

if TYPE_CHECKING:
    from routilux.event import Event
    from routilux.flow.flow import Flow
    from routilux.job_state import JobState
    from routilux.routine import Routine

from routilux.slot import SlotQueueFullError
from routilux.status import ExecutionStatus

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

        Raises:
            ValueError: If thread_pool_size is less than 1.
        """
        # MEDIUM fix: Validate thread_pool_size parameter
        if thread_pool_size < 1:
            raise ValueError(f"thread_pool_size must be at least 1, got {thread_pool_size}")
        if thread_pool_size > 1000:
            import logging
            logging.getLogger(__name__).warning(
                f"thread_pool_size {thread_pool_size} is unusually large, may cause resource issues"
            )

        self.thread_pool_size = thread_pool_size
        self.thread_pool = ThreadPoolExecutor(
            max_workers=thread_pool_size, thread_name_prefix="RoutiluxWorker"
        )
        self._active_jobs: dict[str, JobState] = {}
        self._job_lock = threading.RLock()
        self._shutdown = False
        # Critical fix: Track if thread pool is shutdown to prevent double-shutdown
        self._is_shutdown = False
        # Track active routines for monitoring: job_id -> set[routine_id]
        self._active_routines: Dict[str, Set[str]] = {}
        self._active_routines_lock = threading.RLock()

    def __del__(self) -> None:
        """Cleanup thread pool when Runtime is garbage collected.

        Critical fix: Prevent thread pool leaks when Runtime objects are not
        explicitly cleaned up with shutdown().
        """
        # Shutdown thread pool if not already shutdown
        # Use wait=False to avoid blocking during garbage collection
        if not self._is_shutdown and hasattr(self, "thread_pool"):
            try:
                self.thread_pool.shutdown(wait=False)
            except Exception:
                # Ignore exceptions during garbage collection
                pass

    def __enter__(self):
        """Context manager entry.

        Returns:
            Self for use in with statements.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit.

        Ensures thread pool is properly cleaned up.

        Args:
            exc_type: Exception type if an exception was raised.
            exc_val: Exception value if an exception was raised.
            exc_tb: Exception traceback if an exception was raised.
        """
        self.shutdown(wait=True)
        return False

    def exec(self, flow_name: str, job_state: JobState | None = None) -> JobState:
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
        # Import hooks at method level to avoid circular imports
        from routilux.monitoring.hooks import execution_hooks

        try:
            # Call flow start hook
            execution_hooks.on_flow_start(flow, job_state)

            # Set flow and runtime context in routines and job_state
            for routine in flow.routines.values():
                routine._current_flow = flow
                routine._current_runtime = self
            # Also set on job_state for access in logic functions
            job_state._current_runtime = self
            job_state._current_flow = flow

            # Find entry routine (first routine or one with "trigger" slot)
            # Check if entry_routine_id was specified in job_state
            entry_routine_id = job_state.shared_data.get("entry_routine_id")
            if entry_routine_id and entry_routine_id in flow.routines:
                # Use specified entry routine
                pass
            else:
                # Auto-detect entry routine
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
                # Get entry_params from job_state if available
                entry_params = job_state.shared_data.get("entry_params", {})
                # Create data for trigger
                trigger_slot.enqueue(
                    data=entry_params,
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

            # Check if job failed due to routine error (set by error handler)
            # Only mark as completed if status is still RUNNING
            if job_state.status == ExecutionStatus.RUNNING:
                # Check if all routines completed
                # In a real implementation, we'd track this properly
                # For now, mark as completed
                job_state.status = ExecutionStatus.COMPLETED
                job_state.completed_at = datetime.now()
            # If status is already FAILED (set by error handler), don't override it

        except Exception as e:
            logger.exception(f"Error executing flow {flow.flow_id}: {e}")
            job_state.status = ExecutionStatus.FAILED
            job_state.error = str(e)
            job_state.completed_at = datetime.now()
        finally:
            # Call flow end hook
            status = (
                job_state.status.value
                if hasattr(job_state.status, "value")
                else str(job_state.status)
            )
            execution_hooks.on_flow_end(flow, job_state, status=status)

            # Update job state
            job_state.updated_at = datetime.now()
            # Cleanup from active jobs to prevent memory leak
            with self._job_lock:
                self._active_jobs.pop(job_state.job_id, None)

    def handle_event_emit(
        self, event: Event, event_data: dict[str, Any], job_state: JobState
    ) -> None:
        """Handle event emission and route to connected slots.

        This method routes event data to all connected slots. If a slot
        queue is full, it logs a warning and continues with other slots.

        Args:
            event: Event that was emitted.
            event_data: Event data dictionary with "data" and "metadata" keys.
            job_state: JobState for this execution.
        """
        # Import hooks at method level to avoid circular imports
        from routilux.monitoring.hooks import execution_hooks

        # Get flow to find connections
        from routilux.monitoring.flow_registry import FlowRegistry

        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get(job_state.flow_id)
        if flow is None:
            logger.warning(f"Flow {job_state.flow_id} not found in registry, cannot route event")
            return

        # Find connections for this event
        connections = flow.get_connections_for_event(event)
        if not connections:
            # No consumer slots - discard event (normal case, don't log)
            return

        # Track event emission
        source_routine_id = self._get_routine_id(event.routine, job_state)
        if source_routine_id:
            # Extract data for hook
            data = event_data.get("data", {}) if isinstance(event_data, dict) else {}
            # Record event emission
            job_state.record_execution(
                source_routine_id,
                "event_emit",
                {"event_name": event.name, "data": data},
            )
            should_continue = execution_hooks.on_event_emit(
                event, source_routine_id, job_state, data=data
            )
            if not should_continue:
                # Breakpoint hit, don't route
                return

        # Route to all connected slots
        for connection in connections:
            slot = connection.target_slot
            if slot is None:
                continue
            try:
                # HIGH fix: Validate event_data structure before accessing
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

                # Get source and target routine IDs for connection breakpoint checking
                source_routine_id = self._get_routine_id(event.routine, job_state)
                target_routine_id = self._get_routine_id(slot.routine, job_state)

                # Check connection breakpoint before enqueueing
                if source_routine_id and target_routine_id:
                    from routilux.monitoring.registry import MonitoringRegistry

                    if MonitoringRegistry.is_enabled():
                        breakpoint_mgr = MonitoringRegistry.get_instance().breakpoint_manager
                        if breakpoint_mgr:
                            breakpoint = breakpoint_mgr.check_breakpoint(
                                job_state.job_id,
                                source_routine_id,  # Use source for connection breakpoint
                                "connection",
                                source_routine_id=source_routine_id,
                                source_event_name=event.name,
                                target_routine_id=target_routine_id,
                                target_slot_name=slot.name,
                                variables=data if isinstance(data, dict) else {"data": data},
                            )
                            if breakpoint:
                                debug_store = MonitoringRegistry.get_instance().debug_session_store
                                if debug_store:
                                    session = debug_store.get_or_create(job_state.job_id)
                                    session.pause(
                                        None,
                                        reason=(
                                            f"Breakpoint at connection "
                                            f"{source_routine_id}.{event.name} -> "
                                            f"{target_routine_id}.{slot.name}"
                                        ),
                                    )
                                    # Notify via event manager
                                    from routilux.monitoring.hooks import _publish_event_via_manager

                                    _publish_event_via_manager(
                                        job_state.job_id,
                                        {
                                            "type": "breakpoint_hit",
                                            "job_id": job_state.job_id,
                                            "breakpoint": {
                                                "breakpoint_id": breakpoint.breakpoint_id,
                                                "type": breakpoint.type,
                                                "source_routine_id": breakpoint.source_routine_id,
                                                "source_event_name": breakpoint.source_event_name,
                                                "target_routine_id": breakpoint.target_routine_id,
                                                "target_slot_name": breakpoint.target_slot_name,
                                            },
                                        },
                                    )
                                    # Don't enqueue data yet - paused at breakpoint
                                    continue

                slot.enqueue(
                    data=data,
                    emitted_from=emitted_from,
                    emitted_at=emitted_at,
                )

                # Track slot data reception
                if target_routine_id:
                    # Record slot data reception
                    job_state.record_execution(
                        target_routine_id,
                        "slot_data_received",
                        {
                            "slot_name": slot.name,
                            "source_routine": source_routine_id,
                            "event_name": event.name,
                        },
                    )
                    should_continue = execution_hooks.on_slot_data_received(
                        slot, target_routine_id, job_state, data=data
                    )
                    if not should_continue:
                        # Breakpoint hit, skip this slot
                        continue

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
        routine_id = self._get_routine_id(routine, job_state)
        if routine_id:
            # Record activation check
            job_state.record_execution(
                routine_id,
                "activation_check",
                {
                    "slot_data_counts": {
                        name: slot.get_unconsumed_count()
                        for name, slot in routine.slots.items()
                    }
                },
            )

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
        data_slice: dict[str, list[Any]] | None = None,
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
        # Import hooks at method level to avoid circular imports
        from routilux.monitoring.hooks import execution_hooks

        # Get routine_id
        routine_id = self._get_routine_id(routine, job_state)
        if routine_id is None:
            logger.warning(f"Could not determine routine_id for routine {routine}")
            return

        job_state.current_routine_id = routine_id

        # Mark routine as active for monitoring
        with self._active_routines_lock:
            if job_state.job_id not in self._active_routines:
                self._active_routines[job_state.job_id] = set()
            self._active_routines[job_state.job_id].add(routine_id)

        # Prepare data for logic
        if data_slice is None:
            # Consume all new data from all slots
            data_slice = {}
            for slot_name, slot in routine.slots.items():
                data_slice[slot_name] = slot.consume_all_new()

        # Record routine start
        job_state.record_execution(
            routine_id,
            "start",
            {
                "slot_data_counts": {name: len(data) for name, data in data_slice.items()},
                "policy_message": policy_message,
            },
        )

        # Call routine start hook
        execution_hooks.on_routine_start(routine, routine_id, job_state)

        # Prepare slot_data_lists in order of slot definition
        slot_data_lists = [
            data_slice.get(slot_name, []) for slot_name in sorted(routine.slots.keys())
        ]

        # Execute logic
        if routine._logic is None:
            logger.warning(f"Routine {routine_id} has no logic set, skipping execution")
            # Call routine end hook even if no logic
            execution_hooks.on_routine_end(routine, routine_id, job_state, status="skipped")
            return

        start_time = time.time()
        status = "completed"
        error = None

        try:
            routine._logic(*slot_data_lists, policy_message=policy_message, job_state=job_state)
            # Mark routine as completed
            job_state.update_routine_state(routine_id, {"status": "completed"})
            # Record completion
            duration = time.time() - start_time
            job_state.record_execution(routine_id, "completed", {"duration": duration})
        except Exception as e:
            # Error in logic - apply error handling
            logger.exception(f"Error in logic for routine {routine_id}: {e}")
            status = "failed"
            error = e
            duration = time.time() - start_time
            error_handler = routine.get_error_handler()
            if error_handler is None:
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
                    job_state.record_execution(
                        routine_id,
                        "error",
                        {
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "duration": duration,
                        },
                    )
                elif error_handler.strategy == ErrorStrategy.CONTINUE:
                    status = "error_continued"
                    job_state.record_execution(
                        routine_id,
                        "error_continued",
                        {
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "duration": duration,
                        },
                    )
                elif error_handler.strategy == ErrorStrategy.SKIP:
                    status = "skipped"
                    job_state.update_routine_state(
                        routine_id, {"status": "skipped", "error": str(e)}
                    )
                    job_state.record_execution(
                        routine_id,
                        "error",
                        {
                            "error": str(e),
                            "error_type": type(e).__name__,
                            "duration": duration,
                        },
                    )
                # RETRY strategy would need more complex handling
            else:
                # Default: stop on error
                job_state.status = ExecutionStatus.FAILED
                job_state.error = f"Logic error: {e}"
                job_state.update_routine_state(routine_id, {"status": "failed", "error": str(e)})
                job_state.record_execution(
                    routine_id,
                    "error",
                    {
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "duration": duration,
                    },
                )
        finally:
            # Mark routine as inactive for monitoring
            with self._active_routines_lock:
                if job_state.job_id in self._active_routines:
                    self._active_routines[job_state.job_id].discard(routine_id)
                    # Clean up empty job entry
                    if not self._active_routines[job_state.job_id]:
                        del self._active_routines[job_state.job_id]
            
            # Call routine end hook
            execution_hooks.on_routine_end(routine, routine_id, job_state, status=status, error=error)

    def _get_routine_id(self, routine: Routine, job_state: JobState) -> str | None:
        """Get routine_id for a routine.

        Args:
            routine: Routine instance.
            job_state: JobState for this execution.

        Returns:
            Routine ID if found, None otherwise.
        """

        flow = getattr(routine, "_current_flow", None)
        if flow:
            return flow._get_routine_id(routine)
        return None

    def get_active_routines(self, job_id: str) -> Set[str]:
        """Get set of routine IDs that are currently executing for a job.

        Args:
            job_id: Job identifier.

        Returns:
            Set of routine IDs that are currently active (executing).
            Returns empty set if job_id not found or no active routines.
        """
        with self._active_routines_lock:
            return self._active_routines.get(job_id, set()).copy()

    def wait_until_all_jobs_finished(self, timeout: float | None = None) -> bool:
        """Wait until all active jobs complete.

        Args:
            timeout: Optional timeout in seconds. If None, uses default of 3600 seconds (1 hour)
                to prevent indefinite waiting.

        Returns:
            True if all jobs finished, False if timeout occurred.
        """
        # Fix: Add default maximum timeout to prevent indefinite waiting
        max_timeout = timeout if timeout is not None else 3600.0
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

            elapsed = time.time() - start_time
            if elapsed >= max_timeout:
                return False

            time.sleep(0.1)  # Check every 100ms

    def get_job(self, job_id: str) -> JobState | None:
        """Get job state by ID.

        Args:
            job_id: Job identifier.

        Returns:
            JobState if found, None otherwise.
        """
        with self._job_lock:
            return self._active_jobs.get(job_id)

    def list_jobs(self, status: str | None = None) -> list[JobState]:
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
                    if (
                        j.status.value == status
                        if hasattr(j.status, "value")
                        else str(j.status) == status
                    )
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

    def shutdown(self, wait: bool = True, timeout: float | None = None) -> None:
        """Shutdown runtime and thread pool.

        Critical fix: Prevents double-shutdown and ensures thread pool cleanup.

        Args:
            wait: If True, wait for all jobs to complete before shutting down.
            timeout: Optional timeout in seconds for waiting.
        """
        # Critical fix: Prevent double-shutdown
        if self._is_shutdown:
            return

        self._shutdown = True

        if wait:
            # Wait for jobs to finish, but don't block indefinitely if timeout is None
            # For tests, use a reasonable default timeout
            wait_timeout = timeout if timeout is not None else 5.0
            self.wait_until_all_jobs_finished(timeout=wait_timeout)

        # Shutdown thread pool - use wait=False if we already waited for jobs
        # Critical fix: Set flag before shutdown to prevent race conditions
        self._is_shutdown = True
        self.thread_pool.shutdown(wait=wait)


# Global Runtime instance for API access
_runtime_instance: Runtime | None = None
_runtime_instance_lock = threading.RLock()


def get_runtime_instance() -> Runtime:
    """Get global Runtime instance for API access.

    This function provides a singleton Runtime instance that can be used
    by API endpoints to access runtime state (e.g., active routines).

    Returns:
        Global Runtime instance.
    """
    global _runtime_instance
    with _runtime_instance_lock:
        if _runtime_instance is None:
            _runtime_instance = Runtime(thread_pool_size=10)
        return _runtime_instance
