"""
Slot test cases for new queue-based design.
"""

from datetime import datetime

from routilux import Routine
from routilux.slot import SlotQueueFullError


class TestSlotConnection:
    """Slot connection management tests"""

    def test_connect_to_event(self):
        """Test: Connect to Event"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        # Connect
        slot.connect(event)

        # Verify connection
        assert event in slot.connected_events
        assert slot in event.connected_slots

    def test_disconnect_from_event(self):
        """Test: Disconnect from Event"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output")
        slot = routine.define_slot("input")

        # Connect
        slot.connect(event)
        assert event in slot.connected_events

        # Disconnect
        slot.disconnect(event)
        assert event not in slot.connected_events
        assert slot not in event.connected_slots

    def test_multiple_events_to_slot(self):
        """Test: Multiple events to one slot"""
        routine1 = Routine()
        routine = Routine()
        routine3 = Routine()

        event1 = routine1.define_event("output1")
        event2 = routine.define_event("output2")
        slot = routine3.define_slot("input")

        # Connect multiple events
        slot.connect(event1)
        slot.connect(event2)

        # Verify
        assert len(slot.connected_events) == 2
        assert event1 in slot.connected_events
        assert event2 in slot.connected_events


class TestSlotQueue:
    """Slot queue management tests"""

    def test_enqueue_data(self):
        """Test: Enqueue data to slot"""
        routine = Routine()
        slot = routine.define_slot("input")

        # Enqueue data
        slot.enqueue(
            data={"value": "test"},
            emitted_from="routine_a",
            emitted_at=datetime.now(),
        )

        # Verify data is in queue
        assert slot.get_total_count() == 1
        assert slot.get_unconsumed_count() == 1

    def test_consume_all_new(self):
        """Test: Consume all new data"""
        routine = Routine()
        slot = routine.define_slot("input")

        # Enqueue multiple items
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        slot.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())
        slot.enqueue(data={"value": 3}, emitted_from="r1", emitted_at=datetime.now())

        # Consume all new
        data = slot.consume_all_new()

        # Verify
        assert len(data) == 3
        assert data[0]["value"] == 1
        assert data[1]["value"] == 2
        assert data[2]["value"] == 3
        assert slot.get_unconsumed_count() == 0

    def test_consume_one_new(self):
        """Test: Consume one new data point"""
        routine = Routine()
        slot = routine.define_slot("input")

        # Enqueue multiple items
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        slot.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())

        # Consume one
        data = slot.consume_one_new()

        # Verify
        assert data["value"] == 1
        assert slot.get_unconsumed_count() == 1

        # Consume another
        data = slot.consume_one_new()
        assert data["value"] == 2
        assert slot.get_unconsumed_count() == 0

    def test_peek_without_consuming(self):
        """Test: Peek at data without consuming"""
        routine = Routine()
        slot = routine.define_slot("input")

        # Enqueue data
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        slot.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())

        # Peek
        data = slot.peek_one_new()
        assert data["value"] == 1
        assert slot.get_unconsumed_count() == 2  # Still unconsumed

        # Peek all
        all_data = slot.peek_all_new()
        assert len(all_data) == 2
        assert slot.get_unconsumed_count() == 2  # Still unconsumed

    def test_queue_full_error(self):
        """Test: Queue full error"""
        routine = Routine()
        slot = routine.define_slot("input", max_queue_length=2)

        # Fill queue
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        slot.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())

        # Try to enqueue more (should raise error)
        try:
            slot.enqueue(data={"value": 3}, emitted_from="r1", emitted_at=datetime.now())
            assert False, "Should have raised SlotQueueFullError"
        except SlotQueueFullError:
            pass  # Expected

    def test_watermark_auto_shrink(self):
        """Test: Watermark auto-shrink"""
        routine = Routine()
        slot = routine.define_slot("input", max_queue_length=10, watermark=0.8)

        # Fill queue past watermark
        for i in range(8):
            slot.enqueue(data={"value": i}, emitted_from="r1", emitted_at=datetime.now())

        # Consume some
        slot.consume_all_new()

        # Enqueue more (should trigger auto-shrink)
        slot.enqueue(data={"value": 8}, emitted_from="r1", emitted_at=datetime.now())
        assert slot.get_total_count() == 1  # Consumed data should be cleared

    def test_get_queue_state(self):
        """Test: Get queue state"""
        routine = Routine()
        slot = routine.define_slot("input")

        # Enqueue data
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        slot.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())

        # Get state
        state = slot.get_queue_state()

        # Verify state
        assert state["total_count"] == 2
        assert state["unconsumed_count"] == 2
        assert state["consumed_count"] == 0
        assert state["max_length"] == 1000

    def test_timestamps(self):
        """Test: Data points have timestamps"""
        routine = Routine()
        slot = routine.define_slot("input")

        emitted_at = datetime.now()
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=emitted_at)

        # Consume and verify timestamps are preserved
        data = slot.consume_all_new()
        assert len(data) == 1

        # Check queue state for timestamp info
        state = slot.get_queue_state()
        assert state["oldest_unconsumed"] is None  # All consumed
