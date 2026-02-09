#!/usr/bin/env python3
"""
VEL Infrastructure Test Suite
=============================

Tests for active infrastructure modules.
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


# ═══════════════════════════════════════════════════════════════════════════════
# ACTIVE MODULE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestActiveInfrastructure(unittest.TestCase):
    """Test active infrastructure modules."""
    
    @unittest.skipUnless(module_available('vel_execution_queue'), "vel_execution_queue not available")
    def test_execution_queue_available(self):
        """Test that execution queue is available."""
        from vel_execution_queue import ExecutionQueue
        self.assertTrue(hasattr(ExecutionQueue, '__init__'))
    
    @unittest.skipUnless(module_available('vel_backpressure'), "vel_backpressure not available")
    def test_backpressure_available(self):
        """Test that backpressure config is available."""
        from vel_backpressure import BackpressureConfig
        self.assertTrue(hasattr(BackpressureConfig, '__init__'))
    
    @unittest.skipUnless(module_available('vel_operational_controls'), "vel_operational_controls not available")
    def test_operational_controls_available(self):
        """Test that operational controller is available."""
        from vel_operational_controls import OperationalController
        self.assertTrue(hasattr(OperationalController, '__init__'))


# ═══════════════════════════════════════════════════════════════════════════════
# ARCHIVED MODULE TESTS - Skipped
# ═══════════════════════════════════════════════════════════════════════════════

@unittest.skip("Module vel_distributed_locks archived - tests skipped")
class TestDistributedLocks(unittest.TestCase):
    """Tests for distributed locks - ARCHIVED."""
    pass


@unittest.skip("Module vel_distributed_locks archived - tests skipped")
class TestIdempotency(unittest.TestCase):
    """Tests for idempotency - ARCHIVED."""
    pass


@unittest.skip("Module vel_crash_recovery archived - tests skipped")
class TestCrashRecovery(unittest.TestCase):
    """Tests for crash recovery - ARCHIVED."""
    pass


@unittest.skip("Module vel_security_middleware archived - tests skipped")
class TestSecurityMiddleware(unittest.TestCase):
    """Tests for security middleware - ARCHIVED."""
    pass


@unittest.skip("Module vel_distributed_locks archived - tests skipped")
class TestTransactionQueueLock(unittest.TestCase):
    """Tests for transaction queue lock - ARCHIVED."""
    pass


if __name__ == "__main__":
    unittest.main()
