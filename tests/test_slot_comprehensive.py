"""
Slot 综合测试用例

补充 Slot 类的测试覆盖，特别是边界情况和错误处理。
"""

from routilux import Routine, Slot


class TestSlotMergeStrategy:
    """测试 Slot 合并策略"""

    def test_merge_strategy_custom_callable(self):
        """测试自定义合并函数"""

        def custom_merge(old_data, new_data):
            return {**old_data, **new_data, "merged": True}

        slot = Slot(name="test", merge_strategy=custom_merge)
        slot._data = {"a": 1}

        merged = slot._merge_data({"b": 2})
        assert merged["a"] == 1
        assert merged["b"] == 2
        assert merged["merged"] is True

    def test_merge_strategy_append_with_existing_list(self):
        """测试 append 策略，已有数据是列表"""
        slot = Slot(name="test", merge_strategy="append")
        slot._data = {"key": [1, 2]}

        merged = slot._merge_data({"key": 3})
        assert merged["key"] == [1, 2, 3]

    def test_merge_strategy_append_with_non_list(self):
        """测试 append 策略，已有数据不是列表"""
        slot = Slot(name="test", merge_strategy="append")
        slot._data = {"key": "string"}

        merged = slot._merge_data({"key": "new"})
        assert merged["key"] == ["string", "new"]

    def test_merge_strategy_invalid(self):
        """测试无效的合并策略（应该使用默认覆盖）"""
        slot = Slot(name="test", merge_strategy="invalid_strategy")
        slot._data = {"a": 1}

        merged = slot._merge_data({"b": 2})
        assert merged["b"] == 2
        assert "a" not in merged


class TestSlotHandler:
    """测试 Slot handler"""

    def test_handler_with_kwargs(self):
        """测试接受 **kwargs 的 handler"""

        def kwargs_handler(**kwargs):
            return kwargs

        slot = Slot(name="test", handler=kwargs_handler)
        slot.receive({"a": 1, "b": 2})
        # handler 应该被调用
        assert slot._data == {"a": 1, "b": 2}

    def test_handler_with_single_param(self):
        """测试只接受一个参数的 handler"""

        def single_param_handler(data):
            return data

        slot = Slot(name="test", handler=single_param_handler)
        slot.receive({"value": "test"})
        assert slot._data == {"value": "test"}

    def test_handler_with_multiple_params_partial_match(self):
        """测试多个参数但部分匹配的 handler"""

        def multi_param_handler(a, b, c=None):
            return a, b, c

        slot = Slot(name="test", handler=multi_param_handler)
        slot.receive({"a": 1, "b": 2})
        # 应该能匹配 a 和 b
        assert slot._data == {"a": 1, "b": 2}

    def test_handler_with_no_match(self):
        """测试 handler 参数完全不匹配"""

        def no_match_handler(x, y):
            return x, y

        slot = Slot(name="test", handler=no_match_handler)
        routine = Routine()
        slot.routine = routine  # 设置 routine 避免 __repr__ 错误

        slot.receive({"a": 1, "b": 2})
        # 应该传递整个字典（作为第一个参数）
        assert slot._data == {"a": 1, "b": 2}

    def test_handler_exception_handling(self):
        """测试 handler 异常处理"""

        def failing_handler(data):
            raise ValueError("Handler error")

        slot = Slot(name="test", handler=failing_handler)
        routine = Routine()
        slot.routine = routine

        # 应该不会抛出异常，而是记录到 stats
        slot.receive({"data": "test"})
        assert "errors" in routine._stats
        assert len(routine._stats["errors"]) > 0


class TestSlotSerialization:
    """测试 Slot 序列化"""

    def test_serialize_slot_with_custom_merge_strategy(self):
        """测试序列化带自定义合并策略的 Slot"""

        def custom_merge(old, new):
            return {**old, **new}

        slot = Slot(name="test", merge_strategy=custom_merge)
        routine = Routine()
        slot.routine = routine

        data = slot.serialize()
        assert data["name"] == "test"
        assert data.get("merge_strategy") == "_custom" or "_merge_strategy_metadata" in data

    def test_deserialize_slot_with_metadata(self):
        """测试反序列化带元数据的 Slot"""
        slot = Slot(name="test")
        routine = Routine()
        slot.routine = routine

        # 序列化
        data = slot.serialize()

        # 反序列化
        new_slot = Slot()
        new_slot.deserialize(data)
        assert new_slot.name == "test"
        assert hasattr(new_slot, "_routine_id") or new_slot.routine is None
