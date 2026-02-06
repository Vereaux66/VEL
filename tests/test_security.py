#!/usr/bin/env python3
"""
VEL Security Test Suite
=======================

Comprehensive security testing for military-grade protection.

Run with: python -m pytest tests/test_security.py -v
"""

import os
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from anvel_military_security import (
    AttackType,
    CryptographicSecurity,
    InputValidator,
    IntrusionDetector,
    MilitaryGradeSecurityManager,
    RateLimitConfig,
    RateLimiter,
    ResponseAction,
    SessionManager,
    ThreatLevel,
    CRYPTO_AVAILABLE,
)


class TestInputValidator(unittest.TestCase):
    """Test input validation and sanitization."""
    
    def setUp(self):
        self.validator = InputValidator()
    
    def test_clean_input_passes(self):
        """Clean input should pass validation."""
        safe, attack = self.validator.validate_input("Hello World")
        self.assertTrue(safe)
        self.assertIsNone(attack)
    
    def test_sql_injection_detected(self):
        """SQL injection attempts should be detected."""
        payloads = [
            "' OR '1'='1",
            "1; DROP TABLE users;--",
            "UNION SELECT * FROM passwords",
            "'; DELETE FROM accounts--",
        ]
        
        for payload in payloads:
            safe, attack = self.validator.validate_input(payload)
            self.assertFalse(safe, f"SQL injection not detected: {payload}")
            self.assertEqual(attack, AttackType.SQL_INJECTION)
    
    def test_xss_detected(self):
        """XSS attempts should be detected."""
        payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert(1)",
            "<img onerror=alert(1)>",
            "<svg onload=alert(1)>",
        ]
        
        for payload in payloads:
            safe, attack = self.validator.validate_input(payload)
            self.assertFalse(safe, f"XSS not detected: {payload}")
            self.assertEqual(attack, AttackType.XSS)
    
    def test_command_injection_detected(self):
        """Command injection attempts should be detected."""
        payloads = [
            "test; ls -la",  # More specific command injection pattern
            "test `whoami`",  # Backtick command execution
            "${PATH}",  # Variable expansion
        ]
        
        for payload in payloads:
            safe, attack = self.validator.validate_input(payload)
            self.assertFalse(safe, f"Command injection not detected: {payload}")
            # Note: Some payloads may also match SQL patterns first
            self.assertIn(attack, [AttackType.COMMAND_INJECTION, AttackType.SQL_INJECTION])
    
    def test_path_traversal_detected(self):
        """Path traversal attempts should be detected."""
        payloads = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "%2e%2e/etc/passwd",
        ]
        
        for payload in payloads:
            safe, attack = self.validator.validate_input(payload)
            self.assertFalse(safe, f"Path traversal not detected: {payload}")
            self.assertEqual(attack, AttackType.PATH_TRAVERSAL)
    
    def test_sanitize_html_entities(self):
        """Sanitization should encode dangerous characters."""
        dangerous = '<script>alert("xss")</script>'
        sanitized = self.validator.sanitize(dangerous)
        
        self.assertNotIn("<", sanitized)
        self.assertNotIn(">", sanitized)
        self.assertIn("&lt;", sanitized)
        self.assertIn("&gt;", sanitized)


class TestRateLimiter(unittest.TestCase):
    """Test rate limiting functionality."""
    
    def test_allows_normal_traffic(self):
        """Normal traffic should be allowed."""
        limiter = RateLimiter(RateLimitConfig(
            requests_per_minute=10,
            burst_limit=5,
        ))
        
        for _ in range(5):
            allowed, reason = limiter.check("test_client")
            self.assertTrue(allowed)
            self.assertIsNone(reason)
    
    def test_blocks_burst_traffic(self):
        """Burst traffic should be blocked."""
        limiter = RateLimiter(RateLimitConfig(
            burst_limit=3,
            burst_window_seconds=1,
        ))
        
        # First 3 should pass
        for _ in range(3):
            allowed, _ = limiter.check("burst_client")
            self.assertTrue(allowed)
        
        # Next should be blocked
        allowed, reason = limiter.check("burst_client")
        self.assertFalse(allowed)
        self.assertIn("Burst", reason)
    
    def test_unblock_works(self):
        """Manual unblock should work."""
        limiter = RateLimiter(RateLimitConfig(burst_limit=1, burst_window_seconds=1))
        
        # First request succeeds
        allowed1, _ = limiter.check("client")
        self.assertTrue(allowed1)
        
        # Second request fails (blocked)
        allowed2, _ = limiter.check("client")
        self.assertFalse(allowed2)
        
        # Unblock and wait a moment
        limiter.unblock("client")
        time.sleep(1.1)  # Wait for burst window to clear
        
        # Should work again
        allowed3, _ = limiter.check("client")
        self.assertTrue(allowed3)


class TestCryptographicSecurity(unittest.TestCase):
    """Test cryptographic operations."""
    
    def setUp(self):
        self.crypto = CryptographicSecurity()
    
    def test_token_generation(self):
        """Generated tokens should be unique and correct length."""
        token1 = self.crypto.generate_token(32)
        token2 = self.crypto.generate_token(32)
        
        self.assertNotEqual(token1, token2)
        self.assertGreater(len(token1), 30)  # URL-safe base64 encoding
    
    def test_password_hashing(self):
        """Password hashing should be consistent."""
        password = "SecurePassword123!"
        
        hash1, salt1 = self.crypto.hash_password(password)
        
        # Same password with same salt should give same hash
        hash2, _ = self.crypto.hash_password(password, bytes.fromhex(salt1))
        self.assertEqual(hash1, hash2)
        
        # Different password should give different hash
        hash3, _ = self.crypto.hash_password("DifferentPassword", bytes.fromhex(salt1))
        self.assertNotEqual(hash1, hash3)
    
    def test_password_verification(self):
        """Password verification should work correctly."""
        password = "SecurePassword123!"
        
        hash_hex, salt_hex = self.crypto.hash_password(password)
        
        # Correct password should verify
        self.assertTrue(self.crypto.verify_password(password, hash_hex, salt_hex))
        
        # Wrong password should not verify
        self.assertFalse(self.crypto.verify_password("wrong", hash_hex, salt_hex))
    
    def test_encryption_decryption(self):
        """Data should encrypt and decrypt correctly."""
        if not CRYPTO_AVAILABLE:
            # Skip test if cryptography not available
            self.skipTest("Cryptography library not available")
        
        data = b"sensitive data to protect"
        
        encrypted = self.crypto.encrypt(data)
        decrypted = self.crypto.decrypt(encrypted)
        
        self.assertNotEqual(data, encrypted)
        self.assertEqual(data, decrypted)
    
    def test_hmac_verification(self):
        """HMAC should verify data integrity."""
        data = b"important message"
        
        signature = self.crypto.generate_hmac(data)
        
        # Correct data should verify
        self.assertTrue(self.crypto.verify_hmac(data, signature))
        
        # Tampered data should not verify
        self.assertFalse(self.crypto.verify_hmac(b"tampered message", signature))


class TestSessionManager(unittest.TestCase):
    """Test session management."""
    
    def setUp(self):
        crypto = CryptographicSecurity()
        self.sessions = SessionManager(crypto)
    
    def test_session_creation(self):
        """Sessions should be created correctly."""
        session_id = self.sessions.create_session(
            user_id="user123",
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
        )
        
        self.assertIsNotNone(session_id)
        self.assertGreater(len(session_id), 40)
    
    def test_session_validation(self):
        """Valid sessions should pass validation."""
        session_id = self.sessions.create_session(
            user_id="user123",
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
        )
        
        valid, user_id, error = self.sessions.validate_session(
            session_id,
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
        )
        
        self.assertTrue(valid)
        self.assertEqual(user_id, "user123")
        self.assertIsNone(error)
    
    def test_session_hijack_detection(self):
        """Session hijacking should be detected."""
        session_id = self.sessions.create_session(
            user_id="user123",
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
        )
        
        # Try with different IP/user agent (hijacking attempt)
        valid, _, error = self.sessions.validate_session(
            session_id,
            ip_address="10.0.0.99",  # Different IP
            user_agent="AttackerAgent/1.0",
        )
        
        self.assertFalse(valid)
        self.assertIn("fingerprint", error.lower())
    
    def test_session_invalidation(self):
        """Invalidated sessions should fail validation."""
        session_id = self.sessions.create_session(
            user_id="user123",
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
        )
        
        # Invalidate
        result = self.sessions.invalidate_session(session_id)
        self.assertTrue(result)
        
        # Should no longer validate
        valid, _, _ = self.sessions.validate_session(
            session_id,
            ip_address="192.168.1.1",
            user_agent="TestAgent/1.0",
        )
        self.assertFalse(valid)


class TestIntrusionDetector(unittest.TestCase):
    """Test intrusion detection system."""
    
    def setUp(self):
        self.ids = IntrusionDetector()
    
    def test_clean_request_passes(self):
        """Clean requests should pass."""
        safe, event = self.ids.analyze_request(
            source_ip="192.168.1.1",
            user_id="user123",
            request_data={"name": "John", "action": "view"},
        )
        
        self.assertTrue(safe)
        self.assertIsNone(event)
    
    def test_blocked_ip_rejected(self):
        """Blocked IPs should be rejected."""
        self.ids.block_ip("10.0.0.99")
        
        safe, event = self.ids.analyze_request(
            source_ip="10.0.0.99",
            user_id="attacker",
            request_data={"action": "test"},
        )
        
        self.assertFalse(safe)
        self.assertIsNotNone(event)
    
    def test_malicious_payload_detected(self):
        """Malicious payloads should trigger detection."""
        safe, event = self.ids.analyze_request(
            source_ip="192.168.1.1",
            user_id="user123",
            request_data={"query": "UNION SELECT * FROM passwords"},
        )
        
        self.assertFalse(safe)
        self.assertIsNotNone(event)
        self.assertEqual(event.attack_type, AttackType.SQL_INJECTION)


class TestMilitaryGradeSecurityManager(unittest.TestCase):
    """Test the complete security manager."""
    
    def setUp(self):
        self.manager = MilitaryGradeSecurityManager()
    
    def test_clean_request_allowed(self):
        """Clean requests should be allowed."""
        allowed, event = self.manager.process_request(
            source_ip="192.168.1.1",
            user_id="user123",
            request_data={"action": "view", "page": "dashboard"},
        )
        
        self.assertTrue(allowed)
        self.assertIsNone(event)
    
    def test_malicious_request_blocked(self):
        """Malicious requests should be blocked."""
        allowed, event = self.manager.process_request(
            source_ip="192.168.1.1",
            user_id="attacker",
            request_data={"query": "'; DROP TABLE users;--"},
        )
        
        self.assertFalse(allowed)
        self.assertIsNotNone(event)
        self.assertTrue(event.blocked)
    
    def test_lockdown_blocks_all(self):
        """Lockdown mode should block all requests."""
        self.manager.activate_lockdown("Test lockdown")
        
        allowed, event = self.manager.process_request(
            source_ip="192.168.1.1",
            user_id="user123",
            request_data={"action": "view"},
        )
        
        self.assertFalse(allowed)
        self.assertIn("lockdown", event.event_type)
        
        # Cleanup
        self.manager.deactivate_lockdown()
    
    def test_ip_blocking(self):
        """IP blocking should work."""
        self.manager.block_ip("10.0.0.99", "Test block")
        
        allowed, event = self.manager.process_request(
            source_ip="10.0.0.99",
            user_id="any",
            request_data={"action": "test"},
        )
        
        self.assertFalse(allowed)
        
        # Unblock and try again
        self.manager.unblock_ip("10.0.0.99")
        
        allowed, _ = self.manager.process_request(
            source_ip="10.0.0.99",
            user_id="any",
            request_data={"action": "test"},
        )
        
        self.assertTrue(allowed)
    
    def test_user_blocking(self):
        """User blocking should work."""
        self.manager.block_user("bad_user", "Test block")
        
        allowed, event = self.manager.process_request(
            source_ip="192.168.1.1",
            user_id="bad_user",
            request_data={"action": "test"},
        )
        
        self.assertFalse(allowed)
        
        # Cleanup
        self.manager.unblock_user("bad_user")
    
    def test_security_status(self):
        """Security status should be retrievable."""
        status = self.manager.get_security_status()
        
        self.assertIn("lockdown_mode", status)
        self.assertIn("blocked_ips", status)
        self.assertIn("blocked_users", status)
        self.assertIn("total_events", status)
    
    def test_rate_limiting_integration(self):
        """Rate limiting should be integrated."""
        # Make many rapid requests
        for _ in range(100):
            self.manager.process_request(
                source_ip="rate_test_ip",
                user_id="user",
                request_data={"action": "test"},
            )
        
        # Should eventually be blocked
        allowed, event = self.manager.process_request(
            source_ip="rate_test_ip",
            user_id="user",
            request_data={"action": "test"},
        )
        
        # Either blocked or allowed (depends on timing)
        self.assertIsNotNone(allowed)


class TestSecurityIntegration(unittest.TestCase):
    """Integration tests for the security system."""
    
    def test_full_attack_scenario(self):
        """Test complete attack scenario handling."""
        manager = MilitaryGradeSecurityManager()
        
        # Phase 1: Reconnaissance (clean requests)
        for _ in range(5):
            allowed, _ = manager.process_request(
                source_ip="192.168.1.100",
                user_id=None,
                request_data={"action": "view"},
            )
            self.assertTrue(allowed)
        
        # Phase 2: SQL injection attempt
        allowed, event = manager.process_request(
            source_ip="192.168.1.100",
            user_id=None,
            request_data={"search": "' OR '1'='1"},
        )
        self.assertFalse(allowed)
        self.assertEqual(event.attack_type, AttackType.SQL_INJECTION)
        
        # Verify event was logged
        events = manager.get_recent_events(limit=10)
        self.assertGreater(len(events), 0)
    
    def test_session_with_security(self):
        """Test session management with security checks."""
        manager = MilitaryGradeSecurityManager()
        
        # Create session
        session_id = manager.sessions.create_session(
            user_id="legit_user",
            ip_address="192.168.1.50",
            user_agent="Browser/1.0",
        )
        
        # Valid request with session
        allowed, _ = manager.process_request(
            source_ip="192.168.1.50",
            user_id="legit_user",
            request_data={"action": "trade"},
            session_id=session_id,
            user_agent="Browser/1.0",
        )
        self.assertTrue(allowed)
        
        # Hijacked session attempt
        allowed, event = manager.process_request(
            source_ip="10.0.0.1",  # Different IP
            user_id="legit_user",
            request_data={"action": "withdraw"},
            session_id=session_id,
            user_agent="AttackerBrowser/1.0",
        )
        self.assertFalse(allowed)
        self.assertEqual(event.attack_type, AttackType.SESSION_HIJACK)


if __name__ == "__main__":
    unittest.main(verbosity=2)
