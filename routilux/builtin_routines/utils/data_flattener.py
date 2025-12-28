"""
Data flattener routine.

Flattens nested data structures into flat dictionaries.
"""

from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
from routilux.routine import Routine
from serilux import Serializable


class DataFlattener(Routine):
    """Routine for flattening nested data structures.

    This routine converts nested dictionaries, lists, and Serializable
    objects into flat dictionaries with dot-notation keys.

    Features:
    - Recursive flattening of nested structures
    - Handles Serializable objects
    - Configurable separator for keys
    - Preserves list indices

    Examples:
        >>> flattener = DataFlattener()
        >>> flattener.set_config(separator=".")
        >>> flattener.define_slot("input", handler=flattener.flatten)
        >>> flattener.define_event("output", ["flattened_data"])

        >>> # Input: {"a": {"b": 1, "c": [2, 3]}}
        >>> # Output: {"a.b": 1, "a.c.0": 2, "a.c.1": 3}
    """

    def __init__(self):
        """Initialize DataFlattener routine."""
        super().__init__()

        # Set default configuration
        self.set_config(
            separator=".", preserve_lists=True, max_depth=100  # Prevent infinite recursion
        )

        # Define input slot
        self.input_slot = self.define_slot("input", handler=self._handle_input)

        # Define output event
        self.output_event = self.define_event(
            "output", ["flattened_data", "original_type", "depth"]
        )

    def _handle_input(self, data: Any = None, **kwargs):
        """Handle input data and flatten it.

        Args:
            data: Data to flatten (dict, list, or Serializable object).
            **kwargs: Additional data from slot. If 'data' is not provided,
                will use kwargs or the first value.
        """
        # Extract data using Routine helper method
        data = self._extract_input_data(data, **kwargs)

        # Track statistics
        self._track_operation("flattens")

        flattened_data, original_type, depth = self._flatten(data)

        # Emit result
        self.emit("output", flattened_data=flattened_data, original_type=original_type, depth=depth)

    def _flatten(
        self, value: Any, prefix: str = "", depth: int = 0, visited: Optional[set] = None
    ) -> Tuple[Dict[str, Any], str, int]:
        """Recursively flatten a value.

        Args:
            value: Value to flatten.
            prefix: Current key prefix.
            depth: Current recursion depth.
            visited: Set of visited object IDs to prevent circular references.

        Returns:
            Tuple of (flattened_dict, original_type, max_depth).
        """
        # Initialize visited set on first call
        if visited is None:
            visited = set()

        max_depth = depth
        separator = self.get_config("separator", ".")

        if depth >= self.get_config("max_depth", 100):
            # Prevent infinite recursion
            return {prefix or "value": str(value)}, type(value).__name__, depth

        # Prevent circular references for mutable types
        if isinstance(value, (dict, list)):
            obj_id = id(value)
            if obj_id in visited:
                return {prefix or "value": "[Circular Reference]"}, type(value).__name__, depth
            visited.add(obj_id)

        if isinstance(value, list):
            try:
                result = {}
                preserve_lists = self.get_config("preserve_lists", True)

                if preserve_lists:
                    for i, item in enumerate(value):
                        key = f"{prefix}{separator}{i}" if prefix else str(i)
                        flattened, _, item_depth = self._flatten(item, key, depth + 1, visited)
                        result.update(flattened)
                        max_depth = max(max_depth, item_depth)
                else:
                    # Flatten list items without indices
                    for item in value:
                        flattened, _, item_depth = self._flatten(item, prefix, depth + 1, visited)
                        result.update(flattened)
                        max_depth = max(max_depth, item_depth)

                return result, "list", max_depth
            finally:
                # Remove from visited set when done with this branch
                visited.discard(id(value))

        elif isinstance(value, dict):
            try:
                result = {}
                for key, val in value.items():
                    new_prefix = f"{prefix}{separator}{key}" if prefix else key
                    flattened, _, item_depth = self._flatten(val, new_prefix, depth + 1, visited)
                    result.update(flattened)
                    max_depth = max(max_depth, item_depth)

                return result, "dict", max_depth
            finally:
                # Remove from visited set when done with this branch
                visited.discard(id(value))

        elif isinstance(value, Serializable):
            # Serialize Serializable objects first
            serialized = value.serialize()
            return self._flatten(serialized, prefix, depth + 1, visited)

        else:
            # Primitive type
            key = prefix if prefix else "value"
            return {key: value}, type(value).__name__, depth
