"""
Retry and serialization demonstration for routilux.

This demo shows:
1. A long-running flow with a routine that can retry 4 times
2. The routine intentionally fails with delay
3. After 2 failures, serialize flow and job_state to file
4. Simulate another host loading and resuming
5. Verify that remaining retries work correctly
6. Verify that flow stops after all retries are exhausted

Note: For enhanced demo with real-world scenarios, see enhanced_retry_demo.py
"""

import time
import json
import os
from pathlib import Path
from typing import Optional, Tuple
from routilux import Flow, JobState
from routilux.error_handler import ErrorHandler, ErrorStrategy
from routilux.job_state import JobState
from playground.retry_serialization_demo.failing_routine import (
    FailingRoutine,
    LongRunningRoutine,
    SuccessRoutine,
)


# Storage directory for serialized state
STORAGE_DIR = Path(__file__).parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)


def create_flow_with_retry() -> Tuple[Flow, str]:
    """Create a flow with a retry-enabled routine.
    
    Flow Structure:
        LongRunningRoutine -> FailingRoutine (retry 4 times) -> SuccessRoutine
    
    The FailingRoutine is configured with:
        - max_retries: 4
        - retry_delay: 0.3s
        - retry_backoff: 1.5
    
    Returns:
        Tuple of (Flow, entry_routine_id)
    """
    print("=" * 80)
    print("Creating Flow with Retry Configuration")
    print("=" * 80)
    
    flow = Flow(flow_id="retry_serialization_demo", execution_strategy="sequential")
    
    # Create routines
    long_running = LongRunningRoutine(duration=1.0)
    failing = FailingRoutine(delay=0.5)  # Delay before failure
    success = SuccessRoutine()
    
    # Add routines to flow
    long_id = flow.add_routine(long_running, "long_running")
    failing_id = flow.add_routine(failing, "failing")
    success_id = flow.add_routine(success, "success")
    
    # Configure retry for failing routine
    print(f"\nConfiguring retry for 'failing' routine:")
    print(f"  - max_retries: 4")
    print(f"  - retry_delay: 0.3s")
    print(f"  - retry_backoff: 1.5")
    
    error_handler = ErrorHandler(
        strategy=ErrorStrategy.RETRY,
        max_retries=4,
        retry_delay=0.3,
        retry_backoff=1.5,
        retryable_exceptions=(ValueError,),  # Only retry ValueError
    )
    failing.set_error_handler(error_handler)
    
    # Connect routines
    flow.connect(long_id, "output", failing_id, "input")
    flow.connect(failing_id, "output", success_id, "input")
    
    print(f"\nFlow created:")
    print(f"  - Flow ID: {flow.flow_id}")
    print(f"  - Routines: {list(flow.routines.keys())}")
    print(f"  - Entry routine: {long_id}")
    
    return flow, long_id


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


def monitor_execution_and_save(
    flow: Flow,
    job_state: JobState,
    target_retry_count: int = 2,
    save_file: Optional[str] = None,
) -> Tuple[JobState, bool]:
    """Monitor execution and save state after target retry count.
    
    Uses JobState.wait_for_completion() with progress callback for monitoring.
    
    Args:
        flow: Flow object.
        job_state: JobState object to monitor.
        target_retry_count: Retry count to wait for before saving. Default: 2
        save_file: Optional filename for saving. If None, auto-generates.
    
    Returns:
        Tuple of (JobState, saved: bool)
    """
    print("\n" + "=" * 80)
    print(f"Monitoring Execution (waiting for retry_count >= {target_retry_count})")
    print("=" * 80)
    
    if save_file is None:
        save_file = f"flow_state_{job_state.job_id}.json"
    save_path = STORAGE_DIR / save_file
    
    saved = False
    
    # Find failing routine using library API
    failing_routines = flow.find_routines_by_type(FailingRoutine)
    failing_id, _ = failing_routines[0] if failing_routines else (None, None)
    
    def condition(flow: Flow, job_state: JobState) -> bool:
        """Condition: retry_count >= target_retry_count."""
        nonlocal saved
        
        # Check condition: retry_count >= target_retry_count
        if failing_id:
            retry_count = flow.get_routine_retry_count(failing_id)
            if retry_count is not None and retry_count >= target_retry_count and not saved:
                print(f"\n⚠️  Retry count {retry_count} reached! Saving state...")
                
                # Small delay to ensure state is stable
                time.sleep(0.2)
                
                # Serialize flow and job_state
                flow_data = flow.serialize()
                job_state_data = job_state.serialize()
                
                # Save to file
                save_data = {
                    "flow": flow_data,
                    "job_state": job_state_data,
                    "saved_at": time.time(),
                    "retry_count": retry_count,
                }
                
                with open(save_path, "w") as f:
                    json.dump(save_data, f, indent=2)
                
                print(f"✅ State saved to: {save_path}")
                print(f"   - Flow ID: {flow.flow_id}")
                print(f"   - Job ID: {job_state.job_id}")
                print(f"   - Retry count: {retry_count}/4")
                saved = True
                return True  # Condition met
        
        return False  # Condition not met yet
    
    def progress_callback(queue_size: int, active_count: int, status: str):
        """Progress callback for monitoring execution."""
        retry_count = 0
        if failing_id:
            retry_count = flow.get_routine_retry_count(failing_id) or 0
        print(f"  Status: {status:10s} | Retry count: {retry_count}/4 | Queue: {queue_size} | Active: {active_count}")
    
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
        retry_count = flow.get_routine_retry_count(failing_id) if failing_id else 0
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


def host_a_execute_and_save(flow: Flow, entry_id: str) -> Tuple[JobState, Optional[str]]:
    """Host A: Execute flow and save state after 2 failures.
    
    Args:
        flow: Flow object.
        entry_id: Entry routine ID.
    
    Returns:
        Tuple of (JobState, save_file_path or None)
    """
    print("\n" + "=" * 80)
    print("🌐 Host A: Executing Flow and Saving State")
    print("=" * 80)
    
    # Execute flow
    print("\nStep 1: Starting flow execution...")
    job_state = flow.execute(entry_id, entry_params={"data": "test_data"})
    
    print(f"  Job ID: {job_state.job_id}")
    print(f"  Initial status: {job_state.status}")
    
    # Monitor and save after retry_count >= 2
    print("\nStep 2: Monitoring execution...")
    job_state, saved = monitor_execution_and_save(flow, job_state, target_retry_count=2)
    
    if saved:
        # Find the save file
        save_files = list(STORAGE_DIR.glob(f"flow_state_{job_state.job_id}.json"))
        if save_files:
            save_file = save_files[0].name
            print(f"\n✅ State saved successfully!")
            return job_state, save_file
    
    print(f"\n⚠️  State not saved (execution may have completed too quickly)")
    return job_state, None


def host_b_load_and_resume(save_file: str) -> Tuple[Flow, JobState]:
    """Host B: Load state from file and resume execution.
    
    Args:
        save_file: Filename of saved state.
    
    Returns:
        Tuple of (Flow, resumed JobState).
    """
    print("\n" + "=" * 80)
    print("🌐 Host B: Loading State and Resuming Execution")
    print("=" * 80)
    
    save_path = STORAGE_DIR / save_file
    
    if not save_path.exists():
        raise FileNotFoundError(f"Save file not found: {save_path}")
    
    # Load from file
    print(f"\nStep 1: Loading state from {save_file}...")
    with open(save_path, "r") as f:
        save_data = json.load(f)
    
    print(f"  Saved at: {save_data.get('saved_at', 'unknown')}")
    print(f"  Retry count: {save_data.get('retry_count', 0)}")
    
    # Deserialize flow
    print("\nStep 2: Deserializing Flow...")
    new_flow = Flow()
    new_flow.deserialize(save_data["flow"])
    print(f"  Flow ID: {new_flow.flow_id}")
    print(f"  Routines: {list(new_flow.routines.keys())}")
    
    # Check error handler configuration using library API
    failing_routines = new_flow.find_routines_by_type(FailingRoutine)
    if failing_routines:
        failing_id, failing_routine = failing_routines[0]  # 解包元组: (routine_id, routine)
        error_handler = failing_routine.get_error_handler()
        if error_handler:
            print(f"  Failing routine error handler:")
            print(f"    - Strategy: {error_handler.strategy}")
            print(f"    - Max retries: {error_handler.max_retries}")
            print(f"    - Retry count: {error_handler.retry_count}")
            print(f"    - Retry delay: {error_handler.retry_delay}")
    
    # Deserialize job_state
    print("\nStep 3: Deserializing JobState...")
    new_job_state = JobState()
    new_job_state.deserialize(save_data["job_state"])
    print(f"  Job ID: {new_job_state.job_id}")
    print(f"  Status: {new_job_state.status}")
    print(f"  Execution history: {len(new_job_state.execution_history)} records")
    
    # Display execution history
    print("\n  Execution history (last 5):")
    for record in new_job_state.execution_history[-5:]:
        print(f"    [{record.timestamp}] {record.routine_id}.{record.event_name}")
    
    # Resume execution
    print("\nStep 4: Resuming execution...")
    print("  Expected: Remaining retries should work correctly")
    print("  Expected: Flow should stop after all retries exhausted")
    
    resumed_job_state = new_flow.resume(new_job_state)
    print(f"  Status after resume: {resumed_job_state.status}")
    
    # Wait for completion using JobState.wait_for_completion()
    print("\nStep 5: Waiting for execution to complete...")
    
    # Find failing routine using library API
    failing_routines = new_flow.find_routines_by_type(FailingRoutine)
    failing_id, _ = failing_routines[0] if failing_routines else (None, None)
    
    def progress_callback(queue_size: int, active_count: int, status: str):
        """Progress callback for monitoring resumed execution."""
        retry_count = new_flow.get_routine_retry_count(failing_id) if failing_id else 0
        print(f"  Status: {status:10s} | Retry count: {retry_count}/4 | Queue: {queue_size} | Active: {active_count}")
    
    completed = JobState.wait_for_completion(
        flow=new_flow,
        job_state=resumed_job_state,
        timeout=30.0,
        check_interval=0.1,
        progress_callback=progress_callback
    )
    
    if completed:
        final_retry_count = new_flow.get_routine_retry_count(failing_id) if failing_id else 0
        print(f"  Final status: {resumed_job_state.status}")
        print(f"  Final retry count: {final_retry_count}/4")
    else:
        print(f"  ⚠️  Execution monitoring timed out")
        print(f"  Final status: {resumed_job_state.status}")
    
    return new_flow, resumed_job_state


def verify_results(initial_job_state: JobState, resumed_flow: Flow, resumed_job_state: JobState):
    """Verify that results match expectations.
    
    Args:
        initial_job_state: JobState from Host A.
        resumed_flow: Flow object from Host B.
        resumed_job_state: JobState from Host B.
    """
    print("\n" + "=" * 80)
    print("📊 Verification Results")
    print("=" * 80)
    
    print(f"\nInitial Execution (Host A):")
    print(f"  - Status: {initial_job_state.status}")
    print(f"  - Execution history: {len(initial_job_state.execution_history)} records")
    
    print(f"\nResumed Execution (Host B):")
    print(f"  - Status: {resumed_job_state.status}")
    print(f"  - Execution history: {len(resumed_job_state.execution_history)} records")
    
    # Check final retry count using library API
    failing_routines = resumed_flow.find_routines_by_type(FailingRoutine)
    failing_id, _ = failing_routines[0] if failing_routines else (None, None)
    final_retry_count = resumed_flow.get_routine_retry_count(failing_id) if failing_id else 0
    
    print(f"\nFinal retry count from error_handler: {final_retry_count}/4")
    
    # Expected: 4 retries + 1 initial attempt = 5 total attempts
    # All should fail, so flow should be "failed"
    print(f"\nExpected behavior:")
    print(f"  - FailingRoutine should attempt 5 times (1 initial + 4 retries)")
    print(f"  - All attempts should fail")
    print(f"  - Flow status should be 'failed'")
    print(f"  - SuccessRoutine should NOT execute (flow stops before)")
    
    # Check if SuccessRoutine executed
    success_executed = any(
        r.routine_id == "success" and r.event_name == "output"
        for r in resumed_job_state.execution_history
    )
    
    print(f"\nActual results:")
    print(f"  - Flow status: {resumed_job_state.status}")
    print(f"  - SuccessRoutine executed: {success_executed}")
    
    # Verification
    if resumed_job_state.status == "failed":
        print(f"\n✅ Flow correctly stopped after all retries exhausted")
    else:
        print(f"\n⚠️  Flow status is '{resumed_job_state.status}', expected 'failed'")
    
    if not success_executed:
        print(f"✅ SuccessRoutine correctly did not execute (flow stopped before)")
    else:
        print(f"⚠️  SuccessRoutine executed (unexpected)")
    
    # Display final execution history
    print(f"\nFinal execution history:")
    for i, record in enumerate(resumed_job_state.execution_history, 1):
        print(f"  {i:2d}. [{record.timestamp}] {record.routine_id}.{record.event_name}")


def main():
    """Main demonstration function."""
    print("=" * 80)
    print("Retry and Serialization Demonstration")
    print("=" * 80)
    print("\nThis demo shows:")
    print("  1. A long-running flow with a routine that can retry 4 times")
    print("  2. The routine intentionally fails with delay")
    print("  3. After 2 failures, serialize flow and job_state to file")
    print("  4. Simulate another host loading and resuming")
    print("  5. Verify that remaining retries work correctly")
    print("  6. Verify that flow stops after all retries are exhausted")
    print()
    
    # Create flow
    flow, entry_id = create_flow_with_retry()
    
    # Host A: Execute and save
    initial_job_state, save_file = host_a_execute_and_save(flow, entry_id)
    
    if save_file:
        # Host B: Load and resume
        resumed_flow, resumed_job_state = host_b_load_and_resume(save_file)
        
        # Verify results
        verify_results(initial_job_state, resumed_flow, resumed_job_state)
        
        print("\n" + "=" * 80)
        print("✅ Demonstration completed!")
        print("=" * 80)
    else:
        print("\n⚠️  Could not save state (execution may have completed too quickly)")
        print("   Try increasing the delay in FailingRoutine or reducing target_failures")


if __name__ == "__main__":
    main()

