# Routilux 断点机制改进实施计划

## 执行摘要

本计划针对 Routilux 断点机制存在的问题，在**实现复杂度**和**工程最佳实践**之间找到平衡点。考虑到系统并非高负载场景，我们采用**渐进式改进**策略，优先解决数据丢失风险，添加基本监控，避免过度设计。

**核心原则**：
- ✅ **简单有效**：优先使用简单方案解决问题
- ✅ **渐进改进**：分阶段实施，每阶段都有独立价值
- ✅ **向后兼容**：不破坏现有 API 和功能
- ✅ **可观测性**：添加必要的监控和日志

---

## 改进目标与优先级

### 优先级 P0（必须修复 - 数据完整性）

1. **防止数据丢失**：队列满时采用更安全的策略
2. **断点暂停时阻止入队**：避免暂停期间队列溢出
3. **基本队列监控**：能够及时发现队列问题

### 优先级 P1（重要改进 - 可观测性）

4. **队列状态 API**：提供队列健康检查接口
5. **改进暂停/恢复流程**：保存和恢复 slot 队列状态
6. **增强错误处理**：更详细的错误信息和指标

### 优先级 P2（优化改进 - 可选）

7. **队列配置灵活性**：支持 per-slot 配置
8. **批量断点操作**：提升 API 易用性

---

## 阶段一：核心问题修复（P0）

### 1.1 改进 Slot 队列满时的处理策略

**问题**：当前队列满时直接丢弃事件，可能导致数据丢失。

**解决方案**：实现**简单重试机制** + **队列状态检查**

**实现复杂度**：⭐ (低)

#### 1.1.1 修改 `Slot.enqueue()` 方法

**文件**：`routilux/routilux/slot.py`

**修改内容**：

```python
# 在 Slot 类中添加属性
def __init__(self, ...):
    # ... 现有代码 ...
    self._enqueue_retry_count: int = 0  # 重试计数
    self._max_enqueue_retries: int = 3  # 最大重试次数
    self._enqueue_retry_delay: float = 0.1  # 重试延迟（秒）

# 修改 enqueue 方法
def enqueue(
    self, 
    data: Any, 
    emitted_from: str, 
    emitted_at: datetime,
    retry_count: int = 0  # 新增参数
) -> None:
    """Add data to queue with retry mechanism.
    
    Args:
        data: Data to enqueue.
        emitted_from: Name of the routine that emitted the event.
        emitted_at: Timestamp when the event was emitted.
        retry_count: Current retry attempt (internal use).
    
    Raises:
        SlotQueueFullError: If queue is full after retries.
    """
    with self._lock:
        # Check watermark and auto-shrink
        if len(self._queue) >= self.watermark_threshold:
            self._clear_consumed_data()
        
        # Check if still full
        if len(self._queue) >= self.max_queue_length:
            # 如果还有重试机会，等待后重试
            if retry_count < self._max_enqueue_retries:
                # 释放锁，等待后重试
                time.sleep(self._enqueue_retry_delay * (retry_count + 1))
                # 递归重试
                return self.enqueue(data, emitted_from, emitted_at, retry_count + 1)
            
            # 重试失败，抛出异常
            raise SlotQueueFullError(
                f"Slot '{self.name}' queue is full (max={self.max_queue_length}). "
                f"Unconsumed: {self.get_unconsumed_count()}, Total: {len(self._queue)}. "
                f"Retried {retry_count} times."
            )
        
        # 重置重试计数（成功入队）
        self._enqueue_retry_count = 0
        
        # Add data point
        data_point = SlotDataPoint(
            data=data,
            emitted_at=emitted_at,
            enqueued_at=datetime.now(),
            emitted_from=emitted_from,
        )
        self._queue.append(data_point)
```

**关键点**：
- ✅ 简单重试机制（最多 3 次，指数退避）
- ✅ 不改变现有 API 签名（retry_count 有默认值）
- ✅ 对于非高负载系统，重试通常能解决临时队列满的问题

#### 1.1.2 添加队列状态检查方法

**文件**：`routilux/routilux/slot.py`

**新增方法**：

```python
def get_queue_metrics(self) -> dict[str, Any]:
    """Get current queue metrics for monitoring.
    
    Returns:
        Dictionary with queue metrics:
        - queue_size: Current queue size
        - max_length: Maximum queue length
        - usage_percent: Queue usage percentage (0-100)
        - unconsumed_count: Number of unconsumed items
        - is_full: Whether queue is full
        - is_near_full: Whether queue is near full (>80%)
    """
    with self._lock:
        queue_size = len(self._queue)
        unconsumed = self.get_unconsumed_count()
        usage_percent = (queue_size / self.max_queue_length * 100) if self.max_queue_length > 0 else 0
        
        return {
            "queue_size": queue_size,
            "max_length": self.max_queue_length,
            "usage_percent": round(usage_percent, 2),
            "unconsumed_count": unconsumed,
            "is_full": queue_size >= self.max_queue_length,
            "is_near_full": queue_size >= self.watermark_threshold,
            "slot_name": self.name,
            "routine_id": self.routine._id if self.routine else None,
        }

def is_paused(self) -> bool:
    """Check if the routine owning this slot is paused.
    
    Returns:
        True if routine is paused (via debug session).
    """
    if not self.routine:
        return False
    
    # 检查 routine 所属的 flow 是否暂停
    if hasattr(self.routine, '_current_flow') and self.routine._current_flow:
        return getattr(self.routine._current_flow, '_paused', False)
    
    return False
```

**关键点**：
- ✅ 提供队列状态信息，便于监控
- ✅ 检查 routine 是否暂停，用于后续改进

### 1.2 断点暂停时阻止 slot 入队

**问题**：断点暂停时，slot 队列仍可接收数据，可能导致队列溢出。

**解决方案**：在 `enqueue` 前检查 debug session 状态

**实现复杂度**：⭐ (低)

#### 1.2.1 修改 `Slot.enqueue()` 添加暂停检查

**文件**：`routilux/routilux/slot.py`

**修改内容**：

```python
def enqueue(
    self, 
    data: Any, 
    emitted_from: str, 
    emitted_at: datetime,
    retry_count: int = 0,
    job_id: str | None = None  # 新增：用于检查 debug session
) -> None:
    """Add data to queue with pause check and retry mechanism."""
    # 检查 routine 是否暂停（通过 flow）
    if self.is_paused():
        # 如果暂停，检查是否有 debug session
        if job_id:
            from routilux.monitoring.registry import MonitoringRegistry
            if MonitoringRegistry.is_enabled():
                registry = MonitoringRegistry.get_instance()
                debug_store = registry.debug_session_store
                if debug_store:
                    session = debug_store.get(job_id)
                    if session and session.status == "paused":
                        # 暂停时，延迟入队（等待恢复）
                        # 对于非高负载系统，简单等待即可
                        import time
                        max_wait = 5.0  # 最多等待 5 秒
                        start_time = time.time()
                        while session.status == "paused" and (time.time() - start_time) < max_wait:
                            time.sleep(0.1)
                            session = debug_store.get(job_id)
                            if not session:
                                break
                        
                        # 如果仍然暂停，抛出异常（而不是静默丢弃）
                        if session and session.status == "paused":
                            raise SlotQueueFullError(
                                f"Slot '{self.name}' cannot enqueue: "
                                f"routine is paused at breakpoint (job_id={job_id}). "
                                f"Please resume execution first."
                            )
    
    # ... 继续原有的 enqueue 逻辑 ...
```

**关键点**：
- ✅ 暂停时等待恢复（最多 5 秒），适合非高负载场景
- ✅ 如果长时间暂停，抛出明确的异常，而不是静默丢弃
- ✅ 需要修改调用处传入 `job_id`

#### 1.2.2 修改 `Runtime.handle_event_emit()` 传入 job_id

**文件**：`routilux/routilux/runtime.py`

**修改内容**：

```python
# 在 handle_event_emit 方法中，调用 slot.enqueue 时传入 job_id
slot.enqueue(
    data=data,
    emitted_from=emitted_from,
    emitted_at=emitted_at,
    job_id=job_state.job_id  # 新增
)
```

**关键点**：
- ✅ 最小化修改，只添加一个参数
- ✅ 向后兼容（job_id 有默认值 None）

### 1.3 改进错误处理和日志

**问题**：队列满时只记录 warning，缺少详细信息。

**解决方案**：增强日志和错误信息

**实现复杂度**：⭐ (低)

#### 1.3.1 修改 `Runtime.handle_event_emit()` 的错误处理

**文件**：`routilux/routilux/runtime.py`

**修改内容**：

```python
except SlotQueueFullError as e:
    # 记录详细的错误信息
    queue_metrics = slot.get_queue_metrics() if hasattr(slot, 'get_queue_metrics') else {}
    
    logger.error(
        f"Slot queue full, event dropped. "
        f"Job: {job_state.job_id}, "
        f"Slot: {slot.name} (routine: {target_routine_id}), "
        f"Event: {event.name} (from: {source_routine_id}), "
        f"Queue: {queue_metrics.get('queue_size', 'unknown')}/{queue_metrics.get('max_length', 'unknown')} "
        f"({queue_metrics.get('usage_percent', 0):.1f}% full), "
        f"Unconsumed: {queue_metrics.get('unconsumed_count', 'unknown')}. "
        f"Error: {e}"
    )
    
    # 记录到 job_state 的 shared_log（如果可用）
    if hasattr(job_state, 'append_to_shared_log'):
        job_state.append_to_shared_log({
            "type": "slot_queue_full",
            "timestamp": datetime.now().isoformat(),
            "slot_name": slot.name,
            "routine_id": target_routine_id,
            "event_name": event.name,
            "source_routine_id": source_routine_id,
            "queue_metrics": queue_metrics,
        })
    
    continue
```

**关键点**：
- ✅ 详细的错误日志，包含队列状态
- ✅ 记录到 job_state，便于后续分析

---

## 阶段二：可观测性改进（P1）

### 2.1 添加队列状态查询 API

**问题**：无法通过 API 查询 slot 队列状态。

**解决方案**：添加队列状态查询端点

**实现复杂度**：⭐⭐ (中)

#### 2.1.1 创建队列状态模型

**文件**：`routilux/routilux/api/models/queue.py` (新建)

**内容**：

```python
"""Queue status models for API."""

from pydantic import BaseModel
from typing import Optional


class SlotQueueMetrics(BaseModel):
    """Slot queue metrics."""
    
    slot_name: str
    routine_id: Optional[str] = None
    queue_size: int
    max_length: int
    usage_percent: float
    unconsumed_count: int
    is_full: bool
    is_near_full: bool


class FlowQueueStatusResponse(BaseModel):
    """Flow queue status response."""
    
    flow_id: str
    job_id: Optional[str] = None
    slots: list[SlotQueueMetrics]
    total_slots: int
    full_slots: int
    near_full_slots: int
```

#### 2.1.2 添加队列状态 API 路由

**文件**：`routilux/routilux/api/routes/queues.py` (新建)

**内容**：

```python
"""Queue status API routes."""

from fastapi import APIRouter, HTTPException
from routilux.api.middleware.auth import RequireAuth
from routilux.api.models.queue import FlowQueueStatusResponse, SlotQueueMetrics
from routilux.monitoring.flow_registry import FlowRegistry
from routilux.monitoring.storage import job_store

router = APIRouter()


@router.get(
    "/flows/{flow_id}/queues/status",
    response_model=FlowQueueStatusResponse,
    dependencies=[RequireAuth]
)
async def get_flow_queue_status(flow_id: str, job_id: str = None):
    """Get queue status for all slots in a flow.
    
    Args:
        flow_id: Flow ID.
        job_id: Optional job ID to filter by specific job execution.
    
    Returns:
        Queue status for all slots in the flow.
    """
    flow_registry = FlowRegistry.get_instance()
    flow = flow_registry.get(flow_id)
    
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
    
    # 收集所有 slot 的队列状态
    slot_metrics = []
    for routine_id, routine in flow.routines.items():
        for slot_name, slot in routine.slots.items():
            if hasattr(slot, 'get_queue_metrics'):
                metrics = slot.get_queue_metrics()
                slot_metrics.append(SlotQueueMetrics(**metrics))
    
    # 统计
    full_slots = sum(1 for m in slot_metrics if m.is_full)
    near_full_slots = sum(1 for m in slot_metrics if m.is_near_full)
    
    return FlowQueueStatusResponse(
        flow_id=flow_id,
        job_id=job_id,
        slots=slot_metrics,
        total_slots=len(slot_metrics),
        full_slots=full_slots,
        near_full_slots=near_full_slots,
    )


@router.get(
    "/jobs/{job_id}/queues/status",
    response_model=FlowQueueStatusResponse,
    dependencies=[RequireAuth]
)
async def get_job_queue_status(job_id: str):
    """Get queue status for a specific job.
    
    Args:
        job_id: Job ID.
    
    Returns:
        Queue status for the job's flow.
    """
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    # 使用 flow_id 查询
    return await get_flow_queue_status(job_state.flow_id, job_id=job_id)
```

#### 2.1.3 注册路由

**文件**：`routilux/routilux/api/main.py`

**修改内容**：

```python
# 在路由注册部分添加
from routilux.api.routes import queues

app.include_router(queues.router, prefix="/api", tags=["queues"])
```

### 2.2 改进暂停/恢复流程

**问题**：暂停时未保存 slot 队列状态，恢复时未检查队列健康。

**解决方案**：在暂停时记录队列状态，恢复时检查

**实现复杂度**：⭐⭐ (中)

#### 2.2.1 修改 `pause_job_executor()` 保存队列状态

**文件**：`routilux/routilux/flow/job_state_management.py`

**修改内容**：

```python
def pause_job_executor(
    executor: "JobExecutor",
    reason: str = "",
    checkpoint: Optional[dict[str, Any]] = None,
) -> None:
    """Pause job execution with queue state preservation."""
    # ... 现有代码 ...
    
    # 新增：保存 slot 队列状态
    slot_queue_states = {}
    for routine_id, routine in executor.flow.routines.items():
        routine_slots = {}
        for slot_name, slot in routine.slots.items():
            if hasattr(slot, 'get_queue_metrics'):
                metrics = slot.get_queue_metrics()
                routine_slots[slot_name] = {
                    "queue_size": metrics["queue_size"],
                    "unconsumed_count": metrics["unconsumed_count"],
                    "is_full": metrics["is_full"],
                    "is_near_full": metrics["is_near_full"],
                }
        if routine_slots:
            slot_queue_states[routine_id] = routine_slots
    
    # 记录到 pause_point
    pause_point = {
        "timestamp": datetime.now().isoformat(),
        "reason": reason,
        "checkpoint": checkpoint or {},
        "pending_tasks_count": len(executor.pending_tasks),
        "active_tasks_count": len(executor.active_tasks),
        "queue_size": executor.task_queue.qsize(),
        "slot_queue_states": slot_queue_states,  # 新增
    }
    
    # ... 继续现有代码 ...
```

#### 2.2.2 修改 `resume_job_executor()` 检查队列健康

**文件**：`routilux/routilux/flow/job_state_management.py`

**修改内容**：

```python
def resume_job_executor(executor: "JobExecutor") -> "JobState":
    """Resume job execution with queue health check."""
    # ... 现有代码 ...
    
    # 新增：检查 slot 队列健康
    queue_warnings = []
    for routine_id, routine in executor.flow.routines.items():
        for slot_name, slot in routine.slots.items():
            if hasattr(slot, 'get_queue_metrics'):
                metrics = slot.get_queue_metrics()
                if metrics["is_full"]:
                    queue_warnings.append(
                        f"Slot {routine_id}.{slot_name} is full "
                        f"({metrics['queue_size']}/{metrics['max_length']})"
                    )
                elif metrics["is_near_full"]:
                    queue_warnings.append(
                        f"Slot {routine_id}.{slot_name} is near full "
                        f"({metrics['usage_percent']:.1f}%)"
                    )
    
    if queue_warnings:
        logger.warning(
            f"Resuming job {executor.job_state.job_id} with queue warnings: "
            f"{'; '.join(queue_warnings)}"
        )
    
    # ... 继续现有代码 ...
    
    logger.info(f"Resumed job {executor.job_state.job_id}")
    
    return executor.job_state
```

### 2.3 增强调试 API

**问题**：resume API 不检查队列状态。

**解决方案**：在 resume 时返回队列状态

**实现复杂度**：⭐ (低)

#### 2.3.1 修改 `resume_debug()` API

**文件**：`routilux/routilux/api/routes/debug.py`

**修改内容**：

```python
@router.post("/jobs/{job_id}/debug/resume", dependencies=[RequireAuth])
async def resume_debug(job_id: str):
    """Resume execution from breakpoint with queue status check."""
    # ... 现有代码 ...
    
    session.resume()
    
    # 新增：检查队列状态
    queue_status = None
    try:
        from routilux.api.routes.queues import get_job_queue_status
        queue_status = await get_job_queue_status(job_id)
    except Exception as e:
        logger.warning(f"Failed to get queue status for job {job_id}: {e}")
    
    response = {
        "status": "resumed",
        "job_id": job_id,
    }
    
    if queue_status:
        response["queue_status"] = {
            "total_slots": queue_status.total_slots,
            "full_slots": queue_status.full_slots,
            "near_full_slots": queue_status.near_full_slots,
        }
        if queue_status.full_slots > 0:
            response["warnings"] = [
                f"{queue_status.full_slots} slot(s) are full"
            ]
    
    return response
```

---

## 阶段三：优化改进（P2）

### 3.1 队列配置灵活性

**问题**：队列参数硬编码，不够灵活。

**解决方案**：支持 per-slot 配置，但保持简单

**实现复杂度**：⭐⭐ (中)

#### 3.1.1 添加 Flow 级别的队列配置

**文件**：`routilux/routilux/flow/flow.py`

**修改内容**：

```python
class Flow:
    def __init__(
        self,
        flow_id: str,
        # ... 现有参数 ...
        default_slot_max_queue_length: int = 1000,  # 新增
        default_slot_watermark: float = 0.8,  # 新增
    ):
        # ... 现有代码 ...
        self.default_slot_max_queue_length = default_slot_max_queue_length
        self.default_slot_watermark = default_slot_watermark
```

#### 3.1.2 支持 Routine 级别的队列配置

**文件**：`routilux/routilux/routine.py`

**修改内容**：

```python
class Routine:
    def add_slot(
        self,
        name: str,
        max_queue_length: int | None = None,  # 新增：支持覆盖
        watermark: float | None = None,  # 新增：支持覆盖
    ) -> Slot:
        """Define a slot with optional queue configuration."""
        # 使用 routine 或 flow 的默认值
        if max_queue_length is None:
            max_queue_length = getattr(
                self._current_flow, 
                'default_slot_max_queue_length', 
                1000
            ) if self._current_flow else 1000
        
        if watermark is None:
            watermark = getattr(
                self._current_flow,
                'default_slot_watermark',
                0.8
            ) if self._current_flow else 0.8
        
        slot = Slot(
            name=name,
            routine=self,
            max_queue_length=max_queue_length,
            watermark=watermark,
        )
        # ... 继续现有代码 ...
```

### 3.2 批量断点操作 API

**问题**：只能逐个创建/删除断点。

**解决方案**：添加批量操作端点

**实现复杂度**：⭐ (低)

#### 3.2.1 添加批量断点模型

**文件**：`routilux/routilux/api/models/breakpoint.py`

**修改内容**：

```python
class BreakpointBatchCreateRequest(BaseModel):
    """Batch create breakpoints request."""
    
    breakpoints: list[BreakpointCreateRequest]


class BreakpointBatchResponse(BaseModel):
    """Batch breakpoint response."""
    
    created: list[BreakpointResponse]
    failed: list[dict[str, Any]]  # {breakpoint: ..., error: ...}
    total: int
    success_count: int
    failure_count: int
```

#### 3.2.2 添加批量操作端点

**文件**：`routilux/routilux/api/routes/breakpoints.py`

**修改内容**：

```python
@router.post(
    "/jobs/{job_id}/breakpoints/batch",
    response_model=BreakpointBatchResponse,
    status_code=201,
    dependencies=[RequireAuth],
)
async def create_breakpoints_batch(
    job_id: str, 
    request: BreakpointBatchCreateRequest
):
    """Create multiple breakpoints for a job."""
    # 验证 job 存在
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    registry = MonitoringRegistry.get_instance()
    breakpoint_mgr = registry.breakpoint_manager
    
    if not breakpoint_mgr:
        raise HTTPException(status_code=500, detail="Breakpoint manager not available")
    
    created = []
    failed = []
    
    for bp_request in request.breakpoints:
        try:
            breakpoint = Breakpoint(
                job_id=job_id,
                type=bp_request.type,
                routine_id=bp_request.routine_id,
                slot_name=bp_request.slot_name,
                event_name=bp_request.event_name,
                source_routine_id=bp_request.source_routine_id,
                source_event_name=bp_request.source_event_name,
                target_routine_id=bp_request.target_routine_id,
                target_slot_name=bp_request.target_slot_name,
                condition=bp_request.condition,
                enabled=bp_request.enabled if bp_request.enabled is not None else True,
            )
            breakpoint_mgr.add_breakpoint(breakpoint)
            created.append(_breakpoint_to_response(breakpoint))
        except Exception as e:
            failed.append({
                "breakpoint": bp_request.dict(),
                "error": str(e),
            })
    
    return BreakpointBatchResponse(
        created=created,
        failed=failed,
        total=len(request.breakpoints),
        success_count=len(created),
        failure_count=len(failed),
    )
```

---

## 实施时间表

### 阶段一：核心问题修复（1-2 周）

**Week 1**：
- Day 1-2: 实现 Slot 重试机制（1.1）
- Day 3-4: 实现暂停检查（1.2）
- Day 5: 改进错误处理（1.3）
- Day 6-7: 测试和修复

**Week 2**：
- Day 1-3: 集成测试
- Day 4-5: 文档更新
- Day 6-7: 代码审查和优化

### 阶段二：可观测性改进（1 周）

**Week 3**：
- Day 1-2: 实现队列状态 API（2.1）
- Day 3: 改进暂停/恢复流程（2.2）
- Day 4: 增强调试 API（2.3）
- Day 5-7: 测试和文档

### 阶段三：优化改进（可选，1 周）

**Week 4**：
- Day 1-3: 队列配置灵活性（3.1）
- Day 4-5: 批量断点操作（3.2）
- Day 6-7: 测试和文档

---

## 测试策略

### 单元测试

1. **Slot 重试机制测试**
   - 测试队列满时的重试逻辑
   - 测试重试失败后的异常
   - 测试重试成功的情况

2. **暂停检查测试**
   - 测试暂停时入队的阻塞
   - 测试恢复后正常入队
   - 测试超时后的异常

3. **队列状态 API 测试**
   - 测试队列状态查询
   - 测试空队列和满队列的情况

### 集成测试

1. **断点暂停场景测试**
   - 设置断点 → 触发暂停 → 上游继续发送 → 检查队列状态
   - 恢复执行 → 检查队列是否正常处理

2. **队列满场景测试**
   - 快速发送大量事件 → 检查重试机制
   - 检查错误日志和指标

### 性能测试

- 重试机制的性能影响（应该很小）
- 队列状态查询的性能（应该很快）

---

## 风险评估与缓解

### 风险 1：重试机制可能导致延迟

**风险**：重试机制可能增加事件处理的延迟。

**缓解**：
- 重试次数限制为 3 次
- 重试延迟很短（0.1s, 0.2s, 0.3s）
- 对于非高负载系统，影响可忽略

### 风险 2：暂停检查可能阻塞事件处理

**风险**：暂停时等待恢复可能阻塞事件处理线程。

**缓解**：
- 等待时间限制为 5 秒
- 超时后抛出异常，不会无限阻塞
- 对于调试场景，5 秒足够

### 风险 3：API 变更影响现有客户端

**风险**：新增 API 参数可能影响现有代码。

**缓解**：
- 所有新参数都有默认值
- 保持向后兼容
- 提供迁移指南

---

## 成功指标

### 功能指标

- ✅ 队列满时不再静默丢弃数据（通过重试机制）
- ✅ 断点暂停时队列不会溢出（通过暂停检查）
- ✅ 能够查询队列状态（通过 API）

### 质量指标

- ✅ 单元测试覆盖率 > 80%
- ✅ 集成测试通过率 100%
- ✅ 代码审查通过

### 性能指标

- ✅ 重试机制延迟 < 1 秒（3 次重试）
- ✅ 队列状态查询响应时间 < 100ms
- ✅ 暂停检查开销 < 10ms

---

## 后续优化方向（不在本计划内）

1. **分布式队列管理**：如果需要跨节点同步队列状态
2. **智能队列管理**：基于历史数据自动调整队列参数
3. **完整的可观测性集成**：集成 Prometheus/Grafana
4. **背压机制**：如果需要更复杂的流量控制

---

## 总结

本改进计划采用**渐进式、平衡复杂度**的策略：

1. **阶段一**解决核心问题（数据丢失、队列溢出），使用简单有效的方案
2. **阶段二**添加可观测性，便于监控和调试
3. **阶段三**提供优化改进，提升易用性

所有改进都：
- ✅ 保持向后兼容
- ✅ 实现复杂度适中
- ✅ 适合非高负载系统
- ✅ 有明确的测试策略

**预计总工作量**：3-4 周（如果只做阶段一和阶段二，2-3 周）

---

*文档版本：1.0*  
*最后更新：2024年*  
*作者：系统架构师*
