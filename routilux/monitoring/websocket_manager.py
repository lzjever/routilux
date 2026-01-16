"""
WebSocket manager for real-time monitoring and debug events.

Manages WebSocket connections and broadcasts messages to connected clients.
Supports connection status events, heartbeat, and event filtering.
"""

import asyncio
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

if TYPE_CHECKING:
    from fastapi import WebSocket

    from routilux.monitoring.breakpoint_manager import Breakpoint
    from routilux.monitoring.monitor_collector import ExecutionEvent, ExecutionMetrics
    from routilux.routine import ExecutionContext

# Optional FastAPI import for WebSocket type
try:
    from fastapi import WebSocket
except ImportError:
    # WebSocket is only used for type hints, use Any as fallback
    WebSocket = Any


class WebSocketConnection:
    """Represents a WebSocket connection with subscription management."""

    def __init__(self, job_id: str, websocket: WebSocket):
        """Initialize WebSocket connection.

        Args:
            job_id: Job identifier.
            websocket: WebSocket connection.
        """
        self.job_id = job_id
        self.websocket = websocket
        self.subscriptions: Set[str] = set()  # Subscribed event types
        self.subscribed_all: bool = True  # Default: subscribe to all events
        self.last_ping = time.time()
        self.connected_at = time.time()

    async def subscribe(self, events: List[str]) -> None:
        """Subscribe to specific event types.

        Args:
            events: List of event types to subscribe to.
        """
        self.subscriptions.update(events)
        self.subscribed_all = False

    async def unsubscribe(self, events: List[str]) -> None:
        """Unsubscribe from specific event types.

        Args:
            events: List of event types to unsubscribe from.
        """
        self.subscriptions.difference_update(events)

    async def subscribe_all(self) -> None:
        """Subscribe to all event types."""
        self.subscribed_all = True
        self.subscriptions.clear()

    def should_send_event(self, event_type: str) -> bool:
        """Check if this connection should receive an event.

        Args:
            event_type: Event type to check.

        Returns:
            True if event should be sent, False otherwise.
        """
        return self.subscribed_all or event_type in self.subscriptions

    async def send_json(self, message: Dict) -> None:
        """Send JSON message to this connection.

        Args:
            message: Message dictionary to send.
        """
        await self.websocket.send_json(message)

    async def send_connection_status(self, status: str) -> None:
        """Send connection status event.

        Args:
            status: Connection status (connected/disconnected/reconnecting).
        """
        await self.send_json(
            {
                "type": "connection:status",
                "status": status,
                "timestamp": datetime.utcnow().isoformat(),
                "server_time": datetime.utcnow().isoformat(),
            }
        )

    async def send_ping(self) -> None:
        """Send ping message for heartbeat."""
        self.last_ping = time.time()
        await self.send_json(
            {
                "type": "ping",
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    async def handle_pong(self) -> None:
        """Handle pong response from client."""
        self.last_ping = time.time()


class WebSocketManager:
    """Manages WebSocket connections for real-time updates.

    Thread-safe manager that maintains connections per job_id and broadcasts
    messages to connected clients. Supports event filtering and heartbeat.
    """

    def __init__(self):
        """Initialize WebSocket manager."""
        self._connections: Dict[
            str, Set[WebSocketConnection]
        ] = {}  # job_id -> Set[WebSocketConnection]
        self._lock = asyncio.Lock()
        self._heartbeat_tasks: Dict[str, asyncio.Task] = {}  # job_id -> heartbeat task

    async def connect(self, job_id: str, websocket: WebSocket) -> WebSocketConnection:
        """Connect a WebSocket for a job.

        Args:
            job_id: Job identifier.
            websocket: WebSocket connection.

        Returns:
            WebSocketConnection: The connection object.
        """
        async with self._lock:
            if job_id not in self._connections:
                self._connections[job_id] = set()
                # Start heartbeat task for this job
                self._heartbeat_tasks[job_id] = asyncio.create_task(self._heartbeat_loop(job_id))

            conn = WebSocketConnection(job_id, websocket)
            self._connections[job_id].add(conn)

            # Send connection status
            await conn.send_connection_status("connected")

            return conn

    async def disconnect(self, job_id: str, websocket: WebSocket) -> None:
        """Disconnect a WebSocket for a job.

        Args:
            job_id: Job identifier.
            websocket: WebSocket connection.
        """
        task_to_cancel = None

        async with self._lock:
            if job_id in self._connections:
                # Find and remove the connection
                to_remove = None
                for conn in self._connections[job_id]:
                    if conn.websocket == websocket:
                        to_remove = conn
                        break

                if to_remove:
                    # Fix: Wrap in try-finally to ensure WebSocket is closed
                    try:
                        await to_remove.send_connection_status("disconnected")
                    except Exception:
                        # Ignore send errors, connection might be dead
                        pass
                    finally:
                        # Ensure WebSocket is closed
                        try:
                            await to_remove.websocket.close()
                        except Exception:
                            # Already closed or invalid
                            pass
                    self._connections[job_id].discard(to_remove)

                # Clean up if no more connections
                if not self._connections[job_id]:
                    del self._connections[job_id]
                    # Fix: Cancel and properly await heartbeat task
                    if job_id in self._heartbeat_tasks:
                        task_to_cancel = self._heartbeat_tasks.pop(job_id)

        # Fix: Await cancelled task outside of lock to prevent deadlock
        if task_to_cancel is not None:
            task_to_cancel.cancel()
            try:
                await task_to_cancel
            except asyncio.CancelledError:
                # Expected - task was cancelled
                pass

    async def broadcast(self, job_id: str, event_type: str, message: Dict) -> None:
        """Broadcast message to all subscribed connections for a job.

        Args:
            job_id: Job identifier.
            event_type: Type of event being broadcast.
            message: Message dictionary to send.
        """
        async with self._lock:
            connections = self._connections.get(job_id, set()).copy()

        # Send only to subscribed connections (outside lock to avoid blocking)
        disconnected = []
        for conn in connections:
            if conn.should_send_event(event_type):
                try:
                    await conn.send_json(message)
                except Exception:
                    # Connection closed, mark for removal
                    disconnected.append(conn.websocket)

        # Remove disconnected connections
        for ws in disconnected:
            await self.disconnect(job_id, ws)

    async def _heartbeat_loop(self, job_id: str) -> None:
        """Send periodic heartbeat pings to all connections for a job.

        Args:
            job_id: Job identifier.
        """
        try:
            while True:
                await asyncio.sleep(30)  # 30 second heartbeat

                async with self._lock:
                    connections = list(self._connections.get(job_id, set()))

                for conn in connections:
                    try:
                        await conn.send_ping()
                    except Exception:
                        # Connection failed, will be cleaned up on next broadcast
                        pass

        except asyncio.CancelledError:
            # Heartbeat cancelled, exit gracefully
            pass

    async def send_metrics(self, job_id: str, metrics: "ExecutionMetrics") -> None:
        """Send metrics update.

        Args:
            job_id: Job identifier.
            metrics: Execution metrics.
        """
        message = {
            "type": "metrics",
            "job_id": job_id,
            "metrics": {
                "start_time": metrics.start_time.isoformat() if metrics.start_time else None,
                "end_time": metrics.end_time.isoformat() if metrics.end_time else None,
                "duration": metrics.duration,
                "total_events": metrics.total_events,
                "total_slot_calls": metrics.total_slot_calls,
                "total_event_emits": metrics.total_event_emits,
            },
        }
        await self.broadcast(job_id, "metrics", message)

    async def send_breakpoint_hit(
        self,
        job_id: str,
        breakpoint: "Breakpoint",
        context: Optional["ExecutionContext"] = None,
    ) -> None:
        """Send breakpoint hit notification.

        Args:
            job_id: Job identifier.
            breakpoint: Breakpoint that was hit.
            context: Execution context where breakpoint was hit.
        """
        message = {
            "type": "breakpoint_hit",
            "job_id": job_id,
            "breakpoint": {
                "breakpoint_id": breakpoint.breakpoint_id,
                "type": breakpoint.type,
                "routine_id": breakpoint.routine_id,
                "slot_name": breakpoint.slot_name,
                "event_name": breakpoint.event_name,
            },
            "context": {
                "routine_id": context.routine_id if context else None,
            }
            if context
            else None,
        }
        await self.broadcast(job_id, "breakpoint_hit", message)

    async def send_execution_event(self, job_id: str, event: "ExecutionEvent") -> None:
        """Send execution event notification.

        Args:
            job_id: Job identifier.
            event: Execution event.
        """
        message = {
            "type": "execution_event",
            "job_id": job_id,
            "event": {
                "event_id": event.event_id,
                "routine_id": event.routine_id,
                "event_type": event.event_type,
                "timestamp": event.timestamp.isoformat(),
                "data": event.data,
            },
        }
        await self.broadcast(job_id, "execution_event", message)


# Global instance
ws_manager = WebSocketManager()
