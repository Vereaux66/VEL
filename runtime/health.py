#!/usr/bin/env python3
"""
ANVEL Health Checker
====================

Centralized health checking for ANVEL runtime.
Monitors component health and triggers alerts.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("anvel.runtime.health")


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Health check definition."""
    name: str
    checker: Callable[[], HealthStatus]
    interval_seconds: int = 30
    timeout_seconds: int = 10
    critical: bool = False
    last_check: Optional[float] = None
    last_status: HealthStatus = HealthStatus.UNKNOWN
    consecutive_failures: int = 0


@dataclass  
class HealthReport:
    """Health check report."""
    timestamp: float
    overall_status: HealthStatus
    checks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    critical_failures: List[str] = field(default_factory=list)


class HealthChecker:
    """
    Centralized health monitoring.
    
    Features:
    - Periodic health checks
    - Configurable intervals per check
    - Critical failure detection
    - Health history tracking
    """
    
    def __init__(
        self,
        event_bus: Optional[Any] = None,
        default_interval: int = 30,
    ):
        """
        Initialize health checker.
        
        Args:
            event_bus: Optional event bus for health events
            default_interval: Default check interval in seconds
        """
        self.event_bus = event_bus
        self.default_interval = default_interval
        
        self._checks: Dict[str, HealthCheck] = {}
        self._lock = threading.RLock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._history: List[HealthReport] = []
        self._max_history = 100
    
    def register(
        self,
        name: str,
        checker: Callable[[], HealthStatus],
        interval: Optional[int] = None,
        timeout: int = 10,
        critical: bool = False,
    ) -> None:
        """
        Register a health check.
        
        Args:
            name: Unique check name
            checker: Callable returning HealthStatus
            interval: Check interval in seconds
            timeout: Check timeout in seconds
            critical: If True, failure triggers system alert
        """
        with self._lock:
            self._checks[name] = HealthCheck(
                name=name,
                checker=checker,
                interval_seconds=interval or self.default_interval,
                timeout_seconds=timeout,
                critical=critical,
            )
        logger.debug(f"Registered health check: {name}")
    
    def unregister(self, name: str) -> None:
        """Unregister a health check."""
        with self._lock:
            if name in self._checks:
                del self._checks[name]
    
    def start(self) -> None:
        """Start background health checking."""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(
            target=self._check_loop,
            daemon=True,
            name="health-checker",
        )
        self._thread.start()
        logger.info("Health checker started")
    
    def stop(self) -> None:
        """Stop background health checking."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Health checker stopped")
    
    def _check_loop(self) -> None:
        """Background health check loop."""
        while self._running:
            try:
                self._run_due_checks()
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
            
            time.sleep(1)  # Check every second for due checks
    
    def _run_due_checks(self) -> None:
        """Run any due health checks."""
        now = time.time()
        
        with self._lock:
            checks_to_run = [
                check for check in self._checks.values()
                if check.last_check is None or
                   now - check.last_check >= check.interval_seconds
            ]
        
        for check in checks_to_run:
            self._run_check(check)
    
    def _run_check(self, check: HealthCheck) -> HealthStatus:
        """Run a single health check."""
        try:
            # Run check with timeout
            status = check.checker()
            
            with self._lock:
                check.last_check = time.time()
                check.last_status = status
                
                if status == HealthStatus.HEALTHY:
                    check.consecutive_failures = 0
                else:
                    check.consecutive_failures += 1
            
            # Publish event if unhealthy
            if status == HealthStatus.UNHEALTHY:
                logger.warning(f"Health check failed: {check.name}")
                if self.event_bus and hasattr(self.event_bus, 'publish'):
                    self.event_bus.publish("health.check_failed", {
                        "check": check.name,
                        "status": status.value,
                        "critical": check.critical,
                        "consecutive_failures": check.consecutive_failures,
                    })
            
            return status
            
        except Exception as e:
            logger.error(f"Health check error ({check.name}): {e}")
            with self._lock:
                check.last_check = time.time()
                check.last_status = HealthStatus.UNKNOWN
                check.consecutive_failures += 1
            return HealthStatus.UNKNOWN
    
    def check_now(self, name: Optional[str] = None) -> HealthReport:
        """
        Run health checks immediately.
        
        Args:
            name: Optional specific check name (None = all)
            
        Returns:
            Health report
        """
        with self._lock:
            if name:
                checks = [self._checks[name]] if name in self._checks else []
            else:
                checks = list(self._checks.values())
        
        for check in checks:
            self._run_check(check)
        
        return self.get_report()
    
    def get_report(self) -> HealthReport:
        """Get current health report."""
        now = time.time()
        
        with self._lock:
            checks_data = {}
            warnings = []
            critical_failures = []
            
            for name, check in self._checks.items():
                checks_data[name] = {
                    "status": check.last_status.value,
                    "last_check": check.last_check,
                    "age_seconds": now - check.last_check if check.last_check else None,
                    "consecutive_failures": check.consecutive_failures,
                    "critical": check.critical,
                }
                
                if check.last_status == HealthStatus.UNHEALTHY:
                    if check.critical:
                        critical_failures.append(name)
                    else:
                        warnings.append(f"{name} is unhealthy")
                elif check.last_status == HealthStatus.DEGRADED:
                    warnings.append(f"{name} is degraded")
            
            # Determine overall status
            if critical_failures:
                overall = HealthStatus.UNHEALTHY
            elif warnings:
                overall = HealthStatus.DEGRADED
            else:
                overall = HealthStatus.HEALTHY
            
            report = HealthReport(
                timestamp=now,
                overall_status=overall,
                checks=checks_data,
                warnings=warnings,
                critical_failures=critical_failures,
            )
            
            # Store in history
            self._history.append(report)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]
            
            return report
    
    def get_status(self, name: str) -> HealthStatus:
        """Get status of a specific check."""
        with self._lock:
            check = self._checks.get(name)
            return check.last_status if check else HealthStatus.UNKNOWN
    
    def is_healthy(self) -> bool:
        """Quick check if system is healthy."""
        with self._lock:
            for check in self._checks.values():
                if check.critical and check.last_status == HealthStatus.UNHEALTHY:
                    return False
        return True
    
    def get_history(self, limit: int = 10) -> List[HealthReport]:
        """Get recent health history."""
        with self._lock:
            return self._history[-limit:]


# Factory for common health checks
def create_process_health_check() -> Callable[[], HealthStatus]:
    """Create health check for process metrics."""
    def check():
        try:
            import os
            import psutil
            
            process = psutil.Process(os.getpid())
            memory_pct = process.memory_percent()
            cpu_pct = process.cpu_percent(interval=0.1)
            
            if memory_pct > 90 or cpu_pct > 95:
                return HealthStatus.UNHEALTHY
            elif memory_pct > 70 or cpu_pct > 80:
                return HealthStatus.DEGRADED
            return HealthStatus.HEALTHY
            
        except ImportError:
            return HealthStatus.UNKNOWN
        except Exception:
            return HealthStatus.UNKNOWN
    
    return check


def create_disk_health_check(path: str = "/", threshold_pct: float = 90) -> Callable[[], HealthStatus]:
    """Create health check for disk space."""
    def check():
        try:
            import shutil
            usage = shutil.disk_usage(path)
            used_pct = (usage.used / usage.total) * 100
            
            if used_pct > threshold_pct:
                return HealthStatus.UNHEALTHY
            elif used_pct > threshold_pct - 10:
                return HealthStatus.DEGRADED
            return HealthStatus.HEALTHY
            
        except Exception:
            return HealthStatus.UNKNOWN
    
    return check


def create_service_health_check(service: Any) -> Callable[[], HealthStatus]:
    """Create health check wrapper for a service."""
    def check():
        try:
            if hasattr(service, 'get_status'):
                status = service.get_status()
                if "error" in str(status).lower():
                    return HealthStatus.UNHEALTHY
                elif "degraded" in str(status).lower():
                    return HealthStatus.DEGRADED
                return HealthStatus.HEALTHY
            
            if hasattr(service, 'active'):
                return HealthStatus.HEALTHY if service.active else HealthStatus.UNHEALTHY
            
            if hasattr(service, 'is_healthy'):
                return HealthStatus.HEALTHY if service.is_healthy() else HealthStatus.UNHEALTHY
            
            return HealthStatus.UNKNOWN
            
        except Exception:
            return HealthStatus.UNKNOWN
    
    return check
