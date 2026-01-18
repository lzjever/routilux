"""
Routed stdout for capturing and routing print() output by job_id.

This module provides a way to capture stdout output from routines and
route it to separate buffers based on the current job context.
"""

from __future__ import annotations

import sys
import threading
from collections import defaultdict, deque
from typing import TextIO

from routilux.core.context import _current_job


class RoutedStdout:
    """Route stdout output by job_id.

    This class intercepts all print()/sys.stdout.write() calls and routes
    the output to separate buffers based on the current job context.

    Features:
        - Automatic routing by job_id via contextvars
        - Support for incremental retrieval (pop_chunks)
        - Support for full history retrieval (get_buffer)
        - Concurrent job outputs are completely isolated
        - Output without job context goes to real stdout

    Example:
        >>> # Install at program startup
        >>> routed_stdout = install_routed_stdout()
        >>>
        >>> # In routine logic (job context is automatically set)
        >>> print("Processing data...")  # Output routed to current job
        >>>
        >>> # External retrieval
        >>> chunks = routed_stdout.pop_chunks("job-001")  # Incremental
        >>> buffer = routed_stdout.get_buffer("job-001")  # Full history
    """

    def __init__(
        self,
        real_stdout: TextIO | None = None,
        keep_default: bool = True,
        max_buffer_chars: int = 200_000,
    ):
        """Initialize RoutedStdout.

        Args:
            real_stdout: Real stdout to use for unboud output.
                Defaults to sys.__stdout__.
            keep_default: If True, output without job binding goes to real stdout.
                If False, such output is discarded.
            max_buffer_chars: Maximum characters to keep in buffer per job.
                Older content is trimmed when exceeded.
        """
        self.real = real_stdout if real_stdout is not None else sys.__stdout__
        self.keep_default = keep_default
        self.max_buffer_chars = max_buffer_chars

        self._lock = threading.RLock()
        self._queues: dict[str, deque[str]] = defaultdict(deque)
        self._buffers: dict[str, str] = defaultdict(str)

    def write(self, s: str) -> int:
        """Write string to stdout.

        Routes output to appropriate job buffer based on current context.

        Args:
            s: String to write

        Returns:
            Number of characters written
        """
        if not s:
            return 0

        job = _current_job.get(None)
        job_id = job.job_id if job else None

        with self._lock:
            if job_id is None:
                # No job bound - write to real stdout if keep_default
                if self.keep_default:
                    self.real.write(s)
                    self.real.flush()
                return len(s)

            # 1) Enqueue for incremental retrieval
            self._queues[job_id].append(s)

            # 2) Maintain cumulative buffer for history retrieval
            buf = self._buffers[job_id] + s
            if len(buf) > self.max_buffer_chars:
                buf = buf[-self.max_buffer_chars :]  # Keep tail only
            self._buffers[job_id] = buf

        return len(s)

    def flush(self) -> None:
        """Flush output."""
        with self._lock:
            if self.keep_default:
                self.real.flush()

    @property
    def encoding(self) -> str:
        """Return encoding."""
        return getattr(self.real, "encoding", "utf-8")

    def isatty(self) -> bool:
        """Return False (not a tty)."""
        return False

    def pop_chunks(self, job_id: str) -> list[str]:
        """Pop and return incremental output chunks for a job.

        This is a consuming operation - chunks are removed after retrieval.

        Args:
            job_id: Job ID to get chunks for

        Returns:
            List of output chunks (may be empty)

        Example:
            >>> chunks = routed_stdout.pop_chunks("job-001")
            >>> new_output = "".join(chunks)
        """
        with self._lock:
            q = self._queues.get(job_id)
            if not q:
                return []
            chunks = list(q)
            q.clear()
            return chunks

    def get_buffer(self, job_id: str) -> str:
        """Get full history buffer for a job.

        This is non-consuming - buffer remains intact.

        Args:
            job_id: Job ID to get buffer for

        Returns:
            Full output buffer (may be truncated to max_buffer_chars)

        Example:
            >>> history = routed_stdout.get_buffer("job-001")
            >>> print(f"Job output so far:\\n{history}")
        """
        with self._lock:
            return self._buffers.get(job_id, "")

    def clear_job(self, job_id: str) -> None:
        """Clear all output data for a job.

        Call this when a job is completed to free memory.

        Args:
            job_id: Job ID to clear
        """
        with self._lock:
            self._queues.pop(job_id, None)
            self._buffers.pop(job_id, None)

    def list_jobs(self) -> list[str]:
        """List all job IDs with output data.

        Returns:
            List of job IDs
        """
        with self._lock:
            return list(set(self._queues.keys()) | set(self._buffers.keys()))

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about current output buffers.

        Returns:
            Dictionary with stats
        """
        with self._lock:
            return {
                "job_count": len(set(self._queues.keys()) | set(self._buffers.keys())),
                "total_queue_items": sum(len(q) for q in self._queues.values()),
                "total_buffer_chars": sum(len(b) for b in self._buffers.values()),
            }


# Global instance
_routed_stdout: RoutedStdout | None = None
_original_stdout: TextIO | None = None


def install_routed_stdout(
    keep_default: bool = True, max_buffer_chars: int = 200_000
) -> RoutedStdout:
    """Install routed stdout globally.

    Should be called early in program startup, before any routines run.

    Args:
        keep_default: If True, output without job binding goes to real stdout
        max_buffer_chars: Maximum buffer size per job

    Returns:
        RoutedStdout instance

    Example:
        >>> # At program entry point
        >>> from routilux.core import install_routed_stdout
        >>> install_routed_stdout()
        >>>
        >>> # Now all print() calls in routines are captured by job
    """
    global _routed_stdout, _original_stdout
    if _routed_stdout is None:
        _original_stdout = sys.stdout
        _routed_stdout = RoutedStdout(keep_default=keep_default, max_buffer_chars=max_buffer_chars)
        sys.stdout = _routed_stdout
    return _routed_stdout


def uninstall_routed_stdout() -> None:
    """Uninstall routed stdout and restore original.

    Example:
        >>> uninstall_routed_stdout()
        >>> # sys.stdout is now restored to original
    """
    global _routed_stdout, _original_stdout
    if _original_stdout is not None:
        sys.stdout = _original_stdout
        _routed_stdout = None
        _original_stdout = None


def get_routed_stdout() -> RoutedStdout | None:
    """Get the global RoutedStdout instance.

    Returns:
        RoutedStdout instance if installed, None otherwise
    """
    return _routed_stdout


def get_job_output(job_id: str, incremental: bool = True) -> str:
    """Get output for a specific job.

    Convenience function for retrieving job output.

    Args:
        job_id: Job ID to get output for
        incremental: If True, returns and clears incremental chunks.
            If False, returns full history buffer.

    Returns:
        Output string (may be empty)

    Example:
        >>> # Get incremental output (new since last call)
        >>> new_output = get_job_output("job-001", incremental=True)
        >>>
        >>> # Get full history
        >>> full_output = get_job_output("job-001", incremental=False)
    """
    if _routed_stdout is None:
        return ""

    if incremental:
        chunks = _routed_stdout.pop_chunks(job_id)
        return "".join(chunks)
    else:
        return _routed_stdout.get_buffer(job_id)


def clear_job_output(job_id: str) -> None:
    """Clear output data for a job.

    Args:
        job_id: Job ID to clear
    """
    if _routed_stdout is not None:
        _routed_stdout.clear_job(job_id)
