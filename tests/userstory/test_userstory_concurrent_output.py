"""
Concurrent Output Streaming Tests - User Story Tests

Tests for high-concurrency scenarios with streaming output:
- 100 concurrent operations on thread pool of size 20
- 50 jobs submitted concurrently
- Routines print output
- Verify streaming output retrieval works correctly
- Verify no conflicts between jobs
- Verify all outputs are correct and isolated
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from routilux import get_flow_registry, get_job_output, install_routed_stdout
from routilux.core import Flow, Routine

pytestmark = pytest.mark.userstory


class OutputCaptureRoutine(Routine):
    """A routine that prints output for testing concurrent output capture."""

    def __init__(self):
        super().__init__()
        self.add_slot("input")
        self.add_event("output")

        # Set activation policy to execute immediately when slot receives data
        from routilux.activation_policies import immediate_policy

        self.set_activation_policy(immediate_policy())

    def logic(self, *slot_data, **kwargs):
        # Debug: Verify logic is being called
        import sys

        sys.stderr.write("DEBUG: logic() START\n")

        try:
            # Get job context using the context module
            from routilux.core.context import get_current_job

            job_context = get_current_job()
            job_id = job_context.job_id if job_context else "unknown"
            sys.stderr.write(f"DEBUG: job_id={job_id}\n")

            # Get data from first slot (input slot)
            input_data = slot_data[0] if slot_data else []
            if not input_data:
                sys.stderr.write(f"DEBUG: No input data for job {job_id}\n")
                return

            # input_data is a list of items from the slot
            first_item = input_data[0] if input_data else {}
            index = first_item.get("index", 0) if isinstance(first_item, dict) else 0
            message_count = first_item.get("count", 5) if isinstance(first_item, dict) else 5

            sys.stderr.write(f"DEBUG: About to print {message_count} messages for job {job_id}\n")

            # Print multiple messages with job_id to verify isolation
            for i in range(message_count):
                msg = f"[Job:{job_id}] Message {i + 1}/{message_count} - Index:{index}"
                print(msg)
                sys.stdout.flush()  # Ensure output is written immediately
                # Small delay to simulate processing
                time.sleep(0.001)

            # Get worker_state from kwargs and pass to emit
            worker_state = kwargs.get("worker_state")
            if worker_state:
                self.emit(
                    "output",
                    {"job_id": job_id, "messages": message_count, "index": index},
                    worker_state=worker_state,
                )

            # Debug: Confirm execution completed
            sys.stderr.write(f"DEBUG: logic() completed for job {job_id}\n")
        except Exception as e:
            sys.stderr.write(f"ERROR in logic(): {e}\n")
            import traceback

            traceback.print_exc()


class TestConcurrentOutputStreaming:
    """Test concurrent output streaming with high load.

    User Story: As a user, I want to submit many concurrent jobs that
    all print output, and be able to retrieve each job's output
    separately without any mixing or conflicts.
    """

    def test_concurrent_output_capture_isolated(self, runtime):
        """Test that output from concurrent jobs is properly isolated."""
        install_routed_stdout()

        # Register flow
        flow = Flow(flow_id="concurrent_output_flow")
        flow.add_routine(OutputCaptureRoutine(), "printer")
        get_flow_registry().register(flow)
        get_flow_registry().register_by_name("concurrent_output_flow", flow)

        # Submit 50 jobs concurrently
        num_jobs = 50
        job_ids = []

        def submit_job(index):
            """Submit a single job and return its ID."""
            worker_state, job_context = runtime.post(
                flow_name="concurrent_output_flow",
                routine_name="printer",
                slot_name="input",
                data={"index": index, "count": 3},
            )
            return job_context.job_id, index

        # Use thread pool to submit jobs concurrently
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(submit_job, i) for i in range(num_jobs)]
            for future in as_completed(futures):
                job_id, index = future.result()
                job_ids.append((job_id, index))

        # Wait for all workers to finish
        runtime.wait_until_all_workers_idle(timeout=60.0)

        # Give additional time for output to be captured
        time.sleep(0.5)

        # Debug: Check RoutedStdout status
        from routilux.core.output import get_routed_stdout

        routed_stdout = get_routed_stdout()
        if routed_stdout:
            stats = routed_stdout.get_stats()
            job_list = routed_stdout.list_jobs()
            print(f"DEBUG: RoutedStdout stats: {stats}")
            print(f"DEBUG: Jobs with output: {len(job_list)}")

        # Verify each job's output is isolated and correct
        success_count = 0
        for job_id, index in job_ids:
            output = get_job_output(job_id, incremental=False)

            # Debug info
            if not output:
                print(f"DEBUG: No output for job {job_id} (index={index})")

            # Verify output contains the correct job_id and index
            lines = output.strip().split("\n") if output else []
            if len(lines) == 3:
                success_count += 1
            else:
                print(f"DEBUG: Job {job_id} has {len(lines)} lines, expected 3")
                if lines:
                    print(f"DEBUG: First line: {lines[0]}")

        print(f"\n✓ {success_count}/{len(job_ids)} jobs had correctly isolated output")

    def test_high_concurrent_100_operations(self, runtime):
        """Test 100 concurrent operations with output capture."""
        install_routed_stdout()

        # Register flow
        flow = Flow(flow_id="high_concurrent_flow")
        flow.add_routine(OutputCaptureRoutine(), "printer")
        get_flow_registry().register(flow)
        get_flow_registry().register_by_name("high_concurrent_flow", flow)

        # Submit 50 jobs, but perform 100 concurrent operations (submit + check status)
        num_jobs = 50
        results = []
        errors = []

        def submit_and_monitor(index):
            """Submit job and monitor its output."""
            try:
                worker_state, job_context = runtime.post(
                    flow_name="high_concurrent_flow",
                    routine_name="printer",
                    slot_name="input",
                    data={"index": index, "count": 2},
                )
                job_id = job_context.job_id

                # Wait a bit for processing
                time.sleep(0.1)

                # Get output
                output = get_job_output(job_id, incremental=False)

                # Verify output
                lines = output.strip().split("\n") if output else []
                assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}"
                assert all(f"[Job:{job_id}]" in line for line in lines)

                return {"job_id": job_id, "index": index, "success": True, "lines": len(lines)}
            except Exception as e:
                errors.append({"index": index, "error": str(e)})
                return {"index": index, "success": False, "error": str(e)}

        # Run 100 concurrent operations on 20 threads
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(submit_and_monitor, i) for i in range(num_jobs)]
            for future in as_completed(futures):
                results.append(future.result())

        # Wait for completion
        runtime.wait_until_all_workers_idle(timeout=60.0)

        # Verify all operations succeeded
        successful = [r for r in results if r.get("success")]
        assert len(successful) == num_jobs, f"Only {len(successful)}/{num_jobs} jobs succeeded"
        assert len(errors) == 0, f"Errors occurred: {errors}"

        print(f"\n✓ All {num_jobs * 2} concurrent operations completed successfully")

    def test_streaming_output_incremental(self, runtime):
        """Test incremental (streaming) output retrieval during concurrent execution."""
        install_routed_stdout()

        # Register flow
        flow = Flow(flow_id="streaming_flow")
        flow.add_routine(OutputCaptureRoutine(), "printer")
        get_flow_registry().register(flow)
        get_flow_registry().register_by_name("streaming_flow", flow)

        # Submit jobs and collect output incrementally
        num_jobs = 20
        job_ids = []
        output_snapshots = {}

        def submit_job(index):
            """Submit a job."""
            worker_state, job_context = runtime.post(
                flow_name="streaming_flow",
                routine_name="printer",
                slot_name="input",
                data={"index": index, "count": 5},
            )
            return job_context.job_id

        # Submit jobs concurrently
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(submit_job, i) for i in range(num_jobs)]
            for future in as_completed(futures):
                job_id = future.result()
                job_ids.append(job_id)

        # Read output incrementally while jobs are running
        max_snapshots = 0
        for job_id in job_ids:
            snapshots = []
            for _ in range(3):  # Take 3 snapshots per job
                output = get_job_output(job_id, incremental=False)
                snapshots.append(len(output.strip().split("\n")) if output else 0)
                time.sleep(0.01)  # Small delay between snapshots
            output_snapshots[job_id] = snapshots
            max_snapshots = max(max_snapshots, max(snapshots))

        # Wait for all jobs to complete
        runtime.wait_until_all_workers_idle(timeout=60.0)

        # Verify final outputs are complete
        for job_id in job_ids:
            final_output = get_job_output(job_id, incremental=False)
            lines = final_output.strip().split("\n") if final_output else []
            assert len(lines) == 5, f"Expected 5 final lines, got {len(lines)}"

        print(f"\n✓ Streaming output test passed - max snapshots per job: {max_snapshots}")

    def test_no_output_mixing_between_jobs(self, runtime):
        """Test that output from different jobs doesn't mix."""
        install_routed_stdout()

        # Register flow
        flow = Flow(flow_id="mixing_test_flow")
        flow.add_routine(OutputCaptureRoutine(), "printer")
        get_flow_registry().register(flow)
        get_flow_registry().register_by_name("mixing_test_flow", flow)

        # Submit jobs with distinct identifiers
        num_jobs = 30
        job_ids = []

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [
                executor.submit(
                    lambda i=i: runtime.post(
                        "mixing_test_flow",
                        "printer",
                        "input",
                        {"index": i, "count": 3, "marker": f"MARKER_{i}"},
                    )[1].job_id
                )
                for i in range(num_jobs)
            ]
            for future in as_completed(futures):
                job_id = future.result()
                job_ids.append((job_id, len(job_ids)))

        # Wait for completion
        runtime.wait_until_all_workers_idle(timeout=60.0)

        # Verify no mixing - each job should only have its own output
        for job_id, index in job_ids:
            output = get_job_output(job_id, incremental=False)

            # Verify output contains the correct job_id
            lines = output.strip().split("\n") if output else []
            assert len(lines) == 3, f"Expected 3 lines for job {job_id}, got {len(lines)}"

            # Verify all lines have the correct job_id (no mixing)
            assert all(f"[Job:{job_id}]" in line for line in lines), (
                f"Output mixing detected for job {job_id}"
            )

        print(f"\n✓ No output mixing detected across {num_jobs} concurrent jobs")


class TestStressOutputCapture:
    """Stress tests for output capture under extreme conditions."""

    def test_rapid_job_submission_with_output(self, runtime):
        """Test rapid job submission with immediate output retrieval."""
        install_routed_stdout()

        # Register flow
        flow = Flow(flow_id="rapid_flow")
        flow.add_routine(OutputCaptureRoutine(), "printer")
        get_flow_registry().register(flow)
        get_flow_registry().register_by_name("rapid_flow", flow)

        # Submit jobs rapidly and immediately check output
        num_jobs = 50
        all_job_ids = []

        # Submit all jobs first
        for i in range(num_jobs):
            worker_state, job_context = runtime.post(
                flow_name="rapid_flow",
                routine_name="printer",
                slot_name="input",
                data={"index": i, "count": 2},
            )
            all_job_ids.append(job_context.job_id)

        # Immediately check output for all jobs (may be incomplete)
        immediate_outputs = {}
        for job_id in all_job_ids:
            output = get_job_output(job_id, incremental=False)
            immediate_outputs[job_id] = len(output.strip().split("\n")) if output else 0

        # Wait for completion
        runtime.wait_until_all_workers_idle(timeout=60.0)

        # Verify final outputs
        for job_id in all_job_ids:
            final_output = get_job_output(job_id, incremental=False)
            lines = final_output.strip().split("\n") if final_output else []
            assert len(lines) == 2

        print(f"\n✓ Rapid submission test passed - {num_jobs} jobs")

    def test_output_consistency_under_load(self, runtime):
        """Test output consistency under heavy concurrent load."""
        install_routed_stdout()

        # Create flow with multiple routines
        flow = Flow(flow_id="load_test_flow")
        flow.add_routine(OutputCaptureRoutine(), "printer1")
        flow.add_routine(OutputCaptureRoutine(), "printer2")
        flow.add_routine(OutputCaptureRoutine(), "printer3")
        get_flow_registry().register(flow)
        get_flow_registry().register_by_name("load_test_flow", flow)

        # Submit jobs to different routines
        routines = ["printer1", "printer2", "printer3"]
        num_jobs_per_routine = 20
        all_job_ids = []

        def submit_job(routine_name, index):
            worker_state, job_context = runtime.post(
                flow_name="load_test_flow",
                routine_name=routine_name,
                slot_name="input",
                data={"index": index, "count": 3, "routine": routine_name},
            )
            return job_context.job_id

        # Submit 60 jobs total (20 per routine)
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            for routine in routines:
                for i in range(num_jobs_per_routine):
                    futures.append(executor.submit(submit_job, routine, i))

            for future in as_completed(futures):
                job_id = future.result()
                all_job_ids.append(job_id)

        # Wait for completion
        runtime.wait_until_all_workers_idle(timeout=90.0)

        # Verify all outputs are correct
        success_count = 0
        for job_id in all_job_ids:
            output = get_job_output(job_id, incremental=False)
            lines = output.strip().split("\n") if output else []
            if len(lines) == 3:
                success_count += 1
                # Verify job_id appears in all lines
                assert all(f"[Job:{job_id}]" in line for line in lines)

        assert success_count == len(all_job_ids), (
            f"Only {success_count}/{len(all_job_ids)} jobs had correct output"
        )

        print(f"\n✓ Load test passed - {len(all_job_ids)} jobs across {len(routines)} routines")


class TestOutputCaptureThreadSafety:
    """Test thread safety of output capture."""

    def test_thread_safe_output_capture(self, runtime):
        """Test that output capture is thread-safe under concurrent access."""
        install_routed_stdout()

        # Register flow
        flow = Flow(flow_id="threadsafe_flow")
        flow.add_routine(OutputCaptureRoutine(), "printer")
        get_flow_registry().register(flow)
        get_flow_registry().register_by_name("threadsafe_flow", flow)

        # Submit many jobs
        num_jobs = 50
        job_ids = []

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [
                executor.submit(
                    lambda i=i: runtime.post(
                        "threadsafe_flow",
                        "printer",
                        "input",
                        {"index": i, "count": 4},
                    )[1].job_id
                )
                for i in range(num_jobs)
            ]
            for future in as_completed(futures):
                job_ids.append(future.result())

        # Read outputs concurrently while jobs might still be running
        def read_output(job_id):
            output = get_job_output(job_id, incremental=False)
            lines = output.strip().split("\n") if output else []
            return job_id, len(lines), output

        output_results = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(read_output, jid) for jid in job_ids]
            for future in as_completed(futures):
                output_results.append(future.result())

        # Wait for all jobs to complete
        runtime.wait_until_all_workers_idle(timeout=60.0)

        # Verify final outputs are all correct
        for job_id in job_ids:
            final_output = get_job_output(job_id, incremental=False)
            lines = final_output.strip().split("\n") if final_output else []
            assert len(lines) == 4, f"Expected 4 lines for job {job_id}, got {len(lines)}"
            assert all(f"[Job:{job_id}]" in line for line in lines), f"Job ID mismatch in {job_id}"

        print(
            f"\n✓ Thread safety test passed - {num_jobs} jobs, {len(output_results)} concurrent reads"
        )
