#!/usr/bin/env python3
"""
ANVEL Global Pooled Trading Engine

A decentralized, multi-chain trading engine that operates exclusively on DEXs
for maximum security, privacy, and reliability.

This module provides:
- Single global pooled trading system for large capital
- Multi-chain support (Layer 1, 2, and 3)
- Profit sharing with depositors
- Owner micro-fees for sustainability
- Complete decentralization (no centralized exchanges)

PRODUCTION-CRITICAL: This module handles real capital.
All operations must be deterministic, secure, and auditable.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from collections import deque
import hashlib
import secrets

logger = logging.getLogger(__name__)


# ==============================================================================
# CONSTANTS
# ==============================================================================

# Deposit limits (in USD, assuming 6 decimal stablecoin)
MINIMUM_DEPOSIT_USD = Decimal("10.00")
MINIMUM_WITHDRAWAL_USD = Decimal("15.00")

# Fee structure (in basis points)
OWNER_DEPOSIT_FEE_BPS = Decimal("0")  # No deposit fee — membership fee covers access
OWNER_WITHDRAWAL_FEE_BPS = Decimal("0")  # Standard withdrawal has no BPS fee
REINVESTMENT_BONUS_BPS = Decimal("200")  # 2% bonus on reinvestment
BPS_DENOMINATOR = Decimal("10000")

# =============================================================================
# MEMBERSHIP FEE
# =============================================================================
# Every member pays a flat $10 membership fee on first deposit.
# This fee goes into an off-books rainy-day fund (NOT on-chain, NOT in the
# reserve). It is tracked separately and is owner-controlled emergency capital.
MEMBERSHIP_FEE_USD = Decimal("10.00")

# =============================================================================
# TRADE PROFIT SPLIT (60/30/10)
# =============================================================================
# 60% of realized profit goes to members (proportional to their pool share,
#     compounded daily into their principal)
MEMBER_PROFIT_SHARE_PCT = Decimal("0.60")
# 30% of realized profit goes to the owner
OWNER_PROFIT_SHARE_PCT = Decimal("0.30")
# 10% of realized profit goes to the on-chain emergency/reserve fund
RESERVE_PROFIT_SHARE_PCT = Decimal("0.10")

# Legacy constant - DEPRECATED but exported for backward compatibility with tests
OWNER_TRADE_FEE_BPS = Decimal("10")  # Deprecated: was 0.1% of trade profits

# =============================================================================
# WITHDRAWAL RULES
# =============================================================================
# Minimum withdrawal amount
MINIMUM_WITHDRAWAL_USD = Decimal("15.00")
# Standard withdrawal cooldown: 72 hours
EARNINGS_WITHDRAWAL_COOLDOWN = 72 * 3600  # 72 hours in seconds
# Early withdrawal penalty: 25% of withdrawal amount
EARLY_WITHDRAWAL_PENALTY_PCT = Decimal("0.25")

# =============================================================================
# REFERRAL CONFIGURATION
# =============================================================================
REFERRAL_BONUS_USD = Decimal("1.00")
REFERRAL_LIFETIME_CAP_USD = Decimal("2000.00")
AFFILIATE_LEADER_LIFETIME_CAP_USD = Decimal("100000.00")

# Legacy referral constants - DEPRECATED
REFERRER_BONUS_RATE = Decimal("0.10")
REFERRED_BONUS_BPS = Decimal("200")
REFERRER_BONUS_BPS = Decimal("500")
AFFILIATE_LEADER_BONUS_USD = Decimal("100.00")

# Time periods (in seconds)
PROFIT_DISTRIBUTION_INTERVAL = 24 * 3600  # Daily


# ==============================================================================
# ENUMS
# ==============================================================================

class DepositTier(Enum):
    """
    Single-tier deposit system with graduated bonus percentages.
    
    The system uses a single tier (STANDARD) with bonus percentages
    applied based on deposit amount. This replaces the previous
    three-tier time-locked system.
    
    Bonus Structure (based on deposit amount):
    - $10-$499: Base rate only (6% APY)
    - $500-$999: +0.5% bonus (6.5% APY)
    - $1,000-$1,999: +1% bonus (7% APY)
    - $2,000-$4,999: +1.5% bonus (7.5% APY)
    - $5,000-$9,999: +2% bonus (8% APY)
    - $10,000-$24,999: +2.5% bonus (8.5% APY)
    - $25,000-$49,999: +3% bonus (9% APY)
    - $50,000-$100,000: +3.5% bonus (9.5% APY)
    
    Note: Legacy tier values maintained for backward compatibility.
    """
    STANDARD = "standard"  # Single tier for all deposits
    # Legacy tiers (deprecated but kept for migration)
    THREE_MONTH = "three_month"
    SIX_MONTH = "six_month"
    NINE_MONTH = "nine_month"


class ChainLayer(Enum):
    """Blockchain layer classification."""
    LAYER_1 = "layer_1"  # Ethereum mainnet, BSC, Avalanche, etc.
    LAYER_2 = "layer_2"  # Arbitrum, Optimism, Base, Polygon
    LAYER_3 = "layer_3"  # Application-specific chains


class TradeStatus(Enum):
    """Status of a trade execution."""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERTED = "reverted"


class WithdrawalStatus(Enum):
    """Status of a withdrawal request."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ==============================================================================
# DATA CLASSES
# ==============================================================================

@dataclass
class TierConfig:
    """Configuration for a deposit tier."""
    tier: DepositTier
    lock_period_days: int
    yield_bps: Decimal  # Annual yield in basis points
    min_deposit_usd: Decimal
    max_deposit_usd: Decimal
    is_active: bool = True

    def get_lock_period_seconds(self) -> int:
        """Get lock period in seconds."""
        return self.lock_period_days * 24 * 3600


@dataclass
class UserDeposit:
    """Record of a user's deposit."""
    deposit_id: str
    user_id: str
    amount: Decimal
    tier: DepositTier
    deposit_timestamp: int
    unlock_timestamp: int
    accumulated_earnings: Decimal = Decimal("0")
    last_earnings_claim: int = 0
    reinvestment_count: int = 0
    is_active: bool = True


@dataclass
class PooledTrade:
    """Record of a pooled trade execution."""
    trade_id: str
    chain_id: int
    chain_layer: ChainLayer
    dex_protocol: str
    token_in: str
    token_out: str
    amount_in: Decimal
    amount_out: Decimal
    profit: Decimal
    owner_fee: Decimal
    user_profit_share: Decimal
    tx_hash: Optional[str] = None
    status: TradeStatus = TradeStatus.PENDING
    timestamp: int = 0
    gas_used: int = 0


@dataclass
class ProfitDistribution:
    """
    Record of profit distribution to users.
    
    Split structure (70/20/10):
    - 70% to members (compounded to their principal)
    - 20% to owners
    - 10% to reserve (for referral bonuses and emergencies)
    """
    distribution_id: str
    timestamp: int
    total_profits: Decimal
    owner_fees: Decimal
    user_share: Decimal
    reserve_share: Decimal  # 10% for referral bonuses and rainy days
    total_pool_value: Decimal
    distribution_count: int = 0


@dataclass
class SupportedChain:
    """Configuration for a supported blockchain."""
    chain_id: int
    chain_name: str
    layer: ChainLayer
    rpc_url: str
    block_time_seconds: int = 12
    native_token: str = "ETH"
    is_active: bool = True
    supported_dexes: List[str] = field(default_factory=list)


@dataclass
class DEXConfig:
    """Configuration for a supported DEX."""
    name: str
    chain_ids: List[int]
    router_addresses: Dict[int, str]
    factory_addresses: Dict[int, str]
    fee_tiers: List[int]
    is_active: bool = True


# ==============================================================================
# GRADUATED BONUS STRUCTURE (Single-Tier System)
# ==============================================================================

# Base annual yield rate (realistic, sustainable from DeFi arbitrage + LP yields)
# Achievable through: DEX arbitrage (10-25%), LP provision (8-20%), yield farming (15-40%)
BASE_YIELD_BPS = Decimal("1000")  # 10% APY base rate

# Deposit amount thresholds and bonus percentages (in basis points)
# These are ADDITIVE bonuses on top of the base rate
# Higher deposits enable larger position sizes and better arbitrage opportunities
GRADUATED_BONUS_TIERS: List[Tuple[Decimal, Decimal, Decimal]] = [
    # (min_amount, max_amount, bonus_bps)
    (Decimal("10.00"), Decimal("499.99"), Decimal("0")),       # $10-$499: 10% APY (no bonus)
    (Decimal("500.00"), Decimal("999.99"), Decimal("100")),    # $500-$999: 11% APY (+1%)
    (Decimal("1000.00"), Decimal("1999.99"), Decimal("200")),  # $1,000-$1,999: 12% APY (+2%)
    (Decimal("2000.00"), Decimal("4999.99"), Decimal("300")),  # $2,000-$4,999: 13% APY (+3%)
    (Decimal("5000.00"), Decimal("9999.99"), Decimal("400")),  # $5,000-$9,999: 14% APY (+4%)
    (Decimal("10000.00"), Decimal("24999.99"), Decimal("500")), # $10,000-$24,999: 15% APY (+5%)
    (Decimal("25000.00"), Decimal("49999.99"), Decimal("600")), # $25,000-$49,999: 16% APY (+6%)
    (Decimal("50000.00"), Decimal("100000.00"), Decimal("800")), # $50,000-$100,000: 18% APY (+8%)
]

# Maximum deposit limit
MAXIMUM_DEPOSIT_USD = Decimal("100000.00")


def calculate_effective_yield_bps(deposit_amount: Decimal) -> Decimal:
    """
    Calculate the effective annual yield rate based on deposit amount.
    
    Uses a graduated bonus structure where larger deposits receive
    higher yields. This is a conservative, sustainable model based on
    realistic DeFi yield expectations.
    
    Args:
        deposit_amount: Amount deposited in USD
        
    Returns:
        Effective annual yield in basis points
        
    Raises:
        ValueError: If deposit amount is below minimum or above maximum
    """
    if deposit_amount < MINIMUM_DEPOSIT_USD:
        raise ValueError(
            f"Deposit amount ${deposit_amount} is below minimum ${MINIMUM_DEPOSIT_USD}"
        )
    
    if deposit_amount > MAXIMUM_DEPOSIT_USD:
        raise ValueError(
            f"Deposit amount ${deposit_amount} exceeds maximum ${MAXIMUM_DEPOSIT_USD}"
        )
    
    # Find matching tier
    for min_amt, max_amt, bonus_bps in GRADUATED_BONUS_TIERS:
        if min_amt <= deposit_amount <= max_amt:
            return BASE_YIELD_BPS + bonus_bps
    
    # Fallback to base rate (should not reach here with valid input)
    logger.warning(
        f"No matching tier for deposit amount ${deposit_amount}, using base rate"
    )
    return BASE_YIELD_BPS


def get_deposit_tier_info(deposit_amount: Decimal) -> Dict[str, Any]:
    """
    Get comprehensive tier information for a deposit amount.
    
    Args:
        deposit_amount: Amount to deposit in USD
        
    Returns:
        Dict containing tier details, yield info, and bonus information
    """
    effective_yield = calculate_effective_yield_bps(deposit_amount)
    base_yield = BASE_YIELD_BPS
    bonus = effective_yield - base_yield
    
    # Calculate APY as percentage
    effective_apy = float(effective_yield) / 100
    base_apy = float(base_yield) / 100
    bonus_pct = float(bonus) / 100
    
    # Determine tier name based on bonus
    tier_names = {
        Decimal("0"): "Standard",
        Decimal("100"): "Bronze",
        Decimal("200"): "Silver",
        Decimal("300"): "Gold",
        Decimal("400"): "Platinum",
        Decimal("500"): "Diamond",
        Decimal("600"): "Elite",
        Decimal("800"): "Premier",
    }
    tier_name = tier_names.get(bonus, "Standard")
    
    return {
        "tier_name": tier_name,
        "deposit_amount": float(deposit_amount),
        "base_apy_percent": base_apy,
        "bonus_percent": bonus_pct,
        "effective_apy_percent": effective_apy,
        "effective_yield_bps": int(effective_yield),
        "annual_earnings_estimate": float(deposit_amount * effective_yield / BPS_DENOMINATOR),
        "monthly_earnings_estimate": float(deposit_amount * effective_yield / BPS_DENOMINATOR / Decimal("12")),
        "weekly_earnings_estimate": float(deposit_amount * effective_yield / BPS_DENOMINATOR / Decimal("52")),
    }


# ==============================================================================
# TIER CONFIGURATIONS (Updated for Single-Tier System)
# ==============================================================================

DEFAULT_TIER_CONFIGS: Dict[DepositTier, TierConfig] = {
    # Primary single-tier configuration
    DepositTier.STANDARD: TierConfig(
        tier=DepositTier.STANDARD,
        lock_period_days=30,  # 30-day minimum lock for earnings
        yield_bps=BASE_YIELD_BPS,  # Base rate, bonuses applied dynamically
        min_deposit_usd=MINIMUM_DEPOSIT_USD,
        max_deposit_usd=MAXIMUM_DEPOSIT_USD,
        is_active=True,
    ),
    # Legacy tiers (deprecated - kept for backward compatibility/migration)
    DepositTier.THREE_MONTH: TierConfig(
        tier=DepositTier.THREE_MONTH,
        lock_period_days=90,
        yield_bps=Decimal("600"),  # Mapped to base rate
        min_deposit_usd=Decimal("10.00"),
        max_deposit_usd=Decimal("100000.00"),
        is_active=False,  # Deprecated
    ),
    DepositTier.SIX_MONTH: TierConfig(
        tier=DepositTier.SIX_MONTH,
        lock_period_days=180,
        yield_bps=Decimal("600"),  # Mapped to base rate
        min_deposit_usd=Decimal("10.00"),
        max_deposit_usd=Decimal("100000.00"),
        is_active=False,  # Deprecated
    ),
    DepositTier.NINE_MONTH: TierConfig(
        tier=DepositTier.NINE_MONTH,
        lock_period_days=270,
        yield_bps=Decimal("600"),  # Mapped to base rate
        min_deposit_usd=Decimal("10.00"),
        max_deposit_usd=Decimal("100000.00"),
        is_active=False,  # Deprecated
    ),
}


# ==============================================================================
# SUPPORTED CHAINS (DEX-ONLY, NO CENTRALIZED EXCHANGES)
# ==============================================================================

SUPPORTED_CHAINS: Dict[int, SupportedChain] = {
    # Layer 1 Chains
    1: SupportedChain(
        chain_id=1,
        chain_name="Ethereum Mainnet",
        layer=ChainLayer.LAYER_1,
        rpc_url="https://eth.llamarpc.com",
        block_time_seconds=12,
        native_token="ETH",
        supported_dexes=["uniswap_v3", "sushiswap", "curve"],
    ),
    56: SupportedChain(
        chain_id=56,
        chain_name="BNB Smart Chain",
        layer=ChainLayer.LAYER_1,
        rpc_url="https://bsc-dataseed1.binance.org/",
        block_time_seconds=3,
        native_token="BNB",
        supported_dexes=["pancakeswap_v3", "pancakeswap_v2"],
    ),
    43114: SupportedChain(
        chain_id=43114,
        chain_name="Avalanche C-Chain",
        layer=ChainLayer.LAYER_1,
        rpc_url="https://api.avax.network/ext/bc/C/rpc",
        block_time_seconds=2,
        native_token="AVAX",
        supported_dexes=["traderjoe", "pangolin"],
    ),
    # Layer 2 Chains
    42161: SupportedChain(
        chain_id=42161,
        chain_name="Arbitrum One",
        layer=ChainLayer.LAYER_2,
        rpc_url="https://arb1.arbitrum.io/rpc",
        block_time_seconds=1,
        native_token="ETH",
        supported_dexes=["uniswap_v3", "camelot", "sushiswap"],
    ),
    10: SupportedChain(
        chain_id=10,
        chain_name="Optimism",
        layer=ChainLayer.LAYER_2,
        rpc_url="https://mainnet.optimism.io",
        block_time_seconds=2,
        native_token="ETH",
        supported_dexes=["uniswap_v3", "velodrome"],
    ),
    137: SupportedChain(
        chain_id=137,
        chain_name="Polygon PoS",
        layer=ChainLayer.LAYER_2,
        rpc_url="https://polygon-rpc.com",
        block_time_seconds=2,
        native_token="MATIC",
        supported_dexes=["uniswap_v3", "quickswap", "sushiswap"],
    ),
    8453: SupportedChain(
        chain_id=8453,
        chain_name="Base",
        layer=ChainLayer.LAYER_2,
        rpc_url="https://mainnet.base.org",
        block_time_seconds=2,
        native_token="ETH",
        supported_dexes=["uniswap_v3", "aerodrome"],
    ),
    324: SupportedChain(
        chain_id=324,
        chain_name="zkSync Era",
        layer=ChainLayer.LAYER_2,
        rpc_url="https://mainnet.era.zksync.io",
        block_time_seconds=1,
        native_token="ETH",
        supported_dexes=["syncswap", "mute"],
    ),
    59144: SupportedChain(
        chain_id=59144,
        chain_name="Linea",
        layer=ChainLayer.LAYER_2,
        rpc_url="https://rpc.linea.build",
        block_time_seconds=3,
        native_token="ETH",
        supported_dexes=["syncswap", "velocore"],
    ),
    # Layer 3 Chains (Application-specific)
    660279: SupportedChain(
        chain_id=660279,
        chain_name="Xai",
        layer=ChainLayer.LAYER_3,
        rpc_url="https://xai-chain.net/rpc",
        block_time_seconds=1,
        native_token="XAI",
        supported_dexes=["native"],
    ),
}


# ==============================================================================
# DEX CONFIGURATIONS (DECENTRALIZED ONLY)
# ==============================================================================

SUPPORTED_DEXES: Dict[str, DEXConfig] = {
    "uniswap_v3": DEXConfig(
        name="Uniswap V3",
        chain_ids=[1, 42161, 10, 137, 8453],
        router_addresses={
            1: "0xE592427A0AEce92De3Edee1F18E0157C05861564",
            42161: "0xE592427A0AEce92De3Edee1F18E0157C05861564",
            10: "0xE592427A0AEce92De3Edee1F18E0157C05861564",
            137: "0xE592427A0AEce92De3Edee1F18E0157C05861564",
            8453: "0x2626664c2603336E57B271c5C0b26F421741e481",
        },
        factory_addresses={
            1: "0x1F98431c8aD98523631AE4a59f267346ea31F984",
            42161: "0x1F98431c8aD98523631AE4a59f267346ea31F984",
            10: "0x1F98431c8aD98523631AE4a59f267346ea31F984",
            137: "0x1F98431c8aD98523631AE4a59f267346ea31F984",
            8453: "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",
        },
        fee_tiers=[500, 3000, 10000],
        is_active=True,
    ),
    "pancakeswap_v3": DEXConfig(
        name="PancakeSwap V3",
        chain_ids=[56, 1, 42161],
        router_addresses={
            56: "0x1b81D678ffb9C0263b24A97847620C99d213eB14",
            1: "0x1b81D678ffb9C0263b24A97847620C99d213eB14",
            42161: "0x1b81D678ffb9C0263b24A97847620C99d213eB14",
        },
        factory_addresses={
            56: "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
            1: "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
            42161: "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",
        },
        fee_tiers=[100, 500, 2500, 10000],
        is_active=True,
    ),
    "sushiswap": DEXConfig(
        name="SushiSwap",
        chain_ids=[1, 42161, 137, 43114],
        router_addresses={
            1: "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",
            42161: "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
            137: "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
            43114: "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
        },
        factory_addresses={
            1: "0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac",
            42161: "0xc35DADB65012eC5796536bD9864eD8773aBc74C4",
            137: "0xc35DADB65012eC5796536bD9864eD8773aBc74C4",
            43114: "0xc35DADB65012eC5796536bD9864eD8773aBc74C4",
        },
        fee_tiers=[3000],  # 0.3%
        is_active=True,
    ),
    "curve": DEXConfig(
        name="Curve Finance",
        chain_ids=[1, 42161, 10, 137],
        router_addresses={
            1: "0x99a58482BD75cbab83b27EC03CA68fF489b5788f",
            42161: "0x445FE580eF8d70FF569aB36e80c647af338db351",
            10: "0x0DCDED3545D565bA3B19E683431381007245d983",
            137: "0xfA9a30350048B2BF66865ee20363067c66f67e58",
        },
        factory_addresses={
            1: "0xF18056Bbd320E96A48e3Fbf8bC061322531aac99",
            42161: "0xb17b674D9c5CB2e441F8e196a2f048A81355d031",
            10: "0x2db0E83599a91b508Ac268a6197b8B14F5e72840",
            137: "0x722272D36ef0Da72FF51c5A65Db7b870E2e8D4ee",
        },
        fee_tiers=[400],  # 0.04% typical
        is_active=True,
    ),
    "velodrome": DEXConfig(
        name="Velodrome",
        chain_ids=[10],
        router_addresses={
            10: "0xa062aE8A9c5e11aaA026fc2670B0D65cCc8B2858",
        },
        factory_addresses={
            10: "0x25CbdDb98b35ab1FF77413456B31EC81A6B6B746",
        },
        fee_tiers=[100, 3000],
        is_active=True,
    ),
    "aerodrome": DEXConfig(
        name="Aerodrome",
        chain_ids=[8453],
        router_addresses={
            8453: "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",
        },
        factory_addresses={
            8453: "0x420DD381b31aEf6683db6B902084cB0FFECe40Da",
        },
        fee_tiers=[100, 3000],
        is_active=True,
    ),
    "camelot": DEXConfig(
        name="Camelot",
        chain_ids=[42161],
        router_addresses={
            42161: "0xc873fEcbd354f5A56E00E710B90EF4201db2448d",
        },
        factory_addresses={
            42161: "0x6EcCab422D763aC031210895C81787E87B43A652",
        },
        fee_tiers=[3000],
        is_active=True,
    ),
    "quickswap": DEXConfig(
        name="QuickSwap",
        chain_ids=[137],
        router_addresses={
            137: "0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff",
        },
        factory_addresses={
            137: "0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32",
        },
        fee_tiers=[3000],
        is_active=True,
    ),
    "traderjoe": DEXConfig(
        name="Trader Joe",
        chain_ids=[43114, 42161],
        router_addresses={
            43114: "0x60aE616a2155Ee3d9A68541Ba4544862310933d4",
            42161: "0xbeE5c10Cf6E4F68f831E11C1D9E59B43560B3571",
        },
        factory_addresses={
            43114: "0x9Ad6C38BE94206cA50bb0d90783181e9d5BC5BcE",
            42161: "0x8e42f2F4101563bF679975178e880FD87d3eFd4e",
        },
        fee_tiers=[2500],
        is_active=True,
    ),
    "syncswap": DEXConfig(
        name="SyncSwap",
        chain_ids=[324, 59144],
        router_addresses={
            324: "0x2da10A1e27bF85cEdD8FFb1AbBe97e53391C0295",
            59144: "0x80e38291e06339d10AAB483C65695D004dBD5C69",
        },
        factory_addresses={
            324: "0xf2DAd89f2788a8CD54625C60b55cD3d2D0ACa7Cb",
            59144: "0x37BAc764494c8db4e54BDE72f6965beA9fa0AC2d",
        },
        fee_tiers=[100, 500, 3000],
        is_active=True,
    ),
}


# ==============================================================================
# POOLED TRADING ENGINE
# ==============================================================================

class PooledTradingEngine:
    """
    Global pooled trading engine that operates exclusively on DEXs.

    Features:
    - Multi-chain support (L1, L2, L3)
    - Profit sharing with depositors
    - Owner micro-fees for sustainability
    - Complete decentralization
    - Thread-safe operations
    """

    def __init__(
        self,
        tier_configs: Optional[Dict[DepositTier, TierConfig]] = None,
        private_key: Optional[str] = None,
    ):
        """
        Initialize the pooled trading engine.

        Args:
            tier_configs: Custom tier configurations (uses defaults if None)
            private_key: Private key for signing transactions (from env if None)
        """
        self.tier_configs = tier_configs or DEFAULT_TIER_CONFIGS.copy()
        self._private_key = private_key

        # State management
        self._lock = threading.Lock()
        self._deposits: Dict[str, UserDeposit] = {}
        self._user_deposits: Dict[str, List[str]] = {}  # user_id -> deposit_ids
        self._trades: deque = deque(maxlen=10000)
        self._profit_distributions: deque = deque(maxlen=1000)

        # Pool metrics
        self._total_pool_value = Decimal("0")
        self._undistributed_profits = Decimal("0")
        self._owner_accumulated_fees = Decimal("0")
        self._total_trades_executed = 0
        self._total_profits_distributed = Decimal("0")

        # Reserve account — ON-CHAIN emergency fund (10% of trade profits)
        self._reserve_balance = Decimal("0")
        self._total_reserve_allocated = Decimal("0")

        # Rainy-day fund — OFF-BOOKS owner-controlled emergency capital
        # Funded by $10 membership fees, not visible on-chain
        self._rainy_day_fund = Decimal("0")
        self._total_membership_fees_collected = Decimal("0")

        # Membership tracking
        self._members: Dict[str, Dict] = {}  # user_id -> membership info
        self._membership_paid: set = set()  # user_ids who paid $10

        # Staking / time-lock tracking
        self._staked_deposits: Dict[str, Dict] = {}  # deposit_id -> stake info
        self._timelock_deposits: Dict[str, Dict] = {}  # deposit_id -> lock info

        # Referral tracking
        self._referral_codes: Dict[str, str] = {}  # code -> user_id
        self._user_referrals: Dict[str, str] = {}  # user_id -> referral_code
        self._referral_earnings: Dict[str, Decimal] = {}
        self._referred_users_with_first_deposit: set = set()
        self._team_affiliate_leaders: set = set()
        self._referral_counts: Dict[str, int] = {}

        # User earnings tracking
        self._user_earnings: Dict[str, Decimal] = {}
        self._user_last_earnings_withdrawal: Dict[str, int] = {}

        # Withdrawal requests
        self._pending_withdrawals: Dict[str, Dict] = {}

        # Timing
        self._last_profit_distribution = int(time.time())

        # Active state
        self._is_active = True
        self._is_paused = False

        logger.info(
            "PooledTradingEngine initialized | splits=60/30/10 | "
            "membership=$%.2f | min_withdraw=$%.2f | cooldown=%dh | "
            "early_penalty=%.0f%% | chains=%d | dexes=%d",
            MEMBERSHIP_FEE_USD, MINIMUM_WITHDRAWAL_USD,
            EARNINGS_WITHDRAWAL_COOLDOWN // 3600,
            EARLY_WITHDRAWAL_PENALTY_PCT * 100,
            len(SUPPORTED_CHAINS),
            len(SUPPORTED_DEXES),
        )

    # ==========================================================================
    # DEPOSIT FUNCTIONS
    # ==========================================================================

    def deposit(
        self,
        user_id: str,
        amount: Decimal,
        tier: DepositTier,
        referral_code: Optional[str] = None,
        stake_days: int = 0,
        timelock_until: int = 0,
    ) -> UserDeposit:
        """
        Create a new deposit for a user.

        First-time depositors pay a $10 membership fee that goes to the
        off-books rainy-day fund. Subsequent deposits have no access fee.

        Args:
            user_id: Unique user identifier
            amount: Deposit amount in USD (must cover membership if first time)
            tier: Selected deposit tier
            referral_code: Optional referral code
            stake_days: Optional staking period in days (0 = no staking)
            timelock_until: Optional Unix timestamp to lock funds until

        Returns:
            UserDeposit record

        Raises:
            ValueError: If deposit parameters are invalid
        """
        with self._lock:
            if self._is_paused:
                raise ValueError("Deposits are currently paused")

            # Validate tier
            tier_config = self.tier_configs.get(tier)
            if not tier_config or not tier_config.is_active:
                raise ValueError(f"Tier {tier.value} is not active")

            # ── Membership fee (first deposit only) ──────────────────────
            membership_deducted = Decimal("0")
            if user_id not in self._membership_paid:
                if amount < MEMBERSHIP_FEE_USD + MINIMUM_DEPOSIT_USD:
                    raise ValueError(
                        f"First deposit must be at least "
                        f"${MEMBERSHIP_FEE_USD + MINIMUM_DEPOSIT_USD} "
                        f"(${MEMBERSHIP_FEE_USD} membership + "
                        f"${MINIMUM_DEPOSIT_USD} minimum deposit)"
                    )
                membership_deducted = MEMBERSHIP_FEE_USD
                self._rainy_day_fund += MEMBERSHIP_FEE_USD
                self._total_membership_fees_collected += MEMBERSHIP_FEE_USD
                self._membership_paid.add(user_id)
                self._members[user_id] = {
                    "joined": int(time.time()),
                    "membership_fee_paid": float(MEMBERSHIP_FEE_USD),
                }
                logger.info(
                    "Membership fee collected: user=%s, fee=$%.2f -> rainy-day fund",
                    user_id, float(MEMBERSHIP_FEE_USD),
                )

            net_after_membership = amount - membership_deducted

            # Validate amount against tier limits
            if net_after_membership < MINIMUM_DEPOSIT_USD:
                raise ValueError(f"Minimum deposit is ${MINIMUM_DEPOSIT_USD}")
            if net_after_membership < tier_config.min_deposit_usd:
                raise ValueError(
                    f"Minimum for {tier.value} tier is ${tier_config.min_deposit_usd}"
                )
            if net_after_membership > tier_config.max_deposit_usd:
                raise ValueError(
                    f"Maximum for {tier.value} tier is ${tier_config.max_deposit_usd}"
                )

            net_deposit = net_after_membership  # No BPS fee — membership covers access

            # Create deposit record
            current_time = int(time.time())
            deposit_id = self._generate_deposit_id(user_id, current_time)

            # Lock period: max of tier lock, staking, and timelock
            tier_unlock = current_time + tier_config.get_lock_period_seconds()
            stake_unlock = (current_time + stake_days * 86400) if stake_days > 0 else 0
            timelock_unlock = timelock_until if timelock_until > current_time else 0
            unlock_timestamp = max(tier_unlock, stake_unlock, timelock_unlock)

            deposit = UserDeposit(
                deposit_id=deposit_id,
                user_id=user_id,
                amount=net_deposit,
                tier=tier,
                deposit_timestamp=current_time,
                unlock_timestamp=unlock_timestamp,
                last_earnings_claim=current_time,
            )

            # Store deposit
            self._deposits[deposit_id] = deposit
            if user_id not in self._user_deposits:
                self._user_deposits[user_id] = []
            self._user_deposits[user_id].append(deposit_id)

            # Track staking / timelock metadata
            if stake_days > 0:
                self._staked_deposits[deposit_id] = {
                    "stake_days": stake_days,
                    "stake_start": current_time,
                    "stake_unlock": current_time + stake_days * 86400,
                }
            if timelock_until > current_time:
                self._timelock_deposits[deposit_id] = {
                    "lock_until": timelock_until,
                    "set_at": current_time,
                }

            # Update pool totals
            self._total_pool_value += net_deposit

            # Process referral if provided
            if referral_code:
                self._process_referral(user_id, referral_code, net_deposit)

            logger.info(
                "Deposit created: user=%s, amount=$%.2f, tier=%s, "
                "staked=%dd, unlock=%d",
                user_id, float(net_deposit), tier.value,
                stake_days, unlock_timestamp,
            )

            return deposit

    def withdraw_earnings(
        self, user_id: str, force_early: bool = False,
    ) -> Decimal:
        """
        Withdraw accumulated earnings.

        Standard withdrawal: free, but requires 72-hour cooldown between
        withdrawals and a $15 minimum balance.

        Early withdrawal: available anytime but incurs a 25% penalty fee.
        The penalty goes to the on-chain reserve fund.

        Args:
            user_id: User identifier
            force_early: If True, bypass cooldown but apply 25% penalty

        Returns:
            Net amount withdrawn (after any penalty)

        Raises:
            ValueError: If withdrawal requirements not met
        """
        with self._lock:
            if self._is_paused:
                raise ValueError("Withdrawals are currently paused")

            current_time = int(time.time())
            last_withdrawal = self._user_last_earnings_withdrawal.get(user_id, 0)
            cooldown_remaining = (last_withdrawal + EARNINGS_WITHDRAWAL_COOLDOWN) - current_time

            earnings = self._user_earnings.get(user_id, Decimal("0"))
            if earnings < MINIMUM_WITHDRAWAL_USD:
                raise ValueError(
                    f"Minimum withdrawal is ${MINIMUM_WITHDRAWAL_USD}. "
                    f"Current balance: ${earnings}"
                )

            penalty = Decimal("0")
            if cooldown_remaining > 0 and not force_early:
                hours_left = cooldown_remaining / 3600
                raise ValueError(
                    f"Withdrawal cooldown active. {hours_left:.1f} hours remaining. "
                    f"Use force_early=True to withdraw now with a "
                    f"{int(EARLY_WITHDRAWAL_PENALTY_PCT * 100)}% penalty."
                )

            if cooldown_remaining > 0 and force_early:
                # Apply 25% early withdrawal penalty
                penalty = earnings * EARLY_WITHDRAWAL_PENALTY_PCT
                # Penalty goes to on-chain reserve fund
                self._reserve_balance += penalty
                self._total_reserve_allocated += penalty
                logger.info(
                    "Early withdrawal penalty: user=%s, penalty=$%.2f -> reserve",
                    user_id, float(penalty),
                )

            net_withdrawal = earnings - penalty

            # Update state
            self._user_earnings[user_id] = Decimal("0")
            self._user_last_earnings_withdrawal[user_id] = current_time

            logger.info(
                "Earnings withdrawn: user=%s, gross=$%.2f, penalty=$%.2f, net=$%.2f",
                user_id, float(earnings), float(penalty), float(net_withdrawal),
            )

            return net_withdrawal

    def withdraw_deposit(
        self, user_id: str, deposit_id: str, force_early: bool = False,
    ) -> Decimal:
        """
        Withdraw initial deposit.

        If the lock/stake/timelock period has ended, withdrawal is free.
        If still locked and force_early=True, a 25% penalty applies.
        The penalty goes to the on-chain reserve fund.

        Args:
            user_id: User identifier
            deposit_id: Deposit identifier
            force_early: If True, allow withdrawal before unlock with 25% penalty

        Returns:
            Net amount withdrawn

        Raises:
            ValueError: If withdrawal requirements not met
        """
        with self._lock:
            if self._is_paused:
                raise ValueError("Withdrawals are currently paused")

            if deposit_id not in self._deposits:
                raise ValueError("Deposit not found")

            deposit = self._deposits[deposit_id]
            if deposit.user_id != user_id:
                raise ValueError("Deposit does not belong to user")
            if not deposit.is_active:
                raise ValueError("Deposit is not active")

            current_time = int(time.time())
            is_locked = current_time < deposit.unlock_timestamp

            if is_locked and not force_early:
                remaining = deposit.unlock_timestamp - current_time
                hours_left = remaining / 3600
                raise ValueError(
                    f"Deposit locked for {hours_left:.1f} more hours. "
                    f"Use force_early=True to withdraw now with a "
                    f"{int(EARLY_WITHDRAWAL_PENALTY_PCT * 100)}% penalty."
                )

            amount = deposit.amount
            if amount < MINIMUM_WITHDRAWAL_USD:
                raise ValueError(
                    f"Minimum withdrawal is ${MINIMUM_WITHDRAWAL_USD}. "
                    f"Deposit value: ${amount}"
                )

            penalty = Decimal("0")
            if is_locked and force_early:
                penalty = amount * EARLY_WITHDRAWAL_PENALTY_PCT
                self._reserve_balance += penalty
                self._total_reserve_allocated += penalty
                logger.info(
                    "Early deposit withdrawal penalty: user=%s, deposit=%s, "
                    "penalty=$%.2f -> reserve",
                    user_id, deposit_id, float(penalty),
                )

            net_withdrawal = amount - penalty

            # Claim remaining earnings for this deposit
            if deposit.accumulated_earnings > 0:
                self._user_earnings[user_id] = self._user_earnings.get(
                    user_id, Decimal("0")
                ) + deposit.accumulated_earnings
                deposit.accumulated_earnings = Decimal("0")

            # Update state
            deposit.is_active = False
            self._total_pool_value -= amount

            # Clean up staking/timelock metadata
            self._staked_deposits.pop(deposit_id, None)
            self._timelock_deposits.pop(deposit_id, None)

            logger.info(
                "Deposit withdrawn: user=%s, deposit=%s, gross=$%.2f, "
                "penalty=$%.2f, net=$%.2f",
                user_id, deposit_id, float(amount),
                float(penalty), float(net_withdrawal),
            )

            return net_withdrawal

    def reinvest_deposit(
        self,
        user_id: str,
        deposit_id: str,
        additional_amount: Decimal,
        new_tier: DepositTier,
    ) -> UserDeposit:
        """
        Reinvest deposit after lock period for bonus yield.

        Args:
            user_id: User identifier
            deposit_id: Original deposit identifier
            additional_amount: Additional funds to add
            new_tier: Tier for new deposit period

        Returns:
            Updated UserDeposit record

        Raises:
            ValueError: If reinvestment requirements not met
        """
        with self._lock:
            if self._is_paused:
                raise ValueError("Reinvestments are currently paused")

            if deposit_id not in self._deposits:
                raise ValueError("Deposit not found")

            deposit = self._deposits[deposit_id]
            if deposit.user_id != user_id:
                raise ValueError("Deposit does not belong to user")
            if not deposit.is_active:
                raise ValueError("Deposit is not active")

            current_time = int(time.time())
            if current_time < deposit.unlock_timestamp:
                raise ValueError("Deposit still locked")

            tier_config = self.tier_configs.get(new_tier)
            if not tier_config or not tier_config.is_active:
                raise ValueError(f"Tier {new_tier.value} is not active")

            # Calculate reinvestment bonus
            original_amount = deposit.amount
            bonus_amount = (original_amount * REINVESTMENT_BONUS_BPS) / BPS_DENOMINATOR
            new_total = original_amount + bonus_amount + additional_amount

            # Validate new total against tier limits
            if new_total < tier_config.min_deposit_usd:
                raise ValueError(
                    f"New total ${new_total} below tier minimum ${tier_config.min_deposit_usd}"
                )
            if new_total > tier_config.max_deposit_usd:
                raise ValueError(
                    f"New total ${new_total} exceeds tier maximum ${tier_config.max_deposit_usd}"
                )

            # Claim remaining earnings before reinvestment
            if deposit.accumulated_earnings > 0:
                self._user_earnings[user_id] = self._user_earnings.get(
                    user_id, Decimal("0")
                ) + deposit.accumulated_earnings
                deposit.accumulated_earnings = Decimal("0")

            # Update deposit
            unlock_timestamp = current_time + tier_config.get_lock_period_seconds()
            deposit.amount = new_total
            deposit.tier = new_tier
            deposit.deposit_timestamp = current_time
            deposit.unlock_timestamp = unlock_timestamp
            deposit.last_earnings_claim = current_time
            deposit.reinvestment_count += 1

            # Update pool totals
            net_increase = bonus_amount + additional_amount
            self._total_pool_value += net_increase

            logger.info(
                "Deposit reinvested: user=%s, original=$%.2f, bonus=$%.2f, "
                "additional=$%.2f, new_total=$%.2f, new_tier=%s",
                user_id,
                float(original_amount),
                float(bonus_amount),
                float(additional_amount),
                float(new_total),
                new_tier.value,
            )

            return deposit

    # ==========================================================================
    # REFERRAL FUNCTIONS
    # ==========================================================================

    def generate_referral_code(self, user_id: str) -> str:
        """
        Generate a unique referral code for a user.

        Args:
            user_id: User identifier

        Returns:
            Generated referral code

        Raises:
            ValueError: If user already has code or no active deposits
        """
        with self._lock:
            if user_id in self._user_referrals:
                return self._user_referrals[user_id]

            # Verify user has active deposits
            user_deposit_ids = self._user_deposits.get(user_id, [])
            has_active = any(
                self._deposits[did].is_active
                for did in user_deposit_ids
                if did in self._deposits
            )
            if not has_active:
                raise ValueError("Must have active deposit to generate referral code")

            # Generate unique code
            code = self._generate_referral_code()
            self._referral_codes[code] = user_id
            self._user_referrals[user_id] = code

            logger.info("Referral code generated: user=%s, code=%s", user_id, code)

            return code

    def _process_referral(
        self, referred_user: str, referral_code: str, deposit_amount: Decimal
    ) -> None:
        """
        Process referral bonus when new user deposits with code.

        Simple flat-rate referral system:
        - $1 per successful referral (when the referred user deposits)
        - Normal users: Capped at $2000 total lifetime referral earnings
        - Team affiliate leaders: Same $1 per referral, but capped at $100,000 lifetime

        A "successful referral" means the referred user made their first deposit.
        The bonus is paid from the reserve account (funded by 10% of trade profits).
        """
        referrer_id = self._referral_codes.get(referral_code)
        if not referrer_id or referrer_id == referred_user:
            return

        # Check if this referred user has already deposited (no double-counting)
        if referred_user in self._referred_users_with_first_deposit:
            logger.debug(
                "Referral bonus skipped: user %s already deposited before",
                referred_user,
            )
            return

        # Check lifetime cap based on affiliate status
        is_affiliate_leader = referrer_id in self._team_affiliate_leaders
        current_earnings = self._referral_earnings.get(referrer_id, Decimal("0"))
        
        # Determine the cap: $100,000 for affiliate leaders, $2000 for normal users
        lifetime_cap = AFFILIATE_LEADER_LIFETIME_CAP_USD if is_affiliate_leader else REFERRAL_LIFETIME_CAP_USD
        
        if current_earnings >= lifetime_cap:
            logger.info(
                "Referral bonus skipped: referrer %s has reached $%.2f lifetime cap",
                referrer_id,
                float(lifetime_cap),
            )
            return
        
        # Everyone gets $1 per referral
        referrer_bonus = REFERRAL_BONUS_USD

        # Check if we have enough in reserve to pay the bonus
        if self._reserve_balance < referrer_bonus:
            logger.warning(
                "Referral bonus reduced: reserve balance $%.2f < bonus $%.2f",
                float(self._reserve_balance),
                float(referrer_bonus),
            )
            referrer_bonus = self._reserve_balance  # Pay what we can

        if referrer_bonus <= 0:
            logger.warning("Referral bonus skipped: insufficient reserve balance")
            return

        # Deduct from reserve and credit to referrer
        self._reserve_balance -= referrer_bonus
        self._user_earnings[referrer_id] = self._user_earnings.get(
            referrer_id, Decimal("0")
        ) + referrer_bonus

        # Track referral earnings
        self._referral_earnings[referrer_id] = self._referral_earnings.get(
            referrer_id, Decimal("0")
        ) + referrer_bonus

        # Increment referral count
        self._referral_counts[referrer_id] = self._referral_counts.get(referrer_id, 0) + 1

        # Mark that this user has deposited (for referral tracking)
        self._referred_users_with_first_deposit.add(referred_user)

        # Track the referral relationship
        self._user_referrals[referred_user] = referral_code

        logger.info(
            "Referral bonus processed: referrer=%s%s, referred=%s, "
            "bonus=$%.2f, total_referrals=%d, lifetime_earnings=$%.2f, cap=$%.2f",
            referrer_id,
            " (AFFILIATE)" if is_affiliate_leader else "",
            referred_user,
            float(referrer_bonus),
            self._referral_counts[referrer_id],
            float(self._referral_earnings[referrer_id]),
            float(lifetime_cap),
        )

    def set_team_affiliate_leader(self, user_id: str, is_leader: bool = True) -> None:
        """
        Set or remove a user's team affiliate leader status.

        Team affiliate leaders still earn $1 per successful referral (same as everyone),
        but have a higher lifetime cap of $100,000 instead of $2,000.

        Args:
            user_id: User identifier
            is_leader: True to grant affiliate leader status, False to revoke
        """
        with self._lock:
            if is_leader:
                self._team_affiliate_leaders.add(user_id)
                logger.info("User %s granted team affiliate leader status (cap: $100,000)", user_id)
            else:
                self._team_affiliate_leaders.discard(user_id)
                logger.info("User %s revoked team affiliate leader status (cap: $2,000)", user_id)

    def is_team_affiliate_leader(self, user_id: str) -> bool:
        """Check if user is a team affiliate leader."""
        with self._lock:
            return user_id in self._team_affiliate_leaders

    def get_referral_count(self, user_id: str) -> int:
        """Get the number of successful referrals for a user."""
        with self._lock:
            return self._referral_counts.get(user_id, 0)

    # ==========================================================================
    # TRADING FUNCTIONS
    # ==========================================================================

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
        Execute a trade through an approved DEX protocol.

        Args:
            chain_id: Blockchain chain ID
            dex_name: DEX protocol name
            token_in: Input token address
            token_out: Output token address
            amount_in: Amount to swap
            min_amount_out: Minimum output (slippage protection)

        Returns:
            PooledTrade record

        Raises:
            ValueError: If trade parameters are invalid
        """
        with self._lock:
            if self._is_paused:
                raise ValueError("Trading is currently paused")

            # Validate chain
            chain = SUPPORTED_CHAINS.get(chain_id)
            if not chain or not chain.is_active:
                raise ValueError(f"Chain {chain_id} not supported")

            # Validate DEX
            dex = SUPPORTED_DEXES.get(dex_name)
            if not dex or not dex.is_active:
                raise ValueError(f"DEX {dex_name} not supported")
            if chain_id not in dex.chain_ids:
                raise ValueError(f"DEX {dex_name} not available on chain {chain_id}")

            # Create trade record
            trade_id = self._generate_trade_id()
            current_time = int(time.time())

            # NOTE: In production, this would execute on-chain via Web3
            # For now, we create the trade record for tracking
            trade = PooledTrade(
                trade_id=trade_id,
                chain_id=chain_id,
                chain_layer=chain.layer,
                dex_protocol=dex_name,
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_in,
                amount_out=Decimal("0"),  # Set after execution
                profit=Decimal("0"),
                owner_fee=Decimal("0"),
                user_profit_share=Decimal("0"),
                status=TradeStatus.PENDING,
                timestamp=current_time,
            )

            self._trades.append(trade)
            self._total_trades_executed += 1

            logger.info(
                "Trade initiated: id=%s, chain=%s, dex=%s, %s->%s, amount=$%.2f",
                trade_id,
                chain.chain_name,
                dex_name,
                token_in,
                token_out,
                float(amount_in),
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
        Record completion of a trade and calculate profit distribution.

        Profit split (70/20/10):
        - 70% to members (compounded to their deposited principal)
        - 20% to owners
        - 10% to reserve account (for referral bonuses and emergencies)

        Args:
            trade_id: Trade identifier
            amount_out: Actual output amount
            tx_hash: Transaction hash
            gas_used: Gas used

        Returns:
            Updated PooledTrade record
        """
        with self._lock:
            # Find the trade
            trade = None
            for t in self._trades:
                if t.trade_id == trade_id:
                    trade = t
                    break

            if not trade:
                raise ValueError(f"Trade {trade_id} not found")

            # Calculate profit
            profit = amount_out - trade.amount_in
            if profit > 0:
                # Apply 70/20/10 split
                owner_fee = profit * OWNER_PROFIT_SHARE_PCT  # 20% to owners
                reserve_allocation = profit * RESERVE_PROFIT_SHARE_PCT  # 10% to reserve
                user_profit_share = profit * MEMBER_PROFIT_SHARE_PCT  # 70% to members
            else:
                # Losses are absorbed proportionally (no reserve allocation on losses)
                owner_fee = Decimal("0")
                reserve_allocation = Decimal("0")
                user_profit_share = profit  # Full loss passed to pool

            # Update trade record
            trade.amount_out = amount_out
            trade.profit = profit
            trade.owner_fee = owner_fee
            trade.user_profit_share = user_profit_share
            trade.tx_hash = tx_hash
            trade.gas_used = gas_used
            trade.status = TradeStatus.COMPLETED

            # Update pool metrics
            self._owner_accumulated_fees += owner_fee
            self._undistributed_profits += user_profit_share
            self._reserve_balance += reserve_allocation
            self._total_reserve_allocated += reserve_allocation

            logger.info(
                "Trade completed: id=%s, out=$%.2f, profit=$%.2f, "
                "owner_fee=$%.2f (20%%), reserve=$%.2f (10%%), user_share=$%.2f (70%%)",
                trade_id,
                float(amount_out),
                float(profit),
                float(owner_fee),
                float(reserve_allocation),
                float(user_profit_share),
            )

            return trade

    def distribute_profits(self) -> ProfitDistribution:
        """
        Distribute accumulated profits to depositors with compounding.

        This method distributes the 70% member share of trade profits
        by compounding it to user's principal (deposit.amount), not just
        to accumulated_earnings. This enables true compound growth.

        Returns:
            ProfitDistribution record
        """
        with self._lock:
            current_time = int(time.time())

            if self._undistributed_profits <= 0:
                raise ValueError("No profits to distribute")

            if self._total_pool_value <= 0:
                raise ValueError("No deposits in pool")

            profits_to_distribute = self._undistributed_profits
            self._undistributed_profits = Decimal("0")

            # Track total compounded to pool
            total_compounded = Decimal("0")

            # Distribute proportionally to each active deposit and compound
            distribution_count = 0
            for deposit_id, deposit in self._deposits.items():
                if not deposit.is_active:
                    continue

                # Calculate share based on deposit proportion and tier yield
                tier_config = self.tier_configs[deposit.tier]
                deposit_share = deposit.amount / self._total_pool_value
                tier_multiplier = tier_config.yield_bps / Decimal("1000")  # Normalize

                earnings = profits_to_distribute * deposit_share * tier_multiplier

                # COMPOUND: Add earnings to principal (deposit.amount) not just earnings
                # This enables compound growth on future distributions
                deposit.amount += earnings
                deposit.accumulated_earnings += earnings  # Track total earned for records
                total_compounded += earnings
                distribution_count += 1

            # Update total pool value to reflect compounding
            self._total_pool_value += total_compounded

            # Create distribution record
            distribution_id = self._generate_distribution_id()
            distribution = ProfitDistribution(
                distribution_id=distribution_id,
                timestamp=current_time,
                total_profits=profits_to_distribute,
                owner_fees=Decimal("0"),  # Already deducted at trade level (20%)
                user_share=profits_to_distribute,  # 70% member share
                reserve_share=Decimal("0"),  # Reserve allocated at trade level (10%)
                total_pool_value=self._total_pool_value,
                distribution_count=distribution_count,
            )

            self._profit_distributions.append(distribution)
            self._total_profits_distributed += profits_to_distribute
            self._last_profit_distribution = current_time

            logger.info(
                "Profits distributed (compounded): amount=$%.2f, recipients=%d, "
                "pool_value=$%.2f, total_compounded=$%.2f",
                float(profits_to_distribute),
                distribution_count,
                float(self._total_pool_value),
                float(total_compounded),
            )

            return distribution

    # ==========================================================================
    # QUERY FUNCTIONS
    # ==========================================================================

    def get_user_deposits(self, user_id: str) -> List[UserDeposit]:
        """Get all deposits for a user."""
        with self._lock:
            deposit_ids = self._user_deposits.get(user_id, [])
            return [
                self._deposits[did]
                for did in deposit_ids
                if did in self._deposits
            ]

    def get_user_earnings(self, user_id: str) -> Decimal:
        """Get user's current claimable earnings."""
        with self._lock:
            return self._user_earnings.get(user_id, Decimal("0"))

    def get_reserve_balance(self) -> Decimal:
        """
        Get current reserve account balance.

        The reserve is funded by 10% of trade profits and used for:
        - Referral bonuses ($1 per successful referral for everyone)
        - Emergency/rainy day fund
        """
        with self._lock:
            return self._reserve_balance

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get overall pool statistics."""
        with self._lock:
            return {
                "total_pool_value": float(self._total_pool_value),
                "undistributed_profits": float(self._undistributed_profits),
                "owner_accumulated_fees": float(self._owner_accumulated_fees),
                "reserve_balance": float(self._reserve_balance),
                "total_reserve_allocated": float(self._total_reserve_allocated),
                "rainy_day_fund": float(self._rainy_day_fund),
                "total_membership_fees_collected": float(
                    self._total_membership_fees_collected
                ),
                "total_members": len(self._membership_paid),
                "total_trades_executed": self._total_trades_executed,
                "total_profits_distributed": float(self._total_profits_distributed),
                "total_deposits": len(self._deposits),
                "active_deposits": sum(
                    1 for d in self._deposits.values() if d.is_active
                ),
                "staked_deposits": len(self._staked_deposits),
                "timelocked_deposits": len(self._timelock_deposits),
                "total_users": len(self._user_deposits),
                "total_referral_bonuses_paid": float(
                    sum(self._referral_earnings.values())
                ),
                "total_successful_referrals": sum(self._referral_counts.values()),
                "team_affiliate_leaders": len(self._team_affiliate_leaders),
                "supported_chains": len(SUPPORTED_CHAINS),
                "supported_dexes": len(SUPPORTED_DEXES),
                "is_active": self._is_active,
                "is_paused": self._is_paused,
                "profit_split": {
                    "member_pct": float(MEMBER_PROFIT_SHARE_PCT) * 100,
                    "owner_pct": float(OWNER_PROFIT_SHARE_PCT) * 100,
                    "reserve_pct": float(RESERVE_PROFIT_SHARE_PCT) * 100,
                },
                "withdrawal_rules": {
                    "minimum_usd": float(MINIMUM_WITHDRAWAL_USD),
                    "cooldown_hours": EARNINGS_WITHDRAWAL_COOLDOWN / 3600,
                    "early_penalty_pct": float(EARLY_WITHDRAWAL_PENALTY_PCT) * 100,
                },
                "membership_fee_usd": float(MEMBERSHIP_FEE_USD),
                "referral_config": {
                    "bonus_per_referral_usd": float(REFERRAL_BONUS_USD),
                    "normal_user_lifetime_cap_usd": float(REFERRAL_LIFETIME_CAP_USD),
                    "affiliate_leader_lifetime_cap_usd": float(AFFILIATE_LEADER_LIFETIME_CAP_USD),
                },
            }

    def get_rainy_day_balance(self) -> Decimal:
        """Get current rainy-day fund balance (off-books, owner-controlled)."""
        return self._rainy_day_fund

    def get_membership_status(self, user_id: str) -> Dict[str, Any]:
        """Get membership status for a user."""
        is_member = user_id in self._membership_paid
        info = self._members.get(user_id, {})
        return {
            "is_member": is_member,
            "membership_fee_paid": is_member,
            "joined": info.get("joined"),
            "fee_amount": float(MEMBERSHIP_FEE_USD) if is_member else 0,
        }

    def get_staking_info(self, deposit_id: str) -> Optional[Dict]:
        """Get staking info for a deposit, or None if not staked."""
        return self._staked_deposits.get(deposit_id)

    def get_timelock_info(self, deposit_id: str) -> Optional[Dict]:
        """Get timelock info for a deposit, or None if not locked."""
        return self._timelock_deposits.get(deposit_id)

    def get_tier_config(self, tier: DepositTier) -> TierConfig:
        """Get configuration for a specific tier."""
        config = self.tier_configs.get(tier)
        if not config:
            raise ValueError(f"Unknown tier: {tier}")
        return config

    def get_supported_chains(self) -> List[SupportedChain]:
        """Get list of supported chains."""
        return list(SUPPORTED_CHAINS.values())

    def get_supported_dexes(self) -> List[DEXConfig]:
        """Get list of supported DEXs."""
        return list(SUPPORTED_DEXES.values())

    def get_chain_by_layer(self, layer: ChainLayer) -> List[SupportedChain]:
        """Get chains filtered by layer."""
        return [
            chain for chain in SUPPORTED_CHAINS.values()
            if chain.layer == layer and chain.is_active
        ]

    # ==========================================================================
    # ADMIN FUNCTIONS
    # ==========================================================================

    def withdraw_owner_fees(self) -> Decimal:
        """
        Withdraw accumulated owner fees.

        Returns:
            Amount withdrawn
        """
        with self._lock:
            fees = self._owner_accumulated_fees
            if fees <= 0:
                raise ValueError("No fees to withdraw")

            self._owner_accumulated_fees = Decimal("0")

            logger.info("Owner fees withdrawn: $%.2f", float(fees))

            return fees

    def update_tier_config(
        self,
        tier: DepositTier,
        yield_bps: Optional[Decimal] = None,
        min_deposit: Optional[Decimal] = None,
        max_deposit: Optional[Decimal] = None,
        is_active: Optional[bool] = None,
    ) -> TierConfig:
        """Update tier configuration."""
        with self._lock:
            config = self.tier_configs.get(tier)
            if not config:
                raise ValueError(f"Unknown tier: {tier}")

            if yield_bps is not None:
                if yield_bps > Decimal("5000"):  # Max 50% APY
                    raise ValueError("Yield too high")
                config.yield_bps = yield_bps

            if min_deposit is not None:
                if min_deposit < MINIMUM_DEPOSIT_USD:
                    raise ValueError("Min deposit too low")
                config.min_deposit_usd = min_deposit

            if max_deposit is not None:
                if max_deposit <= config.min_deposit_usd:
                    raise ValueError("Max must exceed min")
                config.max_deposit_usd = max_deposit

            if is_active is not None:
                config.is_active = is_active

            logger.info(
                "Tier config updated: %s, yield=%s bps, min=$%.2f, max=$%.2f",
                tier.value,
                config.yield_bps,
                float(config.min_deposit_usd),
                float(config.max_deposit_usd),
            )

            return config

    def set_paused(self, paused: bool) -> None:
        """Set paused state."""
        with self._lock:
            self._is_paused = paused
            logger.info("Paused state set to: %s", paused)

    # ==========================================================================
    # HELPER FUNCTIONS
    # ==========================================================================

    def _generate_deposit_id(self, user_id: str, timestamp: int) -> str:
        """Generate unique deposit ID."""
        data = f"{user_id}:{timestamp}:{secrets.token_hex(8)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _generate_trade_id(self) -> str:
        """Generate unique trade ID."""
        return f"T{secrets.token_hex(8).upper()}"

    def _generate_distribution_id(self) -> str:
        """Generate unique distribution ID."""
        return f"D{secrets.token_hex(8).upper()}"

    def _generate_referral_code(self) -> str:
        """Generate unique referral code."""
        return f"VEL-{secrets.token_hex(4).upper()}"


# ==============================================================================
# FACTORY FUNCTION
# ==============================================================================

def create_pooled_trading_engine(
    tier_configs: Optional[Dict[DepositTier, TierConfig]] = None,
    private_key: Optional[str] = None,
) -> PooledTradingEngine:
    """
    Factory function to create a pooled trading engine.

    Args:
        tier_configs: Custom tier configurations
        private_key: Private key for signing transactions

    Returns:
        Configured PooledTradingEngine instance
    """
    return PooledTradingEngine(
        tier_configs=tier_configs,
        private_key=private_key,
    )


# ==============================================================================
# MODULE EXPORTS
# ==============================================================================

__all__ = [
    "PooledTradingEngine",
    "create_pooled_trading_engine",
    "DepositTier",
    "ChainLayer",
    "TradeStatus",
    "WithdrawalStatus",
    "TierConfig",
    "UserDeposit",
    "PooledTrade",
    "ProfitDistribution",
    "SupportedChain",
    "DEXConfig",
    "DEFAULT_TIER_CONFIGS",
    "SUPPORTED_CHAINS",
    "SUPPORTED_DEXES",
    "MINIMUM_DEPOSIT_USD",
    "MINIMUM_WITHDRAWAL_USD",
    "MAXIMUM_DEPOSIT_USD",
    "BASE_YIELD_BPS",
    "GRADUATED_BONUS_TIERS",
    "calculate_effective_yield_bps",
    "get_deposit_tier_info",
]
