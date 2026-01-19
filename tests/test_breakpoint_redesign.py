"""
Comprehensive tests for the redesigned slot-level breakpoint mechanism.

Tests cover:
- Breakpoint creation and validation
- BreakpointManager functionality
- Event routing with breakpoints
- Job isolation
- Condition evaluation
- Enable/disable functionality
- Error handling
"""

import pytest
import time
from datetime import datetime

from routilux.monitoring.breakpoint_manager import Breakpoint, BreakpointManager
from routilux.server.models.breakpoint import (
    BreakpointCreateRequest,
    BreakpointResponse,
    BreakpointUpdateRequest,
)
from routilux.core.runtime import Runtime
from routilux.core.flow import Flow
from routilux.core.routine import Routine
from routilux.core.context import JobContext
from routilux.core.worker import WorkerState


class TestBreakpointDataModel:
    """Test Breakpoint data model."""

    def test_create_valid_breakpoint(self):
        """Test creating a valid breakpoint."""
        bp = Breakpoint(
            job_id="job_123",
            routine_id="routine_1",
            slot_name="input",
        )
        assert bp.job_id == "job_123"
        assert bp.routine_id == "routine_1"
        assert bp.slot_name == "input"
        assert bp.enabled is True
        assert bp.hit_count == 0
        assert bp.condition is None
        assert bp.breakpoint_id is not None

    def test_create_breakpoint_with_condition(self):
        """Test creating breakpoint with condition."""
        bp = Breakpoint(
            job_id="job_456",
            routine_id="routine_2",
            slot_name="output",
            condition='data.get("value") > 10',
            enabled=False,
        )
        assert bp.condition == 'data.get("value") > 10'
        assert bp.enabled is False

    def test_breakpoint_validation_missing_job_id(self):
        """Test breakpoint validation - missing job_id."""
        with pytest.raises(ValueError, match="job_id is required"):
            Breakpoint(routine_id="r1", slot_name="s1")

    def test_breakpoint_validation_missing_routine_id(self):
        """Test breakpoint validation - missing routine_id."""
        with pytest.raises(ValueError, match="routine_id is required"):
            Breakpoint(job_id="j1", slot_name="s1")

    def test_breakpoint_validation_missing_slot_name(self):
        """Test breakpoint validation - missing slot_name."""
        with pytest.raises(ValueError, match="slot_name is required"):
            Breakpoint(job_id="j1", routine_id="r1")

    def test_breakpoint_auto_generated_id(self):
        """Test that breakpoint IDs are auto-generated."""
        bp1 = Breakpoint(job_id="j1", routine_id="r1", slot_name="s1")
        bp2 = Breakpoint(job_id="j1", routine_id="r1", slot_name="s1")
        assert bp1.breakpoint_id != bp2.breakpoint_id


class TestBreakpointManager:
    """Test BreakpointManager functionality."""

    def test_add_breakpoint(self):
        """Test adding a breakpoint."""
        mgr = BreakpointManager()
        bp = Breakpoint(job_id="job_1", routine_id="r1", slot_name="s1")
        bp_id = mgr.add_breakpoint(bp)
        assert bp_id == bp.breakpoint_id

    def test_get_breakpoints(self):
        """Test getting breakpoints for a job."""
        mgr = BreakpointManager()
        bp1 = Breakpoint(job_id="job_1", routine_id="r1", slot_name="s1")
        bp2 = Breakpoint(job_id="job_1", routine_id="r2", slot_name="s2")
        bp3 = Breakpoint(job_id="job_2", routine_id="r1", slot_name="s1")

        mgr.add_breakpoint(bp1)
        mgr.add_breakpoint(bp2)
        mgr.add_breakpoint(bp3)

        job1_bps = mgr.get_breakpoints("job_1")
        assert len(job1_bps) == 2
        assert {bp.breakpoint_id for bp in job1_bps} == {bp1.breakpoint_id, bp2.breakpoint_id}

        job2_bps = mgr.get_breakpoints("job_2")
        assert len(job2_bps) == 1
        assert job2_bps[0].breakpoint_id == bp3.breakpoint_id

    def test_remove_breakpoint(self):
        """Test removing a breakpoint."""
        mgr = BreakpointManager()
        bp = Breakpoint(job_id="job_1", routine_id="r1", slot_name="s1")
        mgr.add_breakpoint(bp)

        assert len(mgr.get_breakpoints("job_1")) == 1

        mgr.remove_breakpoint(bp.breakpoint_id, "job_1")
        assert len(mgr.get_breakpoints("job_1")) == 0

    def test_clear_breakpoints(self):
        """Test clearing all breakpoints for a job."""
        mgr = BreakpointManager()
        bp1 = Breakpoint(job_id="job_1", routine_id="r1", slot_name="s1")
        bp2 = Breakpoint(job_id="job_1", routine_id="r2", slot_name="s2")
        mgr.add_breakpoint(bp1)
        mgr.add_breakpoint(bp2)

        assert len(mgr.get_breakpoints("job_1")) == 2

        mgr.clear_breakpoints("job_1")
        assert len(mgr.get_breakpoints("job_1")) == 0

    def test_check_slot_breakpoint_match(self):
        """Test checking slot breakpoint - match."""
        mgr = BreakpointManager()
        bp = Breakpoint(job_id="job_1", routine_id="r1", slot_name="s1")
        mgr.add_breakpoint(bp)

        result = mgr.check_slot_breakpoint("job_1", "r1", "s1")
        assert result is not None
        assert result.breakpoint_id == bp.breakpoint_id
        assert result.hit_count == 1

    def test_check_slot_breakpoint_no_match_different_job(self):
        """Test checking slot breakpoint - no match (different job)."""
        mgr = BreakpointManager()
        bp = Breakpoint(job_id="job_1", routine_id="r1", slot_name="s1")
        mgr.add_breakpoint(bp)

        result = mgr.check_slot_breakpoint("job_2", "r1", "s1")
        assert result is None

    def test_check_slot_breakpoint_no_match_different_routine(self):
        """Test checking slot breakpoint - no match (different routine)."""
        mgr = BreakpointManager()
        bp = Breakpoint(job_id="job_1", routine_id="r1", slot_name="s1")
        mgr.add_breakpoint(bp)

        result = mgr.check_slot_breakpoint("job_1", "r2", "s1")
        assert result is None

    def test_check_slot_breakpoint_no_match_different_slot(self):
        """Test checking slot breakpoint - no match (different slot)."""
        mgr = BreakpointManager()
        bp = Breakpoint(job_id="job_1", routine_id="r1", slot_name="s1")
        mgr.add_breakpoint(bp)

        result = mgr.check_slot_breakpoint("job_1", "r1", "s2")
        assert result is None

    def test_check_slot_breakpoint_disabled(self):
        """Test that disabled breakpoints don't match."""
        mgr = BreakpointManager()
        bp = Breakpoint(job_id="job_1", routine_id="r1", slot_name="s1", enabled=False)
        mgr.add_breakpoint(bp)

        result = mgr.check_slot_breakpoint("job_1", "r1", "s1")
        assert result is None

    def test_check_slot_breakpoint_hit_count_increment(self):
        """Test that hit count increments on each match."""
        mgr = BreakpointManager()
        bp = Breakpoint(job_id="job_1", routine_id="r1", slot_name="s1")
        mgr.add_breakpoint(bp)

        assert bp.hit_count == 0

        result1 = mgr.check_slot_breakpoint("job_1", "r1", "s1")
        assert result1.hit_count == 1

        result2 = mgr.check_slot_breakpoint("job_1", "r1", "s1")
        assert result2.hit_count == 2

    def test_check_slot_breakpoint_condition_true(self):
        """Test breakpoint with condition that evaluates to True."""
        mgr = BreakpointManager()
        bp = Breakpoint(
            job_id="job_1",
            routine_id="r1",
            slot_name="s1",
            condition='value > 10',
        )
        mgr.add_breakpoint(bp)

        # Variables are passed as a dict, condition should access them directly
        result = mgr.check_slot_breakpoint(
            "job_1", "r1", "s1", variables={"value": 20}
        )
        assert result is not None
        assert result.breakpoint_id == bp.breakpoint_id

    def test_check_slot_breakpoint_condition_false(self):
        """Test breakpoint with condition that evaluates to False."""
        mgr = BreakpointManager()
        bp = Breakpoint(
            job_id="job_1",
            routine_id="r1",
            slot_name="s1",
            condition='data.get("value", 0) > 10',
        )
        mgr.add_breakpoint(bp)

        result = mgr.check_slot_breakpoint(
            "job_1", "r1", "s1", variables={"value": 5}
        )
        assert result is None

    def test_check_slot_breakpoint_condition_missing_variable(self):
        """Test breakpoint with condition when variable is missing."""
        mgr = BreakpointManager()
        bp = Breakpoint(
            job_id="job_1",
            routine_id="r1",
            slot_name="s1",
            condition='data.get("value", 0) > 10',
        )
        mgr.add_breakpoint(bp)

        result = mgr.check_slot_breakpoint("job_1", "r1", "s1", variables={})
        assert result is None

    def test_multiple_breakpoints_same_job(self):
        """Test multiple breakpoints for the same job."""
        mgr = BreakpointManager()
        bp1 = Breakpoint(job_id="job_1", routine_id="r1", slot_name="s1")
        bp2 = Breakpoint(job_id="job_1", routine_id="r2", slot_name="s2")
        bp3 = Breakpoint(job_id="job_1", routine_id="r1", slot_name="s2")

        mgr.add_breakpoint(bp1)
        mgr.add_breakpoint(bp2)
        mgr.add_breakpoint(bp3)

        result1 = mgr.check_slot_breakpoint("job_1", "r1", "s1")
        assert result1.breakpoint_id == bp1.breakpoint_id

        result2 = mgr.check_slot_breakpoint("job_1", "r2", "s2")
        assert result2.breakpoint_id == bp2.breakpoint_id

        result3 = mgr.check_slot_breakpoint("job_1", "r1", "s2")
        assert result3.breakpoint_id == bp3.breakpoint_id

    def test_job_isolation(self):
        """Test that breakpoints are isolated by job_id."""
        mgr = BreakpointManager()
        bp1 = Breakpoint(job_id="job_1", routine_id="r1", slot_name="s1")
        bp2 = Breakpoint(job_id="job_2", routine_id="r1", slot_name="s1")

        mgr.add_breakpoint(bp1)
        mgr.add_breakpoint(bp2)

        # Job 1 breakpoint should only match for job_1
        result1 = mgr.check_slot_breakpoint("job_1", "r1", "s1")
        assert result1.breakpoint_id == bp1.breakpoint_id

        # Job 2 breakpoint should only match for job_2
        result2 = mgr.check_slot_breakpoint("job_2", "r1", "s1")
        assert result2.breakpoint_id == bp2.breakpoint_id

        # Job 1 breakpoint should not match for job_2
        result3 = mgr.check_slot_breakpoint("job_2", "r1", "s1")
        assert result3.breakpoint_id == bp2.breakpoint_id  # Should match job_2's breakpoint


class TestAPIModels:
    """Test API models."""

    def test_breakpoint_create_request_valid(self):
        """Test valid BreakpointCreateRequest."""
        req = BreakpointCreateRequest(
            routine_id="r1",
            slot_name="s1",
            condition='data.get("value") > 10',
            enabled=True,
        )
        assert req.routine_id == "r1"
        assert req.slot_name == "s1"
        assert req.condition == 'data.get("value") > 10'
        assert req.enabled is True

    def test_breakpoint_create_request_defaults(self):
        """Test BreakpointCreateRequest with defaults."""
        req = BreakpointCreateRequest(routine_id="r1", slot_name="s1")
        assert req.enabled is True
        assert req.condition is None

    def test_breakpoint_create_request_validation(self):
        """Test BreakpointCreateRequest validation."""
        # Missing routine_id
        with pytest.raises(Exception):  # Pydantic ValidationError
            BreakpointCreateRequest(slot_name="s1")

        # Missing slot_name
        with pytest.raises(Exception):  # Pydantic ValidationError
            BreakpointCreateRequest(routine_id="r1")

    def test_breakpoint_response(self):
        """Test BreakpointResponse."""
        resp = BreakpointResponse(
            breakpoint_id="bp_123",
            job_id="job_456",
            routine_id="r1",
            slot_name="s1",
            condition=None,
            enabled=True,
            hit_count=5,
        )
        assert resp.breakpoint_id == "bp_123"
        assert resp.job_id == "job_456"
        assert resp.routine_id == "r1"
        assert resp.slot_name == "s1"
        assert resp.hit_count == 5


class TestBreakpointIntegration:
    """Integration tests for breakpoint functionality."""

    def test_breakpoint_to_response_conversion(self):
        """Test converting Breakpoint to BreakpointResponse."""
        from routilux.server.routes.breakpoints import _breakpoint_to_response

        bp = Breakpoint(
            job_id="job_123",
            routine_id="routine_1",
            slot_name="input",
            condition='data.get("value") > 10',
            enabled=True,
            hit_count=3,
        )

        resp = _breakpoint_to_response(bp)
        assert isinstance(resp, BreakpointResponse)
        assert resp.breakpoint_id == bp.breakpoint_id
        assert resp.job_id == bp.job_id
        assert resp.routine_id == bp.routine_id
        assert resp.slot_name == bp.slot_name
        assert resp.condition == bp.condition
        assert resp.enabled == bp.enabled
        assert resp.hit_count == bp.hit_count


class TestBreakpointThreadSafety:
    """Test thread safety of BreakpointManager."""

    def test_concurrent_add_breakpoint(self):
        """Test adding breakpoints concurrently."""
        import threading

        mgr = BreakpointManager()
        results = []

        def add_breakpoint(job_id, routine_id, slot_name):
            bp = Breakpoint(job_id=job_id, routine_id=routine_id, slot_name=slot_name)
            bp_id = mgr.add_breakpoint(bp)
            results.append(bp_id)

        threads = []
        for i in range(10):
            t = threading.Thread(
                target=add_breakpoint, args=(f"job_{i}", f"r_{i}", f"s_{i}")
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(results) == 10
        assert len(set(results)) == 10  # All IDs should be unique

    def test_concurrent_check_breakpoint(self):
        """Test checking breakpoints concurrently."""
        import threading

        mgr = BreakpointManager()
        bp = Breakpoint(job_id="job_1", routine_id="r1", slot_name="s1")
        mgr.add_breakpoint(bp)

        results = []

        def check_breakpoint():
            result = mgr.check_slot_breakpoint("job_1", "r1", "s1")
            results.append(result is not None)

        threads = []
        for _ in range(20):
            t = threading.Thread(target=check_breakpoint)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(results) == 20
        assert all(results)  # All should find the breakpoint
        assert bp.hit_count == 20  # Hit count should be 20


class TestBreakpointEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_string_values(self):
        """Test breakpoint with empty string values."""
        with pytest.raises(ValueError):
            Breakpoint(job_id="", routine_id="r1", slot_name="s1")

        with pytest.raises(ValueError):
            Breakpoint(job_id="j1", routine_id="", slot_name="s1")

        with pytest.raises(ValueError):
            Breakpoint(job_id="j1", routine_id="r1", slot_name="")

    def test_none_values(self):
        """Test breakpoint with None values."""
        with pytest.raises(ValueError):
            Breakpoint(job_id=None, routine_id="r1", slot_name="s1")

    def test_remove_nonexistent_breakpoint(self):
        """Test removing a non-existent breakpoint."""
        mgr = BreakpointManager()
        # Should not raise an error
        mgr.remove_breakpoint("nonexistent_id", "job_1")

    def test_get_breakpoints_nonexistent_job(self):
        """Test getting breakpoints for non-existent job."""
        mgr = BreakpointManager()
        bps = mgr.get_breakpoints("nonexistent_job")
        assert len(bps) == 0

    def test_clear_breakpoints_nonexistent_job(self):
        """Test clearing breakpoints for non-existent job."""
        mgr = BreakpointManager()
        # Should not raise an error
        mgr.clear_breakpoints("nonexistent_job")

    def test_check_breakpoint_with_none_variables(self):
        """Test checking breakpoint with None variables."""
        mgr = BreakpointManager()
        bp = Breakpoint(job_id="job_1", routine_id="r1", slot_name="s1")
        mgr.add_breakpoint(bp)

        result = mgr.check_slot_breakpoint("job_1", "r1", "s1", variables=None)
        assert result is not None

    def test_condition_with_invalid_syntax(self):
        """Test breakpoint with invalid condition syntax."""
        mgr = BreakpointManager()
        bp = Breakpoint(
            job_id="job_1",
            routine_id="r1",
            slot_name="s1",
            condition="invalid python syntax !!!",
        )
        mgr.add_breakpoint(bp)

        # Invalid syntax should be handled gracefully - breakpoint should not match
        # (condition evaluation returns False for invalid syntax)
        result = mgr.check_slot_breakpoint("job_1", "r1", "s1", variables={"value": 10})
        assert result is None, "Breakpoint with invalid condition syntax should not match"
