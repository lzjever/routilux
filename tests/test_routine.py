"""
Routine 测试用例
"""

import pytest
from routilux import Routine


class TestRoutineBasic:
    """Routine 基本功能测试"""

    def test_create_routine(self):
        """测试用例 1: 创建 Routine 对象"""
        routine = Routine()
        assert routine._id is not None
        assert isinstance(routine._stats, dict)
        assert len(routine._stats) == 0

    def test_define_slot(self):
        """测试用例 2: 定义 Slot"""
        routine = Routine()

        def handler(data):
            pass

        slot = routine.define_slot("input", handler=handler)
        assert slot.name == "input"
        assert slot.routine == routine
        assert slot.handler == handler
        assert "input" in routine._slots

    def test_define_event(self):
        """测试用例 3: 定义 Event"""
        routine = Routine()

        event = routine.define_event("output", ["result", "status"])
        assert event.name == "output"
        assert event.routine == routine
        assert event.output_params == ["result", "status"]
        assert "output" in routine._events

    def test_emit_event(self):
        """测试用例 4: 触发 Event"""
        routine = Routine()

        # 定义事件
        event = routine.define_event("output", ["data"])

        # 触发事件（没有连接时不应该报错）
        routine.emit("output", data="test")

        # 验证事件已定义
        assert "output" in routine._events
        assert routine.get_event("output") == event

    def test_stats_method(self):
        """测试用例 5: Stats 方法"""
        routine = Routine()

        # 初始状态为空
        stats = routine.stats()
        assert isinstance(stats, dict)
        assert len(stats) == 0

        # 更新状态
        routine._stats["count"] = 1
        routine._stats["result"] = "success"

        # 验证 stats() 返回副本
        stats = routine.stats()
        assert stats["count"] == 1
        assert stats["result"] == "success"

        # 修改返回的字典不应影响内部状态
        stats["new_key"] = "new_value"
        assert "new_key" not in routine._stats


class TestRoutineEdgeCases:
    """Routine 边界情况测试"""

    def test_empty_routine(self):
        """测试用例 6: 空 Routine"""
        routine = Routine()

        # 没有 slots 和 events 的 routine 应该可以正常工作
        assert len(routine._slots) == 0
        assert len(routine._events) == 0

        # 直接调用 __call__ 不应该报错
        routine()

    def test_duplicate_slot_name(self):
        """测试用例 7: 重复定义 Slot"""
        routine = Routine()

        routine.define_slot("input")

        # 重复定义同名 slot 应该报错
        with pytest.raises(ValueError):
            routine.define_slot("input")

    def test_duplicate_event_name(self):
        """测试用例 7: 重复定义 Event"""
        routine = Routine()

        routine.define_event("output")

        # 重复定义同名 event 应该报错
        with pytest.raises(ValueError):
            routine.define_event("output")


class TestRoutineIntegration:
    """Routine 集成测试"""

    def test_routine_lifecycle(self):
        """测试 Routine 完整生命周期"""
        routine = Routine()

        # 1. 定义 slots 和 events
        received_data = []

        def handler(data):
            received_data.append(data)

        routine.define_slot("input", handler=handler)
        routine.define_event("output", ["result"])

        # 2. 更新状态
        routine._stats["initialized"] = True

        # 3. 触发事件
        routine.emit("output", result="test")

        # 4. 查询状态
        stats = routine.stats()
        assert stats["initialized"] is True
        assert "output" in routine._events
        assert "input" in routine._slots
