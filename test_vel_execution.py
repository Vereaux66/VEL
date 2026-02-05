#!/usr/bin/env python3
"""
VEL Production Execution Core - Test Suite
==========================================

Comprehensive tests for all execution core components.
"""

import unittest
from decimal import Decimal

from vel_execution_core import Intent, IntentType
from vel_risk_kernel import RiskKernel
from vel_nonce_manager import NonceManager, TransactionJournalEntry
from vel_state_ledger import StateLedger
from vel_signer import MockSigner, MultiWalletSigner
from vel_circuit_breaker import CircuitBreakerManager, HaltReason
from vel_execution_queue import ExecutionQueue, IntentPriority


class TestIntentValidation(unittest.TestCase):
    """Test intent validation."""
    
    def test_valid_swap_intent(self):
        """Test valid swap intent passes validation."""
        intent = Intent(
            intent_id="test_001",
            intent_type=IntentType.SWAP,
            wallet_address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
            chain_id=1,
            parameters={
                "token_in": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                "token_out": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                "amount_in": "1000.0"
            }
        )
        
        is_valid, error = intent.validate_schema()
        self.assertTrue(is_valid)
        self.assertIsNone(error)
    
    def test_invalid_swap_missing_params(self):
        """Test swap intent with missing parameters fails."""
        intent = Intent(
            intent_id="test_002",
            intent_type=IntentType.SWAP,
            wallet_address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
            chain_id=1,
            parameters={"token_in": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"}
        )
        
        is_valid, error = intent.validate_schema()
        self.assertFalse(is_valid)
        self.assertIsNotNone(error)
        self.assertIn("token_out", error)


class TestRiskKernel(unittest.TestCase):
    """Test risk kernel functionality."""
    
    def setUp(self):
        """Set up risk kernel for tests."""
        self.risk_kernel = RiskKernel(
            portfolio_value_usd=Decimal("1000000"),
            enable_strict_mode=True
        )
    
    def test_initial_state(self):
        """Test initial risk state."""
        state = self.risk_kernel.get_current_state()
        self.assertEqual(state["total_drawdown_usd"], "0")
        self.assertEqual(len(state["asset_exposures"]), 0)
    
    def test_exposure_update(self):
        """Test exposure tracking."""
        self.risk_kernel.update_exposure(
            chain_id=1,
            protocol="uniswap_v3",
            asset="1:WETH",
            value_usd=Decimal("100000")
        )
        
        state = self.risk_kernel.get_current_state()
        self.assertIn(1, state["chain_exposures"])  # Check for integer key
        self.assertIn("uniswap_v3", state["protocol_exposures"])
    
    def test_loss_recording(self):
        """Test loss recording and drawdown tracking."""
        self.risk_kernel.record_loss(Decimal("5000"))
        self.assertEqual(self.risk_kernel.total_drawdown_usd, Decimal("5000"))


class TestCircuitBreaker(unittest.TestCase):
    """Test circuit breaker functionality."""
    
    def setUp(self):
        """Set up circuit breaker for tests."""
        self.cb = CircuitBreakerManager()
    
    def test_initial_state(self):
        """Test initial circuit breaker state."""
        self.assertFalse(self.cb.is_halted())
    
    def test_manual_halt(self):
        """Test manual halt."""
        self.cb.manual_halt("Test halt")
        self.assertTrue(self.cb.is_halted())
        
        state = self.cb.get_state()
        self.assertEqual(state["halt_reason"], "manual")
    
    def test_resume(self):
        """Test resume after halt."""
        self.cb.manual_halt("Test halt")
        self.assertTrue(self.cb.is_halted())
        
        self.cb.resume()
        self.assertFalse(self.cb.is_halted())
    
    def test_chain_halt(self):
        """Test per-chain halt."""
        self.cb.trigger_halt(HaltReason.CHAIN_RPC_FAILURE, chain_id=1)
        self.assertTrue(self.cb.is_chain_halted(1))
        self.assertFalse(self.cb.is_chain_halted(56))
        self.assertFalse(self.cb.is_halted())  # Global not halted


class TestSigner(unittest.TestCase):
    """Test signer implementations."""
    
    def test_mock_signer(self):
        """Test mock signer."""
        signer = MockSigner()
        self.assertTrue(signer.is_available())
        
        wallets = signer.get_supported_wallets()
        self.assertGreater(len(wallets), 0)
        
        signed = signer.sign_transaction(
            chain_id=1,
            wallet_address=wallets[0],
            transaction={"to": "0x123", "value": 0}
        )
        self.assertIsNotNone(signed)
    
    def test_multi_wallet_signer(self):
        """Test multi-wallet signer."""
        multi = MultiWalletSigner()
        mock = MockSigner()
        
        wallet = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
        multi.register_wallet(wallet, mock)
        
        self.assertIn(wallet.lower(), multi.get_supported_wallets())


class TestStateLedger(unittest.TestCase):
    """Test state ledger functionality."""
    
    def setUp(self):
        """Set up state ledger for tests."""
        self.ledger = StateLedger(ledger_path=":memory:")
    
    def test_balance_update(self):
        """Test balance update."""
        wallet = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
        success = self.ledger.update_balance(
            wallet_address=wallet,
            chain_id=1,
            token_address="native",
            balance=Decimal("10.0")
        )
        self.assertTrue(success)
        
        balance = self.ledger.get_balance(wallet, 1, "native")
        self.assertIsNotNone(balance)
        self.assertEqual(balance.balance, Decimal("10.0"))
    
    def test_pnl_recording(self):
        """Test PnL recording."""
        wallet = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0"
        success = self.ledger.record_pnl(
            wallet_address=wallet,
            chain_id=1,
            intent_id="test_001",
            execution_id="exec_001",
            realized_pnl=Decimal("100"),
            gas_spent=Decimal("10"),
            gas_expected=Decimal("8")
        )
        self.assertTrue(success)
        
        total_pnl = self.ledger.get_total_pnl(wallet, 1)
        self.assertEqual(total_pnl, Decimal("90"))  # 100 - 10


class TestExecutionQueue(unittest.TestCase):
    """Test execution queue functionality."""
    
    def setUp(self):
        """Set up execution queue for tests."""
        self.queue = ExecutionQueue(max_queue_depth=100, worker_threads=2)
        self.processed = []
        
        def handler(intent_data):
            self.processed.append(intent_data["intent_id"])
            return True
        
        self.queue.set_execution_handler(handler)
    
    def test_enqueue(self):
        """Test intent enqueuing."""
        success = self.queue.enqueue(
            intent_id="test_001",
            wallet_address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
            intent_data={"intent_id": "test_001"},
            priority=IntentPriority.NORMAL
        )
        self.assertTrue(success)
        self.assertGreater(self.queue.get_queue_depth(), 0)
    
    def test_metrics(self):
        """Test queue metrics."""
        metrics = self.queue.get_metrics()
        self.assertIn("queue_depth", metrics)
        self.assertIn("total_queued", metrics)
        self.assertIn("worker_count", metrics)


class TestNonceManager(unittest.TestCase):
    """Test nonce manager functionality."""
    
    def setUp(self):
        """Set up nonce manager for tests."""
        self.nonce_manager = NonceManager(journal_path=":memory:")
    
    def test_journal_entry(self):
        """Test journal entry creation."""
        entry = TransactionJournalEntry(
            journal_id="journal_001",
            intent_id="intent_001",
            execution_id="exec_001",
            chain_id=1,
            wallet_address="0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0",
            nonce=0,
            tx_hash="0x123",
            simulation_passed=True
        )
        
        success = self.nonce_manager.journal_transaction(entry)
        self.assertTrue(success)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestIntentValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestRiskKernel))
    suite.addTests(loader.loadTestsFromTestCase(TestCircuitBreaker))
    suite.addTests(loader.loadTestsFromTestCase(TestSigner))
    suite.addTests(loader.loadTestsFromTestCase(TestStateLedger))
    suite.addTests(loader.loadTestsFromTestCase(TestExecutionQueue))
    suite.addTests(loader.loadTestsFromTestCase(TestNonceManager))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    import sys
    success = run_tests()
    sys.exit(0 if success else 1)
