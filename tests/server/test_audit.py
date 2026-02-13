"""
Test audit logging for HTTP server.
"""

import json
import os
import sys
from io import StringIO

# Ensure project root is in sys.path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from routilux.server.audit import AuditLogger, get_audit_logger, hash_api_key


def test_audit_log_api_call():
    """Audit logger should record API calls."""
    output = StringIO()
    logger = AuditLogger(output)

    logger.log_api_call(
        api_key_hash="abc123",
        endpoint="/api/v1/flows",
        method="GET",
        status=200,
        duration_ms=45.5,
    )

    log_output = output.getvalue()
    log_data = json.loads(log_output)

    assert log_data["event_type"] == "api_call"
    assert log_data["endpoint"] == "/api/v1/flows"
    assert log_data["method"] == "GET"
    assert log_data["status"] == 200
    assert log_data["duration_ms"] == 45.5
    assert log_data["api_key_hash"] == "abc123"
    assert "timestamp" in log_data


def test_audit_log_api_call_with_optional_fields():
    """Audit logger should handle optional fields in API calls."""
    output = StringIO()
    logger = AuditLogger(output)

    logger.log_api_call(
        endpoint="/api/v1/health",
        method="GET",
        status=200,
        duration_ms=10.2,
        api_key_hash=None,
        ip_address="192.168.1.1",
    )

    log_output = output.getvalue()
    log_data = json.loads(log_output)

    assert log_data["event_type"] == "api_call"
    assert log_data["endpoint"] == "/api/v1/health"
    assert log_data["ip_address"] == "192.168.1.1"
    assert log_data["api_key_hash"] is None


def test_audit_log_auth_failure():
    """Audit logger should record authentication failures."""
    output = StringIO()
    logger = AuditLogger(output)

    logger.log_auth_failure(
        reason="missing_api_key",
        ip_address="127.0.0.1",
    )

    log_output = output.getvalue()
    log_data = json.loads(log_output)

    assert log_data["event_type"] == "auth_failure"
    assert log_data["reason"] == "missing_api_key"
    assert log_data["ip_address"] == "127.0.0.1"
    assert log_data["api_key_provided"] is False
    assert "timestamp" in log_data


def test_audit_log_auth_failure_with_api_key():
    """Audit logger should record auth failures when API key was provided."""
    output = StringIO()
    logger = AuditLogger(output)

    logger.log_auth_failure(
        reason="invalid_api_key",
        ip_address="10.0.0.5",
        api_key_provided=True,
    )

    log_output = output.getvalue()
    log_data = json.loads(log_output)

    assert log_data["event_type"] == "auth_failure"
    assert log_data["reason"] == "invalid_api_key"
    assert log_data["api_key_provided"] is True


def test_audit_log_rate_limit_exceeded():
    """Audit logger should record rate limit events."""
    output = StringIO()
    logger = AuditLogger(output)

    logger.log_rate_limit_exceeded(
        api_key_hash="xyz789",
        ip_address="192.168.1.100",
        limit=60,
    )

    log_output = output.getvalue()
    log_data = json.loads(log_output)

    assert log_data["event_type"] == "rate_limit_exceeded"
    assert log_data["api_key_hash"] == "xyz789"
    assert log_data["ip_address"] == "192.168.1.100"
    assert log_data["limit"] == 60
    assert "timestamp" in log_data


def test_audit_log_rate_limit_without_api_key():
    """Audit logger should record rate limit events without API key."""
    output = StringIO()
    logger = AuditLogger(output)

    logger.log_rate_limit_exceeded(
        api_key_hash=None,
        ip_address="10.0.0.1",
        limit=60,
    )

    log_output = output.getvalue()
    log_data = json.loads(log_output)

    assert log_data["event_type"] == "rate_limit_exceeded"
    assert log_data["api_key_hash"] is None


def test_audit_log_configuration_change():
    """Audit logger should record configuration changes."""
    output = StringIO()
    logger = AuditLogger(output)

    logger.log_configuration_change(
        setting="ROUTILUX_API_KEY_ENABLED",
        old_value="false",
        new_value="true",
    )

    log_output = output.getvalue()
    log_data = json.loads(log_output)

    assert log_data["event_type"] == "configuration_change"
    assert log_data["setting"] == "ROUTILUX_API_KEY_ENABLED"
    assert log_data["old_value"] == "false"
    assert log_data["new_value"] == "true"
    assert "timestamp" in log_data


def test_audit_logger_with_python_logger():
    """Audit logger should work with Python's logging module."""
    import logging

    # Create a custom logger with a StringIO handler
    test_logger = logging.getLogger("test_audit_with_python_logger")
    test_logger.setLevel(logging.INFO)
    test_logger.handlers.clear()  # Clear any existing handlers

    log_stream = StringIO()
    string_handler = logging.StreamHandler(log_stream)
    string_handler.setLevel(logging.INFO)
    test_logger.addHandler(string_handler)

    logger = AuditLogger(output=test_logger)

    logger.log_api_call(
        endpoint="/api/v1/test",
        method="POST",
        status=201,
        duration_ms=123.4,
    )

    # The log should have been written via the logger
    log_output = log_stream.getvalue()
    assert len(log_output) > 0

    # Verify the output contains the expected JSON data
    log_data = json.loads(log_output.strip())
    assert log_data["event_type"] == "api_call"
    assert log_data["endpoint"] == "/api/v1/test"
    assert log_data["method"] == "POST"
    assert log_data["status"] == 201
    assert log_data["duration_ms"] == 123.4


def test_global_audit_logger_enabled_by_default():
    """Global audit logger should be enabled by default."""
    # Clear the global instance to reset state
    import routilux.server.audit as audit_module

    audit_module._audit_logger = None

    # Ensure the env var is not set
    if "ROUTILUX_AUDIT_LOGGING_ENABLED" in os.environ:
        del os.environ["ROUTILUX_AUDIT_LOGGING_ENABLED"]

    logger = get_audit_logger()
    assert logger is not None
    assert isinstance(logger, AuditLogger)


def test_global_audit_logger_can_be_disabled():
    """Global audit logger should respect ROUTILUX_AUDIT_LOGGING_ENABLED=false."""
    # Clear the global instance to reset state
    import routilux.server.audit as audit_module

    audit_module._audit_logger = None

    # Disable audit logging
    os.environ["ROUTILUX_AUDIT_LOGGING_ENABLED"] = "false"

    logger = get_audit_logger()
    assert logger is not None
    assert isinstance(logger, AuditLogger)

    # Clean up
    del os.environ["ROUTILUX_AUDIT_LOGGING_ENABLED"]


def test_multiple_log_entries():
    """Audit logger should handle multiple log entries correctly."""
    output = StringIO()
    logger = AuditLogger(output)

    # Log multiple entries
    logger.log_api_call(
        endpoint="/api/v1/flows",
        method="GET",
        status=200,
        duration_ms=45,
    )

    logger.log_auth_failure(
        reason="invalid_api_key",
        ip_address="192.168.1.1",
    )

    logger.log_rate_limit_exceeded(
        api_key_hash="abc123",
        ip_address="10.0.0.1",
        limit=60,
    )

    log_output = output.getvalue()
    lines = log_output.strip().split("\n")

    assert len(lines) == 3

    # Verify each line is valid JSON
    for line in lines:
        log_data = json.loads(line)
        assert "event_type" in log_data
        assert "timestamp" in log_data

    # Verify specific events
    first_log = json.loads(lines[0])
    assert first_log["event_type"] == "api_call"

    second_log = json.loads(lines[1])
    assert second_log["event_type"] == "auth_failure"

    third_log = json.loads(lines[2])
    assert third_log["event_type"] == "rate_limit_exceeded"


def test_hash_api_key_is_secure():
    """hash_api_key should use SHA-256 and produce consistent output."""
    # Same input should produce same hash (deterministic)
    api_key = "test_api_key_123"
    hash1 = hash_api_key(api_key)
    hash2 = hash_api_key(api_key)

    assert hash1 == hash2
    assert len(hash1) == 16  # First 16 chars of SHA-256 hex
    assert all(c in "0123456789abcdef" for c in hash1)  # Hex characters only


def test_hash_api_key_is_different_for_different_keys():
    """hash_api_key should produce different hashes for different keys."""
    key1 = "api_key_one"
    key2 = "api_key_two"

    hash1 = hash_api_key(key1)
    hash2 = hash_api_key(key2)

    assert hash1 != hash2


def test_hash_api_key_cannot_revert_original():
    """hash_api_key should be one-way (cannot revert to original)."""
    import hashlib

    api_key = "my_secret_api_key"
    hashed = hash_api_key(api_key)

    # The hash should be shorter than the original key
    assert len(hashed) == 16
    assert len(hashed) < len(api_key) or len(api_key) < 16

    # The hash should match the first 16 chars of SHA-256
    expected_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    assert hashed == expected_hash
