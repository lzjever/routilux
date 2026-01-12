"""
并发执行测试运行脚本

在没有 pytest 的情况下，可以运行此脚本来验证并发执行功能。

注意：此脚本需要 routilux 包已安装。
安装方法：pip install -e .
"""

import sys
import threading
import time

# Try to import routilux - if it fails, provide helpful error message
try:
    from routilux import Flow, Routine
except ImportError:
    print("Error: routilux package not found!")
    print("Please install the package first:")
    print("  pip install -e .")
    print("\nOr if you're in development mode:")
    print("  pip install -e '.[dev]'")
    sys.exit(1)


def test_basic_concurrent_execution():
    """测试基本并发执行"""
    print("\n=== 测试 1: 基本并发执行 ===")

    flow = Flow(execution_strategy="concurrent", max_workers=5)
    execution_order = []
    execution_lock = threading.Lock()

    class SourceRoutine(Routine):
        def __init__(self):
            super().__init__()
            self.output_event = self.define_event("output", ["data"])

        def __call__(self):
            time.sleep(0.1)
            self.emit("output", data="test_data", flow=flow)

    class TargetRoutine1(Routine):
        def __init__(self):
            super().__init__()
            self.input_slot = self.define_slot("input", handler=self.process)

        def process(self, data):
            time.sleep(0.2)
            with execution_lock:
                execution_order.append("routine1")

    class TargetRoutine2(Routine):
        def __init__(self):
            super().__init__()
            self.input_slot = self.define_slot("input", handler=self.process)

        def process(self, data):
            time.sleep(0.2)
            with execution_lock:
                execution_order.append("routine2")

    source = SourceRoutine()
    target1 = TargetRoutine1()
    target2 = TargetRoutine2()

    source_id = flow.add_routine(source, "source")
    target1_id = flow.add_routine(target1, "target1")
    target2_id = flow.add_routine(target2, "target2")

    flow.connect(source_id, "output", target1_id, "input")
    flow.connect(source_id, "output", target2_id, "input")

    start_time = time.time()
    job_state = flow.execute(source_id)
    execution_time = time.time() - start_time

    # 等待所有并发任务完成
    flow.wait_for_completion(timeout=2.0)

    assert execution_time < 0.4, f"执行时间 {execution_time:.3f} 应该小于 0.4 秒"
    assert len(execution_order) == 2, f"应该有 2 个 routines 执行，实际 {len(execution_order)}"
    assert job_state.status == "completed"

    print(f"✓ 执行时间: {execution_time:.3f} 秒")
    print(f"✓ 执行顺序: {execution_order}")
    print("✓ 测试通过")


def test_strategy_switching():
    """测试策略切换"""
    print("\n=== 测试 2: 策略切换 ===")

    flow = Flow()
    assert flow.execution_strategy == "sequential"

    flow.set_execution_strategy("concurrent", max_workers=10)
    assert flow.execution_strategy == "concurrent"
    assert flow.max_workers == 10

    flow.set_execution_strategy("sequential")
    assert flow.execution_strategy == "sequential"

    print("✓ 策略切换测试通过")


def test_serialization():
    """测试序列化/反序列化"""
    print("\n=== 测试 3: 序列化/反序列化 ===")

    flow = Flow(execution_strategy="concurrent", max_workers=8)

    class TestRoutine(Routine):
        def __init__(self):
            super().__init__()
            self.output_event = self.define_event("output", ["data"])

    routine = TestRoutine()
    flow.add_routine(routine, "test")

    # 序列化
    data = flow.serialize()
    assert data["execution_strategy"] == "concurrent"
    assert data["max_workers"] == 8

    # 反序列化
    new_flow = Flow()
    new_flow.deserialize(data)
    assert new_flow.execution_strategy == "concurrent"
    assert new_flow.max_workers == 8

    print("✓ 序列化/反序列化测试通过")


def test_dependency_graph():
    """测试依赖图构建"""
    print("\n=== 测试 4: 依赖图构建 ===")

    flow = Flow(execution_strategy="concurrent")

    class R1(Routine):
        def __init__(self):
            super().__init__()
            self.output_event = self.define_event("output", ["data"])

    class R2(Routine):
        def __init__(self):
            super().__init__()
            self.input_slot = self.define_slot("input", handler=lambda x: None)

    r1 = R1()
    r2 = R2()

    r1_id = flow.add_routine(r1, "r1")
    r2_id = flow.add_routine(r2, "r2")

    flow.connect(r1_id, "output", r2_id, "input")

    graph = flow._build_dependency_graph()
    assert r1_id in graph[r2_id]
    assert len(graph[r1_id]) == 0

    print("✓ 依赖图构建测试通过")


def test_thread_safety():
    """测试线程安全"""
    print("\n=== 测试 5: 线程安全 ===")

    flow = Flow(execution_strategy="concurrent", max_workers=10)
    counter = {"value": 0}
    counter_lock = threading.Lock()

    class CounterRoutine(Routine):
        def __init__(self):
            super().__init__()
            self.input_slot = self.define_slot("input", handler=self.process)

        def process(self, data):
            self._stats["count"] = self._stats.get("count", 0) + 1
            with counter_lock:
                counter["value"] += 1

    class SourceRoutine(Routine):
        def __init__(self):
            super().__init__()
            self.output_event = self.define_event("output", ["data"])

        def __call__(self):
            for i in range(20):
                self.emit("output", data=i, flow=flow)

    source = SourceRoutine()
    counter_routine = CounterRoutine()

    source_id = flow.add_routine(source, "source")
    counter_id = flow.add_routine(counter_routine, "counter")

    flow.connect(source_id, "output", counter_id, "input")

    job_state = flow.execute(source_id)

    # 等待所有并发任务完成
    flow.wait_for_completion(timeout=5.0)

    assert counter["value"] == 20, f"Expected 20 messages processed, got {counter['value']}"
    assert job_state.status == "completed"

    print(f"✓ 计数器值: {counter['value']}")
    print("✓ 线程安全测试通过")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("并发执行功能测试")
    print("=" * 60)

    tests = [
        test_basic_concurrent_execution,
        test_strategy_switching,
        test_serialization,
        test_dependency_graph,
        test_thread_safety,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"\n✗ 测试失败: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
