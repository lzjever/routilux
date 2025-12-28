"""
ExecutionTracker 综合测试用例
"""

import time

from routilux import Flow, Routine, ExecutionTracker


class TestExecutionTrackerBasic:
    """ExecutionTracker 基本功能测试"""

    def test_create_tracker(self):
        """测试创建 ExecutionTracker"""
        tracker = ExecutionTracker(flow_id="test_flow")

        assert tracker.flow_id == "test_flow"
        assert tracker.routine_executions == {}
        assert tracker.event_flow == []
        assert tracker.performance_metrics == {}

    def test_record_routine_start(self):
        """测试记录 routine 开始"""
        tracker = ExecutionTracker(flow_id="test_flow")

        params = {"param1": "value1", "param2": 123}
        tracker.record_routine_start("routine1", params)

        assert "routine1" in tracker.routine_executions
        assert len(tracker.routine_executions["routine1"]) == 1

        execution = tracker.routine_executions["routine1"][0]
        assert execution["routine_id"] == "routine1"
        assert execution["status"] == "running"
        assert execution["params"] == params
        assert "start_time" in execution

    def test_record_routine_end(self):
        """测试记录 routine 结束"""
        tracker = ExecutionTracker(flow_id="test_flow")

        # 先记录开始
        tracker.record_routine_start("routine1")

        # 等待一小段时间以计算执行时间
        time.sleep(0.01)

        # 记录结束
        tracker.record_routine_end("routine1", status="completed", result="success")

        execution = tracker.routine_executions["routine1"][0]
        assert execution["status"] == "completed"
        assert execution["result"] == "success"
        assert "end_time" in execution
        assert "execution_time" in execution
        assert execution["execution_time"] > 0

    def test_record_routine_end_with_error(self):
        """测试记录 routine 结束（带错误）"""
        tracker = ExecutionTracker(flow_id="test_flow")

        tracker.record_routine_start("routine1")
        tracker.record_routine_end("routine1", status="failed", error="Test error")

        execution = tracker.routine_executions["routine1"][0]
        assert execution["status"] == "failed"
        assert execution["error"] == "Test error"

    def test_record_routine_end_without_start(self):
        """测试在没有开始记录时记录结束"""
        tracker = ExecutionTracker(flow_id="test_flow")

        # 直接记录结束，应该被忽略
        tracker.record_routine_end("routine1", status="completed")

        assert "routine1" not in tracker.routine_executions


class TestExecutionTrackerEventFlow:
    """ExecutionTracker 事件流测试"""

    def test_record_event(self):
        """测试记录事件"""
        tracker = ExecutionTracker(flow_id="test_flow")

        data = {"key": "value"}
        tracker.record_event("routine1", "output", "routine", data)

        assert len(tracker.event_flow) == 1

        event = tracker.event_flow[0]
        assert event["source_routine_id"] == "routine1"
        assert event["event_name"] == "output"
        assert event["target_routine_id"] == "routine"
        assert event["data"] == data
        assert "timestamp" in event

    def test_record_event_without_target(self):
        """测试记录没有目标的事件"""
        tracker = ExecutionTracker(flow_id="test_flow")

        tracker.record_event("routine1", "output", None, {})

        event = tracker.event_flow[0]
        assert event["target_routine_id"] is None


class TestExecutionTrackerPerformance:
    """ExecutionTracker 性能指标测试"""

    def test_get_routine_performance(self):
        """测试获取 routine 性能指标"""
        tracker = ExecutionTracker(flow_id="test_flow")

        # 记录多次执行
        for i in range(3):
            tracker.record_routine_start("routine1")
            time.sleep(0.01)
            tracker.record_routine_end("routine1", status="completed")

        # 记录一次失败
        tracker.record_routine_start("routine1")
        tracker.record_routine_end("routine1", status="failed")

        perf = tracker.get_routine_performance("routine1")

        assert perf is not None
        assert perf["total_executions"] == 4
        assert perf["completed"] == 3
        assert perf["failed"] == 1
        assert perf["success_rate"] == 0.75
        assert perf["avg_execution_time"] > 0
        assert perf["min_execution_time"] > 0
        assert perf["max_execution_time"] > 0

    def test_get_routine_performance_nonexistent(self):
        """测试获取不存在的 routine 性能指标"""
        tracker = ExecutionTracker(flow_id="test_flow")

        perf = tracker.get_routine_performance("nonexistent")

        assert perf is None

    def test_get_flow_performance(self):
        """测试获取 flow 性能指标"""
        tracker = ExecutionTracker(flow_id="test_flow")

        # 记录多个 routine 的执行
        tracker.record_routine_start("routine1")
        tracker.record_routine_end("routine1", status="completed")

        tracker.record_routine_start("routine")
        tracker.record_routine_end("routine", status="completed")

        # 记录事件
        tracker.record_event("routine1", "output", "routine", {})

        flow_perf = tracker.get_flow_performance()

        assert flow_perf["total_routines"] == 2
        assert flow_perf["total_events"] == 1
        assert flow_perf["total_execution_time"] > 0
        assert flow_perf["avg_routine_time"] > 0

    def test_get_flow_performance_empty(self):
        """测试获取空 flow 的性能指标"""
        tracker = ExecutionTracker(flow_id="test_flow")

        flow_perf = tracker.get_flow_performance()

        assert flow_perf["total_routines"] == 0
        assert flow_perf["total_events"] == 0
        assert flow_perf["total_execution_time"] == 0
        assert flow_perf["avg_routine_time"] == 0


class TestExecutionTrackerIntegration:
    """ExecutionTracker 集成测试"""

    def test_tracker_with_flow_execution(self):
        """测试 tracker 与 flow 执行的集成"""
        flow = Flow(flow_id="test_flow")

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

            def process(self, data):
                pass

        a = RoutineA()
        b = RoutineB()

        id_a = flow.add_routine(a, "A")
        id_b = flow.add_routine(b, "B")

        flow.connect(id_a, "output", id_b, "input")

        # 执行
        flow.execute(id_a)

        # 验证 tracker 被创建和使用
        assert flow.execution_tracker is not None
        assert flow.execution_tracker.flow_id == "test_flow"
        assert len(flow.execution_tracker.routine_executions) > 0
        assert len(flow.execution_tracker.event_flow) > 0


class TestExecutionTrackerSerialization:
    """ExecutionTracker 序列化测试"""

    def test_tracker_serialize(self):
        """测试 tracker 序列化"""
        tracker = ExecutionTracker(flow_id="test_flow")

        tracker.record_routine_start("routine1")
        tracker.record_routine_end("routine1", status="completed")
        tracker.record_event("routine1", "output", "routine", {})

        data = tracker.serialize()

        assert data["_type"] == "ExecutionTracker"
        assert data["flow_id"] == "test_flow"
        assert "routine1" in data["routine_executions"]
        assert len(data["event_flow"]) == 1

    def test_tracker_deserialize(self):
        """测试 tracker 反序列化"""
        data = {
            "_type": "ExecutionTracker",
            "flow_id": "test_flow",
            "routine_executions": {
                "routine1": [
                    {
                        "routine_id": "routine1",
                        "start_time": "2024-01-01T00:00:00",
                        "end_time": "2024-01-01T00:00:01",
                        "status": "completed",
                        "execution_time": 1.0,
                    }
                ]
            },
            "event_flow": [
                {
                    "timestamp": "2024-01-01T00:00:00",
                    "source_routine_id": "routine1",
                    "event_name": "output",
                    "target_routine_id": "routine",
                    "data": {},
                }
            ],
            "performance_metrics": {},
        }

        tracker = ExecutionTracker()
        tracker.deserialize(data)

        assert tracker.flow_id == "test_flow"
        assert "routine1" in tracker.routine_executions
        assert len(tracker.event_flow) == 1
