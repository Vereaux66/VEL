#!/usr/bin/env python3
"""
VEL Configuration Validator Test Suite
=======================================

Tests for configuration schema validation and integrity checking.

Run with: python -m pytest tests/test_config_validator.py -v
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestValidationResult(unittest.TestCase):
    """Test validation result structure."""
    
    def test_initial_state_is_valid(self):
        """New result should start as valid."""
        from vel_config_validator import ValidationResult
        
        result = ValidationResult(is_valid=True)
        
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.errors), 0)
        self.assertEqual(len(result.warnings), 0)
    
    def test_add_error_invalidates_result(self):
        """Adding error should mark result as invalid."""
        from vel_config_validator import ValidationResult
        
        result = ValidationResult(is_valid=True)
        result.add_error("test.json", "field", "missing", "Field is required")
        
        self.assertFalse(result.is_valid)
        self.assertEqual(len(result.errors), 1)
    
    def test_add_warning_keeps_valid(self):
        """Adding warning should keep result valid."""
        from vel_config_validator import ValidationResult
        
        result = ValidationResult(is_valid=True)
        result.add_warning("test.json", "field", "deprecated", "Field is deprecated")
        
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.warnings), 1)


class TestConfigValidatorSchema(unittest.TestCase):
    """Test schema validation logic."""
    
    def setUp(self):
        """Create temporary config directory."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _write_config(self, filename: str, data: dict) -> None:
        """Helper to write config file."""
        path = Path(self.temp_dir) / filename
        with open(path, 'w') as f:
            json.dump(data, f)
    
    def test_validate_valid_system_config(self):
        """Should pass valid system configuration."""
        from vel_config_validator import ConfigValidator
        
        self._write_config("system.json", {
            "log_level": "INFO",
            "environment": "development",
            "data_dir": "data",
            "worker_count": 4
        })
        
        validator = ConfigValidator(self.temp_dir)
        result = validator.validate_all()
        
        # Should be valid (no errors for system.json)
        system_errors = [e for e in result.errors if e.config_file == "system.json"]
        self.assertEqual(len(system_errors), 0)
    
    def test_validate_invalid_enum_value(self):
        """Should fail on invalid enum value."""
        from vel_config_validator import ConfigValidator
        
        self._write_config("system.json", {
            "log_level": "INVALID_LEVEL",  # Not in enum
            "environment": "development"
        })
        
        validator = ConfigValidator(self.temp_dir)
        result = validator.validate_all()
        
        # Should have error for invalid enum
        system_errors = [e for e in result.errors if e.config_file == "system.json"]
        self.assertGreater(len(system_errors), 0)
    
    def test_validate_invalid_type(self):
        """Should fail on invalid type."""
        from vel_config_validator import ConfigValidator
        
        self._write_config("system.json", {
            "environment": "development",
            "worker_count": "four"  # Should be integer
        })
        
        validator = ConfigValidator(self.temp_dir)
        result = validator.validate_all()
        
        type_errors = [e for e in result.errors if "invalid_type" in e.error_type]
        self.assertGreater(len(type_errors), 0)
    
    def test_validate_missing_required_field(self):
        """Should fail on missing required field."""
        from vel_config_validator import ConfigValidator
        
        self._write_config("system.json", {
            "log_level": "INFO"
            # Missing 'environment' which is required
        })
        
        validator = ConfigValidator(self.temp_dir)
        result = validator.validate_all()
        
        required_errors = [e for e in result.errors if "missing_required" in e.error_type]
        self.assertGreater(len(required_errors), 0)
    
    def test_validate_value_below_minimum(self):
        """Should fail on value below minimum."""
        from vel_config_validator import ConfigValidator
        
        self._write_config("system.json", {
            "environment": "development",
            "worker_count": 0  # Min is 1
        })
        
        validator = ConfigValidator(self.temp_dir)
        result = validator.validate_all()
        
        min_errors = [e for e in result.errors if "below_minimum" in e.error_type]
        self.assertGreater(len(min_errors), 0)
    
    def test_validate_value_above_maximum(self):
        """Should fail on value above maximum."""
        from vel_config_validator import ConfigValidator
        
        self._write_config("system.json", {
            "environment": "development",
            "worker_count": 100  # Max is 32
        })
        
        validator = ConfigValidator(self.temp_dir)
        result = validator.validate_all()
        
        max_errors = [e for e in result.errors if "above_maximum" in e.error_type]
        self.assertGreater(len(max_errors), 0)


class TestTradingConfigValidation(unittest.TestCase):
    """Test trading configuration validation."""
    
    def setUp(self):
        """Create temporary config directory."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _write_config(self, filename: str, data: dict) -> None:
        """Helper to write config file."""
        path = Path(self.temp_dir) / filename
        with open(path, 'w') as f:
            json.dump(data, f)
    
    def test_validate_valid_trading_config(self):
        """Should pass valid trading configuration."""
        from vel_config_validator import ConfigValidator
        
        self._write_config("trading.json", {
            "trading_mode": "dry_run",
            "max_position_size_usd": 10000,
            "max_daily_loss_usd": 1000,
            "max_slippage_bps": 100
        })
        
        validator = ConfigValidator(self.temp_dir)
        result = validator.validate_all()
        
        trading_errors = [e for e in result.errors if e.config_file == "trading.json"]
        self.assertEqual(len(trading_errors), 0)
    
    def test_validate_invalid_trading_mode(self):
        """Should fail on invalid trading mode."""
        from vel_config_validator import ConfigValidator
        
        self._write_config("trading.json", {
            "trading_mode": "invalid_mode",  # Not in enum
            "max_position_size_usd": 10000,
            "max_daily_loss_usd": 1000
        })
        
        validator = ConfigValidator(self.temp_dir)
        result = validator.validate_all()
        
        trading_errors = [e for e in result.errors if e.config_file == "trading.json"]
        self.assertGreater(len(trading_errors), 0)


class TestCrossConfigValidation(unittest.TestCase):
    """Test cross-configuration validation."""
    
    def setUp(self):
        """Create temporary config directory."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _write_config(self, filename: str, data: dict) -> None:
        """Helper to write config file."""
        path = Path(self.temp_dir) / filename
        with open(path, 'w') as f:
            json.dump(data, f)
    
    def test_production_debug_mode_fails(self):
        """Should fail if debug enabled in production."""
        from vel_config_validator import ConfigValidator
        
        self._write_config("system.json", {
            "environment": "production",
            "debug": True  # Not allowed in production
        })
        
        validator = ConfigValidator(self.temp_dir)
        result = validator.validate_all()
        
        debug_errors = [e for e in result.errors if "debug" in e.field_path]
        self.assertGreater(len(debug_errors), 0)


class TestInvalidJsonHandling(unittest.TestCase):
    """Test handling of invalid JSON files."""
    
    def setUp(self):
        """Create temporary config directory."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_invalid_json_syntax(self):
        """Should fail on invalid JSON syntax."""
        from vel_config_validator import ConfigValidator
        
        # Write invalid JSON
        path = Path(self.temp_dir) / "system.json"
        with open(path, 'w') as f:
            f.write('{"invalid": json,}')
        
        validator = ConfigValidator(self.temp_dir)
        result = validator.validate_all()
        
        json_errors = [e for e in result.errors if "invalid_json" in e.error_type]
        self.assertGreater(len(json_errors), 0)


class TestMissingConfigDirectory(unittest.TestCase):
    """Test handling of missing config directory."""
    
    def test_missing_directory_error(self):
        """Should error on missing config directory."""
        from vel_config_validator import ConfigValidator
        
        validator = ConfigValidator("/nonexistent/path")
        result = validator.validate_all()
        
        self.assertFalse(result.is_valid)
        dir_errors = [e for e in result.errors if "missing_directory" in e.error_type]
        self.assertGreater(len(dir_errors), 0)


class TestConfigAccess(unittest.TestCase):
    """Test validated config access."""
    
    def setUp(self):
        """Create temporary config directory."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _write_config(self, filename: str, data: dict) -> None:
        """Helper to write config file."""
        path = Path(self.temp_dir) / filename
        with open(path, 'w') as f:
            json.dump(data, f)
    
    def test_get_validated_config(self):
        """Should return validated config after validation."""
        from vel_config_validator import ConfigValidator
        
        self._write_config("system.json", {
            "environment": "development",
            "log_level": "INFO"
        })
        
        validator = ConfigValidator(self.temp_dir)
        validator.validate_all()
        
        config = validator.get_config("system.json")
        self.assertIsNotNone(config)
        self.assertEqual(config["environment"], "development")
    
    def test_get_config_before_validation_raises(self):
        """Should raise error if accessed before validation."""
        from vel_config_validator import ConfigValidator
        
        validator = ConfigValidator(self.temp_dir)
        
        with self.assertRaises(RuntimeError):
            validator.get_config("system.json")
    
    def test_get_config_value(self):
        """Should return specific config value."""
        from vel_config_validator import ConfigValidator
        
        self._write_config("system.json", {
            "environment": "development",
            "log_level": "DEBUG"
        })
        
        validator = ConfigValidator(self.temp_dir)
        validator.validate_all()
        
        value = validator.get_value("system.json", "log_level", "INFO")
        self.assertEqual(value, "DEBUG")
    
    def test_get_config_value_default(self):
        """Should return default value if key not found."""
        from vel_config_validator import ConfigValidator
        
        self._write_config("system.json", {
            "environment": "development"
        })
        
        validator = ConfigValidator(self.temp_dir)
        validator.validate_all()
        
        value = validator.get_value("system.json", "nonexistent", "default_value")
        self.assertEqual(value, "default_value")


class TestImmutableConfig(unittest.TestCase):
    """Test immutable configuration wrapper."""
    
    def test_freeze_and_thaw(self):
        """Should preserve data through freeze/thaw."""
        from vel_config_validator import ImmutableConfig
        
        data = {
            "key1": "value1",
            "key2": 42,
            "nested": {"inner": "data"}
        }
        
        config = ImmutableConfig(data, "test")
        
        self.assertEqual(config.get("key1"), "value1")
        self.assertEqual(config.get("key2"), 42)
    
    def test_frozen_timestamp(self):
        """Should record freeze timestamp."""
        from vel_config_validator import ImmutableConfig
        
        config = ImmutableConfig({"test": 1}, "test")
        
        self.assertIsNotNone(config.frozen_at)
    
    def test_to_dict(self):
        """Should convert back to dict."""
        from vel_config_validator import ImmutableConfig
        
        original = {"a": 1, "b": [2, 3], "c": {"d": 4}}
        config = ImmutableConfig(original, "test")
        
        result = config.to_dict()
        self.assertEqual(result, original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
