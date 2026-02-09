#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║                        VEL UNIFIED ENTRY POINT                               ║
║                    Single Entry Point for All Modules                        ║
║                                                                              ║
║  This is THE authoritative entry point for the VEL trading system.           ║
║  All modules are initialized and wired together from here.                   ║
║                                                                              ║
║  USAGE: python vel_main.py                                                   ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import logging
import os
import sys
import json
import signal
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("vel.main")

# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

VERSION = "3.0.0"
SYSTEM_NAME = "VEL Trading System"


class SystemConfig:
    """Central configuration for the VEL system."""
    
    def __init__(self, config_path: str = "anvel_config.json"):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """Load configuration from file."""
        if Path(self.config_path).exists():
            with open(self.config_path, 'r') as f:
                self.config = json.load(f)
            logger.info(f"Loaded config from {self.config_path}")
        else:
            self.config = self._default_config()
            logger.warning(f"Config not found, using defaults")
    
    def _default_config(self) -> Dict[str, Any]:
        return {
            "system": {
                "name": SYSTEM_NAME,
                "version": VERSION,
                "environment": os.getenv("ANVEL_ENVIRONMENT", "development")
            },
            "trading": {
                "watchlist": ["ETH", "BTC", "USDC"],
                "default_dex": "uniswap_v3",
                "default_chain": 1,
                "max_slippage": 0.005,
                "gas_limit": 300000
            },
            "risk": {
                "max_position_size": 0.05,
                "daily_loss_limit": 0.03,
                "max_trades_per_hour": 20
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot-notation key."""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

class ModuleRegistry:
    """Registry of all VEL system modules."""
    
    # Core modules that MUST be loaded - ALL 39 modules in the VEL system
    CORE_MODULES = [
        # ═══════════════════════════════════════════════════════════════════
        # ANVEL MODULES (25 total)
        # ═══════════════════════════════════════════════════════════════════
        
        # Event & Communication
        ("anvel_event_bus", "ANVELEventBus", "event_bus"),
        
        # Market Data
        ("anvel_market_data", "ANVELMarketData", "market_data"),
        
        # Broker Stack
        ("anvel_broker_base", "BrokerBase", "broker_base"),
        ("anvel_broker_dex_base", "DEXBrokerBase", "dex_broker_base"),
        ("anvel_broker_factory", "BrokerFactory", "broker_factory"),
        ("anvel_dex_broker_factory", "DEXBrokerFactory", "dex_factory"),
        ("anvel_broker_uniswap", "UniswapV3Broker", "uniswap_broker"),
        ("anvel_broker_pancakeswap", "PancakeSwapBroker", "pancakeswap_broker"),
        
        # Trading Engine
        ("anvel_pooled_trading_engine", "PooledTradingEngine", "pooled_engine"),
        ("anvel_pooled_trading_integration", "IntegratedPooledTradingService", "pooled_service"),
        ("anvel_defi_strategies", "StrategyManager", "strategy_manager"),
        ("anvel_automated_executor", "AutomatedExecutor", "executor"),
        
        # Strategy & Learning  
        ("anvel_strategy_core", "ANVELStrategyCore", "strategy_core"),
        ("anvel_continuous_learning", "ContinuousLearner", "learner"),
        ("anvel_analytics_core", "AnalyticsCore", "analytics"),
        ("anvel_eternal_learning_engine", "EternalLearningEngine", "eternal_learner"),
        
        # Utilities
        ("anvel_dependency_utils", "LazyLoader", "lazy_loader"),
        
        # Monitoring & Safety
        ("anvel_monitoring", "ANVELMonitoring", "monitoring"),
        
        # Web & API
        ("anvel_web_server", "ANVELWebServer", "web_server"),
        ("anvel_watchlist", "WatchlistService", "watchlist"),
        ("anvel_watchlist_service", "WatchlistService", "watchlist_service"),
        
        # Subscription & SaaS
        ("anvel_subscription_manager", "ANVELSubscriptionManager", "subscriptions"),
        ("anvel_referral_system", "ReferralSystem", "referrals"),
        
        # Smart Contracts
        ("anvel_smart_contract_manager", "SmartContractManager", "contracts"),
        ("anvel_hybrid_interfaces", "HybridInterface", "hybrid"),
        
        # ═══════════════════════════════════════════════════════════════════
        # VEL EXECUTION ENGINE MODULES (14 total)
        # ═══════════════════════════════════════════════════════════════════
        
        # Core Execution
        ("vel_execution_core", "ExecutionCore", "execution_core"),
        ("vel_execution_queue", "ExecutionQueue", "exec_queue"),
        
        # Risk & Safety
        ("vel_risk_kernel", "RiskKernel", "risk_kernel"),
        ("vel_circuit_breaker", "CircuitBreakerManager", "circuit_breaker"),
        
        # Transaction Management
        ("vel_signer", "SignerInterface", "signer"),
        ("vel_nonce_manager", "NonceManager", "nonce_manager"),
        ("vel_state_ledger", "StateLedger", "state_ledger"),
        ("vel_transaction_simulator", "TransactionSimulator", "tx_simulator"),
        
        # Token & Registry
        ("vel_token_registry", "TokenRegistry", "token_registry"),
        
        # Protection & Resilience
        ("vel_mev_protection", "MEVProtectionConfig", "mev_protection"),
        ("vel_backpressure", "BackpressureConfig", "backpressure"),
        ("vel_chain_finality", "ChainFinalityTracker", "chain_finality"),
        ("vel_chaos_scenarios", "ChaosEngine", "chaos_runner"),
        ("vel_operational_controls", "OperationalController", "ops_controls"),
        
        # RPC Management
        ("vel_rpc_manager", "RPCManager", "rpc_manager"),
        
        # Configuration
        ("vel_config_validator", "ConfigValidator", "config_validator"),
    ]
    
    def __init__(self):
        self.modules: Dict[str, Any] = {}
        self.failed: List[str] = []
    
    def load_module(self, module_name: str, class_name: str, alias: str) -> Optional[Any]:
        """Load a single module and instantiate its main class."""
        try:
            import importlib
            mod = importlib.import_module(module_name)
            
            # Try to get the class
            if hasattr(mod, class_name):
                cls = getattr(mod, class_name)
                # Store class reference (instantiation happens in wire())
                self.modules[alias] = {"module": mod, "class": cls, "instance": None}
                logger.debug(f"Loaded {module_name}.{class_name} as '{alias}'")
                return cls
            else:
                # Module exists but class doesn't - store module anyway
                self.modules[alias] = {"module": mod, "class": None, "instance": None}
                logger.debug(f"Loaded {module_name} (class {class_name} not found)")
                return mod
                
        except ImportError as e:
            logger.warning(f"Could not import {module_name}: {e}")
            self.failed.append(module_name)
            return None
        except Exception as e:
            logger.warning(f"Error loading {module_name}: {e}")
            self.failed.append(module_name)
            return None
    
    def load_all(self) -> int:
        """Load all core modules."""
        logger.info("Loading VEL system modules...")
        loaded = 0
        
        for module_name, class_name, alias in self.CORE_MODULES:
            if self.load_module(module_name, class_name, alias):
                loaded += 1
        
        logger.info(f"Loaded {loaded}/{len(self.CORE_MODULES)} modules ({len(self.failed)} failed)")
        return loaded
    
    def get(self, alias: str) -> Optional[Any]:
        """Get a loaded module by alias."""
        entry = self.modules.get(alias)
        if entry:
            return entry.get("instance") or entry.get("class") or entry.get("module")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM WIRING
# ═══════════════════════════════════════════════════════════════════════════════

class SystemWiring:
    """Wires all modules together."""
    
    def __init__(self, registry: ModuleRegistry, config: SystemConfig):
        self.registry = registry
        self.config = config
        self.instances: Dict[str, Any] = {}
    
    @property
    def wired_instances(self) -> Dict[str, Any]:
        """Alias for instances for compatibility."""
        return self.instances
    
    def wire(self) -> bool:
        """Wire all modules together."""
        logger.info("Wiring system components...")
        
        try:
            # 1. Event Bus (foundation)
            self._init_event_bus()
            
            # 2. Token Registry
            self._init_token_registry()
            
            # 3. DEX Factory & Brokers
            self._init_brokers()
            
            # 4. Risk & Execution
            self._init_execution()
            
            # 5. Trading Engine
            self._init_trading()
            
            # 6. Monitoring
            self._init_monitoring()
            
            # 7. Web Server (optional)
            self._init_web()
            
            logger.info("System wiring complete")
            return True
            
        except Exception as e:
            logger.error(f"Wiring failed: {e}")
            return False
    
    def _init_event_bus(self):
        """Initialize event bus."""
        entry = self.registry.modules.get("event_bus")
        if entry and entry.get("class"):
            self.instances["event_bus"] = entry["class"]()
            logger.info("✓ Event bus initialized")
    
    def _init_token_registry(self):
        """Initialize token registry."""
        entry = self.registry.modules.get("token_registry")
        if entry and entry.get("module"):
            mod = entry["module"]
            if hasattr(mod, "get_token_registry"):
                self.instances["token_registry"] = mod.get_token_registry()
                logger.info("✓ Token registry initialized")
    
    def _init_brokers(self):
        """Initialize DEX factory and brokers."""
        entry = self.registry.modules.get("dex_factory")
        if entry and entry.get("module"):
            mod = entry["module"]
            if hasattr(mod, "get_dex_factory"):
                self.instances["dex_factory"] = mod.get_dex_factory()
                logger.info("✓ DEX factory initialized")
    
    def _init_execution(self):
        """Initialize execution engine."""
        # Risk kernel
        entry = self.registry.modules.get("risk_kernel")
        if entry and entry.get("class"):
            try:
                self.instances["risk_kernel"] = entry["class"]()
                logger.info("✓ Risk kernel initialized")
            except:
                pass
        
        # Circuit breaker
        entry = self.registry.modules.get("circuit_breaker")
        if entry and entry.get("class"):
            try:
                self.instances["circuit_breaker"] = entry["class"]()
                logger.info("✓ Circuit breaker initialized")
            except:
                pass
    
    def _init_trading(self):
        """Initialize trading components."""
        # Strategy manager
        entry = self.registry.modules.get("strategy_manager")
        if entry and entry.get("module"):
            mod = entry["module"]
            if hasattr(mod, "create_default_strategy_manager"):
                try:
                    self.instances["strategy_manager"] = mod.create_default_strategy_manager()
                    logger.info("✓ Strategy manager initialized")
                except:
                    pass
    
    def _init_monitoring(self):
        """Initialize monitoring."""
        entry = self.registry.modules.get("monitoring")
        if entry and entry.get("class"):
            try:
                self.instances["monitoring"] = entry["class"]()
                logger.info("✓ Monitoring initialized")
            except:
                pass
    
    def _init_web(self):
        """Initialize web server (lazy)."""
        entry = self.registry.modules.get("web_server")
        if entry and entry.get("module"):
            mod = entry["module"]
            if hasattr(mod, "get_anvel_server"):
                # Don't start yet, just register
                self.instances["web_server_factory"] = mod.get_anvel_server
                logger.info("✓ Web server registered (not started)")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

class VELSystem:
    """Main VEL Trading System."""
    
    def __init__(self):
        self.config = SystemConfig()
        self.registry = ModuleRegistry()
        self.wiring = SystemWiring(self.registry, self.config)
        self.running = False
        self._shutdown_event = threading.Event()
    
    def initialize(self) -> bool:
        """Initialize the entire system."""
        print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                        VEL TRADING SYSTEM v{VERSION}                           ║
║                     Unified Entry Point - All Modules                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
        """)
        
        logger.info(f"Initializing {SYSTEM_NAME} v{VERSION}...")
        
        # Load all modules
        loaded = self.registry.load_all()
        if loaded == 0:
            logger.error("No modules loaded!")
            return False
        
        # Wire modules together
        if not self.wiring.wire():
            logger.error("System wiring failed!")
            return False
        
        logger.info("=" * 60)
        logger.info("SYSTEM INITIALIZATION COMPLETE")
        logger.info("=" * 60)
        
        # Print status
        self._print_status()
        
        return True
    
    def _print_status(self):
        """Print system status."""
        print("\n" + "=" * 60)
        print("LOADED MODULES:")
        print("=" * 60)
        
        for alias, entry in self.registry.modules.items():
            status = "✓" if entry.get("class") or entry.get("module") else "✗"
            print(f"  {status} {alias}")
        
        if self.registry.failed:
            print("\nFAILED MODULES:")
            for mod in self.registry.failed:
                print(f"  ✗ {mod}")
        
        print("\n" + "=" * 60)
        print(f"WIRED INSTANCES: {len(self.wiring.instances)}")
        print("=" * 60)
        for name in self.wiring.instances:
            print(f"  ✓ {name}")
        print()
    
    def wire(self) -> bool:
        """Convenience method to re-wire the system."""
        return self.wiring.wire()
    
    def start(self):
        """Start the system."""
        if not self.running:
            self.running = True
            logger.info("VEL System started")
            
            # Start web server if available
            web_factory = self.wiring.instances.get("web_server_factory")
            if web_factory:
                try:
                    server = web_factory()
                    logger.info("Web server available at http://localhost:5000")
                except Exception as e:
                    logger.warning(f"Could not start web server: {e}")
    
    def stop(self):
        """Stop the system."""
        if self.running:
            self.running = False
            self._shutdown_event.set()
            logger.info("VEL System stopped")
    
    def wait(self):
        """Wait for shutdown signal."""
        self._shutdown_event.wait()
    
    def run(self):
        """Run the system (blocking)."""
        if not self.initialize():
            sys.exit(1)
        
        self.start()
        
        # Handle shutdown signals
        def signal_handler(sig, frame):
            logger.info("Shutdown signal received")
            self.stop()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        logger.info("System running. Press Ctrl+C to stop.")
        self.wait()


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """Main entry point."""
    system = VELSystem()
    system.run()


if __name__ == "__main__":
    main()
