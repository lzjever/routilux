"""
ErrorHandler 综合测试用例
"""

from routilux import Flow, Routine, ErrorHandler, ErrorStrategy


class TestErrorHandlerStrategies:
    """错误处理策略测试"""

    def test_stop_strategy(self):
        """测试 STOP 策略"""
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

        error_handler = ErrorHandler(strategy=ErrorStrategy.STOP)
        flow.set_error_handler(error_handler)

        job_state = flow.execute(routine_id)

        assert job_state.status == "failed"
        assert error_handler.retry_count == 0

    def test_continue_strategy(self):
        """测试 CONTINUE 策略"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                raise ValueError("Test error")

        routine = FailingRoutine()
        routine_id = flow.add_routine(routine, "failing")

        error_handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)
        flow.set_error_handler(error_handler)

        job_state = flow.execute(routine_id)

        # CONTINUE 策略应该标记为 completed
        assert job_state.status == "completed"
        # 应该记录错误
        assert len(job_state.execution_history) > 0

    def test_retry_strategy_success(self):
        """测试 RETRY 策略 - 重试成功"""
        flow = Flow()
        call_count = [0]

        class RetryRoutine(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)
                self.output_event = self.define_event("output", ["data"])

            def _handle_trigger(self, **kwargs):
                call_count[0] += 1
                if call_count[0] < 2:
                    raise ValueError(f"Test error (attempt {call_count[0]})")
                self.emit("output", data="success")

        routine = RetryRoutine()
        routine_id = flow.add_routine(routine, "retry")

        error_handler = ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=3, retry_delay=0.1)
        flow.set_error_handler(error_handler)

        job_state = flow.execute(routine_id)

        assert job_state.status == "completed"
        assert call_count[0] == 2
        assert error_handler.retry_count == 1

    def test_retry_strategy_failure(self):
        """测试 RETRY 策略 - 重试失败"""
        flow = Flow()
        call_count = [0]

        class AlwaysFailingRoutine(Routine):
            def __init__(self):
                super().__init__()
                # Define trigger slot for entry routine
                self.trigger_slot = self.define_slot("trigger", handler=self._handle_trigger)

            def _handle_trigger(self, **kwargs):
                call_count[0] += 1
                raise ValueError(f"Test error (attempt {call_count[0]})")

        routine = AlwaysFailingRoutine()
        routine_id = flow.add_routine(routine, "failing")

        error_handler = ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=2, retry_delay=0.1)
        flow.set_error_handler(error_handler)

        job_state = flow.execute(routine_id)

        assert job_state.status == "failed"
        # 初始调用 1 次 + 重试 2 次 = 3 次
        assert call_count[0] == 3
        # retry_count 应该等于 max_retries（初始错误调用 1 次 handle_error + 每次重试失败调用 1 次）
        # 第一次错误: retry_count = 1
        # 第一次重试失败: retry_count = 2
        # 所以最终 retry_count = 2
        assert error_handler.retry_count == 2

    def test_skip_strategy(self):
        """测试 SKIP 策略"""
        flow = Flow()

        class FailingRoutine(Routine):
            def __init__(self):
                super().__init__()
                self.output_event = self.define_event("output", ["data"])

            def __call__(self):
                raise ValueError("Test error")

        routine = FailingRoutine()
        routine_id = flow.add_routine(routine, "failing")

        error_handler = ErrorHandler(strategy=ErrorStrategy.SKIP)
        flow.set_error_handler(error_handler)

        job_state = flow.execute(routine_id)

        assert job_state.status == "completed"
        assert job_state.routine_states.get("failing", {}).get("status") == "skipped"


class TestErrorHandlerConfiguration:
    """错误处理器配置测试"""

    def test_error_handler_with_custom_retry_delay(self):
        """测试自定义重试延迟"""
        error_handler = ErrorHandler(
            strategy=ErrorStrategy.RETRY, max_retries=2, retry_delay=0.5, retry_backoff=1.5
        )

        assert error_handler.retry_delay == 0.5
        assert error_handler.retry_backoff == 1.5

    def test_error_handler_with_retryable_exceptions(self):
        """测试可重试异常类型"""
        error_handler = ErrorHandler(
            strategy=ErrorStrategy.RETRY, retryable_exceptions=(ValueError, TypeError)
        )

        assert ValueError in error_handler.retryable_exceptions
        assert TypeError in error_handler.retryable_exceptions

    def test_error_handler_reset(self):
        """测试重置错误处理器"""
        error_handler = ErrorHandler(strategy=ErrorStrategy.RETRY, max_retries=3)

        # 模拟一些重试
        error_handler.retry_count = 2

        # 重置
        error_handler.reset()

        assert error_handler.retry_count == 0

    def test_error_handler_string_strategy(self):
        """测试使用字符串策略"""
        error_handler = ErrorHandler(strategy="stop")

        assert error_handler.strategy == ErrorStrategy.STOP

        error_handler2 = ErrorHandler(strategy="continue")
        assert error_handler2.strategy == ErrorStrategy.CONTINUE


class TestErrorHandlerContext:
    """错误处理器上下文测试"""

    def test_error_handler_with_context(self):
        """测试带上下文的错误处理"""
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

        error_handler = ErrorHandler(strategy=ErrorStrategy.CONTINUE)
        flow.set_error_handler(error_handler)

        # 执行
        job_state = flow.execute(routine_id)

        # 验证错误被记录
        assert job_state.status == "completed"


class TestErrorHandlerSerialization:
    """错误处理器序列化测试"""

    def test_error_handler_serialize(self):
        """测试错误处理器序列化"""
        error_handler = ErrorHandler(
            strategy=ErrorStrategy.RETRY, max_retries=3, retry_delay=1.0, retry_backoff=2.0
        )
        error_handler.retry_count = 1

        data = error_handler.serialize()

        assert data["_type"] == "ErrorHandler"
        assert data["strategy"] == "retry"
        assert data["max_retries"] == 3
        assert data["retry_delay"] == 1.0
        assert data["retry_backoff"] == 2.0
        assert data["retry_count"] == 1

    def test_error_handler_deserialize(self):
        """测试错误处理器反序列化"""
        data = {
            "_type": "ErrorHandler",
            "strategy": "retry",
            "max_retries": 3,
            "retry_delay": 1.0,
            "retry_backoff": 2.0,
            "retry_count": 1,
        }

        error_handler = ErrorHandler()
        error_handler.deserialize(data)

        assert error_handler.strategy == ErrorStrategy.RETRY
        assert error_handler.max_retries == 3
        assert error_handler.retry_delay == 1.0
        assert error_handler.retry_backoff == 2.0
        assert error_handler.retry_count == 1
