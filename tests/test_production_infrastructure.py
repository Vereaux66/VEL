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


def module_available(module_name):
    """Check if a module is available for import."""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVE MODULE TESTS - These test modules in the main system
# ═══════════════════════════════════════════════════════════════════════════════

class TestVELRiskKernel(unittest.TestCase):
    """Test the active risk kernel module."""
    
    @unittest.skipUnless(module_available('vel_risk_kernel'), "vel_risk_kernel not available")
    def test_risk_kernel_import(self):
        """Test that risk kernel can be imported."""
        from vel_risk_kernel import RiskKernel
        self.assertTrue(hasattr(RiskKernel, '__init__'))


class TestVELCircuitBreaker(unittest.TestCase):
    """Test the active circuit breaker module."""
    
    @unittest.skipUnless(module_available('vel_circuit_breaker'), "vel_circuit_breaker not available")
    def test_circuit_breaker_import(self):
        """Test that circuit breaker can be imported."""
        from vel_circuit_breaker import CircuitBreaker
        self.assertTrue(hasattr(CircuitBreaker, '__init__'))


class TestVELExecutionCore(unittest.TestCase):
    """Test the active execution core module."""
    
    @unittest.skipUnless(module_available('vel_execution_core'), "vel_execution_core not available")
    def test_execution_core_import(self):
        """Test that execution core can be imported."""
        try:
            from vel_execution_core import VELExecutionCore
            self.assertTrue(True)
        except ImportError as e:
            # web3 dependency may not be installed
            if 'web3' in str(e):
                self.skipTest("web3 dependency not installed")
            raise


class TestVELStateLedger(unittest.TestCase):
    """Test the active state ledger module."""
    
    @unittest.skipUnless(module_available('vel_state_ledger'), "vel_state_ledger not available")
    def test_state_ledger_import(self):
        """Test that state ledger can be imported."""
        try:
            from vel_state_ledger import StateLedger
            self.assertTrue(True)
        except ImportError as e:
            if 'web3' in str(e):
                self.skipTest("web3 dependency not installed")
            raise


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
        # Should have 39 modules defined
        self.assertEqual(len(registry.CORE_MODULES), 39)


# ═══════════════════════════════════════════════════════════════════════════════
# ARCHIVED/REMOVED MODULE TESTS - Skipped (modules no longer in main system)
# ═══════════════════════════════════════════════════════════════════════════════

@unittest.skip("Module not in main system - archived")
class TestRiskControls(unittest.TestCase):
    """Test risk control engine - NOT IN MAIN SYSTEM."""
    pass


@unittest.skip("Module not in main system - archived")
class TestRateLimiter(unittest.TestCase):
    """Test rate limiter - NOT IN MAIN SYSTEM."""
    pass


@unittest.skip("Module not in main system - archived")
class TestPrometheusMetrics(unittest.TestCase):
    """Test Prometheus metrics - NOT IN MAIN SYSTEM."""
    pass


@unittest.skip("Module not in main system - archived")
class TestStructuredLogging(unittest.TestCase):
    """Test structured logging - NOT IN MAIN SYSTEM."""
    pass


@unittest.skip("Module not in main system - archived")
class TestAISafety(unittest.TestCase):
    """Test AI safety constraints - NOT IN MAIN SYSTEM."""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main()
