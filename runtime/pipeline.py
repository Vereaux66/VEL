#!/usr/bin/env python3
"""
ANVEL Execution Pipeline
========================

Standardized trading execution pipeline.
Routes all strategy outputs through risk kernel before execution.

Pipeline Flow:
1. Strategy generates signal (ExecutionPayload)
2. Payload validated and normalized
3. Risk kernel checks exposure/limits
4. Trade engine executes via broker
5. Results written to pooled trading integration

CRITICAL: No execution can bypass the risk kernel.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("anvel.runtime.pipeline")


class ExecutionStatus(Enum):
    """Execution status codes."""
    PENDING = "pending"
    VALIDATED = "validated"
    RISK_PASSED = "risk_passed"
    RISK_BLOCKED = "risk_blocked"
    EXECUTING = "executing"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SignalType(Enum):
    """Trading signal types."""
    BUY = "buy"
    SELL = "sell"
    SWAP = "swap"
    PROVIDE_LIQUIDITY = "provide_liquidity"
    REMOVE_LIQUIDITY = "remove_liquidity"


@dataclass
class ExecutionPayload:
    """Standardized execution payload for all strategies."""
    payload_id: str = field(default_factory=lambda: f"exec_{uuid.uuid4().hex[:12]}")
    strategy_id: str = "unknown"
    timestamp: float = field(default_factory=time.time)
    signal_type: SignalType = SignalType.BUY
    token_in: str = ""
    token_out: str = ""
    amount_in: Decimal = Decimal("0")
    min_amount_out: Optional[Decimal] = None
    chain_id: int = 1
    protocol: str = "uniswap_v3"
    max_slippage_bps: int = 100
    deadline_seconds: int = 300
    recipient: Optional[str] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5
    dry_run: bool = False
    
    def validate(self) -> List[str]:
        errors = []
        if not self.token_in:
            errors.append("token_in is required")
        if not self.token_out:
            errors.append("token_out is required")
        if self.amount_in <= 0:
            errors.append("amount_in must be positive")
        if self.chain_id <= 0:
            errors.append("chain_id must be positive")
        if self.max_slippage_bps < 0 or self.max_slippage_bps > 5000:
            errors.append("max_slippage_bps must be between 0 and 5000")
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload_id": self.payload_id,
            "strategy_id": self.strategy_id,
            "timestamp": self.timestamp,
            "signal_type": self.signal_type.value,
            "token_in": self.token_in,
            "token_out": self.token_out,
            "amount_in": str(self.amount_in),
            "min_amount_out": str(self.min_amount_out) if self.min_amount_out else None,
            "chain_id": self.chain_id,
            "protocol": self.protocol,
            "max_slippage_bps": self.max_slippage_bps,
            "deadline_seconds": self.deadline_seconds,
            "recipient": self.recipient,
            "extra_params": self.extra_params,
            "priority": self.priority,
            "dry_run": self.dry_run,
        }


@dataclass
class ExecutionResult:
    """Result of execution attempt."""
    payload_id: str
    status: ExecutionStatus
    timestamp: float = field(default_factory=time.time)
    tx_hash: Optional[str] = None
    amount_out: Optional[Decimal] = None
    gas_used: Optional[int] = None
    gas_price_gwei: Optional[Decimal] = None
    total_cost_usd: Optional[Decimal] = None
    slippage_bps: Optional[int] = None
    error: Optional[str] = None
    risk_violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    @property
    def success(self) -> bool:
        return self.status == ExecutionStatus.EXECUTED
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "payload_id": self.payload_id,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "success": self.success,
            "tx_hash": self.tx_hash,
            "amount_out": str(self.amount_out) if self.amount_out else None,
            "gas_used": self.gas_used,
            "gas_price_gwei": str(self.gas_price_gwei) if self.gas_price_gwei else None,
            "total_cost_usd": str(self.total_cost_usd) if self.total_cost_usd else None,
            "slippage_bps": self.slippage_bps,
            "error": self.error,
            "risk_violations": self.risk_violations,
            "warnings": self.warnings,
        }


@dataclass
class SimulationResult:
    """Simulated transaction result for risk checking."""
    expected_output: Decimal = Decimal("0")
    total_cost_wei: int = 0
    slippage_bps: int = 0
    success: bool = True
    error: Optional[str] = None


@dataclass
class ExecutionPlan:
    """Execution plan for risk checking."""
    chain_id: int = 1
    protocol: str = "uniswap_v3"
    transaction_params: Dict[str, Any] = field(default_factory=dict)
    estimated_output: Optional[Decimal] = None


class ExecutionPipeline:
    """Central execution pipeline - all trades must flow through here."""
    
    def __init__(
        self,
        risk_kernel: Optional[Any] = None,
        trade_engine: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        broker_factory: Optional[Any] = None,
        dry_run: bool = False,
    ):
        self.risk_kernel = risk_kernel
        self.trade_engine = trade_engine
        self.event_bus = event_bus
        self.broker_factory = broker_factory
        self.dry_run = dry_run
        self._history: List[ExecutionResult] = []
        self._max_history = 1000
    
    def execute(self, payload: ExecutionPayload) -> ExecutionResult:
        """Execute a trading payload through the pipeline."""
        logger.info(f"Pipeline: Processing {payload.payload_id}")
        
        result = self._validate_payload(payload)
        if result:
            return result
        
        result = self._check_risk(payload)
        if result:
            return result
        
        result = self._execute(payload)
        self._record_result(result)
        
        if result.success:
            self._update_exposures(payload, result)
        
        return result
    
    def _validate_payload(self, payload: ExecutionPayload) -> Optional[ExecutionResult]:
        errors = payload.validate()
        if errors:
            logger.warning(f"Payload validation failed: {errors}")
            return ExecutionResult(
                payload_id=payload.payload_id,
                status=ExecutionStatus.FAILED,
                error=f"Validation errors: {', '.join(errors)}",
            )
        return None
    
    def _check_risk(self, payload: ExecutionPayload) -> Optional[ExecutionResult]:
        if not self.risk_kernel and not self.dry_run:
            logger.error("Risk kernel not available - blocking execution")
            return ExecutionResult(
                payload_id=payload.payload_id,
                status=ExecutionStatus.RISK_BLOCKED,
                error="Risk kernel not available",
                risk_violations=["no_risk_kernel"],
            )
        
        if self.risk_kernel:
            intent = {"payload": payload.to_dict()}
            plan = ExecutionPlan(
                chain_id=payload.chain_id,
                protocol=payload.protocol,
                transaction_params={
                    "token_in": payload.token_in,
                    "token_out": payload.token_out,
                    "amount_in": str(payload.amount_in),
                },
                estimated_output=payload.min_amount_out or payload.amount_in,
            )
            simulation = SimulationResult(
                expected_output=payload.min_amount_out or payload.amount_in,
                total_cost_wei=21000 * 50 * 10**9,
                slippage_bps=payload.max_slippage_bps,
            )
            
            check_result = self.risk_kernel.check(intent, plan, simulation)
            
            if not check_result.passed:
                logger.warning(f"Risk check failed: {check_result.breached_limits}")
                if self.event_bus:
                    self.event_bus.publish("risk.violation", {
                        "payload_id": payload.payload_id,
                        "violations": check_result.breached_limits,
                        "timestamp": time.time(),
                    })
                return ExecutionResult(
                    payload_id=payload.payload_id,
                    status=ExecutionStatus.RISK_BLOCKED,
                    error=check_result.failure_reason,
                    risk_violations=check_result.breached_limits,
                    warnings=check_result.warnings,
                )
            logger.info(f"Risk check passed: {payload.payload_id}")
        return None
    
    def _execute(self, payload: ExecutionPayload) -> ExecutionResult:
        if self.dry_run or payload.dry_run:
            logger.info(f"DRY RUN: {payload.payload_id}")
            return ExecutionResult(
                payload_id=payload.payload_id,
                status=ExecutionStatus.EXECUTED,
                amount_out=payload.amount_in * Decimal("0.99"),
                slippage_bps=100,
                warnings=["dry_run_mode"],
            )
        
        try:
            broker = self._get_broker(payload)
            if not broker:
                return ExecutionResult(
                    payload_id=payload.payload_id,
                    status=ExecutionStatus.FAILED,
                    error=f"No broker for {payload.protocol} on chain {payload.chain_id}",
                )
            
            if self.trade_engine:
                return self._execute_via_engine(payload)
            return self._execute_via_broker(payload, broker)
        except Exception as e:
            logger.exception(f"Execution error: {e}")
            return ExecutionResult(
                payload_id=payload.payload_id,
                status=ExecutionStatus.FAILED,
                error=str(e),
            )
    
    def _execute_via_engine(self, payload: ExecutionPayload) -> ExecutionResult:
        try:
            trade_request = {
                "id": payload.payload_id,
                "action": payload.signal_type.value,
                "token_in": payload.token_in,
                "token_out": payload.token_out,
                "amount": str(payload.amount_in),
                "chain_id": payload.chain_id,
                "protocol": payload.protocol,
                "slippage_bps": payload.max_slippage_bps,
            }
            engine_result = self.trade_engine.execute_trade(trade_request)
            if engine_result.get("success"):
                return ExecutionResult(
                    payload_id=payload.payload_id,
                    status=ExecutionStatus.EXECUTED,
                    tx_hash=engine_result.get("tx_hash"),
                    amount_out=Decimal(str(engine_result.get("amount_out", 0))),
                    gas_used=engine_result.get("gas_used"),
                    slippage_bps=engine_result.get("slippage_bps"),
                )
            return ExecutionResult(
                payload_id=payload.payload_id,
                status=ExecutionStatus.FAILED,
                error=engine_result.get("error", "Trade engine failed"),
            )
        except Exception as e:
            return ExecutionResult(
                payload_id=payload.payload_id,
                status=ExecutionStatus.FAILED,
                error=str(e),
            )
    
    def _execute_via_broker(self, payload: ExecutionPayload, broker: Any) -> ExecutionResult:
        try:
            if hasattr(broker, 'swap'):
                result = broker.swap(
                    token_in=payload.token_in,
                    token_out=payload.token_out,
                    amount_in=payload.amount_in,
                    min_amount_out=payload.min_amount_out,
                    slippage_bps=payload.max_slippage_bps,
                )
            elif hasattr(broker, 'execute'):
                result = broker.execute(payload.to_dict())
            else:
                return ExecutionResult(
                    payload_id=payload.payload_id,
                    status=ExecutionStatus.FAILED,
                    error="Broker has no execution method",
                )
            if result.get("success"):
                return ExecutionResult(
                    payload_id=payload.payload_id,
                    status=ExecutionStatus.EXECUTED,
                    tx_hash=result.get("tx_hash"),
                    amount_out=Decimal(str(result.get("amount_out", 0))),
                    gas_used=result.get("gas_used"),
                )
            return ExecutionResult(
                payload_id=payload.payload_id,
                status=ExecutionStatus.FAILED,
                error=result.get("error", "Broker execution failed"),
            )
        except Exception as e:
            return ExecutionResult(
                payload_id=payload.payload_id,
                status=ExecutionStatus.FAILED,
                error=str(e),
            )
    
    def _get_broker(self, payload: ExecutionPayload) -> Optional[Any]:
        if not self.broker_factory:
            return None
        try:
            if hasattr(self.broker_factory, 'get_broker'):
                return self.broker_factory.get_broker(
                    chain_id=payload.chain_id,
                    protocol=payload.protocol,
                )
            elif hasattr(self.broker_factory, 'create'):
                return self.broker_factory.create(payload.protocol)
        except Exception as e:
            logger.error(f"Broker creation error: {e}")
        return None
    
    def _record_result(self, result: ExecutionResult) -> None:
        self._history.append(result)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        if self.event_bus:
            event_name = "trade.executed" if result.success else "trade.failed"
            self.event_bus.publish(event_name, result.to_dict())
    
    def _update_exposures(self, payload: ExecutionPayload, result: ExecutionResult) -> None:
        if not self.risk_kernel:
            return
        try:
            value_usd = result.amount_out or payload.amount_in
            self.risk_kernel.update_exposure(
                chain_id=payload.chain_id,
                protocol=payload.protocol,
                asset=f"{payload.chain_id}:{payload.token_out}",
                value_usd=value_usd,
            )
        except Exception as e:
            logger.error(f"Exposure update error: {e}")
    
    def get_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._history[-limit:]]
    
    def get_statistics(self) -> Dict[str, Any]:
        if not self._history:
            return {"total": 0}
        total = len(self._history)
        successful = sum(1 for r in self._history if r.success)
        failed = sum(1 for r in self._history if r.status == ExecutionStatus.FAILED)
        blocked = sum(1 for r in self._history if r.status == ExecutionStatus.RISK_BLOCKED)
        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "risk_blocked": blocked,
            "success_rate": successful / total if total > 0 else 0,
        }
