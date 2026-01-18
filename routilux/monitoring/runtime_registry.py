"""
Global runtime registry for API discovery and management.

This registry tracks all Runtime instances created in the system,
allowing the API to discover and select runtimes for job execution.
Uses strong references to keep Runtime instances alive.
"""

import threading
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from routilux.core.runtime import Runtime


class RuntimeRegistry:
    """Global registry for Runtime instances.

    Thread-safe singleton that tracks Runtime instances by ID.
    Uses strong references to keep Runtime instances alive.
    """

    _instance: Optional["RuntimeRegistry"] = None
    _lock = threading.Lock()

    def __init__(self):
        """Initialize registry (private - use get_instance())."""
        self._runtimes: Dict[str, Runtime] = {}  # runtime_id -> Runtime (strong reference)
        self._default_runtime_id: Optional[str] = None
        self._lock: threading.RLock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "RuntimeRegistry":
        """Get singleton instance.

        Returns:
            RuntimeRegistry singleton instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(self, runtime: "Runtime", runtime_id: str, is_default: bool = False) -> None:
        """Register a runtime instance.

        Args:
            runtime: Runtime instance to register.
            runtime_id: Unique identifier for this runtime.
            is_default: If True, set this as the default runtime.

        Raises:
            ValueError: If runtime_id is empty or already registered.
            TypeError: If runtime is not a Runtime instance.
        """
        if not runtime_id:
            raise ValueError("runtime_id cannot be empty")
        if not hasattr(runtime, "thread_pool_size"):
            raise TypeError("runtime must be a Runtime instance")

        with self._lock:
            if runtime_id in self._runtimes:
                raise ValueError(f"Runtime '{runtime_id}' is already registered")
            self._runtimes[runtime_id] = runtime
            if is_default or self._default_runtime_id is None:
                self._default_runtime_id = runtime_id

    def get(self, runtime_id: Optional[str] = None) -> Optional["Runtime"]:
        """Get runtime by ID.

        Args:
            runtime_id: Runtime identifier. If None, returns default runtime.

        Returns:
            Runtime instance if found, None otherwise.
        """
        with self._lock:
            if runtime_id is None:
                runtime_id = self._default_runtime_id
            if runtime_id is None:
                return None
            return self._runtimes.get(runtime_id)

    def get_or_create_default(self, thread_pool_size: int = 10) -> "Runtime":
        """Get default runtime, creating it if it doesn't exist.

        Args:
            thread_pool_size: Thread pool size for new runtime (if created).

        Returns:
            Default Runtime instance.
        """
        with self._lock:
            if self._default_runtime_id is None:
                from routilux.core.runtime import Runtime

                runtime = Runtime(thread_pool_size=thread_pool_size)
                self.register(runtime, "default", is_default=True)
            return self._runtimes[self._default_runtime_id]

    def list_all(self) -> List[str]:
        """List all registered runtime IDs.

        Returns:
            List of runtime IDs.
        """
        with self._lock:
            return list(self._runtimes.keys())

    def get_all(self) -> Dict[str, "Runtime"]:
        """Get all registered runtimes.

        Returns:
            Dictionary mapping runtime_id to Runtime instance.
        """
        with self._lock:
            return self._runtimes.copy()

    def unregister(self, runtime_id: str) -> bool:
        """Unregister a runtime.

        Args:
            runtime_id: Runtime identifier to unregister.

        Returns:
            True if runtime was unregistered, False if not found.

        Raises:
            ValueError: If trying to unregister the default runtime.
        """
        with self._lock:
            if runtime_id not in self._runtimes:
                return False
            if runtime_id == self._default_runtime_id:
                raise ValueError("Cannot unregister the default runtime")
            del self._runtimes[runtime_id]
            return True

    def set_default(self, runtime_id: str) -> None:
        """Set the default runtime.

        Args:
            runtime_id: Runtime identifier to set as default.

        Raises:
            ValueError: If runtime_id is not registered.
        """
        with self._lock:
            if runtime_id not in self._runtimes:
                raise ValueError(f"Runtime '{runtime_id}' is not registered")
            self._default_runtime_id = runtime_id

    def get_default_id(self) -> Optional[str]:
        """Get the default runtime ID.

        Returns:
            Default runtime ID, or None if no default is set.
        """
        with self._lock:
            return self._default_runtime_id

    def clear(self) -> None:
        """Clear all registered runtimes (except default).

        This is mainly for testing purposes.
        """
        with self._lock:
            default_id = self._default_runtime_id
            self._runtimes.clear()
            if default_id:
                # Re-register default if it was set
                # Note: This assumes default runtime still exists, which may not be true
                pass
            self._default_runtime_id = None
