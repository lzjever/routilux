# Retry and Serialization Demonstration

## Overview

This demo demonstrates routilux's ability to handle retry logic with serialization and cross-host recovery. It shows how a flow with a retry-enabled routine can be serialized during execution and resumed on a different host, with retry state correctly preserved.

## Features

1. **Long-Running Flow**: A flow that takes time to execute, allowing serialization during execution
2. **Retry Configuration**: A routine configured to retry up to 4 times on failure
3. **Intentional Failures**: The routine intentionally fails after a delay to simulate transient errors
4. **State Serialization**: Flow and JobState are serialized after 2 failures and saved to file
5. **Cross-Host Recovery**: Simulates loading and resuming execution on a different host
6. **Retry State Preservation**: Verifies that retry count is correctly preserved across serialization
7. **Flow Termination**: Verifies that flow correctly stops after all retries are exhausted

## Architecture

### Flow Structure

```
LongRunningRoutine → FailingRoutine (retry 4x) → SuccessRoutine
```

- **LongRunningRoutine**: Takes ~1 second to complete, simulates a long operation
- **FailingRoutine**: Intentionally fails after 0.5s delay, configured with 4 retries
- **SuccessRoutine**: Should NOT execute (flow stops after retries exhausted)

### Execution Flow

1. **Host A - Initial Execution**:
   - Flow starts execution
   - LongRunningRoutine completes
   - FailingRoutine attempts execution
   - FailingRoutine fails (attempt 1)
   - Error handler retries (attempt 2)
   - FailingRoutine fails again (attempt 2)
   - **State saved to file** (after 2 failures)
   - Execution continues (if not paused)

2. **Host B - Resume Execution**:
   - Load Flow and JobState from file
   - Deserialize both objects
   - Resume execution with `flow.resume(job_state)`
   - **Routilux automatically recovers tasks from slot data** (if not in pending_tasks)
   - FailingRoutine continues retrying (attempts 3, 4, 5)
   - All retries fail
   - Flow status set to "failed"
   - SuccessRoutine does NOT execute

## Key Components

### FailingRoutine

A routine that intentionally fails after a delay:

```python
class FailingRoutine(Routine):
    def __init__(self, delay: float = 0.5):
        self.delay = delay
        self.attempt_count = 0
    
    def process(self, data=None, **kwargs):
        self.attempt_count += 1
        time.sleep(self.delay)  # Delay before failure
        raise ValueError(f"Simulated failure on attempt {self.attempt_count}")
```

### Error Handler Configuration

The FailingRoutine is configured with:

```python
error_handler = ErrorHandler(
    strategy=ErrorStrategy.RETRY,
    max_retries=4,
    retry_delay=0.3,
    retry_backoff=1.5,
    retryable_exceptions=(ValueError,),
)
failing.set_error_handler(error_handler)
```

### Serialization

Flow and JobState are serialized separately:

```python
# Serialize
flow_data = flow.serialize()
job_state_data = job_state.serialize()

# Save to file
save_data = {
    "flow": flow_data,
    "job_state": job_state_data,
    "saved_at": time.time(),
    "failure_count": failure_count,
    "retry_count": retry_count,
}
```

### Deserialization and Resume

```python
# Load from file
with open(save_path, "r") as f:
    save_data = json.load(f)

# Deserialize Flow
new_flow = Flow()
new_flow.deserialize(save_data["flow"])

# Deserialize JobState
new_job_state = JobState()
new_job_state.deserialize(save_data["job_state"])

# Resume execution
resumed_job_state = new_flow.resume(new_job_state)
```

## Expected Behavior

### Retry Count Preservation

The `retry_count` in ErrorHandler should be preserved across serialization:

- **Before serialization**: `error_handler.retry_count = 2` (after 2 failures)
- **After deserialization**: `error_handler.retry_count = 2` (correctly restored)
- **After resume**: Retries continue from count 2, attempting 3, 4, and 5

### Flow Termination

After all retries are exhausted:

- Flow status should be `"failed"`
- SuccessRoutine should NOT execute
- Execution history should show 5 failed attempts (1 initial + 4 retries)

## Running the Demo

```bash
cd routilux/playground/retry_serialization_demo
python retry_demo.py
```

## Output

The demo will show:

1. Flow creation with retry configuration
2. Host A execution and state saving
3. Host B loading and resuming
4. Verification of retry behavior
5. Final execution status

Example output:

```
================================================================================
Creating Flow with Retry Configuration
================================================================================

Configuring retry for 'failing' routine:
  - max_retries: 4
  - retry_delay: 0.3s
  - retry_backoff: 1.5

Flow created:
  - Flow ID: retry_serialization_demo
  - Routines: ['long_running', 'failing', 'success']
  - Entry routine: <routine_id>

================================================================================
🌐 Host A: Executing Flow and Saving State
================================================================================

Step 1: Starting flow execution...
  Job ID: <job_id>
  Initial status: running

Step 2: Monitoring execution...
  Status: running     | Failures: 0/2 | Retry count: 0/4
  Status: running     | Failures: 1/2 | Retry count: 1/4
  Status: running     | Failures: 2/2 | Retry count: 2/4

⚠️  2 failures detected! Saving state...
✅ State saved to: storage/flow_state_<job_id>.json
   - Flow ID: retry_serialization_demo
   - Job ID: <job_id>
   - Failures: 2
   - Retry count: 2

================================================================================
🌐 Host B: Loading State and Resuming Execution
================================================================================

Step 1: Loading state from flow_state_<job_id>.json...
  Saved at: <timestamp>
  Failure count: 2
  Retry count: 2

Step 2: Deserializing Flow...
  Flow ID: retry_serialization_demo
  Routines: ['long_running', 'failing', 'success']
  Failing routine error handler:
    - Strategy: ErrorStrategy.RETRY
    - Max retries: 4
    - Retry count: 2  ← Correctly preserved!
    - Retry delay: 0.3

Step 3: Deserializing JobState...
  Job ID: <job_id>
  Status: running
  Execution history: <n> records

Step 4: Resuming execution...
  Expected: Remaining retries should work correctly
  Expected: Flow should stop after all retries exhausted

Step 5: Waiting for execution to complete...
  Final status: failed
  Final retry count: 4/4

================================================================================
📊 Verification Results
================================================================================

Expected behavior:
  - FailingRoutine should attempt 5 times (1 initial + 4 retries)
  - All attempts should fail
  - Flow status should be 'failed'
  - SuccessRoutine should NOT execute (flow stops before)

Actual results:
  - Flow status: failed
  - SuccessRoutine executed: False

✅ Flow correctly stopped after all retries exhausted
✅ SuccessRoutine correctly did not execute (flow stopped before)
```

## Files

- `retry_demo.py`: Main demonstration script
- `failing_routine.py`: Routines used in the demo
- `README.md`: This document
- `storage/`: Directory for saved state files (created automatically)

## Key Insights

1. **Retry State Preservation**: The `retry_count` in ErrorHandler is correctly serialized and restored, allowing retries to continue from the correct count after deserialization.

2. **Flow and JobState Separation**: Flow (workflow definition) and JobState (execution state) are serialized separately, allowing proper recovery.

3. **Resume Behavior**: `flow.resume(job_state)` correctly restores execution state and continues from where it left off.

4. **Error Handler Serialization**: ErrorHandler's `retry_count` is included in serialization, ensuring retry state is preserved.

5. **Automatic Task Recovery**: Routilux automatically recovers tasks from slot data during `resume()`. You don't need to manually check slot data or create tasks - the library handles this automatically. This works even if you serialize without pausing (some tasks may be in the queue rather than pending_tasks).

## Potential Issues and Solutions

### Issue: Retry count not preserved

If retry count is not preserved after deserialization, check:

1. ErrorHandler's `retry_count` is in `add_serializable_fields()`
2. ErrorHandler is correctly attached to the routine
3. Serialization includes routine's error handler

### Issue: Flow doesn't stop after retries

If flow continues after retries are exhausted, check:

1. ErrorHandler's `handle_error()` returns `False` when `retry_count >= max_retries`
2. Flow correctly handles the return value from error handler
3. Flow status is set to "failed" when retries are exhausted

## Testing

To test the demo:

1. Run the demo and observe output
2. Check that state is saved after 2 failures
3. Verify that retry count is preserved (should be 2)
4. Verify that remaining retries work (attempts 3, 4, 5)
5. Verify that flow stops after all retries exhausted
6. Verify that SuccessRoutine does NOT execute

## Conclusion

This demo demonstrates that routilux fully supports:

- ✅ Retry configuration at routine level
- ✅ Retry state preservation across serialization
- ✅ Cross-host execution recovery
- ✅ Automatic task recovery from slot data
- ✅ Proper flow termination after retries exhausted

**Key Takeaway**: Routilux handles all the complexity of state recovery automatically. You simply:
1. Serialize Flow and JobState separately
2. Deserialize both on the target host
3. Call `flow.resume(job_state)`

The library automatically:
- Recovers tasks from slot data (if not in pending_tasks)
- Preserves retry state
- Restores connection information
- Continues execution seamlessly

You don't need to manually check slot data, create tasks, or handle any of the recovery logic - it's all handled by the library.

If any of these features don't work as expected, the demo will highlight the issue and help identify what needs to be improved.

