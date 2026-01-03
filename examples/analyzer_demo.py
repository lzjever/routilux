#!/usr/bin/env python
"""
Analyzer Demo: Demonstrates routine and workflow analysis capabilities

This example demonstrates:
- Analyzing routine Python files using AST
- Analyzing Flow objects dynamically
- Generating structured JSON descriptions
- Converting to D2 format for visualization
"""

from routilux import Flow, Routine, RoutineAnalyzer, WorkflowAnalyzer, analyze_routine_file, analyze_workflow
import json


class DataSource(Routine):
    """A routine that generates data"""

    def __init__(self):
        super().__init__()
        # Define trigger slot for entry routine
        self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
        self.output_event = self.define_event("output", ["data"])

    def _handle_trigger(self, data=None, **kwargs):
        """Handle trigger and emit data through the output event"""
        output_data = data or kwargs.get("data", "default_data")
        self.emit("output", data=output_data)


class DataProcessor(Routine):
    """A routine that processes data"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self.process)
        self.output_event = self.define_event("output", ["result"])

    def process(self, data):
        """Process incoming data"""
        if isinstance(data, dict):
            data_value = data.get("data", data)
        else:
            data_value = data

        processed_data = f"Processed: {data_value}"
        self.emit("output", result=processed_data)


class DataSink(Routine):
    """A routine that receives final data"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self.receive)

    def receive(self, result):
        """Receive and store the final result"""
        if isinstance(result, dict):
            result_value = result.get("result", result)
        else:
            result_value = result
        print(f"Final result: {result_value}")


def demo_routine_analyzer():
    """Demonstrate routine file analysis."""
    print("=" * 60)
    print("Routine Analyzer Demo")
    print("=" * 60)
    
    # Analyze a routine file
    analyzer = RoutineAnalyzer()
    result = analyzer.analyze_file(__file__)
    
    print("\nAnalysis Result:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Save to JSON file
    output_file = "routine_analysis.json"
    analyzer.save_json(result, output_file)
    print(f"\nAnalysis saved to: {output_file}")


def demo_workflow_analyzer():
    """Demonstrate workflow analysis."""
    print("\n" + "=" * 60)
    print("Workflow Analyzer Demo")
    print("=" * 60)
    
    # Create a flow
    flow = Flow(flow_id="demo_workflow")
    
    # Create routine instances
    source = DataSource()
    processor = DataProcessor()
    sink = DataSink()
    
    # Add routines to the flow
    source_id = flow.add_routine(source, "source")
    processor_id = flow.add_routine(processor, "processor")
    sink_id = flow.add_routine(sink, "sink")
    
    # Connect routines: source -> processor -> sink
    flow.connect(source_id, "output", processor_id, "input")
    flow.connect(processor_id, "output", sink_id, "input")
    
    # Analyze the workflow
    analyzer = WorkflowAnalyzer()
    result = analyzer.analyze_flow(flow, include_source_analysis=True)
    
    print("\nWorkflow Analysis Result:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Save to JSON file
    output_file = "workflow_analysis.json"
    analyzer.save_json(result, output_file)
    print(f"\nAnalysis saved to: {output_file}")
    
    # Convert to D2 format
    d2_content = analyzer.to_d2_format(result)
    print("\nD2 Format:")
    print(d2_content)
    
    # Save D2 file
    d2_file = "workflow.d2"
    analyzer.save_d2(result, d2_file)
    print(f"\nD2 file saved to: {d2_file}")


def demo_convenience_functions():
    """Demonstrate convenience functions."""
    print("\n" + "=" * 60)
    print("Convenience Functions Demo")
    print("=" * 60)
    
    # Analyze routine file using convenience function
    routine_result = analyze_routine_file(__file__)
    print(f"\nFound {len(routine_result['routines'])} routines in file")
    
    # Create and analyze workflow using convenience function
    flow = Flow()
    source = DataSource()
    source_id = flow.add_routine(source, "source")
    
    workflow_result = analyze_workflow(flow, include_source_analysis=True)
    print(f"\nWorkflow has {len(workflow_result['routines'])} routines")
    print(f"Entry points: {workflow_result['entry_points']}")


def main():
    """Main function"""
    try:
        demo_routine_analyzer()
        demo_workflow_analyzer()
        demo_convenience_functions()
        
        print("\n" + "=" * 60)
        print("Demo completed successfully!")
        print("=" * 60)
        print("\nGenerated files:")
        print("  - routine_analysis.json")
        print("  - workflow_analysis.json")
        print("  - workflow.d2")
        print("\nYou can use the D2 file with D2 CLI to generate diagrams:")
        print("  d2 workflow.d2 workflow.svg")
        
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

