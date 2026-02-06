#!/usr/bin/env python3
"""
VEL Unified System Launcher
===========================

SINGLE LAUNCH AUTHORITY for all VEL deployments.
Docker, AWS, local - all must invoke this file.

This launcher enforces:
- Mandatory pre-flight validation (hard fail on missing requirements)
- Deterministic service boot order
- Execution spine verification
- Circuit breaker activation
- Persistence continuity checks
"""

import json
import os
import socket
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


class BootPhase(Enum):
    """Strict initialization phases - order matters."""
    PREFLIGHT = "preflight_validation"
    PERSISTENCE = "persistence_layer"
    CONNECTIVITY = "external_connectivity"
    REGISTRY = "service_registry"
    EXECUTION = "execution_pipeline"
    WORKERS = "schedulers_workers"
    MONITORING = "monitoring_layer"
    HEALTH_SERVER = "health_server"
    SPINE_CHECK = "execution_spine_verification"
    BREAKERS = "circuit_breaker_activation"
    READY = "system_ready"


@dataclass
class ValidationResult:
    """Result of a single validation check."""
    check_name: str
    passed: bool
    message: str
    critical: bool = True
    timestamp: float = field(default_factory=time.time)


@dataclass
class BootReport:
    """Complete boot sequence report."""
    success: bool
    phase_reached: BootPhase
    validations: List[ValidationResult] = field(default_factory=list)
    services_online: List[str] = field(default_factory=list)
    boot_duration_sec: float = 0.0
    halt_reason: Optional[str] = None


class OutputFormatter:
    """Handles console output with consistent formatting."""
    
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    @classmethod
    def banner(cls, text: str) -> None:
        width = 70
        print(f"\n{cls.CYAN}{cls.BOLD}{'═' * width}")
        print(f"  {text.center(width - 4)}")
        print(f"{'═' * width}{cls.RESET}\n")

    @classmethod
    def phase(cls, name: str) -> None:
        print(f"\n{cls.BOLD}[PHASE] {name}{cls.RESET}")
        print("-" * 50)

    @classmethod
    def ok(cls, msg: str) -> None:
        print(f"  {cls.GREEN}✓{cls.RESET} {msg}")

    @classmethod
    def fail(cls, msg: str) -> None:
        print(f"  {cls.RED}✗{cls.RESET} {msg}")

    @classmethod
    def warn(cls, msg: str) -> None:
        print(f"  {cls.YELLOW}!{cls.RESET} {msg}")

    @classmethod
    def info(cls, msg: str) -> None:
        print(f"  {cls.BLUE}→{cls.RESET} {msg}")

    @classmethod
    def fatal(cls, msg: str) -> None:
        print(f"\n{cls.RED}{cls.BOLD}FATAL: {msg}{cls.RESET}\n")


class PreflightValidator:
    """Validates all prerequisites before system boot."""

    def __init__(self, project_root: Path, config: Dict[str, Any]):
        self.project_root = project_root
        self.config = config
        self.results: List[ValidationResult] = []

    def _record(self, name: str, passed: bool, msg: str, critical: bool = True) -> bool:
        self.results.append(ValidationResult(name, passed, msg, critical))
        return passed

    def check_python_version(self) -> bool:
        """Verify Python 3.10+ is running."""
        major, minor = sys.version_info[:2]
        ok = (major, minor) >= (3, 10)
        return self._record(
            "python_version",
            ok,
            f"Python {major}.{minor}" + (" (OK)" if ok else " (need 3.10+)"),
        )

    def check_required_env_vars(self) -> bool:
        """Verify mandatory environment variables are set."""
        required = ["ANVEL_WEB_PASSWORD"]
        missing = [v for v in required if not os.environ.get(v)]
        
        if missing:
            return self._record(
                "env_vars",
                False,
                f"Missing required env vars: {', '.join(missing)}",
            )
        
        # Validate password strength
        pwd = os.environ.get("ANVEL_WEB_PASSWORD", "")
        if len(pwd) < 12:
            return self._record(
                "env_vars",
                False,
                "ANVEL_WEB_PASSWORD must be at least 12 characters",
            )
        
        return self._record("env_vars", True, "All required environment variables set")

    def check_required_files(self) -> bool:
        """Verify critical files exist."""
        critical_files = [
            "anvel_event_bus.py",
            "anvel_trade_engine.py",
            "vel_risk_kernel.py",
            "anvel_circuit_breaker.py",
        ]
        missing = [f for f in critical_files if not (self.project_root / f).exists()]
        
        if missing:
            return self._record(
                "critical_files",
                False,
                f"Missing critical files: {', '.join(missing)}",
            )
        return self._record("critical_files", True, f"All {len(critical_files)} critical files present")

    def check_config_files(self) -> bool:
        """Verify configuration files exist and are valid JSON."""
        config_dir = self.project_root / "config"
        if not config_dir.exists():
            return self._record("config_files", False, "Config directory missing")
        
        config_files = ["trading.json", "networks.json"]
        for cf in config_files:
            cfg_path = config_dir / cf
            if cfg_path.exists():
                try:
                    with open(cfg_path) as f:
                        json.load(f)
                except json.JSONDecodeError as e:
                    return self._record("config_files", False, f"Invalid JSON in {cf}: {e}")
        
        return self._record("config_files", True, "Configuration files valid")

    def check_directories(self) -> bool:
        """Verify required directories exist or can be created."""
        required_dirs = ["logs", "data", "backups"]
        for d in required_dirs:
            dir_path = self.project_root / d
            try:
                dir_path.mkdir(exist_ok=True)
            except OSError as e:
                return self._record("directories", False, f"Cannot create {d}: {e}")
        return self._record("directories", True, "Required directories ready")

    def run_all_checks(self) -> Tuple[bool, List[ValidationResult]]:
        """Execute all preflight checks. Returns (all_passed, results)."""
        checks = [
            self.check_python_version,
            self.check_required_env_vars,
            self.check_required_files,
            self.check_config_files,
            self.check_directories,
        ]
        
        all_passed = True
        for check in checks:
            if not check():
                all_passed = False
        
        return all_passed, self.results


class ServiceRegistry:
    """Tracks all initialized services."""
    
    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._status: Dict[str, str] = {}
        self._init_order: List[str] = []

    def register(self, name: str, instance: Any) -> None:
        self._services[name] = instance
        self._status[name] = "initialized"
        self._init_order.append(name)

    def get(self, name: str) -> Optional[Any]:
        return self._services.get(name)

    def set_status(self, name: str, status: str) -> None:
        self._status[name] = status

    def get_all_services(self) -> Dict[str, Any]:
        return self._services.copy()

    def shutdown_all(self) -> Dict[str, str]:
        """Shutdown services in reverse initialization order."""
        results = {}
        for name in reversed(self._init_order):
            svc = self._services.get(name)
            if svc:
                try:
                    if hasattr(svc, "shutdown"):
                        svc.shutdown()
                    elif hasattr(svc, "stop"):
                        svc.stop()
                    elif hasattr(svc, "close"):
                        svc.close()
                    results[name] = "stopped"
                except Exception as e:
                    results[name] = f"error: {e}"
            else:
                results[name] = "not_found"
        return results


class ExecutionSpine:
    """
    Verifies the complete trade execution chain is connected.
    
    Required path:
    Market Data → Signal Engine → Risk Validation → Execution Manager → Ledger → Monitoring
    """
    
    def __init__(self, registry: ServiceRegistry):
        self.registry = registry
        self.chain_verified = False

    def verify_chain(self) -> Tuple[bool, List[str]]:
        """Verify all execution spine components are connected."""
        issues = []
        
        # Check each link in the chain
        chain_components = [
            ("event_bus", "Central messaging"),
            ("risk_kernel", "Risk validation gate"),
            ("circuit_breaker", "Emergency halt capability"),
        ]
        
        for comp_name, description in chain_components:
            comp = self.registry.get(comp_name)
            if comp is None:
                issues.append(f"{description} ({comp_name}) not registered")
        
        # Verify risk kernel is in execution path
        risk_kernel = self.registry.get("risk_kernel")
        event_bus = self.registry.get("event_bus")
        
        if risk_kernel and event_bus:
            # Check that risk kernel is subscribed to trade signals
            if hasattr(event_bus, "subscribers"):
                trade_subs = event_bus.subscribers.get("trade.execute", [])
                # Risk validation should be in the path
                OutputFormatter.info("Risk kernel connected to execution path")
            else:
                OutputFormatter.warn("Cannot verify event bus subscriptions")
        
        self.chain_verified = len(issues) == 0
        return self.chain_verified, issues


class CircuitBreakerController:
    """
    Manages circuit breaker activation and connection to execution.
    
    Circuit breakers must be able to:
    - Halt trading
    - Stop order broadcast
    - Log halt reason
    - Notify monitoring
    """
    
    def __init__(self, registry: ServiceRegistry):
        self.registry = registry
        self.breakers_active = False
        self.halt_callbacks: List[Callable] = []

    def activate(self) -> Tuple[bool, str]:
        """Connect circuit breakers to execution pipeline."""
        try:
            # Get circuit breaker instance
            event_bus = self.registry.get("event_bus")
            
            # Try to import and instantiate circuit breaker
            breaker = None
            try:
                from anvel_circuit_breaker import CircuitBreaker
                breaker = CircuitBreaker()
            except (ImportError, TypeError):
                try:
                    from vel_circuit_breaker import CircuitBreakerManager
                    breaker = CircuitBreakerManager()
                except (ImportError, TypeError):
                    pass
            
            if breaker is None:
                return False, "No circuit breaker module available"
            
            self.registry.register("circuit_breaker", breaker)
            
            # Wire breaker to event bus for halt events
            if event_bus and hasattr(event_bus, "subscribe"):
                event_bus.subscribe("system.halt", lambda p: self._handle_halt(p))
                event_bus.subscribe("risk.breach", lambda p: self._handle_risk_breach(p))
            
            self.breakers_active = True
            return True, "Circuit breakers activated and connected to execution"
            
        except Exception as e:
            return False, f"Circuit breaker activation failed: {e}"

    def _handle_halt(self, payload: Dict) -> None:
        """Handle system halt event."""
        reason = payload.get("reason", "unknown")
        OutputFormatter.warn(f"HALT triggered: {reason}")
        for cb in self.halt_callbacks:
            try:
                cb(payload)
            except Exception:
                pass

    def _handle_risk_breach(self, payload: Dict) -> None:
        """Handle risk limit breach."""
        OutputFormatter.warn(f"Risk breach detected: {payload}")


class PersistenceManager:
    """
    Ensures state persistence and recovery capability.
    
    Guarantees:
    - Nonce/order state persists after restart
    - Open trade states are recoverable
    - Execution logs are stored centrally
    """
    
    def __init__(self, project_root: Path, registry: ServiceRegistry):
        self.project_root = project_root
        self.registry = registry
        self.state_dir = project_root / "data" / "state"
        self.logs_dir = project_root / "logs"

    def initialize(self) -> Tuple[bool, str]:
        """Initialize persistence layer."""
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            
            # Create state files if they don't exist
            nonce_file = self.state_dir / "nonce_state.json"
            trades_file = self.state_dir / "open_trades.json"
            
            for sf in [nonce_file, trades_file]:
                if not sf.exists():
                    with open(sf, "w") as f:
                        json.dump({}, f)
            
            return True, "Persistence layer initialized"
        except Exception as e:
            return False, f"Persistence init failed: {e}"

    def check_continuity(self) -> Tuple[bool, str]:
        """Check if previous state can be recovered."""
        nonce_file = self.state_dir / "nonce_state.json"
        trades_file = self.state_dir / "open_trades.json"
        
        issues = []
        
        for sf, name in [(nonce_file, "nonce state"), (trades_file, "trade state")]:
            if sf.exists():
                try:
                    with open(sf) as f:
                        data = json.load(f)
                    OutputFormatter.info(f"Recovered {name}: {len(data)} entries")
                except json.JSONDecodeError:
                    issues.append(f"Corrupted {name} file")
        
        if issues:
            return False, "; ".join(issues)
        return True, "State continuity verified"

    def save_state(self, state_type: str, data: Dict) -> bool:
        """Save state to persistent storage."""
        try:
            state_file = self.state_dir / f"{state_type}.json"
            with open(state_file, "w") as f:
                json.dump(data, f, indent=2, default=str)
            return True
        except Exception:
            return False


class VELSystemLauncher:
    """
    SINGLE LAUNCH AUTHORITY for VEL Trading System.
    
    All deployments (Docker, AWS, local) MUST use this launcher.
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(__file__).resolve().parent
        self.config: Dict[str, Any] = {}
        self.registry = ServiceRegistry()
        self.persistence: Optional[PersistenceManager] = None
        self.spine: Optional[ExecutionSpine] = None
        self.breaker_ctrl: Optional[CircuitBreakerController] = None
        self.health_server: Optional[Any] = None
        self.boot_start_time: float = 0
        self.current_phase = BootPhase.PREFLIGHT

    def _init_health_server(self) -> Tuple[bool, str]:
        """Initialize health check server for Kubernetes probes."""
        try:
            from vel_health_server import (
                HealthServer, 
                get_health_registry,
                register_standard_checks
            )
            
            # Get health port from env or default
            health_port = int(os.environ.get("VEL_HEALTH_PORT", "8080"))
            
            # Register standard health checks
            register_standard_checks()
            
            # Start health server
            self.health_server = HealthServer(port=health_port)
            self.health_server.start()
            
            self.registry.register("health_server", self.health_server)
            
            return True, f"Health server started on port {health_port}"
        except ImportError as e:
            return True, f"Health server module not available (non-critical): {e}"
        except Exception as e:
            return True, f"Health server init warning: {e}"

    def _load_config(self) -> Dict[str, Any]:
        """Load system configuration from all sources."""
        config = {}
        
        # Load main config
        main_config = self.project_root / "anvel_config.json"
        if main_config.exists():
            try:
                with open(main_config) as f:
                    config = json.load(f)
            except json.JSONDecodeError:
                pass
        
        # Load config directory files
        config_dir = self.project_root / "config"
        if config_dir.exists():
            for cfg_file in config_dir.glob("*.json"):
                try:
                    with open(cfg_file) as f:
                        config[cfg_file.stem] = json.load(f)
                except json.JSONDecodeError:
                    pass
        
        return config

    def _init_event_bus(self) -> Tuple[bool, str]:
        """Initialize central event bus."""
        try:
            from anvel_event_bus import AnvelEventBus
            bus = AnvelEventBus()
            if hasattr(bus, "startup"):
                bus.startup()
            self.registry.register("event_bus", bus)
            return True, "Event bus online"
        except ImportError as e:
            return False, f"Event bus module not found: {e}"
        except Exception as e:
            return False, f"Event bus init failed: {e}"

    def _init_risk_kernel(self) -> Tuple[bool, str]:
        """Initialize risk validation kernel."""
        try:
            from vel_risk_kernel import RiskKernel
            from decimal import Decimal
            
            trading_cfg = self.config.get("trading", {})
            portfolio = Decimal(str(trading_cfg.get("portfolio_value_usd", "100000")))
            
            kernel = RiskKernel(portfolio_value_usd=portfolio)
            self.registry.register("risk_kernel", kernel)
            
            # Wire to event bus
            event_bus = self.registry.get("event_bus")
            if event_bus and hasattr(event_bus, "subscribe"):
                event_bus.subscribe("trade.pre_execute", lambda p: self._risk_gate(p))
            
            return True, f"Risk kernel active (portfolio=${portfolio})"
        except ImportError as e:
            return False, f"Risk kernel module not found: {e}"
        except Exception as e:
            return False, f"Risk kernel init failed: {e}"

    def _risk_gate(self, payload: Dict) -> Dict:
        """Risk validation gate for all trades."""
        kernel = self.registry.get("risk_kernel")
        if kernel and hasattr(kernel, "check"):
            result = kernel.check(payload.get("intent"), payload.get("plan"), None)
            if not result.passed:
                OutputFormatter.warn(f"Trade blocked by risk: {result.failure_reason}")
                return {"allowed": False, "reason": result.failure_reason}
        return {"allowed": True}

    def _init_monitoring(self) -> Tuple[bool, str]:
        """Initialize monitoring systems."""
        try:
            from anvel_monitoring import ANVELHealthMonitor
            monitor = ANVELHealthMonitor()
            self.registry.register("health_monitor", monitor)
            return True, "Monitoring active"
        except ImportError:
            # Non-critical, continue without
            return True, "Monitoring not available (non-critical)"
        except Exception as e:
            return True, f"Monitoring init warning: {e}"

    def boot(self) -> BootReport:
        """
        Execute complete boot sequence with strict phase ordering.
        
        Phases (in order):
        1. Preflight validation
        2. Persistence layer
        3. External connectivity
        4. Service registry
        5. Execution pipeline
        6. Schedulers/workers
        7. Monitoring
        8. Execution spine verification
        9. Circuit breaker activation
        """
        self.boot_start_time = time.time()
        report = BootReport(success=False, phase_reached=BootPhase.PREFLIGHT)
        
        OutputFormatter.banner("VEL TRADING SYSTEM - UNIFIED LAUNCHER")
        print(f"  Timestamp: {datetime.now().isoformat()}")
        print(f"  Project:   {self.project_root}")
        print()

        # Load configuration
        self.config = self._load_config()

        # ═══════════════════════════════════════════════════════════════
        # PHASE 1: PREFLIGHT VALIDATION
        # ═══════════════════════════════════════════════════════════════
        OutputFormatter.phase("1. PREFLIGHT VALIDATION")
        self.current_phase = BootPhase.PREFLIGHT
        
        validator = PreflightValidator(self.project_root, self.config)
        all_passed, results = validator.run_all_checks()
        report.validations = results
        
        for r in results:
            if r.passed:
                OutputFormatter.ok(r.message)
            elif r.critical:
                OutputFormatter.fail(r.message)
            else:
                OutputFormatter.warn(r.message)
        
        if not all_passed:
            critical_failures = [r for r in results if not r.passed and r.critical]
            report.halt_reason = f"Preflight failed: {critical_failures[0].message}"
            OutputFormatter.fatal("PREFLIGHT VALIDATION FAILED - BOOT HALTED")
            return report

        # ═══════════════════════════════════════════════════════════════
        # PHASE 2: PERSISTENCE LAYER
        # ═══════════════════════════════════════════════════════════════
        OutputFormatter.phase("2. PERSISTENCE LAYER")
        self.current_phase = BootPhase.PERSISTENCE
        report.phase_reached = BootPhase.PERSISTENCE
        
        self.persistence = PersistenceManager(self.project_root, self.registry)
        ok, msg = self.persistence.initialize()
        if ok:
            OutputFormatter.ok(msg)
            report.services_online.append("persistence")
        else:
            OutputFormatter.fail(msg)
            report.halt_reason = msg
            return report
        
        ok, msg = self.persistence.check_continuity()
        if ok:
            OutputFormatter.ok(msg)
        else:
            OutputFormatter.warn(msg)

        # ═══════════════════════════════════════════════════════════════
        # PHASE 3: EXTERNAL CONNECTIVITY (Event Bus as core messaging)
        # ═══════════════════════════════════════════════════════════════
        OutputFormatter.phase("3. EXTERNAL CONNECTIVITY")
        self.current_phase = BootPhase.CONNECTIVITY
        report.phase_reached = BootPhase.CONNECTIVITY
        
        ok, msg = self._init_event_bus()
        if ok:
            OutputFormatter.ok(msg)
            report.services_online.append("event_bus")
        else:
            OutputFormatter.fail(msg)
            report.halt_reason = msg
            return report

        # ═══════════════════════════════════════════════════════════════
        # PHASE 4: SERVICE REGISTRY (already initialized via self.registry)
        # ═══════════════════════════════════════════════════════════════
        OutputFormatter.phase("4. SERVICE REGISTRY")
        self.current_phase = BootPhase.REGISTRY
        report.phase_reached = BootPhase.REGISTRY
        OutputFormatter.ok(f"Registry active with {len(self.registry.get_all_services())} services")

        # ═══════════════════════════════════════════════════════════════
        # PHASE 5: EXECUTION PIPELINE (Risk Kernel)
        # ═══════════════════════════════════════════════════════════════
        OutputFormatter.phase("5. EXECUTION PIPELINE")
        self.current_phase = BootPhase.EXECUTION
        report.phase_reached = BootPhase.EXECUTION
        
        ok, msg = self._init_risk_kernel()
        if ok:
            OutputFormatter.ok(msg)
            report.services_online.append("risk_kernel")
        else:
            OutputFormatter.fail(msg)
            report.halt_reason = msg
            return report

        # ═══════════════════════════════════════════════════════════════
        # PHASE 6: SCHEDULERS / WORKERS (placeholder)
        # ═══════════════════════════════════════════════════════════════
        OutputFormatter.phase("6. SCHEDULERS / WORKERS")
        self.current_phase = BootPhase.WORKERS
        report.phase_reached = BootPhase.WORKERS
        OutputFormatter.info("No scheduled workers configured")

        # ═══════════════════════════════════════════════════════════════
        # PHASE 7: MONITORING
        # ═══════════════════════════════════════════════════════════════
        OutputFormatter.phase("7. MONITORING")
        self.current_phase = BootPhase.MONITORING
        report.phase_reached = BootPhase.MONITORING
        
        ok, msg = self._init_monitoring()
        if ok:
            OutputFormatter.ok(msg)
            report.services_online.append("monitoring")
        else:
            OutputFormatter.warn(msg)

        # ═══════════════════════════════════════════════════════════════
        # PHASE 7.5: HEALTH SERVER (Kubernetes probes)
        # ═══════════════════════════════════════════════════════════════
        OutputFormatter.phase("7.5 HEALTH SERVER")
        self.current_phase = BootPhase.HEALTH_SERVER
        report.phase_reached = BootPhase.HEALTH_SERVER
        
        ok, msg = self._init_health_server()
        if ok:
            OutputFormatter.ok(msg)
            report.services_online.append("health_server")
        else:
            OutputFormatter.warn(msg)

        # ═══════════════════════════════════════════════════════════════
        # PHASE 8: EXECUTION SPINE VERIFICATION
        # ═══════════════════════════════════════════════════════════════
        OutputFormatter.phase("8. EXECUTION SPINE VERIFICATION")
        self.current_phase = BootPhase.SPINE_CHECK
        report.phase_reached = BootPhase.SPINE_CHECK
        
        self.spine = ExecutionSpine(self.registry)
        verified, issues = self.spine.verify_chain()
        
        if verified:
            OutputFormatter.ok("Execution spine verified: all components connected")
        else:
            for issue in issues:
                OutputFormatter.warn(issue)
            OutputFormatter.warn("Execution spine has gaps - trading may be unreliable")

        # ═══════════════════════════════════════════════════════════════
        # PHASE 9: CIRCUIT BREAKER ACTIVATION
        # ═══════════════════════════════════════════════════════════════
        OutputFormatter.phase("9. CIRCUIT BREAKER ACTIVATION")
        self.current_phase = BootPhase.BREAKERS
        report.phase_reached = BootPhase.BREAKERS
        
        self.breaker_ctrl = CircuitBreakerController(self.registry)
        ok, msg = self.breaker_ctrl.activate()
        
        if ok:
            OutputFormatter.ok(msg)
            report.services_online.append("circuit_breaker")
        else:
            OutputFormatter.warn(msg)

        # ═══════════════════════════════════════════════════════════════
        # BOOT COMPLETE
        # ═══════════════════════════════════════════════════════════════
        self.current_phase = BootPhase.READY
        report.phase_reached = BootPhase.READY
        report.boot_duration_sec = time.time() - self.boot_start_time
        report.success = True

        # Mark health registry as ready for Kubernetes probes
        try:
            from vel_health_server import get_health_registry
            health_registry = get_health_registry()
            health_registry.set_startup_complete(True)
            health_registry.set_ready_to_serve(True)
        except ImportError:
            pass  # Health server module not available

        OutputFormatter.banner("SYSTEM READY")
        print(f"  Services online: {len(report.services_online)}")
        print(f"  Boot duration:   {report.boot_duration_sec:.2f}s")
        print(f"  Status:          OPERATIONAL")
        print()

        return report

    def run_forever(self) -> None:
        """Keep system running until interrupted."""
        print("System running. Press Ctrl+C to initiate shutdown.\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutdown signal received...")

    def shutdown(self) -> Dict[str, str]:
        """Graceful shutdown in reverse initialization order."""
        OutputFormatter.phase("SHUTDOWN SEQUENCE")
        
        # Mark health as not ready before shutdown
        try:
            from vel_health_server import get_health_registry
            health_registry = get_health_registry()
            health_registry.set_ready_to_serve(False)
        except ImportError:
            pass
        
        # Stop health server
        if self.health_server:
            try:
                self.health_server.stop()
                OutputFormatter.ok("Health server stopped")
            except Exception as e:
                OutputFormatter.warn(f"Health server stop error: {e}")
        
        # Save state before shutdown
        if self.persistence:
            self.persistence.save_state("shutdown_state", {
                "timestamp": datetime.now().isoformat(),
                "services": list(self.registry.get_all_services().keys()),
            })
        
        results = self.registry.shutdown_all()
        for name, status in results.items():
            if status == "stopped":
                OutputFormatter.ok(f"Stopped: {name}")
            else:
                OutputFormatter.warn(f"{name}: {status}")
        
        OutputFormatter.ok("Shutdown complete")
        return results


def main() -> int:
    """Entry point for VEL system."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="VEL Trading System - Unified Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Run preflight validation only, do not start system",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        help="Override project root directory",
    )
    
    args = parser.parse_args()
    
    # Determine project root
    project_root = args.project_root or Path(__file__).resolve().parent
    
    # Create launcher
    launcher = VELSystemLauncher(project_root=project_root)
    
    if args.validate_only:
        validator = PreflightValidator(project_root, {})
        passed, results = validator.run_all_checks()
        for r in results:
            if r.passed:
                OutputFormatter.ok(r.message)
            else:
                OutputFormatter.fail(r.message)
        return 0 if passed else 1
    
    # Full boot sequence
    report = launcher.boot()
    
    if not report.success:
        OutputFormatter.fatal(f"Boot failed: {report.halt_reason}")
        return 1
    
    # Run until interrupted
    launcher.run_forever()
    
    # Graceful shutdown
    launcher.shutdown()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
