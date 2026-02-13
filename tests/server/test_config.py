"""
Test secure-by-default configuration for HTTP server.

Tests that security is enabled by default and can only be explicitly disabled
for development.
"""

import os
import sys

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def test_default_security_is_enabled():
    """Default configuration should have security enabled."""
    # Clear environment to test true defaults
    for key in list(os.environ.keys()):
        if key.startswith("ROUTILUX_"):
            del os.environ[key]

    # Reload config module to pick up env changes
    import importlib

    from routilux.server import config

    importlib.reload(config)

    cfg = config.APIConfig()
    assert cfg.api_key_enabled is True, "API key should be enabled by default"
    assert cfg.rate_limit_enabled is True, "Rate limiting should be enabled by default"


def test_dev_mode_disables_security():
    """Explicit dev mode should disable security with warning."""
    os.environ["ROUTILUX_ENV"] = "development"
    os.environ["ROUTILUX_DEV_DISABLE_SECURITY"] = "true"

    # Import fresh to pick up env vars
    import importlib

    from routilux.server import config

    importlib.reload(config)

    cfg = config.APIConfig()
    assert cfg.api_key_enabled is False
    assert cfg.rate_limit_enabled is False

    # Clean up
    del os.environ["ROUTILUX_ENV"]
    del os.environ["ROUTILUX_DEV_DISABLE_SECURITY"]


def test_production_env_enforces_security():
    """Production environment should enforce security."""
    os.environ["ROUTILUX_ENV"] = "production"
    os.environ["ROUTILUX_DEV_DISABLE_SECURITY"] = "false"  # Explicit

    import importlib

    from routilux.server import config

    importlib.reload(config)

    cfg = config.APIConfig()
    assert cfg.api_key_enabled is True
    assert cfg.rate_limit_enabled is True

    # Clean up
    del os.environ["ROUTILUX_ENV"]
    del os.environ["ROUTILUX_DEV_DISABLE_SECURITY"]


def test_explicit_env_vars_override_defaults():
    """Explicit environment variables should still override defaults."""
    # Clear environment first
    for key in list(os.environ.keys()):
        if key.startswith("ROUTILUX_"):
            del os.environ[key]

    # Explicitly disable security (legacy behavior)
    os.environ["ROUTILUX_API_KEY_ENABLED"] = "false"
    os.environ["ROUTILUX_RATE_LIMIT_ENABLED"] = "false"

    import importlib

    from routilux.server import config

    importlib.reload(config)

    cfg = config.APIConfig()
    assert cfg.api_key_enabled is False
    assert cfg.rate_limit_enabled is False

    # Clean up
    del os.environ["ROUTILUX_API_KEY_ENABLED"]
    del os.environ["ROUTILUX_RATE_LIMIT_ENABLED"]


def test_explicit_true_env_vars_work():
    """Explicit true environment variables should work."""
    # Clear environment first
    for key in list(os.environ.keys()):
        if key.startswith("ROUTILUX_"):
            del os.environ[key]

    os.environ["ROUTILUX_API_KEY_ENABLED"] = "true"
    os.environ["ROUTILUX_RATE_LIMIT_ENABLED"] = "true"

    import importlib

    from routilux.server import config

    importlib.reload(config)

    cfg = config.APIConfig()
    assert cfg.api_key_enabled is True
    assert cfg.rate_limit_enabled is True

    # Clean up
    del os.environ["ROUTILUX_API_KEY_ENABLED"]
    del os.environ["ROUTILUX_RATE_LIMIT_ENABLED"]


def test_rate_limit_per_minute_validation():
    """Rate limit per minute should be validated."""
    # Clear environment first
    for key in list(os.environ.keys()):
        if key.startswith("ROUTILUX_"):
            del os.environ[key]

    test_cases = [
        ("0", "must be positive"),
        ("-5", "must be positive"),
        ("abc", "using default"),
        ("", "using default"),
    ]

    for value, expected_msg in test_cases:
        os.environ["ROUTILUX_RATE_LIMIT_PER_MINUTE"] = value

        import importlib

        from routilux.server import config

        importlib.reload(config)

        cfg = config.APIConfig()
        assert cfg.rate_limit_per_minute == 60, f"Invalid value {value} should default to 60"

    # Clean up
    if "ROUTILUX_RATE_LIMIT_PER_MINUTE" in os.environ:
        del os.environ["ROUTILUX_RATE_LIMIT_PER_MINUTE"]


def test_dev_mode_takes_precedence():
    """DEV_DISABLE_SECURITY should take precedence over individual settings."""
    # Clear environment first
    for key in list(os.environ.keys()):
        if key.startswith("ROUTILUX_"):
            del os.environ[key]

    # Set conflicting settings: dev mode says disable, but explicit says enable
    os.environ["ROUTILUX_DEV_DISABLE_SECURITY"] = "true"
    os.environ["ROUTILUX_API_KEY_ENABLED"] = "true"
    os.environ["ROUTILUX_RATE_LIMIT_ENABLED"] = "true"

    import importlib

    from routilux.server import config

    importlib.reload(config)

    cfg = config.APIConfig()
    assert cfg.api_key_enabled is False
    assert cfg.rate_limit_enabled is False

    # Clean up
    del os.environ["ROUTILUX_DEV_DISABLE_SECURITY"]
    del os.environ["ROUTILUX_API_KEY_ENABLED"]
    del os.environ["ROUTILUX_RATE_LIMIT_ENABLED"]


def test_production_ignores_dev_disable_security():
    """Production environment should ignore DEV_DISABLE_SECURITY."""
    # Set conflicting: production but DEV_DISABLE_SECURITY=true
    os.environ["ROUTILUX_ENV"] = "production"
    os.environ["ROUTILUX_DEV_DISABLE_SECURITY"] = "true"

    import importlib

    from routilux.server import config

    importlib.reload(config)

    cfg = config.APIConfig()
    # Production should enforce security despite DEV_DISABLE_SECURITY
    assert cfg.is_production is True
    assert cfg.api_key_enabled is True, "Production should enforce API key auth"
    assert cfg.rate_limit_enabled is True, "Production should enforce rate limiting"

    # Clean up
    del os.environ["ROUTILUX_ENV"]
    del os.environ["ROUTILUX_DEV_DISABLE_SECURITY"]


def test_environment_variable_env():
    """ENVIRONMENT variable should also be recognized for production."""
    # Clear environment first
    for key in list(os.environ.keys()):
        if key.startswith("ROUTILUX_") or key == "ENVIRONMENT":
            del os.environ[key]

    os.environ["ENVIRONMENT"] = "production"

    import importlib

    from routilux.server import config

    importlib.reload(config)

    cfg = config.APIConfig()
    assert cfg.is_production is True
    assert cfg.api_key_enabled is True
    assert cfg.rate_limit_enabled is True

    # Clean up
    del os.environ["ENVIRONMENT"]
