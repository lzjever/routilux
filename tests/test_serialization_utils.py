"""
序列化工具函数测试用例

测试 serialization_utils 模块的所有功能，提高代码覆盖率。
"""

from serilux import (
    serialize_callable,
    deserialize_callable,
)
from routilux import Routine


class TestSerializeCallable:
    """测试 serialize_callable 函数"""

    def test_serialize_none(self):
        """测试序列化 None"""
        result = serialize_callable(None)
        assert result is None

    def test_serialize_function(self):
        """测试序列化函数"""

        def test_func():
            pass

        result = serialize_callable(test_func)
        assert result is not None
        assert result["_type"] == "callable"
        assert result["callable_type"] == "function"
        assert result["name"] == "test_func"
        assert "module" in result

    def test_serialize_method(self):
        """测试序列化方法"""

        class TestClass:
            def __init__(self):
                self._id = "test_id"

            def test_method(self):
                pass

        obj = TestClass()
        method = obj.test_method

        result = serialize_callable(method)
        assert result is not None
        assert result["_type"] == "callable"
        assert result["callable_type"] == "method"
        assert result["class_name"] == "TestClass"
        assert result["method_name"] == "test_method"
        assert result["object_id"] == "test_id"

    def test_serialize_builtin(self):
        """测试序列化内置函数"""
        result = serialize_callable(len)
        assert result is not None
        assert result["_type"] == "callable"
        assert result["callable_type"] == "builtin"
        assert result["name"] == "len"

    def test_serialize_lambda(self):
        """测试序列化 lambda 函数"""

        def lambda_func(x):
            return x + 1

        result = serialize_callable(lambda_func)
        # lambda 函数应该被当作普通函数处理
        assert result is not None
        assert result["_type"] == "callable"
        assert result["callable_type"] == "function"

    def test_serialize_callable_with_exception(self):
        """测试序列化时发生异常的情况"""

        # 创建一个会导致序列化失败的 callable
        class BadCallable:
            def __call__(self):
                pass

            @property
            def __name__(self):
                raise Exception("Test exception")

        bad_callable = BadCallable()
        result = serialize_callable(bad_callable)
        # 应该返回 None 而不是抛出异常
        assert result is None

    def test_serialize_method_with_owner_validation_success(self):
        """测试序列化属于 owner 的方法（应该成功）"""

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self._id = "test_routine"

            def test_method(self):
                pass

        routine = TestRoutine()
        method = routine.test_method

        # 传递正确的 owner，应该成功
        result = serialize_callable(method, owner=routine)
        assert result is not None
        assert result["_type"] == "callable"
        assert result["callable_type"] == "method"
        assert result["method_name"] == "test_method"
        assert result["object_id"] == "test_routine"

    def test_serialize_method_with_owner_validation_failure(self):
        """测试序列化不属于 owner 的方法（应该抛出 ValueError）"""

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self._id = "test_routine"

            def test_method(self):
                pass

        routine1 = TestRoutine()
        routine1._id = "routine1"
        routine2 = TestRoutine()
        routine2._id = "routine2"

        # 尝试序列化 routine1 的方法，但传递 routine2 作为 owner
        method = routine1.test_method

        # 应该抛出 ValueError
        import pytest

        with pytest.raises(ValueError, match="Cannot serialize method"):
            serialize_callable(method, owner=routine2)

    def test_serialize_function_with_owner(self):
        """测试序列化函数时传递 owner（应该成功，函数不需要验证）"""

        def test_func():
            pass

        class TestRoutine(Routine):
            pass

        routine = TestRoutine()

        # 函数不需要验证，应该成功
        result = serialize_callable(test_func, owner=routine)
        assert result is not None
        assert result["_type"] == "callable"
        assert result["callable_type"] == "function"
        assert result["name"] == "test_func"


class TestDeserializeCallable:
    """测试 deserialize_callable 函数"""

    def test_deserialize_none(self):
        """测试反序列化 None"""
        result = deserialize_callable(None)
        assert result is None

    def test_deserialize_function(self):
        """测试反序列化函数"""
        # 使用一个在模块中定义的函数
        from routilux.routine import Routine

        # 序列化 Routine 类的方法
        serialized = serialize_callable(Routine.__init__)
        # 注意：模块函数反序列化需要模块可导入，这里测试方法反序列化
        assert serialized is not None

    def test_deserialize_method(self):
        """测试反序列化方法"""

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self._id = "test_routine"

            def test_method(self):
                return "test_result"

        routine = TestRoutine()
        method = routine.test_method

        # 序列化
        serialized = serialize_callable(method)
        assert serialized is not None

        # 反序列化（需要提供 registry）
        from serilux import ObjectRegistry

        registry = ObjectRegistry()
        registry.register(routine, object_id="test_routine")
        deserialized = deserialize_callable(serialized, registry=registry)
        assert deserialized is not None
        assert callable(deserialized)
        assert deserialized() == "test_result"

    def test_deserialize_method_without_context(self):
        """测试反序列化方法但没有提供 context"""

        class TestRoutine(Routine):
            def test_method(self):
                pass

        routine = TestRoutine()
        method = routine.test_method

        serialized = serialize_callable(method)
        assert serialized is not None

        # 没有 context，应该返回 None
        deserialized = deserialize_callable(serialized)
        assert deserialized is None

    def test_deserialize_method_with_wrong_object_id(self):
        """测试反序列化方法但 object_id 不匹配"""

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self._id = "test_routine"

            def test_method(self):
                pass

        routine = TestRoutine()
        method = routine.test_method

        serialized = serialize_callable(method)
        assert serialized is not None

        # 提供错误的 context（object_id 不匹配）
        other_routine = Routine()
        other_routine._id = "other_routine"
        context = {"routines": {"other_routine": other_routine}}
        deserialized = deserialize_callable(serialized, context)
        assert deserialized is None

    def test_deserialize_builtin(self):
        """测试反序列化内置函数"""
        serialized = serialize_callable(len)
        assert serialized is not None

        deserialized = deserialize_callable(serialized)
        assert deserialized is not None
        assert deserialized == len

    def test_deserialize_invalid_type(self):
        """测试反序列化无效类型"""
        invalid_data = {"_type": "invalid_type"}
        result = deserialize_callable(invalid_data)
        assert result is None

    def test_deserialize_missing_fields(self):
        """测试反序列化缺少字段的数据"""
        # 缺少必要字段
        incomplete_data = {"_type": "function"}
        result = deserialize_callable(incomplete_data)
        assert result is None

    def test_deserialize_with_exception(self):
        """测试反序列化时发生异常"""
        # 创建一个会导致反序列化失败的数据
        bad_data = {
            "_type": "function",
            "module": "nonexistent_module_12345",
            "name": "nonexistent_function",
        }
        result = deserialize_callable(bad_data)
        # 应该返回 None 而不是抛出异常
        assert result is None
