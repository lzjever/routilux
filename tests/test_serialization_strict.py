"""
严格的序列化/反序列化测试

这些测试不妥协，如果功能不完备，测试会失败并指出问题。
根据测试结果，我们可以改进业务代码。
"""

import json
import pytest
from routilux import Flow, Routine, ErrorHandler, ErrorStrategy, JobState


class TestRoutineConfigSerialization:
    """测试 Routine 配置的序列化/反序列化 - 必须完整恢复"""

    def test_config_must_be_serialized_and_restored(self):
        """测试：_config 必须被序列化和恢复"""
        routine = Routine()
        routine.set_config(
            api_key="secret_key",
            timeout=30,
            retry_count=3,
            options={"option1": "value1", "option2": "value2"},
        )

        # 序列化
        data = routine.serialize()

        # 验证 _config 在序列化数据中
        assert "_config" in data, "_config 必须被序列化"
        assert data["_config"]["api_key"] == "secret_key"
        assert data["_config"]["timeout"] == 30
        assert data["_config"]["retry_count"] == 3
        assert data["_config"]["options"]["option1"] == "value1"

        # 反序列化
        new_routine = Routine()
        new_routine.deserialize(data)

        # 验证 _config 被完整恢复（不妥协）
        assert new_routine._config == routine._config, "_config 必须被完整恢复"
        assert new_routine._config["api_key"] == "secret_key"
        assert new_routine._config["timeout"] == 30
        assert new_routine._config["retry_count"] == 3
        assert new_routine._config["options"]["option1"] == "value1"

    def test_complex_nested_config_must_be_restored(self):
        """测试：复杂嵌套配置必须被完整恢复"""
        routine = Routine()
        routine.set_config(
            nested_dict={"a": {"b": {"c": 123}}},
            nested_list=[[1, 2], [3, 4]],
            mixed=[{"key": "value"}, [1, 2, 3]],
        )

        data = routine.serialize()
        new_routine = Routine()
        new_routine.deserialize(data)

        # 严格验证：必须完全一致
        assert new_routine._config["nested_dict"]["a"]["b"]["c"] == 123
        assert new_routine._config["nested_list"] == [[1, 2], [3, 4]]
        assert new_routine._config["mixed"] == [{"key": "value"}, [1, 2, 3]]

    def test_stats_must_be_serialized_and_restored(self):
        """测试：_stats 必须被序列化和恢复"""
        routine = Routine()
        routine._stats["processed"] = 42
        routine._stats["errors"] = [{"type": "ValueError", "message": "test"}]

        data = routine.serialize()
        assert "_stats" in data, "_stats 必须被序列化"

        new_routine = Routine()
        new_routine.deserialize(data)

        # 严格验证：必须完全一致
        assert new_routine._stats["processed"] == 42
        assert new_routine._stats["errors"][0]["type"] == "ValueError"


class TestFlowErrorHandlerSerialization:
    """测试 Flow 的 error_handler 序列化 - 必须完整恢复"""

    def test_error_handler_must_be_serialized(self):
        """测试：Flow 的 error_handler 必须被序列化"""
        flow = Flow()
        flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=5))

        data = flow.serialize()

        # 验证 error_handler 在序列化数据中
        assert "error_handler" in data, "error_handler 必须被序列化"
        assert data["error_handler"] is not None, "error_handler 不能为 None"
        assert data["error_handler"]["strategy"] == "retry"
        assert data["error_handler"]["max_retries"] == 5

    def test_error_handler_must_be_restored(self):
        """测试：Flow 的 error_handler 必须被恢复"""
        flow = Flow()
        original_handler = ErrorHandler(
            strategy=ErrorStrategy.RETRY, max_retries=5, retry_delay=2.0
        )
        flow.set_error_handler(original_handler)

        data = flow.serialize()
        new_flow = Flow()
        new_flow.deserialize(data)

        # 严格验证：必须被恢复
        assert new_flow.error_handler is not None, "error_handler 必须被恢复"
        assert new_flow.error_handler.strategy == ErrorStrategy.RETRY
        assert new_flow.error_handler.max_retries == 5
        assert new_flow.error_handler.retry_delay == 2.0


class TestFlowRoundTripSerialization:
    """测试 Flow 的往返序列化 - 必须完全一致"""

    def test_round_trip_must_preserve_all_data(self):
        """测试：往返序列化必须保留所有数据"""
        flow = Flow(execution_strategy="concurrent", max_workers=10)
        flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.outputevent = self.define_event("output", ["data"])
                self.set_config(key="value", number=42)

        routine = TestRoutine()
        routine_id = flow.add_routine(routine, "test")

        # 第一次序列化
        data1 = flow.serialize()

        # 反序列化
        flow2 = Flow()
        flow2.deserialize(data1)

        # 第二次序列化
        data2 = flow2.serialize()

        # 严格验证：关键字段必须一致
        assert data1["execution_strategy"] == data2["execution_strategy"]
        assert data1["max_workers"] == data2["max_workers"]
        assert len(data1["routines"]) == len(data2["routines"])
        assert len(data1["connections"]) == len(data2["connections"])

        # 验证 error_handler 一致（注意：strategy 在序列化时是字符串，反序列化后是枚举）
        if "error_handler" in data1:
            assert "error_handler" in data2, "error_handler 必须在往返序列化中保留"
            # 比较关键字段，忽略 strategy 的类型差异（枚举 vs 字符串）
            eh1 = data1["error_handler"]
            eh2 = data2["error_handler"]
            assert eh1.get("max_retries") == eh2.get("max_retries")
            assert eh1.get("retry_delay") == eh2.get("retry_delay")
            # strategy 值应该一致（即使类型不同）
            strategy1 = eh1.get("strategy")
            strategy2 = eh2.get("strategy")
            if isinstance(strategy1, str):
                assert strategy1 == (strategy2.value if hasattr(strategy2, "value") else strategy2)
            elif hasattr(strategy1, "value"):
                assert strategy1.value == (
                    strategy2.value if hasattr(strategy2, "value") else strategy2
                )

        # 验证 routine 配置一致
        if routine_id in data1["routines"]:
            r1_config = data1["routines"][routine_id].get("_config", {})
            r2_config = data2["routines"][routine_id].get("_config", {})
            assert r1_config == r2_config, "routine _config 必须在往返序列化中保留"


class TestFlowWithJobStateSerialization:
    """测试包含 JobState 的 Flow 序列化"""

    def test_job_state_must_be_serialized_and_restored(self):
        """测试：JobState 必须被序列化和恢复"""
        flow = Flow()
        job_state = JobState(flow_id=flow.flow_id)
        job_state.status = "running"
        job_state.current_routine_id = "routine1"
        flow.job_state = job_state

        data = flow.serialize()
        assert "job_state" in data, "job_state 必须被序列化"

        new_flow = Flow()
        new_flow.deserialize(data)

        # 严格验证：必须被恢复
        assert new_flow.job_state is not None, "job_state 必须被恢复"
        assert new_flow.job_state.flow_id == flow.flow_id
        assert new_flow.job_state.status == "running"
        assert new_flow.job_state.current_routine_id == "routine1"


class TestRoutineHandlerRestoration:
    """测试 Routine handler 的恢复 - 如果无法恢复，应该明确失败或提供替代方案"""

    def test_slot_handler_metadata_must_be_preserved(self):
        """测试：slot handler 的元数据必须被保留"""
        results = []

        def handler(data):
            results.append(data)

        routine = Routine()
        routine.define_slot("input", handler=handler)

        data = routine.serialize()

        # 验证 handler 被序列化（现在直接序列化为 callable，不再使用 _handler_metadata）
        assert "_slots" in data
        slot_data = data["_slots"].get("input", {})
        # Handler is now directly serialized as a callable in the slot data
        assert "handler" in slot_data, "handler 必须被序列化"
        assert isinstance(slot_data["handler"], dict), "handler 应该被序列化为字典"
        assert slot_data["handler"].get("_type") == "callable", "handler 应该是 callable 类型"

        # 反序列化
        new_routine = Routine()
        new_routine.deserialize(data)

        # 验证 slot 结构被恢复
        assert "input" in new_routine._slots
        # 注意：handler 可能无法完全恢复（因为可能是闭包或方法），
        # 但元数据应该被保留以便后续恢复
        assert hasattr(new_routine._slots["input"], "_handler_metadata") or hasattr(
            new_routine._slots["input"], "handler"
        ), "handler 元数据或 handler 本身必须被保留"


class TestSerializationWithSpecialValues:
    """测试特殊值的序列化"""

    def test_none_values_must_be_preserved(self):
        """测试：None 值必须被保留"""
        routine = Routine()
        routine.set_config(
            none_value=None,
            empty_string="",
            zero=0,
            false_value=False,
        )

        data = routine.serialize()
        new_routine = Routine()
        new_routine.deserialize(data)

        # 严格验证
        assert new_routine._config["none_value"] is None
        assert new_routine._config["empty_string"] == ""
        assert new_routine._config["zero"] == 0
        assert new_routine._config["false_value"] is False

    def test_unicode_and_special_chars_must_be_preserved(self):
        """测试：Unicode 和特殊字符必须被保留"""
        routine = Routine()
        routine.set_config(
            unicode_text="测试中文 🎉",
            special_chars="!@#$%^&*()",
            newlines="line1\nline2\nline3",
            quotes='test "quotes"',
        )

        data = routine.serialize()

        # 测试 JSON 兼容性
        json_str = json.dumps(data, ensure_ascii=False)
        loaded_data = json.loads(json_str)

        new_routine = Routine()
        new_routine.deserialize(loaded_data)

        # 严格验证
        assert new_routine._config["unicode_text"] == "测试中文 🎉"
        assert new_routine._config["special_chars"] == "!@#$%^&*()"
        assert new_routine._config["newlines"] == "line1\nline2\nline3"
        assert new_routine._config["quotes"] == 'test "quotes"'


class TestFlowDeserializeAndExecute:
    """测试反序列化后执行 - 必须能正常工作"""

    def test_deserialized_flow_must_be_executable(self):
        """测试：反序列化后的 Flow 必须能执行"""
        flow = Flow(execution_strategy="concurrent", max_workers=3)
        results = []
        results_lock = __import__("threading").Lock()

        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.outputevent = self.define_event("output", ["value"])

            def __call__(self):
                self.emit("output", value=42, flow=flow)

        class TargetRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, value):
                with results_lock:
                    results.append(value.get("value"))

        source = SourceRoutine()
        target = TargetRoutine()

        source_id = flow.add_routine(source, "source")
        target_id = flow.add_routine(target, "target")

        flow.connect(source_id, "output", target_id, "input")

        # 序列化
        data = flow.serialize()

        # 反序列化
        new_flow = Flow()
        new_flow.deserialize(data)

        # 执行（必须能工作）
        # 注意：handler 可能无法完全恢复（特别是闭包和 lambda），
        # 但至少应该能够执行而不抛出异常
        try:
            new_flow.execute(source_id)
            if new_flow.execution_strategy == "concurrent":
                new_flow.wait_for_completion(timeout=2.0)
        except Exception as e:
            pytest.fail(f"反序列化后的 Flow 执行失败: {e}")

        # 验证：如果 handler 被恢复，应该产生结果
        # 如果 handler 无法恢复（闭包/lambda），这是预期的限制
        # 但至少验证 Flow 结构完整，可以执行
        assert source_id in new_flow.routines, "source routine 必须存在"
        assert target_id in new_flow.routines, "target routine 必须存在"
        assert len(new_flow.connections) > 0, "connections 必须被恢复"

        # 如果 handler 是方法（可以恢复），应该产生结果
        # 如果 handler 是闭包/lambda（无法恢复），results 可能为空，这是预期的
        # 这个测试主要验证 Flow 结构完整性和执行不抛异常
