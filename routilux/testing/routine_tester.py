"""
Routine tester utility for unit testing routines.
"""

from typing import TYPE_CHECKING, Any, Dict, List
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from routilux.routine import Routine


class RoutineTester:
    """Utility for testing routines without full Flow setup.

    This class provides a convenient way to test routines in isolation,
    without needing to set up a complete Flow. It mocks the execution
    context and provides methods to call slot handlers and capture events.

    Examples:
        Basic usage:
            >>> from routilux.testing import RoutineTester
            >>> routine = MyRoutine()
            >>> tester = RoutineTester(routine)
            >>>
            >>> # Test slot handler
            >>> tester.call_slot("input", data="test")
            >>>
            >>> # Check emitted events
            >>> events = tester.capture_events()
            >>> assert "output" in events
            >>> assert events["output"][0]["result"] == "expected"
    """

    def __init__(self, routine: "Routine"):
        """Initialize RoutineTester.

        Args:
            routine: Routine instance to test.
        """
        self.routine = routine
        self._captured_events: Dict[str, List[Dict[str, Any]]] = {}
        self._setup_mock_flow()

    def _setup_mock_flow(self) -> None:
        """Setup mock flow context for testing."""
        from routilux.job_state import JobState
        from routilux.routine import _current_job_state

        mock_flow = MagicMock()
        mock_job_state = JobState("test_flow")
        mock_job_state.job_id = "test_job_id"
        mock_job_state.shared_data = {}

        # Fix: Use setattr to safely set _current_flow, with error handling
        try:
            setattr(self.routine, "_current_flow", mock_flow)
        except AttributeError:
            # Routine doesn't have _current_flow attribute yet
            # This is OK for testing - just skip setting it
            pass

        # Set up context variable
        _current_job_state.set(mock_job_state)

        # Mock _get_routine_id to return a test ID
        def mock_get_routine_id(routine):
            return "test_routine_id"

        mock_flow._get_routine_id = mock_get_routine_id

    def call_slot(self, slot_name: str, **kwargs: Any) -> Any:
        """Call a slot handler directly.

        Args:
            slot_name: Name of the slot to call.
            **kwargs: Arguments to pass to the slot handler.

        Returns:
            Return value from slot handler (if any).

        Raises:
            ValueError: If slot doesn't exist.
        """
        slot = self.routine.get_slot(slot_name)
        if not slot:
            raise ValueError(
                f"Slot '{slot_name}' not found in routine {self.routine.__class__.__name__}"
            )

        # Call the slot's receive method
        slot.receive(kwargs)

        return None

    def capture_events(self) -> Dict[str, List[Dict[str, Any]]]:
        """Capture emitted events for testing.

        This method intercepts emit() calls and captures the event data.
        Call this before executing the routine to start capturing.

        Returns:
            Dictionary mapping event names to lists of emitted data.

        Examples:
            >>> tester = RoutineTester(routine)
            >>> events = tester.capture_events()
            >>> tester.call_slot("trigger")
            >>> assert "output" in events
            >>> assert len(events["output"]) > 0
        """
        # Store original emit method
        if not hasattr(self.routine, "_original_emit"):
            self.routine._original_emit = self.routine.emit

        # Create wrapper that captures events
        def mock_emit(event_name: str, flow=None, **kwargs):
            if event_name not in self._captured_events:
                self._captured_events[event_name] = []
            self._captured_events[event_name].append(kwargs)
            # Also call original emit if needed
            # self.routine._original_emit(event_name, flow=flow, **kwargs)

        self.routine.emit = mock_emit

        return self._captured_events

    def get_captured_events(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get currently captured events.

        Returns:
            Dictionary of captured events.
        """
        return self._captured_events.copy()

    def clear_captured_events(self) -> None:
        """Clear all captured events."""
        self._captured_events.clear()
