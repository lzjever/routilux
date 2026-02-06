"""Metrics export module for production monitoring.

This module provides Prometheus-compatible metrics export for monitoring
flow and routine execution in production environments.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class Counter:
    """A counter is a cumulative metric that represents a single monotonically increasing counter.

    The counter value can only increase and is reset to zero on process restart.
    """

    def __init__(self, name: str, description: str, labels: dict[str, str] | None = None) -> None:
        """Initialize a counter.

        Args:
            name: Metric name.
            description: Metric description.
            labels: Optional labels for the metric.
        """
        self.name = name
        self.description = description
        self.labels = labels or {}
        self._value: float = 0
        self._lock = threading.Lock()

    def inc(self, amount: float = 1) -> None:
        """Increment the counter by the given amount.

        Args:
            amount: Amount to increment by (must be positive). Default is 1.
        """
        if amount < 0:
            raise ValueError("Counter can only be incremented by positive amounts")

        with self._lock:
            self._value += amount

    @property
    def value(self) -> float:
        """Get the current counter value."""
        with self._lock:
            return self._value

    def export_prometheus(self) -> str:
        """Export the counter in Prometheus text format.

        Returns:
            Prometheus formatted metric string.
        """
        label_str = ""
        if self.labels:
            label_pairs = [f'{k}="{v}"' for k, v in self.labels.items()]
            label_str = "{" + ",".join(label_pairs) + "}"

        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} counter",
            f"{self.name}{label_str} {self._value}",
        ]
        return "\n".join(lines)


class Gauge:
    """A gauge is a metric that represents a single numerical value that can arbitrarily go up and down."""

    def __init__(self, name: str, description: str, labels: dict[str, str] | None = None) -> None:
        """Initialize a gauge.

        Args:
            name: Metric name.
            description: Metric description.
            labels: Optional labels for the metric.
        """
        self.name = name
        self.description = description
        self.labels = labels or {}
        self._value = 0.0
        self._lock = threading.Lock()

    def set(self, value: float) -> None:
        """Set the gauge to the given value.

        Args:
            value: Value to set.
        """
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1) -> None:
        """Increment the gauge by the given amount.

        Args:
            amount: Amount to increment by.
        """
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1) -> None:
        """Decrement the gauge by the given amount.

        Args:
            amount: Amount to decrement by.
        """
        with self._lock:
            self._value -= amount

    @property
    def value(self) -> float:
        """Get the current gauge value."""
        with self._lock:
            return self._value

    def export_prometheus(self) -> str:
        """Export the gauge in Prometheus text format.

        Returns:
            Prometheus formatted metric string.
        """
        label_str = ""
        if self.labels:
            label_pairs = [f'{k}="{v}"' for k, v in self.labels.items()]
            label_str = "{" + ",".join(label_pairs) + "}"

        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} gauge",
            f"{self.name}{label_str} {self._value}",
        ]
        return "\n".join(lines)


class Histogram:
    """A histogram samples observations and counts them in configurable buckets.

    Histograms track the count, sum, and bucket counts of observations.
    """

    # Default Prometheus buckets (in seconds)
    DEFAULT_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

    def __init__(
        self,
        name: str,
        description: str,
        labels: dict[str, str] | None = None,
        buckets: list[float] | None = None,
    ) -> None:
        """Initialize a histogram.

        Args:
            name: Metric name.
            description: Metric description.
            labels: Optional labels for the metric.
            buckets: Upper bounds for buckets. Must be sorted in ascending order.
        """
        self.name = name
        self.description = description
        self.labels = labels or {}
        self.buckets = buckets or self.DEFAULT_BUCKETS.copy()
        self._count = 0
        self._sum = 0.0
        # Buckets store count of observations <= bucket value
        self._bucket_counts: dict[float, int] = {b: 0 for b in self.buckets}
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        """Record an observation.

        Args:
            value: Observed value to record.
        """
        with self._lock:
            self._count += 1
            self._sum += value
            for bucket in self.buckets:
                if value <= bucket:
                    self._bucket_counts[bucket] += 1

    @property
    def count(self) -> int:
        """Get the total count of observations."""
        with self._lock:
            return self._count

    @property
    def sum(self) -> float:
        """Get the sum of all observations."""
        with self._lock:
            return self._sum

    def export_prometheus(self) -> str:
        """Export the histogram in Prometheus text format.

        Returns:
            Prometheus formatted metric string.
        """
        label_str = ""
        if self.labels:
            label_pairs = [f'{k}="{v}"' for k, v in self.labels.items()]
            label_str = "{" + ",".join(label_pairs) + "}"

        lines = [
            f"# HELP {self.name} {self.description}",
            f"# TYPE {self.name} histogram",
        ]

        # Export bucket counts
        for bucket in self.buckets:
            le_label = f'le="{bucket}"'
            full_label = label_str[:-1] + f",{le_label}}}" if label_str else "{" + le_label + "}"
            lines.append(f"{self.name}_bucket{full_label} {self._bucket_counts[bucket]}")

        # Export +Inf bucket (all observations)
        le_label = 'le="+Inf"'
        full_label = label_str[:-1] + f",{le_label}}}" if label_str else "{" + le_label + "}"
        lines.append(f"{self.name}_bucket{full_label} {self._count}")

        # Export sum and count
        lines.append(f"{self.name}_sum{label_str} {self._sum}")
        lines.append(f"{self.name}_count{label_str} {self._count}")

        return "\n".join(lines)


class MetricsCollector:
    """Registry for collecting and exporting metrics.

    The MetricsCollector manages all metrics and provides Prometheus export functionality.
    """

    def __init__(self) -> None:
        """Initialize the metrics collector."""
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        self._lock = threading.Lock()

    def counter(self, name: str, description: str, labels: dict[str, str] | None = None) -> Counter:
        """Get or create a counter metric.

        Args:
            name: Metric name.
            description: Metric description.
            labels: Optional labels for the metric.

        Returns:
            Counter instance.
        """
        key = self._make_key(name, labels)
        with self._lock:
            if key not in self._counters:
                self._counters[key] = Counter(name, description, labels)
            return self._counters[key]

    def gauge(self, name: str, description: str, labels: dict[str, str] | None = None) -> Gauge:
        """Get or create a gauge metric.

        Args:
            name: Metric name.
            description: Metric description.
            labels: Optional labels for the metric.

        Returns:
            Gauge instance.
        """
        key = self._make_key(name, labels)
        with self._lock:
            if key not in self._gauges:
                self._gauges[key] = Gauge(name, description, labels)
            return self._gauges[key]

    def histogram(
        self,
        name: str,
        description: str,
        labels: dict[str, str] | None = None,
        buckets: list[float] | None = None,
    ) -> Histogram:
        """Get or create a histogram metric.

        Args:
            name: Metric name.
            description: Metric description.
            labels: Optional labels for the metric.
            buckets: Optional bucket boundaries.

        Returns:
            Histogram instance.
        """
        key = self._make_key(name, labels)
        with self._lock:
            if key not in self._histograms:
                self._histograms[key] = Histogram(name, description, labels, buckets)
            return self._histograms[key]

    def get_or_create_counter(
        self, name: str, description: str, labels: dict[str, str] | None = None
    ) -> Counter:
        """Get or create a counter metric with description.

        This is a convenience method that ensures the counter exists.
        If the counter exists, it returns it (ignoring the description).
        If it doesn't exist, it creates a new one.

        Args:
            name: Metric name.
            description: Metric description.
            labels: Optional labels for the metric.

        Returns:
            Counter instance.
        """
        key = self._make_key(name, labels)
        with self._lock:
            if key not in self._counters:
                self._counters[key] = Counter(name, description, labels)
            return self._counters[key]

    def get_counter(self, name: str, labels: dict[str, str] | None = None) -> Counter | None:
        """Get an existing counter metric.

        Args:
            name: Metric name.
            labels: Optional labels to identify specific labeled counter.

        Returns:
            Counter instance or None if not found.
        """
        key = self._make_key(name, labels)
        return self._counters.get(key)

    def get_gauge(self, name: str, labels: dict[str, str] | None = None) -> Gauge | None:
        """Get an existing gauge metric.

        Args:
            name: Metric name.
            labels: Optional labels to identify specific labeled gauge.

        Returns:
            Gauge instance or None if not found.
        """
        key = self._make_key(name, labels)
        return self._gauges.get(key)

    def get_histogram(self, name: str, labels: dict[str, str] | None = None) -> Histogram | None:
        """Get an existing histogram metric.

        Args:
            name: Metric name.
            labels: Optional labels to identify specific labeled histogram.

        Returns:
            Histogram instance or None if not found.
        """
        key = self._make_key(name, labels)
        return self._histograms.get(key)

    def _make_key(self, name: str, labels: dict[str, str] | None) -> str:
        """Create a unique key for a labeled metric.

        Args:
            name: Metric name.
            labels: Optional labels.

        Returns:
            Unique key string.
        """
        if not labels:
            return name
        sorted_items = sorted(labels.items())
        label_str = ",".join(f"{k}={v}" for k, v in sorted_items)
        return f"{name}{{{label_str}}}"

    def export_prometheus(self) -> str:
        """Export all metrics in Prometheus text format.

        Returns:
            Prometheus formatted metrics string.
        """
        lines = []

        with self._lock:
            # Export counters
            for counter in self._counters.values():
                lines.append(counter.export_prometheus())
                lines.append("")

            # Export gauges
            for gauge in self._gauges.values():
                lines.append(gauge.export_prometheus())
                lines.append("")

            # Export histograms
            for histogram in self._histograms.values():
                lines.append(histogram.export_prometheus())
                lines.append("")

        return "\n".join(lines).strip()


class MetricTimer:
    """Context manager for timing operations and recording to a histogram.

    Example:
        >>> collector = MetricsCollector()
        >>> hist = collector.histogram("operation_duration", "Operation duration")
        >>> with MetricTimer(hist):
        ...     # Do some work
        ...     time.sleep(0.1)
    """

    def __init__(self, histogram: Histogram) -> None:
        """Initialize the timer.

        Args:
            histogram: Histogram to record observations to.
        """
        self._histogram = histogram
        self._start: float | None = None

    def __enter__(self) -> MetricTimer:
        """Start the timer."""
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        """Stop the timer and record the observation."""
        if self._start is not None:
            duration = time.perf_counter() - self._start
            self._histogram.observe(duration)
