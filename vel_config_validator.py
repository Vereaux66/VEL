#!/usr/bin/env python3
"""
VEL Configuration Validator
============================

Schema validation and integrity checking for configuration files.
Ensures configuration is valid before engine boot.

Features:
- JSON Schema validation for all config files
- Required field enforcement
- Type checking and value bounds
- Environment integrity verification
- Runtime config immutability enforcement

CRITICAL: No trading system boot without valid configuration.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("vel.config.validator")


# =============================================================================
# Configuration Schemas
# =============================================================================

# Schema definitions for each configuration file
# Format: {field_name: {type, required, min, max, default, enum, description}}

SYSTEM_CONFIG_SCHEMA = {
    "log_level": {
        "type": "string",
        "required": False,
        "default": "INFO",
        "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        "description": "Logging level"
    },
    "data_dir": {
        "type": "string",
        "required": False,
        "default": "data",
        "description": "Data directory path"
    },
    "worker_count": {
        "type": "integer",
        "required": False,
        "default": 4,
        "min": 1,
        "max": 32,
        "description": "Number of worker threads"
    },
    "environment": {
        "type": "string",
        "required": True,
        "enum": ["development", "staging", "production"],
        "description": "Deployment environment"
    },
    "debug": {
        "type": "boolean",
        "required": False,
        "default": False,
        "description": "Enable debug mode"
    }
}

TRADING_CONFIG_SCHEMA = {
    "trading_mode": {
        "type": "string",
        "required": True,
        "enum": ["disabled", "dry_run", "live"],
        "description": "Trading mode"
    },
    "portfolio_value_usd": {
        "type": "number",
        "required": False,
        "default": 10000,
        "min": 0,
        "description": "Total portfolio value in USD"
    },
    "max_position_size_usd": {
        "type": "number",
        "required": True,
        "min": 0,
        "description": "Maximum position size in USD"
    },
    "max_daily_loss_usd": {
        "type": "number",
        "required": True,
        "min": 0,
        "description": "Maximum daily loss limit in USD"
    },
    "max_slippage_bps": {
        "type": "integer",
        "required": False,
        "default": 100,
        "min": 1,
        "max": 1000,
        "description": "Maximum slippage in basis points"
    },
    "default_gas_limit_multiplier": {
        "type": "number",
        "required": False,
        "default": 1.2,
        "min": 1.0,
        "max": 3.0,
        "description": "Gas limit safety multiplier"
    },
    "enable_mev_protection": {
        "type": "boolean",
        "required": False,
        "default": True,
        "description": "Enable MEV protection"
    }
}

NETWORKS_CONFIG_SCHEMA = {
    # Per-chain configuration
    "chains": {
        "type": "object",
        "required": False,
        "description": "Per-chain settings",
        "nested_schema": {
            "enabled": {
                "type": "boolean",
                "required": False,
                "default": True
            },
            "max_gas_gwei": {
                "type": "integer",
                "required": False,
                "min": 1,
                "max": 10000
            },
            "rpc_endpoints": {
                "type": "array",
                "required": False,
                "items_type": "string"
            }
        }
    }
}

INFRASTRUCTURE_CONFIG_SCHEMA = {
    "database_type": {
        "type": "string",
        "required": True,
        "enum": ["sqlite", "postgresql"],
        "description": "Database type"
    },
    "database_url": {
        "type": "string",
        "required": False,
        "description": "Database connection URL"
    },
    "redis_enabled": {
        "type": "boolean",
        "required": False,
        "default": False,
        "description": "Enable Redis caching"
    },
    "redis_url": {
        "type": "string",
        "required": False,
        "description": "Redis connection URL"
    },
    "cache_ttl_seconds": {
        "type": "integer",
        "required": False,
        "default": 300,
        "min": 0,
        "max": 86400,
        "description": "Cache TTL in seconds"
    },
    "connection_pool_size": {
        "type": "integer",
        "required": False,
        "default": 10,
        "min": 1,
        "max": 100,
        "description": "Database connection pool size"
    }
}

# Map of config files to their schemas
CONFIG_SCHEMAS = {
    "system.json": SYSTEM_CONFIG_SCHEMA,
    "trading.json": TRADING_CONFIG_SCHEMA,
    "networks.json": NETWORKS_CONFIG_SCHEMA,
    "infrastructure.json": INFRASTRUCTURE_CONFIG_SCHEMA
}


# =============================================================================
# Validation Results
# =============================================================================

@dataclass
class ValidationError:
    """Single validation error."""
    config_file: str
    field_path: str
    error_type: str
    message: str
    severity: str = "error"  # error, warning


@dataclass
class ValidationResult:
    """Result of configuration validation."""
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationError] = field(default_factory=list)
    validated_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    validation_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def add_error(
        self, 
        config_file: str, 
        field_path: str, 
        error_type: str, 
        message: str
    ) -> None:
        """Add a validation error."""
        self.errors.append(ValidationError(
            config_file=config_file,
            field_path=field_path,
            error_type=error_type,
            message=message,
            severity="error"
        ))
        self.is_valid = False
    
    def add_warning(
        self, 
        config_file: str, 
        field_path: str, 
        error_type: str, 
        message: str
    ) -> None:
        """Add a validation warning."""
        self.warnings.append(ValidationError(
            config_file=config_file,
            field_path=field_path,
            error_type=error_type,
            message=message,
            severity="warning"
        ))


# =============================================================================
# Configuration Validator
# =============================================================================

class ConfigValidator:
    """
    Configuration validator with schema enforcement.
    
    Validates all configuration files against their schemas before
    allowing system boot. Ensures type safety, required fields,
    and value bounds.
    """
    
    def __init__(self, config_dir: str = "config"):
        """
        Initialize the configuration validator.
        
        Args:
            config_dir: Directory containing configuration files
        """
        self.config_dir = Path(config_dir)
        self._validated_configs: Dict[str, Dict[str, Any]] = {}
        self._is_validated = False
    
    def validate_all(self) -> ValidationResult:
        """
        Validate all configuration files.
        
        Returns:
            ValidationResult with all errors and warnings
        """
        result = ValidationResult(is_valid=True)
        
        # Check if config directory exists
        if not self.config_dir.exists():
            result.add_error(
                "config_dir",
                "",
                "missing_directory",
                f"Configuration directory not found: {self.config_dir}"
            )
            return result
        
        # Validate each config file
        for config_file, schema in CONFIG_SCHEMAS.items():
            file_path = self.config_dir / config_file
            
            if not file_path.exists():
                result.add_warning(
                    config_file,
                    "",
                    "missing_file",
                    f"Configuration file not found: {file_path}"
                )
                continue
            
            # Load and parse JSON
            try:
                with open(file_path, 'r') as f:
                    config_data = json.load(f)
            except json.JSONDecodeError as e:
                result.add_error(
                    config_file,
                    "",
                    "invalid_json",
                    f"Invalid JSON in {config_file}: {e}"
                )
                continue
            except Exception as e:
                result.add_error(
                    config_file,
                    "",
                    "read_error",
                    f"Error reading {config_file}: {e}"
                )
                continue
            
            # Validate against schema
            self._validate_config(config_file, config_data, schema, result)
            
            if config_file not in [e.config_file for e in result.errors]:
                result.validated_configs[config_file] = config_data
        
        # Cross-config validation
        self._validate_cross_config(result)
        
        # Environment-specific validation
        self._validate_environment_rules(result)
        
        self._validated_configs = result.validated_configs
        self._is_validated = result.is_valid
        
        return result
    
    def _validate_config(
        self,
        config_file: str,
        config_data: Dict[str, Any],
        schema: Dict[str, Any],
        result: ValidationResult
    ) -> None:
        """Validate a single configuration file against its schema."""
        
        for field_name, field_schema in schema.items():
            field_path = field_name
            value = config_data.get(field_name)
            
            # Check required fields
            if field_schema.get("required", False) and value is None:
                result.add_error(
                    config_file,
                    field_path,
                    "missing_required",
                    f"Required field '{field_name}' is missing"
                )
                continue
            
            # Skip validation if field not present and has default
            if value is None:
                continue
            
            # Type validation
            expected_type = field_schema.get("type")
            if not self._validate_type(value, expected_type):
                result.add_error(
                    config_file,
                    field_path,
                    "invalid_type",
                    f"Field '{field_name}' must be {expected_type}, got {type(value).__name__}"
                )
                continue
            
            # Enum validation
            if "enum" in field_schema:
                if value not in field_schema["enum"]:
                    result.add_error(
                        config_file,
                        field_path,
                        "invalid_enum",
                        f"Field '{field_name}' must be one of {field_schema['enum']}, got '{value}'"
                    )
            
            # Min/max validation for numbers
            if expected_type in ["integer", "number"]:
                if "min" in field_schema and value < field_schema["min"]:
                    result.add_error(
                        config_file,
                        field_path,
                        "below_minimum",
                        f"Field '{field_name}' must be >= {field_schema['min']}, got {value}"
                    )
                
                if "max" in field_schema and value > field_schema["max"]:
                    result.add_error(
                        config_file,
                        field_path,
                        "above_maximum",
                        f"Field '{field_name}' must be <= {field_schema['max']}, got {value}"
                    )
    
    def _validate_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type."""
        type_mapping = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict
        }
        
        expected = type_mapping.get(expected_type)
        if expected is None:
            return True  # Unknown type, allow
        
        return isinstance(value, expected)
    
    def _validate_cross_config(self, result: ValidationResult) -> None:
        """Validate relationships between config files."""
        configs = result.validated_configs
        
        # Infrastructure + trading mode consistency
        if "trading.json" in configs and "infrastructure.json" in configs:
            trading = configs["trading.json"]
            infra = configs["infrastructure.json"]
            
            # Live trading requires database
            if trading.get("trading_mode") == "live":
                if not infra.get("database_url"):
                    result.add_warning(
                        "trading.json",
                        "trading_mode",
                        "missing_dependency",
                        "Live trading mode recommended with database URL configured"
                    )
        
        # System environment + debug flag
        if "system.json" in configs:
            system = configs["system.json"]
            
            if system.get("environment") == "production" and system.get("debug", False):
                result.add_error(
                    "system.json",
                    "debug",
                    "invalid_for_environment",
                    "Debug mode must be disabled in production environment"
                )
    
    def _validate_environment_rules(self, result: ValidationResult) -> None:
        """Validate environment-specific rules."""
        env = os.environ.get("ANVEL_ENVIRONMENT", "development")
        
        if env == "production":
            configs = result.validated_configs
            
            # Production requires all config files
            for config_file in ["system.json", "trading.json", "infrastructure.json"]:
                if config_file not in configs:
                    result.add_error(
                        config_file,
                        "",
                        "production_required",
                        f"Production environment requires {config_file}"
                    )
            
            # Production trading limits
            if "trading.json" in configs:
                trading = configs["trading.json"]
                
                # Ensure reasonable position limits
                max_pos = trading.get("max_position_size_usd", 0)
                if max_pos > 1000000:  # $1M
                    result.add_warning(
                        "trading.json",
                        "max_position_size_usd",
                        "high_limit",
                        f"Production position limit is very high: ${max_pos:,.0f}"
                    )
    
    def get_config(self, config_name: str) -> Optional[Dict[str, Any]]:
        """
        Get validated configuration.
        
        Args:
            config_name: Configuration file name (e.g., "trading.json")
            
        Returns:
            Validated configuration dict or None
            
        Raises:
            RuntimeError: If validation hasn't been run
        """
        if not self._is_validated:
            raise RuntimeError("Configuration not validated. Call validate_all() first.")
        
        return self._validated_configs.get(config_name)
    
    def get_value(
        self, 
        config_name: str, 
        key: str, 
        default: Any = None
    ) -> Any:
        """
        Get a specific configuration value.
        
        Args:
            config_name: Configuration file name
            key: Configuration key
            default: Default value if not found
            
        Returns:
            Configuration value or default
        """
        config = self.get_config(config_name)
        if config is None:
            return default
        return config.get(key, default)


# =============================================================================
# Immutable Configuration Wrapper
# =============================================================================

class ImmutableConfig:
    """
    Immutable configuration wrapper.
    
    Once initialized, configuration values cannot be changed.
    This prevents runtime configuration drift.
    """
    
    def __init__(self, config_data: Dict[str, Any], config_name: str):
        """
        Initialize immutable configuration.
        
        Args:
            config_data: Configuration dictionary
            config_name: Name of the configuration
        """
        self._config_name = config_name
        self._frozen_at = datetime.now(timezone.utc)
        self._data = self._freeze(config_data)
    
    def _freeze(self, data: Any) -> Any:
        """Recursively freeze configuration data."""
        if isinstance(data, dict):
            return tuple(sorted((k, self._freeze(v)) for k, v in data.items()))
        elif isinstance(data, list):
            return tuple(self._freeze(item) for item in data)
        return data
    
    def _thaw(self, data: Any) -> Any:
        """Convert frozen data back to normal structures for reading."""
        if isinstance(data, tuple):
            # Check if it's a dict (tuple of tuples)
            if data and isinstance(data[0], tuple) and len(data[0]) == 2:
                return {k: self._thaw(v) for k, v in data}
            # It's a list
            return [self._thaw(item) for item in data]
        return data
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        thawed = self._thaw(self._data)
        if isinstance(thawed, dict):
            return thawed.get(key, default)
        return default
    
    def __getitem__(self, key: str) -> Any:
        """Get a configuration value by key."""
        thawed = self._thaw(self._data)
        if isinstance(thawed, dict):
            return thawed[key]
        raise KeyError(key)
    
    def to_dict(self) -> Dict[str, Any]:
        """Get a copy of the configuration as a dict."""
        return self._thaw(self._data)
    
    @property
    def frozen_at(self) -> datetime:
        """When the configuration was frozen."""
        return self._frozen_at


# =============================================================================
# Global Configuration Access
# =============================================================================

_global_validator: Optional[ConfigValidator] = None


def validate_configuration(config_dir: str = "config") -> ValidationResult:
    """
    Validate all configuration files.
    
    This should be called during application startup.
    
    Args:
        config_dir: Configuration directory path
        
    Returns:
        ValidationResult
    """
    global _global_validator
    _global_validator = ConfigValidator(config_dir)
    return _global_validator.validate_all()


def get_config(config_name: str) -> Optional[Dict[str, Any]]:
    """
    Get validated configuration.
    
    Args:
        config_name: Configuration file name
        
    Returns:
        Configuration dict or None
    """
    if _global_validator is None:
        raise RuntimeError("Configuration not validated. Call validate_configuration() first.")
    return _global_validator.get_config(config_name)


def get_config_value(config_name: str, key: str, default: Any = None) -> Any:
    """
    Get a specific configuration value.
    
    Args:
        config_name: Configuration file name  
        key: Configuration key
        default: Default value
        
    Returns:
        Configuration value
    """
    if _global_validator is None:
        raise RuntimeError("Configuration not validated. Call validate_configuration() first.")
    return _global_validator.get_value(config_name, key, default)
