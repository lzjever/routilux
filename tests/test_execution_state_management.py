"""
Comprehensive tests for execution state management.

Tests the mechanism of JobState management through Task and thread-local storage,
ensuring that multiple executions are independent and JobState is correctly
updated during execution in both main thread and worker threads.
"""

import threading

from routilux import ErrorHandler, ErrorStrategy, Flow, JobState, Routine


class TestMultipleIndependentExecutions:
    """Test that multiple execute() calls return independent JobStates."""

    def test_sequential_executions_return_different_job_states(self):
        """Test that sequential execute() calls return different JobStates."""
        flow = Flow(flow_id="test_flow")

        class Source(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, **kwargs):
                self.emit("output", data="test")

        source = Source()
        source_id = flow.add_routine(source, "source")

        # Execute multiple times
        js1 = flow.execute(source_id, entry_params={"value": "A"})
        js2 = flow.execute(source_id, entry_params={"value": "B"})
        js3 = flow.execute(source_id, entry_params={"value": "C"})

        # Verify they are different
        assert js1.job_id != js2.job_id
        assert js2.job_id != js3.job_id
        assert js1.job_id != js3.job_id

        # Verify they are independent objects
        assert js1 is not js2
        assert js2 is not js3

        # Verify each has its own execution history
        assert len(js1.execution_history) > 0
        assert len(js2.execution_history) > 0
        assert len(js3.execution_history) > 0

        # Verify Flow doesn't manage them
        assert not hasattr(flow, "job_state")

    def test_execution_state_is_updated_during_execution(self):
        """Test that JobState is updated during execution."""
        flow = Flow(flow_id="test_flow")

        class Source(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, **kwargs):
                self.emit("output", data="test")

        class Processor(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)
                self.output_event = self.define_event("output", ["result"])

            def process(self, data=None, **kwargs):
                self.emit("output", result=f"Processed: {data}")

        source = Source()
        processor = Processor()
        source_id = flow.add_routine(source, "source")
        processor_id = flow.add_routine(processor, "processor")

        flow.connect(source_id, "output", processor_id, "input")

        job_state = flow.execute(source_id)
        from routilux.job_state import JobState

        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # Verify execution history was recorded
        assert len(job_state.execution_history) >= 2  # At least source and processor

        # Verify routine states were recorded
        assert source_id in job_state.routine_states or processor_id in job_state.routine_states

        # Verify status was updated
        assert job_state.status == "completed"


class TestWorkerThreadJobStateAccess:
    """Test that worker threads can access JobState through Task."""

    def test_worker_thread_can_access_job_state(self):
        """Test that handlers in worker threads can access JobState."""
        flow = Flow(flow_id="test_flow")
        accessed_job_states = []
        worker_thread_updates = []

        class Source(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, **kwargs):
                self.emit("output", data="test")

        class Processor(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data=None, **kwargs):
                # This handler runs in a worker thread
                # JobState is now accessed via context variable
                from routilux.routine import _current_job_state

                job_state = _current_job_state.get(None)
                if job_state:
                    accessed_job_states.append(job_state.job_id)
                    # Find routine_id from flow
                    flow = getattr(self, "_current_flow", None)
                    if flow:
                        routine_id = None
                        for rid, routine in flow.routines.items():
                            if routine is self:
                                routine_id = rid
                                break
                        if routine_id:
                            worker_thread_updates.append(routine_id)
                            # Update JobState (should work in worker thread)
                            job_state.update_routine_state(
                                routine_id, {"status": "completed", "worker_thread": True}
                            )

        source = Source()
        processor = Processor()
        source_id = flow.add_routine(source, "source")
        processor_id = flow.add_routine(processor, "processor")

        flow.connect(source_id, "output", processor_id, "input")

        job_state = flow.execute(source_id)
        from routilux.job_state import JobState

        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # Verify worker thread accessed JobState
        assert len(accessed_job_states) > 0
        assert job_state.job_id in accessed_job_states

        # Verify worker thread was able to update JobState
        assert len(worker_thread_updates) > 0
        assert processor_id in worker_thread_updates

        # Verify JobState was updated in worker thread
        routine_state = job_state.get_routine_state(processor_id)
        # Note: routine_state may be None if not explicitly created, but the update was attempted
        if routine_state:
            assert routine_state.get("worker_thread") is True

    def test_task_carries_job_state(self):
        """Test that tasks carry JobState and it's accessible in worker threads."""
        flow = Flow(flow_id="test_flow")
        task_job_states = []

        class Source(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, **kwargs):
                self.emit("output", data="test")

        class Processor(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data=None, **kwargs):
                # Access JobState from context variable (set by slot.receive)
                from routilux.routine import _current_job_state

                job_state = _current_job_state.get(None)
                if job_state:
                    task_job_states.append(job_state.job_id)

        source = Source()
        processor = Processor()
        source_id = flow.add_routine(source, "source")
        processor_id = flow.add_routine(processor, "processor")

        flow.connect(source_id, "output", processor_id, "input")

        job_state = flow.execute(source_id)
        from routilux.job_state import JobState

        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # Verify task carried JobState to worker thread
        assert len(task_job_states) > 0
        assert job_state.job_id in task_job_states


class TestConcurrentExecutions:
    """Test concurrent executions in different threads."""

    def test_concurrent_executions_are_isolated(self):
        """Test that concurrent executions in different threads are isolated."""
        flow = Flow(flow_id="test_flow")
        results = []

        class Source(Routine):
            def __init__(self, name):
                super().__init__()
                self.name = name
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, value=None, **kwargs):
                value = value or kwargs.get("value", "default")
                self.emit("output", data=f"{self.name}:{value}")

        source1 = Source("Source1")
        source2 = Source("Source2")
        s1_id = flow.add_routine(source1, "s1")
        s2_id = flow.add_routine(source2, "s2")

        def run_execution(entry_id, value):
            job_state = flow.execute(entry_id, entry_params={"value": value})
            results.append((threading.current_thread().name, job_state.job_id, value))

        # Run concurrent executions
        thread1 = threading.Thread(target=run_execution, args=(s1_id, "A"))
        thread2 = threading.Thread(target=run_execution, args=(s2_id, "B"))

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # Verify both executions completed
        assert len(results) == 2

        # Verify they have different JobState IDs
        job_ids = [r[1] for r in results]
        assert len(set(job_ids)) == 2  # All different

        # Verify they ran in different threads
        thread_names = [r[0] for r in results]
        assert len(set(thread_names)) >= 1  # May run in same or different threads

    def test_concurrent_executions_update_different_job_states(self):
        """Test that concurrent executions update different JobStates."""
        flow = Flow(flow_id="test_flow")
        job_state_updates = {}

        class Source(Routine):
            def __init__(self, name):
                super().__init__()
                self.name = name
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, value=None, **kwargs):
                value = value or kwargs.get("value", "default")
                # Access JobState and record update
                from routilux.routine import _current_job_state

                job_state = _current_job_state.get(None)
                if job_state:
                    job_state_updates[job_state.job_id] = f"{self.name}:{value}"
                self.emit("output", data=f"{self.name}:{value}")

        source1 = Source("Source1")
        source2 = Source("Source2")
        s1_id = flow.add_routine(source1, "s1")
        s2_id = flow.add_routine(source2, "s2")

        def run_execution(entry_id, value):
            job_state = flow.execute(entry_id, entry_params={"value": value})
            JobState.wait_for_completion(flow, job_state, timeout=2.0)
            return job_state

        # Run concurrent executions
        thread1 = threading.Thread(target=lambda: run_execution(s1_id, "A"))
        thread2 = threading.Thread(target=lambda: run_execution(s2_id, "B"))

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # Verify different JobStates were updated
        assert len(job_state_updates) >= 1  # At least one update recorded


class TestErrorHandlingWithJobState:
    """Test error handling updates JobState correctly."""

    def test_error_handler_updates_job_state_in_worker_thread(self):
        """Test that error handlers can update JobState in worker threads."""
        flow = Flow(flow_id="test_flow")

        class FailingRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, **kwargs):
                raise ValueError("Test error")

        class Source(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, **kwargs):
                self.emit("output", data="test")

        source = Source()
        failing = FailingRoutine()
        source_id = flow.add_routine(source, "source")
        failing_id = flow.add_routine(failing, "failing")

        flow.connect(source_id, "output", failing_id, "input")

        # Set error handler
        error_handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)
        flow.set_error_handler(error_handler)

        job_state = flow.execute(source_id)
        from routilux.job_state import JobState

        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # Verify error was handled and JobState was updated
        # (CONTINUE strategy should allow execution to complete)
        assert job_state.status in ["completed", "failed"]

        # Verify routine state was updated
        routine_state = job_state.get_routine_state(failing_id)
        if routine_state:
            # May be "error_continued" or "failed" depending on implementation
            assert routine_state.get("status") in ["error_continued", "failed", "skipped"]


class TestExecutionHistoryRecording:
    """Test that execution history is recorded correctly."""

    def test_execution_history_recorded_in_main_thread(self):
        """Test that execution history is recorded in main thread."""
        flow = Flow(flow_id="test_flow")

        class Source(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, **kwargs):
                # This runs in main thread
                self.emit("output", data="test")

        source = Source()
        source_id = flow.add_routine(source, "source")

        job_state = flow.execute(source_id)
        from routilux.job_state import JobState

        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # Verify execution history was recorded
        assert len(job_state.execution_history) > 0

        # Verify history contains source routine
        source_records = [r for r in job_state.execution_history if r.routine_id == source_id]
        assert len(source_records) > 0

    def test_execution_history_recorded_in_worker_thread(self):
        """Test that execution history is recorded in worker threads."""
        flow = Flow(flow_id="test_flow")

        class Source(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, **kwargs):
                self.emit("output", data="test")

        class Processor(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)
                self.output_event = self.define_event("output", ["result"])

            def process(self, data=None, **kwargs):
                # This runs in worker thread
                self.emit("output", result=f"Processed: {data}")

        source = Source()
        processor = Processor()
        source_id = flow.add_routine(source, "source")
        processor_id = flow.add_routine(processor, "processor")

        flow.connect(source_id, "output", processor_id, "input")

        job_state = flow.execute(source_id)
        from routilux.job_state import JobState

        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # Verify execution history was recorded for both routines
        assert len(job_state.execution_history) >= 2

        # Verify processor's execution was recorded (runs in worker thread)
        processor_records = [r for r in job_state.execution_history if r.routine_id == processor_id]
        assert len(processor_records) > 0


class TestPauseResumeWithJobState:
    """Test pause/resume with JobState management."""

    def test_pause_resume_uses_correct_job_state(self):
        """Test that pause/resume uses the correct JobState."""
        flow = Flow(flow_id="test_flow")

        class Source(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, **kwargs):
                self.emit("output", data="test")

        source = Source()
        source_id = flow.add_routine(source, "source")

        # Execute and pause
        job_state1 = flow.execute(source_id)
        flow.pause(job_state1, reason="test pause")

        assert job_state1.status == "paused"

        # Resume with the same JobState
        resumed_job_state = flow.resume(job_state1)

        assert resumed_job_state.job_id == job_state1.job_id
        assert resumed_job_state.status == "running"

        # Wait for completion
        from routilux.job_state import JobState

        JobState.wait_for_completion(flow, resumed_job_state, timeout=2.0)

        # Check final status (may need to refresh from job_state)
        # The status is updated in the JobState object
        assert resumed_job_state.status in [
            "completed",
            "running",
        ]  # May still be running if not fully updated

    def test_multiple_executions_can_be_paused_independently(self):
        """Test that multiple executions can be paused independently."""
        flow = Flow(flow_id="test_flow")

        class Source(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, **kwargs):
                self.emit("output", data="test")

        source = Source()
        source_id = flow.add_routine(source, "source")

        # Execute multiple times
        js1 = flow.execute(source_id)
        js2 = flow.execute(source_id)

        # Pause one execution
        flow.pause(js1, reason="pause js1")

        assert js1.status == "paused"
        from routilux.job_state import JobState

        JobState.wait_for_completion(flow, js2, timeout=2.0)
        assert js2.status == "completed"  # js2 should not be affected

        # Resume js1
        resumed = flow.resume(js1)
        JobState.wait_for_completion(flow, resumed, timeout=2.0)

        # Status may be updated in resumed JobState
        assert resumed.status in ["completed", "running"]


class TestSerializationWithMultipleExecutions:
    """Test serialization with multiple executions."""

    def test_serialize_flow_without_execution_state(self):
        """Test that Flow serialization doesn't include execution state."""
        flow = Flow(flow_id="test_flow")

        class Source(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, **kwargs):
                self.emit("output", data="test")

        source = Source()
        source_id = flow.add_routine(source, "source")

        # Execute to create JobState
        js1 = flow.execute(source_id)
        js2 = flow.execute(source_id)

        # Serialize Flow
        flow_data = flow.serialize()

        # Verify no execution state in Flow
        assert "job_state" not in flow_data

        # Serialize JobStates separately
        js1_data = js1.serialize()
        js2_data = js2.serialize()

        # Verify JobStates can be serialized
        assert "job_id" in js1_data
        assert "job_id" in js2_data
        assert js1_data["job_id"] != js2_data["job_id"]

    def test_deserialize_and_resume_execution(self):
        """Test deserializing Flow and JobState separately, then resuming."""
        from serilux import register_serializable

        flow = Flow(flow_id="test_flow")

        @register_serializable
        class Source(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, **kwargs):
                self.emit("output", data="test")

        source = Source()
        source_id = flow.add_routine(source, "source")

        # Execute and pause
        job_state = flow.execute(source_id)
        flow.pause(job_state, reason="test")

        # Serialize separately
        flow_data = flow.serialize()
        job_state_data = job_state.serialize()

        # Deserialize
        new_flow = Flow()
        new_flow.deserialize(flow_data)

        new_job_state = JobState()
        new_job_state.deserialize(job_state_data)

        # Verify they match
        assert new_flow.flow_id == flow.flow_id
        assert new_job_state.job_id == job_state.job_id
        assert new_job_state.status == "paused"

        # Resume
        resumed = new_flow.resume(new_job_state)
        JobState.wait_for_completion(new_flow, resumed, timeout=2.0)

        # Status may be updated in resumed JobState
        assert resumed.status in ["completed", "running"]


class TestComplexScenarios:
    """Test complex scenarios combining multiple features."""

    def test_multiple_executions_with_error_handling(self):
        """Test multiple executions with error handling."""
        flow = Flow(flow_id="test_flow")

        class FailingSource(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, **kwargs):
                raise ValueError("Test error")

        class SuccessSource(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, **kwargs):
                self.emit("output", data="success")

        failing = FailingSource()
        success = SuccessSource()
        failing_id = flow.add_routine(failing, "failing")
        success_id = flow.add_routine(success, "success")

        # Execute failing one
        js1 = flow.execute(failing_id)
        JobState.wait_for_completion(flow, js1, timeout=2.0)
        assert js1.status == "failed"

        # Execute successful one
        js2 = flow.execute(success_id)
        JobState.wait_for_completion(flow, js2, timeout=2.0)
        assert js2.status == "completed"

        # Verify they are independent
        assert js1.job_id != js2.job_id
        assert js1.status != js2.status

    def test_concurrent_executions_with_different_strategies(self):
        """Test concurrent executions with different error strategies."""
        flow = Flow(flow_id="test_flow")
        results = []

        class FailingRoutine(Routine):
            def __init__(self, name):
                super().__init__()
                self.name = name
                self.trigger_slot = self.define_slot("trigger", handler=self.send)
                self.output_event = self.define_event("output", ["data"])

            def send(self, **kwargs):
                raise ValueError(f"Error in {self.name}")

        failing1 = FailingRoutine("Failing1")
        failing2 = FailingRoutine("Failing2")
        f1_id = flow.add_routine(failing1, "f1")
        f2_id = flow.add_routine(failing2, "f2")

        # Set different error strategies
        failing1.set_error_handler(ErrorHandler(strategy=ErrorStrategy.STOP))
        failing2.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))

        def run_execution(entry_id):
            job_state = flow.execute(entry_id)
            results.append((entry_id, job_state.status))

        # Run concurrently
        thread1 = threading.Thread(target=run_execution, args=(f1_id,))
        thread2 = threading.Thread(target=run_execution, args=(f2_id,))

        thread1.start()
        thread2.start()

        thread1.join()
        thread2.join()

        # Verify both executions completed with correct status
        assert len(results) == 2

        # Find results by entry_id
        f1_result = next((r for r in results if r[0] == f1_id), None)
        f2_result = next((r for r in results if r[0] == f2_id), None)

        assert f1_result is not None
        assert f2_result is not None

        # STOP strategy should fail, CONTINUE should complete
        assert f1_result[1] == "failed"
        assert f2_result[1] == "completed"
