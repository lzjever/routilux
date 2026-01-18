# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# Install package with all development dependencies (uses uv if available)
make dev-install

# Run tests
make test                    # Run core tests (excluding API tests)
make test-cov                # Run tests with coverage
make test-unit               # Run only unit tests
make test-api                # Run API endpoint tests
make test-integration        # Run integration tests

# Run a single test file
pytest tests/test_core_flow.py -v

# Run a single test function
pytest tests/test_core_flow.py::test_flow_add_routine -v

# Code quality
make lint                    # Run ruff linting
make format                  # Format code with ruff
make format-check            # Check formatting without modifying
make type-check              # Run mypy type checking
make check                   # Run all checks (lint + format check + tests)

# Build and docs
make build                   # Build source and wheel distributions
make docs                    # Build documentation
```

## Architecture Overview

Routilux is an event-driven workflow orchestration framework with a layered architecture:

```
routilux/                    # Package root
├── core/                    # Core workflow engine (zero external deps, only serilux)
│   ├── routine.py           # Routine base class
│   ├── event.py             # Event class for data emission
│   ├── slot.py              # Slot class for data reception
│   ├── connection.py        # Connection between event and slot
│   ├── flow.py              # Flow (workflow definition)
│   ├── worker.py            # WorkerState (long-running worker state)
│   ├── executor.py          # WorkerExecutor (per-worker task execution)
│   ├── manager.py           # WorkerManager (global worker manager)
│   ├── runtime.py           # Runtime (central execution manager)
│   ├── context.py           # JobContext (per-request execution context)
│   ├── output.py            # RoutedStdout (stdout capture by job_id)
│   ├── registry.py          # FlowRegistry, WorkerRegistry
│   ├── status.py            # Status enums (ExecutionStatus, RoutineStatus, JobStatus)
│   ├── error.py             # ErrorHandler, ErrorStrategy
│   ├── hooks.py             # Abstract execution hooks interface
│   └── task.py              # SlotActivationTask, EventRoutingTask
│
├── monitoring/              # Optional monitoring (depends on core)
│   ├── monitor_service.py   # Monitoring service
│   ├── event_manager.py     # Event management
│   ├── runtime_registry.py  # Runtime registry
│   └── ...                  # Breakpoint, debug, WebSocket support
│
├── server/                  # Optional FastAPI server (depends on core + monitoring)
│   ├── main.py              # FastAPI application entry point
│   ├── routes/              # API endpoints (flows, workers, jobs, monitor, debug)
│   ├── models/              # Pydantic models for API
│   └── storage/             # Storage abstraction (memory, database)
│
├── flow/                    # Flow builder utilities
├── tools/                   # Analysis, DSL, factory, testing utilities
└── activation_policies.py   # Built-in activation policies
```

### Key Architectural Concepts

**Worker vs Job (Important Terminology)**

- **Worker**: A long-running execution context for a Flow (was called `JobState` in older versions). A worker maintains routine state, execution history, and can process multiple jobs over its lifetime.
- **Job**: A single execution request (like an HTTP request). Jobs are created via `Runtime.post()` and have their own `JobContext` for tracking.

The architecture was recently refactored (see `ARCHITECTURE_REFACTORING_PLAN.md`) to separate concerns properly and enable the core module to work without monitoring dependencies.

**Execution Model**

1. Flows contain Routines connected via Event-Slot connections
2. Workers are created from Flows and maintain long-running state
3. Jobs are submitted to Workers via `Runtime.post()`
4. Each Job has a `JobContext` that propagates through routine execution
5. `RoutedStdout` captures print() output by `job_id` for per-request logging

**Thread Safety**

- All operations are thread-safe by design
- `ContextVar` (`_current_job`, `_current_worker_state`) used for thread-local context
- `WorkerState` uses `RLock` for state mutations
- Independent task queues per worker

**Critical Constraints**

- Routines MUST have parameterless constructors (for serialization)
- Use `self.set_config()` for configuration, not `__init__` parameters
- Store execution state in `JobContext`, not instance variables
- The same Routine object can execute concurrently across different jobs

## Activation Policies

Activation policies control when routines execute based on slot data availability:

```python
from routilux.activation_policies import (
    immediate_policy,           # Activate immediately when any slot receives data
    all_slots_ready_policy,    # Activate when all slots have at least 1 item
    batch_size_policy,          # Activate when all slots have at least N items
    time_interval_policy,       # Activate at most once per time interval
    custom_policy,              # Define your own activation logic
    breakpoint_policy,          # Debug breakpoint (pauses execution)
)

routine.set_activation_policy(immediate_policy())
```

## State Management Patterns

```python
# Configuration (read-only during execution)
self.set_config(name="my_routine", timeout=30)
value = self.get_config("timeout", 10)

# Job-level data (shared across routines in same job)
job_context.set_data("key", value)
value = job_context.get_data("key")

# Worker-level state (persists across jobs)
worker_state.routine_states[routine_id] = {"count": 5}
```

## Output Capture

The framework provides per-job stdout capture via `RoutedStdout`:

```python
from routilux import install_routed_stdout, get_job_output

# Install at program startup (optional, enables print() capture)
install_routed_stdout()

# In routine logic, print() works normally
print("This will be captured per-job")

# Get output for a specific job
output = get_job_output(job_id, incremental=False)
```

## Testing Patterns

Tests use pytest and follow naming conventions:
- `tests/test_core_*.py` - Core module tests
- `tests/test_api_v1.py` - API endpoint tests
- Test markers: `api`, `integration`, `timeout`

Key test utilities:
- `RoutineTester` - For testing individual routines
- Mock workers/jobs for isolated testing

## API Server (Optional)

The FastAPI server (`routilux.server`) provides REST and WebSocket endpoints:

```bash
# Install with server dependencies
pip install routilux[server]

# Run the server
python -m routilux.server.main
```

Key endpoints:
- `/api/flows` - Flow management
- `/api/workers` - Worker lifecycle (was `/api/jobs`)
- `/api/jobs` - Job management (per-request jobs)
- `/api/monitor` - Monitoring and debugging
- WebSocket support for real-time job output streaming

## Dependencies

- **Core**: Only `serilux` (serialization framework)
- **Monitoring**: No additional dependencies
- **Server**: `fastapi`, `uvicorn`, `slowapi`
- **Dev**: `pytest`, `pytest-cov`, `ruff`, `mypy`

## Important Notes

1. **Do not modify instance variables during execution** - use `JobContext` for request state
2. **Routines must have parameterless constructors** - use `set_config()` instead
3. **Use `Runtime.post()`** to submit jobs, not `Runtime.exec()` (deprecated)
4. **Worker vs Job terminology** - Workers are long-running, Jobs are single requests
5. **Thread safety is built-in** - all operations are thread-safe by design
