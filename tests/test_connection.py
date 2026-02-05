"""
Connection 测试用例
"""

from routilux import Connection, Routine


class TestConnectionCreation:
    """连接创建测试"""

    def test_create_connection(self):
        """测试用例 1: 创建连接"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input")

        # 创建连接
        connection = Connection(event, slot)

        # 验证连接对象
        assert connection.source_event == event
        assert connection.target_slot == slot


class TestConnectionActivation:
    """连接激活测试"""

    def test_activate_connection(self):
        """测试用例 2: 激活连接"""
        received_data = []

        def handler(data=None, **kwargs):
            if data:
                received_data.append({"data": data})
            elif kwargs:
                received_data.append(kwargs)

        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input", handler=handler)

        connection = Connection(event, slot)

        # 激活连接
        connection.activate({"data": "test"})

        # 验证数据传递到 slot
        assert len(received_data) >= 1
        assert received_data[0].get("data") == "test" or "test" in str(received_data[0])

    def test_activate_with_multiple_params(self):
        """测试用例 3: 激活连接并传递多个参数"""
        received_data = []

        def handler(**kwargs):
            received_data.append(kwargs)

        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["param1", "param2"])
        slot = routine.define_slot("input", handler=handler)

        connection = Connection(event, slot)

        # 激活连接，传递多个参数
        connection.activate({"param1": "value1", "param2": "value2", "extra": "value3"})

        # 验证所有参数都被传递
        assert len(received_data) >= 1
        assert received_data[0].get("param1") == "value1"
        assert received_data[0].get("param2") == "value2"
        assert received_data[0].get("extra") == "value3"
