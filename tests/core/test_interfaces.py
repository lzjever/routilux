"""Tests for Protocol interfaces."""

from routilux.core.interfaces import IEventHandler, IEventRouter, IRoutineExecutor


def test_i_event_router_protocol_exists():
    """Verify IEventRouter protocol exists and has required methods."""

    # Create a mock that satisfies the protocol
    class MockEventRouter:
        def get_connections_for_event(self, event):
            return []

        def get_routine(self, routine_id):
            return None

    # Should satisfy the protocol (structural typing)
    router: IEventRouter = MockEventRouter()
    assert router.get_connections_for_event(None) == []
    assert router.get_routine("test") is None


def test_i_routine_executor_protocol_exists():
    """Verify IRoutineExecutor protocol exists."""

    class MockExecutor:
        def enqueue_task(self, task):
            pass

    executor: IRoutineExecutor = MockExecutor()
    executor.enqueue_task(None)  # Should not raise


def test_i_event_handler_protocol_exists():
    """Verify IEventHandler protocol exists."""

    class MockEventHandler:
        def handle_event_emit(self, event, event_data, worker_state):
            pass

    handler: IEventHandler = MockEventHandler()
    handler.handle_event_emit(None, {}, None)  # Should not raise
