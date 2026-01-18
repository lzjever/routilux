"""
Tests for thread safety in refactored code.

Tests verify that:
1. Flow connections can be modified concurrently
2. ObjectFactory operations are thread-safe
3. Runtime.post() is thread-safe
4. JobExecutor operations are thread-safe
"""

import threading
import time

import pytest

from routilux import Flow, Routine
from routilux.activation_policies import immediate_policy
from routilux.tools.factory.factory import ObjectFactory
from routilux.job_manager import get_job_manager
from routilux.monitoring.flow_registry import FlowRegistry
from routilux.runtime import Runtime


class TestFlowConnectionsThreadSafety:
    """Test thread safety of Flow connections."""

    def test_concurrent_connection_modifications(self):
        """Test: Concurrent modification of connections is thread-safe."""
        flow = Flow("test_flow")

        routine1 = Routine()
        routine1.define_event("output", ["data"])
        routine2 = Routine()
        routine2.define_slot("input")
        routine3 = Routine()
        routine3.define_slot("input")

        flow.add_routine(routine1, "source")
        flow.add_routine(routine2, "target1")
        flow.add_routine(routine3, "target2")

        errors = []
        connections_created = []

        def modify_connections(i):
            try:
                if i % 2 == 0:
                    # Add connection
                    flow.connect("source", "output", "target1", "input")
                else:
                    # Get connections (read)
                    event = routine1._events["output"]
                    connections = flow.get_connections_for_event(event)
                    connections_created.append(len(connections))
            except Exception as e:
                errors.append((i, e))

        # Concurrent modifications
        threads = [threading.Thread(target=modify_connections, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Interface contract: Should handle concurrent access without errors
        # (except expected errors like duplicate connections)
        unexpected_errors = [e for e in errors if "already" not in str(e[1]).lower()]
        assert len(unexpected_errors) == 0

    def test_get_connections_for_event_thread_safe(self):
        """Test: get_connections_for_event() is thread-safe."""
        flow = Flow("test_flow")

        routine1 = Routine()
        routine1.define_event("output", ["data"])
        routine2 = Routine()
        routine2.define_slot("input")

        flow.add_routine(routine1, "source")
        flow.add_routine(routine2, "target")
        flow.connect("source", "output", "target", "input")

        event = routine1._events["output"]
        results = []

        def read_connections(i):
            try:
                connections = flow.get_connections_for_event(event)
                results.append(len(connections))
            except Exception as e:
                results.append(f"error_{i}")

        # Concurrent reads
        threads = [threading.Thread(target=read_connections, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Interface contract: All reads should succeed and return consistent results
        assert all(isinstance(r, int) for r in results)
        assert all(r == 1 for r in results)  # Should have 1 connection


class TestObjectFactoryThreadSafety:
    """Test thread safety of ObjectFactory."""

    def test_concurrent_registration(self):
        """Test: Concurrent registration is thread-safe."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        errors = []
        registered = []

        def register_routine(i):
            try:
                factory.register(f"routine_{i}", Routine, description=f"Routine {i}")
                registered.append(i)
            except Exception as e:
                errors.append((i, e))

        threads = [threading.Thread(target=register_routine, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Interface contract: Should handle concurrent registration
        # (duplicates should raise ValueError, which is expected)
        assert len(registered) == 20 or len([e for e in errors if "already" in str(e[1])]) > 0

    def test_concurrent_creation(self):
        """Test: Concurrent creation is thread-safe."""
        factory = ObjectFactory.get_instance()
        factory._registry.clear()

        factory.register("test", Routine)

        created = []
        errors = []

        def create_routine():
            try:
                obj = factory.create("test")
                created.append(obj)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_routine) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Interface contract: Should create all objects without errors
        assert len(errors) == 0
        assert len(created) == 20
        # All should be different instances
        assert len(set(id(obj) for obj in created)) == 20


class TestRuntimePostThreadSafety:
    """Test thread safety of Runtime.post()."""

    def test_concurrent_post_calls(self):
        """Test: Concurrent post() calls are thread-safe."""
        flow = Flow("test_flow")
        received_count = {"count": 0}

        routine = Routine()
        routine.define_slot("input")

        def logic(input_data, policy_message, job_state):
            received_count["count"] += 1

        routine.set_logic(logic)
        routine.set_activation_policy(immediate_policy())
        flow.add_routine(routine, "routine")

        FlowRegistry.get_instance().register_by_name("test_flow", flow)
        runtime = Runtime()

        job_state = runtime.exec("test_flow")

        errors = []

        def post_data(i):
            try:
                runtime.post("test_flow", "routine", "input", {"index": i}, job_id=job_state.job_id)
            except Exception as e:
                errors.append((i, e))

        # Concurrent posts
        threads = [threading.Thread(target=post_data, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        time.sleep(0.5)

        # Interface contract: Should handle concurrent posts without errors
        assert len(errors) == 0
        assert received_count["count"] >= 20

        runtime.shutdown(wait=True)


class TestJobExecutorThreadSafety:
    """Test thread safety of JobExecutor."""

    def test_concurrent_task_enqueue(self):
        """Test: Concurrent task enqueue is thread-safe."""
        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("input")
        routine.set_logic(lambda *args: None)
        routine.set_activation_policy(immediate_policy())
        flow.add_routine(routine, "routine")

        job_manager = get_job_manager()
        job_state = job_manager.start_job(flow=flow, timeout=None)

        executor = job_state._job_executor
        assert executor is not None

        from routilux.flow.task import SlotActivationTask

        slot = routine.get_slot("input")
        errors = []
        enqueued = []

        def enqueue_task(i):
            try:
                task = SlotActivationTask(slot=slot, data={"index": i}, job_state=job_state)
                executor.enqueue_task(task)
                enqueued.append(i)
            except Exception as e:
                errors.append((i, e))

        # Concurrent enqueue
        threads = [threading.Thread(target=enqueue_task, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        time.sleep(0.5)

        # Interface contract: Should handle concurrent enqueue without errors
        assert len(errors) == 0
        assert len(enqueued) == 20

        executor.stop()

    def test_concurrent_idle_detection(self):
        """Test: Concurrent IDLE detection is thread-safe."""
        flow = Flow("test_flow")
        routine = Routine()
        routine.define_slot("input")
        routine.set_logic(lambda *args: None)
        routine.set_activation_policy(immediate_policy())
        flow.add_routine(routine, "routine")

        job_manager = get_job_manager()
        job_state = job_manager.start_job(flow=flow, timeout=None)

        executor = job_state._job_executor

        # Concurrent IDLE checks
        idle_results = []

        def check_idle():
            try:
                result = executor._all_routines_idle()
                idle_results.append(result)
            except Exception as e:
                idle_results.append(f"error: {e}")

        threads = [threading.Thread(target=check_idle) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Interface contract: Should handle concurrent checks without errors
        assert all(isinstance(r, bool) for r in idle_results)

        executor.stop()
