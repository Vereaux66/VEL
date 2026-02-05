#!/usr/bin/env python3
"""
ANVEL Service Registry
======================

Central registry for all ANVEL services.
Manages service lifecycle, dependencies, and health status.

Features:
- Dependency-ordered startup
- Health monitoring
- Graceful shutdown
- Service discovery
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("anvel.runtime.services")


class ServiceStatus(Enum):
    """Service lifecycle states."""
    REGISTERED = "registered"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class ServiceDefinition:
    """Service definition and state."""
    name: str
    factory: Callable[[], Any]
    dependencies: List[str] = field(default_factory=list)
    required: bool = True
    instance: Optional[Any] = None
    status: ServiceStatus = ServiceStatus.REGISTERED
    error: Optional[str] = None
    started_at: Optional[float] = None
    stopped_at: Optional[float] = None
    
    def __hash__(self):
        return hash(self.name)


class ServiceRegistry:
    """
    Central service registry.
    
    Manages all ANVEL services with:
    - Dependency resolution
    - Ordered startup/shutdown
    - Health checking
    - Service discovery
    """
    
    def __init__(self, event_bus: Optional[Any] = None):
        """
        Initialize service registry.
        
        Args:
            event_bus: Optional event bus for service events
        """
        self.event_bus = event_bus
        self._services: Dict[str, ServiceDefinition] = {}
        self._lock = threading.RLock()
    
    def register(
        self,
        name: str,
        factory: Callable[[], Any],
        dependencies: Optional[List[str]] = None,
        required: bool = True,
    ) -> None:
        """
        Register a service.
        
        Args:
            name: Unique service name
            factory: Callable that creates service instance
            dependencies: List of service names this depends on
            required: If True, system fails if service fails
        """
        with self._lock:
            if name in self._services:
                raise ValueError(f"Service already registered: {name}")
            
            self._services[name] = ServiceDefinition(
                name=name,
                factory=factory,
                dependencies=dependencies or [],
                required=required,
            )
            
            logger.debug(f"Registered service: {name}")
    
    def get(self, name: str) -> Optional[Any]:
        """Get service instance by name."""
        with self._lock:
            svc = self._services.get(name)
            return svc.instance if svc else None
    
    def get_status(self, name: str) -> Optional[ServiceStatus]:
        """Get service status."""
        with self._lock:
            svc = self._services.get(name)
            return svc.status if svc else None
    
    def _resolve_order(self) -> List[str]:
        """
        Resolve service startup order based on dependencies.
        
        Uses topological sort to ensure dependencies start first.
        """
        # Build dependency graph
        in_degree: Dict[str, int] = {name: 0 for name in self._services}
        dependents: Dict[str, List[str]] = {name: [] for name in self._services}
        
        for name, svc in self._services.items():
            for dep in svc.dependencies:
                if dep not in self._services:
                    if svc.required:
                        raise ValueError(
                            f"Service {name} depends on unregistered service: {dep}"
                        )
                    continue
                in_degree[name] += 1
                dependents[dep].append(name)
        
        # Topological sort
        order: List[str] = []
        ready = [name for name, degree in in_degree.items() if degree == 0]
        
        while ready:
            name = ready.pop(0)
            order.append(name)
            
            for dependent in dependents[name]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    ready.append(dependent)
        
        if len(order) != len(self._services):
            # Circular dependency detected
            remaining = set(self._services.keys()) - set(order)
            raise ValueError(f"Circular dependencies detected involving: {remaining}")
        
        return order
    
    def start_all(self) -> Dict[str, bool]:
        """
        Start all registered services in dependency order.
        
        Returns:
            Dict mapping service name to success status
        """
        results: Dict[str, bool] = {}
        
        try:
            order = self._resolve_order()
        except ValueError as e:
            logger.error(f"Dependency resolution failed: {e}")
            return results
        
        logger.info(f"Starting services in order: {order}")
        
        for name in order:
            success = self._start_service(name)
            results[name] = success
            
            if not success:
                svc = self._services[name]
                if svc.required:
                    logger.error(f"Required service failed to start: {name}")
                    # Continue starting non-dependent services
        
        return results
    
    def _start_service(self, name: str) -> bool:
        """Start a single service."""
        with self._lock:
            svc = self._services.get(name)
            if not svc:
                return False
            
            # Check dependencies are running
            for dep_name in svc.dependencies:
                dep = self._services.get(dep_name)
                if not dep or dep.status not in (ServiceStatus.RUNNING, ServiceStatus.DEGRADED):
                    if svc.required:
                        logger.error(f"Cannot start {name}: dependency {dep_name} not running")
                        svc.status = ServiceStatus.FAILED
                        svc.error = f"Dependency {dep_name} not available"
                        return False
            
            svc.status = ServiceStatus.STARTING
        
        try:
            logger.info(f"  Starting: {name}")
            
            # Create instance
            instance = svc.factory()
            
            # Start if it has a startup method
            if hasattr(instance, 'startup'):
                instance.startup()
            elif hasattr(instance, 'start'):
                instance.start()
            
            # Register to event bus if available
            if self.event_bus and hasattr(self.event_bus, 'subscribe'):
                # Service can subscribe to events
                pass
            
            with self._lock:
                svc.instance = instance
                svc.status = ServiceStatus.RUNNING
                svc.started_at = time.time()
            
            # Publish event
            if self.event_bus and hasattr(self.event_bus, 'publish'):
                self.event_bus.publish("service.started", {
                    "service": name,
                    "timestamp": time.time(),
                })
            
            logger.info(f"  Started: {name}")
            return True
            
        except Exception as e:
            logger.error(f"  Failed to start {name}: {e}")
            with self._lock:
                svc.status = ServiceStatus.FAILED
                svc.error = str(e)
            return False
    
    def stop_all(self) -> Dict[str, bool]:
        """
        Stop all services in reverse dependency order.
        
        Returns:
            Dict mapping service name to success status
        """
        results: Dict[str, bool] = {}
        
        try:
            order = list(reversed(self._resolve_order()))
        except ValueError:
            # Fallback to arbitrary order
            order = list(self._services.keys())
        
        logger.info(f"Stopping services in order: {order}")
        
        for name in order:
            success = self._stop_service(name)
            results[name] = success
        
        return results
    
    def _stop_service(self, name: str) -> bool:
        """Stop a single service."""
        with self._lock:
            svc = self._services.get(name)
            if not svc or not svc.instance:
                return True
            
            if svc.status in (ServiceStatus.STOPPED, ServiceStatus.REGISTERED):
                return True
            
            svc.status = ServiceStatus.STOPPING
        
        try:
            logger.info(f"  Stopping: {name}")
            
            instance = svc.instance
            
            # Stop service
            if hasattr(instance, 'shutdown'):
                instance.shutdown()
            elif hasattr(instance, 'stop'):
                instance.stop()
            elif hasattr(instance, 'close'):
                instance.close()
            
            with self._lock:
                svc.status = ServiceStatus.STOPPED
                svc.stopped_at = time.time()
            
            # Publish event
            if self.event_bus and hasattr(self.event_bus, 'publish'):
                self.event_bus.publish("service.stopped", {
                    "service": name,
                    "timestamp": time.time(),
                })
            
            logger.info(f"  Stopped: {name}")
            return True
            
        except Exception as e:
            logger.error(f"  Error stopping {name}: {e}")
            with self._lock:
                svc.status = ServiceStatus.FAILED
                svc.error = str(e)
            return False
    
    def restart(self, name: str) -> bool:
        """Restart a service."""
        if not self._stop_service(name):
            return False
        return self._start_service(name)
    
    def check_health(self) -> Dict[str, Dict[str, Any]]:
        """
        Check health of all services.
        
        Returns:
            Dict mapping service name to health info
        """
        health: Dict[str, Dict[str, Any]] = {}
        
        with self._lock:
            for name, svc in self._services.items():
                status = svc.status.value
                
                # Check instance health if available
                if svc.instance and hasattr(svc.instance, 'get_status'):
                    try:
                        instance_status = svc.instance.get_status()
                        if isinstance(instance_status, str):
                            status = instance_status
                    except Exception:
                        status = "error"
                
                # Check if degraded
                if svc.instance and hasattr(svc.instance, 'active'):
                    if not svc.instance.active:
                        status = "inactive"
                
                health[name] = {
                    "status": status,
                    "required": svc.required,
                    "uptime": time.time() - svc.started_at if svc.started_at else 0,
                    "error": svc.error,
                }
        
        return health
    
    def get_all_running(self) -> Dict[str, Any]:
        """Get all running service instances."""
        with self._lock:
            return {
                name: svc.instance
                for name, svc in self._services.items()
                if svc.instance and svc.status == ServiceStatus.RUNNING
            }
    
    def list_services(self) -> List[Dict[str, Any]]:
        """List all registered services."""
        with self._lock:
            return [
                {
                    "name": svc.name,
                    "status": svc.status.value,
                    "required": svc.required,
                    "dependencies": svc.dependencies,
                }
                for svc in self._services.values()
            ]
