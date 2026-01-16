"""
Global job manager for managing all job executions.

This module provides a singleton GlobalJobManager that manages:
- Global thread pool (shared by all jobs)
- Running job registry
- Job lifecycle management
"""

import atexit
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from routilux.flow.flow import Flow
    from routilux.job_executor import JobExecutor
    from routilux.job_state import JobState

logger = logging.getLogger(__name__)

# Global instance
_global_job_manager: Optional["GlobalJobManager"] = None
_global_job_manager_lock = threading.Lock()


def _cleanup_global_job_manager() -> None:
    """Cleanup function for atexit to ensure proper shutdown."""
    global _global_job_manager
    if _global_job_manager is not None:
        try:
            _global_job_manager.shutdown(wait=False, timeout=1.0)
        except Exception:
            pass  # Ignore errors during cleanup
        _global_job_manager = None


# Register cleanup on exit
atexit.register(_cleanup_global_job_manager)


class GlobalJobManager:
    """Global job manager (singleton).

    Manages all job executions with a shared thread pool.

    Attributes:
        max_workers: Maximum number of worker threads in global thread pool.
        global_thread_pool: ThreadPoolExecutor shared by all jobs.
        running_jobs: Dictionary of running job executors keyed by job_id.
    """

    def __init__(self, max_workers: int = 100):
        """Initialize global job manager.

        Args:
            max_workers: Maximum number of worker threads in global thread pool.
        """
        self.max_workers = max_workers
        self.global_thread_pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="RoutiluxWorker"
        )
        self.running_jobs: Dict[str, "JobExecutor"] = {}
        self._lock = threading.Lock()
        self._shutdown = False

    def start_job(
        self,
        flow: "Flow",
        entry_routine_id: str,
        entry_params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        job_state: Optional["JobState"] = None,
    ) -> "JobState":
        """Start a new job execution.

        This method creates a JobExecutor and starts execution in the background.
        It returns immediately with a JobState that can be used to track progress.

        Args:
            flow: Flow to execute.
            entry_routine_id: Entry routine identifier.
            entry_params: Entry parameters passed to the entry routine's trigger slot.
            timeout: Execution timeout in seconds. If None, uses flow's default timeout.
            job_state: Optional existing JobState to use (for resuming execution).

        Returns:
            JobState object. Status will be RUNNING after this call.

        Raises:
            RuntimeError: If manager is shut down.
            ValueError: If entry_routine_id not found in flow.
        """
        # Critical fix: Validate before creating executor to avoid TOCTOU race condition
        if entry_routine_id not in flow.routines:
            raise ValueError(f"Entry routine '{entry_routine_id}' not found in flow")

        from routilux.job_executor import JobExecutor
        from routilux.job_state import JobState as JobStateClass

        # Create or use provided JobState
        if job_state is None:
            job_state = JobStateClass(flow.flow_id)

        # Auto-register job with global registry if monitoring is enabled
        # This allows the API to discover jobs started outside the API
        try:
            from routilux.monitoring.registry import MonitoringRegistry
            from routilux.monitoring.job_registry import JobRegistry

            if MonitoringRegistry.is_enabled():
                registry = JobRegistry.get_instance()
                registry.register(job_state)
        except ImportError:
            # Monitoring module not available, skip registration
            # This ensures core functionality works without API dependencies
            pass

        # Use flow's timeout if not specified
        effective_timeout = timeout if timeout is not None else flow.execution_timeout

        # Create JobExecutor
        executor = JobExecutor(
            flow=flow,
            job_state=job_state,
            global_thread_pool=self.global_thread_pool,
            timeout=effective_timeout,
        )

        # Critical fix: Extend lock scope to prevent TOCTOU race condition
        # between shutdown check and job registration
        with self._lock:
            if self._shutdown:
                raise RuntimeError("GlobalJobManager is shut down")
            self.running_jobs[job_state.job_id] = executor

        # Start execution (non-blocking)
        executor.start(entry_routine_id, entry_params or {})

        return job_state

    def get_job(self, job_id: str) -> Optional["JobExecutor"]:
        """Get job executor by job_id.

        Args:
            job_id: Job identifier.

        Returns:
            JobExecutor if found, None otherwise.
        """
        with self._lock:
            return self.running_jobs.get(job_id)

    def remove_job(self, job_id: str) -> None:
        """Remove job from running jobs registry.

        This is called by JobExecutor when job completes.

        Args:
            job_id: Job identifier to remove.
        """
        with self._lock:
            self.running_jobs.pop(job_id, None)

    def list_jobs(self) -> list[str]:
        """List all running job IDs.

        Returns:
            List of job IDs.
        """
        with self._lock:
            return list(self.running_jobs.keys())

    def wait_for_job(self, job_id: str, timeout: float | None = None) -> bool:
        """Wait for a specific job to complete.

        Args:
            job_id: Job identifier.
            timeout: Maximum time to wait in seconds. None for infinite wait.

        Returns:
            True if job completed, False if timeout or job not found.
        """
        start_time = time.time()

        while True:
            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return False

            # Check if job exists and is running
            executor = self.get_job(job_id)
            if executor is None:
                # Job not found (either never existed or already completed)
                return True

            if not executor.is_running():
                return True

            time.sleep(0.05)

    def wait_for_all_jobs(self, timeout: float | None = None) -> bool:
        """Wait for all running jobs to complete.

        Args:
            timeout: Maximum time to wait in seconds. None for infinite wait.

        Returns:
            True if all jobs completed, False if timeout.
        """
        start_time = time.time()

        while True:
            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return False

            # Check if all jobs are done
            with self._lock:
                running = [
                    job_id for job_id, executor in self.running_jobs.items()
                    if executor.is_running()
                ]

            if not running:
                return True

            time.sleep(0.05)

    def shutdown(self, wait: bool = True, timeout: float | None = None) -> None:
        """Shutdown global job manager.

        This stops all running jobs and shuts down the thread pool.

        Args:
            wait: Whether to wait for jobs to complete.
            timeout: Wait timeout in seconds (only used if wait=True).
        """
        with self._lock:
            if self._shutdown:
                return

            self._shutdown = True

            # Stop all running jobs
            for executor in list(self.running_jobs.values()):
                executor.stop()

            self.running_jobs.clear()

        # Shutdown thread pool
        if wait:
            self.global_thread_pool.shutdown(wait=True)
        else:
            self.global_thread_pool.shutdown(wait=False)

        logger.info("GlobalJobManager shut down")

    def is_shutdown(self) -> bool:
        """Check if manager is shut down.

        Returns:
            True if shut down, False otherwise.
        """
        return self._shutdown


def get_job_manager(max_workers: int = 100) -> GlobalJobManager:
    """Get or create global job manager instance.

    This is the main entry point for getting the GlobalJobManager.
    The first call creates the singleton instance, subsequent calls
    return the same instance (ignoring max_workers parameter).

    Args:
        max_workers: Maximum workers (only used on first call).

    Returns:
        GlobalJobManager singleton instance.
    """
    global _global_job_manager

    if _global_job_manager is None:
        with _global_job_manager_lock:
            if _global_job_manager is None:
                _global_job_manager = GlobalJobManager(max_workers=max_workers)
                logger.info(f"Created GlobalJobManager with {max_workers} workers")

    return _global_job_manager


def reset_job_manager() -> None:
    """Reset global job manager (for testing only).

    This shuts down the current manager and clears the singleton.
    Should only be used in tests to ensure clean state.
    """
    global _global_job_manager

    with _global_job_manager_lock:
        if _global_job_manager is not None:
            _global_job_manager.shutdown(wait=True)
            _global_job_manager = None
            logger.info("Reset GlobalJobManager")
