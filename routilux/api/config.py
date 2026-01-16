"""
API configuration management.

Handles loading and validation of API configuration from environment variables.
"""

import os
from typing import List, Optional


class APIConfig:
    """API configuration.
    
    Loads configuration from environment variables with sensible defaults.
    """
    
    def __init__(self):
        """Load configuration from environment."""
        # API Key authentication
        self.api_key_enabled: bool = (
            os.getenv("ROUTILUX_API_KEY_ENABLED", "false").lower() == "true"
        )
        self.api_keys: List[str] = self._load_api_keys()
        
        # CORS (already handled in main.py, but keep for reference)
        self.cors_origins: str = os.getenv("ROUTILUX_CORS_ORIGINS", "")
        
        # Rate limiting
        self.rate_limit_enabled: bool = (
            os.getenv("ROUTILUX_RATE_LIMIT_ENABLED", "false").lower() == "true"
        )
        self.rate_limit_per_minute: int = int(
            os.getenv("ROUTILUX_RATE_LIMIT_PER_MINUTE", "60")
        )
    
    def _load_api_keys(self) -> List[str]:
        """Load API keys from environment.
        
        Supports:
        - ROUTILUX_API_KEY: Single API key
        - ROUTILUX_API_KEYS: Comma-separated list of API keys
        
        Returns:
            List of API keys.
        """
        keys = []
        
        # Single key
        single_key = os.getenv("ROUTILUX_API_KEY")
        if single_key:
            keys.append(single_key.strip())
        
        # Multiple keys
        multiple_keys = os.getenv("ROUTILUX_API_KEYS")
        if multiple_keys:
            keys.extend([k.strip() for k in multiple_keys.split(",") if k.strip()])
        
        return keys
    
    def is_api_key_valid(self, api_key: Optional[str]) -> bool:
        """Check if API key is valid.
        
        Args:
            api_key: API key to validate.
            
        Returns:
            True if valid, False otherwise.
        """
        if not self.api_key_enabled:
            return True  # Authentication disabled
        
        if not api_key:
            return False
        
        return api_key in self.api_keys


# Global config instance
_config: Optional[APIConfig] = None


def get_config() -> APIConfig:
    """Get global API config instance.
    
    Returns:
        APIConfig instance.
    """
    global _config
    if _config is None:
        _config = APIConfig()
    return _config
