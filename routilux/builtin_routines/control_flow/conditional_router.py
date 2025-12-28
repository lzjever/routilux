"""
Conditional router routine.

Routes data to different outputs based on conditions.
"""

from __future__ import annotations
from typing import Dict, Any, Callable, Optional, Union
import inspect
import warnings
from routilux.routine import Routine
from routilux.serialization_utils import serialize_callable, deserialize_callable


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

    def _extract_lambda_expression(self, source: str) -> Optional[str]:
        """Extract lambda expression from source code.

        Args:
            source: Source code string (e.g., "f = lambda x: x.get('priority') == 'high'").

        Returns:
            Lambda expression string (e.g., "x.get('priority') == 'high'"), or None if extraction fails.
        """
        # Find lambda keyword
        lambda_pos = source.find("lambda")
        if lambda_pos == -1:
            return None

        # Find the colon after lambda
        colon_pos = source.find(":", lambda_pos)
        if colon_pos == -1:
            return None

        # Extract expression after colon
        expr = source[colon_pos + 1 :].strip()

        # Remove trailing comma or semicolon if present
        expr = expr.rstrip(",;")

        return expr

    def serialize(self) -> Dict[str, Any]:
        """Serialize ConditionalRouter, handling lambda functions in routes.

        Returns:
            Serialized dictionary.
        """
        data = super().serialize()

        # Process routes configuration to serialize callable conditions
        routes = self.get_config("routes", [])
        serialized_routes = []

        for route_name, condition in routes:
            if callable(condition):
                # For lambda functions, always try to convert to string expression first
                # (even if serialize_callable can serialize it, lambda cannot be deserialized)
                if condition.__name__ == "<lambda>":
                    try:
                        source = inspect.getsource(condition)
                        lambda_expr = self._extract_lambda_expression(source)
                        if lambda_expr:
                            serialized_routes.append(
                                (
                                    route_name,
                                    {"_type": "lambda_expression", "expression": lambda_expr},
                                )
                            )
                        else:
                            warnings.warn(
                                f"Lambda condition for route '{route_name}' cannot be serialized. "
                                f"Consider using string expression or function reference instead."
                            )
                            # Skip this route
                            continue
                    except (OSError, TypeError) as e:
                        # Cannot get source (e.g., dynamically created lambda)
                        warnings.warn(
                            f"Lambda condition for route '{route_name}' cannot be serialized: {e}. "
                            f"Consider using string expression or function reference instead."
                        )
                        continue
                else:
                    # Non-lambda callable - try to serialize normally
                    condition_data = serialize_callable(condition)
                    if condition_data:
                        # Function can be serialized (module function, method, builtin)
                        serialized_routes.append((route_name, condition_data))
                    else:
                        # Other non-serializable callable
                        warnings.warn(
                            f"Condition for route '{route_name}' cannot be serialized. "
                            f"Consider using string expression or function reference instead."
                        )
                        continue
            else:
                # Non-callable (dict, str, etc.) - serialize directly
                serialized_routes.append((route_name, condition))

        # Update config in serialized data
        if "_config" in data:
            data["_config"]["routes"] = serialized_routes

        return data

    def deserialize(self, data: Dict[str, Any]) -> None:
        """Deserialize ConditionalRouter, restoring callable conditions from routes.

        Args:
            data: Serialized dictionary.
        """
        super().deserialize(data)

        # Process routes configuration to restore callable conditions
        routes = self.get_config("routes", [])
        deserialized_routes = []

        for route_name, condition_data in routes:
            if isinstance(condition_data, dict) and "_type" in condition_data:
                condition_type = condition_data.get("_type")

                if condition_type == "lambda_expression":
                    # Restore lambda expression
                    expr = condition_data.get("expression")
                    if expr:
                        try:
                            # Replace common lambda parameter names with 'data'
                            # This handles cases where lambda uses 'x', 'item', etc.
                            import re as re_module

                            # Replace standalone variable names (not part of method calls)
                            # Pattern: word boundary + common param names + word boundary
                            expr = re_module.sub(r"\b(x|item|value|obj)\b", "data", expr)

                            # Safe evaluation to restore lambda
                            safe_globals = {
                                "__builtins__": {
                                    "isinstance": isinstance,
                                    "dict": dict,
                                    "list": list,
                                    "str": str,
                                    "int": int,
                                    "float": float,
                                    "bool": bool,
                                }
                            }
                            condition = eval(f"lambda data: {expr}", safe_globals)
                            deserialized_routes.append((route_name, condition))
                        except Exception as e:
                            warnings.warn(
                                f"Failed to deserialize lambda condition for route '{route_name}': {e}"
                            )
                            continue
                    else:
                        warnings.warn(
                            f"Missing expression in lambda condition for route '{route_name}'"
                        )
                        continue
                elif condition_type in ["function", "method", "builtin"]:
                    # Restore function reference
                    condition = deserialize_callable(condition_data)
                    if condition:
                        deserialized_routes.append((route_name, condition))
                    else:
                        warnings.warn(
                            f"Failed to deserialize function condition for route '{route_name}'"
                        )
                        continue
                else:
                    # Other serialized type, use as-is
                    deserialized_routes.append((route_name, condition_data))
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
