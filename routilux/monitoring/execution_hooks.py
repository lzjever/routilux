"""
Monitoring implementation of ExecutionHooksInterface.

This module implements the core ExecutionHooksInterface with monitoring
capabilities including metrics collection, breakpoint support, and
event broadcasting.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from routilux.core.hooks import ExecutionHooksInterface

if TYPE_CHECKING:
    from routilux.core.context import JobContext
    from routilux.core.event import Event
    from routilux.core.flow import Flow
    from routilux.core.worker import WorkerState

logger = logging.getLogger(__name__)


def _publish_event_via_manager(job_id: str, event: dict) -> None:
    """Publish event via event manager with error handling (fire-and-forget).

    Args:
        job_id: Job identifier
        event: Event dictionary to publish
    """
    try:
        from routilux.monitoring.event_manager import get_event_manager

        event_manager = get_event_manager()

        try:
            asyncio.get_running_loop()
            asyncio.create_task(event_manager.publish(job_id, event))
        except RuntimeError:
            # No running event loop - skip publishing
            return
    except (RuntimeError, AttributeError):
        pass
    except Exception as e:
        logger.error(f"Failed to publish event to job {job_id}: {e}")


class MonitoringExecutionHooks(ExecutionHooksInterface):
    """Monitoring implementation of execution hooks.

    Implements ExecutionHooksInterface with:
    - Metrics collection via MonitorCollector
    - Breakpoint support via BreakpointManager
    - Event broadcasting via EventManager
    - Debug session management

    All methods check if monitoring is enabled before proceeding,
    ensuring zero overhead when monitoring is disabled.
    """

    def on_worker_start(self, flow: Flow, worker_state: WorkerState) -> None:
        """Called when a worker starts execution.

        Args:
            flow: Flow being executed
            worker_state: Worker state
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled():
            return

        registry = MonitoringRegistry.get_instance()
        collector = registry.monitor_collector

        if collector:
            collector.record_flow_start(flow.flow_id, worker_state.worker_id)

            _publish_event_via_manager(
                worker_state.worker_id,
                {
                    "type": "worker_start",
                    "worker_id": worker_state.worker_id,
                    "flow_id": flow.flow_id,
                },
            )

    def on_worker_stop(self, flow: Flow, worker_state: WorkerState, status: str) -> None:
        """Called when a worker stops execution.

        Args:
            flow: Flow being executed
            worker_state: Worker state
            status: Final status ("completed", "failed", "cancelled")
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled():
            return

        registry = MonitoringRegistry.get_instance()
        collector = registry.monitor_collector

        if collector:
            collector.record_flow_end(worker_state.worker_id, status)

            metrics = collector.get_metrics(worker_state.worker_id)
            if metrics:
                _publish_event_via_manager(
                    worker_state.worker_id,
                    {
                        "type": "worker_stop",
                        "worker_id": worker_state.worker_id,
                        "flow_id": flow.flow_id,
                        "status": status,
                        "metrics": {
                            "start_time": metrics.start_time.isoformat()
                            if metrics.start_time
                            else None,
                            "end_time": metrics.end_time.isoformat() if metrics.end_time else None,
                            "duration": metrics.duration,
                            "total_events": metrics.total_events,
                            "total_slot_calls": metrics.total_slot_calls,
                            "total_event_emits": metrics.total_event_emits,
                        },
                    },
                )

    def on_job_start(self, job_context: JobContext, worker_state: WorkerState) -> None:
        """Called when a job starts processing.

        Args:
            job_context: Job context
            worker_state: Worker state
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled():
            return

        _publish_event_via_manager(
            worker_state.worker_id,
            {
                "type": "job_start",
                "worker_id": worker_state.worker_id,
                "job_id": job_context.job_id,
                "metadata": job_context.metadata,
            },
        )

    def on_job_end(
        self,
        job_context: JobContext,
        worker_state: WorkerState,
        status: str = "completed",
        error: Exception | None = None,
    ) -> None:
        """Called when a job finishes processing.

        Args:
            job_context: Job context
            worker_state: Worker state
            status: Final status ("completed", "failed")
            error: Error if failed
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled():
            return

        _publish_event_via_manager(
            worker_state.worker_id,
            {
                "type": "job_end",
                "worker_id": worker_state.worker_id,
                "job_id": job_context.job_id,
                "status": status,
                "error": str(error) if error else None,
                "trace_log": job_context.trace_log,
            },
        )

    def on_routine_start(
        self,
        routine_id: str,
        worker_state: WorkerState,
        job_context: JobContext | None = None,
    ) -> bool:
        """Called when a routine starts execution.

        Args:
            routine_id: Routine identifier
            worker_state: Worker state
            job_context: Optional job context

        Returns:
            True to continue execution, False to pause (e.g., breakpoint)
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled():
            return True

        # Publish routine status change event
        _publish_event_via_manager(
            worker_state.worker_id,
            {
                "type": "routine_status_change",
                "worker_id": worker_state.worker_id,
                "job_id": job_context.job_id if job_context else None,
                "routine_id": routine_id,
                "status": "running",
                "is_active": True,
            },
        )

        # Check breakpoint
        registry = MonitoringRegistry.get_instance()
        breakpoint_mgr = registry.breakpoint_manager
        if breakpoint_mgr:
            breakpoint = breakpoint_mgr.check_breakpoint(
                worker_state.worker_id,
                routine_id,
                "routine_start",
            )
            if breakpoint:
                debug_store = registry.debug_session_store
                if debug_store:
                    session = debug_store.get_or_create(worker_state.worker_id)
                    session.pause(None, reason=f"Breakpoint at routine start: {routine_id}")
                    _publish_event_via_manager(
                        worker_state.worker_id,
                        {
                            "type": "breakpoint_hit",
                            "worker_id": worker_state.worker_id,
                            "breakpoint": {
                                "breakpoint_id": breakpoint.breakpoint_id,
                                "type": breakpoint.type,
                                "routine_id": routine_id,
                            },
                        },
                    )
                    return False

        return True

    def on_routine_end(
        self,
        routine_id: str,
        worker_state: WorkerState,
        job_context: JobContext | None = None,
        status: str = "completed",
        error: Exception | None = None,
    ) -> None:
        """Called when a routine finishes execution.

        Args:
            routine_id: Routine identifier
            worker_state: Worker state
            job_context: Optional job context
            status: Final status
            error: Error if failed
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled():
            return

        _publish_event_via_manager(
            worker_state.worker_id,
            {
                "type": "routine_status_change",
                "worker_id": worker_state.worker_id,
                "job_id": job_context.job_id if job_context else None,
                "routine_id": routine_id,
                "status": status,
                "is_active": False,
                "error": str(error) if error else None,
            },
        )

    def on_event_emit(
        self,
        event: Event,
        source_routine_id: str,
        worker_state: WorkerState,
        job_context: JobContext | None = None,
        data: dict[str, Any] | None = None,
    ) -> bool:
        """Called when an event is emitted.

        Args:
            event: Event being emitted
            source_routine_id: Source routine ID
            worker_state: Worker state
            job_context: Optional job context
            data: Event data

        Returns:
            True to continue propagation, False to block
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled():
            return True

        registry = MonitoringRegistry.get_instance()

        # Record event emission
        collector = registry.monitor_collector
        if collector:
            collector.record_event_emit(event.name, source_routine_id, worker_state.worker_id, data)

        # Publish event
        _publish_event_via_manager(
            worker_state.worker_id,
            {
                "type": "event_emit",
                "worker_id": worker_state.worker_id,
                "job_id": job_context.job_id if job_context else None,
                "routine_id": source_routine_id,
                "event_name": event.name,
                "data_keys": list(data.keys()) if data else [],
            },
        )

        # Check breakpoint
        breakpoint_mgr = registry.breakpoint_manager
        if breakpoint_mgr:
            breakpoint = breakpoint_mgr.check_breakpoint(
                worker_state.worker_id,
                source_routine_id,
                "event",
                event_name=event.name,
                variables=data,
            )
            if breakpoint:
                debug_store = registry.debug_session_store
                if debug_store:
                    session = debug_store.get_or_create(worker_state.worker_id)
                    session.pause(
                        None,
                        reason=f"Breakpoint at event emit: {source_routine_id}.{event.name}",
                    )
                    _publish_event_via_manager(
                        worker_state.worker_id,
                        {
                            "type": "breakpoint_hit",
                            "worker_id": worker_state.worker_id,
                            "breakpoint": {
                                "breakpoint_id": breakpoint.breakpoint_id,
                                "type": breakpoint.type,
                                "routine_id": source_routine_id,
                                "event_name": event.name,
                            },
                        },
                    )
                    return False

        return True


# Singleton instance
_monitoring_hooks: MonitoringExecutionHooks | None = None


def get_monitoring_hooks() -> MonitoringExecutionHooks:
    """Get the monitoring hooks instance.

    Returns:
        MonitoringExecutionHooks singleton
    """
    global _monitoring_hooks
    if _monitoring_hooks is None:
        _monitoring_hooks = MonitoringExecutionHooks()
    return _monitoring_hooks


def enable_monitoring_hooks() -> None:
    """Enable monitoring hooks by registering with core.

    This should be called when monitoring is enabled to install
    the monitoring hooks implementation.
    """
    from routilux.core.hooks import set_execution_hooks

    hooks = get_monitoring_hooks()
    set_execution_hooks(hooks)


def disable_monitoring_hooks() -> None:
    """Disable monitoring hooks by resetting to null implementation.

    This should be called when monitoring is disabled.
    """
    from routilux.core.hooks import reset_execution_hooks

    reset_execution_hooks()
