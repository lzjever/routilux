"""
LLM Agent Routine for intelligent agent workflows.

This routine demonstrates how to:
- Use LLM to generate responses and questions
- Pause execution when user input is needed
- Save state to cloud storage
- Resume execution after user input
"""

from typing import Dict, Any, Optional
from playground.llm_agent_cross_host.enhanced_routine import EnhancedRoutine
from playground.llm_agent_cross_host.mock_llm import get_llm_service
from playground.llm_agent_cross_host.logger import get_logger
from serilux import register_serializable


@register_serializable
class LLMAgentRoutine(EnhancedRoutine):
    """LLM Agent Routine that can pause execution to wait for user input.
    
    This routine demonstrates a complete LLM agent workflow:
    1. Process input using LLM
    2. Generate questions when needed
    3. Pause execution and save state
    4. Resume after user input
    """
    
    def __init__(self):
        super().__init__()
        
        # Define slots
        self.trigger_slot = self.define_slot("trigger", handler=self.process)
        self.user_input_slot = self.define_slot("user_input", handler=self.handle_user_input)
        self.continue_slot = self.define_slot("continue", handler=self.continue_processing)
        
        # Define events
        self.output_event = self.define_event("output", ["result", "status"])
        self.question_event = self.define_event("question", ["question", "context"])
        self.completed_event = self.define_event("completed", ["result"])
        
        # Configuration
        self.set_config(
            auto_save_on_pause=True,  # Automatically save state when pausing
            llm_model="mock-gpt-4",
        )
    
    def process(self, task=None, **kwargs):
        """Main processing logic.
        
        This method:
        1. Uses LLM to process the task
        2. If LLM generates a question, pauses execution
        3. Saves state to cloud storage
        
        Execution Flow:
        - Receives task via trigger slot
        - Calls LLM service to process task
        - If LLM needs user input:
          * Stores LLM response and question in shared_data
          * Emits deferred event (will be emitted on resume)
          * Saves execution state to cloud storage
          * Pauses execution
        - If no user input needed:
          * Emits output event and completes
        """
        logger = get_logger()
        ctx = self.get_execution_context()
        if not ctx:
            logger.warning("ROUTINE", "无法获取执行上下文")
            return
        
        # Extract task from input
        task_data = task or kwargs.get("task", "默认任务")
        logger.info("ROUTINE", f"开始处理任务", routine_id=ctx.routine_id, task=task_data)
        
        # Log processing start
        ctx.job_state.append_to_shared_log({
            "action": "process_start",
            "task": task_data,
            "routine_id": ctx.routine_id,
        })
        
        # Use LLM to process
        logger.debug("LLM", "调用LLM服务处理任务", task=task_data)
        llm_service = get_llm_service()
        
        # Simulate LLM processing
        context = f"处理任务: {task_data}"
        llm_result = llm_service.generate_with_question(context)
        
        logger.info("LLM", "LLM处理完成", 
                   response=llm_result["response"][:50] + "...",
                   needs_user_input=llm_result["needs_user_input"])
        
        # Store LLM result in shared data
        ctx.job_state.update_shared_data("llm_response", llm_result["response"])
        ctx.job_state.update_shared_data("llm_question", llm_result["question"])
        ctx.job_state.update_shared_data("task", task_data)
        logger.debug("STATE", "LLM结果已保存到shared_data", 
                   keys=["llm_response", "llm_question", "task"])
        
        # Update routine state
        ctx.job_state.update_routine_state(ctx.routine_id, {
            "status": "processing",
            "llm_response": llm_result["response"],
            "needs_user_input": llm_result["needs_user_input"],
        })
        logger.debug("STATE", "Routine状态已更新", routine_id=ctx.routine_id, status="processing")
        
        # If LLM needs user input, pause execution
        if llm_result.get("needs_user_input", False):
            question = llm_result["question"]
            
            logger.info("ROUTINE", f"🤖 LLM需要用户输入", question=question)
            
            # Emit deferred event (will be emitted on resume)
            self.emit_deferred_event("question", question=question, context=context)
            logger.debug("EVENT", "延迟事件已添加", event="question", 
                       will_emit_on="resume")
            
            # Save state to cloud storage (if configured)
            if self.get_config("auto_save_on_pause", default=True):
                logger.info("STORAGE", "开始保存执行状态到云存储...")
                storage_key = self.save_execution_state()
                ctx.job_state.update_shared_data("storage_key", storage_key)
                logger.info("STORAGE", f"💾 状态已保存", storage_key=storage_key)
            
            # Log pause
            ctx.job_state.append_to_shared_log({
                "action": "paused",
                "reason": "等待用户输入",
                "question": question,
            })
            
            # Pause execution (this will block until all active tasks complete)
            logger.info("EXECUTION", "⏸️  准备暂停执行...")
            logger.debug("EXECUTION", "暂停前检查点", 
                        checkpoint={
                            "question": question,
                            "context": context,
                            "task": task_data,
                            "waiting_for": "user_input",
                        })
            
            self.pause_execution(
                reason="等待用户输入",
                checkpoint={
                    "question": question,
                    "context": context,
                    "task": task_data,
                    "waiting_for": "user_input",
                }
            )
            
            logger.info("EXECUTION", "✅ 执行已暂停", 
                       job_id=ctx.job_state.job_id,
                       status=ctx.job_state.status)
        else:
            # No user input needed, continue processing
            logger.info("ROUTINE", "无需用户输入，继续处理")
            result = f"处理完成: {llm_result['response']}"
            self.emit("output", result=result, status="completed")
            logger.debug("EVENT", "输出事件已发送", event="output", result=result[:50])
            
            ctx.job_state.update_routine_state(ctx.routine_id, {
                "status": "completed",
                "result": result,
            })
            logger.info("ROUTINE", "处理完成", routine_id=ctx.routine_id, status="completed")
    
    def handle_user_input(self, user_response=None, **kwargs):
        """Handle user input after resume.
        
        This method is called when the execution is resumed and user input
        is available.
        
        Execution Flow:
        - Receives user response via user_input slot
        - Retrieves previous context (question, task) from shared_data
        - Calls LLM to process user response
        - Updates shared_data with user response and final result
        - Emits output and completed events
        - Updates routine state to completed
        """
        logger = get_logger()
        ctx = self.get_execution_context()
        if not ctx:
            logger.warning("ROUTINE", "无法获取执行上下文")
            return
        
        # Extract user response
        response = user_response or kwargs.get("user_response", "")
        logger.info("ROUTINE", "👤 收到用户输入", 
                   routine_id=ctx.routine_id,
                   response=response)
        
        # Get previous context
        question = ctx.job_state.get_shared_data("llm_question", "")
        task = ctx.job_state.get_shared_data("task", "")
        logger.debug("STATE", "获取上下文", question=question[:50], task=task)
        
        # Log user input
        ctx.job_state.append_to_shared_log({
            "action": "user_input_received",
            "response": response,
            "question": question,
        })
        
        # Process user response
        logger.info("LLM", "使用LLM处理用户响应...")
        llm_service = get_llm_service()
        prompt = f"用户回复: {response}\n针对问题: {question}\n任务: {task}"
        final_result = llm_service.generate(prompt)
        logger.info("LLM", "LLM处理完成", result=final_result[:50] + "...")
        
        # Update state
        ctx.job_state.update_shared_data("user_response", response)
        ctx.job_state.update_shared_data("final_result", final_result)
        logger.debug("STATE", "用户响应和最终结果已保存到shared_data")
        
        # Emit result
        self.emit("output", result=final_result, status="completed")
        self.emit("completed", result=final_result)
        logger.debug("EVENT", "输出事件已发送", events=["output", "completed"])
        
        # Update routine state
        ctx.job_state.update_routine_state(ctx.routine_id, {
            "status": "completed",
            "user_response": response,
            "result": final_result,
        })
        logger.info("ROUTINE", "✅ 用户输入处理完成", 
                   routine_id=ctx.routine_id,
                   status="completed")
    
    def continue_processing(self, **kwargs):
        """Continue processing after user input.
        
        This is an alternative handler that can be used to continue
        processing with additional data.
        """
        ctx = self.get_execution_context()
        if not ctx:
            return
        
        # Get previous state
        task = ctx.job_state.get_shared_data("task", "")
        user_response = ctx.job_state.get_shared_data("user_response", "")
        
        # Continue processing
        llm_service = get_llm_service()
        prompt = f"继续处理任务: {task}\n用户输入: {user_response}"
        result = llm_service.generate(prompt)
        
        # Emit result
        self.emit("output", result=result, status="continued")
        
        # Update state
        ctx.job_state.update_routine_state(ctx.routine_id, {
            "status": "continued",
            "result": result,
        })

