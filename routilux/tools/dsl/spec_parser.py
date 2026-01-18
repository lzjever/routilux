"""
Specification parser for DSL.

Parses flow specifications from dictionaries and validates structure.
"""

import importlib
from typing import TYPE_CHECKING, Any, Dict, Type, Union

if TYPE_CHECKING:
    from routilux.core.routine import Routine  # noqa: F401


def parse_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Parse and validate flow specification.

    **DEPRECATED**: This function is no longer used by the DSL loader.
    The loader now delegates to ObjectFactory.load_flow_from_dsl() which
    enforces factory-only component usage.

    This function is kept for backward compatibility but should not be used
    in new code. Use ObjectFactory.load_flow_from_dsl() directly.

    Args:
        spec: Flow specification dictionary.

    Returns:
        Parsed and validated specification dictionary.

    Raises:
        ValueError: If specification is invalid.

    .. deprecated::
        Use ObjectFactory.load_flow_from_dsl() instead, which enforces
        factory-only component usage.
    """
    # Validate top-level structure
    if not isinstance(spec, dict):
        raise ValueError("Flow specification must be a dictionary")

    # Validate routines section
    if "routines" not in spec:
        raise ValueError("Flow specification must contain 'routines' section")

    if not isinstance(spec["routines"], dict):
        raise ValueError("'routines' must be a dictionary")

    # Parse routines - keep class as string (factory name), don't load class
    parsed_routines = {}
    for routine_id, routine_spec in spec["routines"].items():
        if not isinstance(routine_spec, dict):
            raise ValueError(f"Routine '{routine_id}' specification must be a dictionary")

        if "class" not in routine_spec:
            raise ValueError(f"Routine '{routine_id}' must specify 'class'")

        # Keep class as string (factory name) - don't load class dynamically
        # This maintains backward compatibility but doesn't use _load_class()
        parsed_routines[routine_id] = {
            "class": routine_spec["class"],  # Keep as string (factory name)
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

    **DEPRECATED**: This function is a security risk and should not be used.
    It uses dynamic class loading which can execute arbitrary code.

    All DSL loading now goes through ObjectFactory which enforces factory-only
    component usage. Use ObjectFactory.load_flow_from_dsl() instead.

    SECURITY WARNING: This function uses importlib.import_module() to dynamically
    load classes from user-provided string paths. This can execute arbitrary code
    if the spec comes from an untrusted source. This function is deprecated and
    should not be used in new code.

    Args:
        class_spec: Either a class object or a string path like "module.path.ClassName".

    Returns:
        Class object.

    Raises:
        ValueError: If class_spec is invalid or loaded class is not a Routine subclass.
        ImportError: If module cannot be imported.

    .. deprecated::
        Use ObjectFactory.load_flow_from_dsl() instead, which enforces
        factory-only component usage and eliminates security risks.
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
        from routilux.core.routine import Routine

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
