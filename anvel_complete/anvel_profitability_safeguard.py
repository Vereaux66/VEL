#!/usr/bin/env python3
"""
ANVEL Profitability Safeguard System

CRITICAL SAFETY MODULE:
Implements profitability safeguards to protect users from continued trading
during losing streaks. Enforces tier-specific win rate thresholds and halts
trading when performance falls below acceptable levels.

IMPORTANT DISCLAIMER:
This module does NOT guarantee profits. It is designed to LIMIT LOSSES by
halting trading when win rates fall below thresholds. Past performance does
not predict future results. All trading involves risk of loss.

DEPENDENCIES:
- Requires `users` table to exist (from anvel_database_schema.sql)
- Requires `trades` table to exist for performance calculation
- Requires PostgreSQL with UUID support
- Optional: Redis for caching (will operate without it)

Thread-safe and production-ready for capital-touching operations.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor
import redis

log = logging.getLogger(__name__)


class TradingStatus(Enum):
    """Trading status for safeguard enforcement."""
    ACTIVE = "active"
    HALTED_LOW_WIN_RATE = "halted_low_win_rate"
    HALTED_MANUAL = "halted_manual"
    HALTED_ADMIN = "halted_admin"


class SubscriptionTier(Enum):
    """Subscription tiers matching anvel_subscription_manager."""
    BASIC = "basic"
    PREMIUM = "premium"


@dataclass
class WinRateThreshold:
    """Win rate threshold configuration per tier."""
    tier: SubscriptionTier
    minimum_win_rate: Decimal
    minimum_trades_required: int
    evaluation_window_days: int

    def __str__(self) -> str:
        return (
            f"{self.tier.value}: {float(self.minimum_win_rate)*100}% win rate "
            f"(min {self.minimum_trades_required} trades, {self.evaluation_window_days} day window)"
        )


@dataclass
class ProfitabilityMetrics:
    """Current profitability metrics for a user."""
    user_id: str
    tier: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: Decimal
    total_pnl: Decimal
    average_pnl: Decimal
    evaluation_period_start: datetime
    evaluation_period_end: datetime
    trading_status: TradingStatus
    threshold_win_rate: Decimal
    trades_until_evaluation: int

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "user_id": self.user_id,
            "tier": self.tier,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": float(self.win_rate),
            "total_pnl": float(self.total_pnl),
            "average_pnl": float(self.average_pnl),
            "evaluation_period_start": self.evaluation_period_start.isoformat(),
            "evaluation_period_end": self.evaluation_period_end.isoformat(),
            "trading_status": self.trading_status.value,
            "threshold_win_rate": float(self.threshold_win_rate),
            "trades_until_evaluation": self.trades_until_evaluation,
        }


# Tier-specific win rate thresholds
# IMPORTANT: These thresholds are for LOSS PREVENTION, not profit guarantees
WIN_RATE_THRESHOLDS: Dict[SubscriptionTier, WinRateThreshold] = {
    SubscriptionTier.BASIC: WinRateThreshold(
        tier=SubscriptionTier.BASIC,
        minimum_win_rate=Decimal("0.50"),  # 50% win rate
        minimum_trades_required=20,  # Need 20 trades before evaluation
        evaluation_window_days=30,
    ),
    SubscriptionTier.PREMIUM: WinRateThreshold(
        tier=SubscriptionTier.PREMIUM,
        minimum_win_rate=Decimal("0.80"),  # 80% win rate
        minimum_trades_required=20,  # Need 20 trades before evaluation
        evaluation_window_days=30,
    ),
}


class ANVELProfitabilitySafeguard:
    """
    Manages profitability safeguards and trading halts.
    
    This system tracks user trading performance and automatically halts
    trading when win rates fall below tier-specific thresholds, protecting
    users from continued losses during losing streaks.
    
    Thread-safe and idempotent for production deployment.
    """

    def __init__(
        self,
        db_config: Dict,
        redis_config: Optional[Dict] = None,
    ):
        """
        Initialize profitability safeguard system.
        
        Args:
            db_config: PostgreSQL connection parameters
            redis_config: Redis connection parameters for caching
        """
        self.db_config = db_config
        self.redis_client: Optional[redis.Redis] = None

        if redis_config:
            try:
                self.redis_client = redis.Redis(
                    host=redis_config.get("host", "localhost"),
                    port=redis_config.get("port", 6379),
                    password=redis_config.get("password"),
                    db=redis_config.get("db", 0),
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                )
                self.redis_client.ping()
                log.info("Profitability safeguard Redis cache connected")
            except redis.RedisError as e:
                log.warning(f"Redis connection failed, operating without cache: {e}")
                self.redis_client = None

        self._ensure_schema()

    def _get_db_connection(self):
        """Get database connection with proper configuration."""
        return psycopg2.connect(
            host=self.db_config["host"],
            port=self.db_config.get("port", 5432),
            dbname=self.db_config["database"],
            user=self.db_config["user"],
            password=self.db_config["password"],
            connect_timeout=10,
        )

    def _ensure_schema(self):
        """
        Ensure profitability safeguard tables exist.
        Idempotent - safe to call multiple times.
        
        Note: Requires users and trades tables to exist first.
        These are created by anvel_database_schema.sql.
        """
        with self._get_db_connection() as conn:
            with conn.cursor() as cur:
                # Verify required tables exist
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name IN ('users', 'trades')
                        GROUP BY table_schema
                        HAVING COUNT(*) = 2
                    )
                """)
                required_tables_exist = cur.fetchone()

                if not required_tables_exist or not required_tables_exist[0]:
                    raise RuntimeError(
                        "Required tables (users, trades) must exist before creating "
                        "profitability safeguard tables. Run anvel_database_schema.sql first."
                    )

                # Trading status tracking table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trading_status (
                        user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                        status VARCHAR(50) NOT NULL DEFAULT 'active',
                        halted_at TIMESTAMP WITH TIME ZONE,
                        halt_reason TEXT,
                        win_rate_at_halt DECIMAL(5, 4),
                        threshold_win_rate DECIMAL(5, 4),
                        total_trades_at_halt INTEGER,
                        can_resume_at TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Index for active status queries
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trading_status_status 
                    ON trading_status(status)
                """)

                # Profitability metrics snapshot table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS profitability_snapshots (
                        id SERIAL PRIMARY KEY,
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        tier VARCHAR(20) NOT NULL,
                        timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        total_trades INTEGER NOT NULL,
                        winning_trades INTEGER NOT NULL,
                        losing_trades INTEGER NOT NULL,
                        win_rate DECIMAL(5, 4) NOT NULL,
                        total_pnl DECIMAL(18, 8) NOT NULL,
                        average_pnl DECIMAL(18, 8) NOT NULL,
                        evaluation_period_days INTEGER NOT NULL,
                        threshold_win_rate DECIMAL(5, 4) NOT NULL,
                        passed_threshold BOOLEAN NOT NULL,
                        action_taken VARCHAR(50)
                    )
                """)

                # Index for user metrics history
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_profitability_snapshots_user 
                    ON profitability_snapshots(user_id, timestamp DESC)
                """)

                # Safeguard events log
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS safeguard_events (
                        id SERIAL PRIMARY KEY,
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        event_type VARCHAR(50) NOT NULL,
                        tier VARCHAR(20) NOT NULL,
                        win_rate DECIMAL(5, 4),
                        threshold_win_rate DECIMAL(5, 4),
                        total_trades INTEGER,
                        details JSONB DEFAULT '{}'
                    )
                """)

                # Index for event queries
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_safeguard_events_user_timestamp 
                    ON safeguard_events(user_id, timestamp DESC)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_safeguard_events_type 
                    ON safeguard_events(event_type, timestamp DESC)
                """)

                conn.commit()
                log.info("Profitability safeguard schema verified successfully")

    def get_user_metrics(
        self,
        user_id: str,
        tier: str,
        evaluation_window_days: Optional[int] = None,
    ) -> ProfitabilityMetrics:
        """
        Calculate current profitability metrics for a user.
        
        Args:
            user_id: UUID of the user
            tier: User's subscription tier (basic or premium)
            evaluation_window_days: Optional override for evaluation window
            
        Returns:
            ProfitabilityMetrics with current performance data
        """
        try:
            tier_enum = SubscriptionTier(tier.lower())
        except ValueError:
            raise ValueError(f"Invalid tier: {tier}. Must be 'basic' or 'premium'.")

        threshold_config = WIN_RATE_THRESHOLDS[tier_enum]
        window_days = evaluation_window_days or threshold_config.evaluation_window_days

        with self._get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get trading status
                cur.execute("""
                    SELECT status, halted_at, halt_reason
                    FROM trading_status
                    WHERE user_id = %s
                """, (user_id,))

                status_row = cur.fetchone()
                if status_row:
                    trading_status = TradingStatus(status_row["status"])
                else:
                    trading_status = TradingStatus.ACTIVE

                # Calculate metrics from trades table
                evaluation_start = datetime.utcnow() - timedelta(days=window_days)
                evaluation_end = datetime.utcnow()

                cur.execute("""
                    SELECT 
                        COUNT(*) as total_trades,
                        COUNT(*) FILTER (WHERE pnl > 0) as winning_trades,
                        COUNT(*) FILTER (WHERE pnl < 0) as losing_trades,
                        COALESCE(SUM(pnl), 0) as total_pnl,
                        COALESCE(AVG(pnl), 0) as average_pnl
                    FROM trades
                    WHERE user_id = %s
                      AND timestamp >= %s
                      AND timestamp <= %s
                      AND status = 'filled'
                      AND pnl IS NOT NULL
                """, (user_id, evaluation_start, evaluation_end))

                metrics = cur.fetchone()

                total_trades = metrics["total_trades"]
                winning_trades = metrics["winning_trades"]
                losing_trades = metrics["losing_trades"]
                total_pnl = Decimal(str(metrics["total_pnl"]))
                average_pnl = Decimal(str(metrics["average_pnl"]))

                # Calculate win rate
                if total_trades > 0:
                    win_rate = Decimal(winning_trades) / Decimal(total_trades)
                else:
                    win_rate = Decimal("0.0")

                # Determine trades until evaluation
                trades_until_evaluation = max(
                    0,
                    threshold_config.minimum_trades_required - total_trades
                )

                return ProfitabilityMetrics(
                    user_id=user_id,
                    tier=tier,
                    total_trades=total_trades,
                    winning_trades=winning_trades,
                    losing_trades=losing_trades,
                    win_rate=win_rate,
                    total_pnl=total_pnl,
                    average_pnl=average_pnl,
                    evaluation_period_start=evaluation_start,
                    evaluation_period_end=evaluation_end,
                    trading_status=trading_status,
                    threshold_win_rate=threshold_config.minimum_win_rate,
                    trades_until_evaluation=trades_until_evaluation,
                )

    def evaluate_and_enforce_safeguards(
        self,
        user_id: str,
        tier: str,
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluate user performance and enforce safeguards if needed.
        
        This is the core safeguard enforcement function. It:
        1. Calculates current win rate
        2. Compares against tier threshold
        3. Halts trading if below threshold
        4. Logs all actions
        
        Args:
            user_id: UUID of the user
            tier: User's subscription tier
            
        Returns:
            Tuple of (can_trade: bool, reason: Optional[str])
            If can_trade is False, reason contains explanation
        """
        metrics = self.get_user_metrics(user_id, tier)

        # If already halted, return immediately
        if metrics.trading_status != TradingStatus.ACTIVE:
            return False, f"Trading halted: {metrics.trading_status.value}"

        # If not enough trades yet, allow trading
        if metrics.trades_until_evaluation > 0:
            log.debug(
                f"User {user_id}: {metrics.trades_until_evaluation} more trades "
                f"needed before safeguard evaluation"
            )
            return True, None

        # Check win rate against threshold
        if metrics.win_rate < metrics.threshold_win_rate:
            # Win rate below threshold - HALT TRADING
            halt_reason = (
                f"Win rate {float(metrics.win_rate)*100:.1f}% is below "
                f"{float(metrics.threshold_win_rate)*100:.1f}% threshold for {tier} tier. "
                f"Trading halted for safety. Performance must improve before resuming."
            )

            self._halt_trading(
                user_id=user_id,
                tier=tier,
                metrics=metrics,
                reason=halt_reason,
            )

            log.warning(
                f"SAFEGUARD ACTIVATED - User {user_id} trading halted",
                extra={
                    "user_id": user_id,
                    "tier": tier,
                    "win_rate": float(metrics.win_rate),
                    "threshold": float(metrics.threshold_win_rate),
                    "total_trades": metrics.total_trades,
                    "total_pnl": float(metrics.total_pnl),
                }
            )

            return False, halt_reason

        # Performance acceptable - allow trading
        log.debug(
            f"User {user_id}: Win rate {float(metrics.win_rate)*100:.1f}% "
            f"exceeds {float(metrics.threshold_win_rate)*100:.1f}% threshold"
        )

        # Record successful evaluation
        self._record_snapshot(metrics, passed=True, action="none")

        return True, None

    def _halt_trading(
        self,
        user_id: str,
        tier: str,
        metrics: ProfitabilityMetrics,
        reason: str,
    ):
        """
        Halt trading for a user and record the event.
        
        Args:
            user_id: UUID of the user
            tier: User's subscription tier
            metrics: Current profitability metrics
            reason: Detailed reason for halt
        """
        with self._get_db_connection() as conn:
            with conn.cursor() as cur:
                # Update or insert trading status
                cur.execute("""
                    INSERT INTO trading_status (
                        user_id, status, halted_at, halt_reason,
                        win_rate_at_halt, threshold_win_rate, total_trades_at_halt
                    )
                    VALUES (%s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s)
                    ON CONFLICT (user_id)
                    DO UPDATE SET
                        status = EXCLUDED.status,
                        halted_at = EXCLUDED.halted_at,
                        halt_reason = EXCLUDED.halt_reason,
                        win_rate_at_halt = EXCLUDED.win_rate_at_halt,
                        threshold_win_rate = EXCLUDED.threshold_win_rate,
                        total_trades_at_halt = EXCLUDED.total_trades_at_halt,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    user_id,
                    TradingStatus.HALTED_LOW_WIN_RATE.value,
                    reason,
                    metrics.win_rate,
                    metrics.threshold_win_rate,
                    metrics.total_trades,
                ))

                # Log safeguard event
                cur.execute("""
                    INSERT INTO safeguard_events (
                        user_id, event_type, tier, win_rate, threshold_win_rate,
                        total_trades, details
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    user_id,
                    "trading_halted",
                    tier,
                    metrics.win_rate,
                    metrics.threshold_win_rate,
                    metrics.total_trades,
                    json.dumps({"reason": reason}),
                ))

                conn.commit()

        # Record snapshot
        self._record_snapshot(metrics, passed=False, action="halt_trading")

        # Invalidate cache
        if self.redis_client:
            self.redis_client.delete(f"trading_status:{user_id}")

    def _record_snapshot(
        self,
        metrics: ProfitabilityMetrics,
        passed: bool,
        action: str,
    ):
        """
        Record profitability metrics snapshot for historical tracking.
        
        Args:
            metrics: Current profitability metrics
            passed: Whether user passed threshold check
            action: Action taken (none, halt_trading, etc.)
        """
        with self._get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO profitability_snapshots (
                        user_id, tier, total_trades, winning_trades, losing_trades,
                        win_rate, total_pnl, average_pnl, evaluation_period_days,
                        threshold_win_rate, passed_threshold, action_taken
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    metrics.user_id,
                    metrics.tier,
                    metrics.total_trades,
                    metrics.winning_trades,
                    metrics.losing_trades,
                    metrics.win_rate,
                    metrics.total_pnl,
                    metrics.average_pnl,
                    (metrics.evaluation_period_end - metrics.evaluation_period_start).days,
                    metrics.threshold_win_rate,
                    passed,
                    action,
                ))
                conn.commit()

    def can_user_trade(self, user_id: str, tier: str) -> Tuple[bool, Optional[str]]:
        """
        Check if user is allowed to trade based on safeguard status.
        
        This is the primary public API for checking trading permissions.
        Call this before executing any trade.
        
        Args:
            user_id: UUID of the user
            tier: User's subscription tier
            
        Returns:
            Tuple of (can_trade: bool, reason: Optional[str])
        """
        # Check cache first
        cache_key = f"trading_status:{user_id}"
        if self.redis_client:
            cached = self.redis_client.get(cache_key)
            if cached:
                status_data = json.loads(cached)
                if status_data["status"] != "active":
                    return False, status_data.get("reason", "Trading halted")

        # Check database
        with self._get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT status, halt_reason
                    FROM trading_status
                    WHERE user_id = %s
                """, (user_id,))

                status_row = cur.fetchone()

                if status_row and status_row["status"] != TradingStatus.ACTIVE.value:
                    # Cache the halted status
                    if self.redis_client:
                        self.redis_client.setex(
                            cache_key,
                            300,  # 5 minutes
                            json.dumps({
                                "status": status_row["status"],
                                "reason": status_row["halt_reason"],
                            })
                        )
                    return False, status_row["halt_reason"]

        # No halt recorded - user can trade
        return True, None

    def resume_trading(
        self,
        user_id: str,
        admin_override: bool = False,
        admin_reason: Optional[str] = None,
    ) -> bool:
        """
        Resume trading for a halted user.
        
        Should only be called after:
        1. User has reviewed their strategy
        2. Sufficient time has passed
        3. Admin review (if admin_override=True)
        
        Args:
            user_id: UUID of the user
            admin_override: Whether this is an admin override
            admin_reason: Reason for admin override
            
        Returns:
            True if trading resumed, False otherwise
        """
        with self._get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Update status to active
                cur.execute("""
                    UPDATE trading_status
                    SET status = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s
                    RETURNING tier
                """, (TradingStatus.ACTIVE.value, user_id))

                result = cur.fetchone()

                if not result:
                    log.warning(f"No trading status found for user {user_id}")
                    return False

                tier = result.get("tier", "unknown")

                # Log resume event
                event_type = "trading_resumed_admin" if admin_override else "trading_resumed"
                details = {}
                if admin_override and admin_reason:
                    details["admin_reason"] = admin_reason

                cur.execute("""
                    INSERT INTO safeguard_events (
                        user_id, event_type, tier, details
                    )
                    VALUES (%s, %s, %s, %s)
                """, (user_id, event_type, tier, json.dumps(details)))

                conn.commit()

        # Invalidate cache
        if self.redis_client:
            self.redis_client.delete(f"trading_status:{user_id}")

        log.info(
            f"Trading resumed for user {user_id}",
            extra={
                "user_id": user_id,
                "admin_override": admin_override,
                "admin_reason": admin_reason,
            }
        )

        return True

    def get_safeguard_history(
        self,
        user_id: str,
        limit: int = 50,
    ) -> List[Dict]:
        """
        Get safeguard event history for a user.
        
        Args:
            user_id: UUID of the user
            limit: Maximum number of events to return
            
        Returns:
            List of safeguard events
        """
        with self._get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        id, timestamp, event_type, tier,
                        win_rate, threshold_win_rate, total_trades, details
                    FROM safeguard_events
                    WHERE user_id = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                """, (user_id, limit))

                events = cur.fetchall()

                return [
                    {
                        "id": event["id"],
                        "timestamp": event["timestamp"].isoformat(),
                        "event_type": event["event_type"],
                        "tier": event["tier"],
                        "win_rate": float(event["win_rate"]) if event["win_rate"] else None,
                        "threshold_win_rate": float(event["threshold_win_rate"]) if event["threshold_win_rate"] else None,
                        "total_trades": event["total_trades"],
                        "details": event["details"],
                    }
                    for event in events
                ]


if __name__ == "__main__":
    # Example usage and testing

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # This would require actual database configuration
    print("ANVEL Profitability Safeguard System")
    print("=" * 60)
    print("\nWin Rate Thresholds:")
    for tier, config in WIN_RATE_THRESHOLDS.items():
        print(f"  {config}")
    print("\nIMPORTANT: This system provides LOSS PREVENTION, not profit guarantees.")
    print("All trading involves risk. Past performance does not predict future results.")
