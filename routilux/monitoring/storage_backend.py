"""
Storage backend abstraction for flow and job persistence.

Provides an abstract base class for storage backends, allowing
switching between in-memory and persistent storage (e.g., SQLite).
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from routilux.flow.flow import Flow
    from routilux.job_state import JobState


class StorageBackend(ABC):
    """Abstract base class for storage backends."""
    
    @abstractmethod
    def get_flow(self, flow_id: str) -> Optional["Flow"]:
        """Get flow by ID."""
        pass
    
    @abstractmethod
    def add_flow(self, flow: "Flow") -> None:
        """Add or update a flow."""
        pass
    
    @abstractmethod
    def remove_flow(self, flow_id: str) -> None:
        """Remove a flow."""
        pass
    
    @abstractmethod
    def list_flows(self) -> List["Flow"]:
        """List all flows."""
        pass
    
    @abstractmethod
    def get_job(self, job_id: str) -> Optional["JobState"]:
        """Get job by ID."""
        pass
    
    @abstractmethod
    def add_job(self, job_state: "JobState") -> None:
        """Add or update a job."""
        pass
    
    @abstractmethod
    def remove_job(self, job_id: str) -> None:
        """Remove a job."""
        pass
    
    @abstractmethod
    def list_jobs(self) -> List["JobState"]:
        """List all jobs."""
        pass
    
    @abstractmethod
    def get_jobs_by_flow(self, flow_id: str) -> List["JobState"]:
        """Get all jobs for a flow."""
        pass


class InMemoryBackend(StorageBackend):
    """In-memory storage backend (default).
    
    This is a wrapper around the existing FlowStore and JobStore
    to provide the StorageBackend interface.
    """
    
    def __init__(self):
        """Initialize in-memory backend."""
        from routilux.monitoring.storage import flow_store, job_store
        self._flow_store = flow_store
        self._job_store = job_store
    
    def get_flow(self, flow_id: str) -> Optional["Flow"]:
        """Get flow by ID."""
        return self._flow_store.get(flow_id)
    
    def add_flow(self, flow: "Flow") -> None:
        """Add or update a flow."""
        self._flow_store.add(flow)
    
    def remove_flow(self, flow_id: str) -> None:
        """Remove a flow."""
        self._flow_store.remove(flow_id)
    
    def list_flows(self) -> List["Flow"]:
        """List all flows."""
        return self._flow_store.list_all()
    
    def get_job(self, job_id: str) -> Optional["JobState"]:
        """Get job by ID."""
        return self._job_store.get(job_id)
    
    def add_job(self, job_state: "JobState") -> None:
        """Add or update a job."""
        self._job_store.add(job_state)
    
    def remove_job(self, job_id: str) -> None:
        """Remove a job."""
        self._job_store.remove(job_id)
    
    def list_jobs(self) -> List["JobState"]:
        """List all jobs."""
        return self._job_store.list_all()
    
    def get_jobs_by_flow(self, flow_id: str) -> List["JobState"]:
        """Get all jobs for a flow."""
        return self._job_store.get_by_flow(flow_id)


# Global backend instance (defaults to in-memory)
_backend: Optional[StorageBackend] = None


def get_backend() -> StorageBackend:
    """Get global storage backend instance.
    
    Returns:
        StorageBackend instance (defaults to InMemoryBackend).
    """
    global _backend
    if _backend is None:
        # Check if SQLite backend is requested
        import os
        storage_backend = os.getenv("ROUTILUX_STORAGE_BACKEND", "memory")
        
        if storage_backend == "sqlite":
            # SQLite backend will be implemented in a separate module
            # For now, fall back to in-memory
            _backend = InMemoryBackend()
        else:
            _backend = InMemoryBackend()
    
    return _backend
