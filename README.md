# Routilux ⚡

[![PyPI version](https://img.shields.io/pypi/v/routilux.svg)](https://pypi.org/project/routilux/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Documentation](https://readthedocs.org/projects/routilux/badge/?version=latest)](https://routilux.readthedocs.io)
[![CI](https://github.com/lzjever/routilux/workflows/CI/badge.svg)](https://github.com/lzjever/routilux/actions)
[![codecov](https://codecov.io/gh/lzjever/routilux/branch/main/graph/badge.svg)](https://codecov.io/gh/lzjever/routilux)

**Routilux** is an event-driven workflow orchestration framework providing flexible connection management, state tracking, and execution control for complex data pipelines and workflows.

## Overview

Routilux is designed for production use with the following architectural principles:

- **Runtime-Based Execution**: Centralized Runtime manages thread pools and execution contexts
- **Event-Driven Architecture**: Non-blocking event emission with unified task queues
- **Activation Policies**: Declarative control over when routines execute
- **State Isolation**: JobState tracks execution state, not routine instances
- **Thread Safety**: All operations are thread-safe by design
- **Serialization Support**: Full workflow state persistence for resumption

## Installation

```bash
pip install routilux
```

For development with all dependencies:

```bash
make dev-install
```

## Quick Start

### Minimal Working Example

This example demonstrates the current architecture with Runtime, activation policies, and logic functions.

```python
from routilux import Flow, Routine
from routilux.activation_policies import immediate_policy
from routilux.runtime import Runtime
from routilux.monitoring.flow_registry import FlowRegistry

class DataSource(Routine):
    """Generates data for processing"""

    def __init__(self):
        super().__init__()
        self.trigger = self.define_slot("trigger")
        self.output = self.define_event("output", ["data"])

        def logic(trigger_data, policy_message, job_state):
            # Process input data
            data = trigger_data[0].get("data", "default") if trigger_data else "default"
            # Emit result (runtime is auto-detected)
            self.emit("output", data=data)

        self.set_logic(logic)
        self.set_activation_policy(immediate_policy())

class DataProcessor(Routine):
    """Processes incoming data"""

    def __init__(self):
        super().__init__()
        self.input = self.define_slot("input")
        self.output = self.define_event("output", ["result"])

        def logic(input_data, policy_message, job_state):
            # Extract data from slot
            if input_data:
                value = input_data[0].get("data", input_data[0])
            else:
                value = ""

            # Process and emit
            processed = f"Processed: {value}"
            self.emit("output", result=processed)

        self.set_logic(logic)
        self.set_activation_policy(immediate_policy())

# Create and configure flow
flow = Flow(flow_id="data_pipeline")
source = DataSource()
processor = DataProcessor()

flow.add_routine(source, "source")
flow.add_routine(processor, "processor")
flow.connect("source", "output", "processor", "input")

# Register flow in FlowRegistry
registry = FlowRegistry.get_instance()
registry.register_by_name("data_pipeline", flow)

# Execute using Runtime
runtime = Runtime(thread_pool_size=5)
job_state = runtime.exec("data_pipeline", entry_params={"data": "Hello"})

# Wait for completion
runtime.wait_until_all_jobs_finished(timeout=5.0)

print(f"Status: {job_state.status}")
runtime.shutdown(wait=True)
```

## Core Architecture

### Components

1. **Runtime**: Centralized execution manager with shared thread pool
2. **Flow**: Workflow definition with routines and connections
3. **Routine**: Unit of work with slots, events, activation policy, and logic
4. **Slot**: Input queue for receiving data from events
5. **Event**: Output mechanism for transmitting data to slots
6. **JobState**: Execution state tracking (isolated from routine instances)

### Execution Model

- **Unified Task Queue**: Both sequential and concurrent modes use same queue-based mechanism
- **Non-Blocking Emit**: Event emission returns immediately; execution happens asynchronously
- **Activation Control**: Policies determine when routines execute based on slot data
- **Thread-Safe State**: JobState tracks execution, not routine instance variables

### Key Concepts

**Activation Policies**

Activation policies control when routines execute:

```python
from routilux.activation_policies import (
    immediate_policy,           # Activate immediately when any slot receives data
    all_slots_ready_policy,    # Activate when all slots have data
    batch_size_policy,          # Activate when all slots have at least N items
    time_interval_policy,       # Activate at most once per time interval
    custom_policy              # Define your own activation logic
)

# Set policy on routine
routine.set_activation_policy(immediate_policy())
```

**Logic Function Signature**

```python
def my_logic(slot_data, policy_message, job_state):
    """
    Args:
        slot_data: Dict[str, list] - Slot name to list of data points
        policy_message: Policy-specific metadata
        job_state: Current JobState for this execution
    """
    # Process data
    # Emit events
    pass

routine.set_logic(my_logic)
```

**State Management**

```python
# Store configuration (read-only during execution)
self.set_config(name="my_routine", timeout=30)
config_value = self.get_config("timeout", 10)

# Store execution state in JobState
job_state.update_routine_state(routine_id, {"processed": True})

# Access shared data
job_state.shared_data["result"] = data

# Append to shared log
job_state.shared_log.append(f"Processed {data}")
```

## Critical Constraints

.. warning:: **DO NOT Accept Constructor Parameters**

   Routines MUST have a parameterless constructor:

   ```python
   # ❌ WRONG - Will break serialization
   class MyRoutine(Routine):
       def __init__(self, name: str):  # Don't do this!
           super().__init__()
           self.name = name
   ```

   ```python
   # ✅ CORRECT - Use _config dictionary
   class MyRoutine(Routine):
       def __init__(self):
           super().__init__()
           self.set_config(name="my_routine")  # Use _config
   ```

.. warning:: **DO NOT Modify Instance Variables During Execution**

   All execution state MUST be stored in JobState:

   ```python
   # ❌ WRONG - Breaks execution isolation
   def logic(self, data, policy_message, job_state):
       self.counter += 1  # Don't modify instance variables!
   ```

   ```python
   # ✅ CORRECT - Use JobState
   def logic(self, data, policy_message, job_state):
       counter = job_state.get_routine_state(routine_id, {}).get("count", 0)
       job_state.update_routine_state(routine_id, {"count": counter + 1})
   ```

   **Why?** The same routine object can execute concurrently in multiple threads. Modifying instance variables causes data races and state corruption.

## Advanced Features

### Error Handling

```python
from routilux import ErrorHandler, ErrorStrategy

# Set flow-level error handler
flow.set_error_handler(
    ErrorHandler(
        strategy=ErrorStrategy.RETRY,
        max_retries=3,
        retry_delay=1.0
    )
)
```

Strategies: `STOP`, `CONTINUE`, `RETRY`, `SKIP`

### Concurrent Execution

```python
# Runtime handles concurrent execution automatically
runtime = Runtime(thread_pool_size=10)

# Independent routines execute in parallel
job_state = runtime.exec("my_flow")
```

### Serialization and Resumption

```python
# Save job state
job_state.save("state.json")

# Resume from saved state
from routilux.job_state import JobState
saved_state = JobState.load("state.json")
runtime.exec("my_flow", job_state=saved_state)
```

## Documentation

**Full documentation**: [routilux.readthedocs.io](https://routilux.readthedocs.io)

- [User Guide](https://routilux.readthedocs.io/en/latest/user_guide/index.html)
- [API Reference](https://routilux.readthedocs.io/en/latest/api_reference/index.html)
- [Examples](https://routilux.readthedocs.io/en/latest/examples/index.html)

## Examples

See `examples/` directory for complete working examples:

```bash
python examples/basic_example.py
python examples/concurrent_flow_demo.py
```

## Development

```bash
# Install development dependencies
make dev-install

# Run tests
make test

# Run with coverage
make test-cov

# Lint and format
make lint
make format

# Build documentation
make docs
```

## Architecture Notes

### Activation Policy System

Routines now use **activation policies** instead of slot handlers:

- **Separation of Concerns**: Slot holds data, policy decides when to execute
- **Flexible Control**: Declarative policies for complex activation conditions
- **Data Slicing**: Policies extract data slices from slots based on conditions

### Runtime vs Flow

- **Runtime**: Global execution manager with thread pool
- **Flow**: Workflow definition (routines, connections)
- **JobExecutor**: Per-job execution context with task queue

### Thread Safety

All operations are thread-safe by design:
- Shared thread pool in Runtime
- Independent task queues per job
- Thread-safe JobState updates
- ContextVars for thread-local storage

## Use Cases

Routilux is designed for:

- **Data Pipelines**: ETL processes, data transformation workflows
- **API Orchestration**: Coordinating multiple API calls with complex dependencies
- **Event Processing**: Real-time event streams and reactive systems
- **Workflow Automation**: Business process automation and task scheduling
- **Microservices Coordination**: Managing interactions between services
- **LLM Agent Workflows**: Complex AI agent orchestration and chaining

## About Routilux

Routilux is part of the **Agentsmith** open-source ecosystem. It is a modular workflow orchestration component extracted from the Agentsmith platform.

### Related Projects

- **[Varlord](https://github.com/lzjever/varlord)** - Configuration management
- **[Serilux](https://github.com/lzjever/serilux)** - Serialization framework
- **[Lexilux](https://github.com/lzjever/lexilux)** - LLM API client

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.
