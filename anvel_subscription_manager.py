#!/usr/bin/env python3
"""
ANVEL Subscription Management System
Handles multi-tier subscriptions with crypto payment support for SaaS deployment.
Designed for 100k+ concurrent users with proper state management and idempotency.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional
from dataclasses import dataclass

import psycopg2
from psycopg2.extras import RealDictCursor
import redis

log = logging.getLogger(__name__)


class SubscriptionTier(Enum):
    """
    Subscription tier definitions with clear limits.
    
    IMPORTANT PROFIT DISCLAIMER:
    VEL is a trading system that uses AI to analyze markets and execute trades.
    Past performance does not guarantee future results. Trading involves substantial
    risk of loss. Profitability cannot be guaranteed regardless of subscription tier.
    Users should only trade with capital they can afford to lose.
    """
    BASIC = "basic"
    PREMIUM = "premium"


class PaymentStatus(Enum):
    """Payment lifecycle states."""
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    REFUNDED = "refunded"
    FAILED = "failed"


@dataclass
class TierLimits:
    """Resource limits per subscription tier."""
    max_api_calls_per_minute: int
    max_active_positions: int
    max_daily_trades: int
    max_exchanges: int
    ai_features_enabled: bool
    backtesting_enabled: bool
    advanced_analytics: bool
    priority_support: bool
    monthly_price_usd: Decimal

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "max_api_calls_per_minute": self.max_api_calls_per_minute,
            "max_active_positions": self.max_active_positions,
            "max_daily_trades": self.max_daily_trades,
            "max_exchanges": self.max_exchanges,
            "ai_features_enabled": self.ai_features_enabled,
            "backtesting_enabled": self.backtesting_enabled,
            "advanced_analytics": self.advanced_analytics,
            "priority_support": self.priority_support,
            "monthly_price_usd": float(self.monthly_price_usd)
        }


# Tier configurations optimized for scalability
# DISCLAIMER: Subscription tiers provide different resource limits and features.
# Higher tiers do NOT guarantee higher profits or trading success.
# All trading involves risk of loss regardless of tier.
TIER_LIMITS: Dict[SubscriptionTier, TierLimits] = {
    SubscriptionTier.BASIC: TierLimits(
        max_api_calls_per_minute=60,
        max_active_positions=5,
        max_daily_trades=50,
        max_exchanges=2,
        ai_features_enabled=True,
        backtesting_enabled=True,
        advanced_analytics=True,
        priority_support=False,
        monthly_price_usd=Decimal("20.00")  # Updated to $20/month standard
    ),
    SubscriptionTier.PREMIUM: TierLimits(
        max_api_calls_per_minute=200,
        max_active_positions=20,
        max_daily_trades=200,
        max_exchanges=5,
        ai_features_enabled=True,
        backtesting_enabled=True,
        advanced_analytics=True,
        priority_support=True,
        monthly_price_usd=Decimal("50.00")  # Premium tier for power users
    ),
}


class ANVELSubscriptionManager:
    """
    Manages user subscriptions, tier limits, and crypto payment tracking.
    Thread-safe and idempotent for distributed deployment.
    """

    def __init__(
        self,
        db_config: Dict,
        redis_config: Optional[Dict] = None,
    ):
        """
        Initialize subscription manager with database and cache.
        
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
                log.info("Redis cache connected successfully")
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
        Ensure subscription tables exist.
        Idempotent - safe to call multiple times.
        Note: Requires users table to exist first.
        """
        with self._get_db_connection() as conn:
            with conn.cursor() as cur:
                # Verify users table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'users'
                    )
                """)
                users_table_exists = cur.fetchone()[0]

                if not users_table_exists:
                    raise RuntimeError(
                        "Users table must exist before creating subscription tables. "
                        "Run anvel_database_schema.sql first."
                    )

                # Subscription plans table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS subscription_plans (
                        id SERIAL PRIMARY KEY,
                        tier VARCHAR(20) UNIQUE NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        monthly_price_usd DECIMAL(10, 2) NOT NULL,
                        limits JSONB NOT NULL,
                        is_active BOOLEAN DEFAULT true,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # User subscriptions table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS user_subscriptions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        tier VARCHAR(20) NOT NULL,
                        status VARCHAR(20) NOT NULL,
                        starts_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        auto_renew BOOLEAN DEFAULT true,
                        payment_method VARCHAR(50),
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id)
                    )
                """)

                # Create index for efficient lookups
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user_tier 
                    ON user_subscriptions(user_id, tier)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_subscriptions_expires 
                    ON user_subscriptions(expires_at) 
                    WHERE status = 'active'
                """)

                # Crypto payment tracking
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS crypto_payments (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        subscription_id UUID REFERENCES user_subscriptions(id),
                        payment_address VARCHAR(100) NOT NULL,
                        crypto_currency VARCHAR(10) NOT NULL,
                        amount_crypto DECIMAL(18, 8) NOT NULL,
                        amount_usd DECIMAL(10, 2) NOT NULL,
                        exchange_rate DECIMAL(18, 8) NOT NULL,
                        tx_hash VARCHAR(100),
                        status VARCHAR(20) NOT NULL,
                        confirmations INTEGER DEFAULT 0,
                        required_confirmations INTEGER DEFAULT 3,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        confirmed_at TIMESTAMP WITH TIME ZONE,
                        expires_at TIMESTAMP WITH TIME ZONE NOT NULL
                    )
                """)

                # Index for payment lookups
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_crypto_payments_address 
                    ON crypto_payments(payment_address)
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_crypto_payments_tx_hash 
                    ON crypto_payments(tx_hash) 
                    WHERE tx_hash IS NOT NULL
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_crypto_payments_status 
                    ON crypto_payments(status, expires_at)
                """)

                # API usage tracking for rate limiting
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS api_usage (
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                        endpoint VARCHAR(100) NOT NULL,
                        request_count INTEGER DEFAULT 1,
                        PRIMARY KEY (user_id, timestamp, endpoint)
                    )
                """)

                # Convert api_usage to hypertable if TimescaleDB available
                try:
                    cur.execute("""
                        SELECT create_hypertable('api_usage', 'timestamp', 
                                                if_not_exists => TRUE)
                    """)
                    log.info("TimescaleDB hypertable created for api_usage")
                except Exception:
                    log.info("TimescaleDB not available, using regular table")

                conn.commit()
                log.info("Subscription schema verified successfully")

    def create_subscription(
        self,
        user_id: str,
        tier: SubscriptionTier,
        duration_months: int = 1,
    ) -> Dict:
        """
        Create or upgrade user subscription.
        Idempotent - multiple calls with same parameters are safe.
        
        Args:
            user_id: UUID of the user
            tier: Subscription tier
            duration_months: Subscription duration in months
            
        Returns:
            Subscription details including payment requirements
        """
        if tier not in TIER_LIMITS:
            raise ValueError(f"Invalid tier: {tier}")

        tier_config = TIER_LIMITS[tier]
        now = datetime.utcnow()
        expires_at = now + timedelta(days=30 * duration_months)

        with self._get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Check existing subscription
                cur.execute("""
                    SELECT id, tier, expires_at 
                    FROM user_subscriptions 
                    WHERE user_id = %s
                """, (user_id,))
                existing = cur.fetchone()

                if existing:
                    # Update existing subscription
                    cur.execute("""
                        UPDATE user_subscriptions 
                        SET tier = %s, 
                            status = %s,
                            expires_at = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = %s
                        RETURNING id, tier, status, starts_at, expires_at
                    """, (tier.value, "active", expires_at, user_id))
                else:
                    # Create new subscription
                    cur.execute("""
                        INSERT INTO user_subscriptions 
                        (user_id, tier, status, starts_at, expires_at)
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id, tier, status, starts_at, expires_at
                    """, (user_id, tier.value, "active", now, expires_at))

                subscription = cur.fetchone()
                conn.commit()

                # Invalidate cache
                if self.redis_client:
                    self.redis_client.delete(f"subscription:{user_id}")

                return {
                    "subscription_id": subscription["id"],
                    "user_id": user_id,
                    "tier": subscription["tier"],
                    "status": subscription["status"],
                    "starts_at": subscription["starts_at"].isoformat(),
                    "expires_at": subscription["expires_at"].isoformat(),
                    "limits": tier_config.to_dict(),
                }

    def get_user_subscription(self, user_id: str) -> Optional[Dict]:
        """
        Get current subscription for user with caching.
        
        Args:
            user_id: UUID of the user
            
        Returns:
            Subscription details or None if no active subscription
        """
        # Check cache first
        cache_key = f"subscription:{user_id}"
        if self.redis_client:
            cached = self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)

        with self._get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, user_id, tier, status, starts_at, expires_at, 
                           auto_renew, payment_method
                    FROM user_subscriptions
                    WHERE user_id = %s
                """, (user_id,))

                subscription = cur.fetchone()

                if not subscription:
                    return None

                # Check expiration
                now = datetime.utcnow()
                if subscription["expires_at"] < now:
                    # Expired - update status
                    cur.execute("""
                        UPDATE user_subscriptions 
                        SET status = 'expired'
                        WHERE user_id = %s
                    """, (user_id,))
                    conn.commit()
                    subscription["status"] = "expired"

                tier = SubscriptionTier(subscription["tier"])
                limits = TIER_LIMITS[tier]

                result = {
                    "subscription_id": subscription["id"],
                    "user_id": subscription["user_id"],
                    "tier": subscription["tier"],
                    "status": subscription["status"],
                    "starts_at": subscription["starts_at"].isoformat(),
                    "expires_at": subscription["expires_at"].isoformat(),
                    "auto_renew": subscription["auto_renew"],
                    "payment_method": subscription["payment_method"],
                    "limits": limits.to_dict(),
                }

                # Cache for 5 minutes
                if self.redis_client:
                    self.redis_client.setex(
                        cache_key,
                        300,
                        json.dumps(result, default=str)
                    )

                return result

    def create_crypto_payment(
        self,
        user_id: str,
        subscription_id: str,
        crypto_currency: str,
        amount_usd: Decimal,
        payment_address: str,
    ) -> Dict:
        """
        Create crypto payment record for subscription.
        
        Args:
            user_id: UUID of the user
            subscription_id: UUID of subscription
            crypto_currency: BTC, ETH, USDT, etc.
            amount_usd: Payment amount in USD
            payment_address: Crypto address for payment
            
        Returns:
            Payment tracking details
            
        Raises:
            NotImplementedError: If price feed integration not configured
        """
        # Use CCXT or requests to fetch live price from public APIs
        try:
            import requests as _req
            # CoinGecko free API — no key required
            _cg_ids = {
                "BTC": "bitcoin", "ETH": "ethereum", "USDT": "tether",
                "USDC": "usd-coin", "XMR": "monero", "SOL": "solana",
                "BNB": "binancecoin", "DOGE": "dogecoin", "ADA": "cardano",
                "XRP": "ripple", "MATIC": "matic-network", "AVAX": "avalanche-2",
            }
            cg_id = _cg_ids.get(crypto_currency.upper())
            if not cg_id:
                # Fallback: use CCXT if available
                try:
                    import ccxt
                    exchange = ccxt.binance({"enableRateLimit": True})
                    ticker = exchange.fetch_ticker(f"{crypto_currency.upper()}/USDT")
                    price_usd = Decimal(str(ticker["last"]))
                except Exception:
                    raise ValueError(
                        f"Unsupported crypto for payment: {crypto_currency}. "
                        f"Supported: {list(_cg_ids.keys())}"
                    )
            else:
                resp = _req.get(
                    f"https://api.coingecko.com/api/v3/simple/price"
                    f"?ids={cg_id}&vs_currencies=usd",
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                price_usd = Decimal(str(data[cg_id]["usd"]))

            crypto_amount = amount_usd / price_usd

            result = {
                "user_id": user_id,
                "subscription_id": subscription_id,
                "crypto_currency": crypto_currency.upper(),
                "amount_usd": float(amount_usd),
                "crypto_amount": float(crypto_amount),
                "exchange_rate": float(price_usd),
                "payment_address": payment_address,
                "status": "pending",
                "created_at": int(time.time()),
            }

            logger.info(
                "Crypto payment created: user=%s, %s %.8f @ $%.2f",
                user_id, crypto_currency, float(crypto_amount), float(price_usd),
            )
            return result

        except ImportError:
            logger.error("requests library required for crypto payments")
            raise ValueError(
                "requests library not installed. Run: pip install requests"
            )

    def check_rate_limit(self, user_id: str, endpoint: str = "default") -> bool:
        """
        Check if user has exceeded rate limits for their tier.
        Uses sliding window algorithm with Redis for accuracy.
        
        Args:
            user_id: UUID of the user
            endpoint: API endpoint identifier
            
        Returns:
            True if within limits, False if exceeded
            
        Raises:
            ValueError: If user has no active subscription
        """
        subscription = self.get_user_subscription(user_id)
        if not subscription or subscription["status"] != "active":
            available_tiers = ", ".join(
                f"{tier.value.capitalize()} (${TIER_LIMITS[tier].monthly_price_usd}/month)"
                for tier in SubscriptionTier
            )
            raise ValueError(
                f"Active subscription required. User {user_id} has "
                f"{'no' if not subscription else subscription['status']} subscription. "
                f"Available tiers: {available_tiers}."
            )

        tier = SubscriptionTier(subscription["tier"])
        limits = TIER_LIMITS[tier]
        max_calls = limits.max_api_calls_per_minute

        if self.redis_client:
            # Sliding window with Redis
            key = f"ratelimit:{user_id}:{endpoint}"
            now = int(time.time())
            window_start = now - 60

            pipe = self.redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)  # Remove old entries
            pipe.zadd(key, {str(now): now})  # Add current request
            pipe.zcard(key)  # Count requests in window
            pipe.expire(key, 60)  # Set expiry
            _, _, count, _ = pipe.execute()

            return count <= max_calls
        else:
            # Fallback to database (less accurate)
            with self._get_db_connection() as conn:
                with conn.cursor() as cur:
                    one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
                    cur.execute("""
                        SELECT COALESCE(SUM(request_count), 0) as total
                        FROM api_usage
                        WHERE user_id = %s 
                        AND endpoint = %s 
                        AND timestamp > %s
                    """, (user_id, endpoint, one_minute_ago))

                    result = cur.fetchone()
                    total = result[0] if result else 0

                    if total < max_calls:
                        # Log this request
                        cur.execute("""
                            INSERT INTO api_usage (user_id, timestamp, endpoint)
                            VALUES (%s, CURRENT_TIMESTAMP, %s)
                            ON CONFLICT (user_id, timestamp, endpoint)
                            DO UPDATE SET request_count = api_usage.request_count + 1
                        """, (user_id, endpoint))
                        conn.commit()
                        return True

                    return False

    def validate_user_limits(self, user_id: str) -> TierLimits:
        """
        Get tier limits for user for validation.
        
        Args:
            user_id: UUID of the user
            
        Returns:
            TierLimits object with resource constraints
        """
        subscription = self.get_user_subscription(user_id)
        if not subscription or subscription["status"] != "active":
            raise ValueError(
                "No active subscription found. "
                "A valid subscription is required to use VEL trading system. "
                "Please subscribe to either Basic ($10/month) or Premium ($20/month) tier."
            )

        tier = SubscriptionTier(subscription["tier"])
        return TIER_LIMITS[tier]

    def cleanup_expired_payments(self) -> int:
        """
        Background task to clean up expired pending payments.
        Should be run periodically (e.g., hourly).
        
        Returns:
            Number of payments marked as expired
        """
        with self._get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE crypto_payments
                    SET status = %s
                    WHERE status = %s 
                    AND expires_at < CURRENT_TIMESTAMP
                    RETURNING id
                """, (PaymentStatus.EXPIRED.value, PaymentStatus.PENDING.value))

                expired_count = cur.rowcount
                conn.commit()

                log.info(f"Marked {expired_count} payments as expired")
                return expired_count
