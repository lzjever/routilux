"""
Connection 测试用例
"""

from routilux import Routine, Connection


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

    def test_create_connection_with_mapping(self):
        """测试用例 1: 创建带参数映射的连接"""
        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["source_param"])
        slot = routine.define_slot("input")

        # 创建带参数映射的连接
        param_mapping = {"source_param": "target_param"}
        connection = Connection(event, slot, param_mapping=param_mapping)

        # 验证参数映射
        assert connection.param_mapping == param_mapping


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


class TestConnectionParamMapping:
    """连接参数映射测试"""

    def test_simple_mapping(self):
        """测试用例 3: 简单映射"""
        received_params = {}

        def handler(mapped_param=None, **kwargs):
            if mapped_param:
                received_params["mapped_param"] = mapped_param
            elif kwargs:
                received_params.update(kwargs)

        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["source_param"])
        slot = routine.define_slot("input", handler=handler)

        # 创建带参数映射的连接
        connection = Connection(event, slot, param_mapping={"source_param": "mapped_param"})

        # 激活连接
        connection.activate({"source_param": "test_value"})

        # 验证参数映射正确
        assert received_params.get("mapped_param") == "test_value"

    def test_complex_mapping(self):
        """测试用例 4: 复杂映射"""
        received_params = {}

        def handler(param1=None, param2=None, **kwargs):
            if param1:
                received_params["param1"] = param1
            if param2:
                received_params["param2"] = param2
            if kwargs:
                received_params.update(kwargs)

        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["src1", "src2"])
        slot = routine.define_slot("input", handler=handler)

        # 创建带多个参数映射的连接
        connection = Connection(event, slot, param_mapping={"src1": "param1", "src2": "param2"})

        # 激活连接
        connection.activate({"src1": "value1", "src2": "value2"})

        # 验证参数映射正确
        assert received_params.get("param1") == "value1"
        assert received_params.get("param2") == "value2"

    def test_partial_mapping(self):
        """测试用例 4: 部分参数映射"""
        received_params = {}

        def handler(mapped_param=None, unmapped_param=None, src2=None, **kwargs):
            if mapped_param:
                received_params["mapped_param"] = mapped_param
            if unmapped_param:
                received_params["unmapped_param"] = unmapped_param
            if src2:
                received_params["unmapped_param"] = src2
            if kwargs:
                received_params.update(kwargs)

        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["src1", "src2"])
        slot = routine.define_slot("input", handler=handler)

        # 只映射部分参数
        connection = Connection(event, slot, param_mapping={"src1": "mapped_param"})

        # 激活连接
        connection.activate({"src1": "value1", "src2": "value2"})

        # 验证映射的参数正确
        assert received_params.get("mapped_param") == "value1"

    def test_no_mapping(self):
        """测试用例 5: 无映射"""
        received_params = {}

        def handler(data=None, **kwargs):
            if data:
                received_params["data"] = data
            elif kwargs:
                received_params.update(kwargs)

        routine1 = Routine()
        routine = Routine()

        event = routine1.define_event("output", ["data"])
        slot = routine.define_slot("input", handler=handler)

        # 创建无参数映射的连接
        connection = Connection(event, slot)

        # 激活连接
        connection.activate({"data": "test"})

        # 验证参数使用原始名称
        assert received_params.get("data") == "test"
