#!/usr/bin/env python3
"""
VEL Security Test Suite
=======================

Tests for security-related modules.
"""

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestMEVProtection(unittest.TestCase):
    """Test that MEV protection is available."""
    
    def test_mev_protection_available(self):
        """Test that MEV protection config is available."""
        from vel_mev_protection import MEVProtectionConfig
        self.assertTrue(hasattr(MEVProtectionConfig, '__init__'))
    
    def test_mev_protection_defaults(self):
        """Test MEV protection default configuration."""
        from vel_mev_protection import MEVProtectionConfig
        config = MEVProtectionConfig()
        self.assertIsNotNone(config)


class TestRiskKernel(unittest.TestCase):
    """Test that risk kernel is available."""
    
    def test_risk_kernel_available(self):
        """Test that risk kernel is available."""
        from vel_risk_kernel import RiskKernel
        self.assertTrue(hasattr(RiskKernel, '__init__'))
    
    def test_risk_kernel_instantiate(self):
        """Test risk kernel instantiation."""
        from vel_risk_kernel import RiskKernel
        kernel = RiskKernel()
        self.assertIsNotNone(kernel)


class TestCircuitBreaker(unittest.TestCase):
    """Test that circuit breaker is available."""
    
    def test_circuit_breaker_available(self):
        """Test circuit breaker manager is available."""
        from vel_circuit_breaker import CircuitBreakerManager
        self.assertTrue(hasattr(CircuitBreakerManager, '__init__'))


class TestOperationalControls(unittest.TestCase):
    """Test operational controls."""
    
    def test_operational_controls_available(self):
        """Test operational controller is available."""
        from vel_operational_controls import OperationalController
        self.assertTrue(hasattr(OperationalController, '__init__'))


if __name__ == "__main__":
    unittest.main()
