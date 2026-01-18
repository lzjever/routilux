"""
Global monitoring registry for optional monitoring features.

This registry allows monitoring to be enabled/disabled globally without
modifying existing code. When disabled, all monitoring hooks return immediately
with zero overhead.
"""

import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from routilux.monitoring.breakpoint_manager import BreakpointManager
    from routilux.monitoring.debug_session import DebugSessionStore
    from routilux.monitoring.monitor_collector import MonitorCollector


class MonitoringRegistry:
    """Global registry for monitoring services.

    This is a singleton that manages monitoring services. When disabled,
    all monitoring operations are no-ops with minimal overhead.
    """

    _instance: Optional["MonitoringRegistry"] = None
    _lock = threading.Lock()
    _enabled: bool = False

    def __init__(self):
        """Initialize registry (private - use get_instance())."""
        self._breakpoint_manager: Optional[BreakpointManager] = None
        self._monitor_collector: Optional[MonitorCollector] = None
        self._debug_session_store: Optional[DebugSessionStore] = None

    @classmethod
    def get_instance(cls) -> "MonitoringRegistry":
        """Get singleton instance.

        Returns:
            MonitoringRegistry instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def enable(cls) -> None:
        """Enable monitoring globally.

        This initializes all monitoring services and registers execution hooks.
        Once enabled, monitoring hooks will collect data and check breakpoints.
        """
        # First get the instance (without holding the lock)
        instance = cls.get_instance()

        # Then initialize and enable services (with lock)
        with cls._lock:
            # Fix: Initialize services BEFORE setting _enabled to True
            # This prevents race condition where other threads see enabled=True but services are None

            # Lazy initialization of services
            if instance._breakpoint_manager is None:
                from routilux.monitoring.breakpoint_manager import BreakpointManager

                instance._breakpoint_manager = BreakpointManager()

            if instance._monitor_collector is None:
                from routilux.monitoring.monitor_collector import MonitorCollector

                instance._monitor_collector = MonitorCollector()

            if instance._debug_session_store is None:
                from routilux.monitoring.debug_session import DebugSessionStore

                instance._debug_session_store = DebugSessionStore()

            # Set enabled AFTER all services are initialized
            cls._enabled = True

        # Register execution hooks with core (outside lock to avoid deadlock)
        from routilux.monitoring.execution_hooks import enable_monitoring_hooks

        enable_monitoring_hooks()

    @classmethod
    def disable(cls) -> None:
        """Disable monitoring globally.

        This stops all monitoring operations and unregisters execution hooks.
        Hooks will return immediately without doing any work.
        """
        with cls._lock:
            cls._enabled = False

        # Unregister execution hooks from core (outside lock to avoid deadlock)
        from routilux.monitoring.execution_hooks import disable_monitoring_hooks

        disable_monitoring_hooks()

    @classmethod
    def is_enabled(cls) -> bool:
        """Check if monitoring is enabled.

        Returns:
            True if monitoring is enabled, False otherwise.
        """
        return cls._enabled

    @property
    def breakpoint_manager(self) -> Optional["BreakpointManager"]:
        """Get breakpoint manager (None if monitoring disabled)."""
        if not self.is_enabled():
            return None
        return self._breakpoint_manager

    @property
    def monitor_collector(self) -> Optional["MonitorCollector"]:
        """Get monitor collector (None if monitoring disabled)."""
        if not self.is_enabled():
            return None
        return self._monitor_collector

    @property
    def debug_session_store(self) -> Optional["DebugSessionStore"]:
        """Get debug session store (None if monitoring disabled)."""
        if not self.is_enabled():
            return None
        return self._debug_session_store
