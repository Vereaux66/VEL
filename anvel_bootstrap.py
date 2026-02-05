#!/usr/bin/env python3
# flake8: noqa
"""Runtime bootstrap wiring for ANVEL modules.

This module uses AggressiveImportRepairer to handle import failures gracefully
by attempting multiple repair strategies before giving up.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, cast

# Track import repair results for reporting
_import_repair_results: Dict[str, Any] = {}
_import_attempts: List[Tuple[str, str, Any, Optional[str]]] = (
    []
)  # (module, class, obj, error)


def _safe_import(module_name: str, class_name: str) -> Tuple[Any, Optional[str]]:
    """
    Safely import a class from a module with aggressive repair on failure.

    Returns (class_or_None, error_message_or_None)
    """
    global _import_repair_results, _import_attempts

    try:
        # First, try importing the repairer
        from anvel_import_repairer import get_repairer

        repairer = get_repairer()

        obj, repair_result = repairer.safe_import(module_name, class_name)
        if repair_result:
            _import_repair_results[module_name] = {
                "success": repair_result.success,
                "attempts": len(repair_result.attempts),
                "error": repair_result.final_error,
            }

        if obj is not None:
            _import_attempts.append((module_name, class_name, obj, None))
            return obj, None

        error_msg = f"Failed to import {class_name} from {module_name}"
        if repair_result and repair_result.final_error:
            error_msg += f": {repair_result.final_error}"
        _import_attempts.append((module_name, class_name, None, error_msg))
        return None, error_msg

    except ImportError:
        # Repairer not available, try direct import
        try:
            import importlib

            mod = importlib.import_module(module_name)
            cls = getattr(mod, class_name, None)
            if cls is None:
                error = f"{class_name} not found in {module_name}"
                _import_attempts.append((module_name, class_name, None, error))
                return None, error
            _import_attempts.append((module_name, class_name, cls, None))
            return cls, None
        except ImportError as e:
            error = str(e)
            _import_attempts.append((module_name, class_name, None, error))
            return None, error


# Import all required classes with aggressive repair
# These will be attempted in order, with repair strategies applied as needed

AnvelEventBus, _err1 = _safe_import("anvel_event_bus", "AnvelEventBus")
AnvelTradeEngine, _err2 = _safe_import("anvel_trade_engine", "AnvelTradeEngine")
ANVELMarketData, _err3 = _safe_import("anvel_market_data", "ANVELMarketData")
ANVELStrategyRunner, _err4 = _safe_import(
    "anvel_strategy_runner", "ANVELStrategyRunner"
)
ANVELAISupervisor, _err5 = _safe_import("anvel_ai_supervisor", "ANVELAISupervisor")
AnvelGuardianAi, _err6 = _safe_import("anvel_guardian_ai", "AnvelGuardianAi")
AnvelSystemOrchestrator, _err7 = _safe_import(
    "anvel_system_orchestrator", "AnvelSystemOrchestrator"
)
AnvelBrain, _err8 = _safe_import("anvel_brain", "AnvelBrain")
ANVELLearningService, _err9 = _safe_import(
    "anvel_learning_service", "ANVELLearningService"
)

# Import monitoring classes
ANVELWatchdog, _err10 = _safe_import("anvel_monitoring", "ANVELWatchdog")
ANVELHeartbeatMonitor, _err11 = _safe_import(
    "anvel_monitoring", "ANVELHeartbeatMonitor"
)
ANVELHealthMonitor, _err12 = _safe_import("anvel_monitoring", "ANVELHealthMonitor")

AnvelMemory, _err13 = _safe_import("anvel_memory", "AnvelMemory")
AnvelConsciousness, _err14 = _safe_import("anvel_consciousness", "AnvelConsciousness")
ANVELSecurityLayer, _err15 = _safe_import("anvel_security_layer", "ANVELSecurityLayer")

# Import integration layer for database wiring
IntegratedTradeEngine, _err_int = _safe_import("anvel_integration", "IntegratedTradeEngine")
LearningFeedbackBridge, _err_lfb = _safe_import("anvel_integration", "LearningFeedbackBridge")
DatabaseService, _err_db = _safe_import("anvel_database_service", "DatabaseService")


def get_import_errors() -> List[Tuple[str, str]]:
    """Return list of (module_name, error_message) for failed imports.

    Dynamically built from the import attempts tracking list.
    """
    return [
        (f"{module}:{cls}", error)
        for module, cls, obj, error in _import_attempts
        if error is not None
    ]


def get_import_repair_summary() -> Dict[str, Any]:
    """Return summary of import repair attempts."""
    return _import_repair_results.copy()


class ANVELRuntimeBootstrap:
    """Wire core ANVEL modules and manage their lifecycle.

    Handles cases where some modules may have failed to import by
    creating placeholder objects or skipping unavailable components.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config: Dict[str, Any] = config or {}
        self._subscriptions: List[str] = []
        self._running = False
        self._last_launch: Dict[str, Any] = {}
        self._unavailable_modules: List[str] = []

        # Report any import errors that occurred
        import_errors = get_import_errors()
        if import_errors:
            for module, error in import_errors:
                print(
                    f"  ⚠ Import issue in {module}: {error[:80] if error else 'unknown'}"
                )
                self._unavailable_modules.append(module)

        # Initialize modules with fallback handling
        self.event_bus = self._safe_init(AnvelEventBus, "event_bus")
        self.watchdog = self._safe_init(
            ANVELWatchdog, "watchdog", timeout=self._get_watchdog_timeout()
        )
        self.heartbeat_monitor = self._safe_init(
            ANVELHeartbeatMonitor,
            "heartbeat_monitor",
            interval=self._get_heartbeat_interval(),
        )
        self.health_monitor = self._safe_init(ANVELHealthMonitor, "health_monitor")
        self.memory = self._safe_init(AnvelMemory, "memory")
        self.consciousness = self._safe_init(AnvelConsciousness, "consciousness")
        self.security_layer = self._safe_init(ANVELSecurityLayer, "security_layer")
        self.guardian = self._safe_init(AnvelGuardianAi, "guardian")
        # Initialize trade engine with database integration
        raw_trade_engine = self._safe_init(
            AnvelTradeEngine, "trade_engine", event_bus=self.event_bus
        )

        # Initialize database service for trade persistence
        self.database_service = self._safe_init(DatabaseService, "database_service")

        # Wrap trade engine with integration layer for persistence
        if raw_trade_engine and IntegratedTradeEngine:
            try:
                self.trade_engine = IntegratedTradeEngine(
                    trade_engine=raw_trade_engine,
                    database_service=self.database_service,
                    event_bus=self.event_bus,
                    user_id="system",
                )
            except (TypeError, AttributeError):
                self.trade_engine = raw_trade_engine
        else:
            self.trade_engine = raw_trade_engine
        self.watchlist = self._get_watchlist()
        self.market_data = self._safe_init(
            ANVELMarketData,
            "market_data",
            event_bus=self.event_bus,
            symbols=self.watchlist,
            broker=self._get_broker(),
            window=400,
            interval=self._get_market_interval(),
        )
        self.brain = self._safe_init(AnvelBrain, "brain")
        self.strategy_runner = self._safe_init(
            ANVELStrategyRunner,
            "strategy_runner",
            market_data=self.market_data,
            event_bus=self.event_bus,
            symbols=self.watchlist,
            threshold=self._get_strategy_threshold(),
            interval=self._get_strategy_interval(),
        )
        self.learning_service = self._safe_init(
            ANVELLearningService,
            "learning_service",
            market_data=self.market_data,
            symbols=self.watchlist,
            event_bus=self.event_bus,
            strategy_runner=self.strategy_runner,
        )

        # Initialize learning feedback bridge for execution feedback loop
        self.learning_feedback_bridge = None
        if LearningFeedbackBridge and self.event_bus:
            try:
                self.learning_feedback_bridge = LearningFeedbackBridge(
                    event_bus=self.event_bus,
                    learning_service=self.learning_service,
                )
                self.learning_feedback_bridge.start()
            except (TypeError, AttributeError) as e:
                import logging
                logging.getLogger(__name__).debug(
                    "Learning feedback bridge init failed: %s", e
                )

        # Attach dependencies if modules are available
        if self.consciousness and self.memory:
            try:
                self.consciousness.attach_memory(self.memory)  # type: ignore[attr-defined]
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_BOOTSTRAP").debug("Exception suppressed in __init__")
        if self.consciousness and self.event_bus:
            try:
                self.consciousness.attach_event_bus(self.event_bus)  # type: ignore[attr-defined]
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_BOOTSTRAP").debug("Exception suppressed in __init__")

        self.supervisor = self._safe_init(
            ANVELAISupervisor,
            "supervisor",
            watchdog=self.watchdog,
            telemetry=None,
            health=self.health_monitor,
            updater=None,
            guardian=self.guardian,
            event_bus=self.event_bus,
            brain=self.brain,
            memory=self.memory,
            trade_engine=self.trade_engine,
        )

        self._wire_event_bus()

        # Build module list, excluding None modules
        module_specs = []
        if self.event_bus:
            module_specs.append({"name": "event_bus", "module": self.event_bus})
        if self.watchdog:
            module_specs.append({"name": "watchdog", "module": self.watchdog})
        if self.heartbeat_monitor:
            module_specs.append(
                {"name": "heartbeat_monitor", "module": self.heartbeat_monitor}
            )
        if self.health_monitor:
            module_specs.append(
                {"name": "health_monitor", "module": self.health_monitor}
            )
        if self.memory:
            module_specs.append({"name": "memory", "module": self.memory})
        if self.consciousness:
            module_specs.append(
                {
                    "name": "consciousness",
                    "module": self.consciousness,
                    "depends_on": ["memory", "event_bus"],
                }
            )
        if self.security_layer:
            module_specs.append(
                {"name": "security_layer", "module": self.security_layer}
            )
        if self.guardian:
            module_specs.append(
                {
                    "name": "guardian",
                    "module": self.guardian,
                    "depends_on": ["event_bus"],
                }
            )
        if self.trade_engine:
            module_specs.append(
                {
                    "name": "trade_engine",
                    "module": self.trade_engine,
                    "depends_on": ["event_bus"],
                }
            )
        if self.market_data:
            module_specs.append(
                {
                    "name": "market_data",
                    "module": self.market_data,
                    "depends_on": ["event_bus"],
                }
            )
        if self.brain:
            module_specs.append(
                {"name": "brain", "module": self.brain, "depends_on": ["event_bus"]}
            )
        if self.strategy_runner:
            module_specs.append(
                {
                    "name": "strategy_runner",
                    "module": self.strategy_runner,
                    "depends_on": ["market_data", "event_bus"],
                }
            )
        if self.learning_service:
            module_specs.append(
                {
                    "name": "learning_service",
                    "module": self.learning_service,
                    "depends_on": ["market_data", "strategy_runner"],
                }
            )
        if self.supervisor:
            module_specs.append(
                {
                    "name": "supervisor",
                    "module": self.supervisor,
                    "depends_on": [
                        "trade_engine",
                        "guardian",
                        "watchdog",
                        "health_monitor",
                        "memory",
                        "event_bus",
                    ],
                }
            )

        self.orchestrator = self._safe_init(
            AnvelSystemOrchestrator, "orchestrator", module_specs
        )

    def _safe_init(self, cls: Any, name: str, *args: Any, **kwargs: Any) -> Any:
        """Safely initialize a class, returning None if it fails or class is None."""
        if cls is None:
            self._unavailable_modules.append(name)
            return None
        try:
            return cls(*args, **kwargs)
        except Exception as e:
            print(f"  ⚠ Failed to initialize {name}: {str(e)[:60]}")
            self._unavailable_modules.append(name)
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_watchlist(self) -> List[str]:
        trading = self.config.get("trading_config", {})
        symbols = trading.get("watchlist") or ["BTC", "ETH"]
        return [str(sym).upper() for sym in symbols]

    def _get_broker(self) -> str:
        trading = self.config.get("trading_config", {})
        return str(trading.get("broker", "kraken")).lower()

    def _get_market_interval(self) -> float:
        trading = self.config.get("market_data", {})
        interval = trading.get("poll_interval", 1.0)
        try:
            return float(interval)
        except Exception:
            return 1.0

    def _get_strategy_threshold(self) -> float:
        strategy_cfg = self.config.get("strategy_config", {})
        try:
            return float(strategy_cfg.get("threshold", 0.6))
        except Exception:
            return 0.6

    def _get_strategy_interval(self) -> float:
        strategy_cfg = self.config.get("strategy_config", {})
        try:
            return float(strategy_cfg.get("interval", 2.0))
        except Exception:
            return 2.0

    def _get_watchdog_timeout(self) -> int:
        monitoring_cfg = self.config.get("monitoring", {})
        trading_cfg = self.config.get("trading_config", {})
        raw = (
            monitoring_cfg.get("watchdog_timeout")
            or trading_cfg.get("check_interval")
            or 60
        )
        try:
            return int(float(raw))
        except Exception:
            return 60

    def _get_heartbeat_interval(self) -> int:
        monitoring_cfg = self.config.get("monitoring", {})
        raw = monitoring_cfg.get("heartbeat_interval") or 10
        try:
            return int(float(raw))
        except Exception:
            return 10

    def _wire_event_bus(self):
        """Wire event bus subscriptions, handling None modules gracefully."""
        if not self.event_bus:
            return

        if self.brain and hasattr(self.brain, "ingest_market_tick"):
            try:
                self._subscriptions.append(
                    self.event_bus.subscribe("market.tick", self.brain.ingest_market_tick)  # type: ignore[arg-type]
                )
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_BOOTSTRAP").debug("Exception suppressed in _wire_event_bus")

        if self.strategy_runner and hasattr(self.strategy_runner, "handle_market_tick"):
            try:
                self._subscriptions.append(
                    self.event_bus.subscribe("market.tick", self.strategy_runner.handle_market_tick)  # type: ignore[arg-type]
                )
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_BOOTSTRAP").debug("Exception suppressed in _wire_event_bus")

        if self.learning_service and hasattr(
            self.learning_service, "handle_market_tick"
        ):
            try:
                self._subscriptions.append(
                    self.event_bus.subscribe("market.tick", self.learning_service.handle_market_tick)  # type: ignore[arg-type]
                )
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_BOOTSTRAP").debug("Exception suppressed in _wire_event_bus")

        try:
            self._subscriptions.append(
                self.event_bus.subscribe("system.events", self._route_system_event)  # type: ignore[arg-type]
            )
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_BOOTSTRAP").debug("Exception suppressed in _wire_event_bus")

        try:
            self._subscriptions.append(
                self.event_bus.subscribe("system.alerts", self._handle_security_alert)  # type: ignore[arg-type]
            )
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_BOOTSTRAP").debug("Exception suppressed in _wire_event_bus")

    def _route_system_event(self, payload: Optional[Dict[str, Any]]):
        if not payload:
            return
        subsystem = str(payload.get("module") or payload.get("source") or "unknown")
        state = (
            payload.get("level")
            or payload.get("intent")
            or payload.get("status")
            or "info"
        )
        meta = {
            "intent": payload.get("intent"),
            "message": payload.get("message") or payload.get("result"),
        }
        try:
            self.consciousness.aware_of(subsystem, state=str(state), meta=meta)  # type: ignore[attr-defined]
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_BOOTSTRAP").debug("Exception suppressed in _route_system_event")
        if (payload.get("intent") or "").lower() == "heartbeat":
            try:
                self.watchdog.ping()
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_BOOTSTRAP").debug("Exception suppressed in _route_system_event")

    def _handle_security_alert(self, payload: Optional[Dict[str, Any]]):
        if not payload:
            return
        source = str(payload.get("module") or payload.get("source") or "unknown")
        description = (
            payload.get("description")
            or payload.get("message")
            or payload.get("intent")
            or "system alert"
        )
        severity = str(payload.get("severity") or payload.get("level") or "medium")
        try:
            self.security_layer.detect(source, str(description), severity=severity)  # type: ignore[attr-defined]
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_BOOTSTRAP").debug("Exception suppressed in _handle_security_alert")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> Dict[str, Any]:
        if self._running:
            return self._last_launch
        if not self.orchestrator:
            self._last_launch = {
                "error": "orchestrator unavailable",
                "modules_started": 0,
            }
            return self._last_launch
        try:
            launch_report = cast(Dict[str, Any], self.orchestrator.startup())
        except Exception as e:
            launch_report = {"error": str(e), "modules_started": 0}
        self._last_launch = launch_report
        self._running = True
        return launch_report

    def stop(self) -> Dict[str, Any]:
        if not self._running:
            return {}
        shutdown_report: Dict[str, Any] = {}

        # Stop learning feedback bridge
        if hasattr(self, "learning_feedback_bridge") and self.learning_feedback_bridge:
            try:
                self.learning_feedback_bridge.stop()
            except (AttributeError, RuntimeError):
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_BOOTSTRAP").debug("Exception suppressed in stop")

        # Close database service
        if hasattr(self, "database_service") and self.database_service:
            try:
                self.database_service.close()
            except (AttributeError, RuntimeError):
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_BOOTSTRAP").debug("Exception suppressed in stop")

        if self.orchestrator:
            try:
                shutdown_report = cast(Dict[str, Any], self.orchestrator.shutdown())
            except Exception as e:
                shutdown_report = {"error": str(e)}
        for token in self._subscriptions:
            if self.event_bus:
                try:
                    self.event_bus.unsubscribe(token)
                except Exception:
                    import logging as _lg  # noqa: E402
                    _lg.getLogger("ANVEL_BOOTSTRAP").debug("Exception suppressed in stop")
        self._subscriptions.clear()
        self._running = False
        return shutdown_report

    def get_status(self) -> Dict[str, Any]:
        trading_mode = self.config.get("trading_config", {}).get(
            "trading_mode", "unknown"
        )
        module_count = 0
        if self.orchestrator:
            module_count = len(getattr(self.orchestrator, "_module_specs", []))
        return {
            "running": self._running,
            "modules": module_count,
            "config_mode": trading_mode,
            "watchdog": (
                self.watchdog.get_status()
                if self.watchdog
                else "[watchdog unavailable]"
            ),
            "heartbeat": (
                self.heartbeat_monitor.get_status()
                if self.heartbeat_monitor
                else "[heartbeat unavailable]"
            ),
            "unavailable_modules": self._unavailable_modules,
        }
