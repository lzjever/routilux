# LLM Agent Cross-Host Interrupt and Recovery Demo

## Overview

This demo demonstrates a complete LLM agent workflow system with cross-host interrupt and recovery capabilities using routilux. It showcases how an LLM agent can pause execution when user input is needed, save state to cloud storage, and resume execution on a different host.

## Features

1. **Active Interruption**: LLM Agent Routine can pause execution from within its handler when user input is needed
2. **State Persistence**: Execution state is automatically saved to cloud storage (simulated)
3. **Cross-Host Recovery**: Load state from cloud storage and continue execution on a different host
4. **Deferred Events**: Use `emit_deferred_event()` to ensure events are emitted on resume
5. **Shared Data**: Use `shared_data` and `shared_log` to store execution data
6. **Comprehensive Logging**: Detailed logging system to help understand execution flow

## Architecture

### Directory Structure

```
playground/llm_agent_cross_host/
├── __init__.py              # Package initialization
├── logger.py                # Logging utility
├── mock_llm.py              # Mock LLM service
├── mock_storage.py          # Mock cloud storage service
├── enhanced_routine.py      # Enhanced Routine base class (convenience methods)
├── llm_agent_routine.py     # LLM Agent Routine implementation
├── cross_host_demo.py       # Complete cross-host recovery demonstration
└── README.md                # This document
```

### Component Diagram

```
┌─────────────────┐
│  Cross-Host     │
│     Demo        │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
┌───▼───┐ ┌──▼────┐
│ Host A│ │Host B │
└───┬───┘ └──┬────┘
    │        │
    │        │
┌───▼────────▼───┐
│  Flow +        │
│  JobState      │
└───┬────────────┘
    │
┌───▼────────────┐
│ LLM Agent      │
│   Routine      │
└───┬────────────┘
    │
┌───▼────┐  ┌──────▼──────┐
│  LLM   │  │   Storage    │
│Service │  │   Service    │
└────────┘  └──────────────┘
```

## Design Patterns

### 1. Enhanced Routine Pattern

The `EnhancedRoutine` class extends the base `Routine` class with convenience methods without modifying the core routilux library:

- **`pause_execution()`**: Convenient method to pause execution from within a routine
- **`save_execution_state()`**: Convenient method to save execution state to cloud storage

This pattern allows extending functionality without core library changes.

### 2. Deferred Event Pattern

Instead of directly emitting events before pausing, use `emit_deferred_event()`:

```python
# ✅ Correct: Deferred event
self.emit_deferred_event("user_input_required", question=question)
self.pause_execution(reason="Waiting for user input")

# ❌ Wrong: Direct emit
self.emit("user_input_required", question=question)  # May execute immediately
self.pause_execution(reason="Waiting for user input")
```

This ensures events are emitted when execution resumes, not before pausing.

### 3. State Persistence Pattern

Execution state is serialized and saved to cloud storage:

1. Serialize Flow (workflow definition)
2. Serialize JobState (execution state)
3. Save both to cloud storage
4. Load and deserialize on another host
5. Resume execution

### 4. Shared Data Pattern

Use `JobState.shared_data` and `JobState.shared_log` to store execution-wide data:

- **shared_data**: Key-value store for shared data
- **shared_log**: Append-only log for execution history

This allows routines to share data without modifying routine instance variables.

## Code Overview

### Core Components

#### 1. PlaygroundLogger (`logger.py`)

Structured logging system with:
- Log levels: DEBUG, INFO, WARNING, ERROR
- Log categories: FLOW, ROUTINE, STATE, STORAGE, LLM, EVENT, EXECUTION
- Timestamps and relative time
- Section and subsection formatting
- Step numbering

#### 2. MockLLMService (`mock_llm.py`)

Simulates LLM API calls:
- `generate(prompt)`: Generate response
- `generate_with_question(context)`: Generate response with question
- `chat(messages)`: Chat-style API

**Real Implementation**: Replace with actual LLM API (OpenAI, Anthropic, etc.)

#### 3. MockCloudStorage (`mock_storage.py`)

Simulates cloud storage:
- `put(key, data)`: Save data
- `get(key)`: Retrieve data
- `delete(key)`: Delete data
- `list_keys(prefix)`: List keys
- `exists(key)`: Check existence

**Real Implementation**: Replace with actual cloud storage (S3, Redis, database, etc.)

#### 4. EnhancedRoutine (`enhanced_routine.py`)

Extended Routine base class with convenience methods:
- `pause_execution(reason, checkpoint)`: Pause execution
- `save_execution_state(storage_key)`: Save execution state

#### 5. LLMAgentRoutine (`llm_agent_routine.py`)

LLM Agent Routine implementation:

**Slots**:
- `trigger`: Entry slot, receives task
- `user_input`: Receives user input
- `continue`: Continue processing

**Events**:
- `output`: Output result
- `question`: Question event (deferred)
- `completed`: Completion event

**Execution Flow**:
1. Receive task via trigger slot
2. Call LLM service to process task
3. If LLM needs user input, pause execution
4. Save state to cloud storage
5. Resume after user input
6. Process user response
7. Complete workflow

#### 6. Cross-Host Demo (`cross_host_demo.py`)

Complete demonstration:
- `create_flow()`: Create workflow
- `host_a_execute_and_save()`: Host A execution and save
- `host_b_load_and_resume()`: Host B load and resume
- `main()`: Main demonstration function

## Execution Flow

### Phase 1: Initialization

```
1. Initialize logger
   - Create PlaygroundLogger instance
   - Set verbose mode and timestamps

2. Initialize LLM service
   - Create MockLLMService instance
   - Set simulated delay (0.05s)

3. Initialize cloud storage
   - Create MockCloudStorage instance
   - Set storage path

4. Create workflow
   - Create Flow object
   - Create LLMAgentRoutine instance
   - Add Routine to Flow
```

### Phase 2: Host A Execution

```
Step 1: Start execution
  - Call flow.execute(entry_id, entry_params={"task": "..."})
  - Flow creates new JobState
  - Start event_loop thread
  - Call trigger slot handler

Step 2: LLM Agent processes task
  - process() method called
  - Extract task parameter
  - Call LLM service to process task
  - LLM returns response and question

Step 3: Save state
  - Save LLM result to shared_data
  - Update routine state to "processing"
  - Detect need for user input

Step 4: Prepare pause
  - Use emit_deferred_event() to save event (emit on resume)
  - Call save_execution_state() to save to cloud storage
  - Log pause

Step 5: Pause execution
  - Call pause_execution()
  - flow.pause() executes:
    * Set flow._paused = True
    * Wait for all active tasks to complete
    * Move pending tasks to _pending_tasks
    * Serialize pending tasks to JobState
    * Set job_state.status = "paused"
  - Execution paused, JobState status = "paused"
```

### Phase 3: Host B Recovery

```
Step 1: Load from cloud storage
  - Use storage_key to load data from cloud storage
  - Get serialized Flow and JobState data

Step 2: Deserialize Flow
  - Create new Flow object
  - Call flow.deserialize() to restore workflow definition
  - Restore routines and connections

Step 3: Deserialize JobState
  - Create new JobState object
  - Call job_state.deserialize() to restore execution state
  - Restore all state data (routine_states, execution_history, etc.)

Step 4: Set user response
  - Save user response to shared_data
  - Prepare to resume execution

Step 5: Resume execution
  - Call flow.resume(job_state)
  - resume() executes:
    * Set job_state.status = "running"
    * Deserialize pending_tasks
    * Automatically emit deferred_events
    * Add pending_tasks to queue
    * Start event_loop

Step 6: Process user input
  - Find LLM Agent Routine
  - Call user_input slot handler
  - handle_user_input() called
  - LLM processes user response
  - Update state and emit events

Step 7: Wait for completion
  - Wait for all tasks to complete
  - JobState status becomes "completed"
```

## User Learning Guide

### Quick Start

1. **Run the demo**:
   ```bash
   cd /home/developer/workspace/routilux
   conda activate mbos
   python -m playground.llm_agent_cross_host.cross_host_demo
   ```

2. **Observe the logs**: The demo outputs detailed logs showing:
   - Each execution step
   - State changes
   - Data flow
   - Key operations

3. **Understand the flow**: Follow the execution from Host A to Host B

### Learning Path

#### Step 1: Understand Basic Concepts

- **Flow**: Workflow definition (routines, connections)
- **JobState**: Execution state (status, routine_states, execution_history)
- **Routine**: Node implementation (slots, events, handlers)
- **Serialization**: Converting objects to/from JSON

#### Step 2: Study the Code

Key files to read:
1. `cross_host_demo.py`: Main demonstration
2. `llm_agent_routine.py`: LLM Agent implementation
3. `enhanced_routine.py`: Convenience methods

#### Step 3: Experiment

Try modifying:
- Task content
- LLM responses
- User input
- Log levels

#### Step 4: Extend

Try:
- Integrating real LLM service
- Integrating real cloud storage
- Adding new routines
- Customizing logging

### Key Concepts to Learn

1. **Deferred Events**: Why use `emit_deferred_event()` instead of `emit()`
2. **State Persistence**: How execution state is serialized and restored
3. **Cross-Host Recovery**: How to transfer and resume execution
4. **Shared Data**: How routines share data via JobState
5. **Pause/Resume**: How execution can be paused and resumed

## Performance Analysis

### Performance Metrics (Measured)

| Operation | Time | Notes |
|-----------|------|-------|
| Initialization | <1ms | Service initialization |
| Single LLM call | 50ms | Simulated delay |
| Flow serialization | 0.214ms | ~1.4KB data |
| JobState serialization | 0.011ms | ~1.1KB data |
| Flow deserialization | 0.257ms | Restore Flow |
| JobState deserialization | 0.027ms | Restore JobState |
| Pause execution | ~1ms | Pause operation |
| Resume execution | <1ms | Resume operation |

### Performance Timeline

```
Timeline (seconds)    Operation                      Duration
─────────────────────────────────────────────────────────────
0.000                 Initialize services            <1ms
0.000                 Create Flow                    <1ms
0.000                 Start execution                <1ms
0.001 → 0.051         LLM process task              50ms ⭐
0.051 → 0.052         Serialize and save state      1ms
0.052 → 0.053         Pause execution               1ms
0.053 → 0.151         execute() returns             98ms
─────────────────────────────────────────────────────────────
0.151                 Load from cloud storage        <1ms
0.151 → 0.152         Deserialize Flow and JobState 1ms
0.152                 Resume execution               <1ms
0.152 → 0.202         LLM process user input        50ms ⭐
0.202 → 10.211        Wait for completion (timeout) 10s ⚠️
─────────────────────────────────────────────────────────────
Total: ~10.2 seconds
```

### Performance Bottlenecks

1. **LLM Call Delay** ⭐⭐⭐
   - **Issue**: Each LLM call takes 50ms (simulated delay)
   - **Total**: 100ms (2 calls)
   - **Impact**: In real scenarios, LLM API calls may be slower (hundreds of ms to seconds)
   - **Optimization**: Use async LLM calls, implement request batching, use caching

2. **execute() Return Delay** ⚠️
   - **Issue**: execute() returns after 98ms
   - **Cause**: Waiting for event_loop processing
   - **Impact**: Affects synchronous call response time
   - **Optimization**: Optimize event_loop wait logic, use async execution mode

3. **Wait for Completion Timeout** ⚠️⚠️
   - **Issue**: Wait for completion takes 10 seconds
   - **Cause**: Timeout wait in demo code
   - **Impact**: This is a code issue, not actual execution time
   - **Optimization**: Improve completion detection logic, use callback mechanism

### Performance Advantages

1. **Serialization/Deserialization**: <0.5ms, excellent performance
2. **Pause/Resume**: <2ms, very fast
3. **Initialization**: <1ms, fast startup
4. **Data Size**: <2KB serialized data, fast transmission

### Optimization Recommendations

#### High Priority

1. **Improve wait logic**: Reduce 10s timeout to <100ms
2. **Optimize execute() return**: Reduce 98ms to <10ms

#### Medium Priority

3. **Async LLM calls**: Don't block main flow
4. **Performance monitoring**: Add performance metrics collection

#### Low Priority

5. **Distributed optimization**: Implement true cross-host execution
6. **State compression**: Compress serialized data

## Usage Examples

### Basic Usage

```python
from routilux import Flow
from playground.llm_agent_cross_host.llm_agent_routine import LLMAgentRoutine
from playground.llm_agent_cross_host.mock_storage import get_storage
from playground.llm_agent_cross_host.logger import get_logger

# Initialize logger
logger = get_logger()

# Create flow
flow = Flow(flow_id="my_workflow")
agent = LLMAgentRoutine()
agent_id = flow.add_routine(agent, "agent")

# Execute
logger.info("EXECUTION", "Start execution")
job_state = flow.execute(agent_id, entry_params={"task": "Analyze data"})

# If paused, save state
if job_state.status == "paused":
    storage_key = f"execution_state/{job_state.job_id}"
    flow_data = flow.serialize()
    job_state_data = job_state.serialize()
    storage = get_storage()
    storage.put(storage_key, {
        "flow": flow_data,
        "job_state": job_state_data,
    })
    logger.info("STORAGE", f"State saved: {storage_key}")
```

### Resume Execution

```python
# Load from cloud storage
storage = get_storage()
transfer_data = storage.get(storage_key)

# Deserialize
flow = Flow()
flow.deserialize(transfer_data["flow"])
job_state = JobState()
job_state.deserialize(transfer_data["job_state"])

# Set user response
job_state.update_shared_data("user_response", "I choose option A")

# Resume execution
logger.info("EXECUTION", "Resume execution")
resumed = flow.resume(job_state)

# Trigger user input handler
agent_routine = flow.routines[agent_id]
user_input_slot = agent_routine.get_slot("user_input")
user_input_slot.call_handler({"user_response": "I choose option A"})
```

## Extension Guide

### Integrate Real LLM Service

Replace `mock_llm.py` implementation:

```python
import openai

class RealLLMService:
    def __init__(self, api_key: str):
        self.client = openai.OpenAI(api_key=api_key)
    
    def generate(self, prompt: str, **kwargs) -> str:
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            **kwargs
        )
        return response.choices[0].message.content
    
    def generate_with_question(self, context: str) -> dict:
        # Implement question generation logic
        response = self.generate(f"Analyze: {context}\nGenerate a question for user confirmation.")
        question = self.generate(f"Based on analysis, generate a concise question.")
        return {
            "response": response,
            "question": question,
            "needs_user_input": True,
        }
```

### Integrate Real Cloud Storage

Replace `mock_storage.py` implementation:

```python
import boto3
import json

class S3Storage:
    def __init__(self, bucket: str):
        self.s3 = boto3.client('s3')
        self.bucket = bucket
    
    def put(self, key: str, data: dict):
        self.s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=json.dumps(data, default=str)
        )
    
    def get(self, key: str) -> dict:
        response = self.s3.get_object(Bucket=self.bucket, Key=key)
        return json.loads(response['Body'].read())
```

### Custom Routine

Inherit from `EnhancedRoutine` or `LLMAgentRoutine`:

```python
from playground.llm_agent_cross_host.enhanced_routine import EnhancedRoutine
from playground.llm_agent_cross_host.logger import get_logger

class MyCustomRoutine(EnhancedRoutine):
    def __init__(self):
        super().__init__()
        self.trigger_slot = self.define_slot("trigger", handler=self.process)
        self.output_event = self.define_event("output", ["result"])
    
    def process(self, **kwargs):
        logger = get_logger()
        logger.info("ROUTINE", "Custom processing logic")
        # Your processing logic
        self.emit("output", result="Processing complete")
```

## Common Issues

### Q1: Why didn't execution pause?

**A**: Check:
1. Does LLM service return `needs_user_input=True`?
2. Is `pause_execution()` called?
3. Check state changes in logs

### Q2: Incorrect state after resume?

**A**: Ensure:
1. Both Flow and JobState are correctly serialized/deserialized
2. All Routine classes use `@register_serializable`
3. Check deserialization process in logs

### Q3: Deferred events not executed?

**A**: Ensure:
1. Use `emit_deferred_event()` instead of `emit()`
2. `resume()` automatically emits deferred events
3. Check event handling in logs

### Q4: How to debug execution flow?

**A**: 
1. Enable verbose logging (default enabled)
2. Check logs for steps and state changes
3. Check shared_data and shared_log
4. View execution_history

### Q5: How to customize logging?

**A**: 
```python
from playground.llm_agent_cross_host.logger import PlaygroundLogger, set_logger

# Create custom logger
logger = PlaygroundLogger(verbose=True, show_timestamps=True)
set_logger(logger)

# Use logger
logger.info("CATEGORY", "Message", key=value)
```

## Key Design Points

### 1. Deferred Event Mechanism

Use `emit_deferred_event()` instead of direct `emit()` to ensure events are emitted on resume:

```python
# ✅ Correct
self.emit_deferred_event("user_input_required", question=question)
self.pause_execution(reason="Waiting for user input")

# ❌ Wrong
self.emit("user_input_required", question=question)  # May execute immediately
self.pause_execution(reason="Waiting for user input")
```

### 2. State Persistence

Execution state is included in JobState and automatically serialized:
- Execution state (status, current_routine_id)
- Routine states (routine_states)
- Execution history (execution_history)
- Pending tasks (pending_tasks)
- Deferred events (deferred_events)
- Shared data (shared_data, shared_log)

### 3. Cross-Host Recovery

Both Flow and JobState must be serialized:
- Flow: Contains workflow definition (routines, connections)
- JobState: Contains execution state

### 4. Routine Registration

All custom Routines must use `@register_serializable` decorator:

```python
from serilux import register_serializable

@register_serializable
class MyRoutine(EnhancedRoutine):
    # ...
```

## Notes

1. **Thread Safety**: All operations are thread-safe under CPython's GIL
2. **Serialization Limits**: Ensure all data can be serialized to JSON
3. **Routine Constraints**: Cannot modify Routine instance variables during execution, use JobState to store state
4. **Storage Key Management**: Recommend using `job_id` as part of storage key for uniqueness
5. **Log Performance**: Detailed logs may affect performance, disable DEBUG logs in production

## Summary

This demo system provides:
- ✅ Complete cross-host interrupt and recovery functionality
- ✅ Detailed logging system for learning
- ✅ Clear code structure and documentation
- ✅ Easy-to-extend interfaces
- ✅ Complete example code

By running and observing this system, you can deeply understand routilux's cross-host execution mechanism and build your own applications on this foundation.

