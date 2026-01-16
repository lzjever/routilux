# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Routilux** is an event-driven workflow orchestration framework for Python (3.8-3.14) that provides flexible workflow building with state management, error handling, and execution tracking. It's part of the Agentsmith open-source ecosystem (along with Varlord, Serilux, and Lexilux).

### Core Architecture

Routilux uses an **event queue architecture** (v0.9.0+) with these key concepts:

- **Routine**: Base class for workflow nodes with Slots (inputs) and Events (outputs)
- **Flow**: Container managing multiple Routines, connecting Events to Slots
- **JobState**: Execution state tracking, completely decoupled from Flow
- **Connection**: Many-to-many relationships between Events and Slots
- **Event Queue**: Unified execution model for sequential and concurrent modes

**Critical architectural change (v0.9.0)**:
- `emit()` is **always non-blocking** - returns immediately after enqueuing tasks
- Flow and JobState are **completely decoupled** - Flow no longer stores execution state
- Each `Flow.execute()` call returns an independent JobState that you must manage
- Automatic flow detection - `emit()` retrieves flow from routine context

### Project Structure

```
routilux/
├── routilux/              # Main package
│   ├── routine.py         # Routine base class
│   ├── flow/              # Flow management subsystem (refactored in v0.9.0)
│   │   ├── flow.py        # Main Flow class
│   │   ├── execution.py   # Sequential/concurrent execution
│   │   ├── event_loop.py  # Event loop and task queue
│   │   ├── state_management.py  # Pause/resume/cancel
│   │   ├── completion.py  # Event loop completion utilities
│   │   ├── task.py        # TaskPriority, SlotActivationTask
│   │   ├── builder.py     # FlowBuilder for fluent API
│   │   ├── dependency.py  # Dependency graph building
│   │   ├── error_handling.py  # Error handling logic
│   │   ├── validation.py  # Flow validation
│   │   └── serialization.py  # Serialization helpers
│   ├── event.py           # Event (output) mechanism
│   ├── slot.py            # Slot (input) mechanism
│   ├── connection.py      # Connection management
│   ├── error_handler.py   # Error handling strategies
│   ├── job_state.py       # Execution state tracking
│   ├── execution_tracker.py # Performance metrics
│   ├── status.py          # ExecutionStatus and RoutineStatus enums
│   ├── output_handler.py  # OutputHandler utilities (Queue, Callback, Null)
│   ├── analysis/          # Workflow analysis tools
│   ├── api/               # FastAPI server (monitoring/debugging)
│   ├── dsl/               # YAML/JSON DSL loader
│   ├── monitoring/        # Debug/breakpoint system
│   └── testing/           # Testing utilities
├── tests/                 # Core test suite (45+ test files)
├── examples/              # Usage examples (14 demos)
├── docs/                  # Sphinx documentation
├── scripts/               # Utility scripts (release notes, setup)
└── pyproject.toml         # Project configuration
```

## Development Commands

### Setup

```bash
# Recommended: For active development
make dev-install           # Install package + all dependencies using uv

# Alternative: Dependencies only (for CI/CD or code review)
make setup-venv            # Install dependencies only (no package)
make install               # Install package after setup-venv
```

**Note**: This project uses [uv](https://github.com/astral-sh/uv) for fast dependency management. All Makefile commands automatically use `uv` if available, otherwise fall back to `pip`.

**Dependency groups vs extras**:
- **Dependency groups** (`dev`, `docs`): Development dependencies not published to PyPI. Use with `uv sync --group docs`
- **Optional dependencies** (`api`, `dev`): Published to PyPI, installable via `pip install routilux[api]`

### Testing

```bash
make test                  # Run all tests
make test-cov              # Run with coverage report
make test-integration      # Run integration tests (requires external services)

# Direct pytest usage
pytest tests/              # Run all tests
pytest tests/test_routine.py  # Run specific test file
pytest tests/ -v -m integration  # Run integration tests only
pytest tests/ -k "test_concurrent"  # Run tests matching pattern
```

**Test markers**: `unit`, `integration`, `slow`, `persistence`, `resume`, `asyncio`, `api`, `websocket`, `debug`
- Integration tests are excluded by default
- Default timeout: 120 seconds
- Coverage requirement: 60% minimum
- Tests use pytest framework - see `tests/README.md` for details

### Code Quality

```bash
make lint                  # Run ruff linting
make format                # Format code with ruff
make format-check          # Check formatting without modifying
make check                 # Run all checks (lint + format-check + test)
make type-check            # Run mypy type checking
make pre-commit-install    # Install pre-commit hooks
make pre-commit-run        # Run pre-commit hooks manually
```

**Ruff configuration**:
- Line length: 100 characters
- Target version: Python 3.8+
- Lint rules: E, F, I, N, W, UP

### Building & Publishing

```bash
make build                 # Build source and wheel distributions
make check-package         # Validate package with twine
make upload                # Upload to PyPI (requires PYPI_TOKEN)
make upload-test           # Upload to TestPyPI (requires TEST_PYPI_TOKEN)
```

### Documentation

```bash
make docs                  # Build HTML documentation (Sphinx)
cd docs && make html       # Direct sphinx build
```

### Cleanup

```bash
make clean                 # Remove build artifacts
make clean-docs            # Clean documentation build
make clean-all             # Clean all build artifacts and cache files
```

## Critical Architectural Constraints

### State Management Rule (CRITICAL)

**Routines MUST NOT modify instance variables during execution.**

```python
# ✅ CORRECT: Store execution state in JobState
flow = self.get_execution_context().flow
job_state = self.get_execution_context().job_state
job_state.update_routine_state(routine_id, {"status": "completed"})

# ❌ WRONG: Modify instance variables
self.counter += 1  # Breaks concurrent execution!
```

**Why?** The same routine instance can be used by multiple concurrent executions. Instance variables would cause data corruption between executions. All execution state must be stored in JobState.

### Routine Configuration Pattern

Routines should use the `_config` dictionary for configuration (not constructor parameters):

```python
class MyProcessor(Routine):
    def __init__(self):
        super().__init__()
        # Set configuration (persists across serialization)
        self.set_config(
            name="my_processor",
            timeout=30,
            max_retries=3
        )

    def process(self, **kwargs):
        # Read configuration during execution
        timeout = self.get_config("timeout", default=10)
        max_retries = self.get_config("max_retries", default=1)

        # Store execution state in JobState
        ctx = self.get_execution_context()
        ctx.job_state.update_routine_state(ctx.routine_id, {
            "processed": True,
            "timeout_used": timeout
        })
```

**Why?** Routines must be serializable. Constructor parameters break serialization. All configuration should be stored in `_config` which is automatically included in serialization.

### Non-Blocking emit()

```python
# emit() is now non-blocking (v0.9.0+)
self.emit("output", data="value")  # Returns immediately

# Flow is automatically detected from routine context
# No need to pass flow parameter in most cases
```

### Flow/JobState Decoupling

```python
# Each execute() returns an independent JobState
job_state = flow.execute(entry_routine_id, entry_params={...})

# Flow does NOT store execution state
# flow.job_state does NOT exist (removed in v0.9.0)

# Pause/resume/cancel require JobState as first argument
flow.pause(job_state)
flow.resume(job_state)
flow.cancel(job_state)
```

### Serialization Requirements

All data must be serializable for persistence/resume:
- Use JSON-compatible types (str, int, float, bool, list, dict, None)
- Avoid callables, file handles, or complex objects
- Use serilux for complex object serialization if needed

## Key Patterns

### Error Handling Strategies

```python
from routilux import ErrorHandler, ErrorStrategy

# STOP: Immediate halt (default)
handler = ErrorHandler(ErrorStrategy.STOP)

# CONTINUE: Log and continue
handler = ErrorHandler(ErrorStrategy.CONTINUE)

# RETRY: Retry with exponential backoff
handler = ErrorHandler(
    ErrorStrategy.RETRY,
    max_retries=3,
    retry_delay=1.0,
    backoff_multiplier=2.0
)

# SKIP: Skip failed routine
handler = ErrorHandler(ErrorStrategy.SKIP)

# Priority: Routine-level > Flow-level > Default (STOP)
routine.set_error_handler(handler)  # Highest priority
flow.set_error_handler(handler)    # Medium priority
```

### Slot Data Merging

```python
# Override: New data replaces old (default)
slot = routine.define_slot("input", handler=process, merge_strategy="override")

# Append: Accumulate values in lists
slot = routine.define_slot("input", handler=aggregate, merge_strategy="append")

# Custom: User-defined merge function
def custom_merge(old, new):
    return {**old, **new, "timestamp": time.time()}

slot = routine.define_slot("input", handler=process, merge_strategy=custom_merge)
```

### DSL Usage

```python
from routilux.dsl import load_flow_from_spec
import yaml

# Load from YAML file
with open("flow.yaml") as f:
    spec = yaml.safe_load(f)
flow = load_flow_from_spec(spec)

# YAML format:
# flow_id: example_flow
# routines:
#   processor:
#     class: mymodule.MyProcessor
#     config:
#       transform_func: "lambda x: x * 2"
# connections:
#   - from: processor.output
#     to: validator.input
```

### FlowBuilder Pattern

For complex workflows, use FlowBuilder for a fluent API:

```python
from routilux.flow import FlowBuilder

builder = FlowBuilder(flow_id="my_workflow")

# Add routines with chaining
builder.add_routine("processor", DataProcessor()) \
       .add_routine("validator", DataValidator()) \
       .connect("processor", "output", "validator", "input")

# Build and execute
flow = builder.build()
job_state = flow.execute("processor", entry_params={"data": "test"})
```

### Execution Strategies

```python
# Sequential mode (default): max_workers=1
flow = Flow()

# Concurrent mode: max_workers>1
flow.set_execution_strategy("concurrent", max_workers=4)

# Both use the SAME unified event queue
# Only worker count differs
# Tasks processed fairly in queue order
```

## API Server (Monitoring & Debugging)

FastAPI-based REST API + WebSocket server in `routilux/api/`:

**Starting the server**:
```bash
python -m routilux.api.main
# Or with custom host/port:
uvicorn routilux.api.main:app --host 0.0.0.0 --port 8000
```

**REST Endpoints**:
- `/api/flows` - Flow CRUD operations
- `/api/jobs` - Job execution and monitoring
- `/api/jobs/{job_id}/breakpoints` - Breakpoint management
- `/api/jobs/{job_id}/debug` - Debug controls (step over/into, variables)
- `/api/jobs/{job_id}/metrics` - Execution metrics

**WebSockets**:
- `/api/ws/jobs/{job_id}/monitor` - Real-time monitoring
- `/api/ws/jobs/{job_id}/debug` - Debug events

**Core monitoring system** (in `routilux/monitoring/`):
- `monitor_collector.py` - Event/data collection from running flows
- `breakpoint_manager.py` - Breakpoint condition evaluation
- `breakpoint_condition.py` - Condition evaluation for breakpoints
- `debug_session.py` - Interactive debugging state management
- `hooks.py` - Execution hooks for pre/post slot processing
- `event_manager.py` - Event streaming and management
- `storage.py` - Debug session persistence
- Plus: `MonitoringRegistry`, `ExecutionMetrics`, `RoutineMetrics`, `ErrorRecord`

**Auto-enable monitoring**: Set environment variable `ROUTILUX_ENABLE_MONITORING=true`

**See `examples/run_debugger_server.py` for a complete debugging setup.**

## Analysis & Testing Tools

### Workflow Analysis

Routilux includes built-in analysis tools for understanding workflow structure:

```python
from routilux import analyze_workflow, WorkflowAnalyzer, WorkflowD2Formatter

# Analyze a flow
analyzer = WorkflowAnalyzer(flow)
analysis = analyzer.analyze()

# Generate D2 diagram (https://d2lang.com/)
formatter = WorkflowD2Formatter()
d2_output = formatter.format(analysis)
print(d2_output)  # Copy to https://play.d2lang.com/

# Or use the convenience function
analysis_result = analyze_workflow(flow)
```

**Analysis components** (in `routilux/analysis/`):
- `analyzers/workflow.py` - `WorkflowAnalyzer` for flow structure, dependencies, and patterns
- `analyzers/routine.py` - `RoutineAnalyzer` for individual routine structure
- `exporters/workflow_d2.py` - `WorkflowD2Formatter` exports to D2 diagram format
- `exporters/routine_markdown.py` - `RoutineMarkdownFormatter` documents routines as markdown
- `exporters/base.py` - `BaseFormatter` for custom exporters

### Testing Utilities

The `routilux.testing.RoutineTester` class provides utilities for testing routines in isolation:

```python
from routilux.testing import RoutineTester

# Create tester for a routine
tester = RoutineTester(MyRoutine())

# Test slot activation
result = tester.activate_slot("input", data="test")
assert result["status"] == "success"

# Verify event emissions
events = tester.get_emitted_events()
assert len(events) == 1
assert events[0].name == "output"
```

## Common Pitfalls

1. **Modifying instance variables in routines**: Always use JobState for execution state
2. **Assuming emit() blocks**: emit() is non-blocking, returns immediately
3. **Accessing flow.job_state**: This field was removed in v0.9.0
4. **Sharing state between executions**: Each execute() is independent, use aggregation patterns
5. **Non-serializable data**: All data must be JSON-serializable for persistence
6. **Retry strategy with broad exceptions**: RETRY only works for specific exception types listed in `retryable_exceptions`
7. **Slot merge in concurrent mode**: Slot merging is not atomic in concurrent mode

## Execution Context Pattern

The recommended way to access execution context is through the `ExecutionContext` NamedTuple:

```python
from routilux.routine import ExecutionContext

# In your routine handler
ctx: ExecutionContext = self.get_execution_context()
# ctx.flow -> Flow instance
# ctx.job_state -> JobState instance
# ctx.routine_id -> str (routine identifier)

# Thread-safe access via ContextVar
# Routilux uses contextvars for concurrent execution safety
```

## Status Values

**ExecutionStatus** (JobState): `PENDING`, `RUNNING`, `PAUSED`, `COMPLETED`, `FAILED`, `CANCELLED`

**RoutineStatus** (individual routines): `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `ERROR_CONTINUED`, `SKIPPED`

Note: `ERROR_CONTINUED` is set when CONTINUE error strategy is used and an error occurs.

## Dependencies

### Core Dependencies
- **serilux** (>=0.3.1): Serialization framework for Routilux objects
- **pyyaml** (>=6.0): YAML DSL support

### Optional Dependencies
- **api** extra: FastAPI, uvicorn, websockets, pydantic, httpx
- **dev** extra: pytest, pytest-cov, ruff, mypy, sphinx
- **docs** extra: Sphinx, sphinx-rtd-theme, furo, sphinx-autodoc-typehints

### Python Version Support
- **Supported**: Python 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14
- **Tested on**: All versions via CI/CD
- **Version range**: `>=3.8,<3.15` (excludes 3.15+)

## Related Projects

- **Varlord**: Configuration management library
- **Serilux**: Serialization framework
- **Lexilux**: Unified LLM API client library

All part of the Agentsmith open-source ecosystem.

## File Locations

- Main package: `/home/percy/works/mygithub/routilux/routilux/`
- Core tests: `/home/percy/works/mygithub/routilux/tests/`
- Examples: `/home/percy/works/mygithub/routilux/examples/`
- API server: `/home/percy/works/mygithub/routilux/routilux/api/`
- Documentation: `/home/percy/works/mygithub/routilux/docs/`
- Playground: `/home/percy/works/mygithub/routilux/playground/` (experimental features)

## CI/CD

The project uses GitHub Actions with workflows in `.github/workflows/`:

- **ci.yml**: Runs tests on Python 3.8-3.14, linting, format checking, and coverage upload
- **release.yml**: Handles PyPI releases with version verification and artifact generation

Coverage is uploaded to Codecov from Python 3.14 tests only.

## Examples Directory

The `examples/` directory contains 14 demos covering:
- `basic_example.py` - Simple workflow
- `complex_routine_demo.py` - Complex routine patterns
- `data_processing.py` - Multi-stage pipeline
- `concurrent_flow_demo.py` - Parallel execution
- `error_handling_example.py` - Error strategies
- `job_state_management.py` - Job state operations
- `llm_agent_complex_demo.py` - Complex agent orchestration
- `retry_with_router_demo.py` - Retry with routing patterns
- `state_management_example.py` - State tracking
- `aggregator_demo.py` - Fan-in/fan-out patterns
- `debugger_test_app.py` - Debugging system usage
- `run_debugger_server.py` - Start monitoring server
- `register_test_flows.py` - Test flow registration
- `overseer_demo_app.py` - Overseer API demo

Run examples with: `python examples/<name>.py`
