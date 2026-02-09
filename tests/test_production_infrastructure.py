#!/usr/bin/env python3
"""
VEL Production Infrastructure Test Suite
=========================================

Tests for production-grade modules in the main system.

Run with: python -m pytest tests/test_production_infrastructure.py -v
"""

import json
import logging
import sys
import time
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVE MODULE TESTS - These test modules in the main system
# ═══════════════════════════════════════════════════════════════════════════════

class TestVELRiskKernel(unittest.TestCase):
    """Test the active risk kernel module."""
    
    def test_risk_kernel_import(self):
        """Test that risk kernel can be imported."""
        from vel_risk_kernel import RiskKernel
        self.assertTrue(hasattr(RiskKernel, '__init__'))


class TestVELCircuitBreaker(unittest.TestCase):
    """Test the active circuit breaker module."""
    
    def test_circuit_breaker_import(self):
        """Test that circuit breaker can be imported."""
        from vel_circuit_breaker import CircuitBreakerManager
        self.assertTrue(hasattr(CircuitBreakerManager, '__init__'))


class TestVELExecutionQueue(unittest.TestCase):
    """Test the active execution queue module."""
    
    def test_execution_queue_import(self):
        """Test that execution queue can be imported."""
        from vel_execution_queue import ExecutionQueue
        self.assertTrue(hasattr(ExecutionQueue, '__init__'))


class TestVELBackpressure(unittest.TestCase):
    """Test the active backpressure module."""
    
    def test_backpressure_import(self):
        """Test that backpressure config can be imported."""
        from vel_backpressure import BackpressureConfig
        self.assertTrue(hasattr(BackpressureConfig, '__init__'))


class TestVELChaosScenarios(unittest.TestCase):
    """Test the active chaos scenarios module."""
    
    def test_chaos_scenarios_import(self):
        """Test that chaos engine can be imported."""
        from vel_chaos_scenarios import ChaosEngine
        self.assertTrue(hasattr(ChaosEngine, '__init__'))


class TestVELMain(unittest.TestCase):
    """Test the unified entry point."""
    
    def test_vel_main_import(self):
        """Test that vel_main can be imported."""
        from vel_main import VELSystem, ModuleRegistry, SystemConfig
        self.assertTrue(hasattr(VELSystem, 'initialize'))
        self.assertTrue(hasattr(ModuleRegistry, 'CORE_MODULES'))
    
    def test_module_registry_count(self):
        """Test that module registry has expected modules."""
        from vel_main import ModuleRegistry
        registry = ModuleRegistry()
        # Should have 41 modules defined (updated count)
        self.assertEqual(len(registry.CORE_MODULES), 41)


class TestANVELEventBus(unittest.TestCase):
    """Test the event bus module."""
    
    def test_event_bus_import(self):
        """Test that event bus can be imported."""
        from anvel_event_bus import ANVELEventBus
        self.assertTrue(hasattr(ANVELEventBus, '__init__'))


class TestANVELBrokerBase(unittest.TestCase):
    """Test the broker base module."""
    
    def test_broker_base_import(self):
        """Test that broker base can be imported."""
        from anvel_broker_base import BrokerBase
        self.assertTrue(hasattr(BrokerBase, '__init__'))


class TestANVELDexBrokerFactory(unittest.TestCase):
    """Test the dex broker factory module."""
    
    def test_dex_broker_factory_import(self):
        """Test that dex broker factory can be imported."""
        from anvel_dex_broker_factory import DEXBrokerFactory
        self.assertTrue(hasattr(DEXBrokerFactory, '__init__'))


class TestVELConfigValidator(unittest.TestCase):
    """Test the config validator module."""
    
    def test_config_validator_import(self):
        """Test that config validator can be imported."""
        from vel_config_validator import ConfigValidator
        self.assertTrue(hasattr(ConfigValidator, '__init__'))


class TestVELRPCManager(unittest.TestCase):
    """Test the RPC manager module."""
    
    def test_rpc_manager_import(self):
        """Test that RPC manager can be imported."""
        from vel_rpc_manager import RPCManager
        self.assertTrue(hasattr(RPCManager, '__init__'))


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
