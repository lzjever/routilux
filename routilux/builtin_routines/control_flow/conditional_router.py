"""
Conditional router routine.

Routes data to different outputs based on conditions.
"""

from __future__ import annotations
from typing import Dict, Any, Callable, Optional, Union
from routilux.routine import Routine
from serilux import (
    register_serializable,
    serialize_callable_with_fallback,
    deserialize_callable,
)


@register_serializable
class ConditionalRouter(Routine):
    """Routine for routing data based on conditions.

    This routine evaluates conditions on input data and routes it to
    different output events based on which conditions are met.

    Features:
        - Multiple conditional routes
        - Configurable condition functions, string expressions, or dictionaries
        - Default route for unmatched cases
        - Priority-based routing
        - Access to routine's config and stats in conditions
        - Full serialization support

    Condition Types:
        - **String expressions** (recommended): Fully serializable, can access
          ``data``, ``config``, and ``stats`` variables
        - **Dictionary conditions**: Field matching, fully serializable
        - **Function references**: Module-level functions, serializable if in module.
          Can accept ``data``, ``config``, and ``stats`` as parameters
        - **Lambda functions**: Can be used at runtime, may be converted to string
          expressions during serialization (if source code is available).
          Can access external variables via closure, but closure variables are lost
          during serialization

    Examples:
        Using string expressions with config access (recommended):
            >>> router = ConditionalRouter()
            >>> router.set_config(
            ...     routes=[
            ...         ("high", "data.get('value', 0) > config.get('threshold', 0)"),
            ...         ("low", "data.get('value', 0) <= config.get('threshold', 0)"),
            ...     ],
            ...     threshold=10
            ... )
            >>> router.input_slot.receive({"data": {"value": 15}})  # Routes to "high"

        Using string expressions with stats access:
            >>> router = ConditionalRouter()
            >>> router.set_config(
            ...     routes=[
            ...         ("active", "stats.get('count', 0) < 10"),
            ...         ("full", "stats.get('count', 0) >= 10"),
            ...     ]
            ... )
            >>> router.set_stat("count", 5)
            >>> router.input_slot.receive({"data": {}})  # Routes to "active"

        Using dictionary conditions:
            >>> router = ConditionalRouter()
            >>> router.set_config(
            ...     routes=[
            ...         ("high", {"priority": "high"}),
            ...         ("low", {"priority": "low"}),
            ...     ]
            ... )
            >>> router.input_slot.receive({"data": {"priority": "high"}})

        Using lambda functions (runtime only, serialization may fail):
            >>> threshold = 10
            >>> router = ConditionalRouter()
            >>> router.set_config(
            ...     routes=[
            ...         ("high", lambda data: data.get('value', 0) > threshold),
            ...     ]
            ... )
            >>> # Lambda works at runtime but may not serialize properly
    """

    def __init__(self):
        """Initialize ConditionalRouter routine."""
        super().__init__()

        # Set default configuration
        self.set_config(
            routes=[],  # List of (route_name, condition_func) tuples
            default_route=None,  # Default route name if no condition matches
            route_priority="first_match",  # "first_match" or "all_matches"
        )

        # Define input slot
        self.input_slot = self.define_slot("input", handler=self._handle_input)

        # Default output event (will be created dynamically)
        self.default_output = self.define_event("output", ["data", "route"])

    def _handle_input(self, data: Any = None, **kwargs):
        """Handle input data and route it.

        Args:
            data: Data to route.
            **kwargs: Additional data from slot. If 'data' is not provided,
                will use kwargs or the first value.
        """
        # Extract data using Routine helper method
        data = self._extract_input_data(data, **kwargs)

        # Track statistics
        self._track_operation("routes")

        routes = self.get_config("routes", [])
        default_route = self.get_config("default_route", None)
        route_priority = self.get_config("route_priority", "first_match")

        matched_routes = []

        # Evaluate conditions
        for route_name, condition in routes:
            try:
                if isinstance(condition, str):
                    # String expression condition
                    result = self._evaluate_string_condition(data, condition)
                    if result:
                        matched_routes.append(route_name)
                        if route_priority == "first_match":
                            break
                elif callable(condition):
                    # Function condition
                    # Pass data, config, and stats to the function if it accepts them
                    try:
                        import inspect

                        sig = inspect.signature(condition)
                        params = list(sig.parameters.keys())

                        # Check if function accepts config or stats
                        if len(params) == 1:
                            # Single parameter: assume it's data
                            result = condition(data)
                        elif len(params) == 2:
                            # Two parameters: try to pass data and config/stats
                            if "config" in params or "stats" in params:
                                # Pass both data and config/stats as keyword arguments
                                func_kwargs = {"data": data}
                                if "config" in params:
                                    func_kwargs["config"] = self._config
                                if "stats" in params:
                                    func_kwargs["stats"] = self._stats
                                result = condition(**func_kwargs)
                            else:
                                # Pass data as first positional arg, config as second
                                result = condition(data, self._config)
                        else:
                            # Multiple parameters: try to pass all as keyword arguments
                            func_kwargs = {}
                            if "data" in params:
                                func_kwargs["data"] = data
                            if "config" in params:
                                func_kwargs["config"] = self._config
                            if "stats" in params:
                                func_kwargs["stats"] = self._stats
                            if func_kwargs:
                                result = condition(**func_kwargs)
                            else:
                                # Fallback: just pass data
                                result = condition(data)
                    except Exception:
                        # Fallback: just pass data
                        result = condition(data)

                    if result:
                        matched_routes.append(route_name)
                        if route_priority == "first_match":
                            break
                elif isinstance(condition, dict):
                    # Dictionary-based condition (field matching)
                    if self._evaluate_dict_condition(data, condition):
                        matched_routes.append(route_name)
                        if route_priority == "first_match":
                            break
            except Exception as e:
                self._track_operation("routes", success=False, route=route_name, error=str(e))

        # Route data
        if matched_routes:
            for route_name in matched_routes:
                # Get or create event for this route
                event = self.get_event(route_name)
                if event is None:
                    event = self.define_event(route_name, ["data", "route"])

                self.emit(route_name, data=data, route=route_name)
                self.increment_stat(f"routes_to_{route_name}")
        else:
            # Use default route
            if default_route:
                event = self.get_event(default_route)
                if event is None:
                    event = self.define_event(default_route, ["data", "route"])
                self.emit(default_route, data=data, route=default_route)
                self.increment_stat(f"routes_to_{default_route}")
            else:
                # Emit to default output
                self.emit("output", data=data, route="unmatched")
                self.increment_stat("unmatched_routes")

    def _evaluate_dict_condition(self, data: Any, condition: Dict[str, Any]) -> bool:
        """Evaluate a dictionary-based condition.

        Args:
            data: Data to evaluate.
            condition: Condition dictionary with field -> expected_value mappings.

        Returns:
            True if condition matches, False otherwise.
        """
        if not isinstance(data, dict):
            return False

        for field, expected_value in condition.items():
            if field not in data:
                return False

            actual_value = data[field]

            # Support callable expected values (custom comparison)
            if callable(expected_value):
                if not expected_value(actual_value):
                    return False
            elif actual_value != expected_value:
                return False

        return True

    def _evaluate_string_condition(self, data: Any, condition: str) -> bool:
        """Evaluate a string expression condition.

        Args:
            data: Data to evaluate.
            condition: String expression to evaluate (e.g., "data.get('priority') == 'high'").

        Returns:
            True if condition matches, False otherwise.

        Note:
            The expression is evaluated in a restricted scope for security.
            Only basic operations and data access are allowed.

            The expression can access:
            - ``data``: The input data being evaluated
            - ``config``: The routine's configuration dictionary (``_config``)
            - ``stats``: The routine's statistics dictionary (``_stats``)

        Examples:
            Access config in condition:
                "data.get('value', 0) > config.get('threshold', 0)"

            Access stats in condition:
                "stats.get('count', 0) < 10"
        """
        try:
            # Restricted scope for safe evaluation
            safe_globals = {
                "__builtins__": {
                    "isinstance": isinstance,
                    "dict": dict,
                    "list": list,
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                    "len": len,
                    "getattr": getattr,
                    "hasattr": hasattr,
                }
            }
            # Provide data, config, and stats to the expression
            safe_locals = {
                "data": data,
                "config": self._config,
                "stats": self._stats,
            }

            result = eval(condition, safe_globals, safe_locals)
            return bool(result)
        except Exception:
            return False

    def serialize(self) -> Dict[str, Any]:
        """Serialize ConditionalRouter, handling lambda functions in routes.

        Callable conditions are automatically serialized using the serialization module's
        smart serialization with fallback to expression extraction.

        Returns:
            Serialized dictionary.
        """
        data = super().serialize()

        # Process routes configuration to serialize callable conditions
        routes = self.get_config("routes", [])
        serialized_routes = []

        for route_name, condition in routes:
            if callable(condition):
                # Use smart serialization with automatic fallback to expression extraction
                try:
                    condition_data = serialize_callable_with_fallback(
                        condition, owner=self, fallback_to_expression=True
                    )
                    serialized_routes.append((route_name, condition_data))
                except ValueError as e:
                    # Re-raise with route name context
                    raise ValueError(
                        f"Condition for route '{route_name}' cannot be serialized: {str(e)}"
                    ) from e
            else:
                # Non-callable (dict, str, etc.) - serialize directly
                serialized_routes.append((route_name, condition))

        # Update config in serialized data
        if "_config" in data:
            data["_config"]["routes"] = serialized_routes

        return data

    def deserialize(self, data: Dict[str, Any], registry: Optional[Any] = None) -> None:
        """Deserialize ConditionalRouter, restoring callable conditions from routes.

        Callable conditions are automatically deserialized by the serialization module,
        including support for lambda expressions.

        Args:
            data: Serialized dictionary.
            registry: Optional ObjectRegistry for deserializing callables.
        """
        super().deserialize(data, registry=registry)

        # Process routes configuration to restore callable conditions
        # Most callables are already deserialized by super().deserialize(), but we need
        # to handle lambda_expression format explicitly since it's stored in config
        routes = self.get_config("routes", [])
        deserialized_routes = []

        for route_name, condition_data in routes:
            # If already deserialized by super().deserialize(), use directly
            if callable(condition_data):
                deserialized_routes.append((route_name, condition_data))
                continue

            # Try to deserialize using the serialization module
            if isinstance(condition_data, dict) and "_type" in condition_data:
                condition = deserialize_callable(condition_data, registry=registry)
                if condition:
                    deserialized_routes.append((route_name, condition))
                else:
                    # If deserialization failed, check if it's a lambda_expression with error
                    if condition_data.get("_type") == "lambda_expression":
                        # deserialize_callable should have handled this, but if it failed,
                        # extract more information for error message
                        expr = condition_data.get("expression", "unknown")
                        raise ValueError(
                            f"Failed to deserialize lambda condition for route '{route_name}': "
                            f"cannot restore lambda expression '{expr}'. "
                            f"The expression may contain unsupported syntax or operations."
                        )
                    else:
                        # Extract more information for error message
                        callable_type = condition_data.get("callable_type") or condition_data.get(
                            "_type", "unknown"
                        )
                        module_name = condition_data.get("module", "unknown")
                        function_name = condition_data.get("name") or condition_data.get(
                            "method_name", "unknown"
                        )

                        raise ValueError(
                            f"Failed to deserialize {callable_type} condition for route '{route_name}': "
                            f"cannot restore {callable_type} '{function_name}' from module '{module_name}'. "
                            f"The function may not exist in the module or the module cannot be imported."
                        )
            else:
                # Non-serialized format (dict, str, etc.) - use directly
                deserialized_routes.append((route_name, condition_data))

        # Update config
        self.set_config(routes=deserialized_routes)

    def add_route(self, route_name: str, condition: Union[Callable, Dict[str, Any], str]) -> None:
        """Add a routing condition.

        Args:
            route_name: Name of the route (will be used as event name).
            condition: Condition function, dictionary, or string expression.
        """
        routes = self.get_config("routes", [])
        routes.append((route_name, condition))
        self.set_config(routes=routes)

        # Pre-create event for this route
        if self.get_event(route_name) is None:
            self.define_event(route_name, ["data", "route"])
