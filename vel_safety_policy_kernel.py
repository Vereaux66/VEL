#!/usr/bin/env python3
"""
VEL Safety Policy Kernel
=========================

SINGLE AUTHORITATIVE SOURCE for all execution safety configuration.

This module unifies:
  - Emergency stop policy
  - Global trade caps (per-minute, per-hour, per-day)
  - Drawdown kill-switch
  - Rate throttling enforcement
  - Position size hard limits
  - Circuit breaker thresholds

NO OTHER MODULE may define execution safety policy.
All safety checks route through this kernel before any trade executes.

Architecture:
  SafetyPolicyKernel is initialized ONCE at system startup.
  It is injected into the trade engine, risk kernel, and execution core.
  It exposes a single gate: allow_execution(intent) -> (bool, reason)
  If the gate returns False, the trade MUST NOT execute. Period.
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("vel.safety_policy")


class EmergencyStopState(Enum):
    """Emergency stop states."""
    CLEAR = "clear"
    TRIGGERED = "triggered"
    COOLDOWN = "cooldown"


class ThrottleLevel(Enum):
    """Rate throttle levels."""
    NORMAL = "normal"
    ELEVATED = "elevated"
    RESTRICTED = "restricted"
    HALTED = "halted"


@dataclass(frozen=True)
class SafetyPolicyConfig:
    """
    Immutable safety policy configuration.
    Changes require system restart — by design.
    """
    # ── Emergency Stop ──────────────────────────────────────────
    emergency_stop_cooldown_seconds: int = 300  # 5 min cooldown after e-stop

    # ── Global Trade Caps ───────────────────────────────────────
    max_trades_per_minute: int = 10
    max_trades_per_hour: int = 120
    max_trades_per_day: int = 1000
    max_usd_volume_per_hour: Decimal = Decimal("500000")
    max_usd_volume_per_day: Decimal = Decimal("2000000")

    # ── Position Size Hard Limits ───────────────────────────────
    max_single_trade_usd: Decimal = Decimal("50000")
    max_portfolio_allocation_pct: Decimal = Decimal("0.25")  # 25% max per asset

    # ── Drawdown Kill-Switch ────────────────────────────────────
    drawdown_warn_pct: Decimal = Decimal("0.03")     # 3% warning
    drawdown_restrict_pct: Decimal = Decimal("0.05")  # 5% restrict new positions
    drawdown_halt_pct: Decimal = Decimal("0.10")      # 10% halt all trading
    drawdown_window_seconds: int = 86400              # 24h rolling window

    # ── Rate Throttling ─────────────────────────────────────────
    throttle_check_interval_seconds: float = 1.0
    elevated_threshold_pct: Decimal = Decimal("0.70")   # 70% of cap = elevated
    restricted_threshold_pct: Decimal = Decimal("0.90")  # 90% of cap = restricted

    # ── Circuit Breaker Integration ─────────────────────────────
    max_consecutive_failures: int = 5
    failure_window_seconds: int = 300  # 5 minutes
    circuit_reset_seconds: int = 60    # 1 min open before half-open


@dataclass
class TradeRecord:
    """Lightweight trade record for rate tracking."""
    timestamp: float
    value_usd: Decimal
    trade_id: str


@dataclass
class SafetyGateResult:
    """Result of safety gate check."""
    allowed: bool
    reason: str
    throttle_level: ThrottleLevel
    warnings: List[str] = field(default_factory=list)
    checked_at: float = field(default_factory=time.time)


class SafetyPolicyKernel:
    """
    Centralized execution safety enforcement.

    Every trade execution path MUST call allow_execution() before proceeding.
    This is the single point of enforcement for all safety policy.
    """

    def __init__(self, config: Optional[SafetyPolicyConfig] = None):
        self._config = config or SafetyPolicyConfig()
        self._lock = threading.RLock()

        # ── Emergency Stop State ───────────────────────────────
        self._emergency_stop_state = EmergencyStopState.CLEAR
        self._emergency_stop_triggered_at: Optional[float] = None
        self._emergency_stop_reason: Optional[str] = None

        # ── Trade Rate Tracking ────────────────────────────────
        self._recent_trades: deque = deque(maxlen=10000)
        self._throttle_level = ThrottleLevel.NORMAL

        # ── Drawdown Tracking ──────────────────────────────────
        self._pnl_records: deque = deque(maxlen=50000)
        self._portfolio_high_watermark_usd = Decimal("0")
        self._current_portfolio_value_usd = Decimal("0")
        self._drawdown_halt_active = False

        # ── Failure Tracking ───────────────────────────────────
        self._failure_timestamps: deque = deque(maxlen=1000)
        self._circuit_open = False
        self._circuit_opened_at: Optional[float] = None

        # ── Callbacks ──────────────────────────────────────────
        self._on_emergency_stop: List[Callable] = []
        self._on_throttle_change: List[Callable] = []
        self._on_drawdown_halt: List[Callable] = []

        logger.info(
            "Safety policy kernel initialized: "
            f"max_trades/min={self._config.max_trades_per_minute}, "
            f"max_trades/hr={self._config.max_trades_per_hour}, "
            f"drawdown_halt={self._config.drawdown_halt_pct * 100}%%"
        )

    @property
    def config(self) -> SafetyPolicyConfig:
        """Read-only access to safety config."""
        return self._config

    # ══════════════════════════════════════════════════════════════
    #  PRIMARY GATE — every execution path calls this
    # ══════════════════════════════════════════════════════════════

    def allow_execution(
        self,
        trade_value_usd: Decimal,
        trade_id: str = "",
    ) -> SafetyGateResult:
        """
        Single gate for all trade execution.

        Returns:
            SafetyGateResult: allowed=True if trade may proceed.
        """
        with self._lock:
            warnings: List[str] = []
            now = time.time()

            # ── Check 1: Emergency Stop ────────────────────────
            estop = self._check_emergency_stop(now)
            if estop is not None:
                return estop

            # ── Check 2: Circuit Breaker ───────────────────────
            cb = self._check_circuit_breaker(now)
            if cb is not None:
                return cb

            # ── Check 3: Drawdown Kill-Switch ──────────────────
            dd = self._check_drawdown(now, warnings)
            if dd is not None:
                return dd

            # ── Check 4: Single Trade Size ─────────────────────
            if trade_value_usd > self._config.max_single_trade_usd:
                return SafetyGateResult(
                    allowed=False,
                    reason=(
                        f"Trade value ${trade_value_usd} exceeds "
                        f"max ${self._config.max_single_trade_usd}"
                    ),
                    throttle_level=self._throttle_level,
                )

            # ── Check 5: Rate Caps ─────────────────────────────
            rate = self._check_rate_caps(now, trade_value_usd, warnings)
            if rate is not None:
                return rate

            # ── All checks passed — record trade ───────────────
            self._recent_trades.append(
                TradeRecord(
                    timestamp=now,
                    value_usd=trade_value_usd,
                    trade_id=trade_id,
                )
            )

            return SafetyGateResult(
                allowed=True,
                reason="all_checks_passed",
                throttle_level=self._throttle_level,
                warnings=warnings,
            )

    # ══════════════════════════════════════════════════════════════
    #  EMERGENCY STOP
    # ══════════════════════════════════════════════════════════════

    def trigger_emergency_stop(self, reason: str = "manual") -> None:
        """Trigger emergency stop. Halts ALL execution immediately."""
        with self._lock:
            self._emergency_stop_state = EmergencyStopState.TRIGGERED
            self._emergency_stop_triggered_at = time.time()
            self._emergency_stop_reason = reason
            logger.critical(f"EMERGENCY STOP TRIGGERED: {reason}")
            for cb in self._on_emergency_stop:
                try:
                    cb(reason)
                except Exception:
                    pass

    def clear_emergency_stop(self) -> bool:
        """
        Clear emergency stop if cooldown has elapsed.

        Returns:
            True if cleared, False if cooldown still active.
        """
        with self._lock:
            if self._emergency_stop_state == EmergencyStopState.CLEAR:
                return True

            now = time.time()
            triggered_at = self._emergency_stop_triggered_at or 0
            elapsed = now - triggered_at

            if elapsed < self._config.emergency_stop_cooldown_seconds:
                remaining = self._config.emergency_stop_cooldown_seconds - elapsed
                logger.warning(
                    f"Cannot clear e-stop: {remaining:.0f}s cooldown remaining"
                )
                return False

            self._emergency_stop_state = EmergencyStopState.CLEAR
            self._emergency_stop_triggered_at = None
            self._emergency_stop_reason = None
            logger.info("Emergency stop cleared")
            return True

    def _check_emergency_stop(self, now: float) -> Optional[SafetyGateResult]:
        """Check emergency stop state."""
        if self._emergency_stop_state == EmergencyStopState.CLEAR:
            return None

        reason = self._emergency_stop_reason or "emergency_stop_active"

        if self._emergency_stop_state == EmergencyStopState.TRIGGERED:
            triggered_at = self._emergency_stop_triggered_at or 0
            elapsed = now - triggered_at
            if elapsed >= self._config.emergency_stop_cooldown_seconds:
                self._emergency_stop_state = EmergencyStopState.COOLDOWN
                return SafetyGateResult(
                    allowed=False,
                    reason=f"emergency_stop_cooldown: {reason}",
                    throttle_level=ThrottleLevel.HALTED,
                )

        return SafetyGateResult(
            allowed=False,
            reason=f"emergency_stop: {reason}",
            throttle_level=ThrottleLevel.HALTED,
        )

    # ══════════════════════════════════════════════════════════════
    #  DRAWDOWN KILL-SWITCH
    # ══════════════════════════════════════════════════════════════

    def update_portfolio_value(self, value_usd: Decimal) -> None:
        """Update current portfolio value for drawdown tracking."""
        with self._lock:
            self._current_portfolio_value_usd = value_usd
            if value_usd > self._portfolio_high_watermark_usd:
                self._portfolio_high_watermark_usd = value_usd

    def record_pnl(self, pnl_usd: Decimal) -> None:
        """Record a PnL event for rolling drawdown calculation."""
        with self._lock:
            self._pnl_records.append((time.time(), pnl_usd))

    def _check_drawdown(
        self, now: float, warnings: List[str]
    ) -> Optional[SafetyGateResult]:
        """Check drawdown limits."""
        if self._portfolio_high_watermark_usd <= 0:
            return None

        current_drawdown = (
            self._portfolio_high_watermark_usd - self._current_portfolio_value_usd
        )
        drawdown_pct = current_drawdown / self._portfolio_high_watermark_usd

        # Rolling window PnL check
        window_start = now - self._config.drawdown_window_seconds
        rolling_loss = sum(
            pnl for ts, pnl in self._pnl_records
            if ts >= window_start and pnl < 0
        )
        rolling_loss_pct = Decimal("0")
        if self._portfolio_high_watermark_usd > 0:
            rolling_loss_pct = abs(rolling_loss) / self._portfolio_high_watermark_usd

        effective_drawdown_pct = max(drawdown_pct, rolling_loss_pct)

        # HALT threshold
        if effective_drawdown_pct >= self._config.drawdown_halt_pct:
            if not self._drawdown_halt_active:
                self._drawdown_halt_active = True
                logger.critical(
                    f"DRAWDOWN KILL-SWITCH: {effective_drawdown_pct:.2%} "
                    f">= {self._config.drawdown_halt_pct:.2%} — halting all trading"
                )
                for cb in self._on_drawdown_halt:
                    try:
                        cb(effective_drawdown_pct)
                    except Exception:
                        pass

            return SafetyGateResult(
                allowed=False,
                reason=(
                    f"drawdown_halt: {effective_drawdown_pct:.2%} "
                    f">= {self._config.drawdown_halt_pct:.2%}"
                ),
                throttle_level=ThrottleLevel.HALTED,
            )

        # RESTRICT threshold
        if effective_drawdown_pct >= self._config.drawdown_restrict_pct:
            return SafetyGateResult(
                allowed=False,
                reason=(
                    f"drawdown_restricted: {effective_drawdown_pct:.2%} "
                    f">= {self._config.drawdown_restrict_pct:.2%}"
                ),
                throttle_level=ThrottleLevel.RESTRICTED,
            )

        # WARN threshold
        if effective_drawdown_pct >= self._config.drawdown_warn_pct:
            warnings.append(
                f"drawdown_warning: {effective_drawdown_pct:.2%} "
                f">= {self._config.drawdown_warn_pct:.2%}"
            )

        # Reset halt if recovered
        if self._drawdown_halt_active and effective_drawdown_pct < self._config.drawdown_warn_pct:
            self._drawdown_halt_active = False
            logger.info("Drawdown recovered below warning threshold")

        return None

    def reset_drawdown_halt(self) -> None:
        """Manual reset of drawdown halt (admin function)."""
        with self._lock:
            self._drawdown_halt_active = False
            self._portfolio_high_watermark_usd = self._current_portfolio_value_usd
            logger.warning("Drawdown halt manually reset — high watermark recalibrated")

    # ══════════════════════════════════════════════════════════════
    #  RATE CAPS & THROTTLING
    # ══════════════════════════════════════════════════════════════

    def _check_rate_caps(
        self,
        now: float,
        trade_value_usd: Decimal,
        warnings: List[str],
    ) -> Optional[SafetyGateResult]:
        """Check trade rate caps and volume caps."""
        one_minute_ago = now - 60
        one_hour_ago = now - 3600
        one_day_ago = now - 86400

        trades_last_minute = sum(
            1 for t in self._recent_trades if t.timestamp >= one_minute_ago
        )
        trades_last_hour = sum(
            1 for t in self._recent_trades if t.timestamp >= one_hour_ago
        )
        trades_last_day = sum(
            1 for t in self._recent_trades if t.timestamp >= one_day_ago
        )
        volume_last_hour = sum(
            t.value_usd for t in self._recent_trades if t.timestamp >= one_hour_ago
        )
        volume_last_day = sum(
            t.value_usd for t in self._recent_trades if t.timestamp >= one_day_ago
        )

        # Hard caps — absolute rejection
        if trades_last_minute >= self._config.max_trades_per_minute:
            return SafetyGateResult(
                allowed=False,
                reason=f"rate_cap_minute: {trades_last_minute}/{self._config.max_trades_per_minute}",
                throttle_level=ThrottleLevel.HALTED,
            )

        if trades_last_hour >= self._config.max_trades_per_hour:
            return SafetyGateResult(
                allowed=False,
                reason=f"rate_cap_hour: {trades_last_hour}/{self._config.max_trades_per_hour}",
                throttle_level=ThrottleLevel.HALTED,
            )

        if trades_last_day >= self._config.max_trades_per_day:
            return SafetyGateResult(
                allowed=False,
                reason=f"rate_cap_day: {trades_last_day}/{self._config.max_trades_per_day}",
                throttle_level=ThrottleLevel.HALTED,
            )

        if volume_last_hour + trade_value_usd > self._config.max_usd_volume_per_hour:
            return SafetyGateResult(
                allowed=False,
                reason=(
                    f"volume_cap_hour: ${volume_last_hour + trade_value_usd} "
                    f"> ${self._config.max_usd_volume_per_hour}"
                ),
                throttle_level=ThrottleLevel.HALTED,
            )

        if volume_last_day + trade_value_usd > self._config.max_usd_volume_per_day:
            return SafetyGateResult(
                allowed=False,
                reason=(
                    f"volume_cap_day: ${volume_last_day + trade_value_usd} "
                    f"> ${self._config.max_usd_volume_per_day}"
                ),
                throttle_level=ThrottleLevel.HALTED,
            )

        # Throttle level calculation
        minute_utilization = Decimal(trades_last_minute) / Decimal(self._config.max_trades_per_minute)
        hour_utilization = Decimal(trades_last_hour) / Decimal(self._config.max_trades_per_hour)
        max_utilization = max(minute_utilization, hour_utilization)

        old_level = self._throttle_level
        if max_utilization >= self._config.restricted_threshold_pct:
            self._throttle_level = ThrottleLevel.RESTRICTED
            warnings.append(f"rate_utilization_restricted: {max_utilization:.0%}")
        elif max_utilization >= self._config.elevated_threshold_pct:
            self._throttle_level = ThrottleLevel.ELEVATED
            warnings.append(f"rate_utilization_elevated: {max_utilization:.0%}")
        else:
            self._throttle_level = ThrottleLevel.NORMAL

        if self._throttle_level != old_level:
            logger.info(f"Throttle level changed: {old_level.value} -> {self._throttle_level.value}")
            for cb in self._on_throttle_change:
                try:
                    cb(old_level, self._throttle_level)
                except Exception:
                    pass

        return None

    # ══════════════════════════════════════════════════════════════
    #  CIRCUIT BREAKER
    # ══════════════════════════════════════════════════════════════

    def record_execution_failure(self) -> None:
        """Record an execution failure for circuit breaker tracking."""
        with self._lock:
            self._failure_timestamps.append(time.time())

    def _check_circuit_breaker(self, now: float) -> Optional[SafetyGateResult]:
        """Check circuit breaker state."""
        if self._circuit_open:
            opened_at = self._circuit_opened_at or 0
            elapsed = now - opened_at
            if elapsed < self._config.circuit_reset_seconds:
                return SafetyGateResult(
                    allowed=False,
                    reason=(
                        f"circuit_breaker_open: "
                        f"{self._config.circuit_reset_seconds - elapsed:.0f}s remaining"
                    ),
                    throttle_level=ThrottleLevel.HALTED,
                )
            # Half-open: allow one trade to test
            self._circuit_open = False
            self._circuit_opened_at = None
            logger.info("Circuit breaker half-open — allowing test execution")
            return None

        # Check recent failure rate
        window_start = now - self._config.failure_window_seconds
        recent_failures = sum(
            1 for ts in self._failure_timestamps if ts >= window_start
        )

        if recent_failures >= self._config.max_consecutive_failures:
            self._circuit_open = True
            self._circuit_opened_at = now
            logger.error(
                f"Circuit breaker OPENED: {recent_failures} failures "
                f"in {self._config.failure_window_seconds}s window"
            )
            return SafetyGateResult(
                allowed=False,
                reason=f"circuit_breaker_tripped: {recent_failures} failures",
                throttle_level=ThrottleLevel.HALTED,
            )

        return None

    # ══════════════════════════════════════════════════════════════
    #  CALLBACKS
    # ══════════════════════════════════════════════════════════════

    def on_emergency_stop(self, callback: Callable) -> None:
        """Register callback for emergency stop events."""
        self._on_emergency_stop.append(callback)

    def on_throttle_change(self, callback: Callable) -> None:
        """Register callback for throttle level changes."""
        self._on_throttle_change.append(callback)

    def on_drawdown_halt(self, callback: Callable) -> None:
        """Register callback for drawdown halt events."""
        self._on_drawdown_halt.append(callback)

    # ══════════════════════════════════════════════════════════════
    #  STATUS & MONITORING
    # ══════════════════════════════════════════════════════════════

    def get_status(self) -> Dict[str, Any]:
        """Get complete safety policy status for monitoring."""
        with self._lock:
            now = time.time()
            one_minute_ago = now - 60
            one_hour_ago = now - 3600
            one_day_ago = now - 86400

            trades_min = sum(1 for t in self._recent_trades if t.timestamp >= one_minute_ago)
            trades_hr = sum(1 for t in self._recent_trades if t.timestamp >= one_hour_ago)
            trades_day = sum(1 for t in self._recent_trades if t.timestamp >= one_day_ago)
            vol_hr = sum(t.value_usd for t in self._recent_trades if t.timestamp >= one_hour_ago)
            vol_day = sum(t.value_usd for t in self._recent_trades if t.timestamp >= one_day_ago)

            drawdown_pct = Decimal("0")
            if self._portfolio_high_watermark_usd > 0:
                drawdown_pct = (
                    (self._portfolio_high_watermark_usd - self._current_portfolio_value_usd)
                    / self._portfolio_high_watermark_usd
                )

            return {
                "emergency_stop": self._emergency_stop_state.value,
                "emergency_stop_reason": self._emergency_stop_reason,
                "throttle_level": self._throttle_level.value,
                "circuit_breaker_open": self._circuit_open,
                "drawdown_halt_active": self._drawdown_halt_active,
                "drawdown_pct": float(drawdown_pct),
                "portfolio_high_watermark_usd": str(self._portfolio_high_watermark_usd),
                "portfolio_current_usd": str(self._current_portfolio_value_usd),
                "rate_caps": {
                    "trades_per_minute": f"{trades_min}/{self._config.max_trades_per_minute}",
                    "trades_per_hour": f"{trades_hr}/{self._config.max_trades_per_hour}",
                    "trades_per_day": f"{trades_day}/{self._config.max_trades_per_day}",
                    "volume_per_hour_usd": f"{vol_hr}/{self._config.max_usd_volume_per_hour}",
                    "volume_per_day_usd": f"{vol_day}/{self._config.max_usd_volume_per_day}",
                },
            }
