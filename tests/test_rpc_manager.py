#!/usr/bin/env python3
"""
VEL RPC Manager Test Suite
==========================

Tests for the multi-provider RPC manager with health scoring and failover.

Run with: python -m pytest tests/test_rpc_manager.py -v
"""

import sys
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestRPCProviderHealth(unittest.TestCase):
    """Test RPC provider health tracking."""
    
    def test_initial_health_score(self):
        """Health should start at 100."""
        from vel_rpc_manager import ProviderHealth, ProviderStatus
        
        health = ProviderHealth(provider_name="test", chain_id=1)
        
        self.assertEqual(health.health_score, 100.0)
        self.assertEqual(health.status, ProviderStatus.HEALTHY)
        self.assertTrue(health.is_available())
    
    def test_health_update_on_success(self):
        """Health should update after successful request."""
        from vel_rpc_manager import ProviderHealth
        
        health = ProviderHealth(provider_name="test", chain_id=1)
        health.update_success(latency_ms=100.0)
        
        self.assertEqual(health.total_requests, 1)
        self.assertEqual(health.successful_requests, 1)
        self.assertEqual(health.consecutive_failures, 0)
        self.assertIsNotNone(health.last_success_time)
    
    def test_health_degradation_on_failure(self):
        """Health score should decrease after failures."""
        from vel_rpc_manager import ProviderHealth, ProviderStatus, TimeoutCategory
        
        health = ProviderHealth(provider_name="test", chain_id=1)
        
        # Simulate multiple failures
        for i in range(3):
            health.update_failure(f"Error {i}", TimeoutCategory.NETWORK)
        
        self.assertEqual(health.consecutive_failures, 3)
        self.assertLess(health.health_score, 100.0)
        # Health should be degraded or worse
        self.assertNotEqual(health.status, ProviderStatus.HEALTHY)
    
    def test_health_recovery_after_success(self):
        """Health should improve after success following failures."""
        from vel_rpc_manager import ProviderHealth, TimeoutCategory
        
        health = ProviderHealth(provider_name="test", chain_id=1)
        
        # Cause degradation
        health.update_failure("Error", TimeoutCategory.NETWORK)
        health.update_failure("Error", TimeoutCategory.NETWORK)
        
        # Record successful request
        health.update_success(100.0)
        
        self.assertEqual(health.consecutive_failures, 0)
    
    def test_rate_limit_handling(self):
        """Provider should be marked unavailable when rate limited."""
        from vel_rpc_manager import ProviderHealth, TimeoutCategory
        
        health = ProviderHealth(provider_name="test", chain_id=1)
        health.update_failure("Rate limit exceeded", TimeoutCategory.RATE_LIMITED)
        
        self.assertTrue(health.is_rate_limited)


class TestRPCManagerConfiguration(unittest.TestCase):
    """Test RPC manager configuration."""
    
    def test_default_configuration(self):
        """Should use default configuration when none provided."""
        from vel_rpc_manager import RPCManager, RPCManagerConfig
        
        manager = RPCManager()
        
        self.assertIsNotNone(manager.config)
        self.assertEqual(manager.config.max_failover_attempts, 5)
    
    def test_custom_configuration(self):
        """Should use custom configuration when provided."""
        from vel_rpc_manager import RPCManager, RPCManagerConfig
        
        config = RPCManagerConfig(max_failover_attempts=10)
        manager = RPCManager(config=config)
        
        self.assertEqual(manager.config.max_failover_attempts, 10)


class TestRPCProviderRegistration(unittest.TestCase):
    """Test provider registration."""
    
    def test_register_single_provider(self):
        """Should register a single provider."""
        from vel_rpc_manager import RPCManager, RPCProviderConfig
        
        manager = RPCManager()
        provider = RPCProviderConfig(
            name="test_provider",
            url="http://localhost:8545",
            chain_id=1
        )
        
        manager.register_provider(provider)
        
        status = manager.get_chain_status(1)
        self.assertEqual(status["provider_count"], 1)
        self.assertEqual(status["providers"][0]["name"], "test_provider")
    
    def test_register_multiple_providers_same_chain(self):
        """Should register multiple providers for the same chain."""
        from vel_rpc_manager import RPCManager, RPCProviderConfig
        
        manager = RPCManager()
        
        provider1 = RPCProviderConfig(
            name="primary",
            url="http://localhost:8545",
            chain_id=1,
            is_primary=True
        )
        provider2 = RPCProviderConfig(
            name="backup",
            url="http://localhost:8546",
            chain_id=1
        )
        
        manager.register_provider(provider1)
        manager.register_provider(provider2)
        
        status = manager.get_chain_status(1)
        self.assertEqual(status["provider_count"], 2)
    
    def test_register_default_providers(self):
        """Should register default providers from chain config."""
        from vel_rpc_manager import RPCManager
        
        manager = RPCManager()
        manager.register_default_providers()
        
        # Should have registered providers for supported chains
        status = manager.get_chain_status(1)  # Ethereum
        self.assertGreater(status["provider_count"], 0)


class TestRPCProviderSelection(unittest.TestCase):
    """Test provider selection logic."""
    
    def test_select_primary_provider(self):
        """Should prefer primary provider when healthy."""
        from vel_rpc_manager import RPCManager, RPCProviderConfig
        
        manager = RPCManager()
        
        manager.register_provider(RPCProviderConfig(
            name="backup", url="http://backup:8545", chain_id=1, priority=5
        ))
        manager.register_provider(RPCProviderConfig(
            name="primary", url="http://primary:8545", chain_id=1, 
            priority=5, is_primary=True
        ))
        
        selected = manager._select_provider(1)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "primary")
    
    def test_select_higher_priority_provider(self):
        """Should prefer higher priority when no primary."""
        from vel_rpc_manager import RPCManager, RPCProviderConfig
        
        manager = RPCManager()
        
        manager.register_provider(RPCProviderConfig(
            name="low_priority", url="http://low:8545", chain_id=1, priority=3
        ))
        manager.register_provider(RPCProviderConfig(
            name="high_priority", url="http://high:8545", chain_id=1, priority=8
        ))
        
        selected = manager._select_provider(1)
        self.assertEqual(selected.name, "high_priority")


class TestRPCTimeoutClassification(unittest.TestCase):
    """Test timeout error classification."""
    
    def test_classify_rate_limit(self):
        """Should classify rate limit errors correctly."""
        from vel_rpc_manager import RPCManager, TimeoutCategory
        
        manager = RPCManager()
        
        error = Exception("429 Too Many Requests")
        category = manager._classify_timeout(error)
        
        self.assertEqual(category, TimeoutCategory.RATE_LIMITED)
    
    def test_classify_network_timeout(self):
        """Should classify network timeouts correctly."""
        from vel_rpc_manager import RPCManager, TimeoutCategory
        
        manager = RPCManager()
        
        error = Exception("Connection timed out")
        category = manager._classify_timeout(error)
        
        self.assertEqual(category, TimeoutCategory.NETWORK)
    
    def test_classify_unknown_error(self):
        """Should classify unknown errors correctly."""
        from vel_rpc_manager import RPCManager, TimeoutCategory
        
        manager = RPCManager()
        
        error = Exception("Some random error")
        category = manager._classify_timeout(error)
        
        self.assertEqual(category, TimeoutCategory.UNKNOWN)


class TestRPCChainStatus(unittest.TestCase):
    """Test chain status reporting."""
    
    def test_chain_status_structure(self):
        """Should return properly structured status."""
        from vel_rpc_manager import RPCManager, RPCProviderConfig
        
        manager = RPCManager()
        manager.register_provider(RPCProviderConfig(
            name="test", url="http://test:8545", chain_id=1
        ))
        
        status = manager.get_chain_status(1)
        
        self.assertIn("chain_id", status)
        self.assertIn("provider_count", status)
        self.assertIn("providers", status)
        self.assertIn("chain_health_score", status)
    
    def test_empty_chain_status(self):
        """Should handle chain with no providers."""
        from vel_rpc_manager import RPCManager
        
        manager = RPCManager()
        
        status = manager.get_chain_status(999)  # Non-existent chain
        
        self.assertEqual(status["provider_count"], 0)
        self.assertEqual(status["chain_health_score"], 0.0)


class TestRPCGlobalInstance(unittest.TestCase):
    """Test global RPC manager instance."""
    
    def test_get_global_manager(self):
        """Should return consistent global manager."""
        from vel_rpc_manager import get_rpc_manager
        
        manager1 = get_rpc_manager()
        manager2 = get_rpc_manager()
        
        self.assertIs(manager1, manager2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
