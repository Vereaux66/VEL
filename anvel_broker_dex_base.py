#!/usr/bin/env python3
"""
ANVEL Decentralized Exchange (DEX) Broker Base

Provides base implementation for DEX brokers with common functionality for:
- Web3 connection management
- ERC-20 token approvals
- Gas estimation and optimization
- Slippage protection
- Transaction confirmation

Production-critical module for decentralized trading operations.
"""

import logging
import threading
import time
from decimal import Decimal
from typing import Any, Dict, Optional
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import TransactionNotFound
from anvel_broker_base import BrokerBase

logger = logging.getLogger(__name__)


class DEXBrokerBase(BrokerBase):
    """Base class for all DEX broker implementations."""

    name = "dex_base"

    # ERC-20 ABI for token operations
    ERC20_ABI = [
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function",
        },
        {
            "constant": False,
            "inputs": [
                {"name": "_spender", "type": "address"},
                {"name": "_value", "type": "uint256"}
            ],
            "name": "approve",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [
                {"name": "_owner", "type": "address"},
                {"name": "_spender", "type": "address"}
            ],
            "name": "allowance",
            "outputs": [{"name": "", "type": "uint256"}],
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function",
        },
    ]

    def __init__(
        self,
        rpc_url: str,
        private_key: Optional[str] = None,
        chain_id: int = 1,
        max_gas_price_gwei: Decimal = Decimal("100"),
        slippage_tolerance_bps: int = 50,  # 0.5%
        confirmation_blocks: int = 2,
    ) -> None:
        """
        Initialize DEX broker.
        
        Args:
            rpc_url: Web3 RPC endpoint URL
            private_key: Private key for signing transactions (hex string with 0x prefix)
            chain_id: Blockchain chain ID (1=Ethereum, 56=BSC, etc.)
            max_gas_price_gwei: Maximum acceptable gas price in Gwei
            slippage_tolerance_bps: Maximum slippage in basis points (50 = 0.5%)
            confirmation_blocks: Number of confirmations to wait for
        
        Note:
            Web3 connection is lazy-initialized on first use to avoid network calls
            during import/build time in restricted environments.
        """
        super().__init__()
        self.rpc_url = rpc_url
        self.private_key = private_key
        self.chain_id = chain_id
        self.max_gas_price_gwei = max_gas_price_gwei
        self.slippage_tolerance_bps = slippage_tolerance_bps
        self.confirmation_blocks = confirmation_blocks

        # Lazy-initialized Web3 connection (no network call at init time)
        self._w3: Optional[Web3] = None
        self._account = None
        self._connection_verified = False
        self._connect_lock = threading.Lock()

        logger.info(
            f"DEX broker configured for chain {chain_id} via {rpc_url}, "
            f"slippage={slippage_tolerance_bps}bps, max_gas={max_gas_price_gwei}gwei "
            "(connection deferred until first use)"
        )

    @property
    def w3(self) -> Web3:
        """Lazy-initialized Web3 connection (thread-safe)."""
        if self._w3 is None:
            self._connect()
        return self._w3

    @property
    def account(self):
        """Lazy-initialized account (thread-safe)."""
        if self._w3 is None:
            self._connect()
        return self._account

    def _connect(self) -> None:
        """
        Establish Web3 connection on first use (thread-safe).
        
        This method is called lazily to avoid network calls during import/build.
        Uses double-checked locking for thread safety.
        """
        if self._connection_verified:
            return
        
        with self._connect_lock:
            # Double-check after acquiring lock
            if self._connection_verified:
                return

            logger.info(f"Establishing Web3 connection to {self.rpc_url}...")
            self._w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            
            if not self._w3.is_connected():
                raise ConnectionError(f"Failed to connect to {self.rpc_url}")

        # Verify chain ID matches
        actual_chain_id = self._w3.eth.chain_id
        if actual_chain_id != self.chain_id:
            raise ValueError(
                f"Chain ID mismatch: expected {self.chain_id}, got {actual_chain_id}"
            )

        # Set account if private key provided
        if self.private_key:
            self._account = self._w3.eth.account.from_key(self.private_key)
            logger.info(f"DEX broker connected with account: {self._account.address}")
        else:
            logger.warning("DEX broker connected without private key - read-only mode")

        self._connection_verified = True
        logger.info(f"DEX broker connected to chain {self.chain_id}")

    def _get_token_contract(self, token_address: str) -> Contract:
        """Get ERC-20 token contract instance."""
        if not Web3.is_address(token_address):
            raise ValueError(f"Invalid token address: {token_address}")
        return self.w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=self.ERC20_ABI
        )

    def _get_token_decimals(self, token_address: str) -> int:
        """Get token decimals."""
        contract = self._get_token_contract(token_address)
        return contract.functions.decimals().call()

    def _to_token_units(self, amount: Decimal, decimals: int) -> int:
        """Convert human-readable amount to token units."""
        return int(amount * Decimal(10 ** decimals))

    def _from_token_units(self, amount: int, decimals: int) -> Decimal:
        """Convert token units to human-readable amount."""
        return Decimal(amount) / Decimal(10 ** decimals)

    def _check_and_approve_token(
        self, token_address: str, spender_address: str, amount: int
    ) -> Optional[str]:
        """
        Check token allowance and approve if needed.
        
        Returns transaction hash if approval was needed, None otherwise.
        """
        if not self.account:
            raise RuntimeError("Cannot approve tokens without private key")

        token_contract = self._get_token_contract(token_address)

        # Check current allowance
        current_allowance = token_contract.functions.allowance(
            self.account.address,
            Web3.to_checksum_address(spender_address)
        ).call()

        if current_allowance >= amount:
            logger.debug(
                f"Token {token_address} already approved for {spender_address}, "
                f"allowance={current_allowance}, needed={amount}"
            )
            return None

        # Need to approve - use max uint256 for infinite approval
        max_uint256 = 2**256 - 1

        logger.info(
            f"Approving token {token_address} for spender {spender_address}, "
            f"amount={max_uint256}"
        )

        # Build approval transaction
        approve_tx = token_contract.functions.approve(
            Web3.to_checksum_address(spender_address),
            max_uint256
        ).build_transaction({
            'from': self.account.address,
            'nonce': self.w3.eth.get_transaction_count(self.account.address),
            'gas': 100000,
            'gasPrice': self._get_gas_price(),
            'chainId': self.chain_id,
        })

        # Sign and send
        signed_tx = self.account.sign_transaction(approve_tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        # Wait for confirmation
        receipt = self._wait_for_transaction(tx_hash.hex())

        if receipt['status'] != 1:
            raise RuntimeError(f"Token approval failed: {tx_hash.hex()}")

        logger.info(f"Token approval confirmed: {tx_hash.hex()}")
        return tx_hash.hex()

    def _get_gas_price(self) -> int:
        """Get current gas price with max limit enforcement."""
        gas_price_wei = self.w3.eth.gas_price
        max_gas_price_wei = int(self.max_gas_price_gwei * Decimal('1000000000'))

        if gas_price_wei > max_gas_price_wei:
            logger.warning(
                f"Gas price {gas_price_wei / 1e9:.2f} gwei exceeds max "
                f"{self.max_gas_price_gwei} gwei, using max"
            )
            return max_gas_price_wei

        return gas_price_wei

    def _estimate_gas(self, transaction: Dict[str, Any]) -> int:
        """Estimate gas for transaction with safety margin."""
        try:
            estimated = self.w3.eth.estimate_gas(transaction)
            # Add 20% safety margin
            return int(estimated * 1.2)
        except Exception as e:
            logger.error(f"Gas estimation failed: {e}")
            # Return reasonable default
            return 300000

    def _wait_for_transaction(
        self, tx_hash: str, timeout: int = 300
    ) -> Dict[str, Any]:
        """
        Wait for transaction confirmation.
        
        Args:
            tx_hash: Transaction hash
            timeout: Maximum time to wait in seconds
            
        Returns:
            Transaction receipt
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)

                # Check if we have enough confirmations
                if receipt['blockNumber'] is not None:
                    current_block = self.w3.eth.block_number
                    confirmations = current_block - receipt['blockNumber']

                    if confirmations >= self.confirmation_blocks:
                        logger.info(
                            f"Transaction {tx_hash} confirmed with "
                            f"{confirmations} confirmations"
                        )
                        return receipt

                    logger.debug(
                        f"Waiting for confirmations: {confirmations}/"
                        f"{self.confirmation_blocks}"
                    )
            except TransactionNotFound:
                logger.debug(f"Transaction {tx_hash} not yet mined")

            time.sleep(2)

        raise TimeoutError(
            f"Transaction {tx_hash} not confirmed within {timeout} seconds"
        )

    def _calculate_min_amount_out(
        self, expected_amount: Decimal, slippage_bps: Optional[int] = None
    ) -> Decimal:
        """
        Calculate minimum amount out with slippage tolerance.
        
        Args:
            expected_amount: Expected output amount
            slippage_bps: Slippage tolerance in basis points (overrides default)
            
        Returns:
            Minimum acceptable amount
        """
        slippage = slippage_bps if slippage_bps is not None else self.slippage_tolerance_bps
        slippage_multiplier = Decimal('1') - (Decimal(slippage) / Decimal('10000'))
        return expected_amount * slippage_multiplier

    def get_balance(self) -> Dict[str, Any]:
        """Get native token balance (ETH, BNB, etc.)."""
        if not self.account:
            return {
                "status": "error",
                "message": "No account configured",
                "balances": {}
            }

        balance_wei = self.w3.eth.get_balance(self.account.address)
        balance_eth = self._from_token_units(balance_wei, 18)

        return {
            "status": "success",
            "balances": {
                "native": float(balance_eth),
                "address": self.account.address,
            }
        }

    def get_token_balance(self, token_address: str) -> Decimal:
        """Get ERC-20 token balance."""
        if not self.account:
            raise RuntimeError("No account configured")

        token_contract = self._get_token_contract(token_address)
        decimals = self._get_token_decimals(token_address)
        balance_units = token_contract.functions.balanceOf(
            self.account.address
        ).call()

        return self._from_token_units(balance_units, decimals)
