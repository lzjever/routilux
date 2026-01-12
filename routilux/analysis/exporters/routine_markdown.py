"""
Routine Markdown formatter.

Converts routine analysis JSON into beautiful, professional Markdown documentation.
"""

from pathlib import Path
from typing import Any, Dict, List

from routilux.analysis.exporters.base import BaseFormatter


class RoutineMarkdownFormatter(BaseFormatter):
    """Formatter for converting routine analysis to Markdown.

    Generates beautiful, well-structured Markdown documentation from
    routine analysis JSON with professional styling.
    """

    def format(self, data: Dict[str, Any]) -> str:
        """Format routine analysis data into Markdown.

        Args:
            data: Routine analysis result dictionary.

        Returns:
            Markdown formatted string.
        """
        lines = []

        # Title with styling
        file_path = data.get("file_path", "unknown")
        lines.append(f"# 📋 Routine Analysis: {Path(file_path).name}")
        lines.append("")

        if "file_path" in data:
            lines.append(f"**Source File:** `{file_path}`")
            lines.append("")

        # Routines
        routines = data.get("routines", [])
        if not routines:
            lines.append("*No routines found in this file.*")
            return "\n".join(lines)

        lines.append(f"**Total Routines:** {len(routines)}")
        lines.append("")
        lines.append("")  # Extra blank line before first routine

        # Format each routine with clear separators
        for i, routine in enumerate(routines):
            if i > 0:
                # More visible separator with extra spacing
                lines.append("")
                lines.append("---")
                lines.append("")
                lines.append("")
            lines.extend(self._format_routine(routine))

        return "\n".join(lines)

    def _format_routine(self, routine: Dict[str, Any]) -> List[str]:
        """Format a single routine into Markdown.

        Args:
            routine: Routine dictionary.

        Returns:
            List of Markdown lines.
        """
        lines = []

        # Routine header (no index, no line number)
        name = routine.get("name", "Unknown")
        lines.append(f"## {name}")
        lines.append("")

        # Docstring
        docstring = routine.get("docstring", "").strip()
        if docstring:
            lines.append(docstring)
            lines.append("")

        # Input Slots section
        slots = routine.get("slots", [])
        if slots:
            lines.append("### 📥 Input Slots")
            lines.append("")
            for slot in slots:
                lines.extend(self._format_slot(slot, routine))
            lines.append("")

        # Output Events section
        events = routine.get("events", [])
        if events:
            lines.append("### 📤 Output Events")
            lines.append("")
            for event in events:
                lines.extend(self._format_event(event, routine))
            lines.append("")

        # Configuration section
        config = routine.get("config", {})
        if config:
            lines.append("### ⚙️ Configuration")
            lines.append("")
            lines.append("| Parameter | Default Value |")
            lines.append("|-----------|---------------|")
            for key, value in config.items():
                value_str = self._format_value(value)
                lines.append(f"| `{key}` | {value_str} |")
            lines.append("")

        return lines

    def _format_slot(self, slot: Dict[str, Any], routine: Dict[str, Any]) -> List[str]:
        """Format a slot into Markdown.

        Args:
            slot: Slot dictionary.
            routine: Routine dictionary (for finding handler info).

        Returns:
            List of Markdown lines.
        """
        lines = []
        name = slot.get("name", "unknown")
        handler = slot.get("handler")
        merge_strategy = slot.get("merge_strategy", "override")

        # Get handler method info for parameters and emits
        handler_params = []
        handler_emits = []
        handler_docstring = ""

        if handler:
            for method in routine.get("methods", []):
                if method.get("name") == handler:
                    handler_params = method.get("parameters", [])
                    handler_emits = method.get("emits", [])
                    handler_docstring = method.get("docstring", "").strip()
                    break

        # Slot name as bold header
        lines.append(f"**`{name}`**")
        lines.append("")

        # Merge Strategy
        lines.append(f"- **Merge Strategy:** `{merge_strategy}`")

        # Parameters (from handler, excluding self/data/kwargs)
        if handler_params:
            params = [p for p in handler_params if p not in ["self", "data", "**kwargs"]]
            if params:
                params_str = ", ".join(f"`{p}`" for p in params)
                lines.append(f"- **Parameters:** {params_str}")

        # Emits events
        if handler_emits:
            emits_str = ", ".join(f"`{e}`" for e in handler_emits)
            lines.append(f"- **Emits Events:** {emits_str}")

        lines.append("")

        # Description (from handler docstring)
        if handler_docstring:
            # Indent the description for better readability
            lines.append(f"  > {handler_docstring}")
            lines.append("")

        return lines

    def _format_event(self, event: Dict[str, Any], routine: Dict[str, Any]) -> List[str]:
        """Format an event into Markdown.

        Args:
            event: Event dictionary.
            routine: Routine dictionary (for finding comments).

        Returns:
            List of Markdown lines.
        """
        lines = []
        name = event.get("name", "unknown")
        output_params = event.get("output_params", [])

        # Event name as bold header
        lines.append(f"**`{name}`**")
        lines.append("")

        # Output parameters
        if output_params:
            params_str = ", ".join(f"`{p}`" for p in output_params)
            lines.append(f"- **Parameters:** {params_str}")
        else:
            lines.append("- **Parameters:** *None specified*")
        lines.append("")

        # Description could be extracted from source code comments if needed

        return lines

    def _format_value(self, value: Any) -> str:
        """Format a configuration value for Markdown table.

        Args:
            value: Configuration value.

        Returns:
            Formatted string.
        """
        if isinstance(value, str):
            return f'`"{value}"`'
        elif isinstance(value, (int, float)):
            return f"`{value}`"
        elif isinstance(value, bool):
            return f"`{str(value)}`"
        elif isinstance(value, list):
            if len(value) <= 3:
                items = ", ".join(self._format_single_value(v) for v in value)
                return f"`[{items}]`"
            else:
                return f"`[{len(value)} items]`"
        elif isinstance(value, dict):
            if len(value) <= 3:
                items = ", ".join(
                    f"`{k}`: {self._format_single_value(v)}" for k, v in value.items()
                )
                return f"`{{{items}}}`"
            else:
                return f"`{{{len(value)} items}}`"
        elif value is None:
            return "`None`"
        else:
            return f"`{str(value)}`"

    def _format_single_value(self, value: Any) -> str:
        """Format a single value (for use in lists/dicts).

        Args:
            value: Value to format.

        Returns:
            Formatted string.
        """
        if isinstance(value, str):
            return f'"{value}"'
        elif isinstance(value, (int, float, bool)):
            return str(value)
        elif value is None:
            return "None"
        else:
            return str(value)
