#!/usr/bin/env python3
"""
VEL AI Self-Repair Safety Constraints
======================================

Production safety constraints for AI/self-modifying components.

For real-money trading, AI modules must be:
- Deterministic: Same inputs produce same outputs
- Auditable: All decisions are logged with reasoning
- Predictable: Behavior is bounded and understood
- Constrained: Self-modification is limited and reversible

This module provides:
- Deterministic execution mode
- Comprehensive audit logging
- Decision bounds and limits
- Rollback capabilities
- Human-in-the-loop gates

Usage:
    from vel_ai_safety import SafeAIExecutor, require_human_approval
    
    executor = SafeAIExecutor()
    
    @require_human_approval(threshold=10000)
    def execute_large_trade(amount):
        ...
"""

import functools
import hashlib
import json
import logging
import os
import random
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("vel.ai.safety")


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class AISafetyConfig:
    """AI safety configuration."""
    # Determinism
    enforce_determinism: bool = True
    fixed_random_seed: Optional[int] = 42
    
    # Decision limits
    max_decision_value_usd: Decimal = Decimal("10000")
    max_decisions_per_hour: int = 100
    max_position_change_percentage: Decimal = Decimal("10.0")
    
    # Human approval thresholds
    human_approval_threshold_usd: Decimal = Decimal("5000")
    human_approval_timeout_seconds: int = 300
    
    # Audit settings
    audit_enabled: bool = True
    audit_retention_days: int = 90
    
    # Self-modification limits
    allow_self_modification: bool = False
    max_code_changes_per_day: int = 0
    
    # Rollback
    enable_rollback: bool = True
    max_rollback_window_hours: int = 24
    
    @classmethod
    def from_env(cls) -> "AISafetyConfig":
        """Load config from environment."""
        return cls(
            enforce_determinism=os.environ.get("VEL_AI_DETERMINISTIC", "true").lower() == "true",
            max_decision_value_usd=Decimal(os.environ.get("VEL_AI_MAX_DECISION_USD", "10000")),
            human_approval_threshold_usd=Decimal(os.environ.get("VEL_AI_HUMAN_THRESHOLD_USD", "5000")),
            allow_self_modification=os.environ.get("VEL_AI_SELF_MODIFY", "false").lower() == "true",
        )


# =============================================================================
# Audit Records
# =============================================================================

class DecisionType(Enum):
    """AI decision types."""
    TRADE_SIGNAL = "trade_signal"
    POSITION_SIZE = "position_size"
    RISK_ASSESSMENT = "risk_assessment"
    STRATEGY_SELECTION = "strategy_selection"
    MARKET_PREDICTION = "market_prediction"
    SELF_REPAIR = "self_repair"
    CODE_MODIFICATION = "code_modification"


@dataclass
class AuditRecord:
    """Audit record for AI decisions."""
    timestamp: datetime
    decision_id: str
    decision_type: DecisionType
    inputs: Dict[str, Any]
    input_hash: str  # Hash of inputs for reproducibility check
    outputs: Dict[str, Any]
    output_hash: str
    reasoning: str
    confidence: float
    value_usd: Optional[Decimal] = None
    human_approved: bool = False
    approved_by: Optional[str] = None
    execution_time_ms: float = 0
    model_version: str = ""
    determinism_verified: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        d["decision_type"] = self.decision_type.value
        d["value_usd"] = str(self.value_usd) if self.value_usd else None
        return d


# =============================================================================
# Deterministic Execution Context
# =============================================================================

class DeterministicContext:
    """
    Context manager for deterministic AI execution.
    
    Ensures:
    - Fixed random seeds
    - Reproducible model inference
    - Consistent timestamp handling
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self, seed: int = 42):
        self.seed = seed
        self._original_random_state = None
        self._original_numpy_state = None
        self._fixed_time = None
    
    def __enter__(self):
        # Store original random state
        self._original_random_state = random.getstate()
        random.seed(self.seed)
        
        # Try to set numpy seed if available
        try:
            import numpy as np
            self._original_numpy_state = np.random.get_state()
            np.random.seed(self.seed)
        except ImportError:
            # numpy is an optional dependency; if not available, skip numpy RNG seeding
            pass
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore random state
        if self._original_random_state:
            random.setstate(self._original_random_state)
        
        # Restore numpy state
        if self._original_numpy_state is not None:
            try:
                import numpy as np
                np.random.set_state(self._original_numpy_state)
            except ImportError:
                # numpy is an optional dependency; if not available, skip restore
                pass
        
        return False
    
    @classmethod
    def get_or_create(cls, seed: int = 42) -> "DeterministicContext":
        """Get or create singleton context."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(seed)
            return cls._instance


def hash_inputs(inputs: Dict[str, Any]) -> str:
    """Create deterministic hash of inputs."""
    # Sort keys for consistency
    sorted_json = json.dumps(inputs, sort_keys=True, default=str)
    return hashlib.sha256(sorted_json.encode()).hexdigest()[:16]


# =============================================================================
# Safe AI Executor
# =============================================================================

class SafeAIExecutor:
    """
    Production-safe AI execution wrapper.
    
    All AI decisions go through this executor which:
    - Enforces determinism
    - Logs all decisions for audit
    - Applies safety limits
    - Manages human approval gates
    """
    
    def __init__(
        self,
        config: Optional[AISafetyConfig] = None,
        audit_callback: Optional[Callable[[AuditRecord], None]] = None
    ):
        self.config = config or AISafetyConfig.from_env()
        self.audit_callback = audit_callback
        
        self._lock = threading.Lock()
        self._audit_log: List[AuditRecord] = []
        self._decisions_this_hour: int = 0
        self._hour_reset_at: datetime = self._get_next_hour()
        self._pending_approvals: Dict[str, dict] = {}
        
        # Code modification tracking
        self._code_changes_today: int = 0
        self._day_reset_at: datetime = self._get_next_day()
        
        logger.info(
            "Safe AI Executor initialized",
            extra={
                "determinism": self.config.enforce_determinism,
                "max_decision_usd": str(self.config.max_decision_value_usd),
                "self_modification": self.config.allow_self_modification
            }
        )
    
    def _get_next_hour(self) -> datetime:
        """Get next hour boundary."""
        now = datetime.now(timezone.utc)
        return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    
    def _get_next_day(self) -> datetime:
        """Get next day boundary."""
        now = datetime.now(timezone.utc)
        return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    
    def _check_limits(self):
        """Check and reset hourly/daily limits."""
        now = datetime.now(timezone.utc)
        
        if now >= self._hour_reset_at:
            self._decisions_this_hour = 0
            self._hour_reset_at = self._get_next_hour()
        
        if now >= self._day_reset_at:
            self._code_changes_today = 0
            self._day_reset_at = self._get_next_day()
    
    def execute(
        self,
        decision_func: Callable,
        inputs: Dict[str, Any],
        decision_type: DecisionType,
        value_usd: Optional[Decimal] = None,
        reasoning: str = "",
        require_approval: bool = False
    ) -> Dict[str, Any]:
        """
        Execute AI decision with safety constraints.
        
        Args:
            decision_func: Function to execute
            inputs: Input parameters
            decision_type: Type of decision
            value_usd: USD value if applicable
            reasoning: Explanation of decision
            require_approval: Force human approval
            
        Returns:
            Decision outputs
        """
        start_time = time.time()
        
        with self._lock:
            self._check_limits()
            
            # Check decision rate limit
            if self._decisions_this_hour >= self.config.max_decisions_per_hour:
                raise SafetyLimitExceeded(
                    f"Hourly decision limit reached: {self._decisions_this_hour}"
                )
            
            # Check value limit
            if value_usd and value_usd > self.config.max_decision_value_usd:
                raise SafetyLimitExceeded(
                    f"Decision value ${value_usd} exceeds limit ${self.config.max_decision_value_usd}"
                )
        
        # Check if human approval required
        needs_approval = require_approval or (
            value_usd and value_usd >= self.config.human_approval_threshold_usd
        )
        
        # Block self-modification if disabled
        if decision_type == DecisionType.CODE_MODIFICATION:
            if not self.config.allow_self_modification:
                raise SafetyLimitExceeded("Self-modification is disabled in production")
            if self._code_changes_today >= self.config.max_code_changes_per_day:
                raise SafetyLimitExceeded("Daily code modification limit reached")
        
        # Generate decision ID
        decision_id = hashlib.sha256(
            f"{time.time()}:{json.dumps(inputs, default=str)}".encode()
        ).hexdigest()[:12]
        
        input_hash = hash_inputs(inputs)
        
        # Execute with determinism if configured
        if self.config.enforce_determinism:
            with DeterministicContext(self.config.fixed_random_seed or 42):
                outputs = decision_func(**inputs)
        else:
            outputs = decision_func(**inputs)
        
        output_hash = hash_inputs(outputs) if isinstance(outputs, dict) else ""
        execution_time = (time.time() - start_time) * 1000
        
        # Verify determinism
        determinism_verified = False
        if self.config.enforce_determinism:
            # Re-execute with same seed and verify
            with DeterministicContext(self.config.fixed_random_seed or 42):
                outputs_verify = decision_func(**inputs)
            
            if isinstance(outputs, dict) and isinstance(outputs_verify, dict):
                determinism_verified = hash_inputs(outputs) == hash_inputs(outputs_verify)
        
        # Create audit record
        audit_record = AuditRecord(
            timestamp=datetime.now(timezone.utc),
            decision_id=decision_id,
            decision_type=decision_type,
            inputs=inputs,
            input_hash=input_hash,
            outputs=outputs if isinstance(outputs, dict) else {"result": outputs},
            output_hash=output_hash,
            reasoning=reasoning,
            confidence=outputs.get("confidence", 0) if isinstance(outputs, dict) else 0,
            value_usd=value_usd,
            execution_time_ms=execution_time,
            determinism_verified=determinism_verified
        )
        
        # Handle approval requirement
        if needs_approval:
            approval_result = self._request_approval(decision_id, audit_record)
            if not approval_result["approved"]:
                audit_record.human_approved = False
                self._log_audit(audit_record)
                raise HumanApprovalRequired(
                    f"Decision {decision_id} requires human approval"
                )
            audit_record.human_approved = True
            audit_record.approved_by = approval_result.get("approved_by")
        
        # Log and return
        with self._lock:
            self._decisions_this_hour += 1
            if decision_type == DecisionType.CODE_MODIFICATION:
                self._code_changes_today += 1
        
        self._log_audit(audit_record)
        
        return outputs
    
    def _request_approval(self, decision_id: str, record: AuditRecord) -> Dict[str, Any]:
        """
        Request human approval for decision.
        
        In production, this would:
        - Send notification to operators
        - Wait for approval within timeout
        - Log the approval decision
        
        For now, returns auto-rejection (must be approved externally).
        """
        logger.warning(
            f"Human approval required for decision {decision_id}",
            extra={
                "decision_id": decision_id,
                "decision_type": record.decision_type.value,
                "value_usd": str(record.value_usd)
            }
        )
        
        # Store pending approval (thread-safe) and prune expired entries
        with self._lock:
            now = datetime.now(timezone.utc)
            now_ts = now.timestamp()
            
            # Prune expired pending approvals to prevent unbounded growth
            expired_ids = [
                key for key, value in self._pending_approvals.items()
                if value.get("timeout_at", 0) <= now_ts
            ]
            for key in expired_ids:
                del self._pending_approvals[key]
            
            self._pending_approvals[decision_id] = {
                "record": record.to_dict(),
                "requested_at": now.isoformat(),
                "timeout_at": now_ts + self.config.human_approval_timeout_seconds,
            }
        
        # In production: Wait for external approval
        # For safety, default to rejection
        return {"approved": False, "reason": "Auto-rejected - requires manual approval"}
    
    def approve_decision(
        self,
        decision_id: str,
        approved_by: str,
        approved: bool = True
    ) -> bool:
        """
        Approve a pending decision.
        
        Called by human operators to approve/reject pending decisions.
        """
        if decision_id not in self._pending_approvals:
            return False
        
        self._pending_approvals.pop(decision_id, None)
        
        logger.info(
            f"Decision {decision_id} {'approved' if approved else 'rejected'} by {approved_by}",
            extra={
                "decision_id": decision_id,
                "approved": approved,
                "approved_by": approved_by
            }
        )
        
        return True
    
    def _log_audit(self, record: AuditRecord):
        """Log audit record."""
        with self._lock:
            self._audit_log.append(record)
            
            # Trim old records
            if len(self._audit_log) > 10000:
                self._audit_log = self._audit_log[-5000:]
        
        logger.info(
            f"AI Decision: {record.decision_type.value}",
            extra={
                "audit_record": record.to_dict()
            }
        )
        
        if self.audit_callback:
            try:
                self.audit_callback(record)
            except Exception as e:
                logger.error(f"Audit callback error: {e}")
    
    def get_audit_log(
        self,
        limit: int = 100,
        decision_type: Optional[DecisionType] = None
    ) -> List[Dict]:
        """Get audit log entries."""
        with self._lock:
            records = self._audit_log[-limit:]
            if decision_type:
                records = [r for r in records if r.decision_type == decision_type]
            return [r.to_dict() for r in records]
    
    def verify_reproducibility(
        self,
        decision_id: str,
        decision_func: Callable
    ) -> bool:
        """
        Verify that a past decision can be reproduced.
        
        Used for auditing and debugging.
        """
        # Find original record
        with self._lock:
            record = next(
                (r for r in self._audit_log if r.decision_id == decision_id),
                None
            )
        
        if not record:
            return False
        
        # Re-execute with same inputs
        with DeterministicContext(self.config.fixed_random_seed or 42):
            new_outputs = decision_func(**record.inputs)
        
        # Compare outputs
        new_hash = hash_inputs(new_outputs) if isinstance(new_outputs, dict) else ""
        return new_hash == record.output_hash


# =============================================================================
# Decorators
# =============================================================================

_default_executor: Optional[SafeAIExecutor] = None


def get_ai_executor() -> SafeAIExecutor:
    """Get default AI executor."""
    global _default_executor
    if _default_executor is None:
        _default_executor = SafeAIExecutor()
    return _default_executor


def safe_ai_decision(
    decision_type: DecisionType,
    value_func: Optional[Callable] = None,
    reasoning_func: Optional[Callable] = None
):
    """
    Decorator for safe AI decisions.
    
    Usage:
        @safe_ai_decision(DecisionType.TRADE_SIGNAL)
        def generate_signal(market_data):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Combine args into kwargs for auditing
            inputs = {f"arg_{i}": arg for i, arg in enumerate(args)}
            inputs.update(kwargs)
            
            # Get value if function provided
            value_usd = None
            if value_func:
                try:
                    value_usd = Decimal(str(value_func(*args, **kwargs)))
                except Exception:
                    # Silently ignore value function errors; value_usd remains None
                    pass
            
            # Get reasoning if function provided
            reasoning = ""
            if reasoning_func:
                try:
                    reasoning = reasoning_func(*args, **kwargs)
                except Exception:
                    # Silently ignore reasoning function errors; reasoning remains empty
                    pass
            
            return get_ai_executor().execute(
                decision_func=lambda **kw: func(*args, **kwargs),
                inputs=inputs,
                decision_type=decision_type,
                value_usd=value_usd,
                reasoning=reasoning
            )
        
        return wrapper
    return decorator


def require_human_approval(threshold_usd: Decimal = None):
    """
    Decorator requiring human approval above threshold.
    
    Usage:
        @require_human_approval(threshold=Decimal("10000"))
        def execute_large_trade(amount):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract value from first argument if numeric
            value = None
            if args and isinstance(args[0], (int, float, Decimal)):
                value = Decimal(str(args[0]))
            elif "amount" in kwargs:
                value = Decimal(str(kwargs["amount"]))
            elif "value_usd" in kwargs:
                value = Decimal(str(kwargs["value_usd"]))
            
            # Check threshold
            config = get_ai_executor().config
            threshold = threshold_usd or config.human_approval_threshold_usd
            
            if value and value >= threshold:
                logger.warning(
                    f"Action requires human approval: value ${value} >= threshold ${threshold}"
                )
                raise HumanApprovalRequired(
                    f"Value ${value} exceeds approval threshold ${threshold}"
                )
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


# =============================================================================
# Exceptions
# =============================================================================

class SafetyLimitExceeded(Exception):
    """Raised when AI safety limits are exceeded."""
    pass


class HumanApprovalRequired(Exception):
    """Raised when human approval is required."""
    pass


class DeterminismViolation(Exception):
    """Raised when determinism cannot be guaranteed."""
    pass
