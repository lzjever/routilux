"""
Workflow analyzer module.

Dynamically analyzes Flow objects to generate structured workflow descriptions.
Combines with routine_analyzer to provide complete workflow information.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

from routilux.analysis.analyzers.routine import RoutineAnalyzer
from routilux.flow import Flow
from routilux.routine import Routine


class WorkflowAnalyzer:
    """Analyzer for Flow objects to generate structured workflow descriptions.

    This class analyzes Flow objects to extract:
    - Flow metadata (flow_id, execution_strategy, etc.)
    - Routine information (combining with routine_analyzer)
    - Connection information (links between routines)
    - Dependency graph
    - Entry points

    The analysis results are structured in JSON format, suitable for
    conversion to visualization formats like D2.
    """

    def __init__(self, routine_analyzer: RoutineAnalyzer | None = None):
        """Initialize the workflow analyzer.

        Args:
            routine_analyzer: Optional RoutineAnalyzer instance for analyzing
                routine source files. If None, a new instance will be created.
        """
        self.routine_analyzer = routine_analyzer or RoutineAnalyzer()

    def analyze_flow(self, flow: Flow, include_source_analysis: bool = True) -> dict[str, Any]:
        """Analyze a Flow object.

        Args:
            flow: Flow object to analyze.
            include_source_analysis: If True, attempt to analyze routine source
                files using AST. If False, only extract runtime information.

        Returns:
            Dictionary containing structured workflow information:
            {
                "flow_id": str,
                "execution_strategy": str,
                "max_workers": int,
                "execution_timeout": float,
                "routines": [
                    {
                        "routine_id": str,
                        "class_name": str,
                        "slots": [...],
                        "events": [...],
                        "config": {...},
                        "source_info": {...}  # if include_source_analysis
                    }
                ],
                "connections": [
                    {
                        "source_routine_id": str,
                        "source_event": str,
                        "target_routine_id": str,
                        "target_slot": str,
                        "param_mapping": {...}
                    }
                ],
                "dependency_graph": {...},
                "entry_points": [...]
            }
        """
        result: dict[str, Any] = {
            "flow_id": flow.flow_id,
            "execution_strategy": flow.execution_strategy,
            "max_workers": flow.max_workers,
            "execution_timeout": flow.execution_timeout,
            "routines": [],
            "connections": [],
            "dependency_graph": {},
            "entry_points": [],
        }

        # Analyze routines
        for routine_id, routine in flow.routines.items():
            routine_info = self._analyze_routine(routine_id, routine, include_source_analysis)
            result["routines"].append(routine_info)

        # Analyze connections
        for connection in flow.connections:
            conn_info = self._analyze_connection(connection, flow)
            if conn_info:
                result["connections"].append(conn_info)

        # Build dependency graph
        result["dependency_graph"] = self._build_dependency_graph(flow)

        # Find entry points (routines with trigger slots)
        result["entry_points"] = self._find_entry_points(flow)

        return result

    def _analyze_routine(
        self, routine_id: str, routine: Routine, include_source_analysis: bool
    ) -> dict[str, Any]:
        """Analyze a routine instance.

        Args:
            routine_id: ID of the routine in the flow.
            routine: Routine instance.
            include_source_analysis: Whether to analyze source file.

        Returns:
            Dictionary containing routine information.
        """
        routine_info: dict[str, Any] = {
            "routine_id": routine_id,
            "class_name": routine.__class__.__name__,
            "docstring": inspect.getdoc(routine.__class__) or "",
            "slots": [],
            "events": [],
            "config": dict(routine._config) if hasattr(routine, "_config") else {},
            "source_info": None,
        }

        # Extract slots
        if hasattr(routine, "_slots"):
            for slot_name, slot in routine._slots.items():
                slot_info = {
                    "name": slot_name,
                    "handler": None,
                    "merge_strategy": getattr(slot, "merge_strategy", "override"),
                }

                # Try to get handler name (convert to string for JSON serialization)
                if hasattr(slot, "handler") and slot.handler:
                    handler = slot.handler
                    if hasattr(handler, "__name__"):
                        slot_info["handler"] = handler.__name__
                    elif hasattr(handler, "__func__"):
                        slot_info["handler"] = handler.__func__.__name__
                    else:
                        # Fallback: convert to string representation
                        slot_info["handler"] = str(handler)

                routine_info["slots"].append(slot_info)

        # Extract events
        if hasattr(routine, "_events"):
            for event_name, event in routine._events.items():
                event_info = {
                    "name": event_name,
                    "output_params": getattr(event, "output_params", []),
                }
                routine_info["events"].append(event_info)

        # Try to analyze source file if requested
        if include_source_analysis:
            source_info = self._analyze_routine_source(routine)
            if source_info:
                routine_info["source_info"] = source_info

        return routine_info

    def _analyze_routine_source(self, routine: Routine) -> dict[str, Any] | None:
        """Attempt to analyze routine source file.

        Args:
            routine: Routine instance.

        Returns:
            Dictionary containing source analysis, or None if source cannot be found.
        """
        try:
            # Get source file path
            source_file = inspect.getfile(routine.__class__)
            if source_file and Path(source_file).exists():
                # Analyze the file
                analysis: dict[str, Any] = self.routine_analyzer.analyze_file(source_file)

                # Find the specific routine class in the analysis
                routines_list = analysis.get("routines", [])
                if isinstance(routines_list, list):
                    for routine_data in routines_list:
                        if (
                            isinstance(routine_data, dict)
                            and routine_data.get("name") == routine.__class__.__name__
                        ):
                            return routine_data
        except (OSError, TypeError):
            # Source file not available (e.g., built-in, dynamically created)
            pass

        return None

    def _get_routine_id(self, routine: Routine, flow: Flow) -> str | None:
        """Find the ID of a Routine object within a Flow.

        Args:
            routine: Routine object.
            flow: Flow object.

        Returns:
            Routine ID if found, None otherwise.
        """
        for rid, r in flow.routines.items():
            if r is routine:
                return rid
        return None

    def _analyze_connection(self, connection, flow: Flow) -> dict[str, Any] | None:
        """Analyze a connection.

        Args:
            connection: Connection object.
            flow: Flow object containing the connection.

        Returns:
            Dictionary containing connection information, or None if routine IDs cannot be found.
        """
        if not connection.source_event or not connection.target_slot:
            return None

        source_routine = connection.source_event.routine
        target_routine = connection.target_slot.routine

        source_routine_id = self._get_routine_id(source_routine, flow)
        target_routine_id = self._get_routine_id(target_routine, flow)

        if not source_routine_id or not target_routine_id:
            return None

        conn_info: dict[str, Any] = {
            "source_routine_id": source_routine_id,
            "source_event": connection.source_event.name,
            "target_routine_id": target_routine_id,
            "target_slot": connection.target_slot.name,
            "param_mapping": dict(connection.param_mapping)
            if hasattr(connection, "param_mapping") and connection.param_mapping
            else {},
        }

        return conn_info

    def _build_dependency_graph(self, flow: Flow) -> dict[str, list[str]]:
        """Build dependency graph from connections.

        Args:
            flow: Flow object.

        Returns:
            Dictionary mapping routine_id to list of dependency routine_ids.
            If A.event -> B.slot, then B depends on A.
        """
        dependency_graph: dict[str, list[str]] = {
            routine_id: [] for routine_id in flow.routines.keys()
        }

        for connection in flow.connections:
            if not connection.source_event or not connection.target_slot:
                continue

            source_routine = connection.source_event.routine
            target_routine = connection.target_slot.routine

            if source_routine is not None and target_routine is not None:
                source_routine_id = self._get_routine_id(source_routine, flow)
                target_routine_id = self._get_routine_id(target_routine, flow)

                if (
                    source_routine_id
                    and target_routine_id
                    and source_routine_id != target_routine_id
                ):
                    if source_routine_id not in dependency_graph[target_routine_id]:
                        dependency_graph[target_routine_id].append(source_routine_id)

        return dependency_graph

    def _find_entry_points(self, flow: Flow) -> list[str]:
        """Find entry point routines (those with trigger slots).

        Args:
            flow: Flow object.

        Returns:
            List of routine_ids that have trigger slots.
        """
        entry_points = []

        for routine_id, routine in flow.routines.items():
            if hasattr(routine, "_slots"):
                for slot_name, slot in routine._slots.items():
                    if slot_name == "trigger":
                        entry_points.append(routine_id)
                        break

        return entry_points

    def _make_json_serializable(self, obj: Any) -> Any:
        """Convert object to JSON-serializable format.

        Args:
            obj: Object to convert.

        Returns:
            JSON-serializable object.
        """
        if isinstance(obj, dict):
            return {k: self._make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_json_serializable(item) for item in obj]
        elif isinstance(obj, (str, int, float, bool, type(None))):
            return obj
        else:
            # Convert non-serializable objects to string
            return str(obj)

    def to_json(self, data: dict[str, Any], indent: int = 2) -> str:
        """Convert analysis result to JSON string.

        Args:
            data: Analysis result dictionary.
            indent: JSON indentation level.

        Returns:
            JSON string representation.
        """
        serializable_data = self._make_json_serializable(data)
        return json.dumps(serializable_data, indent=indent, ensure_ascii=False)

    def save_json(self, data: dict[str, Any], output_path: str | Path, indent: int = 2) -> None:
        """Save analysis result to JSON file.

        Args:
            data: Analysis result dictionary.
            output_path: Path to output JSON file.
            indent: JSON indentation level.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        serializable_data = self._make_json_serializable(data)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(serializable_data, f, indent=indent, ensure_ascii=False)

    def to_d2_format(
        self,
        data: dict[str, Any],
        mode: str = "standard",
        routine_analysis: str | Path | dict[str, Any] | None = None,
    ) -> str:
        """Convert workflow analysis to D2 format string.

        D2 is a diagramming language. This method generates a D2 script
        that can be used to visualize the workflow.

        Args:
            data: Workflow analysis result dictionary.
            mode: Export mode - "standard" for basic visualization,
                  "ultimate" for detailed professional visualization.
            routine_analysis: Optional routine analysis data. Can be:
                - Path to JSON file containing routine analysis
                - Dictionary containing routine analysis data
                If provided in ultimate mode, will enhance nodes with detailed information.

        Returns:
            D2 format string.
        """
        if mode == "ultimate":
            return self._to_d2_format_ultimate(data, routine_analysis)
        else:
            return self._to_d2_format_standard(data)

    def _to_d2_format_standard(self, data: dict[str, Any]) -> str:
        """Generate standard D2 format (backward compatible)."""
        lines = []
        lines.append("# Workflow: " + data.get("flow_id", "unknown"))
        lines.append("")

        # Create nodes for each routine
        for routine in data.get("routines", []):
            routine_id = routine["routine_id"]
            class_name = routine["class_name"]
            lines.append(f'{routine_id}: "{class_name}" {{')

            # Add slots
            if routine.get("slots"):
                lines.append("  slots: {")
                for slot in routine["slots"]:
                    slot_name = slot["name"]
                    lines.append(f'    {slot_name}: "{slot_name}"')
                lines.append("  }")

            # Add events
            if routine.get("events"):
                lines.append("  events: {")
                for event in routine["events"]:
                    event_name = event["name"]
                    lines.append(f'    {event_name}: "{event_name}"')
                lines.append("  }")

            lines.append("}")
            lines.append("")

        # Create connections
        for conn in data.get("connections", []):
            source_id = conn["source_routine_id"]
            target_id = conn["target_routine_id"]
            source_event = conn["source_event"]
            target_slot = conn["target_slot"]

            label = f"{source_event} -> {target_slot}"
            if conn.get("param_mapping"):
                label += f" (mapping: {conn['param_mapping']})"

            lines.append(f'{source_id}.{source_event} -> {target_id}.{target_slot}: "{label}"')

        return "\n".join(lines)

    def _to_d2_format_ultimate(
        self,
        data: dict[str, Any],
        routine_analysis: str | Path | dict[str, Any] | None = None,
    ) -> str:
        """Generate ultimate D2 format with enhanced styling and detailed information."""
        # Load routine analysis if provided
        routine_analysis_data = self._load_routine_analysis(routine_analysis)

        lines = []

        # Header with metadata
        flow_id = data.get("flow_id", "unknown")
        lines.append("# ========================================")
        lines.append(f"# Workflow: {flow_id}")
        lines.append("# ========================================")
        lines.append("")

        # Add layout configuration for better visualization
        lines.append("# Layout Configuration")
        lines.append("vars: {")
        lines.append("  d2-config: {")
        lines.append("    layout-engine: elk")
        lines.append("  }")
        lines.append("}")
        lines.append("direction: right")
        lines.append("")

        # Workflow metadata as comments
        execution_strategy = data.get("execution_strategy", "sequential")
        max_workers = data.get("max_workers", 1)
        execution_timeout = data.get("execution_timeout", 0)
        routines_count = len(data.get("routines", []))
        connections_count = len(data.get("connections", []))
        entry_points = data.get("entry_points", [])

        lines.append("# Workflow Metadata")
        lines.append(f"# Execution Strategy: {execution_strategy}")
        lines.append(f"# Max Workers: {max_workers}")
        if execution_timeout > 0:
            lines.append(f"# Execution Timeout: {execution_timeout}s")
        lines.append(f"# Total Routines: {routines_count}")
        lines.append(f"# Total Connections: {connections_count}")
        lines.append(f"# Entry Points: {len(entry_points)}")
        lines.append("")

        # Create enhanced nodes for each routine
        entry_points_set = set(entry_points)
        for routine in data.get("routines", []):
            routine_id = routine["routine_id"]
            is_entry = routine_id in entry_points_set

            # Get enhanced routine info from analysis if available
            enhanced_info = self._get_enhanced_routine_info(routine, routine_analysis_data)

            lines.extend(self._format_ultimate_routine_node(routine, enhanced_info, is_entry))
            lines.append("")

        # Create enhanced connections
        if data.get("connections"):
            lines.append("# Data Flow Connections")
            for conn in data.get("connections", []):
                lines.extend(self._format_ultimate_connection(conn))
            lines.append("")

        # Add dependency visualization
        dependency_graph = data.get("dependency_graph", {})
        if dependency_graph:
            lines.extend(self._format_dependency_section(dependency_graph, entry_points_set))

        return "\n".join(lines)

    def _load_routine_analysis(
        self, routine_analysis: str | Path | dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Load routine analysis data from file or return dict if already loaded.

        Args:
            routine_analysis: Path to JSON file or dictionary.

        Returns:
            Routine analysis dictionary or None.
        """
        if routine_analysis is None:
            return None

        if isinstance(routine_analysis, dict):
            return routine_analysis

        # Try to load from file
        try:
            file_path = Path(routine_analysis)
            if file_path.exists():
                with open(file_path, encoding="utf-8") as f:
                    result: Any = json.load(f)
                    return result if isinstance(result, dict) else None
        except (OSError, json.JSONDecodeError):
            # Silently fail - will use basic info
            pass

        return None

    def _get_enhanced_routine_info(
        self, routine: dict[str, Any], routine_analysis_data: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Get enhanced routine information from analysis data.

        Args:
            routine: Routine dictionary from workflow analysis.
            routine_analysis_data: Routine analysis data dictionary.

        Returns:
            Enhanced routine info or None.
        """
        if not routine_analysis_data:
            return None

        class_name = routine.get("class_name")
        routines_list = routine_analysis_data.get("routines", [])

        # Find matching routine by class name
        if isinstance(routines_list, list):
            for routine_info in routines_list:
                if isinstance(routine_info, dict) and routine_info.get("name") == class_name:
                    return routine_info

        return None

    def _format_ultimate_routine_node(
        self, routine: dict[str, Any], enhanced_info: dict[str, Any] | None, is_entry: bool
    ) -> list[str]:
        """Format a routine node in ultimate D2 format with enhanced styling.

        Args:
            routine: Routine dictionary from workflow analysis.
            enhanced_info: Enhanced routine info from analysis (optional).
            is_entry: Whether this is an entry point.

        Returns:
            List of D2 lines.
        """
        lines = []
        routine_id = routine["routine_id"]
        class_name = routine["class_name"]
        docstring = routine.get("docstring", "")
        config = routine.get("config", {})
        slots = routine.get("slots", [])
        events = routine.get("events", [])

        # Use enhanced info if available
        if enhanced_info:
            docstring = enhanced_info.get("docstring", docstring)
            config = enhanced_info.get("config", config)
            methods = enhanced_info.get("methods", [])
        else:
            methods = []

        # Determine node styling based on type with gradient colors
        if is_entry:
            fill_color = "#fff3cd"  # Light yellow for entry points
            stroke_color = "#ffc107"  # Amber
            stroke_width = 4
        else:
            # Use different colors based on routine type/name
            class_lower = class_name.lower()
            if "worker" in class_lower or "processor" in class_lower:
                fill_color = "#e3f2fd"  # Light blue for processors
                stroke_color = "#1976d2"  # Blue
            elif "aggregator" in class_lower or "collector" in class_lower:
                fill_color = "#f3e5f5"  # Light purple for aggregators
                stroke_color = "#7b1fa2"  # Purple
            elif "router" in class_lower or "dispatcher" in class_lower:
                fill_color = "#fff3e0"  # Light orange for routers
                stroke_color = "#f57c00"  # Orange
            elif "validator" in class_lower or "controller" in class_lower:
                fill_color = "#e8f5e9"  # Light green for validators
                stroke_color = "#388e3c"  # Green
            elif "sink" in class_lower:
                fill_color = "#fce4ec"  # Light pink for sinks
                stroke_color = "#c2185b"  # Pink
            else:
                fill_color = "#f5f5f5"  # Light gray default
                stroke_color = "#616161"  # Gray
            stroke_width = 3

        # Build comprehensive node label with better formatting (inspired by bank example)
        # Format: ClassName\nDescription\nConfig: key=value
        label_parts = [f"{class_name}"]

        # Add docstring summary (first line, max 50 chars)
        if docstring:
            doc_lines = docstring.strip().split("\n")
            first_line = doc_lines[0].strip()
            if len(first_line) > 50:
                first_line = first_line[:47] + "..."
            if first_line:
                label_parts.append(f"\\n{first_line}")

        # Add key config items in compact format
        if config:
            config_items = []
            for key, value in list(config.items())[:3]:  # Show top 3 config items
                if isinstance(value, (str, int, float, bool)):
                    value_str = str(value)
                    if len(value_str) > 15:
                        value_str = value_str[:12] + "..."
                    config_items.append(f"{key}: {value_str}")
            if config_items:
                config_line = " | ".join(config_items)
                label_parts.append(f"\\n{config_line}")

        # Add entry point indicator
        if is_entry:
            label_parts.append("\\n🔹 ENTRY POINT")

        label = "\\n".join(label_parts)

        lines.append(f'{routine_id}: "{label}" {{')

        # Apply styling with better visual hierarchy
        lines.append("  style: {")
        lines.append(f'    fill: "{fill_color}"')
        lines.append(f'    stroke: "{stroke_color}"')
        lines.append(f"    stroke-width: {stroke_width}")
        lines.append("    font-size: 16")
        lines.append("    bold: true")
        lines.append("    shadow: true")
        lines.append("  }")

        # Add shape configuration
        lines.append("  shape: rectangle")

        # Create slots section with better organization
        if slots:
            lines.append("  slots: {")
            for slot in slots:
                slot_name = slot.get("name", "unknown")
                handler = slot.get("handler")
                merge_strategy = slot.get("merge_strategy", "override")

                # Better formatted slot label (compact format)
                slot_label = f"{slot_name}"
                if handler:
                    slot_label += f"\\n→ {handler}()"
                if merge_strategy != "override":
                    slot_label += f"\\n[{merge_strategy}]"

                lines.append(f'    {slot_name}: "{slot_label}" {{')
                lines.append("      style: {")
                lines.append('        fill: "#e3f2fd"')
                lines.append('        stroke: "#1976d2"')
                lines.append("        stroke-width: 2")
                lines.append("        font-size: 12")
                lines.append("        bold: true")
                lines.append("      }")
                lines.append("    }")
            lines.append("  }")

        # Create events section with better organization
        if events:
            lines.append("  events: {")
            for event in events:
                event_name = event.get("name", "unknown")
                params = event.get("output_params", [])

                # Better formatted event label (compact format)
                event_label = f"{event_name}"
                if params:
                    params_str = ", ".join(params[:3])  # Show top 3 params
                    if len(params) > 3:
                        params_str += f" (+{len(params) - 3})"
                    event_label += f"\\n({params_str})"

                lines.append(f'    {event_name}: "{event_label}" {{')
                lines.append("      style: {")
                lines.append('        fill: "#fff3e0"')
                lines.append('        stroke: "#f57c00"')
                lines.append("        stroke-width: 2")
                lines.append("        font-size: 12")
                lines.append("        bold: true")
                lines.append("      }")
                lines.append("    }")
            lines.append("  }")

        # Add methods info if available (as comment or label extension)
        if methods:
            method_names = [m.get("name", "") for m in methods[:3]]
            if method_names:
                methods_str = ", ".join(method_names)
                if len(methods) > 3:
                    methods_str += f" (+{len(methods) - 3})"
                lines.append(f"  # Methods: {methods_str}")

        lines.append("}")

        return lines

    def _format_ultimate_connection(self, conn: dict[str, Any]) -> list[str]:
        """Format a connection in ultimate D2 format with enhanced styling.

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

        # Build connection path
        connection_path = f"{source_id}.events.{source_event} -> {target_id}.slots.{target_slot}"

        # Build label
        label = f"{source_event} → {target_slot}"
        if param_mapping:
            mapping_items = list(param_mapping.items())[:2]
            mapping_str = ", ".join(f"{k}→{v}" for k, v in mapping_items)
            if len(param_mapping) > 2:
                mapping_str += f" (+{len(param_mapping) - 2})"
            label += f"\\n[{mapping_str}]"

        # Determine connection style based on event/slot names and types
        event_lower = source_event.lower()
        slot_lower = target_slot.lower()
        slot_lower = slot_lower

        # Determine connection type and styling based on semantic meaning
        # Check if this is a result aggregation connection (worker result -> aggregator)
        is_result_aggregation = ("result" in event_lower and "aggregator" in target_id.lower()) or (
            "aggregated" in event_lower
        )

        # Check if this is worker task distribution (dispatcher -> worker)
        is_worker_distribution = "worker" in event_lower and "worker" in target_id.lower()

        # Determine connection type and styling
        if "continue" in event_lower or ("loop" in event_lower and "exit" not in event_lower):
            # Continue loop connections - dashed, animated, brown
            stroke_color = "#8b4513"  # Brown
            stroke_dash = 5
            animated = True
        elif "exit" in event_lower and "loop" in event_lower:
            # Exit loop connections - solid, animated, dark green (success path)
            stroke_color = "#2e7d32"  # Dark green
            stroke_dash = None
            animated = True
        elif is_result_aggregation:
            # Result aggregation - solid, animated, green
            stroke_color = "#388e3c"  # Green
            stroke_dash = None
            animated = True
        elif is_worker_distribution:
            # Worker task distribution - dashed, animated, blue
            stroke_color = "#1976d2"  # Blue
            stroke_dash = 5
            animated = True
        elif "error" in event_lower or "invalid" in event_lower:
            # Error paths - dashed, red, not animated
            stroke_color = "#d32f2f"  # Red
            stroke_dash = 5
            animated = False
        elif "priority" in event_lower or "route" in event_lower or "router" in target_id.lower():
            # Routing connections - dashed, orange, animated
            stroke_color = "#f57c00"  # Orange
            stroke_dash = 5
            animated = True
        else:
            # Default data flow - solid, dark, animated
            stroke_color = "#424242"  # Dark gray
            stroke_dash = None
            animated = True

        lines.append(f'{connection_path}: "{label}" {{')
        lines.append("  style: {")
        lines.append(f'    stroke: "{stroke_color}"')
        lines.append("    stroke-width: 3")
        if stroke_dash:
            lines.append(f"    stroke-dash: {stroke_dash}")
        if animated:
            lines.append("    animated: true")
        lines.append("    opacity: 0.85")
        lines.append("  }")
        lines.append("}")

        return lines

    def _format_dependency_section(
        self, dependency_graph: dict[str, list[str]], entry_points: set
    ) -> list[str]:
        """Format dependency graph section.

        Args:
            dependency_graph: Dependency graph dictionary.
            entry_points: Set of entry point routine IDs.

        Returns:
            List of D2 lines.
        """
        lines = []
        lines.append("# Execution Dependencies")
        lines.append("# (Shows which routines depend on others)")
        lines.append("")

        # Group routines by dependency level
        levels: dict[int, list[str]] = {}
        processed = set()

        # Level 0: Entry points
        for routine_id in entry_points:
            levels.setdefault(0, []).append(routine_id)
            processed.add(routine_id)

        # Assign levels for other routines
        max_level = 0
        remaining = set(dependency_graph.keys()) - processed

        while remaining:
            level = max_level + 1
            found_any = False

            for routine_id in list(remaining):
                deps = dependency_graph.get(routine_id, [])
                if all(dep in processed for dep in deps):
                    levels.setdefault(level, []).append(routine_id)
                    processed.add(routine_id)
                    remaining.remove(routine_id)
                    found_any = True

            if found_any:
                max_level = level
            else:
                # Handle circular dependencies
                for routine_id in remaining:
                    levels.setdefault(level, []).append(routine_id)
                    processed.add(routine_id)
                break

        # Add comment about levels
        if len(levels) > 1:
            lines.append(f"# Execution levels: {len(levels)}")
            for level, routine_ids in sorted(levels.items()):
                lines.append(f"# Level {level}: {', '.join(routine_ids)}")

        lines.append("")

        return lines

    def save_d2(
        self,
        data: dict[str, Any],
        output_path: str | Path,
        mode: str = "standard",
        routine_analysis: str | Path | dict[str, Any] | None = None,
    ) -> None:
        """Save workflow analysis as D2 format file.

        Args:
            data: Workflow analysis result dictionary.
            output_path: Path to output D2 file.
            mode: Export mode - "standard" for basic visualization,
                  "ultimate" for detailed professional visualization.
            routine_analysis: Optional routine analysis data. Can be:
                - Path to JSON file containing routine analysis
                - Dictionary containing routine analysis data
                If provided in ultimate mode, will enhance nodes with detailed information.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        d2_content = self.to_d2_format(data, mode=mode, routine_analysis=routine_analysis)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(d2_content)


def analyze_workflow(flow: Flow, include_source_analysis: bool = True) -> dict[str, Any]:
    """Convenience function to analyze a workflow.

    Args:
        flow: Flow object to analyze.
        include_source_analysis: Whether to analyze routine source files.

    Returns:
        Dictionary containing structured workflow information.
    """
    analyzer = WorkflowAnalyzer()
    return analyzer.analyze_flow(flow, include_source_analysis)
