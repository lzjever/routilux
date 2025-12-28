"""
Execution tracker.

Tracks flow execution state and performance metrics.
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from datetime import datetime
from serilux import register_serializable, Serializable


@register_serializable
class ExecutionTracker(Serializable):
    """Execution tracker for monitoring flow execution state and performance.

    ExecutionTracker provides detailed monitoring and performance analysis
    capabilities for flow execution. It tracks routine executions, event flow,
    and performance metrics to help understand flow behavior and identify
    optimization opportunities.

    Key Features:
        - Routine Execution Tracking: Start/end times, parameters, results
        - Event Flow Tracking: Record all event emissions and data flow
        - Performance Metrics: Execution times, throughput, bottlenecks
        - Execution Analysis: Query execution patterns and statistics

    Data Structure:
        - routine_executions: Dict mapping routine_id to list of execution records
        - event_flow: List of all event emissions with source/target information
        - performance_metrics: Dictionary of calculated performance metrics

    Use Cases:
        - Performance Analysis: Identify slow routines, bottlenecks
        - Debugging: Trace execution flow and data transmission
        - Monitoring: Track routine execution patterns
        - Optimization: Find opportunities to improve flow performance

    Examples:
        Basic usage:
            >>> tracker = ExecutionTracker(flow_id="my_flow")
            >>> flow.execution_tracker = tracker
            >>> # Tracker automatically records during execution
            >>> # After execution, analyze results:
            >>> metrics = tracker.get_performance_metrics()
            >>> print(f"Total executions: {metrics.get('total_executions')}")

        Analyze routine performance:
            >>> executions = tracker.routine_executions.get("my_routine", [])
            >>> for exec in executions:
            ...     print(f"Duration: {exec.get('execution_time')}s")
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
        self.add_serializable_fields(
            ["flow_id", "routine_executions", "event_flow", "performance_metrics"]
        )

    def record_routine_start(self, routine_id: str, params: Dict[str, Any] = None) -> None:
        """Record the start of a routine execution.

        This method is called when a routine begins execution. It creates
        a new execution record with start time and parameters. The record
        is completed when record_routine_end() is called.

        Args:
            routine_id: Unique identifier of the routine starting execution.
                Must match the ID used when adding the routine to the flow.
            params: Optional dictionary of parameters passed to the routine.
                These are the keyword arguments passed to ``routine.__call__(**params)``.
                Example: {"input": "data", "count": 42}

        Side Effects:
            - Creates a new execution record in routine_executions[routine_id]
            - Sets start_time to current timestamp
            - Sets status to "running"
            - Stores params in the execution record

        Examples:
            Record routine start:
                >>> tracker.record_routine_start("processor", {"input": "data"})
                >>> # Later, call record_routine_end() to complete the record
        """
        if routine_id not in self.routine_executions:
            self.routine_executions[routine_id] = []

        execution = {
            "routine_id": routine_id,
            "start_time": datetime.now().isoformat(),
            "params": params or {},
            "status": "running",
        }
        self.routine_executions[routine_id].append(execution)

    def record_routine_end(
        self,
        routine_id: str,
        status: str = "completed",
        result: Any = None,
        error: Optional[str] = None,
    ) -> None:
        """Record the end of a routine execution.

        This method completes an execution record started by record_routine_start().
        It updates the record with end time, status, result, and calculates
        execution duration.

        Args:
            routine_id: Unique identifier of the routine completing execution.
                Must match the ID used in record_routine_start().
            status: Execution status. Common values:
                - "completed": Routine executed successfully
                - "failed": Routine execution failed
                - "skipped": Routine was skipped
                - "error_continued": Error occurred but execution continued
            result: Optional execution result. Can be any serializable value.
                Stored in the execution record for later analysis.
            error: Optional error message if execution failed.
                Should be a string describing the error.
                Only used when status is "failed" or "error_continued".

        Side Effects:
            - Updates the most recent execution record for routine_id
            - Sets end_time to current timestamp
            - Updates status, result, and error fields
            - Calculates execution_time (end_time - start_time)

        Examples:
            Record successful completion:
                >>> tracker.record_routine_end("processor", "completed", result="success")

            Record failure:
                >>> tracker.record_routine_end(
                ...     "processor",
                ...     status="failed",
                ...     error="Connection timeout"
                ... )
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
        data: Dict[str, Any] = None,
    ) -> None:
        """Record an event emission in the event flow.

        This method records when a routine emits an event, tracking the
        data flow from source to target routines. This helps understand
        the execution flow and data transmission patterns.

        Args:
            source_routine_id: Unique identifier of the routine emitting the event.
                This is the routine that called emit().
            event_name: Name of the event that was emitted.
                Example: "output", "result", "error"
            target_routine_id: Optional identifier of the target routine receiving data.
                If the event is connected to multiple slots, this may be the first
                target or None if unknown. Used for tracking data flow direction.
            data: Optional dictionary of data transmitted with the event.
                This contains the keyword arguments passed to ``emit(**kwargs)``.
                Example: {"result": "success", "count": 42}

        Side Effects:
            - Appends a new event record to event_flow list
            - Record includes timestamp, source, target, event name, and data

        Examples:
            Record event emission:
                >>> tracker.record_event(
                ...     "processor",
                ...     "output",
                ...     target_routine_id="validator",
                ...     data={"result": "processed", "count": 10}
                ... )
        """
        event_record = {
            "timestamp": datetime.now().isoformat(),
            "source_routine_id": source_routine_id,
            "event_name": event_name,
            "target_routine_id": target_routine_id,
            "data": data or {},
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

        execution_times = [e.get("execution_time", 0) for e in executions if "execution_time" in e]

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
            "max_execution_time": max_time,
        }

    def get_flow_performance(self) -> Dict[str, Any]:
        """Get performance metrics for the entire flow.

        This method aggregates performance metrics across all routines in
        the flow to provide an overall view of flow performance.

        Returns:
            Dictionary containing overall flow performance metrics:
            - total_routines: int - Number of routines that executed
            - total_events: int - Total number of events emitted
            - total_execution_time: float - Sum of all routine execution times
            - avg_routine_time: float - Average execution time per routine

        Examples:
            Get overall flow performance:
                >>> metrics = tracker.get_flow_performance()
                >>> print(f"Total routines: {metrics['total_routines']}")
                >>> print(f"Total events: {metrics['total_events']}")
                >>> print(f"Total time: {metrics['total_execution_time']:.2f}s")
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
            "avg_routine_time": avg_time,
        }
