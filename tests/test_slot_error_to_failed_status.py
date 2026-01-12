"""
测试 slot handler 错误导致状态设置为 failed 的实际场景
"""

from queue import Queue

from routilux import ErrorHandler, ErrorStrategy, Flow, Routine
from routilux.job_state import JobState


class TestSlotErrorToFailedStatus:
    """测试 slot handler 错误导致状态设置为 failed"""

    def test_slot_handler_error_recorded_and_detected_by_wait_for_completion(self):
        """测试 slot handler 错误被记录，wait_for_completion 检测到并设置状态为 failed"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"
        flow._running = True

        class FailingRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, **kwargs):
                raise RuntimeError("Processing failed")

        routine = FailingRoutine()
        flow_routine_id = "failing_routine"
        flow.add_routine(routine, flow_routine_id)
        routine.set_error_handler(
            ErrorHandler(
                strategy=ErrorStrategy.RETRY, max_retries=2, retryable_exceptions=(RuntimeError,)
            )
        )

        # 模拟 slot.receive 被调用（通过 execute_task）
        # 这会捕获异常并记录到执行历史
        slot = routine.get_slot("input")
        slot.receive({"test": "data"}, job_state=job_state, flow=flow)

        # 验证错误被记录到执行历史
        history = job_state.get_execution_history(flow_routine_id)
        assert len(history) > 0, "Error should be recorded in execution history"
        error_records = [r for r in history if r.event_name == "error"]
        assert len(error_records) > 0, "Should have error records"
        assert error_records[0].routine_id == flow_routine_id

        # 模拟重试用尽后，routine 状态被设置为 failed
        # 这是实际场景：当所有重试都用完后，handle_task_error 会设置 routine 状态为 failed
        job_state.update_routine_state(
            flow_routine_id, {"status": "failed", "error": "Max retries exceeded"}
        )

        # 模拟所有任务完成，调用 wait_for_completion
        flow._task_queue = Queue()  # 空队列
        flow._execution_lock = type(
            "obj", (object,), {"__enter__": lambda self: self, "__exit__": lambda self, *args: None}
        )()
        flow._active_tasks = set()

        # 调用 wait_for_completion
        completed = JobState.wait_for_completion(flow, job_state, timeout=1.0)

        # 验证状态被正确设置为 "failed"
        assert completed, "Should complete successfully"
        assert job_state.status == "failed", (
            f"Status should be 'failed', but got '{job_state.status}'"
        )

        # 验证执行历史中有错误记录
        all_history = job_state.get_execution_history()
        has_error = any(r.event_name in ["error", "failed"] for r in all_history)
        assert has_error, "Should have error in execution history"

    def test_multiple_slot_errors_all_detected(self):
        """测试多个 slot handler 错误都被检测到"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"
        flow._running = True

        class FailingRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, **kwargs):
                raise ValueError("Processing failed")

        routine = FailingRoutine()
        flow_routine_id = "failing_routine"
        flow.add_routine(routine, flow_routine_id)

        # 模拟多次调用，每次都失败
        slot = routine.get_slot("input")
        for i in range(3):
            try:
                slot.receive({"test": f"data_{i}"}, job_state=job_state, flow=flow)
            except Exception:
                pass  # slot.receive 内部捕获异常

        # 验证有多个错误记录
        history = job_state.get_execution_history(flow_routine_id)
        error_records = [r for r in history if r.event_name == "error"]
        assert len(error_records) >= 3, (
            f"Should have at least 3 error records, got {len(error_records)}"
        )

        # 模拟重试用尽后，routine 状态被设置为 failed
        # 这是实际场景：当所有重试都用完后，handle_task_error 会设置 routine 状态为 failed
        job_state.update_routine_state(
            flow_routine_id, {"status": "failed", "error": "Max retries exceeded"}
        )

        # 模拟所有任务完成
        flow._task_queue = Queue()
        flow._execution_lock = type(
            "obj", (object,), {"__enter__": lambda self: self, "__exit__": lambda self, *args: None}
        )()
        flow._active_tasks = set()

        # 调用 wait_for_completion
        completed = JobState.wait_for_completion(flow, job_state, timeout=1.0)

        # 验证状态被正确设置为 "failed"
        assert completed, "Should complete successfully"
        assert job_state.status == "failed", (
            f"Status should be 'failed', but got '{job_state.status}'"
        )
