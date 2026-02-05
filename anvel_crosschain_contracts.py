#!/usr/bin/env python3
"""
ANVEL Cross-Chain Smart Contracts Module

Manages cross-chain smart contract interactions including:
- Bridge contract operations
- Hash Time-Locked Contracts (HTLC) for atomic swaps
- Cross-chain message verification
- Transaction state management with recovery

Production-critical module for capital-touching operations.
"""

import logging
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import TransactionNotFound
from web3.types import TxReceipt

logger = logging.getLogger(__name__)


# ===========================
# Constants
# ===========================

# Wei conversion constants
WEI_PER_ETH = Decimal('1000000000000000000')
WEI_DECIMALS = 18

# Transaction configuration defaults
DEFAULT_TX_TIMEOUT_SECONDS = 300  # 5 minutes
DEFAULT_GAS_LIMIT_APPROVE = 100000
DEFAULT_GAS_LIMIT_BRIDGE = 300000
DEFAULT_GAS_LIMIT_HTLC_CREATE = 300000
DEFAULT_GAS_LIMIT_HTLC_REDEEM = 200000
DEFAULT_GAS_LIMIT_HTLC_REFUND = 150000
DEFAULT_CONFIRMATION_POLL_INTERVAL = 2  # seconds


# ===========================
# Exception Hierarchy
# ===========================

class CrosschainError(Exception):
    """Base exception for all cross-chain errors."""
    pass


class ChainConfigurationError(CrosschainError):
    """Raised when chain configuration is invalid."""
    pass


class BridgeError(CrosschainError):
    """Base exception for bridge operations."""
    pass


class BridgeTransferError(BridgeError):
    """Raised when bridge transfer fails."""
    pass


class BridgeFeeError(BridgeError):
    """Raised when bridge fee estimation fails."""
    pass


class HTLCError(CrosschainError):
    """Base exception for HTLC operations."""
    pass


class HTLCCreationError(HTLCError):
    """Raised when HTLC creation fails."""
    pass


class HTLCRedemptionError(HTLCError):
    """Raised when HTLC redemption fails."""
    pass


class HTLCRefundError(HTLCError):
    """Raised when HTLC refund fails."""
    pass


class HTLCExpiredError(HTLCError):
    """Raised when attempting to redeem an expired HTLC."""
    pass


class VerificationError(CrosschainError):
    """Raised when cross-chain message verification fails."""
    pass


class SignatureVerificationError(VerificationError):
    """Raised when signature verification fails."""
    pass


class MerkleProofError(VerificationError):
    """Raised when merkle proof verification fails."""
    pass


class ReplayProtectionError(VerificationError):
    """Raised when replay attack is detected."""
    pass


class StateManagementError(CrosschainError):
    """Raised when transaction state management fails."""
    pass


# ===========================
# Enums
# ===========================

class ChainType(Enum):
    """Supported blockchain networks."""
    ETHEREUM = "ethereum"
    BSC = "bsc"
    POLYGON = "polygon"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    AVALANCHE = "avalanche"


class TransferStatus(Enum):
    """Status of cross-chain transfer."""
    INITIATED = "initiated"
    SOURCE_CONFIRMED = "source_confirmed"
    RELAYED = "relayed"
    DESTINATION_PENDING = "destination_pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class HTLCStatus(Enum):
    """Status of HTLC contract."""
    ACTIVE = "active"
    REDEEMED = "redeemed"
    REFUNDED = "refunded"
    EXPIRED = "expired"


# ===========================
# Data Classes
# ===========================

@dataclass
class ChainConfig:
    """Configuration for a blockchain network."""
    chain_type: ChainType
    chain_id: int
    rpc_url: str
    bridge_contract_address: Optional[str] = None
    htlc_contract_address: Optional[str] = None
    block_confirmations: int = 12
    max_gas_price_gwei: Decimal = Decimal("100")

    def __post_init__(self):
        """Validate configuration on initialization."""
        if not self.rpc_url:
            raise ChainConfigurationError(f"RPC URL required for {self.chain_type.value}")
        if self.block_confirmations < 1:
            raise ChainConfigurationError("Block confirmations must be at least 1")
        if self.max_gas_price_gwei <= 0:
            raise ChainConfigurationError("Max gas price must be positive")


@dataclass
class BridgeTransfer:
    """Represents a cross-chain bridge transfer."""
    transfer_id: str
    source_chain: ChainType
    destination_chain: ChainType
    token_address: str
    sender: str
    recipient: str
    amount: Decimal
    status: TransferStatus
    source_tx_hash: Optional[str] = None
    destination_tx_hash: Optional[str] = None
    nonce: int = 0
    fee: Decimal = Decimal("0")
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    retry_count: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "transfer_id": self.transfer_id,
            "source_chain": self.source_chain.value,
            "destination_chain": self.destination_chain.value,
            "token_address": self.token_address,
            "sender": self.sender,
            "recipient": self.recipient,
            "amount": str(self.amount),
            "status": self.status.value,
            "source_tx_hash": self.source_tx_hash,
            "destination_tx_hash": self.destination_tx_hash,
            "nonce": self.nonce,
            "fee": str(self.fee),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "retry_count": self.retry_count,
            "last_error": self.last_error,
        }


@dataclass
class HTLCContract:
    """Represents a Hash Time-Locked Contract."""
    contract_id: str
    chain: ChainType
    sender: str
    recipient: str
    token_address: str
    amount: Decimal
    hash_lock: str
    time_lock: datetime
    status: HTLCStatus
    secret: Optional[str] = None
    contract_address: Optional[str] = None
    creation_tx_hash: Optional[str] = None
    redeem_tx_hash: Optional[str] = None
    refund_tx_hash: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self) -> bool:
        """Check if HTLC has expired."""
        return datetime.now(timezone.utc) >= self.time_lock

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "contract_id": self.contract_id,
            "chain": self.chain.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "token_address": self.token_address,
            "amount": str(self.amount),
            "hash_lock": self.hash_lock,
            "time_lock": self.time_lock.isoformat(),
            "status": self.status.value,
            "secret": self.secret,
            "contract_address": self.contract_address,
            "creation_tx_hash": self.creation_tx_hash,
            "redeem_tx_hash": self.redeem_tx_hash,
            "refund_tx_hash": self.refund_tx_hash,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class MerkleProof:
    """Merkle proof for cross-chain message verification."""
    root: str
    leaf: str
    proof: List[str]
    index: int

    def verify(self) -> bool:
        """Verify the merkle proof."""
        computed_hash = self.leaf
        for i, sibling_hash in enumerate(self.proof):
            if (self.index >> i) & 1:
                # Leaf is on the right
                computed_hash = Web3.solidity_keccak(
                    ['bytes32', 'bytes32'],
                    [bytes.fromhex(sibling_hash[2:]), bytes.fromhex(computed_hash[2:])]
                ).hex()
            else:
                # Leaf is on the left
                computed_hash = Web3.solidity_keccak(
                    ['bytes32', 'bytes32'],
                    [bytes.fromhex(computed_hash[2:]), bytes.fromhex(sibling_hash[2:])]
                ).hex()

        return computed_hash.lower() == self.root.lower()


# ===========================
# Main Manager Class
# ===========================

class CrosschainContractManager:
    """
    Manages cross-chain smart contract interactions.
    
    Provides:
    - Bridge contract operations for cross-chain transfers
    - HTLC for atomic swaps
    - Message verification with replay protection
    - Transaction state management with automatic retry
    - Recovery from partial failures
    
    Thread-safe and idempotent operations.
    """

    # Standard ERC20 ABI (minimal interface)
    ERC20_ABI = [
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function"
        },
        {
            "constant": False,
            "inputs": [
                {"name": "_to", "type": "address"},
                {"name": "_value", "type": "uint256"}
            ],
            "name": "transfer",
            "outputs": [{"name": "success", "type": "bool"}],
            "type": "function"
        },
        {
            "constant": False,
            "inputs": [
                {"name": "_spender", "type": "address"},
                {"name": "_value", "type": "uint256"}
            ],
            "name": "approve",
            "outputs": [{"name": "success", "type": "bool"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [
                {"name": "_owner", "type": "address"},
                {"name": "_spender", "type": "address"}
            ],
            "name": "allowance",
            "outputs": [{"name": "remaining", "type": "uint256"}],
            "type": "function"
        }
    ]

    # Simplified Bridge ABI
    BRIDGE_ABI = [
        {
            "constant": False,
            "inputs": [
                {"name": "token", "type": "address"},
                {"name": "amount", "type": "uint256"},
                {"name": "destinationChainId", "type": "uint256"},
                {"name": "recipient", "type": "address"}
            ],
            "name": "initiateBridge",
            "outputs": [{"name": "transferId", "type": "bytes32"}],
            "type": "function"
        },
        {
            "constant": False,
            "inputs": [
                {"name": "transferId", "type": "bytes32"},
                {"name": "proof", "type": "bytes32[]"}
            ],
            "name": "completeBridge",
            "outputs": [{"name": "success", "type": "bool"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [{"name": "transferId", "type": "bytes32"}],
            "name": "getTransferStatus",
            "outputs": [
                {"name": "completed", "type": "bool"},
                {"name": "amount", "type": "uint256"}
            ],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [
                {"name": "token", "type": "address"},
                {"name": "amount", "type": "uint256"},
                {"name": "destinationChainId", "type": "uint256"}
            ],
            "name": "estimateFee",
            "outputs": [{"name": "fee", "type": "uint256"}],
            "type": "function"
        }
    ]

    # Simplified HTLC ABI
    HTLC_ABI = [
        {
            "constant": False,
            "inputs": [
                {"name": "recipient", "type": "address"},
                {"name": "hashLock", "type": "bytes32"},
                {"name": "timeLock", "type": "uint256"},
                {"name": "token", "type": "address"},
                {"name": "amount", "type": "uint256"}
            ],
            "name": "create",
            "outputs": [{"name": "contractId", "type": "bytes32"}],
            "type": "function"
        },
        {
            "constant": False,
            "inputs": [
                {"name": "contractId", "type": "bytes32"},
                {"name": "secret", "type": "bytes32"}
            ],
            "name": "redeem",
            "outputs": [{"name": "success", "type": "bool"}],
            "type": "function"
        },
        {
            "constant": False,
            "inputs": [{"name": "contractId", "type": "bytes32"}],
            "name": "refund",
            "outputs": [{"name": "success", "type": "bool"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [{"name": "contractId", "type": "bytes32"}],
            "name": "getStatus",
            "outputs": [
                {"name": "exists", "type": "bool"},
                {"name": "redeemed", "type": "bool"},
                {"name": "refunded", "type": "bool"},
                {"name": "amount", "type": "uint256"},
                {"name": "timeLock", "type": "uint256"}
            ],
            "type": "function"
        }
    ]

    def __init__(
        self,
        chain_configs: Dict[ChainType, ChainConfig],
        private_key: Optional[str] = None,
        max_retry_attempts: int = 3,
        retry_backoff_seconds: float = 2.0,
    ):
        """
        Initialize cross-chain contract manager.
        
        Args:
            chain_configs: Configuration for each supported chain
            private_key: Private key for signing transactions (NEVER hardcode in production)
            max_retry_attempts: Maximum number of retry attempts for failed operations
            retry_backoff_seconds: Base backoff time for exponential retry
            
        Raises:
            ChainConfigurationError: If configuration validation fails
        """
        self.chain_configs = chain_configs
        self.private_key = private_key
        self.max_retry_attempts = max_retry_attempts
        self.retry_backoff_seconds = retry_backoff_seconds

        # Validate all configurations
        self._validate_configurations()

        # Initialize Web3 instances for each chain
        self.web3_instances: Dict[ChainType, Web3] = {}
        self._initialize_web3_instances()

        # State management
        self._lock = threading.RLock()
        self._active_transfers: Dict[str, BridgeTransfer] = {}
        self._active_htlcs: Dict[str, HTLCContract] = {}
        self._processed_nonces: Dict[ChainType, set] = {chain: set() for chain in ChainType}

        # Contract instances cache
        self._bridge_contracts: Dict[ChainType, Optional[Contract]] = {}
        self._htlc_contracts: Dict[ChainType, Optional[Contract]] = {}

        logger.info(
            "CrosschainContractManager initialized",
            extra={
                "chains": [c.value for c in chain_configs.keys()],
                "max_retry_attempts": max_retry_attempts,
            }
        )

    def _validate_configurations(self) -> None:
        """Validate all chain configurations at startup."""
        if not self.chain_configs:
            raise ChainConfigurationError("At least one chain configuration required")

        for chain_type, config in self.chain_configs.items():
            if config.chain_type != chain_type:
                raise ChainConfigurationError(
                    f"Chain type mismatch: {chain_type} != {config.chain_type}"
                )

            # Validate chain ID matches expected values
            expected_chain_ids = {
                ChainType.ETHEREUM: 1,
                ChainType.BSC: 56,
                ChainType.POLYGON: 137,
                ChainType.ARBITRUM: 42161,
                ChainType.OPTIMISM: 10,
                ChainType.AVALANCHE: 43114,
            }

            expected_id = expected_chain_ids.get(chain_type)
            if expected_id and config.chain_id != expected_id:
                raise ChainConfigurationError(
                    f"Chain ID mismatch for {chain_type.value}: "
                    f"configured {config.chain_id}, expected {expected_id}. "
                    f"Incorrect chain ID could lead to fund loss."
                )

        logger.info("All chain configurations validated successfully")

    def _initialize_web3_instances(self) -> None:
        """Initialize Web3 instances for all configured chains."""
        for chain_type, config in self.chain_configs.items():
            try:
                web3 = Web3(Web3.HTTPProvider(config.rpc_url))

                # Verify connection
                if not web3.is_connected():
                    raise ChainConfigurationError(
                        f"Failed to connect to {chain_type.value} at {config.rpc_url}"
                    )

                # Verify chain ID matches
                actual_chain_id = web3.eth.chain_id
                if actual_chain_id != config.chain_id:
                    raise ChainConfigurationError(
                        f"Chain ID mismatch for {chain_type.value}: "
                        f"expected {config.chain_id}, got {actual_chain_id}"
                    )

                self.web3_instances[chain_type] = web3
                logger.info(
                    f"Connected to {chain_type.value}",
                    extra={
                        "chain_id": actual_chain_id,
                        "block_number": web3.eth.block_number,
                    }
                )

            except Exception as e:
                raise ChainConfigurationError(
                    f"Failed to initialize Web3 for {chain_type.value}: {str(e)}"
                ) from e

    def _get_bridge_contract(self, chain: ChainType) -> Optional[Contract]:
        """Get bridge contract instance for a chain."""
        if chain not in self._bridge_contracts:
            config = self.chain_configs.get(chain)
            if not config or not config.bridge_contract_address:
                self._bridge_contracts[chain] = None
                return None

            web3 = self.web3_instances[chain]
            address = Web3.to_checksum_address(config.bridge_contract_address)
            self._bridge_contracts[chain] = web3.eth.contract(
                address=address,
                abi=self.BRIDGE_ABI
            )

        return self._bridge_contracts[chain]

    def _get_htlc_contract(self, chain: ChainType) -> Optional[Contract]:
        """Get HTLC contract instance for a chain."""
        if chain not in self._htlc_contracts:
            config = self.chain_configs.get(chain)
            if not config or not config.htlc_contract_address:
                self._htlc_contracts[chain] = None
                return None

            web3 = self.web3_instances[chain]
            address = Web3.to_checksum_address(config.htlc_contract_address)
            self._htlc_contracts[chain] = web3.eth.contract(
                address=address,
                abi=self.HTLC_ABI
            )

        return self._htlc_contracts[chain]

    def _generate_transfer_id(self) -> str:
        """Generate unique transfer ID."""
        return f"bridge_{int(time.time() * 1000)}_{secrets.token_hex(16)}"

    def _generate_contract_id(self) -> str:
        """Generate unique contract ID for HTLC."""
        return f"htlc_{int(time.time() * 1000)}_{secrets.token_hex(16)}"

    def _generate_secret(self) -> Tuple[str, str]:
        """Generate secret and hash lock for HTLC."""
        secret = secrets.token_hex(32)
        secret_bytes = bytes.fromhex(secret)
        hash_lock = Web3.solidity_keccak(['bytes32'], [secret_bytes]).hex()
        return secret, hash_lock

    def _to_wei(self, amount: Decimal) -> int:
        """
        Convert amount to wei with proper precision.
        
        Args:
            amount: Amount in Ether/token units
            
        Returns:
            Amount in wei
        """
        return int(amount * WEI_PER_ETH)

    def _from_wei(self, amount_wei: int) -> Decimal:
        """
        Convert wei to Ether/token units with proper precision.
        
        Args:
            amount_wei: Amount in wei
            
        Returns:
            Amount in Ether/token units
        """
        return Decimal(amount_wei) / WEI_PER_ETH

    def _wait_for_confirmations(
        self,
        chain: ChainType,
        tx_hash: str,
        required_confirmations: Optional[int] = None
    ) -> TxReceipt:
        """
        Wait for transaction to receive required confirmations.
        
        Args:
            chain: Blockchain network
            tx_hash: Transaction hash
            required_confirmations: Number of confirmations to wait for
            
        Returns:
            Transaction receipt
            
        Raises:
            BridgeTransferError: If transaction fails or times out
        """
        web3 = self.web3_instances[chain]
        config = self.chain_configs[chain]
        confirmations = required_confirmations or config.block_confirmations

        logger.info(
            f"Waiting for {confirmations} confirmations on {chain.value}",
            extra={"tx_hash": tx_hash}
        )

        # Wait for transaction to be mined
        start_time = time.time()

        while time.time() - start_time < DEFAULT_TX_TIMEOUT_SECONDS:
            try:
                receipt = web3.eth.get_transaction_receipt(tx_hash)

                # Check if transaction failed
                if receipt['status'] == 0:
                    raise BridgeTransferError(
                        f"Transaction {tx_hash} failed on {chain.value}"
                    )

                # Check confirmations
                current_block = web3.eth.block_number
                tx_block = receipt['blockNumber']
                current_confirmations = current_block - tx_block + 1

                if current_confirmations >= confirmations:
                    logger.info(
                        f"Transaction confirmed on {chain.value}",
                        extra={
                            "tx_hash": tx_hash,
                            "confirmations": current_confirmations,
                        }
                    )
                    return receipt

                time.sleep(DEFAULT_CONFIRMATION_POLL_INTERVAL)

            except TransactionNotFound:
                time.sleep(DEFAULT_CONFIRMATION_POLL_INTERVAL)
                continue

        raise BridgeTransferError(
            f"Transaction {tx_hash} confirmation timeout on {chain.value}"
        )

    def _execute_with_retry(
        self,
        operation: str,
        func: callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute operation with exponential backoff retry.
        
        Args:
            operation: Operation name for logging
            func: Function to execute
            *args, **kwargs: Arguments to pass to function
            
        Returns:
            Result from function
            
        Raises:
            Exception: Last exception if all retries fail
        """
        last_exception = None

        for attempt in range(self.max_retry_attempts):
            try:
                result = func(*args, **kwargs)
                if attempt > 0:
                    logger.info(
                        f"{operation} succeeded after {attempt} retries"
                    )
                return result

            except Exception as e:
                last_exception = e
                if attempt < self.max_retry_attempts - 1:
                    backoff = self.retry_backoff_seconds * (2 ** attempt)
                    logger.warning(
                        f"{operation} failed, retrying in {backoff}s",
                        extra={
                            "attempt": attempt + 1,
                            "max_attempts": self.max_retry_attempts,
                            "error": str(e),
                        }
                    )
                    time.sleep(backoff)
                else:
                    logger.error(
                        f"{operation} failed after {self.max_retry_attempts} attempts",
                        extra={"error": str(e)}
                    )

        raise last_exception

    # ===========================
    # Bridge Operations
    # ===========================

    def initiate_bridge_transfer(
        self,
        source_chain: ChainType,
        destination_chain: ChainType,
        token_address: str,
        recipient: str,
        amount: Decimal,
        sender_address: Optional[str] = None,
    ) -> BridgeTransfer:
        """
        Initiate a cross-chain bridge transfer.
        
        Args:
            source_chain: Source blockchain network
            destination_chain: Destination blockchain network
            token_address: Token contract address on source chain
            recipient: Recipient address on destination chain
            amount: Amount to transfer
            sender_address: Sender address (derived from private_key if not provided)
            
        Returns:
            BridgeTransfer object with transfer details
            
        Raises:
            BridgeTransferError: If transfer initiation fails
            ChainConfigurationError: If bridge contract not configured
        """
        if source_chain == destination_chain:
            raise BridgeTransferError("Source and destination chains must be different")

        if amount <= 0:
            raise BridgeTransferError(f"Invalid transfer amount: {amount}")

        if source_chain not in self.chain_configs:
            raise ChainConfigurationError(f"Chain {source_chain.value} not configured")

        if destination_chain not in self.chain_configs:
            raise ChainConfigurationError(f"Chain {destination_chain.value} not configured")

        bridge_contract = self._get_bridge_contract(source_chain)
        if not bridge_contract:
            raise ChainConfigurationError(
                f"Bridge contract not configured for {source_chain.value}"
            )

        if not self.private_key:
            raise BridgeTransferError("Private key required for transaction signing")

        web3 = self.web3_instances[source_chain]

        # Derive sender address if not provided
        if not sender_address:
            account = web3.eth.account.from_key(self.private_key)
            sender_address = account.address

        # Validate addresses
        token_address = Web3.to_checksum_address(token_address)
        recipient = Web3.to_checksum_address(recipient)
        sender_address = Web3.to_checksum_address(sender_address)

        # Generate transfer ID
        transfer_id = self._generate_transfer_id()

        # Create transfer object
        transfer = BridgeTransfer(
            transfer_id=transfer_id,
            source_chain=source_chain,
            destination_chain=destination_chain,
            token_address=token_address,
            sender=sender_address,
            recipient=recipient,
            amount=amount,
            status=TransferStatus.INITIATED,
            nonce=web3.eth.get_transaction_count(sender_address),
        )

        logger.info(
            f"Initiating bridge transfer from {source_chain.value} to {destination_chain.value}",
            extra=transfer.to_dict()
        )

        try:
            # Check and approve token allowance
            token_contract = web3.eth.contract(
                address=token_address,
                abi=self.ERC20_ABI
            )

            allowance = token_contract.functions.allowance(
                sender_address,
                bridge_contract.address
            ).call()

            # Convert amount to wei with proper precision
            amount_wei = self._to_wei(amount)

            if allowance < amount_wei:
                # Approve token transfer
                approve_tx = token_contract.functions.approve(
                    bridge_contract.address,
                    amount_wei
                ).build_transaction({
                    'from': sender_address,
                    'nonce': transfer.nonce,
                    'gas': DEFAULT_GAS_LIMIT_APPROVE,
                    'gasPrice': web3.eth.gas_price,
                })

                signed_approve_tx = web3.eth.account.sign_transaction(
                    approve_tx,
                    self.private_key
                )
                approve_tx_hash = web3.eth.send_raw_transaction(
                    signed_approve_tx.rawTransaction
                )

                logger.info(
                    "Token approval transaction sent",
                    extra={"tx_hash": approve_tx_hash.hex()}
                )

                # Wait for approval confirmation
                self._wait_for_confirmations(source_chain, approve_tx_hash.hex(), 1)

                # Increment nonce for next transaction
                transfer.nonce += 1

            # Estimate bridge fee
            dest_config = self.chain_configs[destination_chain]
            fee = bridge_contract.functions.estimateFee(
                token_address,
                amount_wei,
                dest_config.chain_id
            ).call()
            transfer.fee = self._from_wei(fee)

            # Initiate bridge transfer
            bridge_tx = bridge_contract.functions.initiateBridge(
                token_address,
                amount_wei,
                dest_config.chain_id,
                recipient
            ).build_transaction({
                'from': sender_address,
                'nonce': transfer.nonce,
                'gas': DEFAULT_GAS_LIMIT_BRIDGE,
                'gasPrice': web3.eth.gas_price,
                'value': fee,
            })

            signed_bridge_tx = web3.eth.account.sign_transaction(
                bridge_tx,
                self.private_key
            )
            bridge_tx_hash = web3.eth.send_raw_transaction(
                signed_bridge_tx.rawTransaction
            )

            transfer.source_tx_hash = bridge_tx_hash.hex()
            transfer.status = TransferStatus.SOURCE_CONFIRMED
            transfer.updated_at = datetime.now(timezone.utc)

            logger.info(
                "Bridge transfer initiated",
                extra={
                    "transfer_id": transfer_id,
                    "tx_hash": bridge_tx_hash.hex(),
                    "fee": str(transfer.fee),
                }
            )

            # Wait for confirmations
            self._wait_for_confirmations(source_chain, bridge_tx_hash.hex())

            # Store active transfer
            with self._lock:
                self._active_transfers[transfer_id] = transfer

            return transfer

        except Exception as e:
            transfer.status = TransferStatus.FAILED
            transfer.last_error = str(e)
            transfer.updated_at = datetime.now(timezone.utc)

            logger.error(
                "Bridge transfer initiation failed",
                extra={
                    "transfer_id": transfer_id,
                    "error": str(e),
                }
            )

            raise BridgeTransferError(
                f"Failed to initiate bridge transfer: {str(e)}"
            ) from e

    def complete_bridge_transfer(
        self,
        transfer_id: str,
        merkle_proof: Optional[MerkleProof] = None,
    ) -> BridgeTransfer:
        """
        Complete a cross-chain bridge transfer on destination chain.
        
        Args:
            transfer_id: Transfer ID from initiation
            merkle_proof: Merkle proof for cross-chain message verification
            
        Returns:
            Updated BridgeTransfer object
            
        Raises:
            BridgeTransferError: If transfer completion fails
            StateManagementError: If transfer not found
        """
        with self._lock:
            transfer = self._active_transfers.get(transfer_id)

        if not transfer:
            raise StateManagementError(f"Transfer {transfer_id} not found")

        if transfer.status == TransferStatus.COMPLETED:
            logger.info(f"Transfer {transfer_id} already completed")
            return transfer

        if transfer.status != TransferStatus.SOURCE_CONFIRMED:
            raise BridgeTransferError(
                f"Transfer {transfer_id} not ready for completion. Status: {transfer.status.value}"
            )

        bridge_contract = self._get_bridge_contract(transfer.destination_chain)
        if not bridge_contract:
            raise ChainConfigurationError(
                f"Bridge contract not configured for {transfer.destination_chain.value}"
            )

        if not self.private_key:
            raise BridgeTransferError("Private key required for transaction signing")

        web3 = self.web3_instances[transfer.destination_chain]
        account = web3.eth.account.from_key(self.private_key)

        logger.info(
            f"Completing bridge transfer on {transfer.destination_chain.value}",
            extra={"transfer_id": transfer_id}
        )

        try:
            # Prepare merkle proof (simplified - in production use actual proof)
            proof_bytes = []
            if merkle_proof:
                # Verify merkle proof
                if not merkle_proof.verify():
                    raise MerkleProofError("Invalid merkle proof")
                proof_bytes = [bytes.fromhex(p[2:]) for p in merkle_proof.proof]

            # Convert transfer_id to bytes32
            transfer_id_bytes = Web3.keccak(text=transfer_id)

            # Complete bridge transfer
            complete_tx = bridge_contract.functions.completeBridge(
                transfer_id_bytes,
                proof_bytes
            ).build_transaction({
                'from': account.address,
                'nonce': web3.eth.get_transaction_count(account.address),
                'gas': DEFAULT_GAS_LIMIT_BRIDGE,
                'gasPrice': web3.eth.gas_price,
            })

            signed_complete_tx = web3.eth.account.sign_transaction(
                complete_tx,
                self.private_key
            )
            complete_tx_hash = web3.eth.send_raw_transaction(
                signed_complete_tx.rawTransaction
            )

            transfer.destination_tx_hash = complete_tx_hash.hex()
            transfer.status = TransferStatus.COMPLETED
            transfer.updated_at = datetime.now(timezone.utc)

            logger.info(
                "Bridge transfer completed",
                extra={
                    "transfer_id": transfer_id,
                    "tx_hash": complete_tx_hash.hex(),
                }
            )

            # Wait for confirmations
            self._wait_for_confirmations(transfer.destination_chain, complete_tx_hash.hex())

            # Update stored transfer
            with self._lock:
                self._active_transfers[transfer_id] = transfer

            return transfer

        except Exception as e:
            transfer.status = TransferStatus.FAILED
            transfer.last_error = str(e)
            transfer.retry_count += 1
            transfer.updated_at = datetime.now(timezone.utc)

            logger.error(
                "Bridge transfer completion failed",
                extra={
                    "transfer_id": transfer_id,
                    "retry_count": transfer.retry_count,
                    "error": str(e),
                }
            )

            raise BridgeTransferError(
                f"Failed to complete bridge transfer: {str(e)}"
            ) from e

    def get_transfer_status(self, transfer_id: str) -> Optional[BridgeTransfer]:
        """
        Get status of a bridge transfer.
        
        Args:
            transfer_id: Transfer ID
            
        Returns:
            BridgeTransfer object or None if not found
        """
        with self._lock:
            return self._active_transfers.get(transfer_id)

    def estimate_bridge_fees(
        self,
        source_chain: ChainType,
        destination_chain: ChainType,
        token_address: str,
        amount: Decimal,
    ) -> Decimal:
        """
        Estimate bridge fees for a transfer.
        
        Args:
            source_chain: Source blockchain network
            destination_chain: Destination blockchain network
            token_address: Token contract address
            amount: Amount to transfer
            
        Returns:
            Estimated fee in native token of source chain
            
        Raises:
            BridgeFeeError: If fee estimation fails
        """
        if source_chain not in self.chain_configs:
            raise ChainConfigurationError(f"Chain {source_chain.value} not configured")

        if destination_chain not in self.chain_configs:
            raise ChainConfigurationError(f"Chain {destination_chain.value} not configured")

        bridge_contract = self._get_bridge_contract(source_chain)
        if not bridge_contract:
            raise ChainConfigurationError(
                f"Bridge contract not configured for {source_chain.value}"
            )

        try:
            token_address = Web3.to_checksum_address(token_address)
            # Convert amount to wei with proper precision
            amount_wei = self._to_wei(amount)
            dest_config = self.chain_configs[destination_chain]

            fee_wei = bridge_contract.functions.estimateFee(
                token_address,
                amount_wei,
                dest_config.chain_id
            ).call()

            fee = self._from_wei(fee_wei)

            logger.info(
                "Bridge fee estimated",
                extra={
                    "source_chain": source_chain.value,
                    "destination_chain": destination_chain.value,
                    "amount": str(amount),
                    "fee": str(fee),
                }
            )

            return fee

        except Exception as e:
            logger.error(
                "Bridge fee estimation failed",
                extra={"error": str(e)}
            )
            raise BridgeFeeError(
                f"Failed to estimate bridge fee: {str(e)}"
            ) from e

    # ===========================
    # HTLC Operations
    # ===========================

    def create_htlc(
        self,
        chain: ChainType,
        recipient: str,
        token_address: str,
        amount: Decimal,
        time_lock_hours: int = 24,
        sender_address: Optional[str] = None,
        secret: Optional[str] = None,
    ) -> HTLCContract:
        """
        Create a Hash Time-Locked Contract for atomic swap.
        
        Args:
            chain: Blockchain network
            recipient: Recipient address
            token_address: Token contract address
            amount: Amount to lock
            time_lock_hours: Hours until HTLC expires
            sender_address: Sender address (derived from private_key if not provided)
            secret: Secret for hash lock (generated if not provided)
            
        Returns:
            HTLCContract object
            
        Raises:
            HTLCCreationError: If HTLC creation fails
        """
        if amount <= 0:
            raise HTLCCreationError(f"Invalid amount: {amount}")

        if time_lock_hours <= 0:
            raise HTLCCreationError(f"Invalid time lock: {time_lock_hours}")

        if chain not in self.chain_configs:
            raise ChainConfigurationError(f"Chain {chain.value} not configured")

        htlc_contract = self._get_htlc_contract(chain)
        if not htlc_contract:
            raise ChainConfigurationError(
                f"HTLC contract not configured for {chain.value}"
            )

        if not self.private_key:
            raise HTLCCreationError("Private key required for transaction signing")

        web3 = self.web3_instances[chain]

        # Derive sender address if not provided
        if not sender_address:
            account = web3.eth.account.from_key(self.private_key)
            sender_address = account.address

        # Validate addresses
        token_address = Web3.to_checksum_address(token_address)
        recipient = Web3.to_checksum_address(recipient)
        sender_address = Web3.to_checksum_address(sender_address)

        # Generate secret and hash lock
        if not secret:
            secret, hash_lock = self._generate_secret()
        else:
            secret_bytes = bytes.fromhex(secret)
            hash_lock = Web3.solidity_keccak(['bytes32'], [secret_bytes]).hex()

        # Calculate time lock
        time_lock = datetime.now(timezone.utc) + timedelta(hours=time_lock_hours)
        time_lock_timestamp = int(time_lock.timestamp())

        # Generate contract ID
        contract_id = self._generate_contract_id()

        # Create HTLC object
        htlc = HTLCContract(
            contract_id=contract_id,
            chain=chain,
            sender=sender_address,
            recipient=recipient,
            token_address=token_address,
            amount=amount,
            hash_lock=hash_lock,
            time_lock=time_lock,
            status=HTLCStatus.ACTIVE,
            secret=secret,
        )

        logger.info(
            f"Creating HTLC on {chain.value}",
            extra={
                "contract_id": contract_id,
                "amount": str(amount),
                "time_lock": time_lock.isoformat(),
            }
        )

        try:
            # Check and approve token allowance
            token_contract = web3.eth.contract(
                address=token_address,
                abi=self.ERC20_ABI
            )

            allowance = token_contract.functions.allowance(
                sender_address,
                htlc_contract.address
            ).call()

            # Convert amount to wei with proper precision
            amount_wei = self._to_wei(amount)
            nonce = web3.eth.get_transaction_count(sender_address)

            if allowance < amount_wei:
                # Approve token transfer
                approve_tx = token_contract.functions.approve(
                    htlc_contract.address,
                    amount_wei
                ).build_transaction({
                    'from': sender_address,
                    'nonce': nonce,
                    'gas': DEFAULT_GAS_LIMIT_APPROVE,
                    'gasPrice': web3.eth.gas_price,
                })

                signed_approve_tx = web3.eth.account.sign_transaction(
                    approve_tx,
                    self.private_key
                )
                approve_tx_hash = web3.eth.send_raw_transaction(
                    signed_approve_tx.rawTransaction
                )

                logger.info(
                    "Token approval transaction sent",
                    extra={"tx_hash": approve_tx_hash.hex()}
                )

                # Wait for approval confirmation
                self._wait_for_confirmations(chain, approve_tx_hash.hex(), 1)
                nonce += 1

            # Create HTLC
            hash_lock_bytes = bytes.fromhex(hash_lock[2:])

            create_tx = htlc_contract.functions.create(
                recipient,
                hash_lock_bytes,
                time_lock_timestamp,
                token_address,
                amount_wei
            ).build_transaction({
                'from': sender_address,
                'nonce': nonce,
                'gas': DEFAULT_GAS_LIMIT_HTLC_CREATE,
                'gasPrice': web3.eth.gas_price,
            })

            signed_create_tx = web3.eth.account.sign_transaction(
                create_tx,
                self.private_key
            )
            create_tx_hash = web3.eth.send_raw_transaction(
                signed_create_tx.rawTransaction
            )

            htlc.creation_tx_hash = create_tx_hash.hex()
            htlc.contract_address = htlc_contract.address

            logger.info(
                "HTLC created",
                extra={
                    "contract_id": contract_id,
                    "tx_hash": create_tx_hash.hex(),
                }
            )

            # Wait for confirmations
            self._wait_for_confirmations(chain, create_tx_hash.hex())

            # Store active HTLC
            with self._lock:
                self._active_htlcs[contract_id] = htlc

            return htlc

        except Exception as e:
            logger.error(
                "HTLC creation failed",
                extra={
                    "contract_id": contract_id,
                    "error": str(e),
                }
            )

            raise HTLCCreationError(
                f"Failed to create HTLC: {str(e)}"
            ) from e

    def redeem_htlc(
        self,
        contract_id: str,
        secret: str,
        redeemer_address: Optional[str] = None,
    ) -> HTLCContract:
        """
        Redeem a Hash Time-Locked Contract with secret.
        
        Args:
            contract_id: HTLC contract ID
            secret: Secret to unlock the funds
            redeemer_address: Address redeeming the funds (derived if not provided)
            
        Returns:
            Updated HTLCContract object
            
        Raises:
            HTLCRedemptionError: If redemption fails
            HTLCExpiredError: If HTLC has expired
            StateManagementError: If contract not found
        """
        with self._lock:
            htlc = self._active_htlcs.get(contract_id)

        if not htlc:
            raise StateManagementError(f"HTLC {contract_id} not found")

        if htlc.status == HTLCStatus.REDEEMED:
            logger.info(f"HTLC {contract_id} already redeemed")
            return htlc

        if htlc.is_expired():
            raise HTLCExpiredError(f"HTLC {contract_id} has expired")

        if htlc.status != HTLCStatus.ACTIVE:
            raise HTLCRedemptionError(
                f"HTLC {contract_id} cannot be redeemed. Status: {htlc.status.value}"
            )

        htlc_contract = self._get_htlc_contract(htlc.chain)
        if not htlc_contract:
            raise ChainConfigurationError(
                f"HTLC contract not configured for {htlc.chain.value}"
            )

        if not self.private_key:
            raise HTLCRedemptionError("Private key required for transaction signing")

        web3 = self.web3_instances[htlc.chain]

        # Derive redeemer address if not provided
        if not redeemer_address:
            account = web3.eth.account.from_key(self.private_key)
            redeemer_address = account.address

        redeemer_address = Web3.to_checksum_address(redeemer_address)

        # Verify secret matches hash lock
        secret_bytes = bytes.fromhex(secret)
        computed_hash_lock = Web3.solidity_keccak(['bytes32'], [secret_bytes]).hex()

        if computed_hash_lock.lower() != htlc.hash_lock.lower():
            raise HTLCRedemptionError("Invalid secret: hash does not match")

        logger.info(
            f"Redeeming HTLC on {htlc.chain.value}",
            extra={"contract_id": contract_id}
        )

        try:
            # Convert contract_id to bytes32
            contract_id_bytes = Web3.keccak(text=contract_id)

            # Redeem HTLC
            redeem_tx = htlc_contract.functions.redeem(
                contract_id_bytes,
                secret_bytes
            ).build_transaction({
                'from': redeemer_address,
                'nonce': web3.eth.get_transaction_count(redeemer_address),
                'gas': DEFAULT_GAS_LIMIT_HTLC_REDEEM,
                'gasPrice': web3.eth.gas_price,
            })

            signed_redeem_tx = web3.eth.account.sign_transaction(
                redeem_tx,
                self.private_key
            )
            redeem_tx_hash = web3.eth.send_raw_transaction(
                signed_redeem_tx.rawTransaction
            )

            htlc.redeem_tx_hash = redeem_tx_hash.hex()
            htlc.status = HTLCStatus.REDEEMED

            logger.info(
                "HTLC redeemed",
                extra={
                    "contract_id": contract_id,
                    "tx_hash": redeem_tx_hash.hex(),
                }
            )

            # Wait for confirmations
            self._wait_for_confirmations(htlc.chain, redeem_tx_hash.hex())

            # Update stored HTLC
            with self._lock:
                self._active_htlcs[contract_id] = htlc

            return htlc

        except Exception as e:
            logger.error(
                "HTLC redemption failed",
                extra={
                    "contract_id": contract_id,
                    "error": str(e),
                }
            )

            raise HTLCRedemptionError(
                f"Failed to redeem HTLC: {str(e)}"
            ) from e

    def refund_htlc(
        self,
        contract_id: str,
        sender_address: Optional[str] = None,
    ) -> HTLCContract:
        """
        Refund an expired Hash Time-Locked Contract.
        
        Args:
            contract_id: HTLC contract ID
            sender_address: Original sender address (derived if not provided)
            
        Returns:
            Updated HTLCContract object
            
        Raises:
            HTLCRefundError: If refund fails
            StateManagementError: If contract not found
        """
        with self._lock:
            htlc = self._active_htlcs.get(contract_id)

        if not htlc:
            raise StateManagementError(f"HTLC {contract_id} not found")

        if htlc.status == HTLCStatus.REFUNDED:
            logger.info(f"HTLC {contract_id} already refunded")
            return htlc

        if not htlc.is_expired():
            raise HTLCRefundError(
                f"HTLC {contract_id} has not expired yet. Expires at {htlc.time_lock.isoformat()}"
            )

        if htlc.status == HTLCStatus.REDEEMED:
            raise HTLCRefundError(f"HTLC {contract_id} has already been redeemed")

        htlc_contract = self._get_htlc_contract(htlc.chain)
        if not htlc_contract:
            raise ChainConfigurationError(
                f"HTLC contract not configured for {htlc.chain.value}"
            )

        if not self.private_key:
            raise HTLCRefundError("Private key required for transaction signing")

        web3 = self.web3_instances[htlc.chain]

        # Derive sender address if not provided
        if not sender_address:
            account = web3.eth.account.from_key(self.private_key)
            sender_address = account.address

        sender_address = Web3.to_checksum_address(sender_address)

        logger.info(
            f"Refunding HTLC on {htlc.chain.value}",
            extra={"contract_id": contract_id}
        )

        try:
            # Convert contract_id to bytes32
            contract_id_bytes = Web3.keccak(text=contract_id)

            # Refund HTLC
            refund_tx = htlc_contract.functions.refund(
                contract_id_bytes
            ).build_transaction({
                'from': sender_address,
                'nonce': web3.eth.get_transaction_count(sender_address),
                'gas': DEFAULT_GAS_LIMIT_HTLC_REFUND,
                'gasPrice': web3.eth.gas_price,
            })

            signed_refund_tx = web3.eth.account.sign_transaction(
                refund_tx,
                self.private_key
            )
            refund_tx_hash = web3.eth.send_raw_transaction(
                signed_refund_tx.rawTransaction
            )

            htlc.refund_tx_hash = refund_tx_hash.hex()
            htlc.status = HTLCStatus.REFUNDED

            logger.info(
                "HTLC refunded",
                extra={
                    "contract_id": contract_id,
                    "tx_hash": refund_tx_hash.hex(),
                }
            )

            # Wait for confirmations
            self._wait_for_confirmations(htlc.chain, refund_tx_hash.hex())

            # Update stored HTLC
            with self._lock:
                self._active_htlcs[contract_id] = htlc

            return htlc

        except Exception as e:
            logger.error(
                "HTLC refund failed",
                extra={
                    "contract_id": contract_id,
                    "error": str(e),
                }
            )

            raise HTLCRefundError(
                f"Failed to refund HTLC: {str(e)}"
            ) from e

    def get_htlc_status(self, contract_id: str) -> Optional[HTLCContract]:
        """
        Get status of an HTLC.
        
        Args:
            contract_id: HTLC contract ID
            
        Returns:
            HTLCContract object or None if not found
        """
        with self._lock:
            htlc = self._active_htlcs.get(contract_id)

        if htlc and htlc.status == HTLCStatus.ACTIVE and htlc.is_expired():
            htlc.status = HTLCStatus.EXPIRED
            with self._lock:
                self._active_htlcs[contract_id] = htlc

        return htlc

    # ===========================
    # Verification
    # ===========================

    def verify_signature(
        self,
        message: bytes,
        signature: str,
        expected_signer: str,
    ) -> bool:
        """
        Verify signature from bridge validator.
        
        Args:
            message: Message that was signed
            signature: Signature to verify
            expected_signer: Expected signer address
            
        Returns:
            True if signature is valid
            
        Raises:
            SignatureVerificationError: If verification fails
        """
        try:
            expected_signer = Web3.to_checksum_address(expected_signer)

            # Recover signer address from signature using public API
            # Create a prefixed message hash (EIP-191 compliant)
            message_hash = Web3.keccak(message)
            # Use encode_defunct-style prefixing for recovery
            prefixed_message = b'\x19Ethereum Signed Message:\n32' + message_hash
            prefixed_hash = Web3.keccak(prefixed_message)

            # Use the public recover_hash method
            recovered_address = Web3().eth.account.recover_hash(
                prefixed_hash,
                signature=signature
            )

            is_valid = recovered_address.lower() == expected_signer.lower()

            logger.info(
                f"Signature verification {'succeeded' if is_valid else 'failed'}",
                extra={
                    "expected_signer": expected_signer,
                    "recovered_address": recovered_address,
                }
            )

            return is_valid

        except Exception as e:
            logger.error(
                "Signature verification error",
                extra={"error": str(e)}
            )
            raise SignatureVerificationError(
                f"Failed to verify signature: {str(e)}"
            ) from e

    def check_replay_protection(
        self,
        chain: ChainType,
        nonce: int,
    ) -> bool:
        """
        Check if transaction nonce has been used (replay protection).
        
        Args:
            chain: Blockchain network
            nonce: Transaction nonce
            
        Returns:
            True if nonce has not been used
            
        Raises:
            ReplayProtectionError: If nonce has been used
        """
        with self._lock:
            if nonce in self._processed_nonces[chain]:
                raise ReplayProtectionError(
                    f"Nonce {nonce} already used on {chain.value}"
                )

            self._processed_nonces[chain].add(nonce)

            logger.info(
                "Replay protection check passed",
                extra={"chain": chain.value, "nonce": nonce}
            )

            return True

    # ===========================
    # State Management
    # ===========================

    def get_active_transfers(self) -> List[BridgeTransfer]:
        """Get all active bridge transfers."""
        with self._lock:
            return list(self._active_transfers.values())

    def get_active_htlcs(self) -> List[HTLCContract]:
        """Get all active HTLCs."""
        with self._lock:
            return list(self._active_htlcs.values())

    def retry_failed_transfers(self) -> List[str]:
        """
        Retry all failed bridge transfers.
        
        Returns:
            List of transfer IDs that were retried
        """
        retried_ids = []

        with self._lock:
            failed_transfers = [
                t for t in self._active_transfers.values()
                if t.status == TransferStatus.FAILED
                and t.retry_count < self.max_retry_attempts
            ]

        for transfer in failed_transfers:
            try:
                logger.info(
                    f"Retrying failed transfer {transfer.transfer_id}",
                    extra={"retry_count": transfer.retry_count}
                )

                # Attempt to complete the transfer
                self.complete_bridge_transfer(transfer.transfer_id)
                retried_ids.append(transfer.transfer_id)

            except Exception as e:
                logger.warning(
                    f"Retry failed for transfer {transfer.transfer_id}",
                    extra={"error": str(e)}
                )

        return retried_ids

    @contextmanager
    def transaction_context(self, chain: ChainType):
        """
        Context manager for transaction execution with automatic error handling.
        
        Args:
            chain: Blockchain network
            
        Yields:
            Web3 instance for the chain
            
        Example:
            with manager.transaction_context(ChainType.ETHEREUM) as web3:
                # Execute transactions
                pass
        """
        web3 = self.web3_instances.get(chain)
        if not web3:
            raise ChainConfigurationError(f"Chain {chain.value} not configured")

        start_time = time.time()

        try:
            logger.info(f"Starting transaction context for {chain.value}")
            yield web3

        except Exception as e:
            logger.error(
                f"Transaction context error on {chain.value}",
                extra={
                    "error": str(e),
                    "duration": time.time() - start_time,
                }
            )
            raise

        finally:
            duration = time.time() - start_time
            logger.info(
                f"Transaction context completed for {chain.value}",
                extra={"duration": duration}
            )
