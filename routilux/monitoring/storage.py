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
        
        First checks local store, then falls back to global registry.
        This allows the API to discover flows created outside the API.

        Args:
            flow_id: Flow identifier.

        Returns:
            Flow object or None if not found.
        """
        with self._lock:
            # First check local store
            flow = self._flows.get(flow_id)
            if flow is not None:
                return flow
            
            # Fall back to global registry
            try:
                from routilux.monitoring.flow_registry import FlowRegistry
                registry = FlowRegistry.get_instance()
                flow = registry.get(flow_id)
                if flow is not None:
                    # Auto-add to local store for future queries
                    self._flows[flow_id] = flow
                return flow
            except ImportError:
                # Registry not available, return None
                return None

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
        
        Combines local store and global registry.
        This allows the API to discover flows created outside the API.

        Returns:
            List of all Flow objects.
        """
        with self._lock:
            local_flows = list(self._flows.values())
            
            # Also get flows from global registry
            try:
                from routilux.monitoring.flow_registry import FlowRegistry
                registry = FlowRegistry.get_instance()
                registry_flows = registry.list_all()
                
                # Merge (avoid duplicates)
                flow_ids = {f.flow_id for f in local_flows}
                for flow in registry_flows:
                    if flow.flow_id not in flow_ids:
                        local_flows.append(flow)
                        self._flows[flow.flow_id] = flow  # Cache in local store
            except ImportError:
                # Registry not available, return local flows only
                pass
            
            return local_flows

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
        
        First checks local store, then falls back to global registry.
        This allows the API to discover jobs started outside the API.

        Args:
            job_id: Job identifier.

        Returns:
            JobState object or None if not found.
        """
        with self._lock:
            # First check local store
            job = self._jobs.get(job_id)
            if job is not None:
                return job
            
            # Fall back to global registry
            try:
                from routilux.monitoring.job_registry import JobRegistry
                registry = JobRegistry.get_instance()
                job = registry.get(job_id)
                if job is not None:
                    # Auto-add to local store for future queries
                    self._jobs[job.job_id] = job
                    # Update flow_jobs mapping
                    flow_id = job.flow_id
                    if flow_id not in self._flow_jobs:
                        self._flow_jobs[flow_id] = []
                    if job.job_id not in self._flow_jobs[flow_id]:
                        self._flow_jobs[flow_id].append(job.job_id)
                return job
            except ImportError:
                # Registry not available, return None
                return None

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
        
        Combines local store and global registry.
        This allows the API to discover jobs started outside the API.

        Args:
            flow_id: Flow identifier.

        Returns:
            List of JobState objects for the flow.
        """
        with self._lock:
            # Get from local store
            local_job_ids = self._flow_jobs.get(flow_id, [])
            local_jobs = [self._jobs[jid] for jid in local_job_ids if jid in self._jobs]
            
            # Also get from global registry
            try:
                from routilux.monitoring.job_registry import JobRegistry
                registry = JobRegistry.get_instance()
                registry_jobs = registry.get_by_flow(flow_id)
                
                # Merge (avoid duplicates)
                job_ids = {j.job_id for j in local_jobs}
                for job in registry_jobs:
                    if job.job_id not in job_ids:
                        local_jobs.append(job)
                        # Cache in local store
                        self._jobs[job.job_id] = job
                        if flow_id not in self._flow_jobs:
                            self._flow_jobs[flow_id] = []
                        if job.job_id not in self._flow_jobs[flow_id]:
                            self._flow_jobs[flow_id].append(job.job_id)
            except ImportError:
                # Registry not available, return local jobs only
                pass
            
            return local_jobs

    def list_all(self) -> List["JobState"]:
        """List all jobs.
        
        Combines local store and global registry.
        This allows the API to discover jobs started outside the API.

        Returns:
            List of all JobState objects.
        """
        with self._lock:
            local_jobs = list(self._jobs.values())
            
            # Also get jobs from global registry
            try:
                from routilux.monitoring.job_registry import JobRegistry
                registry = JobRegistry.get_instance()
                registry_jobs = registry.list_all()
                
                # Merge (avoid duplicates)
                job_ids = {j.job_id for j in local_jobs}
                for job in registry_jobs:
                    if job.job_id not in job_ids:
                        local_jobs.append(job)
                        # Cache in local store
                        self._jobs[job.job_id] = job
                        # Update flow_jobs mapping
                        flow_id = job.flow_id
                        if flow_id not in self._flow_jobs:
                            self._flow_jobs[flow_id] = []
                        if job.job_id not in self._flow_jobs[flow_id]:
                            self._flow_jobs[flow_id].append(job.job_id)
            except ImportError:
                # Registry not available, return local jobs only
                pass
            
            return local_jobs

    def clear(self) -> None:
        """Clear all jobs."""
        with self._lock:
            self._jobs.clear()
            self._flow_jobs.clear()
    
    def cleanup_old_jobs(
        self,
        max_age_seconds: int = 86400,  # 24 hours
        status_filter: Optional[List[str]] = None,
    ) -> int:
        """Remove old jobs based on age and status.
        
        Args:
            max_age_seconds: Maximum age in seconds (default: 24 hours).
            status_filter: List of statuses to clean up (None = all).
            
        Returns:
            Number of jobs removed.
        """
        from datetime import datetime, timedelta
        
        cutoff_time = datetime.now() - timedelta(seconds=max_age_seconds)
        removed_count = 0
        
        with self._lock:
            jobs_to_remove = []
            
            for job_id, job_state in list(self._jobs.items()):
                # Check age
                created_at = getattr(job_state, "created_at", None)
                if created_at and created_at < cutoff_time:
                    # Check status filter
                    if status_filter is None or str(job_state.status) in status_filter:
                        jobs_to_remove.append(job_id)
            
            # Remove jobs
            for job_id in jobs_to_remove:
                self.remove(job_id)
                removed_count += 1
        
        return removed_count


# Global instances (used by API)
flow_store = FlowStore()
job_store = JobStore()
