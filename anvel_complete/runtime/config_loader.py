#!/usr/bin/env python3
"""
ANVEL Configuration Loader
===========================

Centralized configuration management for ANVEL runtime.
All services read configuration only from this loader.

Configuration Sources (priority order):
1. Environment variables (highest priority)
2. Config files (JSON/YAML)
3. Default values (lowest priority)

Security:
- No hardcoded credentials
- Credentials loaded from environment only
- Sensitive values masked in logs
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("anvel.runtime.config")

# Sensitive keys that should never be logged
SENSITIVE_KEYS = {
    "api_key", "api_secret", "private_key", "password", "secret",
    "token", "credential", "auth", "key", "passphrase",
    "rpc_url", "database_url", "connection_string",
}


def _is_sensitive(key: str) -> bool:
    """Check if key contains sensitive data."""
    key_lower = key.lower()
    return any(s in key_lower for s in SENSITIVE_KEYS)


def _mask_value(value: Any) -> str:
    """Mask sensitive value for logging."""
    if value is None:
        return "None"
    s = str(value)
    if len(s) <= 4:
        return "****"
    return s[:2] + "****" + s[-2:]


@dataclass
class ConfigSection:
    """Configuration section with type validation."""
    name: str
    data: Dict[str, Any] = field(default_factory=dict)
    required_keys: List[str] = field(default_factory=list)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value with default."""
        return self.data.get(key, default)
    
    def __getitem__(self, key: str) -> Any:
        return self.data[key]
    
    def __contains__(self, key: str) -> bool:
        return key in self.data
    
    def validate(self) -> List[str]:
        """Validate required keys are present."""
        missing = [k for k in self.required_keys if k not in self.data]
        return missing


class ConfigLoader:
    """
    Centralized configuration loader.
    
    Usage:
        loader = ConfigLoader(Path("config"))
        loader.load_all()
        
        trading_config = loader.get("trading")
        api_key = loader.get_secret("EXCHANGE_API_KEY")
    """
    
    # Default configurations
    DEFAULTS = {
        "system": {
            "log_level": "INFO",
            "data_dir": "data",
            "single_node_mode": True,
            "max_workers": 8,
        },
        "trading": {
            "enabled": False,  # Safe default
            "dry_run": True,   # Safe default
            "portfolio_value_usd": "100000",
            "strict_risk_mode": True,
            "max_position_size_pct": 0.1,
            "max_slippage_bps": 100,
            "check_interval": 300,
            "watchlist": ["BTC", "ETH"],
        },
        "infrastructure": {
            "database_type": "sqlite",
            "database_path": "data/anvel.db",
            "redis_enabled": False,
            "cache_ttl_seconds": 300,
        },
        "ai": {
            "enabled": True,
            "learning_enabled": True,
            "anomaly_detection": True,
            "learning_rate": 0.01,
        },
        "monitoring": {
            "heartbeat_interval": 10,
            "health_check_interval": 30,
            "watchdog_timeout": 60,
            "metrics_enabled": True,
        },
        "networks": {
            "default_network": "ethereum",
            "use_testnets": False,
            "enabled_networks": ["ethereum", "arbitrum", "polygon"],
        },
    }
    
    def __init__(
        self,
        config_dir: Optional[Path] = None,
        env_prefix: str = "ANVEL_",
    ):
        """
        Initialize config loader.
        
        Args:
            config_dir: Directory containing config files
            env_prefix: Prefix for environment variable overrides
        """
        self.config_dir = config_dir or Path("config")
        self.env_prefix = env_prefix
        
        # Loaded configurations
        self._configs: Dict[str, ConfigSection] = {}
        self._loaded = False
    
    def load_all(self) -> None:
        """Load all configuration sources."""
        logger.info(f"Loading configuration from: {self.config_dir}")
        
        # Start with defaults
        for section, defaults in self.DEFAULTS.items():
            self._configs[section] = ConfigSection(
                name=section,
                data=defaults.copy(),
            )
        
        # Load from config files
        self._load_config_files()
        
        # Override with environment variables
        self._load_environment_overrides()
        
        # Validate critical sections
        self._validate_config()
        
        self._loaded = True
        logger.info("Configuration loaded successfully")
    
    def _load_config_files(self) -> None:
        """Load configuration from files."""
        if not self.config_dir.exists():
            logger.warning(f"Config directory not found: {self.config_dir}")
            return
        
        # Load JSON files
        for json_file in self.config_dir.glob("*.json"):
            try:
                section_name = json_file.stem
                with open(json_file, "r") as f:
                    data = json.load(f)
                
                if section_name in self._configs:
                    self._configs[section_name].data.update(data)
                else:
                    self._configs[section_name] = ConfigSection(
                        name=section_name,
                        data=data,
                    )
                
                logger.debug(f"  Loaded: {json_file.name}")
                
            except Exception as e:
                logger.error(f"  Error loading {json_file}: {e}")
        
        # Load YAML files if pyyaml available
        try:
            import yaml
            for yaml_file in self.config_dir.glob("*.yaml"):
                try:
                    section_name = yaml_file.stem
                    with open(yaml_file, "r") as f:
                        data = yaml.safe_load(f) or {}
                    
                    if section_name in self._configs:
                        self._configs[section_name].data.update(data)
                    else:
                        self._configs[section_name] = ConfigSection(
                            name=section_name,
                            data=data,
                        )
                    
                    logger.debug(f"  Loaded: {yaml_file.name}")
                    
                except Exception as e:
                    logger.error(f"  Error loading {yaml_file}: {e}")
        except ImportError:
            pass  # YAML support optional
        
        # Also try loading the main anvel_config.json from project root
        main_config = self.config_dir.parent / "anvel_config.json"
        if main_config.exists():
            try:
                with open(main_config, "r") as f:
                    data = json.load(f)
                
                # Distribute to appropriate sections
                for key, value in data.items():
                    if isinstance(value, dict) and key in self._configs:
                        self._configs[key].data.update(value)
                    elif key == "watchlist" and "trading" in self._configs:
                        self._configs["trading"].data["watchlist"] = value
                
                logger.debug(f"  Loaded: {main_config.name}")
            except Exception as e:
                logger.error(f"  Error loading {main_config}: {e}")
    
    def _load_environment_overrides(self) -> None:
        """Load configuration from environment variables."""
        # Pattern: ANVEL_SECTION_KEY=value
        for env_key, env_value in os.environ.items():
            if not env_key.startswith(self.env_prefix):
                continue
            
            # Parse key: ANVEL_TRADING_DRY_RUN -> trading.dry_run
            parts = env_key[len(self.env_prefix):].lower().split("_", 1)
            if len(parts) != 2:
                continue
            
            section, key = parts
            if section not in self._configs:
                continue
            
            # Parse value
            parsed_value = self._parse_env_value(env_value)
            self._configs[section].data[key] = parsed_value
            
            if _is_sensitive(key):
                logger.debug(f"  Env override: {section}.{key} = {_mask_value(parsed_value)}")
            else:
                logger.debug(f"  Env override: {section}.{key} = {parsed_value}")
    
    def _parse_env_value(self, value: str) -> Any:
        """Parse environment variable value to appropriate type."""
        # Boolean
        if value.lower() in ("true", "yes", "1", "on"):
            return True
        if value.lower() in ("false", "no", "0", "off"):
            return False
        
        # Integer
        try:
            return int(value)
        except ValueError:
            pass
        
        # Float
        try:
            return float(value)
        except ValueError:
            pass
        
        # JSON
        if value.startswith(("[", "{")):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        
        # String
        return value
    
    def _validate_config(self) -> None:
        """Validate configuration."""
        warnings = []
        
        # Check trading safety
        trading = self._configs.get("trading", ConfigSection("trading"))
        if trading.get("enabled", False) and not trading.get("dry_run", True):
            if not os.getenv(f"{self.env_prefix}TRADING_CONFIRMED"):
                warnings.append(
                    "Live trading enabled without confirmation. "
                    f"Set {self.env_prefix}TRADING_CONFIRMED=true to confirm."
                )
                # Force dry run for safety
                trading.data["dry_run"] = True
        
        for warning in warnings:
            logger.warning(f"CONFIG WARNING: {warning}")
    
    def get(self, section: str, default: Any = None) -> Union[ConfigSection, Dict[str, Any]]:
        """
        Get configuration section.
        
        Args:
            section: Section name
            default: Default value if section not found
            
        Returns:
            Configuration section data
        """
        if not self._loaded:
            self.load_all()
        
        config_section = self._configs.get(section)
        if config_section is None:
            return default if default is not None else {}
        
        return config_section.data
    
    def get_value(self, section: str, key: str, default: Any = None) -> Any:
        """
        Get specific configuration value.
        
        Args:
            section: Section name
            key: Key within section
            default: Default value
            
        Returns:
            Configuration value
        """
        section_data = self.get(section, {})
        if isinstance(section_data, dict):
            return section_data.get(key, default)
        return default
    
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get secret from environment.
        
        Secrets are ONLY loaded from environment variables.
        Never from files.
        
        Args:
            key: Environment variable name (with or without prefix)
            default: Default value
            
        Returns:
            Secret value or default
        """
        # Try with prefix
        value = os.getenv(f"{self.env_prefix}{key}")
        if value:
            return value
        
        # Try without prefix
        value = os.getenv(key)
        if value:
            return value
        
        return default
    
    def require_secret(self, key: str) -> str:
        """
        Get required secret from environment.
        
        Raises ValueError if not found.
        """
        value = self.get_secret(key)
        if value is None:
            raise ValueError(
                f"Required secret not found: {key}. "
                f"Set environment variable {self.env_prefix}{key} or {key}"
            )
        return value
    
    def to_dict(self, mask_sensitive: bool = True) -> Dict[str, Any]:
        """
        Export configuration as dictionary.
        
        Args:
            mask_sensitive: If True, mask sensitive values
            
        Returns:
            Configuration dictionary
        """
        result = {}
        for name, section in self._configs.items():
            section_data = {}
            for key, value in section.data.items():
                if mask_sensitive and _is_sensitive(key):
                    section_data[key] = _mask_value(value)
                else:
                    section_data[key] = value
            result[name] = section_data
        return result


# Global config instance
_config_loader: Optional[ConfigLoader] = None


def get_config(section: Optional[str] = None) -> Union[ConfigLoader, Dict[str, Any]]:
    """
    Get global configuration.
    
    Args:
        section: Optional section name
        
    Returns:
        ConfigLoader instance or section data
    """
    global _config_loader
    
    if _config_loader is None:
        _config_loader = ConfigLoader()
        _config_loader.load_all()
    
    if section:
        return _config_loader.get(section)
    
    return _config_loader


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """
    Get secret from environment.
    
    Convenience function for get_config().get_secret()
    """
    config = get_config()
    if isinstance(config, ConfigLoader):
        return config.get_secret(key, default)
    return default
