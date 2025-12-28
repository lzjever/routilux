"""
JobState 测试用例
"""

from datetime import datetime

from routilux import JobState


class TestJobStateManagement:
    """JobState 状态管理测试"""

    def test_create_job_state(self):
        """测试用例 1: 创建 JobState"""
        job_state = JobState(flow_id="test_flow")

        assert job_state.flow_id == "test_flow"
        assert job_state.job_id is not None
        assert job_state.status == "pending"
        assert isinstance(job_state.created_at, datetime)
        assert isinstance(job_state.updated_at, datetime)

    def test_update_status(self):
        """测试用例 2: 更新状态"""
        job_state = JobState(flow_id="test_flow")

        # 更新状态
        job_state.status = "running"

        # 验证状态更新
        assert job_state.status == "running"

    def test_update_routine_state(self):
        """测试用例 3: 更新 Routine 状态"""
        job_state = JobState(flow_id="test_flow")

        # 更新 routine 状态
        routine_state = {"status": "completed", "stats": {"count": 1}, "last_event": "success"}
        job_state.update_routine_state("routine1", routine_state)

        # 验证状态保存
        assert "routine1" in job_state.routine_states
        assert job_state.routine_states["routine1"]["status"] == "completed"
        assert job_state.routine_states["routine1"]["stats"]["count"] == 1

    def test_record_execution(self):
        """测试用例 4: 记录执行历史"""
        job_state = JobState(flow_id="test_flow")

        # 记录执行
        job_state.record_execution(
            routine_id="routine1", event_name="output", data={"result": "test"}
        )

        # 验证历史记录
        assert len(job_state.execution_history) == 1
        record = job_state.execution_history[0]
        assert record.routine_id == "routine1"
        assert record.event_name == "output"
        assert record.data == {"result": "test"}
        assert isinstance(record.timestamp, datetime)


class TestJobStateQuery:
    """JobState 状态查询测试"""

    def test_get_routine_state(self):
        """测试用例 5: 查询 Routine 状态"""
        job_state = JobState(flow_id="test_flow")

        # 设置 routine 状态
        job_state.update_routine_state("routine1", {"status": "completed"})

        # 查询状态
        state = job_state.get_routine_state("routine1")
        assert state is not None
        assert state["status"] == "completed"

        # 查询不存在的 routine
        state = job_state.get_routine_state("nonexistent")
        assert state is None

    def test_get_execution_history(self):
        """测试用例 6: 查询执行历史"""
        job_state = JobState(flow_id="test_flow")

        # 记录多条历史
        job_state.record_execution("routine1", "event1", {"data": 1})
        job_state.record_execution("routine", "event2", {"data": 2})
        job_state.record_execution("routine1", "event3", {"data": 3})

        # 查询所有历史
        history = job_state.get_execution_history()
        assert len(history) == 3

        # 验证历史按时间排序
        timestamps = [r.timestamp for r in history]
        assert timestamps == sorted(timestamps)

        # 查询特定 routine 的历史
        routine1_history = job_state.get_execution_history(routine_id="routine1")
        assert len(routine1_history) == 2


class TestJobStateStatus:
    """JobState 状态转换测试"""

    def test_status_transitions(self):
        """测试状态转换"""
        job_state = JobState(flow_id="test_flow")

        # 初始状态
        assert job_state.status == "pending"

        # 状态转换
        job_state.status = "running"
        assert job_state.status == "running"

        job_state.status = "completed"
        assert job_state.status == "completed"

    def test_current_routine_tracking(self):
        """测试当前 routine 跟踪"""
        job_state = JobState(flow_id="test_flow")

        # 设置当前 routine
        job_state.current_routine_id = "routine1"
        assert job_state.current_routine_id == "routine1"

        # 更新当前 routine
        job_state.current_routine_id = "routine"
        assert job_state.current_routine_id == "routine"
