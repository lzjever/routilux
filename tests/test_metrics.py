"""Tests for metrics export."""

from routilux import Flow, Routine
from routilux.metrics import Counter, Gauge, Histogram, MetricsCollector


def test_counter_increment():
    """Counter should increment."""
    counter = Counter("test_counter", "A test counter")
    counter.inc()
    counter.inc(5)

    assert counter.value == 6


def test_histogram_records():
    """Histogram should record observations."""
    histogram = Histogram("test_histogram", "A test histogram")

    histogram.observe(1.0)
    histogram.observe(2.0)
    histogram.observe(3.0)

    assert histogram.count == 3
    assert histogram.sum == 6.0


def test_gauge_set():
    """Gauge should set value."""
    gauge = Gauge("test_gauge", "A test gauge")

    gauge.set(42)
    assert gauge.value == 42

    gauge.inc(5)
    assert gauge.value == 47

    gauge.dec(10)
    assert gauge.value == 37


def test_metrics_collector_tracks_flow_execution():
    """MetricsCollector should track flow execution metrics."""
    flow = Flow()

    class WorkerRoutine(Routine):
        def __init__(self):
            super().__init__()
            self.input_slot = self.define_slot("input", handler=self.process)

        def process(self, **kwargs):
            # Process data
            pass

    routine = WorkerRoutine()
    _ = flow.add_routine(routine, "worker")

    # Enable metrics
    collector = MetricsCollector()
    flow.metrics_collector = collector

    # Simulate metrics tracking
    collector.get_or_create_counter("flow_executions_total", "Total flow executions").inc()
    collector.get_or_create_counter(
        "routine_executions_total", "Total routine executions", labels={"routine": "worker"}
    ).inc()

    # Check metrics were recorded
    assert collector.get_counter("flow_executions_total").value >= 1
    assert (
        collector.get_counter("routine_executions_total", labels={"routine": "worker"}).value >= 1
    )


def test_metrics_export_prometheus_format():
    """Metrics should export in Prometheus format."""
    collector = MetricsCollector()

    counter = collector.counter("test_total", "Test counter")
    counter.inc(10)

    gauge = collector.gauge("test_gauge", "Test gauge")
    gauge.set(42)

    histogram = collector.histogram("test_duration", "Test duration")
    histogram.observe(1.0)
    histogram.observe(2.0)

    # Export to Prometheus format
    output = collector.export_prometheus()

    assert "test_total 10" in output
    assert "test_gauge 42" in output
    assert "test_duration_count" in output
    assert "test_duration_sum" in output


def test_flow_has_metrics_collector():
    """Flow should have a metrics_collector attribute."""
    flow = Flow()

    # Flow should have metrics_collector attribute
    assert hasattr(flow, "metrics_collector")

    # Should be able to set a custom collector
    collector = MetricsCollector()
    flow.metrics_collector = collector
    assert flow.metrics_collector is collector
