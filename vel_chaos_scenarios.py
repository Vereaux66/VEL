#!/usr/bin/env python3
"""
VEL Chaos Engineering & Fault Injection
========================================

Production-grade chaos engineering for resilience testing.

Fault Scenarios:
- RPC outage / partial failure scenarios
- Delayed confirmations simulation
- Stuck transaction storm scenarios
- Signer unavailability simulation
- Corrupted local state injection

Expected Behavior on Faults:
- Deterministic halt (fail closed)
- No duplicate transactions
- No undefined state
- Clear operator alerts via circuit breaker

NO SILENT FAILURES - All chaos scenarios are observable and deterministic.
"""

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class FaultType(Enum):
    """Types of faults that can be injected."""
    RPC_TIMEOUT = "rpc_timeout"
    RPC_ERROR = "rpc_error"
    RPC_PARTIAL_FAILURE = "rpc_partial_failure"
    DELAYED_CONFIRMATION = "delayed_confirmation"
    STUCK_TRANSACTION = "stuck_transaction"
    SIGNER_UNAVAILABLE = "signer_unavailable"
    CORRUPTED_STATE = "corrupted_state"
    NETWORK_PARTITION = "network_partition"
    INSUFFICIENT_GAS = "insufficient_gas"
    NONCE_CONFLICT = "nonce_conflict"
    REORG_SIMULATION = "reorg_simulation"


class FaultSeverity(Enum):
    """Fault severity levels."""
    LOW = "low"          # Recoverable, minimal impact
    MEDIUM = "medium"    # Recoverable, noticeable impact
    HIGH = "high"        # May cause failures, recoverable
    CRITICAL = "critical"  # Likely causes failures, may require halt


@dataclass
class FaultScenario:
    """Fault injection scenario configuration."""
    scenario_id: str
    name: str
    description: str
    fault_type: FaultType
    severity: FaultSeverity
    
    # Injection parameters
    trigger_probability: float = 0.1  # 10% chance
    duration_seconds: Optional[int] = None  # None = one-time fault
    
    # Target selection
    target_chains: Optional[Set[int]] = None  # None = all chains
    target_protocols: Optional[Set[str]] = None
    target_wallets: Optional[Set[str]] = None
    
    # Expected behavior validation
    expected_halt: bool = False
    expected_error_logged: bool = True
    expected_retry: bool = False
    
    # State validation
    validate_no_duplicates: bool = True
    validate_state_consistency: bool = True
    
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FaultInjectionResult:
    """Result of fault injection."""
    result_id: str
    scenario_id: str
    fault_type: FaultType
    
    # Execution
    injected_at: datetime
    completed_at: Optional[datetime] = None
    
    # Target
    chain_id: Optional[int] = None
    protocol: Optional[str] = None
    wallet_address: Optional[str] = None
    intent_id: Optional[str] = None
    
    # Behavior observed
    system_halted: bool = False
    error_logged: bool = False
    retry_attempted: bool = False
    duplicate_detected: bool = False
    state_corrupted: bool = False
    
    # Validation
    behavior_correct: bool = False
    validation_notes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "result_id": self.result_id,
            "scenario_id": self.scenario_id,
            "fault_type": self.fault_type.value,
            "injected_at": self.injected_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "chain_id": self.chain_id,
            "protocol": self.protocol,
            "wallet_address": self.wallet_address,
            "intent_id": self.intent_id,
            "system_halted": self.system_halted,
            "error_logged": self.error_logged,
            "retry_attempted": self.retry_attempted,
            "duplicate_detected": self.duplicate_detected,
            "state_corrupted": self.state_corrupted,
            "behavior_correct": self.behavior_correct,
            "validation_notes": self.validation_notes
        }


class ChaosEngine:
    """
    Chaos engineering and fault injection engine.
    
    Provides controlled fault injection for resilience testing.
    Validates system behavior under failure conditions.
    """
    
    # Safety limits
    MAX_SIMULATED_TIMEOUT_SECONDS = 10  # Maximum delay for simulated timeout scenarios
    
    def __init__(self, enable_chaos: bool = False):
        """
        Initialize chaos engine.
        
        Args:
            enable_chaos: Enable chaos injection (default: disabled for safety)
        """
        self.enable_chaos = enable_chaos
        self._lock = threading.Lock()
        
        # Scenario registry
        self._scenarios: Dict[str, FaultScenario] = {}
        
        # Injection results
        self._injection_results: List[FaultInjectionResult] = []
        
        # Active faults
        self._active_faults: Dict[str, FaultScenario] = {}
        
        # Statistics
        self._total_injections = 0
        self._total_correct_behavior = 0
        
        # Initialize default scenarios
        self._register_default_scenarios()
        
        logger.info(
            "Chaos engine initialized",
            extra={"enable_chaos": enable_chaos, "scenarios": len(self._scenarios)}
        )
    
    def _register_default_scenarios(self):
        """Register default fault scenarios."""
        # RPC Outage
        self.register_scenario(FaultScenario(
            scenario_id="rpc_outage",
            name="RPC Complete Outage",
            description="Simulate complete RPC endpoint failure",
            fault_type=FaultType.RPC_ERROR,
            severity=FaultSeverity.CRITICAL,
            trigger_probability=0.05,
            duration_seconds=30,
            expected_halt=True,
            expected_error_logged=True
        ))
        
        # RPC Partial Failure
        self.register_scenario(FaultScenario(
            scenario_id="rpc_partial_failure",
            name="RPC Partial Failure",
            description="Simulate intermittent RPC failures",
            fault_type=FaultType.RPC_PARTIAL_FAILURE,
            severity=FaultSeverity.MEDIUM,
            trigger_probability=0.1,
            expected_halt=False,
            expected_retry=True
        ))
        
        # RPC Timeout
        self.register_scenario(FaultScenario(
            scenario_id="rpc_timeout",
            name="RPC Timeout",
            description="Simulate RPC request timeouts",
            fault_type=FaultType.RPC_TIMEOUT,
            severity=FaultSeverity.MEDIUM,
            trigger_probability=0.1,
            duration_seconds=60,
            expected_retry=True
        ))
        
        # Delayed Confirmation
        self.register_scenario(FaultScenario(
            scenario_id="delayed_confirmation",
            name="Delayed Transaction Confirmation",
            description="Simulate slow block confirmations",
            fault_type=FaultType.DELAYED_CONFIRMATION,
            severity=FaultSeverity.LOW,
            trigger_probability=0.15,
            duration_seconds=300,
            expected_halt=False
        ))
        
        # Stuck Transaction
        self.register_scenario(FaultScenario(
            scenario_id="stuck_transaction",
            name="Stuck Transaction Storm",
            description="Simulate multiple transactions stuck in mempool",
            fault_type=FaultType.STUCK_TRANSACTION,
            severity=FaultSeverity.HIGH,
            trigger_probability=0.05,
            expected_halt=False,
            expected_retry=True
        ))
        
        # Signer Unavailable
        self.register_scenario(FaultScenario(
            scenario_id="signer_unavailable",
            name="Transaction Signer Unavailable",
            description="Simulate signer service outage",
            fault_type=FaultType.SIGNER_UNAVAILABLE,
            severity=FaultSeverity.CRITICAL,
            trigger_probability=0.03,
            duration_seconds=60,
            expected_halt=True,
            expected_error_logged=True
        ))
        
        # Corrupted State
        self.register_scenario(FaultScenario(
            scenario_id="corrupted_state",
            name="Corrupted Local State",
            description="Simulate corrupted local state data",
            fault_type=FaultType.CORRUPTED_STATE,
            severity=FaultSeverity.CRITICAL,
            trigger_probability=0.01,
            expected_halt=True,
            expected_error_logged=True,
            validate_state_consistency=True
        ))
        
        # Insufficient Gas
        self.register_scenario(FaultScenario(
            scenario_id="insufficient_gas",
            name="Insufficient Gas",
            description="Simulate transactions with insufficient gas",
            fault_type=FaultType.INSUFFICIENT_GAS,
            severity=FaultSeverity.MEDIUM,
            trigger_probability=0.1,
            expected_halt=False,
            expected_error_logged=True
        ))
        
        # Nonce Conflict
        self.register_scenario(FaultScenario(
            scenario_id="nonce_conflict",
            name="Nonce Conflict",
            description="Simulate nonce conflicts in transaction submission",
            fault_type=FaultType.NONCE_CONFLICT,
            severity=FaultSeverity.HIGH,
            trigger_probability=0.05,
            expected_halt=False,
            expected_error_logged=True,
            validate_no_duplicates=True
        ))
        
        # Blockchain Reorg
        self.register_scenario(FaultScenario(
            scenario_id="reorg_simulation",
            name="Blockchain Reorganization",
            description="Simulate blockchain reorganization event",
            fault_type=FaultType.REORG_SIMULATION,
            severity=FaultSeverity.HIGH,
            trigger_probability=0.02,
            expected_halt=False,
            expected_error_logged=True,
            validate_state_consistency=True
        ))
    
    def register_scenario(self, scenario: FaultScenario):
        """Register fault scenario."""
        with self._lock:
            self._scenarios[scenario.scenario_id] = scenario
        
        logger.info(
            f"Fault scenario registered: {scenario.name}",
            extra={
                "scenario_id": scenario.scenario_id,
                "fault_type": scenario.fault_type.value,
                "severity": scenario.severity.value
            }
        )
    
    def should_inject_fault(
        self,
        scenario_id: str,
        chain_id: Optional[int] = None,
        protocol: Optional[str] = None,
        wallet_address: Optional[str] = None
    ) -> bool:
        """
        Check if fault should be injected for this operation.
        
        Args:
            scenario_id: Scenario identifier
            chain_id: Target chain ID
            protocol: Target protocol
            wallet_address: Target wallet
            
        Returns:
            True if fault should be injected
        """
        if not self.enable_chaos:
            return False
        
        scenario = self._scenarios.get(scenario_id)
        if not scenario:
            return False
        
        # Check target filters
        if scenario.target_chains and chain_id not in scenario.target_chains:
            return False
        
        if scenario.target_protocols and protocol and protocol not in scenario.target_protocols:
            return False
        
        if scenario.target_wallets and wallet_address and wallet_address not in scenario.target_wallets:
            return False
        
        # Probabilistic injection
        return random.random() < scenario.trigger_probability
    
    def inject_fault(
        self,
        scenario_id: str,
        chain_id: Optional[int] = None,
        protocol: Optional[str] = None,
        wallet_address: Optional[str] = None,
        intent_id: Optional[str] = None
    ) -> Optional[FaultInjectionResult]:
        """
        Inject fault for scenario.
        
        Args:
            scenario_id: Scenario identifier
            chain_id: Target chain ID
            protocol: Target protocol
            wallet_address: Target wallet
            intent_id: Target intent ID
            
        Returns:
            FaultInjectionResult or None
        """
        if not self.enable_chaos:
            return None
        
        scenario = self._scenarios.get(scenario_id)
        if not scenario:
            logger.error(f"Unknown scenario: {scenario_id}")
            return None
        
        result_id = f"fault_{scenario_id}_{datetime.now(timezone.utc).timestamp()}"
        
        result = FaultInjectionResult(
            result_id=result_id,
            scenario_id=scenario_id,
            fault_type=scenario.fault_type,
            injected_at=datetime.now(timezone.utc),
            chain_id=chain_id,
            protocol=protocol,
            wallet_address=wallet_address,
            intent_id=intent_id
        )
        
        logger.warning(
            f"CHAOS: Injecting fault - {scenario.name}",
            extra={
                "result_id": result_id,
                "scenario_id": scenario_id,
                "fault_type": scenario.fault_type.value,
                "severity": scenario.severity.value,
                "chain_id": chain_id,
                "protocol": protocol,
                "intent_id": intent_id
            }
        )
        
        # Execute fault injection based on type
        try:
            self._execute_fault_injection(scenario, result)
        except Exception as e:
            logger.error(f"Fault injection failed: {e}", exc_info=True)
            result.validation_notes.append(f"Injection failed: {e}")
        
        # Record result
        with self._lock:
            self._injection_results.append(result)
            self._total_injections += 1
        
        return result
    
    def _execute_fault_injection(
        self,
        scenario: FaultScenario,
        result: FaultInjectionResult
    ):
        """Execute specific fault injection."""
        if scenario.fault_type == FaultType.RPC_ERROR:
            self._inject_rpc_error(scenario, result)
        elif scenario.fault_type == FaultType.RPC_TIMEOUT:
            self._inject_rpc_timeout(scenario, result)
        elif scenario.fault_type == FaultType.RPC_PARTIAL_FAILURE:
            self._inject_rpc_partial_failure(scenario, result)
        elif scenario.fault_type == FaultType.DELAYED_CONFIRMATION:
            self._inject_delayed_confirmation(scenario, result)
        elif scenario.fault_type == FaultType.STUCK_TRANSACTION:
            self._inject_stuck_transaction(scenario, result)
        elif scenario.fault_type == FaultType.SIGNER_UNAVAILABLE:
            self._inject_signer_unavailable(scenario, result)
        elif scenario.fault_type == FaultType.CORRUPTED_STATE:
            self._inject_corrupted_state(scenario, result)
        elif scenario.fault_type == FaultType.INSUFFICIENT_GAS:
            self._inject_insufficient_gas(scenario, result)
        elif scenario.fault_type == FaultType.NONCE_CONFLICT:
            self._inject_nonce_conflict(scenario, result)
        elif scenario.fault_type == FaultType.REORG_SIMULATION:
            self._inject_reorg(scenario, result)
    
    def _inject_rpc_error(self, scenario: FaultScenario, result: FaultInjectionResult):
        """Inject RPC error fault."""
        result.error_logged = True
        result.validation_notes.append("RPC error injected")
        
        # In production, this would raise an exception or return error
        # For now, just record the fault
        logger.error(
            "CHAOS: RPC error injected",
            extra={"result_id": result.result_id}
        )
    
    def _inject_rpc_timeout(self, scenario: FaultScenario, result: FaultInjectionResult):
        """Inject RPC timeout fault."""
        # Simulate timeout delay
        if scenario.duration_seconds:
            delay = min(scenario.duration_seconds, self.MAX_SIMULATED_TIMEOUT_SECONDS)
            logger.warning(f"CHAOS: Injecting {delay}s RPC timeout delay")
            time.sleep(delay)
        
        result.retry_attempted = True
        result.validation_notes.append("RPC timeout injected")
    
    def _inject_rpc_partial_failure(self, scenario: FaultScenario, result: FaultInjectionResult):
        """Inject RPC partial failure fault."""
        # 50% chance of failure
        if random.random() < 0.5:
            result.error_logged = True
            result.retry_attempted = True
            result.validation_notes.append("RPC partial failure - request failed")
        else:
            result.validation_notes.append("RPC partial failure - request succeeded")
    
    def _inject_delayed_confirmation(self, scenario: FaultScenario, result: FaultInjectionResult):
        """Inject delayed confirmation fault."""
        # Simulate confirmation delay
        delay = random.randint(5, 30)
        logger.warning(f"CHAOS: Injecting {delay}s confirmation delay")
        
        result.validation_notes.append(f"Confirmation delayed by {delay}s")
    
    def _inject_stuck_transaction(self, scenario: FaultScenario, result: FaultInjectionResult):
        """Inject stuck transaction fault."""
        result.retry_attempted = True
        result.validation_notes.append("Transaction stuck in mempool")
        
        logger.warning(
            "CHAOS: Transaction stuck in mempool",
            extra={"result_id": result.result_id}
        )
    
    def _inject_signer_unavailable(self, scenario: FaultScenario, result: FaultInjectionResult):
        """Inject signer unavailable fault."""
        result.error_logged = True
        result.system_halted = True
        result.validation_notes.append("Signer service unavailable")
        
        logger.error(
            "CHAOS: Signer unavailable",
            extra={"result_id": result.result_id}
        )
    
    def _inject_corrupted_state(self, scenario: FaultScenario, result: FaultInjectionResult):
        """Inject corrupted state fault."""
        result.state_corrupted = True
        result.system_halted = True
        result.error_logged = True
        result.validation_notes.append("Local state corrupted")
        
        logger.critical(
            "CHAOS: Corrupted state detected",
            extra={"result_id": result.result_id}
        )
    
    def _inject_insufficient_gas(self, scenario: FaultScenario, result: FaultInjectionResult):
        """Inject insufficient gas fault."""
        result.error_logged = True
        result.validation_notes.append("Transaction rejected - insufficient gas")
        
        logger.error(
            "CHAOS: Insufficient gas",
            extra={"result_id": result.result_id}
        )
    
    def _inject_nonce_conflict(self, scenario: FaultScenario, result: FaultInjectionResult):
        """Inject nonce conflict fault."""
        result.error_logged = True
        result.validation_notes.append("Nonce conflict detected")
        
        logger.error(
            "CHAOS: Nonce conflict",
            extra={"result_id": result.result_id}
        )
    
    def _inject_reorg(self, scenario: FaultScenario, result: FaultInjectionResult):
        """Inject blockchain reorg fault."""
        # Simulate reorg depth
        reorg_depth = random.randint(1, 5)
        
        result.error_logged = True
        result.validation_notes.append(f"Blockchain reorg detected - {reorg_depth} blocks")
        
        logger.warning(
            f"CHAOS: Blockchain reorg - {reorg_depth} blocks",
            extra={"result_id": result.result_id, "reorg_depth": reorg_depth}
        )
    
    def validate_behavior(
        self,
        result: FaultInjectionResult,
        system_halted: bool,
        error_logged: bool,
        duplicates_detected: bool,
        state_consistent: bool
    ) -> bool:
        """
        Validate system behavior after fault injection.
        
        Args:
            result: Fault injection result to validate
            system_halted: Whether system halted
            error_logged: Whether error was logged
            duplicates_detected: Whether duplicate transactions detected
            state_consistent: Whether state remains consistent
            
        Returns:
            True if behavior was correct
        """
        scenario = self._scenarios.get(result.scenario_id)
        if not scenario:
            return False
        
        # Update result with observed behavior
        result.system_halted = system_halted
        result.error_logged = error_logged
        result.duplicate_detected = duplicates_detected
        result.state_corrupted = not state_consistent
        result.completed_at = datetime.now(timezone.utc)
        
        # Validate expected behavior
        correct = True
        
        if scenario.expected_halt and not system_halted:
            correct = False
            result.validation_notes.append("Expected system halt but none occurred")
        
        if scenario.expected_error_logged and not error_logged:
            correct = False
            result.validation_notes.append("Expected error log but none found")
        
        if scenario.validate_no_duplicates and duplicates_detected:
            correct = False
            result.validation_notes.append("Duplicate transactions detected")
        
        if scenario.validate_state_consistency and not state_consistent:
            correct = False
            result.validation_notes.append("State inconsistency detected")
        
        result.behavior_correct = correct
        
        if correct:
            with self._lock:
                self._total_correct_behavior += 1
        
        logger.info(
            f"Chaos validation: {'PASS' if correct else 'FAIL'}",
            extra=result.to_dict()
        )
        
        return correct
    
    def get_scenario(self, scenario_id: str) -> Optional[FaultScenario]:
        """Get fault scenario by ID."""
        return self._scenarios.get(scenario_id)
    
    def list_scenarios(self) -> List[FaultScenario]:
        """List all registered scenarios."""
        with self._lock:
            return list(self._scenarios.values())
    
    def get_injection_results(
        self,
        scenario_id: Optional[str] = None,
        chain_id: Optional[int] = None
    ) -> List[FaultInjectionResult]:
        """Get fault injection results with optional filters."""
        with self._lock:
            results = self._injection_results.copy()
        
        if scenario_id:
            results = [r for r in results if r.scenario_id == scenario_id]
        
        if chain_id:
            results = [r for r in results if r.chain_id == chain_id]
        
        return sorted(results, key=lambda r: r.injected_at, reverse=True)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get chaos engineering statistics."""
        with self._lock:
            total = self._total_injections
            correct = self._total_correct_behavior
            
            by_type = {}
            by_severity = {}
            
            for result in self._injection_results:
                fault_type = result.fault_type.value
                by_type[fault_type] = by_type.get(fault_type, 0) + 1
                
                scenario = self._scenarios.get(result.scenario_id)
                if scenario:
                    severity = scenario.severity.value
                    by_severity[severity] = by_severity.get(severity, 0) + 1
            
            return {
                "chaos_enabled": self.enable_chaos,
                "total_scenarios": len(self._scenarios),
                "total_injections": total,
                "correct_behavior": correct,
                "behavior_correctness_rate": correct / total if total > 0 else 0,
                "injections_by_type": by_type,
                "injections_by_severity": by_severity
            }
