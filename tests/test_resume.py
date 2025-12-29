"""
恢复功能测试用例
"""

import json

import pytest
from routilux import Flow, Routine, JobState


class TestBasicResume:
    """基本恢复测试"""

    def test_resume_from_middle_state(self, temp_file):
        """测试用例 1: 从中间状态恢复"""
        flow = Flow()

        class RoutineA(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                self.emit("output", data="A")

        class RoutineB(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)
                self.output_event = self.define_event("output", ["data"])

            def process(self, data):
                self._stats["processed"] = True
                self.emit("output", data="B")

        class RoutineC(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data):
                pass

        a = RoutineA()
        b = RoutineB()
        c = RoutineC()

        id_a = flow.add_routine(a, "A")
        id_b = flow.add_routine(b, "B")
        id_c = flow.add_routine(c, "C")

        flow.connect(id_a, "output", id_b, "input")
        flow.connect(id_b, "output", id_c, "input")

        # 执行
        job_state = flow.execute(id_a)

        # 序列化状态
        data = job_state.serialize()
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # 加载并反序列化状态
        with open(temp_file, "r", encoding="utf-8") as f:
            loaded_data = json.load(f)
        job_state2 = JobState()
        job_state2.deserialize(loaded_data)

        # 验证状态恢复
        assert job_state2.flow_id == job_state.flow_id
        assert job_state2.status == job_state.status

    def test_resume_from_completed_state(self, temp_file):
        """测试用例 2: 从完成状态恢复"""
        flow = Flow()

        class SimpleRoutine(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)

            def _handle_trigger(self, **kwargs):
                pass

        routine = SimpleRoutine()
        routine_id = flow.add_routine(routine, "simple")

        # 执行完整流程
        job_state = flow.execute(routine_id)
        assert job_state.status == "completed"

        # 序列化状态
        data = job_state.serialize()
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # 加载并反序列化
        with open(temp_file, "r", encoding="utf-8") as f:
            loaded_data = json.load(f)
        job_state2 = JobState()
        job_state2.deserialize(loaded_data)

        # 验证恢复后的状态
        assert job_state2.status == "completed"
        assert job_state2.flow_id == job_state.flow_id

    def test_resume_from_error_state(self, temp_file):
        """测试用例 3: 从错误状态恢复"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)

            def _handle_trigger(self, **kwargs):
                raise ValueError("Test error")

        routine = FailingRoutine()
        routine_id = flow.add_routine(routine, "failing")

        # 执行流程遇到错误
        job_state = flow.execute(routine_id)
        assert job_state.status == "failed"

        # 序列化状态
        data = job_state.serialize()
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # 加载并反序列化
        with open(temp_file, "r", encoding="utf-8") as f:
            loaded_data = json.load(f)
        job_state2 = JobState()
        job_state2.deserialize(loaded_data)

        # 验证可以恢复错误状态
        assert job_state2.status == "failed"


class TestResumeConsistency:
    """恢复一致性测试"""

    def test_resume_consistency(self, temp_file):
        """测试用例 4: 恢复后状态一致性"""
        flow = Flow()

        class SimpleRoutine(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)

            def _handle_trigger(self, **kwargs):
                pass

        routine = SimpleRoutine()
        routine_id = flow.add_routine(routine, "simple")

        # 执行完整流程
        job_state1 = flow.execute(routine_id)

        # 序列化并保存
        data = job_state1.serialize()
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # 加载并反序列化
        with open(temp_file, "r", encoding="utf-8") as f:
            loaded_data = json.load(f)
        job_state2 = JobState()
        job_state2.deserialize(loaded_data)

        # 验证状态一致性
        assert job_state2.flow_id == job_state1.flow_id
        assert job_state2.status == job_state1.status
        assert job_state2.current_routine_id == job_state1.current_routine_id
        assert len(job_state2.routine_states) == len(job_state1.routine_states)
        assert len(job_state2.execution_history) == len(job_state1.execution_history)

    def test_partial_execution_resume(self, temp_file):
        """测试用例 5: 部分执行恢复"""
        flow = Flow()

        class RoutineA(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, **kwargs):
                self.emit("output", data="A")

        class RoutineB(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)
                self.output_event = self.define_event("output", ["data"])

            def process(self, data):
                self.emit("output", data="B")

        class RoutineC(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)
                self.executed = False

            def process(self, data):
                self.executed = True

        a = RoutineA()
        b = RoutineB()
        c = RoutineC()

        id_a = flow.add_routine(a, "A")
        id_b = flow.add_routine(b, "B")
        id_c = flow.add_routine(c, "C")

        flow.connect(id_a, "output", id_b, "input")
        flow.connect(id_b, "output", id_c, "input")

        # 执行
        job_state = flow.execute(id_a)

        # 序列化状态
        data = job_state.serialize()
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # 恢复并继续执行
        flow2 = Flow(flow_id=flow.flow_id)
        flow2.add_routine(a, "A")
        flow2.add_routine(b, "B")
        flow2.add_routine(c, "C")
        flow2.connect("A", "output", "B", "input")
        flow2.connect("B", "output", "C", "input")

        # 加载并反序列化
        with open(temp_file, "r", encoding="utf-8") as f:
            loaded_data = json.load(f)
        job_state2 = JobState()
        job_state2.deserialize(loaded_data)

        # 恢复执行
        flow2.resume(job_state2)

        # 验证 C 被执行
        assert c.executed is True


class TestResumeEdgeCases:
    """恢复边界情况测试"""

    def test_resume_with_missing_routine(self, temp_file):
        """测试恢复时缺少 routine"""
        # 创建并序列化 job_state
        job_state = JobState(flow_id="test_flow")
        job_state.current_routine_id = "missing_routine"
        data = job_state.serialize()
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # 加载到不包含该 routine 的 flow
        flow = Flow(flow_id="test_flow")
        with open(temp_file, "r", encoding="utf-8") as f:
            loaded_data = json.load(f)
        job_state2 = JobState()
        job_state2.deserialize(loaded_data)

        # 尝试恢复应该报错
        with pytest.raises(ValueError):
            flow.resume(job_state2)

    def test_resume_with_invalid_state(self, temp_file):
        """测试恢复无效状态"""
        # 创建无效的 job_state
        job_state = JobState(flow_id="test_flow")
        job_state.status = "invalid_status"
        data = job_state.serialize()
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        with open(temp_file, "r", encoding="utf-8") as f:
            loaded_data = json.load(f)
        job_state2 = JobState()
        job_state2.deserialize(loaded_data)

        # 尝试恢复应该处理或报错
        # 这里测试是否能正常加载，即使状态无效
        assert job_state2.status == "invalid_status"
