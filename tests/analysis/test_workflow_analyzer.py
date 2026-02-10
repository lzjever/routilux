"""Tests for workflow analyzer module."""

import json

from routilux import Flow, Routine
from routilux.analysis.analyzers.routine import RoutineAnalyzer
from routilux.analysis.analyzers.workflow import WorkflowAnalyzer, analyze_workflow


class DummyRoutine(Routine):
    """A dummy routine for testing."""

    def __init__(self):
        super().__init__()
        self.define_slot("input", self.handle_input)
        self.define_event("output", ["data"])

    def handle_input(self, data):
        pass


class TriggerRoutine(Routine):
    """A routine with trigger slot."""

    def __init__(self):
        super().__init__()
        self.define_slot("trigger", self.handle_trigger)
        self.define_event("output", ["result"])

    def handle_trigger(self, data):
        pass


class TestWorkflowAnalyzer:
    """Test WorkflowAnalyzer class."""

    def test_init(self):
        """Test initialization of WorkflowAnalyzer."""
        analyzer = WorkflowAnalyzer()
        assert analyzer.routine_analyzer is not None
        assert isinstance(analyzer.routine_analyzer, RoutineAnalyzer)

    def test_init_with_custom_routine_analyzer(self):
        """Test initialization with custom RoutineAnalyzer."""
        custom_analyzer = RoutineAnalyzer()
        analyzer = WorkflowAnalyzer(custom_analyzer)
        assert analyzer.routine_analyzer is custom_analyzer

    def test_analyze_flow_basic(self):
        """Test basic flow analysis."""
        flow = Flow("test_flow")
        routine1 = DummyRoutine()
        routine2 = DummyRoutine()

        flow.add_routine(routine1, "r1")
        flow.add_routine(routine2, "r2")
        flow.connect("r1", "output", "r2", "input")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow)

        assert result["flow_id"] == "test_flow"
        assert result["execution_strategy"] == "sequential"
        assert len(result["routines"]) == 2
        assert len(result["connections"]) == 1

    def test_analyze_flow_without_source_analysis(self):
        """Test flow analysis without source file analysis."""
        flow = Flow("test_flow")
        routine = DummyRoutine()

        flow.add_routine(routine, "r1")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow, include_source_analysis=False)

        routine_info = result["routines"][0]
        assert routine_info["routine_id"] == "r1"
        assert routine_info["class_name"] == "DummyRoutine"
        assert routine_info["source_info"] is None

    def test_analyze_flow_extract_routine_info(self):
        """Test that routine information is extracted correctly."""
        flow = Flow("test_flow")
        routine = DummyRoutine()

        flow.add_routine(routine, "r1")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow)

        routine_info = result["routines"][0]
        assert routine_info["routine_id"] == "r1"
        assert routine_info["class_name"] == "DummyRoutine"
        assert len(routine_info["slots"]) == 1
        assert routine_info["slots"][0]["name"] == "input"
        assert len(routine_info["events"]) == 1
        assert routine_info["events"][0]["name"] == "output"

    def test_analyze_flow_connections(self):
        """Test that connections are analyzed correctly."""
        flow = Flow("test_flow")
        routine1 = DummyRoutine()
        routine2 = DummyRoutine()

        flow.add_routine(routine1, "r1")
        flow.add_routine(routine2, "r2")
        flow.connect("r1", "output", "r2", "input")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow)

        assert len(result["connections"]) == 1
        conn = result["connections"][0]
        assert conn["source_routine_id"] == "r1"
        assert conn["source_event"] == "output"
        assert conn["target_routine_id"] == "r2"
        assert conn["target_slot"] == "input"

    def test_analyze_flow_dependency_graph(self):
        """Test that dependency graph is built correctly."""
        flow = Flow("test_flow")
        routine1 = DummyRoutine()
        routine2 = DummyRoutine()
        routine3 = DummyRoutine()

        flow.add_routine(routine1, "r1")
        flow.add_routine(routine2, "r2")
        flow.add_routine(routine3, "r3")
        flow.connect("r1", "output", "r2", "input")
        flow.connect("r2", "output", "r3", "input")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow)

        dep_graph = result["dependency_graph"]
        assert "r1" in dep_graph
        assert "r2" in dep_graph
        assert "r3" in dep_graph
        assert dep_graph["r1"] == []
        assert "r1" in dep_graph["r2"]
        assert "r2" in dep_graph["r3"]

    def test_analyze_flow_entry_points(self):
        """Test that entry points are detected."""
        flow = Flow("test_flow")
        trigger_routine = TriggerRoutine()
        regular_routine = DummyRoutine()

        flow.add_routine(trigger_routine, "entry")
        flow.add_routine(regular_routine, "worker")
        flow.connect("entry", "output", "worker", "input")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow)

        assert "entry" in result["entry_points"]

    def test_analyze_flow_execution_metadata(self):
        """Test that execution metadata is extracted."""
        flow = Flow(
            "test_flow",
            execution_timeout=60.0,
        )

        flow.add_routine(DummyRoutine(), "r1")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow)

        assert result["execution_strategy"] == "sequential"  # default value
        assert result["max_workers"] == 1  # default value
        assert result["execution_timeout"] == 60.0

    def test_to_json(self):
        """Test converting analysis result to JSON."""
        flow = Flow("json_flow")
        flow.add_routine(DummyRoutine(), "r1")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow)

        json_str = analyzer.to_json(result)
        parsed = json.loads(json_str)

        assert parsed["flow_id"] == "json_flow"
        assert len(parsed["routines"]) == 1

    def test_save_json(self, tmp_path):
        """Test saving analysis result to JSON file."""
        flow = Flow("save_flow")
        flow.add_routine(DummyRoutine(), "r1")

        output_file = tmp_path / "output.json"

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow)

        analyzer.save_json(result, output_file)

        assert output_file.exists()
        with open(output_file) as f:
            parsed = json.load(f)
        assert parsed["flow_id"] == "save_flow"

    def test_analyze_workflow_convenience_function(self):
        """Test the convenience function analyze_workflow."""
        flow = Flow("convenience_flow")
        flow.add_routine(DummyRoutine(), "r1")

        result = analyze_workflow(flow)

        assert result["flow_id"] == "convenience_flow"
        assert len(result["routines"]) == 1


class TestWorkflowAnalyzerD2Format:
    """Test D2 format generation."""

    def test_to_d2_format_standard(self):
        """Test standard D2 format generation."""
        flow = Flow("d2_flow")
        flow.add_routine(DummyRoutine(), "r1")
        flow.add_routine(DummyRoutine(), "r2")
        flow.connect("r1", "output", "r2", "input")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow)
        d2_str = analyzer.to_d2_format(result, mode="standard")

        assert "# Workflow: d2_flow" in d2_str
        assert "r1:" in d2_str
        assert "r2:" in d2_str
        assert "r1.output -> r2.input" in d2_str

    def test_to_d2_format_ultimate(self):
        """Test ultimate D2 format generation."""
        flow = Flow("ultimate_flow")
        flow.add_routine(TriggerRoutine(), "entry")
        flow.add_routine(DummyRoutine(), "worker")
        flow.connect("entry", "output", "worker", "input")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow)
        d2_str = analyzer.to_d2_format(result, mode="ultimate")

        assert "# Workflow: ultimate_flow" in d2_str
        assert "# Layout Configuration" in d2_str
        assert "# Workflow Metadata" in d2_str
        assert "direction: right" in d2_str
        assert "layout-engine: elk" in d2_str

    def test_save_d2(self, tmp_path):
        """Test saving D2 format to file."""
        flow = Flow("save_d2_flow")
        flow.add_routine(DummyRoutine(), "r1")

        output_file = tmp_path / "workflow.d2"

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow)

        analyzer.save_d2(result, output_file)

        assert output_file.exists()
        content = output_file.read_text()
        assert "# Workflow:" in content


class TestWorkflowAnalyzerEdgeCases:
    """Test edge cases for WorkflowAnalyzer."""

    def test_analyze_empty_flow(self):
        """Test analyzing an empty flow."""
        flow = Flow("empty_flow")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow)

        assert result["flow_id"] == "empty_flow"
        assert result["routines"] == []
        assert result["connections"] == []
        assert result["dependency_graph"] == {}
        assert result["entry_points"] == []

    def test_analyze_flow_with_unconnected_routines(self):
        """Test flow with unconnected routines."""
        flow = Flow("unconnected_flow")
        flow.add_routine(DummyRoutine(), "r1")
        flow.add_routine(DummyRoutine(), "r2")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow)

        assert len(result["routines"]) == 2
        assert len(result["connections"]) == 0
        assert "r1" in result["dependency_graph"]
        assert "r2" in result["dependency_graph"]

    def test_make_json_serializable(self):
        """Test _make_json_serializable method."""
        analyzer = WorkflowAnalyzer()

        # Test primitive types
        assert analyzer._make_json_serializable("string") == "string"
        assert analyzer._make_json_serializable(42) == 42
        assert analyzer._make_json_serializable(3.14) == 3.14
        assert analyzer._make_json_serializable(True) is True
        assert analyzer._make_json_serializable(None) is None

        # Test dict
        result = analyzer._make_json_serializable({"key": "value"})
        assert result == {"key": "value"}

        # Test list
        result = analyzer._make_json_serializable([1, 2, 3])
        assert result == [1, 2, 3]

        # Test nested
        result = analyzer._make_json_serializable({"list": [1, 2], "nested": {"key": "value"}})
        assert result == {"list": [1, 2], "nested": {"key": "value"}}

        # Test non-serializable (should convert to string)
        non_serializable = object()
        result = analyzer._make_json_serializable(non_serializable)
        assert isinstance(result, str)

    def test_dependency_graph_with_circular_dependencies(self):
        """Test dependency graph with circular connections."""
        flow = Flow("circular_flow")
        r1 = DummyRoutine()
        r2 = DummyRoutine()

        flow.add_routine(r1, "r1")
        flow.add_routine(r2, "r2")
        flow.connect("r1", "output", "r2", "input")
        flow.connect("r2", "output", "r1", "input")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow)

        # Both should depend on each other
        assert "r2" in result["dependency_graph"]["r1"]
        assert "r1" in result["dependency_graph"]["r2"]

    def test_multiple_entry_points(self):
        """Test flow with multiple entry points."""
        flow = Flow("multi_entry_flow")
        flow.add_routine(TriggerRoutine(), "entry1")
        flow.add_routine(TriggerRoutine(), "entry2")
        flow.add_routine(DummyRoutine(), "worker")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow)

        assert len(result["entry_points"]) == 2
        assert "entry1" in result["entry_points"]
        assert "entry2" in result["entry_points"]


class TestWorkflowAnalyzerWithMockRoutine:
    """Test WorkflowAnalyzer with mocked routine that has special attributes."""

    def test_routine_with_config(self):
        """Test analyzing routine with config."""
        flow = Flow("config_flow")
        routine = DummyRoutine()
        routine._config = {"max_retries": 3, "timeout": 30}

        flow.add_routine(routine, "r1")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow, include_source_analysis=False)

        routine_info = result["routines"][0]
        assert routine_info["config"]["max_retries"] == 3
        assert routine_info["config"]["timeout"] == 30

    def test_routine_with_merge_strategy(self):
        """Test that slot merge strategy is extracted."""
        flow = Flow("merge_flow")
        routine = DummyRoutine()
        # Access the slot and set merge_strategy
        if hasattr(routine, "_slots") and "input" in routine._slots:
            routine._slots["input"].merge_strategy = "append"

        flow.add_routine(routine, "r1")

        analyzer = WorkflowAnalyzer()
        result = analyzer.analyze_flow(flow, include_source_analysis=False)

        routine_info = result["routines"][0]
        slot_info = routine_info["slots"][0]
        assert slot_info["merge_strategy"] == "append"
