"""
Enhanced Routine base class with convenience methods.

This module extends the base Routine class with convenience methods for
LLM agent workflows, without modifying the core routilux library.
"""

from typing import Dict, Any, Optional
from routilux import Routine
from playground.llm_agent_cross_host.logger import get_logger
from serilux import register_serializable


@register_serializable
class EnhancedRoutine(Routine):
    """Enhanced Routine with convenience methods for LLM agent workflows.
    
    This class extends the base Routine class with:
    - pause_execution(): Convenient method to pause execution from within a routine
    - Other convenience methods for common patterns
    
    Note: This is a playground extension. In production, you might want to
    add these methods directly to the base Routine class.
    """
    
    def pause_execution(self, reason: str = "", checkpoint: Optional[Dict[str, Any]] = None) -> None:
        """Pause the current execution from within a routine.
        
        This is a convenience method that automatically gets the execution context
        and calls flow.pause(). Useful for LLM agent workflows where routines need
        to pause execution to wait for user input.
        
        Execution Flow:
        1. Gets execution context (flow, job_state, routine_id)
        2. Calls flow.pause() which:
           - Sets flow._paused = True
           - Waits for all active tasks to complete
           - Moves pending tasks from queue to _pending_tasks
           - Serializes pending tasks to JobState
           - Sets job_state.status = "paused"
        
        Args:
            reason: Reason for pausing.
            checkpoint: Optional checkpoint data.
        
        Raises:
            RuntimeError: If not in execution context.
        
        Examples:
            >>> class AIRoutine(EnhancedRoutine):
            ...     def process(self, **kwargs):
            ...         # AI generates a question
            ...         question = "What should I do next?"
            ...         
            ...         # Save question to deferred event
            ...         self.emit_deferred_event("user_input_required", question=question)
            ...         
            ...         # Pause execution
            ...         self.pause_execution(
            ...             reason="Waiting for user input",
            ...             checkpoint={"question": question}
            ...         )
        """
        logger = get_logger()
        ctx = self.get_execution_context()
        if ctx is None:
            raise RuntimeError(
                "Cannot pause execution: not in execution context. "
                "This method can only be called during flow execution."
            )
        
        logger.debug("EXECUTION", "准备暂停执行", 
                    job_id=ctx.job_state.job_id,
                    reason=reason)
        logger.debug("EXECUTION", "暂停前状态", 
                    current_status=ctx.job_state.status,
                    active_tasks="检查中...")
        
        ctx.flow.pause(ctx.job_state, reason=reason, checkpoint=checkpoint)
        
        logger.debug("EXECUTION", "暂停完成", 
                    new_status=ctx.job_state.status,
                    pause_points=len(ctx.job_state.pause_points))
    
    def save_execution_state(self, storage_key: Optional[str] = None) -> str:
        """Save current execution state to cloud storage.
        
        This is a convenience method that serializes the Flow and JobState
        and saves them to cloud storage.
        
        Execution Flow:
        1. Gets execution context
        2. Generates storage key (if not provided)
        3. Serializes Flow (workflow definition)
        4. Serializes JobState (execution state)
        5. Saves both to cloud storage
        
        Serialized Data Includes:
        - Flow: routines, connections, configuration
        - JobState: status, routine_states, execution_history, 
                   pending_tasks, deferred_events, shared_data, etc.
        
        Args:
            storage_key: Optional storage key. If None, uses job_id.
        
        Returns:
            Storage key used.
        
        Raises:
            RuntimeError: If not in execution context.
        """
        logger = get_logger()
        from playground.llm_agent_cross_host.mock_storage import get_storage
        
        ctx = self.get_execution_context()
        if ctx is None:
            raise RuntimeError(
                "Cannot save execution state: not in execution context. "
                "This method can only be called during flow execution."
            )
        
        # Generate storage key if not provided
        if storage_key is None:
            storage_key = f"execution_state/{ctx.job_state.job_id}"
        
        logger.debug("STORAGE", "开始序列化Flow和JobState", storage_key=storage_key)
        
        # Serialize Flow and JobState
        flow_data = ctx.flow.serialize()
        job_state_data = ctx.job_state.serialize()
        
        logger.debug("STORAGE", "序列化完成", 
                    flow_size=f"{len(str(flow_data))} chars",
                    job_state_size=f"{len(str(job_state_data))} chars")
        
        # Save to storage
        storage = get_storage()
        transfer_data = {
            "flow": flow_data,
            "job_state": job_state_data,
        }
        storage.put(storage_key, transfer_data)
        
        logger.info("STORAGE", "执行状态已保存", storage_key=storage_key)
        
        return storage_key

