#!/usr/bin/env python
"""
Formatter demonstration.

This script demonstrates the analysis formatters that convert
analysis JSON results into various output formats.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from routilux import (
    analyze_routine_file,
    analyze_workflow,
    RoutineMarkdownFormatter,
    WorkflowD2Formatter,
)
from analyzer_demo_workflow import create_demo_workflow, create_simple_workflow


def demo_routine_markdown_formatter():
    """Demonstrate routine Markdown formatter."""
    print("=" * 80)
    print("ROUTINE MARKDOWN FORMATTER DEMONSTRATION")
    print("=" * 80)
    
    # Analyze routine file
    routine_file = Path(__file__).parent / "analyzer_demo_routines.py"
    print(f"\nAnalyzing: {routine_file.name}")
    
    routine_result = analyze_routine_file(routine_file)
    
    # Format to Markdown
    formatter = RoutineMarkdownFormatter()
    markdown_content = formatter.format(routine_result)
    
    # Save to file
    output_file = "routine_analysis.md"
    formatter.save(routine_result, output_file)
    
    print(f"✓ Markdown saved to: {output_file}")
    print(f"\nPreview (first 100 lines):")
    print("-" * 80)
    for i, line in enumerate(markdown_content.split('\n')[:100], 1):
        print(f"{i:3}: {line}")
    
    lines = markdown_content.split('\n')
    if len(lines) > 100:
        remaining = len(lines) - 100
        print(f"... ({remaining} more lines)")
    
    return markdown_content


def demo_workflow_d2_formatter():
    """Demonstrate workflow D2 formatter."""
    print("\n" + "=" * 80)
    print("WORKFLOW D2 FORMATTER DEMONSTRATION")
    print("=" * 80)
    
    # Create and analyze workflow
    print("\nCreating demo workflow...")
    flow = create_demo_workflow()
    
    workflow_result = analyze_workflow(flow, include_source_analysis=True)
    
    # Format to D2 with default style
    formatter_default = WorkflowD2Formatter(style="default")
    d2_content_default = formatter_default.format(workflow_result)
    
    output_file_default = "workflow_demo_default.d2"
    formatter_default.save(workflow_result, output_file_default)
    print(f"✓ Default style D2 saved to: {output_file_default}")
    
    # Format to D2 with detailed style
    formatter_detailed = WorkflowD2Formatter(style="detailed")
    d2_content_detailed = formatter_detailed.format(workflow_result)
    
    output_file_detailed = "workflow_demo_detailed.d2"
    formatter_detailed.save(workflow_result, output_file_detailed)
    print(f"✓ Detailed style D2 saved to: {output_file_detailed}")
    
    print(f"\nD2 Preview (first 50 lines of default style):")
    print("-" * 80)
    for i, line in enumerate(d2_content_default.split('\n')[:50], 1):
        print(f"{i:3}: {line}")
    
    lines = d2_content_default.split('\n')
    if len(lines) > 50:
        remaining = len(lines) - 50
        print(f"... ({remaining} more lines)")
    
    return d2_content_default, d2_content_detailed


def demo_comparison():
    """Compare different formatters."""
    print("\n" + "=" * 80)
    print("FORMATTER COMPARISON")
    print("=" * 80)
    
    routine_file = Path(__file__).parent / "analyzer_demo_routines.py"
    routine_result = analyze_routine_file(routine_file)
    
    print("\n1. JSON Format (Original)")
    print("-" * 80)
    print("   - Machine-readable")
    print("   - Complete data structure")
    print("   - Suitable for programmatic processing")
    
    print("\n2. Markdown Format (RoutineMarkdownFormatter)")
    print("-" * 80)
    markdown_formatter = RoutineMarkdownFormatter()
    markdown = markdown_formatter.format(routine_result)
    print("   - Human-readable documentation")
    print("   - Beautiful formatting with emojis")
    print("   - Suitable for documentation and README files")
    print(f"   - Output size: {len(markdown)} characters")
    
    flow = create_demo_workflow()
    workflow_result = analyze_workflow(flow)
    
    print("\n3. D2 Format (WorkflowD2Formatter)")
    print("-" * 80)
    d2_formatter = WorkflowD2Formatter()
    d2 = d2_formatter.format(workflow_result)
    print("   - Visual diagram format")
    print("   - Can be rendered with D2 CLI")
    print("   - Shows workflow structure and connections")
    print(f"   - Output size: {len(d2)} characters")
    
    print("\n4. Usage Recommendations")
    print("-" * 80)
    print("   - JSON: For data processing and integration")
    print("   - Markdown: For documentation and human reading")
    print("   - D2: For visual diagrams and presentations")


def main():
    """Main demonstration function."""
    try:
        # Run demonstrations
        markdown_content = demo_routine_markdown_formatter()
        d2_default, d2_detailed = demo_workflow_d2_formatter()
        demo_comparison()
        
        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print("\nGenerated files:")
        print("  ✓ routine_analysis.md - Beautiful Markdown documentation")
        print("  ✓ workflow_demo_default.d2 - Default style D2 diagram")
        print("  ✓ workflow_demo_detailed.d2 - Detailed style D2 diagram")
        
        print("\nNext steps:")
        print("  1. View routine_analysis.md in a Markdown viewer")
        print("  2. Generate D2 diagrams:")
        print("     d2 workflow_demo_default.d2 workflow_default.svg")
        print("     d2 workflow_demo_detailed.d2 workflow_detailed.svg")
        print("  3. Integrate formatters into your documentation pipeline")
        
        print("\n" + "=" * 80)
        print("DEMONSTRATION COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

