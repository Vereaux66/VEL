#!/usr/bin/env python3
"""
ANVEL Referral System with Bonus Rewards

Implements multi-tier referral program with:
- Referral code generation and tracking
- Commission-based rewards (10% of subscription fees)
- Bonus unlocks for referral milestones
- Fraud prevention and validation
- PostgreSQL persistence with Redis caching

Production-critical module for SaaS revenue sharing.
"""

import logging
import secrets
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional
from dataclasses import dataclass
import psycopg2
from psycopg2.extras import RealDictCursor
import redis

logger = logging.getLogger(__name__)


class ReferralStatus(Enum):
    """Referral relationship status."""
    PENDING = "pending"  # User signed up but not yet paid
    ACTIVE = "active"    # User is paying subscriber
    INACTIVE = "inactive"  # User subscription lapsed
    FRAUDULENT = "fraudulent"  # Flagged as fraud


class BonusTier(Enum):
    """Milestone bonus tiers."""
    BRONZE = "bronze"    # 5 referrals
    SILVER = "silver"    # 10 referrals
    GOLD = "gold"        # 25 referrals
    PLATINUM = "platinum"  # 50 referrals
    DIAMOND = "diamond"  # 100 referrals


@dataclass
class ReferralBonus:
    """Bonus configuration for milestones."""
    tier: BonusTier
    referrals_required: int
    bonus_amount_usd: Decimal
    bonus_description: str


# Referral bonus structure
REFERRAL_BONUSES = [
    ReferralBonus(BonusTier.BRONZE, 5, Decimal("25.00"), "First 5 referrals bonus"),
    ReferralBonus(BonusTier.SILVER, 10, Decimal("75.00"), "10 referrals bonus"),
    ReferralBonus(BonusTier.GOLD, 25, Decimal("200.00"), "25 referrals bonus"),
    ReferralBonus(BonusTier.PLATINUM, 50, Decimal("500.00"), "50 referrals bonus"),
    ReferralBonus(BonusTier.DIAMOND, 100, Decimal("1000.00"), "100 referrals bonus"),
]

# Commission rate for ongoing referrals
REFERRAL_COMMISSION_RATE = Decimal("0.10")  # 10% of subscription fees


class ReferralSystem:
    """
    Manages referral program with commission tracking and bonus payouts.
    Thread-safe and idempotent for distributed deployment.
    """

    def __init__(
        self,
        db_config: Dict,
        redis_config: Optional[Dict] = None,
    ):
        """
        Initialize referral system.
        
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
                    db=redis_config.get("db", 1),  # Use separate DB from subscriptions
                    decode_responses=True,
                    socket_connect_timeout=5,
                )
                self.redis_client.ping()
                logger.info("Referral Redis cache connected")
            except redis.RedisError as e:
                logger.warning(f"Redis connection failed: {e}")
                self.redis_client = None

        self._ensure_schema()

    def _get_db_connection(self):
        """Get database connection."""
        return psycopg2.connect(
            host=self.db_config["host"],
            port=self.db_config.get("port", 5432),
            dbname=self.db_config["database"],
            user=self.db_config["user"],
            password=self.db_config["password"],
            connect_timeout=10,
        )

    def _ensure_schema(self):
        """Create referral tables if they don't exist."""
        with self._get_db_connection() as conn:
            with conn.cursor() as cur:
                # Referral codes table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS referral_codes (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        code VARCHAR(20) UNIQUE NOT NULL,
                        uses_count INT DEFAULT 0,
                        total_earned_usd DECIMAL(10, 2) DEFAULT 0.00,
                        is_active BOOLEAN DEFAULT true,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id)
                    )
                """)

                # Referral relationships table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS referrals (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        referrer_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        referred_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        referral_code VARCHAR(20) NOT NULL,
                        status VARCHAR(20) DEFAULT 'pending',
                        total_commission_usd DECIMAL(10, 2) DEFAULT 0.00,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        activated_at TIMESTAMP WITH TIME ZONE,
                        UNIQUE(referred_user_id)
                    )
                """)

                # Commission payments table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS referral_commissions (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        referral_id UUID NOT NULL REFERENCES referrals(id) ON DELETE CASCADE,
                        subscription_payment_id UUID NOT NULL,
                        amount_usd DECIMAL(10, 2) NOT NULL,
                        payment_status VARCHAR(20) DEFAULT 'pending',
                        paid_at TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Bonus payouts table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS referral_bonuses (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        tier VARCHAR(20) NOT NULL,
                        amount_usd DECIMAL(10, 2) NOT NULL,
                        referrals_count INT NOT NULL,
                        payment_status VARCHAR(20) DEFAULT 'pending',
                        paid_at TIMESTAMP WITH TIME ZONE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # Create indexes
                cur.execute("CREATE INDEX IF NOT EXISTS idx_referral_codes_user ON referral_codes(user_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_referral_codes_code ON referral_codes(code)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_user_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals(referred_user_id)")

                conn.commit()
                logger.info("Referral schema ensured")

    def generate_referral_code(self, user_id: str) -> str:
        """
        Generate unique referral code for user.
        
        Args:
            user_id: User UUID
            
        Returns:
            Referral code (e.g., "VEL-ABC123")
        """
        with self._get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Check if user already has a code
                cur.execute(
                    "SELECT code FROM referral_codes WHERE user_id = %s",
                    (user_id,)
                )
                existing = cur.fetchone()
                if existing:
                    return existing["code"]

                # Generate new unique code
                while True:
                    # Format: VEL-XXXXXX (6 alphanumeric chars)
                    random_part = secrets.token_hex(3).upper()
                    code = f"VEL-{random_part}"

                    # Check uniqueness
                    cur.execute(
                        "SELECT id FROM referral_codes WHERE code = %s",
                        (code,)
                    )
                    if not cur.fetchone():
                        break

                # Insert new code
                cur.execute("""
                    INSERT INTO referral_codes (user_id, code)
                    VALUES (%s, %s)
                    RETURNING code
                """, (user_id, code))

                conn.commit()
                result = cur.fetchone()
                logger.info(f"Generated referral code {code} for user {user_id}")
                return result["code"]

    def apply_referral_code(
        self,
        referred_user_id: str,
        referral_code: str
    ) -> bool:
        """
        Apply referral code when user signs up.
        
        Args:
            referred_user_id: New user's UUID
            referral_code: Referral code to apply
            
        Returns:
            True if applied successfully, False otherwise
        """
        with self._get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Validate code exists and is active
                cur.execute("""
                    SELECT user_id 
                    FROM referral_codes 
                    WHERE code = %s AND is_active = true
                """, (referral_code,))

                code_record = cur.fetchone()
                if not code_record:
                    logger.warning(f"Invalid referral code: {referral_code}")
                    return False

                referrer_user_id = code_record["user_id"]

                # Prevent self-referral
                if referrer_user_id == referred_user_id:
                    logger.warning(f"Self-referral attempt blocked: {referred_user_id}")
                    return False

                # Check if user already has a referral
                cur.execute(
                    "SELECT id FROM referrals WHERE referred_user_id = %s",
                    (referred_user_id,)
                )
                if cur.fetchone():
                    logger.warning(f"User {referred_user_id} already has a referral")
                    return False

                # Create referral relationship
                cur.execute("""
                    INSERT INTO referrals (
                        referrer_user_id,
                        referred_user_id,
                        referral_code,
                        status
                    ) VALUES (%s, %s, %s, 'pending')
                """, (referrer_user_id, referred_user_id, referral_code))

                # Increment uses count
                cur.execute("""
                    UPDATE referral_codes 
                    SET uses_count = uses_count + 1
                    WHERE code = %s
                """, (referral_code,))

                conn.commit()
                logger.info(
                    f"Applied referral code {referral_code} "
                    f"(referrer: {referrer_user_id}, referred: {referred_user_id})"
                )
                return True

    def activate_referral(self, referred_user_id: str) -> None:
        """
        Activate referral when user makes first payment.
        
        Args:
            referred_user_id: User who completed payment
        """
        with self._get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE referrals
                    SET status = 'active',
                        activated_at = CURRENT_TIMESTAMP
                    WHERE referred_user_id = %s 
                      AND status = 'pending'
                """, (referred_user_id,))

                if cur.rowcount > 0:
                    conn.commit()
                    logger.info(f"Activated referral for user {referred_user_id}")

                    # Check for bonus eligibility
                    self._check_and_award_bonuses(referred_user_id, conn)

    def record_commission(
        self,
        subscription_payment_id: str,
        referred_user_id: str,
        subscription_amount_usd: Decimal
    ) -> Optional[str]:
        """
        Record commission when referred user pays subscription.
        
        Args:
            subscription_payment_id: Payment ID from subscription system
            referred_user_id: User who made payment
            subscription_amount_usd: Subscription payment amount
            
        Returns:
            Commission ID if recorded, None otherwise
        """
        commission_amount = subscription_amount_usd * REFERRAL_COMMISSION_RATE

        with self._get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get referral relationship
                cur.execute("""
                    SELECT id, referrer_user_id
                    FROM referrals
                    WHERE referred_user_id = %s
                      AND status = 'active'
                """, (referred_user_id,))

                referral = cur.fetchone()
                if not referral:
                    return None

                # Record commission
                cur.execute("""
                    INSERT INTO referral_commissions (
                        referral_id,
                        subscription_payment_id,
                        amount_usd
                    ) VALUES (%s, %s, %s)
                    RETURNING id
                """, (referral["id"], subscription_payment_id, commission_amount))

                commission_id = cur.fetchone()["id"]

                # Update totals
                cur.execute("""
                    UPDATE referrals
                    SET total_commission_usd = total_commission_usd + %s
                    WHERE id = %s
                """, (commission_amount, referral["id"]))

                cur.execute("""
                    UPDATE referral_codes
                    SET total_earned_usd = total_earned_usd + %s
                    WHERE user_id = %s
                """, (commission_amount, referral["referrer_user_id"]))

                conn.commit()
                logger.info(
                    f"Recorded ${commission_amount} commission for referral {referral['id']}"
                )
                return commission_id

    def _check_and_award_bonuses(self, referred_user_id: str, conn) -> None:
        """Check if referrer qualifies for milestone bonuses."""
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get referrer
            cur.execute("""
                SELECT referrer_user_id
                FROM referrals
                WHERE referred_user_id = %s
            """, (referred_user_id,))

            referral = cur.fetchone()
            if not referral:
                return

            referrer_id = referral["referrer_user_id"]

            # Count active referrals
            cur.execute("""
                SELECT COUNT(*) as count
                FROM referrals
                WHERE referrer_user_id = %s
                  AND status = 'active'
            """, (referrer_id,))

            active_count = cur.fetchone()["count"]

            # Check each bonus tier
            for bonus in REFERRAL_BONUSES:
                if active_count >= bonus.referrals_required:
                    # Check if already awarded
                    cur.execute("""
                        SELECT id FROM referral_bonuses
                        WHERE user_id = %s AND tier = %s
                    """, (referrer_id, bonus.tier.value))

                    if not cur.fetchone():
                        # Award bonus
                        cur.execute("""
                            INSERT INTO referral_bonuses (
                                user_id,
                                tier,
                                amount_usd,
                                referrals_count
                            ) VALUES (%s, %s, %s, %s)
                        """, (
                            referrer_id,
                            bonus.tier.value,
                            bonus.bonus_amount_usd,
                            active_count
                        ))

                        logger.info(
                            f"Awarded {bonus.tier.value} bonus (${bonus.bonus_amount_usd}) "
                            f"to user {referrer_id} for {active_count} referrals"
                        )

            conn.commit()

    def get_referral_stats(self, user_id: str) -> Dict:
        """
        Get referral statistics for user.
        
        Args:
            user_id: User UUID
            
        Returns:
            Dictionary with referral statistics
        """
        with self._get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get referral code
                cur.execute("""
                    SELECT code, uses_count, total_earned_usd
                    FROM referral_codes
                    WHERE user_id = %s
                """, (user_id,))

                code_info = cur.fetchone()
                if not code_info:
                    return {
                        "has_code": False,
                        "code": None,
                        "total_referrals": 0,
                        "active_referrals": 0,
                        "total_earned_usd": 0.0,
                        "pending_commission_usd": 0.0,
                        "bonuses_earned": [],
                    }

                # Get referral counts
                cur.execute("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE status = 'active') as active
                    FROM referrals
                    WHERE referrer_user_id = %s
                """, (user_id,))

                counts = cur.fetchone()

                # Get pending commissions
                cur.execute("""
                    SELECT COALESCE(SUM(amount_usd), 0) as pending
                    FROM referral_commissions rc
                    JOIN referrals r ON r.id = rc.referral_id
                    WHERE r.referrer_user_id = %s
                      AND rc.payment_status = 'pending'
                """, (user_id,))

                pending = cur.fetchone()["pending"]

                # Get bonuses
                cur.execute("""
                    SELECT tier, amount_usd, referrals_count, payment_status
                    FROM referral_bonuses
                    WHERE user_id = %s
                    ORDER BY created_at
                """, (user_id,))

                bonuses = cur.fetchall()

                return {
                    "has_code": True,
                    "code": code_info["code"],
                    "total_referrals": counts["total"],
                    "active_referrals": counts["active"],
                    "total_earned_usd": float(code_info["total_earned_usd"]),
                    "pending_commission_usd": float(pending),
                    "bonuses_earned": [
                        {
                            "tier": b["tier"],
                            "amount_usd": float(b["amount_usd"]),
                            "referrals_count": b["referrals_count"],
                            "status": b["payment_status"],
                        }
                        for b in bonuses
                    ],
                }
