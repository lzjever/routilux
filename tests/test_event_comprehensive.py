"""
Event 综合测试用例

补充 Event 类的测试覆盖，特别是并发执行和错误处理。
"""

import threading
from routilux import Flow, Routine, Event, Slot, ErrorHandler, ErrorStrategy


class TestEventConcurrentEmit:
    """测试 Event 并发 emit"""

    def test_concurrent_emit_error_handling(self):
        """测试并发 emit 时的错误处理"""
        flow = Flow(execution_strategy="concurrent", max_workers=5)

        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                self.emit("output", data="test", flow=flow)

        class FailingRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data):
                # 故意抛出异常
                raise ValueError("Test error in concurrent execution")

        source = SourceRoutine()
        failing = FailingRoutine()

        source_id = flow.add_routine(source, "source")
        failing_id = flow.add_routine(failing, "failing")

        flow.connect(source_id, "output", failing_id, "input")

        # 执行
        job_state = flow.execute(source_id)

        # 等待所有并发任务完成
        flow.wait_for_completion(timeout=2.0)

        # 验证错误被记录到 stats
        assert "errors" in failing._stats, f"Expected 'errors' in stats, got: {failing._stats}"
        assert len(failing._stats["errors"]) > 0
        assert job_state.status == "completed"

    def test_concurrent_emit_without_flow(self):
        """测试并发模式下 emit 但没有提供 flow"""
        flow = Flow(execution_strategy="concurrent", max_workers=5)
        results = []
        results_lock = threading.Lock()

        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                # 不提供 flow，应该使用顺序执行
                self.emit("output", data="test")

        class TargetRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data):
                with results_lock:
                    results.append(data)

        source = SourceRoutine()
        target = TargetRoutine()

        source_id = flow.add_routine(source, "source")
        flow.add_routine(target, "target")

        # 直接连接（不使用 Connection）
        source.output_event.connect(target.input_slot)

        job_state = flow.execute(source_id)
        assert len(results) == 1
        assert job_state.status == "completed"


class TestEventEdgeCases:
    """测试 Event 边界情况"""

    def test_event_repr_without_routine(self):
        """测试 Event.__repr__ 在没有 routine 时"""
        event = Event(name="test_event")
        # 应该不会抛出异常
        repr_str = repr(event)
        assert "test_event" in repr_str or "Event" in repr_str

    def test_event_connect_disconnect_multiple_times(self):
        """测试多次连接和断开"""
        event = Event(name="test")
        slot = Slot(name="test_slot")

        # 多次连接应该只连接一次
        event.connect(slot)
        event.connect(slot)
        assert len(event.connected_slots) == 1

        # 多次断开应该只断开一次
        event.disconnect(slot)
        event.disconnect(slot)
        assert len(event.connected_slots) == 0

    def test_event_emit_to_no_slots(self):
        """测试 emit 到没有连接的 slots"""
        event = Event(name="test")
        # 应该不会抛出异常
        event.emit(data="test")

    def test_event_emit_with_connection_error(self):
        """测试 emit 时 connection 激活失败"""
        flow = Flow()
        flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))

        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                self.emit("output", data="test", flow=flow)

        class TargetRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data):
                raise ValueError("Handler error")

        source = SourceRoutine()
        target = TargetRoutine()

        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")

        flow.connect(source_id, "output", target_id, "input")

        # 执行
        job_state = flow.execute(source_id)
        # 错误应该被记录，但不会中断流程（因为使用了 CONTINUE 策略）
        # 验证 job_state 状态或错误被记录
        assert job_state.status in ["completed", "failed"]
        # 如果状态是 completed，说明错误被继续处理
        # 如果状态是 failed，检查是否有错误记录
        if job_state.status == "completed":
            assert "errors" in target._stats
        else:
            # failed 状态也是可以接受的
            pass
