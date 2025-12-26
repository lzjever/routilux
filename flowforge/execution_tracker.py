"""
Execution tracker.

Tracks flow execution state and performance metrics.
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional
from datetime import datetime
from flowforge.utils.serializable import register_serializable, Serializable


@register_serializable
class ExecutionTracker(Serializable):
    """Execution tracker for monitoring flow execution state and performance.
    
    Tracks routine executions, event flow, and performance metrics to provide
    insights into flow behavior and optimization opportunities.
    """
    
    def __init__(self, flow_id: str = ""):
        """Initialize ExecutionTracker.

        Args:
            flow_id: Flow identifier.
        """
        super().__init__()
        self.flow_id: str = flow_id
        self.routine_executions: Dict[str, List[Dict[str, Any]]] = {}
        self.event_flow: List[Dict[str, Any]] = []
        self.performance_metrics: Dict[str, Any] = {}
        
        # Register serializable fields
        self.add_serializable_fields([
            "flow_id", "routine_executions", "event_flow", "performance_metrics"
        ])
    
    def record_routine_start(self, routine_id: str, params: Dict[str, Any] = None) -> None:
        """Record the start of routine execution.

        Args:
            routine_id: Routine identifier.
            params: Execution parameters.
        """
        if routine_id not in self.routine_executions:
            self.routine_executions[routine_id] = []
        
        execution = {
            "routine_id": routine_id,
            "start_time": datetime.now().isoformat(),
            "params": params or {},
            "status": "running"
        }
        self.routine_executions[routine_id].append(execution)
    
    def record_routine_end(
        self,
        routine_id: str,
        status: str = "completed",
        result: Any = None,
        error: Optional[str] = None
    ) -> None:
        """Record the end of routine execution.

        Args:
            routine_id: Routine identifier.
            status: Execution status ("completed", "failed").
            result: Execution result.
            error: Error message if execution failed.
        """
        if routine_id not in self.routine_executions:
            return
        
        if not self.routine_executions[routine_id]:
            return
        
        execution = self.routine_executions[routine_id][-1]
        execution["end_time"] = datetime.now().isoformat()
        execution["status"] = status
        
        if result is not None:
            execution["result"] = result
        
        if error is not None:
            execution["error"] = error
        
        # Calculate execution time
        if "start_time" in execution and "end_time" in execution:
            start = datetime.fromisoformat(execution["start_time"])
            end = datetime.fromisoformat(execution["end_time"])
            execution["execution_time"] = (end - start).total_seconds()
    
    def record_event(
        self,
        source_routine_id: str,
        event_name: str,
        target_routine_id: Optional[str] = None,
        data: Dict[str, Any] = None
    ) -> None:
        """Record an event emission.

        Args:
            source_routine_id: Source routine identifier.
            event_name: Event name.
            target_routine_id: Target routine identifier if applicable.
            data: Transmitted data.
        """
        event_record = {
            "timestamp": datetime.now().isoformat(),
            "source_routine_id": source_routine_id,
            "event_name": event_name,
            "target_routine_id": target_routine_id,
            "data": data or {}
        }
        self.event_flow.append(event_record)
    
    def get_routine_performance(self, routine_id: str) -> Optional[Dict[str, Any]]:
        """Get performance metrics for a routine.

        Args:
            routine_id: Routine identifier.

        Returns:
            Dictionary containing performance metrics, or None if routine not found.
        """
        if routine_id not in self.routine_executions:
            return None
        
        executions = self.routine_executions[routine_id]
        if not executions:
            return None
        
        # Calculate statistics
        total_executions = len(executions)
        completed = sum(1 for e in executions if e.get("status") == "completed")
        failed = sum(1 for e in executions if e.get("status") == "failed")
        
        execution_times = [
            e.get("execution_time", 0)
            for e in executions
            if "execution_time" in e
        ]
        
        avg_time = sum(execution_times) / len(execution_times) if execution_times else 0
        min_time = min(execution_times) if execution_times else 0
        max_time = max(execution_times) if execution_times else 0
        
        return {
            "total_executions": total_executions,
            "completed": completed,
            "failed": failed,
            "success_rate": completed / total_executions if total_executions > 0 else 0,
            "avg_execution_time": avg_time,
            "min_execution_time": min_time,
            "max_execution_time": max_time
        }
    
    def get_flow_performance(self) -> Dict[str, Any]:
        """Get performance metrics for the entire flow.

        Returns:
            Dictionary containing overall flow performance metrics.
        """
        total_routines = len(self.routine_executions)
        total_events = len(self.event_flow)
        
        all_execution_times = []
        for routine_id in self.routine_executions:
            perf = self.get_routine_performance(routine_id)
            if perf and perf.get("avg_execution_time"):
                all_execution_times.append(perf["avg_execution_time"])
        
        total_time = sum(all_execution_times)
        avg_time = total_time / len(all_execution_times) if all_execution_times else 0
        
        return {
            "total_routines": total_routines,
            "total_events": total_events,
            "total_execution_time": total_time,
            "avg_routine_time": avg_time
        }

