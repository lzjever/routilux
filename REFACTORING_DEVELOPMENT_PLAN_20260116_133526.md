# 线程模型重构开发计划

## 执行摘要

本计划详细描述将Routilux从Flow级别的执行状态迁移到Job级别的执行上下文的完整重构过程。这是一个**重大架构变更**，需要严格按照本计划执行，**不允许任何自由发挥**。

## 设计审查结果

### ✅ 设计方案评估

经过严格审查，设计方案**符合最佳实践**，但需要补充以下关键点：

1. ✅ **架构设计正确**：Job级别隔离、全局线程池、序列化友好
2. ⚠️ **需要补充**：emit()路由机制、暂停/恢复/取消、超时处理、错误清理
3. ⚠️ **需要明确**：Flow.execute()的处理方式（用户说不需要向后兼容）

### 🔴 关键遗漏点

1. **emit()路由问题**：当前`emit()`通过`flow._enqueue_task()`，但新设计中Flow没有task_queue，需要路由到正确的JobExecutor
2. **暂停/恢复/取消**：需要实现这些功能在JobExecutor中
3. **Monitoring hooks**：需要确保在JobExecutor中正确调用
4. **超时处理**：需要实现超时机制
5. **JobExecutor清理**：job完成后需要从GlobalJobManager中移除
6. **错误处理**：需要确保错误时正确清理资源

## 开发计划

### Phase 1: 创建核心基础设施

#### Step 1.1: 创建GlobalJobManager模块

**文件**: `routilux/job_manager.py` (新建)

**任务**:
1. 创建`GlobalJobManager`类（单例模式）
2. 实现线程安全的单例初始化
3. 实现全局线程池管理
4. 实现job注册和查询

**具体实现要求**:

```python
"""
Global job manager for managing all job executions.

This module provides a singleton GlobalJobManager that manages:
- Global thread pool (shared by all jobs)
- Running job registry
- Job lifecycle management
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from routilux.flow.flow import Flow
    from routilux.job_state import JobState

logger = logging.getLogger(__name__)

# Global instance
_global_job_manager: Optional["GlobalJobManager"] = None
_global_job_manager_lock = threading.Lock()


class GlobalJobManager:
    """Global job manager (singleton).
    
    Manages all job executions with a shared thread pool.
    """
    
    def __init__(self, max_workers: int = 100):
        """Initialize global job manager.
        
        Args:
            max_workers: Maximum number of worker threads in global thread pool.
        """
        self.max_workers = max_workers
        self.global_thread_pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="RoutiluxWorker"
        )
        self.running_jobs: dict[str, "JobExecutor"] = {}
        self._lock = threading.Lock()
        self._shutdown = False
    
    def start_job(
        self,
        flow: "Flow",
        entry_routine_id: str,
        entry_params: dict | None = None,
        timeout: float | None = None,
        job_state: "JobState" | None = None,
    ) -> "JobState":
        """Start a new job execution.
        
        Args:
            flow: Flow to execute.
            entry_routine_id: Entry routine identifier.
            entry_params: Entry parameters.
            timeout: Execution timeout in seconds.
            job_state: Optional existing JobState to use.
        
        Returns:
            JobState object (status will be RUNNING).
        
        Raises:
            RuntimeError: If manager is shut down.
            ValueError: If entry_routine_id not found.
        """
        if self._shutdown:
            raise RuntimeError("GlobalJobManager is shut down")
        
        if entry_routine_id not in flow.routines:
            raise ValueError(f"Entry routine '{entry_routine_id}' not found in flow")
        
        from routilux.job_state import JobState
        from routilux.status import ExecutionStatus
        
        # Create or use provided JobState
        if job_state is None:
            job_state = JobState(flow.flow_id)
        
        job_state.status = ExecutionStatus.RUNNING
        job_state.current_routine_id = entry_routine_id
        
        # Create JobExecutor
        from routilux.job_executor import JobExecutor
        
        executor = JobExecutor(
            flow=flow,
            job_state=job_state,
            global_thread_pool=self.global_thread_pool,
            timeout=timeout,
        )
        
        # Register job
        with self._lock:
            if self._shutdown:
                raise RuntimeError("GlobalJobManager is shut down")
            self.running_jobs[job_state.job_id] = executor
        
        # Start execution
        executor.start(entry_routine_id, entry_params or {})
        
        return job_state
    
    def get_job(self, job_id: str) -> Optional["JobExecutor"]:
        """Get job executor by job_id.
        
        Args:
            job_id: Job identifier.
        
        Returns:
            JobExecutor if found, None otherwise.
        """
        with self._lock:
            return self.running_jobs.get(job_id)
    
    def wait_for_all_jobs(self, timeout: float | None = None) -> bool:
        """Wait for all running jobs to complete.
        
        Args:
            timeout: Maximum time to wait in seconds. None for infinite wait.
        
        Returns:
            True if all jobs completed, False if timeout.
        """
        import time
        
        start_time = time.time()
        
        while True:
            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return False
            
            # Check if all jobs are done
            with self._lock:
                running = [
                    job_id for job_id, executor in self.running_jobs.items()
                    if executor.is_running()
                ]
            
            if not running:
                return True
            
            time.sleep(0.1)
    
    def shutdown(self, wait: bool = True, timeout: float | None = None):
        """Shutdown global job manager.
        
        Args:
            wait: Whether to wait for jobs to complete.
            timeout: Wait timeout in seconds.
        """
        with self._lock:
            if self._shutdown:
                return
            
            self._shutdown = True
            
            # Stop all running jobs
            for executor in list(self.running_jobs.values()):
                executor.stop()
            
            self.running_jobs.clear()
        
        # Shutdown thread pool
        if wait:
            self.global_thread_pool.shutdown(wait=True, timeout=timeout)
        else:
            self.global_thread_pool.shutdown(wait=False)


def get_job_manager(max_workers: int = 100) -> GlobalJobManager:
    """Get or create global job manager instance.
    
    Args:
        max_workers: Maximum workers (only used on first call).
    
    Returns:
        GlobalJobManager instance.
    """
    global _global_job_manager
    
    if _global_job_manager is None:
        with _global_job_manager_lock:
            if _global_job_manager is None:
                _global_job_manager = GlobalJobManager(max_workers=max_workers)
    
    return _global_job_manager
```

**验收标准**:
- [ ] 单例模式线程安全
- [ ] 全局线程池正确创建
- [ ] job注册和查询功能正常
- [ ] shutdown功能正确

---

#### Step 1.2: 创建JobExecutor模块

**文件**: `routilux/job_executor.py` (新建)

**任务**:
1. 创建`JobExecutor`类
2. 实现独立的task queue和event loop
3. 实现任务执行逻辑
4. 实现暂停/恢复/取消功能
5. 实现超时处理
6. 实现完成检测和清理

**具体实现要求**:

```python
"""
Job executor for managing individual job execution context.

Each job has its own JobExecutor instance with:
- Independent task queue
- Independent event loop thread
- Reference to global thread pool
"""

import logging
import queue
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from concurrent.futures import ThreadPoolExecutor
    from routilux.flow.flow import Flow
    from routilux.flow.task import SlotActivationTask
    from routilux.job_state import JobState

logger = logging.getLogger(__name__)


class JobExecutor:
    """Manages execution context for a single job."""
    
    def __init__(
        self,
        flow: "Flow",
        job_state: "JobState",
        global_thread_pool: "ThreadPoolExecutor",
        timeout: float | None = None,
    ):
        """Initialize job executor.
        
        Args:
            flow: Flow to execute.
            job_state: JobState for this execution.
            global_thread_pool: Global thread pool to use.
            timeout: Execution timeout in seconds.
        """
        self.flow = flow
        self.job_state = job_state
        self.global_thread_pool = global_thread_pool
        self.timeout = timeout
        
        # Independent execution context
        self.task_queue = queue.Queue()
        self.pending_tasks: list["SlotActivationTask"] = []
        self.event_loop_thread: Optional[threading.Thread] = None
        self.active_tasks: set = set()
        self._running = False
        self._paused = False
        self._lock = threading.Lock()
        self._start_time: Optional[float] = None
        
        # Execution tracker (one per job)
        from routilux.execution_tracker import ExecutionTracker
        self.execution_tracker: Optional[ExecutionTracker] = None
        
        # Set flow context for routines
        for routine in flow.routines.values():
            routine._current_flow = flow
    
    def start(self, entry_routine_id: str, entry_params: dict):
        """Start job execution.
        
        Args:
            entry_routine_id: Entry routine identifier.
            entry_params: Entry parameters.
        
        Raises:
            ValueError: If entry routine not found or no trigger slot.
        """
        from routilux.status import ExecutionStatus
        
        if entry_routine_id not in self.flow.routines:
            raise ValueError(f"Entry routine '{entry_routine_id}' not found")
        
        entry_routine = self.flow.routines[entry_routine_id]
        trigger_slot = entry_routine.get_slot("trigger")
        
        if trigger_slot is None:
            raise ValueError(
                f"Entry routine '{entry_routine_id}' must have 'trigger' slot"
            )
        
        # Update job state
        self.job_state.status = ExecutionStatus.RUNNING
        self.job_state.current_routine_id = entry_routine_id
        self._start_time = time.time()
        
        # Record execution start
        self.job_state.record_execution(entry_routine_id, "start", entry_params)
        
        # Create execution tracker (one per job)
        from routilux.execution_tracker import ExecutionTracker
        self.execution_tracker = ExecutionTracker(self.flow.flow_id)
        self.execution_tracker.record_routine_start(entry_routine_id, entry_params)
        
        # Monitoring hook
        from routilux.monitoring.hooks import execution_hooks
        execution_hooks.on_flow_start(self.flow, self.job_state)
        
        # Start event loop
        self._running = True
        self.event_loop_thread = threading.Thread(
            target=self._event_loop,
            daemon=True,
            name=f"JobExecutor-{self.job_state.job_id[:8]}"
        )
        self.event_loop_thread.start()
        
        # Trigger entry routine
        self._trigger_entry(entry_routine_id, entry_params)
    
    def _event_loop(self):
        """Event loop main logic."""
        while self._running:
            try:
                # Check timeout
                if self.timeout is not None and self._start_time is not None:
                    elapsed = time.time() - self._start_time
                    if elapsed >= self.timeout:
                        logger.warning(
                            f"Job {self.job_state.job_id} timed out after {self.timeout}s"
                        )
                        self._handle_timeout()
                        break
                
                # Check if paused
                if self._paused:
                    time.sleep(0.01)
                    continue
                
                # Get task from queue
                try:
                    task = self.task_queue.get(timeout=0.1)
                except queue.Empty:
                    # Check if complete
                    if self._is_complete():
                        self._handle_completion()
                        break
                    continue
                
                # Submit to global thread pool
                future = self.global_thread_pool.submit(
                    self._execute_task, task
                )
                
                with self._lock:
                    self.active_tasks.add(future)
                
                def on_done(fut=future):
                    with self._lock:
                        self.active_tasks.discard(fut)
                    self.task_queue.task_done()
                
                future.add_done_callback(on_done)
                
            except Exception as e:
                logger.exception(f"Error in event loop for job {self.job_state.job_id}: {e}")
                self._handle_error(e)
                break
        
        # Cleanup
        self._cleanup()
    
    def _execute_task(self, task: "SlotActivationTask"):
        """Execute a single task.
        
        Args:
            task: SlotActivationTask to execute.
        """
        from routilux.routine import _current_job_state
        
        # Set job_state in context
        old_job_state = _current_job_state.get(None)
        _current_job_state.set(self.job_state)
        
        try:
            # Apply parameter mapping if connection exists
            if task.connection:
                mapped_data = task.connection._apply_mapping(task.data)
            else:
                mapped_data = task.data
            
            # Set routine._current_flow for slot.receive()
            if task.slot.routine:
                task.slot.routine._current_flow = self.flow
            
            # Execute slot handler
            # Note: slot.receive() internally calls monitoring hooks
            # (on_routine_start, on_slot_call, on_routine_end)
            # So we don't need to call them here
            task.slot.receive(
                mapped_data,
                job_state=self.job_state,
                flow=self.flow
            )
            
        except Exception as e:
            from routilux.flow.error_handling import handle_task_error
            handle_task_error(task, e, self.flow)
        finally:
            # Restore context
            if old_job_state is not None:
                _current_job_state.set(old_job_state)
            else:
                _current_job_state.set(None)
    
    def _trigger_entry(self, entry_routine_id: str, entry_params: dict):
        """Trigger entry routine.
        
        Args:
            entry_routine_id: Entry routine identifier.
            entry_params: Entry parameters.
        """
        entry_routine = self.flow.routines[entry_routine_id]
        trigger_slot = entry_routine.get_slot("trigger")
        
        from routilux.flow.task import SlotActivationTask
        task = SlotActivationTask(
            slot=trigger_slot,
            data=entry_params,
            job_state=self.job_state,
            connection=None,
        )
        
        self.enqueue_task(task)
    
    def enqueue_task(self, task: "SlotActivationTask"):
        """Enqueue a task for execution.
        
        Args:
            task: SlotActivationTask to enqueue.
        """
        if self._paused:
            self.pending_tasks.append(task)
        else:
            self.task_queue.put(task)
    
    def _is_complete(self) -> bool:
        """Check if job is complete.
        
        Returns:
            True if queue is empty and no active tasks.
        """
        if not self.task_queue.empty():
            return False
        
        with self._lock:
            active = [f for f in self.active_tasks if not f.done()]
            return len(active) == 0
    
    def _handle_completion(self):
        """Handle job completion."""
        from routilux.status import ExecutionStatus
        from routilux.monitoring.hooks import execution_hooks
        
        if self.job_state.status != ExecutionStatus.FAILED:
            self.job_state.status = ExecutionStatus.COMPLETED
            
            # Record execution end
            if self.execution_tracker:
                entry_routine_id = self.job_state.current_routine_id
                if entry_routine_id:
                    self.execution_tracker.record_routine_end(entry_routine_id, "completed")
            
            execution_hooks.on_flow_end(self.flow, self.job_state, "completed")
    
    def _handle_timeout(self):
        """Handle job timeout."""
        from routilux.status import ExecutionStatus
        from routilux.monitoring.hooks import execution_hooks
        
        self.job_state.status = ExecutionStatus.FAILED
        self.job_state.shared_data["error"] = f"Job timed out after {self.timeout}s"
        execution_hooks.on_flow_end(self.flow, self.job_state, "failed")
    
    def _handle_error(self, error: Exception):
        """Handle job error.
        
        Args:
            error: Exception that occurred.
        """
        from routilux.status import ExecutionStatus
        from routilux.monitoring.hooks import execution_hooks
        
        self.job_state.status = ExecutionStatus.FAILED
        if "error" not in self.job_state.shared_data:
            self.job_state.shared_data["error"] = str(error)
        
        # Record execution end
        if self.execution_tracker:
            entry_routine_id = self.job_state.current_routine_id
            if entry_routine_id:
                self.execution_tracker.record_routine_end(entry_routine_id, "failed", error=str(error))
        
        execution_hooks.on_flow_end(self.flow, self.job_state, "failed")
    
    def _cleanup(self):
        """Cleanup job executor."""
        self._running = False
        
        # Remove from global job manager
        from routilux.job_manager import get_job_manager
        job_manager = get_job_manager()
        with job_manager._lock:
            job_manager.running_jobs.pop(self.job_state.job_id, None)
    
    def pause(self, reason: str = "", checkpoint: dict | None = None):
        """Pause job execution.
        
        Args:
            reason: Reason for pausing.
            checkpoint: Optional checkpoint data.
        """
        from routilux.flow.state_management import pause_job_executor
        pause_job_executor(self, reason, checkpoint)
    
    def resume(self) -> "JobState":
        """Resume job execution.
        
        Returns:
            Updated JobState.
        """
        from routilux.flow.state_management import resume_job_executor
        return resume_job_executor(self)
    
    def cancel(self, reason: str = ""):
        """Cancel job execution.
        
        Args:
            reason: Reason for cancellation.
        """
        from routilux.flow.state_management import cancel_job_executor
        cancel_job_executor(self, reason)
    
    def is_running(self) -> bool:
        """Check if job is running.
        
        Returns:
            True if running, False otherwise.
        """
        return self._running and not self._is_complete()
    
    def stop(self):
        """Stop job execution."""
        self._running = False
        if self.event_loop_thread:
            self.event_loop_thread.join(timeout=1.0)
```

**验收标准**:
- [ ] 独立的task queue和event loop
- [ ] 任务正确执行
- [ ] 超时处理正确
- [ ] 完成检测正确
- [ ] 清理逻辑正确

---

### Phase 2: 修改emit()路由机制

#### Step 2.1: 修改Event.emit()方法

**文件**: `routilux/event.py`

**任务**:
1. 修改`emit()`方法，使其路由到正确的JobExecutor
2. 通过JobState找到对应的JobExecutor
3. 如果找不到JobExecutor，使用legacy模式（直接调用）

**具体实现要求**:

```python
def emit(self, flow: "Flow" | None = None, **kwargs) -> None:
    """Emit the event and send data to all connected slots.
    
    Modified to route tasks to JobExecutor instead of Flow.
    """
    # Auto-detect flow from routine context if not provided
    if flow is None and self.routine:
        flow = getattr(self.routine, "_current_flow", None)
    
    # Get job_state from context
    from routilux.routine import _current_job_state
    job_state = _current_job_state.get(None)
    
    # If we have job_state, route to JobExecutor
    if job_state is not None and flow is not None:
        from routilux.job_manager import get_job_manager
        job_manager = get_job_manager()
        executor = job_manager.get_job(job_state.job_id)
        
        if executor is not None:
            # Route to JobExecutor
            for slot in self.connected_slots:
                connection = flow._find_connection(self, slot)
                from routilux.flow.task import SlotActivationTask
                task = SlotActivationTask(
                    slot=slot,
                    data=kwargs,
                    job_state=job_state,
                    connection=connection,
                )
                executor.enqueue_task(task)
            return
    
    # Legacy mode: direct call (no flow or no job_state)
    if flow is None:
        for slot in self.connected_slots:
            slot.receive(**kwargs)
        return
    
    # Fallback: use Flow's enqueue (for backward compatibility during transition)
    # This should not happen in new architecture
    logger.warning(
        f"emit() called with flow but no job_state context. "
        f"Using legacy mode. Event: {self.name}"
    )
    for slot in self.connected_slots:
        connection = flow._find_connection(self, slot)
        from routilux.flow.task import SlotActivationTask
        task = SlotActivationTask(
            slot=slot,
            data=kwargs,
            job_state=None,  # No job_state in legacy mode
            connection=connection,
        )
        flow._enqueue_task(task)  # Legacy method
```

**验收标准**:
- [ ] emit()正确路由到JobExecutor
- [ ] 如果没有job_state，使用legacy模式
- [ ] 所有测试通过

---

#### Step 2.2: 移除Flow._enqueue_task()方法（或标记为deprecated）

**文件**: `routilux/flow/flow.py`

**任务**:
1. 移除`_enqueue_task()`方法（因为不再需要）
2. 或者标记为deprecated并保留用于legacy模式

**具体实现要求**:

```python
# 移除或标记为deprecated
def _enqueue_task(self, task: SlotActivationTask) -> None:
    """Enqueue task (DEPRECATED - use JobExecutor.enqueue_task instead).
    
    This method is kept for legacy compatibility only.
    New code should use JobExecutor.enqueue_task().
    """
    import warnings
    warnings.warn(
        "Flow._enqueue_task() is deprecated. "
        "Use JobExecutor.enqueue_task() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    # Legacy implementation - should not be used in new code
    from routilux.flow.event_loop import enqueue_task
    enqueue_task(task, self)
```

**验收标准**:
- [ ] 方法标记为deprecated
- [ ] 不影响现有legacy代码

---

### Phase 3: 实现暂停/恢复/取消功能

#### Step 3.1: 创建JobExecutor状态管理模块

**文件**: `routilux/flow/job_state_management.py` (新建)

**任务**:
1. 实现`pause_job_executor()`函数
2. 实现`resume_job_executor()`函数
3. 实现`cancel_job_executor()`函数
4. 实现任务序列化/反序列化

**具体实现要求**:

```python
"""
State management for JobExecutor (pause, resume, cancel).

This module handles job-level state management, replacing
Flow-level state management.
"""

import logging
import queue
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from routilux.job_executor import JobExecutor
    from routilux.job_state import JobState

logger = logging.getLogger(__name__)


def pause_job_executor(
    executor: "JobExecutor",
    reason: str = "",
    checkpoint: Optional[Dict[str, Any]] = None,
) -> None:
    """Pause job execution.
    
    Args:
        executor: JobExecutor to pause.
        reason: Reason for pausing.
        checkpoint: Optional checkpoint data.
    """
    executor._paused = True
    
    # Wait for active tasks
    _wait_for_active_tasks(executor)
    
    # Drain task queue
    max_wait = 2.0
    start_time = time.time()
    while not executor.task_queue.empty():
        if time.time() - start_time > max_wait:
            logger.warning(
                f"pause_job_executor: Timeout draining task queue. "
                f"Queue size: {executor.task_queue.qsize()}"
            )
            break
        try:
            task = executor.task_queue.get(timeout=0.1)
            executor.pending_tasks.append(task)
        except queue.Empty:
            break
    
    # Record pause point
    pause_point = {
        "timestamp": datetime.now().isoformat(),
        "reason": reason,
        "checkpoint": checkpoint or {},
        "pending_tasks_count": len(executor.pending_tasks),
        "active_tasks_count": len(executor.active_tasks),
        "queue_size": executor.task_queue.qsize(),
    }
    
    executor.job_state.pause_points.append(pause_point)
    executor.job_state._set_paused(reason=reason, checkpoint=checkpoint)
    
    # Serialize pending tasks
    _serialize_pending_tasks(executor)


def resume_job_executor(executor: "JobExecutor") -> "JobState":
    """Resume job execution.
    
    Args:
        executor: JobExecutor to resume.
    
    Returns:
        Updated JobState.
    """
    if executor.job_state.flow_id != executor.flow.flow_id:
        raise ValueError(
            f"JobState flow_id '{executor.job_state.flow_id}' "
            f"does not match Flow flow_id '{executor.flow.flow_id}'"
        )
    
    executor.job_state._set_running()
    executor._paused = False
    
    # Deserialize pending tasks
    _deserialize_pending_tasks(executor)
    
    # Restart event loop if needed
    if not executor._running or not executor.event_loop_thread.is_alive():
        executor._running = True
        executor.event_loop_thread = threading.Thread(
            target=executor._event_loop,
            daemon=True,
            name=f"JobExecutor-{executor.job_state.job_id[:8]}"
        )
        executor.event_loop_thread.start()
    
    return executor.job_state


def cancel_job_executor(executor: "JobExecutor", reason: str = "") -> None:
    """Cancel job execution.
    
    Args:
        executor: JobExecutor to cancel.
        reason: Reason for cancellation.
    """
    executor._running = False
    executor._paused = False
    
    # Cancel active tasks
    with executor._lock:
        for future in list(executor.active_tasks):
            if not future.done():
                future.cancel()
        executor.active_tasks.clear()
    
    executor.job_state._set_cancelled(reason=reason)


def _wait_for_active_tasks(executor: "JobExecutor") -> None:
    """Wait for all active tasks to complete."""
    check_interval = 0.05
    max_wait_time = 5.0
    start_time = time.time()
    
    while True:
        with executor._lock:
            active = [f for f in executor.active_tasks if not f.done()]
            if not active:
                break
        
        elapsed = time.time() - start_time
        if elapsed > max_wait_time:
            logger.warning(
                f"wait_for_active_tasks timed out after {max_wait_time}s. "
                f"Active tasks: {len(active)}"
            )
            break
        
        time.sleep(check_interval)


def _serialize_pending_tasks(executor: "JobExecutor") -> None:
    """Serialize pending tasks to JobState.
    
    Args:
        executor: JobExecutor to serialize tasks from.
    """
    serialized_tasks = []
    for task in executor.pending_tasks:
        # Find routine_id in flow (not routine._id)
        routine_id = None
        if task.slot.routine:
            for rid, r in executor.flow.routines.items():
                if r is task.slot.routine:
                    routine_id = rid
                    break
        
        connection = task.connection
        serialized = {
            "routine_id": routine_id,  # Flow's routine_id
            "slot_name": task.slot.name,
            "data": task.data,
            "connection_source_routine_id": (
                flow._get_routine_id(connection.source_event.routine)
                if connection and connection.source_event and connection.source_event.routine
                else None
            ),
            "connection_source_event_name": (
                connection.source_event.name if connection and connection.source_event else None
            ),
            "connection_target_routine_id": (
                flow._get_routine_id(connection.target_slot.routine)
                if connection and connection.target_slot and connection.target_slot.routine
                else None
            ),
            "connection_target_slot_name": (
                connection.target_slot.name if connection and connection.target_slot else None
            ),
            "param_mapping": connection.param_mapping if connection else {},
            "priority": task.priority.value,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "created_at": task.created_at.isoformat() if task.created_at else None,
        }
        serialized_tasks.append(serialized)
    
    executor.job_state.pending_tasks = serialized_tasks


def _deserialize_pending_tasks(executor: "JobExecutor") -> None:
    """Deserialize pending tasks from JobState.
    
    Args:
        executor: JobExecutor to deserialize tasks to.
    """
    if not executor.job_state.pending_tasks:
        return
    
    from routilux.flow.task import SlotActivationTask, TaskPriority
    from datetime import datetime
    
    executor.pending_tasks = []
    for serialized in executor.job_state.pending_tasks:
        routine_id = serialized.get("routine_id")
        slot_name = serialized.get("slot_name")
        
        if not routine_id or routine_id not in executor.flow.routines:
            continue
        
        routine = executor.flow.routines[routine_id]
        slot = routine.get_slot(slot_name)
        if not slot:
            continue
        
        # Reconstruct connection
        connection = None
        if serialized.get("connection_source_routine_id"):
            source_routine_id = serialized.get("connection_source_routine_id")
            source_event_name = serialized.get("connection_source_event_name")
            target_routine_id = serialized.get("connection_target_routine_id")
            target_slot_name = serialized.get("connection_target_slot_name")
            
            if (source_routine_id in executor.flow.routines and 
                target_routine_id in executor.flow.routines):
                source_routine = executor.flow.routines[source_routine_id]
                target_routine = executor.flow.routines[target_routine_id]
                source_event = (
                    source_routine.get_event(source_event_name) if source_event_name else None
                )
                target_slot = (
                    target_routine.get_slot(target_slot_name) if target_slot_name else None
                )
                
                if source_event and target_slot:
                    connection = executor.flow._find_connection(source_event, target_slot)
        
        task = SlotActivationTask(
            slot=slot,
            data=serialized.get("data", {}),
            connection=connection,
            priority=TaskPriority(serialized.get("priority", TaskPriority.NORMAL.value)),
            retry_count=serialized.get("retry_count", 0),
            max_retries=serialized.get("max_retries", 0),
            created_at=(
                datetime.fromisoformat(serialized["created_at"])
                if serialized.get("created_at")
                else None
            ),
            job_state=executor.job_state,
        )
        
        executor.pending_tasks.append(task)
        
        # Enqueue task
        executor.enqueue_task(task)
```

**验收标准**:
- [ ] 暂停功能正确
- [ ] 恢复功能正确
- [ ] 取消功能正确
- [ ] 任务序列化/反序列化正确

---

### Phase 4: 修改Flow类

#### Step 4.1: 移除Flow中的执行状态字段

**文件**: `routilux/flow/flow.py`

**任务**:
1. 从`__init__()`中移除执行状态字段
2. 从`add_serializable_fields()`中移除执行状态字段
3. 移除`_get_executor()`方法
4. 移除`set_execution_strategy()`中的executor创建逻辑

**具体实现要求**:

```python
def __init__(
    self,
    flow_id: str | None = None,
    execution_strategy: str = "sequential",
    max_workers: int = 5,
    execution_timeout: float | None = None,
):
    """Initialize Flow.
    
    Args:
        flow_id: Flow identifier.
        execution_strategy: Execution strategy ("sequential" or "concurrent").
        max_workers: Max workers (for configuration only, not used for thread pool).
        execution_timeout: Default execution timeout.
    """
    super().__init__()
    self.flow_id: str = flow_id or str(uuid.uuid4())
    self.routines: dict[str, Routine] = {}
    self.connections: list[Connection] = []
    self.execution_tracker: ExecutionTracker | None = None
    self.error_handler: ErrorHandler | None = None
    
    # Configuration only (not execution state)
    self.execution_strategy: str = execution_strategy
    self.max_workers: int = max_workers if execution_strategy == "concurrent" else 1
    
    # Validate execution_timeout
    if execution_timeout is not None:
        if not isinstance(execution_timeout, (int, float)):
            raise TypeError(
                f"execution_timeout must be numeric, got {type(execution_timeout).__name__}"
            )
        if execution_timeout <= 0:
            raise ValueError(
                f"execution_timeout must be positive, got {execution_timeout}"
            )
    
    self.execution_timeout: float | None = (
        execution_timeout if execution_timeout is not None else 300.0
    )
    
    # ❌ REMOVED: All execution state fields
    # self._task_queue = queue.Queue()  # REMOVED
    # self._pending_tasks: list[SlotActivationTask] = []  # REMOVED
    # self._execution_thread: threading.Thread | None = None  # REMOVED
    # self._execution_lock: threading.Lock = threading.Lock()  # REMOVED
    # self._running: bool = False  # REMOVED
    # self._executor: ThreadPoolExecutor | None = None  # REMOVED
    # self._active_tasks: set[Future] = set()  # REMOVED
    # self._paused: bool = False  # REMOVED
    
    # Serializable fields (only structure, no execution state)
    self.add_serializable_fields(
        [
            "flow_id",
            "execution_strategy",
            "max_workers",
            "execution_timeout",
            "error_handler",
            "routines",
            "connections",
        ]
    )
    
    self._event_slot_connections: dict[tuple, Connection] = {}
```

**验收标准**:
- [ ] 所有执行状态字段已移除
- [ ] 序列化字段列表已更新
- [ ] Flow完全静态

---

#### Step 4.2: 修改Flow.start()方法

**文件**: `routilux/flow/flow.py`

**任务**:
1. 修改`start()`方法使用GlobalJobManager
2. 确保方法签名正确

**具体实现要求**:

```python
def start(
    self,
    entry_routine_id: str,
    entry_params: dict[str, Any] | None = None,
    timeout: float | None = None,
    job_state: JobState | None = None,
) -> JobState:
    """Start flow execution asynchronously.
    
    This method starts execution and returns immediately with a JobState.
    Execution continues in background using GlobalJobManager.
    
    Args:
        entry_routine_id: Entry routine identifier.
        entry_params: Entry parameters.
        timeout: Execution timeout.
        job_state: Optional existing JobState.
    
    Returns:
        JobState (status will be RUNNING initially).
    
    Raises:
        ValueError: If entry_routine_id not found.
    """
    from routilux.job_manager import get_job_manager
    
    job_manager = get_job_manager()
    return job_manager.start_job(
        flow=self,
        entry_routine_id=entry_routine_id,
        entry_params=entry_params,
        timeout=timeout,
        job_state=job_state,
    )
```

**验收标准**:
- [ ] start()方法正确使用GlobalJobManager
- [ ] 立即返回JobState
- [ ] 执行在后台进行

---

#### Step 4.3: 修改Flow.pause()、resume()、cancel()方法

**文件**: `routilux/flow/flow.py`

**任务**:
1. 修改这些方法使用JobExecutor
2. 通过JobState找到JobExecutor

**具体实现要求**:

```python
def pause(self, job_state: JobState, reason: str = "", checkpoint: dict[str, Any] | None = None) -> None:
    """Pause job execution.
    
    Args:
        job_state: JobState to pause.
        reason: Reason for pausing.
        checkpoint: Optional checkpoint data.
    
    Raises:
        ValueError: If job_state flow_id doesn't match.
    """
    if job_state.flow_id != self.flow_id:
        raise ValueError(
            f"JobState flow_id '{job_state.flow_id}' does not match Flow flow_id '{self.flow_id}'"
        )
    
    from routilux.job_manager import get_job_manager
    job_manager = get_job_manager()
    executor = job_manager.get_job(job_state.job_id)
    
    if executor is None:
        raise ValueError(f"Job {job_state.job_id} is not running")
    
    executor.pause(reason=reason, checkpoint=checkpoint)


def resume(self, job_state: JobState) -> JobState:
    """Resume job execution.
    
    Args:
        job_state: JobState to resume.
    
    Returns:
        Updated JobState.
    
    Raises:
        ValueError: If job_state flow_id doesn't match or job not found.
    """
    if job_state.flow_id != self.flow_id:
        raise ValueError(
            f"JobState flow_id '{job_state.flow_id}' does not match Flow flow_id '{self.flow_id}'"
        )
    
    from routilux.job_manager import get_job_manager
    job_manager = get_job_manager()
    executor = job_manager.get_job(job_state.job_id)
    
    if executor is None:
        # Job not running, start it
        return job_manager.start_job(
            flow=self,
            entry_routine_id=job_state.current_routine_id or "",
            job_state=job_state,
        )
    
    return executor.resume()


def cancel(self, job_state: JobState, reason: str = "") -> None:
    """Cancel job execution.
    
    Args:
        job_state: JobState to cancel.
        reason: Reason for cancellation.
    
    Raises:
        ValueError: If job_state flow_id doesn't match.
    """
    if job_state.flow_id != self.flow_id:
        raise ValueError(
            f"JobState flow_id '{job_state.flow_id}' does not match Flow flow_id '{self.flow_id}'"
        )
    
    from routilux.job_manager import get_job_manager
    job_manager = get_job_manager()
    executor = job_manager.get_job(job_state.job_id)
    
    if executor is None:
        # Job not running, just mark as cancelled
        from routilux.status import ExecutionStatus
        job_state.status = ExecutionStatus.CANCELLED
        return
    
    executor.cancel(reason=reason)
```

**验收标准**:
- [ ] pause()正确工作
- [ ] resume()正确工作
- [ ] cancel()正确工作

---

#### Step 4.4: 移除Flow中不再需要的方法

**文件**: `routilux/flow/flow.py`

**任务**:
1. 移除`_get_executor()`方法
2. 移除`set_execution_strategy()`中的executor创建逻辑
3. 移除`wait_for_completion()`方法（已deprecated）
4. 移除`shutdown()`方法（不再需要）

**具体实现要求**:

```python
# ❌ REMOVE: _get_executor() method
# ❌ REMOVE: set_execution_strategy() executor creation logic
# ❌ REMOVE: wait_for_completion() method (already deprecated)
# ❌ REMOVE: shutdown() method

# ✅ KEEP: set_execution_strategy() for configuration only
def set_execution_strategy(self, strategy: str, max_workers: int | None = None) -> None:
    """Set execution strategy (configuration only).
    
    Args:
        strategy: Execution strategy.
        max_workers: Max workers (configuration only).
    """
    if strategy not in ["sequential", "concurrent"]:
        raise ValueError(
            f"Invalid execution strategy: {strategy}. Must be 'sequential' or 'concurrent'"
        )
    
    self.execution_strategy = strategy
    if strategy == "sequential":
        self.max_workers = 1
    elif max_workers is not None:
        self.max_workers = max_workers
    else:
        self.max_workers = 5
    
    # ❌ REMOVED: Executor creation logic
    # Thread pool is now managed by GlobalJobManager
```

**验收标准**:
- [ ] 所有不需要的方法已移除
- [ ] set_execution_strategy()只用于配置

---

### Phase 5: 修改执行相关模块

#### Step 5.1: 修改execute_sequential()和execute_concurrent()

**文件**: `routilux/flow/execution.py`

**任务**:
1. 修改这些函数使用JobExecutor
2. 或者标记为deprecated（如果不再需要）

**具体实现要求**:

由于用户说不需要向后兼容，我们可以：
- **选项A**: 完全移除execute()相关函数（如果不再需要同步执行）
- **选项B**: 保留但重构为使用JobExecutor（如果需要同步执行）

**建议采用选项B**，因为同步执行在某些场景下仍然有用：

```python
def execute_sequential(
    flow: "Flow",
    entry_routine_id: str,
    entry_params: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None,
    job_state: Optional["JobState"] = None,
) -> "JobState":
    """Execute flow synchronously (waits for completion).
    
    This method uses JobExecutor but waits for completion.
    For async execution, use flow.start() instead.
    
    Args:
        flow: Flow to execute.
        entry_routine_id: Entry routine identifier.
        entry_params: Entry parameters.
        timeout: Execution timeout.
        job_state: Optional existing JobState.
    
    Returns:
        JobState (completed or failed).
    """
    from routilux.job_manager import get_job_manager
    from routilux.job_state import JobState as JobStateClass
    
    job_manager = get_job_manager()
    
    # Start job
    if job_state is None:
        job_state = JobStateClass(flow.flow_id)
    
    started_job_state = job_manager.start_job(
        flow=flow,
        entry_routine_id=entry_routine_id,
        entry_params=entry_params,
        timeout=timeout,
        job_state=job_state,
    )
    
    # Wait for completion
    executor = job_manager.get_job(started_job_state.job_id)
    if executor:
        # Wait for event loop to complete
        if executor.event_loop_thread:
            executor.event_loop_thread.join(timeout=timeout)
    
    return started_job_state
```

**验收标准**:
- [ ] execute_sequential()使用JobExecutor
- [ ] 同步等待完成
- [ ] 所有测试通过

---

#### Step 5.2: 修改error_handling.py

**文件**: `routilux/flow/error_handling.py`

**任务**:
1. 修改`handle_task_error()`函数，使其路由retry任务到JobExecutor
2. 移除对`flow._running`的引用（改为JobExecutor）
3. 确保错误处理正确更新JobState

**具体实现要求**:

```python
def handle_task_error(
    task: "SlotActivationTask",
    error: Exception,
    flow: "Flow",
) -> None:
    """Handle task execution error.
    
    Modified to route retry tasks to JobExecutor instead of Flow.
    """
    # ... existing error handling logic ...
    
    if error_handler:
        should_retry = error_handler.handle_error(
            error, routine, routine_id, flow, job_state=task.job_state
        )
        
        if error_handler.strategy.value == "retry":
            if should_retry:
                max_retries = (
                    error_handler.max_retries if error_handler.max_retries > 0 else task.max_retries
                )
                if task.retry_count < max_retries:
                    from routilux.flow.task import SlotActivationTask
                    
                    retry_task = SlotActivationTask(
                        slot=task.slot,
                        data=task.data,
                        connection=task.connection,
                        priority=task.priority,
                        retry_count=task.retry_count + 1,
                        max_retries=max_retries,
                        job_state=task.job_state,
                    )
                    
                    # Route to JobExecutor instead of flow._enqueue_task()
                    if task.job_state:
                        from routilux.job_manager import get_job_manager
                        job_manager = get_job_manager()
                        executor = job_manager.get_job(task.job_state.job_id)
                        if executor:
                            executor.enqueue_task(retry_task)
                            return
                    
                    # Fallback: if no executor found, mark job as failed
                    if task.job_state:
                        from routilux.status import ExecutionStatus
                        task.job_state.status = ExecutionStatus.FAILED
                    return
        
        # ... other error handling strategies ...
    
    # Update JobState on failure
    if task.job_state:
        from routilux.status import ExecutionStatus
        task.job_state.status = ExecutionStatus.FAILED
        if routine_id:
            task.job_state.update_routine_state(
                routine_id, {"status": "failed", "error": str(error)}
            )
    
    # Stop JobExecutor instead of flow._running
    if task.job_state:
        from routilux.job_manager import get_job_manager
        job_manager = get_job_manager()
        executor = job_manager.get_job(task.job_state.job_id)
        if executor:
            executor._running = False
```

**验收标准**:
- [ ] retry任务正确路由到JobExecutor
- [ ] 错误处理正确更新JobState
- [ ] 不再引用flow._running

---

#### Step 5.3: 移除或修改event_loop.py

**文件**: `routilux/flow/event_loop.py`

**任务**:
1. 移除`start_event_loop()`函数（不再需要）
2. 移除`event_loop()`函数（移到JobExecutor中）
3. 保留`enqueue_task()`用于legacy兼容（标记为deprecated）
4. 保留`execute_task()`函数（JobExecutor会使用）

**具体实现要求**:

```python
# ❌ REMOVE: start_event_loop() function
# ❌ REMOVE: event_loop() function (moved to JobExecutor)

# ✅ KEEP: execute_task() for JobExecutor to use
def execute_task(task: "SlotActivationTask", flow: "Flow") -> None:
    """Execute a single task (used by JobExecutor).
    
    Args:
        task: SlotActivationTask to execute.
        flow: Flow object.
    """
    # Implementation remains the same
    # But this is now called by JobExecutor._execute_task()
    pass


# ⚠️ DEPRECATED: enqueue_task() for legacy compatibility
def enqueue_task(task: "SlotActivationTask", flow: "Flow") -> None:
    """Enqueue task (DEPRECATED - use JobExecutor.enqueue_task instead).
    
    This function is kept for legacy compatibility only.
    """
    import warnings
    warnings.warn(
        "enqueue_task() is deprecated. Use JobExecutor.enqueue_task() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    # Legacy implementation
    if flow._paused:
        flow._pending_tasks.append(task)
    else:
        flow._task_queue.put(task)
```

**验收标准**:
- [ ] 不需要的函数已移除
- [ ] execute_task()保留
- [ ] enqueue_task()标记为deprecated

---

#### Step 5.4: 移除或修改completion.py

**文件**: `routilux/flow/completion.py`

**任务**:
1. 移除`ensure_event_loop_running()`（不再需要）
2. 移除`wait_for_event_loop_completion()`（移到JobExecutor中）
3. 或者保留但标记为deprecated

**具体实现要求**:

```python
# ❌ REMOVE: ensure_event_loop_running() function
# ❌ REMOVE: wait_for_event_loop_completion() function

# These functions are no longer needed because:
# - Event loop is managed by JobExecutor
# - Completion is detected by JobExecutor._is_complete()
```

**验收标准**:
- [ ] 不需要的函数已移除

---

### Phase 6: 处理ExecutionTracker

#### Step 6.1: 移除Flow中的ExecutionTracker

**文件**: `routilux/flow/flow.py`

**任务**:
1. 从Flow.__init__()中移除`self.execution_tracker`
2. ExecutionTracker现在在JobExecutor中管理

**具体实现要求**:

```python
def __init__(self, ...):
    # ... existing code ...
    
    # ❌ REMOVED: ExecutionTracker from Flow
    # self.execution_tracker: ExecutionTracker | None = None  # REMOVED
    
    # ExecutionTracker is now managed by JobExecutor (one per job)
```

**验收标准**:
- [ ] Flow中不再有execution_tracker字段
- [ ] 所有对flow.execution_tracker的引用已更新

---

#### Step 6.2: 更新execute_sequential()中的ExecutionTracker引用

**文件**: `routilux/flow/execution.py`

**任务**:
1. 移除`flow.execution_tracker`的创建和使用
2. ExecutionTracker在JobExecutor中管理

**具体实现要求**:

```python
def execute_sequential(...):
    # ... existing code ...
    
    # ❌ REMOVED: ExecutionTracker creation
    # flow.execution_tracker = ExecutionTracker(flow.flow_id)  # REMOVED
    
    # ExecutionTracker is now created in JobExecutor.start()
```

**验收标准**:
- [ ] 不再在execute_sequential()中创建ExecutionTracker
- [ ] 所有ExecutionTracker操作在JobExecutor中

---

### Phase 7: 更新API路由

#### Step 6.1: 更新jobs.py API路由

**文件**: `routilux/api/routes/jobs.py`

**任务**:
1. 更新`start_job()`使用新的架构
2. 更新`pause_job()`, `resume_job()`, `cancel_job()`使用JobExecutor

**具体实现要求**:

```python
@router.post("/jobs", response_model=JobResponse, status_code=201)
async def start_job(request: JobStartRequest):
    """Start a new job from a flow."""
    flow = flow_store.get(request.flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{request.flow_id}' not found")
    
    MonitoringRegistry.enable()
    
    # Use flow.start() which uses GlobalJobManager
    try:
        job_state = flow.start(
            entry_routine_id=request.entry_routine_id,
            entry_params=request.entry_params,
            timeout=request.timeout,
        )
        
        job_store.add(job_state)
        return _job_to_response(job_state)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to start job: {str(e)}") from e


@router.post("/jobs/{job_id}/pause", status_code=200)
async def pause_job(job_id: str):
    """Pause job execution."""
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    flow = flow_store.get(job_state.flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{job_state.flow_id}' not found")
    
    try:
        flow.pause(job_state, reason="Paused via API")
        return {"status": "paused", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to pause job: {str(e)}") from e


@router.post("/jobs/{job_id}/resume", status_code=200)
async def resume_job(job_id: str):
    """Resume job execution."""
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    flow = flow_store.get(job_state.flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{job_state.flow_id}' not found")
    
    try:
        updated_job_state = flow.resume(job_state)
        job_store.add(updated_job_state)
        return {"status": "resumed", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to resume job: {str(e)}") from e


@router.post("/jobs/{job_id}/cancel", status_code=200)
async def cancel_job(job_id: str):
    """Cancel job execution."""
    job_state = job_store.get(job_id)
    if not job_state:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    flow = flow_store.get(job_state.flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail=f"Flow '{job_state.flow_id}' not found")
    
    try:
        flow.cancel(job_state, reason="Cancelled via API")
        return {"status": "cancelled", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to cancel job: {str(e)}") from e
```

**验收标准**:
- [ ] API路由正确使用新架构
- [ ] 所有API端点正常工作

---

### Phase 8: 测试和验证

#### Step 7.1: 创建单元测试

**文件**: `tests/test_job_manager.py` (新建)

**任务**:
1. 测试GlobalJobManager单例模式
2. 测试job启动和查询
3. 测试wait_for_all_jobs()
4. 测试shutdown()

**具体测试要求**:

```python
"""Tests for GlobalJobManager."""

import pytest
from routilux import Flow, Routine
from routilux.job_manager import get_job_manager, GlobalJobManager
from routilux.status import ExecutionStatus


class TestRoutine(Routine):
    def __init__(self):
        super().__init__()
        self.trigger_slot = self.define_slot("trigger", handler=self.handle)
        self.output_event = self.define_event("output", ["data"])
    
    def handle(self, **kwargs):
        self.emit("output", data="test")


def test_global_job_manager_singleton():
    """Test that GlobalJobManager is a singleton."""
    manager1 = get_job_manager(max_workers=50)
    manager2 = get_job_manager(max_workers=100)  # Should return same instance
    
    assert manager1 is manager2
    assert manager1.max_workers == 50  # First call's value


def test_start_job():
    """Test starting a job."""
    flow = Flow(flow_id="test_flow")
    routine = TestRoutine()
    flow.add_routine(routine, "test")
    
    manager = get_job_manager()
    job_state = manager.start_job(
        flow=flow,
        entry_routine_id="test",
        entry_params={"data": "test"}
    )
    
    assert job_state.status == ExecutionStatus.RUNNING
    assert job_state.job_id is not None
    
    # Wait for completion
    import time
    time.sleep(0.5)
    
    executor = manager.get_job(job_state.job_id)
    assert executor is not None


def test_wait_for_all_jobs():
    """Test waiting for all jobs."""
    flow = Flow(flow_id="test_flow")
    routine = TestRoutine()
    flow.add_routine(routine, "test")
    
    manager = get_job_manager()
    
    # Start multiple jobs
    job1 = manager.start_job(flow, "test")
    job2 = manager.start_job(flow, "test")
    job3 = manager.start_job(flow, "test")
    
    # Wait for all
    completed = manager.wait_for_all_jobs(timeout=5.0)
    assert completed is True
```

**验收标准**:
- [ ] 所有单元测试通过
- [ ] 测试覆盖率 > 80%

---

#### Step 7.2: 创建集成测试

**文件**: `tests/test_job_executor.py` (新建)

**任务**:
1. 测试JobExecutor基本功能
2. 测试暂停/恢复/取消
3. 测试超时处理
4. 测试多job并发执行

**具体测试要求**:

```python
"""Tests for JobExecutor."""

import pytest
import time
from routilux import Flow, Routine
from routilux.job_executor import JobExecutor
from routilux.job_manager import get_job_manager
from routilux.job_state import JobState
from routilux.status import ExecutionStatus


def test_job_executor_basic():
    """Test basic JobExecutor functionality."""
    # Create flow and job
    flow = Flow(flow_id="test")
    routine = TestRoutine()
    flow.add_routine(routine, "test")
    
    job_state = JobState(flow.flow_id)
    manager = get_job_manager()
    
    executor = JobExecutor(
        flow=flow,
        job_state=job_state,
        global_thread_pool=manager.global_thread_pool,
    )
    
    executor.start("test", {})
    
    # Wait a bit
    time.sleep(0.5)
    
    # Check status
    assert job_state.status in [ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED]


def test_job_executor_pause_resume():
    """Test pause and resume."""
    # Similar structure
    pass


def test_job_executor_timeout():
    """Test timeout handling."""
    # Similar structure
    pass


def test_multiple_jobs_concurrent():
    """Test multiple jobs running concurrently."""
    flow = Flow(flow_id="test")
    routine = TestRoutine()
    flow.add_routine(routine, "test")
    
    manager = get_job_manager()
    
    # Start 10 jobs
    jobs = []
    for i in range(10):
        job = manager.start_job(flow, "test", entry_params={"index": i})
        jobs.append(job)
    
    # Wait for all
    completed = manager.wait_for_all_jobs(timeout=10.0)
    assert completed is True
    
    # Check all completed
    for job in jobs:
        executor = manager.get_job(job.job_id)
        assert executor is None or not executor.is_running()
```

**验收标准**:
- [ ] 所有集成测试通过
- [ ] 多job并发测试通过

---

#### Step 7.3: 更新现有测试

**任务**:
1. 更新所有使用`flow.execute()`的测试
2. 更新所有使用Flow执行状态的测试
3. 确保所有测试通过

**具体要求**:
- 查找所有测试文件
- 更新测试以使用新架构
- 运行所有测试确保通过

**验收标准**:
- [ ] 所有现有测试更新
- [ ] 所有测试通过

---

### Phase 9: 文档更新

#### Step 8.1: 更新用户文档

**文件**: `docs/source/user_guide/flows.rst`

**任务**:
1. 更新Flow执行相关文档
2. 添加GlobalJobManager使用说明
3. 更新示例代码

**具体要求**:
- 更新"Working with Flows"章节
- 添加"Job Management"章节
- 更新所有示例代码

---

#### Step 8.2: 更新API文档

**文件**: `docs/source/api_reference/`

**任务**:
1. 更新Flow API文档
2. 添加GlobalJobManager API文档
3. 添加JobExecutor API文档（如果需要）

---

## 关键遗漏点补充

### 🔴 发现的关键遗漏

1. **ExecutionTracker处理**：
   - 当前ExecutionTracker在Flow级别
   - 需要移到JobExecutor级别（每个job一个）
   - 或者保持Flow级别但确保线程安全

2. **任务序列化细节**：
   - 需要实现完整的序列化/反序列化逻辑
   - 需要处理routine_id映射（从routine._id到flow.routines中的key）

3. **错误处理中的retry路由**：
   - handle_task_error()中的retry任务需要路由到正确的JobExecutor
   - 不能使用flow._enqueue_task()

4. **Monitoring hooks调用时机**：
   - 确保所有hooks在JobExecutor中正确调用
   - on_flow_start, on_flow_end, on_slot_call等

### 补充实现细节

#### ExecutionTracker处理

**决策**：ExecutionTracker应该移到JobExecutor级别，因为：
- 每个job有独立的执行历史
- 避免多job之间的数据混乱
- 更符合job级别隔离的设计

**实现**：
```python
class JobExecutor:
    def __init__(self, ...):
        # ...
        from routilux.execution_tracker import ExecutionTracker
        self.execution_tracker = ExecutionTracker(flow.flow_id)
```

#### 任务序列化实现

需要完整实现序列化/反序列化，特别注意routine_id映射：

```python
def _serialize_pending_tasks(executor: JobExecutor):
    """Serialize pending tasks to JobState."""
    serialized_tasks = []
    for task in executor.pending_tasks:
        # Find routine_id in flow (not routine._id)
        routine_id = None
        if task.slot.routine:
            for rid, r in executor.flow.routines.items():
                if r is task.slot.routine:
                    routine_id = rid
                    break
        
        serialized = {
            "routine_id": routine_id,  # Use flow's routine_id
            "slot_name": task.slot.name,
            "data": task.data,
            # ... other fields
        }
        serialized_tasks.append(serialized)
    
    executor.job_state.pending_tasks = serialized_tasks
```

#### 错误处理中的retry路由

修改handle_task_error()，使其路由到JobExecutor：

```python
def handle_task_error(task, error, flow):
    # ... error handling logic ...
    
    if should_retry:
        retry_task = SlotActivationTask(...)
        
        # Route to JobExecutor instead of flow._enqueue_task()
        if task.job_state:
            from routilux.job_manager import get_job_manager
            job_manager = get_job_manager()
            executor = job_manager.get_job(task.job_state.job_id)
            if executor:
                executor.enqueue_task(retry_task)
                return
```

## 关键注意事项

### ⚠️ 必须严格遵守的规则

1. **不允许修改JobState结构**：JobState是序列化的核心，不能改变
2. **不允许修改Routine接口**：Routine接口必须保持不变
3. **emit()必须向后兼容**：如果没有job_state，必须使用legacy模式
4. **线程安全**：所有共享资源访问必须加锁
5. **资源清理**：job完成后必须从GlobalJobManager中移除
6. **ExecutionTracker**：每个JobExecutor有独立的ExecutionTracker
7. **任务序列化**：必须使用flow.routines中的routine_id，不是routine._id

### 🔴 关键实现细节

1. **emit()路由逻辑**：
   ```python
   if job_state in context:
       route to JobExecutor
   else:
       use legacy mode (direct call)
   ```

2. **JobExecutor清理**：
   ```python
   def _cleanup(self):
       self._running = False
       # Remove from manager
       job_manager.running_jobs.pop(self.job_state.job_id, None)
   ```

3. **超时处理**：
   ```python
   if timeout and elapsed >= timeout:
       self._handle_timeout()
       break
   ```

4. **完成检测**：
   ```python
   def _is_complete(self):
       return queue.empty() and len(active_tasks) == 0
   ```

## 验收标准总结

### Phase 1-2: 基础设施
- [ ] GlobalJobManager创建并测试通过
- [ ] JobExecutor创建并测试通过
- [ ] emit()路由正确
- [ ] ExecutionTracker移到JobExecutor

### Phase 3-4: 功能实现
- [ ] 暂停/恢复/取消功能正确
- [ ] 任务序列化/反序列化正确
- [ ] Flow类清理完成
- [ ] Flow.start()正确工作

### Phase 5-6: 集成
- [ ] 执行模块更新完成
- [ ] 错误处理更新完成
- [ ] ExecutionTracker处理完成

### Phase 7-8: API和测试
- [ ] API路由更新完成
- [ ] 所有测试通过
- [ ] 多job并发测试通过

### Phase 9: 文档
- [ ] 文档更新完成

## 时间估算

- Phase 1: 2-3天
- Phase 2: 1-2天
- Phase 3: 2-3天
- Phase 4: 2-3天
- Phase 5: 2-3天
- Phase 6: 1天
- Phase 7: 1天
- Phase 8: 3-4天
- Phase 9: 1-2天

**总计**: 15-22天

## 风险控制

1. **逐步迁移**：每个Phase完成后进行测试
2. **回滚计划**：保留旧代码直到新代码完全测试通过
3. **代码审查**：每个Phase完成后进行代码审查
4. **集成测试**：每个Phase完成后运行完整测试套件

## 关键实现细节补充

### emit()路由的完整实现

**关键点**：emit()必须能够路由到正确的JobExecutor，即使在没有显式传递的情况下。

**实现逻辑**：
```python
def emit(self, flow: Flow | None = None, **kwargs):
    # 1. Auto-detect flow
    if flow is None and self.routine:
        flow = getattr(self.routine, "_current_flow", None)
    
    # 2. Get job_state from context
    from routilux.routine import _current_job_state
    job_state = _current_job_state.get(None)
    
    # 3. Route to JobExecutor if available
    if job_state is not None and flow is not None:
        from routilux.job_manager import get_job_manager
        job_manager = get_job_manager()
        executor = job_manager.get_job(job_state.job_id)
        
        if executor is not None:
            # Route to JobExecutor
            for slot in self.connected_slots:
                connection = flow._find_connection(self, slot)
                task = SlotActivationTask(
                    slot=slot,
                    data=kwargs,
                    job_state=job_state,
                    connection=connection,
                )
                executor.enqueue_task(task)
            return
    
    # 4. Legacy mode (no job_state or no executor)
    if flow is None:
        for slot in self.connected_slots:
            slot.receive(**kwargs)
        return
```

### 任务序列化的routine_id映射

**关键点**：必须使用flow.routines中的key作为routine_id，不是routine._id。

**实现**：
```python
# 序列化时
routine_id = None
if task.slot.routine:
    for rid, r in executor.flow.routines.items():
        if r is task.slot.routine:
            routine_id = rid  # Use flow's routine_id
            break

# 反序列化时
routine_id = serialized.get("routine_id")
if routine_id and routine_id in executor.flow.routines:
    routine = executor.flow.routines[routine_id]
    slot = routine.get_slot(slot_name)
```

### JobExecutor完成检测的稳定性

**关键点**：需要多次检查确保真正完成，避免race condition。

**实现**：
```python
def _is_complete(self) -> bool:
    """Check if job is complete (with stability check)."""
    # Check multiple times to avoid race conditions
    for _ in range(3):
        if not self.task_queue.empty():
            return False
        
        with self._lock:
            active = [f for f in self.active_tasks if not f.done()]
            if len(active) > 0:
                return False
        
        time.sleep(0.01)  # Small delay between checks
    
    return True
```

### 错误处理中的资源清理

**关键点**：错误发生时必须正确清理JobExecutor，不能留下僵尸job。

**实现**：
```python
def _handle_error(self, error: Exception):
    """Handle job error with proper cleanup."""
    # Update job state
    self.job_state.status = ExecutionStatus.FAILED
    self.job_state.shared_data["error"] = str(error)
    
    # Stop event loop
    self._running = False
    
    # Cancel active tasks
    with self._lock:
        for future in list(self.active_tasks):
            if not future.done():
                future.cancel()
        self.active_tasks.clear()
    
    # Call hooks
    execution_hooks.on_flow_end(self.flow, self.job_state, "failed")
    
    # Cleanup will be called by _cleanup() when event loop exits
```

## 最终检查清单

### 代码完整性检查

- [ ] GlobalJobManager实现完整
- [ ] JobExecutor实现完整
- [ ] emit()路由逻辑完整
- [ ] 暂停/恢复/取消功能完整
- [ ] 任务序列化/反序列化完整
- [ ] 错误处理更新完整
- [ ] ExecutionTracker处理完整
- [ ] Flow类清理完整
- [ ] API路由更新完整

### 线程安全检查

- [ ] GlobalJobManager单例线程安全
- [ ] JobExecutor的task_queue访问线程安全
- [ ] active_tasks访问有锁保护
- [ ] JobState更新有锁保护
- [ ] running_jobs字典访问有锁保护

### 资源管理检查

- [ ] job完成后从GlobalJobManager移除
- [ ] event loop线程正确join
- [ ] 全局线程池正确shutdown
- [ ] 没有资源泄漏

### 序列化检查

- [ ] Flow序列化不包含执行状态
- [ ] JobState序列化包含所有必要信息
- [ ] 任务序列化使用正确的routine_id
- [ ] 反序列化后可以正确恢复执行

### 功能完整性检查

- [ ] 多job并发执行正常
- [ ] 暂停/恢复功能正常
- [ ] 取消功能正常
- [ ] 超时处理正常
- [ ] 错误处理正常
- [ ] Monitoring hooks正常调用

## 开发顺序（严格按此顺序）

1. **Phase 1**: 创建基础设施（GlobalJobManager + JobExecutor）
2. **Phase 2**: 修改emit()路由
3. **Phase 3**: 实现暂停/恢复/取消
4. **Phase 4**: 清理Flow类
5. **Phase 5**: 更新执行模块和错误处理
6. **Phase 6**: 处理ExecutionTracker
7. **Phase 7**: 更新API路由
8. **Phase 8**: 测试和验证
9. **Phase 9**: 文档更新

**⚠️ 重要**：每个Phase必须完全完成并通过测试后才能进入下一个Phase。

## 最终审查总结

### ✅ 设计方案完整性

经过严格审查，设计方案**完整且正确**：

1. ✅ **架构设计**：Job级别隔离、全局线程池、序列化友好
2. ✅ **关键功能**：emit()路由、暂停/恢复/取消、超时处理、错误处理
3. ✅ **实现细节**：ExecutionTracker、任务序列化、监控hooks、资源清理
4. ✅ **测试计划**：单元测试、集成测试、多job并发测试

### 🔴 必须严格遵守的实现细节

1. **emit()路由**：必须通过JobState找到JobExecutor，不能使用flow._enqueue_task()
2. **任务序列化**：必须使用flow.routines中的routine_id（key），不是routine._id
3. **错误处理retry**：retry任务必须路由到JobExecutor，不能使用flow._enqueue_task()
4. **资源清理**：job完成后必须从GlobalJobManager中移除
5. **ExecutionTracker**：每个JobExecutor有独立的ExecutionTracker
6. **Monitoring hooks**：slot.receive()中已调用，不需要在JobExecutor中重复调用

### 📋 开发检查点

每个Phase完成后必须检查：

1. **代码完整性**：所有功能实现完整
2. **线程安全**：所有共享资源有锁保护
3. **资源管理**：没有资源泄漏
4. **测试通过**：所有相关测试通过
5. **文档更新**：相关文档已更新

### ⚠️ 风险提示

1. **emit()路由**：如果路由失败，会导致任务丢失
2. **任务序列化**：routine_id映射错误会导致恢复失败
3. **资源清理**：清理不当会导致资源泄漏
4. **线程安全**：锁使用不当会导致死锁或数据竞争

### ✅ 验收标准

重构完成后必须满足：

1. ✅ 用户可以创建多个job，每个job独立执行
2. ✅ 所有job共享全局线程池（可设置大小）
3. ✅ 主线程不阻塞，可以继续处理其他逻辑
4. ✅ 可以wait所有job完成或轮询检查状态
5. ✅ JobState状态实时更新
6. ✅ 可以随时查询job状态和数据
7. ✅ Flow完全静态，可以序列化
8. ✅ JobState可以独立序列化
9. ✅ 暂停/恢复/取消功能正常
10. ✅ 超时处理正常
11. ✅ 错误处理正常
12. ✅ 多job并发执行正常

## 开发计划完成

本开发计划已经过严格审查，包含了所有必要的实现细节。开发团队必须**严格按照此计划执行**，**不允许任何自由发挥**。

每个Step都有明确的：
- 文件路径
- 具体任务
- 实现要求（包含代码示例）
- 验收标准

开发过程中如有疑问，必须参考本计划，不得自行决定实现方式。
