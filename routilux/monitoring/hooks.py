"""
Execution hooks for monitoring and debugging.

These hooks are called at key execution points and have zero overhead
when monitoring is disabled.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from routilux.event import Event
    from routilux.flow.flow import Flow
    from routilux.job_state import JobState
    from routilux.routine import ExecutionContext, Routine
    from routilux.slot import Slot

logger = logging.getLogger(__name__)


def _publish_event_via_manager(job_id: str, event: dict) -> None:
    """Publish event via event manager with error handling (fire-and-forget).

    This is a helper function to avoid code duplication in hooks.
    Handles both async and sync contexts.

    Args:
        job_id: Job identifier.
        event: Event dictionary to publish.
    """
    try:
        from routilux.monitoring.event_manager import get_event_manager

        event_manager = get_event_manager()

        try:
            # Only publish if we're in an async context with a running event loop
            # This prevents blocking in synchronous contexts
            asyncio.get_running_loop()
            # In async context, create task without waiting
            asyncio.create_task(event_manager.publish(job_id, event))
        except RuntimeError:
            # No running event loop - skip publishing to avoid blocking
            # This is expected in synchronous API routes and flow execution
            return
    except (RuntimeError, AttributeError):
        # No event loop or import failed, skip event notification
        pass
    except Exception as e:
        logger.error(f"Failed to publish event to job {job_id}: {e}")


class ExecutionHooks:
    """Execution hooks for monitoring and debugging.

    All methods return immediately if monitoring is disabled, ensuring
    zero overhead for existing applications.
    """

    def on_flow_start(self, flow: "Flow", job_state: "JobState") -> None:
        """Hook called when flow execution starts.

        Args:
            flow: Flow being executed.
            job_state: Job state for this execution.
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled():
            return

        registry = MonitoringRegistry.get_instance()
        collector = registry.monitor_collector

        if collector:
            collector.record_flow_start(flow.flow_id, job_state.job_id)

            # Publish flow_start event via event manager (non-blocking)
            _publish_event_via_manager(
                job_state.job_id,
                {
                    "type": "flow_start",
                    "job_id": job_state.job_id,
                    "flow_id": flow.flow_id,
                },
            )

    def on_flow_end(self, flow: "Flow", job_state: "JobState", status: str = "completed") -> None:
        """Hook called when flow execution ends.

        Args:
            flow: Flow that was executed.
            job_state: Job state for this execution.
            status: Final execution status.
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled():
            return

        registry = MonitoringRegistry.get_instance()
        collector = registry.monitor_collector

        if collector:
            collector.record_flow_end(job_state.job_id, status)

            # Get final metrics and broadcast via event manager
            metrics = collector.get_metrics(job_state.job_id)
            if metrics:
                _publish_event_via_manager(
                    job_state.job_id,
                    {
                        "type": "metrics",
                        "job_id": job_state.job_id,
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

    def on_routine_start(
        self,
        routine: "Routine",
        routine_id: str,
        job_state: Optional["JobState"] = None,
    ) -> None:
        """Hook called when routine execution starts.

        Args:
            routine: Routine being executed.
            routine_id: Routine identifier.
            job_state: Optional job state.
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled() or not job_state:
            return

        registry = MonitoringRegistry.get_instance()
        collector = registry.monitor_collector

        if collector:
            # Note: MonitorCollector._publish_event() will automatically
            # publish routine_start events via JobEventManager
            collector.record_routine_start(routine_id, job_state.job_id)

        # Publish routine status change event
        _publish_event_via_manager(
            job_state.job_id,
            {
                "type": "routine_status_change",
                "job_id": job_state.job_id,
                "routine_id": routine_id,
                "status": "running",
                "is_active": True,
            },
        )

        # Publish queue status updates for all slots
        queue_updates = {}
        for slot_name, slot in routine.slots.items():
            try:
                status = slot.get_queue_status()
                queue_updates[slot_name] = status
            except Exception:
                # Ignore errors in queue status retrieval
                pass

        if queue_updates:
            _publish_event_via_manager(
                job_state.job_id,
                {
                    "type": "routine_queue_update",
                    "job_id": job_state.job_id,
                    "routine_id": routine_id,
                    "queues": queue_updates,
                },
            )

    def on_routine_end(
        self,
        routine: "Routine",
        routine_id: str,
        job_state: Optional["JobState"] = None,
        status: str = "completed",
        error: Optional[Exception] = None,
    ) -> None:
        """Hook called when routine execution ends.

        Args:
            routine: Routine that was executed.
            routine_id: Routine identifier.
            job_state: Optional job state.
            status: Execution status.
            error: Optional error that occurred.
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled() or not job_state:
            return

        registry = MonitoringRegistry.get_instance()
        collector = registry.monitor_collector

        if collector:
            collector.record_routine_end(routine_id, job_state.job_id, status, error)

        # Publish routine status change event
        _publish_event_via_manager(
            job_state.job_id,
            {
                "type": "routine_status_change",
                "job_id": job_state.job_id,
                "routine_id": routine_id,
                "status": status,
                "is_active": False,
            },
        )

        # Publish queue status updates for all slots
        queue_updates = {}
        for slot_name, slot in routine.slots.items():
            try:
                status = slot.get_queue_status()
                queue_updates[slot_name] = status
            except Exception:
                # Ignore errors in queue status retrieval
                pass

        if queue_updates:
            _publish_event_via_manager(
                job_state.job_id,
                {
                    "type": "routine_queue_update",
                    "job_id": job_state.job_id,
                    "routine_id": routine_id,
                    "queues": queue_updates,
                },
            )

    def on_slot_call(
        self,
        slot: "Slot",
        routine_id: str,
        job_state: Optional["JobState"] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Hook called when slot handler is called.

        Args:
            slot: Slot being called.
            routine_id: Routine identifier.
            job_state: Optional job state.
            data: Data being passed to slot.

        Returns:
            True if execution should continue, False if should pause.
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled() or not job_state:
            return True

        registry = MonitoringRegistry.get_instance()

        # Record slot call
        collector = registry.monitor_collector
        if collector:
            collector.record_slot_call(slot.name, routine_id, job_state.job_id, data)

        # Check breakpoint
        breakpoint_mgr = registry.breakpoint_manager
        if breakpoint_mgr:
            context = (
                slot.routine.get_execution_context()
                if hasattr(slot, "routine") and slot.routine
                else None
            )
            breakpoint = breakpoint_mgr.check_breakpoint(
                job_state.job_id,
                routine_id,
                "slot",
                slot_name=slot.name,
                context=context,
                variables=data,
            )
            if breakpoint:
                debug_store = registry.debug_session_store
                if debug_store:
                    session = debug_store.get_or_create(job_state.job_id)
                    session.pause(context, reason=f"Breakpoint at {routine_id}.{slot.name}")
                    # Notify via event manager
                    _publish_event_via_manager(
                        job_state.job_id,
                        {
                            "type": "breakpoint_hit",
                            "job_id": job_state.job_id,
                            "breakpoint": {
                                "breakpoint_id": breakpoint.breakpoint_id,
                                "type": breakpoint.type,
                                "routine_id": breakpoint.routine_id,
                                "slot_name": breakpoint.slot_name,
                                "event_name": breakpoint.event_name,
                            },
                        },
                    )
                    return False

        return True

    def on_event_emit(
        self,
        event: "Event",
        routine_id: str,
        job_state: Optional["JobState"] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Hook called when event is emitted.

        Args:
            event: Event being emitted.
            routine_id: Routine identifier.
            job_state: Optional job state.
            data: Data being emitted with event.

        Returns:
            True if execution should continue, False if should pause.
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled() or not job_state:
            return True

        registry = MonitoringRegistry.get_instance()

        # Record event emission
        collector = registry.monitor_collector
        if collector:
            collector.record_event_emit(event.name, routine_id, job_state.job_id, data)

        # Check breakpoint
        breakpoint_mgr = registry.breakpoint_manager
        if breakpoint_mgr:
            context = (
                event.routine.get_execution_context()
                if hasattr(event, "routine") and event.routine
                else None
            )
            breakpoint = breakpoint_mgr.check_breakpoint(
                job_state.job_id,
                routine_id,
                "event",
                event_name=event.name,
                context=context,
                variables=data,
            )
            if breakpoint:
                debug_store = registry.debug_session_store
                if debug_store:
                    session = debug_store.get_or_create(job_state.job_id)
                    session.pause(context, reason=f"Breakpoint at {routine_id}.{event.name}")
                    # Notify via event manager
                    _publish_event_via_manager(
                        job_state.job_id,
                        {
                            "type": "breakpoint_hit",
                            "job_id": job_state.job_id,
                            "breakpoint": {
                                "breakpoint_id": breakpoint.breakpoint_id,
                                "type": breakpoint.type,
                                "routine_id": breakpoint.routine_id,
                                "slot_name": breakpoint.slot_name,
                                "event_name": breakpoint.event_name,
                            },
                        },
                    )
                    return False

        return True

    def on_slot_data_received(
        self,
        slot: "Slot",
        routine_id: str,
        job_state: Optional["JobState"] = None,
        data: Optional[Any] = None,  # Can be any type, not just Dict
    ) -> bool:
        """Hook called when data is enqueued to a slot.

        This replaces on_slot_call() for the new queue-based slot design.

        Args:
            slot: Slot receiving data.
            routine_id: Routine identifier that owns the slot.
            job_state: Optional job state.
            data: Data being enqueued (can be any type).

        Returns:
            True if execution should continue, False if should pause.
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled() or not job_state:
            return True

        registry = MonitoringRegistry.get_instance()

        # Record slot data reception
        collector = registry.monitor_collector
        if collector:
            # Convert data to dict if needed for record_slot_call
            data_dict = data if isinstance(data, dict) else {"data": data}
            collector.record_slot_call(slot.name, routine_id, job_state.job_id, data_dict)

        # Publish queue status update
        try:
            status = slot.get_queue_status()
            _publish_event_via_manager(
                job_state.job_id,
                {
                    "type": "slot_queue_update",
                    "job_id": job_state.job_id,
                    "routine_id": routine_id,
                    "slot_name": slot.name,
                    "queue_status": status,
                },
            )
        except Exception:
            # Ignore errors in queue status retrieval
            pass

        # Check breakpoint
        breakpoint_mgr = registry.breakpoint_manager
        if breakpoint_mgr:
            context = (
                slot.routine.get_execution_context()
                if hasattr(slot, "routine") and slot.routine
                else None
            )
            # Convert data to dict for breakpoint variables
            variables = data if isinstance(data, dict) else {"data": data}
            breakpoint = breakpoint_mgr.check_breakpoint(
                job_state.job_id,
                routine_id,
                "slot",
                slot_name=slot.name,
                context=context,
                variables=variables,
            )
            if breakpoint:
                debug_store = registry.debug_session_store
                if debug_store:
                    session = debug_store.get_or_create(job_state.job_id)
                    session.pause(
                        context, reason=f"Breakpoint at {routine_id}.{slot.name}"
                    )
                    # Notify via event manager
                    _publish_event_via_manager(
                        job_state.job_id,
                        {
                            "type": "breakpoint_hit",
                            "job_id": job_state.job_id,
                            "breakpoint": {
                                "breakpoint_id": breakpoint.breakpoint_id,
                                "type": breakpoint.type,
                                "routine_id": breakpoint.routine_id,
                                "slot_name": breakpoint.slot_name,
                            },
                        },
                    )
                    return False

        return True

    def should_pause_routine(
        self,
        routine_id: str,
        job_state: Optional["JobState"] = None,
        context: Optional["ExecutionContext"] = None,
        variables: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Check if execution should pause at routine start.

        Args:
            routine_id: Routine identifier.
            job_state: Optional job state.
            context: Optional execution context.
            variables: Optional local variables.

        Returns:
            True if execution should pause.
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled() or not job_state:
            return False

        registry = MonitoringRegistry.get_instance()
        breakpoint_mgr = registry.breakpoint_manager

        if breakpoint_mgr:
            return breakpoint_mgr.should_pause_routine(
                job_state.job_id, routine_id, context, variables
            )

        return False

    def pause_execution(
        self, job_id: str, context: Optional["ExecutionContext"] = None, reason: str = ""
    ) -> None:
        """Pause execution at current point.

        Args:
            job_id: Job identifier.
            context: Execution context.
            reason: Reason for pause.
        """
        from routilux.monitoring.registry import MonitoringRegistry

        if not MonitoringRegistry.is_enabled():
            return

        registry = MonitoringRegistry.get_instance()
        debug_store = registry.debug_session_store

        if debug_store:
            session = debug_store.get_or_create(job_id)
            session.pause(context, reason)


# Global instance
execution_hooks = ExecutionHooks()
