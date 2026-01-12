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
        # Define trigger slot for entry routine
        self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
        self.output_event = self.define_event("output", ["data", "source_id"])

    def _handle_trigger(self, **kwargs):
        data = kwargs.get("data", f"data_from_{self.source_id}")
        # Get flow from routine context
        flow = getattr(self, "_current_flow", None)
        self.emit("output", flow=flow, data=data, source_id=self.source_id)


class MultiSourceRoutine(Routine):
    """Source routine that emits multiple messages."""

    def __init__(self):
        super().__init__()
        # Define trigger slot for entry routine
        self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
        self.output_event = self.define_event("output", ["data", "source_id"])

    def _handle_trigger(self, **kwargs):
        # Get flow from routine context
        flow = getattr(self, "_current_flow", None)
        # Emit multiple messages
        for i in range(3):
            self.emit("output", flow=flow, data=f"data{i + 1}", source_id=f"source{i + 1}")


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

            # Get flow from routine context
            flow = getattr(self, "_current_flow", None)
            self.emit("aggregated", flow=flow, all_data=all_data, count=len(all_data))
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

        # Create a single source that emits multiple messages
        multi_source = MultiSourceRoutine()

        # Create aggregator
        aggregator = AggregatorRoutine(expected_count=3)

        # Create consumer
        consumer = ConsumerRoutine()

        # Add to flow
        source_id = flow.add_routine(multi_source, "multi_source")
        agg_id = flow.add_routine(aggregator, "aggregator")
        consumer_id = flow.add_routine(consumer, "consumer")

        # Connect - single source to aggregator
        flow.connect(source_id, "output", agg_id, "input")
        flow.connect(agg_id, "aggregated", consumer_id, "input")

        # Execute - single execute that triggers multiple emits
        job_state = flow.execute(source_id)

        # Wait for all tasks to complete
        from routilux.job_state import JobState

        JobState.wait_for_completion(flow, job_state, timeout=2.0)
        time.sleep(0.1)  # Additional wait for handler execution

        # Verify
        assert aggregator.processed, "Aggregator should have processed"
        assert aggregator.received_count == 3, "Should receive 3 messages"
        assert len(consumer.received_results) == 1, "Consumer should receive 1 result"
        assert consumer.received_results[0]["count"] == 3, "Should have 3 items"

    def test_aggregator_with_partial_messages(self):
        """Test that aggregator doesn't process with partial messages."""
        flow = Flow(flow_id="test_aggregator_partial")

        class PartialSourceRoutine(Routine):
            """Source routine that emits only 2 messages."""

            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data", "source_id"])

            def _handle_trigger(self, **kwargs):
                flow = getattr(self, "_current_flow", None)
                # Emit only 2 messages
                for i in range(2):
                    self.emit("output", flow=flow, data=f"data{i + 1}", source_id=f"source{i + 1}")

        # Create a source that emits only 2 messages
        partial_source = PartialSourceRoutine()

        # Create aggregator expecting 3 messages
        aggregator = AggregatorRoutine(expected_count=3)

        # Add to flow
        source_id = flow.add_routine(partial_source, "partial_source")
        agg_id = flow.add_routine(aggregator, "aggregator")

        # Connect
        flow.connect(source_id, "output", agg_id, "input")

        # Execute - only 2 messages will be emitted
        job_state = flow.execute(source_id)

        # Wait for all tasks to complete
        from routilux.job_state import JobState

        JobState.wait_for_completion(flow, job_state, timeout=2.0)
        time.sleep(0.1)  # Additional wait for handler execution

        # Verify - should not have processed
        assert not aggregator.processed, "Aggregator should not process with partial messages"
        assert aggregator.received_count == 2, "Should receive 2 messages"

    def test_aggregator_concurrent_execution(self):
        """Test aggregator with concurrent execution."""
        flow = Flow(flow_id="test_aggregator_concurrent", execution_strategy="concurrent")

        # Create a single source that emits multiple messages
        multi_source = MultiSourceRoutine()

        # Create aggregator
        aggregator = AggregatorRoutine(expected_count=3)

        # Create consumer
        consumer = ConsumerRoutine()

        # Add to flow
        source_id = flow.add_routine(multi_source, "multi_source")
        agg_id = flow.add_routine(aggregator, "aggregator")
        consumer_id = flow.add_routine(consumer, "consumer")

        # Connect - single source to aggregator
        flow.connect(source_id, "output", agg_id, "input")
        flow.connect(agg_id, "aggregated", consumer_id, "input")

        try:
            # Execute - single execute that triggers multiple emits
            job_state = flow.execute(source_id)

            # Wait for completion
            from routilux.job_state import JobState

            JobState.wait_for_completion(flow, job_state, timeout=5.0)
            time.sleep(0.1)  # Additional wait for handler execution

            # Verify
            assert aggregator.processed, "Aggregator should have processed"
            assert aggregator.received_count == 3, "Should receive 3 messages"
            assert len(consumer.received_results) == 1, "Consumer should receive 1 result"
        finally:
            flow.shutdown(wait=True)
