"""
Comprehensive tests for Slot queue status functionality.

Tests the get_queue_status() method:
- Empty queue status
- Partially filled queue status
- Full queue status
- Pressure level calculation
- Usage percentage calculation
- Thread safety
- Edge cases
"""

import threading
from datetime import datetime

import pytest

from routilux import Routine
from routilux.slot import Slot


class TestSlotQueueStatus:
    """Test Slot queue status functionality"""

    def test_get_queue_status_empty_queue(self):
        """Test: get_queue_status returns correct values for empty queue"""
        routine = Routine()
        slot = routine.define_slot("test_slot", max_queue_length=100, watermark=0.8)

        status = slot.get_queue_status()

        assert status["unconsumed_count"] == 0
        assert status["total_count"] == 0
        assert status["max_length"] == 100
        assert status["watermark_threshold"] == 80
        assert status["usage_percentage"] == 0.0
        assert status["pressure_level"] == "low"
        assert status["is_full"] is False
        assert status["is_near_full"] is False

    def test_get_queue_status_low_usage(self):
        """Test: get_queue_status returns 'low' pressure for low usage"""
        routine = Routine()
        slot = routine.define_slot("test_slot", max_queue_length=100, watermark=0.8)

        # Add 30 items (30% usage, below 60% threshold)
        for i in range(30):
            slot.enqueue(data=i, emitted_from="test", emitted_at=datetime.now())

        status = slot.get_queue_status()

        assert status["unconsumed_count"] == 30
        assert status["total_count"] == 30
        assert status["usage_percentage"] == 0.3
        assert status["pressure_level"] == "low"
        assert status["is_full"] is False
        assert status["is_near_full"] is False

    def test_get_queue_status_medium_usage(self):
        """Test: get_queue_status returns 'medium' pressure for medium usage"""
        routine = Routine()
        slot = routine.define_slot("test_slot", max_queue_length=100, watermark=0.8)

        # Add 70 items (70% usage, between 60% and watermark)
        for i in range(70):
            slot.enqueue(data=i, emitted_from="test", emitted_at=datetime.now())

        status = slot.get_queue_status()

        assert status["unconsumed_count"] == 70
        assert status["total_count"] == 70
        assert status["usage_percentage"] == 0.7
        assert status["pressure_level"] == "medium"
        assert status["is_full"] is False
        assert status["is_near_full"] is False

    def test_get_queue_status_high_usage(self):
        """Test: get_queue_status returns 'high' pressure for high usage (above watermark)"""
        routine = Routine()
        slot = routine.define_slot("test_slot", max_queue_length=100, watermark=0.8)

        # Add 85 items (85% usage, above watermark)
        for i in range(85):
            slot.enqueue(data=i, emitted_from="test", emitted_at=datetime.now())

        status = slot.get_queue_status()

        assert status["unconsumed_count"] == 85
        assert status["total_count"] == 85
        assert status["usage_percentage"] == 0.85
        assert status["pressure_level"] == "high"
        assert status["is_full"] is False
        assert status["is_near_full"] is True

    def test_get_queue_status_critical_usage(self):
        """Test: get_queue_status returns 'critical' pressure for full queue"""
        routine = Routine()
        slot = routine.define_slot("test_slot", max_queue_length=100, watermark=0.8)

        # Fill queue to maximum
        for i in range(100):
            slot.enqueue(data=i, emitted_from="test", emitted_at=datetime.now())

        status = slot.get_queue_status()

        assert status["unconsumed_count"] == 100
        assert status["total_count"] == 100
        assert status["usage_percentage"] == 1.0
        assert status["pressure_level"] == "critical"
        assert status["is_full"] is True
        assert status["is_near_full"] is True

    def test_get_queue_status_watermark_boundary(self):
        """Test: get_queue_status correctly handles watermark boundary"""
        routine = Routine()
        slot = routine.define_slot("test_slot", max_queue_length=100, watermark=0.8)

        # Add exactly watermark threshold items
        for i in range(80):
            slot.enqueue(data=i, emitted_from="test", emitted_at=datetime.now())

        status = slot.get_queue_status()

        assert status["usage_percentage"] == 0.8
        assert status["pressure_level"] == "high"
        assert status["is_near_full"] is True

    def test_get_queue_status_consumed_items_not_counted(self):
        """Test: get_queue_status only counts unconsumed items"""
        routine = Routine()
        slot = routine.define_slot("test_slot", max_queue_length=100, watermark=0.8)

        # Add 50 items
        for i in range(50):
            slot.enqueue(data=i, emitted_from="test", emitted_at=datetime.now())

        # Consume 20 items
        consumed = slot.consume_all_new()
        assert len(consumed) == 50  # All items are "new"

        # Add 30 more items
        for i in range(50, 80):
            slot.enqueue(data=i, emitted_from="test", emitted_at=datetime.now())

        status = slot.get_queue_status()

        # Should show 30 unconsumed (the new items)
        assert status["unconsumed_count"] == 30
        # Total count includes all items in queue
        assert status["total_count"] == 80

    def test_get_queue_status_thread_safe(self):
        """Test: get_queue_status is thread-safe"""
        routine = Routine()
        slot = routine.define_slot("test_slot", max_queue_length=1000, watermark=0.8)

        results = []

        def add_items(start, count):
            for i in range(start, start + count):
                slot.enqueue(data=i, emitted_from="test", emitted_at=datetime.now())

        def get_status():
            status = slot.get_queue_status()
            results.append(status)

        # Add items from multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=add_items, args=(i * 10, 10))
            threads.append(t)
            t.start()

        # Get status from multiple threads
        status_threads = []
        for _ in range(5):
            t = threading.Thread(target=get_status)
            status_threads.append(t)
            t.start()

        for t in threads:
            t.join()
        for t in status_threads:
            t.join()

        # All status calls should succeed without errors
        assert len(results) == 5
        # All should have consistent structure
        for status in results:
            assert "unconsumed_count" in status
            assert "total_count" in status
            assert "usage_percentage" in status
            assert "pressure_level" in status
            assert "is_full" in status
            assert "is_near_full" in status

    def test_get_queue_status_custom_watermark(self):
        """Test: get_queue_status works with custom watermark values"""
        routine = Routine()
        slot = routine.define_slot("test_slot", max_queue_length=200, watermark=0.5)

        # Add 100 items (50% usage, at watermark)
        for i in range(100):
            slot.enqueue(data=i, emitted_from="test", emitted_at=datetime.now())

        status = slot.get_queue_status()

        assert status["max_length"] == 200
        assert status["watermark_threshold"] == 100
        assert status["usage_percentage"] == 0.5
        assert status["pressure_level"] == "high"  # At watermark, should be high
        assert status["is_near_full"] is True

    def test_get_queue_status_zero_max_length_edge_case(self):
        """Test: get_queue_status handles edge case with very small max_length"""
        routine = Routine()
        slot = routine.define_slot("test_slot", max_queue_length=1, watermark=0.8)

        # Add one item (100% usage)
        slot.enqueue(data=1, emitted_from="test", emitted_at=datetime.now())

        status = slot.get_queue_status()

        assert status["max_length"] == 1
        assert status["usage_percentage"] == 1.0
        assert status["pressure_level"] == "critical"
        assert status["is_full"] is True

    def test_get_queue_status_returns_all_required_fields(self):
        """Test: get_queue_status returns all required fields"""
        routine = Routine()
        slot = routine.define_slot("test_slot")

        status = slot.get_queue_status()

        required_fields = [
            "unconsumed_count",
            "total_count",
            "max_length",
            "watermark_threshold",
            "usage_percentage",
            "pressure_level",
            "is_full",
            "is_near_full",
        ]

        for field in required_fields:
            assert field in status, f"Missing required field: {field}"

    def test_get_queue_status_usage_percentage_range(self):
        """Test: get_queue_status usage_percentage is always between 0.0 and 1.0"""
        routine = Routine()
        slot = routine.define_slot("test_slot", max_queue_length=100, watermark=0.8)

        # Test various queue sizes
        for size in [0, 10, 50, 80, 90, 100]:
            # Clear queue
            slot._queue.clear()
            slot._last_consumed_index = -1

            # Add items
            for i in range(size):
                slot.enqueue(data=i, emitted_from="test", emitted_at=datetime.now())

            status = slot.get_queue_status()

            assert 0.0 <= status["usage_percentage"] <= 1.0, \
                f"usage_percentage out of range for size {size}: {status['usage_percentage']}"

    def test_get_queue_status_pressure_level_consistency(self):
        """Test: get_queue_status pressure_level is consistent with usage"""
        routine = Routine()
        slot = routine.define_slot("test_slot", max_queue_length=100, watermark=0.8)

        test_cases = [
            (0, "low", False, False),
            (30, "low", False, False),
            (60, "medium", False, False),
            (70, "medium", False, False),
            (80, "high", False, True),
            (90, "high", False, True),
            (100, "critical", True, True),
        ]

        for size, expected_pressure, expected_full, expected_near_full in test_cases:
            # Clear queue
            slot._queue.clear()
            slot._last_consumed_index = -1

            # Add items
            for i in range(size):
                slot.enqueue(data=i, emitted_from="test", emitted_at=datetime.now())

            status = slot.get_queue_status()

            assert status["pressure_level"] == expected_pressure, \
                f"Wrong pressure level for size {size}: expected {expected_pressure}, got {status['pressure_level']}"
            assert status["is_full"] == expected_full, \
                f"Wrong is_full for size {size}: expected {expected_full}, got {status['is_full']}"
            assert status["is_near_full"] == expected_near_full, \
                f"Wrong is_near_full for size {size}: expected {expected_near_full}, got {status['is_near_full']}"
