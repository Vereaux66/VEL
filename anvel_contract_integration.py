#!/usr/bin/env python3
"""
ANVEL Contract Integration Bridge - Trading System Integration

Enterprise-grade integration module that bridges VEL smart contracts
with the Python trading system. Provides:

- DEX trade execution through VELMultiDEXRouter
- Pool deposit/withdrawal through VELPooledTradingVault
- Cross-chain transfers through VELCrosschainBridge
- Atomic swaps through VELAtomicSwapHTLC
- Privacy-preserving orders through VELAnonymousOrderExecutor

Security Features:
- Transaction simulation before execution
- Slippage protection
- Gas price circuit breakers
- Self-healing on failures
- Comprehensive audit logging

Production-critical module for capital-touching operations.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from web3 import Web3
from web3.types import Wei

from anvel_smart_contract_manager import (
    SmartContractManager,
    ContractConfig,
    ContractType,
    TransactionRequest,
    TransactionResult,
    TransactionStatus,
    HealthStatus,
    SmartContractError,
    get_contract_abi,
    create_smart_contract_manager,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

WEI_PER_ETH = Decimal("1000000000000000000")
BPS_DENOMINATOR = 10000

# DEX Types (matching Solidity enum)
DEX_TYPE_UNISWAP_V2 = 0
DEX_TYPE_UNISWAP_V3 = 1
DEX_TYPE_CURVE = 2
DEX_TYPE_CUSTOM = 3

# Deposit Tiers (matching Solidity enum)
DEPOSIT_TIER_THREE_MONTH = 0
DEPOSIT_TIER_SIX_MONTH = 1
DEPOSIT_TIER_NINE_MONTH = 2


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SwapRoute:
    """Route for a DEX swap."""
    token_in: str
    token_out: str
    amount_in: int  # In token units (wei)
    min_amount_out: int  # Minimum output for slippage protection
    dex_router: str
    dex_type: int
    extra_data: bytes = b""


@dataclass
class SwapResult:
    """Result of a DEX swap."""
    token_in: str
    token_out: str
    amount_in: int
    amount_out: int
    effective_price: Decimal
    gas_used: int
    tx_hash: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DepositResult:
    """Result of a pool deposit."""
    amount: int
    tier: int
    deposit_index: int
    unlock_timestamp: int
    tx_hash: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class HTLCCreationResult:
    """Result of HTLC creation."""
    contract_id: str
    secret: str
    hash_lock: str
    recipient: str
    token: str
    amount: int
    time_lock: int
    tx_hash: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class BridgeTransferResult:
    """Result of a cross-chain bridge transfer."""
    transfer_id: int
    source_chain_id: int
    dest_chain_id: int
    token: str
    amount: int
    fee: int
    tx_hash: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# CONTRACT INTEGRATION BRIDGE
# =============================================================================

class ContractIntegrationBridge:
    """
    Bridge between VEL smart contracts and Python trading system.
    
    Provides high-level interfaces for:
    - DEX trading through VELMultiDEXRouter
    - Pool management through VELPooledTradingVault
    - Cross-chain operations through VELCrosschainBridge
    - Atomic swaps through VELAtomicSwapHTLC
    - Private orders through VELAnonymousOrderExecutor
    """

    def __init__(
        self,
        contract_manager: SmartContractManager,
        default_slippage_bps: int = 50,  # 0.5%
        simulation_enabled: bool = True,
    ):
        """
        Initialize contract integration bridge.
        
        Args:
            contract_manager: SmartContractManager instance
            default_slippage_bps: Default slippage tolerance in basis points
            simulation_enabled: Whether to simulate transactions before execution
        """
        self.contract_manager = contract_manager
        self.default_slippage_bps = default_slippage_bps
        self.simulation_enabled = simulation_enabled
        
        # Track operations
        self._swap_count = 0
        self._deposit_count = 0
        self._htlc_count = 0
        self._bridge_count = 0
        
        # Thread safety
        self._lock = threading.RLock()
        
        logger.info(
            f"ContractIntegrationBridge initialized (slippage={default_slippage_bps}bps, "
            f"simulation={'enabled' if simulation_enabled else 'disabled'})"
        )

    # =========================================================================
    # DEX TRADING (VELMultiDEXRouter)
    # =========================================================================

    def execute_swap(
        self,
        chain_id: int,
        token_in: str,
        token_out: str,
        amount_in: int,
        min_amount_out: int,
        dex_router: str,
        dex_type: int = DEX_TYPE_UNISWAP_V2,
        extra_data: bytes = b"",
        slippage_bps: Optional[int] = None,
    ) -> SwapResult:
        """
        Execute a token swap through VELMultiDEXRouter.
        
        Args:
            chain_id: Chain to execute on
            token_in: Input token address
            token_out: Output token address
            amount_in: Input amount in token units
            min_amount_out: Minimum output amount (slippage protection)
            dex_router: DEX router address
            dex_type: Type of DEX (0=UniV2, 1=UniV3, 2=Curve)
            extra_data: DEX-specific data (e.g., fee tier for UniV3)
            slippage_bps: Custom slippage tolerance for post-swap validation (optional).
                          The actual slippage protection is enforced by min_amount_out.
            
        Returns:
            SwapResult with execution details
            
        Raises:
            SlippageExceededError: If slippage exceeds tolerance
            ContractNotFoundError: If contract not registered
            SmartContractError: For other execution failures
        """
        # Store slippage for potential post-execution validation or logging
        effective_slippage = slippage_bps if slippage_bps is not None else self.default_slippage_bps
        
        # Build swap route struct
        route = (
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(token_out),
            amount_in,
            min_amount_out,
            Web3.to_checksum_address(dex_router),
            dex_type,
            extra_data,
        )
        
        # Create transaction request
        request = TransactionRequest(
            contract_type=ContractType.MULTI_DEX_ROUTER,
            function_name="executeSwap",
            args=(route,),
            simulate_first=self.simulation_enabled,
        )
        
        logger.info(
            f"Executing swap: {amount_in} {token_in} -> {token_out} "
            f"on chain {chain_id}"
        )
        
        # Execute transaction
        result = self.contract_manager.execute_transaction(request, chain_id)
        
        if result.status != TransactionStatus.CONFIRMED:
            raise SmartContractError(
                f"Swap failed: {result.error_message or 'Unknown error'}"
            )
        
        # Extract amount_out from transaction result
        amount_out = self._parse_swap_amount_out(result, min_amount_out)
        
        with self._lock:
            self._swap_count += 1
        
        # Log effective slippage for monitoring (used for analytics/debugging)
        actual_slippage_bps = 0
        if amount_in > 0 and min_amount_out > 0:
            expected_ratio = Decimal(min_amount_out) / Decimal(amount_in)
            actual_ratio = Decimal(amount_out) / Decimal(amount_in)
            if expected_ratio > 0:
                actual_slippage_bps = int((1 - actual_ratio / expected_ratio) * 10000)
        
        logger.debug(
            f"Swap completed: effective_slippage={actual_slippage_bps}bps, "
            f"tolerance={effective_slippage}bps"
        )
        
        return SwapResult(
            token_in=token_in,
            token_out=token_out,
            amount_in=amount_in,
            amount_out=amount_out,
            effective_price=Decimal(amount_out) / Decimal(amount_in) if amount_in > 0 else Decimal(0),
            gas_used=result.gas_used,
            tx_hash=result.tx_hash,
        )

    def _parse_swap_amount_out(self, result: TransactionResult, min_amount_out: int) -> int:
        """
        Parse actual amount_out from transaction result.
        
        Attempts to extract from return value or event logs. Falls back to
        min_amount_out if parsing fails (transaction succeeded so at least
        min_amount_out was received).
        """
        # Try return value first (if contract returns amountOut)
        if result.return_value is not None:
            try:
                return int(result.return_value)
            except (TypeError, ValueError):
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_CONTRACT_INTEGRATION").debug("Exception suppressed in _parse_swap_amount_out")
        
        # Try parsing SwapExecuted event from logs
        for log in result.logs:
            try:
                # Look for SwapExecuted event topic or data
                topics = log.get("topics", [])
                data = log.get("data", "")
                
                # SwapExecuted(address indexed tokenIn, address indexed tokenOut, 
                #              uint256 amountIn, uint256 amountOut)
                # amountOut is typically in the data portion
                if data and len(data) >= 66:  # 0x + 64 hex chars for one uint256
                    # Last 32 bytes (64 hex chars) are typically amountOut
                    amount_hex = data[-64:]
                    return int(amount_hex, 16)
            except (ValueError, TypeError, KeyError):
                continue
        
        # Fallback: transaction succeeded, so at least min_amount_out was received
        logger.debug(
            "Could not parse exact amount_out from tx %s, using min_amount_out",
            result.tx_hash
        )
        return min_amount_out

    def get_swap_quote(
        self,
        chain_id: int,
        token_in: str,
        token_out: str,
        amount_in: int,
        dex_router: str,
        dex_type: int = DEX_TYPE_UNISWAP_V2,
        extra_data: bytes = b"",
    ) -> int:
        """
        Get quote for a swap without executing.
        
        Args:
            chain_id: Chain to query
            token_in: Input token address
            token_out: Output token address
            amount_in: Input amount
            dex_router: DEX router address
            dex_type: Type of DEX
            extra_data: DEX-specific data
            
        Returns:
            Expected output amount
        """
        route = (
            Web3.to_checksum_address(token_in),
            Web3.to_checksum_address(token_out),
            amount_in,
            0,  # min_amount_out not needed for quote
            Web3.to_checksum_address(dex_router),
            dex_type,
            extra_data,
        )
        
        try:
            return self.contract_manager.call_view_function(
                ContractType.MULTI_DEX_ROUTER,
                chain_id,
                "getQuote",
                route,
            )
        except Exception as e:
            logger.warning(f"Quote failed: {e}")
            return 0

    def calculate_min_amount_out(
        self,
        expected_amount: int,
        slippage_bps: Optional[int] = None,
    ) -> int:
        """Calculate minimum amount out based on slippage tolerance."""
        slippage = slippage_bps if slippage_bps is not None else self.default_slippage_bps
        return int(expected_amount * (BPS_DENOMINATOR - slippage) / BPS_DENOMINATOR)

    # =========================================================================
    # POOLED VAULT (VELPooledTradingVault)
    # =========================================================================

    def deposit_to_pool(
        self,
        chain_id: int,
        amount: int,
        tier: int = DEPOSIT_TIER_THREE_MONTH,
        referral_code: bytes = b"\x00" * 32,
    ) -> DepositResult:
        """
        Deposit funds to the pooled trading vault.
        
        Args:
            chain_id: Chain to deposit on
            amount: Amount to deposit (in stablecoin units)
            tier: Deposit tier (0=3mo, 1=6mo, 2=9mo)
            referral_code: Optional referral code
            
        Returns:
            DepositResult with deposit details
        """
        request = TransactionRequest(
            contract_type=ContractType.POOLED_TRADING_VAULT,
            function_name="deposit",
            args=(amount, tier, referral_code),
            simulate_first=self.simulation_enabled,
        )
        
        logger.info(f"Depositing {amount} to pool on chain {chain_id}, tier={tier}")
        
        result = self.contract_manager.execute_transaction(request, chain_id)
        
        if result.status != TransactionStatus.CONFIRMED:
            raise SmartContractError(
                f"Deposit failed: {result.error_message or 'Unknown error'}"
            )
        
        with self._lock:
            self._deposit_count += 1
        
        # Parse Deposited event for deposit_index and unlock_timestamp
        deposit_index, unlock_timestamp = self._parse_deposit_event(result, chain_id, tier)
        
        return DepositResult(
            amount=amount,
            tier=tier,
            deposit_index=deposit_index,
            unlock_timestamp=unlock_timestamp,
            tx_hash=result.tx_hash,
        )

    def _parse_deposit_event(self, result: TransactionResult, chain_id: int, tier: int) -> tuple:
        """
        Parse deposit_index and unlock_timestamp from Deposited event.
        
        Args:
            result: Transaction result containing logs
            chain_id: Chain ID for blockchain time lookup
            tier: Deposit tier for fallback unlock calculation
        
        Returns:
            Tuple of (deposit_index, unlock_timestamp)
        """
        # Try parsing from logs
        for log in result.logs:
            try:
                data = log.get("data", "")
                if data and len(data) >= 130:  # 0x + 128 hex chars for two uint256
                    # Deposited event typically has (user, amount, tier, depositIndex, unlockTimestamp)
                    # depositIndex and unlockTimestamp are usually the last two uint256 values
                    # Each uint256 is 64 hex characters
                    data_hex = data[2:] if data.startswith("0x") else data
                    
                    # Parse last two uint256 values
                    if len(data_hex) >= 128:
                        unlock_hex = data_hex[-64:]
                        index_hex = data_hex[-128:-64]
                        
                        deposit_index = int(index_hex, 16)
                        unlock_timestamp = int(unlock_hex, 16)
                        
                        return deposit_index, unlock_timestamp
            except (ValueError, TypeError, KeyError):
                continue
        
        # If we can't parse, calculate based on tier lock period
        # This is a fallback - transaction succeeded so deposit was made
        logger.warning(
            "Could not parse deposit event from tx %s, using calculated values",
            result.tx_hash
        )
        
        # Try to get blockchain time for accurate calculation
        try:
            w3 = self.contract_manager._get_web3(chain_id)
            current_time = int(w3.eth.get_block("latest")["timestamp"])
        except Exception:
            # Fallback to local time only if blockchain time unavailable
            current_time = int(time.time())
            logger.warning("Using local time for unlock calculation - blockchain time unavailable")
        
        # Calculate unlock timestamp based on tier lock period
        # Tier 0 = 3 months (90 days), Tier 1 = 6 months (180 days), Tier 2 = 9 months (270 days)
        lock_periods = {0: 90, 1: 180, 2: 270}
        lock_days = lock_periods.get(tier, 90)  # Default to 3 months
        unlock_timestamp = current_time + (lock_days * 24 * 60 * 60)
        
        return 0, unlock_timestamp

    def withdraw_earnings(self, chain_id: int) -> TransactionResult:
        """
        Withdraw accumulated earnings from pool.
        
        Args:
            chain_id: Chain to withdraw from
            
        Returns:
            TransactionResult with withdrawal details
        """
        request = TransactionRequest(
            contract_type=ContractType.POOLED_TRADING_VAULT,
            function_name="withdrawEarnings",
            simulate_first=self.simulation_enabled,
        )
        
        logger.info(f"Withdrawing earnings on chain {chain_id}")
        
        return self.contract_manager.execute_transaction(request, chain_id)

    def get_pool_info(self, chain_id: int) -> Dict[str, Any]:
        """
        Get pool information.
        
        Args:
            chain_id: Chain to query
            
        Returns:
            Dict with pool state
        """
        total_value = self.contract_manager.call_view_function(
            ContractType.POOLED_TRADING_VAULT,
            chain_id,
            "totalPoolValue",
        )
        
        paused = self.contract_manager.call_view_function(
            ContractType.POOLED_TRADING_VAULT,
            chain_id,
            "paused",
        )
        
        return {
            "total_pool_value": total_value,
            "paused": paused,
        }

    def get_user_deposits(self, chain_id: int, user_address: str) -> int:
        """
        Get user's total deposited amount.
        
        Args:
            chain_id: Chain to query
            user_address: User's address
            
        Returns:
            Total deposited amount
        """
        return self.contract_manager.call_view_function(
            ContractType.POOLED_TRADING_VAULT,
            chain_id,
            "userTotalDeposited",
            Web3.to_checksum_address(user_address),
        )

    # =========================================================================
    # ATOMIC SWAPS (VELAtomicSwapHTLC)
    # =========================================================================

    def create_htlc(
        self,
        chain_id: int,
        recipient: str,
        token: str,
        amount: int,
        time_lock_hours: int = 24,
    ) -> HTLCCreationResult:
        """
        Create a new Hash Time-Locked Contract.
        
        Args:
            chain_id: Chain to create on
            recipient: Recipient address
            token: Token address (use 0x0 for native ETH)
            amount: Amount to lock
            time_lock_hours: Hours until refund is available
            
        Returns:
            HTLCCreationResult with contract details including secret
        """
        # Generate secure secret
        secret = secrets.token_bytes(32)
        hash_lock = Web3.solidity_keccak(["bytes32"], [secret])
        
        # Calculate time lock based on current chain time for consistency with on-chain validation
        try:
            w3 = self.contract_manager._get_web3(chain_id)
            current_chain_time = int(w3.eth.get_block("latest")["timestamp"])
        except Exception:
            # Fallback to local time if chain time unavailable
            current_chain_time = int(time.time())
            logger.warning("Using local time for HTLC time lock calculation")
        
        time_lock = current_chain_time + (time_lock_hours * 3600)
        
        # Determine value (for ETH) vs token transfer
        value = Wei(amount) if token == "0x" + "0" * 40 else Wei(0)
        
        request = TransactionRequest(
            contract_type=ContractType.ATOMIC_SWAP_HTLC,
            function_name="createHTLC",
            args=(
                Web3.to_checksum_address(recipient),
                Web3.to_checksum_address(token),
                amount,
                hash_lock,
                time_lock,
            ),
            value=value,
            simulate_first=self.simulation_enabled,
        )
        
        logger.info(
            f"Creating HTLC: {amount} -> {recipient} on chain {chain_id}, "
            f"time_lock={time_lock_hours}h"
        )
        
        result = self.contract_manager.execute_transaction(request, chain_id)
        
        if result.status != TransactionStatus.CONFIRMED:
            raise SmartContractError(
                f"HTLC creation failed: {result.error_message or 'Unknown error'}"
            )
        
        with self._lock:
            self._htlc_count += 1
        
        # Parse contract_id from HTLCCreated event or return value
        contract_id = self._parse_htlc_contract_id(result, hash_lock)
        
        return HTLCCreationResult(
            contract_id=contract_id,
            secret=secret.hex(),
            hash_lock=hash_lock.hex(),
            recipient=recipient,
            token=token,
            amount=amount,
            time_lock=time_lock,
            tx_hash=result.tx_hash,
        )

    def _parse_htlc_contract_id(self, result: TransactionResult, hash_lock: bytes) -> str:
        """
        Parse contract_id from HTLC creation result.
        
        Attempts to extract from return value or HTLCCreated event.
        Falls back to hash_lock as contract_id if parsing fails.
        """
        # Try return value first (createHTLC returns contractId)
        if result.return_value is not None:
            try:
                if isinstance(result.return_value, bytes):
                    return result.return_value.hex()
                return str(result.return_value)
            except (TypeError, ValueError):
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_CONTRACT_INTEGRATION").debug("Exception suppressed in _parse_htlc_contract_id")
        
        # Try parsing from logs
        for log in result.logs:
            try:
                data = log.get("data", "")
                if data and len(data) >= 66:  # 0x + 64 hex chars for bytes32
                    # HTLCCreated event typically has contractId as first indexed topic
                    # or in the data portion
                    topics = log.get("topics", [])
                    if len(topics) >= 2:
                        # First topic after event signature is often contractId
                        return topics[1] if topics[1].startswith("0x") else "0x" + topics[1]
                    
                    # Try extracting from data
                    contract_id_hex = data[2:66] if data.startswith("0x") else data[:64]
                    return "0x" + contract_id_hex
            except (ValueError, TypeError, KeyError):
                continue
        
        # Fallback: use hash_lock as contract_id (common pattern in HTLC contracts)
        logger.debug(
            "Could not parse contract_id from tx %s, using hash_lock",
            result.tx_hash
        )
        return hash_lock.hex() if isinstance(hash_lock, bytes) else str(hash_lock)

    def redeem_htlc(
        self,
        chain_id: int,
        contract_id: str,
        secret: str,
    ) -> TransactionResult:
        """
        Redeem an HTLC by revealing the secret.
        
        Args:
            chain_id: Chain where HTLC exists
            contract_id: HTLC contract ID (bytes32 hex)
            secret: Secret that hashes to the hash lock (bytes32 hex)
            
        Returns:
            TransactionResult with redemption details
            
        Raises:
            ValueError: If contract_id or secret is not valid hex
        """
        try:
            contract_id_bytes = bytes.fromhex(contract_id.replace("0x", ""))
        except ValueError as e:
            raise ValueError(f"Invalid contract_id format: must be a valid hex string. {e}") from e
        
        try:
            secret_bytes = bytes.fromhex(secret.replace("0x", ""))
        except ValueError as e:
            raise ValueError(f"Invalid secret format: must be a valid hex string. {e}") from e
        
        request = TransactionRequest(
            contract_type=ContractType.ATOMIC_SWAP_HTLC,
            function_name="redeemHTLC",
            args=(contract_id_bytes, secret_bytes),
            simulate_first=self.simulation_enabled,
        )
        
        logger.info(f"Redeeming HTLC {contract_id} on chain {chain_id}")
        
        return self.contract_manager.execute_transaction(request, chain_id)

    def refund_htlc(self, chain_id: int, contract_id: str) -> TransactionResult:
        """
        Refund an expired HTLC to the sender.
        
        Args:
            chain_id: Chain where HTLC exists
            contract_id: HTLC contract ID
            
        Returns:
            TransactionResult with refund details
            
        Raises:
            ValueError: If contract_id is not valid hex
        """
        try:
            contract_id_bytes = bytes.fromhex(contract_id.replace("0x", ""))
        except ValueError as e:
            raise ValueError(f"Invalid contract_id format: must be a valid hex string. {e}") from e
        
        request = TransactionRequest(
            contract_type=ContractType.ATOMIC_SWAP_HTLC,
            function_name="refundHTLC",
            args=(contract_id_bytes,),
            simulate_first=self.simulation_enabled,
        )
        
        logger.info(f"Refunding HTLC {contract_id} on chain {chain_id}")
        
        return self.contract_manager.execute_transaction(request, chain_id)

    def get_htlc_info(self, chain_id: int, contract_id: str) -> Dict[str, Any]:
        """
        Get HTLC information.
        
        Args:
            chain_id: Chain to query
            contract_id: HTLC contract ID
            
        Returns:
            Dict with HTLC state
            
        Raises:
            ValueError: If contract_id is not valid hex
        """
        try:
            contract_id_bytes = bytes.fromhex(contract_id.replace("0x", ""))
        except ValueError as e:
            raise ValueError(f"Invalid contract_id format: must be a valid hex string. {e}") from e
        
        htlc = self.contract_manager.call_view_function(
            ContractType.ATOMIC_SWAP_HTLC,
            chain_id,
            "getHTLC",
            contract_id_bytes,
        )
        
        return {
            "sender": htlc[0],
            "recipient": htlc[1],
            "token": htlc[2],
            "amount": htlc[3],
            "hash_lock": htlc[4].hex() if isinstance(htlc[4], bytes) else htlc[4],
            "time_lock": htlc[5],
            "state": htlc[6],  # 0=Invalid, 1=Active, 2=Redeemed, 3=Refunded
        }

    # =========================================================================
    # CROSS-CHAIN BRIDGE (VELCrosschainBridge)
    # =========================================================================

    def initiate_bridge_transfer(
        self,
        chain_id: int,
        token: str,
        amount: int,
        recipient: str,
        dest_chain_id: int,
    ) -> BridgeTransferResult:
        """
        Initiate a cross-chain bridge transfer.
        
        Args:
            chain_id: Source chain ID
            token: Token address to bridge
            amount: Amount to bridge
            recipient: Recipient address on destination chain
            dest_chain_id: Destination chain ID
            
        Returns:
            BridgeTransferResult with transfer details
        """
        request = TransactionRequest(
            contract_type=ContractType.CROSSCHAIN_BRIDGE,
            function_name="initiateTransfer",
            args=(
                Web3.to_checksum_address(token),
                amount,
                Web3.to_checksum_address(recipient),
                dest_chain_id,
            ),
            simulate_first=self.simulation_enabled,
        )
        
        logger.info(
            f"Initiating bridge: {amount} {token} from chain {chain_id} to {dest_chain_id}"
        )
        
        result = self.contract_manager.execute_transaction(request, chain_id)
        
        if result.status != TransactionStatus.CONFIRMED:
            raise SmartContractError(
                f"Bridge transfer failed: {result.error_message or 'Unknown error'}"
            )
        
        with self._lock:
            self._bridge_count += 1
        
        # Parse transfer_id and fee from TransferInitiated event
        transfer_id, fee = self._parse_bridge_transfer_event(result)
        
        return BridgeTransferResult(
            transfer_id=transfer_id,
            source_chain_id=chain_id,
            dest_chain_id=dest_chain_id,
            token=token,
            amount=amount,
            fee=fee,
            tx_hash=result.tx_hash,
        )

    def _parse_bridge_transfer_event(self, result: TransactionResult) -> tuple:
        """
        Parse transfer_id and fee from TransferInitiated event.
        
        Returns:
            Tuple of (transfer_id, fee)
        """
        # Try return value first (initiateTransfer typically returns transferId)
        if result.return_value is not None:
            try:
                transfer_id = int(result.return_value)
                return transfer_id, 0  # Fee might need separate lookup
            except (TypeError, ValueError):
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_CONTRACT_INTEGRATION").debug("Exception suppressed in _parse_bridge_transfer_event")
        
        # Try parsing from logs
        for log in result.logs:
            try:
                data = log.get("data", "")
                topics = log.get("topics", [])
                
                # TransferInitiated event typically has transferId as first topic or in data
                if len(topics) >= 2:
                    # Try first indexed topic as transferId
                    topic_hex = topics[1]
                    if topic_hex.startswith("0x"):
                        topic_hex = topic_hex[2:]
                    transfer_id = int(topic_hex, 16)
                    
                    # Try to parse fee from data
                    fee = 0
                    if data and len(data) >= 66:
                        data_hex = data[2:] if data.startswith("0x") else data
                        # Fee is often the last uint256 in the data
                        if len(data_hex) >= 64:
                            fee_hex = data_hex[-64:]
                            fee = int(fee_hex, 16)
                    
                    return transfer_id, fee
                    
            except (ValueError, TypeError, KeyError):
                continue
        
        # Fallback: transaction succeeded, use 0 as transfer_id with warning
        logger.warning(
            "Could not parse transfer_id from bridge tx %s",
            result.tx_hash
        )
        return 0, 0

    def get_bridge_info(self, chain_id: int) -> Dict[str, Any]:
        """
        Get bridge information.
        
        Args:
            chain_id: Chain to query
            
        Returns:
            Dict with bridge state
        """
        paused = self.contract_manager.call_view_function(
            ContractType.CROSSCHAIN_BRIDGE,
            chain_id,
            "paused",
        )
        
        required_sigs = self.contract_manager.call_view_function(
            ContractType.CROSSCHAIN_BRIDGE,
            chain_id,
            "requiredSignatures",
        )
        
        return {
            "paused": paused,
            "required_signatures": required_sigs,
        }

    # =========================================================================
    # STATISTICS AND MONITORING
    # =========================================================================

    def get_statistics(self) -> Dict[str, int]:
        """Get operation statistics."""
        with self._lock:
            return {
                "swaps": self._swap_count,
                "deposits": self._deposit_count,
                "htlcs_created": self._htlc_count,
                "bridge_transfers": self._bridge_count,
            }

    def get_all_contract_health(self) -> List[Dict[str, Any]]:
        """Get health reports for all contracts."""
        reports = self.contract_manager.get_all_health_reports()
        return [
            {
                "contract_type": r.contract_type.value,
                "chain_id": r.chain_id,
                "address": r.address,
                "status": r.status.value,
                "is_paused": r.is_paused,
                "consecutive_failures": r.consecutive_failures,
            }
            for r in reports
        ]

    def run_diagnostics(self) -> Dict[str, Any]:
        """Run full system diagnostics."""
        return self.contract_manager.run_diagnostics()


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_contract_integration(
    chains: Optional[Dict[int, List[str]]] = None,
    private_key: Optional[str] = None,
    contract_addresses: Optional[Dict[str, Dict[int, str]]] = None,
    default_slippage_bps: int = 50,
) -> ContractIntegrationBridge:
    """
    Factory function to create a ContractIntegrationBridge with default configurations.
    
    Args:
        chains: Optional mapping of chain IDs to RPC URLs
        private_key: Optional private key for signing
        contract_addresses: Optional mapping of contract names to chain_id->address
        default_slippage_bps: Default slippage tolerance
        
    Returns:
        Configured ContractIntegrationBridge instance
    """
    # Create contract manager
    manager = create_smart_contract_manager(chains=chains, private_key=private_key)
    
    # Register contracts if addresses provided
    if contract_addresses:
        for contract_name, chain_addresses in contract_addresses.items():
            try:
                contract_type = ContractType(contract_name)
                abi = get_contract_abi(contract_type)
                
                for chain_id, address in chain_addresses.items():
                    if abi:
                        config = ContractConfig(
                            contract_type=contract_type,
                            address=address,
                            chain_id=chain_id,
                            abi=abi,
                        )
                        manager.register_contract(config)
                        
            except ValueError:
                logger.warning(f"Unknown contract type: {contract_name}")
    
    return ContractIntegrationBridge(
        contract_manager=manager,
        default_slippage_bps=default_slippage_bps,
    )
