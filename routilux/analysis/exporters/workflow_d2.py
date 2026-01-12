"""
Workflow D2 formatter.

Converts workflow analysis JSON into beautiful D2 diagram format.
"""

from typing import Any, Dict, List

from routilux.analysis.exporters.base import BaseFormatter


class WorkflowD2Formatter(BaseFormatter):
    """Formatter for converting workflow analysis to D2 format.

    Generates beautiful, well-structured D2 diagrams from workflow
    analysis JSON, including:
    - Routine nodes with slots and events
    - Connections with labels
    - Dependency visualization
    - Entry points highlighting
    """

    def __init__(self, style: str = "default"):
        """Initialize D2 formatter.

        Args:
            style: Diagram style ("default", "compact", "detailed").
        """
        self.style = style

    def format(self, data: Dict[str, Any]) -> str:
        """Format workflow analysis data into D2 format.

        Args:
            data: Workflow analysis result dictionary.

        Returns:
            D2 formatted string.
        """
        lines = []

        # Header
        flow_id = data.get("flow_id", "unknown")
        lines.append(f"# Workflow: {flow_id}")
        lines.append("")

        # Metadata comment
        execution_strategy = data.get("execution_strategy", "sequential")
        max_workers = data.get("max_workers", 1)
        routines_count = len(data.get("routines", []))
        connections_count = len(data.get("connections", []))

        lines.append(f"# Execution Strategy: {execution_strategy}")
        lines.append(f"# Max Workers: {max_workers}")
        lines.append(f"# Routines: {routines_count}")
        lines.append(f"# Connections: {connections_count}")
        lines.append("")

        # Style configuration (commented out - styles applied directly to nodes)
        # D2 doesn't support style.class, so we apply styles directly to nodes
        lines.append("# Style configuration")
        lines.append("# Entry points: orange background (#fff4e6)")
        lines.append("# Regular routines: blue background (#e8f4f8)")
        lines.append("")

        # Define routines
        routines = data.get("routines", [])
        entry_points = set(data.get("entry_points", []))

        for routine in routines:
            routine_id = routine.get("routine_id", "unknown")
            is_entry = routine_id in entry_points
            lines.extend(self._format_routine_node(routine, is_entry))
            lines.append("")

        # Define connections
        connections = data.get("connections", [])
        if connections:
            lines.append("# Connections")
            for conn in connections:
                lines.extend(self._format_connection(conn))
            lines.append("")

        # Dependency graph visualization (optional)
        if self.style == "detailed":
            lines.extend(self._format_dependency_graph(data))

        return "\n".join(lines)

    def _format_routine_node(self, routine: Dict[str, Any], is_entry: bool) -> List[str]:
        """Format a routine node in D2.

        Args:
            routine: Routine dictionary.
            is_entry: Whether this is an entry point.

        Returns:
            List of D2 lines.
        """
        lines = []
        routine_id = routine.get("routine_id", "unknown")
        class_name = routine.get("class_name", "Unknown")

        lines.append(f'{routine_id}: "{class_name}" {{')

        # Apply style directly (D2 doesn't support style.class)
        if is_entry:
            lines.append("  style: {")
            lines.append('    fill: "#fff4e6"')
            lines.append('    stroke: "#d97706"')
            lines.append("    stroke-width: 3")
            lines.append("  }")
            lines.append(f'  label: "{class_name}\\n(Entry Point)"')
        else:
            lines.append("  style: {")
            lines.append('    fill: "#e8f4f8"')
            lines.append('    stroke: "#2c5aa0"')
            lines.append("    stroke-width: 2")
            lines.append("  }")

        # Slots
        slots = routine.get("slots", [])
        if slots:
            lines.append("  slots: {")
            for slot in slots:
                slot_name = slot.get("name", "unknown")
                handler = slot.get("handler")
                if handler:
                    lines.append(f'    {slot_name}: "{slot_name}\\n(handler: {handler})"')
                else:
                    lines.append(f'    {slot_name}: "{slot_name}"')
            lines.append("  }")

        # Events
        events = routine.get("events", [])
        if events:
            lines.append("  events: {")
            for event in events:
                event_name = event.get("name", "unknown")
                params = event.get("output_params", [])
                if params:
                    params_str = ", ".join(params[:3])  # Limit to 3 params
                    if len(params) > 3:
                        params_str += "..."
                    lines.append(f'    {event_name}: "{event_name}\\n({params_str})"')
                else:
                    lines.append(f'    {event_name}: "{event_name}"')
            lines.append("  }")

        lines.append("}")

        return lines

    def _format_connection(self, conn: Dict[str, Any]) -> List[str]:
        """Format a connection in D2.

        Args:
            conn: Connection dictionary.

        Returns:
            List of D2 lines.
        """
        lines = []
        source_id = conn.get("source_routine_id", "unknown")
        source_event = conn.get("source_event", "unknown")
        target_id = conn.get("target_routine_id", "unknown")
        target_slot = conn.get("target_slot", "unknown")
        param_mapping = conn.get("param_mapping", {})

        # Build connection string
        if param_mapping:
            mapping_str = ", ".join(f"{k}→{v}" for k, v in list(param_mapping.items())[:2])
            if len(param_mapping) > 2:
                mapping_str += "..."
            label = f"{source_event} → {target_slot}\\n(mapping: {mapping_str})"
        else:
            label = f"{source_event} → {target_slot}"

        # Use full path to events and slots within routines
        # Format: routine_id.events.event_name -> routine_id.slots.slot_name
        connection_line = f"{source_id}.events.{source_event} -> {target_id}.slots.{target_slot}"

        if self.style == "detailed":
            lines.append(f'{connection_line}: "{label}" {{')
            lines.append("  style: {")
            lines.append('    stroke: "#4a5568"')
            lines.append("    stroke-width: 2")
            lines.append("  }")
            lines.append("}")
        else:
            lines.append(f"{connection_line}")

        return lines

    def _format_dependency_graph(self, data: Dict[str, Any]) -> List[str]:
        """Format dependency graph visualization (optional).

        Args:
            data: Workflow analysis dictionary.

        Returns:
            List of D2 lines.
        """
        lines = []
        dependency_graph = data.get("dependency_graph", {})

        if not dependency_graph:
            return lines

        lines.append("# Dependency Graph")
        lines.append("# (Shows execution dependencies)")
        lines.append("")

        # Create dependency visualization
        for routine_id, deps in dependency_graph.items():
            if deps:
                for dep in deps:
                    lines.append(f"# {dep} -> {routine_id} (dependency)")

        return lines
