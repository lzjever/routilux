"""
测试 Routine 级别的错误处理功能

测试包括：
- Routine 级别的 error_handler
- Critical/Optional routine 标记
- 优先级：routine-level > flow-level > default
"""

from routilux import Flow, Routine, ErrorHandler, ErrorStrategy


class TestRoutineLevelErrorHandler:
    """测试 Routine 级别的错误处理"""

    def test_routine_error_handler_takes_priority(self):
        """测试 routine 级别的 error_handler 优先于 flow 级别的"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __call__(self):
                raise ValueError("Test error")

        routine = FailingRoutine()
        # Routine 级别使用 CONTINUE
        routine.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))
        routine_id = flow.add_routine(routine, "failing")

        # Flow 级别使用 STOP
        flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.STOP))

        job_state = flow.execute(routine_id)

        # Routine 级别的 CONTINUE 应该生效
        assert job_state.status == "completed"
        assert job_state.get_routine_state("failing")["status"] == "error_continued"

    def test_flow_error_handler_as_fallback(self):
        """测试当 routine 没有 error_handler 时，使用 flow 级别的"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __call__(self):
                raise ValueError("Test error")

        routine = FailingRoutine()
        # Routine 没有设置 error_handler
        routine_id = flow.add_routine(routine, "failing")

        # Flow 级别使用 CONTINUE
        flow.set_error_handler(ErrorHandler(strategy=ErrorStrategy.CONTINUE))

        job_state = flow.execute(routine_id)

        # Flow 级别的 CONTINUE 应该生效
        assert job_state.status == "completed"
        assert job_state.get_routine_state("failing")["status"] == "error_continued"

    def test_default_stop_behavior(self):
        """测试当没有设置任何 error_handler 时，使用默认的 STOP 行为"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __call__(self):
                raise ValueError("Test error")

        routine = FailingRoutine()
        routine_id = flow.add_routine(routine, "failing")

        # 没有设置任何 error_handler
        job_state = flow.execute(routine_id)

        # 应该使用默认的 STOP 行为
        assert job_state.status == "failed"
        assert job_state.get_routine_state("failing")["status"] == "failed"


class TestCriticalOptionalRoutines:
    """测试 Critical 和 Optional routine"""

    def test_optional_routine_failure_tolerated(self):
        """测试 optional routine 失败被容忍"""
        flow = Flow()

        class OptionalRoutine(Routine):
            def __call__(self):
                raise ValueError("Optional operation failed")

        optional = OptionalRoutine()
        optional.set_as_optional()  # 使用默认的 CONTINUE
        optional_id = flow.add_routine(optional, "optional")

        job_state = flow.execute(optional_id)

        # Optional routine 失败应该被容忍
        assert job_state.status == "completed"
        assert job_state.get_routine_state("optional")["status"] == "error_continued"

    def test_optional_routine_with_skip(self):
        """测试 optional routine 使用 SKIP 策略"""
        flow = Flow()

        class OptionalRoutine(Routine):
            def __call__(self):
                raise ValueError("Optional operation failed")

        optional = OptionalRoutine()
        optional.set_as_optional(ErrorStrategy.SKIP)
        optional_id = flow.add_routine(optional, "optional")

        job_state = flow.execute(optional_id)

        # Optional routine 应该被跳过
        assert job_state.status == "completed"
        assert job_state.get_routine_state("optional")["status"] == "skipped"

    def test_critical_routine_retry_success(self):
        """测试 critical routine 重试成功"""
        flow = Flow()
        call_count = [0]

        class CriticalRoutine(Routine):
            def __call__(self):
                call_count[0] += 1
                if call_count[0] < 2:
                    raise ConnectionError("Network error")
                # 第二次调用成功

        critical = CriticalRoutine()
        critical.set_as_critical(max_retries=3, retry_delay=0.1)
        critical_id = flow.add_routine(critical, "critical")

        job_state = flow.execute(critical_id)

        # Critical routine 应该重试成功
        assert job_state.status == "completed"
        assert call_count[0] == 2  # 初始调用 + 1次重试
        assert job_state.get_routine_state("critical")["status"] == "completed"
        assert job_state.get_routine_state("critical").get("retry_count", 0) > 0

    def test_critical_routine_retry_failure_flow_fails(self):
        """测试 critical routine 重试失败后 flow 失败"""
        flow = Flow()

        class AlwaysFailingRoutine(Routine):
            def __call__(self):
                raise ConnectionError("Always fails")

        critical = AlwaysFailingRoutine()
        critical.set_as_critical(max_retries=2, retry_delay=0.1)
        critical_id = flow.add_routine(critical, "critical")

        job_state = flow.execute(critical_id)

        # Critical routine 重试失败后，flow 应该失败
        assert job_state.status == "failed"
        assert job_state.get_routine_state("critical")["status"] == "failed"

    def test_mixed_optional_and_critical(self):
        """测试混合使用 optional 和 critical routine"""
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
                self.call_count = 0

            def process(self, data):
                self.call_count += 1

        optional = OptionalRoutine()
        optional.set_as_optional()
        optional_id = flow.add_routine(optional, "optional")

        critical = CriticalRoutine()
        critical.set_as_critical(max_retries=1, retry_delay=0.1)
        critical_id = flow.add_routine(critical, "critical")

        flow.connect(optional_id, "output", critical_id, "input")

        job_state = flow.execute(optional_id)

        # Optional routine 失败应该被容忍，但 critical routine 可能没有收到数据
        assert job_state.status == "completed"
        assert job_state.get_routine_state("optional")["status"] == "error_continued"
        # Critical routine 可能没有执行（因为没有收到数据）


class TestConvenienceMethods:
    """测试便捷方法"""

    def test_set_as_optional_default(self):
        """测试 set_as_optional() 默认使用 CONTINUE"""
        routine = Routine()
        routine.set_as_optional()

        error_handler = routine.get_error_handler()
        assert error_handler is not None
        assert error_handler.strategy == ErrorStrategy.CONTINUE
        assert error_handler.is_critical is False

    def test_set_as_optional_with_skip(self):
        """测试 set_as_optional() 使用 SKIP 策略"""
        routine = Routine()
        routine.set_as_optional(ErrorStrategy.SKIP)

        error_handler = routine.get_error_handler()
        assert error_handler is not None
        assert error_handler.strategy == ErrorStrategy.SKIP
        assert error_handler.is_critical is False

    def test_set_as_critical(self):
        """测试 set_as_critical()"""
        routine = Routine()
        routine.set_as_critical(max_retries=5, retry_delay=2.0, retry_backoff=1.5)

        error_handler = routine.get_error_handler()
        assert error_handler is not None
        assert error_handler.strategy == ErrorStrategy.RETRY
        assert error_handler.is_critical is True
        assert error_handler.max_retries == 5
        assert error_handler.retry_delay == 2.0
        assert error_handler.retry_backoff == 1.5


class TestErrorHandlerIsCritical:
    """测试 ErrorHandler 的 is_critical 属性"""

    def test_is_critical_affects_retry_behavior(self):
        """测试 is_critical 影响重试失败后的行为"""
        flow = Flow()

        class AlwaysFailingRoutine(Routine):
            def __call__(self):
                raise ConnectionError("Always fails")

        # 非 critical routine，重试失败后 flow 继续（如果使用 CONTINUE）
        routine1 = AlwaysFailingRoutine()
        routine1.set_error_handler(
            ErrorHandler(
                strategy=ErrorStrategy.RETRY, max_retries=1, retry_delay=0.1, is_critical=False
            )
        )
        routine1_id = flow.add_routine(routine1, "routine1")

        job_state1 = flow.execute(routine1_id)
        # 非 critical routine，重试失败后 flow 失败（RETRY 策略的默认行为）
        assert job_state1.status == "failed"

        # Critical routine，重试失败后 flow 必须失败
        routine2 = AlwaysFailingRoutine()
        routine2.set_error_handler(
            ErrorHandler(
                strategy=ErrorStrategy.RETRY, max_retries=1, retry_delay=0.1, is_critical=True
            )
        )
        routine2_id = flow.add_routine(routine2, "routine2")

        job_state2 = flow.execute(routine2_id)
        # Critical routine，重试失败后 flow 必须失败
        assert job_state2.status == "failed"

    def test_is_critical_serialization(self):
        """测试 is_critical 属性的序列化"""
        handler = ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=3, is_critical=True)

        data = handler.serialize()
        assert data["is_critical"] is True

        # 反序列化
        new_handler = ErrorHandler()
        new_handler.deserialize(data)
        assert new_handler.is_critical is True
        assert new_handler.strategy == ErrorStrategy.RETRY
        assert new_handler.max_retries == 3
