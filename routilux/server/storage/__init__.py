"""
Storage backends for Routilux API.

Provides:
- MemoryJobStorage: In-memory job storage
- MemoryIdempotencyBackend: In-memory idempotency key storage
- Protocol definitions for custom backends
"""

from routilux.server.storage.base import JobStorageBackend, IdempotencyBackend
from routilux.server.storage.memory import MemoryJobStorage, MemoryIdempotencyBackend

__all__ = [
    "JobStorageBackend",
    "IdempotencyBackend",
    "MemoryJobStorage",
    "MemoryIdempotencyBackend",
]
