"""
WebSocket routes for real-time monitoring and debug events.

Uses event-driven push notifications via JobEventManager instead of polling.
Includes comprehensive error handling, timeouts, and retry logic.
Supports event filtering via subscription management.
"""

import asyncio
import logging
import re
from typing import Dict, Optional
from urllib.parse import parse_qs

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from routilux.monitoring.event_manager import get_event_manager
from routilux.monitoring.registry import MonitoringRegistry
from routilux.monitoring.storage import flow_store

# Note: job_store (old system) removed - use get_job_storage() instead

logger = logging.getLogger(__name__)
router = APIRouter()

# WebSocket configuration
WS_IDLE_TIMEOUT = 300.0  # 5 minutes
WS_SEND_TIMEOUT = 5.0  # 5 seconds
MAX_SEND_RETRIES = 3


async def _check_websocket_auth(websocket: WebSocket) -> bool:
    """Check API key from query when api_key_enabled. Close with 1008 if invalid.

    Returns True if auth passed or disabled, False if closed due to auth failure.
    """
    from routilux.server.config import get_config

    config = get_config()
    if not config.api_key_enabled:
        return True

    query_string = websocket.scope.get("query_string") or b""
    if isinstance(query_string, bytes):
        query_string = query_string.decode("utf-8")
    params = parse_qs(query_string)
    api_key = (params.get("api_key") or [None])[0]

    if not api_key or not config.is_api_key_valid(api_key):
        await websocket.close(code=1008, reason="Invalid or missing API key")
        return False
    return True


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
        # MEDIUM fix: Validate job_id format before processing
        if not job_id or not isinstance(job_id, str):
            await websocket.close(code=1008, reason="Invalid job_id format")
            return
        # job_id should be a UUID format (alphanumeric with dashes)
        if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
            await websocket.close(code=1008, reason="Invalid job_id format")
            return

        # Verify job exists (with error handling)
        try:
            from routilux.server.dependencies import get_job_storage, get_runtime

            job_storage = get_job_storage()
            runtime = get_runtime()
            job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
        except Exception as e:
            logger.error(f"Error checking job {job_id}: {e}")
            await websocket.close(code=1011, reason="Internal error checking job")
            return

        if not job_context:
            await websocket.close(code=1008, reason=f"Job '{job_id}' not found")
            return

        if not await _check_websocket_auth(websocket):
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
        # MEDIUM fix: Validate job_id format before processing
        if not job_id or not isinstance(job_id, str):
            await websocket.close(code=1008, reason="Invalid job_id format")
            return
        # job_id should be a UUID format (alphanumeric with dashes)
        if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
            await websocket.close(code=1008, reason="Invalid job_id format")
            return

        # Verify job exists
        try:
            from routilux.server.dependencies import get_job_storage, get_runtime

            job_storage = get_job_storage()
            runtime = get_runtime()
            job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
        except Exception as e:
            logger.error(f"Error checking job {job_id}: {e}")
            await websocket.close(code=1011, reason="Internal error checking job")
            return

        if not job_context:
            await websocket.close(code=1008, reason=f"Job '{job_id}' not found")
            return

        if not await _check_websocket_auth(websocket):
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
        # MEDIUM fix: Validate flow_id format before processing
        if not flow_id or not isinstance(flow_id, str):
            await websocket.close(code=1008, reason="Invalid flow_id format")
            return
        if not re.match(r"^[a-zA-Z0-9_-]+$", flow_id):
            await websocket.close(code=1008, reason="Invalid flow_id format")
            return

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

        if not await _check_websocket_auth(websocket):
            return

        # Accept WebSocket connection
        await websocket.accept()
        logger.info(f"Flow WebSocket connection accepted for flow {flow_id}")

        # Get all jobs for this flow
        try:
            # Get jobs by flow_id from new storage
            from routilux.server.dependencies import get_job_storage

            job_storage = get_job_storage()
            jobs = job_storage.list_jobs(flow_id=flow_id)
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

        # MEDIUM fix: Ensure tasks are properly cleaned up on disconnect
        try:
            # Wait for all tasks (runs until WebSocket disconnects)
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            # Cancel all pending tasks to ensure cleanup
            for task in tasks:
                if not task.done():
                    task.cancel()
            # Wait for tasks to finish cancellation
            if tasks:
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


@router.websocket("/ws")
async def generic_websocket(websocket: WebSocket):
    """Generic WebSocket endpoint for subscribing to multiple jobs/flows.

    This endpoint allows clients to:
    - Connect without specifying a specific job/flow
    - Subscribe to multiple jobs via messages
    - Receive events from all subscribed jobs

    Client messages:
    - {"type": "subscribe", "job_id": "..."} - Subscribe to a job
    - {"type": "unsubscribe", "job_id": "..."} - Unsubscribe from a job
    - {"type": "ping"} - Keep-alive ping
    """
    event_manager = get_event_manager()
    subscribers: Dict[str, str] = {}  # job_id -> subscriber_id

    try:
        if not await _check_websocket_auth(websocket):
            return

        # Accept WebSocket connection
        await websocket.accept()
        logger.info("Generic WebSocket connection accepted")

        # Send welcome message
        await safe_send_json(
            websocket,
            {
                "type": "connected",
                "message": "Connected to generic WebSocket endpoint. Send subscribe messages to receive events.",
            },
            "welcome message",
        )

        # Handle both incoming messages and events
        async def message_handler():
            """Handle incoming client messages."""
            while True:
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_json(), timeout=WS_IDLE_TIMEOUT
                    )

                    msg_type = message.get("type")
                    job_id = message.get("job_id")

                    if msg_type == "subscribe" and job_id:
                        # Subscribe to a job
                        if job_id not in subscribers:
                            # Verify job exists
                            from routilux.server.dependencies import get_job_storage, get_runtime

                            job_storage = get_job_storage()
                            runtime = get_runtime()
                            job_context = job_storage.get_job(job_id) or runtime.get_job(job_id)
                            if not job_context:
                                await safe_send_json(
                                    websocket,
                                    {
                                        "type": "error",
                                        "message": f"Job '{job_id}' not found",
                                    },
                                    "error message",
                                )
                                continue

                            # Subscribe to job events
                            try:
                                subscriber_id = await event_manager.subscribe(job_id)
                                subscribers[job_id] = subscriber_id
                                logger.info(
                                    f"Generic WebSocket subscribed to job {job_id} as {subscriber_id}"
                                )
                                await safe_send_json(
                                    websocket,
                                    {
                                        "type": "subscribed",
                                        "job_id": job_id,
                                        "subscriber_id": subscriber_id,
                                    },
                                    "subscription confirmation",
                                )
                            except Exception as e:
                                logger.error(f"Error subscribing to job {job_id}: {e}")
                                await safe_send_json(
                                    websocket,
                                    {
                                        "type": "error",
                                        "message": f"Failed to subscribe to job '{job_id}': {e}",
                                    },
                                    "error message",
                                )
                        else:
                            await safe_send_json(
                                websocket,
                                {
                                    "type": "already_subscribed",
                                    "job_id": job_id,
                                },
                                "already subscribed",
                            )

                    elif msg_type == "unsubscribe" and job_id:
                        # Unsubscribe from a job
                        if job_id in subscribers:
                            subscriber_id = subscribers.pop(job_id)
                            try:
                                await event_manager.unsubscribe(subscriber_id)
                                logger.info(
                                    f"Generic WebSocket unsubscribed from job {job_id} ({subscriber_id})"
                                )
                                await safe_send_json(
                                    websocket,
                                    {
                                        "type": "unsubscribed",
                                        "job_id": job_id,
                                    },
                                    "unsubscription confirmation",
                                )
                            except Exception as e:
                                logger.error(f"Error unsubscribing from job {job_id}: {e}")
                        else:
                            await safe_send_json(
                                websocket,
                                {
                                    "type": "not_subscribed",
                                    "job_id": job_id,
                                },
                                "not subscribed",
                            )

                    elif msg_type == "pong":
                        # Handle pong response
                        pass

                    else:
                        logger.warning(f"Unknown message type from client: {msg_type}")

                except asyncio.TimeoutError:
                    # Send ping to keep connection alive
                    await safe_send_json(websocket, {"type": "ping"}, "ping")
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error(f"Error handling client message: {e}", exc_info=True)

        # Track event handler tasks
        event_tasks: Dict[str, asyncio.Task] = {}  # job_id -> task

        async def _handle_job_events(websocket: WebSocket, job_id: str, subscriber_id: str):
            """Handle events for a specific job."""
            try:
                async for event in event_manager.iter_events(subscriber_id):
                    # Add job_id to event if not present
                    if "job_id" not in event:
                        event["job_id"] = job_id

                    success = await safe_send_json(websocket, event, f"event for job {job_id}")
                    if not success:
                        logger.warning(
                            f"Failed to send event, removing subscription for job {job_id}"
                        )
                        break
            except asyncio.CancelledError:
                logger.debug(f"Event handler cancelled for job {job_id}")
            except Exception as e:
                logger.error(f"Error in event handler for job {job_id}: {e}")

        # Start message handler
        message_task = asyncio.create_task(message_handler())

        # Monitor subscribers and start/stop event handlers
        async def monitor_subscriptions():
            """Monitor subscribers and manage event handler tasks."""
            while True:
                try:
                    # Start event handlers for new subscriptions
                    for job_id, subscriber_id in subscribers.items():
                        if job_id not in event_tasks:
                            task = asyncio.create_task(
                                _handle_job_events(websocket, job_id, subscriber_id)
                            )
                            event_tasks[job_id] = task
                            logger.debug(f"Started event handler for job {job_id}")

                    # Stop event handlers for removed subscriptions
                    for job_id in list(event_tasks.keys()):
                        if job_id not in subscribers:
                            task = event_tasks.pop(job_id)
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                            logger.debug(f"Stopped event handler for job {job_id}")

                    await asyncio.sleep(0.5)  # Check every 500ms
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in subscription monitor: {e}")

        monitor_task = asyncio.create_task(monitor_subscriptions())

        # Wait for message handler to complete (disconnect)
        try:
            await message_task
        finally:
            # Cancel monitor and all event tasks
            monitor_task.cancel()
            for task in event_tasks.values():
                task.cancel()
            # Wait for cancellation
            await asyncio.gather(monitor_task, *event_tasks.values(), return_exceptions=True)

    except WebSocketDisconnect as e:
        logger.debug(f"Generic WebSocket disconnected: code={e.code}")
    except asyncio.CancelledError:
        logger.debug("Generic WebSocket task cancelled")
    except asyncio.TimeoutError:
        logger.warning("Generic WebSocket timeout")
    except Exception as e:
        logger.error(f"Unexpected error in generic WebSocket: {e}", exc_info=True)
    finally:
        # Unsubscribe from all jobs
        for job_id, subscriber_id in subscribers.items():
            try:
                await event_manager.unsubscribe(subscriber_id)
                logger.info(f"Generic WebSocket unsubscribed from job {job_id} ({subscriber_id})")
            except Exception as e:
                logger.error(f"Error unsubscribing from job {job_id}: {e}")
