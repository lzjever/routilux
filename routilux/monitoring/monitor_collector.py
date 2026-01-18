"""
Monitor collector for execution metrics and events.

Collects execution metrics, traces, and events for monitoring and analysis.
Publishes events to JobEventManager for real-time streaming.
Uses ring buffers (deque with maxlen) to prevent unbounded memory growth.
"""

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

# Try to import event manager (optional for backwards compatibility)
try:
    from routilux.monitoring.event_manager import get_event_manager

    EVENT_MANAGER_AVAILABLE = True
except ImportError:
    EVENT_MANAGER_AVAILABLE = False


# Maximum events to store per job (ring buffer size)
DEFAULT_MAX_EVENTS_PER_JOB = 1000

# Lock for thread-safe access to DEFAULT_MAX_EVENTS_PER_JOB
_max_events_lock = threading.Lock()


def set_max_events_per_job(max_events: int) -> None:
    """Set the maximum number of events to store per job.

    This setting applies to newly created jobs only, not existing ones.

    Args:
        max_events: Maximum number of events per job (must be > 0).
    """
    global DEFAULT_MAX_EVENTS_PER_JOB
    if max_events <= 0:
        raise ValueError("max_events must be greater than 0")
    # Fix: Use lock to prevent race condition when updating global variable
    with _max_events_lock:
        DEFAULT_MAX_EVENTS_PER_JOB = max_events


@dataclass
class ExecutionEvent:
    """Execution event record.

    Attributes:
        event_id: Unique event identifier.
        job_id: Job ID.
        routine_id: Routine ID.
        event_type: Type of event (routine_start, routine_end, slot_call, event_emit).
        timestamp: Event timestamp.
        data: Event-specific data.
        duration: Duration in seconds (for end events).
        status: Status (for end events).
    """

    event_id: str
    job_id: str
    routine_id: str
    event_type: str
    timestamp: datetime
    data: Dict[str, Any] = field(default_factory=dict)
    duration: Optional[float] = None
    status: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for publishing.

        Returns:
            Dictionary representation of the event.
        """
        return {
            "event_id": self.event_id,
            "job_id": self.job_id,
            "routine_id": self.routine_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "duration": self.duration,
            "status": self.status,
        }


@dataclass
class RoutineMetrics:
    """Metrics for a single routine.

    Attributes:
        routine_id: Routine identifier.
        execution_count: Number of times routine executed.
        total_duration: Total execution time in seconds.
        avg_duration: Average execution time in seconds.
        min_duration: Minimum execution time in seconds.
        max_duration: Maximum execution time in seconds.
        error_count: Number of errors.
        last_execution: Timestamp of last execution.
    """

    routine_id: str
    execution_count: int = 0
    total_duration: float = 0.0
    avg_duration: float = 0.0
    min_duration: Optional[float] = None
    max_duration: Optional[float] = None
    error_count: int = 0
    last_execution: Optional[datetime] = None

    def update(self, duration: float, status: str = "completed") -> None:
        """Update metrics with new execution.

        Args:
            duration: Execution duration in seconds.
            status: Execution status.
        """
        self.execution_count += 1
        self.total_duration += duration
        self.avg_duration = self.total_duration / self.execution_count

        if self.min_duration is None or duration < self.min_duration:
            self.min_duration = duration
        if self.max_duration is None or duration > self.max_duration:
            self.max_duration = duration

        if status in ("failed", "error"):
            self.error_count += 1

        self.last_execution = datetime.now()


@dataclass
class ErrorRecord:
    """Error record.

    Attributes:
        error_id: Unique error identifier.
        job_id: Job ID.
        routine_id: Routine ID where error occurred.
        timestamp: Error timestamp.
        error_type: Error type (exception class name).
        error_message: Error message.
        traceback: Optional traceback.
    """

    error_id: str
    job_id: str
    routine_id: str
    timestamp: datetime
    error_type: str
    error_message: str
    traceback: Optional[str] = None


@dataclass
class ExecutionMetrics:
    """Aggregated execution metrics.

    Attributes:
        job_id: Job identifier.
        flow_id: Flow identifier.
        start_time: Execution start time.
        end_time: Execution end time (None if still running).
        duration: Total duration in seconds (None if still running).
        routine_metrics: Metrics per routine.
        total_events: Total number of events.
        total_slot_calls: Total number of slot calls.
        total_event_emits: Total number of event emissions.
        errors: List of error records.
    """

    job_id: str
    flow_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: Optional[float] = None
    routine_metrics: Dict[str, RoutineMetrics] = field(default_factory=dict)
    total_events: int = 0
    total_slot_calls: int = 0
    total_event_emits: int = 0
    errors: List[ErrorRecord] = field(default_factory=list)


class MonitorCollector:
    """Collects execution metrics and events.

    Thread-safe collector that records execution events and computes metrics.
    Publishes events to JobEventManager for real-time WebSocket streaming.
    Uses ring buffers (deque with maxlen) to prevent unbounded memory growth.
    """

    def __init__(self, max_events_per_job: Optional[int] = None):
        """Initialize monitor collector.

        Args:
            max_events_per_job: Maximum events to store per job (ring buffer size).
                              If None, uses DEFAULT_MAX_EVENTS_PER_JOB (1000).
        """
        self._max_events_per_job = max_events_per_job or DEFAULT_MAX_EVENTS_PER_JOB
        self._metrics: Dict[str, ExecutionMetrics] = {}  # job_id -> ExecutionMetrics
        self._events: Dict[
            str, Deque[ExecutionEvent]
        ] = {}  # job_id -> Deque[ExecutionEvent] (ring buffer)
        # Note: _routine_starts removed - in concurrent model, we track thread counts instead
        # of individual instance lifecycles. This dictionary was causing data corruption
        # when multiple instances of the same routine executed concurrently.
        self._lock = threading.RLock()
        self._event_counter = 0

        # Get event manager if available (for real-time streaming)
        self._event_manager = None
        if EVENT_MANAGER_AVAILABLE:
            try:
                self._event_manager = get_event_manager()
            except Exception:
                # Event manager initialization failed, continue without it
                pass

    def _publish_event(self, event: ExecutionEvent) -> None:
        """Publish event to event manager for WebSocket streaming.

        Args:
            event: Execution event to publish.
        """
        if self._event_manager is not None:
            try:
                # Only publish if we're in an async context with a running event loop
                # This prevents blocking in synchronous contexts (e.g., API routes)
                import asyncio
                import logging

                try:
                    asyncio.get_running_loop()
                    # In async context, create task without waiting
                    asyncio.create_task(self._event_manager.publish(event.job_id, event.to_dict()))
                except RuntimeError:
                    # No running event loop - skip publishing to avoid blocking
                    # This is expected in synchronous API routes and flow execution
                    logging.debug(
                        f"No event loop running, skipping event publish for job {event.job_id}"
                    )
            except (RuntimeError, AttributeError) as e:
                # Expected errors when event manager is not available or in wrong context
                logging.debug(f"Cannot publish event: {e}")
            except Exception as e:
                # Critical fix: Log unexpected errors instead of silently swallowing them
                # This helps with debugging while not breaking execution
                logging.error(f"Unexpected error publishing event for job {event.job_id}: {e}")

    def record_flow_start(self, flow_id: str, job_id: str) -> None:
        """Record flow execution start.

        Args:
            flow_id: Flow identifier.
            job_id: Job identifier.
        """
        with self._lock:
            if job_id not in self._metrics:
                self._metrics[job_id] = ExecutionMetrics(
                    job_id=job_id,
                    flow_id=flow_id,
                    start_time=datetime.now(),
                )
                # Use deque with maxlen as ring buffer
                self._events[job_id] = deque(maxlen=self._max_events_per_job)

    def record_flow_end(self, job_id: str, status: str = "completed") -> None:
        """Record flow execution end.

        Args:
            job_id: Job identifier.
            status: Final status.
        """
        with self._lock:
            if job_id in self._metrics:
                metrics = self._metrics[job_id]
                metrics.end_time = datetime.now()
                if metrics.start_time:
                    metrics.duration = (metrics.end_time - metrics.start_time).total_seconds()

    def record_routine_start(self, routine_id: str, job_id: str) -> None:
        """Record routine execution start (for event publishing only).

        Note: In the concurrent execution model, we no longer track individual
        instance lifecycles. This method is kept for backward compatibility and
        event publishing (WebSocket), but does not collect lifecycle data.

        Args:
            routine_id: Routine identifier.
            job_id: Job identifier.
        """
        # Only publish event for WebSocket streaming, no data collection
        with self._lock:
            # Record event for WebSocket streaming
            event = ExecutionEvent(
                event_id=f"event_{self._event_counter}",
                job_id=job_id,
                routine_id=routine_id,
                event_type="routine_start",
                timestamp=datetime.now(),
            )
            self._event_counter += 1

            if job_id not in self._events:
                self._events[job_id] = deque(maxlen=self._max_events_per_job)
            self._events[job_id].append(event)

            if job_id in self._metrics:
                self._metrics[job_id].total_events += 1

        # Publish event for WebSocket streaming (outside lock)
        self._publish_event(event)

    def record_routine_end(
        self,
        routine_id: str,
        job_id: str,
        status: str = "completed",
        error: Optional[Exception] = None,
    ) -> None:
        """Record routine execution end (for event publishing only).

        Note: In the concurrent execution model, we no longer track individual
        instance lifecycles. This method is kept for backward compatibility and
        event publishing (WebSocket), but does not collect lifecycle data.
        Use record_routine_execution() for updating aggregate metrics.

        Args:
            routine_id: Routine identifier.
            job_id: Job identifier.
            status: Execution status.
            error: Optional error that occurred.
        """
        # Only publish event for WebSocket streaming, no data collection
        with self._lock:
            # Record event for WebSocket streaming
            event = ExecutionEvent(
                event_id=f"event_{self._event_counter}",
                job_id=job_id,
                routine_id=routine_id,
                event_type="routine_end",
                timestamp=datetime.now(),
                duration=None,  # Duration not available without lifecycle tracking
                status=status,
            )
            self._event_counter += 1

            if job_id not in self._events:
                self._events[job_id] = deque(maxlen=self._max_events_per_job)
            self._events[job_id].append(event)

            if job_id in self._metrics:
                self._metrics[job_id].total_events += 1

        # Publish event for WebSocket streaming (outside lock)
        self._publish_event(event)

    def record_routine_execution(
        self,
        routine_id: str,
        job_id: str,
        duration: float,
        status: str = "completed",
        error: Optional[Exception] = None,
    ) -> None:
        """Record a routine execution for aggregate metrics (statistics only).

        This method is used in the new concurrent monitoring model where we track
        thread counts instead of individual instance lifecycles. This method only
        updates aggregate metrics (execution count, total duration, etc.) and does
        not track instance start/end times.

        Args:
            routine_id: Routine identifier.
            job_id: Job identifier.
            duration: Execution duration in seconds.
            status: Execution status (completed, failed, error_continued, skipped).
            error: Optional error that occurred.
        """
        with self._lock:
            # Ensure metrics exist
            if job_id not in self._metrics:
                # Get flow_id from JobContext
                from routilux.server.dependencies import get_job_storage, get_runtime
                job_storage = get_job_storage()
                runtime = get_runtime()
                job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
                flow_id = job_context.flow_id if job_context else "unknown"
                self._metrics[job_id] = ExecutionMetrics(
                    job_id=job_id,
                    flow_id=flow_id,
                    start_time=datetime.now(),
                )

            metrics = self._metrics[job_id]

            # Initialize routine metrics if needed
            if routine_id not in metrics.routine_metrics:
                metrics.routine_metrics[routine_id] = RoutineMetrics(routine_id=routine_id)

            # Update aggregate metrics
            routine_metrics = metrics.routine_metrics[routine_id]
            routine_metrics.update(duration, status)
            routine_metrics.last_execution = datetime.now()

            # Record error if present
            if error:
                error_record = ErrorRecord(
                    error_id=f"error_{self._event_counter}",
                    job_id=job_id,
                    routine_id=routine_id,
                    timestamp=datetime.now(),
                    error_type=type(error).__name__,
                    error_message=str(error),
                )
                metrics.errors.append(error_record)
                self._event_counter += 1

    def record_slot_call(
        self,
        slot_name: str,
        routine_id: str,
        job_id: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record slot call.

        Args:
            slot_name: Slot name.
            routine_id: Routine identifier.
            job_id: Job identifier.
            data: Optional data passed to slot.
        """
        with self._lock:
            event = ExecutionEvent(
                event_id=f"event_{self._event_counter}",
                job_id=job_id,
                routine_id=routine_id,
                event_type="slot_call",
                timestamp=datetime.now(),
                data={"slot_name": slot_name, "data_keys": list(data.keys()) if data else []},
            )
            self._event_counter += 1

            if job_id not in self._events:
                self._events[job_id] = deque(maxlen=self._max_events_per_job)
            self._events[job_id].append(event)

            if job_id in self._metrics:
                self._metrics[job_id].total_events += 1
                self._metrics[job_id].total_slot_calls += 1

        # Publish event for WebSocket streaming (outside lock)
        self._publish_event(event)

    def record_event_emit(
        self,
        event_name: str,
        routine_id: str,
        job_id: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record event emission.

        Args:
            event_name: Event name.
            routine_id: Routine identifier.
            job_id: Job identifier.
            data: Optional data emitted with event.
        """
        with self._lock:
            event = ExecutionEvent(
                event_id=f"event_{self._event_counter}",
                job_id=job_id,
                routine_id=routine_id,
                event_type="event_emit",
                timestamp=datetime.now(),
                data={"event_name": event_name, "data_keys": list(data.keys()) if data else []},
            )
            self._event_counter += 1

            if job_id not in self._events:
                self._events[job_id] = deque(maxlen=self._max_events_per_job)
            self._events[job_id].append(event)

            if job_id in self._metrics:
                self._metrics[job_id].total_events += 1
                self._metrics[job_id].total_event_emits += 1

        # Publish event for WebSocket streaming (outside lock)
        self._publish_event(event)

    def get_metrics(self, job_id: str) -> Optional[ExecutionMetrics]:
        """Get execution metrics for a job.

        Args:
            job_id: Job identifier.

        Returns:
            ExecutionMetrics or None if not found.
        """
        with self._lock:
            return self._metrics.get(job_id)

    def get_execution_trace(self, job_id: str, limit: Optional[int] = None) -> List[ExecutionEvent]:
        """Get execution trace for a job.

        Args:
            job_id: Job identifier.
            limit: Optional limit on number of events to return.

        Returns:
            List of execution events (chronologically ordered).
        """
        with self._lock:
            events = self._events.get(job_id, deque())
            if limit:
                # Convert deque slice to list
                return list(events)[-limit:]
            return list(events)

    def clear(self, job_id: str) -> None:
        """Clear all data for a job.

        Args:
            job_id: Job identifier.
        """
        with self._lock:
            self._metrics.pop(job_id, None)
            self._events.pop(job_id, None)
            self._routine_starts.pop(job_id, None)

        # Cleanup event manager subscribers for this job
        if self._event_manager is not None:
            try:
                import asyncio

                # Only attempt async cleanup if there's a running event loop
                # This avoids deprecation warnings from get_event_loop()
                try:
                    asyncio.get_running_loop()
                    # Loop is running, create a task
                    asyncio.create_task(self._event_manager.cleanup(job_id))
                except RuntimeError:
                    # No running loop available, skip async cleanup
                    # This is safe - the cleanup is best-effort and not critical
                    pass
            except Exception:
                # Event cleanup failed, continue silently
                pass
