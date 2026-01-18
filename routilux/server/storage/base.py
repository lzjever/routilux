"""
Storage backend protocols for Routilux API.

Defines the interfaces that storage backends must implement.
"""

from typing import Any, Dict, List, Optional, Protocol

from routilux.core.context import JobContext


class JobStorageBackend(Protocol):
    """Protocol for job storage backends.

    Implement this protocol to create custom job storage
    (e.g., Redis, PostgreSQL, MongoDB).
    """

    def save_job(self, job: JobContext) -> None:
        """Save or update a job.

        Args:
            job: JobContext to save
        """
        ...

    def get_job(self, job_id: str) -> Optional[JobContext]:
        """Get job by ID.

        Args:
            job_id: Job identifier

        Returns:
            JobContext if found, None otherwise
        """
        ...

    def delete_job(self, job_id: str) -> bool:
        """Delete a job.

        Args:
            job_id: Job identifier

        Returns:
            True if deleted, False if not found
        """
        ...

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
            flow_id: Filter by flow ID
            status: Filter by status
            limit: Maximum results
            offset: Skip first N results

        Returns:
            List of matching JobContext objects
        """
        ...

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
        ...


class IdempotencyBackend(Protocol):
    """Protocol for idempotency key storage.

    Implement this protocol to create custom idempotency storage
    (e.g., Redis with TTL support).
    """

    def check_and_set(
        self, key: str, response: Optional[Dict[str, Any]], ttl_seconds: int = 86400
    ) -> Optional[Dict[str, Any]]:
        """Check if key exists and optionally set response.

        If key exists, return cached response.
        If key doesn't exist and response is not None, store response.

        Args:
            key: Idempotency key
            response: Response to cache (None to just check)
            ttl_seconds: Time-to-live in seconds

        Returns:
            Cached response if key existed, None otherwise
        """
        ...

    def delete(self, key: str) -> None:
        """Delete idempotency key.

        Args:
            key: Idempotency key to delete
        """
        ...

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached response for key.

        Args:
            key: Idempotency key

        Returns:
            Cached response or None
        """
        ...

    def set(self, key: str, response: Dict[str, Any], ttl_seconds: int = 86400) -> None:
        """Set cached response for key.

        Args:
            key: Idempotency key
            response: Response to cache
            ttl_seconds: Time-to-live in seconds
        """
        ...
