"""
Unified monitoring service for accessing monitoring data.

This service provides a centralized interface for retrieving monitoring data,
including routine execution status, queue status, and metadata.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional, Set

if TYPE_CHECKING:
    from routilux.flow.flow import Flow
    from routilux.job_state import JobState
    from routilux.routine import Routine

# Import models with TYPE_CHECKING to avoid circular import
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from routilux.api.models.monitor import (
        JobMonitoringData,
        RoutineExecutionStatus,
        RoutineInfo,
        RoutineMonitoringData,
        SlotQueueStatus,
    )
from routilux.monitoring.flow_registry import FlowRegistry
from routilux.monitoring.registry import MonitoringRegistry
from routilux.monitoring.storage import job_store
from routilux.runtime import get_runtime_instance


class MonitorService:
    """Unified monitoring data access service.

    This service provides a centralized interface for retrieving monitoring data,
    abstracting away the complexity of accessing Runtime, JobState, Flow, and
    MonitoringRegistry.

    Examples:
        >>> service = MonitorService()
        >>> monitoring_data = service.get_job_monitoring_data(job_id)
        >>> routine_data = service.get_routine_monitoring_data(job_id, routine_id)
    """

    def __init__(self):
        """Initialize MonitorService."""
        self._runtime = None
        self._registry = MonitoringRegistry.get_instance()

    def _get_runtime(self):
        """Get Runtime instance (lazy initialization)."""
        if self._runtime is None:
            self._runtime = get_runtime_instance()
        return self._runtime

    def get_active_routines(self, job_id: str) -> Set[str]:
        """Get set of routine IDs that are currently executing for a job.

        Args:
            job_id: Job identifier.

        Returns:
            Set of routine IDs that are currently active (executing).
        """
        runtime = self._get_runtime()
        return runtime.get_active_routines(job_id)

    def get_routine_execution_status(
        self, job_id: str, routine_id: str, job_state: Optional[JobState] = None
    ) -> "RoutineExecutionStatus":
        """Get execution status for a specific routine.

        Args:
            job_id: Job identifier.
            routine_id: Routine identifier.
            job_state: Optional JobState (will be fetched if not provided).

        Returns:
            RoutineExecutionStatus with current execution state.
        """
        if job_state is None:
            job_state = job_store.get(job_id)
            if not job_state:
                raise ValueError(f"Job '{job_id}' not found")

        # Check if currently executing
        active_routines = self.get_active_routines(job_id)
        is_active = routine_id in active_routines

        # Get routine state
        routine_state = job_state.get_routine_state(routine_id)

        # Determine status - ensure it's always a string
        if routine_state:
            status_value = routine_state.get("status", "pending")
            # Convert to string if it's an enum or other type
            status = str(status_value) if status_value is not None else "pending"
        elif is_active:
            status = "running"
        else:
            status = "pending"

        # Get metrics
        # Lazy import to avoid circular dependency
        from routilux.api.models.monitor import RoutineExecutionStatus

        execution_count = 0
        error_count = 0
        last_execution_time = None

        collector = self._registry.monitor_collector
        if collector:
            metrics = collector.get_metrics(job_id)
            if metrics and routine_id in metrics.routine_metrics:
                rm = metrics.routine_metrics[routine_id]
                execution_count = rm.execution_count
                error_count = rm.error_count
                last_execution_time = rm.last_execution

        return RoutineExecutionStatus(
            routine_id=routine_id,
            is_active=is_active,
            status=status,
            last_execution_time=last_execution_time,
            execution_count=execution_count,
            error_count=error_count,
        )

    def get_routine_queue_status(
        self, job_id: str, routine_id: str
    ) -> List["SlotQueueStatus"]:
        """Get queue status for all slots in a routine.

        Args:
            job_id: Job identifier.
            routine_id: Routine identifier.

        Returns:
            List of SlotQueueStatus for all slots in the routine.
        """
        job_state = job_store.get(job_id)
        if not job_state:
            raise ValueError(f"Job '{job_id}' not found")

        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get(job_state.flow_id)
        if not flow:
            raise ValueError(f"Flow '{job_state.flow_id}' not found")

        if routine_id not in flow.routines:
            raise ValueError(f"Routine '{routine_id}' not found")

        routine = flow.routines[routine_id]

        # Lazy import to avoid circular dependency
        from routilux.api.models.monitor import SlotQueueStatus

        queue_statuses = []
        for slot_name, slot in routine.slots.items():
            status = slot.get_queue_status()
            queue_statuses.append(
                SlotQueueStatus(
                    slot_name=slot_name,
                    routine_id=routine_id,
                    **status,
                )
            )

        return queue_statuses

    def get_routine_info(self, flow_id: str, routine_id: str) -> "RoutineInfo":
        """Get metadata information for a routine.

        Args:
            flow_id: Flow identifier.
            routine_id: Routine identifier.

        Returns:
            RoutineInfo with routine metadata.
        """
        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get(flow_id)
        if not flow:
            raise ValueError(f"Flow '{flow_id}' not found")

        if routine_id not in flow.routines:
            raise ValueError(f"Routine '{routine_id}' not found")

        routine = flow.routines[routine_id]

        # Get policy information
        policy_info = routine.get_activation_policy_info()

        # Get config
        config = routine.get_all_config()

        # Get slots and events
        slots = list(routine.slots.keys())
        events = list(routine.events.keys())

        # Lazy import to avoid circular dependency
        from routilux.api.models.monitor import RoutineInfo

        # Get routine type
        routine_type = type(routine).__name__

        return RoutineInfo(
            routine_id=routine_id,
            routine_type=routine_type,
            activation_policy=policy_info,
            config=config,
            slots=slots,
            events=events,
        )

    def get_routine_monitoring_data(
        self, job_id: str, routine_id: str
    ) -> "RoutineMonitoringData":
        """Get complete monitoring data for a routine.

        Args:
            job_id: Job identifier.
            routine_id: Routine identifier.

        Returns:
            RoutineMonitoringData with execution status, queue status, and metadata.
        """
        job_state = job_store.get(job_id)
        if not job_state:
            raise ValueError(f"Job '{job_id}' not found")

        # Lazy import to avoid circular dependency
        from routilux.api.models.monitor import RoutineMonitoringData

        # Get execution status
        execution_status = self.get_routine_execution_status(job_id, routine_id, job_state)

        # Get queue status
        queue_status = self.get_routine_queue_status(job_id, routine_id)

        # Get metadata
        info = self.get_routine_info(job_state.flow_id, routine_id)

        return RoutineMonitoringData(
            routine_id=routine_id,
            execution_status=execution_status,
            queue_status=queue_status,
            info=info,
        )

    def get_job_monitoring_data(self, job_id: str) -> "JobMonitoringData":
        """Get complete monitoring data for a job.

        Args:
            job_id: Job identifier.

        Returns:
            JobMonitoringData with monitoring data for all routines.
        """
        job_state = job_store.get(job_id)
        if not job_state:
            raise ValueError(f"Job '{job_id}' not found")

        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get(job_state.flow_id)
        if not flow:
            raise ValueError(f"Flow '{job_state.flow_id}' not found")

        # Lazy import to avoid circular dependency
        from routilux.api.models.monitor import JobMonitoringData

        # Build monitoring data for each routine
        routines_data: Dict[str, "RoutineMonitoringData"] = {}
        for routine_id in flow.routines.keys():
            routines_data[routine_id] = self.get_routine_monitoring_data(job_id, routine_id)

        return JobMonitoringData(
            job_id=job_id,
            flow_id=job_state.flow_id,
            job_status=str(job_state.status),
            routines=routines_data,
            updated_at=job_state.updated_at,
        )

    def get_all_routines_status(
        self, job_id: str
    ) -> Dict[str, "RoutineExecutionStatus"]:
        """Get execution status for all routines in a job.

        Args:
            job_id: Job identifier.

        Returns:
            Dictionary mapping routine_id to RoutineExecutionStatus.
        """
        job_state = job_store.get(job_id)
        if not job_state:
            raise ValueError(f"Job '{job_id}' not found")

        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get(job_state.flow_id)
        if not flow:
            raise ValueError(f"Flow '{job_state.flow_id}' not found")

        routines_status: Dict[str, RoutineExecutionStatus] = {}
        for routine_id in flow.routines.keys():
            routines_status[routine_id] = self.get_routine_execution_status(
                job_id, routine_id, job_state
            )

        return routines_status

    def get_all_queues_status(
        self, job_id: str
    ) -> Dict[str, List["SlotQueueStatus"]]:
        """Get queue status for all routines in a job.

        Args:
            job_id: Job identifier.

        Returns:
            Dictionary mapping routine_id to list of SlotQueueStatus.
        """
        job_state = job_store.get(job_id)
        if not job_state:
            raise ValueError(f"Job '{job_id}' not found")

        flow_registry = FlowRegistry.get_instance()
        flow = flow_registry.get(job_state.flow_id)
        if not flow:
            raise ValueError(f"Flow '{job_state.flow_id}' not found")

        all_queues: Dict[str, List[SlotQueueStatus]] = {}
        for routine_id in flow.routines.keys():
            all_queues[routine_id] = self.get_routine_queue_status(job_id, routine_id)

        return all_queues


# Global MonitorService instance
_monitor_service: Optional[MonitorService] = None


def get_monitor_service() -> MonitorService:
    """Get global MonitorService instance.

    Returns:
        Global MonitorService instance.
    """
    global _monitor_service
    if _monitor_service is None:
        _monitor_service = MonitorService()
    return _monitor_service
