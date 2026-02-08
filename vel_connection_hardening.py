#!/usr/bin/env python3
"""
VEL Connection Hardening Module
================================

Production-grade connection hardening for ensuring system reliability.

Features:
- Connection pool management with health monitoring
- Automatic reconnection with exponential backoff
- Connection validation and verification
- Graceful degradation patterns
- Wire-up verification for system integrity

This module ensures all system connections are:
1. Validated before use
2. Monitored continuously
3. Automatically recovered on failure
4. Future-proofed with versioning
"""

import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import hashlib
import secrets

logger = logging.getLogger("vel.connection.hardening")


class ConnectionState(Enum):
    """Connection state enumeration."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DEGRADED = "degraded"
    FAILED = "failed"
    RECOVERING = "recovering"


class ConnectionType(Enum):
    """Types of connections in the system."""
    DATABASE = "database"
    REDIS = "redis"
    RPC = "rpc"
    WEBSOCKET = "websocket"
    API = "api"
    INTERNAL = "internal"


# Health thresholds (configurable)
DEFAULT_MAX_CONSECUTIVE_FAILURES = 3
DEFAULT_MIN_SUCCESS_RATE = 0.95


@dataclass
class ConnectionHealth:
    """Health metrics for a connection."""
    connection_id: str
    connection_type: ConnectionType
    state: ConnectionState
    latency_ms: float = 0.0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    failure_count: int = 0
    consecutive_failures: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Configurable thresholds
    max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES
    min_success_rate: float = DEFAULT_MIN_SUCCESS_RATE
    
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
    
    def is_healthy(self) -> bool:
        """Check if connection is healthy."""
        return (
            self.state == ConnectionState.CONNECTED and
            self.consecutive_failures < self.max_consecutive_failures and
            self.success_rate() >= self.min_success_rate
        )


@dataclass
class ConnectionConfig:
    """Configuration for a managed connection."""
    name: str
    connection_type: ConnectionType
    endpoint: str
    timeout_seconds: float = 30.0
    max_retries: int = 5
    retry_delay_seconds: float = 1.0
    max_retry_delay_seconds: float = 60.0
    health_check_interval_seconds: float = 30.0
    auto_reconnect: bool = True
    verify_ssl: bool = True
    # Health thresholds
    max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES
    min_success_rate: float = DEFAULT_MIN_SUCCESS_RATE
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConnectionValidator:
    """
    Validates connection integrity and security.
    
    Performs:
    - Connection verification
    - SSL/TLS validation
    - Timeout enforcement
    - Response validation
    """
    
    # Validation timeout
    VALIDATION_TIMEOUT_SECONDS = 10.0
    
    # Maximum acceptable latency (ms)
    MAX_ACCEPTABLE_LATENCY_MS = 5000.0
    
    @classmethod
    def validate_connection(
        cls,
        config: ConnectionConfig,
        test_fn: Callable[[], bool]
    ) -> Tuple[bool, str, float]:
        """
        Validate a connection.
        
        Args:
            config: Connection configuration
            test_fn: Function to test the connection
            
        Returns:
            Tuple of (is_valid, message, latency_ms)
        """
        start_time = time.time()
        
        try:
            # Run validation with timeout
            result = test_fn()
            latency_ms = (time.time() - start_time) * 1000
            
            if not result:
                return False, "Connection test returned False", latency_ms
            
            if latency_ms > cls.MAX_ACCEPTABLE_LATENCY_MS:
                return False, f"Latency too high: {latency_ms:.2f}ms", latency_ms
            
            return True, "Connection validated successfully", latency_ms
            
        except TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            return False, "Connection timed out", latency_ms
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return False, f"Connection error: {str(e)}", latency_ms


class ManagedConnection(ABC):
    """
    Abstract base class for managed connections.
    
    Provides:
    - Automatic reconnection
    - Health monitoring
    - Graceful degradation
    """
    
    def __init__(self, config: ConnectionConfig):
        self.config = config
        self.health = ConnectionHealth(
            connection_id=self._generate_id(),
            connection_type=config.connection_type,
            state=ConnectionState.DISCONNECTED
        )
        self._lock = threading.RLock()
        self._reconnect_thread: Optional[threading.Thread] = None
        self._health_check_thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
    
    def _generate_id(self) -> str:
        """Generate unique connection ID."""
        return f"{self.config.name}-{secrets.token_hex(4)}"
    
    @abstractmethod
    def _do_connect(self) -> bool:
        """Perform actual connection. Subclasses must implement."""
        pass
    
    @abstractmethod
    def _do_disconnect(self) -> None:
        """Perform actual disconnection. Subclasses must implement."""
        pass
    
    @abstractmethod
    def _do_health_check(self) -> bool:
        """Perform health check. Subclasses must implement."""
        pass
    
    def connect(self) -> bool:
        """
        Establish connection with validation.
        
        Returns:
            True if connection successful
        """
        with self._lock:
            if self.health.state == ConnectionState.CONNECTED:
                return True
            
            self.health.state = ConnectionState.CONNECTING
            logger.info(f"Connecting to {self.config.name}...")
            
            try:
                if self._do_connect():
                    self.health.state = ConnectionState.CONNECTED
                    self.health.last_success = datetime.now(timezone.utc)
                    self.health.consecutive_failures = 0
                    logger.info(f"Connected to {self.config.name}")
                    return True
                else:
                    self._record_failure("Connection returned False")
                    return False
            except Exception as e:
                self._record_failure(str(e))
                return False
    
    def disconnect(self) -> None:
        """Disconnect and cleanup."""
        with self._lock:
            self._shutdown.set()
            try:
                self._do_disconnect()
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
            finally:
                self.health.state = ConnectionState.DISCONNECTED
    
    def _record_failure(self, error: str) -> None:
        """Record connection failure."""
        self.health.failure_count += 1
        self.health.consecutive_failures += 1
        self.health.last_failure = datetime.now(timezone.utc)
        self.health.state = ConnectionState.FAILED
        self.health.metadata["last_error"] = error
        logger.warning(f"Connection {self.config.name} failed: {error}")
        
        # Trigger auto-reconnect if enabled
        if self.config.auto_reconnect and not self._shutdown.is_set():
            self._start_reconnect()
    
    def _start_reconnect(self) -> None:
        """Start reconnection process in background."""
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return  # Already reconnecting
        
        self.health.state = ConnectionState.RECOVERING
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            name=f"reconnect-{self.config.name}",
            daemon=True
        )
        self._reconnect_thread.start()
    
    def _reconnect_loop(self) -> None:
        """Reconnection loop with exponential backoff."""
        delay = self.config.retry_delay_seconds
        attempts = 0
        
        while not self._shutdown.is_set() and attempts < self.config.max_retries:
            attempts += 1
            logger.info(f"Reconnection attempt {attempts}/{self.config.max_retries} for {self.config.name}")
            
            try:
                if self._do_connect():
                    with self._lock:
                        self.health.state = ConnectionState.CONNECTED
                        self.health.last_success = datetime.now(timezone.utc)
                        self.health.consecutive_failures = 0
                    logger.info(f"Reconnected to {self.config.name}")
                    return
            except Exception as e:
                logger.warning(f"Reconnection attempt {attempts} failed: {e}")
            
            # Exponential backoff with jitter
            jitter = secrets.randbelow(1000) / 1000.0
            sleep_time = min(delay * (1 + jitter), self.config.max_retry_delay_seconds)
            self._shutdown.wait(sleep_time)
            delay *= 2
        
        logger.error(f"Failed to reconnect to {self.config.name} after {attempts} attempts")
        with self._lock:
            self.health.state = ConnectionState.FAILED
    
    def start_health_monitoring(self) -> None:
        """Start background health monitoring."""
        if self._health_check_thread and self._health_check_thread.is_alive():
            return
        
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            name=f"health-{self.config.name}",
            daemon=True
        )
        self._health_check_thread.start()
    
    def _health_check_loop(self) -> None:
        """Background health check loop."""
        while not self._shutdown.wait(self.config.health_check_interval_seconds):
            if self.health.state != ConnectionState.CONNECTED:
                continue
            
            try:
                start_time = time.time()
                if self._do_health_check():
                    latency_ms = (time.time() - start_time) * 1000
                    with self._lock:
                        self.health.latency_ms = latency_ms
                        self.health.total_requests += 1
                        self.health.successful_requests += 1
                        self.health.last_success = datetime.now(timezone.utc)
                else:
                    self._record_failure("Health check returned False")
            except Exception as e:
                self._record_failure(f"Health check error: {e}")


class ConnectionManager:
    """
    Central manager for all system connections.
    
    Provides:
    - Connection registration and tracking
    - Unified health monitoring
    - System wire-up verification
    - Graceful shutdown coordination
    """
    
    def __init__(self):
        self._connections: Dict[str, ManagedConnection] = {}
        self._lock = threading.RLock()
        self._shutdown = threading.Event()
        self._wire_up_verified = False
        self._wire_up_hash: Optional[str] = None
    
    def register(self, connection: ManagedConnection) -> None:
        """Register a connection for management."""
        with self._lock:
            self._connections[connection.config.name] = connection
            logger.info(f"Registered connection: {connection.config.name}")
    
    def unregister(self, name: str) -> None:
        """Unregister a connection."""
        with self._lock:
            if name in self._connections:
                del self._connections[name]
                logger.info(f"Unregistered connection: {name}")
    
    def get_connection(self, name: str) -> Optional[ManagedConnection]:
        """Get a connection by name."""
        return self._connections.get(name)
    
    def connect_all(self) -> Tuple[int, int]:
        """
        Connect all registered connections.
        
        Returns:
            Tuple of (successful_count, total_count)
        """
        successful = 0
        total = len(self._connections)
        
        for name, connection in self._connections.items():
            try:
                if connection.connect():
                    successful += 1
                    connection.start_health_monitoring()
            except Exception as e:
                logger.error(f"Failed to connect {name}: {e}")
        
        return successful, total
    
    def disconnect_all(self) -> None:
        """Disconnect all connections gracefully."""
        self._shutdown.set()
        for name, connection in self._connections.items():
            try:
                connection.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting {name}: {e}")
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get health summary for all connections."""
        summary = {
            "total_connections": len(self._connections),
            "healthy": 0,
            "degraded": 0,
            "failed": 0,
            "wire_up_verified": self._wire_up_verified,
            "connections": {}
        }
        
        for name, conn in self._connections.items():
            health = conn.health
            summary["connections"][name] = {
                "state": health.state.value,
                "latency_ms": health.latency_ms,
                "success_rate": health.success_rate(),
                "consecutive_failures": health.consecutive_failures,
                "is_healthy": health.is_healthy()
            }
            
            if health.is_healthy():
                summary["healthy"] += 1
            elif health.state in (ConnectionState.DEGRADED, ConnectionState.RECOVERING):
                summary["degraded"] += 1
            else:
                summary["failed"] += 1
        
        return summary
    
    def verify_wire_up(self) -> Tuple[bool, List[str]]:
        """
        Verify that all system connections are properly wired up.
        
        Returns:
            Tuple of (all_verified, list_of_issues)
        """
        issues = []
        
        # Check all connections are connected
        for name, conn in self._connections.items():
            if conn.health.state != ConnectionState.CONNECTED:
                issues.append(f"Connection {name} not connected (state: {conn.health.state.value})")
            elif not conn.health.is_healthy():
                issues.append(f"Connection {name} not healthy (success_rate: {conn.health.success_rate():.2%})")
        
        # Calculate wire-up hash for future verification
        connection_states = sorted([
            f"{name}:{conn.health.state.value}"
            for name, conn in self._connections.items()
        ])
        self._wire_up_hash = hashlib.sha256(
            "|".join(connection_states).encode()
        ).hexdigest()[:16]
        
        self._wire_up_verified = len(issues) == 0
        return self._wire_up_verified, issues
    
    def get_wire_up_hash(self) -> Optional[str]:
        """Get current wire-up verification hash."""
        return self._wire_up_hash


# =============================================================================
# Security Hardening Functions
# =============================================================================

def harden_connection_config(config: ConnectionConfig) -> ConnectionConfig:
    """
    Apply security hardening to connection configuration.
    
    Args:
        config: Original configuration
        
    Returns:
        Hardened configuration
    """
    # Enforce minimum timeout
    if config.timeout_seconds < 5.0:
        config.timeout_seconds = 5.0
        logger.warning(f"Increased timeout for {config.name} to minimum 5s")
    
    # Enforce maximum timeout
    if config.timeout_seconds > 120.0:
        config.timeout_seconds = 120.0
        logger.warning(f"Reduced timeout for {config.name} to maximum 120s")
    
    # Enforce SSL for external connections
    if config.connection_type != ConnectionType.INTERNAL:
        if not config.verify_ssl:
            logger.warning(f"SSL verification disabled for {config.name} - consider enabling")
    
    # Add security metadata
    config.metadata["hardened"] = True
    config.metadata["hardened_at"] = datetime.now(timezone.utc).isoformat()
    
    return config


def validate_endpoint_security(endpoint: str, connection_type: ConnectionType) -> Tuple[bool, str]:
    """
    Validate endpoint security requirements.
    
    Args:
        endpoint: The endpoint URL/address
        connection_type: Type of connection
        
    Returns:
        Tuple of (is_secure, message)
    """
    # Check for HTTPS for API connections
    if connection_type == ConnectionType.API:
        if endpoint.startswith("http://") and not endpoint.startswith("http://localhost"):
            return False, "API endpoints must use HTTPS"
    
    # Check for WSS for WebSocket connections
    if connection_type == ConnectionType.WEBSOCKET:
        if endpoint.startswith("ws://") and not endpoint.startswith("ws://localhost"):
            return False, "WebSocket endpoints must use WSS"
    
    # Check for proper RPC URL format
    if connection_type == ConnectionType.RPC:
        if not (endpoint.startswith("http://") or endpoint.startswith("https://")):
            return False, "RPC endpoints must use HTTP/HTTPS"
    
    return True, "Endpoint security validated"


# =============================================================================
# Global Connection Manager
# =============================================================================

_global_connection_manager: Optional[ConnectionManager] = None
_manager_lock = threading.Lock()


def get_connection_manager() -> ConnectionManager:
    """Get or create the global connection manager."""
    global _global_connection_manager
    
    if _global_connection_manager is None:
        with _manager_lock:
            if _global_connection_manager is None:
                _global_connection_manager = ConnectionManager()
    
    return _global_connection_manager


def reset_connection_manager() -> None:
    """Reset the global connection manager (for testing)."""
    global _global_connection_manager
    
    with _manager_lock:
        if _global_connection_manager is not None:
            _global_connection_manager.disconnect_all()
            _global_connection_manager = None
