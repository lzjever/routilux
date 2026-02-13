"""
Tests for new builtin routines.
"""


import pytest

from routilux.builtin_routines import (
    Aggregator,
    Batcher,
    Debouncer,
    Filter,
    Mapper,
    RetryHandler,
    SchemaValidator,
    Splitter,
)


class TestMapper:
    """Tests for Mapper routine."""

    def test_mapper_creation(self):
        """Test Mapper can be created."""
        mapper = Mapper()
        assert "input" in mapper._slots
        assert "output" in mapper._events

    def test_mapper_simple_rename(self):
        """Test simple field renaming."""
        mapper = Mapper()
        mapper.set_config(mappings={"old_name": "new_name"})

        # Check configuration
        assert mapper.get_config("mappings") == {"old_name": "new_name"}

    def test_mapper_dot_notation(self):
        """Test dot notation path extraction."""
        mapper = Mapper()
        mapper.set_config(mappings={"user_name": "user.name"})

        # Test internal extraction
        data = {"user": {"name": "John"}}
        value, found = mapper._extract_dot_path(data, "user.name")
        assert found
        assert value == "John"

    def test_mapper_add_mapping(self):
        """Test adding mappings."""
        mapper = Mapper()
        mapper.add_mapping("email", "user.email")

        mappings = mapper.get_config("mappings")
        assert "email" in mappings


class TestSchemaValidator:
    """Tests for SchemaValidator routine."""

    def test_validator_creation(self):
        """Test SchemaValidator can be created."""
        validator = SchemaValidator()
        assert "input" in validator._slots
        assert "valid" in validator._events
        assert "invalid" in validator._events

    def test_custom_validator(self):
        """Test custom validation function."""
        validator = SchemaValidator()

        def validate_positive(data):
            if data > 0:
                return True, []
            return False, ["Value must be positive"]

        validator.set_custom_validator(validate_positive)

        is_valid, errors = validator._validate_custom(5, validate_positive)
        assert is_valid

        is_valid, errors = validator._validate_custom(-1, validate_positive)
        assert not is_valid


class TestFilter:
    """Tests for Filter routine."""

    def test_filter_creation(self):
        """Test Filter can be created."""
        filter_routine = Filter()
        assert "input" in filter_routine._slots
        assert "passed" in filter_routine._events
        assert "rejected" in filter_routine._events

    def test_filter_callable_condition(self):
        """Test filter with callable condition."""
        filter_routine = Filter()
        filter_routine.set_config(condition=lambda x: x > 10)

        passes, reason = filter_routine._evaluate_condition(15, lambda x: x > 10)
        assert passes

        passes, reason = filter_routine._evaluate_condition(5, lambda x: x > 10)
        assert not passes

    def test_filter_dict_condition(self):
        """Test filter with dict condition."""
        filter_routine = Filter()
        condition = {"status": "active", "verified": True}

        passes, _ = filter_routine._evaluate_condition(
            {"status": "active", "verified": True}, condition
        )
        assert passes

        passes, _ = filter_routine._evaluate_condition(
            {"status": "inactive", "verified": True}, condition
        )
        assert not passes


class TestAggregator:
    """Tests for Aggregator routine."""

    def test_aggregator_creation(self):
        """Test Aggregator can be created."""
        aggregator = Aggregator()
        assert "aggregated" in aggregator._events
        assert "timeout" in aggregator._events

    def test_aggregator_setup_slots(self):
        """Test setting up aggregation slots."""
        aggregator = Aggregator()
        aggregator.setup_slots(["a", "b", "c"])

        assert "a" in aggregator._slots
        assert "b" in aggregator._slots
        assert "c" in aggregator._slots

    def test_aggregator_merge_dict(self):
        """Test dict merge strategy."""
        aggregator = Aggregator()

        data = {"a": [1], "b": [2], "c": [3]}
        result = aggregator._merge_data(data, "dict")

        assert result == {"a": 1, "b": 2, "c": 3}

    def test_aggregator_merge_list(self):
        """Test list merge strategy."""
        aggregator = Aggregator()

        data = {"a": [1, 2], "b": [3]}
        result = aggregator._merge_data(data, "list")

        assert result == [1, 2, 3]


class TestBatcher:
    """Tests for Batcher routine."""

    def test_batcher_creation(self):
        """Test Batcher can be created."""
        batcher = Batcher()
        assert "input" in batcher._slots
        assert "batch" in batcher._events
        assert "timeout" in batcher._events

    def test_batcher_config(self):
        """Test batcher configuration."""
        batcher = Batcher()
        batcher.set_config(batch_size=50, batch_timeout=10.0)

        assert batcher.get_config("batch_size") == 50
        assert batcher.get_config("batch_timeout") == 10.0

    def test_batcher_get_pending_count(self):
        """Test getting pending count."""
        batcher = Batcher()
        assert batcher.get_pending_count() == 0


class TestSplitter:
    """Tests for Splitter routine."""

    def test_splitter_creation(self):
        """Test Splitter can be created."""
        splitter = Splitter()
        assert "input" in splitter._slots
        assert "item" in splitter._events

    def test_split_list(self):
        """Test splitting a list."""
        splitter = Splitter()
        items = splitter._split_target([1, 2, 3], False, "values")

        assert items == [1, 2, 3]

    def test_split_dict_values(self):
        """Test splitting dict values."""
        splitter = Splitter()
        items = splitter._split_target({"a": 1, "b": 2}, False, "values")

        assert items == [1, 2]

    def test_split_dict_entries(self):
        """Test splitting dict entries."""
        splitter = Splitter()
        items = splitter._split_target({"a": 1, "b": 2}, False, "entries")

        assert {"key": "a", "value": 1} in items
        assert {"key": "b", "value": 2} in items

    def test_split_string(self):
        """Test splitting strings."""
        splitter = Splitter()

        # Without string splitting
        items = splitter._split_target("hello", False, "values")
        assert items == ["hello"]

        # With string splitting
        items = splitter._split_target("hello", True, "values")
        assert items == ["h", "e", "l", "l", "o"]


class TestDebouncer:
    """Tests for Debouncer routine."""

    def test_debouncer_creation(self):
        """Test Debouncer can be created."""
        debouncer = Debouncer()
        assert "input" in debouncer._slots
        assert "debounced" in debouncer._events
        assert "leading" in debouncer._events

    def test_debouncer_config(self):
        """Test debouncer configuration."""
        debouncer = Debouncer()
        debouncer.set_config(wait=0.5, leading=True, trailing=False)

        assert debouncer.get_config("wait") == 0.5
        assert debouncer.get_config("leading") is True
        assert debouncer.get_config("trailing") is False

    def test_debouncer_is_pending(self):
        """Test checking pending state."""
        debouncer = Debouncer()
        assert not debouncer.is_pending()


class TestRetryHandler:
    """Tests for RetryHandler routine."""

    def test_retry_handler_creation(self):
        """Test RetryHandler can be created."""
        handler = RetryHandler()
        assert "input" in handler._slots
        assert "success" in handler._events
        assert "retry" in handler._events
        assert "exhausted" in handler._events

    def test_retry_handler_config(self):
        """Test retry handler configuration."""
        handler = RetryHandler()
        handler.set_config(max_attempts=5, backoff="exponential", base_delay=0.5)

        assert handler.get_config("max_attempts") == 5
        assert handler.get_config("backoff") == "exponential"

    def test_retry_delay_calculation(self):
        """Test delay calculation for different backoff strategies."""
        handler = RetryHandler()

        # Fixed backoff
        delay = handler._calculate_delay(3, "fixed", 1.0, 60.0)
        assert delay == 1.0

        # Linear backoff
        delay = handler._calculate_delay(3, "linear", 1.0, 60.0)
        assert delay == 3.0

        # Exponential backoff
        delay = handler._calculate_delay(3, "exponential", 1.0, 60.0)
        assert delay == 4.0  # 2^(3-1) = 4

    def test_retry_delay_cap(self):
        """Test that delay is capped at max_delay."""
        handler = RetryHandler()

        delay = handler._calculate_delay(10, "exponential", 1.0, 5.0)
        assert delay == 5.0  # Capped at max_delay

    def test_is_retryable(self):
        """Test retryable exception checking."""
        handler = RetryHandler()

        # All exceptions retryable when None
        assert handler._is_retryable(ValueError("test"), None)
        assert handler._is_retryable(RuntimeError("test"), None)

        # Specific exceptions
        assert handler._is_retryable(ValueError("test"), [ValueError, TypeError])
        assert not handler._is_retryable(RuntimeError("test"), [ValueError, TypeError])

    def test_execute_with_retry_success(self):
        """Test successful execution with retry."""
        handler = RetryHandler()

        def success_op():
            return "result"

        result = handler.execute_with_retry(success_op, max_attempts=3)
        assert result == "result"

    def test_execute_with_retry_eventual_success(self):
        """Test eventual success after retries."""
        handler = RetryHandler()
        attempts = [0]

        def eventually_succeed():
            attempts[0] += 1
            if attempts[0] < 3:
                raise ValueError("Not yet")
            return "success"

        result = handler.execute_with_retry(eventually_succeed, max_attempts=5, base_delay=0.01)
        assert result == "success"
        assert attempts[0] == 3

    def test_execute_with_retry_exhausted(self):
        """Test retry exhaustion."""
        handler = RetryHandler()

        def always_fail():
            raise ValueError("Always fails")

        with pytest.raises(ValueError, match="Always fails"):
            handler.execute_with_retry(always_fail, max_attempts=3, base_delay=0.01)
