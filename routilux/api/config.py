"""
API configuration management.

Handles loading and validation of API configuration from environment variables.
"""

import logging
import os
import threading
from typing import List, Optional

logger = logging.getLogger(__name__)


class APIConfig:
    """API configuration.

    Loads configuration from environment variables with sensible defaults.

    Auth control (all-or-nothing, 要么都保护要么都放开):
        ROUTILUX_API_KEY_ENABLED controls whether all APIs require X-API-Key:
        - true:  All REST endpoints and WebSockets require a valid X-API-Key
                 (header for REST; api_key query for WebSocket). 401/403 or
                 close(1008) when missing/invalid.
        - false: All endpoints are public; X-API-Key is ignored if sent.
        No mixed mode: the server either protects everything or nothing.
    """

    def __init__(self):
        """Load configuration from environment."""
        # API Key authentication: when True, ALL endpoints require X-API-Key
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
        # CRITICAL fix: Add error handling for rate_limit_per_minute parsing
        try:
            self.rate_limit_per_minute: int = int(os.getenv("ROUTILUX_RATE_LIMIT_PER_MINUTE", "60"))
            if self.rate_limit_per_minute <= 0:
                raise ValueError("rate_limit_per_minute must be positive")
        except (ValueError, TypeError) as e:
            logger.warning(f"Invalid ROUTILUX_RATE_LIMIT_PER_MINUTE, using default: {e}")
            self.rate_limit_per_minute = 60

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
_config_lock = threading.Lock()


def get_config() -> APIConfig:
    """Get global API config instance.

    Critical fix: Thread-safe singleton initialization using double-checked locking.

    Returns:
        APIConfig instance.
    """
    global _config
    if _config is None:
        with _config_lock:
            # Double-check inside lock
            if _config is None:
                _config = APIConfig()
    return _config
