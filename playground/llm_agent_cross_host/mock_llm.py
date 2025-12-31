"""
Mock LLM Service for demonstration purposes.

This module simulates an LLM service that can generate responses and questions.
In a real implementation, this would call an actual LLM API (OpenAI, Anthropic, etc.).
"""

import time
import random
from typing import Dict, Any, Optional, List


class MockLLMService:
    """Mock LLM service that simulates LLM API calls."""
    
    def __init__(self, model: str = "mock-gpt-4", delay: float = 0.1):
        """Initialize mock LLM service.
        
        Args:
            model: Model name (for simulation).
            delay: Simulated API call delay in seconds.
        """
        self.model = model
        self.delay = delay
        self.call_count = 0
    
    def generate(self, prompt: str, max_tokens: int = 100, temperature: float = 0.7) -> str:
        """Generate a response from the LLM.
        
        Args:
            prompt: Input prompt.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
        
        Returns:
            Generated response text.
        """
        self.call_count += 1
        
        # Simulate API call delay
        time.sleep(self.delay)
        
        # Simple mock responses based on prompt content
        prompt_lower = prompt.lower()
        
        if "question" in prompt_lower or "ask" in prompt_lower:
            # Generate a question
            questions = [
                "用户，您希望如何处理这个任务？",
                "请选择您偏好的处理方式：A) 快速处理 B) 详细分析 C) 跳过",
                "您是否需要我继续执行下一步操作？",
                "请确认是否继续：是/否",
            ]
            return random.choice(questions)
        
        elif "analyze" in prompt_lower or "分析" in prompt_lower:
            return f"分析结果：这是一个模拟的分析响应（调用 #{self.call_count}）"
        
        elif "process" in prompt_lower or "处理" in prompt_lower:
            return f"处理完成：已处理 {random.randint(1, 100)} 条记录"
        
        else:
            return f"LLM响应 #{self.call_count}：已收到您的请求 '{prompt[:50]}...'"
    
    def generate_with_question(self, context: str) -> Dict[str, Any]:
        """Generate a response that includes a question for the user.
        
        This simulates an LLM agent that needs user input to continue.
        
        Args:
            context: Context information for the LLM.
        
        Returns:
            Dictionary with 'response' and 'question' fields.
        """
        self.call_count += 1
        time.sleep(self.delay)
        
        # Simulate LLM generating a response and a question
        response = f"基于上下文 '{context[:30]}...'，我已经完成了初步分析。"
        question = random.choice([
            "您希望我如何处理这个结果？",
            "请选择下一步操作：继续/暂停/取消",
            "是否需要我执行额外的验证步骤？",
        ])
        
        return {
            "response": response,
            "question": question,
            "needs_user_input": True,
        }
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Chat completion API (OpenAI-style).
        
        Args:
            messages: List of message dicts with 'role' and 'content'.
            **kwargs: Additional parameters.
        
        Returns:
            Generated response.
        """
        self.call_count += 1
        time.sleep(self.delay)
        
        # Extract last user message
        last_message = messages[-1] if messages else {"content": ""}
        user_content = last_message.get("content", "")
        
        # Generate response
        return self.generate(user_content)


# Global instance for easy access
_llm_service = None


def get_llm_service() -> MockLLMService:
    """Get or create the global LLM service instance."""
    global _llm_service
    if _llm_service is None:
        _llm_service = MockLLMService()
    return _llm_service


def set_llm_service(service: MockLLMService) -> None:
    """Set the global LLM service instance."""
    global _llm_service
    _llm_service = service

