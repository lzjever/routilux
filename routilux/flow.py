"""
Flow class.

Flow manager responsible for managing multiple Routine nodes and execution flow.
"""

from __future__ import annotations
import uuid
import threading
from datetime import datetime
from typing import Dict, Optional, Any, List, Set, Tuple, TYPE_CHECKING
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

        # Concurrent execution related
        self.execution_strategy: str = execution_strategy
        self.max_workers: int = max_workers
        self._concurrent_executor: Optional[ThreadPoolExecutor] = None
        self._execution_lock: threading.Lock = threading.Lock()
        self._dependency_graph: Optional[Dict[str, Set[str]]] = None
        self._active_futures: Set[Future] = set()

        # Register serializable fields
        # routines and connections are included - base class will automatically serialize/deserialize them
        # We only need to add routine_id metadata and restore references after deserialization
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

        # Maintain event -> connection mapping for fast lookup
        # Note: _event_slot_connections doesn't need persistence, can be rebuilt from connections
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
        if max_workers is not None:
            self.max_workers = max_workers

        # If switching to concurrent mode, ensure thread pool is created
        if strategy == "concurrent" and self._concurrent_executor is None:
            self._get_executor()

    def _get_executor(self) -> ThreadPoolExecutor:
        """Get or create thread pool executor.

        Returns:
            ThreadPoolExecutor instance.
        """
        if self._concurrent_executor is None:
            self._concurrent_executor = ThreadPoolExecutor(max_workers=self.max_workers)
        return self._concurrent_executor

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

        Determines dependencies by analyzing connections:
        - If A.event -> B.slot, then B depends on A (B must wait for A to complete).

        Returns:
            Dependency graph dictionary: {routine_id: {dependent routine_ids}}.
        """
        graph = {rid: set() for rid in self.routines.keys()}

        for conn in self.connections:
            source_rid = self._get_routine_id(conn.source_event.routine)
            target_rid = self._get_routine_id(conn.target_slot.routine)

            if source_rid and target_rid and source_rid != target_rid:
                graph[target_rid].add(source_rid)

        return graph

    def _get_ready_routines(
        self, completed: Set[str], dependency_graph: Dict[str, Set[str]], running: Set[str]
    ) -> List[str]:
        """Get routines ready for execution (all dependencies completed and not running).

        Args:
            completed: Set of completed routine IDs.
            dependency_graph: Dependency graph.
            running: Set of currently running routine IDs.

        Returns:
            List of routine IDs ready for execution.
        """
        ready = []
        for routine_id, dependencies in dependency_graph.items():
            # Check: all dependencies completed, and currently not running
            if (
                dependencies.issubset(completed)
                and routine_id not in completed
                and routine_id not in running
            ):
                ready.append(routine_id)
        return ready

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

    def add_routine(self, routine: "Routine", routine_id: Optional[str] = None) -> str:
        """Add a routine to the flow.

        This method registers a Routine instance in the flow, making it available
        for connections and execution. Each routine must have a unique ID within
        the flow.

        Args:
            routine: Routine instance to add. Must be a subclass of Routine.
                The routine should be fully configured (slots/events defined)
                before adding to the flow, though you can modify it afterward.
            routine_id: Optional unique identifier for this routine in the flow.
                If None, uses routine._id (auto-generated hex ID).
                If provided, must be unique within this flow.
                Recommended: Use descriptive names like "data_processor", "validator"
                for better readability in logs and debugging.

        Returns:
            The routine ID used (either provided or routine._id).
            Store this ID to use when connecting routines or executing the flow.

        Raises:
            ValueError: If routine_id already exists in the flow.
                Each routine must have a unique ID.

        Examples:
            Basic usage:
                >>> flow = Flow()
                >>> routine = MyRoutine()
                >>> routine_id = flow.add_routine(routine, "my_routine")
                >>> # Use routine_id for connections and execution

            Using auto-generated ID:
                >>> routine_id = flow.add_routine(routine)  # Uses routine._id
                >>> print(routine_id)  # e.g., "0x7f8a1b2c3d4e"

            Multiple routines:
                >>> processor_id = flow.add_routine(Processor(), "processor")
                >>> validator_id = flow.add_routine(Validator(), "validator")
                >>> flow.connect(processor_id, "output", validator_id, "input")
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

        This creates a data flow connection: when the source routine emits the
        specified event, the data is automatically passed to the target routine's
        slot handler.

        Parameter Mapping:
            The param_mapping dictionary allows you to rename parameters when
            passing data from event to slot. This is useful when:
            - Event and slot use different parameter names
            - You want to transform parameter names for clarity
            - You need to map multiple events to the same slot with different names

            Format: {event_param_name: slot_param_name}

            If param_mapping is None, parameters are passed with their original names.
            If an event parameter is not in the mapping, it's passed with the same name.
            If a slot parameter is not in the mapping and the event doesn't have
            a parameter with that name, it will be missing (handler should handle this).

        Args:
            source_routine_id: Identifier of the routine that emits the event.
                Must be a routine added to this flow via add_routine().
            source_event: Name of the event to connect from. This event must
                be defined in the source routine using define_event().
            target_routine_id: Identifier of the routine that receives the data.
                Must be a routine added to this flow via add_routine().
            target_slot: Name of the slot to connect to. This slot must be
                defined in the target routine using define_slot().
            param_mapping: Optional dictionary mapping event parameter names to
                slot parameter names. If None, parameters are passed unchanged.
                Example: {"event_data": "slot_input", "event_count": "slot_count"}

        Returns:
            Connection object representing this connection. You typically don't
            need to use this return value, but it can be useful for:
            - Inspecting connection details
            - Programmatically managing connections
            - Debugging connection issues

        Raises:
            ValueError: If any of the following conditions are not met:
                - Source routine does not exist
                - Source event does not exist in source routine
                - Target routine does not exist
                - Target slot does not exist in target routine

        Examples:
            Basic connection (no parameter mapping):
                >>> flow = Flow()
                >>> source_id = flow.add_routine(SourceRoutine(), "source")
                >>> target_id = flow.add_routine(TargetRoutine(), "target")
                >>> flow.connect(source_id, "output", target_id, "input")
                >>> # When source emits "output" with {"data": "value"},
                >>> # target's "input" slot handler receives {"data": "value"}

            Connection with parameter mapping:
                >>> flow.connect(
                ...     source_id, "output",
                ...     target_id, "input",
                ...     param_mapping={"source_data": "target_input", "count": "total"}
                ... )
                >>> # Event emits: {"source_data": "x", "count": 5, "extra": "ignored"}
                >>> # Slot receives: {"target_input": "x", "total": 5, "extra": "ignored"}

            Multiple connections from same event:
                >>> flow.connect(source_id, "output", target1_id, "input1")
                >>> flow.connect(source_id, "output", target2_id, "input2")
                >>> # Both targets receive data when source emits "output"
        """
        # Validate source routine
        if source_routine_id not in self.routines:
            raise ValueError(f"Source routine '{source_routine_id}' not found in flow")

        source_routine = self.routines[source_routine_id]
        source_event_obj = source_routine.get_event(source_event)
        if source_event_obj is None:
            raise ValueError(f"Event '{source_event}' not found in routine '{source_routine_id}'")

        # Validate target routine
        if target_routine_id not in self.routines:
            raise ValueError(f"Target routine '{target_routine_id}' not found in flow")

        target_routine = self.routines[target_routine_id]
        target_slot_obj = target_routine.get_slot(target_slot)
        if target_slot_obj is None:
            raise ValueError(f"Slot '{target_slot}' not found in routine '{target_routine_id}'")

        # Create connection
        from routilux.connection import Connection

        connection = Connection(source_event_obj, target_slot_obj, param_mapping)
        self.connections.append(connection)

        # Maintain mapping
        key = (source_event_obj, target_slot_obj)
        self._event_slot_connections[key] = connection

        return connection

    def set_error_handler(self, error_handler: "ErrorHandler") -> None:
        """Set error handler for the flow.

        This sets the default error handler for all routines in the flow.
        Individual routines can override this by setting their own error handler
        using routine.set_error_handler().

        Priority order:
        1. Routine-level error handler (if set)
        2. Flow-level error handler (if set)
        3. Default behavior (STOP)

        Args:
            error_handler: ErrorHandler object.
        """
        self.error_handler = error_handler

    def _get_error_handler_for_routine(
        self, routine: "Routine", routine_id: str
    ) -> Optional["ErrorHandler"]:
        """Get error handler for a routine.

        Priority order:
        1. Routine-level error handler (if set)
        2. Flow-level error handler (if set)
        3. None (default STOP behavior)

        Args:
            routine: Routine object.
            routine_id: Routine ID.

        Returns:
            ErrorHandler instance or None.
        """
        # Priority 1: Routine-level error handler
        if routine.get_error_handler() is not None:
            return routine.get_error_handler()

        # Priority 2: Flow-level error handler
        return self.error_handler

    def pause(self, reason: str = "", checkpoint: Optional[Dict[str, Any]] = None) -> None:
        """Pause execution.

        This is the main entry point for pausing execution. JobState is only
        responsible for state recording, while execution control is managed by Flow.

        Args:
            reason: Reason for pausing.
            checkpoint: Optional checkpoint data.

        Raises:
            ValueError: If there is no active job_state.
        """
        if not self.job_state:
            raise ValueError("No active job_state to pause. Flow must be executing.")

        self.job_state._set_paused(reason=reason, checkpoint=checkpoint)
        self._paused = True

    def execute(
        self,
        entry_routine_id: str,
        entry_params: Optional[Dict[str, Any]] = None,
        execution_strategy: Optional[str] = None,
    ) -> "JobState":
        """Execute the flow starting from the specified entry routine.

        This method initiates workflow execution. The flow will:
        1. Execute the entry routine with the provided parameters
        2. Propagate execution through connected routines based on events/slots
        3. Handle errors according to configured error handlers
        4. Track execution state in the returned JobState

        Execution Strategy:
            - "sequential": Routines execute one at a time in dependency order
            - "concurrent": Independent routines can execute in parallel using threads

        The execution strategy can be set:
            - At Flow initialization (execution_strategy parameter)
            - Via set_execution_strategy() method
            - Per-execution via this method's execution_strategy parameter (temporary override)

        Args:
            entry_routine_id: Identifier of the routine to start execution from.
                This routine must exist in the flow (added via add_routine()).
            entry_params: Optional dictionary of parameters to pass to the entry
                routine's __call__ method. These are passed as keyword arguments.
                Example: {"data": "value", "count": 42}
            execution_strategy: Optional execution strategy override.
                If provided, temporarily overrides the flow's default strategy
                for this execution only. Must be "sequential" or "concurrent".
                If None, uses the flow's default strategy.

        Returns:
            JobState object containing:
            - Execution status ("completed", "failed", "paused", "cancelled")
            - State of each routine in the flow
            - Execution history with timestamps
            - Error information (if any)

            Use job_state.status to check execution result.
            Use job_state.get_routine_state(routine_id) to inspect individual routine states.

        Raises:
            ValueError: If entry_routine_id does not exist in the flow.
            RuntimeError: If flow is already executing (concurrent execution not supported).

        Examples:
            Basic execution:
                >>> flow = Flow()
                >>> routine = MyRoutine()
                >>> routine_id = flow.add_routine(routine, "my_routine")
                >>> job_state = flow.execute(routine_id, entry_params={"input": "data"})
                >>> print(job_state.status)  # "completed" or "failed"

            Execution with custom strategy:
                >>> job_state = flow.execute(
                ...     routine_id,
                ...     entry_params={"input": "data"},
                ...     execution_strategy="concurrent"  # Override default
                ... )

            Checking execution results:
                >>> job_state = flow.execute(routine_id)
                >>> if job_state.status == "completed":
                ...     routine_state = job_state.get_routine_state(routine_id)
                ...     print(f"Routine executed: {routine_state['status']}")
        """
        if entry_routine_id not in self.routines:
            raise ValueError(f"Entry routine '{entry_routine_id}' not found in flow")

        # Determine execution strategy to use
        strategy = execution_strategy or self.execution_strategy

        # Select execution method based on strategy
        if strategy == "concurrent":
            return self._execute_concurrent(entry_routine_id, entry_params)
        else:
            return self._execute_sequential(entry_routine_id, entry_params)

    def _execute_sequential(
        self, entry_routine_id: str, entry_params: Optional[Dict[str, Any]] = None
    ) -> "JobState":
        """Execute Flow sequentially (original logic).

        Args:
            entry_routine_id: Entry routine identifier.
            entry_params: Entry parameters.

        Returns:
            JobState object.
        """
        # Create JobState
        from routilux.job_state import JobState
        from routilux.execution_tracker import ExecutionTracker

        job_state = JobState(self.flow_id)
        job_state.status = "running"
        job_state.current_routine_id = entry_routine_id
        self.job_state = job_state

        # Create execution tracker
        self.execution_tracker = ExecutionTracker(self.flow_id)

        entry_params = entry_params or {}

        try:
            # Execute entry routine (pass flow so events can be transmitted via Connection)
            entry_routine = self.routines[entry_routine_id]

            # Set flow context to all routines so emit can access it
            for routine in self.routines.values():
                routine._current_flow = self

            # Record execution start
            from datetime import datetime

            start_time = datetime.now()
            job_state.record_execution(entry_routine_id, "start", entry_params)
            self.execution_tracker.record_routine_start(entry_routine_id, entry_params)

            # Execute entry routine
            entry_routine(**entry_params)

            # Calculate execution time
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            # Update state
            job_state.update_routine_state(
                entry_routine_id,
                {
                    "status": "completed",
                    "stats": entry_routine.stats(),
                    "execution_time": execution_time,
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                },
            )

            # Record completion
            job_state.record_execution(
                entry_routine_id, "completed", {"execution_time": execution_time}
            )
            self.execution_tracker.record_routine_end(entry_routine_id, "completed")

            job_state.status = "completed"

        except Exception as e:
            # Use error handler to process error
            # Priority: routine-level > flow-level > default (STOP)
            error_handler = self._get_error_handler_for_routine(entry_routine, entry_routine_id)
            if error_handler:
                should_continue = error_handler.handle_error(
                    e, entry_routine, entry_routine_id, self
                )

                # If continue strategy, mark as completed
                if error_handler.strategy.value == "continue":
                    job_state.status = "completed"
                    job_state.update_routine_state(
                        entry_routine_id,
                        {
                            "status": "error_continued",
                            "error": str(e),
                            "stats": entry_routine.stats(),
                        },
                    )
                    return job_state

                # If skip strategy, mark as completed
                if error_handler.strategy.value == "skip":
                    job_state.status = "completed"
                    return job_state

                # If retry strategy
                if should_continue and error_handler.strategy.value == "retry":
                    # Retry logic (handle_error already incremented retry_count if exception is retryable)
                    # max_retries represents maximum retry count, so total attempts = 1 + max_retries
                    retry_success = False
                    # Already attempted once (initial call), need to retry max_retries more times
                    remaining_retries = error_handler.max_retries
                    for attempt in range(remaining_retries):
                        try:
                            entry_routine(**entry_params)
                            retry_success = True
                            break
                        except Exception as retry_error:
                            # On each retry failure, check if we should continue
                            # For non-retryable exceptions, handle_error returns False immediately
                            should_continue_retry = error_handler.handle_error(
                                retry_error, entry_routine, entry_routine_id, self
                            )
                            if not should_continue_retry:
                                # Non-retryable exception or max retries exceeded
                                e = retry_error
                                break
                            # If should_continue_retry is True, we'll continue to next retry
                            # (unless we've exhausted all retries)
                            if attempt >= remaining_retries - 1:
                                # Last retry failed
                                e = retry_error
                                break

                    if retry_success:
                        # Retry succeeded, continue normal flow
                        end_time = datetime.now()
                        execution_time = (end_time - start_time).total_seconds()
                        job_state.update_routine_state(
                            entry_routine_id,
                            {
                                "status": "completed",
                                "stats": entry_routine.stats(),
                                "execution_time": execution_time,
                                "retry_count": error_handler.retry_count,
                            },
                        )
                        job_state.record_execution(
                            entry_routine_id,
                            "completed",
                            {"execution_time": execution_time, "retried": True},
                        )
                        if self.execution_tracker:
                            self.execution_tracker.record_routine_end(entry_routine_id, "completed")
                        job_state.status = "completed"
                        return job_state
                    # Retry failed, continue error handling (will execute default error handling below)

            # Default error handling (if no error handler or strategy is STOP)
            from datetime import datetime

            error_time = datetime.now()
            job_state.status = "failed"
            job_state.update_routine_state(
                entry_routine_id,
                {"status": "failed", "error": str(e), "error_time": error_time.isoformat()},
            )
            # Record error to execution history
            job_state.record_execution(
                entry_routine_id, "error", {"error": str(e), "error_type": type(e).__name__}
            )
            if self.execution_tracker:
                self.execution_tracker.record_routine_end(entry_routine_id, "failed", error=str(e))
            import logging

            logging.exception(f"Error executing flow: {e}")

        return job_state

    def _execute_concurrent(
        self, entry_routine_id: str, entry_params: Optional[Dict[str, Any]] = None
    ) -> "JobState":
        """Execute Flow concurrently.

        In concurrent mode, routines triggered by Event.emit execute concurrently.
        Entry routine still executes synchronously to trigger event flow.

        Args:
            entry_routine_id: Entry routine identifier.
            entry_params: Entry parameters.

        Returns:
            JobState object.
        """
        # Concurrent execution is mainly implemented by modifying Event.emit behavior
        # Here we just ensure Flow is in concurrent mode, then use sequential execution logic
        # Actual concurrency is handled in Event.emit

        # Temporarily use sequential execution but mark as concurrent mode
        # Event.emit will check flow.execution_strategy to decide whether to execute concurrently
        return self._execute_sequential(entry_routine_id, entry_params)

    def _execute_routine_safe(
        self, routine_id: str, routine: "Routine", params: Dict[str, Any], start_time: "datetime"
    ) -> Tuple[str, Any, Optional[Exception], float]:
        """Execute routine in a thread-safe manner.

        Args:
            routine_id: Routine identifier.
            routine: Routine object.
            params: Execution parameters.
            start_time: Start time.

        Returns:
            Tuple of (routine_id, result, error, execution_time).
        """
        from datetime import datetime

        result = None
        error = None

        try:
            # Execute routine (outside lock to avoid blocking)
            result = routine(**params)
        except Exception as e:
            error = e

        # Calculate execution time
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()

        return (routine_id, result, error, execution_time)

    def resume(self, job_state: Optional["JobState"] = None) -> "JobState":
        """Resume execution from paused or saved state.

        This is the main entry point for resuming execution. JobState is only
        responsible for state recording, while execution control is managed by Flow.

        Args:
            job_state: JobState to resume (uses current job_state if None).

        Returns:
            Updated JobState.

        Raises:
            ValueError: If job_state flow_id doesn't match or routine doesn't exist.
        """
        if job_state is None:
            job_state = self.job_state

        if job_state is None:
            raise ValueError("No JobState to resume")

        if job_state.flow_id != self.flow_id:
            raise ValueError(
                f"JobState flow_id '{job_state.flow_id}' does not match Flow flow_id '{self.flow_id}'"
            )

        # Validate current routine exists
        if job_state.current_routine_id and job_state.current_routine_id not in self.routines:
            raise ValueError(f"Current routine '{job_state.current_routine_id}' not found in flow")

        # Restore state (controlled by Flow)
        job_state._set_running()
        self._paused = False
        self.job_state = job_state

        # Restore routine states
        for routine_id, routine_state in job_state.routine_states.items():
            if routine_id in self.routines:
                routine = self.routines[routine_id]
                # Restore routine state
                if "stats" in routine_state:
                    routine._stats.update(routine_state["stats"])

        # Continue execution from current routine
        if job_state.current_routine_id:
            try:
                routine = self.routines[job_state.current_routine_id]

                # Set flow context
                for r in self.routines.values():
                    r._current_flow = self

                # Execute routine
                routine()

                job_state.status = "completed"
                job_state.update_routine_state(
                    job_state.current_routine_id, {"status": "completed", "stats": routine.stats()}
                )
            except Exception as e:
                # Use error handler
                # Priority: routine-level > flow-level > default (STOP)
                error_handler = self._get_error_handler_for_routine(
                    routine, job_state.current_routine_id
                )
                if error_handler:
                    should_continue = error_handler.handle_error(
                        e, routine, job_state.current_routine_id, self
                    )
                    if not should_continue:
                        job_state.status = "failed"
                else:
                    job_state.status = "failed"

                job_state.update_routine_state(
                    job_state.current_routine_id, {"status": "failed", "error": str(e)}
                )

        return job_state

    def cancel(self, reason: str = "") -> None:
        """Cancel execution.

        This is the main entry point for canceling execution. JobState is only
        responsible for state recording, while execution control is managed by Flow.

        Args:
            reason: Reason for cancellation.

        Raises:
            ValueError: If there is no active job_state.
        """
        if not self.job_state:
            raise ValueError("No active job_state to cancel. Flow must be executing.")

        self.job_state._set_cancelled(reason=reason)
        self._paused = False  # Clear pause flag when canceling

        # If in concurrent mode, cancel all running tasks
        if self.execution_strategy == "concurrent":
            with self._execution_lock:
                for future in self._active_futures.copy():
                    future.cancel()
                self._active_futures.clear()

    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """Wait for all concurrent tasks to complete.

        In concurrent execution mode, this method waits for all active futures to complete.
        This is useful for ensuring all asynchronous tasks complete before program exit.

        Args:
            timeout: Timeout in seconds (infinite wait if None).

        Returns:
            True if all tasks completed before timeout, False otherwise.
        """
        if self.execution_strategy != "concurrent":
            return True  # Sequential execution mode doesn't need to wait

        import time as time_module

        start_time = time_module.time() if timeout else None
        check_interval = 0.05  # Check interval in seconds
        max_empty_checks = 5  # Consecutive empty checks before considering complete
        empty_check_count = 0

        # Loop until all futures complete
        while True:
            # Check timeout
            if start_time and timeout:
                elapsed = time_module.time() - start_time
                if elapsed >= timeout:
                    # Timeout, check if any remain incomplete
                    with self._execution_lock:
                        remaining = [f for f in self._active_futures if not f.done()]
                    return len(remaining) == 0

            # Get all currently active futures and check completion status
            with self._execution_lock:
                futures_to_wait = list(self._active_futures)

            if not futures_to_wait:
                # No active futures
                empty_check_count += 1
                if empty_check_count >= max_empty_checks:
                    # Multiple consecutive empty checks, all tasks completed
                    return True
                # Brief wait in case new futures are being added
                time_module.sleep(check_interval)
                continue

            # Active futures exist, reset empty check count
            empty_check_count = 0

            # Check if all futures are completed
            all_done = True
            for future in futures_to_wait:
                if not future.done():
                    all_done = False
                    break

            if all_done:
                # All futures completed, but new ones might be added
                # Wait a bit longer to ensure no new futures
                time_module.sleep(check_interval)
                # Check again
                with self._execution_lock:
                    futures_to_wait = list(self._active_futures)
                    if not futures_to_wait:
                        return True
            else:
                # Still have incomplete futures, wait and check again
                time_module.sleep(check_interval)

    def shutdown(self, wait: bool = True, timeout: Optional[float] = None) -> None:
        """Shutdown Flow's concurrent executor.

        In concurrent mode, this method waits for all tasks to complete (if wait=True),
        then shuts down the thread pool. This is important for proper resource cleanup
        before program exit.

        Args:
            wait: Whether to wait for all tasks to complete.
            timeout: Wait timeout in seconds (only effective when wait=True).
        """
        if self.execution_strategy != "concurrent" or self._concurrent_executor is None:
            return

        if wait:
            self.wait_for_completion(timeout=timeout)

        # Shutdown thread pool
        self._concurrent_executor.shutdown(wait=wait)
        self._concurrent_executor = None

        # Clear futures set
        with self._execution_lock:
            self._active_futures.clear()

    def serialize(self) -> Dict[str, Any]:
        """Serialize Flow, including all routines and connections.

        Before serialization, this method validates that all Serializable objects
        in the Flow (routines, connections, slots, events, etc.) can be constructed
        without arguments. This ensures that deserialization will succeed.

        Returns:
            Serialized dictionary containing flow data.

        Raises:
            TypeError: If any Serializable object in the Flow cannot be constructed
                without arguments. The error message includes details about which
                object failed and how to fix it.
        """
        # Validate all Serializable objects before serialization
        # This catches issues early and provides clear error messages
        from serilux import validate_serializable_tree

        validate_serializable_tree(self)

        # Let base class handle all registered fields including routines and connections
        # Base class automatically handles Serializable objects in dicts and lists
        data = super().serialize()

        return data

    def deserialize(self, data: Dict[str, Any]) -> None:
        """Deserialize Flow, restoring all routines and connections.

        Args:
            data: Serialized data dictionary.
        """
        # Special case: Handle job_state datetime conversion
        job_state_data = data.get("job_state", None)
        if job_state_data:
            from datetime import datetime

            # Convert datetime strings to datetime objects
            if isinstance(job_state_data.get("created_at"), str):
                job_state_data["created_at"] = datetime.fromisoformat(job_state_data["created_at"])
            if isinstance(job_state_data.get("updated_at"), str):
                job_state_data["updated_at"] = datetime.fromisoformat(job_state_data["updated_at"])

        super().deserialize(data)

        # Post-process: Restore routine references by finding routines with matching event/slot names
        # (This is Flow-specific logic that base class cannot handle)

        for routine in self.routines.values():
            routine.current_flow = self._current_flow

        # Post-process: Restore connection references by finding routines with matching event/slot names
        # (This is Flow-specific logic that base class cannot handle)

        valid_connections = []
        for connection in self.connections:
            source_event_name = getattr(connection, "_source_event_name", None)
            target_slot_name = getattr(connection, "_target_slot_name", None)

            # Find source routine by event name
            if source_event_name:
                for routine in self.routines.values():
                    source_event = routine.get_event(source_event_name)
                    if source_event:
                        connection.source_event = source_event
                        break

            # Find target routine by slot name
            if target_slot_name:
                for routine in self.routines.values():
                    target_slot = routine.get_slot(target_slot_name)
                    if target_slot:
                        connection.target_slot = target_slot
                        break

            # Only add connection if both event and slot are found (ignore invalid/incomplete connections)
            if connection.source_event and connection.target_slot:
                # Establish bidirectional connection
                if connection.target_slot not in connection.source_event.connected_slots:
                    connection.source_event.connect(connection.target_slot)
                if connection.source_event not in connection.target_slot.connected_events:
                    connection.target_slot.connect(connection.source_event)

                valid_connections.append(connection)
                # Rebuild mapping
                key = (connection.source_event, connection.target_slot)
                self._event_slot_connections[key] = connection

        # Update connections list with only valid connections
        self.connections = valid_connections
