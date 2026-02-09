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


def module_available(module_name):
    """Check if a module is available for import."""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


class TestSecurityModulesAvailable(unittest.TestCase):
    """Test that security modules are available."""
    
    @unittest.skipUnless(module_available('vel_signer'), "vel_signer not available")
    def test_signer_available(self):
        """Test that transaction signer is available."""
        from vel_signer import SignerInterface
        self.assertTrue(hasattr(SignerInterface, '__init__'))
    
    @unittest.skipUnless(module_available('vel_mev_protection'), "vel_mev_protection not available")
    def test_mev_protection_available(self):
        """Test that MEV protection is available."""
        from vel_mev_protection import MEVProtectionConfig
        self.assertTrue(hasattr(MEVProtectionConfig, '__init__'))
    
    @unittest.skipUnless(module_available('vel_risk_kernel'), "vel_risk_kernel not available")
    def test_risk_kernel_available(self):
        """Test that risk kernel is available."""
        from vel_risk_kernel import RiskKernel
        self.assertTrue(hasattr(RiskKernel, '__init__'))


# ═══════════════════════════════════════════════════════════════════════════════
# ARCHIVED MODULE TESTS - Skipped (modules moved to VEL-ARC)
# ═══════════════════════════════════════════════════════════════════════════════

@unittest.skip("Module not in main system - archived")
class TestVELSecurityCore(unittest.TestCase):
    """Test VEL security core - ARCHIVED."""
    pass


@unittest.skip("Module not in main system - archived")  
class TestVELSecurityHardening(unittest.TestCase):
    """Test VEL security hardening - ARCHIVED."""
    pass


if __name__ == "__main__":
    unittest.main()
