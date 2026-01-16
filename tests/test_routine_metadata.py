"""
Comprehensive tests for Routine metadata functionality.

Tests:
- get_activation_policy_info() method
- get_all_config() method
- Policy type detection
- Policy configuration extraction
- Config retrieval
"""

import pytest

from routilux import Routine
from routilux.activation_policies import (
    all_slots_ready_policy,
    batch_size_policy,
    immediate_policy,
    time_interval_policy,
)


class TestRoutineActivationPolicyInfo:
    """Test Routine activation policy info extraction"""

    def test_get_activation_policy_info_no_policy(self):
        """Test: get_activation_policy_info returns 'none' when no policy set"""
        routine = Routine()
        info = routine.get_activation_policy_info()

        assert info["type"] == "none"
        assert info["config"] == {}
        assert "description" in info
        assert "No activation policy set" in info["description"]

    def test_get_activation_policy_info_immediate(self):
        """Test: get_activation_policy_info correctly identifies immediate policy"""
        routine = Routine()
        routine.set_activation_policy(immediate_policy())

        info = routine.get_activation_policy_info()

        assert info["type"] == "immediate"
        assert info["config"] == {}
        assert "immediately" in info["description"].lower()

    def test_get_activation_policy_info_batch_size(self):
        """Test: get_activation_policy_info correctly identifies batch_size policy"""
        routine = Routine()
        routine.set_activation_policy(batch_size_policy(10))

        info = routine.get_activation_policy_info()

        assert info["type"] == "batch_size"
        assert "min_batch_size" in info["config"]
        assert info["config"]["min_batch_size"] == 10
        assert "10" in info["description"] or "batch" in info["description"].lower()

    def test_get_activation_policy_info_time_interval(self):
        """Test: get_activation_policy_info correctly identifies time_interval policy"""
        routine = Routine()
        routine.set_activation_policy(time_interval_policy(5.0))

        info = routine.get_activation_policy_info()

        assert info["type"] == "time_interval"
        assert "min_interval_seconds" in info["config"]
        assert info["config"]["min_interval_seconds"] == 5.0
        assert "5" in info["description"] or "interval" in info["description"].lower()

    def test_get_activation_policy_info_all_slots_ready(self):
        """Test: get_activation_policy_info correctly identifies all_slots_ready policy"""
        routine = Routine()
        routine.set_activation_policy(all_slots_ready_policy())

        info = routine.get_activation_policy_info()

        assert info["type"] == "all_slots_ready"
        assert info["config"] == {}
        assert "all slots" in info["description"].lower() or "all_slots" in info["description"].lower()

    def test_get_activation_policy_info_returns_all_fields(self):
        """Test: get_activation_policy_info returns all required fields"""
        routine = Routine()
        routine.set_activation_policy(immediate_policy())

        info = routine.get_activation_policy_info()

        required_fields = ["type", "config", "description"]
        for field in required_fields:
            assert field in info, f"Missing required field: {field}"

    def test_get_activation_policy_info_config_is_dict(self):
        """Test: get_activation_policy_info config is always a dictionary"""
        routine = Routine()

        # Test with no policy
        info = routine.get_activation_policy_info()
        assert isinstance(info["config"], dict)

        # Test with policy
        routine.set_activation_policy(immediate_policy())
        info = routine.get_activation_policy_info()
        assert isinstance(info["config"], dict)

    def test_get_activation_policy_info_description_is_string(self):
        """Test: get_activation_policy_info description is always a string"""
        routine = Routine()

        # Test with no policy
        info = routine.get_activation_policy_info()
        assert isinstance(info["description"], str)
        assert len(info["description"]) > 0

        # Test with policy
        routine.set_activation_policy(immediate_policy())
        info = routine.get_activation_policy_info()
        assert isinstance(info["description"], str)
        assert len(info["description"]) > 0


class TestRoutineConfig:
    """Test Routine configuration methods"""

    def test_get_all_config_empty(self):
        """Test: get_all_config returns empty dict when no config set"""
        routine = Routine()
        config = routine.get_all_config()

        assert isinstance(config, dict)
        assert len(config) == 0

    def test_get_all_config_returns_copy(self):
        """Test: get_all_config returns a copy, not the original"""
        routine = Routine()
        routine.set_config(key1="value1", key2="value2")

        config1 = routine.get_all_config()
        config2 = routine.get_all_config()

        # Modifying one should not affect the other
        config1["new_key"] = "new_value"
        assert "new_key" not in config2

    def test_get_all_config_returns_all_values(self):
        """Test: get_all_config returns all configuration values"""
        routine = Routine()
        routine.set_config(
            name="test_routine",
            timeout=30,
            retries=3,
            enabled=True,
        )

        config = routine.get_all_config()

        assert config["name"] == "test_routine"
        assert config["timeout"] == 30
        assert config["retries"] == 3
        assert config["enabled"] is True
        assert len(config) == 4

    def test_get_all_config_thread_safe(self):
        """Test: get_all_config is thread-safe"""
        import threading

        routine = Routine()
        routine.set_config(counter=0)

        results = []

        def read_config():
            config = routine.get_all_config()
            results.append(config)

        threads = [threading.Thread(target=read_config) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All reads should succeed
        assert len(results) == 10
        # All should return the same config
        for config in results:
            assert config["counter"] == 0

    def test_get_all_config_after_set_config(self):
        """Test: get_all_config reflects changes after set_config"""
        routine = Routine()

        # Initially empty
        config = routine.get_all_config()
        assert len(config) == 0

        # Set config
        routine.set_config(key1="value1")
        config = routine.get_all_config()
        assert config["key1"] == "value1"

        # Update config
        routine.set_config(key2="value2")
        config = routine.get_all_config()
        assert config["key1"] == "value1"
        assert config["key2"] == "value2"

    def test_get_all_config_various_types(self):
        """Test: get_all_config handles various data types"""
        routine = Routine()
        routine.set_config(
            string_val="test",
            int_val=42,
            float_val=3.14,
            bool_val=True,
            list_val=[1, 2, 3],
            dict_val={"nested": "value"},
            none_val=None,
        )

        config = routine.get_all_config()

        assert config["string_val"] == "test"
        assert config["int_val"] == 42
        assert config["float_val"] == 3.14
        assert config["bool_val"] is True
        assert config["list_val"] == [1, 2, 3]
        assert config["dict_val"] == {"nested": "value"}
        assert config["none_val"] is None
