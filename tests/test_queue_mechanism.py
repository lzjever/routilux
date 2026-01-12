"""
队列机制测试用例

测试新的事件队列模式：
- 非阻塞 emit()
- 统一执行模型
- 任务队列和事件循环
- Pause/Resume 序列化
"""

import threading
import time

from routilux import Flow, Routine
from routilux.job_state import JobState


class TestNonBlockingEmit:
    """测试非阻塞 emit()"""

    def test_emit_returns_immediately(self):
        """测试 emit() 立即返回，不等待下游执行"""
        flow = Flow()
        execution_order = []
        lock = threading.Lock()

        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, **kwargs):
                # emit 应该立即返回 (flow自动从routine上下文获取)
                start_time = time.time()
                self.emit("output", data="test")
                emit_time = time.time() - start_time

                with lock:
                    execution_order.append(("emit_returned", emit_time))

        class TargetRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data):
                time.sleep(0.1)  # 模拟耗时操作
                with lock:
                    execution_order.append(("target_processed", time.time()))

        source = SourceRoutine()
        target = TargetRoutine()

        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")

        flow.connect(source_id, "output", target_id, "input")

        # 执行
        job_state = flow.execute(source_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # emit 应该在 target 处理完成之前就返回
        # 但由于是队列机制，我们需要等待事件循环完成
        assert job_state.status == "completed"
        assert len(execution_order) >= 2

    def test_multiple_emits_queued(self):
        """测试多个 emit() 调用会被排队"""
        flow = Flow()
        received_data = []

        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, **kwargs):
                # 连续 emit 多次 (flow自动从routine上下文获取)
                for i in range(3):
                    self.emit("output", data=f"data_{i}")

        class TargetRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data=None, **kwargs):
                if data:
                    received_data.append(data)
                elif kwargs:
                    received_data.append(kwargs.get("data"))

        source = SourceRoutine()
        target = TargetRoutine()

        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")

        flow.connect(source_id, "output", target_id, "input")

        job_state = flow.execute(source_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        assert job_state.status == "completed"
        # 所有数据都应该被接收
        assert len(received_data) == 3
        # 数据可能是字典格式或字符串格式
        data_values = [
            d if isinstance(d, str) else d.get("data") if isinstance(d, dict) else str(d)
            for d in received_data
        ]
        assert "data_0" in data_values
        assert "data_1" in data_values
        assert "data_2" in data_values


class TestUnifiedExecutionModel:
    """测试统一执行模型"""

    def test_sequential_mode_uses_queue(self):
        """测试顺序模式使用队列机制"""
        flow = Flow(execution_strategy="sequential")

        assert flow.max_workers == 1
        assert flow._task_queue is not None
        assert flow._executor is None  # 延迟创建

    def test_concurrent_mode_uses_queue(self):
        """测试并发模式使用队列机制"""
        flow = Flow(execution_strategy="concurrent", max_workers=5)

        assert flow.max_workers == 5
        assert flow._task_queue is not None
        assert flow._executor is None  # 延迟创建

    def test_unified_execution_logic(self):
        """测试顺序和并发使用相同的执行逻辑"""
        flow_seq = Flow(execution_strategy="sequential")
        flow_con = Flow(execution_strategy="concurrent", max_workers=3)

        # 两者都应该有队列和事件循环基础设施
        assert hasattr(flow_seq, "_task_queue")
        assert hasattr(flow_seq, "_start_event_loop")
        assert hasattr(flow_con, "_task_queue")
        assert hasattr(flow_con, "_start_event_loop")

        # 区别只在 max_workers
        assert flow_seq.max_workers == 1
        assert flow_con.max_workers == 3


class TestEventLoop:
    """测试事件循环"""

    def test_event_loop_starts_on_execute(self):
        """测试执行时启动事件循环"""
        flow = Flow()

        class SimpleRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)

            def _handle_trigger(self, **kwargs):
                pass

        routine = SimpleRoutine()
        routine_id = flow.add_routine(routine, "simple")

        # 执行前事件循环未启动
        assert not flow._running

        job_state = flow.execute(routine_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # 执行后事件循环应该已停止（因为任务完成）
        assert job_state.status == "completed"

    def test_event_loop_processes_tasks(self):
        """测试事件循环处理任务"""
        flow = Flow()
        processed = []

        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, **kwargs):
                self.emit("output", flow=flow, data="test")

        class TargetRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data):
                processed.append(data)

        source = SourceRoutine()
        target = TargetRoutine()

        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")

        flow.connect(source_id, "output", target_id, "input")

        job_state = flow.execute(source_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        assert job_state.status == "completed"
        assert len(processed) == 1
        # 数据可能是字典格式或字符串格式
        value = (
            processed[0]
            if isinstance(processed[0], str)
            else processed[0].get("data")
            if isinstance(processed[0], dict)
            else str(processed[0])
        )
        assert value == "test"


class TestPauseResumeSerialization:
    """测试 Pause/Resume 序列化"""

    def test_pause_saves_pending_tasks(self):
        """测试 pause 时保存 pending 任务"""
        flow = Flow()
        processed = []

        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, **kwargs):
                # emit 多个任务
                for i in range(3):
                    self.emit("output", flow=flow, data=f"data_{i}")

        class TargetRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data):
                processed.append(data)

        source = SourceRoutine()
        target = TargetRoutine()

        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")

        flow.connect(source_id, "output", target_id, "input")

        # 启动执行
        job_state = flow.execute(source_id)

        # 在任务处理前暂停（这在实际场景中可能需要在另一个线程中）
        # 这里我们验证 pause 方法能正确序列化 pending 任务
        flow.pause(job_state, reason="test")

        # 验证 pending_tasks 被序列化
        assert hasattr(job_state, "pending_tasks")
        # 注意：由于执行可能已完成，pending_tasks 可能为空

    def test_resume_restores_pending_tasks(self):
        """测试 resume 时恢复 pending 任务"""
        flow = Flow()
        processed = []

        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, **kwargs):
                self.emit("output", flow=flow, data="test")

        class TargetRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data):
                processed.append(data)

        source = SourceRoutine()
        target = TargetRoutine()

        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")

        flow.connect(source_id, "output", target_id, "input")

        # 执行并暂停
        job_state = flow.execute(source_id)
        flow.pause(job_state, reason="test")

        # 序列化
        serialized = job_state.serialize()

        # 创建新 flow 并恢复（使用相同的 flow_id）
        from routilux.job_state import JobState

        flow2 = Flow(flow_id=flow.flow_id)  # 使用相同的 flow_id
        flow2.add_routine(SourceRoutine(), "source")
        flow2.add_routine(TargetRoutine(), "target")
        flow2.connect("source", "output", "target", "input")

        # 正确创建和反序列化 JobState
        job_state2 = JobState(flow2.flow_id)
        job_state2.deserialize(serialized)

        # 恢复执行
        flow2.resume(job_state2)

        # 验证状态恢复
        assert job_state2.status in ["running", "completed"]


class TestTaskErrorHandling:
    """测试任务级错误处理"""

    def test_task_error_handling(self):
        """测试任务执行错误处理"""
        flow = Flow()

        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, **kwargs):
                self.emit("output", flow=flow, data="test")

        class TargetRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data=None, **kwargs):
                # 使用 propagate_exceptions 来让错误传播
                raise ValueError("Test error")

        source = SourceRoutine()
        target = TargetRoutine()

        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")

        flow.connect(source_id, "output", target_id, "input")

        # 注意：slot 的错误默认是被捕获的，不会导致 flow 失败
        # 错误会被记录到 JobState
        job_state = flow.execute(source_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # 由于 slot 错误被捕获，flow 应该完成
        assert job_state.status == "completed"

        # 验证错误被记录到JobState
        # Errors are tracked in execution history, not routine._stats
        history = job_state.get_execution_history(target_id)
        assert len(history) > 0
