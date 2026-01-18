# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Routilux is an event-driven workflow orchestration framework built in Python. It provides flexible workflow execution with connection management, state tracking, and real-time monitoring capabilities.

**Tech Stack:** Python 3.8-3.14, FastAPI (optional API), serilux (serialization)

**Core Architecture:** Event-driven workflow orchestration with routines communicating via events (output) and slots (input), managed by a central Flow orchestrator.

## Development Commands

### Setup
```bash
make dev-install          # Install package + all dependencies (recommended)
make setup-venv           # Install dependencies only (CI/CD, tools only)
```

### Testing
```bash
make test                 # Core tests only (excludes API, userstory)
make test-cov             # With coverage report (htmlcov/)
make test-api             # API endpoint tests
make test-userstory       # User story integration tests
make test-integration     # Tests requiring external services
make test-unit            # Unit tests only

# Run single test
pytest tests/test_specific.py::test_function -v
```

### Code Quality
```bash
make lint                 # Ruff linting
make format               # Ruff formatting (line-length: 100, double quotes)
make format-check         # Check formatting
make type-check           # Mypy type checking
make check               # Run all checks (lint + format-check + test)
```

### Building & Publishing
```bash
make build               # Create distributions
make check-package       # Verify package
PYPI_TOKEN=xxx make upload       # Upload to PyPI
TEST_PYPI_TOKEN=xxx make upload-test  # Upload to TestPyPI
```

### Documentation
```bash
make docs                # Build Sphinx docs
```

## Architecture Overview

### Core Module (`routilux/core/`)

The workflow engine is built on these key concepts:

- **Routine**: Base class for processing units. Routines define input `slots` and output `events`. They MUST NOT accept constructor parameters (for serialization). Store config in `_config` dict, execution state in `WorkerState`.

- **Flow**: Orchestrator that manages multiple Routine nodes and their connections. Routes events from routine outputs to routine inputs via Connections.

- **Runtime**: Execution environment for posting jobs to flows.

- **Worker**: Each routine runs in its own WorkerExecutor, managed by WorkerManager. Workers maintain state across executions (worker-level state, persistent) vs JobContext (per-request, temporary).

- **Activation Policies**: Control when routines execute:
  - `immediate_policy`: Execute immediately when slot receives data
  - `all_slots_ready_policy`: Wait for all slots to have data
  - `batch_size_policy`: Process in batches
  - `time_interval_policy`: Time-based execution
  - `breakpoint_policy`: Debug breakpoint support
  - `custom_policy`: User-defined policies

- **Slot/Event/Connection**: Data flow mechanisms. Slots receive data (input), Events emit data (output), Connections link events to slots.

### Flow Management (`routilux/flow/`)

- **FlowBuilder**: Declarative flow construction
- **Validation**: Flow structure validation
- **State Management**: Job state persistence (pending → running → completed/failed/paused/cancelled)

### Monitoring & Debugging (`routilux/monitoring/`)

- **Breakpoint Manager**: Debug breakpoints and conditional execution
- **Event Manager**: Real-time event streaming via WebSocket
- **Monitor Service**: Comprehensive monitoring and metrics
- **Debug Session**: Interactive debugging workflows

### HTTP API Server (`routilux/server/`)

FastAPI-based REST API with routes for:
- Flows, jobs, workers, runtimes
- Breakpoints and debugging
- WebSocket monitoring
- Route modules in `routilux/server/routes/`

## Key Architectural Patterns

### Event-Driven Communication
Routines communicate via events (output) and slots (input) with async, decoupled execution.

### Registry Pattern
Central registries (`FlowRegistry`, `WorkerRegistry`) for global flow/worker management with plugin-like architecture.

### State Management Hierarchy
1. **Worker-level state** (`WorkerState`): Long-running, persistent across executions
2. **Job-level state** (`JobContext`): Per-request, temporary - access via `get_current_job()`

### Output Capture
Use `install_routed_stdout()` at program startup to route print() statements to job-specific output buffers. Retrieve via `get_job_output(job_id)`.

## Important Constraints

### Routine Design
- Routines MUST NOT accept constructor parameters (serialization requirement)
- Store configuration in `_config` dictionary (read-only during execution)
- Store execution state in `WorkerState` via `worker_state.update_routine_state()`
- Use `JobContext` (via `get_current_job()`) for per-request state

### Code Style
- Line length: 100 characters
- Double quotes for strings
- Ruff for linting/formatting
- Mypy for type checking (Python 3.7 target)

### Test Organization
- Core tests: `tests/`
- User story tests: `tests/userstory/` (multi-API workflows)
- Markers: `@pytest.mark.integration`, `@pytest.mark.api`, `@pytest.mark.userstory`
- Parallel execution via pytest-xdist (`-n auto`)

## Dependency Management

**Preferred:** UV (modern Python packaging)
```bash
uv sync --group docs --all-extras
```

**Fallback:** pip + virtualenv
```bash
pip install -e ".[dev]"
```

## Current Branch Status

Branch: `refactor/architecture-v2` - Major architectural cleanup and refactoring in progress. Legacy modules have been removed, and the codebase has been restructured around the core/flow/monitoring/server architecture.
