"""
Specification parser for DSL.

Parses flow specifications from dictionaries and validates structure.
"""

import importlib
from typing import TYPE_CHECKING, Any, Dict, Type, Union

if TYPE_CHECKING:
    from routilux.routine import Routine  # noqa: F401


def parse_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Parse and validate flow specification.

    Args:
        spec: Flow specification dictionary.

    Returns:
        Parsed and validated specification dictionary.

    Raises:
        ValueError: If specification is invalid.
    """
    # Validate top-level structure
    if not isinstance(spec, dict):
        raise ValueError("Flow specification must be a dictionary")

    # Validate routines section
    if "routines" not in spec:
        raise ValueError("Flow specification must contain 'routines' section")

    if not isinstance(spec["routines"], dict):
        raise ValueError("'routines' must be a dictionary")

    # Parse routines
    parsed_routines = {}
    for routine_id, routine_spec in spec["routines"].items():
        if not isinstance(routine_spec, dict):
            raise ValueError(f"Routine '{routine_id}' specification must be a dictionary")

        if "class" not in routine_spec:
            raise ValueError(f"Routine '{routine_id}' must specify 'class'")

        # Load routine class
        routine_class = _load_class(routine_spec["class"])
        parsed_routines[routine_id] = {
            "class": routine_class,
            "config": routine_spec.get("config", {}),
            "error_handler": routine_spec.get("error_handler"),
        }

    # Parse connections
    parsed_connections = []
    if "connections" in spec:
        if not isinstance(spec["connections"], list):
            raise ValueError("'connections' must be a list")

        for conn in spec["connections"]:
            if not isinstance(conn, dict):
                raise ValueError("Each connection must be a dictionary")

            if "from" not in conn or "to" not in conn:
                raise ValueError("Connection must specify 'from' and 'to'")

            parsed_connections.append(
                {
                    "from": conn["from"],
                    "to": conn["to"],
                    "param_mapping": conn.get("param_mapping"),
                }
            )

    # Parse execution settings
    parsed_execution = spec.get("execution", {})

    return {
        "flow_id": spec.get("flow_id"),
        "routines": parsed_routines,
        "connections": parsed_connections,
        "execution": parsed_execution,
    }


def _load_class(class_spec: Union[str, Type]) -> Type:
    """Load class from string path or return class object.

    Args:
        class_spec: Either a class object or a string path like "module.path.ClassName".

    Returns:
        Class object.
    """
    if isinstance(class_spec, type):
        return class_spec

    if not isinstance(class_spec, str):
        raise ValueError(
            f"Class specification must be a string or class object, got {type(class_spec)}"
        )

    # Parse module path and class name
    parts = class_spec.split(".")
    if len(parts) < 2:
        raise ValueError(
            f"Invalid class path: {class_spec}. Expected format: 'module.path.ClassName'"
        )

    module_path = ".".join(parts[:-1])
    class_name = parts[-1]

    try:
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)

        # Validate that the loaded class is a Routine subclass
        # Import here at runtime to avoid circular imports at module level
        from routilux.routine import Routine

        if not isinstance(cls, type):
            raise ValueError(
                f"Loaded object {class_spec} is not a class, it's {type(cls).__name__}"
            )

        if not issubclass(cls, Routine):
            raise ValueError(
                f"Class {class_spec} must be a subclass of Routine, "
                f"but it's a subclass of {cls.__bases__}"
            )

        return cls
    except (ImportError, AttributeError) as e:
        raise ValueError(f"Failed to load class {class_spec}: {e}") from e
