# tests/cli/test_discovery.py
"""Tests for routine discovery system."""

import pytest
from pathlib import Path
from routilux.cli.discovery import RoutineDiscovery, discover_routines


def test_discovery_scan_directory(tmp_path):
    """Test scanning a directory for Python files."""
    # Create test files
    (tmp_path / "routine1.py").write_text("pass")
    (tmp_path / "routine2.py").write_text("pass")
    (tmp_path / "not_python.txt").write_text("pass")

    discovery = RoutineDiscovery()
    files = discovery.scan_directory(tmp_path)

    assert len(files) == 2
    assert all(f.suffix == ".py" for f in files)


@pytest.mark.skip(reason="Task 3 (decorator system) not implemented yet")
def test_discovery_with_decorator(tmp_path):
    """Test discovering routines decorated with @register_routine."""
    # Create a routine file with decorator
    routine_file = tmp_path / "my_routine.py"
    routine_file.write_text("""
from routilux.cli.decorators import register_routine

@register_routine("test_processor")
def my_logic(data):
    return data
""")

    factory = discover_routines([tmp_path])

    # Check routine is registered
    routines = factory.list_available()
    routine_names = [r["name"] for r in routines]
    assert "test_processor" in routine_names


@pytest.mark.skip(reason="Task 3 (decorator system) not implemented yet")
def test_discovery_with_class_based(tmp_path):
    """Test discovering class-based routines."""
    routine_file = tmp_path / "class_routine.py"
    routine_file.write_text("""
from routilux.core.routine import Routine

class MyProcessor(Routine):
    factory_name = "class_processor"

    def setup(self):
        self.add_slot("input")
        self.add_event("output")
""")

    factory = discover_routines([tmp_path])

    routines = factory.list_available()
    routine_names = [r["name"] for r in routines]
    assert "class_processor" in routine_names


def test_discovery_handles_import_errors(tmp_path):
    """Test that discovery skips modules with import errors."""
    # Create a file with import error
    bad_file = tmp_path / "bad_routine.py"
    bad_file.write_text("import nonexistent_module")

    # Create a good file
    good_file = tmp_path / "good_routine.py"
    good_file.write_text("pass")

    # Should not raise, should skip bad file
    factory = discover_routines([tmp_path], on_error="warn")

    # Good file should still be processed
    assert factory is not None


@pytest.mark.skip(reason="Task 3 (decorator system) not implemented yet")
def test_discovery_duplicate_registration(tmp_path):
    """Test that duplicate registration raises error."""
    routine_file = tmp_path / "routine.py"
    routine_file.write_text("""
from routilux.cli.decorators import register_routine

@register_routine("duplicate")
def func1(data):
    return data

@register_routine("duplicate")
def func2(data):
    return data
""")

    with pytest.raises(ValueError, match="already registered"):
        discover_routines([tmp_path])
