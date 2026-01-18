"""
FastAPI dependency injection for Routilux API.

This module provides dependency functions for:
- Runtime access
- Registry access
- Storage backends
"""

from functools import lru_cache
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from routilux.core.registry import FlowRegistry, WorkerRegistry
    from routilux.core.runtime import Runtime
    from routilux.monitoring.runtime_registry import RuntimeRegistry
    from routilux.server.storage.memory import MemoryIdempotencyBackend, MemoryJobStorage


@lru_cache
def get_runtime_registry() -> "RuntimeRegistry":
    """Get RuntimeRegistry singleton.

    Returns:
        RuntimeRegistry instance
    """
    from routilux.monitoring.runtime_registry import RuntimeRegistry

    return RuntimeRegistry.get_instance()


def get_runtime() -> "Runtime":
    """Get default Runtime instance.

    This is the main dependency for accessing the execution runtime.

    Returns:
        Default Runtime instance
    """
    registry = get_runtime_registry()
    return registry.get_or_create_default()


def get_flow_registry() -> "FlowRegistry":
    """Get FlowRegistry singleton.

    Returns:
        FlowRegistry instance
    """
    from routilux.core.registry import FlowRegistry

    return FlowRegistry.get_instance()


def get_worker_registry() -> "WorkerRegistry":
    """Get WorkerRegistry singleton.

    Returns:
        WorkerRegistry instance
    """
    from routilux.core.registry import WorkerRegistry

    return WorkerRegistry.get_instance()


# Storage singletons (lazy initialization)
_job_storage: Optional["MemoryJobStorage"] = None
_idempotency_backend: Optional["MemoryIdempotencyBackend"] = None


def get_job_storage() -> "MemoryJobStorage":
    """Get job storage backend.

    Currently uses in-memory storage. Can be replaced with
    persistent storage (Redis, PostgreSQL, etc.) in production.

    Returns:
        Job storage backend instance
    """
    global _job_storage
    if _job_storage is None:
        from routilux.server.storage.memory import MemoryJobStorage

        _job_storage = MemoryJobStorage()
    return _job_storage


def get_idempotency_backend() -> "MemoryIdempotencyBackend":
    """Get idempotency key storage backend.

    Currently uses in-memory storage. Should be replaced with
    Redis or similar in production for distributed idempotency.

    Returns:
        Idempotency backend instance
    """
    global _idempotency_backend
    if _idempotency_backend is None:
        from routilux.server.storage.memory import MemoryIdempotencyBackend

        _idempotency_backend = MemoryIdempotencyBackend()
    return _idempotency_backend


def reset_storage() -> None:
    """Reset storage backends (for testing).

    This clears the singleton instances so they will be
    recreated on next access.
    """
    global _job_storage, _idempotency_backend
    _job_storage = None
    _idempotency_backend = None
