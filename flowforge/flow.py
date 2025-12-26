"""
Flow class.

Flow manager responsible for managing multiple Routine nodes and execution flow.
"""
from __future__ import annotations
import uuid
import threading
from datetime import datetime
from typing import Dict, Optional, Any, List, Set, Tuple, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor, Future, as_completed

if TYPE_CHECKING:
    from flowforge.routine import Routine
    from flowforge.connection import Connection
    from flowforge.job_state import JobState
    from flowforge.event import Event
    from flowforge.slot import Slot
    from flowforge.execution_tracker import ExecutionTracker
    from flowforge.error_handler import ErrorHandler

from flowforge.utils.serializable import register_serializable, Serializable
from flowforge.serialization_utils import (
    get_routine_class_info,
    load_routine_class,
    serialize_callable,
    deserialize_callable
)


@register_serializable
class Flow(Serializable):
    """Flow manager for orchestrating workflow execution.
    
    Responsibilities:
    - Manage multiple Routine nodes
    - Manage connections between nodes
    - Execute workflow
    - Persistence and restoration
    """
    
    def __init__(
        self, 
        flow_id: Optional[str] = None,
        execution_strategy: str = "sequential",
        max_workers: int = 5
    ):
        """Initialize Flow.

        Args:
            flow_id: Flow identifier (auto-generated if None).
            execution_strategy: Execution strategy, "sequential" or "concurrent".
            max_workers: Maximum number of worker threads for concurrent execution.
        """
        super().__init__()
        self.flow_id: str = flow_id or str(uuid.uuid4())
        self.routines: Dict[str, 'Routine'] = {}
        self.connections: List['Connection'] = []
        self.job_state: Optional['JobState'] = None
        self._current_flow: Optional['Flow'] = None
        self.execution_tracker: Optional['ExecutionTracker'] = None
        self.error_handler: Optional['ErrorHandler'] = None
        self._paused: bool = False
        
        # Concurrent execution related
        self.execution_strategy: str = execution_strategy
        self.max_workers: int = max_workers
        self._concurrent_executor: Optional[ThreadPoolExecutor] = None
        self._execution_lock: threading.Lock = threading.Lock()
        self._dependency_graph: Optional[Dict[str, Set[str]]] = None
        self._active_futures: Set[Future] = set()
        
        # Register serializable fields
        # Note: routines and connections require special handling in serialize method
        self.add_serializable_fields([
            "flow_id", "routines", "connections", "job_state", "_paused",
            "execution_strategy", "max_workers"
        ])
        
        # Maintain event -> connection mapping for fast lookup
        # Note: _event_slot_connections doesn't need persistence, can be rebuilt from connections
        self._event_slot_connections: Dict[tuple, 'Connection'] = {}
    
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
            raise ValueError(f"Invalid execution strategy: {strategy}. Must be 'sequential' or 'concurrent'")
        
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
    
    def _get_routine_id(self, routine: 'Routine') -> Optional[str]:
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
        self, 
        completed: Set[str], 
        dependency_graph: Dict[str, Set[str]],
        running: Set[str]
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
            if (dependencies.issubset(completed) and 
                routine_id not in completed and 
                routine_id not in running):
                ready.append(routine_id)
        return ready
    
    def _find_connection(self, event: 'Event', slot: 'Slot') -> Optional['Connection']:
        """Find Connection from event to slot.

        Args:
            event: Event object.
            slot: Slot object.

        Returns:
            Connection object if found, None otherwise.
        """
        key = (event, slot)
        return self._event_slot_connections.get(key)
    
    def add_routine(self, routine: 'Routine', routine_id: Optional[str] = None) -> str:
        """Add a routine to the flow.

        Args:
            routine: Routine object.
            routine_id: Routine ID (uses routine._id if None).

        Returns:
            Routine ID.

        Raises:
            ValueError: If routine_id already exists.
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
        param_mapping: Optional[Dict[str, str]] = None
    ) -> 'Connection':
        """Connect two routines.

        Args:
            source_routine_id: Source routine identifier.
            source_event: Source event name.
            target_routine_id: Target routine identifier.
            target_slot: Target slot name.
            param_mapping: Parameter mapping dictionary.

        Returns:
            Connection object.

        Raises:
            ValueError: If routine, event, or slot does not exist.
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
        from flowforge.connection import Connection
        connection = Connection(source_event_obj, target_slot_obj, param_mapping)
        self.connections.append(connection)
        
        # Maintain mapping
        key = (source_event_obj, target_slot_obj)
        self._event_slot_connections[key] = connection
        
        return connection
    
    def set_error_handler(self, error_handler: 'ErrorHandler') -> None:
        """Set error handler.

        Args:
            error_handler: ErrorHandler object.
        """
        self.error_handler = error_handler
    
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
        execution_strategy: Optional[str] = None
    ) -> 'JobState':
        """Execute the flow.

        Args:
            entry_routine_id: Entry routine identifier.
            entry_params: Entry parameters.
            execution_strategy: Execution strategy (optional, overrides default).

        Returns:
            JobState object.

        Raises:
            ValueError: If entry_routine_id does not exist.
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
        self,
        entry_routine_id: str,
        entry_params: Optional[Dict[str, Any]] = None
    ) -> 'JobState':
        """Execute Flow sequentially (original logic).

        Args:
            entry_routine_id: Entry routine identifier.
            entry_params: Entry parameters.

        Returns:
            JobState object.
        """
        # Create JobState
        from flowforge.job_state import JobState
        from flowforge.execution_tracker import ExecutionTracker
        
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
            job_state.update_routine_state(entry_routine_id, {
                "status": "completed",
                "stats": entry_routine.stats(),
                "execution_time": execution_time,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat()
            })
            
            # Record completion
            job_state.record_execution(entry_routine_id, "completed", {
                "execution_time": execution_time
            })
            self.execution_tracker.record_routine_end(entry_routine_id, "completed")
            
            job_state.status = "completed"
            
        except Exception as e:
            # Use error handler to process error
            if self.error_handler:
                should_continue = self.error_handler.handle_error(
                    e, entry_routine, entry_routine_id, self
                )
                
                # If continue strategy, mark as completed
                if self.error_handler.strategy.value == "continue":
                    job_state.status = "completed"
                    job_state.update_routine_state(entry_routine_id, {
                        "status": "error_continued",
                        "error": str(e),
                        "stats": entry_routine.stats()
                    })
                    return job_state
                
                # If skip strategy, mark as completed
                if self.error_handler.strategy.value == "skip":
                    job_state.status = "completed"
                    return job_state
                
                # If retry strategy
                if should_continue and self.error_handler.strategy.value == "retry":
                    # Retry logic (handle_error already incremented retry_count, continue retrying here)
                    # max_retries represents maximum retry count, so total attempts = 1 + max_retries
                    retry_success = False
                    # Already attempted once (initial call), need to retry max_retries more times
                    remaining_retries = self.error_handler.max_retries
                    for attempt in range(remaining_retries):
                        try:
                            entry_routine(**entry_params)
                            retry_success = True
                            break
                        except Exception as retry_error:
                            # On each retry failure, call handle_error again to update retry_count
                            if attempt < remaining_retries - 1:
                                should_continue_retry = self.error_handler.handle_error(
                                    retry_error, entry_routine, entry_routine_id, self
                                )
                                if not should_continue_retry:
                                    e = retry_error
                                    break
                            else:
                                # Last retry failed
                                e = retry_error
                                break
                    
                    if retry_success:
                        # Retry succeeded, continue normal flow
                        end_time = datetime.now()
                        execution_time = (end_time - start_time).total_seconds()
                        job_state.update_routine_state(entry_routine_id, {
                            "status": "completed",
                            "stats": entry_routine.stats(),
                            "execution_time": execution_time,
                            "retry_count": self.error_handler.retry_count
                        })
                        job_state.record_execution(entry_routine_id, "completed", {
                            "execution_time": execution_time,
                            "retried": True
                        })
                        if self.execution_tracker:
                            self.execution_tracker.record_routine_end(entry_routine_id, "completed")
                        job_state.status = "completed"
                        return job_state
                    # Retry failed, continue error handling (will execute default error handling below)
            
            # Default error handling (if no error handler or strategy is STOP)
            from datetime import datetime
            error_time = datetime.now()
            job_state.status = "failed"
            job_state.update_routine_state(entry_routine_id, {
                "status": "failed",
                "error": str(e),
                "error_time": error_time.isoformat()
            })
            # Record error to execution history
            job_state.record_execution(entry_routine_id, "error", {
                "error": str(e),
                "error_type": type(e).__name__
            })
            if self.execution_tracker:
                self.execution_tracker.record_routine_end(
                    entry_routine_id, "failed", error=str(e)
                )
            import logging
            logging.exception(f"Error executing flow: {e}")
        
        return job_state
    
    def _execute_concurrent(
        self,
        entry_routine_id: str,
        entry_params: Optional[Dict[str, Any]] = None
    ) -> 'JobState':
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
        self,
        routine_id: str,
        routine: 'Routine',
        params: Dict[str, Any],
        start_time: 'datetime'
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
    
    def resume(self, job_state: Optional['JobState'] = None) -> 'JobState':
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
            raise ValueError(f"JobState flow_id '{job_state.flow_id}' does not match Flow flow_id '{self.flow_id}'")
        
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
                job_state.update_routine_state(job_state.current_routine_id, {
                    "status": "completed",
                    "stats": routine.stats()
                })
            except Exception as e:
                # Use error handler
                if self.error_handler:
                    should_continue = self.error_handler.handle_error(
                        e, routine, job_state.current_routine_id, self
                    )
                    if not should_continue:
                        job_state.status = "failed"
                else:
                    job_state.status = "failed"
                
                job_state.update_routine_state(job_state.current_routine_id, {
                    "status": "failed",
                    "error": str(e)
                })
        
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

        Returns:
            Serialized dictionary containing flow data.
        """
        # First call parent serialize, which handles registered fields
        # But we need special handling for routines and connections
        data = {}
        
        # Serialize basic fields
        for field in self.fields_to_serialize:
            if field in ["routines", "connections"]:
                continue  # These fields require special handling
            value = getattr(self, field, None)
            if isinstance(value, Serializable):
                data[field] = value.serialize()
            elif isinstance(value, list):
                data[field] = [
                    item.serialize() if isinstance(item, Serializable) else item
                    for item in value
                ]
            elif isinstance(value, dict):
                data[field] = {
                    k: v.serialize() if isinstance(v, Serializable) else v
                    for k, v in value.items()
                }
            else:
                data[field] = value
        
        # Add type information
        data["_type"] = type(self).__name__
        
        # Serialize routines (complete information)
        routines_data = {}
        for routine_id, routine in self.routines.items():
            routine_data = routine.serialize()
            routine_data["routine_id"] = routine_id
            routines_data[routine_id] = routine_data
        
        data["routines"] = routines_data
        
        # Serialize connections (need to save Flow's routine_id, not routine._id)
        connections_data = []
        for connection in self.connections:
            conn_data = connection.serialize()
            
            # Find routine_id in Flow
            source_routine_id = None
            target_routine_id = None
            
            for rid, routine in self.routines.items():
                if routine == connection.source_event.routine:
                    source_routine_id = rid
                if routine == connection.target_slot.routine:
                    target_routine_id = rid
            
            # Override with Flow's routine_id
            if source_routine_id:
                conn_data["_source_routine_id"] = source_routine_id
            if target_routine_id:
                conn_data["_target_routine_id"] = target_routine_id
            
            connections_data.append(conn_data)
        
        data["connections"] = connections_data
        
        return data
    
    def deserialize(self, data: Dict[str, Any]) -> None:
        """Deserialize Flow, restoring all routines and connections.

        Args:
            data: Serialized data dictionary.
        """
        # First deserialize basic fields (excluding fields requiring special handling)
        basic_data = {k: v for k, v in data.items() if k not in ["routines", "connections", "job_state", "_type"]}
        
        # Handle job_state if present
        if "job_state" in data and data["job_state"]:
            from flowforge.job_state import JobState
            from datetime import datetime
            
            job_state_data = data["job_state"].copy()
            
            # Handle datetime
            if isinstance(job_state_data.get("created_at"), str):
                job_state_data["created_at"] = datetime.fromisoformat(job_state_data["created_at"])
            if isinstance(job_state_data.get("updated_at"), str):
                job_state_data["updated_at"] = datetime.fromisoformat(job_state_data["updated_at"])
            
            job_state = JobState()
            job_state.deserialize(job_state_data)
            basic_data["job_state"] = job_state
        
        # Call parent deserialize to handle basic fields
        super().deserialize(basic_data)
        
        # Restore concurrent execution related (if deserialized as concurrent mode, need to reinitialize)
        if self.execution_strategy == "concurrent":
            self._execution_lock = threading.Lock()
            self._dependency_graph = None
            self._active_futures = set()  # Initialize futures tracking set
            # Thread pool will be created when needed, not here
        
        # Restore routines
        if "routines" in data:
            routines_data = data["routines"]
            self.routines = {}
            
            # First pass: create all routine instances
            for routine_id, routine_data in routines_data.items():
                class_info = routine_data.get("_class_info", {})
                routine_class = load_routine_class(class_info)
                
                if routine_class:
                    # Create routine instance
                    routine = routine_class()
                    # Deserialize routine (excluding slots and events references)
                    routine.deserialize(routine_data)
                    self.routines[routine_id] = routine
                else:
                    # If class cannot be loaded, create a basic Routine instance
                    # But still try to restore slots and events
                    from flowforge.routine import Routine
                    routine = Routine()
                    routine._id = routine_data.get("_id", routine_id)
                    routine._stats = routine_data.get("_stats", {})
                    # Restore basic structure of slots and events
                    if "_slots" in routine_data:
                        from flowforge.slot import Slot
                        for slot_name, slot_data in routine_data["_slots"].items():
                            slot = Slot()
                            slot.name = slot_data.get("name", slot_name)
                            slot._data = slot_data.get("_data", {})
                            slot.merge_strategy = slot_data.get("merge_strategy", "override")
                            slot.routine = routine
                            if "_handler_metadata" in slot_data:
                                slot._handler_metadata = slot_data["_handler_metadata"]
                            routine._slots[slot_name] = slot
                    if "_events" in routine_data:
                        from flowforge.event import Event
                        for event_name, event_data in routine_data["_events"].items():
                            event = Event()
                            event.deserialize(event_data)
                            event.routine = routine
                            routine._events[event_name] = event
                    self.routines[routine_id] = routine
            
            # Second pass: restore slots' handlers and merge_strategy
            for routine_id, routine_data in routines_data.items():
                routine = self.routines.get(routine_id)
                if not routine:
                    continue
                
                # Restore slots' handlers
                if "_slots" in routine_data:
                    for slot_name, slot_data in routine_data["_slots"].items():
                        slot = routine._slots.get(slot_name)
                        if slot:
                            # Restore handler
                            if "_handler_metadata" in slot_data:
                                handler = deserialize_callable(
                                    slot_data["_handler_metadata"],
                                    {"routines": self.routines}
                                )
                                if handler:
                                    slot.handler = handler
                            
                            # Restore merge_strategy
                            if "_merge_strategy_metadata" in slot_data:
                                strategy = deserialize_callable(
                                    slot_data["_merge_strategy_metadata"],
                                    {"routines": self.routines}
                                )
                                if strategy:
                                    slot.merge_strategy = strategy
                            
                            # Clean up temporary data
                            if hasattr(slot, "_serialized_data"):
                                delattr(slot, "_serialized_data")
        
        # Restore connections
        if "connections" in data:
            from flowforge.connection import Connection
            
            self.connections = []
            
            for conn_data in data["connections"]:
                connection = Connection()
                connection.deserialize(conn_data)
                
                # Rebuild reference relationships
                source_routine_id = getattr(connection, "_source_routine_id", None)
                source_event_name = getattr(connection, "_source_event_name", None)
                target_routine_id = getattr(connection, "_target_routine_id", None)
                target_slot_name = getattr(connection, "_target_slot_name", None)
                
                if source_routine_id and source_event_name:
                    source_routine = self.routines.get(source_routine_id)
                    if source_routine:
                        source_event = source_routine.get_event(source_event_name)
                        if source_event:
                            connection.source_event = source_event
                
                if target_routine_id and target_slot_name:
                    target_routine = self.routines.get(target_routine_id)
                    if target_routine:
                        target_slot = target_routine.get_slot(target_slot_name)
                        if target_slot:
                            connection.target_slot = target_slot
                
                # If successfully rebuilt references, add to connections
                if connection.source_event and connection.target_slot:
                    # Establish bidirectional connection (if not already established)
                    if connection.target_slot not in connection.source_event.connected_slots:
                        connection.source_event.connect(connection.target_slot)
                    if connection.source_event not in connection.target_slot.connected_events:
                        connection.target_slot.connect(connection.source_event)
                    
                    self.connections.append(connection)
                    # Rebuild mapping
                    key = (connection.source_event, connection.target_slot)
                    self._event_slot_connections[key] = connection

