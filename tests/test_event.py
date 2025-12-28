"""
Event 测试用例
"""

from routilux import Routine


class TestEventConnection:
    """Event 连接管理测试"""

    def test_connect_to_slot(self):
        """测试用例 1: 连接到 Slot"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        # 连接
        event.connect(slot)

        # 验证连接关系
        assert slot in event.connected_slots
        assert event in slot.connected_events

    def test_disconnect_from_slot(self):
        """测试用例 2: 断开连接"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output")
        slot = routine.define_slot("input")

        # 连接
        event.connect(slot)
        assert slot in event.connected_slots

        # 断开
        event.disconnect(slot)
        assert slot not in event.connected_slots
        assert event not in slot.connected_events

    def test_one_to_many_connection(self):
        """测试用例 3: 一对多连接 - 一个 event 连接多个 slots"""
        routine1 = Routine()
        routine = Routine()
        routine3 = Routine()

        event = routine1.define_event("output")
        slot1 = routine.define_slot("input1")
        slot2 = routine3.define_slot("input2")

        # 连接多个 slots
        event.connect(slot1)
        event.connect(slot2)

        # 验证
        assert len(event.connected_slots) == 2
        assert slot1 in event.connected_slots
        assert slot2 in event.connected_slots


class TestEventEmission:
    """Event 事件触发测试"""

    def test_emit_to_connected_slots(self):
        """测试用例 4: 触发事件"""
        received_data = []

        def handler1(data=None, **kwargs):
            if data:
                received_data.append(("handler1", {"data": data}))
            elif kwargs:
                received_data.append(("handler1", kwargs))

        def handler2(data=None, **kwargs):
            if data:
                received_data.append(("handler2", {"data": data}))
            elif kwargs:
                received_data.append(("handler2", kwargs))

        class Routine1(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                self.emit("output", data="test")

        routine1 = Routine1()
        routine = Routine()
        routine3 = Routine()

        slot1 = routine.define_slot("input1", handler=handler1)
        slot2 = routine3.define_slot("input2", handler=handler2)

        # 连接
        routine1.get_event("output").connect(slot1)
        routine1.get_event("output").connect(slot2)

        # 触发事件（需要通过 Flow 来正确触发）
        from routilux import Flow

        flow = Flow()
        flow.add_routine(routine1, "r1")
        flow.add_routine(routine, "r2")
        flow.add_routine(routine3, "r3")
        flow.connect("r1", "output", "r2", "input1")
        flow.connect("r1", "output", "r3", "input2")

        # 执行 flow
        flow.execute("r1")

        # 验证所有连接的 slots 都收到数据
        assert len(received_data) >= 2

    def test_emit_without_connections(self):
        """测试用例 5: 无连接事件"""
        routine = Routine()

        routine.define_event("output", ["data"])

        # 没有连接的事件应该可以正常触发，不报错
        routine.emit("output", data="test")

        # 验证事件已定义
        assert "output" in routine._events

    def test_output_params(self):
        """测试用例 6: 输出参数验证"""
        routine = Routine()

        # 定义带输出参数的事件
        event = routine.define_event("output", ["result", "status"])

        # 验证输出参数正确记录
        assert "result" in event.output_params
        assert "status" in event.output_params

        # 未声明的参数也应该能传递
        routine.emit("output", result="ok", status="success", extra="data")


class TestEventDataFlow:
    """Event 数据流测试"""

    def test_data_propagation(self):
        """测试数据传播"""
        results = []

        def handler(value1=None, value2=None, **kwargs):
            if value1 or value2:
                results.append({"value1": value1, "value2": value2})
            elif kwargs:
                results.append(kwargs)

        class Routine1(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["value1", "value2"])

            def __call__(self):
                self.emit("output", value1="a", value2="b")

        routine1 = Routine1()
        routine = Routine()

        slot = routine.define_slot("input", handler=handler)

        # 连接
        routine1.get_event("output").connect(slot)

        # 触发事件，传递多个参数（需要通过 Flow）
        from routilux import Flow

        flow = Flow()
        flow.add_routine(routine1, "r1")
        flow.add_routine(routine, "r2")
        flow.connect("r1", "output", "r2", "input")

        # 执行 flow
        flow.execute("r1")

        # 验证数据正确传递
        assert len(results) >= 1
        # 检查 value1 和 value2 是否在结果中
        first_result = results[0]
        assert first_result.get("value1") == "a" or "a" in str(first_result)
        assert first_result.get("value2") == "b" or "b" in str(first_result)
