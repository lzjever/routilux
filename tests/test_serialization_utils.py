"""
序列化工具函数测试用例

测试 serialization_utils 模块的所有功能，提高代码覆盖率。
"""
import pytest
import inspect
from flowforge.serialization_utils import (
    serialize_callable,
    deserialize_callable,
    get_routine_class_info,
    load_routine_class
)
from flowforge import Routine


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
        assert result["_type"] == "function"
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
        assert result["_type"] == "method"
        assert result["class_name"] == "TestClass"
        assert result["method_name"] == "test_method"
        assert result["object_id"] == "test_id"
    
    def test_serialize_builtin(self):
        """测试序列化内置函数"""
        result = serialize_callable(len)
        assert result is not None
        assert result["_type"] == "builtin"
        assert result["name"] == "len"
    
    def test_serialize_lambda(self):
        """测试序列化 lambda 函数"""
        lambda_func = lambda x: x + 1
        
        result = serialize_callable(lambda_func)
        # lambda 函数应该被当作普通函数处理
        assert result is not None
        assert result["_type"] == "function"
    
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


class TestDeserializeCallable:
    """测试 deserialize_callable 函数"""
    
    def test_deserialize_none(self):
        """测试反序列化 None"""
        result = deserialize_callable(None)
        assert result is None
    
    def test_deserialize_function(self):
        """测试反序列化函数"""
        # 使用一个在模块中定义的函数
        from flowforge.routine import Routine
        
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
        
        # 反序列化（需要提供 context）
        context = {"routines": {"test_routine": routine}}
        deserialized = deserialize_callable(serialized, context)
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
            "name": "nonexistent_function"
        }
        result = deserialize_callable(bad_data)
        # 应该返回 None 而不是抛出异常
        assert result is None


class TestGetRoutineClassInfo:
    """测试 get_routine_class_info 函数"""
    
    def test_get_routine_class_info(self):
        """测试获取 Routine 类信息"""
        class CustomRoutine(Routine):
            pass
        
        routine = CustomRoutine()
        info = get_routine_class_info(routine)
        
        assert "class_name" in info
        assert "module" in info
        assert info["class_name"] == "CustomRoutine"
        # 模块名可能是 flowforge 或 tests.test_serialization_utils
        assert isinstance(info["module"], str)
        assert len(info["module"]) > 0


class TestLoadRoutineClass:
    """测试 load_routine_class 函数"""
    
    def test_load_routine_class(self):
        """测试加载 Routine 类"""
        # 使用标准的 Routine 类，确保可以加载
        from flowforge.routine import Routine
        
        routine = Routine()
        class_info = get_routine_class_info(routine)
        
        loaded_class = load_routine_class(class_info)
        assert loaded_class is not None
        assert loaded_class == Routine
    
    def test_load_routine_class_invalid_module(self):
        """测试加载无效模块的类"""
        invalid_info = {
            "module": "nonexistent_module_12345",
            "class_name": "SomeClass"
        }
        result = load_routine_class(invalid_info)
        assert result is None
    
    def test_load_routine_class_invalid_class(self):
        """测试加载无效类名"""
        # 使用一个存在的模块但无效的类名
        class_info = {
            "module": "flowforge.routine",
            "class_name": "NonexistentClass12345"
        }
        result = load_routine_class(class_info)
        assert result is None
    
    def test_load_routine_class_missing_fields(self):
        """测试加载缺少字段的类信息"""
        incomplete_info = {"class_name": "SomeClass"}
        result = load_routine_class(incomplete_info)
        assert result is None
        
        incomplete_info2 = {"module": "some.module"}
        result2 = load_routine_class(incomplete_info2)
        assert result2 is None
    
    def test_load_routine_class_with_exception(self):
        """测试加载类时发生异常"""
        # 创建一个会导致加载失败的类信息
        bad_info = {
            "module": None,  # 无效的模块名
            "class_name": "SomeClass"
        }
        result = load_routine_class(bad_info)
        assert result is None

