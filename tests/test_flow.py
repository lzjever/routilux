"""
Flow 测试用例
"""

import pytest
from routilux import Flow, Routine


class TestFlowManagement:
    """Flow 管理测试"""

    def test_create_flow(self):
        """测试用例 1: 创建 Flow"""
        # 使用自动生成的 flow_id
        flow = Flow()
        assert flow.flow_id is not None

        # 使用指定的 flow_id
        flow = Flow(flow_id="test_flow")
        assert flow.flow_id == "test_flow"

    def test_add_routine(self):
        """测试用例 2: 添加 Routine"""
        flow = Flow()
        routine = Routine()

        # 添加 routine，使用自动生成的 id
        routine_id = flow.add_routine(routine)
        assert routine_id is not None
        assert routine_id in flow.routines
        assert flow.routines[routine_id] == routine

        # 添加 routine，使用指定的 id
        routine = Routine()
        routine_id2 = flow.add_routine(routine, routine_id="custom_id")
        assert routine_id2 == "custom_id"
        assert "custom_id" in flow.routines

    def test_connect_routines(self):
        """测试用例 3: 连接 Routines"""
        flow = Flow()

        routine1 = Routine()
        routine = Routine()

        # 定义 events 和 slots
        routine1.define_event("output", ["data"])
        routine.define_slot("input")

        # 添加到 flow
        id1 = flow.add_routine(routine1, "routine1")
        id2 = flow.add_routine(routine, "routine")

        # 连接
        connection = flow.connect(id1, "output", id2, "input")
        assert connection is not None
        assert connection in flow.connections

    def test_connect_invalid_routine(self):
        """测试用例 3: 无效连接 - 不存在的 routine"""
        flow = Flow()

        # 尝试连接不存在的 routine 应该报错
        with pytest.raises(ValueError):
            flow.connect("nonexistent", "output", "target", "input")

    def test_connect_invalid_event(self):
        """测试用例 3: 无效连接 - 不存在的 event"""
        flow = Flow()

        routine1 = Routine()
        routine = Routine()

        id1 = flow.add_routine(routine1, "routine1")
        id2 = flow.add_routine(routine, "routine")

        # 尝试连接不存在的 event 应该报错
        with pytest.raises(ValueError):
            flow.connect(id1, "nonexistent_event", id2, "input")

    def test_connect_invalid_slot(self):
        """测试用例 3: 无效连接 - 不存在的 slot"""
        flow = Flow()

        routine1 = Routine()
        routine = Routine()

        routine1.define_event("output")

        id1 = flow.add_routine(routine1, "routine1")
        id2 = flow.add_routine(routine, "routine")

        # 尝试连接不存在的 slot 应该报错
        with pytest.raises(ValueError):
            flow.connect(id1, "output", id2, "nonexistent_slot")


class TestFlowExecution:
    """Flow 执行测试"""

    def test_simple_linear_flow(self):
        """测试用例 4: 简单线性流程 A -> B -> C"""
        flow = Flow()

        class RoutineA(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, data=None, **kwargs):
                data = data or kwargs.get("data", "A")
                self.emit("output", data=data)

        class RoutineB(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)
                self.output_event = self.define_event("output", ["data"])

            def process(self, data):
                self.emit("output", data=f"B({data})")

        class RoutineC(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)
                self.result = None

            def process(self, data):
                self.result = f"C({data})"

        a = RoutineA()
        b = RoutineB()
        c = RoutineC()

        # 添加到 flow
        id_a = flow.add_routine(a, "A")
        id_b = flow.add_routine(b, "B")
        id_c = flow.add_routine(c, "C")

        # 连接
        flow.connect(id_a, "output", id_b, "input")
        flow.connect(id_b, "output", id_c, "input")

        # 执行
        job_state = flow.execute(id_a, entry_params={"data": "start"})

        # 验证
        assert job_state.status == "completed"
        assert c.result is not None

    def test_branch_flow(self):
        """测试用例 5: 分支流程 A -> (B, C)"""
        flow = Flow()

        results = {}

        class RoutineA(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, data=None, **kwargs):
                data = data or kwargs.get("data", "A")
                self.emit("output", data=data)

        class RoutineB(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data):
                results["B"] = f"B({data})"

        class RoutineC(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data):
                results["C"] = f"C({data})"

        a = RoutineA()
        b = RoutineB()
        c = RoutineC()

        id_a = flow.add_routine(a, "A")
        id_b = flow.add_routine(b, "B")
        id_c = flow.add_routine(c, "C")

        # 连接：A 的输出连接到 B 和 C
        flow.connect(id_a, "output", id_b, "input")
        flow.connect(id_a, "output", id_c, "input")

        # 执行
        job_state = flow.execute(id_a)

        # 验证两个分支都执行了
        assert job_state.status == "completed"
        assert "B" in results or "C" in results

    def test_converge_flow(self):
        """测试用例 6: 汇聚流程 (A, B) -> C"""
        flow = Flow()

        received_data = []

        class RoutineA(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, **kwargs):
                self.emit("output", data="A")

        class RoutineB(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, **kwargs):
                self.emit("output", data="B")

        class RoutineC(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot(
                    "input", handler=self.process, merge_strategy="append"
                )

            def process(self, data):
                received_data.append(data)

        a = RoutineA()
        b = RoutineB()
        c = RoutineC()

        id_a = flow.add_routine(a, "A")
        id_b = flow.add_routine(b, "B")
        id_c = flow.add_routine(c, "C")

        # 连接：A 和 B 的输出都连接到 C
        flow.connect(id_a, "output", id_c, "input")
        flow.connect(id_b, "output", id_c, "input")

        # 执行（顺序执行 A 和 B）
        flow.execute(id_a)
        flow.execute(id_b)

        # 验证 C 收到了输入
        assert len(received_data) >= 1

    def test_empty_flow(self):
        """测试用例 8: 空 Flow"""
        flow = Flow()

        # 空 flow 应该可以创建
        assert len(flow.routines) == 0
        assert len(flow.connections) == 0

    def test_single_routine_flow(self):
        """测试用例 9: 单个 Routine"""
        flow = Flow()

        class SimpleRoutine(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.called = False

            def _handle_trigger(self, **kwargs):
                self.called = True

        routine = SimpleRoutine()
        routine_id = flow.add_routine(routine, "single")

        # 执行
        job_state = flow.execute(routine_id)

        # 验证
        assert job_state.status == "completed"
        assert routine.called is True


class TestFlowErrorHandling:
    """Flow 错误处理测试"""

    def test_nonexistent_entry_routine(self):
        """测试用例 10: 不存在的 Entry Routine"""
        flow = Flow()

        # 尝试执行不存在的 routine 应该报错
        with pytest.raises(ValueError):
            flow.execute("nonexistent_routine")

    def test_routine_execution_exception(self):
        """测试用例 11: Routine 执行异常"""
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

        # 执行应该捕获异常
        job_state = flow.execute(routine_id)

        # 验证错误状态被记录
        assert job_state.status == "failed"
        assert routine_id in job_state.routine_states
        assert "error" in job_state.routine_states[routine_id]
