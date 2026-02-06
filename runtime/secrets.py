#!/usr/bin/env python3
"""
ANVEL Secrets Manager
=====================

Secure secrets and credentials management.
Secrets are ONLY loaded from environment variables or secret managers.
NEVER from configuration files.

Supports:
- Environment variables
- AWS Secrets Manager (optional)
- HashiCorp Vault (optional)
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("anvel.runtime.secrets")


@dataclass
class SecretSpec:
    """Secret specification."""
    name: str
    env_var: str
    required: bool = True
    description: str = ""
    default: Optional[str] = None


# Known secrets used by VEL (DEX-only)
# NOTE: CEX API keys have been removed. VEL enforces DEX-only trading.
KNOWN_SECRETS = {
    # Blockchain RPC endpoints
    "ETHEREUM_RPC_URL": SecretSpec(
        name="ethereum_rpc",
        env_var="ANVEL_ETHEREUM_RPC_URL",
        required=False,
        description="Ethereum RPC endpoint URL",
    ),
    "ARBITRUM_RPC_URL": SecretSpec(
        name="arbitrum_rpc",
        env_var="ANVEL_ARBITRUM_RPC_URL",
        required=False,
        description="Arbitrum RPC endpoint URL",
    ),
    "POLYGON_RPC_URL": SecretSpec(
        name="polygon_rpc",
        env_var="ANVEL_POLYGON_RPC_URL",
        required=False,
        description="Polygon RPC endpoint URL",
    ),
    
    # Wallet private keys
    "WALLET_PRIVATE_KEY": SecretSpec(
        name="wallet_private_key",
        env_var="ANVEL_WALLET_PRIVATE_KEY",
        required=False,
        description="Trading wallet private key (KEEP SECURE)",
    ),
    
    # Database
    "DATABASE_URL": SecretSpec(
        name="database_url",
        env_var="ANVEL_DATABASE_URL",
        required=False,
        description="Database connection string",
        default="sqlite:///data/anvel.db",
    ),
    "REDIS_URL": SecretSpec(
        name="redis_url",
        env_var="ANVEL_REDIS_URL",
        required=False,
        description="Redis connection URL",
    ),
    
    # AWS
    "AWS_ACCESS_KEY_ID": SecretSpec(
        name="aws_access_key",
        env_var="AWS_ACCESS_KEY_ID",
        required=False,
        description="AWS access key ID",
    ),
    "AWS_SECRET_ACCESS_KEY": SecretSpec(
        name="aws_secret_key",
        env_var="AWS_SECRET_ACCESS_KEY",
        required=False,
        description="AWS secret access key",
    ),
    "AWS_REGION": SecretSpec(
        name="aws_region",
        env_var="AWS_REGION",
        required=False,
        description="AWS region",
        default="us-east-1",
    ),
}


class SecretsManager:
    """
    Centralized secrets management.
    
    Secrets are loaded from (in priority order):
    1. AWS Secrets Manager (if configured)
    2. HashiCorp Vault (if configured)
    3. Environment variables
    
    Secrets are NEVER loaded from files.
    """
    
    def __init__(
        self,
        env_prefix: str = "ANVEL_",
        use_aws_secrets: bool = False,
        use_vault: bool = False,
        aws_secret_name: Optional[str] = None,
        vault_path: Optional[str] = None,
    ):
        """
        Initialize secrets manager.
        
        Args:
            env_prefix: Prefix for environment variables
            use_aws_secrets: Enable AWS Secrets Manager
            use_vault: Enable HashiCorp Vault
            aws_secret_name: AWS Secrets Manager secret name
            vault_path: Vault secret path
        """
        self.env_prefix = env_prefix
        self.use_aws_secrets = use_aws_secrets
        self.use_vault = use_vault
        self.aws_secret_name = aws_secret_name or "anvel/production"
        self.vault_path = vault_path or "secret/anvel"
        
        # Cached secrets
        self._cache: Dict[str, str] = {}
        self._loaded = False
        
        # AWS and Vault clients (lazy loaded)
        self._aws_client: Optional[Any] = None
        self._vault_client: Optional[Any] = None
    
    def load_all(self) -> None:
        """Load all secrets from configured sources."""
        if self._loaded:
            return
        
        logger.info("Loading secrets...")
        
        # Load from AWS Secrets Manager
        if self.use_aws_secrets:
            self._load_aws_secrets()
        
        # Load from Vault
        if self.use_vault:
            self._load_vault_secrets()
        
        # Load from environment (always, as override)
        self._load_env_secrets()
        
        self._loaded = True
        
        # Log what was loaded (masked)
        loaded_keys = list(self._cache.keys())
        logger.info(f"Loaded {len(loaded_keys)} secrets")
    
    def _load_aws_secrets(self) -> None:
        """Load secrets from AWS Secrets Manager."""
        try:
            import boto3
            import json
            
            if self._aws_client is None:
                self._aws_client = boto3.client("secretsmanager")
            
            response = self._aws_client.get_secret_value(
                SecretId=self.aws_secret_name
            )
            
            secret_string = response.get("SecretString")
            if secret_string:
                secrets = json.loads(secret_string)
                for key, value in secrets.items():
                    self._cache[key.upper()] = str(value)
                logger.info(f"  Loaded {len(secrets)} secrets from AWS")
            
        except ImportError:
            logger.warning("  boto3 not available, skipping AWS Secrets Manager")
        except Exception as e:
            logger.warning(f"  AWS Secrets Manager error: {e}")
    
    def _load_vault_secrets(self) -> None:
        """Load secrets from HashiCorp Vault."""
        try:
            import hvac
            
            vault_addr = os.getenv("VAULT_ADDR", "http://localhost:8200")
            vault_token = os.getenv("VAULT_TOKEN")
            
            if not vault_token:
                logger.warning("  VAULT_TOKEN not set, skipping Vault")
                return
            
            if self._vault_client is None:
                self._vault_client = hvac.Client(url=vault_addr, token=vault_token)
            
            if not self._vault_client.is_authenticated():
                logger.warning("  Vault authentication failed")
                return
            
            response = self._vault_client.secrets.kv.v2.read_secret_version(
                path=self.vault_path.lstrip("secret/")
            )
            
            secrets = response.get("data", {}).get("data", {})
            for key, value in secrets.items():
                self._cache[key.upper()] = str(value)
            logger.info(f"  Loaded {len(secrets)} secrets from Vault")
            
        except ImportError:
            logger.warning("  hvac not available, skipping Vault")
        except Exception as e:
            logger.warning(f"  Vault error: {e}")
    
    def _load_env_secrets(self) -> None:
        """Load secrets from environment variables."""
        count = 0
        
        for spec in KNOWN_SECRETS.values():
            # Try with prefix
            value = os.getenv(spec.env_var)
            if value:
                self._cache[spec.env_var.replace(self.env_prefix, "")] = value
                count += 1
                continue
            
            # Try without prefix
            key_without_prefix = spec.env_var.replace(self.env_prefix, "")
            value = os.getenv(key_without_prefix)
            if value:
                self._cache[key_without_prefix] = value
                count += 1
        
        # Also load any ANVEL_* environment variables
        for key, value in os.environ.items():
            if key.startswith(self.env_prefix):
                cache_key = key.replace(self.env_prefix, "")
                if cache_key not in self._cache:
                    self._cache[cache_key] = value
                    count += 1
        
        logger.debug(f"  Loaded {count} secrets from environment")
    
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get a secret value.
        
        Args:
            key: Secret key (with or without prefix)
            default: Default value if not found
            
        Returns:
            Secret value or default
        """
        if not self._loaded:
            self.load_all()
        
        # Normalize key
        normalized = key.upper().replace(self.env_prefix, "")
        
        # Check cache
        value = self._cache.get(normalized)
        if value:
            return value
        
        # Check known secrets for default
        spec = KNOWN_SECRETS.get(key.upper()) or KNOWN_SECRETS.get(normalized)
        if spec and spec.default:
            return spec.default
        
        return default
    
    def require(self, key: str) -> str:
        """
        Get a required secret.
        
        Raises ValueError if not found.
        """
        value = self.get(key)
        if value is None:
            raise ValueError(f"Required secret not found: {key}")
        return value
    
    def has(self, key: str) -> bool:
        """Check if a secret exists."""
        return self.get(key) is not None
    
    def validate_required(self, keys: list) -> list:
        """
        Validate that required secrets are present.
        
        Returns list of missing keys.
        """
        missing = []
        for key in keys:
            if not self.has(key):
                missing.append(key)
        return missing
    
    def get_rpc_url(self, network: str) -> Optional[str]:
        """Get RPC URL for a network."""
        key = f"{network.upper()}_RPC_URL"
        return self.get(key)
    
    def get_exchange_credentials(self, exchange: str) -> Dict[str, Optional[str]]:
        """Get exchange API credentials."""
        exchange_upper = exchange.upper()
        return {
            "api_key": self.get(f"{exchange_upper}_API_KEY"),
            "api_secret": self.get(f"{exchange_upper}_API_SECRET"),
            "passphrase": self.get(f"{exchange_upper}_PASSPHRASE"),
        }
    
    def clear_cache(self) -> None:
        """Clear cached secrets."""
        self._cache.clear()
        self._loaded = False


# Global secrets manager instance
_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """Get global secrets manager."""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
        _secrets_manager.load_all()
    return _secrets_manager


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get a secret from the global manager."""
    return get_secrets_manager().get(key, default)


def require_secret(key: str) -> str:
    """Get a required secret from the global manager."""
    return get_secrets_manager().require(key)
