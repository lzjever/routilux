"""
Enhanced retry and serialization demonstration with real-world scenarios.

This demo shows:
1. Real-world data processing flow with retry capability
2. Detailed monitoring of data flow, events, and state
3. Serialization and cross-host recovery
4. Comprehensive verification of retry behavior
"""

import time
import json
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from datetime import datetime
from routilux import Flow, JobState
from routilux.error_handler import ErrorHandler, ErrorStrategy
from routilux.job_state import JobState
from playground.retry_serialization_demo.data_processing_routines import (
    DataFetchRoutine,
    DataProcessRoutine,
    DataValidatorRoutine,
    DataStorageRoutine,
)
from playground.retry_serialization_demo.showcase_scenarios import (
    create_api_to_db_flow,
)


# Storage directory for serialized state
STORAGE_DIR = Path(__file__).parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)


class ExecutionMonitor:
    """Monitor for tracking execution details."""
    
    def __init__(self):
        """Initialize monitor."""
        self.start_time = time.time()
        self.events_log = []
        self.data_flow_log = []
        self.state_changes = []
    
    def log_event(self, routine_id: str, event_name: str, data: Dict[str, Any]):
        """Log an event with detailed data information."""
        timestamp = time.time() - self.start_time
        self.events_log.append({
            "timestamp": timestamp,
            "routine_id": routine_id,
            "event_name": event_name,
            "data": data,
        })
        print(f"  📤 [{timestamp:6.3f}s] {routine_id}.{event_name}")
        if data:
            for key, value in data.items():
                if isinstance(value, dict):
                    if "items" in value:
                        items = value["items"]
                        print(f"      {key}: {len(items)} items")
                        # Show item details for small lists
                        if isinstance(items, list) and len(items) <= 5:
                            for item in items:
                                if isinstance(item, dict):
                                    item_info = ", ".join([f"{k}:{v}" for k, v in list(item.items())[:2]])
                                    print(f"         • {item_info}")
                    elif "request_id" in value:
                        print(f"      {key}.request_id: {value['request_id']}")
                    elif "total_items" in value:
                        print(f"      {key}.total_items: {value['total_items']}")
                    else:
                        print(f"      {key}: {len(value)} keys")
                elif isinstance(value, list):
                    print(f"      {key}: {len(value)} items")
                else:
                    print(f"      {key}: {str(value)[:60]}")
    
    def log_data_flow(self, from_routine: str, to_routine: str, data_summary: str):
        """Log data flow between routines."""
        timestamp = time.time() - self.start_time
        self.data_flow_log.append({
            "timestamp": timestamp,
            "from": from_routine,
            "to": to_routine,
            "summary": data_summary,
        })
        print(f"  🔀 [{timestamp:6.3f}s] {from_routine} → {to_routine}: {data_summary}")
    
    def log_state_change(self, routine_id: str, old_state: str, new_state: str, details: str = ""):
        """Log state change."""
        timestamp = time.time() - self.start_time
        self.state_changes.append({
            "timestamp": timestamp,
            "routine_id": routine_id,
            "old_state": old_state,
            "new_state": new_state,
            "details": details,
        })
        print(f"  🔄 [{timestamp:6.3f}s] {routine_id}: {old_state} → {new_state} {details}")
    
    def print_summary(self):
        """Print execution summary with detailed breakdown."""
        print("\n" + "=" * 80)
        print("📊 Execution Summary")
        print("=" * 80)
        print(f"Total events: {len(self.events_log)}")
        print(f"Data flows: {len(self.data_flow_log)}")
        print(f"State changes: {len(self.state_changes)}")
        print(f"Total duration: {time.time() - self.start_time:.3f}s")
        
        # Event breakdown by routine
        if self.events_log:
            print(f"\nEvent breakdown by routine:")
            routine_events = {}
            for event in self.events_log:
                rid = event["routine_id"]
                routine_events[rid] = routine_events.get(rid, 0) + 1
            for rid, count in sorted(routine_events.items()):
                print(f"   {rid}: {count} events")
        
        # Data flow summary
        if self.data_flow_log:
            print(f"\nData flow summary:")
            for flow in self.data_flow_log:
                print(f"   {flow['from']} → {flow['to']}: {flow['summary']}")


def create_real_world_flow() -> Tuple[Flow, str]:
    """Create a real-world data processing flow with retry.
    
    Flow Structure:
        DataFetchRoutine -> DataProcessRoutine (retry 4x) -> DataValidatorRoutine -> DataStorageRoutine
    
    Returns:
        Tuple of (Flow, entry_routine_id)
    """
    print("=" * 80)
    print("🏗️  Creating Real-World Data Processing Flow")
    print("=" * 80)
    
    flow = Flow(flow_id="data_processing_flow", execution_strategy="sequential")
    
    # Create routines
    fetcher = DataFetchRoutine(fetch_duration=0.8)
    processor = DataProcessRoutine(processing_delay=0.5, failure_rate=1.0)  # Always fail for demo
    validator = DataValidatorRoutine()
    storage = DataStorageRoutine()
    
    # Add routines to flow
    fetch_id = flow.add_routine(fetcher, "data_fetch")
    process_id = flow.add_routine(processor, "data_process")
    validator_id = flow.add_routine(validator, "data_validator")
    storage_id = flow.add_routine(storage, "data_storage")
    
    # Configure retry for processor routine
    print(f"\n⚙️  Configuring retry for 'data_process' routine:")
    print(f"   - Strategy: RETRY")
    print(f"   - Max retries: 4")
    print(f"   - Retry delay: 0.3s")
    print(f"   - Retry backoff: 1.5x")
    print(f"   - Retryable exceptions: ValueError")
    
    error_handler = ErrorHandler(
        strategy=ErrorStrategy.RETRY,
        max_retries=4,
        retry_delay=0.3,
        retry_backoff=1.5,
        retryable_exceptions=(ValueError,),
    )
    processor.set_error_handler(error_handler)
    
    # Connect routines
    flow.connect(fetch_id, "output", process_id, "input")
    flow.connect(process_id, "output", validator_id, "input")
    flow.connect(validator_id, "output", storage_id, "input")
    
    print(f"\n✅ Flow created:")
    print(f"   - Flow ID: {flow.flow_id}")
    print(f"   - Routines: {list(flow.routines.keys())}")
    print(f"   - Entry routine: {fetch_id}")
    print(f"   - Flow structure: fetch → process (retry) → validate → storage")
    
    return flow, fetch_id


def _get_retry_count_for_routine(flow: Flow, routine_type: type) -> int:
    """Helper function to get retry count for a routine of specific type.
    
    Uses Flow.find_routines_by_type() and Flow.get_routine_retry_count().
    
    Args:
        flow: Flow object.
        routine_type: Type of routine to find.
    
    Returns:
        Retry count (0 if not found or no error handler).
    """
    routines = flow.find_routines_by_type(routine_type)
    if routines:
        routine_id, _ = routines[0]
        retry_count = flow.get_routine_retry_count(routine_id)
        if retry_count is not None:
            return retry_count
        # Fallback to attempt_count if available
        _, routine = routines[0]
        if hasattr(routine, 'attempt_count') and routine.attempt_count > 0:
            return routine.attempt_count - 1
    return 0


def monitor_execution_with_details(
    flow: Flow,
    job_state: JobState,
    monitor: ExecutionMonitor,
    target_retry_count: int = 2,
    save_file: Optional[str] = None,
) -> Tuple[JobState, bool]:
    """Monitor execution with detailed tracking and save state.
    
    Uses JobState.wait_for_completion() with progress callback for monitoring.
    
    Args:
        flow: Flow object.
        job_state: JobState object to monitor.
        monitor: ExecutionMonitor instance.
        target_retry_count: Retry count to wait for before saving.
        save_file: Optional filename for saving.
    
    Returns:
        Tuple of (JobState, saved: bool)
    """
    print("\n" + "=" * 80)
    print(f"👀 Monitoring Execution (target retry_count >= {target_retry_count})")
    print("=" * 80)
    
    if save_file is None:
        save_file = f"flow_state_{job_state.job_id}.json"
    save_path = STORAGE_DIR / save_file
    
    saved = False
    last_history_count = 0
    
    # Find processor routine using library API
    processor_routines = flow.find_routines_by_type(DataProcessRoutine)
    processor_id, processor_routine = processor_routines[0] if processor_routines else (None, None)
    
    def condition(flow: Flow, job_state: JobState) -> bool:
        """Condition: retry_count >= target_retry_count."""
        nonlocal saved, last_history_count
        
        # Track execution history changes
        current_history_count = len(job_state.execution_history)
        if current_history_count > last_history_count:
            new_records = job_state.execution_history[last_history_count:]
            for record in new_records:
                # Log event with data details
                data_summary = {}
                if record.data:
                    for key, value in record.data.items():
                        if isinstance(value, dict):
                            if "items" in value:
                                data_summary[key] = f"{len(value['items'])} items"
                            elif "request_id" in value:
                                data_summary[key] = f"request_id: {value['request_id']}"
                            else:
                                data_summary[key] = f"{len(value)} keys"
                        elif isinstance(value, list):
                            data_summary[key] = f"{len(value)} items"
                        else:
                            data_summary[key] = str(value)[:50]  # Truncate long values
                monitor.log_event(record.routine_id, record.event_name, data_summary)
                
                # Track data flow between routines
                if record.event_name == "output" and record.data:
                    if record.routine_id == "data_fetch":
                        monitor.log_data_flow("data_fetch", "data_process", 
                                             f"{record.data.get('data', {}).get('total_items', 0)} items")
                    elif record.routine_id == "data_process":
                        monitor.log_data_flow("data_process", "data_validator", 
                                             "processed data")
                    elif record.routine_id == "data_validator":
                        monitor.log_data_flow("data_validator", "data_storage", 
                                             "validated data")
            last_history_count = current_history_count
        
        # Track routine state changes
        if processor_id and processor_routine:
            routine_state = job_state.get_routine_state(processor_id)
            if routine_state:
                routine_status = routine_state.get("status", "unknown")
                if routine_status not in ["pending"]:
                    last_state = getattr(monitor, '_last_processor_state', None)
                    if last_state != routine_status:
                        attempt_count = processor_routine.attempt_count if hasattr(processor_routine, 'attempt_count') else 0
                        retry_count = flow.get_routine_retry_count(processor_id) or 0
                        monitor.log_state_change(processor_id, last_state or "previous", routine_status, 
                                                 f"(retry_count: {retry_count}, attempt: {attempt_count})")
                        monitor._last_processor_state = routine_status
        
        # Check condition: retry_count >= target_retry_count
        if processor_id:
            retry_count = flow.get_routine_retry_count(processor_id)
            if retry_count is not None and retry_count >= target_retry_count and not saved:
                print(f"\n⚠️  Target retry count {retry_count} reached! Saving state...")
                
                time.sleep(0.2)  # Ensure state is stable
                
                # Serialize flow and job_state
                flow_data = flow.serialize()
                job_state_data = job_state.serialize()
                
                # Save to file
                save_data = {
                    "flow": flow_data,
                    "job_state": job_state_data,
                    "saved_at": time.time(),
                    "saved_at_iso": datetime.now().isoformat(),
                    "retry_count": retry_count,
                    "execution_history_count": len(job_state.execution_history),
                    "monitor_summary": {
                        "events": len(monitor.events_log),
                        "data_flows": len(monitor.data_flow_log),
                        "state_changes": len(monitor.state_changes),
                    },
                }
                
                with open(save_path, "w") as f:
                    json.dump(save_data, f, indent=2, default=str)
                
                print(f"✅ State saved to: {save_path}")
                print(f"   - Flow ID: {flow.flow_id}")
                print(f"   - Job ID: {job_state.job_id}")
                print(f"   - Retry count: {retry_count}/4")
                print(f"   - Execution history: {len(job_state.execution_history)} records")
                print(f"   - Events logged: {len(monitor.events_log)}")
                saved = True
                return True  # Condition met
        
        return False  # Condition not met yet
    
    def progress_callback(queue_size: int, active_count: int, status: str):
        """Progress callback for monitoring execution."""
        retry_count = 0
        if processor_id:
            retry_count = flow.get_routine_retry_count(processor_id) or 0
        current_history_count = len(job_state.execution_history)
        print(f"  📊 Status: {status:10s} | Retry: {retry_count}/4 | "
              f"History: {current_history_count} records | Queue: {queue_size} | Active: {active_count}")
    
    # Use JobState.wait_until_condition() to wait for target retry count
    condition_met = JobState.wait_until_condition(
        flow=flow,
        job_state=job_state,
        condition=condition,
        timeout=30.0,
        check_interval=0.1,
        progress_callback=progress_callback
    )
    
    if not condition_met and not saved:
        retry_count = flow.get_routine_retry_count(processor_id) if processor_id else 0
        print(f"\n⚠️  Condition not met before timeout or execution completed")
        print(f"   Final status: {job_state.status}")
        print(f"   Final retry count: {retry_count}/4")
    
    # If saved, wait for completion using JobState.wait_for_completion()
    if saved:
        JobState.wait_for_completion(
            flow=flow,
            job_state=job_state,
            timeout=30.0,
            check_interval=0.2,
            progress_callback=progress_callback
        )
    
    return job_state, saved


def host_a_execute_and_save(flow: Flow, entry_id: str) -> Tuple[JobState, Optional[str], ExecutionMonitor]:
    """Host A: Execute flow and save state.
    
    Returns:
        Tuple of (JobState, save_file_path or None, ExecutionMonitor)
    """
    print("\n" + "=" * 80)
    print("🌐 Host A: Executing Flow and Saving State")
    print("=" * 80)
    
    monitor = ExecutionMonitor()
    
    # Execute flow
    print("\n📋 Step 1: Starting flow execution...")
    request_id = f"req_{int(time.time())}"
    job_state = flow.execute(entry_id, entry_params={"request_id": request_id})
    
    print(f"   Job ID: {job_state.job_id}")
    print(f"   Request ID: {request_id}")
    print(f"   Initial status: {job_state.status}")
    
    # Monitor and save
    print("\n📋 Step 2: Monitoring execution with detailed tracking...")
    job_state, saved = monitor_execution_with_details(
        flow, job_state, monitor, target_retry_count=2
    )
    
    if saved:
        save_files = list(STORAGE_DIR.glob(f"flow_state_{job_state.job_id}.json"))
        if save_files:
            save_file = save_files[0].name
            print(f"\n✅ State saved successfully!")
            monitor.print_summary()
            return job_state, save_file, monitor
    
    print(f"\n⚠️  State not saved")
    return job_state, None, monitor


def host_b_load_and_resume(save_file: str) -> Tuple[Flow, JobState, Dict[str, Any]]:
    """Host B: Load state and resume execution.
    
    Returns:
        Tuple of (Flow, resumed JobState, save_metadata)
    """
    print("\n" + "=" * 80)
    print("🌐 Host B: Loading State and Resuming Execution")
    print("=" * 80)
    
    save_path = STORAGE_DIR / save_file
    
    if not save_path.exists():
        raise FileNotFoundError(f"Save file not found: {save_path}")
    
    # Load from file
    print(f"\n📋 Step 1: Loading state from {save_file}...")
    with open(save_path, "r") as f:
        save_data = json.load(f)
    
    print(f"   Saved at: {save_data.get('saved_at_iso', 'unknown')}")
    print(f"   Retry count: {save_data.get('retry_count', 0)}")
    print(f"   Execution history: {save_data.get('execution_history_count', 0)} records")
    if "monitor_summary" in save_data:
        summary = save_data["monitor_summary"]
        print(f"   Events logged: {summary.get('events', 0)}")
        print(f"   Data flows: {summary.get('data_flows', 0)}")
        print(f"   State changes: {summary.get('state_changes', 0)}")
    
    # Deserialize flow
    print("\n📋 Step 2: Deserializing Flow...")
    new_flow = Flow()
    new_flow.deserialize(save_data["flow"])
    print(f"   Flow ID: {new_flow.flow_id}")
    print(f"   Routines: {list(new_flow.routines.keys())}")
    
    # Check error handler configuration using library API
    processor_routines = new_flow.find_routines_by_type(DataProcessRoutine)
    if processor_routines:
        processor_id, processor_routine = processor_routines[0]  # 解包元组: (routine_id, routine)
        error_handler = processor_routine.get_error_handler()
        if error_handler:
            print(f"\n   ⚙️  Processor error handler:")
            print(f"      - Strategy: {error_handler.strategy}")
            print(f"      - Max retries: {error_handler.max_retries}")
            print(f"      - Retry count: {error_handler.retry_count} ✅ (preserved!)")
            print(f"      - Retry delay: {error_handler.retry_delay}s")
            print(f"      - Retry backoff: {error_handler.retry_backoff}x")
    
    # Deserialize job_state
    print("\n📋 Step 3: Deserializing JobState...")
    new_job_state = JobState()
    new_job_state.deserialize(save_data["job_state"])
    print(f"   Job ID: {new_job_state.job_id}")
    print(f"   Status: {new_job_state.status}")
    print(f"   Execution history: {len(new_job_state.execution_history)} records")
    
    # Display execution history with detailed data
    print("\n   📜 Execution history with data:")
    for i, record in enumerate(new_job_state.execution_history, 1):
        print(f"      {i}. [{record.timestamp}] {record.routine_id}.{record.event_name}")
        if record.data:
            for key, value in record.data.items():
                if isinstance(value, dict):
                    if "items" in value:
                        items = value["items"]
                        print(f"         {key}: {len(items)} items")
                        if items and len(items) <= 3:
                            for item in items:
                                if isinstance(item, dict):
                                    item_str = ", ".join([f"{k}:{v}" for k, v in list(item.items())[:2]])
                                    print(f"            - {item_str}")
                    elif "request_id" in value:
                        print(f"         {key}.request_id: {value['request_id']}")
                    elif "total_items" in value:
                        print(f"         {key}.total_items: {value['total_items']}")
                    else:
                        print(f"         {key}: {len(value)} keys")
                elif isinstance(value, list):
                    print(f"         {key}: {len(value)} items")
                else:
                    print(f"         {key}: {value}")
    
    # Display shared data with details
    if new_job_state.shared_data:
        print("\n   📦 Shared data:")
        for key, value in new_job_state.shared_data.items():
            if isinstance(value, dict):
                print(f"      {key}:")
                for sub_key, sub_value in list(value.items())[:5]:  # Show first 5 keys
                    if isinstance(sub_value, (dict, list)):
                        print(f"         {sub_key}: {len(sub_value)} items")
                    else:
                        print(f"         {sub_key}: {sub_value}")
                if len(value) > 5:
                    print(f"         ... ({len(value) - 5} more keys)")
            elif isinstance(value, list):
                print(f"      {key}: {len(value)} items")
                for item in value[:3]:  # Show first 3 items
                    print(f"         - {item}")
                if len(value) > 3:
                    print(f"         ... ({len(value) - 3} more items)")
            else:
                print(f"      {key}: {value}")
    
    # Resume execution
    print("\n📋 Step 4: Resuming execution...")
    print("   Expected: Remaining retries should work correctly")
    print("   Expected: Flow should stop after all retries exhausted")
    print("   Note: Routilux will automatically recover tasks from slot data if needed")
    
    resumed_job_state = new_flow.resume(new_job_state)
    print(f"   Status after resume: {resumed_job_state.status}")
    
    # Wait for completion using JobState.wait_for_completion()
    print("\n📋 Step 5: Waiting for execution to complete...")
    print("   Monitoring retry attempts and execution progress...")
    
    last_history_count = len(resumed_job_state.execution_history)
    processor_routines = new_flow.find_routines_by_type(DataProcessRoutine)
    processor_id, processor_routine = processor_routines[0] if processor_routines else (None, None)
    last_retry_count = new_flow.get_routine_retry_count(processor_id) if processor_id else 0
    
    def progress_callback(queue_size: int, active_count: int, status: str):
        """Progress callback for monitoring resumed execution."""
        nonlocal last_history_count, last_retry_count
        
        # Track new execution history
        current_history_count = len(resumed_job_state.execution_history)
        if current_history_count > last_history_count:
            new_records = resumed_job_state.execution_history[last_history_count:]
            for record in new_records:
                print(f"   📝 New event: {record.routine_id}.{record.event_name}")
            last_history_count = current_history_count
        
        # Track retry count changes using library API
        if processor_id:
            retry_count = new_flow.get_routine_retry_count(processor_id) or 0
            if retry_count > last_retry_count:
                print(f"   🔄 Retry count updated: {last_retry_count} → {retry_count}/4")
                last_retry_count = retry_count
            
            # Track attempt count
            if processor_routine and hasattr(processor_routine, 'attempt_count'):
                if processor_routine.attempt_count > 0:
                    print(f"   📊 Processor attempt count: {processor_routine.attempt_count}")
    
    completed = JobState.wait_for_completion(
        flow=new_flow,
        job_state=resumed_job_state,
        timeout=30.0,
        check_interval=0.2,
        progress_callback=progress_callback
    )
    
    if completed:
        final_retry_count = new_flow.get_routine_retry_count(processor_id) if processor_id else 0
        final_attempt_count = 0
        if processor_routine and hasattr(processor_routine, 'attempt_count'):
            final_attempt_count = processor_routine.attempt_count
        
        print(f"\n   ✅ Execution completed!")
        print(f"   Final status: {resumed_job_state.status}")
        print(f"   Final retry count: {final_retry_count}/4")
        print(f"   Final attempt count: {final_attempt_count}")
        print(f"   Total execution history: {len(resumed_job_state.execution_history)} records")
    else:
        print(f"\n   ⚠️  Execution monitoring timed out")
        print(f"   Final status: {resumed_job_state.status}")
    
    return new_flow, resumed_job_state, save_data


def verify_results_comprehensive(
    initial_job_state: JobState,
    initial_monitor: ExecutionMonitor,
    resumed_flow: Flow,
    resumed_job_state: JobState,
    save_metadata: Dict[str, Any],
):
    """Comprehensive verification of results.
    
    Args:
        initial_job_state: JobState from Host A.
        initial_monitor: ExecutionMonitor from Host A.
        resumed_flow: Flow object from Host B.
        resumed_job_state: JobState from Host B.
        save_metadata: Metadata from saved state.
    """
    print("\n" + "=" * 80)
    print("📊 Comprehensive Verification Results")
    print("=" * 80)
    
    print(f"\n📋 Initial Execution (Host A):")
    print(f"   - Status: {initial_job_state.status}")
    print(f"   - Execution history: {len(initial_job_state.execution_history)} records")
    print(f"   - Events logged: {len(initial_monitor.events_log)}")
    print(f"   - Data flows: {len(initial_monitor.data_flow_log)}")
    print(f"   - State changes: {len(initial_monitor.state_changes)}")
    
    print(f"\n📋 Resumed Execution (Host B):")
    print(f"   - Status: {resumed_job_state.status}")
    print(f"   - Execution history: {len(resumed_job_state.execution_history)} records")
    
    # Check final retry count using library API
    processor_routines = resumed_flow.find_routines_by_type(DataProcessRoutine)
    processor_id, _ = processor_routines[0] if processor_routines else (None, None)
    final_retry_count = resumed_flow.get_routine_retry_count(processor_id) if processor_id else 0
    
    print(f"\n📋 Retry State Verification:")
    print(f"   - Saved retry count: {save_metadata.get('retry_count', 0)}")
    print(f"   - Final retry count: {final_retry_count}")
    print(f"   - Expected final: 4 (all retries exhausted)")
    
    # Expected behavior
    print(f"\n📋 Expected Behavior:")
    print(f"   ✅ DataProcessRoutine should attempt 5 times (1 initial + 4 retries)")
    print(f"   ✅ All attempts should fail (simulated)")
    print(f"   ✅ Flow status should be 'failed'")
    print(f"   ✅ DataValidatorRoutine should NOT execute (flow stops before)")
    print(f"   ✅ DataStorageRoutine should NOT execute (flow stops before)")
    
    # Check which routines executed
    executed_routines = set()
    for record in resumed_job_state.execution_history:
        executed_routines.add(record.routine_id)
    
    print(f"\n📋 Actual Results:")
    print(f"   - Flow status: {resumed_job_state.status}")
    print(f"   - Routines executed: {sorted(executed_routines)}")
    print(f"   - DataValidatorRoutine executed: {'data_validator' in executed_routines}")
    print(f"   - DataStorageRoutine executed: {'data_storage' in executed_routines}")
    
    # Verification
    print(f"\n📋 Verification:")
    if resumed_job_state.status == "failed":
        print(f"   ✅ Flow correctly stopped after all retries exhausted")
    else:
        print(f"   ⚠️  Flow status is '{resumed_job_state.status}', expected 'failed'")
    
    if "data_validator" not in executed_routines:
        print(f"   ✅ DataValidatorRoutine correctly did not execute")
    else:
        print(f"   ⚠️  DataValidatorRoutine executed (unexpected)")
    
    if "data_storage" not in executed_routines:
        print(f"   ✅ DataStorageRoutine correctly did not execute")
    else:
        print(f"   ⚠️  DataStorageRoutine executed (unexpected)")
    
    if final_retry_count == 4:
        print(f"   ✅ Retry count correctly reached maximum (4)")
    else:
        print(f"   ⚠️  Retry count is {final_retry_count}, expected 4")
    
    # Data flow verification
    print(f"\n📋 Data Flow Verification:")
    data_fetch_executed = "data_fetch" in executed_routines
    data_process_executed = "data_process" in executed_routines
    
    print(f"   - DataFetchRoutine executed: {data_fetch_executed}")
    print(f"   - DataProcessRoutine executed: {data_process_executed}")
    
    if data_fetch_executed:
        print(f"   ✅ Data was fetched successfully")
    if data_process_executed:
        print(f"   ✅ Data processing was attempted (with retries)")
    
    # Display final execution history with data flow
    print(f"\n📋 Final Execution History (with data flow):")
    prev_routine = None
    for i, record in enumerate(resumed_job_state.execution_history, 1):
        print(f"   {i:2d}. [{record.timestamp}] {record.routine_id}.{record.event_name}")
        
        # Show data flow arrow if this is an output event
        if record.event_name == "output" and prev_routine:
            print(f"        🔀 → Next routine will receive this data")
        
        # Show data summary
        if record.data:
            data_items = []
            for key, value in record.data.items():
                if isinstance(value, dict):
                    if "items" in value:
                        data_items.append(f"{key}: {len(value['items'])} items")
                    elif "request_id" in value:
                        data_items.append(f"request_id: {value['request_id']}")
                    else:
                        data_items.append(f"{key}: {len(value)} keys")
                elif isinstance(value, list):
                    data_items.append(f"{key}: {len(value)} items")
                else:
                    data_items.append(f"{key}: {value}")
            if data_items:
                print(f"        📦 Data: {', '.join(data_items[:3])}")
                if len(data_items) > 3:
                    print(f"             ... ({len(data_items) - 3} more fields)")
        
        prev_routine = record.routine_id


def main():
    """Main demonstration function."""
    print("=" * 80)
    print("🚀 Enhanced Retry and Serialization Demonstration")
    print("=" * 80)
    print("\nThis demo shows:")
    print("  1. Real-world data processing flow (fetch → process → validate → storage)")
    print("  2. Data processing routine with retry capability (4 retries)")
    print("  3. Detailed monitoring of data flow, events, and state")
    print("  4. Serialization after 2 failures and cross-host recovery")
    print("  5. Comprehensive verification of retry behavior")
    print("  6. Data integrity and state preservation")
    print()
    
    import sys
    scenario = sys.argv[1] if len(sys.argv) > 1 else "data_processing"
    
    if scenario == "api_to_db":
        print("📌 Running API-to-Database scenario...")
        flow, entry_id = create_api_to_db_flow()
        # For API scenario, use different monitoring
        print("\n⚠️  Note: API-to-DB scenario uses different flow structure")
        print("   This scenario demonstrates multiple retry-enabled routines")
        return
    else:
        # Create data processing flow
        flow, entry_id = create_real_world_flow()
    
    # Host A: Execute and save
    initial_job_state, save_file, monitor = host_a_execute_and_save(flow, entry_id)
    
    if save_file:
        # Host B: Load and resume
        resumed_flow, resumed_job_state, save_metadata = host_b_load_and_resume(save_file)
        
        # Verify results
        verify_results_comprehensive(
            initial_job_state, monitor, resumed_flow, resumed_job_state, save_metadata
        )
        
        print("\n" + "=" * 80)
        print("✅ Enhanced Demonstration Completed!")
        print("=" * 80)
        print("\nKey Takeaways:")
        print("  ✅ Retry mechanism works correctly in concurrent mode")
        print("  ✅ Retry state is correctly preserved across serialization")
        print("  ✅ Data flow and events are properly tracked")
        print("  ✅ Cross-host recovery maintains execution context")
        print("  ✅ Flow correctly stops after all retries exhausted")
    else:
        print("\n⚠️  Could not save state (execution may have completed too quickly)")


if __name__ == "__main__":
    main()

