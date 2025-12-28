"""
Connection 综合测试用例 - 补充缺失的功能测试
"""

from routilux import Routine, Connection


class TestConnectionDisconnect:
    """Connection 断开连接测试"""

    def test_disconnect(self):
        """测试断开连接"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        # 创建连接
        connection = Connection(event, slot)

        # 验证连接已建立
        assert slot in event.connected_slots
        assert event in slot.connected_events

        # 断开连接
        connection.disconnect()

        # 验证连接已断开
        assert slot not in event.connected_slots
        assert event not in slot.connected_events

    def test_disconnect_multiple_times(self):
        """测试多次断开连接（应该是安全的）"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        connection = Connection(event, slot)

        # 第一次断开
        connection.disconnect()

        # 再次断开应该不会报错
        connection.disconnect()

        # 验证连接已断开
        assert slot not in event.connected_slots


class TestConnectionActivation:
    """Connection 激活测试"""

    def test_activate_with_mapping(self):
        """测试带参数映射的激活"""
        routine1 = Routine()
        routine = Routine()

        received_data = {}

        def handler(mapped_param):
            received_data["mapped_param"] = mapped_param

        event = routine1.define_event("output", ["source_param"])
        slot = routine.define_slot("input", handler=handler)

        param_mapping = {"source_param": "mapped_param"}
        connection = Connection(event, slot, param_mapping=param_mapping)

        # 激活连接
        connection.activate({"source_param": "test_value"})

        # 验证参数映射生效
        assert received_data["mapped_param"] == "test_value"

    def test_activate_without_mapping(self):
        """测试不带参数映射的激活"""
        routine1 = Routine()
        routine = Routine()

        received_data = {}

        # 根据 slot 的逻辑，如果 handler 参数名不匹配字典中的键，会传递整个字典
        # 所以我们需要使用 **kwargs 或者匹配的参数名
        def handler(**kwargs):
            received_data["data"] = kwargs.get("data")

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input", handler=handler)

        connection = Connection(event, slot)

        # 激活连接
        connection.activate({"data": "test_value"})

        # 验证数据传递
        assert received_data["data"] == "test_value"

    def test_activate_with_partial_mapping(self):
        """测试部分参数映射"""
        routine1 = Routine()
        routine = Routine()

        received_data = {}

        def handler(mapped_param, other_param):
            received_data["mapped_param"] = mapped_param
            received_data["other_param"] = other_param

        event = routine1.define_event("output", ["source_param", "other_param"])
        slot = routine.define_slot("input", handler=handler)

        # 只映射一个参数
        param_mapping = {"source_param": "mapped_param"}
        connection = Connection(event, slot, param_mapping=param_mapping)

        # 激活连接
        connection.activate({"source_param": "test_value", "other_param": "other_value"})

        # 验证参数映射和直接传递
        assert received_data["mapped_param"] == "test_value"
        assert received_data["other_param"] == "other_value"


class TestConnectionSerialization:
    """Connection 序列化测试"""

    def test_connection_serialize(self):
        """测试连接序列化"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        param_mapping = {"data": "input_data"}
        connection = Connection(event, slot, param_mapping=param_mapping)

        data = connection.serialize()

        assert data["_type"] == "Connection"
        assert data["_source_event_name"] == "output"
        assert data["_target_slot_name"] == "input"
        assert data["param_mapping"] == param_mapping

    def test_connection_deserialize(self):
        """测试连接反序列化"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        data = {
            "_type": "Connection",
            "_source_event_name": "output",
            "_target_slot_name": "input",
            "param_mapping": {"data": "input_data"},
        }

        connection = Connection()
        connection.deserialize(data)

        # 需要手动设置 event 和 slot（因为反序列化时可能还没有这些对象）
        connection.source_event = event
        connection.target_slot = slot

        assert connection.source_event == event
        assert connection.target_slot == slot
        assert connection.param_mapping == {"data": "input_data"}
