#!/usr/bin/env python3
"""
ANVEL PancakeSwap V2 DEX Broker

Provides decentralized trading on PancakeSwap (BSC) with:
- Constant product AMM swaps
- Multi-hop routing
- CAKE rewards integration
- Low fees optimized for BSC
- Fast finality

Production-critical module for BSC decentralized trading.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional
from web3 import Web3
from anvel_broker_dex_base import DEXBrokerBase
from vel_token_registry import get_token_registry

logger = logging.getLogger(__name__)


class PancakeSwapBroker(DEXBrokerBase):
    """PancakeSwap V2 DEX broker implementation."""

    name = "pancakeswap_v2"

    # PancakeSwap contract addresses (BSC mainnet)
    ROUTER_ADDRESS = "0x10ED43C718714eb63d5aA57B78B54704E256024E"  # PancakeSwap Router V2
    FACTORY_ADDRESS = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"
    WBNB_ADDRESS = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"  # Wrapped BNB

    # PancakeSwap Router V2 ABI (simplified)
    ROUTER_ABI = [
        {
            "inputs": [
                {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                {"internalType": "address[]", "name": "path", "type": "address[]"},
                {"internalType": "address", "name": "to", "type": "address"},
                {"internalType": "uint256", "name": "deadline", "type": "uint256"},
            ],
            "name": "swapExactTokensForTokens",
            "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
            "stateMutability": "nonpayable",
            "type": "function",
        },
        {
            "inputs": [
                {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                {"internalType": "address[]", "name": "path", "type": "address[]"},
            ],
            "name": "getAmountsOut",
            "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [
                {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
                {"internalType": "address[]", "name": "path", "type": "address[]"},
            ],
            "name": "getAmountsIn",
            "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [
                {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                {"internalType": "address[]", "name": "path", "type": "address[]"},
                {"internalType": "address", "name": "to", "type": "address"},
                {"internalType": "uint256", "name": "deadline", "type": "uint256"},
            ],
            "name": "swapExactETHForTokens",
            "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
            "stateMutability": "payable",
            "type": "function",
        },
        {
            "inputs": [
                {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
                {"internalType": "address[]", "name": "path", "type": "address[]"},
                {"internalType": "address", "name": "to", "type": "address"},
                {"internalType": "uint256", "name": "deadline", "type": "uint256"},
            ],
            "name": "swapExactTokensForETH",
            "outputs": [{"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}],
            "stateMutability": "nonpayable",
            "type": "function",
        },
    ]

    def __init__(
        self,
        rpc_url: str = "https://bsc-dataseed1.binance.org/",
        private_key: Optional[str] = None,
        chain_id: int = 56,  # BSC mainnet
        router_address: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Initialize PancakeSwap broker.
        
        Args:
            rpc_url: BSC RPC endpoint URL
            private_key: Private key for signing transactions
            chain_id: Blockchain chain ID (56=BSC mainnet, 97=BSC testnet)
            router_address: Custom router address (defaults to mainnet)
            **kwargs: Additional arguments passed to DEXBrokerBase
        """
        # Set BSC-optimized defaults if not provided
        if 'max_gas_price_gwei' not in kwargs:
            kwargs['max_gas_price_gwei'] = Decimal("5")  # BSC has much lower gas
        if 'slippage_tolerance_bps' not in kwargs:
            kwargs['slippage_tolerance_bps'] = 100  # 1% for BSC volatility
        if 'confirmation_blocks' not in kwargs:
            kwargs['confirmation_blocks'] = 3  # BSC has ~3s blocks

        super().__init__(rpc_url, private_key, chain_id, **kwargs)

        # Use custom address if provided, otherwise use mainnet default
        self.router_address = router_address or self.ROUTER_ADDRESS

        # Initialize router contract
        self.router = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.router_address),
            abi=self.ROUTER_ABI
        )

        logger.info(
            f"PancakeSwap broker initialized on BSC chain {chain_id}, "
            f"router={self.router_address}"
        )

    def get_quote(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        path: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Get quote for swapping tokens.
        
        Args:
            token_in: Input token address
            token_out: Output token address
            amount_in: Input amount (human-readable)
            path: Custom routing path (defaults to direct swap)
            
        Returns:
            Quote information including expected output amount
        """
        try:
            # Get token decimals
            decimals_in = self._get_token_decimals(token_in)
            decimals_out = self._get_token_decimals(token_out)

            # Convert to token units
            amount_in_units = self._to_token_units(amount_in, decimals_in)

            # Build path (default to direct swap)
            if path is None:
                path = [
                    Web3.to_checksum_address(token_in),
                    Web3.to_checksum_address(token_out)
                ]
            else:
                path = [Web3.to_checksum_address(addr) for addr in path]

            # Get amounts out from router
            amounts = self.router.functions.getAmountsOut(
                amount_in_units,
                path
            ).call()

            # Last element is the output amount
            amount_out_units = amounts[-1]
            amount_out = self._from_token_units(amount_out_units, decimals_out)

            # Calculate price
            price = amount_out / amount_in if amount_in > 0 else Decimal('0')

            # Calculate price impact (approximate)
            # In V2, price impact = (amount_out / amount_in) - market_price
            # For simplicity, we return the effective price

            return {
                "status": "success",
                "source": self.name,
                "token_in": token_in,
                "token_out": token_out,
                "amount_in": float(amount_in),
                "amount_out": float(amount_out),
                "price": float(price),
                "path": path,
                "path_amounts": [float(self._from_token_units(amt, decimals_in if i == 0 else decimals_out))
                                 for i, amt in enumerate(amounts)],
            }
        except Exception as e:
            logger.error(f"Failed to get quote: {e}")
            return {
                "status": "error",
                "source": self.name,
                "message": str(e),
            }

    def execute_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        slippage_bps: Optional[int] = None,
        deadline_seconds: int = 300,
        path: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute swap on PancakeSwap V2.
        
        Args:
            token_in: Input token address
            token_out: Output token address
            amount_in: Input amount (human-readable)
            slippage_bps: Slippage tolerance in basis points
            deadline_seconds: Transaction deadline in seconds from now
            path: Custom routing path (defaults to direct swap or via WBNB)
            
        Returns:
            Swap execution result with transaction hash
        """
        if not self.account:
            raise RuntimeError("Cannot execute swap without private key")

        try:
            # Build optimal path if not provided
            if path is None:
                # Try direct swap first
                try:
                    quote_direct = self.get_quote(token_in, token_out, amount_in, None)
                    if quote_direct['status'] == 'success':
                        path = [token_in, token_out]
                except:
                    import logging as _lg  # noqa: E402
                    _lg.getLogger("ANVEL_BROKER_PANCAKESWAP").debug("Exception suppressed in execute_swap")

                # If direct doesn't work, try via WBNB
                if path is None:
                    path = [token_in, self.WBNB_ADDRESS, token_out]

            # Get quote to determine expected output
            quote = self.get_quote(token_in, token_out, amount_in, path)
            if quote['status'] != 'success':
                raise RuntimeError(f"Quote failed: {quote.get('message')}")

            expected_amount_out = Decimal(str(quote['amount_out']))

            # Calculate minimum amount out with slippage protection
            min_amount_out = self._calculate_min_amount_out(
                expected_amount_out, slippage_bps
            )

            # Get token decimals and convert amounts
            decimals_in = self._get_token_decimals(token_in)
            decimals_out = self._get_token_decimals(token_out)
            amount_in_units = self._to_token_units(amount_in, decimals_in)
            min_amount_out_units = self._to_token_units(min_amount_out, decimals_out)

            # Check and approve token if needed
            approval_tx = self._check_and_approve_token(
                token_in, self.router_address, amount_in_units
            )

            # Calculate deadline
            deadline = self.w3.eth.get_block('latest')['timestamp'] + deadline_seconds

            # Convert path to checksummed addresses
            path_checksummed = [Web3.to_checksum_address(addr) for addr in path]

            # Build transaction
            swap_tx = self.router.functions.swapExactTokensForTokens(
                amount_in_units,
                min_amount_out_units,
                path_checksummed,
                self.account.address,
                deadline
            ).build_transaction({
                'from': self.account.address,
                'nonce': self.w3.eth.get_transaction_count(self.account.address),
                'gas': self._estimate_gas({
                    'from': self.account.address,
                    'to': self.router_address,
                    'value': 0,
                }),
                'gasPrice': self._get_gas_price(),
                'chainId': self.chain_id,
            })

            # Sign and send
            signed_tx = self.account.sign_transaction(swap_tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            logger.info(
                f"PancakeSwap swap transaction sent: {tx_hash.hex()}, "
                f"in={amount_in} {token_in}, expected_out={expected_amount_out} {token_out}"
            )

            # Wait for confirmation
            receipt = self._wait_for_transaction(tx_hash.hex())

            if receipt['status'] != 1:
                raise RuntimeError(f"Swap transaction failed: {tx_hash.hex()}")

            logger.info(f"PancakeSwap swap confirmed: {tx_hash.hex()}")

            return {
                "status": "success",
                "tx_hash": tx_hash.hex(),
                "approval_tx": approval_tx,
                "token_in": token_in,
                "token_out": token_out,
                "amount_in": float(amount_in),
                "expected_amount_out": float(expected_amount_out),
                "min_amount_out": float(min_amount_out),
                "path": path,
                "gas_used": receipt['gasUsed'],
                "block_number": receipt['blockNumber'],
            }

        except Exception as e:
            logger.error(f"PancakeSwap swap execution failed: {e}")
            return {
                "status": "error",
                "message": str(e),
            }

    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: Optional[float] = None,
        order_type: str = "market",
        slippage_bps: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute swap on PancakeSwap.
        
        Args:
            symbol: Trading pair (e.g., "BUSD/BNB")
            side: "buy" or "sell"
            qty: Amount to trade
            price: Ignored for market orders
            order_type: Must be "market"
            slippage_bps: Custom slippage tolerance
            
        Returns:
            Order execution result
        """
        if not self.account:
            return {
                "status": "error",
                "message": "Cannot execute order without private key",
            }

        if order_type != "market":
            return {
                "status": "error",
                "message": f"Order type '{order_type}' not supported on DEX",
            }

        try:
            # Parse symbol
            tokens = symbol.replace('/', '-').split('-')
            if len(tokens) != 2:
                raise ValueError(f"Invalid symbol format: {symbol}")

            token_a, token_b = tokens[0].strip().upper(), tokens[1].strip().upper()

            # Resolve token addresses via registry
            registry = get_token_registry()
            token_a_addr = registry.resolve_or_raise(token_a, self.chain_id)
            token_b_addr = registry.resolve_or_raise(token_b, self.chain_id)

            # Determine input/output tokens based on side
            if side.lower() == "buy":
                token_in = token_b_addr
                token_out = token_a_addr
                amount_in = Decimal(str(qty))
            elif side.lower() == "sell":
                token_in = token_a_addr
                token_out = token_b_addr
                amount_in = Decimal(str(qty))
            else:
                raise ValueError(f"Invalid side: {side}")

            # Execute the swap via the real on-chain method
            result = self.execute_swap(
                token_in=token_in,
                token_out=token_out,
                amount_in=amount_in,
                slippage_bps=slippage_bps,
            )

            result["symbol"] = symbol
            result["side"] = side
            result["qty"] = qty
            return result

        except Exception as e:
            logger.error(f"Order submission failed: {e}")
            return {
                "status": "error",
                "message": str(e),
            }

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get current price for a trading pair via small quote."""
        try:
            tokens = symbol.replace('/', '-').split('-')
            if len(tokens) != 2:
                raise ValueError(f"Invalid symbol format: {symbol}")

            token_a, token_b = tokens[0].strip().upper(), tokens[1].strip().upper()

            registry = get_token_registry()
            token_a_addr = registry.resolve_or_raise(token_a, self.chain_id)
            token_b_addr = registry.resolve_or_raise(token_b, self.chain_id)

            # Quote 1 unit of token_a for price discovery
            quote = self.get_quote(token_a_addr, token_b_addr, Decimal("1"))

            if quote["status"] == "success":
                return {
                    "status": "success",
                    "symbol": symbol.upper(),
                    "source": self.name,
                    "last": quote["price"],
                    "bid": quote["price"],
                    "ask": quote["price"],
                }

            return {
                "status": "error",
                "symbol": symbol.upper(),
                "source": self.name,
                "message": quote.get("message", "Quote failed"),
            }
        except Exception as e:
            return {
                "status": "error",
                "symbol": symbol.upper(),
                "source": self.name,
                "message": str(e),
            }
