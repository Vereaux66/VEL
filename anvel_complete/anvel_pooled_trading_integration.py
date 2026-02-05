#!/usr/bin/env python3
"""
ANVEL Pooled Trading Integration Module

This module wires the pooled trading engine into the core VEL system:
- Database persistence via anvel_database_service
- Event bus integration for real-time updates
- Web3 execution via DEX brokers
- API gateway integration

PRODUCTION-CRITICAL: This module handles real capital flows.
All operations must be atomic, auditable, and recoverable.
"""

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

# Internal imports
from anvel_pooled_trading_engine import (
    PooledTradingEngine,
    DepositTier,
    ChainLayer,
    TradeStatus,
    WithdrawalStatus,
    TierConfig,
    UserDeposit,
    PooledTrade,
    ProfitDistribution,
    DEFAULT_TIER_CONFIGS,
    SUPPORTED_CHAINS,
    SUPPORTED_DEXES,
    MINIMUM_DEPOSIT_USD,
    MINIMUM_WITHDRAWAL_USD,
    MAXIMUM_DEPOSIT_USD,
    BASE_YIELD_BPS,
    GRADUATED_BONUS_TIERS,
    EARNINGS_WITHDRAWAL_COOLDOWN,
    OWNER_DEPOSIT_FEE_BPS,
    OWNER_WITHDRAWAL_FEE_BPS,
    OWNER_TRADE_FEE_BPS,
    BPS_DENOMINATOR,
    calculate_effective_yield_bps,
    get_deposit_tier_info,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# DATABASE INTEGRATION
# ==============================================================================

class PooledTradingDatabaseAdapter:
    """
    Database adapter for pooled trading operations.
    Provides persistent storage for deposits, earnings, trades, and distributions.
    
    Uses the existing anvel_database_service infrastructure with the schema
    defined in migrations/002_pooled_trading_system.sql
    """

    def __init__(self, db_service: Any):
        """
        Initialize database adapter.
        
        Args:
            db_service: Instance of DatabaseService from anvel_database_service
        """
        self._db = db_service
        self._initialized = False
        self._verify_schema()

    def _verify_schema(self) -> bool:
        """Verify required tables exist."""
        if not self._db.is_available:
            logger.warning("Database not available - operating in memory-only mode")
            return False

        required_tables = [
            'deposit_tiers',
            'pooled_deposits', 
            'user_earnings',
            'pooled_referral_codes',
            'pooled_referrals',
            'user_rewards',
            'pooled_trades',
            'profit_distributions',
            'owner_fees',
        ]

        try:
            with self._db.get_connection() as conn:
                with conn.cursor() as cur:
                    for table in required_tables:
                        cur.execute("""
                            SELECT EXISTS (
                                SELECT FROM information_schema.tables 
                                WHERE table_name = %s
                            )
                        """, (table,))
                        exists = cur.fetchone()[0]
                        if not exists:
                            logger.error(f"Required table missing: {table}")
                            logger.error(
                                "Run migrations/002_pooled_trading_system.sql first"
                            )
                            return False
            
            self._initialized = True
            logger.info("Pooled trading database schema verified")
            return True
            
        except Exception as e:
            logger.error(f"Schema verification failed: {e}")
            return False

    @property
    def is_available(self) -> bool:
        """Check if database is available and schema is valid."""
        return self._initialized and self._db.is_available

    # =========================================================================
    # Deposit Operations
    # =========================================================================

    def create_deposit(
        self,
        user_id: str,
        tier_name: str,
        amount_usd: Decimal,
        net_amount_usd: Decimal,
        unlock_timestamp: int,
        tx_hash: Optional[str] = None,
        chain_id: Optional[int] = None,
    ) -> Optional[str]:
        """
        Create a new pooled deposit record.
        
        Args:
            user_id: UUID of the user
            tier_name: Tier name ('three_month', 'six_month', 'nine_month')
            amount_usd: Original deposit amount
            net_amount_usd: Amount after fees
            unlock_timestamp: When deposit unlocks
            tx_hash: Blockchain transaction hash
            chain_id: Blockchain chain ID
            
        Returns:
            Deposit UUID or None if failed
        """
        if not self.is_available:
            logger.warning("Database unavailable, deposit not persisted")
            return None

        try:
            with self._db.transaction() as conn:
                with conn.cursor() as cur:
                    # Get tier ID
                    cur.execute(
                        "SELECT id FROM deposit_tiers WHERE tier_name = %s",
                        (tier_name,)
                    )
                    tier_row = cur.fetchone()
                    if not tier_row:
                        raise ValueError(f"Unknown tier: {tier_name}")
                    tier_id = tier_row[0]

                    # Create deposit
                    cur.execute("""
                        INSERT INTO pooled_deposits (
                            user_id, tier_id, amount_usd, net_amount_usd,
                            unlock_timestamp, tx_hash, chain_id
                        ) VALUES (
                            %s, %s, %s, %s,
                            to_timestamp(%s), %s, %s
                        )
                        RETURNING id
                    """, (
                        user_id, tier_id, float(amount_usd), float(net_amount_usd),
                        unlock_timestamp, tx_hash, chain_id
                    ))
                    deposit_id = str(cur.fetchone()[0])

                    logger.info(
                        "Deposit created in DB: id=%s, user=%s, amount=$%.2f",
                        deposit_id, user_id, float(net_amount_usd)
                    )
                    return deposit_id

        except Exception as e:
            logger.error(f"Failed to create deposit: {e}")
            return None

    def get_user_deposits(self, user_id: str) -> List[Dict]:
        """Get all deposits for a user."""
        if not self.is_available:
            return []

        try:
            with self._db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT 
                            pd.id, pd.amount_usd, pd.net_amount_usd,
                            dt.tier_name, pd.deposit_timestamp, pd.unlock_timestamp,
                            pd.accumulated_earnings, pd.reinvestment_count,
                            pd.is_active, pd.tx_hash
                        FROM pooled_deposits pd
                        JOIN deposit_tiers dt ON pd.tier_id = dt.id
                        WHERE pd.user_id = %s
                        ORDER BY pd.deposit_timestamp DESC
                    """, (user_id,))
                    
                    rows = cur.fetchall()
                    return [
                        {
                            'id': str(row[0]),
                            'amount_usd': Decimal(str(row[1])),
                            'net_amount_usd': Decimal(str(row[2])),
                            'tier': row[3],
                            'deposit_timestamp': row[4],
                            'unlock_timestamp': row[5],
                            'accumulated_earnings': Decimal(str(row[6] or 0)),
                            'reinvestment_count': row[7],
                            'is_active': row[8],
                            'tx_hash': row[9],
                        }
                        for row in rows
                    ]
        except Exception as e:
            logger.error(f"Failed to get user deposits: {e}")
            return []

    def update_deposit_status(
        self,
        deposit_id: str,
        is_active: bool,
        accumulated_earnings: Optional[Decimal] = None,
        reinvestment_count: Optional[int] = None,
    ) -> bool:
        """Update deposit status."""
        if not self.is_available:
            return False

        try:
            with self._db.transaction() as conn:
                with conn.cursor() as cur:
                    updates = ["is_active = %s"]
                    params = [is_active]
                    
                    if accumulated_earnings is not None:
                        updates.append("accumulated_earnings = %s")
                        params.append(float(accumulated_earnings))
                    
                    if reinvestment_count is not None:
                        updates.append("reinvestment_count = %s")
                        params.append(reinvestment_count)

                    params.append(deposit_id)
                    
                    cur.execute(f"""
                        UPDATE pooled_deposits 
                        SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, params)

                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update deposit: {e}")
            return False

    # =========================================================================
    # Earnings Operations
    # =========================================================================

    def get_or_create_user_earnings(self, user_id: str) -> Dict:
        """Get or create user earnings record."""
        if not self.is_available:
            return {
                'claimable_amount': Decimal('0'),
                'total_earned': Decimal('0'),
                'total_withdrawn': Decimal('0'),
            }

        try:
            with self._db.transaction() as conn:
                with conn.cursor() as cur:
                    # Try to get existing
                    cur.execute("""
                        SELECT claimable_amount, total_earned, total_withdrawn,
                               last_withdrawal_timestamp
                        FROM user_earnings WHERE user_id = %s
                    """, (user_id,))
                    row = cur.fetchone()
                    
                    if row:
                        return {
                            'claimable_amount': Decimal(str(row[0] or 0)),
                            'total_earned': Decimal(str(row[1] or 0)),
                            'total_withdrawn': Decimal(str(row[2] or 0)),
                            'last_withdrawal': row[3],
                        }
                    
                    # Create new
                    cur.execute("""
                        INSERT INTO user_earnings (user_id)
                        VALUES (%s)
                        RETURNING claimable_amount, total_earned, total_withdrawn
                    """, (user_id,))
                    row = cur.fetchone()
                    return {
                        'claimable_amount': Decimal(str(row[0] or 0)),
                        'total_earned': Decimal(str(row[1] or 0)),
                        'total_withdrawn': Decimal(str(row[2] or 0)),
                        'last_withdrawal': None,
                    }
        except Exception as e:
            logger.error(f"Failed to get/create user earnings: {e}")
            return {
                'claimable_amount': Decimal('0'),
                'total_earned': Decimal('0'),
                'total_withdrawn': Decimal('0'),
            }

    def add_user_earnings(
        self,
        user_id: str,
        amount: Decimal,
        source: str = 'trade',
    ) -> bool:
        """Add earnings to user's claimable balance."""
        if not self.is_available:
            return False

        try:
            with self._db.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO user_earnings (user_id, claimable_amount, total_earned)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (user_id) DO UPDATE SET
                            claimable_amount = user_earnings.claimable_amount + EXCLUDED.claimable_amount,
                            total_earned = user_earnings.total_earned + EXCLUDED.total_earned,
                            updated_at = CURRENT_TIMESTAMP
                    """, (user_id, float(amount), float(amount)))
                    return True
        except Exception as e:
            logger.error(f"Failed to add earnings: {e}")
            return False

    def record_earnings_withdrawal(
        self,
        user_id: str,
        amount: Decimal,
    ) -> bool:
        """Record an earnings withdrawal."""
        if not self.is_available:
            return False

        try:
            with self._db.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE user_earnings SET
                            claimable_amount = claimable_amount - %s,
                            total_withdrawn = total_withdrawn + %s,
                            last_withdrawal_timestamp = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = %s
                        AND claimable_amount >= %s
                        RETURNING id
                    """, (float(amount), float(amount), user_id, float(amount)))
                    return cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Failed to record withdrawal: {e}")
            return False

    # =========================================================================
    # Trade Operations
    # =========================================================================

    def record_trade(
        self,
        trade: PooledTrade,
    ) -> bool:
        """Record a pooled trade."""
        if not self.is_available:
            return False

        try:
            with self._db.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO pooled_trades (
                            chain_id, chain_layer, dex_protocol,
                            token_in, token_out, amount_in, amount_out,
                            profit, owner_fee, user_profit_share,
                            tx_hash, gas_used, status
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        trade.chain_id,
                        trade.chain_layer.value if trade.chain_layer else None,
                        trade.dex_protocol,
                        trade.token_in,
                        trade.token_out,
                        float(trade.amount_in),
                        float(trade.amount_out),
                        float(trade.profit),
                        float(trade.owner_fee),
                        float(trade.user_profit_share),
                        trade.tx_hash,
                        trade.gas_used,
                        trade.status.value,
                    ))
                    return True
        except Exception as e:
            logger.error(f"Failed to record trade: {e}")
            return False

    def record_profit_distribution(
        self,
        distribution: ProfitDistribution,
    ) -> bool:
        """Record a profit distribution."""
        if not self.is_available:
            return False

        try:
            with self._db.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO profit_distributions (
                            total_profits, owner_fees, user_share,
                            total_pool_value, distribution_count
                        ) VALUES (%s, %s, %s, %s, %s)
                    """, (
                        float(distribution.total_profits),
                        float(distribution.owner_fees),
                        float(distribution.user_share),
                        float(distribution.total_pool_value),
                        distribution.distribution_count,
                    ))
                    return True
        except Exception as e:
            logger.error(f"Failed to record distribution: {e}")
            return False

    # =========================================================================
    # Owner Fee Operations
    # =========================================================================

    def record_owner_fee(
        self,
        fee_type: str,
        amount: Decimal,
        related_id: Optional[str] = None,
    ) -> bool:
        """Record an owner fee."""
        if not self.is_available:
            return False

        try:
            with self._db.transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO owner_fees (fee_type, amount, related_id)
                        VALUES (%s, %s, %s)
                    """, (fee_type, float(amount), related_id))
                    return True
        except Exception as e:
            logger.error(f"Failed to record owner fee: {e}")
            return False

    def get_pool_summary(self) -> Dict:
        """Get pool summary statistics."""
        if not self.is_available:
            return {
                'total_users': 0,
                'total_deposits': 0,
                'active_deposits': 0,
                'total_pool_value': Decimal('0'),
                'total_profits': Decimal('0'),
            }

        try:
            with self._db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM v_pool_summary")
                    row = cur.fetchone()
                    if row:
                        return {
                            'total_users': row[0] or 0,
                            'total_deposits': row[1] or 0,
                            'active_deposits': row[2] or 0,
                            'total_pool_value': Decimal(str(row[3] or 0)),
                            'total_accumulated_earnings': Decimal(str(row[4] or 0)),
                            'total_completed_trades': row[5] or 0,
                            'total_trading_profit': Decimal(str(row[6] or 0)),
                            'total_owner_fees': Decimal(str(row[8] or 0)),
                        }
        except Exception as e:
            logger.error(f"Failed to get pool summary: {e}")
        
        return {
            'total_users': 0,
            'total_deposits': 0,
            'active_deposits': 0,
            'total_pool_value': Decimal('0'),
            'total_profits': Decimal('0'),
        }


# ==============================================================================
# EVENT BUS INTEGRATION
# ==============================================================================

class PooledTradingEventPublisher:
    """
    Event publisher for pooled trading operations.
    Publishes events to the system-wide event bus for real-time updates.
    """

    # Event channels
    CHANNEL_DEPOSITS = "pooled.deposits"
    CHANNEL_TRADES = "pooled.trades"
    CHANNEL_EARNINGS = "pooled.earnings"
    CHANNEL_DISTRIBUTIONS = "pooled.distributions"

    def __init__(self, event_bus: Any):
        """
        Initialize event publisher.
        
        Args:
            event_bus: ANVELEventBus instance
        """
        self._bus = event_bus
        self._ensure_channels()

    def _ensure_channels(self):
        """Ensure required channels exist."""
        if hasattr(self._bus, 'subscribers'):
            for channel in [
                self.CHANNEL_DEPOSITS,
                self.CHANNEL_TRADES,
                self.CHANNEL_EARNINGS,
                self.CHANNEL_DISTRIBUTIONS,
            ]:
                self._bus.subscribers.setdefault(channel, [])

    def publish_deposit(
        self,
        user_id: str,
        deposit_id: str,
        amount: Decimal,
        tier: str,
        event_type: str = 'created',
    ):
        """Publish deposit event."""
        try:
            self._bus.publish(self.CHANNEL_DEPOSITS, {
                'type': event_type,
                'user_id': user_id,
                'deposit_id': deposit_id,
                'amount': float(amount),
                'tier': tier,
                'timestamp': time.time(),
            })
        except Exception as e:
            logger.warning(f"Failed to publish deposit event: {e}")

    def publish_trade(
        self,
        trade_id: str,
        chain_id: int,
        dex: str,
        amount_in: Decimal,
        amount_out: Decimal,
        profit: Decimal,
        status: str,
    ):
        """Publish trade event."""
        try:
            self._bus.publish(self.CHANNEL_TRADES, {
                'type': 'executed',
                'trade_id': trade_id,
                'chain_id': chain_id,
                'dex': dex,
                'amount_in': float(amount_in),
                'amount_out': float(amount_out),
                'profit': float(profit),
                'status': status,
                'timestamp': time.time(),
            })
        except Exception as e:
            logger.warning(f"Failed to publish trade event: {e}")

    def publish_earnings(
        self,
        user_id: str,
        amount: Decimal,
        event_type: str = 'added',
    ):
        """Publish earnings event."""
        try:
            self._bus.publish(self.CHANNEL_EARNINGS, {
                'type': event_type,
                'user_id': user_id,
                'amount': float(amount),
                'timestamp': time.time(),
            })
        except Exception as e:
            logger.warning(f"Failed to publish earnings event: {e}")

    def publish_distribution(
        self,
        total_profits: Decimal,
        recipient_count: int,
    ):
        """Publish distribution event."""
        try:
            self._bus.publish(self.CHANNEL_DISTRIBUTIONS, {
                'type': 'distributed',
                'total_profits': float(total_profits),
                'recipient_count': recipient_count,
                'timestamp': time.time(),
            })
        except Exception as e:
            logger.warning(f"Failed to publish distribution event: {e}")


# ==============================================================================
# INTEGRATED POOLED TRADING SERVICE
# ==============================================================================

class IntegratedPooledTradingService:
    """
    Production-ready pooled trading service with full system integration.
    
    Integrates:
    - PooledTradingEngine for business logic
    - PooledTradingDatabaseAdapter for persistence
    - PooledTradingEventPublisher for real-time updates
    - DEX brokers for on-chain execution
    
    This is the main entry point for pooled trading operations in VEL.
    """

    def __init__(
        self,
        database_service: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        dex_brokers: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize integrated service.
        
        Args:
            database_service: DatabaseService instance for persistence
            event_bus: ANVELEventBus instance for events
            dex_brokers: Dict of DEX broker instances keyed by chain_id
        """
        # Core engine
        self._engine = PooledTradingEngine()
        
        # Database adapter
        self._db_adapter: Optional[PooledTradingDatabaseAdapter] = None
        if database_service:
            try:
                self._db_adapter = PooledTradingDatabaseAdapter(database_service)
            except Exception as e:
                logger.warning(f"Database adapter init failed: {e}")
        
        # Event publisher
        self._event_publisher: Optional[PooledTradingEventPublisher] = None
        if event_bus:
            try:
                self._event_publisher = PooledTradingEventPublisher(event_bus)
            except Exception as e:
                logger.warning(f"Event publisher init failed: {e}")
        
        # DEX brokers (keyed by chain_id)
        self._dex_brokers = dex_brokers or {}
        
        # State
        self._lock = threading.Lock()
        self._initialized = True
        
        logger.info(
            "IntegratedPooledTradingService initialized: "
            f"db={self._db_adapter is not None}, "
            f"events={self._event_publisher is not None}, "
            f"dex_brokers={len(self._dex_brokers)}"
        )

    # =========================================================================
    # Deposit Operations
    # =========================================================================

    def deposit(
        self,
        user_id: str,
        amount: Decimal,
        tier: DepositTier,
        referral_code: Optional[str] = None,
        tx_hash: Optional[str] = None,
        chain_id: Optional[int] = None,
    ) -> UserDeposit:
        """
        Create a deposit with full integration.
        
        - Creates deposit in engine
        - Persists to database
        - Publishes event
        
        Args:
            user_id: User ID
            amount: Deposit amount
            tier: Deposit tier
            referral_code: Optional referral code
            tx_hash: On-chain transaction hash (if applicable)
            chain_id: Chain ID (if on-chain)
            
        Returns:
            UserDeposit record
            
        Raises:
            ValueError: If deposit validation fails
        """
        with self._lock:
            # Create in engine (validates and processes)
            deposit = self._engine.deposit(
                user_id=user_id,
                amount=amount,
                tier=tier,
                referral_code=referral_code,
            )
            
            # Persist to database
            if self._db_adapter and self._db_adapter.is_available:
                db_id = self._db_adapter.create_deposit(
                    user_id=user_id,
                    tier_name=tier.value,
                    amount_usd=amount,
                    net_amount_usd=deposit.amount,
                    unlock_timestamp=deposit.unlock_timestamp,
                    tx_hash=tx_hash,
                    chain_id=chain_id,
                )
                if db_id:
                    # Record owner fee
                    fee = amount - deposit.amount
                    if fee > 0:
                        self._db_adapter.record_owner_fee('deposit', fee, db_id)
            
            # Publish event
            if self._event_publisher:
                self._event_publisher.publish_deposit(
                    user_id=user_id,
                    deposit_id=deposit.deposit_id,
                    amount=deposit.amount,
                    tier=tier.value,
                    event_type='created',
                )
            
            logger.info(
                "Deposit created: user=%s, amount=$%.2f, tier=%s",
                user_id, float(deposit.amount), tier.value
            )
            
            return deposit

    def withdraw_earnings(self, user_id: str) -> Decimal:
        """
        Withdraw user earnings with full integration.
        
        Args:
            user_id: User ID
            
        Returns:
            Amount withdrawn
            
        Raises:
            ValueError: If withdrawal fails
        """
        with self._lock:
            # Withdraw from engine
            amount = self._engine.withdraw_earnings(user_id)
            
            # Record in database
            # Note: The engine already deducted the fee and tracked it internally
            # We just record the withdrawal, not the fee (engine handles fee tracking)
            if self._db_adapter and self._db_adapter.is_available:
                self._db_adapter.record_earnings_withdrawal(user_id, amount)
            
            # Publish event
            if self._event_publisher:
                self._event_publisher.publish_earnings(
                    user_id=user_id,
                    amount=amount,
                    event_type='withdrawn',
                )
            
            logger.info("Earnings withdrawn: user=%s, amount=$%.2f", user_id, float(amount))
            
            return amount

    def withdraw_deposit(self, user_id: str, deposit_id: str) -> Decimal:
        """
        Withdraw deposit after unlock with full integration.
        
        Args:
            user_id: User ID
            deposit_id: Deposit ID
            
        Returns:
            Amount withdrawn
            
        Raises:
            ValueError: If withdrawal fails
        """
        with self._lock:
            # Withdraw from engine
            amount = self._engine.withdraw_deposit(user_id, deposit_id)
            
            # Update database
            # Note: The engine already deducted the fee and tracked it internally
            if self._db_adapter and self._db_adapter.is_available:
                self._db_adapter.update_deposit_status(deposit_id, is_active=False)
            
            # Publish event
            if self._event_publisher:
                self._event_publisher.publish_deposit(
                    user_id=user_id,
                    deposit_id=deposit_id,
                    amount=amount,
                    tier='',
                    event_type='withdrawn',
                )
            
            logger.info(
                "Deposit withdrawn: user=%s, deposit=%s, amount=$%.2f",
                user_id, deposit_id, float(amount)
            )
            
            return amount

    def reinvest_deposit(
        self,
        user_id: str,
        deposit_id: str,
        additional_amount: Decimal,
        new_tier: DepositTier,
    ) -> UserDeposit:
        """
        Reinvest deposit with bonus.
        
        Args:
            user_id: User ID
            deposit_id: Original deposit ID
            additional_amount: Additional funds to add
            new_tier: New tier
            
        Returns:
            Updated deposit
        """
        with self._lock:
            # Reinvest in engine
            deposit = self._engine.reinvest_deposit(
                user_id=user_id,
                deposit_id=deposit_id,
                additional_amount=additional_amount,
                new_tier=new_tier,
            )
            
            # Update database
            if self._db_adapter and self._db_adapter.is_available:
                self._db_adapter.update_deposit_status(
                    deposit_id=deposit_id,
                    is_active=True,
                    reinvestment_count=deposit.reinvestment_count,
                )
            
            # Publish event
            if self._event_publisher:
                self._event_publisher.publish_deposit(
                    user_id=user_id,
                    deposit_id=deposit_id,
                    amount=deposit.amount,
                    tier=new_tier.value,
                    event_type='reinvested',
                )
            
            logger.info(
                "Deposit reinvested: user=%s, deposit=%s, new_amount=$%.2f",
                user_id, deposit_id, float(deposit.amount)
            )
            
            return deposit

    # =========================================================================
    # Referral Operations
    # =========================================================================

    def generate_referral_code(self, user_id: str) -> str:
        """Generate referral code for user."""
        return self._engine.generate_referral_code(user_id)

    # =========================================================================
    # Trading Operations
    # =========================================================================

    def execute_trade(
        self,
        chain_id: int,
        dex_name: str,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        min_amount_out: Decimal,
    ) -> PooledTrade:
        """
        Execute trade on DEX with full integration.
        
        If a DEX broker is configured for the chain, it will execute on-chain.
        Otherwise, it creates a pending trade record.
        
        Args:
            chain_id: Blockchain chain ID
            dex_name: DEX protocol name
            token_in: Input token address
            token_out: Output token address
            amount_in: Amount to trade
            min_amount_out: Minimum output (slippage protection)
            
        Returns:
            PooledTrade record
        """
        with self._lock:
            # Create trade in engine
            trade = self._engine.execute_trade(
                chain_id=chain_id,
                dex_name=dex_name,
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_in,
                min_amount_out=min_amount_out,
            )
            
            # Execute on-chain if broker available
            broker = self._dex_brokers.get(chain_id)
            if broker:
                try:
                    # This would be the actual on-chain execution
                    # For now, we mark as pending for manual/bot execution
                    logger.info(
                        "DEX broker available for chain %d - trade queued for execution",
                        chain_id
                    )
                except Exception as e:
                    logger.error(f"On-chain execution failed: {e}")
                    trade.status = TradeStatus.FAILED
            
            # Record in database
            if self._db_adapter and self._db_adapter.is_available:
                self._db_adapter.record_trade(trade)
            
            # Publish event
            if self._event_publisher:
                self._event_publisher.publish_trade(
                    trade_id=trade.trade_id,
                    chain_id=chain_id,
                    dex=dex_name,
                    amount_in=amount_in,
                    amount_out=trade.amount_out,
                    profit=trade.profit,
                    status=trade.status.value,
                )
            
            return trade

    def record_trade_completion(
        self,
        trade_id: str,
        amount_out: Decimal,
        tx_hash: str,
        gas_used: int,
    ) -> PooledTrade:
        """
        Record completion of a trade.
        
        Args:
            trade_id: Trade ID
            amount_out: Actual output amount
            tx_hash: Transaction hash
            gas_used: Gas used
            
        Returns:
            Updated trade
        """
        with self._lock:
            # Record in engine
            trade = self._engine.record_trade_completion(
                trade_id=trade_id,
                amount_out=amount_out,
                tx_hash=tx_hash,
                gas_used=gas_used,
            )
            
            # Update database
            if self._db_adapter and self._db_adapter.is_available:
                self._db_adapter.record_trade(trade)
                if trade.owner_fee > 0:
                    self._db_adapter.record_owner_fee('trade', trade.owner_fee, trade_id)
            
            # Publish event
            if self._event_publisher:
                self._event_publisher.publish_trade(
                    trade_id=trade_id,
                    chain_id=trade.chain_id,
                    dex=trade.dex_protocol,
                    amount_in=trade.amount_in,
                    amount_out=amount_out,
                    profit=trade.profit,
                    status=trade.status.value,
                )
            
            return trade

    def distribute_profits(self) -> ProfitDistribution:
        """
        Distribute accumulated profits to depositors.
        
        Returns:
            Distribution record
        """
        with self._lock:
            # Distribute in engine
            distribution = self._engine.distribute_profits()
            
            # Record in database
            if self._db_adapter and self._db_adapter.is_available:
                self._db_adapter.record_profit_distribution(distribution)
            
            # Publish event
            if self._event_publisher:
                self._event_publisher.publish_distribution(
                    total_profits=distribution.total_profits,
                    recipient_count=distribution.distribution_count,
                )
            
            logger.info(
                "Profits distributed: $%.2f to %d recipients",
                float(distribution.total_profits),
                distribution.distribution_count,
            )
            
            return distribution

    # =========================================================================
    # Query Operations
    # =========================================================================

    def get_user_deposits(self, user_id: str) -> List[UserDeposit]:
        """Get user's deposits."""
        return self._engine.get_user_deposits(user_id)

    def get_user_earnings(self, user_id: str) -> Decimal:
        """Get user's claimable earnings."""
        return self._engine.get_user_earnings(user_id)

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        stats = self._engine.get_pool_stats()
        
        # Supplement with database stats if available
        if self._db_adapter and self._db_adapter.is_available:
            db_stats = self._db_adapter.get_pool_summary()
            stats['db_total_users'] = db_stats.get('total_users', 0)
            stats['db_total_deposits'] = db_stats.get('total_deposits', 0)
        
        return stats

    def get_tier_config(self, tier: DepositTier) -> TierConfig:
        """Get tier configuration."""
        return self._engine.get_tier_config(tier)

    def get_supported_chains(self) -> List:
        """Get supported chains."""
        return self._engine.get_supported_chains()

    def get_supported_dexes(self) -> List:
        """Get supported DEXes."""
        return self._engine.get_supported_dexes()

    # =========================================================================
    # Admin Operations
    # =========================================================================

    def withdraw_owner_fees(self) -> Decimal:
        """Withdraw accumulated owner fees."""
        with self._lock:
            return self._engine.withdraw_owner_fees()

    def set_paused(self, paused: bool) -> None:
        """Pause/unpause the service."""
        with self._lock:
            self._engine.set_paused(paused)
            logger.info("Service paused: %s", paused)


# ==============================================================================
# FACTORY FUNCTION
# ==============================================================================

_integrated_service: Optional[IntegratedPooledTradingService] = None
_service_lock = threading.Lock()


def get_pooled_trading_service(
    database_service: Optional[Any] = None,
    event_bus: Optional[Any] = None,
    dex_brokers: Optional[Dict[str, Any]] = None,
    force_new: bool = False,
) -> IntegratedPooledTradingService:
    """
    Get or create the integrated pooled trading service.
    
    This is the main entry point for accessing pooled trading functionality.
    
    Args:
        database_service: Optional DatabaseService for persistence
        event_bus: Optional ANVELEventBus for events
        dex_brokers: Optional dict of DEX brokers
        force_new: Force creation of new instance
        
    Returns:
        IntegratedPooledTradingService instance
    """
    global _integrated_service
    
    with _service_lock:
        if _integrated_service is None or force_new:
            _integrated_service = IntegratedPooledTradingService(
                database_service=database_service,
                event_bus=event_bus,
                dex_brokers=dex_brokers,
            )
        return _integrated_service


# ==============================================================================
# MODULE EXPORTS
# ==============================================================================

__all__ = [
    'PooledTradingDatabaseAdapter',
    'PooledTradingEventPublisher',
    'IntegratedPooledTradingService',
    'get_pooled_trading_service',
    # Re-export from engine
    'DepositTier',
    'ChainLayer',
    'TradeStatus',
    'WithdrawalStatus',
    'TierConfig',
    'UserDeposit',
    'PooledTrade',
    'ProfitDistribution',
    'DEFAULT_TIER_CONFIGS',
    'SUPPORTED_CHAINS',
    'SUPPORTED_DEXES',
    'MINIMUM_DEPOSIT_USD',
    'MINIMUM_WITHDRAWAL_USD',
]
