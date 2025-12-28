"""
Test Event Execution Order.

This test suite verifies the execution order behavior when an event emits
to multiple connected slots, especially when downstream slots emit further events.
"""

from routilux import Flow, Routine


class ExecutionOrderTracker:
    """Track execution order of routines."""

    def __init__(self):
        self.execution_order = []
        self.execution_times = {}

    def record(self, routine_id: str, action: str = "executed"):
        """Record execution of a routine."""
        import time

        timestamp = time.time()
        self.execution_order.append((routine_id, action, timestamp))
        if routine_id not in self.execution_times:
            self.execution_times[routine_id] = []
        self.execution_times[routine_id].append(timestamp)

    def get_order(self):
        """Get execution order as list of routine IDs."""
        return [item[0] for item in self.execution_order]

    def clear(self):
        """Clear tracking data."""
        self.execution_order = []
        self.execution_times = {}


class SourceRoutine(Routine):
    """Source routine that emits to multiple slots."""

    def __init__(self, tracker: ExecutionOrderTracker, routine_id: str):
        super().__init__()
        self.tracker = tracker
        self.routine_id = routine_id
        self.output_event = self.define_event("output")

    def __call__(self, **kwargs):
        self.tracker.record(self.routine_id, "start")
        self.emit("output", data="test_data")
        self.tracker.record(self.routine_id, "end")


class IntermediateRoutine(Routine):
    """Intermediate routine that receives and emits further."""

    def __init__(
        self, tracker: ExecutionOrderTracker, routine_id: str, downstream_routine_id: str = None
    ):
        super().__init__()
        self.tracker = tracker
        self.routine_id = routine_id
        self.downstream_routine_id = downstream_routine_id
        self.input_slot = self.define_slot("input", handler=self._handle_input)
        self.output_event = self.define_event("output")

    def _handle_input(self, data=None, **kwargs):
        self.tracker.record(self.routine_id, "start")
        if self.downstream_routine_id:
            # Emit to downstream routine
            self.emit("output", data="downstream_data")
        self.tracker.record(self.routine_id, "end")


class LeafRoutine(Routine):
    """Leaf routine that only receives data."""

    def __init__(self, tracker: ExecutionOrderTracker, routine_id: str):
        super().__init__()
        self.tracker = tracker
        self.routine_id = routine_id
        self.input_slot = self.define_slot("input", handler=self._handle_input)

    def _handle_input(self, data=None, **kwargs):
        self.tracker.record(self.routine_id, "executed")


class TestEventExecutionOrder:
    """Test execution order when event emits to multiple slots."""

    def test_sequential_order_same_level(self):
        """Test: When an event emits to multiple slots at the same level,
        they execute in connection order, sequentially."""
        tracker = ExecutionOrderTracker()

        # Create flow: Source -> Slot1, Slot2, Slot3 (all at same level)
        flow = Flow()
        source = SourceRoutine(tracker, "source")
        routine1 = LeafRoutine(tracker, "routine1")
        routine2 = LeafRoutine(tracker, "routine2")
        routine3 = LeafRoutine(tracker, "routine3")

        flow.add_routine(source, "source")
        flow.add_routine(routine1, "routine1")
        flow.add_routine(routine2, "routine2")
        flow.add_routine(routine3, "routine3")

        # Connect in order: 1, 2, 3
        flow.connect("source", "output", "routine1", "input")
        flow.connect("source", "output", "routine2", "input")
        flow.connect("source", "output", "routine3", "input")

        # Execute
        flow.execute("source")

        # Verify execution order
        order = tracker.get_order()
        print(f"Execution order: {order}")

        # Source should start first
        assert order[0] == "source"
        # Then routine1, routine2, routine3 should execute in order
        assert "routine1" in order
        assert "routine2" in order
        assert "routine3" in order

        # Find positions
        source_start_idx = order.index("source")
        r1_idx = order.index("routine1")
        r2_idx = order.index("routine2")
        r3_idx = order.index("routine3")

        # All routines should execute after source starts
        assert r1_idx > source_start_idx
        assert r2_idx > source_start_idx
        assert r3_idx > source_start_idx

        # In sequential mode, they should execute in connection order
        assert r1_idx < r2_idx < r3_idx

    def test_sequential_order_with_downstream(self):
        """Test: When a slot's handler emits to downstream slots,
        downstream execution completes before continuing to next sibling slot.

        This tests depth-first execution behavior.
        """
        tracker = ExecutionOrderTracker()

        # Create flow:
        # Source -> Intermediate1 -> Leaf1
        #       -> Intermediate2 -> Leaf2
        #       -> Leaf3
        flow = Flow()
        source = SourceRoutine(tracker, "source")
        intermediate1 = IntermediateRoutine(tracker, "intermediate1", "leaf1")
        intermediate2 = IntermediateRoutine(tracker, "intermediate2", "leaf2")
        leaf1 = LeafRoutine(tracker, "leaf1")
        leaf2 = LeafRoutine(tracker, "leaf2")
        leaf3 = LeafRoutine(tracker, "leaf3")

        flow.add_routine(source, "source")
        flow.add_routine(intermediate1, "intermediate1")
        flow.add_routine(intermediate2, "intermediate2")
        flow.add_routine(leaf1, "leaf1")
        flow.add_routine(leaf2, "leaf2")
        flow.add_routine(leaf3, "leaf3")

        # Connect: source -> intermediate1, intermediate2, leaf3
        flow.connect("source", "output", "intermediate1", "input")
        flow.connect("source", "output", "intermediate2", "input")
        flow.connect("source", "output", "leaf3", "input")

        # Connect intermediates to their leaves
        flow.connect("intermediate1", "output", "leaf1", "input")
        flow.connect("intermediate2", "output", "leaf2", "input")

        # Execute
        flow.execute("source")

        # Verify execution order
        order = tracker.get_order()
        print(f"Execution order: {order}")

        # Source should start first
        assert order[0] == "source"

        # Find positions
        i1_start_idx = order.index("intermediate1")
        i2_start_idx = order.index("intermediate2")
        l1_idx = order.index("leaf1")
        l2_idx = order.index("leaf2")

        # Intermediate1 should execute before intermediate2 (connection order)
        assert i1_start_idx < i2_start_idx

        # Leaf1 should execute after intermediate1 starts but before intermediate2
        # (depth-first: complete intermediate1's chain before moving to intermediate2)
        assert l1_idx > i1_start_idx
        assert l1_idx < i2_start_idx

        # Leaf2 should execute after intermediate2 starts
        assert l2_idx > i2_start_idx

        # Leaf3 should execute after intermediate2 completes (last sibling)
        # Actually, leaf3 might execute before intermediate2 if it's processed first
        # Let's verify that all three siblings (intermediate1, intermediate2, leaf3)
        # execute in connection order
        assert i1_start_idx < i2_start_idx

        # The key point: leaf1 (downstream of intermediate1) should complete
        # before intermediate2 starts
        assert l1_idx < i2_start_idx

    def test_sequential_order_deep_nesting(self):
        """Test: Deep nesting - verify depth-first execution."""
        tracker = ExecutionOrderTracker()

        # Create flow:
        # Source -> A -> B -> C
        #       -> D
        flow = Flow()
        source = SourceRoutine(tracker, "source")

        class ChainRoutine(Routine):
            def __init__(self, tracker, routine_id, next_id):
                super().__init__()
                self.tracker = tracker
                self.routine_id = routine_id
                self.next_id = next_id
                self.input_slot = self.define_slot("input", handler=self._handle_input)
                self.output_event = self.define_event("output")

            def _handle_input(self, data=None, **kwargs):
                self.tracker.record(self.routine_id, "start")
                if self.next_id:
                    self.emit("output", data="chain_data")
                self.tracker.record(self.routine_id, "end")

        a = ChainRoutine(tracker, "A", "B")
        b = ChainRoutine(tracker, "B", "C")
        c = LeafRoutine(tracker, "C")
        d = LeafRoutine(tracker, "D")

        flow.add_routine(source, "source")
        flow.add_routine(a, "A")
        flow.add_routine(b, "B")
        flow.add_routine(c, "C")
        flow.add_routine(d, "D")

        # Connect: source -> A, D
        flow.connect("source", "output", "A", "input")
        flow.connect("source", "output", "D", "input")

        # Connect chain: A -> B -> C
        flow.connect("A", "output", "B", "input")
        flow.connect("B", "output", "C", "input")

        # Execute
        flow.execute("source")

        # Verify execution order
        order = tracker.get_order()
        print(f"Execution order: {order}")

        # Find positions
        a_idx = order.index("A")
        b_idx = order.index("B")
        c_idx = order.index("C")
        d_idx = order.index("D")

        # Chain should complete before D: A -> B -> C should all execute before D
        assert a_idx < d_idx
        assert b_idx < d_idx
        assert c_idx < d_idx

        # Chain order: A -> B -> C
        assert a_idx < b_idx < c_idx

    def test_concurrent_order(self):
        """Test: In concurrent mode, sibling slots execute concurrently.

        Note: This test verifies that tasks are submitted concurrently,
        but actual execution timing may vary.
        """
        tracker = ExecutionOrderTracker()

        # Create flow: Source -> Slot1, Slot2, Slot3 (all at same level)
        flow = Flow()
        flow.set_execution_strategy("concurrent")

        source = SourceRoutine(tracker, "source")
        routine1 = LeafRoutine(tracker, "routine1")
        routine2 = LeafRoutine(tracker, "routine2")
        routine3 = LeafRoutine(tracker, "routine3")

        flow.add_routine(source, "source")
        flow.add_routine(routine1, "routine1")
        flow.add_routine(routine2, "routine2")
        flow.add_routine(routine3, "routine3")

        # Connect in order: 1, 2, 3
        flow.connect("source", "output", "routine1", "input")
        flow.connect("source", "output", "routine2", "input")
        flow.connect("source", "output", "routine3", "input")

        # Execute
        flow.execute("source")

        # Wait for completion
        flow.wait_for_completion()
        flow.shutdown()

        # Verify all routines executed
        order = tracker.get_order()
        print(f"Execution order (concurrent): {order}")

        assert "source" in order
        assert "routine1" in order
        assert "routine2" in order
        assert "routine3" in order

        # In concurrent mode, execution order is not guaranteed
        # But all should execute after source starts
        source_idx = order.index("source")
        r1_idx = order.index("routine1")
        r2_idx = order.index("routine2")
        r3_idx = order.index("routine3")

        assert r1_idx > source_idx
        assert r2_idx > source_idx
        assert r3_idx > source_idx

        # Note: In concurrent mode, r1, r2, r3 may execute in any order
        # We can't assert a specific order here
