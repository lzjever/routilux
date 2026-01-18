"""
Slot class for receiving data from other routines.

Slots are queue-based buffers that store data with timestamps.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from routilux.core.event import Event
    from routilux.core.routine import Routine

from serilux import Serializable


class SlotQueueFullError(Exception):
    """Exception raised when slot queue is full and cannot accept more data."""

    pass


@dataclass
class SlotDataPoint:
    """Data point in a slot queue with timestamps."""

    data: Any
    emitted_at: datetime
    enqueued_at: datetime
    consumed_at: Optional[datetime] = None
    emitted_from: str = ""


# Note: Not using @register_serializable to avoid conflict with legacy module
class Slot(Serializable):
    """Input slot for receiving data from other routines.

    A Slot is a queue-based buffer that stores data points with timestamps.
    Data is enqueued when events are emitted, and consumed by activation policies.

    Key Concepts:
        - Slots are defined in routines using add_slot()
        - Slots connect to events via Flow.connect()
        - Data is enqueued automatically when connected events are emitted
        - Activation policies consume data from slots

    Queue Management:
        - Max queue length with watermark (default: 1000, watermark: 0.8)
        - Auto-shrink: consumed data is cleared when watermark is reached
        - Exception on full: raises SlotQueueFullError if queue is full

    Examples:
        >>> slot = routine.add_slot("input")
        >>> slot.enqueue(data={"value": 1}, emitted_from="routine_a", emitted_at=datetime.now())
        >>> data = slot.consume_all_new()
    """

    def __init__(
        self,
        name: str = "",
        routine: Optional["Routine"] = None,
        max_queue_length: int = 1000,
        watermark: float = 0.8,
    ):
        """Initialize Slot.

        Args:
            name: Slot name
            routine: Parent Routine object
            max_queue_length: Maximum queue length (default: 1000)
            watermark: Watermark threshold for auto-shrink (default: 0.8)
        """
        if max_queue_length <= 0:
            raise ValueError(f"max_queue_length must be > 0, got {max_queue_length}")
        if not 0.0 <= watermark <= 1.0:
            raise ValueError(f"watermark must be between 0.0 and 1.0, got {watermark}")

        super().__init__()
        self.name: str = name
        self.routine: Optional["Routine"] = routine
        self.max_queue_length: int = max_queue_length
        self.watermark: float = watermark
        self.watermark_threshold: int = int(max_queue_length * watermark)
        self.connected_events: List["Event"] = []

        # Queue management
        self._queue: List[SlotDataPoint] = []
        self._last_consumed_index: int = -1
        self._lock = threading.RLock()
        self._connection_lock: threading.RLock = threading.RLock()

        # Register serializable fields
        self.add_serializable_fields(["name", "max_queue_length", "watermark"])

    def __repr__(self) -> str:
        """Return string representation."""
        if self.routine:
            return f"Slot[{getattr(self.routine, '_id', 'unknown')}.{self.name}]"
        return f"Slot[{self.name}]"

    def connect(self, event: "Event") -> None:
        """Connect to an event (thread-safe)."""
        lock1, lock2 = sorted((self._connection_lock, event._connection_lock), key=id)
        with lock1, lock2:
            if event not in self.connected_events:
                self.connected_events.append(event)
                if self not in event.connected_slots:
                    event.connected_slots.append(self)

    def disconnect(self, event: "Event") -> None:
        """Disconnect from an event (thread-safe)."""
        lock1, lock2 = sorted((self._connection_lock, event._connection_lock), key=id)
        with lock1, lock2:
            if event in self.connected_events:
                self.connected_events.remove(event)
                if self in event.connected_slots:
                    event.connected_slots.remove(self)

    def enqueue(self, data: Any, emitted_from: str, emitted_at: datetime) -> None:
        """Add data to queue.

        Args:
            data: Data to enqueue
            emitted_from: Name of routine that emitted the event
            emitted_at: Timestamp when event was emitted

        Raises:
            SlotQueueFullError: If queue is full
        """
        with self._lock:
            if len(self._queue) >= self.watermark_threshold:
                self._clear_consumed_data()

            if len(self._queue) >= self.max_queue_length:
                raise SlotQueueFullError(
                    f"Slot '{self.name}' queue is full (max={self.max_queue_length})"
                )

            data_point = SlotDataPoint(
                data=data,
                emitted_at=emitted_at,
                enqueued_at=datetime.now(),
                emitted_from=emitted_from,
            )
            self._queue.append(data_point)

    def consume_all_new(self) -> List[Any]:
        """Consume all new data since last consumed."""
        with self._lock:
            start_index = self._last_consumed_index + 1
            end_index = len(self._queue)
            if start_index >= end_index:
                return []

            data = [dp.data for dp in self._queue[start_index:end_index]]
            now = datetime.now()
            for i in range(start_index, end_index):
                self._queue[i].consumed_at = now

            self._last_consumed_index = end_index - 1
            return data

    def consume_one_new(self) -> Optional[Any]:
        """Consume one new data point."""
        with self._lock:
            next_index = self._last_consumed_index + 1
            if next_index >= len(self._queue):
                return None

            data_point = self._queue[next_index]
            data_point.consumed_at = datetime.now()
            self._last_consumed_index = next_index
            return data_point.data

    def consume_all(self) -> List[Any]:
        """Consume all data (new + old)."""
        with self._lock:
            data = [dp.data for dp in self._queue]
            now = datetime.now()
            for dp in self._queue:
                if dp.consumed_at is None:
                    dp.consumed_at = now
            self._last_consumed_index = len(self._queue) - 1
            return data

    def consume_latest_and_mark_all_consumed(self) -> Optional[Any]:
        """Consume latest item and mark all previous as consumed."""
        with self._lock:
            if len(self._queue) == 0:
                return None

            now = datetime.now()
            for i in range(len(self._queue) - 1):
                if self._queue[i].consumed_at is None:
                    self._queue[i].consumed_at = now

            latest = self._queue[-1]
            latest.consumed_at = now
            self._last_consumed_index = len(self._queue) - 1
            return latest.data

    def peek_all_new(self) -> List[Any]:
        """Peek at all new data without consuming."""
        with self._lock:
            start_index = self._last_consumed_index + 1
            return [dp.data for dp in self._queue[start_index:]]

    def peek_one_new(self) -> Optional[Any]:
        """Peek at next unconsumed data point."""
        with self._lock:
            next_index = self._last_consumed_index + 1
            if next_index >= len(self._queue):
                return None
            return self._queue[next_index].data

    def peek_latest(self) -> Optional[Any]:
        """Peek at latest data point."""
        with self._lock:
            if len(self._queue) == 0:
                return None
            return self._queue[-1].data

    def get_unconsumed_count(self) -> int:
        """Get count of unconsumed data points."""
        with self._lock:
            return len(self._queue) - (self._last_consumed_index + 1)

    def get_total_count(self) -> int:
        """Get total count of data points."""
        with self._lock:
            return len(self._queue)

    def get_queue_state(self) -> dict[str, Any]:
        """Get current queue state for inspection."""
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
                "oldest_unconsumed": oldest_unconsumed.isoformat()
                if oldest_unconsumed
                else None,
            }

    def get_queue_status(self) -> dict[str, Any]:
        """Get queue status for monitoring."""
        with self._lock:
            unconsumed = self.get_unconsumed_count()
            total = len(self._queue)
            usage = total / self.max_queue_length if self.max_queue_length > 0 else 0.0

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

            return {
                "unconsumed_count": unconsumed,
                "total_count": total,
                "max_length": self.max_queue_length,
                "watermark_threshold": self.watermark_threshold,
                "usage_percentage": usage,
                "pressure_level": pressure,
                "is_full": is_full,
                "is_near_full": usage >= self.watermark,
            }

    def _clear_consumed_data(self) -> None:
        """Clear consumed data to free space."""
        with self._lock:
            first_unconsumed = self._last_consumed_index + 1
            if first_unconsumed > 0:
                self._queue = self._queue[first_unconsumed:]
                self._last_consumed_index = -1

    def serialize(self) -> dict[str, Any]:
        """Serialize Slot."""
        data = super().serialize()
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
        """Deserialize Slot."""
        super().deserialize(data, strict=strict, registry=registry)

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
