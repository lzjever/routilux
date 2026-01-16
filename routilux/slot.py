"""
Slot class.

Input slot for receiving data from other routines.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from routilux.event import Event
    from routilux.routine import Routine

from serilux import Serializable, register_serializable


@register_serializable
class Slot(Serializable):
    """Input slot for receiving data from other routines.

    A Slot represents an input point in a Routine that can receive data from
    connected Events in other routines. Slots enable many-to-many data reception:
    a slot can connect to multiple events, and an event can connect to multiple
    slots. When data arrives, it's merged with existing data and passed to a
    handler function.

    Key Concepts:
        - Slots are defined in routines using define_slot()
        - Slots connect to events via Flow.connect()
        - Data is received automatically when connected events are emitted
        - Data merging follows the configured merge_strategy
        - Handler functions process the merged data

    Merge Strategy Behavior:
        - "override" (default): Each new data completely replaces the previous
          data. The handler receives only the latest data. Best for stateless
          processing where only the most recent value matters.
          Example: Latest sensor reading, current configuration

        - "append": New data values are appended to lists. If a key doesn't
          exist, it's initialized as an empty list. If the existing value is not
          a list, it's converted to a list first. The handler receives the
          accumulated data each time. Best for aggregation scenarios.
          Example: Collecting multiple data points, building arrays

        - Custom function: A callable(old_data, new_data) -> merged_data.
          Allows custom merge logic like deep merging, averaging, or other
          domain-specific operations. Provides full control over merge behavior.

    Handler Function:
        The handler can accept data in two ways (auto-detected):
        1. handler(data) - receives merged data as a dictionary
        2. ``handler(**data)`` - receives unpacked keyword arguments

        Handler errors are caught and logged to JobState execution history,
        but don't stop flow execution (slot handlers are always error-tolerant).

    Important Notes:
        - The merge_strategy affects both what data is stored in self._data
          and what data is passed to the handler.
        - In concurrent execution, merge operations are not atomic.
          If multiple events send data simultaneously, race conditions may occur.
        - The handler is called immediately after each receive() with the
          merged data, not deferred until all data is collected.
        - Parameter mapping (from Flow.connect()) is applied before merging.

    Examples:
        Override strategy (default):
            >>> slot = routine.define_slot("input", handler=process, merge_strategy="override")
            >>> # Event emits {"value": 1} -> handler receives {"value": 1}
            >>> # Event emits {"value": 2} -> handler receives {"value": 2}
            >>> # slot._data is {"value": 2} (previous data replaced)

        Append strategy:
            >>> slot = routine.define_slot("input", handler=aggregate, merge_strategy="append")
            >>> # Event emits {"value": 1} -> handler receives {"value": [1]}
            >>> # Event emits {"value": 2} -> handler receives {"value": [1, 2]}
            >>> # slot._data is {"value": [1, 2]} (values accumulated)

        Custom merge function:
            >>> def custom_merge(old, new):
            ...     return {**old, **new, "merged_at": time.time()}
            >>> slot = routine.define_slot("input", handler=process, merge_strategy=custom_merge)
            >>> # Custom logic: deep merge with timestamp
    """

    def __init__(
        self,
        name: str = "",
        routine: Routine | None = None,
        handler: Callable | None = None,
        merge_strategy: str = "override",
    ):
        """Initialize Slot.

        Args:
            name: Slot name. Used to identify the slot within its parent routine.
            routine: Parent Routine object that owns this slot.
            handler: Handler function called when data is received. The function
                signature can be flexible:

                - If it accepts ``**kwargs``, all merged data is passed as keyword arguments
                - If it accepts a single 'data' parameter, the entire merged dict is passed
                - If it accepts a single parameter with a different name, the matching
                  value from merged data is passed, or the entire dict if no match
                - If it accepts multiple parameters, matching values are passed as kwargs

                If None, no handler is called when data is received.
            merge_strategy: Strategy for merging new data with existing data.
                Possible values:

                - "override" (default): New data completely replaces old data.
                  Each receive() call passes only the new data to the handler.
                  Use this when you only need the latest data.
                - "append": New values are appended to lists. Existing non-list
                  values are converted to lists first. The handler receives
                  accumulated data each time. Use this for aggregation scenarios.
                - Callable: A function(old_data: Dict, new_data: Dict) -> Dict
                  that implements custom merge logic. The function should return
                  the merged result. Use this for complex merge requirements like
                  deep merging, averaging, or domain-specific operations.

        Note:
            The merge_strategy determines how data accumulates in self._data and
            what data is passed to the handler. See the class docstring for
            detailed examples and behavior descriptions.
        """
        super().__init__()
        self.name: str = name
        self.routine: Routine = routine
        self.handler: Callable | None = handler
        self.merge_strategy: Any = merge_strategy
        self.connected_events: list[Event] = []
        self._data: dict[str, Any] = {}

        # Register serializable fields
        # handler and merge_strategy are automatically serialized if they're callables
        self.add_serializable_fields(["name", "_data", "handler", "merge_strategy"])

    def __repr__(self) -> str:
        """Return string representation of the Slot."""
        if self.routine:
            return f"Slot[{self.routine._id}.{self.name}]"
        else:
            return f"Slot[{self.name}]"

    def connect(self, event: Event, param_mapping: dict[str, str] | None = None) -> None:
        """Connect to an event.

        Args:
            event: Event object to connect to.
            param_mapping: Parameter mapping dictionary mapping event parameter names to slot parameter names.
        """
        if event not in self.connected_events:
            self.connected_events.append(event)
            # Bidirectional connection
            if self not in event.connected_slots:
                event.connected_slots.append(self)

    def disconnect(self, event: Event) -> None:
        """Disconnect from an event.

        Args:
            event: Event object to disconnect from.
        """
        if event in self.connected_events:
            self.connected_events.remove(event)
            # Bidirectional disconnection
            if self in event.connected_slots:
                event.connected_slots.remove(self)

    def receive(self, data: dict[str, Any], job_state=None, flow=None) -> None:
        """Receive data, merge with existing data, and call handler.

        This method is called automatically when a connected event is emitted.
        You typically don't call this directly - it's invoked by the event
        emission mechanism. However, you may call it directly for testing
        or manual data injection.

        Processing Steps:
            1. Merge new data with existing slot data according to merge_strategy
            2. Update slot's internal _data dictionary with merged result
            3. Call the handler function (if defined) with the merged data
            4. Handler receives data either as dict or unpacked kwargs (auto-detected)

        Handler Invocation:

        The handler is called immediately after merging. If the handler
        accepts ``**kwargs``, data is unpacked; otherwise it's passed as a dict.
        Errors in the handler are caught and logged to JobState execution history,
        but don't stop flow execution (slot handler errors are always tolerated).

        Args:
            data: Dictionary of data to receive. This is typically the data
                emitted by a connected event, possibly transformed by
                parameter mapping from the Connection.
                Example: {"result": "success", "count": 42}

        Examples:
            Manual data injection (for testing):
                >>> slot = routine.define_slot("input", handler=process_data)
                >>> slot.receive({"value": "test", "count": 1})
                >>> # Handler is called with merged data

            Automatic reception (normal usage):
                >>> # When connected event emits, receive() is called automatically
                >>> event.emit(flow=my_flow, value="data", count=5)
                >>> # Slot's receive() is called internally with {"value": "data", "count": 5}
        """
        # Merge new data with existing data according to merge_strategy
        # This updates self._data and returns the merged result
        merged_data = self._merge_data(data)

        # Set job_state in context variable for thread-safe access
        # ContextVar ensures each execution context has its own value
        from routilux.routine import _current_job_state

        old_job_state = None
        if job_state is not None:
            old_job_state = _current_job_state.get(None)
            _current_job_state.set(job_state)

        try:
            # Call handler with merged data if handler is defined
            if self.handler is not None:
                # Monitoring hook: Slot call (before handler execution)
                from routilux.monitoring.hooks import execution_hooks

                routine_id = None
                if flow and self.routine:
                    routine_id = flow._get_routine_id(self.routine)

                if routine_id and job_state and self.routine:
                    # Monitoring hook: Routine start
                    execution_hooks.on_routine_start(self.routine, routine_id, job_state)

                    # Check if should pause at routine start (breakpoint check)
                    if execution_hooks.should_pause_routine(
                        routine_id, job_state, None, merged_data
                    ):
                        from routilux.monitoring.registry import MonitoringRegistry

                        if MonitoringRegistry.is_enabled():
                            registry = MonitoringRegistry.get_instance()
                            debug_store = registry.debug_session_store
                            if debug_store:
                                session = debug_store.get_or_create(job_state.job_id)
                                context = self.routine.get_execution_context()
                                session.pause(context, reason=f"Breakpoint at routine {routine_id}")
                                # Wait for resume (with timeout to prevent indefinite hangs)
                                import time

                                max_wait = 60  # Maximum 60 seconds wait for resume (reduced from 1 hour)
                                start_wait = time.time()
                                while session.status == "paused":
                                    if time.time() - start_wait > max_wait:
                                        raise TimeoutError(
                                            f"Breakpoint wait timed out after {max_wait}s. "
                                            f"Routine: {routine_id}, Job: {job_state.job_id}"
                                        )
                                    # Check if job was cancelled or failed while waiting
                                    job_status = str(job_state.status)
                                    if job_status in ["cancelled", "failed"]:
                                        raise RuntimeError(
                                            f"Job {job_state.job_id} was {job_status} while waiting for breakpoint resume"
                                        )
                                    time.sleep(0.1)

                    # Check if should pause at slot call (breakpoint check)
                    if not execution_hooks.on_slot_call(self, routine_id, job_state, merged_data):
                        # Execution paused by breakpoint - wait for resume
                        from routilux.monitoring.registry import MonitoringRegistry

                        if MonitoringRegistry.is_enabled():
                            registry = MonitoringRegistry.get_instance()
                            debug_store = registry.debug_session_store
                            if debug_store:
                                session = debug_store.get(job_state.job_id)
                                if session and session.status == "paused":
                                    # Wait for resume (with timeout to prevent indefinite hangs)
                                    import time

                                    max_wait = 60  # Maximum 60 seconds wait for resume (reduced from 1 hour)
                                    start_wait = time.time()
                                    while session.status == "paused":
                                        if time.time() - start_wait > max_wait:
                                            raise TimeoutError(
                                                f"Breakpoint wait timed out after {max_wait}s. "
                                                f"Slot: {self.name}, Job: {job_state.job_id}"
                                            )
                                        # Check if job was cancelled or failed while waiting
                                        job_status = str(job_state.status)
                                        if job_status in ["cancelled", "failed"]:
                                            raise RuntimeError(
                                                f"Job {job_state.job_id} was {job_status} while waiting for breakpoint resume"
                                            )
                                        time.sleep(0.1)

                # Initialize error tracking (must be in outer scope)
                error_occurred = False
                error_exception = None

                try:
                    # Check for timeout
                    timeout = None
                    if self.routine:
                        timeout = self.routine.get_config("timeout")

                    # Critical fix: Validate timeout is numeric before using
                    if timeout is not None:
                        if not isinstance(timeout, (int, float)):
                            logging.getLogger(__name__).warning(
                                f"Invalid timeout value: {timeout} (type: {type(timeout)}). "
                                f"Timeout must be numeric. Ignoring timeout."
                            )
                            timeout = None
                        elif timeout <= 0 or timeout != timeout or not __import__('math').isfinite(timeout):  # NaN and infinity check
                            logging.getLogger(__name__).warning(
                                f"Invalid timeout value: {timeout}. "
                                f"Timeout must be positive and finite. Ignoring timeout."
                            )
                            timeout = None

                    # Execute handler with timeout if configured
                    if timeout:
                        from concurrent.futures import ThreadPoolExecutor
                        from concurrent.futures import TimeoutError as FuturesTimeoutError

                        def execute_handler():
                            import inspect

                            from routilux.routine import _current_job_state

                            # Set job_state in context variable for this thread
                            # This is necessary because ThreadPoolExecutor creates a new thread
                            # and ContextVar is thread-local
                            old_job_state = _current_job_state.get(None)
                            _current_job_state.set(job_state)

                            try:
                                sig = inspect.signature(self.handler)
                                params = list(sig.parameters.keys())

                                if self._is_kwargs_handler(self.handler):
                                    return self.handler(**merged_data)
                                elif len(params) == 1 and params[0] == "data":
                                    return self.handler(merged_data)
                                elif len(params) == 1:
                                    param_name = params[0]
                                    if param_name in merged_data:
                                        return self.handler(merged_data[param_name])
                                    else:
                                        return self.handler(merged_data)
                                else:
                                    matched_params = {}
                                    for param_name in params:
                                        if param_name in merged_data:
                                            matched_params[param_name] = merged_data[param_name]

                                    if matched_params:
                                        return self.handler(**matched_params)
                                    else:
                                        return self.handler(merged_data)
                            finally:
                                # Restore previous job_state in context variable
                                if old_job_state is not None:
                                    _current_job_state.set(old_job_state)
                                else:
                                    _current_job_state.set(None)

                        with ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(execute_handler)
                            try:
                                future.result(timeout=timeout)
                            except FuturesTimeoutError as e:
                                raise TimeoutError(
                                    f"Slot handler '{self.name}' in routine '{self.routine.__class__.__name__}' "
                                    f"exceeded timeout of {timeout} seconds"
                                ) from e
                    else:
                        # No timeout, execute normally
                        import inspect

                        sig = inspect.signature(self.handler)
                        params = list(sig.parameters.keys())

                        # If handler accepts **kwargs, pass all data directly
                        if self._is_kwargs_handler(self.handler):
                            self.handler(**merged_data)
                        elif len(params) == 1 and params[0] == "data":
                            # Handler only accepts one 'data' parameter, pass entire dictionary
                            self.handler(merged_data)
                        elif len(params) == 1:
                            # Handler only accepts one parameter, try to pass matching value
                            param_name = params[0]
                            if param_name in merged_data:
                                self.handler(merged_data[param_name])
                            else:
                                # If no matching parameter, pass entire dictionary
                                self.handler(merged_data)
                        else:
                            # Multiple parameters, try to match
                            matched_params = {}
                            for param_name in params:
                                if param_name in merged_data:
                                    matched_params[param_name] = merged_data[param_name]

                            if matched_params:
                                self.handler(**matched_params)
                            else:
                                # If no match, pass entire dictionary as first parameter
                                self.handler(merged_data)
                # Fix: Don't catch SystemExit or KeyboardInterrupt - these should propagate
                except (SystemExit, KeyboardInterrupt):
                    raise
                except Exception as e:
                    error_occurred = True
                    error_exception = e
                    # Record exception but don't interrupt flow
                    import logging

                    # Build enhanced error context
                    error_context = {
                        "routine": self.routine.__class__.__name__ if self.routine else "Unknown",
                        "slot": self.name,
                        "routine_id": None,
                        "job_id": job_state.job_id if job_state else None,
                        "data_keys": list(merged_data.keys())
                        if isinstance(merged_data, dict)
                        else str(type(merged_data)),
                    }

                    # Try to get routine_id from flow
                    if flow and self.routine:
                        error_context["routine_id"] = flow._get_routine_id(self.routine)
                    elif self.routine:
                        # Try to get flow from routine
                        routine_flow = getattr(self.routine, "_current_flow", None)
                        if routine_flow:
                            error_context["routine_id"] = routine_flow._get_routine_id(self.routine)

                    error_msg = (
                        f"Error in slot handler: {error_context['routine']}.{error_context['slot']}\n"
                        f"  Routine ID: {error_context['routine_id']}\n"
                        f"  Job ID: {error_context['job_id']}\n"
                        f"  Data keys: {error_context['data_keys']}\n"
                        f"  Error: {type(e).__name__}: {str(e)}"
                    )

                    logging.exception(error_msg)
                    # Errors are tracked in JobState execution history, not routine._stats
                    if job_state and self.routine:
                        # Try to get flow from parameter, then from routine
                        if flow is None:
                            flow = getattr(self.routine, "_current_flow", None)
                        if flow:
                            # Find routine_id in flow using flow._get_routine_id()
                            routine_id = flow._get_routine_id(self.routine)
                            if routine_id:
                                # Critical fix: Get error handler from routine first, fall back to flow error handler
                                error_handler = self.routine.get_error_handler()
                                if error_handler is None and hasattr(flow, 'error_handler'):
                                    error_handler = flow.error_handler

                                # Check if this is a RETRY strategy and we have flow/job_state context
                                # (indicating this was called from a task, not directly)
                                if (
                                    error_handler
                                    and error_handler.strategy.value == "retry"
                                    and flow
                                    and job_state
                                ):
                                    # For RETRY strategy in task context, create a temporary task
                                    # and call handle_task_error to trigger retry logic
                                    from routilux.flow.error_handling import handle_task_error
                                    from routilux.flow.task import SlotActivationTask, TaskPriority

                                    # Record error in execution history first (for tracking and testing)
                                    job_state.record_execution(
                                        routine_id, "error", {"slot": self.name, "error": str(e)}
                                    )

                                    # Create a temporary task with current retry_count from error_handler
                                    # Note: We use error_handler.retry_count as the initial retry_count
                                    # The handle_task_error will increment it and check against max_retries
                                    # Use original data (not merged_data) because retry will call _merge_data again
                                    temp_task = SlotActivationTask(
                                        slot=self,
                                        data=data,  # Use original data, not merged_data (retry will merge again)
                                        connection=None,  # Connection info not available here, but handle_task_error can work without it
                                        priority=TaskPriority.NORMAL,
                                        retry_count=error_handler.retry_count,  # Current retry count from error handler
                                        max_retries=error_handler.max_retries,
                                        job_state=job_state,
                                    )

                                    # Call handle_task_error to process retry logic
                                    # This will check retry_count, increment it, and enqueue retry task if needed
                                    handle_task_error(temp_task, e, flow)

                                    # handle_task_error handles the retry logic and will record error again
                                    # if max retries are reached, but we've already recorded the first error above
                                    return

                                # For non-RETRY strategies or direct calls (no flow/job_state), record error normally
                                job_state.record_execution(
                                    routine_id, "error", {"slot": self.name, "error": str(e)}
                                )

                                # If routine has error handler with STOP strategy, mark as failed immediately
                                if error_handler and error_handler.strategy.value == "stop":
                                    # STOP strategy: mark routine as failed immediately
                                    job_state.update_routine_state(
                                        routine_id, {"status": "failed", "error": str(e)}
                                    )
                                    # Critical fix: Also mark job_state as FAILED for STOP strategy
                                    # This ensures wait() and job status checks properly detect the failure
                                    from routilux.status import ExecutionStatus
                                    job_state.status = ExecutionStatus.FAILED

                # Monitoring hook: Routine end (after handler execution)
                if routine_id and job_state and self.routine:
                    from routilux.monitoring.hooks import execution_hooks

                    status = "failed" if error_occurred else "completed"
                    execution_hooks.on_routine_end(
                        self.routine, routine_id, job_state, status, error_exception
                    )
        finally:
            # Restore previous job_state in context variable
            from routilux.routine import _current_job_state

            if old_job_state is not None:
                _current_job_state.set(old_job_state)
            else:
                _current_job_state.set(None)

    def _merge_data(self, new_data: dict[str, Any]) -> dict[str, Any]:
        """Merge new data into existing data according to merge_strategy.

        This method implements the core merge logic based on the configured
        merge_strategy. It updates self._data with the merged result and
        returns the merged data to be passed to the handler.

        Merge Strategy Implementations:
            - "override": Completely replaces self._data with new_data.
              Previous data is discarded. This is the simplest and most
              common strategy, suitable when only the latest data matters.

            - "append": Accumulates values in lists. For each key in new_data:
              - If key doesn't exist in self._data: initialize as empty list
              - If existing value is not a list: convert to list [old_value]
              - Append new value to the list
              This allows collecting multiple data points over time.

            - Custom function: Calls the function with (self._data, new_data)
              and uses the return value. The function is responsible for:
              - Reading from self._data (old state)
              - Merging with new_data
              - Returning the merged result
              Note: The function should NOT modify self._data directly;
              this method will update it with the return value.

        Args:
            new_data: New data dictionary received from an event. This will be
                merged with the existing self._data according to merge_strategy.

        Returns:
            Merged data dictionary. This is what will be passed to the handler
            function. The format depends on the merge_strategy:
            - "override": Returns new_data (previous data discarded)
            - "append": Returns dict with lists containing accumulated values
            - Custom: Returns whatever the custom function returns

        Side Effects:
            Updates self._data with the merged result. This state persists
            across multiple receive() calls, allowing data accumulation.

        Examples:
            Override behavior:
                >>> slot._data = {"a": 1, "b": 2}
                >>> merged = slot._merge_data({"a": 10, "c": 3})
                >>> merged  # {"a": 10, "c": 3}
                >>> slot._data  # {"a": 10, "c": 3} (b is lost)

            Append behavior:
                >>> slot._data = {"a": 1}
                >>> merged = slot._merge_data({"a": 2, "b": 3})
                >>> merged  # {"a": [1, 2], "b": [3]}
                >>> slot._data  # {"a": [1, 2], "b": [3]}
                >>> merged = slot._merge_data({"a": 4})
                >>> merged  # {"a": [1, 2, 4], "b": [3]}
        """
        # Fix: Validate new_data type to prevent AttributeError
        if not isinstance(new_data, dict):
            new_data = {}

        if self.merge_strategy == "override":
            # Override strategy: new data completely replaces old data
            # Previous data in self._data is discarded
            # This is the default and most common strategy
            self._data = new_data.copy()
            return self._data

        elif self.merge_strategy == "append":
            # Append strategy: accumulate values in lists
            # This allows collecting multiple data points over time
            merged = {}
            for key, value in new_data.items():
                # Initialize as empty list if key doesn't exist
                if key not in self._data:
                    self._data[key] = []

                # Convert existing value to list if it's not already a list
                # This handles the case where first receive() had a non-list value
                if not isinstance(self._data[key], list):
                    self._data[key] = [self._data[key]]

                # Append new value to the list
                self._data[key].append(value)

                # Return the accumulated list for this key
                merged[key] = self._data[key]
            return merged

        elif callable(self.merge_strategy):
            # Custom merge function: delegate to user-provided function
            # The function receives (old_data, new_data) and should return merged result
            # Note: The function should not modify self._data directly
            merged_result = self.merge_strategy(self._data, new_data)

            # Update self._data with the merged result
            # This ensures state consistency for future merges
            self._data = merged_result.copy() if isinstance(merged_result, dict) else merged_result

            return merged_result

        else:
            # Fallback: treat unknown strategy as "override"
            # This handles cases where merge_strategy is set to an invalid value
            self._data = new_data.copy()
            return self._data

    def call_handler(self, data: dict[str, Any], propagate_exceptions: bool = False) -> None:
        """Call handler with data, optionally propagating exceptions.

        This method is used for entry routine trigger slots where exceptions
        need to propagate to Flow's error handling logic. It merges data
        according to merge_strategy and calls the handler with appropriate
        parameters.

        Args:
            data: Data dictionary to pass to handler. This will be merged
                with existing slot data according to merge_strategy.
            propagate_exceptions: If True, exceptions propagate to caller;
                if False, they are caught and logged (default: False).
                For entry routine trigger slots, set to True to allow
                Flow's error handling strategies to work.

        Raises:
            Exception: If propagate_exceptions is True and handler raises
                an exception, it will be re-raised.

        Examples:
            Entry routine trigger slot (exceptions propagate):
                >>> trigger_slot.call_handler(entry_params, propagate_exceptions=True)

            Normal slot handler (exceptions caught):
                >>> slot.call_handler(data, propagate_exceptions=False)
        """
        # Merge new data with existing data according to merge_strategy
        # This updates self._data and returns the merged result
        merged_data = self._merge_data(data)

        # Call handler with merged data if handler is defined
        if self.handler is not None:
            # Initialize error tracking
            error_occurred = False
            error_exception = None

            try:
                import inspect

                sig = inspect.signature(self.handler)
                params = list(sig.parameters.keys())

                # If handler accepts **kwargs, pass all data directly
                if self._is_kwargs_handler(self.handler):
                    self.handler(**merged_data)
                elif len(params) == 1 and params[0] == "data":
                    # Handler only accepts one 'data' parameter, pass entire dictionary
                    self.handler(merged_data)
                elif len(params) == 1:
                    # Handler only accepts one parameter, try to pass matching value
                    param_name = params[0]
                    if param_name in merged_data:
                        self.handler(merged_data[param_name])
                    else:
                        # If no matching parameter, pass entire dictionary
                        self.handler(merged_data)
                else:
                    # Multiple parameters, try to match
                    matched_params = {}
                    for param_name in params:
                        if param_name in merged_data:
                            matched_params[param_name] = merged_data[param_name]

                    if matched_params:
                        self.handler(**matched_params)
                    else:
                        # If no match, pass entire dictionary as first parameter
                        self.handler(merged_data)
            except Exception as e:
                error_occurred = True
                error_exception = e
                # Build enhanced error context for all errors
                import logging

                # Get context for error message
                job_state = None
                flow = None
                routine_id = None

                # Try to get job_state from context variable
                from routilux.routine import _current_job_state

                job_state = _current_job_state.get(None)

                # Try to get flow from routine
                if self.routine:
                    flow = getattr(self.routine, "_current_flow", None)
                    if flow:
                        routine_id = flow._get_routine_id(self.routine)

                # Build error context
                error_context = {
                    "routine": self.routine.__class__.__name__ if self.routine else "Unknown",
                    "slot": self.name,
                    "routine_id": routine_id,
                    "job_id": job_state.job_id if job_state else None,
                    "data_keys": list(merged_data.keys())
                    if isinstance(merged_data, dict)
                    else str(type(merged_data)),
                }

                error_msg = (
                    f"Error in slot handler: {error_context['routine']}.{error_context['slot']}\n"
                    f"  Routine ID: {error_context['routine_id']}\n"
                    f"  Job ID: {error_context['job_id']}\n"
                    f"  Data keys: {error_context['data_keys']}\n"
                    f"  Error: {type(e).__name__}: {str(e)}"
                )

                logging.exception(error_msg)

                if propagate_exceptions:
                    # Re-raise exception for entry routine trigger slots
                    # This allows Flow's error handling strategies to work
                    raise
                else:
                    # Record exception but don't interrupt flow (normal slot behavior)
                    # Errors are tracked in JobState execution history, not routine._stats
                    # Try to get job_state and flow from routine if available
                    if self.routine:
                        if job_state is None:
                            job_state = getattr(self.routine, "_job_state", None)
                        if flow is None:
                            flow = getattr(self.routine, "_current_flow", None)
                        if job_state and flow:
                            # Find routine_id in flow using flow._get_routine_id()
                            if routine_id is None:
                                routine_id = flow._get_routine_id(self.routine)
                                if routine_id:
                                    job_state.record_execution(
                                        routine_id, "error", {"slot": self.name, "error": str(e)}
                                    )

            # Monitoring hook: Routine end (after handler execution in call_handler)
            if self.routine:
                from routilux.routine import _current_job_state

                job_state = _current_job_state.get(None)
                if job_state:
                    flow = getattr(self.routine, "_current_flow", None)
                    if flow:
                        routine_id = flow._get_routine_id(self.routine)
                        if routine_id:
                            from routilux.monitoring.hooks import execution_hooks

                            status = "failed" if error_occurred else "completed"
                            execution_hooks.on_routine_end(
                                self.routine, routine_id, job_state, status, error_exception
                            )

    @staticmethod
    def _is_kwargs_handler(handler: Callable) -> bool:
        """Check if handler accepts **kwargs.

        Args:
            handler: Handler function.

        Returns:
            True if handler accepts **kwargs.
        """
        import inspect

        sig = inspect.signature(handler)
        for param in sig.parameters.values():
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                return True
        return False

    def serialize(self) -> dict[str, Any]:
        """Serialize Slot.

        Callables (handler, merge_strategy) are automatically handled by Serializable base class.

        Returns:
            Serialized dictionary.
        """
        # Let base class handle registered fields (name, _data, handler, merge_strategy)
        # Serializable automatically serializes callables
        data = super().serialize()

        # Note: _routine_id is NOT serialized here - it's Flow's responsibility
        # Flow will add routine_id when serializing routines

        return data

    def deserialize(self, data: dict[str, Any], registry: Any | None = None) -> None:
        """Deserialize Slot.

        Callables (handler, merge_strategy) are automatically handled by Serializable base class.

        Args:
            data: Serialized data dictionary.
            registry: Optional ObjectRegistry for deserializing callables.
        """
        # Let base class handle registered fields (name, _data, handler, merge_strategy)
        # Serializable automatically deserializes callables if registry is provided
        super().deserialize(data, registry=registry)

        # Handle legacy format: if merge_strategy was serialized as "_custom", restore it
        if hasattr(self, "merge_strategy") and self.merge_strategy == "_custom":
            # Try to restore from legacy metadata if present
            if hasattr(self, "_merge_strategy_metadata"):
                from serilux import deserialize_callable

                strategy = deserialize_callable(self._merge_strategy_metadata, registry=registry)
                if strategy:
                    self.merge_strategy = strategy
                delattr(self, "_merge_strategy_metadata")
            else:
                # Fallback to override if no metadata
                self.merge_strategy = "override"

        # Note: routine reference (routine_id) is restored by Routine.deserialize()
        # or Flow.deserialize(), not here - it's not Slot's responsibility
