#!/usr/bin/env python3
"""
ANVEL Runtime Package
=====================

Single-node runtime boot system for ANVEL trading platform.
Implements deterministic startup sequence without Kubernetes dependency.

Components:
- RuntimeBoot: Master launch process
- ConfigLoader: Centralized configuration
- ServiceRegistry: Service dependency management
- HealthChecker: Component health verification
"""

from .boot import RuntimeBoot, RuntimeState, RuntimeConfig
from .config_loader import ConfigLoader, get_config
from .service_registry import ServiceRegistry, ServiceStatus
from .health import HealthChecker, HealthStatus
from .secrets import SecretsManager, get_secret
from .pipeline import ExecutionPipeline, ExecutionPayload, ExecutionResult

__all__ = [
    # Boot
    "RuntimeBoot",
    "RuntimeState",
    "RuntimeConfig",
    # Config
    "ConfigLoader",
    "get_config",
    # Services
    "ServiceRegistry",
    "ServiceStatus",
    # Health
    "HealthChecker",
    "HealthStatus",
    # Secrets
    "SecretsManager",
    "get_secret",
    # Pipeline
    "ExecutionPipeline",
    "ExecutionPayload",
    "ExecutionResult",
]

__version__ = "1.0.0"
