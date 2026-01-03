"""
Routine Markdown formatter.

Converts routine analysis JSON into beautiful Markdown documentation.
"""

from pathlib import Path
from typing import Dict, Any, List
from routilux.analysis_formatters.base import BaseFormatter


class RoutineMarkdownFormatter(BaseFormatter):
    """Formatter for converting routine analysis to Markdown.
    
    Generates beautiful, well-structured Markdown documentation from
    routine analysis JSON, including:
    - Class documentation
    - Slots and events
    - Configuration
    - Methods
    - Examples
    """
    
    def format(self, data: Dict[str, Any]) -> str:
        """Format routine analysis data into Markdown.
        
        Args:
            data: Routine analysis result dictionary.
        
        Returns:
            Markdown formatted string.
        """
        lines = []
        
        # Title
        file_path = data.get("file_path", "unknown")
        lines.append(f"# Routine Analysis: {Path(file_path).name}")
        lines.append("")
        
        if "file_path" in data:
            lines.append(f"**Source File:** `{file_path}`")
            lines.append("")
        
        # Routines
        routines = data.get("routines", [])
        if not routines:
            lines.append("No routines found in this file.")
            return "\n".join(lines)
        
        lines.append(f"Found **{len(routines)}** routine(s) in this file.")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Format each routine
        for i, routine in enumerate(routines, 1):
            lines.extend(self._format_routine(routine, i, len(routines)))
            if i < len(routines):
                lines.append("")
                lines.append("---")
                lines.append("")
        
        return "\n".join(lines)
    
    def _format_routine(self, routine: Dict[str, Any], index: int, total: int) -> List[str]:
        """Format a single routine into Markdown.
        
        Args:
            routine: Routine dictionary.
            index: Routine index (1-based).
            total: Total number of routines.
        
        Returns:
            List of Markdown lines.
        """
        lines = []
        
        # Routine header
        name = routine.get("name", "Unknown")
        lines.append(f"## {index}. {name}")
        lines.append("")
        
        # Docstring
        docstring = routine.get("docstring", "").strip()
        if docstring:
            lines.append(docstring)
            lines.append("")
        
        # Metadata
        metadata = []
        line_number = routine.get("line_number")
        if line_number:
            metadata.append(f"**Line:** {line_number}")
        
        if metadata:
            lines.append(" | ".join(metadata))
            lines.append("")
        
        # Slots section
        slots = routine.get("slots", [])
        if slots:
            lines.append("### 📥 Input Slots")
            lines.append("")
            for slot in slots:
                lines.extend(self._format_slot(slot))
            lines.append("")
        
        # Events section
        events = routine.get("events", [])
        if events:
            lines.append("### 📤 Output Events")
            lines.append("")
            for event in events:
                lines.extend(self._format_event(event))
            lines.append("")
        
        # Configuration section
        config = routine.get("config", {})
        if config:
            lines.append("### ⚙️ Configuration")
            lines.append("")
            lines.append("| Parameter | Value |")
            lines.append("|-----------|-------|")
            for key, value in config.items():
                value_str = self._format_value(value)
                lines.append(f"| `{key}` | {value_str} |")
            lines.append("")
        
        # Methods section
        methods = routine.get("methods", [])
        if methods:
            lines.append("### 🔧 Methods")
            lines.append("")
            for method in methods:
                lines.extend(self._format_method(method))
            lines.append("")
        
        return lines
    
    def _format_slot(self, slot: Dict[str, Any]) -> List[str]:
        """Format a slot into Markdown.
        
        Args:
            slot: Slot dictionary.
        
        Returns:
            List of Markdown lines.
        """
        lines = []
        name = slot.get("name", "unknown")
        handler = slot.get("handler")
        merge_strategy = slot.get("merge_strategy", "override")
        
        lines.append(f"#### `{name}`")
        lines.append("")
        
        details = []
        if handler:
            details.append(f"**Handler:** `{handler}()`")
        details.append(f"**Merge Strategy:** `{merge_strategy}`")
        
        lines.append(" | ".join(details))
        lines.append("")
        
        return lines
    
    def _format_event(self, event: Dict[str, Any]) -> List[str]:
        """Format an event into Markdown.
        
        Args:
            event: Event dictionary.
        
        Returns:
            List of Markdown lines.
        """
        lines = []
        name = event.get("name", "unknown")
        output_params = event.get("output_params", [])
        
        lines.append(f"#### `{name}`")
        lines.append("")
        
        if output_params:
            params_str = ", ".join(f"`{p}`" for p in output_params)
            lines.append(f"**Output Parameters:** {params_str}")
        else:
            lines.append("**Output Parameters:** *None specified*")
        
        lines.append("")
        
        return lines
    
    def _format_method(self, method: Dict[str, Any]) -> List[str]:
        """Format a method into Markdown.
        
        Args:
            method: Method dictionary.
        
        Returns:
            List of Markdown lines.
        """
        lines = []
        name = method.get("name", "unknown")
        docstring = method.get("docstring", "").strip()
        parameters = method.get("parameters", [])
        emits = method.get("emits", [])
        
        # Method signature
        params_str = ", ".join(parameters) if parameters else ""
        signature = f"`{name}({params_str})`"
        lines.append(f"#### {signature}")
        lines.append("")
        
        # Docstring
        if docstring:
            lines.append(docstring)
            lines.append("")
        
        # Emits events
        if emits:
            emits_str = ", ".join(f"`{e}`" for e in emits)
            lines.append(f"**Emits Events:** {emits_str}")
            lines.append("")
        
        return lines
    
    def _format_value(self, value: Any) -> str:
        """Format a configuration value for Markdown table.
        
        Args:
            value: Configuration value.
        
        Returns:
            Formatted string.
        """
        if isinstance(value, str):
            return f"`{value}`"
        elif isinstance(value, (int, float, bool)):
            return f"`{value}`"
        elif isinstance(value, list):
            if len(value) <= 3:
                items = ", ".join(str(v) for v in value)
                return f"`[{items}]`"
            else:
                return f"`[{len(value)} items]`"
        elif isinstance(value, dict):
            if len(value) <= 3:
                items = ", ".join(f"{k}: {v}" for k, v in value.items())
                return f"`{{{items}}}`"
            else:
                return f"`{{{len(value)} items}}`"
        else:
            return f"`{str(value)}`"

