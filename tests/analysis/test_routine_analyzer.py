"""Tests for routine analyzer module."""

import json

import pytest

from routilux.analysis.analyzers.routine import RoutineAnalyzer, analyze_routine_file


class TestRoutineAnalyzer:
    """Test RoutineAnalyzer class."""

    def test_init(self):
        """Test initialization of RoutineAnalyzer."""
        analyzer = RoutineAnalyzer()
        assert analyzer.routines == []

    def test_analyze_file_with_simple_routine(self, tmp_path):
        """Test analyzing a simple routine file."""
        # Create a simple routine file
        routine_code = '''
from routilux import Routine

class SimpleRoutine(Routine):
    """A simple routine for testing."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", self.handle_input)
        self.define_event("output", ["data"])

    def handle_input(self, data):
        pass
'''
        test_file = tmp_path / "simple_routine.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        assert result["file_path"] == str(test_file)
        assert len(result["routines"]) == 1
        routine = result["routines"][0]
        assert routine["name"] == "SimpleRoutine"
        assert "simple routine for testing" in routine["docstring"].lower()
        assert len(routine["slots"]) == 1
        assert routine["slots"][0]["name"] == "input"
        assert routine["slots"][0]["handler"] == "handle_input"
        assert len(routine["events"]) == 1
        assert routine["events"][0]["name"] == "output"

    def test_analyze_file_with_multiple_routines(self, tmp_path):
        """Test analyzing a file with multiple routines."""
        routine_code = '''
from routilux import Routine

class FirstRoutine(Routine):
    """First routine."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", self.handle)

class SecondRoutine(Routine):
    """Second routine."""

    def __init__(self):
        super().__init__()
        self.define_event("output", ["data"])
'''
        test_file = tmp_path / "multiple_routines.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        assert len(result["routines"]) == 2
        routine_names = [r["name"] for r in result["routines"]]
        assert "FirstRoutine" in routine_names
        assert "SecondRoutine" in routine_names

    def test_analyze_file_not_found(self):
        """Test analyzing a non-existent file."""
        analyzer = RoutineAnalyzer()
        with pytest.raises(FileNotFoundError):
            analyzer.analyze_file("/nonexistent/path.py")

    def test_analyze_file_with_config(self, tmp_path):
        """Test analyzing a routine with configuration."""
        routine_code = '''
from routilux import Routine

class ConfiguredRoutine(Routine):
    """A routine with configuration."""

    def __init__(self):
        super().__init__()
        self.set_config(max_retries=3, timeout=30)
        self.define_slot("input", self.handle)
'''
        test_file = tmp_path / "configured_routine.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        routine = result["routines"][0]
        assert routine["config"]["max_retries"] == 3
        assert routine["config"]["timeout"] == 30

    def test_analyze_file_with_merge_strategy(self, tmp_path):
        """Test analyzing a routine with custom merge strategy."""
        routine_code = '''
from routilux import Routine

class MergeRoutine(Routine):
    """A routine with merge strategy."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", self.handle, merge_strategy="append")
'''
        test_file = tmp_path / "merge_routine.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        routine = result["routines"][0]
        assert routine["slots"][0]["merge_strategy"] == "append"

    def test_analyze_file_with_slot_handler_as_kwarg(self, tmp_path):
        """Test analyzing a routine with slot handler as keyword argument."""
        routine_code = '''
from routilux import Routine

class KwargRoutine(Routine):
    """A routine using kwargs."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", handler=self.handle)
'''
        test_file = tmp_path / "kwarg_routine.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        routine = result["routines"][0]
        assert routine["slots"][0]["handler"] == "handle"

    def test_analyze_file_with_event_output_params(self, tmp_path):
        """Test analyzing events with output parameters."""
        routine_code = '''
from routilux import Routine

class EventRoutine(Routine):
    """A routine with event output params."""

    def __init__(self):
        super().__init__()
        self.define_event("result", ["data", "status", "timestamp"])
'''
        test_file = tmp_path / "event_routine.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        routine = result["routines"][0]
        assert routine["events"][0]["output_params"] == ["data", "status", "timestamp"]

    def test_analyze_file_extracts_methods(self, tmp_path):
        """Test that methods are extracted."""
        routine_code = '''
from routilux import Routine

class MethodRoutine(Routine):
    """A routine with methods."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", self.handle)

    def handle(self, data):
        """Handle input data."""
        pass

    def process(self, data):
        """Process data."""
        pass

    def cleanup(self):
        """Clean up resources."""
        pass
'''
        test_file = tmp_path / "method_routine.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        routine = result["routines"][0]
        method_names = [m["name"] for m in routine["methods"]]
        assert "__init__" in method_names
        assert "handle" in method_names
        assert "process" in method_names
        assert "cleanup" in method_names

    def test_analyze_file_detects_emit_calls(self, tmp_path):
        """Test that emit calls are detected in methods."""
        routine_code = '''
from routilux import Routine

class EmitRoutine(Routine):
    """A routine that emits."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", self.handle)
        self.define_event("output", [])

    def handle(self, data):
        """Handle and emit."""
        self.emit("output", data=data)
'''
        test_file = tmp_path / "emit_routine.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        routine = result["routines"][0]
        handle_method = next(m for m in routine["methods"] if m["name"] == "handle")
        assert "emits" in handle_method
        assert "output" in handle_method["emits"]

    def test_analyze_file_with_full_module_path(self, tmp_path):
        """Test analyzing routine with full module path inheritance."""
        routine_code = '''
import routilux

class FullPathRoutine(routilux.Routine):
    """A routine using full path."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", self.handle)
'''
        test_file = tmp_path / "full_path_routine.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        assert len(result["routines"]) == 1
        assert result["routines"][0]["name"] == "FullPathRoutine"

    def test_analyze_file_without_routine(self, tmp_path):
        """Test analyzing a file without any routines."""
        code = '''
def regular_function():
    """Just a regular function."""
    pass

class RegularClass:
    """Just a regular class."""
    pass
'''
        test_file = tmp_path / "no_routine.py"
        test_file.write_text(code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        assert len(result["routines"]) == 0

    def test_inherits_from_routine_detects_direct_inheritance(self, tmp_path):
        """Test _inherits_from_routine with direct inheritance."""
        routine_code = """
from routilux import Routine

class DirectRoutine(Routine):
    pass
"""
        test_file = tmp_path / "direct.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        assert len(result["routines"]) == 1

    def test_to_json(self, tmp_path):
        """Test converting analysis result to JSON."""
        routine_code = '''
from routilux import Routine

class JsonRoutine(Routine):
    """A routine for JSON testing."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", self.handle)
        self.define_event("output", ["data"])
'''
        test_file = tmp_path / "json_routine.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        json_str = analyzer.to_json(result)
        parsed = json.loads(json_str)

        assert parsed["file_path"] == str(test_file)
        assert len(parsed["routines"]) == 1
        assert parsed["routines"][0]["name"] == "JsonRoutine"

    def test_to_json_with_custom_indent(self, tmp_path):
        """Test JSON serialization with custom indentation."""
        routine_code = """
from routilux import Routine

class IndentRoutine(Routine):
    pass
"""
        test_file = tmp_path / "indent_routine.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        json_str = analyzer.to_json(result, indent=4)
        assert "    " in json_str  # 4 spaces

    def test_save_json(self, tmp_path):
        """Test saving analysis result to JSON file."""
        routine_code = '''
from routilux import Routine

class SaveRoutine(Routine):
    """A routine for save testing."""
    pass
'''
        test_file = tmp_path / "save_routine.py"
        test_file.write_text(routine_code)

        output_file = tmp_path / "output.json"

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        analyzer.save_json(result, output_file)

        assert output_file.exists()
        with open(output_file) as f:
            parsed = json.load(f)
        assert parsed["routines"][0]["name"] == "SaveRoutine"

    def test_save_json_creates_parent_directories(self, tmp_path):
        """Test that save_json creates parent directories."""
        routine_code = """
from routilux import Routine

class SaveRoutine(Routine):
    pass
"""
        test_file = tmp_path / "save_routine.py"
        test_file.write_text(routine_code)

        output_file = tmp_path / "subdir" / "nested" / "output.json"

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        analyzer.save_json(result, output_file)

        assert output_file.exists()

    def test_analyze_routine_file_convenience_function(self, tmp_path):
        """Test the convenience function analyze_routine_file."""
        routine_code = '''
from routilux import Routine

class ConvenienceRoutine(Routine):
    """Testing convenience function."""
    pass
'''
        test_file = tmp_path / "convenience_routine.py"
        test_file.write_text(routine_code)

        result = analyze_routine_file(test_file)

        assert result["file_path"] == str(test_file)
        assert result["routines"][0]["name"] == "ConvenienceRoutine"

    def test_analyze_file_with_unicode(self, tmp_path):
        """Test analyzing a file with Unicode characters."""
        routine_code = '''
from routilux import Routine

class UnicodeRoutine(Routine):
    """测试中文文档字符串
    你好世界 🌍
    """
    pass
'''
        test_file = tmp_path / "unicode_routine.py"
        test_file.write_text(routine_code, encoding="utf-8")

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        routine = result["routines"][0]
        assert "测试" in routine["docstring"]
        assert "你好世界" in routine["docstring"]
        assert "🌍" in routine["docstring"]

    def test_analyze_file_with_complex_config(self, tmp_path):
        """Test analyzing routine with complex configuration values."""
        routine_code = '''
from routilux import Routine

class ComplexConfigRoutine(Routine):
    """A routine with complex config."""

    def __init__(self):
        super().__init__()
        self.set_config(
            name="test",
            count=42,
            rate=3.14,
            enabled=True,
            items=[1, 2, 3],
            nested={"key": "value"}
        )
'''
        test_file = tmp_path / "complex_config.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        routine = result["routines"][0]
        config = routine["config"]
        assert config["name"] == "test"
        assert config["count"] == 42
        assert config["rate"] == 3.14
        assert config["enabled"] is True
        assert config["items"] == [1, 2, 3]
        assert config["nested"]["key"] == "value"


class TestRoutineAnalyzerEdgeCases:
    """Test edge cases for RoutineAnalyzer."""

    def test_analyze_empty_init_method(self, tmp_path):
        """Test routine with empty __init__ method."""
        routine_code = """
from routilux import Routine

class EmptyInitRoutine(Routine):
    def __init__(self):
        super().__init__()
"""
        test_file = tmp_path / "empty_init.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        routine = result["routines"][0]
        assert routine["slots"] == []
        assert routine["events"] == []
        assert routine["config"] == {}

    def test_analyze_file_with_syntax_error(self, tmp_path):
        """Test handling of file with syntax errors."""
        # Invalid Python syntax
        test_file = tmp_path / "syntax_error.py"
        test_file.write_text("from routilux import Routine\nbroken syntax here")

        analyzer = RoutineAnalyzer()
        with pytest.raises(SyntaxError):
            analyzer.analyze_file(test_file)

    def test_analyze_with_lambda_in_config(self, tmp_path):
        """Test analyzing routine with lambda (should still work)."""
        routine_code = """
from routilux import Routine

class LambdaRoutine(Routine):
    def __init__(self):
        super().__init__()
        self.set_config(func=lambda x: x * 2)
"""
        test_file = tmp_path / "lambda_routine.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        # Lambda values are not literal, so config may be empty or have None
        _ = result["routines"][0]
        # The analyzer should not crash on lambdas

    def test_method_parameters_extraction(self, tmp_path):
        """Test that method parameters are correctly extracted."""
        routine_code = '''
from routilux import Routine

class ParamRoutine(Routine):
    def process(self, data, options=None, extra=42):
        """Process with parameters."""
        pass

    def no_params(self):
        """No parameters."""
        pass
'''
        test_file = tmp_path / "param_routine.py"
        test_file.write_text(routine_code)

        analyzer = RoutineAnalyzer()
        result = analyzer.analyze_file(test_file)

        routine = result["routines"][0]
        process_method = next(m for m in routine["methods"] if m["name"] == "process")
        assert "self" in process_method["parameters"]
        assert "data" in process_method["parameters"]
        assert "options" in process_method["parameters"]
        assert "extra" in process_method["parameters"]

        no_params_method = next(m for m in routine["methods"] if m["name"] == "no_params")
        assert "self" in no_params_method["parameters"]
