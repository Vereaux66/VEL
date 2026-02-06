#!/usr/bin/env python3
"""
VEL Production Infrastructure Test Suite
=========================================

Tests for production-grade modules:
- Risk controls
- Rate limiting
- Metrics collection
- Structured logging
- AI safety constraints

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


class TestRiskControls(unittest.TestCase):
    """Test risk control engine."""
    
    def setUp(self):
        from vel_risk_controls import RiskControlEngine, RiskConfig, reset_risk_controller
        reset_risk_controller()
        self.config = RiskConfig(
            max_daily_loss_usd=Decimal("1000"),
            max_trades_per_minute=10,
            max_trades_per_hour=50,
            max_trades_per_day=100,
            max_trade_size_usd=Decimal("500"),
            min_trade_size_usd=Decimal("1"),
            max_slippage_percentage=Decimal("2.0"),
            require_manual_reset=False,
            kill_switch_cooldown_seconds=0,  # No cooldown for tests
        )
        self.engine = RiskControlEngine(config=self.config)
    
    def _create_trade(self, amount_usd=Decimal("100"), slippage=Decimal("0.5")):
        from vel_risk_controls import TradeRequest
        return TradeRequest(
            trade_id=f"test_{time.time()}",
            wallet_address="0x1234567890abcdef",
            chain_id=1,
            token_in="USDC",
            token_out="ETH",
            amount_in=amount_usd,
            amount_in_usd=amount_usd,
            expected_amount_out=amount_usd / Decimal("2000"),
            expected_amount_out_usd=amount_usd,
            max_slippage=slippage,
        )
    
    def test_trade_allowed(self):
        """Test that valid trades are allowed."""
        trade = self._create_trade(amount_usd=Decimal("100"))
        result = self.engine.pre_trade_check(trade)
        self.assertTrue(result.allowed, f"Trade should be allowed: {result.reason}")
    
    def test_trade_blocked_too_small(self):
        """Test that trades below minimum are blocked."""
        trade = self._create_trade(amount_usd=Decimal("0.5"))
        result = self.engine.pre_trade_check(trade)
        self.assertFalse(result.allowed)
        self.assertIn("below minimum", result.reason)
    
    def test_trade_blocked_too_large(self):
        """Test that trades above maximum are blocked."""
        trade = self._create_trade(amount_usd=Decimal("1000"))
        result = self.engine.pre_trade_check(trade)
        self.assertFalse(result.allowed)
        self.assertIn("exceeds maximum", result.reason)
    
    def test_trade_blocked_high_slippage(self):
        """Test that trades with high slippage are blocked."""
        trade = self._create_trade(slippage=Decimal("5.0"))
        result = self.engine.pre_trade_check(trade)
        self.assertFalse(result.allowed)
        self.assertIn("Slippage", result.reason)
    
    def test_kill_switch(self):
        """Test global kill switch."""
        # Activate kill switch
        self.engine.trigger_kill_switch("Test halt", activated_by="test")
        self.assertTrue(self.engine.is_kill_switch_active)
        
        # Trade should be blocked
        trade = self._create_trade()
        result = self.engine.pre_trade_check(trade)
        self.assertFalse(result.allowed)
        self.assertIn("Kill switch", result.reason)
        
        # Reset kill switch
        self.engine.reset_kill_switch(reset_by="test")
        self.assertFalse(self.engine.is_kill_switch_active)
        
        # Trade should now be allowed
        result = self.engine.pre_trade_check(trade)
        self.assertTrue(result.allowed)
    
    def test_daily_loss_limit(self):
        """Test that daily loss limit triggers kill switch."""
        # Record large loss
        self.engine.record_trade_result(
            trade_id="loss1",
            pnl_usd=Decimal("-600"),
            token="ETH",
            position_change_usd=Decimal("0")
        )
        
        # Should still be active
        self.assertFalse(self.engine.is_kill_switch_active)
        
        # Record another loss to exceed limit
        self.engine.record_trade_result(
            trade_id="loss2",
            pnl_usd=Decimal("-500"),
            token="ETH",
            position_change_usd=Decimal("0")
        )
        
        # Kill switch should be active
        self.assertTrue(self.engine.is_kill_switch_active)


class TestRateLimiter(unittest.TestCase):
    """Test rate limiting."""
    
    def setUp(self):
        from vel_rate_limiter import SlidingWindowRateLimiter, RateLimitConfig
        self.config = RateLimitConfig(
            default_limit=5,
            default_period=60,
        )
        self.limiter = SlidingWindowRateLimiter(config=self.config)
    
    def test_allows_within_limit(self):
        """Test requests within limit are allowed."""
        for i in range(5):
            result = self.limiter.check(f"client_{i}", "/api/test", limit=5, period=60)
            self.assertTrue(result.allowed, f"Request {i} should be allowed")
    
    def test_blocks_over_limit(self):
        """Test requests over limit are blocked."""
        client = "heavy_client"
        
        # Make requests up to limit
        for i in range(5):
            result = self.limiter.check(client, "/api/test", limit=5, period=60)
            self.assertTrue(result.allowed)
        
        # Next request should be blocked
        result = self.limiter.check(client, "/api/test", limit=5, period=60)
        self.assertFalse(result.allowed)
        self.assertIsNotNone(result.retry_after)
    
    def test_different_clients_separate(self):
        """Test different clients have separate limits."""
        # Exhaust client1's limit
        for i in range(5):
            self.limiter.check("client1", "/api/test", limit=5, period=60)
        
        # client2 should still be allowed
        result = self.limiter.check("client2", "/api/test", limit=5, period=60)
        self.assertTrue(result.allowed)
    
    def test_headers_returned(self):
        """Test rate limit headers are returned."""
        result = self.limiter.check("client", "/api/test", limit=10, period=60)
        headers = result.headers()
        
        self.assertIn("X-RateLimit-Limit", headers)
        self.assertIn("X-RateLimit-Remaining", headers)
        self.assertIn("X-RateLimit-Reset", headers)
        self.assertEqual(headers["X-RateLimit-Limit"], "10")


class TestWebSocketRateLimiter(unittest.TestCase):
    """Test WebSocket rate limiting."""
    
    def setUp(self):
        from vel_rate_limiter import WebSocketRateLimiter
        self.limiter = WebSocketRateLimiter(
            max_connections_per_client=3,
            max_messages_per_second=5,
            max_message_size=1024,
        )
    
    def test_connection_limit(self):
        """Test connection limit per client."""
        client = "ws_client"
        
        # Should allow up to limit
        for i in range(3):
            self.assertTrue(self.limiter.can_connect(client))
        
        # Should block over limit
        self.assertFalse(self.limiter.can_connect(client))
        
        # After disconnect, should allow again
        self.limiter.on_disconnect(client)
        self.assertTrue(self.limiter.can_connect(client))
    
    def test_message_size_limit(self):
        """Test message size limit."""
        client = "ws_client"
        
        # Small message OK
        self.assertTrue(self.limiter.can_send_message(client, message_size=100))
        
        # Large message blocked
        self.assertFalse(self.limiter.can_send_message(client, message_size=2000))


class TestPrometheusMetrics(unittest.TestCase):
    """Test Prometheus metrics collection."""
    
    def setUp(self):
        from vel_prometheus_metrics import VELMetricsCollector, reset_metrics_collector
        reset_metrics_collector()
        self.collector = VELMetricsCollector()
    
    def test_record_intent(self):
        """Test recording intents."""
        self.collector.record_intent(chain_id=1, protocol="uniswap_v3", signal_type="swap")
        # Should not raise
    
    def test_record_execution(self):
        """Test recording executions."""
        self.collector.record_execution(
            chain_id=1,
            protocol="uniswap_v3",
            success=True,
            latency_seconds=0.15,
            value_usd=1000,
        )
        # Should not raise
    
    def test_circuit_breaker_state(self):
        """Test circuit breaker state."""
        self.collector.set_circuit_breaker_state("global", is_open=False)
        self.collector.set_circuit_breaker_state("global", is_open=True)
        # Should not raise
    
    def test_get_metrics(self):
        """Test metrics output."""
        self.collector.record_intent(chain_id=1, protocol="test", signal_type="swap")
        metrics = self.collector.get_metrics()
        self.assertIsInstance(metrics, bytes)


class TestStructuredLogging(unittest.TestCase):
    """Test structured logging."""
    
    def test_json_formatter(self):
        """Test JSON formatter output."""
        from vel_structured_logging import VELJSONFormatter
        
        formatter = VELJSONFormatter(
            service_name="test-service",
            environment="test"
        )
        
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        data = json.loads(output)
        
        self.assertEqual(data["level"], "INFO")
        self.assertEqual(data["logger"], "test.logger")
        self.assertIn("Test message", data["message"])
        self.assertEqual(data["service"], "test-service")
        self.assertEqual(data["environment"], "test")
    
    def test_sensitive_data_masking(self):
        """Test sensitive data is masked."""
        from vel_structured_logging import mask_sensitive_data
        
        text = 'password="secret123" api_key="abc123"'
        masked = mask_sensitive_data(text)
        
        self.assertIn("***MASKED***", masked)
        self.assertNotIn("secret123", masked)
        self.assertNotIn("abc123", masked)
    
    def test_trace_context(self):
        """Test trace context management."""
        from vel_structured_logging import TraceContext, trace_id_var
        
        self.assertIsNone(trace_id_var.get())
        
        with TraceContext(trace_id="test-trace-123"):
            self.assertEqual(trace_id_var.get(), "test-trace-123")
        
        self.assertIsNone(trace_id_var.get())


class TestAISafety(unittest.TestCase):
    """Test AI safety constraints."""
    
    def setUp(self):
        from vel_ai_safety import SafeAIExecutor, AISafetyConfig
        self.config = AISafetyConfig(
            enforce_determinism=True,
            fixed_random_seed=42,
            max_decision_value_usd=Decimal("1000"),
            max_decisions_per_hour=100,
            allow_self_modification=False,
        )
        self.executor = SafeAIExecutor(config=self.config)
    
    def test_deterministic_execution(self):
        """Test deterministic execution produces same results."""
        from vel_ai_safety import DecisionType
        import random
        
        def random_decision(seed_val):
            # Use random without explicit re-seeding - should be deterministic
            # because SafeAIExecutor sets the seed before each call
            return {"value": random.random(), "input": seed_val}
        
        # Execute twice with same input
        result1 = self.executor.execute(
            decision_func=random_decision,
            inputs={"seed_val": 123},
            decision_type=DecisionType.TRADE_SIGNAL,
        )
        
        result2 = self.executor.execute(
            decision_func=random_decision,
            inputs={"seed_val": 123},
            decision_type=DecisionType.TRADE_SIGNAL,
        )
        
        # Results should be identical due to deterministic context
        self.assertEqual(result1["value"], result2["value"])
    
    def test_value_limit(self):
        """Test value limit enforcement."""
        from vel_ai_safety import DecisionType, SafetyLimitExceeded
        
        def simple_decision():
            return {"result": "ok"}
        
        with self.assertRaises(SafetyLimitExceeded):
            self.executor.execute(
                decision_func=simple_decision,
                inputs={},
                decision_type=DecisionType.TRADE_SIGNAL,
                value_usd=Decimal("5000"),  # Over limit
            )
    
    def test_self_modification_blocked(self):
        """Test self-modification is blocked when disabled."""
        from vel_ai_safety import DecisionType, SafetyLimitExceeded
        
        def modify_code():
            return {"modified": True}
        
        with self.assertRaises(SafetyLimitExceeded):
            self.executor.execute(
                decision_func=modify_code,
                inputs={},
                decision_type=DecisionType.CODE_MODIFICATION,
            )
    
    def test_audit_logging(self):
        """Test audit logging."""
        from vel_ai_safety import DecisionType
        
        def simple_decision(x):
            return {"result": x * 2}
        
        self.executor.execute(
            decision_func=simple_decision,
            inputs={"x": 5},
            decision_type=DecisionType.TRADE_SIGNAL,
            reasoning="Test decision",
        )
        
        audit_log = self.executor.get_audit_log(limit=10)
        self.assertGreater(len(audit_log), 0)
        
        last_entry = audit_log[-1]
        self.assertEqual(last_entry["decision_type"], "trade_signal")
        self.assertEqual(last_entry["reasoning"], "Test decision")


class TestGunicornConfig(unittest.TestCase):
    """Test gunicorn configuration."""
    
    def test_config_imports(self):
        """Test gunicorn config can be imported."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "gunicorn_conf",
            str(Path(__file__).parent.parent / "gunicorn.conf.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Check key settings exist
        self.assertTrue(hasattr(module, "workers"))
        self.assertTrue(hasattr(module, "bind"))
        self.assertTrue(hasattr(module, "timeout"))
        self.assertTrue(hasattr(module, "worker_class"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
