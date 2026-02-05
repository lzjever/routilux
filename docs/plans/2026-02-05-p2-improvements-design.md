# P2 改进方案设计文档 (A02)

**日期**: 2026-02-05
**目标**: 完成代码审查中识别的所有 P2（中优先级）问题
**状态**: 设计阶段

---

## 概述

本设计文档描述了 Routilux 框架 P2 级别改进的完整方案。所有改进遵循以下原则：

- **KISS**: 保持简单，删除不必要的复杂逻辑
- **DRY**: 消除重复代码
- **SOLID**: 单一职责、开闭原则
- **YAGNI**: 移除未使用的功能

### 涉及问题

| ID | 问题 | 优先级 | 预计时间 |
|----|------|--------|----------|
| P2-1 | 复杂参数映射逻辑 | 中 | 2 小时 |
| P2-2 | 已弃用的 `__call__` 方法 | 中 | 1 小时 |
| P2-3 | 文档示例过于简单 | 中 | 3 小时 |
| P2-4 | 缺少架构设计文档 | 中 | 4 小时 |
| P2-5 | 无性能基准测试 | 中 | 3 小时 |

**总计**: ~13 小时

---

## P2-1: 删除复杂参数映射逻辑

### 问题分析

`connection.py:249-266` 包含复杂的参数映射逻辑，用于将事件数据转换为槽处理函数的参数。该代码：

1. 逻辑复杂，难以理解和维护
2. 使用频率低（基于代码审查）
3. 违反 YAGNI 原则

### 设计决策

**删除参数映射功能**，简化连接逻辑。

### 变更内容

**文件**: `routilux/connection.py`

**删除内容**:
```python
# 删除 _map_parameters 方法（约 20 行）
def _map_parameters(self, data: Dict[str, Any], signature: inspect.Signature) -> Dict[str, Any]:
    # ... 复杂的参数映射逻辑 ...
```

**简化后的连接逻辑**:
```python
def connect(self, event: Event, slot: Slot) -> "Connection":
    """连接事件到槽。

    Args:
        event: 源事件。
        slot: 目标槽。

    Returns:
        Connection 对象。
    """
    if slot.routine and slot.routine._flow != self._flow:
        raise ConfigurationError("Cannot connect events across different Flows")

    connection = Connection(event, slot)
    self._connections.append(connection)
    return connection
```

### 影响评估

- **破坏性变更**: 是（如果有用户依赖参数映射）
- **缓解措施**: 项目未发布，无需向后兼容

---

## P2-2: 删除 `__call__` 方法

### 问题分析

`routine.py:154+` 包含已弃用的 `__call__` 方法，允许用户像函数一样调用 Routine。问题：

1. 误导用户：Routine 应该通过 Flow.execute() 执行
2. 违反架构设计：Flow 是执行控制器，不是 Routine
3. 造成概念混乱

### 设计决策

**删除 `__call__` 方法**，强制使用 Flow.execute()。

### 变更内容

**文件**: `routilux/routine.py`

**删除内容**:
```python
# 删除 __call__ 方法（约 50 行）
def __call__(self, **params) -> Any:
    """已弃用：请使用 Flow.execute() 代替。"""
    # ...
```

### 用户迁移指南

```python
# 旧方式（已删除）
result = routine(**data)

# 新方式（推荐）
job_state = flow.execute(routine_id, entry_params=data)
result = job_state.get_output()
```

### 影响评估

- **破坏性变更**: 是
- **缓解措施**: 项目未发布，无需向后兼容

---

## P2-3: 重写文档示例

### 问题分析

当前文档示例过于简单（"hello world" 风格），无法展示 Routilux 的真实能力。

### 设计决策

**添加真实场景示例**，覆盖常见使用模式。

### 变更内容

**文件**: `README.md`, `docs/source/tutorial/`, `examples/`

#### 新增示例

1. **数据处理流水线** (`examples/data_pipeline.py`)
   - 多阶段数据处理
   - 错误处理和重试
   - 条件分支

2. **异步任务编排** (`examples/async_orchestration.py`)
   - 并发执行
   - 任务依赖
   - 结果聚合

3. **长运行工作流** (`examples/long_running_workflow.py`)
   - 暂停/恢复
   - 状态持久化
   - 检查点

4. **错误处理模式** (`examples/error_handling.py`)
   - 异常捕获
   - 重试策略
   - 回滚机制

#### README 结构

```markdown
# Routilux

## 快速开始
[简化的安装和基本用法]

## 核心概念
- Flow: 工作流容器
- Routine: 可复用组件
- Event/Slot: 数据传递机制
- JobState: 状态管理

## 示例

### 数据处理流水线
[真实示例]

### 异步任务编排
[真实示例]

## API 参考
[链接到完整文档]
```

---

## P2-4: 创建架构设计文档

### 问题分析

缺少架构设计文档，新用户难以理解：
- 组件如何协作
- 数据流向
- 设计决策和权衡

### 设计决策

**创建全面的架构设计文档**，包含图表和说明。

### 变更内容

**新文件**: `docs/source/design/architecture.rst`

#### 文档结构

```rst
架构设计
========

概述
----
Routilux 是一个基于事件驱动的工作流编排框架...

组件图
----
.. graphviz::
   [组件关系图]

数据流
------
.. graphviz::
   [数据流向图]

时序图
------
.. graphviz::
   [执行时序图]

设计决策
--------
1. 为什么选择事件驱动模型？
2. 为什么使用 Slot 而不是直接函数调用？
3. 为什么 JobState 可序列化？

权衡
----
- 并发 vs 简单性
- 灵活性 vs 性能
- 可扩展性 vs 易用性
```

#### 关键图表

**组件图**:
```
┌─────────────────────────────────────┐
│              Flow                   │
│  ┌─────────┐    ┌─────────┐        │
│  │ Routine │───→│ Routine │        │
│  └─────────┘    └─────────┘        │
│       │              │              │
│       v              v              │
│    ┌──────────────────────┐        │
│    │   JobState           │        │
│    └──────────────────────┘        │
└─────────────────────────────────────┘
```

**数据流图**:
```
Event ──→ Connection ──→ Slot.receive() ──→ Handler
                                              │
                                              v
                                         JobState
```

---

## P2-5: 性能基准测试

### 问题分析

缺少性能基准测试，无法：
- 检测性能回归
- 优化瓶颈
- 与其他方案对比

### 设计决策

**使用 pytest-benchmark 实现性能基准测试**。

### 变更内容

**新文件**: `tests/benchmarks/`

#### 测试场景

1. **事件发射性能** (`test_emit_benchmark.py`)
   ```python
   def test_event_emission_throughput(benchmark):
       flow = Flow("test")
       routine = Routine("emitter")
       flow.add_routine(routine)

       def emit_1000():
           for i in range(1000):
               routine.emit("output", value=i)

       benchmark(emit_1000)
   ```

2. **槽处理性能** (`test_slot_benchmark.py`)
   ```python
   def test_slot_receive_throughput(benchmark):
       routine = Routine("receiver")
       slot = routine.define_slot("input", handler=lambda d: None)

       def receive_1000():
           for i in range(1000):
               slot.receive({"value": i})

       benchmark(receive_1000)
   ```

3. **并发执行性能** (`test_concurrent_benchmark.py`)
   ```python
   def test_concurrent_execution_speedup(benchmark):
       flow = Flow("test", execution_mode="concurrent", max_workers=4)
       # ... 设置多个并发 routine ...

       benchmark(lambda: flow.execute("entry", entry_params={}))
   ```

4. **序列化性能** (`test_serialization_benchmark.py`)
   ```python
   def test_jobstate_serialization(benchmark):
       job_state = JobState("test")
       # ... 添加一些历史记录 ...

       benchmark(lambda: job_state.serialize())
   ```

#### 依赖添加

**文件**: `pyproject.toml`

```toml
[dependency-groups]
dev = [
    # ... 现有依赖 ...
    "pytest-benchmark>=4.0.0",
]
```

#### CI 集成

**新文件**: `.github/workflows/benchmark.yml`

```yaml
name: Benchmark

on:
  push:
    branches: [main]
  pull_request:

jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install uv
        uses: astral-sh/setup-uv@v4
      - name: Install dependencies
        run: uv sync --group dev
      - name: Run benchmarks
        run: uv run pytest tests/benchmarks/ --benchmark-only
```

---

## 实施计划

### 依赖关系

```
P2-1 (删除参数映射)
    │
    ├─→ P2-2 (删除 __call__)
    │
    ├─→ P2-5 (基准测试) ←── 需要简化的连接逻辑
    │
P2-3 (文档示例) ←──────── 独立
    │
P2-4 (架构文档) ←─────── 独立
```

### 实施顺序

1. **第一阶段**: P2-1 + P2-2 (代码清理，~3 小时)
2. **第二阶段**: P2-5 (基准测试，~3 小时)
3. **第三阶段**: P2-3 + P2-4 (文档，~7 小时)

### 验收标准

每个任务完成后：
- [ ] 所有现有测试通过
- [ ] 无新增 linting 错误
- [ ] 无新增类型错误
- [ ] 代码审查通过

---

## 总结

本设计方案：

1. **删除不必要功能**: P2-1, P2-2
2. **提升文档质量**: P2-3, P2-4
3. **建立性能基线**: P2-5

所有变更遵循 YAGNI 原则，删除未使用功能，确保项目结构清晰、易于维护。

---

**文档版本**: 1.0
**最后更新**: 2026-02-05
