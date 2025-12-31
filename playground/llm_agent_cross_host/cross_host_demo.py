"""
Complete demonstration of cross-host LLM agent workflow.

This module demonstrates:
1. Host A: Execute workflow, pause when LLM needs user input, save to cloud storage
2. Host B: Load from cloud storage, resume execution with user input

Execution Flow Overview:
========================

Host A (Initial Execution):
---------------------------
1. Create Flow with LLM Agent Routine
2. Execute flow with task
3. LLM Agent processes task
4. LLM generates question, needs user input
5. Routine pauses execution
6. Execution state saved to cloud storage
7. JobState status = "paused"

Host B (Resume Execution):
---------------------------
1. Load Flow and JobState from cloud storage
2. Deserialize both objects
3. Resume execution (flow.resume())
4. Deferred events are automatically emitted
5. Trigger user input handler with user response
6. LLM processes user response
7. Workflow completes
8. JobState status = "completed"
"""

import time
from routilux import Flow, JobState
from playground.llm_agent_cross_host.llm_agent_routine import LLMAgentRoutine
from playground.llm_agent_cross_host.mock_storage import get_storage
from playground.llm_agent_cross_host.mock_llm import get_llm_service, set_llm_service, MockLLMService
from playground.llm_agent_cross_host.logger import get_logger, set_logger, PlaygroundLogger


def create_flow() -> Flow:
    """Create a flow with LLM agent routine.
    
    Flow Structure:
    - Flow ID: "llm_agent_workflow"
    - Single Routine: LLMAgentRoutine
      * Slots: trigger, user_input, continue
      * Events: output, question, completed
    
    Returns:
        Tuple of (Flow, agent_routine_id)
    """
    logger = get_logger()
    logger.debug("FLOW", "创建Flow对象", flow_id="llm_agent_workflow")
    
    flow = Flow(flow_id="llm_agent_workflow")
    
    # Create LLM agent routine
    logger.debug("FLOW", "创建LLM Agent Routine")
    agent = LLMAgentRoutine()
    agent_id = flow.add_routine(agent, "llm_agent")
    logger.debug("FLOW", "Routine已添加到Flow", routine_id=agent_id)
    
    return flow, agent_id


def host_a_execute_and_save(flow: Flow, entry_id: str, task: str = "分析用户数据"):
    """Host A: Execute workflow and save to cloud storage when paused.
    
    Execution Steps:
    1. Execute flow with task
    2. Flow starts event loop
    3. Trigger slot handler called
    4. LLM Agent processes task
    5. LLM generates question
    6. Routine pauses execution
    7. State saved to cloud storage
    8. JobState status = "paused"
    
    Args:
        flow: Flow object.
        entry_id: Entry routine ID.
        task: Task to process.
    
    Returns:
        JobState object.
    """
    logger = get_logger()
    logger.section("🌐 Host A: 执行工作流并保存到云存储")
    
    # Execute flow
    logger.step(1, f"开始执行任务: {task}")
    logger.debug("EXECUTION", "调用flow.execute()", entry_id=entry_id, task=task)
    
    job_state = flow.execute(entry_id, entry_params={"task": task})
    
    logger.debug("EXECUTION", "execute()返回", 
                job_id=job_state.job_id,
                status=job_state.status)
    
    # Wait for execution (may pause)
    # Note: execute() is synchronous and waits for completion or pause
    logger.step(2, "等待执行完成或暂停...")
    max_wait = 10.0
    start_time = time.time()
    
    # Check status immediately after execute
    logger.info("STATE", f"初始状态: {job_state.status}")
    
    while time.time() - start_time < max_wait:
        current_status = job_state.status
        if current_status in ["completed", "failed", "paused", "cancelled"]:
            logger.state_change("running", current_status)
            break
        time.sleep(0.1)
    
    # Additional wait to ensure pause is processed
    if job_state.status == "running":
        logger.debug("EXECUTION", "执行仍在运行，等待暂停处理...")
        time.sleep(0.5)  # Give pause time to process
    
    # Check if paused
    if job_state.status == "paused":
        logger.step(3, "执行已暂停，检查状态")
        logger.info("STATE", f"⏸️  执行已暂停")
        
        last_pause = job_state.pause_points[-1]
        logger.info("STATE", f"暂停原因: {last_pause['reason']}")
        logger.debug("STATE", "暂停检查点", checkpoint=last_pause['checkpoint'])
        
        # Get storage key
        storage_key = job_state.get_shared_data("storage_key")
        if storage_key:
            logger.info("STORAGE", f"存储键: {storage_key}")
        else:
            # Manually save if not auto-saved
            logger.warning("STORAGE", "未找到存储键，手动保存...")
            storage_key = f"execution_state/{job_state.job_id}"
            flow_data = flow.serialize()
            job_state_data = job_state.serialize()
            storage = get_storage()
            storage.put(storage_key, {
                "flow": flow_data,
                "job_state": job_state_data,
            })
            logger.info("STORAGE", f"已手动保存到: {storage_key}")
        
        # Display shared data
        logger.subsection("📊 共享数据")
        shared_data = job_state.shared_data
        for key, value in shared_data.items():
            logger.debug("STATE", f"  {key}: {value}")
        
        # Display execution history
        logger.subsection(f"📜 执行历史 ({len(job_state.execution_history)} 条)")
        for record in job_state.execution_history[-5:]:  # Show last 5
            logger.debug("EXECUTION", f"  [{record.timestamp}] {record.routine_id}.{record.event_name}")
    
    elif job_state.status == "completed":
        logger.info("EXECUTION", f"✅ 执行已完成")
        logger.info("EXECUTION", f"执行历史: {len(job_state.execution_history)} 条记录")
    
    return job_state


def host_b_load_and_resume(storage_key: str, user_response: str):
    """Host B: Load from cloud storage and resume execution.
    
    Execution Steps:
    1. Load Flow and JobState from cloud storage
    2. Deserialize Flow (workflow definition)
    3. Deserialize JobState (execution state)
    4. Verify deserialized data
    5. Set user response in shared_data
    6. Resume execution (flow.resume())
    7. Deferred events are automatically emitted
    8. Trigger user input handler
    9. Wait for completion
    10. Display final state
    
    Args:
        storage_key: Storage key from Host A.
        user_response: User response to continue execution.
    
    Returns:
        Resumed JobState object.
    """
    logger = get_logger()
    logger.section("🌐 Host B: 从云存储加载并恢复执行")
    
    # Load from cloud storage
    logger.step(1, f"从云存储加载: {storage_key}")
    storage = get_storage()
    transfer_data = storage.get(storage_key)
    
    if not transfer_data:
        logger.error("STORAGE", f"存储键未找到: {storage_key}")
        raise ValueError(f"Storage key not found: {storage_key}")
    
    logger.debug("STORAGE", "数据加载完成", 
                has_flow="flow" in transfer_data,
                has_job_state="job_state" in transfer_data)
    
    # Deserialize Flow
    logger.step(2, "反序列化 Flow (工作流定义)")
    flow = Flow()
    flow.deserialize(transfer_data["flow"])
    logger.info("FLOW", f"Flow ID: {flow.flow_id}")
    logger.info("FLOW", f"Routines: {list(flow.routines.keys())}")
    
    # Deserialize JobState
    logger.step(3, "反序列化 JobState (执行状态)")
    job_state = JobState()
    job_state.deserialize(transfer_data["job_state"])
    logger.info("STATE", f"Job ID: {job_state.job_id}")
    logger.state_change("paused", job_state.status, "反序列化后")
    logger.info("STATE", f"Flow ID: {job_state.flow_id}")
    
    if job_state.pause_points:
        last_pause = job_state.pause_points[-1]
        logger.info("STATE", f"最后暂停原因: {last_pause['reason']}")
        logger.debug("STATE", "暂停检查点", checkpoint=last_pause['checkpoint'])
    
    # Display shared data
    logger.subsection("📊 共享数据 (恢复前)")
    shared_data = job_state.shared_data
    for key, value in shared_data.items():
        logger.debug("STATE", f"  {key}: {value}")
    
    # Set user response in shared data
    logger.step(4, f"设置用户响应: {user_response}")
    job_state.update_shared_data("user_response", user_response)
    logger.debug("STATE", "用户响应已保存到shared_data")
    
    # Resume execution
    logger.step(5, "恢复执行 (flow.resume())")
    logger.debug("EXECUTION", "resume()将执行以下操作:")
    logger.debug("EXECUTION", "  - 设置job_state.status = 'running'")
    logger.debug("EXECUTION", "  - 反序列化pending_tasks")
    logger.debug("EXECUTION", "  - 自动emit deferred_events")
    logger.debug("EXECUTION", "  - 将pending_tasks加入队列")
    logger.debug("EXECUTION", "  - 启动event_loop")
    
    resumed_job_state = flow.resume(job_state)
    logger.state_change("paused", resumed_job_state.status, "resume()后")
    
    # Trigger user input handler
    # Find LLM agent routine
    logger.step(6, "触发用户输入处理")
    agent_routine_id = None
    agent_routine = None
    for rid, routine in flow.routines.items():
        if isinstance(routine, LLMAgentRoutine):
            agent_routine_id = rid
            agent_routine = routine
            break
    
    if agent_routine:
        logger.info("ROUTINE", f"找到LLM Agent Routine: {agent_routine_id}")
        user_input_slot = agent_routine.get_slot("user_input")
        if user_input_slot:
            logger.debug("EVENT", "调用user_input slot handler", 
                        routine_id=agent_routine_id,
                        user_response=user_response)
            user_input_slot.call_handler({"user_response": user_response})
        else:
            logger.warning("ROUTINE", "未找到user_input slot")
    else:
        logger.warning("ROUTINE", "未找到LLM Agent Routine")
    
    # Wait for completion
    logger.step(7, "等待执行完成...")
    max_wait = 10.0
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        if resumed_job_state.status in ["completed", "failed", "cancelled"]:
            logger.state_change("running", resumed_job_state.status)
            break
        time.sleep(0.1)
    
    # Display final state
    logger.subsection("📊 最终状态")
    logger.info("STATE", f"状态: {resumed_job_state.status}")
    logger.info("STATE", f"执行历史: {len(resumed_job_state.execution_history)} 条记录")
    
    # Display final shared data
    logger.subsection("📊 最终共享数据")
    final_shared_data = resumed_job_state.shared_data
    for key, value in final_shared_data.items():
        logger.debug("STATE", f"  {key}: {value}")
    
    # Display routine state
    if agent_routine_id:
        routine_state = resumed_job_state.get_routine_state(agent_routine_id)
        if routine_state:
            logger.subsection(f"📋 Routine状态 ({agent_routine_id})")
            for key, value in routine_state.items():
                logger.debug("STATE", f"  {key}: {value}")
    
    return resumed_job_state


def main():
    """Main demonstration function.
    
    Complete Demo Flow:
    ==================
    
    Phase 1: Initialization
    -----------------------
    1. Initialize logger
    2. Initialize LLM service (mock)
    3. Initialize cloud storage (mock)
    4. Create Flow with LLM Agent Routine
    
    Phase 2: Host A Execution
    -------------------------
    5. Execute flow with task
    6. LLM processes task and generates question
    7. Routine pauses execution
    8. State saved to cloud storage
    
    Phase 3: Host B Recovery
    -------------------------
    9. Load Flow and JobState from cloud storage
    10. Resume execution
    11. Process user input
    12. Complete workflow
    
    Phase 4: Summary
    ----------------
    13. Display execution summary
    """
    logger = get_logger()
    logger.section("🚀 LLM智能体跨主机中断恢复系统演示")
    
    # Initialize services
    logger.subsection("🔧 初始化服务")
    logger.step(1, "初始化LLM服务 (模拟)")
    llm_service = MockLLMService(delay=0.05)  # Faster for demo
    set_llm_service(llm_service)
    logger.info("SERVICE", "✅ LLM服务已初始化", model=llm_service.model)
    
    logger.step(2, "初始化云存储服务 (模拟)")
    logger.info("SERVICE", "✅ 云存储服务已初始化")
    
    # Create flow
    logger.subsection("📐 创建工作流")
    logger.step(3, "创建Flow和LLM Agent Routine")
    flow, agent_id = create_flow()
    logger.info("FLOW", f"Flow ID: {flow.flow_id}")
    logger.info("FLOW", f"Agent Routine ID: {agent_id}")
    
    # ============================================
    # Host A: Execute and save
    # ============================================
    logger.subsection("Phase 2: Host A 执行")
    job_state = host_a_execute_and_save(flow, agent_id, task="分析用户行为数据")
    
    # Check if paused
    if job_state.status == "paused":
        storage_key = job_state.get_shared_data("storage_key")
        if not storage_key:
            storage_key = f"execution_state/{job_state.job_id}"
        
        # ============================================
        # Host B: Load and resume
        # ============================================
        logger.subsection("Phase 3: Host B 恢复")
        user_response = "我选择方案A：继续详细分析"
        resumed_job_state = host_b_load_and_resume(storage_key, user_response)
        
        # Summary
        logger.subsection("Phase 4: 执行总结")
        logger.section("📊 执行总结")
        logger.info("SUMMARY", f"初始执行状态: {job_state.status}")
        logger.info("SUMMARY", f"恢复后状态: {resumed_job_state.status}")
        logger.info("SUMMARY", f"总执行历史记录: {len(resumed_job_state.execution_history)}")
        logger.info("SUMMARY", f"暂停次数: {len(resumed_job_state.pause_points)}")
        logger.info("SUMMARY", f"共享日志条目: {len(resumed_job_state.shared_log)}")
        logger.info("SUMMARY", "✅ 演示完成！")
    else:
        logger.warning("EXECUTION", "执行未暂停，无需跨主机恢复")
        logger.info("EXECUTION", f"最终状态: {job_state.status}")


if __name__ == "__main__":
    # Initialize logger with verbose mode
    logger = PlaygroundLogger(verbose=True, show_timestamps=True)
    set_logger(logger)
    
    main()

