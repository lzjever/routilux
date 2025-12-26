"""
Serialization utility functions.

Used for serializing and deserializing Routine, Flow, and other objects.
"""
import importlib
import inspect
from typing import Dict, Any, Optional, Callable, Type


def serialize_callable(callable_obj: Optional[Callable]) -> Optional[Dict[str, Any]]:
    """Serialize a callable object (function or method).

    Args:
        callable_obj: Callable object to serialize.

    Returns:
        Serialized dictionary, or None if serialization is not possible.
    """
    if callable_obj is None:
        return None
    
    try:
        # Try to get function information
        if inspect.ismethod(callable_obj):
            # Method
            return {
                "_type": "method",
                "class_name": callable_obj.__self__.__class__.__name__,
                "method_name": callable_obj.__name__,
                "object_id": getattr(callable_obj.__self__, "_id", None)
            }
        elif inspect.isfunction(callable_obj):
            # Function
            module = inspect.getmodule(callable_obj)
            if module:
                return {
                    "_type": "function",
                    "module": module.__name__,
                    "name": callable_obj.__name__
                }
        elif inspect.isbuiltin(callable_obj):
            # Builtin function
            return {
                "_type": "builtin",
                "name": callable_obj.__name__
            }
    except Exception:
        pass
    
    return None


def deserialize_callable(callable_data: Optional[Dict[str, Any]], context: Optional[Dict[str, Any]] = None) -> Optional[Callable]:
    """Deserialize a callable object.

    Args:
        callable_data: Serialized callable object data.
        context: Context information (e.g., routine object dictionary).

    Returns:
        Callable object, or None if deserialization is not possible.
    """
    if callable_data is None:
        return None
    
    context = context or {}
    
    try:
        callable_type = callable_data.get("_type")
        
        if callable_type == "method":
            # Restore method
            class_name = callable_data.get("class_name")
            method_name = callable_data.get("method_name")
            object_id = callable_data.get("object_id")
            
            if object_id and "routines" in context:
                # Find object from context
                for routine in context["routines"].values():
                    if hasattr(routine, "_id") and routine._id == object_id:
                        if hasattr(routine, method_name):
                            return getattr(routine, method_name)
        
        elif callable_type == "function":
            # Restore function
            module_name = callable_data.get("module")
            function_name = callable_data.get("name")
            
            if module_name and function_name:
                module = importlib.import_module(module_name)
                if hasattr(module, function_name):
                    return getattr(module, function_name)
        
        elif callable_type == "builtin":
            # Builtin function
            name = callable_data.get("name")
            if name:
                return __builtins__.get(name)
    
    except Exception:
        pass
    
    return None


def get_routine_class_info(routine: Any) -> Dict[str, Any]:
    """Get class information for a Routine.

    Args:
        routine: Routine instance.

    Returns:
        Dictionary containing class information.
    """
    cls = routine.__class__
    return {
        "class_name": cls.__name__,
        "module": cls.__module__
    }


def load_routine_class(class_info: Dict[str, Any]) -> Optional[Type]:
    """Load Routine class from class information.

    Args:
        class_info: Dictionary containing class_name and module.

    Returns:
        Routine class, or None if loading fails.
    """
    try:
        module_name = class_info.get("module")
        class_name = class_info.get("class_name")
        
        if module_name and class_name:
            module = importlib.import_module(module_name)
            if hasattr(module, class_name):
                return getattr(module, class_name)
    except Exception:
        pass
    
    return None

