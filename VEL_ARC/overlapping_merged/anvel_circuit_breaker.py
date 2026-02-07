#!/usr/bin/env python3
"""
Circuit Breaker Pattern Implementation for ANVEL
Protects against cascading failures from external APIs and services.
"""

from __future__ import annotations

import time
import threading
from enum import Enum
from typing import Callable, Any, Optional
from dataclasses import dataclass, field
from collections import deque


class CircuitState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit tripped, blocking calls
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close from half-open
    timeout: float = 60.0  # Seconds before trying half-open
    window_size: int = 100  # Rolling window for failure rate

    # Advanced settings
    failure_rate_threshold: float = 0.5  # 50% failure rate triggers open
    min_calls: int = 10  # Minimum calls before checking failure rate


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker"""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None

    # Recent call history (for failure rate calculation)
    recent_calls: deque = field(default_factory=lambda: deque(maxlen=100))


class CircuitBreaker:
    """
    Circuit Breaker to prevent cascading failures.

    Usage:
        breaker = CircuitBreaker("kraken_api")

        @breaker.protected
        def call_kraken():
            return kraken.get_ticker("BTC/USD")

        # Or use context manager
        with breaker:
            result = kraken.get_ticker("BTC/USD")

    States:
        - CLOSED: Normal operation, all calls go through
        - OPEN: Too many failures, reject all calls immediately
        - HALF_OPEN: Testing if service recovered, allow limited calls
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.metrics = CircuitBreakerMetrics()

        self._lock = threading.RLock()
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._opened_at = 0.0

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to call
            *args, **kwargs: Arguments to pass to function

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: Original exception from function
        """
        with self._lock:
            state = self._get_state()

            if state == CircuitState.OPEN:
                self.metrics.rejected_calls += 1
                raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is OPEN")

        # Execute the call
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def protected(self, func: Callable) -> Callable:
        """
        Decorator to protect a function with circuit breaker.

        Usage:
            @breaker.protected
            def my_function():
                # ...
        """

        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)

        return wrapper

    def __enter__(self):
        """Context manager entry"""
        with self._lock:
            state = self._get_state()
            if state == CircuitState.OPEN:
                self.metrics.rejected_calls += 1
                raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is OPEN")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if exc_type is None:
            self._on_success()
        else:
            self._on_failure()
        return False  # Don't suppress exceptions

    def _get_state(self) -> CircuitState:
        """Get current state, transitioning if necessary"""
        if self.state == CircuitState.OPEN:
            # Check if timeout elapsed
            if time.time() - self._opened_at >= self.config.timeout:
                self._transition_to(CircuitState.HALF_OPEN)

        return self.state

    def _on_success(self):
        """Record successful call"""
        with self._lock:
            self.metrics.total_calls += 1
            self.metrics.successful_calls += 1
            self.metrics.last_success_time = time.time()
            self.metrics.recent_calls.append(True)

            if self.state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            elif self.state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = max(0, self._failure_count - 1)

    def _on_failure(self):
        """Record failed call"""
        with self._lock:
            self.metrics.total_calls += 1
            self.metrics.failed_calls += 1
            self.metrics.last_failure_time = time.time()
            self.metrics.recent_calls.append(False)

            self._failure_count += 1
            self._last_failure_time = time.time()

            # Check if should open circuit
            if self.state == CircuitState.HALF_OPEN:
                # Any failure in half-open state reopens circuit
                self._transition_to(CircuitState.OPEN)
            elif self.state == CircuitState.CLOSED:
                # Check failure threshold
                if self._failure_count >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

                # Check failure rate if we have enough calls
                if len(self.metrics.recent_calls) >= self.config.min_calls:
                    failure_rate = self._calculate_failure_rate()
                    if failure_rate >= self.config.failure_rate_threshold:
                        self._transition_to(CircuitState.OPEN)

    def _calculate_failure_rate(self) -> float:
        """Calculate failure rate from recent calls"""
        if not self.metrics.recent_calls:
            return 0.0

        failures = sum(1 for success in self.metrics.recent_calls if not success)
        return failures / len(self.metrics.recent_calls)

    def _transition_to(self, new_state: CircuitState):
        """Transition to a new state"""
        old_state = self.state
        self.state = new_state
        self.metrics.state_changes += 1

        # Reset counters on state change
        if new_state == CircuitState.OPEN:
            self._opened_at = time.time()
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            self._failure_count = 0
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0

        # Log state change (use logging if available, otherwise print)
        try:
            import logging

            logger = logging.getLogger("anvel.circuit_breaker")
            logger.warning(
                "Circuit breaker '%s': %s -> %s",
                self.name, old_state.value, new_state.value
            )
        except ImportError:
            print(
                f"Circuit breaker '{self.name}': {old_state.value} -> {new_state.value}"
            )

    def reset(self):
        """Manually reset circuit breaker to CLOSED state"""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0
            self._success_count = 0

    def get_metrics(self) -> dict:
        """Get current metrics"""
        with self._lock:
            return {
                "name": self.name,
                "state": self.state.value,
                "total_calls": self.metrics.total_calls,
                "successful_calls": self.metrics.successful_calls,
                "failed_calls": self.metrics.failed_calls,
                "rejected_calls": self.metrics.rejected_calls,
                "success_rate": (
                    self.metrics.successful_calls / self.metrics.total_calls
                    if self.metrics.total_calls > 0
                    else 0.0
                ),
                "failure_rate": self._calculate_failure_rate(),
                "state_changes": self.metrics.state_changes,
                "last_failure": self.metrics.last_failure_time,
                "last_success": self.metrics.last_success_time,
            }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""

    pass


class CircuitBreakerRegistry:
    """
    Global registry for circuit breakers.
    Allows centralized management and monitoring.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._breakers = {}
        return cls._instance

    def register(
        self, name: str, config: Optional[CircuitBreakerConfig] = None
    ) -> CircuitBreaker:
        """Register or get a circuit breaker"""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config)
        return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name"""
        return self._breakers.get(name)

    def get_all_metrics(self) -> dict:
        """Get metrics for all circuit breakers"""
        return {name: breaker.get_metrics() for name, breaker in self._breakers.items()}

    def reset_all(self):
        """Reset all circuit breakers"""
        for breaker in self._breakers.values():
            breaker.reset()


# Global registry instance
registry = CircuitBreakerRegistry()


def get_circuit_breaker(
    name: str, config: Optional[CircuitBreakerConfig] = None
) -> CircuitBreaker:
    """
    Get or create a circuit breaker from global registry.

    Args:
        name: Circuit breaker name
        config: Optional configuration

    Returns:
        CircuitBreaker instance
    """
    return registry.register(name, config)


# Example usage
if __name__ == "__main__":
    # Create circuit breaker
    breaker = get_circuit_breaker("example_api")

    # Simulate API calls
    def unstable_api():
        import random

        if random.random() < 0.4:  # 40% failure rate
            raise Exception("API Error")
        return "Success"

    # Test circuit breaker
    for i in range(20):
        try:
            result = breaker.call(unstable_api)
            print(f"Call {i+1}: {result}")
        except CircuitBreakerOpenError:
            print(f"Call {i+1}: Circuit OPEN, skipping")
        except Exception as e:
            print(f"Call {i+1}: Failed - {e}")

        time.sleep(0.1)

    # Print metrics
    print("\nMetrics:", breaker.get_metrics())
