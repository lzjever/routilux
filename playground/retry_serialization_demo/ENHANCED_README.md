# Enhanced Retry and Serialization Demonstration

## Overview

This enhanced demo provides a comprehensive, real-world demonstration of routilux's retry and serialization capabilities. It simulates actual system operations with detailed monitoring, data flow tracking, and cross-host recovery.

## Features

### 1. Real-World Data Processing Flow

The demo simulates a complete data processing pipeline:

```
DataFetchRoutine → DataProcessRoutine (retry 4x) → DataValidatorRoutine → DataStorageRoutine
```

**Routines**:
- **DataFetchRoutine**: Simulates fetching data from external API
  - Generates structured data (user_id, items, metadata)
  - Includes request tracking
  - Emits data with timestamps

- **DataProcessRoutine**: Simulates data processing with retry capability
  - Processes items with transformations
  - May fail due to transient errors (network timeouts)
  - Configured with 4 retries, exponential backoff

- **DataValidatorRoutine**: Validates processed data
  - Checks data quality
  - Generates validation reports

- **DataStorageRoutine**: Stores validated data
  - Simulates database writes
  - Tracks storage transactions

### 2. Detailed Monitoring

**ExecutionMonitor** tracks:
- **Events**: All event emissions with data details
- **Data Flow**: Data transmission between routines
- **State Changes**: Routine state transitions
- **Timing**: Precise timestamps for all operations

### 3. Comprehensive Data Tracking

The demo tracks:
- **Event Data**: Complete data payloads in events
- **Data Flow**: How data moves between routines
- **Execution History**: Complete execution timeline
- **Shared Data**: Data shared across routines
- **State Information**: Routine and flow states

### 4. Cross-Host Recovery

Demonstrates:
- **State Serialization**: Flow and JobState serialization
- **State Preservation**: Retry count and execution state preserved
- **Cross-Host Loading**: Loading state on different host
- **Execution Resume**: Continuing execution from saved state

## Running the Demo

### Basic Demo

```bash
cd routilux/playground/retry_serialization_demo
python enhanced_retry_demo.py
```

### Original Simple Demo

```bash
python retry_demo.py
```

## Output Features

### Event Tracking

```
📤 [ 0.801s] data_fetch.start
   request_id: req_1767445144
📤 [ 0.801s] data_fetch.output
   data: 3 items
      • id:1, name:Product A
      • id:2, name:Product B
      • id:3, name:Product C
   metadata: 3 keys
   timestamp: 2026-01-03T20:59:05.338459
```

### Data Flow Tracking

```
🔀 [ 0.801s] data_fetch → data_process: 3 items
```

Shows how data flows from one routine to another.

### State Changes

```
🔄 [ 5.806s] data_process: previous → failed (retry_count: 4, attempt: 5)
```

Tracks routine state transitions with context.

### Retry Progress

```
📊 Status: running    | Retry: 2/4 | History: 2 records
🔄 [DataProcessRoutine] Attempt 3: Starting data processing...
❌ [DataProcessRoutine] Attempt 3: Transient processing error
```

Shows retry attempts with detailed information.

## Key Demonstrations

### 1. Retry Mechanism

- ✅ Retry works correctly in concurrent/sequential mode
- ✅ Retry count increments correctly
- ✅ Exponential backoff delays work as expected
- ✅ Retry state preserved across serialization

### 2. Data Flow

- ✅ Events carry complete data structures
- ✅ Data flows correctly between routines
- ✅ Data integrity maintained across retries
- ✅ Data visible in execution history

### 3. Serialization

- ✅ Flow structure serialized correctly
- ✅ JobState execution history preserved
- ✅ Retry count preserved in ErrorHandler
- ✅ Routine states preserved

### 4. Cross-Host Recovery

- ✅ State loaded correctly on different host
- ✅ Retry count restored (2/4 preserved)
- ✅ Execution context maintained
- ✅ Data structures intact

## Verification Points

The demo verifies:

1. **Retry Count Preservation**
   - Saved: retry_count = 2
   - Restored: retry_count = 2 ✅

2. **Execution History**
   - All events recorded
   - Data payloads preserved
   - Timestamps maintained

3. **Data Integrity**
   - Data structures preserved
   - Item counts maintained
   - Request IDs tracked

4. **Flow Behavior**
   - Flow stops after retries exhausted
   - Downstream routines don't execute
   - Status correctly set to "failed"

## Showcase Scenarios

Additional scenarios available in `showcase_scenarios.py`:

- **API-to-Database Flow**: API calls → Database writes → Notifications
- Multiple retry-enabled routines in one flow
- Different retry configurations per routine

## Technical Details

### Retry Configuration

```python
ErrorHandler(
    strategy=ErrorStrategy.RETRY,
    max_retries=4,
    retry_delay=0.3,
    retry_backoff=1.5,
    retryable_exceptions=(ValueError,),
)
```

**Retry Delays**:
- Attempt 1 → 2: 0.3s
- Attempt 2 → 3: 0.45s (0.3 × 1.5)
- Attempt 3 → 4: 0.675s (0.3 × 1.5²)
- Attempt 4 → 5: 1.0125s (0.3 × 1.5³)

### Serialization Format

Saved state includes:
```json
{
  "flow": { /* Flow structure */ },
  "job_state": { /* Execution state */ },
  "saved_at": 1767445144.940949,
  "saved_at_iso": "2026-01-03T20:59:06.940949",
  "retry_count": 2,
  "execution_history_count": 2,
  "monitor_summary": {
    "events": 2,
    "data_flows": 1,
    "state_changes": 1
  }
}
```

## Expected Behavior

### Host A (Initial Execution)

1. DataFetchRoutine executes → fetches 3 items
2. DataProcessRoutine attempts processing
3. Attempt 1 fails → Retry 1/4
4. Attempt 2 fails → Retry 2/4
5. **State saved** (retry_count = 2)
6. Attempt 3 fails → Retry 3/4
7. Attempt 4 fails → Retry 4/4
8. Attempt 5 fails → Max retries exceeded
9. Flow status = "failed"

### Host B (Resume Execution)

1. Load Flow and JobState from file
2. Verify retry_count = 2 (preserved ✅)
3. Resume execution
4. Continue retries (if pending tasks exist)
5. Verify final state

## Key Insights

1. **Retry State Preservation**: The `retry_count` in ErrorHandler is correctly serialized and restored, allowing retries to continue from the correct count.

2. **Data Flow Tracking**: All data structures are preserved, including nested dictionaries, lists, and metadata.

3. **Execution Context**: The complete execution context (history, states, data) is maintained across serialization.

4. **Error Handling**: The retry mechanism correctly handles slot handler errors in concurrent mode.

## Files

- `enhanced_retry_demo.py`: Main enhanced demonstration
- `data_processing_routines.py`: Real-world routine implementations
- `showcase_scenarios.py`: Additional showcase scenarios
- `retry_demo.py`: Original simple demonstration
- `failing_routine.py`: Simple failing routines (for basic demo)
- `README.md`: Original documentation
- `ENHANCED_README.md`: This document

## Improvements Over Basic Demo

1. **Real-World Scenarios**: Simulates actual system operations
2. **Detailed Monitoring**: Comprehensive tracking of events, data flow, and state
3. **Data Visualization**: Clear display of data structures and flow
4. **Enhanced Verification**: More comprehensive checks and validations
5. **Better Output**: Rich, informative output with emojis and formatting

## Conclusion

This enhanced demo demonstrates that routilux fully supports:

- ✅ Retry mechanism in concurrent mode
- ✅ Retry state preservation across serialization
- ✅ Cross-host execution recovery
- ✅ Data flow tracking and monitoring
- ✅ Complete execution context preservation

All features work as expected and meet user requirements.

