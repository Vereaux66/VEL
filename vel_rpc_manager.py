#!/usr/bin/env python3
"""
VEL Multi-Provider RPC Manager
==============================

Production-grade RPC pool abstraction with:
- Multi-provider support per chain
- Health scoring and monitoring
- Automatic failover rotation
- Timeout classification
- Exponential backoff with jitter
- Concurrent request handling
- Provider priority weighting

This module ensures RPC reliability for DeFi operations where
a single provider stall cannot halt execution.

CRITICAL: All RPC calls should flow through this manager.
Direct RPC access bypasses health monitoring and failover.
"""

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar

logger = logging.getLogger("vel.rpc.manager")

T = TypeVar('T')


# =============================================================================
# Configuration
# =============================================================================

class ProviderStatus(Enum):
    """Provider health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"


class TimeoutCategory(Enum):
    """Timeout classification for appropriate handling."""
    NETWORK = "network"           # Network-level timeout
    NODE_OVERLOAD = "node_overload"  # Node is overloaded
    RATE_LIMITED = "rate_limited"    # Rate limit hit
    UNKNOWN = "unknown"


@dataclass
class RPCProviderConfig:
    """Configuration for an RPC provider."""
    name: str
    url: str
    chain_id: int
    priority: int = 1  # Higher = more preferred (1-10)
    timeout_seconds: float = 10.0
    max_retries: int = 3
    is_primary: bool = False
    rate_limit_rps: Optional[int] = None  # Requests per second limit
    

@dataclass
class ProviderHealth:
    """Health metrics for an RPC provider."""
    provider_name: str
    chain_id: int
    status: ProviderStatus = ProviderStatus.HEALTHY
    health_score: float = 100.0  # 0-100 score
    consecutive_failures: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_latency_ms: float = 0.0
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    last_error: Optional[str] = None
    is_rate_limited: bool = False
    rate_limit_reset_time: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None
    
    def update_success(self, latency_ms: float) -> None:
        """Update metrics after successful request."""
        self.total_requests += 1
        self.successful_requests += 1
        self.consecutive_failures = 0
        self.last_success_time = datetime.now(timezone.utc)
        
        # Update rolling average latency
        if self.avg_latency_ms == 0:
            self.avg_latency_ms = latency_ms
        else:
            # Exponential moving average
            self.avg_latency_ms = 0.9 * self.avg_latency_ms + 0.1 * latency_ms
        
        # Recalculate health score
        self._recalculate_score()
    
    def update_failure(self, error: str, category: TimeoutCategory) -> None:
        """Update metrics after failed request."""
        self.total_requests += 1
        self.failed_requests += 1
        self.consecutive_failures += 1
        self.last_failure_time = datetime.now(timezone.utc)
        self.last_error = error
        
        # Handle rate limiting
        if category == TimeoutCategory.RATE_LIMITED:
            self.is_rate_limited = True
            # Set cooldown period with exponential backoff
            cooldown_seconds = min(60 * (2 ** min(self.consecutive_failures, 5)), 3600)
            self.rate_limit_reset_time = datetime.now(timezone.utc) + timedelta(seconds=cooldown_seconds)
        
        # Set cooldown for other failures
        if category != TimeoutCategory.RATE_LIMITED:
            cooldown_seconds = min(5 * (2 ** min(self.consecutive_failures - 1, 6)), 300)
            self.cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=cooldown_seconds)
        
        # Recalculate health score
        self._recalculate_score()
    
    def _recalculate_score(self) -> None:
        """Recalculate health score based on metrics."""
        if self.total_requests == 0:
            self.health_score = 100.0
            self.status = ProviderStatus.HEALTHY
            return
        
        # Base score from success rate
        success_rate = self.successful_requests / self.total_requests
        base_score = success_rate * 100
        
        # Penalty for consecutive failures
        failure_penalty = min(self.consecutive_failures * 15, 50)
        
        # Penalty for high latency (>1s average)
        latency_penalty = 0
        if self.avg_latency_ms > 1000:
            latency_penalty = min((self.avg_latency_ms - 1000) / 100, 20)
        
        # Calculate final score
        self.health_score = max(0, base_score - failure_penalty - latency_penalty)
        
        # Determine status
        if self.health_score >= 80:
            self.status = ProviderStatus.HEALTHY
        elif self.health_score >= 50:
            self.status = ProviderStatus.DEGRADED
        elif self.health_score >= 20:
            self.status = ProviderStatus.UNHEALTHY
        else:
            self.status = ProviderStatus.OFFLINE
    
    def is_available(self) -> bool:
        """Check if provider is available for requests."""
        now = datetime.now(timezone.utc)
        
        # Check cooldown
        if self.cooldown_until and now < self.cooldown_until:
            return False
        
        # Check rate limit
        if self.is_rate_limited and self.rate_limit_reset_time:
            if now < self.rate_limit_reset_time:
                return False
            self.is_rate_limited = False
        
        # Check if completely offline
        if self.status == ProviderStatus.OFFLINE:
            # Allow retry after 5 minutes
            if self.last_failure_time:
                if now > self.last_failure_time + timedelta(minutes=5):
                    return True
            return False
        
        return True


@dataclass
class RPCManagerConfig:
    """Configuration for the RPC manager."""
    # Failover behavior
    max_failover_attempts: int = 5
    failover_delay_ms: int = 100
    
    # Health check
    health_check_interval_seconds: int = 30
    health_check_timeout_seconds: float = 5.0
    
    # Backoff configuration
    initial_backoff_ms: int = 100
    max_backoff_ms: int = 10000
    backoff_multiplier: float = 2.0
    jitter_factor: float = 0.1


# =============================================================================
# RPC Manager Implementation
# =============================================================================

class RPCManager:
    """
    Multi-provider RPC manager with health scoring and failover.
    
    Provides resilient RPC access by:
    - Maintaining a pool of providers per chain
    - Tracking health metrics for each provider
    - Automatically routing to healthy providers
    - Implementing exponential backoff on failures
    - Supporting concurrent request handling
    """
    
    def __init__(self, config: Optional[RPCManagerConfig] = None):
        """
        Initialize the RPC manager.
        
        Args:
            config: Manager configuration (uses defaults if not provided)
        """
        self.config = config or RPCManagerConfig()
        
        # Provider configurations per chain
        self._providers: Dict[int, List[RPCProviderConfig]] = {}
        
        # Health tracking per provider
        self._health: Dict[str, ProviderHealth] = {}  # provider_key -> health
        
        # Web3 connections per provider
        self._web3_connections: Dict[str, Any] = {}  # provider_key -> Web3
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Health check thread
        self._health_check_thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
        
        logger.info("RPC Manager initialized")
    
    def _get_provider_key(self, chain_id: int, provider_name: str) -> str:
        """Generate unique key for a provider."""
        return f"{chain_id}:{provider_name}"
    
    def register_provider(self, provider: RPCProviderConfig) -> None:
        """
        Register an RPC provider.
        
        Args:
            provider: Provider configuration
        """
        with self._lock:
            if provider.chain_id not in self._providers:
                self._providers[provider.chain_id] = []
            
            # Check for duplicates
            existing = [p for p in self._providers[provider.chain_id] 
                       if p.name == provider.name]
            if existing:
                logger.warning(f"Provider {provider.name} already registered for chain {provider.chain_id}")
                return
            
            self._providers[provider.chain_id].append(provider)
            
            # Initialize health tracking
            key = self._get_provider_key(provider.chain_id, provider.name)
            self._health[key] = ProviderHealth(
                provider_name=provider.name,
                chain_id=provider.chain_id
            )
            
            logger.info(
                f"Registered RPC provider: {provider.name} for chain {provider.chain_id}",
                extra={"chain_id": provider.chain_id, "provider": provider.name}
            )
    
    def register_default_providers(self) -> None:
        """Register default providers from chain configuration."""
        from anvel_dex_broker_factory import SUPPORTED_CHAINS
        
        for chain_id, chain_config in SUPPORTED_CHAINS.items():
            if not chain_config.is_active:
                continue
            
            # Register default RPC as primary
            default_provider = RPCProviderConfig(
                name=f"{chain_config.name.lower().replace(' ', '_')}_default",
                url=chain_config.default_rpc,
                chain_id=chain_id,
                priority=5,
                is_primary=True
            )
            self.register_provider(default_provider)
    
    def get_web3(self, chain_id: int) -> Any:
        """
        Get Web3 instance for a chain.
        
        Returns the connection for the healthiest available provider.
        
        Args:
            chain_id: Chain ID
            
        Returns:
            Web3 instance
            
        Raises:
            RuntimeError: If no providers are available
        """
        provider = self._select_provider(chain_id)
        if not provider:
            raise RuntimeError(f"No available RPC providers for chain {chain_id}")
        
        key = self._get_provider_key(chain_id, provider.name)
        
        with self._lock:
            if key not in self._web3_connections:
                from web3 import Web3
                self._web3_connections[key] = Web3(Web3.HTTPProvider(
                    provider.url,
                    request_kwargs={'timeout': provider.timeout_seconds}
                ))
            
            return self._web3_connections[key]
    
    def _select_provider(self, chain_id: int) -> Optional[RPCProviderConfig]:
        """
        Select the best available provider for a chain.
        
        Selection criteria:
        1. Provider must be available (not in cooldown)
        2. Primary providers preferred
        3. Higher priority preferred
        4. Higher health score preferred
        
        Args:
            chain_id: Chain ID
            
        Returns:
            Selected provider or None if none available
        """
        with self._lock:
            providers = self._providers.get(chain_id, [])
            if not providers:
                return None
            
            # Filter available providers
            available = []
            for p in providers:
                key = self._get_provider_key(chain_id, p.name)
                health = self._health.get(key)
                if health and health.is_available():
                    available.append((p, health))
            
            if not available:
                # Try to use any provider if all are in cooldown
                logger.warning(f"All providers for chain {chain_id} in cooldown, using fallback")
                if providers:
                    return providers[0]
                return None
            
            # Sort by: primary status, priority, health score
            available.sort(
                key=lambda x: (
                    x[0].is_primary,
                    x[0].priority,
                    x[1].health_score
                ),
                reverse=True
            )
            
            return available[0][0]
    
    def execute_with_failover(
        self,
        chain_id: int,
        operation: Callable[[Any], T],
        operation_name: str = "rpc_call"
    ) -> T:
        """
        Execute an RPC operation with automatic failover.
        
        Tries multiple providers until one succeeds or all fail.
        
        Args:
            chain_id: Chain ID
            operation: Function that takes Web3 instance and returns result
            operation_name: Name for logging
            
        Returns:
            Operation result
            
        Raises:
            RuntimeError: If all providers fail
        """
        providers = self._get_sorted_providers(chain_id)
        
        if not providers:
            raise RuntimeError(f"No RPC providers configured for chain {chain_id}")
        
        last_error: Optional[Exception] = None
        backoff_ms = self.config.initial_backoff_ms
        
        for attempt in range(self.config.max_failover_attempts):
            for provider in providers:
                key = self._get_provider_key(chain_id, provider.name)
                health = self._health.get(key)
                
                if health and not health.is_available():
                    continue
                
                try:
                    web3 = self._get_web3_for_provider(provider)
                    
                    start_time = time.time()
                    result = operation(web3)
                    latency_ms = (time.time() - start_time) * 1000
                    
                    # Update health on success
                    if health:
                        health.update_success(latency_ms)
                    
                    logger.debug(
                        f"RPC {operation_name} succeeded via {provider.name}",
                        extra={
                            "chain_id": chain_id,
                            "provider": provider.name,
                            "latency_ms": latency_ms
                        }
                    )
                    
                    return result
                    
                except Exception as e:
                    last_error = e
                    category = self._classify_timeout(e)
                    
                    if health:
                        health.update_failure(str(e), category)
                    
                    logger.warning(
                        f"RPC {operation_name} failed via {provider.name}: {e}",
                        extra={
                            "chain_id": chain_id,
                            "provider": provider.name,
                            "error": str(e),
                            "category": category.value
                        }
                    )
            
            # Backoff before retry
            if attempt < self.config.max_failover_attempts - 1:
                jitter = random.uniform(
                    -self.config.jitter_factor * backoff_ms,
                    self.config.jitter_factor * backoff_ms
                )
                sleep_ms = backoff_ms + jitter
                time.sleep(sleep_ms / 1000)
                backoff_ms = min(
                    backoff_ms * self.config.backoff_multiplier,
                    self.config.max_backoff_ms
                )
        
        raise RuntimeError(
            f"All RPC providers failed for chain {chain_id} after "
            f"{self.config.max_failover_attempts} attempts: {last_error}"
        )
    
    def _get_sorted_providers(self, chain_id: int) -> List[RPCProviderConfig]:
        """Get providers sorted by health and priority."""
        with self._lock:
            providers = self._providers.get(chain_id, [])
            
            # Sort by health and priority
            def sort_key(p: RPCProviderConfig) -> tuple:
                key = self._get_provider_key(chain_id, p.name)
                health = self._health.get(key)
                score = health.health_score if health else 50.0
                return (p.is_primary, p.priority, score)
            
            return sorted(providers, key=sort_key, reverse=True)
    
    def _get_web3_for_provider(self, provider: RPCProviderConfig) -> Any:
        """Get or create Web3 instance for a provider."""
        key = self._get_provider_key(provider.chain_id, provider.name)
        
        with self._lock:
            if key not in self._web3_connections:
                from web3 import Web3
                self._web3_connections[key] = Web3(Web3.HTTPProvider(
                    provider.url,
                    request_kwargs={'timeout': provider.timeout_seconds}
                ))
            
            return self._web3_connections[key]
    
    def _classify_timeout(self, error: Exception) -> TimeoutCategory:
        """Classify a timeout/error for appropriate handling."""
        error_str = str(error).lower()
        
        if "rate" in error_str or "429" in error_str or "too many" in error_str:
            return TimeoutCategory.RATE_LIMITED
        
        if "timeout" in error_str or "timed out" in error_str:
            return TimeoutCategory.NETWORK
        
        if "overload" in error_str or "capacity" in error_str:
            return TimeoutCategory.NODE_OVERLOAD
        
        return TimeoutCategory.UNKNOWN
    
    def get_chain_status(self, chain_id: int) -> Dict[str, Any]:
        """
        Get status summary for a chain's providers.
        
        Args:
            chain_id: Chain ID
            
        Returns:
            Status dictionary with provider health info
        """
        with self._lock:
            providers = self._providers.get(chain_id, [])
            status = {
                "chain_id": chain_id,
                "provider_count": len(providers),
                "providers": []
            }
            
            for p in providers:
                key = self._get_provider_key(chain_id, p.name)
                health = self._health.get(key)
                
                provider_status = {
                    "name": p.name,
                    "url": p.url[:50] + "..." if len(p.url) > 50 else p.url,
                    "is_primary": p.is_primary,
                    "priority": p.priority,
                }
                
                if health:
                    provider_status.update({
                        "status": health.status.value,
                        "health_score": round(health.health_score, 1),
                        "total_requests": health.total_requests,
                        "success_rate": round(
                            health.successful_requests / max(health.total_requests, 1) * 100, 1
                        ),
                        "avg_latency_ms": round(health.avg_latency_ms, 1),
                        "consecutive_failures": health.consecutive_failures,
                        "is_available": health.is_available()
                    })
                
                status["providers"].append(provider_status)
            
            # Calculate overall chain health
            if providers:
                avg_health = sum(
                    self._health.get(self._get_provider_key(chain_id, p.name), 
                                    ProviderHealth(p.name, chain_id)).health_score
                    for p in providers
                ) / len(providers)
                status["chain_health_score"] = round(avg_health, 1)
            else:
                status["chain_health_score"] = 0.0
            
            return status
    
    def start_health_monitoring(self) -> None:
        """Start background health monitoring thread."""
        if self._health_check_thread and self._health_check_thread.is_alive():
            return
        
        self._shutdown.clear()
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True,
            name="rpc-health-monitor"
        )
        self._health_check_thread.start()
        logger.info("Started RPC health monitoring")
    
    def stop_health_monitoring(self) -> None:
        """Stop background health monitoring."""
        self._shutdown.set()
        if self._health_check_thread:
            self._health_check_thread.join(timeout=5)
        logger.info("Stopped RPC health monitoring")
    
    def _health_check_loop(self) -> None:
        """Background health check loop."""
        while not self._shutdown.is_set():
            try:
                self._run_health_checks()
            except Exception as e:
                logger.error(f"Health check error: {e}", exc_info=True)
            
            self._shutdown.wait(self.config.health_check_interval_seconds)
    
    def _run_health_checks(self) -> None:
        """Run health checks on all providers."""
        with self._lock:
            chains = list(self._providers.keys())
        
        for chain_id in chains:
            providers = self._providers.get(chain_id, [])
            for provider in providers:
                self._check_provider_health(provider)
    
    def _check_provider_health(self, provider: RPCProviderConfig) -> None:
        """
        Check health of a single provider.
        
        Performs eth_blockNumber call to verify connectivity.
        """
        key = self._get_provider_key(provider.chain_id, provider.name)
        
        try:
            web3 = self._get_web3_for_provider(provider)
            
            start_time = time.time()
            block_number = web3.eth.block_number
            latency_ms = (time.time() - start_time) * 1000
            
            health = self._health.get(key)
            if health:
                health.update_success(latency_ms)
                
            logger.debug(
                f"Health check passed: {provider.name} (block {block_number}, {latency_ms:.0f}ms)"
            )
            
        except Exception as e:
            health = self._health.get(key)
            if health:
                health.update_failure(str(e), self._classify_timeout(e))
            
            logger.warning(f"Health check failed for {provider.name}: {e}")


# =============================================================================
# Global Instance
# =============================================================================

_global_rpc_manager: Optional[RPCManager] = None
_manager_lock = threading.Lock()


def get_rpc_manager() -> RPCManager:
    """
    Get the global RPC manager instance.
    
    Creates and initializes if not already done.
    """
    global _global_rpc_manager
    
    with _manager_lock:
        if _global_rpc_manager is None:
            _global_rpc_manager = RPCManager()
            _global_rpc_manager.register_default_providers()
        
        return _global_rpc_manager


def configure_rpc_manager(config: RPCManagerConfig) -> RPCManager:
    """
    Configure and return the global RPC manager.
    
    Should be called during application startup to customize configuration.
    """
    global _global_rpc_manager
    
    with _manager_lock:
        _global_rpc_manager = RPCManager(config)
        _global_rpc_manager.register_default_providers()
        return _global_rpc_manager
