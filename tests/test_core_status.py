"""Tests for status enums."""

from routilux.core import ExecutionStatus, JobStatus, RoutineStatus


class TestExecutionStatus:
    """Test ExecutionStatus enum."""

    def test_execution_status_values(self):
        """Test that ExecutionStatus has expected values."""
        assert ExecutionStatus.IDLE == "idle"
        assert ExecutionStatus.RUNNING == "running"
        assert ExecutionStatus.PAUSED == "paused"
        assert ExecutionStatus.COMPLETED == "completed"
        assert ExecutionStatus.FAILED == "failed"
        assert ExecutionStatus.CANCELLED == "cancelled"

    def test_execution_status_string_representation(self):
        """Test string representation of ExecutionStatus."""
        assert ExecutionStatus.IDLE.value == "idle"
        assert ExecutionStatus.RUNNING.value == "running"
        # str() returns the enum name, .value returns the string value
        assert str(ExecutionStatus.IDLE) == "ExecutionStatus.IDLE"

    def test_execution_status_equality(self):
        """Test equality comparison of ExecutionStatus."""
        assert ExecutionStatus.IDLE == "idle"
        assert ExecutionStatus.IDLE != "running"


class TestJobStatus:
    """Test JobStatus enum."""

    def test_job_status_values(self):
        """Test that JobStatus has expected values."""
        assert JobStatus.PENDING == "pending"
        assert JobStatus.RUNNING == "running"
        assert JobStatus.COMPLETED == "completed"
        assert JobStatus.FAILED == "failed"
        assert JobStatus.CANCELLED == "cancelled"

    def test_job_status_string_representation(self):
        """Test string representation of JobStatus."""
        assert JobStatus.PENDING.value == "pending"
        assert JobStatus.RUNNING.value == "running"
        # str() returns the enum name, .value returns the string value
        assert str(JobStatus.PENDING) == "JobStatus.PENDING"


class TestRoutineStatus:
    """Test RoutineStatus enum."""

    def test_routine_status_values(self):
        """Test that RoutineStatus has expected values."""
        assert RoutineStatus.IDLE.value == "idle"
        assert RoutineStatus.RUNNING.value == "running"
        assert RoutineStatus.COMPLETED.value == "completed"
        assert RoutineStatus.FAILED.value == "failed"

    def test_routine_status_string_representation(self):
        """Test string representation of RoutineStatus."""
        assert RoutineStatus.IDLE.value == "idle"
        assert RoutineStatus.RUNNING.value == "running"
        # str() returns the enum name, .value returns the string value
        assert str(RoutineStatus.IDLE) == "RoutineStatus.IDLE"
