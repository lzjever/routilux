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
        # 创建 flow
        flow1 = Flow(flow_id="test_flow")

        class TestRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

        routine = TestRoutine()
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
