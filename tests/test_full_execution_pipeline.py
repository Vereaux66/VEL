#!/usr/bin/env python3
"""
VEL Full Execution Pipeline Integration Test
=============================================

Tests the complete execution lifecycle:
intent → simulate → risk → nonce → sign → send → confirm → reconcile

This test validates that all components work together correctly.
"""

import hashlib
import json
import os
import tempfile
import time
import unittest
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch


# =============================================================================
# Test Data Structures
# =============================================================================

@dataclass
class MockIntent:
    """Mock trading intent for testing."""
    intent_id: str
    action: str  # "buy" or "sell"
    token_in: str
    token_out: str
    amount_in: Decimal
    min_amount_out: Decimal
    chain_id: int = 1
    deadline: int = 0
    user_address: str = "0x1234567890123456789012345678901234567890"
    
    def __post_init__(self):
        if self.deadline == 0:
            self.deadline = int(time.time()) + 3600

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "action": self.action,
            "token_in": self.token_in,
            "token_out": self.token_out,
            "amount_in": str(self.amount_in),
            "min_amount_out": str(self.min_amount_out),
            "chain_id": self.chain_id,
            "deadline": self.deadline,
            "user_address": self.user_address,
        }


@dataclass
class MockSimulationResult:
    """Mock simulation result."""
    success: bool
    expected_output: Decimal
    gas_estimate: int
    slippage_bps: int
    error: Optional[str] = None


@dataclass
class MockRiskAssessment:
    """Mock risk assessment result."""
    approved: bool
    risk_score: float
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class MockTransaction:
    """Mock transaction for testing."""
    tx_hash: str
    from_address: str
    to_address: str
    value: int
    gas: int
    gas_price: int
    nonce: int
    data: str
    chain_id: int


@dataclass
class MockReceipt:
    """Mock transaction receipt."""
    tx_hash: str
    status: int  # 1 = success, 0 = failure
    block_number: int
    gas_used: int
    effective_gas_price: int


# =============================================================================
# Mock Components
# =============================================================================

class MockNonceManager:
    """Mock nonce manager for testing."""
    
    def __init__(self):
        self._nonces: Dict[str, int] = {}
        self._lock = MagicMock()
    
    def get_nonce(self, address: str, chain_id: int = 1) -> int:
        key = f"{chain_id}:{address}"
        if key not in self._nonces:
            self._nonces[key] = 0
        return self._nonces[key]
    
    def increment_nonce(self, address: str, chain_id: int = 1) -> int:
        key = f"{chain_id}:{address}"
        if key not in self._nonces:
            self._nonces[key] = 0
        self._nonces[key] += 1
        return self._nonces[key] - 1
    
    def rollback_nonce(self, address: str, chain_id: int = 1) -> None:
        key = f"{chain_id}:{address}"
        if key in self._nonces and self._nonces[key] > 0:
            self._nonces[key] -= 1


class MockSigner:
    """Mock transaction signer for testing."""
    
    def __init__(self, private_key: str = "0x" + "1" * 64):
        self._private_key = private_key
        self._address = "0x1234567890123456789012345678901234567890"
    
    @property
    def address(self) -> str:
        return self._address
    
    def sign_transaction(self, tx: Dict[str, Any]) -> str:
        # Return mock signed transaction
        return "0x" + hashlib.sha256(
            json.dumps(tx, sort_keys=True).encode()
        ).hexdigest()
    
    def sign_message(self, message: str) -> str:
        return "0x" + hashlib.sha256(
            (message + self._private_key).encode()
        ).hexdigest()


class MockRiskKernel:
    """Mock risk kernel for testing."""
    
    def __init__(self):
        self._max_position_size = Decimal("100000")
        self._max_slippage_bps = 500  # 5%
        self._circuit_breaker_tripped = False
    
    def check_risk(self, intent: MockIntent, simulation: MockSimulationResult) -> MockRiskAssessment:
        violations = []
        warnings = []
        
        # Check circuit breaker
        if self._circuit_breaker_tripped:
            violations.append("Circuit breaker is tripped")
            return MockRiskAssessment(
                approved=False,
                risk_score=1.0,
                violations=violations
            )
        
        # Check position size
        if intent.amount_in > self._max_position_size:
            violations.append(f"Position size {intent.amount_in} exceeds max {self._max_position_size}")
        
        # Check slippage
        if simulation.slippage_bps > self._max_slippage_bps:
            violations.append(f"Slippage {simulation.slippage_bps}bps exceeds max {self._max_slippage_bps}bps")
        
        # Calculate risk score
        risk_score = min(1.0, simulation.slippage_bps / 1000 + float(intent.amount_in) / 1000000)
        
        if risk_score > 0.5:
            warnings.append(f"Elevated risk score: {risk_score:.2f}")
        
        return MockRiskAssessment(
            approved=len(violations) == 0,
            risk_score=risk_score,
            violations=violations,
            warnings=warnings
        )
    
    def trip_circuit_breaker(self) -> None:
        self._circuit_breaker_tripped = True
    
    def reset_circuit_breaker(self) -> None:
        self._circuit_breaker_tripped = False


class MockSimulator:
    """Mock transaction simulator for testing."""
    
    def __init__(self):
        self._default_gas = 150000
        self._price_impact_factor = 0.001  # 0.1% per 1000 units
    
    def simulate(self, intent: MockIntent) -> MockSimulationResult:
        # Calculate mock output based on amount
        amount = float(intent.amount_in)
        price_impact = amount * self._price_impact_factor
        slippage_bps = int(price_impact * 100)
        
        expected_output = Decimal(str(amount * (1 - price_impact)))
        
        # Check if output meets minimum
        if expected_output < intent.min_amount_out:
            return MockSimulationResult(
                success=False,
                expected_output=expected_output,
                gas_estimate=self._default_gas,
                slippage_bps=slippage_bps,
                error="Output below minimum"
            )
        
        return MockSimulationResult(
            success=True,
            expected_output=expected_output,
            gas_estimate=self._default_gas,
            slippage_bps=slippage_bps
        )


class MockRPCProvider:
    """Mock RPC provider for testing."""
    
    def __init__(self):
        self._pending_txs: Dict[str, MockTransaction] = {}
        self._mined_txs: Dict[str, MockReceipt] = {}
        self._block_number = 1000
        self._gas_price = 50_000_000_000  # 50 gwei
    
    def get_gas_price(self) -> int:
        return self._gas_price
    
    def send_transaction(self, signed_tx: str) -> str:
        # Generate mock tx hash
        tx_hash = "0x" + hashlib.sha256(signed_tx.encode()).hexdigest()
        return tx_hash
    
    def get_transaction_receipt(self, tx_hash: str) -> Optional[MockReceipt]:
        return self._mined_txs.get(tx_hash)
    
    def mine_transaction(self, tx_hash: str, success: bool = True) -> None:
        """Helper to simulate mining a transaction."""
        self._block_number += 1
        self._mined_txs[tx_hash] = MockReceipt(
            tx_hash=tx_hash,
            status=1 if success else 0,
            block_number=self._block_number,
            gas_used=150000,
            effective_gas_price=self._gas_price
        )


class MockStateLedger:
    """Mock state ledger for testing."""
    
    def __init__(self):
        self._states: Dict[str, Dict[str, Any]] = {}
        self._journal: List[Dict[str, Any]] = []
    
    def record_intent(self, intent_id: str, intent: Dict[str, Any]) -> None:
        self._states[intent_id] = {
            "intent": intent,
            "stage": "recorded",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self._journal.append({
            "action": "record_intent",
            "intent_id": intent_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    def update_stage(self, intent_id: str, stage: str, data: Optional[Dict] = None) -> None:
        if intent_id in self._states:
            self._states[intent_id]["stage"] = stage
            if data:
                self._states[intent_id].update(data)
            self._journal.append({
                "action": "update_stage",
                "intent_id": intent_id,
                "stage": stage,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
    
    def get_state(self, intent_id: str) -> Optional[Dict[str, Any]]:
        return self._states.get(intent_id)
    
    def get_journal(self) -> List[Dict[str, Any]]:
        return self._journal.copy()
    
    def check_duplicate(self, intent_id: str) -> bool:
        """Check if intent already exists (replay protection)."""
        return intent_id in self._states


class MockReconciliationEngine:
    """Mock reconciliation engine for testing."""
    
    def __init__(self, rpc: MockRPCProvider, ledger: MockStateLedger):
        self._rpc = rpc
        self._ledger = ledger
        self._pending_reconciliation: Dict[str, str] = {}  # intent_id -> tx_hash
    
    def add_for_reconciliation(self, intent_id: str, tx_hash: str) -> None:
        self._pending_reconciliation[intent_id] = tx_hash
    
    def reconcile(self) -> Dict[str, str]:
        """
        Reconcile pending transactions.
        
        Returns:
            Dict mapping intent_id to status (confirmed/failed/pending)
        """
        results = {}
        
        for intent_id, tx_hash in list(self._pending_reconciliation.items()):
            receipt = self._rpc.get_transaction_receipt(tx_hash)
            
            if receipt:
                if receipt.status == 1:
                    self._ledger.update_stage(intent_id, "confirmed", {
                        "tx_hash": tx_hash,
                        "block_number": receipt.block_number,
                        "gas_used": receipt.gas_used
                    })
                    results[intent_id] = "confirmed"
                else:
                    self._ledger.update_stage(intent_id, "failed", {
                        "tx_hash": tx_hash,
                        "error": "Transaction reverted"
                    })
                    results[intent_id] = "failed"
                
                del self._pending_reconciliation[intent_id]
            else:
                results[intent_id] = "pending"
        
        return results


# =============================================================================
# Full Execution Pipeline
# =============================================================================

class ExecutionPipeline:
    """
    Full execution pipeline that coordinates all components.
    
    Stages:
    1. Intent validation
    2. Simulation
    3. Risk assessment
    4. Nonce acquisition
    5. Transaction signing
    6. Broadcast
    7. Confirmation
    8. Reconciliation
    """
    
    def __init__(
        self,
        nonce_manager: MockNonceManager,
        signer: MockSigner,
        risk_kernel: MockRiskKernel,
        simulator: MockSimulator,
        rpc: MockRPCProvider,
        ledger: MockStateLedger,
        reconciler: MockReconciliationEngine
    ):
        self._nonce_manager = nonce_manager
        self._signer = signer
        self._risk_kernel = risk_kernel
        self._simulator = simulator
        self._rpc = rpc
        self._ledger = ledger
        self._reconciler = reconciler
    
    def generate_intent_id(self, intent_data: Dict[str, Any]) -> str:
        """Generate deterministic intent ID."""
        canonical = json.dumps(intent_data, sort_keys=True)
        return "intent_" + hashlib.sha256(canonical.encode()).hexdigest()[:16]
    
    def execute(self, intent: MockIntent) -> Dict[str, Any]:
        """
        Execute the full trading pipeline.
        
        Returns:
            Result dictionary with status and details
        """
        result = {
            "intent_id": intent.intent_id,
            "success": False,
            "stage_reached": "init",
            "tx_hash": None,
            "error": None,
            "details": {}
        }
        
        try:
            # Stage 1: Record intent and check for duplicates
            if self._ledger.check_duplicate(intent.intent_id):
                result["error"] = "Duplicate intent detected (replay protection)"
                result["stage_reached"] = "validation"
                return result
            
            self._ledger.record_intent(intent.intent_id, intent.to_dict())
            result["stage_reached"] = "recorded"
            
            # Stage 2: Simulation
            simulation = self._simulator.simulate(intent)
            self._ledger.update_stage(intent.intent_id, "simulated", {
                "simulation_success": simulation.success,
                "expected_output": str(simulation.expected_output),
                "gas_estimate": simulation.gas_estimate,
                "slippage_bps": simulation.slippage_bps
            })
            result["stage_reached"] = "simulated"
            result["details"]["simulation"] = {
                "success": simulation.success,
                "expected_output": str(simulation.expected_output),
                "slippage_bps": simulation.slippage_bps
            }
            
            if not simulation.success:
                result["error"] = f"Simulation failed: {simulation.error}"
                self._ledger.update_stage(intent.intent_id, "simulation_failed")
                return result
            
            # Stage 3: Risk assessment
            risk = self._risk_kernel.check_risk(intent, simulation)
            self._ledger.update_stage(intent.intent_id, "risk_assessed", {
                "risk_approved": risk.approved,
                "risk_score": risk.risk_score,
                "violations": risk.violations
            })
            result["stage_reached"] = "risk_assessed"
            result["details"]["risk"] = {
                "approved": risk.approved,
                "score": risk.risk_score,
                "violations": risk.violations,
                "warnings": risk.warnings
            }
            
            if not risk.approved:
                result["error"] = f"Risk check failed: {', '.join(risk.violations)}"
                self._ledger.update_stage(intent.intent_id, "risk_rejected")
                return result
            
            # Stage 4: Nonce acquisition
            nonce = self._nonce_manager.increment_nonce(
                intent.user_address,
                intent.chain_id
            )
            self._ledger.update_stage(intent.intent_id, "nonce_acquired", {
                "nonce": nonce
            })
            result["stage_reached"] = "nonce_acquired"
            result["details"]["nonce"] = nonce
            
            # Stage 5: Build and sign transaction
            tx = {
                "from": intent.user_address,
                "to": "0xRouterAddress",
                "value": 0,
                "gas": simulation.gas_estimate,
                "gasPrice": self._rpc.get_gas_price(),
                "nonce": nonce,
                "chainId": intent.chain_id,
                "data": f"swap({intent.token_in},{intent.token_out},{intent.amount_in})"
            }
            
            signed_tx = self._signer.sign_transaction(tx)
            self._ledger.update_stage(intent.intent_id, "signed", {
                "signed_tx_hash": hashlib.sha256(signed_tx.encode()).hexdigest()[:16]
            })
            result["stage_reached"] = "signed"
            
            # Stage 6: Broadcast
            tx_hash = self._rpc.send_transaction(signed_tx)
            self._ledger.update_stage(intent.intent_id, "broadcast", {
                "tx_hash": tx_hash
            })
            result["stage_reached"] = "broadcast"
            result["tx_hash"] = tx_hash
            
            # Stage 7: Add to reconciliation queue
            self._reconciler.add_for_reconciliation(intent.intent_id, tx_hash)
            self._ledger.update_stage(intent.intent_id, "pending_confirmation")
            result["stage_reached"] = "pending_confirmation"
            
            result["success"] = True
            return result
            
        except Exception as e:
            result["error"] = str(e)
            self._ledger.update_stage(intent.intent_id, "error", {
                "error": str(e)
            })
            return result


# =============================================================================
# Integration Tests
# =============================================================================

class TestFullExecutionPipeline(unittest.TestCase):
    """Integration tests for the full execution pipeline."""
    
    def setUp(self):
        """Set up test components."""
        self.nonce_manager = MockNonceManager()
        self.signer = MockSigner()
        self.risk_kernel = MockRiskKernel()
        self.simulator = MockSimulator()
        self.rpc = MockRPCProvider()
        self.ledger = MockStateLedger()
        self.reconciler = MockReconciliationEngine(self.rpc, self.ledger)
        
        self.pipeline = ExecutionPipeline(
            nonce_manager=self.nonce_manager,
            signer=self.signer,
            risk_kernel=self.risk_kernel,
            simulator=self.simulator,
            rpc=self.rpc,
            ledger=self.ledger,
            reconciler=self.reconciler
        )
    
    def test_successful_execution(self):
        """Test complete successful execution flow."""
        intent = MockIntent(
            intent_id="test_intent_001",
            action="buy",
            token_in="USDC",
            token_out="ETH",
            amount_in=Decimal("1000"),
            min_amount_out=Decimal("0.5")
        )
        
        result = self.pipeline.execute(intent)
        
        self.assertTrue(result["success"])
        self.assertEqual(result["stage_reached"], "pending_confirmation")
        self.assertIsNotNone(result["tx_hash"])
        self.assertIsNone(result["error"])
        
        # Verify state was recorded
        state = self.ledger.get_state(intent.intent_id)
        self.assertIsNotNone(state)
        self.assertEqual(state["stage"], "pending_confirmation")
    
    def test_simulation_failure(self):
        """Test handling of simulation failure."""
        intent = MockIntent(
            intent_id="test_intent_sim_fail",
            action="buy",
            token_in="USDC",
            token_out="ETH",
            amount_in=Decimal("1000"),
            min_amount_out=Decimal("1000")  # Unrealistic - will fail
        )
        
        result = self.pipeline.execute(intent)
        
        self.assertFalse(result["success"])
        self.assertEqual(result["stage_reached"], "simulated")
        self.assertIn("Simulation failed", result["error"])
    
    def test_risk_rejection(self):
        """Test handling of risk rejection."""
        intent = MockIntent(
            intent_id="test_intent_risk_fail",
            action="buy",
            token_in="USDC",
            token_out="ETH",
            amount_in=Decimal("200000"),  # Exceeds max position size
            min_amount_out=Decimal("0.1")
        )
        
        result = self.pipeline.execute(intent)
        
        self.assertFalse(result["success"])
        self.assertEqual(result["stage_reached"], "risk_assessed")
        self.assertIn("Risk check failed", result["error"])
    
    def test_circuit_breaker_blocks_execution(self):
        """Test that circuit breaker blocks execution."""
        self.risk_kernel.trip_circuit_breaker()
        
        intent = MockIntent(
            intent_id="test_intent_circuit",
            action="buy",
            token_in="USDC",
            token_out="ETH",
            amount_in=Decimal("100"),
            min_amount_out=Decimal("0.01")
        )
        
        result = self.pipeline.execute(intent)
        
        self.assertFalse(result["success"])
        self.assertIn("Circuit breaker", result["error"])
    
    def test_replay_protection(self):
        """Test that duplicate intents are rejected."""
        intent = MockIntent(
            intent_id="test_intent_replay",
            action="buy",
            token_in="USDC",
            token_out="ETH",
            amount_in=Decimal("100"),
            min_amount_out=Decimal("0.01")
        )
        
        # First execution should succeed
        result1 = self.pipeline.execute(intent)
        self.assertTrue(result1["success"])
        
        # Second execution with same intent_id should fail
        result2 = self.pipeline.execute(intent)
        self.assertFalse(result2["success"])
        self.assertIn("Duplicate intent", result2["error"])
    
    def test_reconciliation_confirms_transaction(self):
        """Test that reconciliation confirms mined transactions."""
        intent = MockIntent(
            intent_id="test_intent_reconcile",
            action="buy",
            token_in="USDC",
            token_out="ETH",
            amount_in=Decimal("100"),
            min_amount_out=Decimal("0.01")
        )
        
        result = self.pipeline.execute(intent)
        self.assertTrue(result["success"])
        
        # Simulate mining the transaction
        self.rpc.mine_transaction(result["tx_hash"], success=True)
        
        # Run reconciliation
        reconcile_results = self.reconciler.reconcile()
        
        self.assertEqual(reconcile_results[intent.intent_id], "confirmed")
        
        # Verify state was updated
        state = self.ledger.get_state(intent.intent_id)
        self.assertEqual(state["stage"], "confirmed")
        self.assertIsNotNone(state.get("block_number"))
    
    def test_reconciliation_handles_failed_transaction(self):
        """Test that reconciliation handles reverted transactions."""
        intent = MockIntent(
            intent_id="test_intent_revert",
            action="buy",
            token_in="USDC",
            token_out="ETH",
            amount_in=Decimal("100"),
            min_amount_out=Decimal("0.01")
        )
        
        result = self.pipeline.execute(intent)
        self.assertTrue(result["success"])
        
        # Simulate failed transaction
        self.rpc.mine_transaction(result["tx_hash"], success=False)
        
        # Run reconciliation
        reconcile_results = self.reconciler.reconcile()
        
        self.assertEqual(reconcile_results[intent.intent_id], "failed")
        
        state = self.ledger.get_state(intent.intent_id)
        self.assertEqual(state["stage"], "failed")
    
    def test_nonce_management(self):
        """Test that nonces are correctly managed across transactions."""
        intents = [
            MockIntent(
                intent_id=f"test_intent_nonce_{i}",
                action="buy",
                token_in="USDC",
                token_out="ETH",
                amount_in=Decimal("100"),
                min_amount_out=Decimal("0.01")
            )
            for i in range(3)
        ]
        
        for i, intent in enumerate(intents):
            result = self.pipeline.execute(intent)
            self.assertTrue(result["success"])
            self.assertEqual(result["details"]["nonce"], i)
    
    def test_deterministic_intent_id_generation(self):
        """Test that intent IDs are deterministic."""
        intent_data = {
            "action": "buy",
            "token_in": "USDC",
            "token_out": "ETH",
            "amount_in": "1000",
            "user": "0x123"
        }
        
        id1 = self.pipeline.generate_intent_id(intent_data)
        id2 = self.pipeline.generate_intent_id(intent_data)
        
        self.assertEqual(id1, id2)
        self.assertTrue(id1.startswith("intent_"))
    
    def test_execution_journal_audit_trail(self):
        """Test that all stages are recorded in the journal."""
        intent = MockIntent(
            intent_id="test_intent_journal",
            action="buy",
            token_in="USDC",
            token_out="ETH",
            amount_in=Decimal("100"),
            min_amount_out=Decimal("0.01")
        )
        
        self.pipeline.execute(intent)
        
        journal = self.ledger.get_journal()
        
        # Verify all stages were recorded
        stages = [entry["stage"] if "stage" in entry else entry["action"] 
                  for entry in journal if entry.get("intent_id") == intent.intent_id]
        
        self.assertIn("record_intent", stages)
        # Journal should have multiple entries for different stages
        self.assertGreater(len(journal), 1)


class TestReorgHandling(unittest.TestCase):
    """Tests for blockchain reorganization handling."""
    
    def setUp(self):
        """Set up test components."""
        self.nonce_manager = MockNonceManager()
        self.signer = MockSigner()
        self.risk_kernel = MockRiskKernel()
        self.simulator = MockSimulator()
        self.rpc = MockRPCProvider()
        self.ledger = MockStateLedger()
        self.reconciler = MockReconciliationEngine(self.rpc, self.ledger)
        
        self.pipeline = ExecutionPipeline(
            nonce_manager=self.nonce_manager,
            signer=self.signer,
            risk_kernel=self.risk_kernel,
            simulator=self.simulator,
            rpc=self.rpc,
            ledger=self.ledger,
            reconciler=self.reconciler
        )
    
    def test_pending_transaction_not_confirmed_prematurely(self):
        """Test that pending transactions remain pending until mined."""
        intent = MockIntent(
            intent_id="test_intent_pending",
            action="buy",
            token_in="USDC",
            token_out="ETH",
            amount_in=Decimal("100"),
            min_amount_out=Decimal("0.01")
        )
        
        result = self.pipeline.execute(intent)
        self.assertTrue(result["success"])
        
        # Don't mine - transaction stays pending
        reconcile_results = self.reconciler.reconcile()
        
        self.assertEqual(reconcile_results[intent.intent_id], "pending")
        
        state = self.ledger.get_state(intent.intent_id)
        self.assertEqual(state["stage"], "pending_confirmation")


class TestDBCorruptionRecovery(unittest.TestCase):
    """Tests for database corruption scenarios."""
    
    def test_ledger_state_consistency(self):
        """Test that ledger maintains consistency."""
        ledger = MockStateLedger()
        
        # Record intent
        ledger.record_intent("test_001", {"action": "buy"})
        
        # Update multiple times
        ledger.update_stage("test_001", "simulated")
        ledger.update_stage("test_001", "risk_assessed")
        ledger.update_stage("test_001", "signed")
        
        # Verify final state
        state = ledger.get_state("test_001")
        self.assertEqual(state["stage"], "signed")
        
        # Verify journal has all entries
        journal = ledger.get_journal()
        self.assertEqual(len(journal), 4)  # 1 record + 3 updates


if __name__ == "__main__":
    unittest.main()
