#!/usr/bin/env python
"""
Example workflow for analyzer demonstration.

This script creates a complex workflow to demonstrate
workflow_analyzer capabilities.
"""

from routilux import Flow
from analyzer_demo_routines import (
    DataCollector,
    DataProcessor,
    DataValidator,
    DataAggregator,
    DataRouter,
    DataSink
)


def create_demo_workflow() -> Flow:
    """Create a demo workflow with multiple routines and connections.
    
    Workflow structure:
    - DataCollector (entry point)
      -> DataProcessor
      -> DataValidator
      -> DataAggregator
      -> DataRouter
         -> DataSink (high_priority)
         -> DataSink (medium_priority)
         -> DataSink (low_priority)
    
    Returns:
        Configured Flow object.
    """
    # Create flow
    flow = Flow(
        flow_id="demo_analyzer_workflow",
        execution_strategy="concurrent",
        max_workers=3,
        execution_timeout=60.0
    )
    
    # Create routine instances
    collector = DataCollector()
    processor = DataProcessor()
    validator = DataValidator()
    aggregator = DataAggregator()
    router = DataRouter()
    sink_high = DataSink()
    sink_medium = DataSink()
    sink_low = DataSink()
    
    # Add routines to flow
    collector_id = flow.add_routine(collector, "collector")
    processor_id = flow.add_routine(processor, "processor")
    validator_id = flow.add_routine(validator, "validator")
    aggregator_id = flow.add_routine(aggregator, "aggregator")
    router_id = flow.add_routine(router, "router")
    sink_high_id = flow.add_routine(sink_high, "sink_high")
    sink_medium_id = flow.add_routine(sink_medium, "sink_medium")
    sink_low_id = flow.add_routine(sink_low, "sink_low")
    
    # Connect routines
    # collector -> processor
    flow.connect(collector_id, "data", processor_id, "input")
    
    # processor -> validator
    flow.connect(processor_id, "output", validator_id, "data")
    
    # validator -> aggregator (valid path)
    flow.connect(validator_id, "valid", aggregator_id, "input")
    
    # aggregator -> router
    flow.connect(aggregator_id, "result", router_id, "input")
    
    # router -> sinks (multiple outputs)
    flow.connect(router_id, "high_priority", sink_high_id, "high_input")
    flow.connect(router_id, "medium_priority", sink_medium_id, "medium_input")
    flow.connect(router_id, "low_priority", sink_low_id, "low_input")
    
    # Also connect validator invalid -> aggregator (for error handling demo)
    flow.connect(validator_id, "invalid", aggregator_id, "input", 
                 param_mapping={"data": "value"})
    
    return flow


def create_simple_workflow() -> Flow:
    """Create a simple linear workflow.
    
    Workflow structure:
    - DataCollector -> DataProcessor -> DataSink
    
    Returns:
        Configured Flow object.
    """
    flow = Flow(flow_id="simple_demo_workflow")
    
    collector = DataCollector()
    processor = DataProcessor()
    sink = DataSink()
    
    collector_id = flow.add_routine(collector, "collector")
    processor_id = flow.add_routine(processor, "processor")
    sink_id = flow.add_routine(sink, "sink")
    
    flow.connect(collector_id, "data", processor_id, "input")
    flow.connect(processor_id, "output", sink_id, "low_input")
    
    return flow


if __name__ == "__main__":
    # Create workflows
    complex_flow = create_demo_workflow()
    simple_flow = create_simple_workflow()
    
    print("Created demo workflows:")
    print(f"  - Complex workflow: {complex_flow.flow_id}")
    print(f"  - Simple workflow: {simple_flow.flow_id}")
    print(f"\nComplex workflow has {len(complex_flow.routines)} routines")
    print(f"Simple workflow has {len(simple_flow.routines)} routines")

