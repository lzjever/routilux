"""
Flow class.

Flow manager responsible for managing multiple Routine nodes and execution flow.
"""

from __future__ import annotations
import uuid
import threading
import queue
from typing import Dict, Optional, Any, List, Set, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor, Future

if TYPE_CHECKING:
    from routilux.routine import Routine
    from routilux.connection import Connection
    from routilux.job_state import JobState
    from routilux.event import Event
    from routilux.slot import Slot
    from routilux.execution_tracker import ExecutionTracker
    from routilux.error_handler import ErrorHandler

from serilux import register_serializable, Serializable

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
        flow_id: Optional[str] = None,
        execution_strategy: str = "sequential",
        max_workers: int = 5,
    ):
        """Initialize Flow.

        Args:
            flow_id: Flow identifier (auto-generated if None).
            execution_strategy: Execution strategy, "sequential" or "concurrent".
            max_workers: Maximum number of worker threads for concurrent execution.
        """
        super().__init__()
        self.flow_id: str = flow_id or str(uuid.uuid4())
        self.routines: Dict[str, "Routine"] = {}
        self.connections: List["Connection"] = []
        self.job_state: Optional["JobState"] = None
        self._current_flow: Optional["Flow"] = None
        self.execution_tracker: Optional["ExecutionTracker"] = None
        self.error_handler: Optional["ErrorHandler"] = None
        self._paused: bool = False

        self.execution_strategy: str = execution_strategy
        self.max_workers: int = max_workers if execution_strategy == "concurrent" else 1

        self._task_queue: queue.Queue = queue.Queue()
        self._pending_tasks: List[SlotActivationTask] = []

        self._execution_thread: Optional[threading.Thread] = None
        self._execution_lock: threading.Lock = threading.Lock()
        self._running: bool = False

        self._executor: Optional[ThreadPoolExecutor] = None
        self._active_tasks: Set[Future] = set()

        self.add_serializable_fields(
            [
                "flow_id",
                "job_state",
                "_paused",
                "execution_strategy",
                "max_workers",
                "error_handler",
                "routines",
                "connections",
            ]
        )

        self._event_slot_connections: Dict[tuple, "Connection"] = {}

    def __repr__(self) -> str:
        """Return string representation of the Flow."""
        return f"Flow[{self.flow_id}]"

    def set_execution_strategy(self, strategy: str, max_workers: Optional[int] = None) -> None:
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

    def _get_routine_id(self, routine: "Routine") -> Optional[str]:
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

    def _build_dependency_graph(self) -> Dict[str, Set[str]]:
        """Build routine dependency graph.

        Returns:
            Dependency graph dictionary: {routine_id: {dependent routine_ids}}.
        """
        from routilux.flow.dependency import build_dependency_graph

        return build_dependency_graph(self.routines, self.connections)

    def _get_ready_routines(
        self, completed: Set[str], dependency_graph: Dict[str, Set[str]], running: Set[str]
    ) -> List[str]:
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

    def _find_connection(self, event: "Event", slot: "Slot") -> Optional["Connection"]:
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

    def add_routine(self, routine: "Routine", routine_id: Optional[str] = None) -> str:
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
        param_mapping: Optional[Dict[str, str]] = None,
    ) -> "Connection":
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

    def set_error_handler(self, error_handler: "ErrorHandler") -> None:
        """Set error handler for the flow.

        Args:
            error_handler: ErrorHandler object.
        """
        self.error_handler = error_handler

    def _get_error_handler_for_routine(
        self, routine: "Routine", routine_id: str
    ) -> Optional["ErrorHandler"]:
        """Get error handler for a routine.

        Args:
            routine: Routine object.
            routine_id: Routine ID.

        Returns:
            ErrorHandler instance or None.
        """
        from routilux.flow.error_handling import get_error_handler_for_routine

        return get_error_handler_for_routine(routine, routine_id, self)

    def pause(self, reason: str = "", checkpoint: Optional[Dict[str, Any]] = None) -> None:
        """Pause execution.

        Args:
            reason: Reason for pausing.
            checkpoint: Optional checkpoint data.

        Raises:
            ValueError: If there is no active job_state.
        """
        from routilux.flow.state_management import pause_flow

        pause_flow(self, reason, checkpoint)

    def resume(self, job_state: Optional["JobState"] = None) -> "JobState":
        """Resume execution from paused or saved state.

        Args:
            job_state: JobState to resume (uses current job_state if None).

        Returns:
            Updated JobState.

        Raises:
            ValueError: If job_state flow_id doesn't match or routine doesn't exist.
        """
        from routilux.flow.state_management import resume_flow

        return resume_flow(self, job_state)

    def cancel(self, reason: str = "") -> None:
        """Cancel execution.

        Args:
            reason: Reason for cancellation.

        Raises:
            ValueError: If there is no active job_state.
        """
        from routilux.flow.state_management import cancel_flow

        cancel_flow(self, reason)

    def execute(
        self,
        entry_routine_id: str,
        entry_params: Optional[Dict[str, Any]] = None,
        execution_strategy: Optional[str] = None,
    ) -> "JobState":
        """Execute the flow starting from the specified entry routine.

        Args:
            entry_routine_id: Identifier of the routine to start execution from.
            entry_params: Optional dictionary of parameters to pass to the entry
                routine's trigger slot.
            execution_strategy: Optional execution strategy override.

        Returns:
            JobState object containing execution status and state.

        Raises:
            ValueError: If entry_routine_id does not exist in the flow.
        """
        from routilux.flow.execution import execute_flow

        return execute_flow(self, entry_routine_id, entry_params, execution_strategy)

    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """Wait for all tasks to complete.

        Args:
            timeout: Timeout in seconds (infinite wait if None).

        Returns:
            True if all tasks completed before timeout, False otherwise.
        """
        if self._execution_thread:
            self._execution_thread.join(timeout=timeout)
            return not self._execution_thread.is_alive()
        return True

    def shutdown(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """Shutdown Flow's executor and event loop.

        Args:
            wait: Whether to wait for all tasks to complete.
            timeout: Wait timeout in seconds (only effective when wait=True).
        """
        self._running = False

        if wait:
            self.wait_for_completion(timeout=timeout)

        if self._executor:
            self._executor.shutdown(wait=wait)
            self._executor = None

        with self._execution_lock:
            self._active_tasks.clear()

    def serialize(self) -> Dict[str, Any]:
        """Serialize Flow, including all routines and connections.

        Returns:
            Serialized dictionary containing flow data.

        Raises:
            TypeError: If any Serializable object in the Flow cannot be constructed
                without arguments.
        """
        from routilux.flow.serialization import serialize_flow

        return serialize_flow(self)

    def deserialize(self, data: Dict[str, Any]) -> None:
        """Deserialize Flow, restoring all routines and connections.

        Args:
            data: Serialized data dictionary.
        """
        from routilux.flow.serialization import deserialize_flow

        deserialize_flow(self, data)
