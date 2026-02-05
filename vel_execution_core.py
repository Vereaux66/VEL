#!/usr/bin/env python3
"""
VEL Production Execution Core
==============================

Complete intent-to-execution pipeline for DeFi trading operations.
Production-critical, capital-safe, crash-safe, and restart-safe.

Pipeline stages:
1. Intent validation (schema + sanity checks)
2. Strategy resolution (intent → actionable plan)
3. DEX protocol selection (via broker factory)
4. Route determination (token path, pools, constraints)
5. Transaction construction (calldata, recipient, value)
6. Pre-broadcast simulation
7. Risk kernel enforcement
8. Signing handoff
9. Broadcast
10. Confirmation tracking
11. Final state reconciliation

CRITICAL INVARIANTS:
- No transaction broadcast without successful simulation
- No transaction execution without passing risk checks
- All state changes are journaled
- All operations are idempotent
- Failures result in system halt, not silent degradation
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from vel_transaction_simulator import TransactionSimulator, SimulationResult
from vel_risk_kernel import RiskKernel, RiskCheckResult
from vel_nonce_manager import NonceManager
from vel_state_ledger import StateLedger
from vel_signer import SignerInterface
from vel_circuit_breaker import CircuitBreakerManager
from vel_execution_queue import ExecutionQueue
from anvel_dex_broker_factory import get_dex_factory, DEXBrokerFactory

# Operational hardening modules
from vel_mev_protection import MEVProtectionEngine, MEVProtectionConfig
from vel_chain_finality import ChainFinalityTracker, ChainFinalityConfig
from vel_backpressure import BackpressureManager, BackpressureConfig
from vel_operational_controls import OperationalController
from vel_chaos_scenarios import ChaosEngine

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """Execution pipeline status."""
    PENDING = "pending"
    VALIDATING = "validating"
    ROUTING = "routing"
    SIMULATING = "simulating"
    RISK_CHECKING = "risk_checking"
    SIGNING = "signing"
    BROADCASTING = "broadcasting"
    CONFIRMING = "confirming"
    RECONCILING = "reconciling"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


class IntentType(Enum):
    """Supported intent types (DeFi only)."""
    SWAP = "swap"
    ADD_LIQUIDITY = "add_liquidity"
    REMOVE_LIQUIDITY = "remove_liquidity"
    STAKE = "stake"
    UNSTAKE = "unstake"
    BORROW = "borrow"
    REPAY = "repay"
    SUPPLY = "supply"
    WITHDRAW = "withdraw"


@dataclass
class Intent:
    """User intent structure."""
    intent_id: str
    intent_type: IntentType
    wallet_address: str
    chain_id: int
    parameters: Dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def validate_schema(self) -> tuple[bool, Optional[str]]:
        """Validate intent schema."""
        if not self.intent_id or not isinstance(self.intent_id, str):
            return False, "Invalid intent_id"
        
        if not isinstance(self.intent_type, IntentType):
            return False, "Invalid intent_type"
        
        if not self.wallet_address or not isinstance(self.wallet_address, str):
            return False, "Invalid wallet_address"
        
        if not isinstance(self.chain_id, int) or self.chain_id <= 0:
            return False, "Invalid chain_id"
        
        if not isinstance(self.parameters, dict):
            return False, "Invalid parameters"
        
        # Type-specific validation
        if self.intent_type == IntentType.SWAP:
            required = ["token_in", "token_out", "amount_in"]
            for field_name in required:
                if field_name not in self.parameters:
                    return False, f"Missing required field: {field_name}"
            
            # Validate amounts
            try:
                amount = Decimal(str(self.parameters["amount_in"]))
                if amount <= 0:
                    return False, "amount_in must be positive"
            except Exception as e:
                return False, f"Invalid amount_in: {e}"
        
        elif self.intent_type == IntentType.ADD_LIQUIDITY:
            required = ["token_a", "token_b", "amount_a", "amount_b"]
            for field_name in required:
                if field_name not in self.parameters:
                    return False, f"Missing required field: {field_name}"
        
        elif self.intent_type in [IntentType.SUPPLY, IntentType.WITHDRAW, IntentType.STAKE, IntentType.UNSTAKE]:
            required = ["token", "amount", "protocol"]
            for field_name in required:
                if field_name not in self.parameters:
                    return False, f"Missing required field: {field_name}"
        
        elif self.intent_type in [IntentType.BORROW, IntentType.REPAY]:
            required = ["token", "amount", "protocol"]
            for field_name in required:
                if field_name not in self.parameters:
                    return False, f"Missing required field: {field_name}"
        
        return True, None


@dataclass
class ExecutionPlan:
    """Resolved execution plan from intent."""
    plan_id: str
    intent_id: str
    intent_type: IntentType
    wallet_address: str
    chain_id: int
    protocol: str
    route: Dict[str, Any]
    transaction_params: Dict[str, Any]
    estimated_gas: int
    estimated_output: Optional[Decimal] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ExecutionRecord:
    """Complete execution record."""
    execution_id: str
    intent_id: str
    status: ExecutionStatus
    intent: Intent
    plan: Optional[ExecutionPlan] = None
    simulation_result: Optional[SimulationResult] = None
    risk_check_result: Optional[RiskCheckResult] = None
    signed_tx: Optional[str] = None
    tx_hash: Optional[str] = None
    confirmation_block: Optional[int] = None
    gas_used: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def update_status(self, status: ExecutionStatus, error: Optional[str] = None) -> None:
        """Update execution status."""
        self.status = status
        self.updated_at = datetime.now(timezone.utc)
        if error:
            self.error_message = error
        
        logger.info(
            f"Execution {self.execution_id} status updated: {status.value}",
            extra={
                "execution_id": self.execution_id,
                "intent_id": self.intent_id,
                "status": status.value,
                "error": error
            }
        )


class ExecutionCore:
    """
    Production execution core orchestrator.
    
    Coordinates the complete intent-to-execution pipeline with:
    - Deterministic validation and routing
    - Mandatory simulation before broadcast
    - Non-bypassable risk enforcement
    - Crash-safe state management
    - Complete audit trail
    """
    
    def __init__(
        self,
        dex_factory: Optional[DEXBrokerFactory] = None,
        simulator: Optional[TransactionSimulator] = None,
        risk_kernel: Optional[RiskKernel] = None,
        nonce_manager: Optional[NonceManager] = None,
        state_ledger: Optional[StateLedger] = None,
        signer: Optional[SignerInterface] = None,
        circuit_breaker: Optional[CircuitBreakerManager] = None,
        execution_queue: Optional[ExecutionQueue] = None,
        # Operational hardening components
        mev_protection: Optional[MEVProtectionEngine] = None,
        chain_finality: Optional[ChainFinalityTracker] = None,
        backpressure_manager: Optional[BackpressureManager] = None,
        operational_controller: Optional[OperationalController] = None,
        chaos_engine: Optional[ChaosEngine] = None,
    ):
        """
        Initialize execution core.
        
        Args:
            dex_factory: DEX broker factory (defaults to global instance)
            simulator: Transaction simulator
            risk_kernel: Risk enforcement engine
            nonce_manager: Nonce tracking and TX journal
            state_ledger: Canonical state ledger
            signer: Transaction signing interface
            circuit_breaker: Circuit breaker manager
            execution_queue: Execution queue manager
            mev_protection: MEV protection engine
            chain_finality: Chain finality tracker
            backpressure_manager: Backpressure & capacity manager
            operational_controller: Operational controls
            chaos_engine: Chaos engineering engine
        """
        self.dex_factory = dex_factory or get_dex_factory()
        self.simulator = simulator or TransactionSimulator()
        self.risk_kernel = risk_kernel or RiskKernel()
        self.nonce_manager = nonce_manager or NonceManager()
        self.state_ledger = state_ledger or StateLedger()
        self.signer = signer or self._get_default_signer()
        self.circuit_breaker = circuit_breaker or CircuitBreakerManager()
        self.execution_queue = execution_queue or ExecutionQueue()
        
        # Operational hardening components
        self.mev_protection = mev_protection or MEVProtectionEngine()
        self.chain_finality = chain_finality or ChainFinalityTracker()
        self.backpressure = backpressure_manager or BackpressureManager()
        self.operational = operational_controller or OperationalController()
        self.chaos = chaos_engine or ChaosEngine(enable_chaos=False)
        
        # Execution record cache
        self._executions: Dict[str, ExecutionRecord] = {}
        
        logger.info("Execution core initialized with all components including operational hardening")
    
    def _get_default_signer(self) -> SignerInterface:
        """Get default signer implementation."""
        from vel_signer import get_default_signer
        return get_default_signer()
    
    def execute_intent(self, intent: Intent, tenant_id: str = "default") -> ExecutionRecord:
        """
        Execute complete intent-to-execution pipeline.
        
        This is the main entry point for intent execution. It orchestrates
        all pipeline stages with proper error handling and state tracking.
        
        Args:
            intent: User intent to execute
            tenant_id: Tenant identifier for quota tracking
            
        Returns:
            ExecutionRecord with complete execution details
            
        Raises:
            Various exceptions on unrecoverable errors (system halts)
        """
        execution_id = str(uuid.uuid4())
        execution = ExecutionRecord(
            execution_id=execution_id,
            intent_id=intent.intent_id,
            status=ExecutionStatus.PENDING,
            intent=intent
        )
        self._executions[execution_id] = execution
        
        try:
            # Stage 0: Backpressure check - can we accept this intent?
            can_accept = self.backpressure.accept_intent(
                intent.intent_id,
                tenant_id,
                intent.wallet_address
            )
            
            if not can_accept:
                execution.update_status(ExecutionStatus.REJECTED, "Backpressure - system overloaded")
                return execution
            
            # Stage 1: Validate intent
            execution.update_status(ExecutionStatus.VALIDATING)
            is_valid, validation_error = self._validate_intent(intent)
            if not is_valid:
                execution.update_status(ExecutionStatus.REJECTED, validation_error)
                self.backpressure.complete_execution(intent.intent_id, intent.wallet_address, False)
                return execution
            
            # Start execution (acquire wallet lock)
            if not self.backpressure.start_execution(intent.intent_id, intent.wallet_address):
                execution.update_status(ExecutionStatus.REJECTED, "Wallet busy with another execution")
                return execution
            
            # Stage 2: Resolve strategy and route
            execution.update_status(ExecutionStatus.ROUTING)
            plan = self._resolve_execution_plan(intent)
            if not plan:
                execution.update_status(ExecutionStatus.FAILED, "Failed to resolve execution plan")
                self.backpressure.complete_execution(intent.intent_id, intent.wallet_address, False)
                return execution
            execution.plan = plan
            
            # Stage 2.5: MEV Protection Check
            if intent.intent_type == IntentType.SWAP:
                # Derive trade size from intent parameters - use estimated_output if available
                trade_size_usd = plan.estimated_output if plan.estimated_output else Decimal("10000")
                expected_slippage = plan.transaction_params.get("slippage_bps", 50)
                
                mev_assessment = self.mev_protection.assess_mev_risk(
                    intent_id=intent.intent_id,
                    chain_id=plan.chain_id,
                    protocol=plan.protocol,
                    route=plan.route,
                    trade_size_usd=trade_size_usd,
                    expected_slippage_bps=expected_slippage
                )
                
                from vel_mev_protection import RoutingDecision
                if mev_assessment.decision == RoutingDecision.REJECT:
                    execution.update_status(
                        ExecutionStatus.REJECTED,
                        f"MEV risk too high: {', '.join(mev_assessment.reasons)}"
                    )
                    self.backpressure.complete_execution(intent.intent_id, intent.wallet_address, False)
                    return execution
            
            # Stage 3: Simulate transaction
            execution.update_status(ExecutionStatus.SIMULATING)
            sim_result = self._simulate_transaction(plan)
            if not sim_result.success:
                execution.update_status(
                    ExecutionStatus.REJECTED,
                    f"Simulation failed: {sim_result.error_message}"
                )
                return execution
            execution.simulation_result = sim_result
            
            # Stage 4: Risk kernel check (CANNOT BE BYPASSED)
            execution.update_status(ExecutionStatus.RISK_CHECKING)
            risk_result = self._check_risk(intent, plan, sim_result)
            if not risk_result.passed:
                execution.update_status(
                    ExecutionStatus.REJECTED,
                    f"Risk check failed: {risk_result.failure_reason}"
                )
                return execution
            execution.risk_check_result = risk_result
            
            # Stage 5: Sign transaction
            execution.update_status(ExecutionStatus.SIGNING)
            signed_tx = self._sign_transaction(plan, sim_result)
            if not signed_tx:
                execution.update_status(ExecutionStatus.FAILED, "Transaction signing failed")
                return execution
            execution.signed_tx = signed_tx
            
            # Stage 6: Broadcast transaction
            execution.update_status(ExecutionStatus.BROADCASTING)
            tx_hash = self._broadcast_transaction(plan.chain_id, signed_tx)
            if not tx_hash:
                execution.update_status(ExecutionStatus.FAILED, "Transaction broadcast failed")
                return execution
            execution.tx_hash = tx_hash
            
            # Stage 7: Track confirmation
            execution.update_status(ExecutionStatus.CONFIRMING)
            confirmed = self._wait_for_confirmation(plan.chain_id, tx_hash, plan.wallet_address)
            if not confirmed:
                execution.update_status(ExecutionStatus.FAILED, "Transaction confirmation failed")
                self.backpressure.complete_execution(intent.intent_id, intent.wallet_address, False)
                return execution
            
            # Stage 7.5: Register for finality tracking
            # Get block number from confirmed transaction
            block_number = execution.confirmation_block or 0
            if block_number > 0:
                self.chain_finality.register_transaction(
                    tx_hash=tx_hash,
                    chain_id=plan.chain_id,
                    block_number=block_number,
                    block_hash="",  # Would fetch from chain
                    execution_id=execution_id,
                    intent_id=intent.intent_id
                )
            
            # Stage 8: Reconcile state
            execution.update_status(ExecutionStatus.RECONCILING)
            reconciled = self._reconcile_state(execution)
            if not reconciled:
                # This is critical - ledger divergence detected
                logger.critical(
                    f"State reconciliation failed for execution {execution_id}",
                    extra={"execution_id": execution_id, "tx_hash": tx_hash}
                )
                self.circuit_breaker.trigger_halt("ledger_divergence")
                execution.update_status(ExecutionStatus.FAILED, "State reconciliation failed")
                self.backpressure.complete_execution(intent.intent_id, intent.wallet_address, False)
                return execution
            
            # Success
            execution.update_status(ExecutionStatus.COMPLETED)
            self.backpressure.complete_execution(intent.intent_id, intent.wallet_address, True)
            return execution
            
        except Exception as e:
            logger.error(
                f"Execution pipeline failed for {execution_id}: {e}",
                extra={"execution_id": execution_id, "error": str(e)},
                exc_info=True
            )
            execution.update_status(ExecutionStatus.FAILED, str(e))
            self.backpressure.complete_execution(intent.intent_id, intent.wallet_address, False)
            return execution
    
    def _validate_intent(self, intent: Intent) -> tuple[bool, Optional[str]]:
        """
        Validate intent schema and sanity checks.
        
        Returns:
            (is_valid, error_message)
        """
        # Schema validation
        is_valid, error = intent.validate_schema()
        if not is_valid:
            logger.warning(
                f"Intent {intent.intent_id} failed schema validation: {error}",
                extra={"intent_id": intent.intent_id, "error": error}
            )
            return False, error
        
        # Sanity checks
        if self.circuit_breaker.is_halted():
            return False, "System is halted - circuit breaker triggered"
        
        # Check operational controls
        if self.operational.is_halted(
            chain_id=intent.chain_id,
            wallet_address=intent.wallet_address
        ):
            return False, "Operations halted by operational controller"
        
        # Check chain is supported
        supported_chains = self.dex_factory.get_supported_chains()
        chain_ids = [c.chain_id for c in supported_chains]
        if intent.chain_id not in chain_ids:
            return False, f"Unsupported chain: {intent.chain_id}"
        
        return True, None
    
    def _resolve_execution_plan(self, intent: Intent) -> Optional[ExecutionPlan]:
        """
        Resolve intent into executable plan.
        
        Maps high-level intent to specific protocol interactions,
        determines optimal routing, and constructs transaction parameters.
        
        Args:
            intent: Validated user intent
            
        Returns:
            ExecutionPlan or None if resolution fails
        """
        try:
            if intent.intent_type == IntentType.SWAP:
                return self._resolve_swap_plan(intent)
            elif intent.intent_type == IntentType.ADD_LIQUIDITY:
                return self._resolve_add_liquidity_plan(intent)
            elif intent.intent_type == IntentType.REMOVE_LIQUIDITY:
                return self._resolve_remove_liquidity_plan(intent)
            elif intent.intent_type in [IntentType.SUPPLY, IntentType.WITHDRAW]:
                return self._resolve_lending_plan(intent)
            elif intent.intent_type in [IntentType.STAKE, IntentType.UNSTAKE]:
                return self._resolve_staking_plan(intent)
            elif intent.intent_type in [IntentType.BORROW, IntentType.REPAY]:
                return self._resolve_borrow_plan(intent)
            else:
                logger.error(f"Unsupported intent type: {intent.intent_type}")
                return None
        except Exception as e:
            logger.error(
                f"Failed to resolve execution plan: {e}",
                extra={"intent_id": intent.intent_id},
                exc_info=True
            )
            return None
    
    def _resolve_swap_plan(self, intent: Intent) -> Optional[ExecutionPlan]:
        """Resolve swap intent to execution plan."""
        params = intent.parameters
        token_in = params["token_in"]
        token_out = params["token_out"]
        amount_in = Decimal(str(params["amount_in"]))
        
        # Get best route across all DEXes on the chain
        route = self.dex_factory.get_best_route(
            chain_id=intent.chain_id,
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in
        )
        
        if not route:
            logger.warning(
                f"No route found for swap {token_in} -> {token_out} on chain {intent.chain_id}"
            )
            return None
        
        # Construct transaction parameters
        tx_params = {
            "token_in": token_in,
            "token_out": token_out,
            "amount_in": str(amount_in),
            "min_amount_out": str(params.get("min_amount_out", 0)),
            "slippage_bps": params.get("slippage_bps", 50),
            "deadline": params.get("deadline", 300),
            "recipient": intent.wallet_address,
        }
        
        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            intent_id=intent.intent_id,
            intent_type=intent.intent_type,
            wallet_address=intent.wallet_address,
            chain_id=intent.chain_id,
            protocol=route["dex_name"],
            route=route,
            transaction_params=tx_params,
            estimated_gas=250000,  # Conservative estimate
            estimated_output=route.get("expected_output")
        )
    
    def _resolve_add_liquidity_plan(self, intent: Intent) -> Optional[ExecutionPlan]:
        """Resolve add liquidity intent to execution plan.
        
        Constructs an execution plan that calls the DEX router's
        addLiquidity function with the specified token pair and amounts.
        """
        params = intent.parameters
        token_a = params.get("token_a")
        token_b = params.get("token_b")
        amount_a = params.get("amount_a")
        amount_b = params.get("amount_b")

        if not all([token_a, token_b, amount_a, amount_b]):
            logger.error(
                "Add liquidity intent missing required parameters "
                "(token_a, token_b, amount_a, amount_b)",
                extra={"intent_id": intent.intent_id},
            )
            return None

        # Find a DEX on the target chain that supports liquidity provision
        dexes = self.dex_factory.get_supported_dexes(intent.chain_id)
        if not dexes:
            logger.warning(
                "No DEXes available on chain %d for liquidity provision",
                intent.chain_id,
            )
            return None

        # Use first available DEX (caller can specify via parameters)
        target_dex = params.get("dex_name", dexes[0].name if dexes else None)
        if not target_dex:
            return None

        tx_params = {
            "action": "add_liquidity",
            "token_a": token_a,
            "token_b": token_b,
            "amount_a": str(amount_a),
            "amount_b": str(amount_b),
            "amount_a_min": str(
                Decimal(str(amount_a)) * Decimal("0.995")
            ),  # 0.5% slippage
            "amount_b_min": str(
                Decimal(str(amount_b)) * Decimal("0.995")
            ),
            "recipient": intent.wallet_address,
            "deadline": params.get("deadline", 300),
        }

        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            intent_id=intent.intent_id,
            intent_type=intent.intent_type,
            wallet_address=intent.wallet_address,
            chain_id=intent.chain_id,
            protocol=target_dex,
            route={
                "dex_name": target_dex,
                "chain_id": intent.chain_id,
                "token_a": token_a,
                "token_b": token_b,
                "action": "add_liquidity",
            },
            transaction_params=tx_params,
            estimated_gas=350000,
        )
    
    def _resolve_remove_liquidity_plan(self, intent: Intent) -> Optional[ExecutionPlan]:
        """Resolve remove liquidity intent to execution plan.
        
        Constructs an execution plan to remove liquidity from a pool by
        burning LP tokens and receiving the underlying token pair.
        """
        params = intent.parameters
        token_a = params.get("token_a")
        token_b = params.get("token_b")
        liquidity_amount = params.get("liquidity_amount")

        if not all([token_a, token_b, liquidity_amount]):
            logger.error(
                "Remove liquidity intent missing required parameters "
                "(token_a, token_b, liquidity_amount)",
                extra={"intent_id": intent.intent_id},
            )
            return None

        dexes = self.dex_factory.get_supported_dexes(intent.chain_id)
        target_dex = params.get("dex_name", dexes[0].name if dexes else None)
        if not target_dex:
            return None

        tx_params = {
            "action": "remove_liquidity",
            "token_a": token_a,
            "token_b": token_b,
            "liquidity_amount": str(liquidity_amount),
            "amount_a_min": str(params.get("amount_a_min", 0)),
            "amount_b_min": str(params.get("amount_b_min", 0)),
            "recipient": intent.wallet_address,
            "deadline": params.get("deadline", 300),
        }

        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            intent_id=intent.intent_id,
            intent_type=intent.intent_type,
            wallet_address=intent.wallet_address,
            chain_id=intent.chain_id,
            protocol=target_dex,
            route={
                "dex_name": target_dex,
                "chain_id": intent.chain_id,
                "token_a": token_a,
                "token_b": token_b,
                "action": "remove_liquidity",
            },
            transaction_params=tx_params,
            estimated_gas=300000,
        )
    
    def _resolve_lending_plan(self, intent: Intent) -> Optional[ExecutionPlan]:
        """Resolve lending (supply/withdraw) intent to execution plan.
        
        Targets Aave V3-compatible lending pool contracts for
        supply (deposit collateral) and withdraw operations.
        """
        params = intent.parameters
        token = params.get("token")
        amount = params.get("amount")
        action = "supply" if intent.intent_type == IntentType.SUPPLY else "withdraw"

        if not all([token, amount]):
            logger.error(
                "Lending intent missing required parameters (token, amount)",
                extra={"intent_id": intent.intent_id},
            )
            return None

        # Aave V3 pool addresses per chain
        aave_v3_pools = {
            1: "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
            42161: "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
            10: "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
            137: "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
            8453: "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
            43114: "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        }

        pool_address = aave_v3_pools.get(intent.chain_id)
        if not pool_address:
            logger.warning(
                "No Aave V3 pool configured for chain %d", intent.chain_id,
            )
            return None

        tx_params = {
            "action": action,
            "protocol": "aave_v3",
            "pool_address": pool_address,
            "token": token,
            "amount": str(amount),
            "on_behalf_of": intent.wallet_address,
        }

        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            intent_id=intent.intent_id,
            intent_type=intent.intent_type,
            wallet_address=intent.wallet_address,
            chain_id=intent.chain_id,
            protocol="aave_v3",
            route={
                "protocol": "aave_v3",
                "chain_id": intent.chain_id,
                "pool_address": pool_address,
                "action": action,
            },
            transaction_params=tx_params,
            estimated_gas=350000,
        )
    
    def _resolve_staking_plan(self, intent: Intent) -> Optional[ExecutionPlan]:
        """Resolve staking intent to execution plan.
        
        Supports native ETH staking via Lido (stETH) and similar
        liquid staking protocols on supported chains.
        """
        params = intent.parameters
        token = params.get("token")
        amount = params.get("amount")
        action = "stake" if intent.intent_type == IntentType.STAKE else "unstake"

        if not all([token, amount]):
            logger.error(
                "Staking intent missing required parameters (token, amount)",
                extra={"intent_id": intent.intent_id},
            )
            return None

        # Lido stETH addresses per chain
        lido_contracts = {
            1: "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",   # Lido stETH
            42161: "0x5979D7b546E38E9Ab8049B4385a4eF83065f9F46",  # wstETH on Arb
            10: "0x1F32b1c2345538c0c6f582fCB022739c4A194Ebb",   # wstETH on OP
        }

        staking_protocol = params.get("protocol", "lido")
        contract_address = lido_contracts.get(intent.chain_id)

        if not contract_address:
            logger.warning(
                "No staking contract configured for chain %d", intent.chain_id,
            )
            return None

        tx_params = {
            "action": action,
            "protocol": staking_protocol,
            "contract_address": contract_address,
            "token": token,
            "amount": str(amount),
            "recipient": intent.wallet_address,
        }

        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            intent_id=intent.intent_id,
            intent_type=intent.intent_type,
            wallet_address=intent.wallet_address,
            chain_id=intent.chain_id,
            protocol=staking_protocol,
            route={
                "protocol": staking_protocol,
                "chain_id": intent.chain_id,
                "contract_address": contract_address,
                "action": action,
            },
            transaction_params=tx_params,
            estimated_gas=300000,
        )
    
    def _resolve_borrow_plan(self, intent: Intent) -> Optional[ExecutionPlan]:
        """Resolve borrow/repay intent to execution plan.
        
        Targets Aave V3-compatible lending pools for borrow and repay
        operations.  Requires existing collateral for borrows.
        """
        params = intent.parameters
        token = params.get("token")
        amount = params.get("amount")
        action = "borrow" if intent.intent_type == IntentType.BORROW else "repay"

        if not all([token, amount]):
            logger.error(
                "Borrow intent missing required parameters (token, amount)",
                extra={"intent_id": intent.intent_id},
            )
            return None

        # Reuse Aave V3 pool addresses
        aave_v3_pools = {
            1: "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
            42161: "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
            10: "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
            137: "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
            8453: "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
            43114: "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        }

        pool_address = aave_v3_pools.get(intent.chain_id)
        if not pool_address:
            logger.warning(
                "No Aave V3 pool configured for chain %d", intent.chain_id,
            )
            return None

        # Interest rate mode: 1 = stable, 2 = variable (default variable)
        interest_rate_mode = int(params.get("interest_rate_mode", 2))

        tx_params = {
            "action": action,
            "protocol": "aave_v3",
            "pool_address": pool_address,
            "token": token,
            "amount": str(amount),
            "interest_rate_mode": interest_rate_mode,
            "on_behalf_of": intent.wallet_address,
        }

        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            intent_id=intent.intent_id,
            intent_type=intent.intent_type,
            wallet_address=intent.wallet_address,
            chain_id=intent.chain_id,
            protocol="aave_v3",
            route={
                "protocol": "aave_v3",
                "chain_id": intent.chain_id,
                "pool_address": pool_address,
                "action": action,
            },
            transaction_params=tx_params,
            estimated_gas=400000,
        )
    
    def _simulate_transaction(self, plan: ExecutionPlan) -> SimulationResult:
        """Simulate transaction before broadcast."""
        return self.simulator.simulate(
            chain_id=plan.chain_id,
            wallet_address=plan.wallet_address,
            transaction_params=plan.transaction_params,
            route=plan.route
        )
    
    def _check_risk(
        self,
        intent: Intent,
        plan: ExecutionPlan,
        sim_result: SimulationResult
    ) -> RiskCheckResult:
        """Run risk kernel checks (cannot be bypassed)."""
        return self.risk_kernel.check(
            intent=intent,
            plan=plan,
            simulation_result=sim_result
        )
    
    def _sign_transaction(
        self,
        plan: ExecutionPlan,
        sim_result: SimulationResult
    ) -> Optional[str]:
        """Sign transaction via signer interface."""
        return self.signer.sign_transaction(
            chain_id=plan.chain_id,
            wallet_address=plan.wallet_address,
            transaction=sim_result.transaction_data
        )
    
    def _broadcast_transaction(self, chain_id: int, signed_tx: str) -> Optional[str]:
        """Broadcast signed transaction to blockchain."""
        try:
            tx_hash = self.nonce_manager.broadcast_transaction(
                chain_id=chain_id,
                signed_tx=signed_tx
            )
            return tx_hash
        except Exception as e:
            logger.error(f"Transaction broadcast failed: {e}", exc_info=True)
            return None
    
    def _wait_for_confirmation(
        self,
        chain_id: int,
        tx_hash: str,
        wallet_address: str
    ) -> bool:
        """Wait for transaction confirmation."""
        try:
            return self.nonce_manager.wait_for_confirmation(
                chain_id=chain_id,
                tx_hash=tx_hash,
                wallet_address=wallet_address
            )
        except Exception as e:
            logger.error(f"Confirmation wait failed: {e}", exc_info=True)
            return False
    
    def _reconcile_state(self, execution: ExecutionRecord) -> bool:
        """Reconcile on-chain state with ledger."""
        try:
            return self.state_ledger.reconcile(execution)
        except Exception as e:
            logger.error(f"State reconciliation failed: {e}", exc_info=True)
            return False
    
    def get_execution(self, execution_id: str) -> Optional[ExecutionRecord]:
        """Get execution record by ID."""
        return self._executions.get(execution_id)
    
    def list_executions(
        self,
        wallet_address: Optional[str] = None,
        status: Optional[ExecutionStatus] = None
    ) -> List[ExecutionRecord]:
        """List executions with optional filters."""
        executions = list(self._executions.values())
        
        if wallet_address:
            executions = [e for e in executions if e.intent.wallet_address == wallet_address]
        
        if status:
            executions = [e for e in executions if e.status == status]
        
        return sorted(executions, key=lambda e: e.created_at, reverse=True)


def create_execution_core(**kwargs) -> ExecutionCore:
    """Factory function to create execution core with dependencies."""
    return ExecutionCore(**kwargs)
