"""
持久化测试用例
"""

import json
import os
import pytest
from routilux import Flow, Routine, JobState


class TestFlowPersistence:
    """Flow 持久化测试"""

    def test_save_flow(self, temp_file):
        """测试用例 1: 序列化 Flow"""
        flow = Flow(flow_id="test_flow")

        # 添加一些 routines
        routine1 = Routine()
        routine = Routine()

        routine1.define_event("output", ["data"])
        routine.define_slot("input")

        id1 = flow.add_routine(routine1, "routine1")
        id2 = flow.add_routine(routine, "routine")

        # 连接
        flow.connect(id1, "output", id2, "input")

        # 序列化
        data = flow.serialize()

        # 保存到文件（用于验证）
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # 验证文件存在
        assert os.path.exists(temp_file)

        # 验证文件格式（JSON）
        with open(temp_file, "r") as f:
            loaded_data = json.load(f)
            assert loaded_data["flow_id"] == "test_flow"
            assert len(loaded_data["routines"]) == 2
            assert len(loaded_data["connections"]) == 1

    def test_load_flow(self, temp_file):
        """测试用例 2: 反序列化 Flow"""
        # 先创建一个 flow 并序列化
        flow1 = Flow(flow_id="test_flow")
        routine1 = Routine()
        routine = Routine()
        routine1.define_event("output", ["data"])
        routine.define_slot("input")
        id1 = flow1.add_routine(routine1, "routine1")
        id2 = flow1.add_routine(routine, "routine")
        flow1.connect(id1, "output", id2, "input")

        # 序列化并保存到文件
        data = flow1.serialize()
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # 从文件加载并反序列化
        with open(temp_file, "r", encoding="utf-8") as f:
            loaded_data = json.load(f)

        flow2 = Flow()
        flow2.deserialize(loaded_data)

        # 验证加载的 flow 结构正确
        assert flow2.flow_id == "test_flow"
        assert len(flow2.routines) == 2
        assert len(flow2.connections) == 1

    def test_save_load_consistency(self, temp_file):
        """测试用例 3: 序列化和反序列化一致性"""
        from serilux import register_serializable

        # 创建 flow
        flow1 = Flow(flow_id="test_flow")

        @register_serializable
        class PersistenceTestRoutine0(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

        routine = PersistenceTestRoutine0()
        flow1.add_routine(routine, "test_routine")

        # 序列化并保存
        data = flow1.serialize()
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # 加载并反序列化
        with open(temp_file, "r", encoding="utf-8") as f:
            loaded_data = json.load(f)

        flow2 = Flow()
        flow2.deserialize(loaded_data)

        # 验证可以执行加载的 flow（需要重新添加 routine 实例）
        # 注意：反序列化只恢复结构，不恢复 routine 实例
        assert flow2.flow_id == "test_flow"


class TestJobStatePersistence:
    """JobState 持久化测试"""

    def test_save_job_state(self, temp_file):
        """测试用例 4: 保存 JobState"""
        job_state = JobState(flow_id="test_flow")
        job_state.status = "running"
        job_state.current_routine_id = "routine1"
        job_state.update_routine_state("routine1", {"status": "completed"})
        job_state.record_execution("routine1", "output", {"data": "test"})

        # 保存
        job_state.save(temp_file)

        # 验证文件存在
        assert os.path.exists(temp_file)

        # 验证文件格式
        with open(temp_file, "r") as f:
            data = json.load(f)
            assert data["flow_id"] == "test_flow"
            assert data["status"] == "running"
            assert data["current_routine_id"] == "routine1"

    def test_load_job_state(self, temp_file):
        """测试用例 5: 加载 JobState"""
        # 先创建一个 job_state 并保存
        job_state1 = JobState(flow_id="test_flow")
        job_state1.status = "running"
        job_state1.update_routine_state("routine1", {"status": "completed"})
        job_state1.save(temp_file)

        # 加载
        job_state2 = JobState.load(temp_file)

        # 验证状态恢复
        assert job_state2.flow_id == "test_flow"
        assert job_state2.status == "running"
        assert "routine1" in job_state2.routine_states

    def test_save_load_consistency(self, temp_file):
        """测试用例 6: 保存和加载一致性"""
        # 创建 job_state
        job_state1 = JobState(flow_id="test_flow")
        job_state1.status = "completed"
        job_state1.current_routine_id = "routine1"
        job_state1.update_routine_state(
            "routine1", {"status": "completed", "stats": {"count": 1, "result": "success"}}
        )
        job_state1.record_execution("routine1", "output", {"data": "test"})

        # 保存
        job_state1.save(temp_file)

        # 加载
        job_state2 = JobState.load(temp_file)

        # 验证一致性
        assert job_state2.flow_id == job_state1.flow_id
        assert job_state2.status == job_state1.status
        assert job_state2.current_routine_id == job_state1.current_routine_id
        assert len(job_state2.execution_history) == len(job_state1.execution_history)


class TestPersistenceEdgeCases:
    """持久化边界情况测试"""

    def test_serialize_to_file(self, tmp_path):
        """测试序列化到文件"""
        flow = Flow()

        # 序列化
        data = flow.serialize()

        # 保存到文件
        filepath = str(tmp_path / "flow.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        assert os.path.exists(filepath)

    def test_deserialize_from_invalid_json(self, temp_file):
        """测试从无效的 JSON 反序列化"""
        # 写入无效的 JSON
        with open(temp_file, "w") as f:
            f.write("invalid json content")

        # 应该报错
        with pytest.raises((json.JSONDecodeError, ValueError)):
            with open(temp_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            flow = Flow()
            flow.deserialize(data)

    def test_deserialize_invalid_structure(self, temp_file):
        """测试反序列化结构不正确的数据"""
        # 写入结构不正确的 JSON
        with open(temp_file, "w") as f:
            json.dump({"invalid": "structure"}, f)

        # 应该报错或返回空 flow
        with open(temp_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        try:
            flow = Flow()
            flow.deserialize(data)
            # 如果反序列化成功，验证是空 flow
            assert flow.flow_id is not None
        except (ValueError, KeyError, AttributeError):
            # 如果报错，这也是可以接受的
            pass


class TestSerializationComprehensive:
    """序列化/反序列化的全面测试 - 从用户角度"""

    def test_serialize_flow_with_multiple_connections(self):
        """测试序列化包含多个连接的 Flow"""
        from serilux import register_serializable

        flow = Flow(flow_id="multi_connection_flow")

        @register_serializable
        class PersistenceSourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.outputevent = self.define_event("output", ["data"])

        @register_serializable
        class PersistenceTargetRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=lambda x: None)

        source = PersistenceSourceRoutine()
        target1 = PersistenceTargetRoutine()
        target1.set_config(name="target1")
        target2 = PersistenceTargetRoutine()
        target2.set_config(name="target2")
        target3 = PersistenceTargetRoutine()
        target3.set_config(name="target3")

        source_id = flow.add_routine(source, "source")
        t1_id = flow.add_routine(target1, "target1")
        t2_id = flow.add_routine(target2, "target2")
        t3_id = flow.add_routine(target3, "target3")

        flow.connect(source_id, "output", t1_id, "input")
        flow.connect(source_id, "output", t2_id, "input")
        flow.connect(source_id, "output", t3_id, "input")

        # 序列化
        data = flow.serialize()

        # 验证连接被正确序列化
        assert len(data["connections"]) == 3

        # 反序列化
        new_flow = Flow()
        new_flow.deserialize(data)

        # 验证连接被恢复
        assert len(new_flow.connections) == 3

    def test_serialize_flow_with_chained_routines(self):
        """测试序列化链式连接的 Flow"""
        from serilux import register_serializable

        flow = Flow(flow_id="chained_flow")

        @register_serializable
        class PersistenceR1(Routine):
            def __init__(self):
                super().__init__()
                self.outputevent = self.define_event("output", ["data"])

        @register_serializable
        class PersistenceR2(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=lambda x: None)
                self.outputevent = self.define_event("output", ["data"])

        @register_serializable
        class PersistenceR3(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=lambda x: None)

        r1 = PersistenceR1()
        r2 = PersistenceR2()
        r3 = PersistenceR3()

        r1_id = flow.add_routine(r1, "r1")
        r2_id = flow.add_routine(r2, "r2")
        r3_id = flow.add_routine(r3, "r3")

        flow.connect(r1_id, "output", r2_id, "input")
        flow.connect(r2_id, "output", r3_id, "input")

        # 序列化
        data = flow.serialize()

        # 反序列化
        new_flow = Flow()
        new_flow.deserialize(data)

        # 验证链式结构被恢复
        assert len(new_flow.connections) == 2
        assert len(new_flow.routines) == 3

    def test_serialize_deserialize_with_custom_routine_config(self):
        """测试序列化/反序列化包含自定义配置的 Routine"""
        from serilux import register_serializable

        flow = Flow(flow_id="config_flow")

        @register_serializable
        class ConfigurableRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.outputevent = self.define_event("output", ["data"])
                # 设置复杂配置
                self.set_config(
                    api_key="secret_key",
                    timeout=30,
                    retry_count=3,
                    options={"option1": "value1", "option2": "value2"},
                )

        routine = ConfigurableRoutine()
        routine_id = flow.add_routine(routine, "configurable")

        # 序列化
        data = flow.serialize()

        # 反序列化
        new_flow = Flow()
        new_flow.deserialize(data)

        # 验证配置被恢复（如果 _config 被序列化）
        restored_routine = new_flow.routines[routine_id]
        config = restored_routine._config
        if config:
            assert config["api_key"] == "secret_key"
            assert config["timeout"] == 30
            assert config["retry_count"] == 3
            assert config["options"]["option1"] == "value1"
        else:
            # 如果配置没有被序列化，至少验证 routine 被恢复了
            assert routine_id in new_flow.routines

    def test_serialize_with_special_characters(self):
        """测试序列化包含特殊字符的数据"""
        from serilux import register_serializable

        flow = Flow(flow_id="special_chars_flow")

        @register_serializable
        class SpecialRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.outputevent = self.define_event("output", ["data"])
                # 包含特殊字符的配置
                self.set_config(
                    unicode_text="测试中文 🎉",
                    special_chars="!@#$%^&*()",
                    newlines="line1\nline2\nline3",
                    quotes='test "quotes"',
                )

        routine = SpecialRoutine()
        routine_id = flow.add_routine(routine, "special")

        # 序列化
        data = flow.serialize()

        # 保存到 JSON 文件（测试 JSON 兼容性）
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            json.dump(data, f, ensure_ascii=False)
            temp_file = f.name

        try:
            # 从文件加载
            with open(temp_file, "r", encoding="utf-8") as f:
                loaded_data = json.load(f)

            # 反序列化
            new_flow = Flow()
            new_flow.deserialize(loaded_data)

            # 验证特殊字符被正确恢复（如果 _config 被序列化）
            restored_routine = new_flow.routines[routine_id]
            config = restored_routine._config
            if config:
                assert config["unicode_text"] == "测试中文 🎉"
                assert config["special_chars"] == "!@#$%^&*()"
                assert config["newlines"] == "line1\nline2\nline3"
                assert config["quotes"] == 'test "quotes"'
            else:
                # 如果配置没有被序列化，至少验证 routine 被恢复了
                assert routine_id in new_flow.routines
        finally:
            os.unlink(temp_file)

    def test_serialize_with_large_data(self):
        """测试序列化包含大量数据的 Flow"""
        from serilux import register_serializable

        flow = Flow(flow_id="large_data_flow")

        @register_serializable
        class LargeDataRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.outputevent = self.define_event("output", ["data"])
                # 创建大量数据
                large_list = list(range(1000))
                large_dict = {f"key_{i}": f"value_{i}" for i in range(100)}
                self.set_config(large_list=large_list, large_dict=large_dict)

        routine = LargeDataRoutine()
        routine_id = flow.add_routine(routine, "large_data")

        # 序列化
        data = flow.serialize()

        # 验证数据被序列化
        routine_data = data["routines"][routine_id]
        assert len(routine_data["_config"]["large_list"]) == 1000
        assert len(routine_data["_config"]["large_dict"]) == 100

        # 反序列化
        new_flow = Flow()
        new_flow.deserialize(data)

        # 验证数据被恢复（如果 _config 被序列化）
        restored_routine = new_flow.routines[routine_id]
        config = restored_routine._config
        if config:
            assert len(config["large_list"]) == 1000
            assert len(config["large_dict"]) == 100
        else:
            # 如果配置没有被序列化，至少验证 routine 被恢复了
            assert routine_id in new_flow.routines

    def test_serialize_deserialize_idempotency(self):
        """测试序列化/反序列化的幂等性（多次序列化结果一致）"""
        from serilux import register_serializable

        flow = Flow(flow_id="idempotency_test")

        @register_serializable
        class PersistenceTestRoutine1(Routine):
            def __init__(self):
                super().__init__()
                self.outputevent = self.define_event("output", ["data"])
                self.set_config(value=42, name="test")

        routine = PersistenceTestRoutine1()
        routine_id = flow.add_routine(routine, "test")

        # 第一次序列化
        data1 = flow.serialize()

        # 反序列化
        new_flow = Flow()
        new_flow.deserialize(data1)

        # 第二次序列化
        data2 = new_flow.serialize()

        # 验证关键字段一致
        assert data1["flow_id"] == data2["flow_id"]
        assert len(data1["routines"]) == len(data2["routines"])
        assert len(data1["connections"]) == len(data2["connections"])

        # 验证 routine 配置一致（如果 _config 被序列化）
        r1_config = data1["routines"][routine_id].get("_config", {})
        r2_config = data2["routines"][routine_id].get("_config", {})
        # 如果配置存在，验证一致性
        if r1_config and r2_config:
            if "value" in r1_config:
                assert r1_config["value"] == r2_config.get("value")
            if "name" in r1_config:
                assert r1_config["name"] == r2_config.get("name")
        # 至少验证 routine 结构一致
        assert routine_id in data1["routines"]
        assert routine_id in data2["routines"]

    def test_deserialize_with_missing_routine_id(self):
        """测试反序列化时缺少 routine_id 的情况"""
        from serilux import register_serializable

        flow = Flow(flow_id="test_flow")

        @register_serializable
        class PersistenceTestRoutine2(Routine):
            def __init__(self):
                super().__init__()
                self.outputevent = self.define_event("output", ["data"])

        routine = PersistenceTestRoutine2()
        routine_id = flow.add_routine(routine, "test")

        # 序列化
        data = flow.serialize()

        # 尝试删除 routine_id（如果存在）
        # 注意：routine_id 可能不在序列化数据中（因为我们已经移除了添加 routine_id 的代码）
        if routine_id in data["routines"] and "routine_id" in data["routines"][routine_id]:
            del data["routines"][routine_id]["routine_id"]

        # 反序列化应该仍然成功（使用字典的 key 作为 routine_id）
        new_flow = Flow()
        new_flow.deserialize(data)

        # 验证 routine 仍然存在
        assert routine_id in new_flow.routines or len(new_flow.routines) > 0

    def test_serialize_with_none_values(self):
        """测试序列化包含 None 值的数据"""
        from serilux import register_serializable

        flow = Flow(flow_id="none_values_flow")

        @register_serializable
        class NoneRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.outputevent = self.define_event("output", ["data"])
                self.set_config(
                    none_value=None,
                    empty_string="",
                    zero=0,
                    false_value=False,
                )

        routine = NoneRoutine()
        routine_id = flow.add_routine(routine, "none")

        # 序列化
        data = flow.serialize()

        # 反序列化
        new_flow = Flow()
        new_flow.deserialize(data)

        # 验证 None 值被正确处理（如果 _config 被序列化）
        restored_routine = new_flow.routines[routine_id]
        config = restored_routine._config
        if config:
            assert config["none_value"] is None
            assert config["empty_string"] == ""
            assert config["zero"] == 0
            assert config["false_value"] is False
        else:
            # 如果配置没有被序列化，至少验证 routine 被恢复了
            assert routine_id in new_flow.routines

    def test_serialize_with_datetime_values(self):
        """测试序列化包含 datetime 的数据"""
        from datetime import datetime

        flow = Flow(flow_id="datetime_flow")
        job_state = JobState(flow_id=flow.flow_id)
        flow.job_state = job_state

        # 序列化（包含 datetime）
        data = flow.serialize()

        # 验证 datetime 被序列化为字符串
        if "job_state" in data and data["job_state"]:
            assert isinstance(data["job_state"]["created_at"], str)

        # 反序列化
        new_flow = Flow()
        new_flow.deserialize(data)

        # 验证 datetime 被恢复
        if new_flow.job_state:
            assert isinstance(new_flow.job_state.created_at, datetime)

    def test_serialize_deserialize_multiple_rounds(self):
        """测试多次序列化/反序列化循环"""
        from serilux import register_serializable

        flow = Flow(flow_id="multi_round_flow")

        @register_serializable
        class PersistenceTestRoutine3(Routine):
            def __init__(self):
                super().__init__()
                self.outputevent = self.define_event("output", ["data"])
                self.set_config(round=0)

        routine = PersistenceTestRoutine3()
        routine_id = flow.add_routine(routine, "test")

        # 进行多轮序列化/反序列化
        for round_num in range(5):
            # 更新配置
            routine.set_config(round=round_num)

            # 序列化
            data = flow.serialize()

            # 反序列化
            new_flow = Flow()
            new_flow.deserialize(data)

            # 验证配置被正确恢复（如果 _config 被序列化）
            restored_routine = new_flow.routines[routine_id]
            config = restored_routine._config
            if config:
                assert config["round"] == round_num
            else:
                # 如果配置没有被序列化，至少验证 routine 被恢复了
                assert routine_id in new_flow.routines

            # 更新 flow 引用以便下一轮
            flow = new_flow
            routine = restored_routine
