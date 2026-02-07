#!/usr/bin/env python3
"""
VEL Circuit Breaker Manager
============================

Failure modes and emergency controls.
System fails CLOSED - safety over liveness.

Halt triggers:
- Chain RPC degraded/unavailable
- Signer unavailable
- Ledger divergence detected
- Risk limit breach
- Abnormal failure rate
- Manual emergency halt

When halted:
- No new intent acceptance
- No transaction broadcasting
- Existing confirmations still tracked
- System remains in safe state

Recovery:
- Requires explicit operator intervention
- State must be verified before resume
- Circuit breaker reset after root cause fixed
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class HaltReason(Enum):
    """Reasons for system halt."""
    MANUAL = "manual"
    CHAIN_RPC_FAILURE = "chain_rpc_failure"
    SIGNER_UNAVAILABLE = "signer_unavailable"
    LEDGER_DIVERGENCE = "ledger_divergence"
    RISK_BREACH = "risk_breach"
    HIGH_FAILURE_RATE = "high_failure_rate"
    ABNORMAL_BEHAVIOR = "abnormal_behavior"


@dataclass
class CircuitBreakerState:
    """Circuit breaker state."""
    is_halted: bool = False
    halt_reason: Optional[HaltReason] = None
    halted_at: Optional[datetime] = None
    halt_message: Optional[str] = None
    can_auto_recover: bool = False
    
    # Per-chain circuit breakers
    halted_chains: Dict[int, HaltReason] = field(default_factory=dict)
    
    # Per-protocol circuit breakers
    halted_protocols: Dict[str, HaltReason] = field(default_factory=dict)


@dataclass
class HealthMetrics:
    """System health metrics."""
    total_intents: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    rejected_intents: int = 0
    pending_executions: int = 0
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    
    def failure_rate(self) -> float:
        """Calculate failure rate."""
        total = self.successful_executions + self.failed_executions
        if total == 0:
            return 0.0
        return self.failed_executions / total
    
    def success_rate(self) -> float:
        """Calculate success rate."""
        return 1.0 - self.failure_rate()


class CircuitBreakerManager:
    """
    Circuit breaker manager.
    
    Monitors system health and triggers halts when safety conditions are violated.
    System fails closed - halts are sticky and require operator intervention.
    """
    
    # Thresholds
    MAX_FAILURE_RATE = 0.3  # 30% failure rate triggers halt
    MIN_SAMPLE_SIZE = 10     # Minimum executions before checking failure rate
    FAILURE_WINDOW_SECONDS = 300  # 5 minute window for failure rate calculation
    
    def __init__(self):
        """Initialize circuit breaker manager."""
        self._state = CircuitBreakerState()
        self._metrics = HealthMetrics()
        self._lock = threading.Lock()
        
        # Failure tracking
        self._recent_failures: List[datetime] = []
        
        logger.info("Circuit breaker manager initialized")
    
    def is_halted(self) -> bool:
        """Check if system is halted."""
        with self._lock:
            return self._state.is_halted
    
    def is_chain_halted(self, chain_id: int) -> bool:
        """Check if specific chain is halted."""
        with self._lock:
            return chain_id in self._state.halted_chains
    
    def is_protocol_halted(self, protocol: str) -> bool:
        """Check if specific protocol is halted."""
        with self._lock:
            return protocol in self._state.halted_protocols
    
    def trigger_halt(
        self,
        reason: HaltReason,
        message: Optional[str] = None,
        chain_id: Optional[int] = None,
        protocol: Optional[str] = None,
        can_auto_recover: bool = False
    ):
        """
        Trigger system halt.
        
        Args:
            reason: Halt reason
            message: Additional context
            chain_id: If provided, halt only this chain
            protocol: If provided, halt only this protocol
            can_auto_recover: If True, system may auto-recover
        """
        with self._lock:
            if chain_id:
                # Per-chain halt
                self._state.halted_chains[chain_id] = reason
                logger.error(
                    f"CHAIN HALTED: chain_id={chain_id}, reason={reason.value}, msg={message}",
                    extra={
                        "halt_type": "chain",
                        "chain_id": chain_id,
                        "reason": reason.value,
                        "halt_message": message
                    }
                )
            elif protocol:
                # Per-protocol halt
                self._state.halted_protocols[protocol] = reason
                logger.error(
                    f"PROTOCOL HALTED: protocol={protocol}, reason={reason.value}, msg={message}",
                    extra={
                        "halt_type": "protocol",
                        "protocol": protocol,
                        "reason": reason.value,
                        "halt_message": message
                    }
                )
            else:
                # Global halt
                self._state.is_halted = True
                self._state.halt_reason = reason
                self._state.halted_at = datetime.now(timezone.utc)
                self._state.halt_message = message
                self._state.can_auto_recover = can_auto_recover
                
                logger.critical(
                    f"SYSTEM HALTED: reason={reason.value}, msg={message}",
                    extra={
                        "halt_type": "global",
                        "reason": reason.value,
                        "halt_message": message,
                        "can_auto_recover": can_auto_recover
                    }
                )
    
    def manual_halt(self, message: str = "Manual emergency halt"):
        """Trigger manual halt (operator initiated)."""
        self.trigger_halt(HaltReason.MANUAL, message, can_auto_recover=False)
    
    def resume(
        self,
        chain_id: Optional[int] = None,
        protocol: Optional[str] = None
    ) -> bool:
        """
        Resume operations.
        
        Requires operator intervention - cannot be called automatically
        unless can_auto_recover was True.
        
        Args:
            chain_id: If provided, resume only this chain
            protocol: If provided, resume only this protocol
            
        Returns:
            True if resumed successfully
        """
        with self._lock:
            if chain_id:
                # Resume chain
                if chain_id in self._state.halted_chains:
                    del self._state.halted_chains[chain_id]
                    logger.warning(
                        f"Chain resumed: chain_id={chain_id}",
                        extra={"chain_id": chain_id}
                    )
                    return True
            elif protocol:
                # Resume protocol
                if protocol in self._state.halted_protocols:
                    del self._state.halted_protocols[protocol]
                    logger.warning(
                        f"Protocol resumed: protocol={protocol}",
                        extra={"protocol": protocol}
                    )
                    return True
            else:
                # Resume global
                if not self._state.is_halted:
                    logger.info("System already running")
                    return True
                
                self._state.is_halted = False
                self._state.halt_reason = None
                self._state.halted_at = None
                self._state.halt_message = None
                self._state.can_auto_recover = False
                
                logger.warning(
                    "SYSTEM RESUMED",
                    extra={"resumed_at": datetime.now(timezone.utc).isoformat()}
                )
                return True
        
        return False
    
    def record_intent(self):
        """Record incoming intent."""
        with self._lock:
            self._metrics.total_intents += 1
    
    def record_success(self):
        """Record successful execution."""
        with self._lock:
            self._metrics.successful_executions += 1
            self._metrics.last_success_at = datetime.now(timezone.utc)
    
    def record_failure(self):
        """Record failed execution."""
        now = datetime.now(timezone.utc)
        
        with self._lock:
            self._metrics.failed_executions += 1
            self._metrics.last_failure_at = now
            self._recent_failures.append(now)
            
            # Check failure rate
            self._check_failure_rate()
    
    def record_rejection(self):
        """Record rejected intent."""
        with self._lock:
            self._metrics.rejected_intents += 1
    
    def record_pending(self, delta: int = 1):
        """Update pending execution count."""
        with self._lock:
            self._metrics.pending_executions += delta
            if self._metrics.pending_executions < 0:
                self._metrics.pending_executions = 0
    
    def _check_failure_rate(self):
        """Check if failure rate exceeds threshold."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.FAILURE_WINDOW_SECONDS)
        
        # Remove old failures
        self._recent_failures = [f for f in self._recent_failures if f > cutoff]
        
        # Need minimum sample size
        total = self._metrics.successful_executions + self._metrics.failed_executions
        if total < self.MIN_SAMPLE_SIZE:
            return
        
        # Check failure rate
        failure_rate = self._metrics.failure_rate()
        
        if failure_rate > self.MAX_FAILURE_RATE:
            self.trigger_halt(
                HaltReason.HIGH_FAILURE_RATE,
                f"Failure rate {failure_rate:.1%} exceeds threshold {self.MAX_FAILURE_RATE:.1%}",
                can_auto_recover=False
            )
    
    def check_chain_health(self, chain_id: int, is_healthy: bool) -> bool:
        """
        Check and update chain health.
        
        Args:
            chain_id: Chain ID
            is_healthy: Current health status
            
        Returns:
            True if chain is operational
        """
        if not is_healthy:
            if not self.is_chain_halted(chain_id):
                self.trigger_halt(
                    HaltReason.CHAIN_RPC_FAILURE,
                    f"Chain {chain_id} RPC unhealthy",
                    chain_id=chain_id,
                    can_auto_recover=True
                )
            return False
        else:
            # Chain is healthy - auto-recover if allowed
            if self.is_chain_halted(chain_id):
                reason = self._state.halted_chains.get(chain_id)
                if reason == HaltReason.CHAIN_RPC_FAILURE:
                    logger.info(f"Chain {chain_id} recovered - auto-resuming")
                    self.resume(chain_id=chain_id)
            return True
    
    def check_signer_health(self, is_available: bool):
        """Check signer health."""
        if not is_available and not self.is_halted():
            self.trigger_halt(
                HaltReason.SIGNER_UNAVAILABLE,
                "Transaction signer unavailable",
                can_auto_recover=False
            )
    
    def get_state(self) -> Dict:
        """Get circuit breaker state."""
        with self._lock:
            return {
                "is_halted": self._state.is_halted,
                "halt_reason": self._state.halt_reason.value if self._state.halt_reason else None,
                "halted_at": self._state.halted_at.isoformat() if self._state.halted_at else None,
                "halt_message": self._state.halt_message,
                "can_auto_recover": self._state.can_auto_recover,
                "halted_chains": {k: v.value for k, v in self._state.halted_chains.items()},
                "halted_protocols": {k: v.value for k, v in self._state.halted_protocols.items()},
            }
    
    def get_metrics(self) -> Dict:
        """Get health metrics."""
        with self._lock:
            return {
                "total_intents": self._metrics.total_intents,
                "successful_executions": self._metrics.successful_executions,
                "failed_executions": self._metrics.failed_executions,
                "rejected_intents": self._metrics.rejected_intents,
                "pending_executions": self._metrics.pending_executions,
                "failure_rate": self._metrics.failure_rate(),
                "success_rate": self._metrics.success_rate(),
                "last_success_at": self._metrics.last_success_at.isoformat() if self._metrics.last_success_at else None,
                "last_failure_at": self._metrics.last_failure_at.isoformat() if self._metrics.last_failure_at else None,
            }
    
    def reset_metrics(self):
        """Reset health metrics (admin function)."""
        with self._lock:
            self._metrics = HealthMetrics()
            self._recent_failures.clear()
            logger.warning("Health metrics reset")


# =============================================================================
# SERVICE-LEVEL CIRCUIT BREAKER (merged from anvel_circuit_breaker.py)
# =============================================================================
# Provides decorator and context manager patterns for protecting individual
# service calls (e.g., RPC endpoints, external APIs).

from enum import Enum as BaseEnum
from collections import deque
from typing import Callable, Any


class ServiceCircuitState(BaseEnum):
    """Circuit breaker states for service-level protection."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit tripped, blocking calls
    HALF_OPEN = "half_open"  # Testing if service recovered


class ServiceCircuitBreakerConfig:
    """Configuration for service-level circuit breaker."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 60.0,
        window_size: int = 100,
        failure_rate_threshold: float = 0.5,
        min_calls: int = 10
    ):
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.window_size = window_size
        self.failure_rate_threshold = failure_rate_threshold
        self.min_calls = min_calls


class ServiceCircuitBreakerOpenError(Exception):
    """Raised when service circuit breaker is open."""
    pass


class ServiceCircuitBreaker:
    """
    Service-level circuit breaker for protecting individual service calls.
    
    Merged from anvel_circuit_breaker.py - provides decorator and context
    manager patterns for protecting RPC calls, external APIs, etc.
    
    Usage:
        breaker = ServiceCircuitBreaker("ethereum_rpc")
        
        @breaker.protected
        def call_rpc():
            return web3.eth.block_number
        
        # Or use context manager
        with breaker:
            result = web3.eth.block_number
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[ServiceCircuitBreakerConfig] = None
    ):
        self.name = name
        self.config = config or ServiceCircuitBreakerConfig()
        self.state = ServiceCircuitState.CLOSED
        
        self._lock = threading.RLock()
        self._failure_count = 0
        self._success_count = 0
        self._opened_at = 0.0
        self._recent_calls: deque = deque(maxlen=self.config.window_size)
        
        # Metrics
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.rejected_calls = 0
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Raises:
            ServiceCircuitBreakerOpenError: If circuit is open
        """
        with self._lock:
            state = self._get_state()
            if state == ServiceCircuitState.OPEN:
                self.rejected_calls += 1
                raise ServiceCircuitBreakerOpenError(
                    f"Service circuit breaker '{self.name}' is OPEN"
                )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise
    
    def protected(self, func: Callable) -> Callable:
        """Decorator to protect a function with circuit breaker."""
        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)
        return wrapper
    
    def __enter__(self):
        """Context manager entry."""
        with self._lock:
            state = self._get_state()
            if state == ServiceCircuitState.OPEN:
                self.rejected_calls += 1
                raise ServiceCircuitBreakerOpenError(
                    f"Service circuit breaker '{self.name}' is OPEN"
                )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type is None:
            self._on_success()
        else:
            self._on_failure()
        return False
    
    def _get_state(self) -> ServiceCircuitState:
        """Get current state, transitioning if necessary."""
        import time
        if self.state == ServiceCircuitState.OPEN:
            if time.time() - self._opened_at >= self.config.timeout:
                self._transition_to(ServiceCircuitState.HALF_OPEN)
        return self.state
    
    def _on_success(self):
        """Record successful call."""
        import time
        with self._lock:
            self.total_calls += 1
            self.successful_calls += 1
            self._recent_calls.append(True)
            
            if self.state == ServiceCircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition_to(ServiceCircuitState.CLOSED)
            elif self.state == ServiceCircuitState.CLOSED:
                self._failure_count = max(0, self._failure_count - 1)
    
    def _on_failure(self):
        """Record failed call."""
        import time
        with self._lock:
            self.total_calls += 1
            self.failed_calls += 1
            self._recent_calls.append(False)
            self._failure_count += 1
            
            if self.state == ServiceCircuitState.HALF_OPEN:
                self._transition_to(ServiceCircuitState.OPEN)
            elif self.state == ServiceCircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    self._transition_to(ServiceCircuitState.OPEN)
                
                if len(self._recent_calls) >= self.config.min_calls:
                    failure_rate = self._calculate_failure_rate()
                    if failure_rate >= self.config.failure_rate_threshold:
                        self._transition_to(ServiceCircuitState.OPEN)
    
    def _calculate_failure_rate(self) -> float:
        """Calculate failure rate from recent calls."""
        if not self._recent_calls:
            return 0.0
        failures = sum(1 for success in self._recent_calls if not success)
        return failures / len(self._recent_calls)
    
    def _transition_to(self, new_state: ServiceCircuitState):
        """Transition to a new state."""
        import time
        old_state = self.state
        self.state = new_state
        
        if new_state == ServiceCircuitState.OPEN:
            self._opened_at = time.time()
            self._success_count = 0
        elif new_state in (ServiceCircuitState.HALF_OPEN, ServiceCircuitState.CLOSED):
            self._failure_count = 0
            self._success_count = 0
        
        logger.warning(
            f"Service circuit breaker '{self.name}': {old_state.value} -> {new_state.value}"
        )
    
    def reset(self):
        """Manually reset to CLOSED state."""
        with self._lock:
            self._transition_to(ServiceCircuitState.CLOSED)
    
    def get_metrics(self) -> Dict:
        """Get current metrics."""
        with self._lock:
            return {
                "name": self.name,
                "state": self.state.value,
                "total_calls": self.total_calls,
                "successful_calls": self.successful_calls,
                "failed_calls": self.failed_calls,
                "rejected_calls": self.rejected_calls,
                "failure_rate": self._calculate_failure_rate(),
            }
