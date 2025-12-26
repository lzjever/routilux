# Examples

This directory contains practical examples demonstrating flowforge usage.

## Examples

### basic_example.py
A simple example demonstrating:
- Creating routines with slots and events
- Connecting routines in a flow
- Executing a flow
- Checking execution status

**Run:**
```bash
python examples/basic_example.py
```

### data_processing.py
A multi-stage data processing pipeline example demonstrating:
- Complex data flow with multiple stages
- Parameter mapping
- Statistics tracking

**Run:**
```bash
python examples/data_processing.py
```

### error_handling_example.py
Examples demonstrating different error handling strategies:
- RETRY strategy with retry configuration
- CONTINUE strategy for error logging
- SKIP strategy for fault tolerance

**Run:**
```bash
python examples/error_handling_example.py
```

### state_management_example.py
Examples demonstrating JobState and ExecutionTracker usage:
- JobState for execution tracking
- ExecutionTracker for performance monitoring
- State serialization and persistence

**Run:**
```bash
python examples/state_management_example.py
```

### concurrent_flow_demo.py
A comprehensive demo of concurrent execution capabilities:
- Concurrent execution strategy with thread pools
- Multiple parallel routines executing simultaneously
- Performance comparison (sequential vs concurrent)
- Error handling in concurrent execution
- Serialization of concurrent flows
- Dynamic strategy switching
- Real-world scenario: concurrent data fetching and processing

**Features demonstrated:**
- Creating flows with concurrent execution strategy
- Setting max_workers for thread pool
- Automatic parallel execution of independent routines
- Thread-safe state management
- Performance improvements with concurrent execution

**Run:**
```bash
python examples/concurrent_flow_demo.py
```

**Expected output:**
- Execution time comparison showing concurrent execution is faster
- Demonstration of parallel data fetching from multiple sources
- Error handling in concurrent scenarios
- Serialization/deserialization of concurrent flows

## Running Examples

All examples use FlowForge which is a standalone package. No additional dependencies are required.

```bash
# From project root
cd examples
python basic_example.py
```

## Requirements

Examples use only the standard library and flowforge. No additional dependencies are required beyond the core package.

