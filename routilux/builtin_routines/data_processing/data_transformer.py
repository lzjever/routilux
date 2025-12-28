"""
Data transformer routine.

Transforms data using configurable transformation functions.
"""

from __future__ import annotations
from typing import Any, Callable, Optional, List
from routilux.routine import Routine


class DataTransformer(Routine):
    """Routine for transforming data using configurable functions.

    This routine applies transformation functions to input data, useful
    for data cleaning, normalization, and format conversion.

    Features:
    - Configurable transformation functions
    - Chain multiple transformations
    - Support for custom transformation logic
    - Error handling and validation

    Examples:
        >>> transformer = DataTransformer()
        >>> transformer.set_config(
        ...     transformations=["lowercase", "strip_whitespace"]
        ... )
        >>> transformer.define_slot("input", handler=transformer.transform)
        >>> transformer.define_event("output", ["transformed_data", "transformation_applied"])
    """

    def __init__(self):
        """Initialize DataTransformer routine."""
        super().__init__()

        # Set default configuration
        self.set_config(
            transformations=[],  # List of transformation names or functions
            transformation_map={},  # Map of transformation names to functions
            chain_transformations=True,  # Apply transformations in sequence
        )

        # Register built-in transformations
        self._register_builtin_transformations()

        # Define input slot
        self.input_slot = self.define_slot("input", handler=self._handle_input)

        # Define output event
        self.output_event = self.define_event(
            "output", ["transformed_data", "transformation_applied", "errors"]
        )

    def _register_builtin_transformations(self):
        """Register built-in transformation functions."""
        builtins = {
            "lowercase": lambda x: str(x).lower() if isinstance(x, str) else x,
            "uppercase": lambda x: str(x).upper() if isinstance(x, str) else x,
            "strip_whitespace": lambda x: str(x).strip() if isinstance(x, str) else x,
            "to_string": lambda x: str(x),
            "to_int": lambda x: int(x) if isinstance(x, (int, float, str)) else x,
            "to_float": lambda x: float(x) if isinstance(x, (int, float, str)) else x,
            "remove_none": lambda x: (
                {k: v for k, v in x.items() if v is not None} if isinstance(x, dict) else x
            ),
        }

        # Get existing map or create new one
        current_map = self._config.get("transformation_map", {})
        current_map.update(builtins)
        self._config["transformation_map"] = current_map

    def _handle_input(self, data: Any = None, transformations: Optional[List] = None, **kwargs):
        """Handle input data and apply transformations.

        Args:
            data: Data to transform.
            transformations: Optional list of transformation names/functions.
                If not provided, uses _config["transformations"].
            **kwargs: Additional data from slot. If 'data' is not provided,
                will use kwargs or the first value.
        """
        # Extract data using Routine helper method
        data = self._extract_input_data(data, **kwargs)

        # Track statistics
        self._track_operation("transformations")

        # Get transformations from input or config
        transformations = transformations or self.get_config("transformations", [])
        transformation_map = self.get_config("transformation_map", {})

        transformed_data = data
        applied_transformations = []
        errors = []

        # Apply transformations
        for transform in transformations:
            try:
                if isinstance(transform, str):
                    # Look up transformation function
                    if transform in transformation_map:
                        transform_func = transformation_map[transform]
                        transformed_data = transform_func(transformed_data)
                        applied_transformations.append(transform)
                    else:
                        errors.append(f"Unknown transformation: {transform}")
                elif callable(transform):
                    # Direct function
                    transformed_data = transform(transformed_data)
                    applied_transformations.append(
                        transform.__name__ if hasattr(transform, "__name__") else "custom"
                    )
                else:
                    errors.append(f"Invalid transformation: {transform}")
            except Exception as e:
                errors.append(f"Error applying {transform}: {str(e)}")
                self._track_operation(
                    "transformation_errors", success=False, transform=str(transform), error=str(e)
                )

        # Emit result
        self.emit(
            "output",
            transformed_data=transformed_data,
            transformation_applied=applied_transformations,
            errors=errors if errors else None,
        )

    def register_transformation(self, name: str, func: Callable) -> None:
        """Register a custom transformation function.

        Args:
            name: Transformation name.
            func: Transformation function that takes data and returns transformed data.
        """
        transformation_map = self.get_config("transformation_map", {})
        transformation_map[name] = func
        self.set_config(transformation_map=transformation_map)
