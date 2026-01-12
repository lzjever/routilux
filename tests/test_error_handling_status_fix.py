"""
严格测试用例：验证错误处理状态修复

测试修复的两个 bug：
1. handle_task_error 中 routine_id 获取正确性
2. wait_for_completion 在检测到错误时不会将状态误设为 "completed"
"""

import threading

from routilux import ErrorHandler, ErrorStrategy, Flow, Routine
from routilux.flow.error_handling import handle_task_error
from routilux.flow.task import SlotActivationTask
from routilux.job_state import JobState


class TestHandleTaskErrorRoutineIdFix:
    """测试 handle_task_error 中 routine_id 获取正确性的修复"""

    def test_routine_id_is_correctly_resolved_from_flow(self):
        """测试 routine_id 从 flow 中正确解析，而不是使用 routine._id"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"
        flow._running = True

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, **kwargs):
                raise ValueError("Test error")

        routine = TestRoutine()
        # 使用自定义 routine_id，与 routine._id 不同
        flow_routine_id = "custom_routine_id_123"
        flow.add_routine(routine, flow_routine_id)
        routine.set_error_handler(ErrorHandler(strategy=ErrorStrategy.STOP))

        slot = routine.get_slot("input")
        task = SlotActivationTask(slot=slot, data={"test": "data"}, job_state=job_state)

        handle_task_error(task, ValueError("Test error"), flow)

        # 验证状态更新使用了正确的 routine_id
        assert job_state.status == "failed"
        routine_state = job_state.get_routine_state(flow_routine_id)
        assert routine_state is not None, f"Routine state should exist for {flow_routine_id}"
        assert routine_state.get("status") == "failed"
        assert "error" in routine_state

    def test_routine_id_correctly_updated_on_retry_exhaustion(self):
        """测试重试用尽时，routine_id 正确用于状态更新"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"
        flow._running = True

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, **kwargs):
                raise RuntimeError("Retryable error")

        routine = TestRoutine()
        flow_routine_id = "retry_routine_456"
        flow.add_routine(routine, flow_routine_id)
        routine.set_error_handler(
            ErrorHandler(
                strategy=ErrorStrategy.RETRY, max_retries=2, retryable_exceptions=(RuntimeError,)
            )
        )

        slot = routine.get_slot("input")
        # 模拟已经达到最大重试次数
        task = SlotActivationTask(
            slot=slot,
            data={"test": "data"},
            retry_count=2,  # 已达到 max_retries
            max_retries=2,
            job_state=job_state,
        )

        # 第一次调用应该尝试重试，但由于 retry_count >= max_retries，会 fall through
        handle_task_error(task, RuntimeError("Retryable error"), flow)

        # 验证状态更新使用了正确的 routine_id
        assert job_state.status == "failed"
        routine_state = job_state.get_routine_state(flow_routine_id)
        assert routine_state is not None, f"Routine state should exist for {flow_routine_id}"
        assert routine_state.get("status") == "failed"
        assert "error" in routine_state

    def test_routine_id_correctly_used_in_continue_strategy(self):
        """测试 CONTINUE 策略中 routine_id 正确用于记录错误"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"
        flow._running = True

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, **kwargs):
                raise ValueError("Continue error")

        routine = TestRoutine()
        flow_routine_id = "continue_routine_789"
        flow.add_routine(routine, flow_routine_id)
        routine.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))

        slot = routine.get_slot("input")
        task = SlotActivationTask(slot=slot, data={"test": "data"}, job_state=job_state)

        handle_task_error(task, ValueError("Continue error"), flow)

        # 验证错误记录使用了正确的 routine_id
        history = job_state.get_execution_history(flow_routine_id)
        assert len(history) > 0, "Error should be recorded in execution history"
        error_records = [r for r in history if r.event_name == "error"]
        assert len(error_records) > 0, "Should have error records"
        assert error_records[0].routine_id == flow_routine_id
        assert flow._running, "Flow should continue running"

    def test_routine_id_correctly_used_in_skip_strategy(self):
        """测试 SKIP 策略中 routine_id 正确用于状态更新"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"
        flow._running = True

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, **kwargs):
                raise ValueError("Skip error")

        routine = TestRoutine()
        flow_routine_id = "skip_routine_101"
        flow.add_routine(routine, flow_routine_id)
        routine.set_error_handler(ErrorHandler(strategy=ErrorStrategy.SKIP))

        slot = routine.get_slot("input")
        task = SlotActivationTask(slot=slot, data={"test": "data"}, job_state=job_state)

        handle_task_error(task, ValueError("Skip error"), flow)

        # 验证状态更新使用了正确的 routine_id
        routine_state = job_state.get_routine_state(flow_routine_id)
        assert routine_state is not None, f"Routine state should exist for {flow_routine_id}"
        assert routine_state.get("status") == "skipped"

    def test_routine_id_fallback_when_not_in_flow(self):
        """测试当 routine 不在 flow 中时，使用 routine._id 作为后备"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"
        flow._running = True

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, **kwargs):
                raise ValueError("Error")

        routine = TestRoutine()
        # 不将 routine 添加到 flow 中
        # 但设置 routine._id 用于后备
        routine._id = "fallback_routine_id"

        slot = routine.get_slot("input")
        task = SlotActivationTask(slot=slot, data={"test": "data"}, job_state=job_state)

        handle_task_error(task, ValueError("Error"), flow)

        # 验证状态更新使用了后备 routine_id
        assert job_state.status == "failed"
        routine_state = job_state.get_routine_state("fallback_routine_id")
        assert routine_state is not None, "Should use fallback routine_id"
        assert routine_state.get("status") == "failed"


class TestWaitForCompletionErrorDetectionFix:
    """测试 wait_for_completion 在检测到错误时不会将状态误设为 "completed" 的修复"""

    def test_wait_for_completion_detects_error_in_execution_history(self):
        """测试 wait_for_completion 检测执行历史中的错误（当 routine 状态为 failed 时）"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"

        # 模拟执行历史中有错误记录，并且 routine 状态为 failed
        # 这模拟了真正的失败场景（如重试用尽）
        job_state.record_execution("routine1", "error", {"error": "Test error"})
        job_state.update_routine_state("routine1", {"status": "failed", "error": "Test error"})
        job_state.record_execution("routine2", "output", {"data": "success"})

        # 模拟所有任务已完成（队列为空，无活动任务）
        # 但状态仍然是 "running"
        from queue import Queue

        mock_queue = Queue()
        # 确保队列为空
        while not mock_queue.empty():
            try:
                mock_queue.get_nowait()
            except Exception:
                break
        flow._task_queue = mock_queue
        flow._execution_lock = threading.Lock()
        flow._active_tasks = set()

        # 调用 wait_for_completion
        completed = JobState.wait_for_completion(flow, job_state, timeout=1.0)

        # 验证状态被正确设置为 "failed" 而不是 "completed"
        assert completed, "Should complete successfully"
        assert job_state.status == "failed", (
            "Status should be 'failed' when routine state is 'failed'"
        )

    def test_wait_for_completion_detects_error_in_routine_states(self):
        """测试 wait_for_completion 检测 routine_states 中的失败状态"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"

        # 模拟 routine_states 中有失败状态
        job_state.update_routine_state("routine1", {"status": "failed", "error": "Test error"})
        job_state.update_routine_state("routine2", {"status": "completed"})

        # 模拟所有任务已完成
        from queue import Queue

        mock_queue = Queue()
        # 确保队列为空
        while not mock_queue.empty():
            try:
                mock_queue.get_nowait()
            except Exception:
                break
        flow._task_queue = mock_queue
        flow._execution_lock = threading.Lock()
        flow._active_tasks = set()

        # 调用 wait_for_completion
        completed = JobState.wait_for_completion(flow, job_state, timeout=1.0)

        # 验证状态被正确设置为 "failed"
        assert completed, "Should complete successfully"
        assert job_state.status == "failed", (
            "Status should be 'failed' when routine states have failures"
        )

    def test_wait_for_completion_sets_completed_when_no_errors(self):
        """测试 wait_for_completion 在没有错误时正确设置为 "completed" """
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"

        # 模拟执行历史中只有成功记录
        job_state.record_execution("routine1", "output", {"data": "success"})
        job_state.record_execution("routine2", "completed", {"result": "ok"})
        job_state.update_routine_state("routine1", {"status": "completed"})
        job_state.update_routine_state("routine2", {"status": "completed"})

        # 模拟所有任务已完成
        from queue import Queue

        mock_queue = Queue()
        # 确保队列为空
        while not mock_queue.empty():
            try:
                mock_queue.get_nowait()
            except Exception:
                break
        flow._task_queue = mock_queue
        flow._execution_lock = threading.Lock()
        flow._active_tasks = set()

        # 调用 wait_for_completion
        completed = JobState.wait_for_completion(flow, job_state, timeout=1.0)

        # 验证状态被正确设置为 "completed"
        assert completed, "Should complete successfully"
        assert job_state.status == "completed", "Status should be 'completed' when no errors"

    def test_wait_for_completion_detects_failed_event_in_history(self):
        """测试 wait_for_completion 检测执行历史中的 "failed" 事件（当 routine 状态为 failed 时）"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"

        # 模拟执行历史中有 "failed" 事件，并且 routine 状态为 failed
        job_state.record_execution("routine1", "failed", {"error": "Critical failure"})
        job_state.update_routine_state(
            "routine1", {"status": "failed", "error": "Critical failure"}
        )

        # 模拟所有任务已完成
        from queue import Queue

        mock_queue = Queue()
        # 确保队列为空
        while not mock_queue.empty():
            try:
                mock_queue.get_nowait()
            except Exception:
                break
        flow._task_queue = mock_queue
        flow._execution_lock = threading.Lock()
        flow._active_tasks = set()

        # 调用 wait_for_completion
        completed = JobState.wait_for_completion(flow, job_state, timeout=1.0)

        # 验证状态被正确设置为 "failed"
        assert completed, "Should complete successfully"
        assert job_state.status == "failed", (
            "Status should be 'failed' when routine state is 'failed'"
        )

    def test_wait_for_completion_detects_error_status_in_routine_states(self):
        """测试 wait_for_completion 检测 routine_states 中的 "error" 状态"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"

        # 模拟 routine_states 中有 "error" 状态
        job_state.update_routine_state("routine1", {"status": "error", "error": "Some error"})

        # 模拟所有任务已完成
        from queue import Queue

        mock_queue = Queue()
        # 确保队列为空
        while not mock_queue.empty():
            try:
                mock_queue.get_nowait()
            except Exception:
                break
        flow._task_queue = mock_queue
        flow._execution_lock = threading.Lock()
        flow._active_tasks = set()

        # 调用 wait_for_completion
        completed = JobState.wait_for_completion(flow, job_state, timeout=1.0)

        # 验证状态被正确设置为 "failed"
        assert completed, "Should complete successfully"
        assert job_state.status == "failed", (
            "Status should be 'failed' when 'error' status detected"
        )

    def test_wait_for_completion_integration_with_retry_exhaustion(self):
        """集成测试：重试用尽后，wait_for_completion 正确检测失败"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"
        flow._running = True

        class FailingRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)
                self.call_count = 0

            def process(self, **kwargs):
                self.call_count += 1
                raise RuntimeError(f"Error on attempt {self.call_count}")

        routine = FailingRoutine()
        flow_routine_id = "failing_routine"
        flow.add_routine(routine, flow_routine_id)
        routine.set_error_handler(
            ErrorHandler(
                strategy=ErrorStrategy.RETRY,
                max_retries=2,
                retry_delay=0.01,  # 快速重试用于测试
                retryable_exceptions=(RuntimeError,),
            )
        )

        # 创建任务并触发错误处理
        slot = routine.get_slot("input")
        task = SlotActivationTask(
            slot=slot,
            data={"test": "data"},
            retry_count=2,  # 已达到最大重试
            max_retries=2,
            job_state=job_state,
        )

        # 处理错误（应该设置状态为 failed）
        handle_task_error(task, RuntimeError("Max retries exceeded"), flow)

        # 验证状态已设置为 failed
        assert job_state.status == "failed"
        routine_state = job_state.get_routine_state(flow_routine_id)
        assert routine_state is not None
        assert routine_state.get("status") == "failed"

        # 模拟任务完成，调用 wait_for_completion
        from queue import Queue

        mock_queue = Queue()
        # 确保队列为空
        while not mock_queue.empty():
            try:
                mock_queue.get_nowait()
            except Exception:
                break
        flow._task_queue = mock_queue
        flow._execution_lock = threading.Lock()
        flow._active_tasks = set()

        # 临时将状态改回 running（模拟竞态条件）
        job_state.status = "running"

        # 调用 wait_for_completion
        completed = JobState.wait_for_completion(flow, job_state, timeout=1.0)

        # 验证状态被正确检测并设置为 "failed"
        assert completed, "Should complete successfully"
        assert job_state.status == "failed", (
            "Status should remain 'failed' after wait_for_completion"
        )

    def test_wait_for_completion_preserves_existing_failed_status(self):
        """测试 wait_for_completion 不会覆盖已有的 "failed" 状态"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "failed"  # 已经是 failed 状态

        # 模拟所有任务已完成
        from queue import Queue

        mock_queue = Queue()
        # 确保队列为空
        while not mock_queue.empty():
            try:
                mock_queue.get_nowait()
            except Exception:
                break
        flow._task_queue = mock_queue
        flow._execution_lock = threading.Lock()
        flow._active_tasks = set()

        # 调用 wait_for_completion
        completed = JobState.wait_for_completion(flow, job_state, timeout=1.0)

        # 验证状态保持为 "failed"
        assert completed, "Should complete successfully"
        assert job_state.status == "failed", "Status should remain 'failed'"

    def test_wait_for_completion_preserves_existing_completed_status(self):
        """测试 wait_for_completion 不会覆盖已有的 "completed" 状态"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "completed"  # 已经是 completed 状态

        # 模拟所有任务已完成
        from queue import Queue

        mock_queue = Queue()
        # 确保队列为空
        while not mock_queue.empty():
            try:
                mock_queue.get_nowait()
            except Exception:
                break
        flow._task_queue = mock_queue
        flow._execution_lock = threading.Lock()
        flow._active_tasks = set()

        # 调用 wait_for_completion
        completed = JobState.wait_for_completion(flow, job_state, timeout=1.0)

        # 验证状态保持为 "completed"
        assert completed, "Should complete successfully"
        assert job_state.status == "completed", "Status should remain 'completed'"


class TestErrorHandlingStatusFixIntegration:
    """集成测试：验证两个修复协同工作"""

    def test_full_flow_retry_exhaustion_to_failed_status(self):
        """完整流程测试：重试用尽 -> 状态设置为 failed -> wait_for_completion 保持 failed"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        job_state.status = "running"
        flow._running = True

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, **kwargs):
                raise RuntimeError("Processing error")

        routine = TestRoutine()
        flow_routine_id = "test_routine"
        flow.add_routine(routine, flow_routine_id)
        routine.set_error_handler(
            ErrorHandler(
                strategy=ErrorStrategy.RETRY,
                max_retries=3,
                retry_delay=0.01,
                retryable_exceptions=(RuntimeError,),
            )
        )

        slot = routine.get_slot("input")
        task = SlotActivationTask(
            slot=slot,
            data={"test": "data"},
            retry_count=3,  # 已达到最大重试
            max_retries=3,
            job_state=job_state,
        )

        # 步骤 1: 处理错误，应该设置状态为 failed
        handle_task_error(task, RuntimeError("Max retries exceeded"), flow)

        # 验证步骤 1: 状态和 routine 状态都正确设置
        assert job_state.status == "failed"
        routine_state = job_state.get_routine_state(flow_routine_id)
        assert routine_state is not None
        assert routine_state.get("status") == "failed"
        assert "error" in routine_state

        # 步骤 2: 模拟任务完成，但状态被误设为 running（模拟竞态条件）
        job_state.status = "running"

        # 模拟所有任务已完成
        from queue import Queue

        mock_queue = Queue()
        # 确保队列为空
        while not mock_queue.empty():
            try:
                mock_queue.get_nowait()
            except Exception:
                break
        flow._task_queue = mock_queue
        flow._execution_lock = threading.Lock()
        flow._active_tasks = set()

        # 步骤 3: 调用 wait_for_completion
        completed = JobState.wait_for_completion(flow, job_state, timeout=1.0)

        # 验证步骤 3: wait_for_completion 应该检测到错误并保持 failed 状态
        assert completed, "Should complete successfully"
        assert job_state.status == "failed", "Status should be 'failed' after detecting errors"

        # 验证执行历史中有错误记录
        history = job_state.get_execution_history()
        has_error = any(r.event_name in ["error", "failed"] for r in history)
        assert has_error or any(
            rs.get("status") in ["failed", "error"]
            for rs in job_state.routine_states.values()
            if isinstance(rs, dict)
        ), "Should have error indicators in history or routine states"
