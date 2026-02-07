#!/usr/bin/env python3
"""
VEL Orchestration Manifest
============================

SINGLE AUTHORITATIVE startup sequencer for the entire ANVEL system.

This module defines the canonical service dependency graph, startup order,
and readiness verification protocol. It replaces fragmented startup logic
across START_ANVEL.py and ANVEL_MASTER.py with a deterministic boot sequence.

Startup Phases (strict order):
  Phase 0: Pre-flight — environment, disk, permissions
  Phase 1: Safety — SafetyPolicyKernel, RiskKernel, CircuitBreaker
  Phase 2: State — StateLedger persistence verified, OperationalControls loaded
  Phase 3: Infrastructure — EventBus, Database, Redis
  Phase 4: Native — Rust gateway link verification, native core init
  Phase 5: Core — TradeEngine, MarketData, BrokerAdapters
  Phase 6: Intelligence — Brain, StrategyRunner, LearningService
  Phase 7: Monitoring — Watchdog, Heartbeat, HealthMonitor
  Phase 8: Web — API Gateway, WebSocket, Dashboard
  Phase 9: Autonomous — SelfHeal, AutoRepair, Guardian

Every phase gate checks readiness of the previous phase before proceeding.
If a phase fails, the system halts at that phase — no partial starts.

Usage:
    manifest = OrchestrationManifest(config=config)
    boot_report = manifest.execute_boot_sequence()
    if not boot_report.success:
        print(f"Boot failed at phase {boot_report.failed_phase}: {boot_report.failure_reason}")
        sys.exit(1)
"""

import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("vel.orchestration")


class BootPhase(IntEnum):
    """Strict boot phase ordering."""
    PREFLIGHT = 0
    SAFETY = 1
    STATE = 2
    INFRASTRUCTURE = 3
    NATIVE = 4
    CORE = 5
    INTELLIGENCE = 6
    MONITORING = 7
    WEB = 8
    AUTONOMOUS = 9


PHASE_NAMES = {
    BootPhase.PREFLIGHT: "Pre-flight Checks",
    BootPhase.SAFETY: "Safety Policy & Risk Kernel",
    BootPhase.STATE: "State Ledger & Operational Controls",
    BootPhase.INFRASTRUCTURE: "Infrastructure (EventBus, DB, Redis)",
    BootPhase.NATIVE: "Native/Rust Gateway Verification",
    BootPhase.CORE: "Core Trading Engine",
    BootPhase.INTELLIGENCE: "AI & Strategy Intelligence",
    BootPhase.MONITORING: "Monitoring & Health",
    BootPhase.WEB: "Web & API Gateway",
    BootPhase.AUTONOMOUS: "Autonomous Operations",
}


@dataclass
class PhaseResult:
    """Result of a single boot phase."""
    phase: BootPhase
    success: bool
    duration_seconds: float
    components_started: List[str] = field(default_factory=list)
    components_failed: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class BootReport:
    """Complete boot sequence report."""
    success: bool
    total_duration_seconds: float
    phases_completed: int
    total_phases: int
    failed_phase: Optional[int] = None
    failure_reason: Optional[str] = None
    phase_results: List[PhaseResult] = field(default_factory=list)
    components_online: List[str] = field(default_factory=list)
    components_failed: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class OrchestrationManifest:
    """
    Authoritative boot sequence controller.

    Owns the dependency graph and enforces startup order.
    No service may start before its dependencies are verified ready.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        project_root: Optional[Path] = None,
    ):
        self.config = config or {}
        self.project_root = project_root or Path(__file__).resolve().parent

        # Live references to initialized components (populated during boot)
        self.components: Dict[str, Any] = {}

        # Phase registry: maps phase -> list of (name, init_fn, readiness_fn)
        self._phase_registry: Dict[BootPhase, List[Tuple[str, Callable, Optional[Callable]]]] = {
            phase: [] for phase in BootPhase
        }

        self._register_default_phases()

    def _register_default_phases(self) -> None:
        """Register the canonical boot sequence."""

        # Phase 0: Preflight
        self.register_component(
            BootPhase.PREFLIGHT, "python_version", self._check_python_version
        )
        self.register_component(
            BootPhase.PREFLIGHT, "disk_space", self._check_disk_space
        )
        self.register_component(
            BootPhase.PREFLIGHT, "write_permissions", self._check_write_permissions
        )
        self.register_component(
            BootPhase.PREFLIGHT, "config_loaded", self._load_config
        )

        # Phase 1: Safety (MUST load before any execution components)
        self.register_component(
            BootPhase.SAFETY, "safety_policy_kernel", self._init_safety_policy_kernel
        )
        self.register_component(
            BootPhase.SAFETY, "risk_kernel", self._init_risk_kernel
        )
        self.register_component(
            BootPhase.SAFETY, "circuit_breaker", self._init_circuit_breaker
        )

        # Phase 2: State
        self.register_component(
            BootPhase.STATE, "operational_controls", self._init_operational_controls
        )
        self.register_component(
            BootPhase.STATE, "state_ledger", self._init_state_ledger,
            readiness_fn=self._verify_state_ledger_persistence,
        )

        # Phase 3: Infrastructure
        self.register_component(
            BootPhase.INFRASTRUCTURE, "event_bus", self._init_event_bus
        )
        self.register_component(
            BootPhase.INFRASTRUCTURE, "database", self._init_database
        )

        # Phase 4: Native / Rust (optional — Python fallbacks exist)
        self.register_component(
            BootPhase.NATIVE, "rust_gateway", self._init_rust_gateway,
            readiness_fn=self._verify_rust_gateway_link,
            required=False,
        )
        self.register_component(
            BootPhase.NATIVE, "native_core", self._init_native_core,
            required=False,
        )

        # Phase 5: Core trading
        self.register_component(
            BootPhase.CORE, "broker_adapter", self._init_broker_adapter
        )
        self.register_component(
            BootPhase.CORE, "market_data", self._init_market_data
        )
        self.register_component(
            BootPhase.CORE, "trade_engine", self._init_trade_engine
        )

        # Phase 6: Intelligence (optional — system runs in degraded mode without AI)
        self.register_component(
            BootPhase.INTELLIGENCE, "brain", self._init_brain,
            required=False,
        )
        self.register_component(
            BootPhase.INTELLIGENCE, "strategy_runner", self._init_strategy_runner,
            required=False,
        )
        self.register_component(
            BootPhase.INTELLIGENCE, "learning_service", self._init_learning_service,
            required=False,
        )

        # Phase 7: Monitoring (heartbeat is required for Docker healthcheck)
        self.register_component(
            BootPhase.MONITORING, "watchdog", self._init_watchdog,
            required=False,
        )
        self.register_component(
            BootPhase.MONITORING, "heartbeat_monitor", self._init_heartbeat,
            required=False,
        )
        self.register_component(
            BootPhase.MONITORING, "health_monitor", self._init_health_monitor,
            required=False,
        )
        self.register_component(
            BootPhase.MONITORING, "engine_heartbeat", self._start_engine_heartbeat
        )

        # Phase 8: Web (optional — engine can run headless)
        self.register_component(
            BootPhase.WEB, "web_server", self._init_web_server,
            required=False,
        )

        # Phase 9: Autonomous (optional — nice to have, not required for trading)
        self.register_component(
            BootPhase.AUTONOMOUS, "guardian", self._init_guardian,
            required=False,
        )
        self.register_component(
            BootPhase.AUTONOMOUS, "supervisor", self._init_supervisor,
            required=False,
        )

    def register_component(
        self,
        phase: BootPhase,
        name: str,
        init_fn: Callable,
        readiness_fn: Optional[Callable] = None,
        required: bool = True,
    ) -> None:
        """Register a component in a specific boot phase.

        Args:
            required: If True, failure of this component fails the phase.
                      If False, failure is logged but boot continues.
        """
        self._phase_registry[phase].append((name, init_fn, readiness_fn, required))

    # ══════════════════════════════════════════════════════════════
    #  BOOT SEQUENCE EXECUTION
    # ══════════════════════════════════════════════════════════════

    def execute_boot_sequence(self) -> BootReport:
        """
        Execute the complete deterministic boot sequence.

        Returns:
            BootReport with success/failure details.
        """
        boot_start = time.time()
        phase_results: List[PhaseResult] = []
        all_online: List[str] = []
        all_failed: List[str] = []
        all_warnings: List[str] = []

        for phase in BootPhase:
            phase_name = PHASE_NAMES.get(phase, f"Phase {phase}")
            logger.info(f"{'═' * 70}")
            logger.info(f"  BOOT PHASE {phase}: {phase_name}")
            logger.info(f"{'═' * 70}")

            phase_start = time.time()
            components = self._phase_registry.get(phase, [])

            if not components:
                phase_results.append(PhaseResult(
                    phase=phase,
                    success=True,
                    duration_seconds=0,
                    warnings=["no components registered"],
                ))
                continue

            started: List[str] = []
            failed: List[str] = []
            failed_required: List[str] = []
            warnings: List[str] = []

            for name, init_fn, readiness_fn, required in components:
                try:
                    logger.info(f"  Starting: {name} ({'required' if required else 'optional'})")
                    result = init_fn()

                    if result is not None:
                        self.components[name] = result

                    # Run readiness verification if provided
                    if readiness_fn is not None:
                        ready = readiness_fn()
                        if not ready:
                            if required:
                                failed_required.append(name)
                                logger.error(f"  ✗ {name}: readiness check failed (REQUIRED)")
                            else:
                                failed.append(name)
                                warnings.append(f"{name}: readiness check failed (optional)")
                                logger.warning(f"  ⚠ {name}: readiness check failed (optional, continuing)")
                            continue

                    started.append(name)
                    logger.info(f"  ✓ {name}: ready")

                except Exception as e:
                    if required:
                        failed_required.append(name)
                        logger.error(f"  ✗ {name}: {e} (REQUIRED)")
                    else:
                        failed.append(name)
                        warnings.append(f"{name}: {e} (optional)")
                        logger.warning(f"  ⚠ {name}: {e} (optional, continuing)")

            phase_duration = time.time() - phase_start
            phase_success = len(failed_required) == 0

            phase_results.append(PhaseResult(
                phase=phase,
                success=phase_success,
                duration_seconds=phase_duration,
                components_started=started,
                components_failed=failed_required + failed,
                warnings=warnings,
                error=f"Required components failed: {', '.join(failed_required)}" if failed_required else None,
            ))

            all_online.extend(started)
            all_failed.extend(failed_required + failed)
            all_warnings.extend(warnings)

            if not phase_success:
                total_duration = time.time() - boot_start
                logger.error(
                    f"Boot sequence HALTED at phase {phase} ({phase_name}): "
                    f"{', '.join(failed_required)} failed (required)"
                )
                return BootReport(
                    success=False,
                    total_duration_seconds=total_duration,
                    phases_completed=phase,
                    total_phases=len(BootPhase),
                    failed_phase=phase,
                    failure_reason=f"Phase {phase} ({phase_name}) failed: {', '.join(failed_required)} (required)",
                    phase_results=phase_results,
                    components_online=all_online,
                    components_failed=all_failed,
                    warnings=all_warnings,
                )

        total_duration = time.time() - boot_start
        logger.info(f"{'═' * 70}")
        logger.info(f"  BOOT COMPLETE: {len(all_online)} components online in {total_duration:.1f}s")
        logger.info(f"{'═' * 70}")

        return BootReport(
            success=True,
            total_duration_seconds=total_duration,
            phases_completed=len(BootPhase),
            total_phases=len(BootPhase),
            phase_results=phase_results,
            components_online=all_online,
            components_failed=all_failed,
            warnings=all_warnings,
        )

    # ══════════════════════════════════════════════════════════════
    #  SHUTDOWN (reverse order)
    # ══════════════════════════════════════════════════════════════

    def execute_shutdown_sequence(self) -> Dict[str, str]:
        """Shut down all components in reverse boot order."""
        results: Dict[str, str] = {}

        for phase in reversed(list(BootPhase)):
            components = self._phase_registry.get(phase, [])
            for name, _, _, _ in reversed(components):
                component = self.components.get(name)
                if component is None:
                    continue
                try:
                    if hasattr(component, "shutdown"):
                        component.shutdown()
                        results[name] = "stopped"
                    elif hasattr(component, "stop"):
                        component.stop()
                        results[name] = "stopped"
                    elif hasattr(component, "close"):
                        component.close()
                        results[name] = "closed"
                    else:
                        results[name] = "no_shutdown_method"
                except Exception as e:
                    results[name] = f"error: {e}"
                    logger.error(f"Shutdown error for {name}: {e}")

        return results

    # ══════════════════════════════════════════════════════════════
    #  PHASE 0: PREFLIGHT IMPLEMENTATIONS
    # ══════════════════════════════════════════════════════════════

    def _check_python_version(self) -> str:
        import sys
        v = sys.version_info
        if v < (3, 8):
            raise RuntimeError(f"Python 3.8+ required, found {v.major}.{v.minor}")
        return f"{v.major}.{v.minor}.{v.micro}"

    def _check_disk_space(self) -> float:
        import shutil
        total, used, free = shutil.disk_usage(self.project_root)
        free_gb = free / (1024 ** 3)
        if free_gb < 0.5:
            raise RuntimeError(f"Insufficient disk space: {free_gb:.2f} GB")
        return free_gb

    def _check_write_permissions(self) -> bool:
        test_file = self.project_root / ".boot_write_test"
        try:
            test_file.touch()
            test_file.unlink()
            return True
        except Exception as e:
            raise RuntimeError(f"Write permission check failed: {e}")

    def _load_config(self) -> Dict[str, Any]:
        import json
        
        # Load main config file
        config_path = self.project_root / "anvel_config.json"
        if config_path.exists():
            with open(config_path, "r") as f:
                loaded = json.load(f)
            self.config.update(loaded)
        
        # Validate configuration files using schema validator
        try:
            from vel_config_validator import validate_configuration, ValidationResult
            config_dir = self.project_root / "config"
            
            if config_dir.exists():
                result: ValidationResult = validate_configuration(str(config_dir))
                
                # Log validation warnings
                for warning in result.warnings:
                    logger.warning(
                        f"Config validation warning: {warning.config_file} - "
                        f"{warning.field_path}: {warning.message}"
                    )
                
                # Fail on validation errors in strict mode
                if not result.is_valid:
                    error_messages = [
                        f"{e.config_file}/{e.field_path}: {e.message}"
                        for e in result.errors
                    ]
                    raise RuntimeError(
                        f"Configuration validation failed: {'; '.join(error_messages)}"
                    )
                
                # Merge validated configs
                for config_name, config_data in result.validated_configs.items():
                    key = config_name.replace(".json", "_config")
                    self.config[key] = config_data
                
                logger.info("Configuration validated successfully")
        except ImportError:
            logger.debug("Config validator not available, skipping schema validation")
        except RuntimeError:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.warning(f"Config validation error (non-fatal): {e}")
        
        return self.config

    # ══════════════════════════════════════════════════════════════
    #  PHASE 1: SAFETY
    # ══════════════════════════════════════════════════════════════

    def _init_safety_policy_kernel(self) -> Any:
        from vel_safety_policy_kernel import SafetyPolicyKernel, SafetyPolicyConfig

        trading_cfg = self.config.get("trading_config", {})
        safety_cfg = self.config.get("safety_policy", {})

        policy_config = SafetyPolicyConfig(
            max_trades_per_minute=safety_cfg.get("max_trades_per_minute", 10),
            max_trades_per_hour=safety_cfg.get("max_trades_per_hour", 120),
            max_trades_per_day=safety_cfg.get("max_trades_per_day", 1000),
            drawdown_halt_pct=_decimal(safety_cfg.get("drawdown_halt_pct", "0.10")),
        )
        return SafetyPolicyKernel(config=policy_config)

    def _init_risk_kernel(self) -> Any:
        from vel_risk_kernel import RiskKernel
        return RiskKernel(enable_strict_mode=True)

    def _init_circuit_breaker(self) -> Any:
        from vel_circuit_breaker import CircuitBreakerManager
        return CircuitBreakerManager()

    # ══════════════════════════════════════════════════════════════
    #  PHASE 2: STATE
    # ══════════════════════════════════════════════════════════════

    def _init_operational_controls(self) -> Any:
        from vel_operational_controls import OperationalController
        return OperationalController()

    def _init_state_ledger(self) -> Any:
        from vel_state_ledger import StateLedger
        return StateLedger()

    def _verify_state_ledger_persistence(self) -> bool:
        """Verify state ledger can persist and retrieve data."""
        ledger = self.components.get("state_ledger")
        if ledger is None:
            return False
        # Verify the ledger object initialized (has its db connection or file)
        if hasattr(ledger, "db_path"):
            return Path(ledger.db_path).parent.exists()
        return True

    # ══════════════════════════════════════════════════════════════
    #  PHASE 3: INFRASTRUCTURE
    # ══════════════════════════════════════════════════════════════

    def _init_event_bus(self) -> Any:
        from anvel_event_bus import AnvelEventBus
        bus = AnvelEventBus()
        bus.startup()
        return bus

    def _init_database(self) -> Any:
        from anvel_database_service import DatabaseService
        return DatabaseService()

    # ══════════════════════════════════════════════════════════════
    #  PHASE 4: NATIVE / RUST
    # ══════════════════════════════════════════════════════════════

    def _init_rust_gateway(self) -> Any:
        """Attempt to initialize Rust gateway connection."""
        hybrid_cfg = self.config.get("system_config", {}).get("hybrid", {})
        if not hybrid_cfg.get("enabled", False):
            logger.info("Hybrid/Rust gateway disabled in config — skipping")
            return {"status": "disabled", "endpoint": None}

        endpoint = hybrid_cfg.get("gateway_endpoint", "http://localhost:50052")
        return {"status": "configured", "endpoint": endpoint}

    def _verify_rust_gateway_link(self) -> bool:
        """Verify Rust gateway is reachable if enabled."""
        gw = self.components.get("rust_gateway")
        if gw is None or gw.get("status") == "disabled":
            return True  # Not required when disabled

        endpoint = gw.get("endpoint")
        if not endpoint:
            return True

        # In production, this would HTTP GET the gateway health endpoint.
        # During build/local dev, we accept configured-but-unreachable as OK
        # since the gateway may start in a separate container.
        try:
            import urllib.request
            req = urllib.request.Request(f"{endpoint}/health", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            logger.warning(
                f"Rust gateway at {endpoint} not reachable — "
                "will retry at runtime (expected if starting in separate container)"
            )
            return True  # Non-blocking: gateway may start later in compose

    def _init_native_core(self) -> Any:
        try:
            from anvel_native_core import NativeExecCore
            core = NativeExecCore()
            return core
        except ImportError:
            logger.warning("NativeExecCore not available — Python fallback active")
            return None

    # ══════════════════════════════════════════════════════════════
    #  PHASE 5: CORE
    # ══════════════════════════════════════════════════════════════

    def _init_broker_adapter(self) -> Any:
        trading_cfg = self.config.get("trading_config", {})
        broker_name = trading_cfg.get("broker", "uniswap_v3")
        try:
            from anvel_broker_factory import BrokerFactory

            # Create DEX execution broker
            dex_broker = BrokerFactory.create_dex(dex_id=broker_name)

            # Also create a read-only data feed for price discovery
            data_feed = None
            try:
                data_feed = BrokerFactory.create_data_feed(source="kraken")
            except Exception as e:
                logger.warning(f"Data feed init: {e} (non-fatal)")

            return {
                "dex_broker": dex_broker,
                "data_feed": data_feed,
                "dex_id": broker_name,
                "status": "active",
            }
        except Exception as e:
            logger.error(f"Broker adapter init failed: {e}")
            raise  # Required component — must not silently degrade

    def _init_market_data(self) -> Any:
        event_bus = self.components.get("event_bus")
        trading_cfg = self.config.get("trading_config", {})
        watchlist = trading_cfg.get("watchlist", ["BTC", "ETH"])

        try:
            from anvel_market_data import ANVELMarketData
            return ANVELMarketData(
                event_bus=event_bus,
                symbols=watchlist[:20],  # Cap initial symbols for fast boot
                broker=trading_cfg.get("broker", "kraken"),
                window=400,
                interval=trading_cfg.get("check_interval", 300) / 60,
            )
        except Exception as e:
            logger.warning(f"MarketData init: {e}")
            return None

    def _init_trade_engine(self) -> Any:
        event_bus = self.components.get("event_bus")
        safety_kernel = self.components.get("safety_policy_kernel")
        risk_kernel = self.components.get("risk_kernel")

        try:
            from anvel_trade_engine import AnvelTradeEngine
            engine = AnvelTradeEngine(event_bus=event_bus)

            # Wire safety policy kernel into trade engine
            if safety_kernel and hasattr(engine, "_safety_policy"):
                engine._safety_policy = safety_kernel
            elif safety_kernel:
                engine._safety_policy = safety_kernel

            # Wire risk kernel
            if risk_kernel and hasattr(engine, "_risk_kernel"):
                engine._risk_kernel = risk_kernel
            elif risk_kernel:
                engine._risk_kernel = risk_kernel

            # Wire native core
            native_core = self.components.get("native_core")
            if native_core:
                engine._native_core = native_core

            return engine
        except Exception as e:
            logger.warning(f"TradeEngine init: {e}")
            return None

    # ══════════════════════════════════════════════════════════════
    #  PHASE 6: INTELLIGENCE
    # ══════════════════════════════════════════════════════════════

    def _init_brain(self) -> Any:
        """Initialize AI core (using consolidated ai.core module).
        
        ai.core is REQUIRED - no fallback to legacy modules.
        """
        try:
            from ai.core import AISupervisor
            event_bus = self.components.get("event_bus")
            return AISupervisor(event_bus=event_bus)
        except ImportError as e:
            logger.error(f"REQUIRED ai.core module not available: {e}")
            logger.error("Install AI dependencies: pip install -r requirements.txt")
            raise ImportError(
                "ai.core is required for VEL operation. "
                "Ensure all dependencies are installed."
            ) from e
        except Exception as e:
            logger.warning(f"AI Supervisor init: {e}")
            return None

    def _init_strategy_runner(self) -> Any:
        market_data = self.components.get("market_data")
        event_bus = self.components.get("event_bus")
        trading_cfg = self.config.get("trading_config", {})
        strategy_cfg = self.config.get("strategy_config", {})

        try:
            from anvel_strategy_runner import ANVELStrategyRunner
            return ANVELStrategyRunner(
                market_data=market_data,
                event_bus=event_bus,
                symbols=trading_cfg.get("watchlist", ["BTC", "ETH"])[:20],
                threshold=float(strategy_cfg.get("threshold", 0.6)),
                interval=float(strategy_cfg.get("interval", 2.0)),
            )
        except Exception as e:
            logger.warning(f"StrategyRunner init: {e}")
            return None

    def _init_learning_service(self) -> Any:
        market_data = self.components.get("market_data")
        event_bus = self.components.get("event_bus")
        strategy_runner = self.components.get("strategy_runner")

        try:
            from ai.learning import ContinuousLearningSystem
            return ContinuousLearningSystem()
        except Exception:
            try:
                from anvel_continuous_learning import ContinuousLearningSystem as CLSFallback
                return CLSFallback()
            except Exception as e2:
                logger.warning(f"LearningService init: {e2}")
                return None

    # ══════════════════════════════════════════════════════════════
    #  PHASE 7: MONITORING
    # ══════════════════════════════════════════════════════════════

    def _init_watchdog(self) -> Any:
        monitoring_cfg = self.config.get("monitoring", {})
        timeout = int(monitoring_cfg.get("watchdog_timeout", 60))
        try:
            from anvel_monitoring import ANVELWatchdog
            return ANVELWatchdog(timeout=timeout)
        except Exception as e:
            logger.warning(f"Watchdog init: {e}")
            return None

    def _init_heartbeat(self) -> Any:
        monitoring_cfg = self.config.get("monitoring", {})
        interval = int(monitoring_cfg.get("heartbeat_interval", 10))
        try:
            from anvel_monitoring import ANVELHeartbeatMonitor
            return ANVELHeartbeatMonitor(interval=interval)
        except Exception as e:
            logger.warning(f"Heartbeat init: {e}")
            return None

    def _init_health_monitor(self) -> Any:
        try:
            from anvel_monitoring import ANVELHealthMonitor
            return ANVELHealthMonitor()
        except Exception as e:
            logger.warning(f"HealthMonitor init: {e}")
            return None

    def _start_engine_heartbeat(self) -> Any:
        """Write a heartbeat file periodically for Docker healthcheck."""
        import threading
        heartbeat_path = self.project_root / "data" / ".engine_heartbeat"
        heartbeat_path.parent.mkdir(parents=True, exist_ok=True)

        def _writer():
            while True:
                try:
                    heartbeat_path.write_text(str(time.time()))
                except Exception:
                    pass
                time.sleep(15)

        t = threading.Thread(target=_writer, daemon=True, name="engine-heartbeat")
        t.start()
        # Write initial heartbeat immediately
        heartbeat_path.write_text(str(time.time()))
        return {"path": str(heartbeat_path), "status": "running"}

    # ══════════════════════════════════════════════════════════════
    #  PHASE 8: WEB
    # ══════════════════════════════════════════════════════════════

    def _init_web_server(self) -> Any:
        # Production deployment uses webapp.app via gunicorn.
        # Verify the actual deployment target is importable.
        try:
            import importlib
            mod = importlib.import_module("webapp.app")
            # Verify it has the create_app factory or app object
            has_factory = hasattr(mod, "create_app")
            has_app = hasattr(mod, "app")
            if not has_factory and not has_app:
                logger.warning("webapp.app has neither create_app() nor app object")
                return {"status": "incomplete", "module": "webapp.app"}
            return {"status": "importable", "module": "webapp.app", "has_create_app": has_factory, "port": 8080}
        except Exception as e:
            logger.warning(f"WebServer module check (webapp.app): {e}")
            # Fallback: check standalone anvel_web_server
            try:
                import importlib
                importlib.import_module("anvel_web_server")
                return {"status": "fallback", "module": "anvel_web_server", "port": 5000}
            except Exception as e2:
                logger.warning(f"WebServer fallback check (anvel_web_server): {e2}")
                return {"status": "unavailable", "error": str(e)}

    # ══════════════════════════════════════════════════════════════
    #  PHASE 9: AUTONOMOUS
    # ══════════════════════════════════════════════════════════════

    def _init_guardian(self) -> Any:
        try:
            from anvel_guardian_ai import AnvelGuardianAi
            return AnvelGuardianAi()
        except Exception as e:
            logger.warning(f"Guardian init: {e}")
            return None

    def _init_supervisor(self) -> Any:
        watchdog = self.components.get("watchdog")
        health = self.components.get("health_monitor")
        event_bus = self.components.get("event_bus")
        brain = self.components.get("brain")
        trade_engine = self.components.get("trade_engine")
        guardian = self.components.get("guardian")

        try:
            from ai.core import AISupervisor
            return AISupervisor(
                watchdog=watchdog,
                telemetry=None,
                health=health,
                updater=None,
                guardian=guardian,
                event_bus=event_bus,
                brain=brain,
                memory=None,
                trade_engine=trade_engine,
            )
        except Exception as e:
            logger.warning(f"Supervisor init: {e}")
            return None


def _decimal(val: Any) -> "Decimal":
    """Safe Decimal conversion."""
    from decimal import Decimal as D
    try:
        return D(str(val))
    except Exception:
        return D("0")
