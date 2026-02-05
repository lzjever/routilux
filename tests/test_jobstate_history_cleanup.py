"""Tests for JobState history retention limits."""

from datetime import datetime, timedelta

from routilux.job_state import ExecutionRecord, JobState


class TestHistorySizeLimit:
    """Tests for max_history_size retention policy."""

    def test_history_limited_by_max_size(self):
        """JobState should limit history to max_history_size entries."""
        job_state = JobState("test_flow")
        job_state.max_history_size = 5

        # Add 10 records
        for i in range(10):
            job_state.record_execution(f"routine_{i}", "event", {"index": i})

        # Should only keep last 5
        history = job_state.get_execution_history()
        assert len(history) == 5
        assert history[0].routine_id == "routine_5"
        assert history[4].routine_id == "routine_9"

    def test_max_history_size_zero_keeps_none(self):
        """max_history_size=0 should keep no history."""
        job_state = JobState("test_flow")
        job_state.max_history_size = 0

        job_state.record_execution("routine", "event", {"data": "test"})

        history = job_state.get_execution_history()
        assert len(history) == 0

    def test_max_history_size_none_means_unlimited(self):
        """max_history_size=None should mean unlimited history."""
        job_state = JobState("test_flow")
        job_state.max_history_size = None

        # Add many records
        for i in range(100):
            job_state.record_execution(f"routine_{i}", "event", {"index": i})

        # Should keep all
        history = job_state.get_execution_history()
        assert len(history) == 100


class TestHistoryTimeLimit:
    """Tests for history_ttl_seconds retention policy."""

    def test_history_limited_by_ttl(self):
        """JobState should remove records older than history_ttl_seconds."""
        job_state = JobState("test_flow")
        job_state.history_ttl_seconds = 60  # 1 minute TTL

        now = datetime.now()

        # Add records at different times
        old_record = ExecutionRecord("old_routine", "event", {})
        old_record.timestamp = now - timedelta(seconds=120)
        job_state.execution_history.append(old_record)

        new_record = ExecutionRecord("new_routine", "event", {})
        new_record.timestamp = now - timedelta(seconds=30)
        job_state.execution_history.append(new_record)

        # Trigger cleanup by recording new event
        job_state.record_execution("current", "event", {})

        history = job_state.get_execution_history()
        routine_ids = [r.routine_id for r in history]

        # Old record should be removed
        assert "old_routine" not in routine_ids
        assert "new_routine" in routine_ids
        assert "current" in routine_ids

    def test_history_ttl_none_means_no_time_limit(self):
        """history_ttl_seconds=None should mean no time-based eviction."""
        job_state = JobState("test_flow")
        job_state.history_ttl_seconds = None

        now = datetime.now()

        # Add very old record
        old_record = ExecutionRecord("old_routine", "event", {})
        old_record.timestamp = now - timedelta(days=365)
        job_state.execution_history.append(old_record)

        # Trigger cleanup
        job_state.record_execution("current", "event", {})

        history = job_state.get_execution_history()
        routine_ids = [r.routine_id for r in history]
        assert "old_routine" in routine_ids


class TestHybridRetention:
    """Tests for combined size + time limits."""

    def test_either_limit_triggers_cleanup(self):
        """Cleanup should trigger when EITHER limit is reached."""
        job_state = JobState("test_flow")
        job_state.max_history_size = 100
        job_state.history_ttl_seconds = 60

        now = datetime.now()

        # Add old record (triggers time limit)
        old_record = ExecutionRecord("old", "event", {})
        old_record.timestamp = now - timedelta(seconds=120)
        job_state.execution_history.append(old_record)

        # Trigger cleanup
        job_state.record_execution("new", "event", {})

        history = job_state.get_execution_history()
        routine_ids = [r.routine_id for r in history]
        assert "old" not in routine_ids  # Time limit removed it
        assert "new" in routine_ids


class TestRetentionDefaults:
    """Tests for default retention values."""

    def test_default_max_history_size(self):
        """Default max_history_size should be 1000."""
        job_state = JobState("test_flow")
        assert job_state.max_history_size == 1000

    def test_default_history_ttl(self):
        """Default history_ttl_seconds should be 3600 (1 hour)."""
        job_state = JobState("test_flow")
        assert job_state.history_ttl_seconds == 3600
