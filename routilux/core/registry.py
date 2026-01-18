"""
Global registries for Flow and Worker instances.

These registries track all Flow and WorkerState instances created in the system,
allowing discovery of instances created outside the API.
Uses weak references to avoid preventing garbage collection.
"""

from __future__ import annotations

import logging
import threading
import time
import weakref
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from routilux.core.flow import Flow
    from routilux.core.worker import WorkerState

logger = logging.getLogger(__name__)


class FlowRegistry:
    """Global registry for Flow instances.

    Thread-safe singleton that uses weak references to track Flow instances.
    Automatically cleans up dead references when flows are garbage collected.

    Usage:
        >>> registry = FlowRegistry.get_instance()
        >>> registry.register_by_name("my_flow", flow)
        >>> flow = registry.get_by_name("my_flow")
    """

    _instance: FlowRegistry | None = None
    _lock = threading.Lock()

    def __init__(self):
        """Initialize registry (private - use get_instance())."""
        self._flows: dict[str, weakref.ref] = {}  # flow_id -> weakref
        self._named_flows: dict[str, Flow] = {}  # name -> Flow (strong reference)
        self._lock: threading.RLock = threading.RLock()

    @classmethod
    def get_instance(cls) -> FlowRegistry:
        """Get singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(self, flow: Flow) -> None:
        """Register a flow instance (weak reference).

        Args:
            flow: Flow instance to register
        """
        if not hasattr(flow, "flow_id"):
            raise TypeError("flow must have flow_id attribute")

        with self._lock:

            def cleanup_callback(ref):
                """Callback when flow is garbage collected."""
                with self._lock:
                    flow_id = None
                    for fid, r in list(self._flows.items()):
                        if r is ref:
                            flow_id = fid
                            break
                    if flow_id:
                        self._flows.pop(flow_id, None)

            self._flows[flow.flow_id] = weakref.ref(flow, cleanup_callback)

    def get(self, flow_id: str) -> Flow | None:
        """Get flow by ID.

        Args:
            flow_id: Flow identifier

        Returns:
            Flow if found and alive, None otherwise
        """
        with self._lock:
            ref = self._flows.get(flow_id)
            if ref is None:
                return None
            flow = ref()
            if flow is None:
                self._flows.pop(flow_id, None)
            return flow

    def list_all(self) -> list[Flow]:
        """List all registered flows (alive ones only)."""
        with self._lock:
            flows = []
            dead_flow_ids = []

            for flow_id, ref in self._flows.items():
                flow = ref()
                if flow is None:
                    dead_flow_ids.append(flow_id)
                else:
                    flows.append(flow)

            for flow_id in dead_flow_ids:
                self._flows.pop(flow_id, None)

            return flows

    def register_by_name(self, name: str, flow: Flow) -> None:
        """Register a flow by name (strong reference).

        This creates a strong reference, so the flow won't be
        garbage collected. Use for flows that should be available
        by name for execution.

        Args:
            name: Unique name for the flow
            flow: Flow instance

        Raises:
            ValueError: If name is already registered
        """
        if not hasattr(flow, "flow_id"):
            raise TypeError("flow must have flow_id attribute")

        with self._lock:
            if name in self._named_flows:
                raise ValueError(f"Flow name '{name}' is already registered")

            self._named_flows[name] = flow
            self.register(flow)

    def get_by_name(self, name: str) -> Flow | None:
        """Get flow by name.

        Args:
            name: Flow name

        Returns:
            Flow if found, None otherwise
        """
        with self._lock:
            return self._named_flows.get(name)

    def unregister_by_name(self, name: str) -> bool:
        """Unregister a flow by name.

        Args:
            name: Flow name

        Returns:
            True if unregistered, False if not found
        """
        with self._lock:
            if name in self._named_flows:
                del self._named_flows[name]
                return True
            return False

    def clear(self) -> None:
        """Clear all registered flows (for testing)."""
        with self._lock:
            self._flows.clear()
            self._named_flows.clear()


class WorkerRegistry:
    """Global registry for WorkerState instances.

    Thread-safe singleton that uses weak references to track WorkerState instances.
    Maintains flow_id to worker_id mapping for efficient querying.

    Usage:
        >>> registry = WorkerRegistry.get_instance()
        >>> registry.register(worker_state)
        >>> workers = registry.get_by_flow("my_flow")
    """

    _instance: WorkerRegistry | None = None
    _lock = threading.Lock()

    def __init__(self):
        """Initialize registry (private - use get_instance())."""
        self._workers: dict[str, weakref.ref] = {}  # worker_id -> weakref
        self._flow_workers: dict[str, list[str]] = {}  # flow_id -> [worker_id, ...]
        self._lock: threading.RLock = threading.RLock()
        self._gc_cleanup_lock: threading.Lock = threading.Lock()
        self._cleanup_queue: list[str] = []
        self._cleanup_queue_lock: threading.Lock = threading.Lock()

        # Completed workers tracking for automatic cleanup
        self._completed_workers: dict[str, datetime] = {}  # worker_id -> completed_at
        self._cleanup_interval: float = 600.0  # 10 minutes
        self._cleanup_thread: threading.Thread | None = None
        self._cleanup_running: bool = False
        self._cleanup_thread_lock: threading.Lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> WorkerRegistry:
        """Get singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(self, worker_state: WorkerState) -> None:
        """Register a worker state instance.

        Args:
            worker_state: WorkerState instance
        """
        if not hasattr(worker_state, "worker_id") or not hasattr(worker_state, "flow_id"):
            raise TypeError("worker_state must have worker_id and flow_id attributes")

        with self._lock:

            def cleanup_callback(ref):
                """Callback when worker is garbage collected."""
                worker_id = None
                for wid, r in list(self._workers.items()):
                    if r is ref:
                        worker_id = wid
                        break

                if worker_id:
                    with self._cleanup_queue_lock:
                        self._cleanup_queue.append(worker_id)
                    self._process_cleanup_queue()

            self._workers[worker_state.worker_id] = weakref.ref(worker_state, cleanup_callback)

            flow_id = worker_state.flow_id
            if flow_id not in self._flow_workers:
                self._flow_workers[flow_id] = []
            self._flow_workers[flow_id].append(worker_state.worker_id)

            self._start_cleanup_thread()

    def _process_cleanup_queue(self) -> None:
        """Process queued cleanup operations (non-blocking)."""
        if self._gc_cleanup_lock.acquire(blocking=False):
            try:
                with self._cleanup_queue_lock:
                    worker_ids_to_clean = self._cleanup_queue.copy()
                    self._cleanup_queue.clear()

                with self._lock:
                    for worker_id in worker_ids_to_clean:
                        self._workers.pop(worker_id, None)
                        for flow_id, worker_list in list(self._flow_workers.items()):
                            if worker_id in worker_list:
                                worker_list.remove(worker_id)
                                if not worker_list:
                                    self._flow_workers.pop(flow_id, None)
            finally:
                self._gc_cleanup_lock.release()

    def get(self, worker_id: str) -> WorkerState | None:
        """Get worker by ID."""
        with self._lock:
            ref = self._workers.get(worker_id)
            if ref is None:
                return None
            worker = ref()
            if worker is None:
                self._workers.pop(worker_id, None)
            return worker

    def get_by_flow(self, flow_id: str) -> list[WorkerState]:
        """Get all workers for a flow."""
        with self._lock:
            worker_ids = self._flow_workers.get(flow_id, [])
            workers = []
            dead_worker_ids = []

            for worker_id in worker_ids:
                ref = self._workers.get(worker_id)
                if ref is None:
                    dead_worker_ids.append(worker_id)
                    continue
                worker = ref()
                if worker is None:
                    dead_worker_ids.append(worker_id)
                    self._workers.pop(worker_id, None)
                else:
                    workers.append(worker)

            for worker_id in dead_worker_ids:
                if flow_id in self._flow_workers:
                    try:
                        self._flow_workers[flow_id].remove(worker_id)
                    except ValueError:
                        pass
                if not self._flow_workers.get(flow_id):
                    self._flow_workers.pop(flow_id, None)

            return workers

    def list_all(self) -> list[WorkerState]:
        """List all registered workers."""
        with self._lock:
            workers = []
            dead_worker_ids = []

            for worker_id, ref in self._workers.items():
                worker = ref()
                if worker is None:
                    dead_worker_ids.append(worker_id)
                else:
                    workers.append(worker)

            for worker_id in dead_worker_ids:
                self._workers.pop(worker_id, None)
                for flow_id, worker_list in list(self._flow_workers.items()):
                    if worker_id in worker_list:
                        worker_list.remove(worker_id)
                        if not worker_list:
                            self._flow_workers.pop(flow_id, None)

            return workers

    def mark_completed(self, worker_id: str) -> None:
        """Mark a worker as completed for cleanup tracking."""
        with self._lock:
            self._completed_workers[worker_id] = datetime.now()
            logger.debug(f"Marked worker {worker_id} as completed for cleanup tracking")

    def _start_cleanup_thread(self) -> None:
        """Start the cleanup thread if not already running."""
        with self._cleanup_thread_lock:
            if self._cleanup_running:
                return
            self._cleanup_running = True
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop, daemon=True, name="WorkerRegistryCleanup"
            )
            self._cleanup_thread.start()
            logger.debug("Started WorkerRegistry cleanup thread")

    def _cleanup_loop(self) -> None:
        """Background thread loop for cleaning up completed workers."""
        while self._cleanup_running:
            try:
                time.sleep(self._cleanup_interval)
                self._cleanup_completed_workers()
            except Exception as e:
                logger.exception(f"Error in cleanup loop: {e}")

    def _cleanup_completed_workers(self) -> None:
        """Clean up completed workers that have exceeded retention period."""
        now = datetime.now()
        cutoff_time = now - timedelta(seconds=self._cleanup_interval)

        with self._lock:
            workers_to_remove = []
            for worker_id, completed_at in self._completed_workers.items():
                try:
                    if not isinstance(completed_at, datetime):
                        logger.warning(f"Invalid completed_at for worker {worker_id}, removing")
                        workers_to_remove.append(worker_id)
                        continue
                    if completed_at < cutoff_time:
                        workers_to_remove.append(worker_id)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Error comparing completed_at for worker {worker_id}: {e}")
                    workers_to_remove.append(worker_id)

            for worker_id in workers_to_remove:
                self._workers.pop(worker_id, None)
                self._completed_workers.pop(worker_id, None)

                for flow_id, worker_list in list(self._flow_workers.items()):
                    if worker_id in worker_list:
                        worker_list.remove(worker_id)
                        if not worker_list:
                            self._flow_workers.pop(flow_id, None)

            if workers_to_remove:
                logger.debug(f"Cleaned up {len(workers_to_remove)} completed workers")

    def clear(self) -> None:
        """Clear all registered workers (for testing)."""
        with self._lock:
            self._workers.clear()
            self._flow_workers.clear()
            self._completed_workers.clear()

        with self._cleanup_thread_lock:
            self._cleanup_running = False


# Convenience functions
def get_flow_registry() -> FlowRegistry:
    """Get the global FlowRegistry instance."""
    return FlowRegistry.get_instance()


def get_worker_registry() -> WorkerRegistry:
    """Get the global WorkerRegistry instance."""
    return WorkerRegistry.get_instance()
