"""Integration tests for Runtime - event routing and multi-routine flows."""

import time

import pytest
from routilux import immediate_policy
from routilux.core import Flow, FlowRegistry, JobStatus, Runtime, Routine, get_flow_registry


class TestEventRouting:
    """Test event routing between routines."""

    def test_simple_event_routing(self):
        """Test routing an event from one routine to another."""
        received_data = []
        
        class SourceRoutine(Routine):
            def setup(self):
                self.add_slot("input")
                self.add_event("output")
                self.set_activation_policy(immediate_policy())
            
            def logic(self, input_data_list, **kwargs):
                # input_data_list is a list of data points from the slot
                # For immediate policy, we get all new data
                # worker_state is passed as kwargs
                worker_state = kwargs.get("worker_state")
                if input_data_list:
                    # Use the first (or all) data points
                    for data in input_data_list:
                        # Get runtime from worker_state
                        runtime = getattr(worker_state, "_runtime", None)
                        if runtime:
                            self.emit("output", runtime=runtime, worker_state=worker_state, **data)
                return {}
        
        class TargetRoutine(Routine):
            def setup(self):
                self.add_slot("input")
                self.set_activation_policy(immediate_policy())
            
            def logic(self, input_data_list, **kwargs):
                # input_data_list is a list of data points from the slot
                for data in input_data_list:
                    received_data.append(data)
                return {}
        
        flow = Flow()
        flow.flow_id = "test_flow"
        source = SourceRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect(source_id, "output", target_id, "input")
        
        # Register flow
        registry = get_flow_registry()
        registry.register_by_name("test_flow", flow)
        
        runtime = Runtime()
        runtime.exec("test_flow")
        
        worker_state, job = runtime.post("test_flow", "source", "input", {"value": 42})
        
        # Wait for event routing - give more time for async execution
        # The event needs to be emitted, routed, and the target routine executed
        max_wait = 2.0
        start_time = time.time()
        while len(received_data) == 0 and (time.time() - start_time) < max_wait:
            time.sleep(0.1)
        
        # Check if data was received
        if len(received_data) == 0:
            # Debug: check worker state
            print(f"Worker status: {worker_state.status}")
            print(f"Worker executor: {getattr(worker_state, '_executor', None)}")
            # This might indicate a bug in event routing
            pytest.fail(f"Event routing failed - no data received after {max_wait}s. "
                       f"Worker status: {worker_state.status}")
        
        assert len(received_data) == 1
        assert received_data[0]["value"] == 42

    def test_multi_hop_event_routing(self):
        """Test routing events through multiple routines."""
        results = []
        
        class R1(Routine):
            def setup(self):
                self.add_slot("input")
                self.add_event("output")
                self.set_activation_policy(immediate_policy())
            
            def logic(self, input_data_list, **kwargs):
                worker_state = kwargs.get("worker_state")
                runtime = getattr(worker_state, "_runtime", None) if worker_state else None
                for data in input_data_list:
                    if runtime and worker_state:
                        # Use {**data, 'step': 1} so 'step' overwrites any existing 'step' in data
                        self.emit("output", runtime=runtime, worker_state=worker_state, **{**data, "step": 1})
                return {}
        
        class R2(Routine):
            def setup(self):
                self.add_slot("input")
                self.add_event("output")
                self.set_activation_policy(immediate_policy())
            
            def logic(self, input_data_list, **kwargs):
                worker_state = kwargs.get("worker_state")
                runtime = getattr(worker_state, "_runtime", None) if worker_state else None
                for data in input_data_list:
                    if runtime and worker_state:
                        # Use {**data, 'step': 2} so 'step' overwrites any existing 'step' in data
                        self.emit("output", runtime=runtime, worker_state=worker_state, **{**data, "step": 2})
                return {}
        
        class R3(Routine):
            def setup(self):
                self.add_slot("input")
                self.set_activation_policy(immediate_policy())
            
            def logic(self, input_data_list, **kwargs):
                for data in input_data_list:
                    results.append(data)
                return {}
        
        flow = Flow()
        flow.flow_id = "test_flow"
        r1 = R1()
        r1.setup()
        r2 = R2()
        r2.setup()
        r3 = R3()
        r3.setup()
        
        r1_id = flow.add_routine(r1, "r1")
        r2_id = flow.add_routine(r2, "r2")
        r3_id = flow.add_routine(r3, "r3")
        
        flow.connect(r1_id, "output", r2_id, "input")
        flow.connect(r2_id, "output", r3_id, "input")
        
        # Register flow
        registry = get_flow_registry()
        registry.register_by_name("test_flow", flow)
        
        runtime = Runtime()
        runtime.exec("test_flow")
        
        runtime.post("test_flow", "r1", "input", {"value": 10})
        
        # Wait for multi-hop routing - give more time
        max_wait = 2.0
        start_time = time.time()
        while len(results) == 0 and (time.time() - start_time) < max_wait:
            time.sleep(0.1)
        
        if len(results) == 0:
            pytest.fail(f"Multi-hop routing failed - no data received after {max_wait}s")
        
        assert len(results) == 1
        assert results[0]["step"] == 2
        assert results[0]["value"] == 10

    def test_fan_out_event_routing(self):
        """Test routing one event to multiple routines."""
        results = []
        
        class SourceRoutine(Routine):
            def setup(self):
                self.add_slot("input")
                self.add_event("output")
                self.set_activation_policy(immediate_policy())
            
            def logic(self, input_data_list, **kwargs):
                worker_state = kwargs.get("worker_state")
                runtime = getattr(worker_state, "_runtime", None) if worker_state else None
                for data in input_data_list:
                    if runtime and worker_state:
                        self.emit("output", runtime=runtime, worker_state=worker_state, **data)
                return {}
        
        class Target1(Routine):
            def setup(self):
                self.add_slot("input")
                self.set_activation_policy(immediate_policy())
            
            def logic(self, input_data_list, **kwargs):
                for data in input_data_list:
                    results.append(("target1", data))
                return {}
        
        class Target2(Routine):
            def setup(self):
                self.add_slot("input")
                self.set_activation_policy(immediate_policy())
            
            def logic(self, input_data_list, **kwargs):
                for data in input_data_list:
                    results.append(("target2", data))
                return {}
        
        flow = Flow()
        flow.flow_id = "test_flow"
        source = SourceRoutine()
        source.setup()
        target1 = Target1()
        target1.setup()
        target2 = Target2()
        target2.setup()
        
        source_id = flow.add_routine(source, "source")
        t1_id = flow.add_routine(target1, "target1")
        t2_id = flow.add_routine(target2, "target2")
        
        flow.connect(source_id, "output", t1_id, "input")
        flow.connect(source_id, "output", t2_id, "input")
        
        # Register flow
        registry = get_flow_registry()
        registry.register_by_name("test_flow", flow)
        
        runtime = Runtime()
        runtime.exec("test_flow")
        
        runtime.post("test_flow", "source", "input", {"value": 5})
        
        # Wait for fan-out routing
        max_wait = 2.0
        start_time = time.time()
        while len(results) < 2 and (time.time() - start_time) < max_wait:
            time.sleep(0.1)
        
        if len(results) < 2:
            pytest.fail(f"Fan-out routing failed - only {len(results)} targets received data after {max_wait}s")
        
        assert len(results) == 2
        target_names = {r[0] for r in results}
        assert target_names == {"target1", "target2"}
        assert all(r[1]["value"] == 5 for r in results)


class TestJobContextPropagation:
    """Test that JobContext propagates through routines."""

    def test_job_context_available_in_routines(self):
        """Test that JobContext is available in routine logic."""
        job_ids = []
        
        class TestRoutine(Routine):
            def setup(self):
                self.add_slot("input")
                self.add_event("output")
                self.set_activation_policy(immediate_policy())
            
            def logic(self, input_data_list, **kwargs):
                from routilux.core import get_current_job
                job = get_current_job()
                if job:
                    job_ids.append(job.job_id)
                worker_state = kwargs.get("worker_state")
                runtime = getattr(worker_state, "_runtime", None) if worker_state else None
                for data in input_data_list:
                    if runtime and worker_state:
                        self.emit("output", runtime=runtime, worker_state=worker_state, **data)
                return {}
        
        class TargetRoutine(Routine):
            def setup(self):
                self.add_slot("input")
                self.set_activation_policy(immediate_policy())
            
            def logic(self, input_data_list, **kwargs):
                from routilux.core import get_current_job
                job = get_current_job()
                if job:
                    job_ids.append(job.job_id)
                return {}
        
        flow = Flow()
        flow.flow_id = "test_flow"
        source = TestRoutine()
        source.setup()
        target = TargetRoutine()
        target.setup()
        
        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")
        flow.connect(source_id, "output", target_id, "input")
        
        # Register flow
        registry = get_flow_registry()
        registry.register_by_name("test_flow", flow)
        
        runtime = Runtime()
        runtime.exec("test_flow")
        
        worker_state, job = runtime.post("test_flow", "source", "input", {"test": "data"})
        
        # Wait for event routing and target routine execution
        max_wait = 2.0
        start_time = time.time()
        while len(job_ids) < 2 and (time.time() - start_time) < max_wait:
            time.sleep(0.1)
        
        if len(job_ids) < 2:
            pytest.fail(f"Job context propagation failed - only {len(job_ids)} routines saw job_id after {max_wait}s")
        
        # Both routines should see the same job_id
        assert len(job_ids) == 2
        assert job_ids[0] == job.job_id
        assert job_ids[1] == job.job_id
