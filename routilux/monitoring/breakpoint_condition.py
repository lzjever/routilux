"""
Breakpoint condition evaluator.

Safely evaluates Python expressions in breakpoint conditions with restricted
execution context for security.
"""

import ast
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from routilux.core.routine import ExecutionContext


def evaluate_condition(
    condition: str,
    context: Optional["ExecutionContext"] = None,
    variables: Optional[Dict[str, Any]] = None,
) -> bool:
    """Evaluate a breakpoint condition safely.

    This function evaluates Python expressions in a restricted context.
    Only basic operations and safe built-ins are allowed.

    Args:
        condition: Python expression to evaluate (e.g., "data.get('value') > 10").
        context: Execution context (provides access to flow, job_state, routine_id).
        variables: Local variables dictionary (e.g., data passed to slot handler).

    Returns:
        True if condition evaluates to True, False otherwise.

    Raises:
        ValueError: If condition is invalid or contains unsafe operations.
    """
    if not condition:
        return True

    # Build evaluation context with safe operations
    safe_builtins = {
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "type": type,
        "isinstance": isinstance,
        "hasattr": hasattr,
        "getattr": getattr,
    }

    eval_context: Dict[str, Any] = {
        "__builtins__": safe_builtins,
    }

    # Add variables from context
    # Critical fix: Validate that variables don't override safe builtins
    # This prevents security bypass via __builtins__ override
    if variables:
        for key, value in variables.items():
            # Prevent override of __builtins__ and other protected keys
            if key in ("__builtins__", "__import__", "__name__", "__file__"):
                raise ValueError(f"Cannot override protected variable: {key}")
            # Ensure value is safe (no callables that could escape sandbox)
            # BUT: Allow callables that are methods on built-in types (like dict.get)
            # We only block custom callables
            if callable(value) and key not in safe_builtins:
                # Check if it's a method on a built-in type (like dict.get, list.append)
                # These are safe because they operate on the object itself
                if hasattr(value, '__self__') and isinstance(value.__self__, (dict, list, tuple, str, int, float)):
                    # It's a method on a built-in type - allow it
                    eval_context[key] = value
                else:
                    # It's a custom callable - block it
                    raise ValueError(f"Custom callables not allowed in conditions: {key}")
            else:
                eval_context[key] = value

    # Add context variables
    if context:
        eval_context["job_state"] = context.job_state  # type: ignore[assignment]
        eval_context["flow"] = context.flow  # type: ignore[assignment]
        eval_context["routine_id"] = context.routine_id  # type: ignore[assignment]

        # Add shared data access
        if context.job_state:
            eval_context["shared_data"] = context.job_state.shared_data
            eval_context["config"] = {}  # Routine config would need to be passed separately

    try:
        # Parse and validate the expression
        tree = ast.parse(condition, mode="eval")

        # Check for unsafe operations
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Allow only safe function calls
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                    if func_name not in safe_builtins and func_name not in eval_context:
                        raise ValueError(f"Unsafe function call: {func_name}")
                # Method calls (e.g., data.get()) are allowed - they use ast.Attribute
                # which is not a direct function call

            # Disallow imports and other unsafe operations
            unsafe_nodes = [ast.Import, ast.ImportFrom, ast.Global]
            # ast.Exec was removed in Python 3.12, but we check for it if available
            if hasattr(ast, "Exec"):
                unsafe_nodes.append(ast.Exec)
            if isinstance(node, tuple(unsafe_nodes)):
                raise ValueError("Import and exec statements are not allowed in conditions")

        # Evaluate the expression
        result = eval(compile(tree, "<string>", "eval"), eval_context)

        # Convert to boolean
        return bool(result)

    except SyntaxError as e:
        raise ValueError(f"Invalid condition syntax: {e}") from e
    except ValueError as e:
        # Re-raise security violations
        if "Unsafe" in str(e) or "Import" in str(e):
            raise
        # Other ValueErrors are treated as False
        return False
    except (KeyError, AttributeError, TypeError, NameError):
        # These are expected errors for invalid data access or missing names
        # Return False (breakpoint doesn't trigger)
        return False
    except Exception as e:
        # For unexpected exceptions, log and return False
        # This should not happen for valid expressions, but we handle it gracefully
        import logging

        logging.debug(f"Unexpected exception in condition evaluation: {type(e).__name__}: {e}")
        return False
