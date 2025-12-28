"""
Test cases for aggregator pattern - waiting for all expected messages.
"""

import time
from routilux import Flow, Routine


class SourceRoutine(Routine):
    """Source routine that emits data."""

    def __init__(self, source_id: str):
        super().__init__()
        self.source_id = source_id
        self.output_event = self.define_event("output", ["data", "source_id"])

    def __call__(self, **kwargs):
        super().__call__(**kwargs)
        data = kwargs.get("data", f"data_from_{self.source_id}")
        self.emit("output", data=data, source_id=self.source_id)


class AggregatorRoutine(Routine):
    """Aggregator that waits for all expected messages."""

    def __init__(self, expected_count: int = 3):
        super().__init__()
        self.expected_count = expected_count
        self.set_config(expected_count=expected_count)
        self.processed = False
        self.received_count = 0

        self.input_slot = self.define_slot(
            "input", handler=self._handle_input, merge_strategy="append"
        )
        self.output_event = self.define_event("aggregated", ["all_data", "count"])

    def _handle_input(self, **kwargs):
        """Handle input and check if all messages received."""
        # Count messages using any list field
        received_count = 0
        if "source_id" in kwargs and isinstance(kwargs["source_id"], list):
            received_count = len(kwargs["source_id"])
        elif "data" in kwargs and isinstance(kwargs["data"], list):
            received_count = len(kwargs["data"])

        self.received_count = received_count
        expected_count = self.get_config("expected_count", self.expected_count)

        if received_count >= expected_count and not self.processed:
            self.processed = True
            # Process aggregated data
            all_data = []
            if "data" in kwargs and isinstance(kwargs["data"], list):
                all_data = kwargs["data"]

            self.emit("aggregated", all_data=all_data, count=len(all_data))
            # Reset for next aggregation
            self.input_slot._data = {}


class ConsumerRoutine(Routine):
    """Consumer that receives aggregated results."""

    def __init__(self):
        super().__init__()
        self.received_results = []
        self.input_slot = self.define_slot("input", handler=self._handle_input)

    def _handle_input(self, all_data: list = None, count: int = None, **kwargs):
        self.received_results.append({"data": all_data, "count": count})


class TestAggregatorPattern:
    """Test aggregator pattern."""

    def test_aggregator_waits_for_all_messages(self):
        """Test that aggregator waits for all expected messages."""
        flow = Flow(flow_id="test_aggregator")

        # Create sources
        source1 = SourceRoutine("source1")
        source2 = SourceRoutine("source2")
        source3 = SourceRoutine("source3")

        # Create aggregator
        aggregator = AggregatorRoutine(expected_count=3)

        # Create consumer
        consumer = ConsumerRoutine()

        # Add to flow
        id1 = flow.add_routine(source1, "source1")
        id2 = flow.add_routine(source2, "source2")
        id3 = flow.add_routine(source3, "source3")
        agg_id = flow.add_routine(aggregator, "aggregator")
        consumer_id = flow.add_routine(consumer, "consumer")

        # Connect
        flow.connect(id1, "output", agg_id, "input")
        flow.connect(id2, "output", agg_id, "input")
        flow.connect(id3, "output", agg_id, "input")
        flow.connect(agg_id, "aggregated", consumer_id, "input")

        # Execute sources
        flow.execute(id1, entry_params={"data": "data1"})
        flow.execute(id2, entry_params={"data": "data2"})
        flow.execute(id3, entry_params={"data": "data3"})

        # Wait a bit
        time.sleep(0.2)

        # Verify
        assert aggregator.processed, "Aggregator should have processed"
        assert aggregator.received_count == 3, "Should receive 3 messages"
        assert len(consumer.received_results) == 1, "Consumer should receive 1 result"
        assert consumer.received_results[0]["count"] == 3, "Should have 3 items"

    def test_aggregator_with_partial_messages(self):
        """Test that aggregator doesn't process with partial messages."""
        flow = Flow(flow_id="test_aggregator_partial")

        # Create sources
        source1 = SourceRoutine("source1")
        source2 = SourceRoutine("source2")

        # Create aggregator expecting 3 messages
        aggregator = AggregatorRoutine(expected_count=3)

        # Add to flow
        id1 = flow.add_routine(source1, "source1")
        id2 = flow.add_routine(source2, "source2")
        agg_id = flow.add_routine(aggregator, "aggregator")

        # Connect
        flow.connect(id1, "output", agg_id, "input")
        flow.connect(id2, "output", agg_id, "input")

        # Execute only 2 sources
        flow.execute(id1, entry_params={"data": "data1"})
        flow.execute(id2, entry_params={"data": "data2"})

        # Wait a bit
        time.sleep(0.2)

        # Verify - should not have processed
        assert not aggregator.processed, "Aggregator should not process with partial messages"
        assert aggregator.received_count == 2, "Should receive 2 messages"

    def test_aggregator_concurrent_execution(self):
        """Test aggregator with concurrent execution."""
        flow = Flow(flow_id="test_aggregator_concurrent", execution_strategy="concurrent")

        # Create sources
        source1 = SourceRoutine("source1")
        source2 = SourceRoutine("source2")
        source3 = SourceRoutine("source3")

        # Create aggregator
        aggregator = AggregatorRoutine(expected_count=3)

        # Create consumer
        consumer = ConsumerRoutine()

        # Add to flow
        id1 = flow.add_routine(source1, "source1")
        id2 = flow.add_routine(source2, "source2")
        id3 = flow.add_routine(source3, "source3")
        agg_id = flow.add_routine(aggregator, "aggregator")
        consumer_id = flow.add_routine(consumer, "consumer")

        # Connect
        flow.connect(id1, "output", agg_id, "input")
        flow.connect(id2, "output", agg_id, "input")
        flow.connect(id3, "output", agg_id, "input")
        flow.connect(agg_id, "aggregated", consumer_id, "input")

        try:
            # Execute sources concurrently
            flow.execute(id1, entry_params={"data": "data1"})
            flow.execute(id2, entry_params={"data": "data2"})
            flow.execute(id3, entry_params={"data": "data3"})

            # Wait for completion
            flow.wait_for_completion(timeout=5.0)

            # Verify
            assert aggregator.processed, "Aggregator should have processed"
            assert aggregator.received_count == 3, "Should receive 3 messages"
            assert len(consumer.received_results) == 1, "Consumer should receive 1 result"
        finally:
            flow.shutdown(wait=True)
