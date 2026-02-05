#!/usr/bin/env python3
"""
ANVEL Production Readiness Test Suite
======================================

Run with: python -m pytest tests/test_production_readiness.py -v
"""

import os
import sys
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestConfigLoader(unittest.TestCase):
    """Test configuration loading."""
    
    def test_config_loader_initialization(self):
        from runtime.config_loader import ConfigLoader
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = ConfigLoader(config_dir=Path(tmpdir))
            loader.load_all()
            system = loader.get("system")
            self.assertIn("log_level", system)
    
    def test_config_env_override(self):
        from runtime.config_loader import ConfigLoader
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["ANVEL_SYSTEM_LOG_LEVEL"] = "DEBUG"
            try:
                loader = ConfigLoader(config_dir=Path(tmpdir))
                loader.load_all()
                system = loader.get("system")
                self.assertEqual(system.get("log_level"), "DEBUG")
            finally:
                del os.environ["ANVEL_SYSTEM_LOG_LEVEL"]


class TestSecretsManager(unittest.TestCase):
    """Test secrets management."""
    
    def test_secrets_from_environment(self):
        from runtime.secrets import SecretsManager
        os.environ["ANVEL_TEST_SECRET"] = "test_value"
        try:
            manager = SecretsManager()
            manager.load_all()
            value = manager.get("TEST_SECRET")
            self.assertEqual(value, "test_value")
        finally:
            del os.environ["ANVEL_TEST_SECRET"]
    
    def test_require_missing_raises(self):
        from runtime.secrets import SecretsManager
        manager = SecretsManager()
        manager.load_all()
        with self.assertRaises(ValueError):
            manager.require("NONEXISTENT_SECRET_12345")


class TestServiceRegistry(unittest.TestCase):
    """Test service registry."""
    
    def test_service_registration(self):
        from runtime.service_registry import ServiceRegistry
        registry = ServiceRegistry()
        registry.register("test_service", lambda: "instance")
        services = registry.list_services()
        self.assertEqual(len(services), 1)
    
    def test_dependency_order(self):
        from runtime.service_registry import ServiceRegistry
        order = []
        registry = ServiceRegistry()
        registry.register("a", lambda: order.append("a") or "a")
        registry.register("b", lambda: order.append("b") or "b", dependencies=["a"])
        registry.register("c", lambda: order.append("c") or "c", dependencies=["b"])
        registry.start_all()
        self.assertEqual(order, ["a", "b", "c"])
    
    def test_circular_dependency(self):
        from runtime.service_registry import ServiceRegistry
        registry = ServiceRegistry()
        registry.register("a", lambda: "a", dependencies=["b"])
        registry.register("b", lambda: "b", dependencies=["a"])
        # Circular dependency causes empty results (no services started)
        results = registry.start_all()
        self.assertEqual(len(results), 0)  # Nothing started due to circular dep


class TestHealthChecker(unittest.TestCase):
    """Test health checking."""
    
    def test_health_check(self):
        from runtime.health import HealthChecker, HealthStatus
        checker = HealthChecker()
        checker.register("test", lambda: HealthStatus.HEALTHY)
        report = checker.check_now()
        self.assertEqual(report.overall_status, HealthStatus.HEALTHY)
    
    def test_critical_failure(self):
        from runtime.health import HealthChecker, HealthStatus
        checker = HealthChecker()
        checker.register("crit", lambda: HealthStatus.UNHEALTHY, critical=True)
        report = checker.check_now()
        self.assertEqual(report.overall_status, HealthStatus.UNHEALTHY)


class TestExecutionPipeline(unittest.TestCase):
    """Test execution pipeline."""
    
    def test_payload_validation(self):
        from runtime.pipeline import ExecutionPipeline, ExecutionPayload, ExecutionStatus
        pipeline = ExecutionPipeline(dry_run=True)
        payload = ExecutionPayload(token_in="", token_out="ETH", amount_in=Decimal("1"))
        result = pipeline.execute(payload)
        self.assertEqual(result.status, ExecutionStatus.FAILED)
    
    def test_risk_kernel_required(self):
        from runtime.pipeline import ExecutionPipeline, ExecutionPayload, ExecutionStatus, SignalType
        pipeline = ExecutionPipeline(dry_run=False)
        payload = ExecutionPayload(
            token_in="USDC", token_out="ETH", amount_in=Decimal("1000"),
            signal_type=SignalType.SWAP,
        )
        result = pipeline.execute(payload)
        self.assertEqual(result.status, ExecutionStatus.RISK_BLOCKED)
    
    def test_dry_run(self):
        from runtime.pipeline import ExecutionPipeline, ExecutionPayload, ExecutionStatus, SignalType
        pipeline = ExecutionPipeline(dry_run=True)
        payload = ExecutionPayload(
            token_in="USDC", token_out="ETH", amount_in=Decimal("1000"),
            signal_type=SignalType.SWAP, chain_id=1, protocol="uniswap_v3",
        )
        result = pipeline.execute(payload)
        self.assertEqual(result.status, ExecutionStatus.EXECUTED)
        self.assertTrue(result.success)
    
    def test_risk_blocked(self):
        from runtime.pipeline import ExecutionPipeline, ExecutionPayload, ExecutionStatus, SignalType
        mock_kernel = MagicMock()
        mock_result = MagicMock()
        mock_result.passed = False
        mock_result.breached_limits = ["drawdown"]
        mock_result.warnings = []
        mock_result.failure_reason = "Limit exceeded"
        mock_kernel.check.return_value = mock_result
        
        pipeline = ExecutionPipeline(risk_kernel=mock_kernel, dry_run=False)
        payload = ExecutionPayload(
            token_in="USDC", token_out="ETH", amount_in=Decimal("1000"),
            signal_type=SignalType.SWAP,
        )
        result = pipeline.execute(payload)
        self.assertEqual(result.status, ExecutionStatus.RISK_BLOCKED)


class TestRuntimeBoot(unittest.TestCase):
    """Test runtime boot."""
    
    def test_state_transitions(self):
        from runtime.boot import RuntimeBoot, RuntimeState, RuntimeConfig
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RuntimeConfig(
                config_dir=Path(tmpdir) / "config",
                data_dir=Path(tmpdir) / "data",
            )
            (Path(tmpdir) / "config").mkdir()
            (Path(tmpdir) / "data").mkdir()
            
            rt = RuntimeBoot(config=config, project_root=Path(tmpdir))
            self.assertEqual(rt.state, RuntimeState.UNINITIALIZED)
            
            if rt.boot():
                self.assertEqual(rt.state, RuntimeState.RUNNING)
                rt.shutdown()
                self.assertEqual(rt.state, RuntimeState.STOPPED)
    
    def test_event_bus_initialized(self):
        from runtime.boot import RuntimeBoot, RuntimeConfig
        with tempfile.TemporaryDirectory() as tmpdir:
            config = RuntimeConfig(
                config_dir=Path(tmpdir) / "config",
                data_dir=Path(tmpdir) / "data",
            )
            (Path(tmpdir) / "config").mkdir()
            (Path(tmpdir) / "data").mkdir()
            
            rt = RuntimeBoot(config=config, project_root=Path(tmpdir))
            rt.boot()
            self.assertIn("event_bus", rt._services)
            rt.shutdown()


class TestIntegration(unittest.TestCase):
    """Integration tests."""
    
    def test_full_execution_flow(self):
        from runtime.pipeline import ExecutionPipeline, ExecutionPayload, ExecutionStatus, SignalType
        
        mock_kernel = MagicMock()
        mock_result = MagicMock()
        mock_result.passed = True
        mock_result.breached_limits = []
        mock_result.warnings = []
        mock_kernel.check.return_value = mock_result
        
        mock_bus = MagicMock()
        
        pipeline = ExecutionPipeline(
            risk_kernel=mock_kernel, event_bus=mock_bus, dry_run=True
        )
        
        payload = ExecutionPayload(
            strategy_id="momentum_v1", token_in="USDC", token_out="ETH",
            amount_in=Decimal("1000"), signal_type=SignalType.SWAP,
            chain_id=1, protocol="uniswap_v3",
        )
        
        result = pipeline.execute(payload)
        self.assertEqual(result.status, ExecutionStatus.EXECUTED)
        mock_kernel.check.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
