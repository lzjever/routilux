"""Tests for Routine mixin separation."""


from routilux.routine import Routine


class TestConfigMixin:
    """Tests for ConfigMixin functionality."""

    def test_configure_stores_params(self):
        """ConfigMixin should store parameters."""
        routine = Routine()
        routine.configure(param1="value1", param2="value2")
        assert routine._config == {"param1": "value1", "param2": "value2"}

    def test_get_param_returns_value(self):
        """ConfigMixin.get_param should return stored values."""
        routine = Routine()
        routine.configure(api_key="secret")
        assert routine.get_param("api_key") == "secret"

    def test_get_param_with_default(self):
        """ConfigMixin.get_param should return default if not found."""
        routine = Routine()
        assert routine.get_param("missing", default="default") == "default"


class TestExecutionMixin:
    """Tests for ExecutionMixin functionality."""

    def test_define_event_creates_event(self):
        """ExecutionMixin.define_event should create events."""
        routine = Routine()
        event = routine.define_event("output", output_params=["result"])
        assert event.name == "output"

    def test_define_slot_creates_slot(self):
        """ExecutionMixin.define_slot should create slots."""

        def handler(data):
            pass

        routine = Routine()
        slot = routine.define_slot("input", handler=handler)
        assert slot.name == "input"
        assert slot.handler is handler

    def test_get_slot_returns_slot(self):
        """ExecutionMixin.get_slot should return slot by name."""

        def handler(data):
            pass

        routine = Routine()
        slot = routine.define_slot("input", handler=handler)
        assert routine.get_slot("input") is slot

    def test_get_event_returns_event(self):
        """ExecutionMixin.get_event should return event by name."""
        routine = Routine()
        event = routine.define_event("output", output_params=["result"])
        assert routine.get_event("output") is event


class TestLifecycleMixin:
    """Tests for LifecycleMixin functionality."""

    def test_before_execution_hook_callable(self):
        """LifecycleMixin should have before_execution hook."""
        routine = Routine()

        def hook():
            pass

        routine.before_execution(hook)
        # Should not raise

    def test_after_execution_hook_callable(self):
        """LifecycleMixin should have after_execution hook."""
        routine = Routine()

        def hook(state):
            pass

        routine.after_execution(hook)
        # Should not raise


class TestRoutineComposition:
    """Tests for Routine as composition of mixins."""

    def test_routine_has_config_methods(self):
        """Routine should have all ConfigMixin methods."""
        routine = Routine()
        assert hasattr(routine, "configure")
        assert hasattr(routine, "get_param")
        assert hasattr(routine, "set_config")
        assert hasattr(routine, "get_config")

    def test_routine_has_execution_methods(self):
        """Routine should have all ExecutionMixin methods."""
        routine = Routine()
        assert hasattr(routine, "define_event")
        assert hasattr(routine, "define_slot")
        assert hasattr(routine, "emit")
        assert hasattr(routine, "get_slot")
        assert hasattr(routine, "get_event")

    def test_routine_has_lifecycle_methods(self):
        """Routine should have all LifecycleMixin methods."""
        routine = Routine()
        assert hasattr(routine, "before_execution")
        assert hasattr(routine, "after_execution")
