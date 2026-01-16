"""
In-memory storage managers for flows, jobs, and debug sessions.

These stores are used by the FastAPI backend to manage flow and job state.
"""

import threading
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from routilux.flow.flow import Flow
    from routilux.job_state import JobState


class FlowStore:
    """In-memory flow storage.

    Thread-safe store for Flow objects.
    """

    def __init__(self):
        """Initialize flow store."""
        self._flows: Dict[str, Flow] = {}
        self._lock = threading.RLock()

    def get(self, flow_id: str) -> Optional["Flow"]:
        """Get flow by ID.

        Args:
            flow_id: Flow identifier.

        Returns:
            Flow object or None if not found.
        """
        with self._lock:
            return self._flows.get(flow_id)

    def add(self, flow: "Flow") -> None:
        """Add or update a flow.

        Args:
            flow: Flow object to store.
        """
        with self._lock:
            self._flows[flow.flow_id] = flow

    def remove(self, flow_id: str) -> None:
        """Remove a flow.

        Args:
            flow_id: Flow identifier.
        """
        with self._lock:
            self._flows.pop(flow_id, None)

    def list_all(self) -> List["Flow"]:
        """List all flows.

        Returns:
            List of all Flow objects.
        """
        with self._lock:
            return list(self._flows.values())

    def clear(self) -> None:
        """Clear all flows."""
        with self._lock:
            self._flows.clear()


class JobStore:
    """In-memory job storage.

    Thread-safe store for JobState objects.
    """

    def __init__(self):
        """Initialize job store."""
        self._jobs: Dict[str, JobState] = {}  # job_id -> JobState
        self._flow_jobs: Dict[str, List[str]] = {}  # flow_id -> [job_id, ...]
        self._lock = threading.RLock()

    def get(self, job_id: str) -> Optional["JobState"]:
        """Get job by ID.

        Args:
            job_id: Job identifier.

        Returns:
            JobState object or None if not found.
        """
        with self._lock:
            return self._jobs.get(job_id)

    def add(self, job_state: "JobState") -> None:
        """Add or update a job.

        Args:
            job_state: JobState object to store.
        """
        with self._lock:
            self._jobs[job_state.job_id] = job_state

            # Update flow_jobs mapping
            flow_id = job_state.flow_id
            if flow_id not in self._flow_jobs:
                self._flow_jobs[flow_id] = []
            if job_state.job_id not in self._flow_jobs[flow_id]:
                self._flow_jobs[flow_id].append(job_state.job_id)

    def remove(self, job_id: str) -> None:
        """Remove a job.

        Args:
            job_id: Job identifier.
        """
        with self._lock:
            job_state = self._jobs.pop(job_id, None)
            if job_state:
                flow_id = job_state.flow_id
                # Fix: Use exception handling to avoid TOCTOU race condition
                if flow_id in self._flow_jobs:
                    job_list = self._flow_jobs[flow_id]
                    # Use try-except to handle case where job_id removed by another thread
                    try:
                        job_list.remove(job_id)
                    except ValueError:
                        # job_id not in list - already removed by another thread
                        pass
                    # Clean up empty lists
                    if not job_list:
                        del self._flow_jobs[flow_id]

    def get_by_flow(self, flow_id: str) -> List["JobState"]:
        """Get all jobs for a flow.

        Args:
            flow_id: Flow identifier.

        Returns:
            List of JobState objects for the flow.
        """
        with self._lock:
            job_ids = self._flow_jobs.get(flow_id, [])
            return [self._jobs[jid] for jid in job_ids if jid in self._jobs]

    def list_all(self) -> List["JobState"]:
        """List all jobs.

        Returns:
            List of all JobState objects.
        """
        with self._lock:
            return list(self._jobs.values())

    def clear(self) -> None:
        """Clear all jobs."""
        with self._lock:
            self._jobs.clear()
            self._flow_jobs.clear()


# Global instances (used by API)
flow_store = FlowStore()
job_store = JobStore()
