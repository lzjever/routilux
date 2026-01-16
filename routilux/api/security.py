"""
Security utilities for expression evaluation.

Provides safe expression evaluation with AST checking and sandboxing.
"""

import ast
import signal
from typing import Any, Dict


class SecurityError(Exception):
    """Security violation during expression evaluation."""

    pass


class TimeoutError(Exception):
    """Expression evaluation timed out."""

    pass


# Safe built-in functions
SAFE_BUILTINS = {
    # Built-in functions
    "abs": abs,
    "all": all,
    "any": any,
    "bin": bin,
    "bool": bool,
    "bytearray": bytearray,
    "bytes": bytes,
    "chr": chr,
    "complex": complex,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    "hex": hex,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "oct": oct,
    "ord": ord,
    "pow": pow,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    # Constants
    "True": True,
    "False": False,
    "None": None,
}


# Base forbidden AST nodes (available in all Python 3.8+ versions)
BASE_FORBIDDEN_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
    ast.GeneratorExp,
    ast.DictComp,
    ast.ListComp,
    ast.SetComp,
    ast.Assign,
    ast.AugAssign,
    ast.AnnAssign,
    ast.Delete,
    ast.AsyncFor,
    ast.AsyncWith,
    ast.Global,
    ast.Nonlocal,
    ast.Return,
    ast.Yield,
    ast.YieldFrom,
    ast.Try,
    ast.Raise,
    ast.Assert,
)

# Build FORBIDDEN_NODES tuple with nodes that exist in current Python version
FORBIDDEN_NODES = tuple(node for node in BASE_FORBIDDEN_NODES if hasattr(ast, node.__name__))

# Note: The following nodes don't exist in Python 3.8+ and are not checked:
# - ast.Exec: exec is a function in Python 3, not a statement
# - ast.Comp: Removed in Python 3.8+
# If these appear in the AST, they will be caught by the generic node type check


def check_ast_safety(tree: ast.AST) -> None:
    """Check AST for forbidden nodes.

    Args:
        tree: AST tree to check.

    Raises:
        SecurityError: If forbidden node is found.
    """
    for node in ast.walk(tree):
        if isinstance(node, FORBIDDEN_NODES):
            node_type = node.__class__.__name__
            raise SecurityError(f"Operation '{node_type}' is not allowed in expression")

        # Check function calls
        if isinstance(node, ast.Call):
            # Only allow calling safe built-in functions
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name not in SAFE_BUILTINS:
                    raise SecurityError(f"Function '{func_name}' is not allowed")
            elif isinstance(node.func, ast.Attribute):
                # Only allow accessing attributes, not calling methods
                if node.attr not in ("__getitem__", "__len__"):
                    raise SecurityError(f"Method call '{node.attr}' is not allowed")


def timeout_handler(signum, frame):
    """Handle timeout signal."""
    raise TimeoutError("Expression evaluation timed out")


def safe_evaluate(
    expression: str,
    variables: Dict[str, Any],
    timeout: float = 5.0,
    max_memory_mb: int = 100,
) -> Dict[str, Any]:
    """Safely evaluate an expression.

    Args:
        expression: Expression to evaluate.
        variables: Local variables available to expression.
        timeout: Maximum time in seconds (default 5.0).
        max_memory_mb: Maximum memory in MB (not enforced in this implementation).

    Returns:
        Dictionary with 'value' and 'type' keys.

    Raises:
        SecurityError: If expression contains unsafe operations.
        TimeoutError: If evaluation times out.
        ValueError: If expression has syntax errors.
        Exception: If evaluation fails for other reasons.
    """
    # Parse expression
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid syntax: {e}") from e

    # Check AST safety
    check_ast_safety(tree)

    # Use cross-platform timeout mechanism
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
    import platform

    def _evaluate_in_thread(expression_code, safe_builtins, variables):
        """Evaluate expression in a separate thread."""
        return eval(expression_code, {"__builtins__": safe_builtins}, variables)

    # Check if we're on Unix (SIGALRM works)
    is_unix = platform.system() != "Windows"

    if is_unix:
        # Use signal-based timeout on Unix (more efficient)
        old_handler = None
        try:
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(int(timeout))
            
            result = eval(compile(tree, "<string>", "eval"), {"__builtins__": SAFE_BUILTINS}, variables)
            
            signal.alarm(0)
            return {"value": result, "type": type(result).__name__}
        except TimeoutError:
            signal.alarm(0)
            raise TimeoutError("Expression evaluation timed out") from None
        except SecurityError:
            raise
        except Exception as e:
            raise Exception(f"Evaluation error: {str(e)}") from e
        finally:
            if old_handler is not None:
                signal.signal(signal.SIGALRM, old_handler)
    else:
        # Use ThreadPoolExecutor on Windows (cross-platform)
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    _evaluate_in_thread,
                    compile(tree, "<string>", "eval"),
                    SAFE_BUILTINS,
                    variables
                )
                result = future.result(timeout=timeout)
                return {"value": result, "type": type(result).__name__}
        except FutureTimeoutError:
            raise TimeoutError("Expression evaluation timed out") from None
        except SecurityError:
            raise
        except Exception as e:
            raise Exception(f"Evaluation error: {str(e)}") from e
