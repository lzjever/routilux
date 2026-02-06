"""
Routine analyzer module.

Analyzes routine Python files using AST to generate structured descriptions.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any


class RoutineAnalyzer:
    """Analyzer for routine Python files using AST parsing.

    This class analyzes routine Python files to extract:
    - Routine class definitions
    - Slots (input mechanisms)
    - Events (output mechanisms)
    - Configuration
    - Handler functions
    - Documentation strings

    The analysis results are structured in JSON format, suitable for
    conversion to visualization formats like D2.
    """

    def __init__(self) -> None:
        """Initialize the routine analyzer."""
        self.routines: list[dict[str, Any]] = []

    def analyze_file(self, file_path: str | Path) -> dict[str, Any]:
        """Analyze a routine Python file.

        Args:
            file_path: Path to the Python file containing routine definitions.

        Returns:
            Dictionary containing structured routine information:
            {
                "file_path": str,
                "routines": [
                    {
                        "name": str,
                        "docstring": str,
                        "slots": [...],
                        "events": [...],
                        "config": {...},
                        "methods": [...],
                        "line_number": int
                    }
                ]
            }
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, encoding="utf-8") as f:
            source_code = f.read()

        tree = ast.parse(source_code, filename=str(file_path))

        result: dict[str, Any] = {"file_path": str(file_path), "routines": []}

        # Find all classes that inherit from Routine
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if self._inherits_from_routine(node):
                    routine_info = self._analyze_routine_class(node, source_code)
                    if routine_info:
                        result["routines"].append(routine_info)

        return result

    def _inherits_from_routine(self, class_node: ast.ClassDef) -> bool:
        """Check if a class inherits from Routine.

        Args:
            class_node: AST class definition node.

        Returns:
            True if the class inherits from Routine, False otherwise.
        """
        for base in class_node.bases:
            if isinstance(base, ast.Name):
                if base.id == "Routine":
                    return True
            elif isinstance(base, ast.Attribute):
                # Handle cases like "routilux.Routine"
                if base.attr == "Routine":
                    return True
        return False

    def _analyze_routine_class(
        self, class_node: ast.ClassDef, source_code: str
    ) -> dict[str, Any] | None:
        """Analyze a routine class definition.

        Args:
            class_node: AST class definition node.
            source_code: Full source code of the file.

        Returns:
            Dictionary containing routine information.
        """
        routine_info: dict[str, Any] = {
            "name": class_node.name,
            "docstring": ast.get_docstring(class_node) or "",
            "slots": [],
            "events": [],
            "config": {},
            "methods": [],
            "line_number": class_node.lineno,
        }

        # Analyze __init__ method for slots, events, and config
        init_method = self._find_method(class_node, "__init__")
        if init_method:
            routine_info["slots"] = self._extract_slots(init_method)
            routine_info["events"] = self._extract_events(init_method)
            routine_info["config"] = self._extract_config(init_method)

        # Extract all methods
        for node in class_node.body:
            if isinstance(node, ast.FunctionDef):
                method_info = self._analyze_method(node)
                routine_info["methods"].append(method_info)

        return routine_info

    def _find_method(self, class_node: ast.ClassDef, method_name: str) -> ast.FunctionDef | None:
        """Find a method in a class.

        Args:
            class_node: AST class definition node.
            method_name: Name of the method to find.

        Returns:
            AST function definition node if found, None otherwise.
        """
        for node in class_node.body:
            if isinstance(node, ast.FunctionDef) and node.name == method_name:
                return node
        return None

    def _extract_slots(self, init_method: ast.FunctionDef) -> list[dict[str, Any]]:
        """Extract slot definitions from __init__ method.

        Args:
            init_method: AST function definition node for __init__.

        Returns:
            List of slot information dictionaries.
        """
        slots = []

        for node in ast.walk(init_method):
            if isinstance(node, ast.Call):
                # Look for self.define_slot(...) calls
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "define_slot":
                        slot_info = self._parse_define_slot_call(node)
                        if slot_info:
                            slots.append(slot_info)

        return slots

    def _extract_events(self, init_method: ast.FunctionDef) -> list[dict[str, Any]]:
        """Extract event definitions from __init__ method.

        Args:
            init_method: AST function definition node for __init__.

        Returns:
            List of event information dictionaries.
        """
        events = []

        for node in ast.walk(init_method):
            if isinstance(node, ast.Call):
                # Look for self.define_event(...) calls
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "define_event":
                        event_info = self._parse_define_event_call(node)
                        if event_info:
                            events.append(event_info)

        return events

    def _extract_config(self, init_method: ast.FunctionDef) -> dict[str, Any]:
        """Extract configuration from __init__ method.

        Args:
            init_method: AST function definition node for __init__.

        Returns:
            Dictionary containing configuration information.
        """
        config = {}

        for node in ast.walk(init_method):
            if isinstance(node, ast.Call):
                # Look for self.set_config(...) calls
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "set_config":
                        config.update(self._parse_set_config_call(node))

        return config

    def _parse_define_slot_call(self, call_node: ast.Call) -> dict[str, Any] | None:
        """Parse a define_slot call.

        Args:
            call_node: AST call node for define_slot.

        Returns:
            Dictionary containing slot information.
        """
        if len(call_node.args) < 1:
            return None

        slot_info = {
            "name": self._extract_string_value(call_node.args[0]),
            "handler": None,
            "merge_strategy": "override",
        }

        # Extract handler from args or kwargs
        if len(call_node.args) > 1:
            handler_node = call_node.args[1]
            slot_info["handler"] = self._extract_function_reference(handler_node)

        # Extract merge_strategy from kwargs
        for keyword in call_node.keywords:
            if keyword.arg == "handler":
                slot_info["handler"] = self._extract_function_reference(keyword.value)
            elif keyword.arg == "merge_strategy":
                slot_info["merge_strategy"] = self._extract_string_value(keyword.value)

        return slot_info

    def _parse_define_event_call(self, call_node: ast.Call) -> dict[str, Any] | None:
        """Parse a define_event call.

        Args:
            call_node: AST call node for define_event.

        Returns:
            Dictionary containing event information.
        """
        if len(call_node.args) < 1:
            return None

        event_info: dict[str, Any] = {"name": self._extract_string_value(call_node.args[0]), "output_params": []}

        # Extract output_params from args or kwargs
        if len(call_node.args) > 1:
            params_node = call_node.args[1]
            event_info["output_params"] = self._extract_list_of_strings(params_node)

        for keyword in call_node.keywords:
            if keyword.arg == "output_params":
                event_info["output_params"] = self._extract_list_of_strings(keyword.value)

        return event_info

    def _parse_set_config_call(self, call_node: ast.Call) -> dict[str, Any]:
        """Parse a set_config call.

        Args:
            call_node: AST call node for set_config.

        Returns:
            Dictionary containing configuration key-value pairs.
        """
        config = {}

        # set_config can be called with keyword arguments
        for keyword in call_node.keywords:
            if keyword.arg:
                config[keyword.arg] = self._extract_literal_value(keyword.value)

        return config

    def _extract_string_value(self, node: ast.AST) -> str | None:
        """Extract string value from AST node.

        Args:
            node: AST node.

        Returns:
            String value if node is a string literal, None otherwise.
        """
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        elif hasattr(ast, "Str") and isinstance(node, ast.Str):  # Python < 3.8 compatibility
            # node.s is typed as Any, so we need to cast it
            s_val: Any = node.s
            return s_val if isinstance(s_val, str) else None
        return None

    def _extract_literal_value(self, node: ast.AST) -> Any:
        """Extract literal value from AST node.

        Args:
            node: AST node.

        Returns:
            Literal value (string, int, float, bool, list, dict, None).
        """
        if isinstance(node, ast.Constant):
            return node.value
        elif hasattr(ast, "Str") and isinstance(node, ast.Str):  # Python < 3.8 compatibility
            return node.s
        elif hasattr(ast, "Num") and isinstance(node, ast.Num):  # Python < 3.8 compatibility
            return node.n
        elif hasattr(ast, "NameConstant") and isinstance(node, ast.NameConstant):  # Python < 3.8 compatibility
            return node.value
        elif isinstance(node, ast.List):
            return [self._extract_literal_value(item) for item in node.elts]
        elif isinstance(node, ast.Dict):
            result = {}
            for k, v in zip(node.keys, node.values):
                key = self._extract_literal_value(k) if k else None
                value = self._extract_literal_value(v)
                if key is not None:
                    result[key] = value
            return result
        return None

    def _extract_list_of_strings(self, node: ast.AST) -> list[str]:
        """Extract list of strings from AST node.

        Args:
            node: AST node.

        Returns:
            List of strings.
        """
        if isinstance(node, ast.List):
            result = []
            for item in node.elts:
                value = self._extract_string_value(item)
                if value is not None:
                    result.append(value)
            return result
        return []

    def _extract_function_reference(self, node: ast.AST) -> str | None:
        """Extract function reference from AST node.

        Args:
            node: AST node.

        Returns:
            Function name as string, or None if not a simple reference.
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            # Handle self.method_name
            if isinstance(node.value, ast.Name) and node.value.id == "self":
                return node.attr
        return None

    def _analyze_method(self, method_node: ast.FunctionDef) -> dict[str, Any]:
        """Analyze a method definition.

        Args:
            method_node: AST function definition node.

        Returns:
            Dictionary containing method information.
        """
        method_info = {
            "name": method_node.name,
            "docstring": ast.get_docstring(method_node) or "",
            "parameters": [arg.arg for arg in method_node.args.args],
            "line_number": method_node.lineno,
        }

        # Check if method emits events
        emits = []
        for node in ast.walk(method_node):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "emit":
                        # Try to extract event name
                        if len(node.args) > 0:
                            event_name = self._extract_string_value(node.args[0])
                            if event_name:
                                emits.append(event_name)

        if emits:
            method_info["emits"] = emits

        return method_info

    def to_json(self, data: dict[str, Any], indent: int = 2) -> str:
        """Convert analysis result to JSON string.

        Args:
            data: Analysis result dictionary.
            indent: JSON indentation level.

        Returns:
            JSON string representation.
        """
        return json.dumps(data, indent=indent, ensure_ascii=False)

    def save_json(self, data: dict[str, Any], output_path: str | Path, indent: int = 2) -> None:
        """Save analysis result to JSON file.

        Args:
            data: Analysis result dictionary.
            output_path: Path to output JSON file.
            indent: JSON indentation level.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)


def analyze_routine_file(file_path: str | Path) -> dict[str, Any]:
    """Convenience function to analyze a routine file.

    Args:
        file_path: Path to the Python file containing routine definitions.

    Returns:
        Dictionary containing structured routine information.
    """
    analyzer = RoutineAnalyzer()
    return analyzer.analyze_file(file_path)
