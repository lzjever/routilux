"""
Monitoring implementation of ExecutionHooksInterface.

This module implements the core ExecutionHooksInterface with monitoring
capabilities including metrics collection, breakpoint support, and
event broadcasting.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING, Any

from routilux.core.hooks import ExecutionHooksInterface

if TYPE_CHECKING:
    from routilux.core.context import JobContext
    from routilux.core.event import Event
    from routilux.core.flow import Flow
    from routilux.core.worker import WorkerState

logger = logging.getLogger(__name__)


# Global event publisher for sync-to-async bridge
# This is initialized once and reused, avoiding thread creation overhead
_event_publisher_loop: asyncio.AbstractEventLoop | None = None
_event_publisher_thread: threading.Thread | None = None
_event_publisher_queue: asyncio.Queue | None = None
_event_publisher_lock = threading.Lock()


def _ensure_event_publisher():
    """Ensure global event publisher is running.
    
    Creates a single background thread with event loop that processes
    events from sync contexts. This is more efficient than creating
    a new thread for each event.
    """
    global _event_publisher_loop, _event_publisher_thread, _event_publisher_queue
    
    with _event_publisher_lock:
        if _event_publisher_thread is not None and _event_publisher_thread.is_alive():
            return  # Already running
        
        def run_event_loop():
            """Background thread that runs event loop for sync-to-async bridge."""
            global _event_publisher_loop, _event_publisher_queue
            
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            _event_publisher_loop = new_loop
            queue = asyncio.Queue()
            _event_publisher_queue = queue
            
            async def publisher():
                """Async task that processes events from queue."""
                from routilux.monitoring.event_manager import get_event_manager
                event_manager = get_event_manager()
                
                while True:
                    try:
                        # Wait for event with timeout to allow checking if we should continue
                        job_id, event = await asyncio.wait_for(
                            queue.get(), timeout=1.0
                        )
                        try:
                            await event_manager.publish(job_id, event)
                        except Exception as e:
                            logger.error(f"Error publishing event {event.get('type')} for job {job_id}: {e}", exc_info=True)
                    except asyncio.TimeoutError:
                        # No events for 1 second, but keep running (queue might get events later)
                        continue
                    except Exception as e:
                        logger.error(f"Error in event publisher loop: {e}", exc_info=True)
            
            # Create and run publisher task
            task = new_loop.create_task(publisher())
            new_loop.run_forever()
        
        _event_publisher_thread = threading.Thread(
            target=run_event_loop, daemon=True, name="EventPublisher"
        )
        _event_publisher_thread.start()
        
        # Give thread time to initialize
        import time
        time.sleep(0.1)


def _publish_event_via_manager(job_id: str, event: dict) -> None:
    """Publish event via event manager with error handling (fire-and-forget).

    Supports both async and sync contexts. In sync contexts, uses a global
    background event loop thread to publish events efficiently.

    Args:
        job_id: Job identifier
        event: Event dictionary to publish
    """
    try:
        from routilux.monitoring.event_manager import get_event_manager

        event_manager = get_event_manager()

        try:
            loop = asyncio.get_running_loop()
            # In async context, create task without waiting
            asyncio.create_task(event_manager.publish(job_id, event))
        except RuntimeError:
            # No running event loop - use global background publisher
            _ensure_event_publisher()
            
            if _event_publisher_loop is not None and _event_publisher_queue is not None:
                # Schedule event in the background loop using call_soon_threadsafe
                # This is more efficient than using a thread queue
                def put_event():
                    try:
                        _event_publisher_queue.put_nowait((job_id, event))
                    except Exception as e:
                        logger.error(f"Failed to queue event for job {job_id}: {e}")
                
                _event_publisher_loop.call_soon_threadsafe(put_event)
            else:
                # Fallback: log warning but don't fail
                logger.warning(f"Event publisher not available, dropping event for job {job_id}")
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
        from datetime import datetime

        if not MonitoringRegistry.is_enabled():
            return

        # Publish job_started event with frontend-expected format
        logger.debug(f"Publishing job_started event for job {job_context.job_id}")
        _publish_event_via_manager(
            job_context.job_id,  # Use job_id instead of worker_id
            {
                "type": "job_started",  # Frontend expects "job_started"
                "job_id": job_context.job_id,
                "timestamp": datetime.now().isoformat(),
                "data": {
                    "flow_id": worker_state.flow_id,
                    "worker_id": worker_state.worker_id,
                    "metadata": job_context.metadata,
                }
            },
        )
        logger.debug(f"Published job_started event for job {job_context.job_id}")

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
        from datetime import datetime

        if not MonitoringRegistry.is_enabled():
            return

        # Determine event type based on status
        event_type = "job_completed" if status == "completed" else "job_failed"

        # Publish job event with frontend-expected format
        _publish_event_via_manager(
            job_context.job_id,  # Use job_id instead of worker_id
            {
                "type": event_type,  # Frontend expects "job_completed" or "job_failed"
                "job_id": job_context.job_id,
                "timestamp": datetime.now().isoformat(),
                "data": {
                    "flow_id": worker_state.flow_id,
                    "worker_id": worker_state.worker_id,
                    "status": status,
                    "error": str(error) if error else None,
                    "trace_log": job_context.trace_log,
                }
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
        from datetime import datetime

        if not MonitoringRegistry.is_enabled():
            return True

        # Publish routine_started event (not routine_status_change)
        _publish_event_via_manager(
            job_context.job_id if job_context else worker_state.worker_id,
            {
                "type": "routine_started",  # Frontend expects "routine_started"
                "job_id": job_context.job_id if job_context else None,
                "timestamp": datetime.now().isoformat(),
                "data": {
                    "routine_id": routine_id,
                    "worker_id": worker_state.worker_id,
                }
            },
        )

        # Note: Breakpoints are now checked during event routing in Runtime.handle_event_emit
        # No breakpoint check needed here for routine start

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
        from datetime import datetime

        if not MonitoringRegistry.is_enabled():
            return

        # Determine event type based on status
        event_type = "routine_completed" if status == "completed" else "routine_failed"

        # Publish routine event
        _publish_event_via_manager(
            job_context.job_id if job_context else worker_state.worker_id,
            {
                "type": event_type,  # Frontend expects "routine_completed" or "routine_failed"
                "job_id": job_context.job_id if job_context else None,
                "timestamp": datetime.now().isoformat(),
                "data": {
                    "routine_id": routine_id,
                    "worker_id": worker_state.worker_id,
                    "status": status,
                    "error": str(error) if error else None,
                }
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

        # Note: Breakpoints are now checked during event routing in Runtime.handle_event_emit
        # when data is about to be enqueued to slots. No breakpoint check needed here for event emit.

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
