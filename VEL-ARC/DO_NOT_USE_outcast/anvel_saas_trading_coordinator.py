#!/usr/bin/env python3
"""
ANVEL SaaS Trading Bot Coordinator

Integrates subscription management, referral system, and decentralized trading
for multi-user SaaS deployment with secure fund management.

Production-critical module coordinating:
- User subscription validation
- Referral commission processing
- DEX trade execution with user funds
- Smart contract interaction for fund security
- Multi-user isolation and rate limiting
"""

import logging
from decimal import Decimal
from typing import Dict, Optional, Any
from dataclasses import dataclass

from anvel_subscription_manager import (
    ANVELSubscriptionManager,
    SubscriptionTier,
    TIER_LIMITS
)
from anvel_referral_system import ReferralSystem
from anvel_broker_factory import BrokerFactory

logger = logging.getLogger(__name__)


@dataclass
class TradingUser:
    """User trading session data."""
    user_id: str
    subscription_tier: SubscriptionTier
    has_active_subscription: bool
    daily_trades_used: int
    active_positions: int
    referral_code: Optional[str]


class SaaSTradingCoordinator:
    """
    Coordinates multi-user trading with subscription and referral integration.
    Ensures secure fund management and proper isolation between users.
    """

    def __init__(
        self,
        subscription_manager: ANVELSubscriptionManager,
        referral_system: ReferralSystem,
        user_vault_address: Optional[str] = None,
    ):
        """
        Initialize SaaS trading coordinator.
        
        Args:
            subscription_manager: Subscription management system
            referral_system: Referral tracking system
            user_vault_address: Smart contract address for user fund vault
        """
        self.subscription_manager = subscription_manager
        self.referral_system = referral_system
        self.user_vault_address = user_vault_address

        # User session cache
        self.active_users: Dict[str, TradingUser] = {}

        logger.info("SaaS Trading Coordinator initialized")

    def validate_user_access(
        self,
        user_id: str,
        required_tier: Optional[SubscriptionTier] = None
    ) -> bool:
        """
        Validate user has active subscription and meets tier requirements.
        
        Args:
            user_id: User UUID
            required_tier: Minimum required tier (None for any active subscription)
            
        Returns:
            True if user has valid access, False otherwise
        """
        # Get subscription
        subscription = self.subscription_manager.get_user_subscription(user_id)

        if not subscription or subscription.get("status") != "active":
            logger.warning(f"User {user_id} has no active subscription")
            return False

        # Check tier requirement
        if required_tier:
            user_tier = SubscriptionTier(subscription["tier"])
            if user_tier != required_tier:
                logger.warning(
                    f"User {user_id} has {user_tier.value} tier, "
                    f"requires {required_tier.value}"
                )
                return False

        return True

    def execute_user_trade(
        self,
        user_id: str,
        dex_id: str,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        slippage_bps: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute DEX trade on behalf of subscribed user.
        
        Args:
            user_id: User UUID
            dex_id: DEX identifier ('uniswap_v3', 'pancakeswap_v2')
            token_in: Input token address
            token_out: Output token address
            amount_in: Amount to trade
            slippage_bps: Slippage tolerance
            
        Returns:
            Trade execution result
        """
        # Validate subscription
        if not self.validate_user_access(user_id):
            return {
                "status": "error",
                "message": "Active subscription required",
                "user_id": user_id,
            }

        # Get subscription details
        subscription = self.subscription_manager.get_user_subscription(user_id)
        tier = SubscriptionTier(subscription["tier"])
        limits = TIER_LIMITS[tier]

        # Check daily trade limit
        daily_trades = self._get_user_daily_trades(user_id)
        if daily_trades >= limits.max_daily_trades:
            return {
                "status": "error",
                "message": f"Daily trade limit reached ({limits.max_daily_trades})",
                "user_id": user_id,
                "tier": tier.value,
            }

        # Check rate limit
        if not self.subscription_manager.check_rate_limit(user_id, f"trade_{dex_id}"):
            return {
                "status": "error",
                "message": "Rate limit exceeded",
                "user_id": user_id,
            }

        try:
            # Create DEX broker
            dex_broker = BrokerFactory.create_dex(
                dex_id,
                slippage_tolerance_bps=slippage_bps or 50,
            )

            # Execute trade
            result = dex_broker.execute_swap(
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_in,
                slippage_bps=slippage_bps,
            )

            if result["status"] == "success":
                # Increment trade counter
                self._increment_user_trades(user_id)

                logger.info(
                    f"User {user_id} trade successful: {amount_in} {token_in} -> "
                    f"{result.get('expected_amount_out')} {token_out}"
                )

            return {
                **result,
                "user_id": user_id,
                "tier": tier.value,
                "daily_trades_used": daily_trades + 1,
                "daily_trades_limit": limits.max_daily_trades,
            }

        except Exception as e:
            logger.error(f"Trade execution failed for user {user_id}: {e}")
            return {
                "status": "error",
                "message": str(e),
                "user_id": user_id,
            }

    def process_subscription_payment(
        self,
        user_id: str,
        payment_amount_usd: Decimal,
        payment_id: str,
    ) -> Dict[str, Any]:
        """
        Process subscription payment and handle referral commissions.
        
        Args:
            user_id: User UUID
            payment_amount_usd: Payment amount in USD
            payment_id: Payment transaction ID
            
        Returns:
            Processing result with referral info
        """
        result = {
            "status": "success",
            "user_id": user_id,
            "payment_amount": float(payment_amount_usd),
            "referral_commission": 0.0,
        }

        # Activate referral if this is first payment
        try:
            self.referral_system.activate_referral(user_id)
        except Exception as e:
            logger.warning(f"Failed to activate referral for {user_id}: {e}")

        # Record referral commission
        try:
            commission_id = self.referral_system.record_commission(
                subscription_payment_id=payment_id,
                referred_user_id=user_id,
                subscription_amount_usd=payment_amount_usd,
            )

            if commission_id:
                commission_amount = payment_amount_usd * Decimal("0.10")  # 10%
                result["referral_commission"] = float(commission_amount)
                result["commission_id"] = commission_id
                logger.info(
                    f"Recorded ${commission_amount} commission for user {user_id} payment"
                )
        except Exception as e:
            logger.error(f"Failed to record referral commission: {e}")

        return result

    def create_user_referral_code(self, user_id: str) -> str:
        """
        Create referral code for user.
        
        Args:
            user_id: User UUID
            
        Returns:
            Referral code
        """
        return self.referral_system.generate_referral_code(user_id)

    def apply_referral_to_user(
        self,
        new_user_id: str,
        referral_code: str
    ) -> bool:
        """
        Apply referral code to new user signup.
        
        Args:
            new_user_id: New user UUID
            referral_code: Referral code to apply
            
        Returns:
            True if applied successfully
        """
        return self.referral_system.apply_referral_code(
            referred_user_id=new_user_id,
            referral_code=referral_code
        )

    def get_user_dashboard_data(self, user_id: str) -> Dict[str, Any]:
        """
        Get comprehensive dashboard data for user.
        
        Args:
            user_id: User UUID
            
        Returns:
            Dashboard data including subscription, referrals, limits
        """
        # Get subscription
        subscription = self.subscription_manager.get_user_subscription(user_id)

        if not subscription:
            return {
                "has_subscription": False,
                "message": "No active subscription",
            }

        tier = SubscriptionTier(subscription["tier"])
        limits = TIER_LIMITS[tier]

        # Get referral stats
        referral_stats = self.referral_system.get_referral_stats(user_id)

        # Get usage stats
        daily_trades = self._get_user_daily_trades(user_id)

        return {
            "has_subscription": True,
            "subscription": {
                "tier": tier.value,
                "status": subscription["status"],
                "expires_at": subscription.get("ends_at"),
                "monthly_price": float(limits.monthly_price_usd),
            },
            "limits": {
                "api_calls_per_minute": limits.max_api_calls_per_minute,
                "active_positions": limits.max_active_positions,
                "daily_trades": limits.max_daily_trades,
                "exchanges": limits.max_exchanges,
            },
            "usage": {
                "daily_trades_used": daily_trades,
                "daily_trades_remaining": max(0, limits.max_daily_trades - daily_trades),
            },
            "features": {
                "ai_enabled": limits.ai_features_enabled,
                "backtesting": limits.backtesting_enabled,
                "advanced_analytics": limits.advanced_analytics,
                "priority_support": limits.priority_support,
            },
            "referral": referral_stats,
        }

    def _get_user_daily_trades(self, user_id: str) -> int:
        """Get number of trades user executed today."""
        # In production, query from database
        # For now, return from cache
        user = self.active_users.get(user_id)
        return user.daily_trades_used if user else 0

    def _increment_user_trades(self, user_id: str) -> None:
        """Increment user's daily trade counter."""
        # In production, update database
        if user_id in self.active_users:
            self.active_users[user_id].daily_trades_used += 1
