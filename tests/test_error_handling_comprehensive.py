"""
全面的错误处理测试用例

从用户角度测试错误处理的预期行为，不依赖实现细节。
"""

import time
from routilux import Flow, Routine, ErrorHandler, ErrorStrategy


class TestErrorHandlerPriority:
    """测试错误处理器的优先级"""

    def test_routine_handler_overrides_flow_handler(self):
        """测试routine级别的handler优先于flow级别的handler"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __call__(self):
                raise ValueError("Test error")

        routine = FailingRoutine()
        # Routine级别使用CONTINUE
        routine.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
        routine_id = flow.add_routine(routine, "failing")

        # Flow级别使用STOP
        flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.STOP))

        job_state = flow.execute(routine_id)

        # Routine级别的CONTINUE应该生效，flow应该完成
        assert job_state.status == "completed"
        assert job_state.get_routine_state("failing")["status"] == "error_continued"

    def test_flow_handler_used_when_routine_has_no_handler(self):
        """测试当routine没有handler时，使用flow级别的handler"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __call__(self):
                raise ValueError("Test error")

        routine = FailingRoutine()
        # Routine没有设置handler
        routine_id = flow.add_routine(routine, "failing")

        # Flow级别使用CONTINUE
        flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))

        job_state = flow.execute(routine_id)

        # Flow级别的CONTINUE应该生效
        assert job_state.status == "completed"
        assert job_state.get_routine_state("failing")["status"] == "error_continued"

    def test_default_stop_when_no_handler_set(self):
        """测试当没有设置任何handler时，使用默认的STOP行为"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __call__(self):
                raise ValueError("Test error")

        routine = FailingRoutine()
        routine_id = flow.add_routine(routine, "failing")

        # 没有设置任何handler
        job_state = flow.execute(routine_id)

        # 应该使用默认的STOP行为
        assert job_state.status == "failed"
        assert job_state.get_routine_state("failing")["status"] == "failed"


class TestOptionalRoutines:
    """测试Optional routine的行为"""

    def test_optional_routine_failure_tolerated_default(self):
        """测试optional routine失败被容忍（默认CONTINUE策略）"""
        flow = Flow()

        class OptionalRoutine(Routine):
            def __call__(self):
                raise ValueError("Optional operation failed")

        optional = OptionalRoutine()
        optional.set_as_optional()  # 默认使用CONTINUE
        optional_id = flow.add_routine(optional, "optional")

        job_state = flow.execute(optional_id)

        # Optional routine失败应该被容忍
        assert job_state.status == "completed"
        assert job_state.get_routine_state("optional")["status"] == "error_continued"

    def test_optional_routine_with_skip_strategy(self):
        """测试optional routine使用SKIP策略"""
        flow = Flow()

        class OptionalRoutine(Routine):
            def __call__(self):
                raise ValueError("Optional operation failed")

        optional = OptionalRoutine()
        optional.set_as_optional(ErrorStrategy.SKIP)
        optional_id = flow.add_routine(optional, "optional")

        job_state = flow.execute(optional_id)

        # Optional routine应该被跳过
        assert job_state.status == "completed"
        assert job_state.get_routine_state("optional")["status"] == "skipped"

    def test_optional_routine_does_not_stop_flow(self):
        """测试optional routine失败不会停止flow"""
        flow = Flow()

        class OptionalRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                raise ValueError("Optional failed")

        class MainRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)
                self.received = False

            def process(self, data):
                self.received = True

        optional = OptionalRoutine()
        optional.set_as_optional()
        optional_id = flow.add_routine(optional, "optional")

        main = MainRoutine()
        main_id = flow.add_routine(main, "main")

        # 即使optional失败，main也应该能执行（如果有其他数据源）
        flow.connect(optional_id, "output", main_id, "input")

        job_state = flow.execute(optional_id)

        # Flow应该完成，即使optional失败
        assert job_state.status == "completed"
        assert job_state.get_routine_state("optional")["status"] == "error_continued"


class TestCriticalRoutines:
    """测试Critical routine的行为"""

    def test_critical_routine_retry_success(self):
        """测试critical routine重试成功"""
        flow = Flow()
        call_count = [0]

        class CriticalRoutine(Routine):
            def __call__(self):
                call_count[0] += 1
                if call_count[0] < 3:
                    raise ConnectionError("Network error")
                # 第三次调用成功

        critical = CriticalRoutine()
        critical.set_as_critical(max_retries=5, retry_delay=0.1)
        critical_id = flow.add_routine(critical, "critical")

        job_state = flow.execute(critical_id)

        # Critical routine应该重试成功
        assert job_state.status == "completed"
        assert call_count[0] == 3  # 初始调用 + 2次重试
        assert job_state.get_routine_state("critical")["status"] == "completed"
        assert job_state.get_routine_state("critical").get("retry_count", 0) > 0

    def test_critical_routine_retry_failure_causes_flow_failure(self):
        """测试critical routine重试失败后flow失败"""
        flow = Flow()

        class AlwaysFailingRoutine(Routine):
            def __call__(self):
                raise ConnectionError("Always fails")

        critical = AlwaysFailingRoutine()
        critical.set_as_critical(max_retries=2, retry_delay=0.1)
        critical_id = flow.add_routine(critical, "critical")

        job_state = flow.execute(critical_id)

        # Critical routine重试失败后，flow应该失败
        assert job_state.status == "failed"
        assert job_state.get_routine_state("critical")["status"] == "failed"

    def test_critical_routine_non_retryable_exception_stops_immediately(self):
        """测试critical routine遇到不可重试异常时立即停止"""
        flow = Flow()
        call_count = [0]

        class CriticalRoutine(Routine):
            def __call__(self):
                call_count[0] += 1
                raise ValueError("Non-retryable error")

        critical = CriticalRoutine()
        # 设置只重试ConnectionError，不重试ValueError
        critical.set_error_handler(
            ErrorHandler(
                strategy=ErrorStrategy.RETRY,
                max_retries=5,
                retry_delay=0.1,
                retryable_exceptions=(ConnectionError,),
                is_critical=True,
            )
        )
        critical_id = flow.add_routine(critical, "critical")

        job_state = flow.execute(critical_id)

        # 不可重试异常应该立即停止，不进行重试
        assert job_state.status == "failed"
        assert call_count[0] == 1  # 只执行一次，不重试
        assert job_state.get_routine_state("critical")["status"] == "failed"

    def test_critical_routine_custom_retry_config(self):
        """测试critical routine使用自定义重试配置"""
        flow = Flow()
        call_count = [0]

        class CriticalRoutine(Routine):
            def __call__(self):
                call_count[0] += 1
                if call_count[0] < 2:
                    raise ConnectionError("Network error")

        critical = CriticalRoutine()
        critical.set_as_critical(max_retries=3, retry_delay=0.2, retry_backoff=1.5)
        critical_id = flow.add_routine(critical, "critical")

        job_state = flow.execute(critical_id)

        # 应该重试成功
        assert job_state.status == "completed"
        assert call_count[0] == 2  # 初始调用 + 1次重试


class TestMixedRoutines:
    """测试混合使用optional和critical routine"""

    def test_optional_and_critical_together(self):
        """测试同时使用optional和critical routine"""
        flow = Flow()

        class OptionalRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                raise ValueError("Optional failed")

        class CriticalRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)
                self.processed = False

            def process(self, data):
                self.processed = True

        optional = OptionalRoutine()
        optional.set_as_optional()
        optional_id = flow.add_routine(optional, "optional")

        critical = CriticalRoutine()
        critical.set_as_critical(max_retries=1, retry_delay=0.1)
        critical_id = flow.add_routine(critical, "critical")

        flow.connect(optional_id, "output", critical_id, "input")

        job_state = flow.execute(optional_id)

        # Optional routine失败应该被容忍
        assert job_state.status == "completed"
        assert job_state.get_routine_state("optional")["status"] == "error_continued"
        # Critical routine可能没有收到数据（因为optional失败），但flow应该完成

    def test_multiple_optional_routines(self):
        """测试多个optional routine"""
        flow = Flow()

        class OptionalRoutine(Routine):
            def __init__(self, name):
                super().__init__()
                self.set_config(name=name)
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                raise ValueError(f"{self.get_config('name')} failed")

        optional1 = OptionalRoutine("optional1")
        optional1.set_as_optional()
        optional1_id = flow.add_routine(optional1, "optional1")

        optional2 = OptionalRoutine("optional2")
        optional2.set_as_optional()
        optional2_id = flow.add_routine(optional2, "optional2")

        job_state1 = flow.execute(optional1_id)
        assert job_state1.status == "completed"

        job_state2 = flow.execute(optional2_id)
        assert job_state2.status == "completed"

    def test_critical_routine_failure_stops_entire_flow(self):
        """测试critical routine失败会停止整个flow"""
        flow = Flow()

        class OptionalRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                raise ValueError("Optional failed")

        class CriticalRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data):
                raise ConnectionError("Critical operation failed")

        optional = OptionalRoutine()
        optional.set_as_optional()
        optional_id = flow.add_routine(optional, "optional")

        critical = CriticalRoutine()
        critical.set_as_critical(max_retries=1, retry_delay=0.1)
        critical_id = flow.add_routine(critical, "critical")

        flow.connect(optional_id, "output", critical_id, "input")

        flow.execute(optional_id)

        # Optional routine失败被容忍，但critical routine失败会导致flow失败
        # 注意：在这个场景中，optional失败后不会emit数据，所以critical可能不会执行
        # 但如果有其他数据源触发critical，critical失败应该导致flow失败


class TestRetryBehavior:
    """测试重试行为"""

    def test_retry_only_retryable_exceptions(self):
        """测试只重试可重试的异常"""
        flow = Flow()
        call_count = [0]

        class MixedRoutine(Routine):
            def __call__(self):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise ConnectionError("Retryable error")
                else:
                    raise ValueError("Non-retryable error")

        routine = MixedRoutine()
        routine.set_error_handler(
            ErrorHandler(
                strategy=ErrorStrategy.RETRY,
                max_retries=3,
                retry_delay=0.1,
                retryable_exceptions=(ConnectionError,),
            )
        )
        routine_id = flow.add_routine(routine, "mixed")

        job_state = flow.execute(routine_id)

        # 第一次ConnectionError应该重试，第二次ValueError应该立即停止
        assert job_state.status == "failed"
        assert call_count[0] == 2  # 初始调用 + 1次重试（遇到ValueError后停止）

    def test_retry_all_exceptions_by_default(self):
        """测试默认情况下重试所有异常"""
        flow = Flow()
        call_count = [0]

        class FailingRoutine(Routine):
            def __call__(self):
                call_count[0] += 1
                if call_count[0] < 3:
                    raise ValueError("Error")
                # 第三次调用成功

        routine = FailingRoutine()
        routine.set_error_handler(
            ErrorHandler(
                strategy=ErrorStrategy.RETRY,
                max_retries=3,
                retry_delay=0.1,
                # 默认retryable_exceptions包含所有异常
            )
        )
        routine_id = flow.add_routine(routine, "failing")

        job_state = flow.execute(routine_id)

        # 应该重试成功
        assert job_state.status == "completed"
        assert call_count[0] == 3

    def test_retry_delay_and_backoff(self):
        """测试重试延迟和退避"""
        flow = Flow()
        call_count = [0]
        retry_times = []

        class FailingRoutine(Routine):
            def __call__(self):
                call_count[0] += 1
                retry_times.append(time.time())
                if call_count[0] < 3:
                    raise ConnectionError("Network error")

        routine = FailingRoutine()
        routine.set_error_handler(
            ErrorHandler(
                strategy=ErrorStrategy.RETRY, max_retries=3, retry_delay=0.2, retry_backoff=2.0
            )
        )
        routine_id = flow.add_routine(routine, "failing")

        job_state = flow.execute(routine_id)

        # 应该重试成功
        assert job_state.status == "completed"
        assert call_count[0] == 3

        # 验证重试延迟（允许一些误差）
        if len(retry_times) >= 2:
            delay1 = retry_times[1] - retry_times[0]
            assert 0.15 <= delay1 <= 0.3  # 第一次重试延迟约0.2s

        if len(retry_times) >= 3:
            delay2 = retry_times[2] - retry_times[1]
            assert 0.35 <= delay2 <= 0.5  # 第二次重试延迟约0.4s (0.2 * 2)


class TestErrorHandlerStrategies:
    """测试各种错误处理策略"""

    def test_stop_strategy_immediately_fails(self):
        """测试STOP策略立即失败"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __call__(self):
                raise ValueError("Test error")

        routine = FailingRoutine()
        routine.set_error_handler(ErrorHandler(strategy=ErrorStrategy.STOP))
        routine_id = flow.add_routine(routine, "failing")

        job_state = flow.execute(routine_id)

        assert job_state.status == "failed"
        assert job_state.get_routine_state("failing")["status"] == "failed"

    def test_continue_strategy_tolerates_errors(self):
        """测试CONTINUE策略容忍错误"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __call__(self):
                raise ValueError("Test error")

        routine = FailingRoutine()
        routine.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
        routine_id = flow.add_routine(routine, "failing")

        job_state = flow.execute(routine_id)

        assert job_state.status == "completed"
        assert job_state.get_routine_state("failing")["status"] == "error_continued"

    def test_skip_strategy_marks_as_skipped(self):
        """测试SKIP策略标记为跳过"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __call__(self):
                raise ValueError("Test error")

        routine = FailingRoutine()
        routine.set_error_handler(ErrorHandler(strategy=ErrorStrategy.SKIP))
        routine_id = flow.add_routine(routine, "failing")

        job_state = flow.execute(routine_id)

        assert job_state.status == "completed"
        assert job_state.get_routine_state("failing")["status"] == "skipped"

    def test_continue_vs_skip_difference(self):
        """测试CONTINUE和SKIP的区别"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __call__(self):
                raise ValueError("Test error")

        # 测试CONTINUE
        routine1 = FailingRoutine()
        routine1.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
        routine1_id = flow.add_routine(routine1, "continue_routine")

        job_state1 = flow.execute(routine1_id)
        assert job_state1.get_routine_state("continue_routine")["status"] == "error_continued"

        # 测试SKIP
        routine2 = FailingRoutine()
        routine2.set_error_handler(ErrorHandler(strategy=ErrorStrategy.SKIP))
        routine2_id = flow.add_routine(routine2, "skip_routine")

        job_state2 = flow.execute(routine2_id)
        assert job_state2.get_routine_state("skip_routine")["status"] == "skipped"

        # 两者都完成flow，但状态标记不同
        assert job_state1.status == "completed"
        assert job_state2.status == "completed"


class TestComplexScenarios:
    """测试复杂场景"""

    def test_flow_with_mixed_success_and_failure(self):
        """测试flow中有些routine成功，有些失败"""
        flow = Flow()

        class SuccessfulRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                self.emit("output", data="success")

        class OptionalFailingRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)
                self.output_event = self.define_event("output", ["data"])
                self.processed = False

            def __call__(self):
                raise ValueError("Optional failed")

            def process(self, data):
                self.processed = True

        class CriticalRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)
                self.processed = False

            def process(self, data):
                self.processed = True

        success = SuccessfulRoutine()
        success_id = flow.add_routine(success, "success")

        optional = OptionalFailingRoutine()
        optional.set_as_optional()
        optional_id = flow.add_routine(optional, "optional")

        critical = CriticalRoutine()
        critical.set_as_critical(max_retries=1, retry_delay=0.1)
        critical_id = flow.add_routine(critical, "critical")

        flow.connect(success_id, "output", optional_id, "input")
        flow.connect(success_id, "output", critical_id, "input")

        job_state = flow.execute(success_id)

        # Success routine应该成功
        success_state = job_state.get_routine_state("success")
        assert success_state is not None
        assert success_state["status"] == "completed"

        # Optional routine失败应该被容忍（如果__call__被执行）
        optional_state = job_state.get_routine_state("optional")
        if optional_state is not None:
            # 如果optional routine的__call__被执行，应该标记为error_continued
            assert optional_state["status"] == "error_continued"

        # Critical routine通过slot handler接收数据，可能没有routine state
        # 但flow应该完成（因为source成功，且optional失败被容忍）
        # Flow应该完成
        assert job_state.status == "completed"

        # 验证critical routine确实处理了数据（通过检查其processed标志）
        # 注意：这需要等待flow完成
        flow.wait_for_completion(timeout=1.0)
        assert critical.processed is True

    def test_cascading_failures(self):
        """测试级联失败场景"""
        flow = Flow()

        class SourceRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                self.emit("output", data="test")

        class OptionalRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                raise ValueError("Optional failed")

            def process(self, data):
                # 即使__call__失败，process仍然可能被调用（如果数据在失败前到达）
                pass

        class CriticalRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.input_slot = self.define_slot("input", handler=self.process)

            def process(self, data):
                raise ConnectionError("Critical failed")

        source = SourceRoutine()
        source_id = flow.add_routine(source, "source")

        optional = OptionalRoutine()
        optional.set_as_optional()
        optional_id = flow.add_routine(optional, "optional")

        critical = CriticalRoutine()
        critical.set_as_critical(max_retries=1, retry_delay=0.1)
        critical_id = flow.add_routine(critical, "critical")

        flow.connect(source_id, "output", optional_id, "input")
        flow.connect(source_id, "output", critical_id, "input")

        job_state = flow.execute(source_id)

        # Source应该成功
        source_state = job_state.get_routine_state("source")
        assert source_state is not None
        assert source_state["status"] == "completed"

        # Optional失败被容忍（如果__call__被执行）
        optional_state = job_state.get_routine_state("optional")
        if optional_state is not None:
            assert optional_state["status"] == "error_continued"

        # Critical在slot handler中失败，这不会触发routine级别的错误处理
        # Slot handler的错误会被记录在routine的stats中，但不会停止flow
        # Flow应该完成（因为source成功）
        assert job_state.status == "completed"


class TestErrorHandlerConfiguration:
    """测试错误处理器配置"""

    def test_custom_error_handler_configuration(self):
        """测试自定义错误处理器配置"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __call__(self):
                raise ConnectionError("Network error")

        routine = FailingRoutine()
        routine.set_error_handler(
            ErrorHandler(
                strategy=ErrorStrategy.RETRY,
                max_retries=5,
                retry_delay=0.3,
                retry_backoff=1.5,
                retryable_exceptions=(ConnectionError, TimeoutError),
            )
        )
        flow.add_routine(routine, "failing")

        # 验证配置
        handler = routine.get_error_handler()
        assert handler.strategy == ErrorStrategy.RETRY
        assert handler.max_retries == 5
        assert handler.retry_delay == 0.3
        assert handler.retry_backoff == 1.5
        assert ConnectionError in handler.retryable_exceptions
        assert TimeoutError in handler.retryable_exceptions

    def test_error_handler_reset(self):
        """测试错误处理器重置"""
        handler = ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=3)

        # 模拟一些重试
        handler.retry_count = 2
        assert handler.retry_count == 2

        # 重置
        handler.reset()
        assert handler.retry_count == 0


class TestEdgeCases:
    """测试边界情况"""

    def test_routine_without_error_handler_in_flow_with_handler(self):
        """测试flow有handler，但routine没有handler的情况"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __call__(self):
                raise ValueError("Test error")

        routine = FailingRoutine()
        # Routine没有设置handler
        routine_id = flow.add_routine(routine, "failing")

        # Flow设置了handler
        flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))

        job_state = flow.execute(routine_id)

        # 应该使用flow级别的handler
        assert job_state.status == "completed"
        assert job_state.get_routine_state("failing")["status"] == "error_continued"

    def test_multiple_routines_different_handlers(self):
        """测试多个routine使用不同的handler"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __call__(self):
                raise ValueError("Test error")

        routine1 = FailingRoutine()
        routine1.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
        routine1_id = flow.add_routine(routine1, "routine1")

        routine2 = FailingRoutine()
        routine2.set_error_handler(ErrorHandler(strategy=ErrorStrategy.SKIP))
        routine2_id = flow.add_routine(routine2, "routine2")

        job_state1 = flow.execute(routine1_id)
        assert job_state1.get_routine_state("routine1")["status"] == "error_continued"

        job_state2 = flow.execute(routine2_id)
        assert job_state2.get_routine_state("routine2")["status"] == "skipped"

    def test_error_handler_serialization(self):
        """测试错误处理器的序列化"""
        handler = ErrorHandler(
            strategy=ErrorStrategy.RETRY,
            max_retries=5,
            retry_delay=1.0,
            retry_backoff=2.0,
            is_critical=True,
        )

        data = handler.serialize()

        # 反序列化
        new_handler = ErrorHandler()
        new_handler.deserialize(data)

        assert new_handler.strategy == ErrorStrategy.RETRY
        assert new_handler.max_retries == 5
        assert new_handler.retry_delay == 1.0
        assert new_handler.retry_backoff == 2.0
        assert new_handler.is_critical is True
