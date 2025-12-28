"""
Slot class.

Input slot for receiving data from other routines.
"""

from __future__ import annotations
from typing import Callable, Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from routilux.routine import Routine
    from routilux.event import Event

from serilux import register_serializable, Serializable


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

        Handler errors are caught and logged to routine._stats["errors"],
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
        routine: Optional["Routine"] = None,
        handler: Optional[Callable] = None,
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
        self.routine: "Routine" = routine
        self.handler: Optional[Callable] = handler
        self.merge_strategy: Any = merge_strategy
        self.connected_events: List["Event"] = []
        self._data: Dict[str, Any] = {}

        # Register serializable fields
        # handler and merge_strategy are automatically serialized if they're callables
        self.add_serializable_fields(["name", "_data", "handler", "merge_strategy"])

    def __repr__(self) -> str:
        """Return string representation of the Slot."""
        if self.routine:
            return f"Slot[{self.routine._id}.{self.name}]"
        else:
            return f"Slot[{self.name}]"

    def connect(self, event: "Event", param_mapping: Optional[Dict[str, str]] = None) -> None:
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

    def disconnect(self, event: "Event") -> None:
        """Disconnect from an event.

        Args:
            event: Event object to disconnect from.
        """
        if event in self.connected_events:
            self.connected_events.remove(event)
            # Bidirectional disconnection
            if self in event.connected_slots:
                event.connected_slots.remove(self)

    def receive(self, data: Dict[str, Any]) -> None:
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
        Errors in the handler are caught and logged to routine._stats["errors"],
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

        # Call handler with merged data if handler is defined
        if self.handler is not None:
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
                # Record exception but don't interrupt flow
                import logging

                logging.exception(f"Error in slot {self} handler: {e}")
                self.routine._stats.setdefault("errors", []).append(
                    {"slot": self.name, "error": str(e)}
                )

    def _merge_data(self, new_data: Dict[str, Any]) -> Dict[str, Any]:
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

    def serialize(self) -> Dict[str, Any]:
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

    def deserialize(self, data: Dict[str, Any], registry: Optional[Any] = None) -> None:
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
