#!/usr/bin/env python3
"""
VEL Config Validator Test Suite
===============================

Tests for the vel_config_validator module.
"""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestValidationResult(unittest.TestCase):
    """Tests for ValidationResult class."""
    
    def test_validation_result_creation_valid(self):
        """A ValidationResult can be created as valid."""
        from vel_config_validator import ValidationResult
        result = ValidationResult(is_valid=True)
        self.assertTrue(result.is_valid)
    
    def test_validation_result_creation_invalid(self):
        """A ValidationResult can be created as invalid."""
        from vel_config_validator import ValidationResult
        result = ValidationResult(is_valid=False)
        self.assertFalse(result.is_valid)
    
    def test_add_error_invalidates_result(self):
        """Adding an error should invalidate the result."""
        from vel_config_validator import ValidationResult
        result = ValidationResult(is_valid=True)
        result.add_error("config.json", "field", "type_error", "Test error message")
        self.assertFalse(result.is_valid)
    
    def test_add_warning_keeps_valid(self):
        """Adding a warning should keep result valid."""
        from vel_config_validator import ValidationResult
        result = ValidationResult(is_valid=True)
        result.add_warning("config.json", "field", "type_warning", "Test warning")
        self.assertTrue(result.is_valid)


class TestConfigValidatorSchema(unittest.TestCase):
    """Tests for config schema validation."""
    
    def test_system_config_schema_exists(self):
        """System config schema should be defined."""
        from vel_config_validator import SYSTEM_CONFIG_SCHEMA
        self.assertIsInstance(SYSTEM_CONFIG_SCHEMA, dict)
        self.assertIn("environment", SYSTEM_CONFIG_SCHEMA)
    
    def test_trading_config_schema_exists(self):
        """Trading config schema should be defined."""
        from vel_config_validator import TRADING_CONFIG_SCHEMA
        self.assertIsInstance(TRADING_CONFIG_SCHEMA, dict)
        self.assertIn("trading_mode", TRADING_CONFIG_SCHEMA)


class TestConfigValidator(unittest.TestCase):
    """Tests for ConfigValidator class."""
    
    def test_validator_creation(self):
        """ConfigValidator should be instantiable."""
        from vel_config_validator import ConfigValidator
        validator = ConfigValidator()
        self.assertIsNotNone(validator)
    
    def test_validator_has_validate_all(self):
        """ConfigValidator should have validate_all method."""
        from vel_config_validator import ConfigValidator
        validator = ConfigValidator()
        self.assertTrue(hasattr(validator, 'validate_all'))


class TestImmutableConfig(unittest.TestCase):
    """Tests for immutable config wrapper."""
    
    def test_immutable_config_creation(self):
        """ImmutableConfig should be creatable with name and data."""
        from vel_config_validator import ImmutableConfig
        config = ImmutableConfig({"key": "value"}, "test_config")
        self.assertIsNotNone(config)
    
    def test_immutable_config_access(self):
        """ImmutableConfig should allow read access via get method."""
        from vel_config_validator import ImmutableConfig
        config = ImmutableConfig({"key": "value"}, "test_config")
        self.assertEqual(config.get("key"), "value")


if __name__ == "__main__":
    unittest.main()
