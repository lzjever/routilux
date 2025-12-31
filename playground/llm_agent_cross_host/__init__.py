"""
LLM Agent Cross-Host Interrupt and Recovery Demo.

This demo demonstrates a complete LLM agent workflow with:
- Active interruption from within routines
- State persistence to cloud storage
- Cross-host recovery and continuation
"""

__version__ = "1.0.0"

# Make key components easily accessible
from playground.llm_agent_cross_host.llm_agent_routine import LLMAgentRoutine
from playground.llm_agent_cross_host.enhanced_routine import EnhancedRoutine
from playground.llm_agent_cross_host.mock_llm import MockLLMService, get_llm_service, set_llm_service
from playground.llm_agent_cross_host.mock_storage import MockCloudStorage, get_storage, set_storage
from playground.llm_agent_cross_host.logger import PlaygroundLogger, get_logger, set_logger

__all__ = [
    "LLMAgentRoutine",
    "EnhancedRoutine",
    "MockLLMService",
    "get_llm_service",
    "set_llm_service",
    "MockCloudStorage",
    "get_storage",
    "set_storage",
    "PlaygroundLogger",
    "get_logger",
    "set_logger",
]

