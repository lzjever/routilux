"""
Aggregator Routine Demo

Demonstrates how to create a routine that waits for all expected messages
before processing and emitting results.
"""

from routilux import Flow, Routine
import time


class SearchTask(Routine):
    """A search task routine that simulates searching."""

    def __init__(self, task_name: str):
        super().__init__()
        self.task_name = task_name
        self.set_config(task_name=task_name)

        # Define trigger slot
        self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)

        # Define output event
        self.output_event = self.define_event("result", ["query", "results", "task_name"])

    def __call__(self, **kwargs):
        """Execute the routine."""
        super().__call__(**kwargs)
        # If called directly, trigger the search
        query = kwargs.get("query", "default")
        self._handle_trigger(query=query)

    def _handle_trigger(self, query: str = None, **kwargs):
        """Handle search trigger."""
        query = query or kwargs.get("query", "default")

        # Simulate search operation
        time.sleep(0.1)  # Simulate I/O delay

        # Generate mock results
        results = [
            f"{self.task_name}_result_1",
            f"{self.task_name}_result_2",
            f"{self.task_name}_result_3",
        ]

        # Track operation
        self._track_operation("searches", success=True, results_count=len(results))

        # Emit results
        self.emit("result", query=query, results=results, task_name=self.task_name)


class ResultAggregator(Routine):
    """Aggregator routine that waits for all expected messages before processing."""

    def __init__(self, expected_count: int = 3):
        super().__init__()
        self.expected_count = expected_count

        # Set configuration
        self.set_config(expected_count=expected_count, timeout=10.0)  # Optional timeout

        # Define input slot with append strategy to collect all results
        self.input_slot = self.define_slot(
            "input",
            handler=self._handle_input,
            merge_strategy="append",  # Collect all incoming data
        )

        # Define output event
        self.output_event = self.define_event(
            "aggregated", ["all_results", "total_count", "queries"]
        )

    def _handle_input(self, **kwargs):
        """Handle input and check if we have all expected messages.

        With merge_strategy="append", each receive() call adds to the accumulated data.
        The handler receives the merged data (with lists), so we can check the length
        of any list field to determine how many messages we've received.

        Args:
            **kwargs: Merged data from slot. With append strategy, values are lists.
                For example: {'task_name': ['task1', 'task2'], 'results': [[...], [...]]}
        """
        # With merge_strategy="append", kwargs contains accumulated data where
        # values are lists. We can check the length of any list to count messages.

        # Count how many messages we've received
        # Use task_name list length as the count (since each message has a task_name)
        received_count = 0
        if "task_name" in kwargs and isinstance(kwargs["task_name"], list):
            received_count = len(kwargs["task_name"])
        elif "results" in kwargs and isinstance(kwargs["results"], list):
            # If task_name not available, use results list length
            received_count = len(kwargs["results"])
        elif "query" in kwargs and isinstance(kwargs["query"], list):
            received_count = len(kwargs["query"])
        else:
            # Fallback: count any list field
            for key, value in kwargs.items():
                if isinstance(value, list) and value:
                    received_count = len(value)
                    break

        expected_count = self.get_config("expected_count", self.expected_count)

        # Get current task_name from kwargs if available
        current_task = kwargs.get("task_name", "unknown")
        if isinstance(current_task, list) and current_task:
            current_task = current_task[-1]  # Get last one

        print(
            f"Aggregator received message from {current_task}. "
            f"Total received: {received_count}/{expected_count}"
        )

        # Check if we've received all expected messages
        if received_count >= expected_count:
            print(f"✅ All {expected_count} messages received! Processing aggregated results...")

            # Process all accumulated data (kwargs contains the merged data)
            self._process_aggregated_results(kwargs)

            # Reset for next aggregation (optional)
            self.input_slot._data = {}
        else:
            print(f"⏳ Waiting for more messages ({received_count}/{expected_count})...")

    def _process_aggregated_results(self, accumulated_data: dict):
        """Process all aggregated results and emit.

        Args:
            accumulated_data: Dictionary with accumulated data. With append strategy,
                values are lists containing all received values.
        """
        # Track operation
        self._track_operation("aggregations", success=True)

        # Extract all results
        all_results = []
        queries = []
        task_names = []

        if "results" in accumulated_data:
            # results is a list of lists (each search task's results)
            results_list = accumulated_data["results"]
            if isinstance(results_list, list):
                for result_list in results_list:
                    if isinstance(result_list, list):
                        all_results.extend(result_list)
                    else:
                        all_results.append(result_list)

        if "query" in accumulated_data:
            query_list = accumulated_data["query"]
            queries = query_list if isinstance(query_list, list) else [query_list]

        if "task_name" in accumulated_data:
            task_name_list = accumulated_data["task_name"]
            task_names = task_name_list if isinstance(task_name_list, list) else [task_name_list]

        print(f"📊 Aggregated {len(all_results)} results from {len(task_names)} search tasks")

        # Emit aggregated result
        self.emit(
            "aggregated", all_results=all_results, total_count=len(all_results), queries=queries
        )

        # Reset for next aggregation (optional)
        # self.input_slot._data = {}


def demo_aggregator():
    """Demonstrate aggregator routine."""
    print("=" * 70)
    print("Aggregator Routine Demo")
    print("=" * 70)

    # Create flow
    flow = Flow(flow_id="aggregator_demo")

    # Create search tasks
    search1 = SearchTask("SearchEngine1")
    search2 = SearchTask("SearchEngine2")
    search3 = SearchTask("SearchEngine3")

    # Create aggregator (expects 3 results)
    aggregator = ResultAggregator(expected_count=3)

    # Add to flow
    id1 = flow.add_routine(search1, "search1")
    id2 = flow.add_routine(search2, "search2")
    id3 = flow.add_routine(search3, "search3")
    agg_id = flow.add_routine(aggregator, "aggregator")

    # Connect all search tasks to aggregator
    flow.connect(id1, "result", agg_id, "input")
    flow.connect(id2, "result", agg_id, "input")
    flow.connect(id3, "result", agg_id, "input")

    # Create a consumer to receive aggregated results
    class ResultConsumer(Routine):
        def __init__(self):
            super().__init__()
            self.received_results = []
            self.input_slot = self.define_slot("input", handler=self._handle_input)

        def _handle_input(self, all_results: list = None, total_count: int = None, **kwargs):
            self.received_results.append({"results": all_results, "count": total_count})
            print(f"📦 Consumer received aggregated result: {total_count} total results")

    consumer = ResultConsumer()
    consumer_id = flow.add_routine(consumer, "consumer")
    flow.connect(agg_id, "aggregated", consumer_id, "input")

    print("\nFlow structure:")
    print("  search1 -> aggregator -> consumer")
    print("  search2 -> aggregator")
    print("  search3 -> aggregator")
    print("\nAggregator expects: 3 messages")

    # Execute all search tasks
    print("\n🚀 Executing all search tasks...")
    flow.execute(id1, entry_params={"query": "test query"})
    flow.execute(id2, entry_params={"query": "test query"})
    flow.execute(id3, entry_params={"query": "test query"})

    # Wait a bit for all messages to arrive
    time.sleep(0.5)

    print("\n" + "=" * 70)
    print("Results:")
    print(f"  Aggregator stats: {aggregator.stats()}")
    print(f"  Consumer received: {len(consumer.received_results)} aggregated result(s)")
    if consumer.received_results:
        print(f"  Total results in aggregation: {consumer.received_results[0]['count']}")
    print("=" * 70)


if __name__ == "__main__":
    demo_aggregator()
