"""
Tests for analysis exporters (routine_markdown, workflow_d2).
"""


from routilux.analysis.exporters.routine_markdown import RoutineMarkdownFormatter
from routilux.analysis.exporters.workflow_d2 import WorkflowD2Formatter


class TestRoutineMarkdownFormatter:
    """Tests for RoutineMarkdownFormatter."""

    def test_format_empty_data(self):
        """Test formatting empty routine analysis data."""
        formatter = RoutineMarkdownFormatter()
        result = formatter.format({})
        assert result is not None
        assert "No routines found" in result

    def test_format_data_with_file_path(self):
        """Test formatting with file path."""
        formatter = RoutineMarkdownFormatter()
        data = {"file_path": "test_routine.py"}
        result = formatter.format(data)
        assert "test_routine.py" in result
        assert "Source File" in result

    def test_format_data_with_routines(self):
        """Test formatting routine data."""
        formatter = RoutineMarkdownFormatter()
        data = {
            "file_path": "test.py",
            "routines": [
                {
                    "name": "TestRoutine",
                    "docstring": "Test routine docstring",
                    "slots": [
                        {
                            "name": "input",
                            "handler": "_handle_input",
                            "merge_strategy": "override",
                        }
                    ],
                    "events": [
                        {
                            "name": "output",
                            "output_params": ["result", "status"],
                        }
                    ],
                    "config": {"timeout": 30, "retries": 3},
                    "methods": [
                        {
                            "name": "_handle_input",
                            "parameters": ["self", "data"],
                            "emits": ["output"],
                            "docstring": "Handle input data",
                        }
                    ],
                }
            ],
        }
        result = formatter.format(data)
        assert "TestRoutine" in result
        assert "Test routine docstring" in result
        assert "input" in result
        assert "output" in result
        assert "timeout" in result
        assert "Handle input data" in result

    def test_format_value_string(self):
        """Test _format_value with string."""
        formatter = RoutineMarkdownFormatter()
        result = formatter._format_value("test")
        assert '"test"' in result

    def test_format_value_int(self):
        """Test _format_value with int."""
        formatter = RoutineMarkdownFormatter()
        result = formatter._format_value(42)
        assert "42" in result

    def test_format_value_float(self):
        """Test _format_value with float."""
        formatter = RoutineMarkdownFormatter()
        result = formatter._format_value(3.14)
        assert "3.14" in result

    def test_format_value_bool(self):
        """Test _format_value with bool."""
        formatter = RoutineMarkdownFormatter()
        result = formatter._format_value(True)
        assert "True" in result

    def test_format_value_none(self):
        """Test _format_value with None."""
        formatter = RoutineMarkdownFormatter()
        result = formatter._format_value(None)
        assert "None" in result

    def test_format_value_list_small(self):
        """Test _format_value with small list."""
        formatter = RoutineMarkdownFormatter()
        result = formatter._format_value([1, 2, 3])
        assert "[" in result
        assert "]" in result

    def test_format_value_list_large(self):
        """Test _format_value with large list."""
        formatter = RoutineMarkdownFormatter()
        result = formatter._format_value(list(range(10)))
        assert "10 items" in result

    def test_format_value_dict_small(self):
        """Test _format_value with small dict."""
        formatter = RoutineMarkdownFormatter()
        result = formatter._format_value({"a": 1, "b": 2})
        assert "{" in result
        assert "}" in result

    def test_format_value_dict_large(self):
        """Test _format_value with large dict."""
        formatter = RoutineMarkdownFormatter()
        result = formatter._format_value({str(i): i for i in range(10)})
        assert "10 items" in result

    def test_format_single_value(self):
        """Test _format_single_value."""
        formatter = RoutineMarkdownFormatter()
        assert formatter._format_single_value("test") == '"test"'
        assert formatter._format_single_value(42) == "42"
        assert formatter._format_single_value(3.14) == "3.14"
        assert formatter._format_single_value(True) == "True"
        assert formatter._format_single_value(None) == "None"

    def test_format_slot_no_handler(self):
        """Test _format_slot without handler."""
        formatter = RoutineMarkdownFormatter()
        slot = {"name": "input", "merge_strategy": "override"}
        result = formatter._format_slot(slot, {})
        assert any("input" in line for line in result)

    def test_format_event_no_params(self):
        """Test _format_event without parameters."""
        formatter = RoutineMarkdownFormatter()
        event = {"name": "output", "output_params": []}
        result = formatter._format_event(event, {})
        assert any("output" in line for line in result)
        assert any("None specified" in line for line in result)

    def test_format_multiple_routines(self):
        """Test formatting multiple routines."""
        formatter = RoutineMarkdownFormatter()
        data = {
            "file_path": "test.py",
            "routines": [
                {
                    "name": "Routine1",
                    "docstring": "First routine",
                    "slots": [],
                    "events": [],
                    "config": {},
                    "methods": [],
                },
                {
                    "name": "Routine2",
                    "docstring": "Second routine",
                    "slots": [],
                    "events": [],
                    "config": {},
                    "methods": [],
                },
            ],
        }
        result = formatter.format(data)
        assert "Routine1" in result
        assert "Routine2" in result
        assert "---" in result  # Separator

    def test_format_slot_with_params(self):
        """Test _format_slot with handler parameters."""
        formatter = RoutineMarkdownFormatter()
        slot = {
            "name": "input",
            "handler": "_handle_input",
            "merge_strategy": "override",
        }
        routine = {
            "methods": [
                {
                    "name": "_handle_input",
                    "parameters": ["self", "data", "extra_param"],
                    "emits": [],
                    "docstring": "",
                }
            ]
        }
        result = formatter._format_slot(slot, routine)
        assert any("extra_param" in line for line in result)

    def test_format_slot_with_emits(self):
        """Test _format_slot with emits."""
        formatter = RoutineMarkdownFormatter()
        slot = {
            "name": "input",
            "handler": "_handle_input",
            "merge_strategy": "override",
        }
        routine = {
            "methods": [
                {
                    "name": "_handle_input",
                    "parameters": ["self", "data"],
                    "emits": ["output", "status"],
                    "docstring": "",
                }
            ]
        }
        result = formatter._format_slot(slot, routine)
        assert any("output" in line for line in result)
        assert any("status" in line for line in result)

    def test_format_event_with_params(self):
        """Test _format_event with output parameters."""
        formatter = RoutineMarkdownFormatter()
        event = {"name": "output", "output_params": ["result", "status", "error"]}
        result = formatter._format_event(event, {})
        assert any("result" in line for line in result)
        assert any("status" in line for line in result)


class TestWorkflowD2Formatter:
    """Tests for WorkflowD2Formatter."""

    def test_init_default_style(self):
        """Test initialization with default style."""
        formatter = WorkflowD2Formatter()
        assert formatter.style == "default"

    def test_init_custom_style(self):
        """Test initialization with custom style."""
        formatter = WorkflowD2Formatter(style="detailed")
        assert formatter.style == "detailed"

    def test_format_empty_data(self):
        """Test formatting empty workflow data."""
        formatter = WorkflowD2Formatter()
        result = formatter.format({})
        assert result is not None
        assert "Workflow" in result

    def test_format_with_basic_data(self):
        """Test formatting with basic workflow data."""
        formatter = WorkflowD2Formatter()
        data = {
            "flow_id": "test_flow",
            "execution_strategy": "concurrent",
            "max_workers": 4,
            "routines": [],
            "connections": [],
        }
        result = formatter.format(data)
        assert "test_flow" in result
        assert "concurrent" in result
        assert "4" in result

    def test_format_with_routines(self):
        """Test formatting with routines."""
        formatter = WorkflowD2Formatter()
        data = {
            "flow_id": "test_flow",
            "execution_strategy": "sequential",
            "max_workers": 1,
            "routines": [
                {
                    "routine_id": "routine1",
                    "class_name": "MyRoutine",
                    "slots": [{"name": "input", "handler": "_handle_input"}],
                    "events": [{"name": "output", "output_params": ["result"]}],
                }
            ],
            "connections": [],
            "entry_points": ["routine1"],
        }
        result = formatter.format(data)
        assert "routine1" in result
        assert "MyRoutine" in result
        assert "Entry Point" in result

    def test_format_with_connections(self):
        """Test formatting with connections."""
        formatter = WorkflowD2Formatter()
        data = {
            "flow_id": "test_flow",
            "execution_strategy": "sequential",
            "max_workers": 1,
            "routines": [
                {
                    "routine_id": "r1",
                    "class_name": "Routine1",
                    "slots": [],
                    "events": [],
                },
                {
                    "routine_id": "r2",
                    "class_name": "Routine2",
                    "slots": [],
                    "events": [],
                },
            ],
            "connections": [
                {
                    "source_routine_id": "r1",
                    "source_event": "output",
                    "target_routine_id": "r2",
                    "target_slot": "input",
                    "param_mapping": {"data": "input_data"},
                }
            ],
            "entry_points": [],
        }
        result = formatter.format(data)
        assert "r1.events.output -> r2.slots.input" in result

    def test_format_connection_without_mapping(self):
        """Test formatting connection without param mapping."""
        formatter = WorkflowD2Formatter()
        data = {
            "flow_id": "test_flow",
            "execution_strategy": "sequential",
            "max_workers": 1,
            "routines": [
                {
                    "routine_id": "r1",
                    "class_name": "Routine1",
                    "slots": [],
                    "events": [],
                },
                {
                    "routine_id": "r2",
                    "class_name": "Routine2",
                    "slots": [],
                    "events": [],
                },
            ],
            "connections": [
                {
                    "source_routine_id": "r1",
                    "source_event": "output",
                    "target_routine_id": "r2",
                    "target_slot": "input",
                    "param_mapping": {},
                }
            ],
            "entry_points": [],
        }
        result = formatter.format(data)
        assert "r1.events.output -> r2.slots.input" in result

    def test_format_detailed_style(self):
        """Test formatting with detailed style."""
        formatter = WorkflowD2Formatter(style="detailed")
        data = {
            "flow_id": "test_flow",
            "execution_strategy": "sequential",
            "max_workers": 1,
            "routines": [
                {
                    "routine_id": "r1",
                    "class_name": "Routine1",
                    "slots": [],
                    "events": [],
                },
                {
                    "routine_id": "r2",
                    "class_name": "Routine2",
                    "slots": [],
                    "events": [],
                },
            ],
            "connections": [
                {
                    "source_routine_id": "r1",
                    "source_event": "output",
                    "target_routine_id": "r2",
                    "target_slot": "input",
                    "param_mapping": {},
                }
            ],
            "entry_points": [],
        }
        result = formatter.format(data)
        assert "stroke" in result

    def test_format_with_dependency_graph(self):
        """Test formatting with dependency graph."""
        formatter = WorkflowD2Formatter(style="detailed")
        data = {
            "flow_id": "test_flow",
            "execution_strategy": "sequential",
            "max_workers": 1,
            "routines": [],
            "connections": [],
            "dependency_graph": {
                "routine2": ["routine1"],
                "routine3": ["routine2"],
            },
        }
        result = formatter.format(data)
        assert "Dependency Graph" in result
        assert "routine1 -> routine2" in result
        assert "routine2 -> routine3" in result

    def test_format_empty_dependency_graph(self):
        """Test formatting with empty dependency graph."""
        formatter = WorkflowD2Formatter(style="detailed")
        data = {
            "flow_id": "test_flow",
            "execution_strategy": "sequential",
            "max_workers": 1,
            "routines": [],
            "connections": [],
            "dependency_graph": {},
        }
        result = formatter.format(data)
        # Should not include dependency graph section
        assert "Dependency Graph" not in result or result.count("Dependency Graph") <= 1

    def test_format_routine_node_with_slots(self):
        """Test _format_routine_node with slots."""
        formatter = WorkflowD2Formatter()
        routine = {
            "routine_id": "test_routine",
            "class_name": "TestRoutine",
            "slots": [
                {"name": "input1", "handler": "_handler1"},
                {"name": "input2", "handler": None},
            ],
            "events": [],
        }
        result = formatter._format_routine_node(routine, False)
        assert any("input1" in line for line in result)
        assert any("input2" in line for line in result)

    def test_format_routine_node_with_events(self):
        """Test _format_routine_node with events."""
        formatter = WorkflowD2Formatter()
        routine = {
            "routine_id": "test_routine",
            "class_name": "TestRoutine",
            "slots": [],
            "events": [
                {"name": "output", "output_params": ["result", "status"]},
                {"name": "error", "output_params": []},
            ],
        }
        result = formatter._format_routine_node(routine, False)
        assert any("output" in line for line in result)
        assert any("error" in line for line in result)

    def test_format_routine_node_entry_point(self):
        """Test _format_routine_node for entry point."""
        formatter = WorkflowD2Formatter()
        routine = {
            "routine_id": "entry_routine",
            "class_name": "EntryRoutine",
            "slots": [],
            "events": [],
        }
        result = formatter._format_routine_node(routine, True)
        assert any("Entry Point" in line for line in result)
        assert any("fff4e6" in line for line in result)  # Entry point color

    def test_format_connection_with_many_params(self):
        """Test _format_connection with many parameters in mapping."""
        formatter = WorkflowD2Formatter(style="detailed")  # Use detailed style to get label
        conn = {
            "source_routine_id": "r1",
            "source_event": "output",
            "target_routine_id": "r2",
            "target_slot": "input",
            "param_mapping": {"a": "1", "b": "2", "c": "3", "d": "4", "e": "5"},
        }
        result = formatter._format_connection(conn)
        # With 5 params, it should truncate with "..." in the label
        assert any("..." in line for line in result)

    def test_format_connection_event_with_many_params(self):
        """Test _format_connection with event output params."""
        formatter = WorkflowD2Formatter()
        data = {
            "flow_id": "test_flow",
            "execution_strategy": "sequential",
            "max_workers": 1,
            "routines": [
                {
                    "routine_id": "r1",
                    "class_name": "Routine1",
                    "slots": [],
                    "events": [],
                },
                {
                    "routine_id": "r2",
                    "class_name": "Routine2",
                    "slots": [],
                    "events": [],
                },
            ],
            "connections": [
                {
                    "source_routine_id": "r1",
                    "source_event": "output",
                    "target_routine_id": "r2",
                    "target_slot": "input",
                    "param_mapping": {},
                }
            ],
            "entry_points": [],
        }
        # Now test with routine having many params
        data["routines"][0]["events"] = [
            {"name": "output", "output_params": ["a", "b", "c", "d", "e"]}
        ]
        result = formatter.format(data)
        assert "..." in result  # Should truncate params
