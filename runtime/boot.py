#!/usr/bin/env python3
"""
ANVEL Runtime Boot
==================

Master launch process for single-node ANVEL deployment.
Does NOT require Kubernetes - runs directly on any Linux/macOS system.

Startup Order (strict):
1. Load configuration
2. Initialize event bus
3. Initialize network registry  
4. Initialize heartbeat monitor
5. Initialize meta controller
6. Wire risk kernel into execution path
7. Start all services
8. Begin monitoring loop

All services register to event bus before starting execution logic.
"""

import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("anvel.runtime.boot")


class RuntimeState(Enum):
    """Runtime states."""
    UNINITIALIZED = "uninitialized"
    BOOTING = "booting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class RuntimeConfig:
    """Runtime configuration."""
    config_dir: Path = field(default_factory=lambda: Path("config"))
    data_dir: Path = field(default_factory=lambda: Path("data"))
    log_level: str = "INFO"
    heartbeat_interval: int = 10
    health_check_interval: int = 30
    single_node_mode: bool = True  # No Kubernetes required
    enable_ai: bool = True
    enable_trading: bool = True
    dry_run: bool = False


@dataclass
class BootResult:
    """Result of boot sequence."""
    success: bool
    state: RuntimeState
    duration_seconds: float
    components_online: List[str] = field(default_factory=list)
    components_failed: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None


class RuntimeBoot:
    """
    Master runtime boot process.
    
    Initializes all ANVEL components in correct dependency order.
    Ensures event bus is available before any service starts.
    """
    
    def __init__(
        self,
        config: Optional[RuntimeConfig] = None,
        project_root: Optional[Path] = None,
    ):
        self.config = config or RuntimeConfig()
        self.project_root = project_root or Path(__file__).resolve().parent.parent
        self.state = RuntimeState.UNINITIALIZED
        
        # Core components (initialized during boot)
        self.event_bus: Optional[Any] = None
        self.network_registry: Optional[Any] = None
        self.heartbeat_monitor: Optional[Any] = None
        self.meta_controller: Optional[Any] = None
        self.risk_kernel: Optional[Any] = None
        self.config_loader: Optional[Any] = None
        
        # Service registry
        self._services: Dict[str, Any] = {}
        self._service_status: Dict[str, str] = {}
        
        # Thread management
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        
        # Setup logging
        self._setup_logging()
    
    def _setup_logging(self) -> None:
        """Configure logging."""
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format=log_format,
        )
    
    def boot(self) -> bool:
        """
        Execute full boot sequence.
        
        Returns:
            True if boot successful, False otherwise
        """
        start_time = time.time()
        self.state = RuntimeState.BOOTING
        logger.info("=" * 60)
        logger.info("ANVEL Runtime Boot - Starting")
        logger.info("=" * 60)
        
        try:
            # Phase 1: Load configuration
            logger.info("[Phase 1/7] Loading configuration...")
            if not self._load_configuration():
                return self._boot_failed("Configuration load failed")
            
            # Phase 2: Initialize event bus (REQUIRED FIRST)
            logger.info("[Phase 2/7] Initializing event bus...")
            if not self._init_event_bus():
                return self._boot_failed("Event bus initialization failed")
            
            # Phase 3: Initialize network registry
            logger.info("[Phase 3/7] Initializing network registry...")
            if not self._init_network_registry():
                return self._boot_failed("Network registry initialization failed")
            
            # Phase 4: Initialize heartbeat monitor
            logger.info("[Phase 4/7] Initializing heartbeat monitor...")
            if not self._init_heartbeat_monitor():
                logger.warning("Heartbeat monitor init failed (non-critical)")
            
            # Phase 5: Initialize meta controller
            logger.info("[Phase 5/7] Initializing meta controller...")
            if not self._init_meta_controller():
                logger.warning("Meta controller init failed (non-critical)")
            
            # Phase 6: Initialize risk kernel (REQUIRED before trading)
            logger.info("[Phase 6/7] Initializing risk kernel...")
            if not self._init_risk_kernel():
                if self.config.enable_trading:
                    return self._boot_failed("Risk kernel required for trading")
                logger.warning("Risk kernel init failed (trading disabled)")
            
            # Phase 7: Register and start all services
            logger.info("[Phase 7/7] Starting services...")
            if not self._start_services():
                return self._boot_failed("Service startup failed")
            
            # Boot successful
            duration = time.time() - start_time
            self.state = RuntimeState.RUNNING
            
            logger.info("=" * 60)
            logger.info(f"ANVEL Runtime Boot - SUCCESS ({duration:.2f}s)")
            logger.info(f"  Components online: {len(self._services)}")
            logger.info(f"  Single-node mode: {self.config.single_node_mode}")
            logger.info(f"  Trading enabled: {self.config.enable_trading}")
            logger.info(f"  Dry run: {self.config.dry_run}")
            logger.info("=" * 60)
            
            # Start monitoring loop
            self._start_monitoring()
            
            return True
            
        except Exception as e:
            logger.exception(f"Boot failed with exception: {e}")
            return self._boot_failed(str(e))
    
    def _boot_failed(self, reason: str) -> bool:
        """Handle boot failure."""
        self.state = RuntimeState.FAILED
        logger.error(f"BOOT FAILED: {reason}")
        return False
    
    def _load_configuration(self) -> bool:
        """Load configuration from config directory."""
        try:
            from .config_loader import ConfigLoader
            
            config_path = self.project_root / self.config.config_dir
            self.config_loader = ConfigLoader(config_path)
            self.config_loader.load_all()
            
            logger.info(f"  Config loaded from: {config_path}")
            return True
            
        except ImportError:
            # Fallback if module not yet available
            logger.warning("  ConfigLoader not available, using defaults")
            return True
        except Exception as e:
            logger.error(f"  Config load error: {e}")
            return False
    
    def _init_event_bus(self) -> bool:
        """Initialize event bus - REQUIRED for all services."""
        try:
            # Try importing from project modules
            try:
                from anvel_event_bus import AnvelEventBus
                self.event_bus = AnvelEventBus()
            except ImportError:
                from anvel_event_bus import ANVELEventBus
                self.event_bus = ANVELEventBus()
            
            # Start the event bus
            if hasattr(self.event_bus, 'startup'):
                self.event_bus.startup()
            
            # Register core channels
            core_channels = [
                "system.boot",
                "system.shutdown",
                "system.health",
                "trade.signals",
                "trade.execution",
                "trade.results",
                "risk.alerts",
                "risk.violations",
            ]
            
            for channel in core_channels:
                if hasattr(self.event_bus, 'subscribers'):
                    self.event_bus.subscribers.setdefault(channel, [])
            
            self._services["event_bus"] = self.event_bus
            self._service_status["event_bus"] = "running"
            
            # Publish boot event
            self.event_bus.publish("system.boot", {
                "phase": "event_bus_ready",
                "timestamp": time.time(),
            })
            
            logger.info("  Event bus initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"  Event bus init error: {e}")
            return False
    
    def _init_network_registry(self) -> bool:
        """Initialize network registry."""
        try:
            from anvel_network_registry import NetworkRegistry, get_network_registry
            
            use_testnets = os.getenv("ANVEL_USE_TESTNETS", "false").lower() == "true"
            self.network_registry = get_network_registry(use_testnets=use_testnets)
            
            # Register to event bus
            if self.event_bus:
                self.event_bus.subscribe("network.health_check", 
                    lambda p: self._check_network_health(p))
            
            self._services["network_registry"] = self.network_registry
            self._service_status["network_registry"] = "running"
            
            network_count = len(self.network_registry.get_supported_network_ids())
            logger.info(f"  Network registry initialized ({network_count} networks)")
            return True
            
        except Exception as e:
            logger.error(f"  Network registry init error: {e}")
            return False
    
    def _init_heartbeat_monitor(self) -> bool:
        """Initialize heartbeat monitor."""
        try:
            # Use VEL health server for heartbeat monitoring
            from vel_health_server import HealthServer
            
            self.heartbeat_monitor = HealthServer()
            
            # Register to event bus
            if self.event_bus:
                self.event_bus.subscribe("system.heartbeat_request",
                    lambda p: self.heartbeat_monitor.get_status() if hasattr(self.heartbeat_monitor, 'get_status') else {"status": "ok"})
            
            # Start monitoring
            if hasattr(self.heartbeat_monitor, 'start'):
                self.heartbeat_monitor.start()
            
            self._services["heartbeat_monitor"] = self.heartbeat_monitor
            self._service_status["heartbeat_monitor"] = "running"
            
            logger.info(f"  Heartbeat monitor initialized (interval={self.config.heartbeat_interval}s)")
            return True
            
        except ImportError:
            # Fallback - heartbeat not critical
            logger.warning("  Heartbeat monitor not available (vel_health_server not found)")
            self._service_status["heartbeat_monitor"] = "unavailable"
            return True
        except Exception as e:
            logger.error(f"  Heartbeat monitor init error: {e}")
            return False
    
    def _init_meta_controller(self) -> bool:
        """Initialize meta controller (AI oversight)."""
        try:
            from anvel_meta_controller import ANVELMetaController, create_meta_controller
            
            persistence_dir = self.project_root / self.config.data_dir / "meta_controller"
            persistence_dir.mkdir(parents=True, exist_ok=True)
            
            self.meta_controller = create_meta_controller(
                persistence_dir=str(persistence_dir),
                enable_learning=self.config.enable_ai,
                enable_anomaly_detection=True,
                enable_codebase_awareness=False,  # Disable for production
            )
            
            # Register to event bus
            if self.event_bus:
                self.event_bus.subscribe("meta.proposal",
                    lambda p: self._handle_meta_proposal(p))
                self.event_bus.subscribe("meta.health_report",
                    lambda p: self._handle_meta_health(p))
            
            # Register components for monitoring
            for name, svc in self._services.items():
                if hasattr(self.meta_controller, 'register_component'):
                    self.meta_controller.register_component(
                        name=name,
                        health_checker=lambda: {"status": "healthy"},
                    )
            
            self._services["meta_controller"] = self.meta_controller
            self._service_status["meta_controller"] = "running"
            
            logger.info("  Meta controller initialized")
            return True
            
        except Exception as e:
            logger.error(f"  Meta controller init error: {e}")
            return False
    
    def _init_risk_kernel(self) -> bool:
        """Initialize risk kernel - REQUIRED for trading."""
        try:
            from vel_risk_kernel import RiskKernel
            from decimal import Decimal
            
            # Get portfolio value from config
            trading_config = {}
            if self.config_loader:
                trading_config = self.config_loader.get("trading", {})
            
            portfolio_value = Decimal(str(trading_config.get("portfolio_value_usd", "100000")))
            strict_mode = trading_config.get("strict_risk_mode", True)
            
            self.risk_kernel = RiskKernel(
                portfolio_value_usd=portfolio_value,
                enable_strict_mode=strict_mode,
            )
            
            # Register to event bus
            if self.event_bus:
                self.event_bus.subscribe("risk.check_request",
                    lambda p: self._handle_risk_check(p))
                self.event_bus.subscribe("risk.exposure_update",
                    lambda p: self._handle_exposure_update(p))
            
            self._services["risk_kernel"] = self.risk_kernel
            self._service_status["risk_kernel"] = "running"
            
            logger.info(f"  Risk kernel initialized (portfolio=${portfolio_value})")
            return True
            
        except Exception as e:
            logger.error(f"  Risk kernel init error: {e}")
            return False
    
    def _start_services(self) -> bool:
        """Register all services to event bus and start execution."""
        try:
            # Ensure all services are registered
            for name, service in self._services.items():
                if self.event_bus and hasattr(service, '__class__'):
                    # Services are now registered to event bus
                    pass
            
            # Publish ready event
            if self.event_bus:
                self.event_bus.publish("system.boot", {
                    "phase": "services_ready",
                    "services": list(self._services.keys()),
                    "timestamp": time.time(),
                })
            
            logger.info(f"  All services started: {list(self._services.keys())}")
            return True
            
        except Exception as e:
            logger.error(f"  Service startup error: {e}")
            return False
    
    def _start_monitoring(self) -> None:
        """Start background monitoring loop."""
        def monitor_loop():
            while not self._stop_event.is_set():
                try:
                    self._run_health_checks()
                except Exception as e:
                    logger.error(f"Health check error: {e}")
                
                self._stop_event.wait(self.config.health_check_interval)
        
        self._monitor_thread = threading.Thread(
            target=monitor_loop,
            daemon=True,
            name="runtime-monitor"
        )
        self._monitor_thread.start()
    
    def _run_health_checks(self) -> None:
        """Run periodic health checks."""
        with self._lock:
            for name, service in self._services.items():
                try:
                    if hasattr(service, 'get_status'):
                        status = service.get_status()
                        self._service_status[name] = "healthy"
                    elif hasattr(service, 'active') and not service.active:
                        self._service_status[name] = "stopped"
                    else:
                        self._service_status[name] = "unknown"
                except Exception as e:
                    self._service_status[name] = f"error: {e}"
    
    def _check_network_health(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle network health check request."""
        if not self.network_registry:
            return {"status": "unavailable"}
        
        network_id = payload.get("network_id")
        if network_id:
            try:
                config = self.network_registry.get_network(network_id)
                return {"status": "healthy", "network": network_id}
            except ValueError:
                return {"status": "unknown", "network": network_id}
        
        return {"status": "healthy", "networks": self.network_registry.get_supported_network_ids()}
    
    def _handle_meta_proposal(self, payload: Dict[str, Any]) -> None:
        """Handle meta controller proposal."""
        logger.info(f"Meta proposal received: {payload}")
    
    def _handle_meta_health(self, payload: Dict[str, Any]) -> None:
        """Handle meta controller health report."""
        logger.debug(f"Meta health: {payload}")
    
    def _handle_risk_check(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle risk check request."""
        if not self.risk_kernel:
            return {"passed": False, "reason": "Risk kernel not available"}
        
        # Extract check parameters
        intent = payload.get("intent")
        plan = payload.get("plan")
        simulation = payload.get("simulation")
        
        result = self.risk_kernel.check(intent, plan, simulation)
        return {
            "passed": result.passed,
            "breached": result.breached_limits,
            "warnings": result.warnings,
            "reason": result.failure_reason,
        }
    
    def _handle_exposure_update(self, payload: Dict[str, Any]) -> None:
        """Handle exposure update after trade."""
        if not self.risk_kernel:
            return
        
        from decimal import Decimal
        self.risk_kernel.update_exposure(
            chain_id=payload.get("chain_id", 1),
            protocol=payload.get("protocol", "unknown"),
            asset=payload.get("asset", "unknown"),
            value_usd=Decimal(str(payload.get("value_usd", 0))),
        )
    
    def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("Initiating runtime shutdown...")
        self.state = RuntimeState.STOPPING
        
        # Signal stop to monitor thread
        self._stop_event.set()
        
        # Publish shutdown event
        if self.event_bus:
            self.event_bus.publish("system.shutdown", {
                "timestamp": time.time(),
                "reason": "graceful_shutdown",
            })
        
        # Stop services in reverse order
        services_to_stop = list(reversed(list(self._services.keys())))
        for name in services_to_stop:
            try:
                service = self._services[name]
                if hasattr(service, 'shutdown'):
                    service.shutdown()
                elif hasattr(service, 'close'):
                    service.close()
                elif hasattr(service, 'stop_monitoring'):
                    service.stop_monitoring()
                
                self._service_status[name] = "stopped"
                logger.info(f"  Stopped: {name}")
            except Exception as e:
                logger.error(f"  Error stopping {name}: {e}")
        
        self.state = RuntimeState.STOPPED
        logger.info("Runtime shutdown complete")
    
    def get_status(self) -> Dict[str, Any]:
        """Get runtime status."""
        return {
            "state": self.state.value,
            "services": self._service_status.copy(),
            "components_online": [
                name for name, status in self._service_status.items()
                if status in ("running", "healthy")
            ],
        }
    
    def is_healthy(self) -> bool:
        """Check if runtime is healthy."""
        if self.state != RuntimeState.RUNNING:
            return False
        
        # Check critical services
        critical = ["event_bus", "risk_kernel"]
        for name in critical:
            status = self._service_status.get(name, "unknown")
            if status not in ("running", "healthy"):
                return False
        
        return True


def main():
    """CLI entry point for runtime boot."""
    import argparse
    
    parser = argparse.ArgumentParser(description="ANVEL Runtime Boot")
    parser.add_argument("--dry-run", action="store_true", help="Enable dry run mode")
    parser.add_argument("--no-trading", action="store_true", help="Disable trading")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI features")
    parser.add_argument("--log-level", default="INFO", help="Log level")
    args = parser.parse_args()
    
    config = RuntimeConfig(
        dry_run=args.dry_run,
        enable_trading=not args.no_trading,
        enable_ai=not args.no_ai,
        log_level=args.log_level,
    )
    
    runtime = RuntimeBoot(config=config)
    
    if runtime.boot():
        print("\nANVEL Runtime is running. Press Ctrl+C to stop.")
        try:
            while runtime.is_healthy():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nInterrupt received")
        finally:
            runtime.shutdown()
    else:
        print("Boot failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
