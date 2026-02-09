# routilux/cli/decorators.py
"""Decorator for registering routines with the factory."""

from typing import Callable, Optional

from routilux.core.routine import Routine
from routilux.tools.factory.factory import ObjectFactory
from routilux.tools.factory.metadata import ObjectMetadata


def register_routine(
    name: str,
    *,
    category: str = "user",
    tags: Optional[list[str]] = None,
    description: str = "",
    metadata: Optional[ObjectMetadata] = None,
) -> Callable:
    """Decorator to register a function as a routine.

    Creates a dynamic Routine subclass that wraps the function as the routine's logic.
    The routine is automatically registered with ObjectFactory.

    Args:
        name: Factory name for the routine (must be unique)
        category: Category for organization (default: "user")
        tags: Optional list of tags for discovery
        description: Human-readable description
        metadata: Optional ObjectMetadata (overrides other params if provided)

    Returns:
        The original function (unchanged)

    Raises:
        ValueError: If name is already registered

    Examples:
        >>> @register_routine("my_processor", category="processing", tags=["fast"])
        ... def my_logic(data, **kwargs):
        ...     return process(data)
    """
    def decorator(func: Callable) -> Callable:
        factory = ObjectFactory.get_instance()

        # Check if already registered
        if name in factory._registry:
            raise ValueError(f"Routine '{name}' is already registered")

        # Create metadata if not provided
        if metadata is None:
            docstring = func.__doc__.strip() if func.__doc__ else None
            metadata_obj = ObjectMetadata(
                name=name,
                description=description or docstring or "",
                category=category,
                tags=tags or []
            )
        else:
            metadata_obj = metadata

        # Create dynamic Routine subclass
        class _DynamicRoutine(Routine):
            """Dynamically created routine from function."""

            def setup(self):
                """Set up slots and events for the routine."""
                # Add default input slot
                self.add_slot("input")
                # Add default output event
                self.add_event("output")
                # Set the logic function
                self.set_logic(func)

        # Register the class with factory
        factory.register(name, _DynamicRoutine, metadata=metadata_obj)

        # Return original function unchanged
        return func

    return decorator


def auto_register_routine(
    cls: Optional[type[Routine]] = None,
    *,
    name: Optional[str] = None,
    category: str = "user",
    tags: Optional[list[str]] = None,
    description: str = "",
) -> type[Routine]:
    """Automatically register a Routine subclass with the factory.

    Use as a decorator on Routine classes:

        @auto_register_routine(name="my_processor")
        class MyProcessor(Routine):
            def setup(self):
                self.add_slot("input")
                self.add_event("output")

    Or without arguments (uses factory_name attribute):

        @auto_register_routine()
        class MyProcessor(Routine):
            factory_name = "my_processor"
            def setup(self):
                self.add_slot("input")

    Args:
        cls: Routine subclass to register (None if called with args)
        name: Factory name (uses class name or cls.factory_name if not provided)
        category: Category for organization
        tags: Optional list of tags
        description: Human-readable description

    Returns:
        The original class unchanged

    Examples:
        >>> @auto_register_routine()
        ... class MyProcessor(Routine):
        ...     factory_name = "my_processor"
        ...     def setup(self):
        ...         self.add_slot("input")
    """
    def decorator(c: type[Routine]) -> type[Routine]:
        factory = ObjectFactory.get_instance()

        # Determine factory name
        factory_name = name or getattr(c, "factory_name", c.__name__)

        # Create metadata if not in docstring
        docstring = c.__doc__.strip() if c.__doc__ else None
        metadata_obj = ObjectMetadata(
            name=factory_name,
            description=description or docstring or "",
            category=category,
            tags=tags or []
        )

        # Register the class
        factory.register(factory_name, c, metadata=metadata_obj)

        return c

    if cls is not None:
        # Called as @auto_register_routine without parentheses
        return decorator(cls)
    else:
        # Called as @auto_register_routine() with parentheses
        return decorator
