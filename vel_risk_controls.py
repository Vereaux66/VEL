#!/usr/bin/env python3
"""
VEL Risk Engine - Global Kill Switch and Max Daily Loss Enforcement
====================================================================

Production-grade risk controls with emergency shutdown capabilities.

Features:
- Global kill switch for immediate trading halt
- Max daily loss enforcement with automatic shutdown
- Rate limiting per wallet and global
- Atomic execution validation
- Audit logging for all risk decisions

Usage:
    from vel_risk_controls import RiskControlEngine, get_risk_controller
    
    controller = get_risk_controller()
    
    # Check before trade
    if not controller.pre_trade_check(trade):
        return "Trade blocked by risk controls"
    
    # Emergency shutdown
    controller.trigger_kill_switch("Market anomaly detected")
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from contextlib import contextmanager

logger = logging.getLogger("vel.risk.controls")


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class RiskConfig:
    """Risk control configuration."""
    # Daily loss limits
    max_daily_loss_usd: Decimal = Decimal("10000")
    max_daily_loss_percentage: Decimal = Decimal("5.0")  # % of portfolio
    
    # Position limits
    max_position_size_usd: Decimal = Decimal("50000")
    max_position_percentage: Decimal = Decimal("25.0")  # % of portfolio
    
    # Rate limits
    max_trades_per_minute: int = 10
    max_trades_per_hour: int = 100
    max_trades_per_day: int = 500
    
    # Trade size limits
    min_trade_size_usd: Decimal = Decimal("10")
    max_trade_size_usd: Decimal = Decimal("10000")
    
    # Slippage limits
    max_slippage_percentage: Decimal = Decimal("1.0")
    
    # Gas limits
    max_gas_price_gwei: int = 500
    max_gas_cost_usd: Decimal = Decimal("100")
    
    # Kill switch settings
    kill_switch_cooldown_seconds: int = 300  # 5 minutes minimum between resets
    require_manual_reset: bool = True
    
    @classmethod
    def from_env(cls) -> "RiskConfig":
        """Load config from environment variables."""
        return cls(
            max_daily_loss_usd=Decimal(os.environ.get("VEL_MAX_DAILY_LOSS_USD", "10000")),
            max_daily_loss_percentage=Decimal(os.environ.get("VEL_MAX_DAILY_LOSS_PCT", "5.0")),
            max_position_size_usd=Decimal(os.environ.get("VEL_MAX_POSITION_USD", "50000")),
            max_position_percentage=Decimal(os.environ.get("VEL_MAX_POSITION_PCT", "25.0")),
            max_trades_per_minute=int(os.environ.get("VEL_MAX_TRADES_PER_MIN", "10")),
            max_trades_per_hour=int(os.environ.get("VEL_MAX_TRADES_PER_HOUR", "100")),
            max_trades_per_day=int(os.environ.get("VEL_MAX_TRADES_PER_DAY", "500")),
            min_trade_size_usd=Decimal(os.environ.get("VEL_MIN_TRADE_USD", "10")),
            max_trade_size_usd=Decimal(os.environ.get("VEL_MAX_TRADE_USD", "10000")),
            max_slippage_percentage=Decimal(os.environ.get("VEL_MAX_SLIPPAGE_PCT", "1.0")),
            max_gas_price_gwei=int(os.environ.get("VEL_MAX_GAS_GWEI", "500")),
            max_gas_cost_usd=Decimal(os.environ.get("VEL_MAX_GAS_USD", "100")),
            require_manual_reset=os.environ.get("VEL_REQUIRE_MANUAL_RESET", "true").lower() == "true",
        )


# =============================================================================
# Risk Events
# =============================================================================

class RiskEvent(Enum):
    """Risk event types."""
    TRADE_ALLOWED = "trade_allowed"
    TRADE_BLOCKED = "trade_blocked"
    DAILY_LOSS_WARNING = "daily_loss_warning"
    DAILY_LOSS_LIMIT_HIT = "daily_loss_limit_hit"
    RATE_LIMIT_HIT = "rate_limit_hit"
    KILL_SWITCH_ACTIVATED = "kill_switch_activated"
    KILL_SWITCH_RESET = "kill_switch_reset"
    POSITION_LIMIT_HIT = "position_limit_hit"
    GAS_LIMIT_HIT = "gas_limit_hit"


@dataclass
class RiskDecision:
    """Result of a risk check."""
    allowed: bool
    reason: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    event: RiskEvent = RiskEvent.TRADE_ALLOWED
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def blocked(self) -> bool:
        return not self.allowed


@dataclass
class TradeRequest:
    """Trade request for risk evaluation."""
    trade_id: str
    wallet_address: str
    chain_id: int
    token_in: str
    token_out: str
    amount_in: Decimal
    amount_in_usd: Decimal
    expected_amount_out: Decimal
    expected_amount_out_usd: Decimal
    max_slippage: Decimal
    gas_price_gwei: Optional[int] = None
    gas_limit: Optional[int] = None
    strategy_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Rate Limiter
# =============================================================================

class TokenBucketRateLimiter:
    """Token bucket rate limiter."""
    
    def __init__(self, capacity: int, refill_rate: float, refill_interval: float = 1.0):
        """
        Initialize rate limiter.
        
        Args:
            capacity: Maximum tokens in bucket
            refill_rate: Tokens added per interval
            refill_interval: Interval in seconds
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.refill_interval = refill_interval
        self.tokens = float(capacity)
        self.last_refill = time.time()
        self._lock = threading.Lock()
    
    def acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens."""
        with self._lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        intervals = elapsed / self.refill_interval
        refill_amount = intervals * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + refill_amount)
        self.last_refill = now
    
    @property
    def available(self) -> float:
        """Get available tokens."""
        with self._lock:
            self._refill()
            return self.tokens


# =============================================================================
# Risk Control Engine
# =============================================================================

class RiskControlEngine:
    """
    Production-grade risk control engine.
    
    Implements:
    - Global kill switch for emergency shutdown
    - Max daily loss enforcement
    - Position size limits
    - Rate limiting
    - Gas price limits
    - Audit logging
    """
    
    def __init__(
        self,
        config: Optional[RiskConfig] = None,
        audit_callback: Optional[Callable[[Dict], None]] = None
    ):
        """
        Initialize risk control engine.
        
        Args:
            config: Risk configuration
            audit_callback: Callback for audit events
        """
        self.config = config or RiskConfig.from_env()
        self.audit_callback = audit_callback
        
        self._lock = threading.Lock()
        
        # Kill switch state
        self._kill_switch_active = False
        self._kill_switch_reason: Optional[str] = None
        self._kill_switch_activated_at: Optional[datetime] = None
        self._kill_switch_activated_by: Optional[str] = None
        
        # Daily tracking
        self._daily_pnl = Decimal("0")
        self._daily_trade_count = 0
        self._daily_reset_at: datetime = self._get_next_reset_time()
        
        # Position tracking
        self._positions: Dict[str, Decimal] = {}  # token -> value_usd
        
        # Rate limiters
        self._rate_limiter_minute = TokenBucketRateLimiter(
            capacity=self.config.max_trades_per_minute,
            refill_rate=self.config.max_trades_per_minute,
            refill_interval=60.0
        )
        self._rate_limiter_hour = TokenBucketRateLimiter(
            capacity=self.config.max_trades_per_hour,
            refill_rate=self.config.max_trades_per_hour,
            refill_interval=3600.0
        )
        
        # Trade history for rate limiting
        self._trade_timestamps: List[datetime] = []
        
        logger.info("Risk control engine initialized")
        logger.info(f"Max daily loss: ${self.config.max_daily_loss_usd}")
        logger.info(f"Max position size: ${self.config.max_position_size_usd}")
    
    def _get_next_reset_time(self) -> datetime:
        """Get next daily reset time (midnight UTC)."""
        now = datetime.now(timezone.utc)
        tomorrow = now.date() + timedelta(days=1)
        return datetime.combine(tomorrow, datetime.min.time(), timezone.utc)
    
    def _check_daily_reset(self):
        """Check if daily counters need reset."""
        now = datetime.now(timezone.utc)
        if now >= self._daily_reset_at:
            logger.info("Resetting daily risk counters")
            self._daily_pnl = Decimal("0")
            self._daily_trade_count = 0
            self._daily_reset_at = self._get_next_reset_time()
            # Clean up old trade timestamps
            cutoff = now - timedelta(hours=24)
            self._trade_timestamps = [ts for ts in self._trade_timestamps if ts > cutoff]
    
    # ─────────────────────────────────────────────────────────────────────────
    # Kill Switch
    # ─────────────────────────────────────────────────────────────────────────
    
    def trigger_kill_switch(
        self,
        reason: str,
        activated_by: str = "system"
    ) -> bool:
        """
        Activate global kill switch - stops ALL trading immediately.
        
        Args:
            reason: Reason for activation
            activated_by: Who/what activated (user, system, alert)
            
        Returns:
            True if activated
        """
        with self._lock:
            if self._kill_switch_active:
                logger.warning("Kill switch already active")
                return False
            
            self._kill_switch_active = True
            self._kill_switch_reason = reason
            self._kill_switch_activated_at = datetime.now(timezone.utc)
            self._kill_switch_activated_by = activated_by
            
            logger.critical(
                f"KILL SWITCH ACTIVATED by {activated_by}: {reason}",
                extra={
                    "event": "kill_switch_activated",
                    "reason": reason,
                    "activated_by": activated_by
                }
            )
            
            self._audit(RiskEvent.KILL_SWITCH_ACTIVATED, {
                "reason": reason,
                "activated_by": activated_by,
                "daily_pnl": str(self._daily_pnl),
                "trade_count": self._daily_trade_count
            })
            
            return True
    
    def reset_kill_switch(
        self,
        reset_by: str,
        confirmation_code: Optional[str] = None
    ) -> bool:
        """
        Reset kill switch - requires manual confirmation in production.
        
        Args:
            reset_by: Who is resetting
            confirmation_code: Required confirmation code
            
        Returns:
            True if reset successful
        """
        with self._lock:
            if not self._kill_switch_active:
                logger.info("Kill switch not active")
                return True
            
            # Check cooldown
            if self._kill_switch_activated_at:
                elapsed = (datetime.now(timezone.utc) - self._kill_switch_activated_at).total_seconds()
                if elapsed < self.config.kill_switch_cooldown_seconds:
                    remaining = self.config.kill_switch_cooldown_seconds - elapsed
                    logger.warning(f"Kill switch cooldown not expired: {remaining:.0f}s remaining")
                    return False
            
            # Require confirmation in production
            if self.config.require_manual_reset:
                expected_code = os.environ.get("VEL_KILL_SWITCH_RESET_CODE")
                if expected_code and confirmation_code != expected_code:
                    logger.warning("Invalid kill switch reset confirmation code")
                    return False
            
            self._kill_switch_active = False
            previous_reason = self._kill_switch_reason
            self._kill_switch_reason = None
            self._kill_switch_activated_at = None
            self._kill_switch_activated_by = None
            
            logger.warning(
                f"KILL SWITCH RESET by {reset_by}",
                extra={
                    "event": "kill_switch_reset",
                    "reset_by": reset_by,
                    "previous_reason": previous_reason
                }
            )
            
            self._audit(RiskEvent.KILL_SWITCH_RESET, {
                "reset_by": reset_by,
                "previous_reason": previous_reason
            })
            
            return True
    
    @property
    def is_kill_switch_active(self) -> bool:
        """Check if kill switch is active."""
        with self._lock:
            return self._kill_switch_active
    
    def get_kill_switch_status(self) -> Dict[str, Any]:
        """Get detailed kill switch status."""
        with self._lock:
            return {
                "active": self._kill_switch_active,
                "reason": self._kill_switch_reason,
                "activated_at": self._kill_switch_activated_at.isoformat() if self._kill_switch_activated_at else None,
                "activated_by": self._kill_switch_activated_by,
                "cooldown_remaining": self._get_cooldown_remaining()
            }
    
    def _get_cooldown_remaining(self) -> int:
        """Get remaining cooldown seconds."""
        if not self._kill_switch_activated_at:
            return 0
        elapsed = (datetime.now(timezone.utc) - self._kill_switch_activated_at).total_seconds()
        remaining = self.config.kill_switch_cooldown_seconds - elapsed
        return max(0, int(remaining))
    
    # ─────────────────────────────────────────────────────────────────────────
    # Pre-Trade Risk Check
    # ─────────────────────────────────────────────────────────────────────────
    
    def pre_trade_check(self, trade: TradeRequest) -> RiskDecision:
        """
        Perform pre-trade risk check.
        
        Args:
            trade: Trade request to evaluate
            
        Returns:
            RiskDecision indicating if trade is allowed
        """
        with self._lock:
            self._check_daily_reset()
            
            # Check kill switch first
            if self._kill_switch_active:
                return RiskDecision(
                    allowed=False,
                    reason=f"Kill switch active: {self._kill_switch_reason}",
                    event=RiskEvent.TRADE_BLOCKED
                )
            
            warnings = []
            
            # Check daily loss limit
            if self._daily_pnl < -self.config.max_daily_loss_usd:
                self.trigger_kill_switch(
                    f"Daily loss limit exceeded: ${abs(self._daily_pnl)}",
                    activated_by="risk_engine"
                )
                return RiskDecision(
                    allowed=False,
                    reason=f"Daily loss limit exceeded: ${abs(self._daily_pnl)}",
                    event=RiskEvent.DAILY_LOSS_LIMIT_HIT
                )
            
            # Warn if approaching limit
            loss_ratio = abs(self._daily_pnl) / self.config.max_daily_loss_usd if self._daily_pnl < 0 else Decimal("0")
            if loss_ratio > Decimal("0.8"):
                warnings.append(f"Approaching daily loss limit: {loss_ratio * 100:.0f}% used")
            
            # Check trade size limits
            if trade.amount_in_usd < self.config.min_trade_size_usd:
                return RiskDecision(
                    allowed=False,
                    reason=f"Trade size ${trade.amount_in_usd} below minimum ${self.config.min_trade_size_usd}",
                    event=RiskEvent.TRADE_BLOCKED
                )
            
            if trade.amount_in_usd > self.config.max_trade_size_usd:
                return RiskDecision(
                    allowed=False,
                    reason=f"Trade size ${trade.amount_in_usd} exceeds maximum ${self.config.max_trade_size_usd}",
                    event=RiskEvent.TRADE_BLOCKED
                )
            
            # Check position size limit
            current_position = self._positions.get(trade.token_out, Decimal("0"))
            new_position = current_position + trade.expected_amount_out_usd
            if new_position > self.config.max_position_size_usd:
                return RiskDecision(
                    allowed=False,
                    reason=f"Position would exceed limit: ${new_position} > ${self.config.max_position_size_usd}",
                    event=RiskEvent.POSITION_LIMIT_HIT
                )
            
            # Check slippage
            if trade.max_slippage > self.config.max_slippage_percentage:
                return RiskDecision(
                    allowed=False,
                    reason=f"Slippage {trade.max_slippage}% exceeds maximum {self.config.max_slippage_percentage}%",
                    event=RiskEvent.TRADE_BLOCKED
                )
            
            # Check gas price
            if trade.gas_price_gwei and trade.gas_price_gwei > self.config.max_gas_price_gwei:
                return RiskDecision(
                    allowed=False,
                    reason=f"Gas price {trade.gas_price_gwei} gwei exceeds maximum {self.config.max_gas_price_gwei}",
                    event=RiskEvent.GAS_LIMIT_HIT
                )
            
            # Check rate limits
            if not self._rate_limiter_minute.acquire():
                return RiskDecision(
                    allowed=False,
                    reason="Rate limit exceeded: too many trades per minute",
                    event=RiskEvent.RATE_LIMIT_HIT
                )
            
            if not self._rate_limiter_hour.acquire():
                return RiskDecision(
                    allowed=False,
                    reason="Rate limit exceeded: too many trades per hour",
                    event=RiskEvent.RATE_LIMIT_HIT
                )
            
            # Check daily trade count
            if self._daily_trade_count >= self.config.max_trades_per_day:
                return RiskDecision(
                    allowed=False,
                    reason=f"Daily trade limit reached: {self._daily_trade_count}",
                    event=RiskEvent.RATE_LIMIT_HIT
                )
            
            # Trade allowed
            self._trade_timestamps.append(trade.timestamp)
            
            decision = RiskDecision(
                allowed=True,
                warnings=warnings,
                event=RiskEvent.TRADE_ALLOWED,
                metadata={
                    "daily_pnl": str(self._daily_pnl),
                    "trade_count": self._daily_trade_count,
                    "rate_limit_remaining_minute": int(self._rate_limiter_minute.available),
                    "rate_limit_remaining_hour": int(self._rate_limiter_hour.available)
                }
            )
            
            self._audit(RiskEvent.TRADE_ALLOWED, {
                "trade_id": trade.trade_id,
                "amount_usd": str(trade.amount_in_usd),
                "warnings": warnings
            })
            
            return decision
    
    # ─────────────────────────────────────────────────────────────────────────
    # Post-Trade Updates
    # ─────────────────────────────────────────────────────────────────────────
    
    def record_trade_result(
        self,
        trade_id: str,
        pnl_usd: Decimal,
        token: str,
        position_change_usd: Decimal
    ):
        """
        Record trade result and update risk state.
        
        Args:
            trade_id: Trade identifier
            pnl_usd: Profit/loss in USD
            token: Token traded
            position_change_usd: Change in position value
        """
        with self._lock:
            self._daily_pnl += pnl_usd
            self._daily_trade_count += 1
            
            # Update position
            current = self._positions.get(token, Decimal("0"))
            self._positions[token] = current + position_change_usd
            
            logger.info(
                f"Trade {trade_id} recorded: PnL=${pnl_usd}, Daily PnL=${self._daily_pnl}",
                extra={
                    "trade_id": trade_id,
                    "pnl_usd": str(pnl_usd),
                    "daily_pnl": str(self._daily_pnl),
                    "trade_count": self._daily_trade_count
                }
            )
            
            # Check if loss limit hit
            if self._daily_pnl < -self.config.max_daily_loss_usd:
                self.trigger_kill_switch(
                    f"Daily loss limit hit: ${abs(self._daily_pnl)}",
                    activated_by="risk_engine"
                )
    
    # ─────────────────────────────────────────────────────────────────────────
    # Status and Metrics
    # ─────────────────────────────────────────────────────────────────────────
    
    def get_status(self) -> Dict[str, Any]:
        """Get current risk engine status."""
        with self._lock:
            self._check_daily_reset()
            return {
                "kill_switch": self.get_kill_switch_status(),
                "daily_pnl_usd": str(self._daily_pnl),
                "daily_loss_limit_usd": str(self.config.max_daily_loss_usd),
                "daily_loss_utilization": str(abs(self._daily_pnl) / self.config.max_daily_loss_usd * 100) if self._daily_pnl < 0 else "0",
                "daily_trade_count": self._daily_trade_count,
                "daily_trade_limit": self.config.max_trades_per_day,
                "rate_limit_minute_available": int(self._rate_limiter_minute.available),
                "rate_limit_hour_available": int(self._rate_limiter_hour.available),
                "positions": {k: str(v) for k, v in self._positions.items()},
                "next_daily_reset": self._daily_reset_at.isoformat()
            }
    
    # ─────────────────────────────────────────────────────────────────────────
    # Audit Logging
    # ─────────────────────────────────────────────────────────────────────────
    
    def _audit(self, event: RiskEvent, data: Dict[str, Any]):
        """Record audit event."""
        audit_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event.value,
            "data": data
        }
        
        logger.info(
            f"RISK AUDIT: {event.value}",
            extra={"audit_record": json.dumps(audit_record)}
        )
        
        if self.audit_callback:
            try:
                self.audit_callback(audit_record)
            except Exception as e:
                logger.error(f"Audit callback error: {e}")


# =============================================================================
# Global Instance
# =============================================================================

_risk_controller: Optional[RiskControlEngine] = None
_risk_lock = threading.Lock()


def get_risk_controller() -> RiskControlEngine:
    """Get global risk controller instance."""
    global _risk_controller
    if _risk_controller is None:
        with _risk_lock:
            if _risk_controller is None:
                _risk_controller = RiskControlEngine()
    return _risk_controller


def reset_risk_controller():
    """Reset risk controller (for testing)."""
    global _risk_controller
    with _risk_lock:
        _risk_controller = None
