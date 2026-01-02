# ID 用途指南：job_id, flow_id, routine_id

## 概述

routilux 中有三个重要的 ID，它们在不同层面标识工作流和执行：

| ID | 类型 | 默认格式 | 作用域 | 重要性 |
|----|------|---------|--------|--------|
| `job_id` | UUID | UUID v4 | 单次执行 | ⭐⭐⭐ 非常重要 |
| `flow_id` | 字符串 | UUID v4（可自定义） | 工作流定义 | ⭐⭐ 重要 |
| `routine_id` | 字符串 | `hex(id(self))`（可自定义） | 工作流节点 | ⭐⭐ 重要 |

## 1. job_id - 执行实例唯一标识

### 用途

**`job_id` 是每次工作流执行的唯一标识符**，用于区分不同的执行实例。

### 特点

- ✅ **自动生成**：每次创建 `JobState` 时自动生成 UUID
- ✅ **全局唯一**：使用 UUID v4，确保全局唯一性
- ✅ **不可自定义**：用户无法修改
- ✅ **执行级别**：每个 `flow.execute()` 调用都会创建新的 `job_id`

### 使用场景

#### 1. 状态持久化和恢复

```python
# 保存执行状态
job_state = flow.execute(entry_id)
storage_key = f"execution_state/{job_state.job_id}"  # 使用 job_id 作为存储键
storage.put(storage_key, {
    "flow": flow.serialize(),
    "job_state": job_state.serialize(),
})

# 恢复执行状态
transfer_data = storage.get(storage_key)
job_state = JobState()
job_state.deserialize(transfer_data["job_state"])
# job_id 用于标识这是哪个执行实例
```

#### 2. 执行追踪和日志

```python
# 在日志中记录执行ID
logger.info(f"Execution started: {job_state.job_id}")

# 查询特定执行的状态
execution_state = storage.get(f"execution_state/{job_id}")
```

#### 3. 多执行实例管理

```python
# 同一个 Flow 可以同时执行多次，每个执行有独立的 job_id
flow = Flow(flow_id="my_workflow")

job1 = flow.execute(entry_id, entry_params={"task": "A"})  # job_id: xxx-1
job2 = flow.execute(entry_id, entry_params={"task": "B"})  # job_id: xxx-2

assert job1.job_id != job2.job_id  # 不同的执行实例
```

### 对客户代码的重要性

**⭐⭐⭐ 非常重要**

- **必须使用**：跨主机恢复、状态持久化等场景必须使用 `job_id`
- **存储键**：推荐使用 `job_id` 作为云存储的键
- **追踪**：用于追踪和查询特定执行实例
- **日志关联**：将日志与执行实例关联

### 代码示例

```python
# 在 cross_host_demo.py 中的使用
storage_key = f"execution_state/{job_state.job_id}"
# 输出: "execution_state/3a46aec8-363c-4487-b842-3ea38a0e9c99"
```

---

## 2. flow_id - 工作流定义标识

### 用途

**`flow_id` 标识工作流的定义**，用于区分不同的工作流模板。

### 特点

- ✅ **可自定义**：创建 Flow 时可以指定，也可以自动生成 UUID
- ✅ **工作流级别**：同一个 `flow_id` 可以执行多次（每次有不同的 `job_id`）
- ✅ **序列化恢复**：用于验证恢复的 Flow 和 JobState 是否匹配

### 使用场景

#### 1. 工作流版本管理

```python
# 使用有意义的 flow_id 标识工作流版本
flow_v1 = Flow(flow_id="data_processing_v1")
flow_v2 = Flow(flow_id="data_processing_v2")

# 可以同时存在多个版本
```

#### 2. 恢复验证

```python
# 恢复时验证 flow_id 是否匹配
flow = Flow()
flow.deserialize(transfer_data["flow"])

job_state = JobState()
job_state.deserialize(transfer_data["job_state"])

# 系统会自动验证 flow_id 是否匹配
if job_state.flow_id != flow.flow_id:
    raise ValueError("Flow ID mismatch!")
```

#### 3. 工作流分类和查询

```python
# 查询特定工作流的所有执行
all_executions = [
    job for job in all_job_states 
    if job.flow_id == "my_workflow"
]
```

### 对客户代码的重要性

**⭐⭐ 重要**

- **推荐自定义**：使用有意义的名称便于管理
- **版本控制**：可以用于工作流版本管理
- **恢复验证**：系统自动验证，但了解其作用有助于调试
- **查询过滤**：可以用于查询特定工作流的执行

### 代码示例

```python
# 在 cross_host_demo.py 中的使用
flow = Flow(flow_id="llm_agent_workflow")  # 自定义 flow_id
# 输出: "llm_agent_workflow"

# 自动生成
flow = Flow()  # flow_id 自动生成 UUID
# 输出: "9867d45c-1b5f-4af2-87c0-6e73c93df14d"
```

---

## 3. routine_id - 工作流节点标识

### 用途

**`routine_id` 标识工作流中的节点（Routine）**，用于在 Flow 中定位和操作特定的 Routine。

### 特点

- ✅ **可自定义**：添加 Routine 时可以指定，也可以使用自动生成的 `hex(id(self))`
- ✅ **Flow 级别**：在同一个 Flow 内必须唯一
- ✅ **执行时访问**：通过 `get_execution_context()` 获取当前执行的 `routine_id`

### 使用场景

#### 1. 添加和连接 Routine

```python
# 添加 Routine 时指定 routine_id
flow = Flow()
processor = DataProcessor()
processor_id = flow.add_routine(processor, "processor")  # 自定义 routine_id

validator = DataValidator()
validator_id = flow.add_routine(validator, "validator")  # 自定义 routine_id

# 连接 Routine
flow.connect(processor_id, "output", validator_id, "input")
```

#### 2. 执行入口指定

```python
# 指定从哪个 Routine 开始执行
job_state = flow.execute(processor_id, entry_params={"data": "test"})
```

#### 3. 状态查询和更新

```python
# 在 Routine 内部更新自己的状态
def process(self, data):
    ctx = self.get_execution_context()
    if ctx:
        # 使用 routine_id 更新状态
        ctx.job_state.update_routine_state(ctx.routine_id, {
            "status": "processing",
            "processed_count": 10
        })

# 查询特定 Routine 的状态
routine_state = job_state.get_routine_state("processor")
```

#### 4. 执行历史查询

```python
# 查询特定 Routine 的执行历史
history = job_state.get_execution_history(routine_id="processor")
for record in history:
    print(f"{record.routine_id} emitted {record.event_name}")
```

### 对客户代码的重要性

**⭐⭐ 重要**

- **必须使用**：添加 Routine、连接、执行入口都需要 `routine_id`
- **推荐自定义**：使用有意义的名称便于理解和维护
- **状态管理**：更新和查询 Routine 状态时需要
- **调试追踪**：执行历史和日志中会使用

### 代码示例

```python
# 在 cross_host_demo.py 中的使用
agent = LLMAgentRoutine()
agent_id = flow.add_routine(agent, "llm_agent")  # 自定义 routine_id
# 输出: "llm_agent"

# 执行
job_state = flow.execute(agent_id, entry_params={"task": "..."})

# 查询状态
routine_state = job_state.get_routine_state(agent_id)
```

---

## 实际使用建议

### 1. job_id - 必须使用

**场景**：状态持久化、跨主机恢复、执行追踪

```python
# ✅ 推荐：使用 job_id 作为存储键
storage_key = f"execution_state/{job_state.job_id}"

# ✅ 推荐：在日志中记录 job_id
logger.info(f"Execution {job_state.job_id} started")

# ✅ 推荐：用于查询特定执行
execution = storage.get(f"execution_state/{job_id}")
```

### 2. flow_id - 推荐自定义

**场景**：工作流版本管理、分类查询

```python
# ✅ 推荐：使用有意义的名称
flow = Flow(flow_id="llm_agent_workflow_v1")

# ✅ 可以用于版本管理
flow_v1 = Flow(flow_id="data_processing_v1")
flow_v2 = Flow(flow_id="data_processing_v2")

# ⚠️ 也可以自动生成（如果不需要版本管理）
flow = Flow()  # 自动生成 UUID
```

### 3. routine_id - 推荐自定义

**场景**：添加 Routine、连接、状态管理

```python
# ✅ 推荐：使用有意义的名称
processor_id = flow.add_routine(processor, "data_processor")
validator_id = flow.add_routine(validator, "data_validator")

# ⚠️ 也可以使用自动生成的（但不推荐，难以理解）
routine_id = flow.add_routine(routine)  # 使用 hex(id(self))
```

---

## 总结

### 重要性排序

1. **job_id** ⭐⭐⭐ - **必须使用**
   - 每次执行唯一标识
   - 状态持久化和恢复的关键
   - 执行追踪和日志关联

2. **flow_id** ⭐⭐ - **推荐自定义**
   - 工作流定义标识
   - 版本管理和分类查询
   - 恢复验证（系统自动）

3. **routine_id** ⭐⭐ - **推荐自定义**
   - 工作流节点标识
   - 添加、连接、执行入口
   - 状态管理和历史查询

### 客户代码使用建议

- **必须使用 `job_id`**：所有状态持久化和恢复场景
- **推荐自定义 `flow_id`**：便于版本管理和查询
- **推荐自定义 `routine_id`**：便于理解和维护
- **了解其作用**：有助于调试和问题排查

### 常见错误

```python
# ❌ 错误：使用 flow_id 作为存储键（多个执行会覆盖）
storage_key = f"execution_state/{flow.flow_id}"  # 错误！

# ✅ 正确：使用 job_id 作为存储键
storage_key = f"execution_state/{job_state.job_id}"  # 正确

# ❌ 错误：使用自动生成的 routine_id（难以理解）
routine_id = flow.add_routine(routine)  # 不推荐

# ✅ 正确：使用有意义的 routine_id
routine_id = flow.add_routine(routine, "my_processor")  # 推荐
```

