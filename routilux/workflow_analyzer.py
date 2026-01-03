"""
Workflow analyzer module.

Dynamically analyzes Flow objects to generate structured workflow descriptions.
Combines with routine_analyzer to provide complete workflow information.
"""

from __future__ import annotations
import json
import inspect
from typing import Dict, Any, List, Optional, Union
from pathlib import Path

from routilux.flow import Flow
from routilux.routine import Routine
from routilux.routine_analyzer import RoutineAnalyzer


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
    
    def __init__(self, routine_analyzer: Optional[RoutineAnalyzer] = None):
        """Initialize the workflow analyzer.
        
        Args:
            routine_analyzer: Optional RoutineAnalyzer instance for analyzing
                routine source files. If None, a new instance will be created.
        """
        self.routine_analyzer = routine_analyzer or RoutineAnalyzer()
    
    def analyze_flow(self, flow: Flow, include_source_analysis: bool = True) -> Dict[str, Any]:
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
        result = {
            "flow_id": flow.flow_id,
            "execution_strategy": flow.execution_strategy,
            "max_workers": flow.max_workers,
            "execution_timeout": flow.execution_timeout,
            "routines": [],
            "connections": [],
            "dependency_graph": {},
            "entry_points": []
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
    
    def _analyze_routine(self, routine_id: str, routine: Routine, include_source_analysis: bool) -> Dict[str, Any]:
        """Analyze a routine instance.
        
        Args:
            routine_id: ID of the routine in the flow.
            routine: Routine instance.
            include_source_analysis: Whether to analyze source file.
        
        Returns:
            Dictionary containing routine information.
        """
        routine_info = {
            "routine_id": routine_id,
            "class_name": routine.__class__.__name__,
            "docstring": inspect.getdoc(routine.__class__) or "",
            "slots": [],
            "events": [],
            "config": dict(routine._config) if hasattr(routine, "_config") else {},
            "source_info": None
        }
        
        # Extract slots
        if hasattr(routine, "_slots"):
            for slot_name, slot in routine._slots.items():
                slot_info = {
                    "name": slot_name,
                    "handler": None,
                    "merge_strategy": getattr(slot, "merge_strategy", "override")
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
                    "output_params": getattr(event, "output_params", [])
                }
                routine_info["events"].append(event_info)
        
        # Try to analyze source file if requested
        if include_source_analysis:
            source_info = self._analyze_routine_source(routine)
            if source_info:
                routine_info["source_info"] = source_info
        
        return routine_info
    
    def _analyze_routine_source(self, routine: Routine) -> Optional[Dict[str, Any]]:
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
                analysis = self.routine_analyzer.analyze_file(source_file)
                
                # Find the specific routine class in the analysis
                for routine_data in analysis.get("routines", []):
                    if routine_data["name"] == routine.__class__.__name__:
                        return routine_data
        except (OSError, TypeError):
            # Source file not available (e.g., built-in, dynamically created)
            pass
        
        return None
    
    def _get_routine_id(self, routine: Routine, flow: Flow) -> Optional[str]:
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
    
    def _analyze_connection(self, connection, flow: Flow) -> Optional[Dict[str, Any]]:
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
        
        conn_info = {
            "source_routine_id": source_routine_id,
            "source_event": connection.source_event.name,
            "target_routine_id": target_routine_id,
            "target_slot": connection.target_slot.name,
            "param_mapping": dict(connection.param_mapping) if connection.param_mapping else {}
        }
        
        return conn_info
    
    def _build_dependency_graph(self, flow: Flow) -> Dict[str, List[str]]:
        """Build dependency graph from connections.
        
        Args:
            flow: Flow object.
        
        Returns:
            Dictionary mapping routine_id to list of dependency routine_ids.
            If A.event -> B.slot, then B depends on A.
        """
        dependency_graph = {routine_id: [] for routine_id in flow.routines.keys()}
        
        for connection in flow.connections:
            if not connection.source_event or not connection.target_slot:
                continue
            
            source_routine = connection.source_event.routine
            target_routine = connection.target_slot.routine
            
            source_routine_id = self._get_routine_id(source_routine, flow)
            target_routine_id = self._get_routine_id(target_routine, flow)
            
            if source_routine_id and target_routine_id and source_routine_id != target_routine_id:
                if source_routine_id not in dependency_graph[target_routine_id]:
                    dependency_graph[target_routine_id].append(source_routine_id)
        
        return dependency_graph
    
    def _find_entry_points(self, flow: Flow) -> List[str]:
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
    
    def to_json(self, data: Dict[str, Any], indent: int = 2) -> str:
        """Convert analysis result to JSON string.
        
        Args:
            data: Analysis result dictionary.
            indent: JSON indentation level.
        
        Returns:
            JSON string representation.
        """
        serializable_data = self._make_json_serializable(data)
        return json.dumps(serializable_data, indent=indent, ensure_ascii=False)
    
    def save_json(self, data: Dict[str, Any], output_path: Union[str, Path], indent: int = 2) -> None:
        """Save analysis result to JSON file.
        
        Args:
            data: Analysis result dictionary.
            output_path: Path to output JSON file.
            indent: JSON indentation level.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        serializable_data = self._make_json_serializable(data)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_data, f, indent=indent, ensure_ascii=False)
    
    def to_d2_format(self, data: Dict[str, Any]) -> str:
        """Convert workflow analysis to D2 format string.
        
        D2 is a diagramming language. This method generates a D2 script
        that can be used to visualize the workflow.
        
        Args:
            data: Workflow analysis result dictionary.
        
        Returns:
            D2 format string.
        """
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
    
    def save_d2(self, data: Dict[str, Any], output_path: Union[str, Path]) -> None:
        """Save workflow analysis as D2 format file.
        
        Args:
            data: Workflow analysis result dictionary.
            output_path: Path to output D2 file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        d2_content = self.to_d2_format(data)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(d2_content)


def analyze_workflow(flow: Flow, include_source_analysis: bool = True) -> Dict[str, Any]:
    """Convenience function to analyze a workflow.
    
    Args:
        flow: Flow object to analyze.
        include_source_analysis: Whether to analyze routine source files.
    
    Returns:
        Dictionary containing structured workflow information.
    """
    analyzer = WorkflowAnalyzer()
    return analyzer.analyze_flow(flow, include_source_analysis)

