# Routilux Timeout机制重构方案

## 问题总结

当前timeout实现存在严重的架构缺陷：
- 两层ThreadPoolExecutor嵌套
- ContextVar无法跨线程传递
- 资源浪费（每次创建新executor）
- 职责不清（timeout在基础设施层）

## 方案对比

### 方案1: 统一Executor + Context显式传递（推荐）

**优点：**
- ✅ 保持向后兼容
- ✅ 只有一层executor
- ✅ context通过task传递，不依赖线程
- ✅ 性能提升（复用executor）
- ✅ 代码更清晰

**缺点：**
- 需要修改task定义
- context传递略复杂

**改动范围：**
- `routilux/flow/task.py` - 添加context到task
- `routilux/slot.py` - 移除executor创建，使用task的executor
- `routilux/flow/flow.py` - 统一管理executor

**实施步骤：**

#### Step 1: 修改SlotActivationTask
```python
@dataclass
class SlotActivationTask:
    slot: Slot
    data: dict[str, Any]
    connection: Connection | None = None
    priority: TaskPriority = TaskPriority.NORMAL
    retry_count: int = 0
    max_retries: int = 0
    created_at: datetime | None = None
    job_state: Any | None = None
    timeout: float | None = None  # 新增：timeout配置
    executor: ThreadPoolExecutor | None = None  # 新增：使用flow的executor
```

#### Step 2: 修改execute_task，在task层处理timeout
```python
def execute_task(task: SlotActivationTask, flow: "Flow") -> None:
    """Execute a single task with optional timeout."""
    try:
        if task.connection:
            mapped_data = task.connection._apply_mapping(task.data)
        else:
            mapped_data = task.data

        if task.slot.routine:
            task.slot.routine._current_flow = flow

        # 如果没有timeout，直接调用
        if task.timeout is None:
            task.slot.receive(mapped_data, job_state=task.job_state, flow=flow)
        else:
            # 使用flow的executor，创建带timeout的任务
            if task.executor is None:
                task.executor = flow._get_executor()

            # 提交到executor并等待结果（带timeout）
            future = task.executor.submit(
                task.slot.receive,
                mapped_data,
                job_state=task.job_state,
                flow=flow
            )
            try:
                future.result(timeout=task.timeout)
            except TimeoutError:
                # 处理超时
                flow._handle_slot_timeout(task.slot, task.timeout)
                future.cancel()
    except Exception as e:
        from routilux.flow.error_handling import handle_task_error
        handle_task_error(task, e, flow)
```

#### Step 3: 修改emit()，传递timeout配置
```python
# 在emit()中创建task时，添加timeout配置
task = SlotActivationTask(
    slot=slot,
    data=kwargs.copy(),
    connection=connection,
    priority=TaskPriority.NORMAL,
    created_at=datetime.now(),
    job_state=job_state,
    timeout=self.routine.get_config("timeout") if self.routine else None,  # 新增
    executor=flow._get_executor(),  # 使用flow的executor
)
```

#### Step 4: 简化slot.receive()
```python
def receive(self, data: dict[str, Any], job_state=None, flow=None) -> None:
    # 移除ThreadPoolExecutor相关代码
    merged_data = self._merge_data(data)

    # 设置context
    from routilux.routine import _current_job_state
    old_job_state = None
    if job_state is not None:
        old_job_state = _current_job_state.get(None)
        _current_job_state.set(job_state)

    try:
        if self.handler is not None:
            # 直接调用handler，不再处理timeout
            sig = inspect.signature(self.handler)
            params = list(sig.parameters.keys())

            if self._is_kwargs_handler(self.handler):
                self.handler(**merged_data)
            elif len(params) == 1 and params[0] == "data":
                self.handler(merged_data)
            # ... 其他情况 ...
    finally:
        # 恢复context
        if old_job_state is not None:
            _current_job_state.set(old_job_state)
        elif job_state is not None:
            _current_job_state.set(None)
```

---

### 方案2: 完全移除框架层timeout，由用户代码处理（最干净）

**优点：**
- ✅ 最干净的架构
- ✅ 职责清晰（timeout是业务逻辑）
- ✅ 零框架复杂度
- ✅ 更灵活

**缺点：**
- ❌ 破坏向后兼容
- ❌ 用户需要改代码

**实施方案：**

#### Step 1: Deprecation warning
```python
# slot.py
if timeout:
    import warnings
    warnings.warn(
        "Slot-level timeout is deprecated and will be removed in v1.0. "
        "Use timeout handling in your handler code instead. "
        "See: https://github.com/your-repo/docs/timeout-migration.md",
        DeprecationWarning,
        stacklevel=2
    )
    # 仍然执行，但发出警告
```

#### Step 2: 提供迁移指南
```python
# 旧代码
class MyRoutine(Routine):
    def __init__(self):
        super().__init__()
        self.set_config(timeout=30)  # 框架层timeout
        self.define_slot("input", handler=self.process)

    def process(self, data):
        # 业务逻辑，超过30秒会被中断

# 新代码
class MyRoutine(Routine):
    def __init__(self):
        super().__init__()
        self.define_slot("input", handler=self.process)

    def process(self, data):
        import signal
        from contextlib import contextmanager

        @contextmanager
        def timeout_context(seconds):
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Operation timed out after {seconds} seconds")

            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
            try:
                yield
            finally:
                signal.alarm(0)

        with timeout_context(30):
            # 业务逻辑，超过30秒会被中断
            pass
```

#### Step 3: 在v1.0完全移除
```python
# v1.0中移除timeout相关代码
def receive(self, data, job_state=None, flow=None):
    # 直接调用，不再处理timeout
    if self.handler is not None:
        self.handler(**merged_data)
```

---

### 方案3: 改用asyncio架构（最彻底，但工作量大）

**优点：**
- ✅ 原生支持timeout
- ✅ 更现代的异步模型
- ✅ 没有线程切换开销
- ✅ 更好的资源利用

**缺点：**
- ❌ 需要大规模重构
- ❌ 破坏向后兼容（用户代码改为async）
- ❌ 学习曲线陡峭

**实施大纲：**

#### Step 1: 核心API改为async
```python
class Flow:
    async def execute_async(self, entry_routine_id, entry_params=None):
        """异步执行flow"""
        job_state = JobState(self.flow_id)
        # ...

class Routine:
    async def process_async(self, **kwargs):
        """异步handler"""
        # ...
```

#### Step 2: 使用asyncio timeout
```python
import asyncio

async def receive_async(self, data, job_state=None, flow=None):
    merged_data = self._merge_data(data)

    # 设置context (使用asyncio的contextvar)
    _current_job_state.set(job_state)

    try:
        if self.timeout:
            # 使用asyncio.wait_for实现timeout
            await asyncio.wait_for(
                self.handler_async(**merged_data),
                timeout=self.timeout
            )
        else:
            await self.handler_async(**merged_data)
    except asyncio.TimeoutError:
        raise TimeoutError(f"Handler exceeded timeout of {self.timeout} seconds")
    finally:
        _current_job_state.set(None)
```

#### Step 3: 保持同步API兼容
```python
def execute(self, entry_routine_id, entry_params=None):
    """同步API，内部调用async"""
    import asyncio
    return asyncio.run(self.execute_async(entry_routine_id, entry_params))
```

---

## 推荐方案

**推荐方案1（统一Executor）**，原因：
1. ✅ 向后兼容，现有代码无需修改
2. ✅ 性能提升（复用executor）
3. ✅ 架构清晰（只有一层executor）
4. ✅ 实施风险低
5. ✅ 为未来迁移到方案2或3做准备

## 实施计划

### Phase 1: 准备工作（1天）
- [ ] 添加task.timeout和task.executor字段
- [ ] 更新SlotActivationTask构造函数
- [ ] 编写单元测试

### Phase 2: 核心重构（2-3天）
- [ ] 修改execute_task()处理timeout
- [ ] 修改emit()传递timeout配置
- [ ] 简化slot.receive()，移除ThreadPoolExecutor
- [ ] 更新flow executor管理

### Phase 3: 测试验证（2天）
- [ ] 单元测试覆盖
- [ ] 集成测试验证
- [ ] 性能基准测试
- [ ] 向后兼容性测试

### Phase 4: 文档和迁移（1天）
- [ ] 更新API文档
- [ ] 提供迁移指南（如果需要）
- [ ] 添加changelog

**总计：6-7天**

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 破坏向后兼容 | 高 | 充分测试，提供迁移指南 |
| 性能回归 | 中 | 性能基准测试 |
| Context传递bug | 中 | 完善单元测试 |
| Executor管理复杂度 | 低 | 代码审查，充分文档 |

## 成功标准

- [ ] 所有现有测试通过
- [ ] 新增单元测试覆盖率 > 80%
- [ ] 性能不低于现有实现
- [ ] Context传递100%可靠
- [ ] 无ThreadPoolExecutor嵌套
