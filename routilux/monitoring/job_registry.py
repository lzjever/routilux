"""
Global job registry for API discovery.

This registry tracks all JobState instances created in the system,
allowing the API to discover jobs started outside the API.
Uses weak references to avoid preventing garbage collection.
"""

import threading
import weakref
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from routilux.job_state import JobState


class JobRegistry:
    """Global registry for JobState instances.
    
    Thread-safe singleton that uses weak references to track JobState instances.
    Maintains flow_id to job_id mapping for efficient querying.
    """
    
    _instance: Optional["JobRegistry"] = None
    _lock = threading.Lock()
    
    def __init__(self):
        """Initialize registry (private - use get_instance())."""
        self._jobs: Dict[str, weakref.ref] = {}
        self._flow_jobs: Dict[str, List[str]] = {}  # flow_id -> [job_id, ...]
        self._lock = threading.RLock()
    
    @classmethod
    def get_instance(cls) -> "JobRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def register(self, job_state: "JobState") -> None:
        """Register a job state instance.
        
        Args:
            job_state: JobState instance to register.
        """
        if not hasattr(job_state, 'job_id') or not hasattr(job_state, 'flow_id'):
            raise TypeError("job_state must be a JobState instance with job_id and flow_id")
        
        with self._lock:
            def cleanup_callback(ref):
                """Callback when job is garbage collected."""
                with self._lock:
                    # Find job_id for this ref
                    job_id = None
                    for jid, r in list(self._jobs.items()):
                        if r is ref:
                            job_id = jid
                            break
                    if job_id:
                        self._jobs.pop(job_id, None)
                        # Clean up flow_jobs mapping
                        for flow_id, job_list in list(self._flow_jobs.items()):
                            if job_id in job_list:
                                job_list.remove(job_id)
                                if not job_list:
                                    self._flow_jobs.pop(flow_id, None)
            
            self._jobs[job_state.job_id] = weakref.ref(job_state, cleanup_callback)
            
            # Update flow_jobs mapping
            flow_id = job_state.flow_id
            if flow_id not in self._flow_jobs:
                self._flow_jobs[flow_id] = []
            if job_state.job_id not in self._flow_jobs[flow_id]:
                self._flow_jobs[flow_id].append(job_state.job_id)
    
    def get(self, job_id: str) -> Optional["JobState"]:
        """Get job by ID."""
        with self._lock:
            ref = self._jobs.get(job_id)
            if ref is None:
                return None
            job = ref()
            if job is None:
                self._jobs.pop(job_id, None)
            return job
    
    def get_by_flow(self, flow_id: str) -> List["JobState"]:
        """Get all jobs for a flow."""
        with self._lock:
            job_ids = self._flow_jobs.get(flow_id, [])
            jobs = []
            dead_job_ids = []
            
            for job_id in job_ids:
                ref = self._jobs.get(job_id)
                if ref is None:
                    dead_job_ids.append(job_id)
                    continue
                job = ref()
                if job is None:
                    dead_job_ids.append(job_id)
                    self._jobs.pop(job_id, None)
                else:
                    jobs.append(job)
            
            # Clean up dead references
            for job_id in dead_job_ids:
                if flow_id in self._flow_jobs:
                    try:
                        self._flow_jobs[flow_id].remove(job_id)
                    except ValueError:
                        pass
                if not self._flow_jobs.get(flow_id):
                    self._flow_jobs.pop(flow_id, None)
            
            return jobs
    
    def list_all(self) -> List["JobState"]:
        """List all registered jobs."""
        with self._lock:
            jobs = []
            dead_job_ids = []
            
            for job_id, ref in self._jobs.items():
                job = ref()
                if job is None:
                    dead_job_ids.append(job_id)
                else:
                    jobs.append(job)
            
            # Clean up
            for job_id in dead_job_ids:
                self._jobs.pop(job_id, None)
                # Also clean up flow_jobs mapping
                for flow_id, job_list in list(self._flow_jobs.items()):
                    if job_id in job_list:
                        job_list.remove(job_id)
                        if not job_list:
                            self._flow_jobs.pop(flow_id, None)
            
            return jobs
    
    def clear(self) -> None:
        """Clear all registered jobs (for testing only)."""
        with self._lock:
            self._jobs.clear()
            self._flow_jobs.clear()
