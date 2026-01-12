"""
Flow 综合测试用例 - 补充缺失的功能测试
"""

import pytest

from routilux import ErrorHandler, ErrorStrategy, Flow, Routine
from routilux.job_state import JobState


class TestFlowCancel:
    """Flow 取消功能测试"""

    def test_cancel_without_job_state(self):
        """测试在没有 job_state 时取消应该报错"""
        from routilux import JobState

        flow = Flow()
        # Create a JobState with wrong flow_id to test validation
        wrong_job_state = JobState(flow_id="wrong_flow_id")

        with pytest.raises(ValueError, match="does not match"):
            flow.cancel(wrong_job_state, reason="Test cancel")

    def test_cancel_active_job(self):
        """测试取消正在执行的 job"""
        flow = Flow()

        class LongRunningRoutine(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, **kwargs):
                # 模拟长时间运行
                self.emit("output", data="running")

        routine = LongRunningRoutine()
        routine_id = flow.add_routine(routine, "long_running")

        # 执行
        job_state = flow.execute(routine_id)

        # 取消
        flow.cancel(job_state, reason="User cancelled")

        # 验证取消状态
        assert job_state.status == "cancelled"
        assert flow._paused is False


class TestFlowErrorHandler:
    """Flow 错误处理器测试"""

    def test_set_error_handler(self):
        """测试设置错误处理器"""
        flow = Flow()
        error_handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)

        flow.set_error_handler(error_handler)

        assert flow.error_handler == error_handler
        assert flow.error_handler.strategy == ErrorStrategy.CONTINUE

    def test_error_handler_stop_strategy(self):
        """测试 STOP 策略"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)

            def _handle_trigger(self, **kwargs):
                raise ValueError("Test error")

        routine = FailingRoutine()
        routine_id = flow.add_routine(routine, "failing")

        error_handler = ErrorHandler(strategy=ErrorStrategy.STOP)
        flow.set_error_handler(error_handler)

        job_state = flow.execute(routine_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        assert job_state.status == "failed"

    def test_error_handler_skip_strategy(self):
        """测试 SKIP 策略"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, **kwargs):
                raise ValueError("Test error")

        class SuccessRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)
                self.executed = False

            def process(self, data):
                self.executed = True

        failing = FailingRoutine()
        success = SuccessRoutine()

        id_fail = flow.add_routine(failing, "failing")
        id_success = flow.add_routine(success, "success")

        flow.connect(id_fail, "output", id_success, "input")

        error_handler = ErrorHandler(strategy=ErrorStrategy.SKIP)
        flow.set_error_handler(error_handler)

        job_state = flow.execute(id_fail)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # SKIP 策略应该标记为 completed
        assert job_state.status == "completed"
        # 失败的 routine 应该被标记为 skipped
        assert job_state.routine_states.get("failing", {}).get("status") == "skipped"


class TestFlowPauseResume:
    """Flow 暂停和恢复测试"""

    def test_pause_without_job_state(self):
        """测试在没有 job_state 时暂停应该报错"""
        from routilux import JobState

        flow = Flow()
        # Create a JobState with wrong flow_id to test validation
        wrong_job_state = JobState(flow_id="wrong_flow_id")

        with pytest.raises(ValueError, match="does not match"):
            flow.pause(wrong_job_state, reason="Test pause")

    def test_pause_with_checkpoint(self):
        """测试带检查点的暂停"""
        flow = Flow()

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                self.emit("output", data="test")

        routine = TestRoutine()
        routine_id = flow.add_routine(routine, "test")

        # 执行
        job_state = flow.execute(routine_id)

        # 暂停并设置检查点
        checkpoint = {"step": 1, "data": "checkpoint_data"}
        flow.pause(job_state, reason="Test pause with checkpoint", checkpoint=checkpoint)

        # 验证暂停状态
        assert job_state.status == "paused"
        assert flow._paused is True
        assert len(job_state.pause_points) > 0
        assert job_state.pause_points[-1]["checkpoint"] == checkpoint

    def test_resume_from_paused_state(self):
        """测试从暂停状态恢复"""
        flow = Flow()

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])
                self.call_count = 0

            def _handle_trigger(self, **kwargs):
                self.call_count += 1
                # Get flow from routine context
                flow = getattr(self, "_current_flow", None)
                self.emit("output", flow=flow, data=f"call_{self.call_count}")

        routine = TestRoutine()
        routine_id = flow.add_routine(routine, "test")

        # 执行
        job_state = flow.execute(routine_id)

        # 等待初始任务完成
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # 暂停 - 此时应该没有待处理任务，所以pause可能不会保存任何任务
        flow.pause(job_state, reason="Test pause")
        assert job_state.status == "paused"

        # 恢复
        flow.resume(job_state)

        # 等待任务完成
        import time

        JobState.wait_for_completion(flow, job_state, timeout=3.0)
        time.sleep(0.2)  # Additional wait for status update

        # 验证恢复状态 - resume后如果没有待处理任务，事件循环应该停止
        # 由于没有待处理任务，状态可能保持running，但_paused应该为False
        assert flow._paused is False
        # 如果事件循环还在运行但没有任务，shutdown它
        if flow._running:
            flow.shutdown(wait=True)


class TestFlowFindConnection:
    """Flow 查找连接测试"""

    def test_find_connection(self):
        """测试查找连接"""
        flow = Flow()

        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        id1 = flow.add_routine(routine1, "routine1")
        id2 = flow.add_routine(routine, "routine")

        # 连接
        connection = flow.connect(id1, "output", id2, "input")

        # 查找连接
        found_connection = flow._find_connection(event, slot)

        assert found_connection == connection

    def test_find_nonexistent_connection(self):
        """测试查找不存在的连接"""
        flow = Flow()

        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        # 不创建连接，直接查找
        found_connection = flow._find_connection(event, slot)

        assert found_connection is None


class TestFlowSerializationEdgeCases:
    """Flow 序列化边界情况测试"""

    def test_serialize_empty_flow(self):
        """测试序列化空 Flow"""
        flow = Flow(flow_id="empty_flow")

        data = flow.serialize()

        assert data["flow_id"] == "empty_flow"
        assert data["_type"] == "Flow"
        assert data["routines"] == {}
        assert data["connections"] == []
        assert data.get("job_state") is None

    def test_serialize_flow_with_job_state(self):
        """测试序列化带 job_state 的 Flow"""
        flow = Flow(flow_id="test_flow")

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)

            def _handle_trigger(self, **kwargs):
                pass

        routine = TestRoutine()
        routine_id = flow.add_routine(routine, "test")

        # 执行以创建 job_state
        job_state = flow.execute(routine_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        # 序列化（Flow 不再包含执行状态）
        data = flow.serialize()
        assert "job_state" not in data, "Flow 序列化不应包含执行状态"

        # JobState 需要单独序列化
        job_state_data = job_state.serialize()
        assert "job_id" in job_state_data
        assert job_state_data["flow_id"] == "test_flow"
        assert job_state_data["status"] == "completed"

    def test_deserialize_flow_with_missing_routines(self):
        """测试反序列化缺少 routines 的 Flow"""
        flow = Flow()

        # 创建不完整的数据
        incomplete_data = {
            "_type": "Flow",
            "flow_id": "test_flow",
            "routines": {},
            "connections": [],
        }

        flow.deserialize(incomplete_data)

        assert flow.flow_id == "test_flow"
        assert len(flow.routines) == 0
        assert len(flow.connections) == 0

    def test_deserialize_flow_with_invalid_connections(self):
        """测试反序列化无效连接的 Flow（连接指向不存在的 routine）"""
        flow = Flow()

        routine = Routine()
        routine_id = flow.add_routine(routine, "test")

        # 创建包含无效连接的数据（连接指向不存在的 routine）
        # 连接对象会被创建，但无法找到对应的 event 和 slot，应该被忽略
        invalid_data = {
            "_type": "Flow",
            "flow_id": "test_flow",
            "routines": {routine_id: routine.serialize()},
            "connections": [
                {
                    "_type": "Connection",
                    "_source_routine_id": "nonexistent",
                    "_source_event_name": "output",
                    "_target_routine_id": "nonexistent",
                    "_target_slot_name": "input",
                    "param_mapping": {},
                }
            ],
        }

        flow.deserialize(invalid_data)

        # 无效连接应该被忽略（因为找不到对应的 event 和 slot）
        assert len(flow.connections) == 0


class TestFlowComplexScenarios:
    """Flow 复杂场景测试"""

    def test_multiple_flows_independent(self):
        """测试多个独立的 Flow"""
        flow1 = Flow(flow_id="flow1")
        flow2 = Flow(flow_id="flow2")

        routine1 = Routine()
        routine = Routine()

        id1 = flow1.add_routine(routine1, "r1")
        id2 = flow2.add_routine(routine, "r2")

        # 两个 flow 应该独立
        assert flow1.flow_id == "flow1"
        assert flow2.flow_id == "flow2"
        assert id1 in flow1.routines
        assert id2 in flow2.routines
        assert id1 not in flow2.routines
        assert id2 not in flow1.routines

    def test_flow_with_nested_routines(self):
        """测试包含嵌套 routine 的 Flow"""
        flow = Flow()

        class ParentRoutine(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])
                self.child_routine = Routine()

            def _handle_trigger(self, **kwargs):
                self.emit("output", data="parent")

        parent = ParentRoutine()
        parent_id = flow.add_routine(parent, "parent")

        # 执行
        job_state = flow.execute(parent_id)
        JobState.wait_for_completion(flow, job_state, timeout=2.0)

        assert job_state.status == "completed"
        assert parent.child_routine is not None
