#!/usr/bin/env python
"""Async Task Orchestration Example.

This example demonstrates concurrent task execution:
1. Execute multiple independent tasks in parallel
2. Aggregate results from concurrent tasks
3. Handle timeouts and retries
"""

from routilux import Flow, Routine
from routilux.job_state import JobState
import time


class UserFetcher(Routine):
    """Fetches user profile data."""

    def __init__(self):
        super().__init__()
        self.define_slot("trigger", handler=self.fetch_user)
        self.define_event("output", ["user_id", "name", "email"])

    def fetch_user(self, user_id=None, **kwargs):
        """Fetch user data."""
        user_id = user_id if user_id is not None else kwargs.get("user_id", 0)
        time.sleep(0.5)  # Simulate API call
        result = {"user_id": user_id, "name": f"User_{user_id}", "email": f"user{user_id}@example.com"}
        print(f"  [Task 1] Fetched user data: {result['name']}")
        self.emit("output", **result)


class OrdersFetcher(Routine):
    """Fetches user order history."""

    def __init__(self):
        super().__init__()
        self.define_slot("trigger", handler=self.fetch_orders)
        self.define_event("output", ["user_id", "orders", "total"])

    def fetch_orders(self, user_id=None, **kwargs):
        """Fetch order data."""
        user_id = user_id if user_id is not None else kwargs.get("user_id", 0)
        time.sleep(0.7)  # Simulate API call
        result = {"user_id": user_id, "orders": [1, 2, 3], "total": 150.0}
        print(f"  [Task 2] Fetched {len(result['orders'])} orders")
        self.emit("output", **result)


class PreferencesFetcher(Routine):
    """Fetches user preferences."""

    def __init__(self):
        super().__init__()
        self.define_slot("trigger", handler=self.fetch_preferences)
        self.define_event("output", ["user_id", "notifications", "theme"])

    def fetch_preferences(self, user_id=None, **kwargs):
        """Fetch preferences data."""
        user_id = user_id if user_id is not None else kwargs.get("user_id", 0)
        time.sleep(0.3)  # Simulate API call
        result = {"user_id": user_id, "notifications": True, "theme": "dark"}
        print(f"  [Task 3] Fetched preferences")
        self.emit("output", **result)


class ProfileAggregator(Routine):
    """Aggregates profile data from multiple sources."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", handler=self.aggregate, merge_strategy="append")
        self.profile_data = {}
        self.received_count = 0

    def aggregate(self, **kwargs):
        """Aggregate data from all sources."""
        data = dict(kwargs)
        self.received_count += 1

        if "name" in data:
            self.profile_data["user"] = data
            print(f"  [Aggregator] Received user data: {data.get('name')}")
        elif "orders" in data:
            self.profile_data["orders"] = data
            print(f"  [Aggregator] Received orders data")
        elif "notifications" in data:
            self.profile_data["preferences"] = data
            print(f"  [Aggregator] Received preferences data")

        # Check if we have all data (3 sources)
        if self.received_count == 3:
            print("\n  [Aggregator] Profile complete!")
            user_name = self.profile_data.get('user', {}).get('name', 'Unknown')
            orders_data = self.profile_data.get('orders', {})
            orders_list = orders_data.get('orders', [])
            orders_total = orders_data.get('total', 0) if isinstance(orders_data.get('total'), (int, float)) else 0
            theme = self.profile_data.get('preferences', {}).get('theme', 'default')
            print(f"  - User: {user_name}")
            print(f"  - Orders: {len(orders_list) if isinstance(orders_list, list) else 0} items")
            print(f"  - Total: ${float(orders_total):.2f}")
            print(f"  - Theme: {theme}")


def main():
    """Run the async orchestration example."""
    # Create flow with concurrent execution
    flow = Flow("async_orchestration")
    flow.set_execution_strategy("concurrent", max_workers=4)

    # Create routine instances
    user_fetcher = UserFetcher()
    orders_fetcher = OrdersFetcher()
    prefs_fetcher = PreferencesFetcher()
    aggregator = ProfileAggregator()

    # Add routines to flow
    user_id = flow.add_routine(user_fetcher, "fetch_user")
    orders_id = flow.add_routine(orders_fetcher, "fetch_orders")
    prefs_id = flow.add_routine(prefs_fetcher, "fetch_preferences")
    agg_id = flow.add_routine(aggregator, "aggregator")

    # Connect all tasks to aggregator (fan-in pattern)
    flow.connect(user_id, "output", agg_id, "input")
    flow.connect(orders_id, "output", agg_id, "input")
    flow.connect(prefs_id, "output", agg_id, "input")

    # Start execution
    print("\n=== Async Orchestration Example ===\n")
    print("Fetching user profile data from multiple sources in parallel...\n")

    user_id_value = 12345

    # Execute all fetch tasks
    job_state1 = flow.execute(user_id, entry_params={"user_id": user_id_value})
    job_state2 = flow.execute(orders_id, entry_params={"user_id": user_id_value})
    job_state3 = flow.execute(prefs_id, entry_params={"user_id": user_id_value})

    # Wait for completion
    JobState.wait_for_completion(flow, job_state1, timeout=10.0)
    JobState.wait_for_completion(flow, job_state2, timeout=10.0)
    JobState.wait_for_completion(flow, job_state3, timeout=10.0)

    print(f"\nExecution status: {job_state1.status}")
    print(f"Final profile data keys: {list(aggregator.profile_data.keys())}")


if __name__ == "__main__":
    main()
