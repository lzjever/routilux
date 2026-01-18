"""
In-memory storage backends for Routilux API.

These are suitable for development and testing.
For production, implement persistent backends.
"""

import threading
import time
from typing import Any, Dict, List, Optional

from routilux.core.context import JobContext


class MemoryJobStorage:
    """In-memory job storage for development/testing.

    Thread-safe implementation using RLock.
    Falls back to Runtime for jobs created outside the API.
    """

    def __init__(self):
        self._jobs: Dict[str, JobContext] = {}
        # Note: _job_flow_map removed - JobContext now contains flow_id directly
        self._lock = threading.RLock()

    def save_job(self, job: JobContext, flow_id: Optional[str] = None) -> None:
        """Save or update a job.

        Args:
            job: JobContext to save
            flow_id: Optional flow_id to associate with job
        """
        with self._lock:
            self._jobs[job.job_id] = job
            # Note: flow_id parameter kept for backward compatibility but ignored
            # JobContext now contains flow_id directly

    def get_job(self, job_id: str) -> Optional[JobContext]:
        """Get job by ID.

        First checks local storage, then falls back to Runtime.

        Args:
            job_id: Job identifier

        Returns:
            JobContext if found, None otherwise
        """
        with self._lock:
            # Check local storage first
            if job_id in self._jobs:
                return self._jobs[job_id]

        # Fall back to Runtime (for jobs created outside API)
        try:
            from routilux.monitoring.runtime_registry import RuntimeRegistry

            registry = RuntimeRegistry.get_instance()
            for runtime in registry.get_all().values():
                job = runtime.get_job(job_id)
                if job:
                    # Cache it
                    with self._lock:
                        self._jobs[job_id] = job
                    return job
        except Exception:
            pass

        return None

    def delete_job(self, job_id: str) -> bool:
        """Delete a job.

        Args:
            job_id: Job identifier

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False

    def list_jobs(
        self,
        worker_id: Optional[str] = None,
        flow_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[JobContext]:
        """List jobs with optional filters.

        Args:
            worker_id: Filter by worker ID
            flow_id: Filter by flow ID (uses job_flow_map)
            status: Filter by status
            limit: Maximum results
            offset: Skip first N results

        Returns:
            List of matching JobContext objects
        """
        # First sync with Runtime
        self._sync_from_runtime()

        with self._lock:
            jobs = list(self._jobs.values())

            # Apply filters
            if worker_id:
                jobs = [j for j in jobs if j.worker_id == worker_id]

            if flow_id:
                # JobContext now contains flow_id directly
                jobs = [j for j in jobs if j.flow_id == flow_id]

            if status:
                jobs = [j for j in jobs if j.status == status]

            # Sort by created_at descending
            jobs.sort(key=lambda j: j.created_at, reverse=True)

            # Apply pagination
            return jobs[offset : offset + limit]

    def count_jobs(
        self,
        worker_id: Optional[str] = None,
        flow_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        """Count jobs matching filters.

        Args:
            worker_id: Filter by worker ID
            flow_id: Filter by flow ID
            status: Filter by status

        Returns:
            Count of matching jobs
        """
        # First sync with Runtime
        self._sync_from_runtime()

        with self._lock:
            jobs = list(self._jobs.values())

            if worker_id:
                jobs = [j for j in jobs if j.worker_id == worker_id]

            if flow_id:
                # JobContext now contains flow_id directly
                jobs = [j for j in jobs if j.flow_id == flow_id]

            if status:
                jobs = [j for j in jobs if j.status == status]

            return len(jobs)

    def get_flow_id(self, job_id: str) -> Optional[str]:
        """Get flow_id for a job.

        Args:
            job_id: Job identifier

        Returns:
            Flow ID if known, None otherwise
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                return job.flow_id
            # Try Runtime
            try:
                from routilux.monitoring.runtime_registry import RuntimeRegistry

                registry = RuntimeRegistry.get_instance()
                for runtime in registry.get_all().values():
                    job = runtime.get_job(job_id)
                    if job:
                        return job.flow_id
            except Exception:
                pass
            return None

    def _sync_from_runtime(self) -> None:
        """Sync jobs from Runtime to local storage."""
        try:
            from routilux.monitoring.runtime_registry import RuntimeRegistry

            registry = RuntimeRegistry.get_instance()

            for runtime in registry.get_all().values():
                for job in runtime.list_jobs():
                    with self._lock:
                        if job.job_id not in self._jobs:
                            self._jobs[job.job_id] = job
        except Exception:
            pass

    def clear(self) -> None:
        """Clear all jobs (for testing)."""
        with self._lock:
            self._jobs.clear()


class MemoryIdempotencyBackend:
    """In-memory idempotency key storage.

    Thread-safe implementation with TTL support.
    For production, use Redis or similar.
    """

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}  # key -> {response, expires_at}
        self._lock = threading.RLock()

    def check_and_set(
        self, key: str, response: Optional[Dict[str, Any]], ttl_seconds: int = 86400
    ) -> Optional[Dict[str, Any]]:
        """Check if key exists and optionally set response.

        Args:
            key: Idempotency key
            response: Response to cache
            ttl_seconds: Time-to-live in seconds

        Returns:
            Cached response if key existed, None otherwise
        """
        with self._lock:
            # Clean expired entries
            self._cleanup_expired()

            # Check if key exists
            if key in self._cache:
                entry = self._cache[key]
                if entry["expires_at"] > time.time():
                    return entry.get("response")
                else:
                    del self._cache[key]

            # Set new entry if response provided
            if response is not None:
                self._cache[key] = {"response": response, "expires_at": time.time() + ttl_seconds}

            return None

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached response for key.

        Args:
            key: Idempotency key

        Returns:
            Cached response or None
        """
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if entry["expires_at"] > time.time():
                    return entry.get("response")
                else:
                    del self._cache[key]
            return None

    def set(self, key: str, response: Dict[str, Any], ttl_seconds: int = 86400) -> None:
        """Set cached response for key.

        Args:
            key: Idempotency key
            response: Response to cache
            ttl_seconds: Time-to-live in seconds
        """
        with self._lock:
            self._cache[key] = {"response": response, "expires_at": time.time() + ttl_seconds}

    def delete(self, key: str) -> None:
        """Delete idempotency key.

        Args:
            key: Idempotency key to delete
        """
        with self._lock:
            self._cache.pop(key, None)

    def _cleanup_expired(self) -> None:
        """Remove expired entries."""
        now = time.time()
        expired = [k for k, v in self._cache.items() if v["expires_at"] <= now]
        for key in expired:
            del self._cache[key]

    def clear(self) -> None:
        """Clear all entries (for testing)."""
        with self._lock:
            self._cache.clear()
