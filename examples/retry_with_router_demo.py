#!/usr/bin/env python
"""
演示：使用 ConditionalRouter 实现 retry 功能

这个示例展示了如何通过 Flow 的连接和 ConditionalRouter 来实现重试逻辑，
而不是使用 RetryHandler 包装 callable。

设计思路：
1. 业务 Routine (R1) 有自己的业务逻辑，可能成功或失败
2. R1 成功 -> 发送到 success 事件
3. R1 失败 -> 发送到 failure 事件（包含 retry_count）
4. ConditionalRouter 接收 R1 的结果：
   - 如果成功 -> 透传给下游
   - 如果失败且 retry_count < max_retries -> 发送 retry 事件回 R1
   - 如果失败且 retry_count >= max_retries -> 发送 final_failure 事件
"""
from typing import Any
from routilux import Flow, Routine
import time


class BusinessRoutine(Routine):
    """业务逻辑 Routine（模拟可能失败的业务操作）"""

    def __init__(self):
        super().__init__()
        self.input_slot = self.define_slot("input", handler=self._handle_input)
        self.success_event = self.define_event("success", ["result", "data", "retry_count"])
        self.failure_event = self.define_event("failure", ["error", "data", "retry_count"])

    def _handle_input(self, data: Any = None, retry_count: int = 0, **kwargs):
        """处理业务逻辑（可能失败）"""
        # 提取数据
        if data is None:
            data = kwargs.get("data")

        retry_count = kwargs.get("retry_count", retry_count)

        # 模拟业务逻辑：前2次失败，第3次成功
        try:
            if retry_count < 2:
                raise ValueError(f"Temporary failure (attempt {retry_count + 1})")

            # 成功
            result = f"Successfully processed: {data} (after {retry_count + 1} attempts)"
            print(f"  [BusinessRoutine] Success: {result}")
            self.emit("success", result=result, data=data, retry_count=retry_count)
        except Exception as e:
            # 失败
            error_msg = str(e)
            print(f"  [BusinessRoutine] Failure: {error_msg} (attempt {retry_count + 1})")
            self.emit("failure", error=error_msg, data=data, retry_count=retry_count)


class RetryRouter(Routine):
    """重试路由器（使用 ConditionalRouter 模式）"""

    def __init__(self, max_retries: int = 3):
        super().__init__()
        self.set_config(max_retries=max_retries)

        # 输入：接收业务 routine 的结果（成功或失败）
        self.input_slot = self.define_slot("input", handler=self._handle_input)

        # 输出事件
        self.retry_event = self.define_event("retry", ["data", "retry_count"])
        self.final_success_event = self.define_event(
            "final_success", ["result", "data", "total_attempts"]
        )
        self.final_failure_event = self.define_event(
            "final_failure", ["error", "data", "total_attempts"]
        )

    def _handle_input(
        self,
        result: Any = None,
        error: str = None,
        data: Any = None,
        retry_count: int = 0,
        **kwargs,
    ):
        """处理输入，判断是成功还是失败，决定是否重试"""
        # 提取数据
        result = kwargs.get("result", result)
        error = kwargs.get("error", error)
        data = kwargs.get("data", data)
        retry_count = kwargs.get("retry_count", retry_count)

        max_retries = self.get_config("max_retries", 3)

        # 判断：成功还是失败
        if result and not error:
            # 成功：透传给下游
            total_attempts = retry_count + 1
            print(
                f"  [RetryRouter] Success after {total_attempts} attempts, forwarding to downstream"
            )
            self.emit("final_success", result=result, data=data, total_attempts=total_attempts)
        elif error:
            # 失败：判断是否需要重试
            if retry_count < max_retries:
                # 需要重试：发送 retry 事件回业务 routine
                next_retry_count = retry_count + 1
                print(f"  [RetryRouter] Retrying (attempt {next_retry_count}/{max_retries})...")
                time.sleep(0.1)  # 模拟延迟
                self.emit("retry", data=data, retry_count=next_retry_count)
            else:
                # 超过最大重试次数：发送最终失败
                total_attempts = retry_count + 1
                print(
                    f"  [RetryRouter] Max retries ({max_retries}) exceeded, sending final failure"
                )
                self.emit("final_failure", error=error, data=data, total_attempts=total_attempts)


class ResultCollector(Routine):
    """结果收集器（用于演示）"""

    def __init__(self):
        super().__init__()
        self.success_results = []
        self.failure_results = []
        self.input_slot = self.define_slot("input", handler=self._handle_input)

    def _handle_input(self, result: Any = None, error: str = None, **kwargs):
        """收集结果"""
        if result:
            self.success_results.append({"result": result, **kwargs})
            print(f"  [ResultCollector] Received success: {result}")
        if error:
            self.failure_results.append({"error": error, **kwargs})
            print(f"  [ResultCollector] Received failure: {error}")


def demo_retry_with_router():
    """演示：使用 ConditionalRouter 模式实现 retry"""
    print("=" * 70)
    print("演示：使用 ConditionalRouter 模式实现 retry")
    print("=" * 70)
    print()

    flow = Flow(flow_id="retry_demo")

    # 创建 routines
    business = BusinessRoutine()
    retry_router = RetryRouter(max_retries=3)
    collector = ResultCollector()

    # 添加到 flow
    business_id = flow.add_routine(business, "business")
    router_id = flow.add_routine(retry_router, "retry_router")
    collector_id = flow.add_routine(collector, "collector")

    # 设置 flow 上下文（这样 emit 才能通过 Connection 传递）
    for routine in flow.routines.values():
        routine._current_flow = flow

    # 连接：
    # 1. business.success -> retry_router.input (成功路径)
    # 2. business.failure -> retry_router.input (失败路径)
    # 3. retry_router.retry -> business.input (重试路径)
    # 4. retry_router.final_success -> collector.input (最终成功)
    # 5. retry_router.final_failure -> collector.input (最终失败)

    flow.connect(business_id, "success", router_id, "input")
    flow.connect(business_id, "failure", router_id, "input")
    flow.connect(router_id, "retry", business_id, "input")
    flow.connect(router_id, "final_success", collector_id, "input")
    flow.connect(router_id, "final_failure", collector_id, "input")

    # 执行：发送初始数据
    print("执行：发送初始数据 'test_data'...")
    print()

    # 直接调用 business routine 的 input slot
    business.input_slot.receive({"data": "test_data", "retry_count": 0})

    # 等待处理（重试可能需要一些时间）
    time.sleep(2.0)

    print()
    print("=" * 70)
    print("结果统计:")
    print("=" * 70)
    print(f"  成功结果数: {len(collector.success_results)}")
    print(f"  失败结果数: {len(collector.failure_results)}")

    if collector.success_results:
        print("\n  成功详情:")
        for i, result in enumerate(collector.success_results, 1):
            print(f"    {i}. {result}")

    if collector.failure_results:
        print("\n  失败详情:")
        for i, result in enumerate(collector.failure_results, 1):
            print(f"    {i}. {result}")


def demo_max_retries_exceeded():
    """演示：超过最大重试次数的情况"""
    print("\n" + "=" * 70)
    print("演示：超过最大重试次数的情况")
    print("=" * 70)
    print()

    # 创建一个总是失败的 BusinessRoutine
    class AlwaysFailingRoutine(Routine):
        def __init__(self):
            super().__init__()
            self.input_slot = self.define_slot("input", handler=self._handle_input)
            self.success_event = self.define_event("success", ["result", "data", "retry_count"])
            self.failure_event = self.define_event("failure", ["error", "data", "retry_count"])

        def _handle_input(self, data: Any = None, retry_count: int = 0, **kwargs):
            data = kwargs.get("data", data)
            retry_count = kwargs.get("retry_count", retry_count)

            # 总是失败
            error_msg = f"Always fails (attempt {retry_count + 1})"
            print(f"  [AlwaysFailingRoutine] Failure: {error_msg}")
            self.emit("failure", error=error_msg, data=data, retry_count=retry_count)

    flow = Flow(flow_id="retry_demo_max")

    business = AlwaysFailingRoutine()
    retry_router = RetryRouter(max_retries=2)  # 只允许2次重试
    collector = ResultCollector()

    business_id = flow.add_routine(business, "business")
    router_id = flow.add_routine(retry_router, "retry_router")
    collector_id = flow.add_routine(collector, "collector")

    # 设置 flow 上下文
    for routine in flow.routines.values():
        routine._current_flow = flow

    flow.connect(business_id, "success", router_id, "input")
    flow.connect(business_id, "failure", router_id, "input")
    flow.connect(router_id, "retry", business_id, "input")
    flow.connect(router_id, "final_success", collector_id, "input")
    flow.connect(router_id, "final_failure", collector_id, "input")

    print("执行：发送初始数据 'test_data'（将超过最大重试次数）...")
    print()

    # 直接调用 business routine 的 input slot
    business.input_slot.receive({"data": "test_data", "retry_count": 0})

    time.sleep(2.0)

    print()
    print("=" * 70)
    print("结果统计:")
    print("=" * 70)
    print(f"  成功结果数: {len(collector.success_results)}")
    print(f"  失败结果数: {len(collector.failure_results)}")

    if collector.failure_results:
        print("\n  最终失败详情:")
        for i, result in enumerate(collector.failure_results, 1):
            print(f"    {i}. {result}")


if __name__ == "__main__":
    demo_retry_with_router()
    demo_max_retries_exceeded()
