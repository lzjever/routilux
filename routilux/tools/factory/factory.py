"""
Global Object Factory for creating Flow and Routine objects from prototypes.
"""

import threading
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Type, Union

from routilux.tools.factory.metadata import ObjectMetadata

if TYPE_CHECKING:
    from routilux.core.flow import Flow


class ObjectFactory:
    """Global factory for creating objects from registered prototypes.

    Supports both class-based and instance-based prototypes:
    - Class prototypes: Store the class, create new instances on demand
    - Instance prototypes: Store class + config/policy/logic, clone on demand

    Thread-safe singleton pattern.

    Examples:
        Register a class prototype:
            >>> factory = ObjectFactory.get_instance()
            >>> factory.register("data_processor", DataProcessor, description="Processes data")

        Register an instance prototype:
            >>> base = DataProcessor()
            >>> base.set_config(timeout=30)
            >>> base.set_activation_policy(immediate_policy())
            >>> factory.register("fast_processor", base, description="Fast processing")

        Create objects:
            >>> routine = factory.create("data_processor")
            >>> routine = factory.create("fast_processor", config={"timeout": 60})
    """

    _instance: Optional["ObjectFactory"] = None
    _lock = threading.Lock()

    def __init__(self):
        """Initialize factory (private - use get_instance())."""
        self._registry: Dict[str, Dict[str, Any]] = {}
        self._registry_lock = threading.RLock()
        # Reverse mapping from class to factory name for DSL export
        self._class_to_name: Dict[Type, str] = {}
        self._name_to_class: Dict[str, Type] = {}

    @classmethod
    def get_instance(cls) -> "ObjectFactory":
        """Get the global factory instance (singleton).

        Returns:
            ObjectFactory instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(
        self,
        name: str,
        prototype: Union[Type, Any],
        description: str = "",
        metadata: Optional[ObjectMetadata] = None,
    ) -> None:
        """Register a prototype (class or instance).

        Args:
            name: Unique name for the prototype.
            prototype: Class or instance to register.
            description: Human-readable description.
            metadata: Optional ObjectMetadata object. If provided, overrides description.

        Raises:
            ValueError: If name is already registered or prototype is invalid.
        """
        with self._registry_lock:
            if name in self._registry:
                raise ValueError(f"Prototype '{name}' is already registered")

            # Validate prototype is not None
            if prototype is None:
                raise ValueError("Prototype cannot be None")

            # Determine if prototype is a class or instance
            if isinstance(prototype, type):
                # Class prototype
                self._registry[name] = {
                    "type": "class",
                    "prototype": prototype,
                    "config": {},
                    "activation_policy": None,
                    "logic": None,
                    "error_handler": None,
                    "metadata": metadata or ObjectMetadata(name=name, description=description),
                }
                # Build reverse mapping
                self._class_to_name[prototype] = name
                self._name_to_class[name] = prototype
            else:
                # Instance prototype - extract class and configuration
                prototype_class = prototype.__class__

                # Check if it's a Flow - Flows need special handling (clone routines/connections)
                from routilux.core.flow import Flow

                if isinstance(prototype, Flow):
                    # For Flow instances, store the original instance for cloning
                    # We'll clone it when creating new instances
                    # Note: Flow doesn't have _config like Routine, so we don't extract it
                    self._registry[name] = {
                        "type": "instance",
                        "prototype": prototype_class,
                        "original_instance": prototype,  # Store original for cloning
                        "config": {},  # Flow doesn't use _config
                        "activation_policy": None,
                        "logic": None,
                        "error_handler": getattr(prototype, "error_handler", None),
                        "metadata": metadata or ObjectMetadata(name=name, description=description),
                    }
                    # Build reverse mapping
                    self._class_to_name[prototype_class] = name
                    self._name_to_class[name] = prototype_class
                else:
                    # Routine instance - extract config, policy, logic, slots, events
                    config = getattr(prototype, "_config", {}).copy()
                    activation_policy = getattr(prototype, "_activation_policy", None)
                    logic = getattr(prototype, "_logic", None)
                    error_handler = getattr(prototype, "_error_handler", None)
                    # Preserve slots and events for cloning
                    slots = getattr(prototype, "_slots", {}).copy()
                    events = getattr(prototype, "_events", {}).copy()

                    self._registry[name] = {
                        "type": "instance",
                        "prototype": prototype_class,
                        "config": config,
                        "activation_policy": activation_policy,
                        "logic": logic,
                        "error_handler": error_handler,
                        "slots": slots,
                        "events": events,
                        "metadata": metadata or ObjectMetadata(name=name, description=description),
                    }
                    # Build reverse mapping
                    self._class_to_name[prototype_class] = name
                    self._name_to_class[name] = prototype_class

    def create(
        self,
        name: str,
        config: Optional[Dict[str, Any]] = None,
        override_policy: Optional[Callable] = None,
        override_logic: Optional[Callable] = None,
    ) -> Any:
        """Create an object from a registered prototype.

        Args:
            name: Name of the registered prototype.
            config: Optional configuration dictionary to merge with prototype config.
            override_policy: Optional activation policy to override prototype policy.
            override_logic: Optional logic function to override prototype logic.

        Returns:
            New object instance (Routine or Flow).

        Raises:
            ValueError: If prototype is not found.
        """
        with self._registry_lock:
            if name not in self._registry:
                raise ValueError(
                    f"Prototype '{name}' not found. Available: {list(self._registry.keys())}"
                )

            proto = self._registry[name]
            proto_class = proto["prototype"]

            # Create instance based on prototype type
            if proto["type"] == "instance":
                # Check if we have an original Flow instance to clone
                if "original_instance" in proto:
                    # Flow instance prototype - clone it
                    from routilux.tools.factory.cloning import clone_flow

                    original_flow = proto["original_instance"]
                    instance = clone_flow(original_flow)
                else:
                    # Routine instance - create new and apply config
                    instance = proto_class()
                    instance._config = proto["config"].copy()

                    # Clone slots from prototype
                    if "slots" in proto:
                        for slot_name, slot in proto["slots"].items():
                            # Clone slot by redefining it with same parameters
                            from routilux.core.slot import Slot

                            cloned_slot = Slot(
                                slot.name,
                                instance,
                                max_queue_length=slot.max_queue_length,
                                watermark=slot.watermark,
                            )
                            instance._slots[slot_name] = cloned_slot

                    # Clone events from prototype
                    if "events" in proto:
                        for event_name, event in proto["events"].items():
                            # Clone event by redefining it with same parameters
                            from routilux.core.event import Event

                            cloned_event = Event(
                                event.name,
                                instance,
                                output_params=event.output_params.copy()
                                if event.output_params
                                else None,
                            )
                            instance._events[event_name] = cloned_event

                    # Apply prototype policy/logic if not overridden
                    if override_policy is None and proto.get("activation_policy"):
                        instance.set_activation_policy(proto["activation_policy"])
                    if override_logic is None and proto.get("logic"):
                        instance.set_logic(proto["logic"])
                    if proto.get("error_handler"):
                        instance.set_error_handler(proto["error_handler"])
            else:
                # Class prototype - just create instance
                instance = proto_class()

            # Merge override config (overrides prototype config)
            # Note: Flow doesn't have set_config, only Routine does
            if config and hasattr(instance, "set_config"):
                instance.set_config(**config)

            # Apply overrides (only for Routine)
            if override_policy and hasattr(instance, "set_activation_policy"):
                instance.set_activation_policy(override_policy)
            if override_logic and hasattr(instance, "set_logic"):
                instance.set_logic(override_logic)

            return instance

    def list_available(
        self, category: Optional[str] = None, object_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all available prototypes.

        Args:
            category: Optional category filter (e.g., 'data_generation', 'transformation').
            object_type: Optional object type filter. 'routine' or 'flow'.
                        If None, returns all objects.

        Returns:
            List of dictionaries with prototype information, including 'object_type' field
            that distinguishes between 'routine' and 'flow'.
        """
        with self._registry_lock:
            results = []
            for name, proto in self._registry.items():
                metadata = proto.get("metadata", ObjectMetadata(name=name))

                # Filter by category
                if category and metadata.category != category:
                    continue

                # Determine object type (routine or flow)
                prototype_class = proto.get("prototype")
                if prototype_class is None:
                    # Fallback: try to get from original_instance
                    original_instance = proto.get("original_instance")
                    if original_instance:
                        prototype_class = original_instance.__class__
                    else:
                        continue  # Skip if we can't determine type

                # Check if it's a Flow or Routine
                from routilux.core.flow import Flow
                from routilux.core.routine import Routine

                if issubclass(prototype_class, Flow):
                    detected_object_type = "flow"
                elif issubclass(prototype_class, Routine):
                    detected_object_type = "routine"
                else:
                    # Unknown type, skip or mark as unknown
                    detected_object_type = "unknown"

                # Filter by object_type
                if object_type and detected_object_type != object_type:
                    continue

                results.append(
                    {
                        "name": name,
                        "type": proto["type"],  # Prototype type: "class" or "instance"
                        "object_type": detected_object_type,  # Object type: "routine" or "flow"
                        "description": metadata.description,
                        "category": metadata.category,
                        "tags": metadata.tags,
                        "example_config": metadata.example_config,
                        "version": metadata.version,
                    }
                )
            return results

    def get_metadata(self, name: str) -> Optional[ObjectMetadata]:
        """Get metadata for a registered prototype.

        Args:
            name: Prototype name.

        Returns:
            ObjectMetadata or None if not found.
        """
        with self._registry_lock:
            if name not in self._registry:
                return None
            return self._registry[name].get("metadata")

    def unregister(self, name: str) -> None:
        """Unregister a prototype.

        Args:
            name: Prototype name to unregister.

        Raises:
            ValueError: If prototype is not found.
        """
        with self._registry_lock:
            if name not in self._registry:
                raise ValueError(f"Prototype '{name}' not found")
            # Remove from reverse mapping
            if name in self._name_to_class:
                class_obj = self._name_to_class[name]
                if class_obj in self._class_to_name:
                    del self._class_to_name[class_obj]
                del self._name_to_class[name]
            del self._registry[name]

    def clear(self) -> None:
        """Clear all registered prototypes."""
        with self._registry_lock:
            self._registry.clear()
            self._class_to_name.clear()
            self._name_to_class.clear()

    def get_factory_name(self, obj: Any) -> Optional[str]:
        """Get factory name for an object instance or class.

        This method enables reverse lookup from a routine/flow instance or class
        to its registered factory name. This is essential for DSL export.

        Args:
            obj: Routine or Flow instance, or class object.

        Returns:
            Factory name if the object/class is registered, None otherwise.

        Examples:
            >>> factory = ObjectFactory.get_instance()
            >>> factory.register("data_source", DataSource)
            >>> routine = factory.create("data_source")
            >>> factory.get_factory_name(routine)  # Returns "data_source"
            >>> factory.get_factory_name(DataSource)  # Returns "data_source"
        """
        with self._registry_lock:
            if isinstance(obj, type):
                # obj is a class
                return self._class_to_name.get(obj)
            else:
                # obj is an instance
                return self._class_to_name.get(obj.__class__)

    def export_flow_to_dsl(self, flow: "Flow", format: str = "dict") -> Union[Dict[str, Any], str]:
        """Export flow to DSL format using factory names.

        This method exports a flow to its DSL representation, using factory names
        instead of class paths. All routines in the flow must be registered in the
        factory for export to succeed.

        Args:
            flow: Flow instance to export.
            format: Output format: "dict", "yaml", or "json". Default: "dict".

        Returns:
            DSL representation:
            - If format="dict": Returns dictionary
            - If format="yaml": Returns YAML string
            - If format="json": Returns JSON string

        Raises:
            ValueError: If flow contains routines not registered in factory.

        Examples:
            >>> factory = ObjectFactory.get_instance()
            >>> factory.register("data_source", DataSource)
            >>> flow = Flow()
            >>> routine = factory.create("data_source")
            >>> flow.add_routine(routine, "source")
            >>> dsl_dict = factory.export_flow_to_dsl(flow)
            >>> dsl_yaml = factory.export_flow_to_dsl(flow, format="yaml")
        """
        from routilux.core.flow import Flow

        if not isinstance(flow, Flow):
            raise TypeError(f"Expected Flow instance, got {type(flow).__name__}")

        # Build DSL dictionary
        dsl_dict: Dict[str, Any] = {
            "flow_id": flow.flow_id,
            "routines": {},
            "connections": [],
            "execution": {
                "timeout": flow.execution_timeout,
            },
        }

        # Export routines using factory names
        for routine_id, routine in flow.routines.items():
            factory_name = self.get_factory_name(routine)
            if factory_name is None:
                raise ValueError(
                    f"Routine '{routine_id}' (class: {routine.__class__.__name__}) "
                    f"is not registered in factory. Cannot export to DSL. "
                    f"Please register the routine class in factory first."
                )

            routine_spec: Dict[str, Any] = {
                "class": factory_name,  # Use factory name, not class path
            }

            # Export config if present
            if hasattr(routine, "_config") and routine._config:
                routine_spec["config"] = routine._config.copy()

            # Export error handler if present
            if hasattr(routine, "get_error_handler"):
                error_handler = routine.get_error_handler()
                if error_handler:
                    routine_spec["error_handler"] = {
                        "strategy": error_handler.strategy.value,
                        "max_retries": error_handler.max_retries,
                        "retry_delay": error_handler.retry_delay,
                    }
                    if hasattr(error_handler, "retry_backoff") and error_handler.retry_backoff:
                        routine_spec["error_handler"]["retry_backoff"] = error_handler.retry_backoff
                    if hasattr(error_handler, "is_critical"):
                        routine_spec["error_handler"]["is_critical"] = error_handler.is_critical

            dsl_dict["routines"][routine_id] = routine_spec

        # Export connections
        for conn in flow.connections:
            # Check for None before accessing connection attributes
            if conn.source_event is None or conn.target_slot is None:
                continue  # Skip incomplete connections

            if conn.source_event.routine is None or conn.target_slot.routine is None:
                continue  # Skip connections with None routines

            source_routine_id = flow._get_routine_id(conn.source_event.routine)
            target_routine_id = flow._get_routine_id(conn.target_slot.routine)

            conn_spec = {
                "from": f"{source_routine_id}.{conn.source_event.name}",
                "to": f"{target_routine_id}.{conn.target_slot.name}",
            }
            dsl_dict["connections"].append(conn_spec)

        # Format conversion
        if format == "yaml":
            import yaml

            return yaml.dump(dsl_dict, default_flow_style=False)
        elif format == "json":
            import json

            return json.dumps(dsl_dict, indent=2)
        else:
            return dsl_dict

    def load_flow_from_dsl(self, dsl_dict: Dict[str, Any]) -> "Flow":
        """Load flow from DSL using only factory-registered components.

        This method creates a Flow from a DSL dictionary, using only components
        registered in the factory. This enforces security and portability by
        preventing dynamic class loading.

        Args:
            dsl_dict: DSL dictionary with structure:
                {
                    "flow_id": "optional_flow_id",
                    "routines": {
                        "routine_id": {
                            "class": "factory_name",  # Must be factory name
                            "config": {...},
                            "error_handler": {...}
                        }
                    },
                    "connections": [
                        {"from": "r1.output", "to": "r2.input"}
                    ],
                    "execution": {
                        "timeout": 300.0
                    }
                }

        Returns:
            Flow instance created from DSL.

        Raises:
            ValueError: If DSL references unregistered components or is invalid.

        Examples:
            >>> factory = ObjectFactory.get_instance()
            >>> factory.register("data_source", DataSource)
            >>> dsl = {
            ...     "flow_id": "my_flow",
            ...     "routines": {
            ...         "source": {"class": "data_source", "config": {}}
            ...     },
            ...     "connections": []
            ... }
            >>> flow = factory.load_flow_from_dsl(dsl)
        """
        from routilux.core.error import ErrorHandler, ErrorStrategy
        from routilux.core.flow import Flow
        from routilux.core.routine import Routine

        # Validate DSL structure
        if not isinstance(dsl_dict, dict):
            raise ValueError("DSL must be a dictionary")

        # Create flow
        flow_id = dsl_dict.get("flow_id")
        flow = Flow(flow_id=flow_id)

        # Validate and load routines
        routines = dsl_dict.get("routines")
        if not isinstance(routines, dict):
            raise ValueError("DSL must contain a 'routines' dictionary with routine definitions")

        for routine_id, routine_spec in routines.items():
            if not isinstance(routine_spec, dict):
                raise ValueError(f"Routine '{routine_id}' specification must be a dictionary")

            # Get factory name (required)
            factory_name = routine_spec.get("class")
            if not factory_name:
                raise ValueError(
                    f"Routine '{routine_id}' must specify 'class' field with factory name"
                )

            if not isinstance(factory_name, str):
                raise ValueError(
                    f"Routine '{routine_id}' 'class' field must be a string (factory name), "
                    f"got {type(factory_name).__name__}"
                )

            # Validate factory name exists
            if factory_name not in self._registry:
                available = list(self._registry.keys())
                raise ValueError(
                    f"Routine '{routine_id}' references unregistered factory name '{factory_name}'. "
                    f"Available factory names: {available}"
                )

            # Create routine from factory
            config = routine_spec.get("config")
            if config is not None and not isinstance(config, dict):
                raise ValueError(
                    f"Config for routine '{routine_id}' must be a dictionary, "
                    f"got {type(config).__name__}"
                )

            routine = self.create(factory_name, config=config)

            # Validate it's a Routine instance
            if not isinstance(routine, Routine):
                raise ValueError(
                    f"Factory '{factory_name}' created {type(routine).__name__}, "
                    f"but expected Routine instance for routine '{routine_id}'"
                )

            # Apply error handler if specified
            error_handler_spec = routine_spec.get("error_handler")
            if error_handler_spec:
                if isinstance(error_handler_spec, dict):
                    strategy_str = error_handler_spec.get("strategy", "stop")
                    try:
                        strategy = ErrorStrategy[strategy_str.upper()]
                    except KeyError:
                        strategy = ErrorStrategy.STOP

                    handler = ErrorHandler(
                        strategy=strategy,
                        max_retries=error_handler_spec.get("max_retries"),
                        retry_delay=error_handler_spec.get("retry_delay"),
                        retry_backoff=error_handler_spec.get("retry_backoff"),
                        is_critical=error_handler_spec.get("is_critical", False),
                    )
                    routine.set_error_handler(handler)
                elif isinstance(error_handler_spec, ErrorHandler):
                    routine.set_error_handler(error_handler_spec)
                else:
                    raise ValueError(
                        f"Error handler for routine '{routine_id}' must be a dictionary or ErrorHandler instance"
                    )

            flow.add_routine(routine, routine_id)

        # Load connections
        connections = dsl_dict.get("connections", [])
        if not isinstance(connections, list):
            raise ValueError("'connections' must be a list in DSL")

        for conn in connections:
            if not isinstance(conn, dict):
                raise ValueError(f"Each connection must be a dictionary, got {type(conn).__name__}")

            if "from" not in conn or "to" not in conn:
                raise ValueError("Connection must specify 'from' and 'to' keys")

            from_path = conn["from"].split(".")
            to_path = conn["to"].split(".")

            if len(from_path) != 2 or len(to_path) != 2:
                raise ValueError(
                    f"Invalid connection format: {conn['from']} -> {conn['to']}. "
                    f"Expected 'routine_id.event_name' -> 'routine_id.slot_name'"
                )

            # Validate path segments are non-empty
            if not all(from_path) or not all(to_path):
                raise ValueError(
                    f"Connection path cannot contain empty segments: {conn['from']} -> {conn['to']}"
                )

            source_id = from_path[0]
            source_event = from_path[1]
            target_id = to_path[0]
            target_slot = to_path[1]

            # Validate routine IDs exist
            if source_id not in flow.routines:
                raise ValueError(f"Connection source routine '{source_id}' not found in flow")
            if target_id not in flow.routines:
                raise ValueError(f"Connection target routine '{target_id}' not found in flow")

            flow.connect(source_id, source_event, target_id, target_slot)

        # Apply execution settings
        execution = dsl_dict.get("execution", {})
        if isinstance(execution, dict) and "timeout" in execution:
            timeout = execution["timeout"]
            if isinstance(timeout, (int, float)) and timeout > 0:
                flow.execution_timeout = timeout

        return flow
