from typing import Any, Dict, List, Optional
import inspect


class SerializableRegistry:
    """Registry for serializable classes to facilitate class lookup and instantiation."""

    registry = {}

    @classmethod
    def register_class(cls, class_name: str, class_ref: type):
        """Register a class for serialization purposes by adding it to the registry.

        Args:
            class_name: The name of the class to register.
            class_ref: A reference to the class being registered.
        """
        cls.registry[class_name] = class_ref

    @classmethod
    def get_class(cls, class_name: str):
        """Retrieve a class reference from the registry by its name.

        Args:
            class_name: The name of the class to retrieve.

        Returns:
            The class reference if found, None otherwise.
        """
        return cls.registry.get(class_name)


def register_serializable(cls):
    """Decorator to register a class as serializable in the registry.

    This decorator ensures that the class can be instantiated without arguments,
    which is required for proper deserialization. It validates that __init__
    either accepts no parameters (except self) or all parameters have default values.

    Args:
        cls: Class to be registered.

    Returns:
        The same class with registration completed.

    Raises:
        TypeError: If the class cannot be initialized without arguments.
            This happens when __init__ has required parameters (without defaults)
            other than 'self'. For Routine subclasses, use _config dictionary
            instead of constructor parameters.

    Note:
        For Routine subclasses, all configuration should be stored in _config
        dictionary and set after object creation, not passed as constructor
        parameters. This ensures proper serialization/deserialization support.
    """
    init_signature = inspect.signature(cls.__init__)
    parameters = init_signature.parameters.values()

    for param in parameters:
        if (
            param.name != "self"
            and param.default == inspect.Parameter.empty
            and param.kind != inspect.Parameter.VAR_KEYWORD
            and param.kind != inspect.Parameter.VAR_POSITIONAL
        ):
            error_message = (
                f"Error: {cls.__name__} cannot be initialized without parameters. "
                f"Serializable classes must support initialization with no arguments.\n"
                f"For Routine subclasses, use _config dictionary instead of constructor parameters.\n"
                f"Example: routine.set_config(key=value) or routine._config['key'] = value"
            )
            print(error_message)
            raise TypeError(error_message)
    SerializableRegistry.register_class(cls.__name__, cls)
    return cls


class Serializable:
    """A base class for objects that can be serialized and deserialized."""

    def __init__(self) -> None:
        """Initialize a serializable object with no specific fields."""
        self.fields_to_serialize = []

    def add_serializable_fields(self, fields: List[str]) -> None:
        """Add field names to the list that should be included in serialization.

        Args:
            fields: List of field names to be serialized.

        Raises:
            ValueError: If any provided field is not a string.
        """
        if not all(isinstance(field, str) for field in fields):
            raise ValueError("All fields must be strings")
        self.fields_to_serialize.extend(fields)
        self.fields_to_serialize = list(set(self.fields_to_serialize))

    def remove_serializable_fields(self, fields: List[str]) -> None:
        """Remove field names from the list that should be included in serialization.

        Args:
            fields: List of field names to be removed.
        """
        self.fields_to_serialize = [
            x for x in self.fields_to_serialize if x not in fields
        ]

    def serialize(self) -> Dict[str, Any]:
        """Serialize the object to a dictionary.

        Returns:
            Dictionary containing all serializable fields.
        """
        data = {"_type": type(self).__name__}
        for field in self.fields_to_serialize:
            value = getattr(self, field, None)
            if isinstance(value, Serializable):
                data[field] = value.serialize()
            elif isinstance(value, list):
                data[field] = [
                    item.serialize() if isinstance(item, Serializable) else item
                    for item in value
                ]
            elif isinstance(value, dict):
                data[field] = {
                    k: v.serialize() if isinstance(v, Serializable) else v
                    for k, v in value.items()
                }
            else:
                data[field] = value
        return data

    def deserialize(self, data: Dict[str, Any]) -> None:
        """Deserialize the object from a dictionary, restoring its state.

        Args:
            data: Dictionary containing all serializable fields.
        """
        for key, value in data.items():
            if key == "_type":
                continue
            if isinstance(value, dict):
                if "_type" in value:
                    attr_class = SerializableRegistry.get_class(value["_type"])
                    if attr_class:
                        attr: Serializable = attr_class()
                        attr.deserialize(value)
                    else:
                        attr = {
                            k: Serializable.deserialize_item(v)
                            for k, v in value.items()
                        }
                else:
                    attr = {
                        k: Serializable.deserialize_item(v) for k, v in value.items()
                    }
            elif isinstance(value, list):
                attr = [Serializable.deserialize_item(item) for item in value]
            else:
                attr = value
            setattr(self, key, attr)

    @staticmethod
    def deserialize_item(item: Dict[str, Any]) -> Any:
        """Deserialize an item.

        Args:
            item: Item to deserialize.

        Returns:
            Deserialized item.
        """
        if isinstance(item, dict):
            if "_type" in item:
                attr_class = SerializableRegistry.get_class(item["_type"])
                if not attr_class:
                    return {
                        k: Serializable.deserialize_item(v) for k, v in item.items()
                    }
                else:
                    obj: Serializable = attr_class()
                    obj.deserialize(item)
                    return obj
            else:
                return {k: Serializable.deserialize_item(v) for k, v in item.items()}
        elif isinstance(item, list):
            return [Serializable.deserialize_item(item) for item in item]
        else:
            return item

