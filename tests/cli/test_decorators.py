# tests/cli/test_decorators.py
"""Tests for @register_routine decorator."""

import pytest
from routilux.cli.decorators import register_routine
from routilux.tools.factory.factory import ObjectFactory


def test_register_simple_function():
    """Test registering a simple function as a routine."""
    factory = ObjectFactory.get_instance()

    @register_routine("simple_processor")
    def my_logic(data):
        return data.upper()

    # Check routine is registered
    routines = factory.list_available()
    routine_names = [r["name"] for r in routines]
    assert "simple_processor" in routine_names


def test_register_with_metadata():
    """Test registering with metadata."""
    factory = ObjectFactory.get_instance()

    @register_routine(
        "metadata_processor",
        category="processing",
        tags=["fast", "simple"],
        description="A test processor"
    )
    def my_logic(data):
        return data

    metadata = factory.get_metadata("metadata_processor")
    assert metadata is not None
    assert metadata.category == "processing"
    assert "fast" in metadata.tags


def test_create_routine_from_factory():
    """Test that registered routine can be created from factory."""
    factory = ObjectFactory.get_instance()

    @register_routine("factory_test")
    def process(data):
        return data * 2

    # Create instance from factory
    routine = factory.create("factory_test")
    assert routine is not None
    assert hasattr(routine, "_logic")


def test_duplicate_registration_raises():
    """Test that duplicate registration raises error."""
    factory = ObjectFactory.get_instance()

    @register_routine("duplicate_test")
    def func1(data):
        return data

    with pytest.raises(ValueError, match="already registered"):
        @register_routine("duplicate_test")
        def func2(data):
            return data


def test_decorator_preserves_function():
    """Test that decorator preserves original function."""
    @register_routine("preserve_test")
    def my_function(data):
        return data

    # Function should still be callable
    assert my_function("test") == "test"
