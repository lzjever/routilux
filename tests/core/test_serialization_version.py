"""Tests for Flow serialization version management.

Tests that Flow serialization includes version field and that
deserialization validates version compatibility.
"""

import pytest

from routilux.core import SERIALIZATION_VERSION, SUPPORTED_SERIALIZATION_VERSIONS, Flow, Routine
from routilux.exceptions import SerializationError


def test_flow_serialization_includes_version():
    """Serialized flow should include version field."""
    flow = Flow("test_flow")
    routine = Routine()
    flow.add_routine(routine, "test_routine")

    serialized = flow.serialize()

    assert "version" in serialized, "Serialized data must include version field"
    assert isinstance(serialized["version"], int), "Version must be an integer"
    assert serialized["version"] == SERIALIZATION_VERSION, "Version should match current version"


def test_flow_deserialization_validates_version():
    """Deserialization should validate version compatibility."""
    flow = Flow("test_flow")
    routine = Routine()
    flow.add_routine(routine, "test_routine")

    serialized = flow.serialize()

    # Simulate future version
    unsupported_version = 999
    serialized["version"] = unsupported_version

    with pytest.raises(
        SerializationError, match=f"Unsupported serialization version: {unsupported_version}"
    ):
        flow.deserialize(serialized)


def test_flow_deserialization_accepts_current_version():
    """Deserialization should accept current version."""
    flow = Flow("test_flow")
    routine = Routine()
    flow.add_routine(routine, "test_routine")

    serialized = flow.serialize()

    # Should not raise
    new_flow = Flow()
    new_flow.deserialize(serialized)

    assert new_flow.flow_id == flow.flow_id
    assert "test_routine" in new_flow.routines


def test_flow_deserialization_accepts_supported_versions():
    """Deserialization should accept all supported versions."""
    flow = Flow("test_flow")
    routine = Routine()
    flow.add_routine(routine, "test_routine")

    serialized = flow.serialize()

    # Test all supported versions
    for version in SUPPORTED_SERIALIZATION_VERSIONS:
        serialized["version"] = version
        new_flow = Flow()
        new_flow.deserialize(serialized)
        assert new_flow.flow_id == flow.flow_id


def test_flow_deserialization_missing_version_field():
    """Deserialization should handle missing version field gracefully (legacy data)."""
    flow = Flow("test_flow")
    routine = Routine()
    flow.add_routine(routine, "test_routine")

    serialized = flow.serialize()
    # Remove version field to simulate legacy data (before versioning was added)
    del serialized["version"]

    # Should handle legacy data gracefully for backward compatibility
    new_flow = Flow()
    new_flow.deserialize(serialized)

    # Verify that legacy data can be deserialized
    assert new_flow.flow_id == flow.flow_id
    assert "test_routine" in new_flow.routines

    # After deserializing legacy data, the version should be set to current
    assert new_flow._serialization_version == SERIALIZATION_VERSION


def test_flow_deserialization_invalid_version_type():
    """Deserialization should reject non-integer version values."""
    flow = Flow("test_flow")
    routine = Routine()
    flow.add_routine(routine, "test_routine")

    serialized = flow.serialize()
    # Set version to invalid type
    serialized["version"] = "1.0"

    with pytest.raises(SerializationError, match="Version must be an integer"):
        flow.deserialize(serialized)
