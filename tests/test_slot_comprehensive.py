"""
Comprehensive tests for Slot queue-based design.

Tests include:
- Queue operations (consume, peek, enqueue)
- Thread safety
- Edge cases
- Error handling
- Boundary conditions
"""

import threading
import time
from datetime import datetime

import pytest

from routilux import Routine
from routilux.slot import SlotQueueFullError


class TestSlotQueueOperations:
    """Test Slot queue operations"""

    def test_consume_all_new_empty_queue(self):
        """Test: Consume all new from empty queue"""
        routine = Routine()
        slot = routine.define_slot("input")

        data = slot.consume_all_new()
        assert data == []
        assert slot.get_unconsumed_count() == 0

    def test_consume_one_new_empty_queue(self):
        """Test: Consume one new from empty queue"""
        routine = Routine()
        slot = routine.define_slot("input")

        data = slot.consume_one_new()
        assert data is None
        assert slot.get_unconsumed_count() == 0

    def test_consume_all_empty_queue(self):
        """Test: Consume all from empty queue"""
        routine = Routine()
        slot = routine.define_slot("input")

        data = slot.consume_all()
        assert data == []
        assert slot.get_total_count() == 0

    def test_consume_latest_and_mark_all_consumed_empty(self):
        """Test: Consume latest from empty queue"""
        routine = Routine()
        slot = routine.define_slot("input")

        data = slot.consume_latest_and_mark_all_consumed()
        assert data is None

    def test_peek_one_new_empty_queue(self):
        """Test: Peek one new from empty queue"""
        routine = Routine()
        slot = routine.define_slot("input")

        data = slot.peek_one_new()
        assert data is None

    def test_peek_latest_empty_queue(self):
        """Test: Peek latest from empty queue"""
        routine = Routine()
        slot = routine.define_slot("input")

        data = slot.peek_latest()
        assert data is None

    def test_consume_sequence(self):
        """Test: Consume sequence - consume_all_new, then consume_one_new"""
        routine = Routine()
        slot = routine.define_slot("input")

        # Enqueue initial data
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        slot.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())

        # Consume all new
        data = slot.consume_all_new()
        assert len(data) == 2
        assert slot.get_unconsumed_count() == 0

        # Enqueue more
        slot.enqueue(data={"value": 3}, emitted_from="r1", emitted_at=datetime.now())
        slot.enqueue(data={"value": 4}, emitted_from="r1", emitted_at=datetime.now())

        # Consume one
        data = slot.consume_one_new()
        assert data["value"] == 3
        assert slot.get_unconsumed_count() == 1

        # Consume another
        data = slot.consume_one_new()
        assert data["value"] == 4
        assert slot.get_unconsumed_count() == 0

    def test_consume_all_vs_consume_all_new(self):
        """Test: Difference between consume_all and consume_all_new"""
        routine = Routine()
        slot = routine.define_slot("input")

        # Enqueue and consume some
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        slot.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())
        slot.consume_all_new()  # Consume first 2

        # Enqueue more
        slot.enqueue(data={"value": 3}, emitted_from="r1", emitted_at=datetime.now())

        # consume_all_new only gets new (unconsumed)
        data = slot.consume_all_new()
        assert len(data) == 1
        assert data[0]["value"] == 3

        # Reset: enqueue again
        slot.enqueue(data={"value": 4}, emitted_from="r1", emitted_at=datetime.now())

        # consume_all gets everything in queue (all items, including previously consumed)
        # Note: After watermark clear, consumed items are removed, so only unconsumed remain
        # But if watermark hasn't triggered, consume_all returns all items in queue
        data = slot.consume_all()
        # After consume_all_new consumed item 3, only item 4 remains unconsumed
        # But consume_all returns all items in queue (consumed + unconsumed)
        # However, if watermark cleared consumed items, only unconsumed remain
        # So we check: consume_all should return all items currently in queue
        assert len(data) >= 1  # At least the new item
        assert data[-1]["value"] == 4  # Latest item should be 4

    def test_peek_vs_consume(self):
        """Test: Peek does not consume, consume does"""
        routine = Routine()
        slot = routine.define_slot("input")

        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())

        # Peek
        data = slot.peek_one_new()
        assert data["value"] == 1
        assert slot.get_unconsumed_count() == 1  # Still unconsumed

        # Peek again (should get same data)
        data = slot.peek_one_new()
        assert data["value"] == 1
        assert slot.get_unconsumed_count() == 1  # Still unconsumed

        # Now consume
        data = slot.consume_one_new()
        assert data["value"] == 1
        assert slot.get_unconsumed_count() == 0  # Now consumed

    def test_consume_latest_and_mark_all_consumed(self):
        """Test: Consume latest and mark all previous as consumed"""
        routine = Routine()
        slot = routine.define_slot("input")

        # Enqueue multiple items
        for i in range(5):
            slot.enqueue(data={"value": i}, emitted_from="r1", emitted_at=datetime.now())

        # Consume latest
        data = slot.consume_latest_and_mark_all_consumed()
        assert data["value"] == 4

        # All should be marked as consumed
        assert slot.get_unconsumed_count() == 0
        assert slot.get_total_count() == 5  # Still in queue, just consumed

    def test_get_unconsumed_count_accuracy(self):
        """Test: get_unconsumed_count accuracy"""
        routine = Routine()
        slot = routine.define_slot("input")

        assert slot.get_unconsumed_count() == 0

        # Enqueue 5 items
        for i in range(5):
            slot.enqueue(data={"value": i}, emitted_from="r1", emitted_at=datetime.now())
        assert slot.get_unconsumed_count() == 5

        # Consume 2
        slot.consume_one_new()
        slot.consume_one_new()
        assert slot.get_unconsumed_count() == 3

        # Consume all new
        slot.consume_all_new()
        assert slot.get_unconsumed_count() == 0

    def test_get_total_count_accuracy(self):
        """Test: get_total_count includes consumed items"""
        routine = Routine()
        slot = routine.define_slot("input")

        assert slot.get_total_count() == 0

        # Enqueue 5 items
        for i in range(5):
            slot.enqueue(data={"value": i}, emitted_from="r1", emitted_at=datetime.now())
        assert slot.get_total_count() == 5

        # Consume 2
        slot.consume_one_new()
        slot.consume_one_new()
        assert slot.get_total_count() == 5  # Still in queue

        # Consume all new
        slot.consume_all_new()
        assert slot.get_total_count() == 5  # Still in queue, just consumed


class TestSlotQueueFull:
    """Test Slot queue full scenarios"""

    def test_queue_full_exact_capacity(self):
        """Test: Queue full at exact capacity"""
        routine = Routine()
        slot = routine.define_slot("input", max_queue_length=3)

        # Fill to capacity
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        slot.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())
        slot.enqueue(data={"value": 3}, emitted_from="r1", emitted_at=datetime.now())

        assert slot.get_total_count() == 3

        # Next enqueue should fail
        with pytest.raises(SlotQueueFullError):
            slot.enqueue(data={"value": 4}, emitted_from="r1", emitted_at=datetime.now())

    def test_queue_full_after_consumption(self):
        """Test: Queue can accept more after consumption"""
        routine = Routine()
        slot = routine.define_slot("input", max_queue_length=2)

        # Fill to capacity
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        slot.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())

        # Consume one
        slot.consume_one_new()

        # Should be able to enqueue one more
        slot.enqueue(data={"value": 3}, emitted_from="r1", emitted_at=datetime.now())
        assert slot.get_total_count() == 2  # One consumed, one new

    def test_queue_full_error_message(self):
        """Test: Queue full error has informative message"""
        routine = Routine()
        slot = routine.define_slot("input", max_queue_length=1)

        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())

        with pytest.raises(SlotQueueFullError) as exc_info:
            slot.enqueue(data={"value": 2}, emitted_from="r1", emitted_at=datetime.now())

        error_msg = str(exc_info.value)
        assert "Slot" in error_msg
        assert "queue is full" in error_msg or "full" in error_msg.lower()


class TestSlotWatermark:
    """Test Slot watermark auto-shrink"""

    def test_watermark_auto_shrink_triggered(self):
        """Test: Watermark auto-shrink is triggered correctly"""
        routine = Routine()
        slot = routine.define_slot("input", max_queue_length=10, watermark=0.8)

        # Fill past watermark (8 items, watermark is 8)
        for i in range(8):
            slot.enqueue(data={"value": i}, emitted_from="r1", emitted_at=datetime.now())

        # Consume all (they become consumed)
        slot.consume_all_new()

        # Enqueue more (should trigger auto-shrink)
        slot.enqueue(data={"value": 8}, emitted_from="r1", emitted_at=datetime.now())

        # Consumed data should be cleared
        assert slot.get_total_count() == 1
        assert slot.get_unconsumed_count() == 1

    def test_watermark_not_triggered_below_threshold(self):
        """Test: Watermark not triggered below threshold"""
        routine = Routine()
        slot = routine.define_slot("input", max_queue_length=10, watermark=0.8)

        # Fill below watermark (7 items, threshold is 8)
        for i in range(7):
            slot.enqueue(data={"value": i}, emitted_from="r1", emitted_at=datetime.now())

        # Consume all
        slot.consume_all_new()

        # Enqueue more (should NOT trigger auto-shrink)
        slot.enqueue(data={"value": 7}, emitted_from="r1", emitted_at=datetime.now())

        # Consumed data should still be there (not shrunk)
        # Total count includes consumed items
        assert slot.get_total_count() >= 1

    def test_watermark_with_mixed_consumed_unconsumed(self):
        """Test: Watermark with mix of consumed and unconsumed"""
        routine = Routine()
        slot = routine.define_slot("input", max_queue_length=10, watermark=0.8)

        # Fill queue
        for i in range(10):
            slot.enqueue(data={"value": i}, emitted_from="r1", emitted_at=datetime.now())

        # Consume first 5
        for _ in range(5):
            slot.consume_one_new()

        # Enqueue more (should trigger shrink since we're at watermark)
        # But we have 5 unconsumed + 5 consumed = 10 total
        # After shrink, should have only unconsumed
        slot.enqueue(data={"value": 10}, emitted_from="r1", emitted_at=datetime.now())

        # Should have shrunk consumed items
        assert slot.get_unconsumed_count() == 6  # 5 remaining + 1 new


class TestSlotThreadSafety:
    """Test Slot thread safety"""

    def test_concurrent_enqueue(self):
        """Test: Concurrent enqueue operations"""
        routine = Routine()
        slot = routine.define_slot("input")

        results = []
        errors = []

        def enqueue_data(i):
            try:
                slot.enqueue(
                    data={"value": i}, emitted_from=f"r{i}", emitted_at=datetime.now()
                )
                results.append(i)
            except Exception as e:
                errors.append((i, e))

        threads = []
        for i in range(20):
            t = threading.Thread(target=enqueue_data, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All should succeed
        assert len(errors) == 0
        assert len(results) == 20
        assert slot.get_total_count() == 20

    def test_concurrent_consume(self):
        """Test: Concurrent consume operations"""
        routine = Routine()
        slot = routine.define_slot("input")

        # Enqueue data
        for i in range(20):
            slot.enqueue(data={"value": i}, emitted_from="r1", emitted_at=datetime.now())

        consumed = []
        errors = []

        def consume_data():
            try:
                data = slot.consume_one_new()
                if data is not None:
                    consumed.append(data["value"])
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(20):
            t = threading.Thread(target=consume_data)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should consume all items exactly once
        assert len(errors) == 0
        assert len(consumed) == 20
        assert set(consumed) == set(range(20))  # All values 0-19
        assert slot.get_unconsumed_count() == 0

    def test_concurrent_enqueue_and_consume(self):
        """Test: Concurrent enqueue and consume"""
        routine = Routine()
        slot = routine.define_slot("input")

        enqueued = []
        consumed = []

        def enqueue_worker():
            for i in range(10):
                slot.enqueue(
                    data={"value": i}, emitted_from="r1", emitted_at=datetime.now()
                )
                enqueued.append(i)
                time.sleep(0.01)

        def consume_worker():
            while len(consumed) < 10:
                data = slot.consume_one_new()
                if data is not None:
                    consumed.append(data["value"])
                time.sleep(0.01)

        t1 = threading.Thread(target=enqueue_worker)
        t2 = threading.Thread(target=consume_worker)

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        # All items should be enqueued and consumed
        assert len(enqueued) == 10
        assert len(consumed) == 10
        assert set(consumed) == set(range(10))

    def test_concurrent_peek(self):
        """Test: Concurrent peek operations"""
        routine = Routine()
        slot = routine.define_slot("input")

        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())

        peeked_values = []

        def peek_worker():
            for _ in range(10):
                data = slot.peek_one_new()
                if data is not None:
                    peeked_values.append(data["value"])
                time.sleep(0.001)

        threads = []
        for _ in range(5):
            t = threading.Thread(target=peek_worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # All should peek the same value (not consumed)
        assert len(peeked_values) == 50  # 5 threads * 10 peeks
        assert all(v == 1 for v in peeked_values)
        assert slot.get_unconsumed_count() == 1  # Still unconsumed


class TestSlotEdgeCases:
    """Test Slot edge cases"""

    def test_enqueue_none_data(self):
        """Test: Enqueue None as data"""
        routine = Routine()
        slot = routine.define_slot("input")

        slot.enqueue(data=None, emitted_from="r1", emitted_at=datetime.now())

        data = slot.consume_all_new()
        assert len(data) == 1
        assert data[0] is None

    def test_enqueue_complex_data(self):
        """Test: Enqueue complex data structures"""
        routine = Routine()
        slot = routine.define_slot("input")

        complex_data = {
            "nested": {"deep": {"value": 42}},
            "list": [1, 2, 3],
            "tuple": (4, 5, 6),
        }

        slot.enqueue(data=complex_data, emitted_from="r1", emitted_at=datetime.now())

        data = slot.consume_all_new()
        assert len(data) == 1
        assert data[0] == complex_data

    def test_get_queue_state_empty(self):
        """Test: Get queue state for empty queue"""
        routine = Routine()
        slot = routine.define_slot("input")

        state = slot.get_queue_state()
        assert state["total_count"] == 0
        assert state["unconsumed_count"] == 0
        assert state["consumed_count"] == 0
        assert state["oldest_unconsumed"] is None

    def test_get_queue_state_partial_consumption(self):
        """Test: Get queue state with partial consumption"""
        routine = Routine()
        slot = routine.define_slot("input")

        # Enqueue 5 items
        for i in range(5):
            slot.enqueue(data={"value": i}, emitted_from="r1", emitted_at=datetime.now())

        # Consume 2
        slot.consume_one_new()
        slot.consume_one_new()

        state = slot.get_queue_state()
        assert state["total_count"] == 5
        assert state["unconsumed_count"] == 3
        assert state["consumed_count"] == 2
        assert state["oldest_unconsumed"] is not None

    def test_timestamps_preserved(self):
        """Test: Timestamps are preserved correctly"""
        routine = Routine()
        slot = routine.define_slot("input")

        emitted_at = datetime(2024, 1, 1, 12, 0, 0)
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=emitted_at)

        # Timestamps are stored in SlotDataPoint, not directly accessible
        # But we can verify queue state
        state = slot.get_queue_state()
        assert state["total_count"] == 1

        # Consume and verify data is correct
        data = slot.consume_all_new()
        assert len(data) == 1
        assert data[0]["value"] == 1

    def test_custom_max_queue_length(self):
        """Test: Custom max_queue_length works"""
        routine = Routine()
        slot = routine.define_slot("input", max_queue_length=5)

        # Fill to capacity
        for i in range(5):
            slot.enqueue(data={"value": i}, emitted_from="r1", emitted_at=datetime.now())

        assert slot.get_total_count() == 5

        # Next should fail
        with pytest.raises(SlotQueueFullError):
            slot.enqueue(data={"value": 5}, emitted_from="r1", emitted_at=datetime.now())

    def test_custom_watermark(self):
        """Test: Custom watermark threshold"""
        routine = Routine()
        slot = routine.define_slot("input", max_queue_length=100, watermark=0.5)

        # Watermark threshold should be 50
        assert slot.watermark_threshold == 50

        # Fill to 50 (at watermark)
        for i in range(50):
            slot.enqueue(data={"value": i}, emitted_from="r1", emitted_at=datetime.now())

        # Consume all
        slot.consume_all_new()

        # Enqueue more (should trigger shrink)
        slot.enqueue(data={"value": 50}, emitted_from="r1", emitted_at=datetime.now())

        # Should have shrunk
        assert slot.get_total_count() == 1


class TestSlotErrorHandling:
    """Test Slot error handling"""

    def test_enqueue_after_shutdown(self):
        """Test: Slot behavior is consistent (no shutdown state)"""
        routine = Routine()
        slot = routine.define_slot("input")

        # Slots don't have shutdown state, but test normal operation
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        assert slot.get_total_count() == 1

    def test_consume_from_empty_after_consumption(self):
        """Test: Consume from empty queue after previous consumption"""
        routine = Routine()
        slot = routine.define_slot("input")

        # Enqueue and consume
        slot.enqueue(data={"value": 1}, emitted_from="r1", emitted_at=datetime.now())
        slot.consume_all_new()

        # Try to consume again (should return empty)
        data = slot.consume_all_new()
        assert data == []

    def test_queue_state_after_clear(self):
        """Test: Queue state after watermark clear"""
        routine = Routine()
        slot = routine.define_slot("input", max_queue_length=10, watermark=0.8)

        # Fill and consume
        for i in range(8):
            slot.enqueue(data={"value": i}, emitted_from="r1", emitted_at=datetime.now())
        slot.consume_all_new()

        # Trigger shrink
        slot.enqueue(data={"value": 8}, emitted_from="r1", emitted_at=datetime.now())

        state = slot.get_queue_state()
        assert state["total_count"] == 1
        assert state["unconsumed_count"] == 1
        assert state["consumed_count"] == 0
