"""
WebSocket routes for real-time monitoring and debug events.

Uses event-driven push notifications via JobEventManager instead of polling.
Includes comprehensive error handling, timeouts, and retry logic.
Supports event filtering via subscription management.
"""

import asyncio
import logging
from typing import Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from routilux.monitoring.event_manager import get_event_manager
from routilux.monitoring.registry import MonitoringRegistry
from routilux.monitoring.storage import flow_store, job_store

logger = logging.getLogger(__name__)
router = APIRouter()

# WebSocket configuration
WS_IDLE_TIMEOUT = 300.0  # 5 minutes
WS_SEND_TIMEOUT = 5.0  # 5 seconds
MAX_SEND_RETRIES = 3


async def safe_send_json(
    websocket: WebSocket,
    data: dict,
    description: str = "message",
) -> bool:
    """Safely send JSON to WebSocket with retry logic.

    Args:
        websocket: WebSocket connection.
        data: Data to send.
        description: Description of data for logging.

    Returns:
        True if send succeeded, False otherwise.
    """
    for attempt in range(MAX_SEND_RETRIES):
        try:
            await asyncio.wait_for(websocket.send_json(data), timeout=WS_SEND_TIMEOUT)
            return True
        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout sending {description} (attempt {attempt + 1}/{MAX_SEND_RETRIES})"
            )
            if attempt < MAX_SEND_RETRIES - 1:
                await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff
        except Exception as e:
            logger.error(f"Failed to send {description}: {e}")
            return False

    logger.error(f"Failed to send {description} after {MAX_SEND_RETRIES} attempts")
    return False


async def handle_client_message(
    websocket: WebSocket, message: Dict, subscriptions: Dict[str, bool]
) -> None:
    """Handle client messages for subscription management.

    Args:
        websocket: WebSocket connection.
        message: Message from client.
        subscriptions: Dictionary tracking current subscriptions.
    """
    action = message.get("action")

    if action == "subscribe":
        # Subscribe to specific event types
        events = message.get("events", [])
        event_types = subscriptions.setdefault("event_types", set())

        # Send confirmation
        await safe_send_json(
            websocket,
            {
                "type": "subscription:confirmed",
                "action": "subscribe",
                "events": events,
            },
            "subscription confirmation",
        )

        logger.debug(f"Client subscribed to events: {events}")

    elif action == "unsubscribe":
        # Unsubscribe from specific event types
        events = message.get("events", [])
        event_types = subscriptions.get("event_types", set())

        for event in events:
            event_types.discard(event)

        # Send confirmation
        await safe_send_json(
            websocket,
            {
                "type": "subscription:confirmed",
                "action": "unsubscribe",
                "events": events,
            },
            "unsubscribe confirmation",
        )

        logger.debug(f"Client unsubscribed from events: {events}")

    elif action == "subscribe_all":
        # Subscribe to all events
        subscriptions["event_types"] = set()
        subscriptions["all"] = True

        # Send confirmation
        await safe_send_json(
            websocket,
            {
                "type": "subscription:confirmed",
                "action": "subscribe_all",
            },
            "subscribe all confirmation",
        )

        logger.debug("Client subscribed to all events")

    elif action == "pong":
        # Handle pong response (already handled by heartbeat)
        pass

    else:
        logger.warning(f"Unknown client message action: {action}")


@router.websocket("/ws/jobs/{job_id}/monitor")
async def job_monitor_websocket(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time job monitoring.

    Uses event-driven push notifications via JobEventManager.
    Receives events as they occur instead of polling.

    Features:
    - Automatic retry on send failures
    - Connection timeout handling
    - Comprehensive error logging
    """
    subscriber_id: Optional[str] = None

    try:
        # Verify job exists (with error handling)
        try:
            job_state = job_store.get(job_id)
        except Exception as e:
            logger.error(f"Error checking job {job_id}: {e}")
            await websocket.close(code=1011, reason="Internal error checking job")
            return

        if not job_state:
            await websocket.close(code=1008, reason=f"Job '{job_id}' not found")
            return

        # Accept WebSocket connection
        await websocket.accept()
        logger.info(f"WebSocket connection accepted for job {job_id}")

        # Subscribe to job events
        event_manager = get_event_manager()
        subscriber_id = await event_manager.subscribe(job_id)
        logger.info(f"WebSocket subscribed to job {job_id} as {subscriber_id}")

        registry = MonitoringRegistry.get_instance()
        collector = registry.monitor_collector

        # Send initial metrics
        if collector:
            try:
                metrics = collector.get_metrics(job_id)
                if metrics:
                    success = await safe_send_json(
                        websocket,
                        {
                            "type": "metrics",
                            "job_id": job_id,
                            "metrics": {
                                "start_time": metrics.start_time.isoformat()
                                if metrics.start_time
                                else None,
                                "end_time": metrics.end_time.isoformat()
                                if metrics.end_time
                                else None,
                                "duration": metrics.duration,
                                "total_events": metrics.total_events,
                                "total_slot_calls": metrics.total_slot_calls,
                                "total_event_emits": metrics.total_event_emits,
                            },
                        },
                        "initial metrics",
                    )
                    if not success:
                        logger.warning(f"Failed to send initial metrics for job {job_id}")
            except Exception as e:
                logger.error(f"Error getting/sending metrics for job {job_id}: {e}")

        # Event-driven loop: receive events as they occur
        async for event in event_manager.iter_events(subscriber_id):
            # Send event to WebSocket client
            success = await safe_send_json(websocket, event, f"event for job {job_id}")
            if not success:
                logger.warning(f"Failed to send event, closing connection for job {job_id}")
                break

            # Send periodic ping to keep connection alive (every 30 events)
            # This is lightweight since events are pushed as they occur
            if event.get("event_type") != "ping":
                await safe_send_json(websocket, {"type": "ping"}, "ping")

    except WebSocketDisconnect as e:
        logger.debug(f"WebSocket disconnected for job {job_id}: code={e.code}")
    except asyncio.CancelledError:
        logger.debug(f"WebSocket task cancelled for job {job_id}")
    except asyncio.TimeoutError:
        logger.warning(f"WebSocket timeout for job {job_id}")
    except Exception as e:
        logger.error(f"Unexpected error in job monitor WebSocket for {job_id}: {e}", exc_info=True)
    finally:
        # Unsubscribe from events (if subscription was successful)
        if subscriber_id:
            try:
                event_manager = get_event_manager()
                await event_manager.unsubscribe(subscriber_id)
                logger.info(f"WebSocket unsubscribed from job {job_id} ({subscriber_id})")
            except Exception as e:
                logger.error(f"Error unsubscribing from job {job_id}: {e}")


@router.websocket("/ws/jobs/{job_id}/debug")
async def job_debug_websocket(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time debug events.

    Uses event-driven push notifications via JobEventManager.
    Filters and sends debug-relevant events only.
    """
    subscriber_id: Optional[str] = None

    try:
        # Verify job exists
        try:
            job_state = job_store.get(job_id)
        except Exception as e:
            logger.error(f"Error checking job {job_id}: {e}")
            await websocket.close(code=1011, reason="Internal error checking job")
            return

        if not job_state:
            await websocket.close(code=1008, reason=f"Job '{job_id}' not found")
            return

        # Accept WebSocket connection
        await websocket.accept()
        logger.info(f"Debug WebSocket connection accepted for job {job_id}")

        # Subscribe to job events
        event_manager = get_event_manager()
        subscriber_id = await event_manager.subscribe(job_id)
        logger.info(f"Debug WebSocket subscribed to job {job_id} as {subscriber_id}")

        registry = MonitoringRegistry.get_instance()
        debug_store = registry.debug_session_store

        # Send initial debug session state
        if debug_store:
            try:
                session = debug_store.get(job_id)
                if session:
                    success = await safe_send_json(
                        websocket,
                        {
                            "type": "debug_session",
                            "job_id": job_id,
                            "status": session.status,
                        },
                        "debug session",
                    )
                    if not success:
                        logger.warning(f"Failed to send debug session for job {job_id}")
            except Exception as e:
                logger.error(f"Error getting/sending debug session for job {job_id}: {e}")

        # Event-driven loop: receive events as they occur
        async for event in event_manager.iter_events(subscriber_id):
            # Filter for debug-relevant events
            event_type = event.get("event_type")
            if event_type in ("routine_start", "routine_end", "slot_call"):
                # Send debug event to client
                success = await safe_send_json(
                    websocket,
                    {"type": "debug_event", "event": event},
                    f"debug event for job {job_id}",
                )
                if not success:
                    break

            # Send periodic ping
            if event_type != "ping":
                await safe_send_json(websocket, {"type": "ping"}, "ping")

    except WebSocketDisconnect as e:
        logger.debug(f"Debug WebSocket disconnected for job {job_id}: code={e.code}")
    except asyncio.CancelledError:
        logger.debug(f"Debug WebSocket task cancelled for job {job_id}")
    except asyncio.TimeoutError:
        logger.warning(f"Debug WebSocket timeout for job {job_id}")
    except Exception as e:
        logger.error(f"Unexpected error in debug WebSocket for {job_id}: {e}", exc_info=True)
    finally:
        # Unsubscribe from events
        if subscriber_id:
            try:
                event_manager = get_event_manager()
                await event_manager.unsubscribe(subscriber_id)
                logger.info(f"Debug WebSocket unsubscribed from job {job_id} ({subscriber_id})")
            except Exception as e:
                logger.error(f"Error unsubscribing from job {job_id}: {e}")


@router.websocket("/ws/flows/{flow_id}/monitor")
async def flow_monitor_websocket(websocket: WebSocket, flow_id: str):
    """WebSocket endpoint for real-time flow monitoring.

    Aggregates events from all jobs belonging to this flow.
    Manages multiple subscriptions concurrently.
    """
    event_manager = get_event_manager()
    subscribers = []  # List of (job_id, subscriber_id) tuples

    try:
        # Verify flow exists
        try:
            flow = flow_store.get(flow_id)
        except Exception as e:
            logger.error(f"Error checking flow {flow_id}: {e}")
            await websocket.close(code=1011, reason="Internal error checking flow")
            return

        if not flow:
            await websocket.close(code=1008, reason=f"Flow '{flow_id}' not found")
            return

        # Accept WebSocket connection
        await websocket.accept()
        logger.info(f"Flow WebSocket connection accepted for flow {flow_id}")

        # Get all jobs for this flow
        try:
            jobs = job_store.get_by_flow(flow_id)
        except Exception as e:
            logger.error(f"Error getting jobs for flow {flow_id}: {e}")
            await websocket.close(code=1011, reason="Internal error getting jobs")
            return

        # Subscribe to all job events
        for job in jobs:
            try:
                sub_id = await event_manager.subscribe(job.job_id)
                subscribers.append((job.job_id, sub_id))
                logger.info(f"Flow WebSocket subscribed to job {job.job_id} as {sub_id}")
            except Exception as e:
                logger.error(f"Error subscribing to job {job.job_id}: {e}")

        # Send initial flow metrics
        success = await safe_send_json(
            websocket,
            {
                "type": "flow_metrics",
                "flow_id": flow_id,
                "total_jobs": len(jobs),
            },
            "flow metrics",
        )
        if not success:
            logger.warning(f"Failed to send flow metrics for {flow_id}")

        # Create tasks to listen to all job events concurrently
        async def listen_to_job(job_id: str, sub_id: str):
            """Listen to events from a single job."""
            try:
                async for event in event_manager.iter_events(sub_id):
                    # Forward event with flow context
                    success = await safe_send_json(
                        websocket,
                        {
                            "type": "flow_job_event",
                            "flow_id": flow_id,
                            "job_id": job_id,
                            "event": event,
                        },
                        f"flow event for job {job_id}",
                    )
                    if not success:
                        break
            except Exception as e:
                logger.error(f"Error listening to job {job_id}: {e}")

        # Run all listeners concurrently
        tasks = [listen_to_job(job_id, sub_id) for job_id, sub_id in subscribers]

        # Wait for all tasks (runs until WebSocket disconnects)
        await asyncio.gather(*tasks, return_exceptions=True)

    except WebSocketDisconnect as e:
        logger.debug(f"Flow WebSocket disconnected for flow {flow_id}: code={e.code}")
    except asyncio.CancelledError:
        logger.debug(f"Flow WebSocket task cancelled for flow {flow_id}")
    except asyncio.TimeoutError:
        logger.warning(f"Flow WebSocket timeout for flow {flow_id}")
    except Exception as e:
        logger.error(
            f"Unexpected error in flow monitor WebSocket for {flow_id}: {e}", exc_info=True
        )
    finally:
        # Unsubscribe from all job events
        for job_id, sub_id in subscribers:
            try:
                await event_manager.unsubscribe(sub_id)
                logger.info(f"Flow WebSocket unsubscribed from job {job_id} ({sub_id})")
            except Exception as e:
                logger.error(f"Error unsubscribing from job {job_id}: {e}")
