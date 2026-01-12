"""
Flow class.

Flow manager responsible for managing multiple Routine nodes and execution flow.
"""

from __future__ import annotations

import queue
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from routilux.connection import Connection
    from routilux.error_handler import ErrorHandler
    from routilux.event import Event
    from routilux.execution_tracker import ExecutionTracker
    from routilux.job_state import JobState
    from routilux.routine import Routine
    from routilux.slot import Slot

from serilux import Serializable, register_serializable

from routilux.flow.task import SlotActivationTask


@register_serializable
class Flow(Serializable):
    """Flow manager for orchestrating workflow execution.

    A Flow is a container that manages multiple Routine nodes and their
    connections, providing workflow orchestration capabilities including
    execution, error handling, state management, and persistence.

    Key Responsibilities:
        - Routine Management: Add, organize, and track routines in the workflow
        - Connection Management: Link routines via events and slots
        - Execution Control: Execute workflows sequentially or concurrently
        - Error Handling: Apply error handling strategies at flow or routine level
        - State Management: Track execution state via JobState
        - Persistence: Serialize and restore flow state for resumption

    Execution Modes:
        - Sequential: Routines execute one at a time in dependency order.
          Suitable for workflows with dependencies or when order matters.
        - Concurrent: Independent routines execute in parallel using threads.
          Suitable for independent operations that can run simultaneously.
          Use max_workers to control parallelism.

    Error Handling:
        Error handlers can be set at two levels:
        1. Flow-level: Default handler for all routines (set_error_handler())
        2. Routine-level: Override for specific routines (routine.set_error_handler())

        Priority: Routine-level > Flow-level > Default (STOP)

    Examples:
        Basic workflow:
            >>> flow = Flow()
            >>> routine1 = DataProcessor()
            >>> routine2 = DataValidator()
            >>> id1 = flow.add_routine(routine1, "processor")
            >>> id2 = flow.add_routine(routine2, "validator")
            >>> flow.connect(id1, "output", id2, "input")
            >>> job_state = flow.execute(id1, entry_params={"data": "test"})

        Concurrent execution:
            >>> flow = Flow(execution_strategy="concurrent", max_workers=5)
            >>> # Add routines and connections...
            >>> job_state = flow.execute(entry_id)
            >>> flow.wait_for_completion()  # Wait for all threads
            >>> flow.shutdown()  # Clean up thread pool

        Error handling:
            >>> from routilux import ErrorHandler, ErrorStrategy
            >>> flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
            >>> # Or set per-routine:
            >>> routine.set_as_critical(max_retries=3)
    """

    def __init__(
        self,
        flow_id: str | None = None,
        execution_strategy: str = "sequential",
        max_workers: int = 5,
        execution_timeout: float | None = None,
    ):
        """Initialize Flow.

        Args:
            flow_id: Flow identifier (auto-generated if None).
            execution_strategy: Execution strategy, "sequential" or "concurrent".
            max_workers: Maximum number of worker threads for concurrent execution.
            execution_timeout: Default timeout for execution completion in seconds.
                None for no timeout (default: 300.0 seconds).
        """
        super().__init__()
        self.flow_id: str = flow_id or str(uuid.uuid4())
        self.routines: dict[str, Routine] = {}
        self.connections: list[Connection] = []
        self._current_flow: Flow | None = None
        self.execution_tracker: ExecutionTracker | None = None
        self.error_handler: ErrorHandler | None = None
        self._paused: bool = False

        self.execution_strategy: str = execution_strategy
        self.max_workers: int = max_workers if execution_strategy == "concurrent" else 1
        self.execution_timeout: float | None = (
            execution_timeout if execution_timeout is not None else 300.0
        )

        self._task_queue: queue.Queue = queue.Queue()
        self._pending_tasks: list[SlotActivationTask] = []

        self._execution_thread: threading.Thread | None = None
        self._execution_lock: threading.Lock = threading.Lock()
        self._running: bool = False

        self._executor: ThreadPoolExecutor | None = None
        self._active_tasks: set[Future] = set()

        self.add_serializable_fields(
            [
                "flow_id",
                "_paused",
                "execution_strategy",
                "max_workers",
                "error_handler",
                "routines",
                "connections",
            ]
        )

        self._event_slot_connections: dict[tuple, Connection] = {}

    def __repr__(self) -> str:
        """Return string representation of the Flow."""
        return f"Flow[{self.flow_id}]"

    def set_execution_strategy(self, strategy: str, max_workers: int | None = None) -> None:
        """Set execution strategy.

        Args:
            strategy: Execution strategy, "sequential" or "concurrent".
            max_workers: Maximum number of worker threads (only effective in concurrent mode).
        """
        if strategy not in ["sequential", "concurrent"]:
            raise ValueError(
                f"Invalid execution strategy: {strategy}. Must be 'sequential' or 'concurrent'"
            )

        self.execution_strategy = strategy
        if strategy == "sequential":
            self.max_workers = 1
        elif max_workers is not None:
            self.max_workers = max_workers
        else:
            self.max_workers = 5

        if self._executor:
            self._executor.shutdown(wait=True)
        self._executor = ThreadPoolExecutor(max_workers=self.max_workers)

    def _get_executor(self) -> ThreadPoolExecutor:
        """Get or create thread pool executor.

        Returns:
            ThreadPoolExecutor instance.
        """
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        return self._executor

    def _get_routine_id(self, routine: Routine) -> str | None:
        """Find the ID of a Routine object within this Flow.

        Args:
            routine: Routine object.

        Returns:
            Routine ID if found, None otherwise.
        """
        for rid, r in self.routines.items():
            if r is routine:
                return rid
        return None

    def _build_dependency_graph(self) -> dict[str, set[str]]:
        """Build routine dependency graph.

        Returns:
            Dependency graph dictionary: {routine_id: {dependent routine_ids}}.
        """
        from routilux.flow.dependency import build_dependency_graph

        return build_dependency_graph(self.routines, self.connections)

    def _get_ready_routines(
        self, completed: set[str], dependency_graph: dict[str, set[str]], running: set[str]
    ) -> list[str]:
        """Get routines ready for execution.

        Args:
            completed: Set of completed routine IDs.
            dependency_graph: Dependency graph.
            running: Set of currently running routine IDs.

        Returns:
            List of routine IDs ready for execution.
        """
        from routilux.flow.dependency import get_ready_routines

        return get_ready_routines(completed, dependency_graph, running)

    def _find_connection(self, event: Event, slot: Slot) -> Connection | None:
        """Find Connection from event to slot.

        Args:
            event: Event object.
            slot: Slot object.

        Returns:
            Connection object if found, None otherwise.
        """
        key = (event, slot)
        return self._event_slot_connections.get(key)

    def _enqueue_task(self, task: SlotActivationTask) -> None:
        """Enqueue a task for execution.

        Args:
            task: SlotActivationTask to enqueue.
        """
        from routilux.flow.event_loop import enqueue_task

        enqueue_task(task, self)

    def _start_event_loop(self) -> None:
        """Start the event loop thread."""
        from routilux.flow.event_loop import start_event_loop

        start_event_loop(self)

    def add_routine(self, routine: Routine, routine_id: str | None = None) -> str:
        """Add a routine to the flow.

        Args:
            routine: Routine instance to add.
            routine_id: Optional unique identifier for this routine in the flow.

        Returns:
            The routine ID used.

        Raises:
            ValueError: If routine_id already exists in the flow.
        """
        rid = routine_id or routine._id
        if rid in self.routines:
            raise ValueError(f"Routine ID '{rid}' already exists in flow")

        self.routines[rid] = routine
        return rid

    def connect(
        self,
        source_routine_id: str,
        source_event: str,
        target_routine_id: str,
        target_slot: str,
        param_mapping: dict[str, str] | None = None,
    ) -> Connection:
        """Connect two routines by linking a source event to a target slot.

        Args:
            source_routine_id: Identifier of the routine that emits the event.
            source_event: Name of the event to connect from.
            target_routine_id: Identifier of the routine that receives the data.
            target_slot: Name of the slot to connect to.
            param_mapping: Optional dictionary mapping event parameter names to
                slot parameter names.

        Returns:
            Connection object representing this connection.

        Raises:
            ValueError: If any of the required components don't exist.
        """
        if source_routine_id not in self.routines:
            raise ValueError(f"Source routine '{source_routine_id}' not found in flow")

        source_routine = self.routines[source_routine_id]
        source_event_obj = source_routine.get_event(source_event)
        if source_event_obj is None:
            raise ValueError(f"Event '{source_event}' not found in routine '{source_routine_id}'")

        if target_routine_id not in self.routines:
            raise ValueError(f"Target routine '{target_routine_id}' not found in flow")

        target_routine = self.routines[target_routine_id]
        target_slot_obj = target_routine.get_slot(target_slot)
        if target_slot_obj is None:
            raise ValueError(f"Slot '{target_slot}' not found in routine '{target_routine_id}'")

        from routilux.connection import Connection

        connection = Connection(source_event_obj, target_slot_obj, param_mapping)
        self.connections.append(connection)

        key = (source_event_obj, target_slot_obj)
        self._event_slot_connections[key] = connection

        return connection

    def set_error_handler(self, error_handler: ErrorHandler) -> None:
        """Set error handler for the flow.

        Args:
            error_handler: ErrorHandler object.
        """
        self.error_handler = error_handler

    def find_routines_by_type(self, routine_type: type) -> list[tuple[str, Routine]]:
        """Find routines by type.

        Args:
            routine_type: Type of routine to find (e.g., DataProcessRoutine).

        Returns:
            List of (routine_id, routine) tuples matching the type.

        Examples:
            Find all DataProcessRoutine instances:
                >>> routines = flow.find_routines_by_type(DataProcessRoutine)
                >>> for routine_id, routine in routines:
                ...     print(f"Found {routine_id}: {routine}")
        """
        return [
            (rid, routine)
            for rid, routine in self.routines.items()
            if isinstance(routine, routine_type)
        ]

    def get_routine_retry_count(self, routine_id: str) -> int | None:
        """Get retry count for a routine.

        Args:
            routine_id: Routine identifier.

        Returns:
            Retry count if routine has error handler with retry strategy, None otherwise.

        Examples:
            Get retry count for a routine:
                >>> retry_count = flow.get_routine_retry_count("processor")
                >>> if retry_count is not None:
                ...     print(f"Current retry count: {retry_count}")
        """
        routine = self.routines.get(routine_id)
        if not routine:
            return None
        error_handler = routine.get_error_handler()
        if error_handler:
            return error_handler.retry_count
        return None

    def _get_error_handler_for_routine(
        self, routine: Routine, routine_id: str
    ) -> ErrorHandler | None:
        """Get error handler for a routine.

        Args:
            routine: Routine object.
            routine_id: Routine ID.

        Returns:
            ErrorHandler instance or None.
        """
        from routilux.flow.error_handling import get_error_handler_for_routine

        return get_error_handler_for_routine(routine, routine_id, self)

    def pause(
        self, job_state: JobState, reason: str = "", checkpoint: dict[str, Any] | None = None
    ) -> None:
        """Pause execution.

        Args:
            job_state: JobState to pause.
            reason: Reason for pausing.
            checkpoint: Optional checkpoint data.

        Raises:
            ValueError: If job_state flow_id doesn't match.
        """
        from routilux.flow.state_management import pause_flow

        if job_state.flow_id != self.flow_id:
            raise ValueError(
                f"JobState flow_id '{job_state.flow_id}' does not match Flow flow_id '{self.flow_id}'"
            )
        pause_flow(self, job_state, reason, checkpoint)

    def resume(self, job_state: JobState) -> JobState:
        """Resume execution from paused or saved state.

        Args:
            job_state: JobState to resume.

        Returns:
            Updated JobState.

        Raises:
            ValueError: If job_state flow_id doesn't match or routine doesn't exist.
        """
        from routilux.flow.state_management import resume_flow

        return resume_flow(self, job_state)

    def cancel(self, job_state: JobState, reason: str = "") -> None:
        """Cancel execution.

        Args:
            job_state: JobState to cancel.
            reason: Reason for cancellation.

        Raises:
            ValueError: If job_state flow_id doesn't match.
        """
        from routilux.flow.state_management import cancel_flow

        if job_state.flow_id != self.flow_id:
            raise ValueError(
                f"JobState flow_id '{job_state.flow_id}' does not match Flow flow_id '{self.flow_id}'"
            )
        cancel_flow(self, job_state, reason)

    def execute(
        self,
        entry_routine_id: str,
        entry_params: dict[str, Any] | None = None,
        execution_strategy: str | None = None,
        timeout: float | None = None,
    ) -> JobState:
        """Execute the flow starting from the specified entry routine.

        Args:
            entry_routine_id: Identifier of the routine to start execution from.
            entry_params: Optional dictionary of parameters to pass to the entry
                routine's trigger slot.
            execution_strategy: Optional execution strategy override.
            timeout: Optional timeout for execution completion in seconds.
                If None, uses flow.execution_timeout (default: 300.0 seconds).

        Returns:
            JobState object containing execution status and state.

        Raises:
            ValueError: If entry_routine_id does not exist in the flow.
        """
        from routilux.flow.execution import execute_flow

        return execute_flow(self, entry_routine_id, entry_params, execution_strategy, timeout)

    def wait_for_completion(
        self, timeout: float | None = None, job_state: JobState | None = None
    ) -> bool:
        """Wait for all tasks to complete.

        .. deprecated::
           This method is deprecated. Use ``JobState.wait_for_completion()`` instead
           for proper error detection and state management.

        For proper completion detection with error checking, use:

        .. code-block:: python

           from routilux.job_state import JobState
           completed = JobState.wait_for_completion(flow, job_state, timeout=timeout)

        Args:
            timeout: Timeout in seconds (infinite wait if None).
            job_state: Optional JobState object. If provided, will use
                JobState.wait_for_completion() for proper error detection.

        Returns:
            True if all tasks completed before timeout, False otherwise.
        """
        import warnings

        # If job_state is provided, use the proper method
        if job_state is not None:
            warnings.warn(
                "Flow.wait_for_completion() is deprecated. "
                "Use JobState.wait_for_completion(flow, job_state, timeout) instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            from routilux.job_state import JobState

            return JobState.wait_for_completion(flow=self, job_state=job_state, timeout=timeout)

        # Legacy behavior: just wait for thread (no error checking)
        warnings.warn(
            "Flow.wait_for_completion() without job_state is deprecated and does not check for errors. "
            "Use JobState.wait_for_completion(flow, job_state, timeout) instead for proper error detection.",
            DeprecationWarning,
            stacklevel=2,
        )
        if self._execution_thread:
            self._execution_thread.join(timeout=timeout)
            return not self._execution_thread.is_alive()
        return True

    def shutdown(self, wait: bool = True, timeout: float | None = None) -> None:
        """Shutdown Flow's executor and event loop.

        Args:
            wait: Whether to wait for all tasks to complete.
            timeout: Wait timeout in seconds (only effective when wait=True).
        """
        self._running = False

        if wait:
            import warnings

            # Suppress deprecation warning for shutdown - it's a generic cleanup method
            # that doesn't have a specific job_state context
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore", category=DeprecationWarning, module="routilux.flow.flow"
                )
                self.wait_for_completion(timeout=timeout)

        if self._executor:
            self._executor.shutdown(wait=wait)
            self._executor = None

        with self._execution_lock:
            self._active_tasks.clear()

    def serialize(self) -> dict[str, Any]:
        """Serialize Flow, including all routines and connections.

        Returns:
            Serialized dictionary containing flow data (structure only, no execution state).

        Raises:
            TypeError: If any Serializable object in the Flow cannot be constructed
                without arguments.

        Note:
            Flow serialization only includes structure (routines, connections, config).
            Execution state (JobState) must be serialized separately:
            1. Serialize Flow: flow_data = flow.serialize()
            2. Serialize JobState: job_state_data = job_state.serialize()
            3. Deserialize both on target host
            4. Use flow.resume(job_state) to continue execution
        """
        from routilux.flow.serialization import serialize_flow

        return serialize_flow(self)

    def deserialize(self, data: dict[str, Any]) -> None:
        """Deserialize Flow, restoring all routines and connections.

        Args:
            data: Serialized data dictionary.
        """
        from routilux.flow.serialization import deserialize_flow

        deserialize_flow(self, data)
