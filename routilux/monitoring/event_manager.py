"""
Event manager for job-level event streaming.

Provides event-driven push notifications using asyncio queues,
eliminating polling overhead in WebSocket connections.
"""

import asyncio
import logging
import threading
from typing import AsyncIterator, Dict, Set

logger = logging.getLogger(__name__)

# Module-level lock for thread-safe singleton initialization
_event_manager_lock = threading.Lock()
_event_manager: "JobEventManager | None" = None


class JobEventManager:
    """Manages event streaming for jobs using bounded queues.

    Uses asyncio.Queue with bounded size (maxsize=100) to prevent
    unbounded memory growth. Each job has its own event queue.
    WebSocket connections subscribe to job queues and receive
    events asynchronously.

    This replaces the polling pattern with push-based notifications,
    significantly reducing latency and resource usage.
    """

    # Maximum queue size per job (ring buffer equivalent)
    MAX_QUEUE_SIZE = 100

    def __init__(self) -> None:
        """Initialize the event manager."""
        # job_id -> asyncio.Queue
        self._queues: Dict[str, asyncio.Queue] = {}
        # job_id -> set of subscriber IDs (for tracking)
        self._subscribers: Dict[str, Set[str]] = {}
        # subscriber_id -> (job_id, queue)
        self._subscriber_info: Dict[str, tuple[str, asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._subscriber_counter = 0

    async def subscribe(self, job_id: str) -> str:
        """Subscribe to events for a job.

        Creates a unique subscription that can be used to iterate
        over events for the specified job.

        Args:
            job_id: Job identifier to subscribe to. Must be a non-empty string.

        Returns:
            Unique subscriber ID for this subscription.

        Raises:
            ValueError: If job_id is empty or not a string.
            RuntimeError: If subscription fails.

        Example:
            .. code-block:: python

                manager = JobEventManager()
                sub_id = await manager.subscribe("job_123")
                async for event in manager.iter_events(sub_id):
                    print(f"Event: {event}")
        """
        # Validate job_id
        if not isinstance(job_id, str):
            raise ValueError(f"job_id must be a string, got {type(job_id).__name__}")
        if not job_id or not job_id.strip():
            raise ValueError("job_id cannot be empty")

        try:
            async with self._lock:
                # Create queue if it doesn't exist
                if job_id not in self._queues:
                    self._queues[job_id] = asyncio.Queue(maxsize=self.MAX_QUEUE_SIZE)
                    logger.debug(f"Created event queue for job {job_id}")

                # Track subscriber
                self._subscriber_counter += 1
                subscriber_id = f"sub_{self._subscriber_counter}"

                if job_id not in self._subscribers:
                    self._subscribers[job_id] = set()
                self._subscribers[job_id].add(subscriber_id)

                self._subscriber_info[subscriber_id] = (job_id, self._queues[job_id])

                logger.debug(
                    f"Subscriber {subscriber_id} subscribed to job {job_id} "
                    f"(total: {len(self._subscribers[job_id])})"
                )

                return subscriber_id
        except Exception as e:
            logger.error(f"Failed to subscribe to job {job_id}: {e}")
            raise RuntimeError(f"Subscription failed for job {job_id}: {e}") from e

    async def unsubscribe(self, subscriber_id: str) -> None:
        """Unsubscribe a subscriber.

        Args:
            subscriber_id: Subscriber ID returned by subscribe().

        Example:
            .. code-block:: python

                await manager.unsubscribe(sub_id)
        """
        async with self._lock:
            if subscriber_id not in self._subscriber_info:
                logger.warning(f"Subscriber {subscriber_id} not found")
                return

            job_id, _ = self._subscriber_info[subscriber_id]

            # Remove from subscribers
            if job_id in self._subscribers:
                self._subscribers[job_id].discard(subscriber_id)
                if not self._subscribers[job_id]:
                    # No more subscribers, clean up queue
                    self._queues.pop(job_id, None)
                    self._subscribers.pop(job_id, None)
                    logger.debug(f"Cleaned up event queue for job {job_id}")

            # Remove subscriber info
            del self._subscriber_info[subscriber_id]

            logger.debug(
                f"Subscriber {subscriber_id} unsubscribed from job {job_id} "
                f"(remaining: {len(self._subscribers.get(job_id, set()))})"
            )

    async def publish(self, job_id: str, event: dict) -> None:
        """Publish an event to all subscribers of a job.

        If the queue is full (maxsize=100), the oldest event is
        automatically dropped (ring buffer behavior).

        Args:
            job_id: Job identifier. Must be a non-empty string.
            event: Event dictionary to publish. Must be a dict.

        Raises:
            ValueError: If job_id is empty or event is not a dict.

        Example:
            .. code-block:: python

                await manager.publish("job_123", {"type": "metrics", "data": {...}})
        """
        # Validate job_id
        if not isinstance(job_id, str):
            raise ValueError(f"job_id must be a string, got {type(job_id).__name__}")
        if not job_id or not job_id.strip():
            raise ValueError("job_id cannot be empty")

        # Validate event
        if not isinstance(event, dict):
            raise ValueError(f"event must be a dict, got {type(event).__name__}")
        if not event:
            logger.warning(f"Attempted to publish empty event to job {job_id}")
            return

        async with self._lock:
            if job_id not in self._queues:
                # No subscribers yet - create queue anyway to buffer events
                # This ensures events published before subscription are not lost
                self._queues[job_id] = asyncio.Queue(maxsize=self.MAX_QUEUE_SIZE)
                logger.debug(f"Created event queue for job {job_id} (no subscribers yet)")

            queue = self._queues[job_id]

        # Publish outside lock to avoid blocking
        try:
            # HIGH fix: Use put_nowait() with exception handling instead of check-then-act pattern
            # This prevents TOCTOU race condition where queue state changes between full() check and put()
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Queue is full, remove oldest event and try again (ring buffer behavior)
                try:
                    queue.get_nowait()
                    queue.put_nowait(event)
                    logger.debug(f"Event queue full for job {job_id}, dropped oldest event")
                except asyncio.QueueEmpty:
                    # Shouldn't happen, but handle gracefully
                    logger.warning(f"Event queue full for job {job_id}, dropping event")
            logger.debug(f"Published event to job {job_id}, queue size: {queue.qsize()}")

        except Exception as e:
            logger.error(f"Error publishing event to job {job_id}: {e}", exc_info=True)

    async def iter_events(self, subscriber_id: str) -> AsyncIterator[dict]:
        """Iterate over events for a subscriber.

        This is an async generator that yields events as they arrive.
        It will continue until the subscriber is unsubscribed.

        Args:
            subscriber_id: Subscriber ID returned by subscribe().

        Yields:
            Event dictionaries.

        Example:
            .. code-block:: python

                sub_id = await manager.subscribe("job_123")
                async for event in manager.iter_events(sub_id):
                    if event.get("type") == "done":
                        break
        """
        # HIGH fix: Acquire lock to prevent race condition when accessing _subscriber_info
        async with self._lock:
            if subscriber_id not in self._subscriber_info:
                logger.warning(f"Subscriber {subscriber_id} not found")
                return

            job_id, queue = self._subscriber_info[subscriber_id]

        try:
            while True:
                # Check if subscriber still exists (may have been unsubscribed)
                async with self._lock:
                    if subscriber_id not in self._subscriber_info:
                        logger.debug(f"Subscriber {subscriber_id} no longer exists")
                        break

                # Wait for event (with timeout to check subscriber status)
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=1.0)
                    yield event
                except asyncio.TimeoutError:
                    # Check subscriber status and continue
                    continue

        except asyncio.CancelledError:
            logger.debug(f"Event iterator cancelled for subscriber {subscriber_id}")
        except Exception as e:
            logger.error(f"Error in event iterator for subscriber {subscriber_id}: {e}")

    def get_subscriber_count(self, job_id: str) -> int:
        """Get the number of active subscribers for a job.

        This is a synchronous method (can be called from sync context).

        Args:
            job_id: Job identifier.

        Returns:
            Number of active subscribers.
        """
        # CRITICAL fix: Add synchronous lock for thread-safe access in sync methods
        # Since this is a sync method that can be called from non-async contexts,
        # we need a separate lock for thread safety
        if not hasattr(self, "_sync_lock"):
            import threading

            self._sync_lock = threading.RLock()

        with self._sync_lock:
            subscribers = self._subscribers.get(job_id, set()).copy()
            return len(subscribers)

    async def cleanup(self, job_id: str) -> None:
        """Clean up all resources for a job.

        Removes all subscribers and the event queue for a job.
        Call this when a job is completed/cancelled.

        Args:
            job_id: Job identifier.

        Example:
            .. code-block:: python

                await manager.cleanup("job_123")
        """
        async with self._lock:
            if job_id not in self._queues:
                return

            # Get all subscribers to remove
            subscribers = self._subscribers.get(job_id, set()).copy()

            # Remove all subscribers
            for subscriber_id in subscribers:
                if subscriber_id in self._subscriber_info:
                    del self._subscriber_info[subscriber_id]

            # Clean up job resources
            self._queues.pop(job_id, None)
            self._subscribers.pop(job_id, None)

            logger.info(f"Cleaned up {len(subscribers)} subscribers for job {job_id}")

    async def shutdown(self) -> None:
        """Shutdown the event manager and clean up all resources.

        Call this when shutting down the application.
        """
        async with self._lock:
            job_ids = list(self._queues.keys())

        for job_id in job_ids:
            await self.cleanup(job_id)

        logger.info("Event manager shutdown complete")

    def get_status(self) -> dict:
        """Get status information about the event manager.

        Returns:
            Dictionary with status information (job counts, subscriber counts, etc).

        Note:
            This is a synchronous method for monitoring purposes.
        """
        # Fix: Copy data for thread safety since this is a sync method
        # We can't use async with in a sync method
        queues_copy = self._queues.copy()
        subscribers_copy = self._subscribers.copy()
        subscriber_info_copy = self._subscriber_info.copy()

        return {
            "total_jobs": len(queues_copy),
            "total_subscribers": len(subscriber_info_copy),
            "jobs": {
                job_id: {
                    "subscribers": len(subs),
                    "queue_size": queues_copy[job_id].qsize() if job_id in queues_copy else 0,
                }
                for job_id, subs in subscribers_copy.items()
            },
        }


def get_event_manager() -> JobEventManager:
    """Get the global event manager singleton.

    Returns:
        The global JobEventManager instance.

    Example:
        .. code-block:: python

            from routilux.monitoring.event_manager import get_event_manager

            manager = get_event_manager()
            await manager.publish("job_123", {"type": "event", "data": "..."})
    """
    global _event_manager
    # Fix: Use double-checked locking with proper lock for thread safety
    if _event_manager is None:
        with _event_manager_lock:
            if _event_manager is None:
                _event_manager = JobEventManager()
                logger.info("Created global event manager instance")
    return _event_manager
