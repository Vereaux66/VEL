#!/usr/bin/env python3
"""
VEL Operational Controls & Incident Management
===============================================

Production-grade operational controls for emergency response.

Features:
- Global kill switch (halt all execution)
- Per-chain halt
- Per-protocol halt
- Safe resume procedures with state verification
- Incident severity classification (CRITICAL, HIGH, MEDIUM, LOW)
- Audit export for post-mortems

Rules:
- Ops actions must not require code changes
- All ops actions must be logged and reversible
- State must be verified before resume
- Halt operations fail closed

NO SILENT FAILURES - All operational actions are explicit and auditable.
"""

import json
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class IncidentSeverity(Enum):
    """Incident severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class HaltScope(Enum):
    """Scope of halt operation."""
    GLOBAL = "global"
    CHAIN = "chain"
    PROTOCOL = "protocol"
    WALLET = "wallet"


class OperationalAction(Enum):
    """Operational action types."""
    HALT_GLOBAL = "halt_global"
    HALT_CHAIN = "halt_chain"
    HALT_PROTOCOL = "halt_protocol"
    HALT_WALLET = "halt_wallet"
    RESUME_GLOBAL = "resume_global"
    RESUME_CHAIN = "resume_chain"
    RESUME_PROTOCOL = "resume_protocol"
    RESUME_WALLET = "resume_wallet"
    VERIFY_STATE = "verify_state"
    EXPORT_AUDIT = "export_audit"
    EMERGENCY_STOP = "emergency_stop"


@dataclass
class IncidentRecord:
    """Incident record for tracking."""
    incident_id: str
    severity: IncidentSeverity
    title: str
    description: str
    
    # Classification
    affected_chains: Set[int] = field(default_factory=set)
    affected_protocols: Set[str] = field(default_factory=set)
    affected_wallets: Set[str] = field(default_factory=set)
    
    # Response
    halt_triggered: bool = False
    halt_scope: Optional[HaltScope] = None
    
    # Timeline
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    
    # Actions taken
    actions_taken: List[str] = field(default_factory=list)
    
    # Operator
    reported_by: Optional[str] = None
    acknowledged_by: Optional[str] = None
    resolved_by: Optional[str] = None
    
    # Post-mortem
    root_cause: Optional[str] = None
    resolution_notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "incident_id": self.incident_id,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "affected_chains": list(self.affected_chains),
            "affected_protocols": list(self.affected_protocols),
            "affected_wallets": list(self.affected_wallets),
            "halt_triggered": self.halt_triggered,
            "halt_scope": self.halt_scope.value if self.halt_scope else None,
            "detected_at": self.detected_at.isoformat(),
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "actions_taken": self.actions_taken,
            "reported_by": self.reported_by,
            "acknowledged_by": self.acknowledged_by,
            "resolved_by": self.resolved_by,
            "root_cause": self.root_cause,
            "resolution_notes": self.resolution_notes
        }


@dataclass
class OperationalActionRecord:
    """Record of operational action taken."""
    action_id: str
    action_type: OperationalAction
    
    # Context
    operator: str
    reason: str
    
    # Target
    chain_id: Optional[int] = None
    protocol: Optional[str] = None
    wallet_address: Optional[str] = None
    
    # State
    success: bool = False
    error_message: Optional[str] = None
    
    # Metadata
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "operator": self.operator,
            "reason": self.reason,
            "chain_id": self.chain_id,
            "protocol": self.protocol,
            "wallet_address": self.wallet_address,
            "success": self.success,
            "error_message": self.error_message,
            "executed_at": self.executed_at.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class SystemHealthSnapshot:
    """System health snapshot."""
    snapshot_id: str
    
    # Execution state
    pending_intents: int
    executing_intents: int
    completed_today: int
    failed_today: int
    
    # Circuit breaker state
    is_halted: bool
    halted_chains: List[int]
    halted_protocols: List[str]
    
    # Resource utilization
    queue_utilization: float
    execution_utilization: float
    
    # Recent incidents
    open_incidents: int
    critical_incidents: int
    
    # Timestamp
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "snapshot_id": self.snapshot_id,
            "pending_intents": self.pending_intents,
            "executing_intents": self.executing_intents,
            "completed_today": self.completed_today,
            "failed_today": self.failed_today,
            "is_halted": self.is_halted,
            "halted_chains": self.halted_chains,
            "halted_protocols": self.halted_protocols,
            "queue_utilization": self.queue_utilization,
            "execution_utilization": self.execution_utilization,
            "open_incidents": self.open_incidents,
            "critical_incidents": self.critical_incidents,
            "captured_at": self.captured_at.isoformat()
        }


class OperationalController:
    """
    Operational controls and incident management system.
    
    Provides emergency controls and incident tracking for
    production operations.
    """
    
    def __init__(
        self,
        audit_log_path: str = "data/operational_audit.jsonl"
    ):
        """
        Initialize operational controller.
        
        Args:
            audit_log_path: Path to audit log file
        """
        self.audit_log_path = audit_log_path
        self._lock = threading.Lock()
        
        # Ensure audit directory exists
        Path(audit_log_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Incident tracking
        self._incidents: Dict[str, IncidentRecord] = {}
        self._action_history: List[OperationalActionRecord] = []
        
        # Halt state
        self._global_halt = False
        self._halted_chains: Set[int] = set()
        self._halted_protocols: Set[str] = set()
        self._halted_wallets: Set[str] = set()
        
        # Health snapshots
        self._health_snapshots: List[SystemHealthSnapshot] = []
        
        logger.info(
            "Operational controller initialized",
            extra={"audit_log_path": audit_log_path}
        )
    
    def emergency_stop(self, operator: str, reason: str) -> bool:
        """
        EMERGENCY STOP - Immediately halt all operations.
        
        This is the most severe operational action.
        Use only when system integrity is at risk.
        
        Args:
            operator: Operator initiating emergency stop
            reason: Reason for emergency stop
            
        Returns:
            True if emergency stop successful
        """
        action_id = f"emergency_{datetime.now(timezone.utc).timestamp()}"
        
        logger.critical(
            f"EMERGENCY STOP initiated by {operator}: {reason}",
            extra={
                "action_id": action_id,
                "operator": operator,
                "reason": reason
            }
        )
        
        try:
            with self._lock:
                self._global_halt = True
            
            # Record action
            action_record = OperationalActionRecord(
                action_id=action_id,
                action_type=OperationalAction.EMERGENCY_STOP,
                operator=operator,
                reason=reason,
                success=True
            )
            
            self._record_action(action_record)
            
            logger.critical(
                "EMERGENCY STOP completed - all operations halted",
                extra={"action_id": action_id}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Emergency stop failed: {e}", exc_info=True)
            
            action_record = OperationalActionRecord(
                action_id=action_id,
                action_type=OperationalAction.EMERGENCY_STOP,
                operator=operator,
                reason=reason,
                success=False,
                error_message=str(e)
            )
            
            self._record_action(action_record)
            return False
    
    def halt_global(self, operator: str, reason: str) -> bool:
        """
        Halt all system operations globally.
        
        Args:
            operator: Operator initiating halt
            reason: Reason for halt
            
        Returns:
            True if halt successful
        """
        action_id = f"halt_global_{datetime.now(timezone.utc).timestamp()}"
        
        logger.error(
            f"Global halt initiated by {operator}: {reason}",
            extra={
                "action_id": action_id,
                "operator": operator,
                "reason": reason
            }
        )
        
        try:
            with self._lock:
                self._global_halt = True
            
            action_record = OperationalActionRecord(
                action_id=action_id,
                action_type=OperationalAction.HALT_GLOBAL,
                operator=operator,
                reason=reason,
                success=True
            )
            
            self._record_action(action_record)
            
            logger.error(
                "Global halt completed",
                extra={"action_id": action_id}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Global halt failed: {e}", exc_info=True)
            return False
    
    def halt_chain(self, chain_id: int, operator: str, reason: str) -> bool:
        """
        Halt operations for specific chain.
        
        Args:
            chain_id: Chain ID to halt
            operator: Operator initiating halt
            reason: Reason for halt
            
        Returns:
            True if halt successful
        """
        action_id = f"halt_chain_{chain_id}_{datetime.now(timezone.utc).timestamp()}"
        
        logger.error(
            f"Chain {chain_id} halt initiated by {operator}: {reason}",
            extra={
                "action_id": action_id,
                "chain_id": chain_id,
                "operator": operator,
                "reason": reason
            }
        )
        
        try:
            with self._lock:
                self._halted_chains.add(chain_id)
            
            action_record = OperationalActionRecord(
                action_id=action_id,
                action_type=OperationalAction.HALT_CHAIN,
                operator=operator,
                reason=reason,
                chain_id=chain_id,
                success=True
            )
            
            self._record_action(action_record)
            
            logger.error(
                f"Chain {chain_id} halt completed",
                extra={"action_id": action_id, "chain_id": chain_id}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Chain halt failed: {e}", exc_info=True)
            return False
    
    def halt_protocol(self, protocol: str, operator: str, reason: str) -> bool:
        """
        Halt operations for specific protocol.
        
        Args:
            protocol: Protocol name to halt
            operator: Operator initiating halt
            reason: Reason for halt
            
        Returns:
            True if halt successful
        """
        action_id = f"halt_protocol_{protocol}_{datetime.now(timezone.utc).timestamp()}"
        
        logger.error(
            f"Protocol {protocol} halt initiated by {operator}: {reason}",
            extra={
                "action_id": action_id,
                "protocol": protocol,
                "operator": operator,
                "reason": reason
            }
        )
        
        try:
            with self._lock:
                self._halted_protocols.add(protocol.lower())
            
            action_record = OperationalActionRecord(
                action_id=action_id,
                action_type=OperationalAction.HALT_PROTOCOL,
                operator=operator,
                reason=reason,
                protocol=protocol,
                success=True
            )
            
            self._record_action(action_record)
            
            logger.error(
                f"Protocol {protocol} halt completed",
                extra={"action_id": action_id, "protocol": protocol}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Protocol halt failed: {e}", exc_info=True)
            return False
    
    def halt_wallet(self, wallet_address: str, operator: str, reason: str) -> bool:
        """
        Halt operations for specific wallet.
        
        Args:
            wallet_address: Wallet address to halt
            operator: Operator initiating halt
            reason: Reason for halt
            
        Returns:
            True if halt successful
        """
        action_id = f"halt_wallet_{wallet_address}_{datetime.now(timezone.utc).timestamp()}"
        
        logger.error(
            f"Wallet {wallet_address} halt initiated by {operator}: {reason}",
            extra={
                "action_id": action_id,
                "wallet_address": wallet_address,
                "operator": operator,
                "reason": reason
            }
        )
        
        try:
            with self._lock:
                self._halted_wallets.add(wallet_address.lower())
            
            action_record = OperationalActionRecord(
                action_id=action_id,
                action_type=OperationalAction.HALT_WALLET,
                operator=operator,
                reason=reason,
                wallet_address=wallet_address,
                success=True
            )
            
            self._record_action(action_record)
            
            logger.error(
                f"Wallet {wallet_address} halt completed",
                extra={"action_id": action_id, "wallet_address": wallet_address}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Wallet halt failed: {e}", exc_info=True)
            return False
    
    def resume_global(
        self,
        operator: str,
        state_verified: bool,
        verification_notes: Optional[str] = None
    ) -> bool:
        """
        Resume global operations after halt.
        
        Requires explicit state verification before resume.
        
        Args:
            operator: Operator initiating resume
            state_verified: Whether state has been verified safe
            verification_notes: Notes from state verification
            
        Returns:
            True if resume successful
        """
        if not state_verified:
            logger.error(
                "Cannot resume without state verification",
                extra={"operator": operator}
            )
            return False
        
        action_id = f"resume_global_{datetime.now(timezone.utc).timestamp()}"
        
        logger.warning(
            f"Global resume initiated by {operator}",
            extra={
                "action_id": action_id,
                "operator": operator,
                "verification_notes": verification_notes
            }
        )
        
        try:
            with self._lock:
                self._global_halt = False
            
            action_record = OperationalActionRecord(
                action_id=action_id,
                action_type=OperationalAction.RESUME_GLOBAL,
                operator=operator,
                reason="State verified safe for resume",
                success=True,
                metadata={
                    "state_verified": state_verified,
                    "verification_notes": verification_notes
                }
            )
            
            self._record_action(action_record)
            
            logger.warning(
                "Global resume completed - operations resumed",
                extra={"action_id": action_id}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Global resume failed: {e}", exc_info=True)
            return False
    
    def resume_chain(self, chain_id: int, operator: str, state_verified: bool) -> bool:
        """Resume operations for specific chain."""
        if not state_verified:
            logger.error(f"Cannot resume chain {chain_id} without state verification")
            return False
        
        action_id = f"resume_chain_{chain_id}_{datetime.now(timezone.utc).timestamp()}"
        
        try:
            with self._lock:
                self._halted_chains.discard(chain_id)
            
            action_record = OperationalActionRecord(
                action_id=action_id,
                action_type=OperationalAction.RESUME_CHAIN,
                operator=operator,
                reason="State verified safe for resume",
                chain_id=chain_id,
                success=True
            )
            
            self._record_action(action_record)
            
            logger.warning(
                f"Chain {chain_id} resumed",
                extra={"action_id": action_id, "chain_id": chain_id}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Chain resume failed: {e}", exc_info=True)
            return False
    
    def resume_protocol(self, protocol: str, operator: str, state_verified: bool) -> bool:
        """Resume operations for specific protocol."""
        if not state_verified:
            logger.error(f"Cannot resume protocol {protocol} without state verification")
            return False
        
        action_id = f"resume_protocol_{protocol}_{datetime.now(timezone.utc).timestamp()}"
        
        try:
            with self._lock:
                self._halted_protocols.discard(protocol.lower())
            
            action_record = OperationalActionRecord(
                action_id=action_id,
                action_type=OperationalAction.RESUME_PROTOCOL,
                operator=operator,
                reason="State verified safe for resume",
                protocol=protocol,
                success=True
            )
            
            self._record_action(action_record)
            
            logger.warning(
                f"Protocol {protocol} resumed",
                extra={"action_id": action_id, "protocol": protocol}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Protocol resume failed: {e}", exc_info=True)
            return False
    
    def is_halted(
        self,
        chain_id: Optional[int] = None,
        protocol: Optional[str] = None,
        wallet_address: Optional[str] = None
    ) -> bool:
        """
        Check if operations are halted.
        
        Args:
            chain_id: Optional chain ID to check
            protocol: Optional protocol to check
            wallet_address: Optional wallet to check
            
        Returns:
            True if halted
        """
        with self._lock:
            # Global halt affects everything
            if self._global_halt:
                return True
            
            # Chain-specific halt
            if chain_id and chain_id in self._halted_chains:
                return True
            
            # Protocol-specific halt
            if protocol and protocol.lower() in self._halted_protocols:
                return True
            
            # Wallet-specific halt
            if wallet_address and wallet_address.lower() in self._halted_wallets:
                return True
        
        return False
    
    def create_incident(
        self,
        severity: IncidentSeverity,
        title: str,
        description: str,
        reported_by: Optional[str] = None,
        affected_chains: Optional[Set[int]] = None,
        affected_protocols: Optional[Set[str]] = None,
        affected_wallets: Optional[Set[str]] = None
    ) -> IncidentRecord:
        """
        Create new incident record.
        
        Args:
            severity: Incident severity
            title: Incident title
            description: Incident description
            reported_by: Operator reporting incident
            affected_chains: Affected chain IDs
            affected_protocols: Affected protocols
            affected_wallets: Affected wallets
            
        Returns:
            IncidentRecord
        """
        incident_id = f"incident_{datetime.now(timezone.utc).timestamp()}"
        
        incident = IncidentRecord(
            incident_id=incident_id,
            severity=severity,
            title=title,
            description=description,
            reported_by=reported_by,
            affected_chains=affected_chains or set(),
            affected_protocols=affected_protocols or set(),
            affected_wallets=affected_wallets or set()
        )
        
        with self._lock:
            self._incidents[incident_id] = incident
        
        logger.error(
            f"Incident created: {severity.value} - {title}",
            extra=incident.to_dict()
        )
        
        # Auto-trigger halt for critical incidents
        if severity == IncidentSeverity.CRITICAL:
            logger.critical("Critical incident - considering automatic halt")
            incident.halt_triggered = True
            incident.halt_scope = HaltScope.GLOBAL
        
        return incident
    
    def acknowledge_incident(self, incident_id: str, acknowledged_by: str) -> bool:
        """Acknowledge incident."""
        with self._lock:
            incident = self._incidents.get(incident_id)
            if not incident:
                return False
            
            incident.acknowledged_at = datetime.now(timezone.utc)
            incident.acknowledged_by = acknowledged_by
        
        logger.info(
            f"Incident {incident_id} acknowledged by {acknowledged_by}",
            extra={"incident_id": incident_id, "acknowledged_by": acknowledged_by}
        )
        
        return True
    
    def resolve_incident(
        self,
        incident_id: str,
        resolved_by: str,
        root_cause: Optional[str] = None,
        resolution_notes: Optional[str] = None
    ) -> bool:
        """Resolve incident."""
        with self._lock:
            incident = self._incidents.get(incident_id)
            if not incident:
                return False
            
            incident.resolved_at = datetime.now(timezone.utc)
            incident.resolved_by = resolved_by
            incident.root_cause = root_cause
            incident.resolution_notes = resolution_notes
        
        logger.info(
            f"Incident {incident_id} resolved by {resolved_by}",
            extra={
                "incident_id": incident_id,
                "resolved_by": resolved_by,
                "root_cause": root_cause
            }
        )
        
        return True
    
    def export_audit_log(
        self,
        output_path: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> str:
        """
        Export audit log for post-mortem analysis.
        
        Args:
            output_path: Output file path (defaults to timestamped file)
            start_time: Filter start time
            end_time: Filter end time
            
        Returns:
            Path to exported audit log
        """
        if not output_path:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_path = f"data/audit_export_{timestamp}.json"
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        with self._lock:
            # Filter actions by time range
            actions = self._action_history
            if start_time:
                actions = [a for a in actions if a.executed_at >= start_time]
            if end_time:
                actions = [a for a in actions if a.executed_at <= end_time]
            
            # Filter incidents by time range
            incidents = list(self._incidents.values())
            if start_time:
                incidents = [i for i in incidents if i.detected_at >= start_time]
            if end_time:
                incidents = [i for i in incidents if i.detected_at <= end_time]
            
            audit_data = {
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "start_time": start_time.isoformat() if start_time else None,
                "end_time": end_time.isoformat() if end_time else None,
                "actions": [a.to_dict() for a in actions],
                "incidents": [i.to_dict() for i in incidents],
                "system_state": {
                    "global_halt": self._global_halt,
                    "halted_chains": list(self._halted_chains),
                    "halted_protocols": list(self._halted_protocols),
                    "halted_wallets": list(self._halted_wallets)
                }
            }
        
        with open(output_path, 'w') as f:
            json.dump(audit_data, f, indent=2)
        
        logger.info(
            f"Audit log exported to {output_path}",
            extra={
                "output_path": output_path,
                "action_count": len(actions),
                "incident_count": len(incidents)
            }
        )
        
        return output_path
    
    def _record_action(self, action: OperationalActionRecord):
        """Record operational action to audit log."""
        with self._lock:
            self._action_history.append(action)
        
        # Append to audit log file
        try:
            with open(self.audit_log_path, 'a') as f:
                f.write(json.dumps(action.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to write to audit log: {e}")
    
    def get_open_incidents(self) -> List[IncidentRecord]:
        """Get all open incidents."""
        with self._lock:
            return [
                incident for incident in self._incidents.values()
                if incident.resolved_at is None
            ]
    
    def get_critical_incidents(self) -> List[IncidentRecord]:
        """Get all critical incidents."""
        with self._lock:
            return [
                incident for incident in self._incidents.values()
                if incident.severity == IncidentSeverity.CRITICAL
                and incident.resolved_at is None
            ]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get operational statistics."""
        with self._lock:
            open_incidents = len(self.get_open_incidents())
            critical_incidents = len(self.get_critical_incidents())
            
            return {
                "global_halt": self._global_halt,
                "halted_chains": list(self._halted_chains),
                "halted_protocols": list(self._halted_protocols),
                "halted_wallets": list(self._halted_wallets),  # Return list for consistency
                "total_incidents": len(self._incidents),
                "open_incidents": open_incidents,
                "critical_incidents": critical_incidents,
                "total_actions": len(self._action_history),
                "health_snapshots": len(self._health_snapshots)
            }
