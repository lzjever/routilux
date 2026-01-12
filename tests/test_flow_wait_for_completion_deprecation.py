"""
测试 Flow.wait_for_completion() 的 deprecation 和新行为
"""

import warnings

from routilux import Flow, JobState, Routine


class TestFlowWaitForCompletionDeprecation:
    """测试 Flow.wait_for_completion() 的 deprecation 和新行为"""

    def test_flow_wait_for_completion_with_job_state_uses_proper_method(self):
        """测试 Flow.wait_for_completion(job_state=...) 使用正确的方法"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, **kwargs):
                raise ValueError("Test error")

        routine = TestRoutine()
        flow.add_routine(routine, "test_routine")

        # 模拟错误记录，并且设置 routine 状态为 failed
        # 这模拟了真正的失败场景（如重试用尽）
        job_state.record_execution("test_routine", "error", {"error": "Test error"})
        job_state.update_routine_state("test_routine", {"status": "failed", "error": "Test error"})

        # 模拟所有任务完成
        from queue import Queue

        flow._task_queue = Queue()
        flow._execution_lock = type(
            "obj", (object,), {"__enter__": lambda self: self, "__exit__": lambda self, *args: None}
        )()
        flow._active_tasks = set()

        # 使用 Flow.wait_for_completion(job_state=...) 应该调用 JobState.wait_for_completion()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            completed = flow.wait_for_completion(timeout=1.0, job_state=job_state)

            # 应该发出 deprecation warning
            assert len(w) > 0
            assert any(issubclass(warning.category, DeprecationWarning) for warning in w)

        # 应该检测到错误并设置状态为 failed
        assert completed, "Should complete successfully"
        assert job_state.status == "failed", (
            "Status should be 'failed' when routine state is 'failed'"
        )

    def test_flow_wait_for_completion_without_job_state_legacy_behavior(self):
        """测试 Flow.wait_for_completion() 没有 job_state 时的旧行为"""
        flow = Flow()

        # 使用 Flow.wait_for_completion() 没有 job_state 时应该发出 warning
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            completed = flow.wait_for_completion(timeout=0.1)

            # 应该发出 deprecation warning
            assert len(w) > 0
            assert any(issubclass(warning.category, DeprecationWarning) for warning in w)

        # 应该返回 True（没有线程时）
        assert completed is True

    def test_recommended_usage_job_state_wait_for_completion(self):
        """测试推荐的用法：直接使用 JobState.wait_for_completion()"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"

        # 模拟错误记录，并且设置 routine 状态为 failed
        # 这模拟了真正的失败场景（如重试用尽）
        job_state.record_execution("test_routine", "error", {"error": "Test error"})
        job_state.update_routine_state("test_routine", {"status": "failed", "error": "Test error"})

        # 模拟所有任务完成
        from queue import Queue

        flow._task_queue = Queue()
        flow._execution_lock = type(
            "obj", (object,), {"__enter__": lambda self: self, "__exit__": lambda self, *args: None}
        )()
        flow._active_tasks = set()

        # 推荐的用法：直接使用 JobState.wait_for_completion()
        completed = JobState.wait_for_completion(flow=flow, job_state=job_state, timeout=1.0)

        # 应该检测到错误并设置状态为 failed
        assert completed, "Should complete successfully"
        assert job_state.status == "failed", (
            "Status should be 'failed' when routine state is 'failed'"
        )
