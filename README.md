# Routilux ⚡

[![PyPI version](https://img.shields.io/pypi/v/routilux.svg)](https://pypi.org/project/routilux/)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![Documentation](https://readthedocs.org/projects/routilux/badge/?version=latest)](https://routilux.readthedocs.io)

**Routilux** is a powerful, event-driven workflow orchestration framework that makes building complex data pipelines and workflows effortless. With its intuitive API and flexible architecture, you can create sophisticated workflows in minutes, not hours.

## ✨ Why Routilux?

- 🚀 **Event Queue Architecture**: Non-blocking event emission with unified execution model for both sequential and concurrent modes
- 🔗 **Flexible Connections**: Many-to-many relationships between routines with intelligent data routing
- 📊 **Built-in State Management**: Track execution state, performance metrics, and history out of the box
- 🛡️ **Robust Error Handling**: Multiple strategies (STOP, CONTINUE, RETRY, SKIP) with automatic recovery
- ⚡ **Concurrent Execution**: Automatic parallelization for I/O-bound operations via unified event queue
- 💾 **Persistence & Recovery**: Save and resume workflows from any point with pending task serialization
- 🎯 **Production Ready**: Comprehensive error handling, execution tracking, and monitoring
- 🎨 **Simplified API**: Automatic flow detection - no need to pass flow parameter in most cases

## 🎯 Perfect For

- **Data Pipelines**: ETL processes, data transformation workflows
- **API Orchestration**: Coordinating multiple API calls with complex dependencies
- **Event Processing**: Real-time event streams and reactive systems
- **Workflow Automation**: Business process automation and task scheduling
- **Microservices Coordination**: Managing interactions between services
- **LLM Agent Workflows**: Complex AI agent orchestration and chaining

## 📦 Installation

### Quick Install (Recommended)

```bash
pip install routilux
```

That's it! You're ready to go.

### Development Install

For development with all dependencies:

```bash
pip install -e ".[dev]"
# Or using Makefile
make dev-install
```

## 🚀 Quick Start

### Create Your First Workflow in 3 Steps

**Step 1: Define a Routine**

```python
from routilux import Routine

class DataProcessor(Routine):
    def __init__(self):
        super().__init__()
        # Define input slot
        self.input_slot = self.define_slot("input", handler=self.process_data)
        # Define output event
        self.output_event = self.define_event("output", ["result"])
    
    def process_data(self, data=None, **kwargs):
        # Flow is automatically detected from routine context
        result = f"Processed: {data}"
        self._stats["processed_count"] = self._stats.get("processed_count", 0) + 1
        self.emit("output", result=result)  # No need to pass flow!
```

**Step 2: Create and Connect a Flow**

```python
from routilux import Flow

flow = Flow(flow_id="my_workflow")

processor1 = DataProcessor()
processor2 = DataProcessor()

id1 = flow.add_routine(processor1, "processor1")
id2 = flow.add_routine(processor2, "processor2")

# Connect: processor1's output → processor2's input
flow.connect(id1, "output", id2, "input")
```

**Step 3: Execute**

```python
job_state = flow.execute(id1, entry_params={"data": "Hello, Routilux!"})
print(job_state.status)  # "completed"
print(processor1.stats())  # {"processed_count": 1}
```

**🎉 Done!** You've created your first workflow.

## 💡 Key Features

### 🔄 Event Queue Architecture

Routines communicate through events and slots using a unified event queue pattern:

```python
# Multiple routines can listen to the same event
flow.connect(processor1, "output", processor2, "input")
flow.connect(processor1, "output", processor3, "input")  # Fan-out

# Multiple events can feed into the same slot
flow.connect(processor1, "output", aggregator, "input")
flow.connect(processor2, "output", aggregator, "input")  # Fan-in

# emit() is non-blocking - returns immediately after enqueuing tasks
# Flow is automatically detected from routine context
self.emit("output", data="value")  # No flow parameter needed!
```

### 🎛️ Flexible State Management

Track everything automatically:

```python
# Access routine state
stats = routine.stats()  # {"processed_count": 42, "errors": 0}

# Track execution history
history = job_state.get_execution_history()

# Performance metrics
perf = flow.execution_tracker.get_routine_performance("processor1")
```

### 🛡️ Built-in Error Handling

Choose the right strategy for your use case:

```python
from routilux import ErrorHandler, ErrorStrategy

# Stop on error (default)
flow.set_error_handler(ErrorHandler(ErrorStrategy.STOP))

# Continue and log errors
flow.set_error_handler(ErrorHandler(ErrorStrategy.CONTINUE))

# Retry with exponential backoff
flow.set_error_handler(ErrorHandler(
    ErrorStrategy.RETRY,
    max_retries=3,
    retry_delay=1.0,
    backoff_multiplier=2.0
))
```

### ⚡ Unified Execution Model

Both sequential and concurrent modes use the same event queue mechanism:

```python
# Sequential mode (default): max_workers=1
flow = Flow()  # Sequential by default

# Concurrent mode: max_workers>1
flow.set_execution_strategy("concurrent", max_workers=4)

# Tasks are processed fairly in queue order
# Long chains don't block shorter ones
job_state = flow.execute(entry_routine_id)
flow.wait_for_completion()  # Wait for async tasks
```

### 💾 Persistence & Recovery

Save and resume workflows:

```python
# Save workflow state
job_state.save("workflow_state.json")

# Later, resume from saved state
saved_state = JobState.load("workflow_state.json")
flow.resume(saved_state)
```

## 📚 Documentation

**📖 Full documentation available at: [routilux.readthedocs.io](https://routilux.readthedocs.io)**

### Documentation Highlights

- **📘 [User Guide](https://routilux.readthedocs.io/en/latest/user_guide/index.html)**: Comprehensive guide covering all features
- **🔧 [API Reference](https://routilux.readthedocs.io/en/latest/api_reference/index.html)**: Complete API documentation
- **💻 [Examples](https://routilux.readthedocs.io/en/latest/examples/index.html)**: Real-world code examples
- **🏗️ [Design](https://routilux.readthedocs.io/en/latest/design/index.html)**: Architecture and design principles

### Build Documentation Locally

```bash
pip install -e ".[docs]"
cd docs && make html
```

## 🎓 Examples

Check out the `examples/` directory for practical examples:

- **`basic_example.py`** - Your first workflow
- **`data_processing.py`** - Multi-stage data pipeline
- **`concurrent_flow_demo.py`** - Parallel execution
- **`error_handling_example.py`** - Error handling strategies
- **`state_management_example.py`** - State tracking and recovery
- **`builtin_routines_demo.py`** - Using built-in routines

Run examples:

```bash
python examples/basic_example.py
```

## 🧩 Built-in Routines

Routilux comes with a rich set of built-in routines ready to use:

- **Text Processing**: `TextClipper`, `TextRenderer`, `ResultExtractor`
- **Data Processing**: `DataTransformer`, `DataValidator`, `DataFlattener`
- **Control Flow**: `ConditionalRouter` for dynamic routing
- **Utilities**: `TimeProvider` for timestamps

```python
from routilux.builtin_routines import ConditionalRouter, DataTransformer

# Use built-in routines directly
router = ConditionalRouter()
transformer = DataTransformer()
```

## 🏗️ Project Structure

```
routilux/
├── routilux/              # Main package
│   ├── routine.py         # Routine base class
│   ├── flow.py            # Flow manager
│   ├── job_state.py       # State management
│   ├── connection.py      # Connection management
│   ├── event.py           # Event class
│   ├── slot.py            # Slot class
│   ├── error_handler.py   # Error handling
│   └── execution_tracker.py # Performance tracking
├── tests/                 # Comprehensive test suite
├── examples/              # Usage examples
└── docs/                  # Sphinx documentation
```

## 🧪 Testing

Routilux comes with comprehensive tests:

```bash
# Run all tests
make test-all

# Run with coverage
make test-cov

# Run specific test suite
pytest tests/                    # Core tests
pytest routilux/builtin_routines/  # Built-in routines tests
```

## 🤝 Contributing

We welcome contributions! Here's how you can help:

1. **Star the project** ⭐ - Show your support
2. **Report bugs** 🐛 - Help us improve
3. **Suggest features** 💡 - Share your ideas
4. **Submit PRs** 🔧 - Contribute code

## 🏢 About Agentsmith

**Routilux** is part of the **Agentsmith** open-source ecosystem. Agentsmith is a ToB AI agent and algorithm development platform, currently deployed in multiple highway management companies, securities firms, and regulatory agencies in China. The Agentsmith team is gradually open-sourcing the platform by removing proprietary code and algorithm modules, as well as enterprise-specific customizations, while decoupling the system for modular use by the open-source community.

### 🌟 Agentsmith Open-Source Projects

- **[Varlord](https://github.com/lzjever/varlord)** ⚙️ - Configuration management library with multi-source support
- **[Routilux](https://github.com/lzjever/routilux)** ⚡ - Event-driven workflow orchestration framework
- **[Serilux](https://github.com/lzjever/serilux)** 📦 - Flexible serialization framework for Python objects
- **[Lexilux](https://github.com/lzjever/lexilux)** 🚀 - Unified LLM API client library

These projects are modular components extracted from the Agentsmith platform, designed to be used independently or together to build powerful applications.


## 📄 License

Routilux is licensed under the **Apache License 2.0**. See [LICENSE](LICENSE) for details.

## 🔗 Links

- **📦 PyPI**: [pypi.org/project/routilux](https://pypi.org/project/routilux)
- **📚 Documentation**: [routilux.readthedocs.io](https://routilux.readthedocs.io)
- **🐙 GitHub**: [github.com/lzjever/routilux](https://github.com/lzjever/routilux)
- **📧 Issues**: [github.com/lzjever/routilux/issues](https://github.com/lzjever/routilux/issues)

## ⭐ Show Your Support

If Routilux helps you build amazing workflows, consider giving it a star on GitHub!

---

**Built with ❤️ by the Routilux Team**

*Making workflow orchestration simple, powerful, and fun.*
