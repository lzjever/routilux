"""
Global worker manager for managing all worker executions.

This module provides a singleton WorkerManager that manages:
- Global thread pool (shared by all workers)
- Running worker registry
- Worker lifecycle management
"""

from __future__ import annotations

import atexit
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from routilux.core.executor import WorkerExecutor
    from routilux.core.flow import Flow
    from routilux.core.worker import WorkerState

logger = logging.getLogger(__name__)

# Global instance
_global_worker_manager: Optional["WorkerManager"] = None
_global_worker_manager_lock = threading.Lock()


def _cleanup_global_worker_manager() -> None:
    """Cleanup function for atexit to ensure proper shutdown."""
    global _global_worker_manager
    if _global_worker_manager is not None:
        try:
            _global_worker_manager.shutdown(wait=False, timeout=0.0, fast_cleanup=True)
        except Exception:
            pass
        _global_worker_manager = None


# Register cleanup on exit
atexit.register(_cleanup_global_worker_manager)


class WorkerManager:
    """Global worker manager (singleton).

    Manages all worker executions with a shared thread pool.

    Attributes:
        max_workers: Maximum number of worker threads in global thread pool
        global_thread_pool: ThreadPoolExecutor shared by all workers
        running_workers: Dictionary of running worker executors keyed by worker_id
    """

    def __init__(self, max_workers: int = 100):
        """Initialize worker manager.

        Args:
            max_workers: Maximum number of worker threads in global thread pool
        """
        self.max_workers = max_workers
        self.global_thread_pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="RoutiluxWorker"
        )
        self.running_workers: Dict[str, "WorkerExecutor"] = {}
        self._lock = threading.Lock()
        self._shutdown = False

    def start_worker(
        self,
        flow: "Flow",
        timeout: Optional[float] = None,
        worker_state: Optional["WorkerState"] = None,
    ) -> "WorkerState":
        """Start a new worker execution.

        This method creates a WorkerExecutor and starts execution in the background.
        It returns immediately with a WorkerState that can be used to track progress.
        All routines start in IDLE state, waiting for jobs via Runtime.post().

        Args:
            flow: Flow to execute
            timeout: Execution timeout in seconds (None = use flow default)
            worker_state: Optional existing WorkerState (for resuming)

        Returns:
            WorkerState object (status will be RUNNING)

        Raises:
            RuntimeError: If manager is shut down
        """
        from routilux.core.executor import WorkerExecutor
        from routilux.core.worker import WorkerState as WorkerStateClass

        # Create or use provided WorkerState
        if worker_state is None:
            worker_state = WorkerStateClass(flow.flow_id)

        # Auto-register with global registry
        try:
            from routilux.core.registry import WorkerRegistry

            registry = WorkerRegistry.get_instance()
            registry.register(worker_state)
        except ImportError:
            pass

        # Use flow's timeout if not specified
        effective_timeout = timeout if timeout is not None else flow.execution_timeout

        # Create WorkerExecutor
        executor = WorkerExecutor(
            flow=flow,
            worker_state=worker_state,
            global_thread_pool=self.global_thread_pool,
            timeout=effective_timeout,
        )

        # Register and start
        with self._lock:
            if self._shutdown:
                raise RuntimeError("WorkerManager is shut down")
            self.running_workers[worker_state.worker_id] = executor

        # Start execution (non-blocking)
        executor.start()

        return worker_state

    def get_worker(self, worker_id: str) -> Optional["WorkerExecutor"]:
        """Get worker executor by worker_id.

        Args:
            worker_id: Worker identifier

        Returns:
            WorkerExecutor if found, None otherwise
        """
        with self._lock:
            return self.running_workers.get(worker_id)

    def stop_worker(self, worker_id: str, reason: str = "") -> bool:
        """Stop a running worker.

        Args:
            worker_id: Worker identifier
            reason: Reason for stopping

        Returns:
            True if worker was stopped, False if not found
        """
        with self._lock:
            executor = self.running_workers.get(worker_id)
            if executor is None:
                return False

            executor.cancel(reason=reason)
            del self.running_workers[worker_id]
            return True

    def list_workers(self) -> list[str]:
        """List all running worker IDs.

        Returns:
            List of worker IDs
        """
        with self._lock:
            return list(self.running_workers.keys())

    def get_worker_count(self) -> int:
        """Get count of running workers.

        Returns:
            Number of running workers
        """
        with self._lock:
            return len(self.running_workers)

    def shutdown(
        self,
        wait: bool = True,
        timeout: float = 30.0,
        fast_cleanup: bool = False,
    ) -> None:
        """Shutdown the worker manager.

        Args:
            wait: Whether to wait for workers to complete
            timeout: Timeout for waiting
            fast_cleanup: If True, skip waiting (for atexit cleanup)
        """
        with self._lock:
            self._shutdown = True
            workers_to_cancel = list(self.running_workers.items())

        # Cancel all workers
        for worker_id, executor in workers_to_cancel:
            try:
                executor.cancel(reason="Worker manager shutdown")
            except Exception as e:
                if not fast_cleanup:
                    logger.warning(f"Error cancelling worker {worker_id}: {e}")

        if wait and not fast_cleanup:
            # Wait for workers to finish
            start = time.time()
            while time.time() - start < timeout:
                with self._lock:
                    if not self.running_workers:
                        break
                time.sleep(0.1)

        # Clear running workers
        with self._lock:
            self.running_workers.clear()

        # Shutdown thread pool
        try:
            if fast_cleanup:
                # Fast cleanup: don't wait
                self.global_thread_pool.shutdown(wait=False, cancel_futures=True)
            else:
                self.global_thread_pool.shutdown(wait=wait)
        except Exception as e:
            if not fast_cleanup:
                logger.warning(f"Error shutting down thread pool: {e}")


def get_worker_manager() -> WorkerManager:
    """Get the global WorkerManager instance.

    Creates a new instance if one doesn't exist.

    Returns:
        Global WorkerManager instance
    """
    global _global_worker_manager
    if _global_worker_manager is None:
        with _global_worker_manager_lock:
            if _global_worker_manager is None:
                _global_worker_manager = WorkerManager()
    return _global_worker_manager


def reset_worker_manager() -> None:
    """Reset the global WorkerManager (for testing).

    Shuts down existing manager and clears the global reference.
    """
    global _global_worker_manager
    if _global_worker_manager is not None:
        with _global_worker_manager_lock:
            if _global_worker_manager is not None:
                try:
                    _global_worker_manager.shutdown(wait=True, timeout=5.0)
                except Exception:
                    pass
                _global_worker_manager = None
