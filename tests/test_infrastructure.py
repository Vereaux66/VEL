#!/usr/bin/env python3
"""
VEL Production Infrastructure Test Suite
=========================================

Tests for production readiness infrastructure components.

Run with: python -m pytest tests/test_infrastructure.py -v
"""

import os
import sys
import tempfile
import threading
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDistributedLocks(unittest.TestCase):
    """Test distributed locking system."""
    
    def test_lock_manager_initialization(self):
        """Lock manager should initialize correctly."""
        from vel_distributed_locks import DistributedLockManager, LockConfig
        
        config = LockConfig(default_lock_timeout_seconds=10)
        manager = DistributedLockManager(config=config)
        
        self.assertIsNotNone(manager._owner_id)
        self.assertEqual(manager.config.default_lock_timeout_seconds, 10)
    
    def test_lock_acquire_and_release(self):
        """Should acquire and release locks correctly."""
        from vel_distributed_locks import DistributedLockManager, LockType
        
        manager = DistributedLockManager()
        
        # Acquire lock
        lock_info = manager.acquire(LockType.WALLET, "0x1234567890")
        self.assertIsNotNone(lock_info)
        self.assertEqual(lock_info.lock_type, LockType.WALLET)
        self.assertEqual(lock_info.resource_id, "0x1234567890")
        
        # Release lock
        released = manager.release(lock_info)
        self.assertTrue(released)
    
    def test_lock_prevents_concurrent_access(self):
        """Lock should prevent concurrent access."""
        from vel_distributed_locks import DistributedLockManager, LockType
        
        manager = DistributedLockManager()
        
        # Acquire first lock
        lock1 = manager.acquire(LockType.WALLET, "shared_resource")
        self.assertIsNotNone(lock1)
        
        # Try to acquire second lock (should fail with blocking=False)
        lock2 = manager.acquire(LockType.WALLET, "shared_resource", blocking=False)
        self.assertIsNone(lock2)
        
        # Release first lock
        manager.release(lock1)
        
        # Now should be able to acquire
        lock3 = manager.acquire(LockType.WALLET, "shared_resource")
        self.assertIsNotNone(lock3)
        manager.release(lock3)
    
    def test_lock_context_manager(self):
        """Lock context manager should work correctly."""
        from vel_distributed_locks import DistributedLockManager, LockType, LockAcquisitionError
        
        manager = DistributedLockManager()
        
        # Using context manager
        with manager.lock(LockType.WALLET, "context_test"):
            # Lock should be held
            lock = manager.acquire(LockType.WALLET, "context_test", blocking=False)
            self.assertIsNone(lock)  # Cannot acquire while in context
        
        # Lock should be released after context
        lock = manager.acquire(LockType.WALLET, "context_test", blocking=False)
        self.assertIsNotNone(lock)
        manager.release(lock)
    
    def test_lock_timeout_auto_release(self):
        """Lock should auto-release after timeout."""
        from vel_distributed_locks import DistributedLockManager, LockType, LockConfig
        
        config = LockConfig(default_lock_timeout_seconds=1)
        manager = DistributedLockManager(config=config)
        
        # Acquire lock with short timeout
        lock1 = manager.acquire(LockType.WALLET, "timeout_test", timeout_seconds=1)
        self.assertIsNotNone(lock1)
        
        # Wait for timeout
        time.sleep(1.5)
        
        # Should now be able to acquire
        lock2 = manager.acquire(LockType.WALLET, "timeout_test", blocking=False)
        self.assertIsNotNone(lock2)
        manager.release(lock2)


class TestIdempotency(unittest.TestCase):
    """Test idempotency engine."""
    
    def test_idempotency_engine_initialization(self):
        """Idempotency engine should initialize correctly."""
        from vel_distributed_locks import IdempotencyEngine
        
        engine = IdempotencyEngine(default_ttl_seconds=3600)
        self.assertEqual(engine.default_ttl, 3600)
    
    def test_idempotency_key_tracking(self):
        """Should track and deduplicate idempotency keys."""
        from vel_distributed_locks import IdempotencyEngine
        
        engine = IdempotencyEngine()
        
        # First call should start operation
        is_new, existing = engine.start("trade_123")
        self.assertTrue(is_new)
        self.assertIsNone(existing)
        
        # Second call should return existing
        is_new2, existing2 = engine.start("trade_123")
        self.assertFalse(is_new2)
        self.assertIsNotNone(existing2)
        self.assertEqual(existing2.status, "processing")
    
    def test_idempotency_completion(self):
        """Should track completed operations."""
        from vel_distributed_locks import IdempotencyEngine
        
        engine = IdempotencyEngine()
        
        # Start and complete
        engine.start("complete_test")
        engine.complete("complete_test", {"result": "success", "tx_hash": "0xabc"})
        
        # Check result
        record = engine.check("complete_test")
        self.assertIsNotNone(record)
        self.assertEqual(record.status, "completed")
        self.assertEqual(record.result["result"], "success")
    
    def test_idempotency_context_manager(self):
        """Context manager should handle idempotency correctly."""
        from vel_distributed_locks import IdempotencyEngine
        
        engine = IdempotencyEngine()
        
        # First execution
        with engine.execute("ctx_test") as ctx:
            self.assertFalse(ctx.already_executed)
            ctx.complete({"value": 42})
        
        # Second execution should return cached result
        with engine.execute("ctx_test") as ctx:
            self.assertTrue(ctx.already_executed)
            self.assertEqual(ctx.result["value"], 42)


class TestCrashRecovery(unittest.TestCase):
    """Test crash recovery system."""
    
    def test_wal_initialization(self):
        """Write-ahead log should initialize correctly."""
        from vel_crash_recovery import WriteAheadLog
        
        with tempfile.TemporaryDirectory() as tmpdir:
            wal = WriteAheadLog(wal_path=tmpdir)
            self.assertTrue(Path(tmpdir).exists())
    
    def test_wal_append_and_read(self):
        """WAL should append and read entries correctly."""
        from vel_crash_recovery import WriteAheadLog, JournalEntryType
        
        with tempfile.TemporaryDirectory() as tmpdir:
            wal = WriteAheadLog(wal_path=tmpdir)
            
            # Append entry
            entry = wal.append(
                JournalEntryType.TRANSACTION_SUBMITTED,
                {"tx_hash": "0xabc", "wallet": "0x123", "chain_id": 1, "nonce": 5}
            )
            
            self.assertIsNotNone(entry.entry_id)
            self.assertEqual(entry.entry_type, JournalEntryType.TRANSACTION_SUBMITTED)
            
            # Read entries
            entries = wal.read_since()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].data["tx_hash"], "0xabc")
    
    def test_wal_checkpoints(self):
        """WAL checkpoints should work correctly."""
        from vel_crash_recovery import WriteAheadLog, JournalEntryType
        
        with tempfile.TemporaryDirectory() as tmpdir:
            wal = WriteAheadLog(wal_path=tmpdir)
            
            # Add some entries
            for i in range(3):
                wal.append(
                    JournalEntryType.BALANCE_UPDATE,
                    {"wallet": "0x123", "chain_id": 1, "token": "native",
                     "old_balance": str(i), "new_balance": str(i+1)}
                )
            
            # Create checkpoint
            state = {"balances": {"0x123": "100"}}
            checkpoint = wal.create_checkpoint(state)
            
            self.assertIsNotNone(checkpoint.checkpoint_id)
            self.assertTrue(checkpoint.verify())
            
            # Get latest checkpoint
            latest = wal.get_latest_checkpoint()
            self.assertIsNotNone(latest)
            self.assertEqual(latest.checkpoint_id, checkpoint.checkpoint_id)
    
    def test_journal_entry_integrity(self):
        """Journal entries should verify integrity correctly."""
        from vel_crash_recovery import JournalEntry, JournalEntryType
        
        entry = JournalEntry(
            entry_id="test_001",
            entry_type=JournalEntryType.TRANSACTION_CONFIRMED,
            timestamp=time.time(),
            data={"tx_hash": "0xabc", "block_number": 12345}
        )
        entry.checksum = entry.compute_checksum()
        
        # Should verify
        self.assertTrue(entry.verify())
        
        # Tamper with data
        entry.data["block_number"] = 99999
        
        # Should fail verification
        self.assertFalse(entry.verify())
    
    def test_recovery_manager(self):
        """Recovery manager should handle recovery correctly."""
        from vel_crash_recovery import WriteAheadLog, CrashRecoveryManager, JournalEntryType
        
        with tempfile.TemporaryDirectory() as tmpdir:
            wal = WriteAheadLog(wal_path=tmpdir)
            
            # Add entries and checkpoint
            wal.append(JournalEntryType.NONCE_ALLOCATED, 
                      {"wallet": "0x123", "chain_id": 1, "nonce": 0, "intent_id": "i1"})
            wal.create_checkpoint({"nonces": {"0x123": 0}})
            wal.append(JournalEntryType.NONCE_ALLOCATED,
                      {"wallet": "0x123", "chain_id": 1, "nonce": 1, "intent_id": "i2"})
            
            # Recovery
            recovery = CrashRecoveryManager(wal)
            result = recovery.recover()
            
            self.assertTrue(result.success)
            self.assertEqual(result.entries_replayed, 1)


class TestSecurityMiddleware(unittest.TestCase):
    """Test security middleware."""
    
    @classmethod
    def setUpClass(cls):
        """Check if Flask is available."""
        try:
            import flask
            cls.flask_available = True
        except ImportError:
            cls.flask_available = False
    
    def test_rate_limiter_allows_normal_traffic(self):
        """Rate limiter should allow normal traffic."""
        if not self.flask_available:
            self.skipTest("Flask not installed")
        from vel_security_middleware import TokenBucketRateLimiter
        
        limiter = TokenBucketRateLimiter(requests_per_minute=60, burst_size=10)
        
        # First 10 requests should be allowed
        for _ in range(10):
            allowed, info = limiter.is_allowed("test_client")
            self.assertTrue(allowed)
    
    def test_rate_limiter_blocks_excessive_traffic(self):
        """Rate limiter should block excessive traffic."""
        if not self.flask_available:
            self.skipTest("Flask not installed")
        from vel_security_middleware import TokenBucketRateLimiter
        
        limiter = TokenBucketRateLimiter(requests_per_minute=60, burst_size=5)
        
        # Exhaust burst
        for _ in range(5):
            limiter.is_allowed("burst_client")
        
        # Next should be blocked
        allowed, info = limiter.is_allowed("burst_client")
        self.assertFalse(allowed)
    
    def test_replay_protector(self):
        """Replay protector should detect duplicate nonces."""
        if not self.flask_available:
            self.skipTest("Flask not installed")
        from vel_security_middleware import ReplayProtector
        
        protector = ReplayProtector(ttl_seconds=60)
        
        # First use should succeed
        valid, reason = protector.check_and_record("unique_nonce_123456")
        self.assertTrue(valid)
        self.assertEqual(reason, "ok")
        
        # Second use should fail
        valid, reason = protector.check_and_record("unique_nonce_123456")
        self.assertFalse(valid)
        self.assertEqual(reason, "nonce_reused")
    
    def test_signature_verifier(self):
        """Signature verifier should validate signatures correctly."""
        if not self.flask_available:
            self.skipTest("Flask not installed")
        from vel_security_middleware import SignatureVerifier
        import hmac
        import hashlib
        
        secret = "test_secret_key"
        verifier = SignatureVerifier(secret_key=secret)
        
        timestamp = str(int(time.time()))
        method = "POST"
        path = "/api/trade"
        body = b'{"token": "ETH", "amount": 1.0}'
        
        # Generate valid signature
        message = f"{timestamp}{method}{path}".encode('utf-8') + body
        signature = hmac.new(
            secret.encode('utf-8'),
            message,
            hashlib.sha256
        ).hexdigest()
        
        # Should verify
        valid, reason = verifier.verify(signature, timestamp, method, path, body)
        self.assertTrue(valid)
        self.assertEqual(reason, "ok")
    
    def test_key_rotation_manager(self):
        """Key rotation manager should rotate keys correctly."""
        if not self.flask_available:
            self.skipTest("Flask not installed")
        from vel_security_middleware import KeyRotationManager
        
        manager = KeyRotationManager(overlap_seconds=60)
        
        # Add initial key
        manager.add_key("key_v1", "secret_value_1")
        
        # Validate key
        valid, key_id = manager.validate_key("secret_value_1")
        self.assertTrue(valid)
        self.assertEqual(key_id, "key_v1")
        
        # Rotate to new key
        manager.rotate_key("key_v1", "key_v2", "secret_value_2")
        
        # Both keys should work during overlap period
        valid_old, _ = manager.validate_key("secret_value_1")
        valid_new, _ = manager.validate_key("secret_value_2")
        self.assertTrue(valid_old)
        self.assertTrue(valid_new)


class TestTransactionQueueLock(unittest.TestCase):
    """Test transaction queue locking."""
    
    def test_queue_ordering(self):
        """Transactions should queue in order."""
        from vel_distributed_locks import (
            DistributedLockManager, TransactionQueueLock
        )
        
        lock_manager = DistributedLockManager()
        queue = TransactionQueueLock(lock_manager)
        
        # Enqueue multiple transactions
        pos1 = queue.enqueue("0x123", 1, "tx_1")
        pos2 = queue.enqueue("0x123", 1, "tx_2")
        pos3 = queue.enqueue("0x123", 1, "tx_3")
        
        self.assertEqual(pos1, 0)
        self.assertEqual(pos2, 1)
        self.assertEqual(pos3, 2)


class TestStateLedgerIntegration(unittest.TestCase):
    """Integration tests for state ledger."""
    
    @classmethod
    def setUpClass(cls):
        """Check if web3 is available."""
        try:
            import web3
            cls.web3_available = True
        except ImportError:
            cls.web3_available = False
    
    def test_ledger_persistence(self):
        """State ledger should persist data correctly."""
        if not self.web3_available:
            self.skipTest("web3 not installed")
        from vel_state_ledger import StateLedger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/test_ledger.db"
            
            # Create ledger and add balance
            ledger = StateLedger(ledger_path=db_path)
            ledger.update_balance("0x123", 1, "native", Decimal("10.5"))
            
            # Retrieve balance
            balance = ledger.get_balance("0x123", 1, "native")
            self.assertIsNotNone(balance)
            self.assertEqual(balance.balance, Decimal("10.5"))
            
            ledger.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
