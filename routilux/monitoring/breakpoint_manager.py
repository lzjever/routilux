"""
Breakpoint manager for debugging workflow execution.

Manages slot-level breakpoints with optional conditions.
"""

import threading
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from routilux.core.routine import ExecutionContext


@dataclass
class Breakpoint:
    """Breakpoint definition for slot-level debugging.

    Attributes:
        breakpoint_id: Unique identifier for this breakpoint.
        job_id: Job ID this breakpoint applies to.
        routine_id: Routine ID where the slot is located (required).
        slot_name: Slot name where breakpoint is set (required).
        condition: Optional Python expression to evaluate (e.g., "data.get('value') > 10").
        enabled: Whether this breakpoint is active.
        hit_count: Number of times this breakpoint has been hit.
    """

    breakpoint_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    routine_id: str = ""  # Required, no longer Optional
    slot_name: str = ""  # Required, no longer Optional
    condition: Optional[str] = None
    enabled: bool = True
    hit_count: int = 0

    def __post_init__(self):
        """Validate breakpoint configuration."""
        if not self.job_id:
            raise ValueError("job_id is required for breakpoints")
        if not self.routine_id:
            raise ValueError("routine_id is required for slot breakpoints")
        if not self.slot_name:
            raise ValueError("slot_name is required for slot breakpoints")


class BreakpointManager:
    """Manages breakpoints for workflow debugging.

    Thread-safe breakpoint manager that stores breakpoints by job_id
    and provides efficient lookup for breakpoint checking during execution.
    """

    def __init__(self):
        """Initialize breakpoint manager."""
        self._breakpoints: Dict[
            str, Dict[str, Breakpoint]
        ] = {}  # job_id -> {breakpoint_id -> Breakpoint}
        self._lock = threading.RLock()

    def add_breakpoint(self, breakpoint: Breakpoint) -> str:
        """Add a breakpoint.

        Args:
            breakpoint: Breakpoint to add.

        Returns:
            breakpoint_id of the added breakpoint.
        """
        with self._lock:
            if breakpoint.job_id not in self._breakpoints:
                self._breakpoints[breakpoint.job_id] = {}

            self._breakpoints[breakpoint.job_id][breakpoint.breakpoint_id] = breakpoint
            return breakpoint.breakpoint_id

    def remove_breakpoint(self, breakpoint_id: str, job_id: str) -> None:
        """Remove a breakpoint.

        Args:
            breakpoint_id: ID of breakpoint to remove.
            job_id: Job ID the breakpoint belongs to.
        """
        with self._lock:
            if job_id in self._breakpoints:
                self._breakpoints[job_id].pop(breakpoint_id, None)
                if not self._breakpoints[job_id]:
                    del self._breakpoints[job_id]

    def get_breakpoints(self, job_id: str) -> List[Breakpoint]:
        """Get all breakpoints for a job.

        Args:
            job_id: Job ID to get breakpoints for.

        Returns:
            List of breakpoints for the job.
        """
        with self._lock:
            return list(self._breakpoints.get(job_id, {}).values())

    def clear_breakpoints(self, job_id: str) -> None:
        """Clear all breakpoints for a job.

        Args:
            job_id: Job ID to clear breakpoints for.
        """
        with self._lock:
            if job_id in self._breakpoints:
                del self._breakpoints[job_id]

    def check_slot_breakpoint(
        self,
        job_id: str,
        routine_id: str,
        slot_name: str,
        context: Optional["ExecutionContext"] = None,
        variables: Optional[Dict] = None,
    ) -> Optional[Breakpoint]:
        """Check if a breakpoint should trigger for a slot enqueue operation.

        This method is called during event routing when data is about to be
        enqueued to a slot. If a matching breakpoint is found, the enqueue
        operation should be skipped.

        Args:
            job_id: Job ID being executed.
            routine_id: Target routine ID where the slot is located.
            slot_name: Target slot name where data would be enqueued.
            context: Execution context (for condition evaluation).
            variables: Local variables (for condition evaluation).

        Returns:
            Breakpoint that should trigger, or None if no breakpoint should trigger.
        """
        with self._lock:
            job_breakpoints = self._breakpoints.get(job_id, {})

            for breakpoint in job_breakpoints.values():
                if not breakpoint.enabled:
                    continue

                # Match on (job_id, routine_id, slot_name)
                if breakpoint.routine_id != routine_id:
                    continue

                if breakpoint.slot_name != slot_name:
                    continue

                # Evaluate condition if present
                if breakpoint.condition:
                    from routilux.monitoring.breakpoint_condition import evaluate_condition
                    import logging
                    
                    logger = logging.getLogger(__name__)
                    
                    # Debug: Log condition evaluation
                    logger.debug(
                        f"Evaluating condition: {breakpoint.condition}, "
                        f"variables={variables}, variables_type={type(variables)}"
                    )
                    
                    try:
                        condition_result = evaluate_condition(breakpoint.condition, context, variables or {})
                        logger.debug(f"Condition result: {condition_result}")
                        
                        if not condition_result:
                            continue
                    except Exception as e:
                        logger.warning(
                            f"Error evaluating condition '{breakpoint.condition}': {e}, "
                            f"variables={variables}"
                        )
                        # If condition evaluation fails, don't match
                        continue

                # Breakpoint matches - increment hit count and return
                breakpoint.hit_count += 1
                return breakpoint

            return None
