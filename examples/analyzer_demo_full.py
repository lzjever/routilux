#!/usr/bin/env python
"""
Full analyzer demonstration.

This script demonstrates the complete capabilities of both
routine_analyzer and workflow_analyzer with real examples.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from routilux import RoutineAnalyzer, WorkflowAnalyzer, analyze_routine_file, analyze_workflow

# Import workflow creators
from analyzer_demo_workflow import create_demo_workflow, create_simple_workflow


def demo_routine_analysis():
    """Demonstrate routine file analysis."""
    print("=" * 80)
    print("ROUTINE ANALYSIS DEMONSTRATION")
    print("=" * 80)
    
    # Get the routine file path
    routine_file = Path(__file__).parent / "analyzer_demo_routines.py"
    
    print(f"\nAnalyzing routine file: {routine_file}")
    print("-" * 80)
    
    # Analyze using convenience function
    result = analyze_routine_file(routine_file)
    
    print(f"\nFound {len(result['routines'])} routines:")
    for routine in result['routines']:
        print(f"\n  Routine: {routine['name']}")
        print(f"    Line: {routine['line_number']}")
        print(f"    Docstring: {routine['docstring'][:60]}..." if len(routine['docstring']) > 60 else f"    Docstring: {routine['docstring']}")
        print(f"    Slots: {len(routine['slots'])}")
        for slot in routine['slots']:
            print(f"      - {slot['name']} (handler: {slot['handler']}, merge: {slot['merge_strategy']})")
        print(f"    Events: {len(routine['events'])}")
        for event in routine['events']:
            params = ", ".join(event['output_params'])
            print(f"      - {event['name']} (params: {params})")
        if routine['config']:
            print(f"    Config: {routine['config']}")
        print(f"    Methods: {len(routine['methods'])}")
        for method in routine['methods']:
            emits = f" (emits: {', '.join(method.get('emits', []))})" if method.get('emits') else ""
            print(f"      - {method['name']}{emits}")
    
    # Save to JSON
    output_file = "routine_analysis_demo.json"
    analyzer = RoutineAnalyzer()
    analyzer.save_json(result, output_file)
    print(f"\n✓ Analysis saved to: {output_file}")
    
    return result


def demo_workflow_analysis():
    """Demonstrate workflow analysis."""
    print("\n" + "=" * 80)
    print("WORKFLOW ANALYSIS DEMONSTRATION")
    print("=" * 80)
    
    # Create workflows
    print("\nCreating demo workflows...")
    complex_flow = create_demo_workflow()
    simple_flow = create_simple_workflow()
    
    # Analyze complex workflow
    print(f"\nAnalyzing complex workflow: {complex_flow.flow_id}")
    print("-" * 80)
    
    workflow_result = analyze_workflow(complex_flow, include_source_analysis=True)
    
    print(f"\nWorkflow Information:")
    print(f"  Flow ID: {workflow_result['flow_id']}")
    print(f"  Execution Strategy: {workflow_result['execution_strategy']}")
    print(f"  Max Workers: {workflow_result['max_workers']}")
    print(f"  Execution Timeout: {workflow_result['execution_timeout']}s")
    print(f"  Routines: {len(workflow_result['routines'])}")
    print(f"  Connections: {len(workflow_result['connections'])}")
    print(f"  Entry Points: {workflow_result['entry_points']}")
    
    print(f"\nRoutines:")
    for routine in workflow_result['routines']:
        print(f"  - {routine['routine_id']} ({routine['class_name']})")
        print(f"    Slots: {len(routine['slots'])} - {[s['name'] for s in routine['slots']]}")
        print(f"    Events: {len(routine['events'])} - {[e['name'] for e in routine['events']]}")
        if routine.get('source_info'):
            print(f"    Source analysis: ✓ Available")
    
    print(f"\nConnections:")
    for conn in workflow_result['connections']:
        mapping = f" (mapping: {conn['param_mapping']})" if conn['param_mapping'] else ""
        print(f"  {conn['source_routine_id']}.{conn['source_event']} -> "
              f"{conn['target_routine_id']}.{conn['target_slot']}{mapping}")
    
    print(f"\nDependency Graph:")
    for routine_id, deps in workflow_result['dependency_graph'].items():
        if deps:
            print(f"  {routine_id} depends on: {', '.join(deps)}")
        else:
            print(f"  {routine_id} has no dependencies (entry point)")
    
    # Save to JSON
    output_file = "workflow_analysis_demo.json"
    analyzer = WorkflowAnalyzer()
    analyzer.save_json(workflow_result, output_file)
    print(f"\n✓ Analysis saved to: {output_file}")
    
    # Generate D2 format
    print(f"\nGenerating D2 format...")
    d2_content = analyzer.to_d2_format(workflow_result)
    d2_file = "workflow_demo.d2"
    analyzer.save_d2(workflow_result, d2_file)
    print(f"✓ D2 file saved to: {d2_file}")
    print(f"\nD2 Preview (first 30 lines):")
    print("-" * 80)
    lines = d2_content.split('\n')
    for i, line in enumerate(lines[:30], 1):
        print(f"{i:3}: {line}")
    if len(lines) > 30:
        remaining = len(lines) - 30
        print(f"... ({remaining} more lines)")
    
    # Analyze simple workflow
    print(f"\n\nAnalyzing simple workflow: {simple_flow.flow_id}")
    print("-" * 80)
    
    simple_result = analyze_workflow(simple_flow, include_source_analysis=True)
    print(f"  Routines: {len(simple_result['routines'])}")
    print(f"  Connections: {len(simple_result['connections'])}")
    
    simple_output_file = "workflow_simple_demo.json"
    analyzer.save_json(simple_result, simple_output_file)
    print(f"✓ Simple workflow analysis saved to: {simple_output_file}")
    
    return workflow_result, simple_result


def demo_comparison():
    """Compare different analysis approaches."""
    print("\n" + "=" * 80)
    print("ANALYSIS COMPARISON")
    print("=" * 80)
    
    routine_file = Path(__file__).parent / "analyzer_demo_routines.py"
    
    # AST-based analysis
    print("\n1. AST-based Routine Analysis (Static)")
    print("-" * 80)
    ast_result = analyze_routine_file(routine_file)
    print(f"   Found {len(ast_result['routines'])} routines via AST")
    print(f"   Can extract: class structure, slots, events, config, methods")
    
    # Runtime-based analysis
    print("\n2. Runtime Workflow Analysis (Dynamic)")
    print("-" * 80)
    flow = create_demo_workflow()
    runtime_result = analyze_workflow(flow, include_source_analysis=False)
    print(f"   Found {len(runtime_result['routines'])} routines in workflow")
    print(f"   Can extract: runtime state, connections, dependencies, entry points")
    
    # Combined analysis
    print("\n3. Combined Analysis (Best of Both)")
    print("-" * 80)
    combined_result = analyze_workflow(flow, include_source_analysis=True)
    routines_with_source = sum(1 for r in combined_result['routines'] if r.get('source_info'))
    print(f"   Found {len(combined_result['routines'])} routines")
    print(f"   {routines_with_source} routines have source analysis available")
    print(f"   Combines: static structure + runtime connections + dependencies")


def main():
    """Main demonstration function."""
    try:
        # Run demonstrations
        routine_result = demo_routine_analysis()
        workflow_result, simple_result = demo_workflow_analysis()
        demo_comparison()
        
        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print("\nGenerated files:")
        print("  ✓ routine_analysis_demo.json - Routine AST analysis")
        print("  ✓ workflow_analysis_demo.json - Complex workflow analysis")
        print("  ✓ workflow_simple_demo.json - Simple workflow analysis")
        print("  ✓ workflow_demo.d2 - D2 format for visualization")
        
        print("\nNext steps:")
        print("  1. View JSON files to see structured data")
        print("  2. Use D2 CLI to generate diagrams:")
        print("     d2 workflow_demo.d2 workflow_demo.svg")
        print("  3. Integrate analyzers into your workflow documentation pipeline")
        
        print("\n" + "=" * 80)
        print("DEMONSTRATION COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

