#!/usr/bin/env python3
"""
Tests for VEL Connection Hardening Module
==========================================

Comprehensive tests for connection hardening, validation, and management.
"""

import threading
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from vel_connection_hardening import (
    ConnectionConfig,
    ConnectionHealth,
    ConnectionManager,
    ConnectionState,
    ConnectionType,
    ConnectionValidator,
    ManagedConnection,
    get_connection_manager,
    harden_connection_config,
    reset_connection_manager,
    validate_endpoint_security,
)


class MockManagedConnection(ManagedConnection):
    """Mock implementation of ManagedConnection for testing."""
    
    def __init__(self, config: ConnectionConfig, fail_connect: bool = False, fail_health: bool = False):
        super().__init__(config)
        self.fail_connect = fail_connect
        self.fail_health = fail_health
        self.connect_count = 0
        self.disconnect_count = 0
        self.health_check_count = 0
    
    def _do_connect(self) -> bool:
        self.connect_count += 1
        if self.fail_connect:
            raise ConnectionError("Mock connection failure")
        return True
    
    def _do_disconnect(self) -> None:
        self.disconnect_count += 1
    
    def _do_health_check(self) -> bool:
        self.health_check_count += 1
        return not self.fail_health


class TestConnectionHealth(unittest.TestCase):
    """Tests for ConnectionHealth dataclass."""
    
    def test_initial_state(self):
        """Test initial health state."""
        health = ConnectionHealth(
            connection_id="test-1",
            connection_type=ConnectionType.DATABASE,
            state=ConnectionState.DISCONNECTED
        )
        self.assertEqual(health.success_rate(), 1.0)
        self.assertFalse(health.is_healthy())
    
    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        health = ConnectionHealth(
            connection_id="test-1",
            connection_type=ConnectionType.API,
            state=ConnectionState.CONNECTED,
            total_requests=100,
            successful_requests=95
        )
        self.assertEqual(health.success_rate(), 0.95)
    
    def test_is_healthy_requirements(self):
        """Test healthy status requirements."""
        health = ConnectionHealth(
            connection_id="test-1",
            connection_type=ConnectionType.RPC,
            state=ConnectionState.CONNECTED,
            total_requests=100,
            successful_requests=96,
            consecutive_failures=0
        )
        self.assertTrue(health.is_healthy())
        
        # Not healthy if not connected
        health.state = ConnectionState.DISCONNECTED
        self.assertFalse(health.is_healthy())
        
        # Not healthy with too many failures
        health.state = ConnectionState.CONNECTED
        health.consecutive_failures = 5
        self.assertFalse(health.is_healthy())
        
        # Not healthy with low success rate
        health.consecutive_failures = 0
        health.successful_requests = 90
        self.assertFalse(health.is_healthy())


class TestConnectionValidator(unittest.TestCase):
    """Tests for ConnectionValidator."""
    
    def test_successful_validation(self):
        """Test successful connection validation."""
        config = ConnectionConfig(
            name="test",
            connection_type=ConnectionType.API,
            endpoint="https://api.example.com"
        )
        
        is_valid, message, latency = ConnectionValidator.validate_connection(
            config, lambda: True
        )
        
        self.assertTrue(is_valid)
        self.assertIn("successfully", message)
        self.assertGreater(latency, 0)
    
    def test_failed_validation(self):
        """Test failed connection validation."""
        config = ConnectionConfig(
            name="test",
            connection_type=ConnectionType.API,
            endpoint="https://api.example.com"
        )
        
        is_valid, message, latency = ConnectionValidator.validate_connection(
            config, lambda: False
        )
        
        self.assertFalse(is_valid)
        self.assertIn("False", message)
    
    def test_validation_with_exception(self):
        """Test validation when test function raises exception."""
        config = ConnectionConfig(
            name="test",
            connection_type=ConnectionType.API,
            endpoint="https://api.example.com"
        )
        
        def raise_error():
            raise RuntimeError("Test error")
        
        is_valid, message, latency = ConnectionValidator.validate_connection(
            config, raise_error
        )
        
        self.assertFalse(is_valid)
        self.assertIn("error", message.lower())


class TestManagedConnection(unittest.TestCase):
    """Tests for ManagedConnection."""
    
    def test_successful_connect(self):
        """Test successful connection."""
        config = ConnectionConfig(
            name="test",
            connection_type=ConnectionType.DATABASE,
            endpoint="localhost:5432"
        )
        conn = MockManagedConnection(config)
        
        result = conn.connect()
        
        self.assertTrue(result)
        self.assertEqual(conn.health.state, ConnectionState.CONNECTED)
        self.assertEqual(conn.connect_count, 1)
    
    def test_failed_connect(self):
        """Test failed connection."""
        config = ConnectionConfig(
            name="test",
            connection_type=ConnectionType.DATABASE,
            endpoint="localhost:5432",
            auto_reconnect=False
        )
        conn = MockManagedConnection(config, fail_connect=True)
        
        result = conn.connect()
        
        self.assertFalse(result)
        self.assertEqual(conn.health.state, ConnectionState.FAILED)
        self.assertEqual(conn.health.failure_count, 1)
    
    def test_disconnect(self):
        """Test disconnection."""
        config = ConnectionConfig(
            name="test",
            connection_type=ConnectionType.DATABASE,
            endpoint="localhost:5432"
        )
        conn = MockManagedConnection(config)
        conn.connect()
        
        conn.disconnect()
        
        self.assertEqual(conn.health.state, ConnectionState.DISCONNECTED)
        self.assertEqual(conn.disconnect_count, 1)
    
    def test_already_connected(self):
        """Test connecting when already connected."""
        config = ConnectionConfig(
            name="test",
            connection_type=ConnectionType.DATABASE,
            endpoint="localhost:5432"
        )
        conn = MockManagedConnection(config)
        
        conn.connect()
        result = conn.connect()  # Try to connect again
        
        self.assertTrue(result)
        self.assertEqual(conn.connect_count, 1)  # Should not reconnect


class TestConnectionManager(unittest.TestCase):
    """Tests for ConnectionManager."""
    
    def setUp(self):
        """Set up test fixtures."""
        reset_connection_manager()
        self.manager = ConnectionManager()
    
    def tearDown(self):
        """Clean up after tests."""
        self.manager.disconnect_all()
        reset_connection_manager()
    
    def test_register_connection(self):
        """Test registering a connection."""
        config = ConnectionConfig(
            name="test-db",
            connection_type=ConnectionType.DATABASE,
            endpoint="localhost:5432"
        )
        conn = MockManagedConnection(config)
        
        self.manager.register(conn)
        
        self.assertIsNotNone(self.manager.get_connection("test-db"))
    
    def test_unregister_connection(self):
        """Test unregistering a connection."""
        config = ConnectionConfig(
            name="test-db",
            connection_type=ConnectionType.DATABASE,
            endpoint="localhost:5432"
        )
        conn = MockManagedConnection(config)
        
        self.manager.register(conn)
        self.manager.unregister("test-db")
        
        self.assertIsNone(self.manager.get_connection("test-db"))
    
    def test_connect_all(self):
        """Test connecting all registered connections."""
        configs = [
            ConnectionConfig(name="db", connection_type=ConnectionType.DATABASE, endpoint="localhost:5432"),
            ConnectionConfig(name="redis", connection_type=ConnectionType.REDIS, endpoint="localhost:6379"),
        ]
        
        for config in configs:
            self.manager.register(MockManagedConnection(config))
        
        successful, total = self.manager.connect_all()
        
        self.assertEqual(successful, 2)
        self.assertEqual(total, 2)
    
    def test_health_summary(self):
        """Test health summary generation."""
        config = ConnectionConfig(
            name="test",
            connection_type=ConnectionType.API,
            endpoint="https://api.example.com"
        )
        conn = MockManagedConnection(config)
        self.manager.register(conn)
        conn.connect()
        
        summary = self.manager.get_health_summary()
        
        self.assertEqual(summary["total_connections"], 1)
        self.assertEqual(summary["healthy"], 1)
        self.assertIn("test", summary["connections"])
    
    def test_wire_up_verification(self):
        """Test wire-up verification."""
        config = ConnectionConfig(
            name="test",
            connection_type=ConnectionType.DATABASE,
            endpoint="localhost:5432"
        )
        conn = MockManagedConnection(config)
        self.manager.register(conn)
        conn.connect()
        
        verified, issues = self.manager.verify_wire_up()
        
        self.assertTrue(verified)
        self.assertEqual(len(issues), 0)
        self.assertIsNotNone(self.manager.get_wire_up_hash())
    
    def test_wire_up_verification_fails_when_disconnected(self):
        """Test wire-up verification fails for disconnected connections."""
        config = ConnectionConfig(
            name="test",
            connection_type=ConnectionType.DATABASE,
            endpoint="localhost:5432"
        )
        conn = MockManagedConnection(config)
        self.manager.register(conn)
        # Don't connect
        
        verified, issues = self.manager.verify_wire_up()
        
        self.assertFalse(verified)
        self.assertGreater(len(issues), 0)


class TestSecurityHardening(unittest.TestCase):
    """Tests for security hardening functions."""
    
    def test_harden_connection_config_minimum_timeout(self):
        """Test minimum timeout enforcement."""
        config = ConnectionConfig(
            name="test",
            connection_type=ConnectionType.API,
            endpoint="https://api.example.com",
            timeout_seconds=1.0  # Too low
        )
        
        hardened = harden_connection_config(config)
        
        self.assertGreaterEqual(hardened.timeout_seconds, 5.0)
        self.assertTrue(hardened.metadata.get("hardened"))
    
    def test_harden_connection_config_maximum_timeout(self):
        """Test maximum timeout enforcement."""
        config = ConnectionConfig(
            name="test",
            connection_type=ConnectionType.API,
            endpoint="https://api.example.com",
            timeout_seconds=300.0  # Too high
        )
        
        hardened = harden_connection_config(config)
        
        self.assertLessEqual(hardened.timeout_seconds, 120.0)
    
    def test_validate_endpoint_security_api(self):
        """Test API endpoint security validation."""
        # HTTPS should pass
        is_secure, _ = validate_endpoint_security(
            "https://api.example.com", ConnectionType.API
        )
        self.assertTrue(is_secure)
        
        # HTTP should fail (except localhost)
        is_secure, _ = validate_endpoint_security(
            "http://api.example.com", ConnectionType.API
        )
        self.assertFalse(is_secure)
        
        # Localhost HTTP is OK
        is_secure, _ = validate_endpoint_security(
            "http://localhost:8080", ConnectionType.API
        )
        self.assertTrue(is_secure)
    
    def test_validate_endpoint_security_websocket(self):
        """Test WebSocket endpoint security validation."""
        # WSS should pass
        is_secure, _ = validate_endpoint_security(
            "wss://ws.example.com", ConnectionType.WEBSOCKET
        )
        self.assertTrue(is_secure)
        
        # WS should fail (except localhost)
        is_secure, _ = validate_endpoint_security(
            "ws://ws.example.com", ConnectionType.WEBSOCKET
        )
        self.assertFalse(is_secure)
    
    def test_validate_endpoint_security_rpc(self):
        """Test RPC endpoint security validation."""
        # HTTP/HTTPS should pass
        is_secure, _ = validate_endpoint_security(
            "https://rpc.example.com", ConnectionType.RPC
        )
        self.assertTrue(is_secure)
        
        # Invalid format should fail
        is_secure, _ = validate_endpoint_security(
            "rpc.example.com", ConnectionType.RPC
        )
        self.assertFalse(is_secure)


class TestGlobalConnectionManager(unittest.TestCase):
    """Tests for global connection manager."""
    
    def tearDown(self):
        """Clean up after tests."""
        reset_connection_manager()
    
    def test_get_connection_manager_singleton(self):
        """Test that get_connection_manager returns singleton."""
        manager1 = get_connection_manager()
        manager2 = get_connection_manager()
        
        self.assertIs(manager1, manager2)
    
    def test_reset_connection_manager(self):
        """Test resetting the global connection manager."""
        manager1 = get_connection_manager()
        reset_connection_manager()
        manager2 = get_connection_manager()
        
        self.assertIsNot(manager1, manager2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
