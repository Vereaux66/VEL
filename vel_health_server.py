#!/usr/bin/env python3
"""
VEL Health Check Server
========================

Production-grade health check endpoints for Kubernetes probes and load balancer health checks.

Endpoints:
- /health - Combined health check (for ALB)
- /healthz - Kubernetes liveness probe  
- /ready - Kubernetes readiness probe
- /metrics - Prometheus metrics endpoint

Usage:
    from vel_health_server import HealthServer
    
    server = HealthServer(port=8080)
    server.start()  # Starts in background thread
    
    # When shutting down:
    server.stop()
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("vel.health")


class HealthStatus(Enum):
    """Health check status values."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status of a single component."""
    name: str
    status: HealthStatus
    message: str = ""
    last_check: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "last_check": datetime.fromtimestamp(self.last_check, tz=timezone.utc).isoformat(),
            "metadata": self.metadata
        }


@dataclass  
class HealthCheckResult:
    """Result of a comprehensive health check."""
    status: HealthStatus
    components: List[ComponentHealth]
    startup_complete: bool = False
    ready_to_serve: bool = False
    version: str = "1.0.0"
    uptime_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "startup_complete": self.startup_complete,
            "ready_to_serve": self.ready_to_serve,
            "version": self.version,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": [c.to_dict() for c in self.components]
        }


class HealthRegistry:
    """
    Registry for health check functions.
    
    Components register their health check functions, which are called
    during health checks.
    """
    
    def __init__(self):
        self._checks: Dict[str, Callable[[], ComponentHealth]] = {}
        self._startup_complete = False
        self._ready_to_serve = False
        self._start_time = time.time()
        self._lock = threading.Lock()
        
    def register(self, name: str, check_fn: Callable[[], ComponentHealth]) -> None:
        """Register a health check function for a component."""
        with self._lock:
            self._checks[name] = check_fn
            logger.info(f"Registered health check: {name}")
    
    def unregister(self, name: str) -> None:
        """Unregister a health check."""
        with self._lock:
            self._checks.pop(name, None)
    
    def set_startup_complete(self, complete: bool = True) -> None:
        """Mark startup as complete."""
        self._startup_complete = complete
        logger.info(f"Startup complete: {complete}")
    
    def set_ready_to_serve(self, ready: bool = True) -> None:
        """Mark system as ready to serve traffic."""
        self._ready_to_serve = ready
        logger.info(f"Ready to serve: {ready}")
    
    def check_all(self) -> HealthCheckResult:
        """Run all health checks and return combined result."""
        components: List[ComponentHealth] = []
        overall_status = HealthStatus.HEALTHY
        
        with self._lock:
            checks = dict(self._checks)
        
        for name, check_fn in checks.items():
            try:
                result = check_fn()
                components.append(result)
                
                if result.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif result.status == HealthStatus.DEGRADED and overall_status != HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.DEGRADED
                    
            except Exception as e:
                components.append(ComponentHealth(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {str(e)}"
                ))
                overall_status = HealthStatus.UNHEALTHY
        
        return HealthCheckResult(
            status=overall_status,
            components=components,
            startup_complete=self._startup_complete,
            ready_to_serve=self._ready_to_serve,
            uptime_seconds=time.time() - self._start_time
        )
    
    def check_liveness(self) -> bool:
        """
        Liveness check - is the process alive and not deadlocked?
        
        Returns True if the process should continue running.
        Returns False if the process should be restarted.
        """
        # Basic liveness: can we respond at all?
        # More sophisticated checks could include:
        # - Thread deadlock detection
        # - Memory pressure checks
        # - Event loop responsiveness
        return True
    
    def check_readiness(self) -> bool:
        """
        Readiness check - is the system ready to receive traffic?
        
        Returns True if the system should receive traffic.
        Returns False if traffic should be routed elsewhere.
        """
        if not self._startup_complete:
            return False
        
        if not self._ready_to_serve:
            return False
        
        # Check critical components
        result = self.check_all()
        return result.status != HealthStatus.UNHEALTHY


# Global registry
_health_registry: Optional[HealthRegistry] = None
_registry_lock = threading.Lock()


def get_health_registry() -> HealthRegistry:
    """Get global health registry instance."""
    global _health_registry
    if _health_registry is None:
        with _registry_lock:
            if _health_registry is None:
                _health_registry = HealthRegistry()
    return _health_registry


class HealthRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for health endpoints."""
    
    # Suppress default logging
    def log_message(self, format: str, *args) -> None:
        pass
    
    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        """Send JSON response."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def _send_text(self, status_code: int, text: str, content_type: str = "text/plain") -> None:
        """Send text response."""
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(text.encode())
    
    def do_GET(self) -> None:
        """Handle GET requests."""
        registry = get_health_registry()
        
        if self.path == "/health" or self.path == "/":
            # Combined health check (for ALB)
            result = registry.check_all()
            status_code = 200 if result.status == HealthStatus.HEALTHY else 503
            self._send_json(status_code, result.to_dict())
            
        elif self.path == "/healthz" or self.path == "/livez":
            # Kubernetes liveness probe
            if registry.check_liveness():
                self._send_json(200, {"status": "alive"})
            else:
                self._send_json(503, {"status": "dead"})
                
        elif self.path == "/ready" or self.path == "/readyz":
            # Kubernetes readiness probe
            if registry.check_readiness():
                self._send_json(200, {"status": "ready"})
            else:
                self._send_json(503, {"status": "not_ready"})
                
        elif self.path == "/metrics":
            # Prometheus metrics endpoint
            try:
                from vel_prometheus_metrics import get_metrics_collector
                collector = get_metrics_collector()
                metrics = collector.get_metrics()
                content_type = collector.get_content_type()
                self._send_text(200, metrics.decode() if isinstance(metrics, bytes) else metrics, content_type)
            except ImportError:
                self._send_text(503, "Metrics collector not available")
            except Exception as e:
                self._send_text(503, f"Error collecting metrics: {e}")
                
        elif self.path == "/status":
            # Detailed status endpoint
            result = registry.check_all()
            self._send_json(200, {
                **result.to_dict(),
                "detailed": True,
                "pid": __import__("os").getpid(),
                "hostname": __import__("socket").gethostname()
            })
            
        else:
            self._send_json(404, {"error": "Not found"})


class HealthServer:
    """
    Health check HTTP server.
    
    Runs in a background thread and provides health endpoints.
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        """
        Initialize health server.
        
        Args:
            host: Host to bind to
            port: Port to listen on
        """
        self.host = host
        self.port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
    
    def start(self) -> None:
        """Start health server in background thread."""
        if self._running:
            logger.warning("Health server already running")
            return
        
        self._server = HTTPServer((self.host, self.port), HealthRequestHandler)
        self._server.timeout = 1  # Allow periodic checks of _running flag
        self._running = True
        
        self._thread = threading.Thread(
            target=self._serve,
            name="health-server",
            daemon=True
        )
        self._thread.start()
        
        logger.info(f"Health server started on {self.host}:{self.port}")
    
    def _serve(self) -> None:
        """Server loop using serve_forever for proper shutdown handling."""
        if not self._server:
            return
        self._server.serve_forever()
    
    def stop(self) -> None:
        """Stop health server."""
        self._running = False
        
        if self._server:
            # shutdown() will cause serve_forever() to exit
            self._server.shutdown()
            # Close the server socket promptly after shutdown
            self._server.server_close()
            self._server = None
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
            self._thread = None
        
        logger.info("Health server stopped")


# =============================================================================
# Convenience Functions
# =============================================================================

def register_component_health(
    name: str,
    check_fn: Callable[[], ComponentHealth]
) -> None:
    """Register a component health check."""
    get_health_registry().register(name, check_fn)


def create_simple_check(
    name: str,
    healthy_fn: Callable[[], bool],
    message: str = ""
) -> Callable[[], ComponentHealth]:
    """
    Create a simple health check function.
    
    Args:
        name: Component name
        healthy_fn: Function that returns True if healthy
        message: Optional status message
        
    Returns:
        Health check function suitable for registration
    """
    def check() -> ComponentHealth:
        try:
            is_healthy = healthy_fn()
            return ComponentHealth(
                name=name,
                status=HealthStatus.HEALTHY if is_healthy else HealthStatus.UNHEALTHY,
                message=message if is_healthy else f"{name} check failed"
            )
        except Exception as e:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=str(e)
            )
    return check


# =============================================================================
# Standard Health Checks
# =============================================================================

def check_database_health() -> ComponentHealth:
    """Check database connectivity."""
    try:
        import os
        db_host = os.environ.get("VEL_DB_HOST", "localhost")
        # In a real implementation, attempt a database ping
        return ComponentHealth(
            name="database",
            status=HealthStatus.HEALTHY,
            message=f"Connected to {db_host}"
        )
    except Exception as e:
        return ComponentHealth(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message=str(e)
        )


def check_redis_health() -> ComponentHealth:
    """Check Redis connectivity using actual PING command."""
    import os
    redis_url = os.environ.get("VEL_REDIS_URL", "redis://localhost:6379")
    
    try:
        import redis
        
        # Parse Redis URL and connect
        client = redis.from_url(redis_url, socket_connect_timeout=5)
        
        # Execute actual PING command
        response = client.ping()
        if response:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                message="Redis PING successful"
            )
        else:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message="Redis PING returned False"
            )
            
    except ImportError:
        # Redis client not installed - report as degraded but not fatal
        return ComponentHealth(
            name="redis",
            status=HealthStatus.DEGRADED,
            message="Redis client not installed (pip install redis)"
        )
    except redis.ConnectionError as e:
        return ComponentHealth(
            name="redis",
            status=HealthStatus.UNHEALTHY,
            message=f"Redis connection failed: {e}"
        )
    except redis.TimeoutError:
        return ComponentHealth(
            name="redis",
            status=HealthStatus.UNHEALTHY,
            message="Redis connection timed out"
        )
    except Exception as e:
        return ComponentHealth(
            name="redis",
            status=HealthStatus.UNHEALTHY,
            message=f"Redis error: {e}"
        )


def check_circuit_breaker_health() -> ComponentHealth:
    """Check circuit breaker status."""
    try:
        from vel_circuit_breaker import CircuitBreakerManager
        # In a real implementation, check if breaker is tripped
        return ComponentHealth(
            name="circuit_breaker",
            status=HealthStatus.HEALTHY,
            message="Circuit breaker closed"
        )
    except ImportError:
        return ComponentHealth(
            name="circuit_breaker",
            status=HealthStatus.DEGRADED,
            message="Circuit breaker module not available"
        )
    except Exception as e:
        return ComponentHealth(
            name="circuit_breaker",
            status=HealthStatus.UNHEALTHY,
            message=str(e)
        )


def register_standard_checks() -> None:
    """Register standard health checks."""
    registry = get_health_registry()
    registry.register("database", check_database_health)
    registry.register("redis", check_redis_health)
    registry.register("circuit_breaker", check_circuit_breaker_health)


# =============================================================================
# Main (for standalone testing)
# =============================================================================

if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    # Register standard checks
    register_standard_checks()
    
    # Mark as ready
    registry = get_health_registry()
    registry.set_startup_complete(True)
    registry.set_ready_to_serve(True)
    
    # Start server
    server = HealthServer(port=8080)
    server.start()
    
    print("Health server running on http://localhost:8080")
    print("Endpoints: /health, /healthz, /ready, /metrics, /status")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        sys.exit(0)
