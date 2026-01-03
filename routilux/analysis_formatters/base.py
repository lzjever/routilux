"""
Base formatter class for analysis results.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Union
from pathlib import Path


class BaseFormatter(ABC):
    """Base class for all analysis formatters.
    
    Formatters convert analysis JSON results into various output formats
    such as Markdown, D2, HTML, etc.
    """
    
    @abstractmethod
    def format(self, data: Dict[str, Any]) -> str:
        """Format analysis data into output string.
        
        Args:
            data: Analysis result dictionary.
        
        Returns:
            Formatted string output.
        """
        pass
    
    def save(self, data: Dict[str, Any], output_path: Union[str, Path]) -> None:
        """Save formatted output to file.
        
        Args:
            data: Analysis result dictionary.
            output_path: Path to output file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        formatted_content = self.format(data)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(formatted_content)

