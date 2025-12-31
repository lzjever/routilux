"""
Logging utility for playground demo system.

Provides structured logging with different log levels and categories
to help users understand the execution flow and learn the system.
"""

import time
from typing import Optional, Dict, Any
from datetime import datetime


class PlaygroundLogger:
    """Structured logger for playground demonstrations."""
    
    # Log levels
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    
    # Log categories
    CATEGORY_FLOW = "FLOW"
    CATEGORY_ROUTINE = "ROUTINE"
    CATEGORY_STATE = "STATE"
    CATEGORY_STORAGE = "STORAGE"
    CATEGORY_LLM = "LLM"
    CATEGORY_EVENT = "EVENT"
    CATEGORY_EXECUTION = "EXECUTION"
    
    def __init__(self, verbose: bool = True, show_timestamps: bool = True):
        """Initialize logger.
        
        Args:
            verbose: Whether to show detailed logs.
            show_timestamps: Whether to show timestamps in logs.
        """
        self.verbose = verbose
        self.show_timestamps = show_timestamps
        self.start_time = time.time()
    
    def _format_message(self, level: str, category: str, message: str) -> str:
        """Format log message.
        
        Args:
            level: Log level.
            category: Log category.
            message: Log message.
        
        Returns:
            Formatted message.
        """
        parts = []
        
        if self.show_timestamps:
            elapsed = time.time() - self.start_time
            parts.append(f"[{elapsed:.3f}s]")
        
        parts.append(f"[{level}]")
        parts.append(f"[{category}]")
        parts.append(message)
        
        return " ".join(parts)
    
    def log(self, level: str, category: str, message: str, **kwargs):
        """Log a message.
        
        Args:
            level: Log level.
            category: Log category.
            message: Log message.
            **kwargs: Additional data to include.
        """
        if not self.verbose and level == self.DEBUG:
            return
        
        formatted = self._format_message(level, category, message)
        
        if kwargs:
            details = ", ".join(f"{k}={v}" for k, v in kwargs.items())
            formatted += f" ({details})"
        
        print(formatted)
    
    def debug(self, category: str, message: str, **kwargs):
        """Log debug message."""
        self.log(self.DEBUG, category, message, **kwargs)
    
    def info(self, category: str, message: str, **kwargs):
        """Log info message."""
        self.log(self.INFO, category, message, **kwargs)
    
    def warning(self, category: str, message: str, **kwargs):
        """Log warning message."""
        self.log(self.WARNING, category, message, **kwargs)
    
    def error(self, category: str, message: str, **kwargs):
        """Log error message."""
        self.log(self.ERROR, category, message, **kwargs)
    
    def section(self, title: str, width: int = 70):
        """Print a section header.
        
        Args:
            title: Section title.
            width: Section width.
        """
        print("\n" + "=" * width)
        print(title)
        print("=" * width)
    
    def subsection(self, title: str):
        """Print a subsection header.
        
        Args:
            title: Subsection title.
        """
        print(f"\n--- {title} ---")
    
    def step(self, step_num: int, description: str, **kwargs):
        """Log an execution step.
        
        Args:
            step_num: Step number.
            description: Step description.
            **kwargs: Additional data.
        """
        message = f"步骤 {step_num}: {description}"
        self.info(self.CATEGORY_EXECUTION, message, **kwargs)
    
    def state_change(self, old_state: str, new_state: str, reason: str = ""):
        """Log state change.
        
        Args:
            old_state: Old state.
            new_state: New state.
            reason: Reason for change.
        """
        message = f"状态变化: {old_state} -> {new_state}"
        if reason:
            message += f" (原因: {reason})"
        self.info(self.CATEGORY_STATE, message)
    
    def data_flow(self, source: str, target: str, data_type: str, **kwargs):
        """Log data flow.
        
        Args:
            source: Data source.
            target: Data target.
            data_type: Type of data.
            **kwargs: Additional data.
        """
        message = f"数据流: {source} -> {target} ({data_type})"
        self.debug(self.CATEGORY_FLOW, message, **kwargs)


# Global logger instance
_logger = None


def get_logger() -> PlaygroundLogger:
    """Get or create global logger instance."""
    global _logger
    if _logger is None:
        _logger = PlaygroundLogger()
    return _logger


def set_logger(logger: PlaygroundLogger) -> None:
    """Set global logger instance."""
    global _logger
    _logger = logger

