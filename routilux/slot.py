"""
Slot class.

Input slot for receiving data from other routines.
Slots are queue-based buffers that store data with timestamps.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from routilux.event import Event
    from routilux.routine import Routine

from serilux import Serializable, register_serializable


class SlotQueueFullError(Exception):
    """Exception raised when slot queue is full and cannot accept more data."""

    pass


@dataclass
class SlotDataPoint:
    """Data point in a slot queue with timestamps."""

    data: Any
    emitted_at: datetime
    enqueued_at: datetime
    consumed_at: datetime | None = None
    emitted_from: str = ""


@register_serializable
class Slot(Serializable):
    """Input slot for receiving data from other routines.

    A Slot is a queue-based buffer that stores data points with timestamps.
    Data is enqueued when events are emitted, and consumed by activation policies.

    Key Concepts:
        - Slots are defined in routines using define_slot()
        - Slots connect to events via Flow.connect()
        - Data is enqueued automatically when connected events are emitted
        - Activation policies consume data from slots
        - Each data point has timestamps: emitted_at, enqueued_at, consumed_at

    Queue Management:
        - Max queue length with watermark (default: 1000, watermark: 0.8)
        - Auto-shrink: consumed data is cleared when watermark is reached
        - Exception on full: raises SlotQueueFullError if queue is full and can't shrink

    Examples:
        Basic usage:
            >>> slot = routine.define_slot("input")
            >>> slot.enqueue(data={"value": 1}, emitted_from="routine_a", emitted_at=datetime.now())
            >>> data = slot.consume_all_new()
    """

    def __init__(
        self,
        name: str = "",
        routine: Routine | None = None,
        max_queue_length: int = 1000,
        watermark: float = 0.8,
    ):
        """Initialize Slot.

        Args:
            name: Slot name. Used to identify the slot within its parent routine.
            routine: Parent Routine object that owns this slot.
            max_queue_length: Maximum number of data points in the queue.
                Default: 1000
            watermark: Watermark threshold (0.0 to 1.0). When queue reaches
                this percentage of max_queue_length, consumed data is cleared.
                Default: 0.8 (80%)
        """
        # LOW fix: Add validation for parameters
        if max_queue_length <= 0:
            raise ValueError(f"max_queue_length must be > 0, got {max_queue_length}")
        if not 0.0 <= watermark <= 1.0:
            raise ValueError(f"watermark must be between 0.0 and 1.0, got {watermark}")

        super().__init__()
        self.name: str = name
        self.routine: Routine | None = routine
        self.max_queue_length: int = max_queue_length
        self.watermark: float = watermark
        self.watermark_threshold: int = int(max_queue_length * watermark)
        self.connected_events: list[Event] = []

        # Queue management
        self._queue: list[SlotDataPoint] = []
        self._last_consumed_index: int = -1  # Index of last consumed item
        self._lock = threading.RLock()  # Reentrant lock for queue operations
        # Critical fix: Separate lock for connection management to prevent deadlocks
        self._connection_lock: threading.RLock = threading.RLock()

        # Register serializable fields
        self.add_serializable_fields(["name", "max_queue_length", "watermark"])

    def __repr__(self) -> str:
        """Return string representation of the Slot."""
        if self.routine:
            return f"Slot[{self.routine._id}.{self.name}]"
        else:
            return f"Slot[{self.name}]"

    def connect(self, event: Event) -> None:
        """Connect to an event.

        Critical fix: Thread-safe connection to prevent race conditions
        in concurrent execution mode. Use lock ordering to prevent deadlock.

        Args:
            event: Event object to connect to.
        """
        # HIGH fix: Always acquire locks in consistent order (by id) to prevent deadlock
        lock1, lock2 = sorted((self._connection_lock, event._connection_lock), key=id)
        with lock1, lock2:
            if event not in self.connected_events:
                self.connected_events.append(event)
                # Bidirectional connection
                if self not in event.connected_slots:
                    event.connected_slots.append(self)

    def disconnect(self, event: Event) -> None:
        """Disconnect from an event.

        Critical fix: Thread-safe disconnection to prevent race conditions
        in concurrent execution mode. Use lock ordering to prevent deadlock.

        Args:
            event: Event object to disconnect from.
        """
        # HIGH fix: Always acquire locks in consistent order (by id) to prevent deadlock
        lock1, lock2 = sorted((self._connection_lock, event._connection_lock), key=id)
        with lock1, lock2:
            if event in self.connected_events:
                self.connected_events.remove(event)
                # Bidirectional disconnection
                if self in event.connected_slots:
                    event.connected_slots.remove(self)

    def enqueue(self, data: Any, emitted_from: str, emitted_at: datetime) -> None:
        """Add data to queue.

        This method is called by Runtime when an event is emitted and routed
        to this slot. It adds the data to the queue with timestamps.

        Args:
            data: Data to enqueue (any type).
            emitted_from: Name of the routine that emitted the event.
            emitted_at: Timestamp when the event was emitted.

        Raises:
            SlotQueueFullError: If queue is full and cannot be shrunk.

        Examples:
            >>> slot.enqueue(
            ...     data={"value": 1},
            ...     emitted_from="routine_a",
            ...     emitted_at=datetime.now()
            ... )
        """
        with self._lock:
            # Check watermark and auto-shrink
            if len(self._queue) >= self.watermark_threshold:
                self._clear_consumed_data()

            # Check if still full
            if len(self._queue) >= self.max_queue_length:
                raise SlotQueueFullError(
                    f"Slot '{self.name}' queue is full (max={self.max_queue_length}). "
                    f"Unconsumed: {self.get_unconsumed_count()}, Total: {len(self._queue)}"
                )

            # Add data point
            data_point = SlotDataPoint(
                data=data,
                emitted_at=emitted_at,
                enqueued_at=datetime.now(),
                emitted_from=emitted_from,
            )
            self._queue.append(data_point)

    def consume_all_new(self) -> list[Any]:
        """Consume all new data since last consumed, mark as consumed.

        Returns:
            List of data points (not SlotDataPoint objects, just the data).

        Examples:
            >>> data_list = slot.consume_all_new()
            >>> # Process data_list
        """
        with self._lock:
            start_index = self._last_consumed_index + 1
            end_index = len(self._queue)
            if start_index >= end_index:
                return []

            # Extract data
            data = [dp.data for dp in self._queue[start_index:end_index]]

            # Mark as consumed
            now = datetime.now()
            for i in range(start_index, end_index):
                self._queue[i].consumed_at = now

            self._last_consumed_index = end_index - 1
            return data

    def consume_one_new(self) -> Any | None:
        """Consume one new data point, mark as consumed.

        Returns:
            Data point if available, None otherwise.

        Examples:
            >>> data = slot.consume_one_new()
            >>> if data is not None:
            ...     # Process data
        """
        with self._lock:
            next_index = self._last_consumed_index + 1
            if next_index >= len(self._queue):
                return None

            data_point = self._queue[next_index]
            data_point.consumed_at = datetime.now()
            self._last_consumed_index = next_index
            return data_point.data

    def consume_all(self) -> list[Any]:
        """Consume all data (new + old), mark all as consumed.

        Returns:
            List of all data points.

        Examples:
            >>> all_data = slot.consume_all()
        """
        with self._lock:
            data = [dp.data for dp in self._queue]
            now = datetime.now()
            for dp in self._queue:
                if dp.consumed_at is None:
                    dp.consumed_at = now
            self._last_consumed_index = len(self._queue) - 1
            return data

    def consume_latest_and_mark_all_consumed(self) -> Any | None:
        """Consume the latest item and mark all previous as consumed.

        Returns:
            Latest data point if available, None otherwise.

        Examples:
            >>> latest = slot.consume_latest_and_mark_all_consumed()
        """
        with self._lock:
            if len(self._queue) == 0:
                return None

            # Mark all previous as consumed
            now = datetime.now()
            for i in range(len(self._queue) - 1):
                if self._queue[i].consumed_at is None:
                    self._queue[i].consumed_at = now

            # Consume latest
            latest = self._queue[-1]
            latest.consumed_at = now
            self._last_consumed_index = len(self._queue) - 1
            return latest.data

    def peek_all_new(self) -> list[Any]:
        """Peek at all new data without consuming.

        Returns:
            List of new data points (not consumed).

        Examples:
            >>> new_data = slot.peek_all_new()
            >>> # Inspect without consuming
        """
        with self._lock:
            start_index = self._last_consumed_index + 1
            end_index = len(self._queue)
            return [dp.data for dp in self._queue[start_index:end_index]]

    def peek_one_new(self) -> Any | None:
        """Peek at one new data point without consuming.

        Returns:
            Next unconsumed data point if available, None otherwise.

        Examples:
            >>> next_data = slot.peek_one_new()
        """
        with self._lock:
            next_index = self._last_consumed_index + 1
            if next_index >= len(self._queue):
                return None
            return self._queue[next_index].data

    def peek_latest(self) -> Any | None:
        """Peek at the latest data point without consuming.

        Returns:
            Latest data point if available, None otherwise.

        Examples:
            >>> latest = slot.peek_latest()
        """
        with self._lock:
            if len(self._queue) == 0:
                return None
            return self._queue[-1].data

    def get_unconsumed_count(self) -> int:
        """Get count of unconsumed data points.

        Returns:
            Number of unconsumed items in the queue.

        Examples:
            >>> count = slot.get_unconsumed_count()
        """
        with self._lock:
            return len(self._queue) - (self._last_consumed_index + 1)

    def get_total_count(self) -> int:
        """Get total count of data points (consumed + unconsumed).

        Returns:
            Total number of items in the queue.

        Examples:
            >>> total = slot.get_total_count()
        """
        with self._lock:
            return len(self._queue)

    def get_queue_state(self) -> dict[str, Any]:
        """Get current queue state for inspection.

        Returns:
            Dictionary with queue state information.

        Examples:
            >>> state = slot.get_queue_state()
            >>> print(state["unconsumed_count"])
        """
        with self._lock:
            unconsumed_count = self.get_unconsumed_count()
            oldest_unconsumed = None
            if unconsumed_count > 0:
                first_unconsumed_index = self._last_consumed_index + 1
                if first_unconsumed_index < len(self._queue):
                    oldest_unconsumed = self._queue[first_unconsumed_index].enqueued_at

            return {
                "total_count": len(self._queue),
                "unconsumed_count": unconsumed_count,
                "consumed_count": self._last_consumed_index + 1,
                "max_length": self.max_queue_length,
                "watermark_threshold": self.watermark_threshold,
                "oldest_unconsumed": oldest_unconsumed.isoformat() if oldest_unconsumed else None,
            }

    def get_queue_status(self) -> dict[str, Any]:
        """Get queue status information for monitoring.

        Returns comprehensive queue status including pressure level and usage metrics.

        Returns:
            Dictionary with queue status information:
            - unconsumed_count: Number of unconsumed data points
            - total_count: Total number of data points in queue
            - max_length: Maximum queue length
            - watermark_threshold: Watermark threshold for auto-shrink
            - usage_percentage: Queue usage percentage (0.0-1.0)
            - pressure_level: Pressure level (low, medium, high, critical)
            - is_full: Whether queue is full
            - is_near_full: Whether queue is near full (above watermark)

        Examples:
            >>> status = slot.get_queue_status()
            >>> print(status["pressure_level"])  # "low", "medium", "high", or "critical"
            >>> print(status["usage_percentage"])  # 0.0 to 1.0
        """
        with self._lock:
            unconsumed = self.get_unconsumed_count()
            total = len(self._queue)
            usage = total / self.max_queue_length if self.max_queue_length > 0 else 0.0

            # Calculate pressure level
            if usage >= 1.0:
                pressure = "critical"
                is_full = True
            elif usage >= self.watermark:
                pressure = "high"
                is_full = False
            elif usage >= 0.6:
                pressure = "medium"
                is_full = False
            else:
                pressure = "low"
                is_full = False

            is_near_full = usage >= self.watermark

            return {
                "unconsumed_count": unconsumed,
                "total_count": total,
                "max_length": self.max_queue_length,
                "watermark_threshold": self.watermark_threshold,
                "usage_percentage": usage,
                "pressure_level": pressure,
                "is_full": is_full,
                "is_near_full": is_near_full,
            }

    def _clear_consumed_data(self) -> None:
        """Clear all consumed data to free space.

        This is called automatically when watermark is reached.
        """
        with self._lock:
            # Find first unconsumed index
            first_unconsumed = self._last_consumed_index + 1
            if first_unconsumed > 0:
                # Remove consumed items
                self._queue = self._queue[first_unconsumed:]
                self._last_consumed_index = -1

    def serialize(self) -> dict[str, Any]:
        """Serialize Slot.

        Returns:
            Serialized dictionary.
        """
        data = super().serialize()
        # Serialize queue state (for resumption)
        with self._lock:
            data["_queue"] = [
                {
                    "data": dp.data,
                    "emitted_at": dp.emitted_at.isoformat(),
                    "enqueued_at": dp.enqueued_at.isoformat(),
                    "consumed_at": dp.consumed_at.isoformat() if dp.consumed_at else None,
                    "emitted_from": dp.emitted_from,
                }
                for dp in self._queue
            ]
            data["_last_consumed_index"] = self._last_consumed_index
        return data

    def deserialize(
        self, data: dict[str, Any], strict: bool = False, registry: Any | None = None
    ) -> None:
        """Deserialize Slot.

        Args:
            data: Serialized data dictionary.
            strict: Whether to use strict deserialization.
            registry: Optional ObjectRegistry for deserializing callables.
        """
        super().deserialize(data, strict=strict, registry=registry)

        # Restore queue state
        if "_queue" in data:
            self._queue = []
            for dp_data in data["_queue"]:
                data_point = SlotDataPoint(
                    data=dp_data["data"],
                    emitted_at=datetime.fromisoformat(dp_data["emitted_at"]),
                    enqueued_at=datetime.fromisoformat(dp_data["enqueued_at"]),
                    consumed_at=datetime.fromisoformat(dp_data["consumed_at"])
                    if dp_data.get("consumed_at")
                    else None,
                    emitted_from=dp_data.get("emitted_from", ""),
                )
                self._queue.append(data_point)

            self._last_consumed_index = data.get("_last_consumed_index", -1)
