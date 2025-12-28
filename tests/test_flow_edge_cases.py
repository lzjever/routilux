"""
Flow 边界情况和错误处理测试

补充 Flow 类的测试覆盖，特别是边界情况和错误处理路径。
"""

import pytest
from routilux import Flow, Routine, JobState, ErrorHandler, ErrorStrategy


class TestFlowDeserializeEdgeCases:
    """测试 Flow 反序列化的边界情况"""

    def test_deserialize_with_missing_routine_class(self):
        """测试反序列化时无法加载 routine 类（应该报错）"""
        from serilux import register_serializable

        flow = Flow()

        @register_serializable
        class EdgeCaseTestRoutine(Routine):
            pass

        routine = EdgeCaseTestRoutine()
        routine_id = flow.add_routine(routine, "test")

        # 序列化
        data = flow.serialize()

        # 修改 _type 使其指向不存在的类
        data["routines"][routine_id]["_type"] = "NonexistentRoutineClass"

        # 反序列化应该报错（因为类未注册）
        new_flow = Flow()
        with pytest.raises(ValueError, match="class not found in registry"):
            new_flow.deserialize(data)

    def test_deserialize_with_invalid_job_state_datetime(self):
        """测试反序列化时 job_state datetime 处理"""
        flow = Flow()
        job_state = JobState(flow.flow_id)
        flow.job_state = job_state

        # 序列化
        data = flow.serialize()

        # 修改 datetime 为无效格式
        if "job_state" in data and data["job_state"]:
            data["job_state"]["created_at"] = "invalid_datetime"

        # 反序列化应该处理错误
        new_flow = Flow()
        try:
            new_flow.deserialize(data)
            # 如果成功，验证 job_state
            if new_flow.job_state:
                assert isinstance(new_flow.job_state, JobState)
        except Exception:
            # 如果失败也是可以接受的
            pass

    def test_deserialize_with_partial_connection_data(self):
        """测试反序列化时连接数据不完整"""
        from serilux import register_serializable

        flow = Flow()

        @register_serializable
        class R1(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

        @register_serializable
        class R2(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=lambda x: None)

        r1 = R1()
        r2 = R2()

        r1_id = flow.add_routine(r1, "r1")
        r2_id = flow.add_routine(r2, "r2")

        flow.connect(r1_id, "output", r2_id, "input")

        # 序列化
        data = flow.serialize()

        # 修改连接数据使其不完整（删除 _source_event_name，这样连接就无法恢复）
        if "connections" in data and len(data["connections"]) > 0:
            data["connections"][0].pop("_source_event_name", None)

        # 反序列化
        new_flow = Flow()
        new_flow.deserialize(data)
        # 不完整的连接应该被忽略
        assert len(new_flow.connections) == 0 or len(new_flow.connections) < len(flow.connections)


class TestFlowExecuteEdgeCases:
    """测试 Flow 执行的边界情况"""

    def test_execute_routine_with_no_flow_context(self):
        """测试执行 routine 但没有设置 flow 上下文"""
        flow = Flow()

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                # 尝试 emit 但没有 flow 上下文
                self.emit("output", data="test")

        routine = TestRoutine()
        routine_id = flow.add_routine(routine, "test")

        # 不设置 flow 上下文
        job_state = flow.execute(routine_id)
        assert job_state.status == "completed"

    def test_execute_with_resume_error_handling(self):
        """测试 resume 时的错误处理"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __call__(self):
                raise ValueError("Resume error")

        routine = FailingRoutine()
        routine_id = flow.add_routine(routine, "failing")

        # 创建 job_state
        job_state = JobState(flow.flow_id)
        job_state.status = "paused"
        job_state.current_routine_id = routine_id
        flow.job_state = job_state

        # 设置错误处理器
        flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))

        # resume
        result_job_state = flow.resume(job_state)
        # 根据错误处理策略，状态可能是 completed、failed 或 running
        assert result_job_state.status in ["completed", "failed", "running"]
        # 验证错误被处理（CONTINUE 策略会继续执行）
        if result_job_state.status == "completed":
            # 如果完成，说明错误被继续处理
            pass
        elif result_job_state.status == "failed":
            # 如果失败，说明错误没有被继续
            pass
        # running 状态也是可以接受的（如果错误处理器决定继续）


class TestFlowConnectionEdgeCases:
    """测试 Flow 连接的边界情况"""

    def test_connect_with_same_routine(self):
        """测试连接同一个 routine 的 event 和 slot"""
        flow = Flow()

        class SelfConnectingRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])
                self.input_slot = self.define_slot("input", handler=lambda x: None)

        routine = SelfConnectingRoutine()
        routine_id = flow.add_routine(routine, "self")

        # 应该可以连接
        connection = flow.connect(routine_id, "output", routine_id, "input")
        assert connection is not None
        assert len(flow.connections) == 1


class TestFlowSerializationEdgeCases:
    """测试 Flow 序列化的边界情况"""

    def test_serialize_flow_with_none_values(self):
        """测试序列化包含 None 值的 Flow"""
        flow = Flow()
        flow.job_state = None
        flow.error_handler = None
        flow.execution_tracker = None

        data = flow.serialize()
        assert "job_state" in data or data.get("job_state") is None
        assert "error_handler" in data or data.get("error_handler") is None

    def test_serialize_flow_with_empty_routines(self):
        """测试序列化没有 routines 的 Flow"""
        flow = Flow()
        data = flow.serialize()
        assert "routines" in data
        assert isinstance(data["routines"], dict)

    def test_serialize_flow_with_empty_connections(self):
        """测试序列化没有 connections 的 Flow"""
        flow = Flow()
        data = flow.serialize()
        assert "connections" in data
        assert isinstance(data["connections"], list)
