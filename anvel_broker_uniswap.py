#!/usr/bin/env python3
"""
ANVEL Uniswap V3 DEX Broker

Provides decentralized trading on Uniswap V3 with:
- Direct on-chain order execution
- Multi-hop routing for optimal prices
- Concentrated liquidity position management
- MEV protection via slippage limits
- Gas optimization

Production-critical module for decentralized trading.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional
from web3 import Web3
from anvel_broker_dex_base import DEXBrokerBase
from vel_token_registry import get_token_registry

logger = logging.getLogger(__name__)


class UniswapV3Broker(DEXBrokerBase):
    """Uniswap V3 DEX broker implementation."""

    name = "uniswap_v3"

    # Uniswap V3 contract addresses (Ethereum mainnet)
    ROUTER_ADDRESS = "0xE592427A0AEce92De3Edee1F18E0157C05861564"  # SwapRouter
    QUOTER_ADDRESS = "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6"  # QuoterV2
    FACTORY_ADDRESS = "0x1F98431c8aD98523631AE4a59f267346ea31F984"

    # Common fee tiers (in hundredths of basis points)
    FEE_LOW = 500      # 0.05%
    FEE_MEDIUM = 3000  # 0.3%
    FEE_HIGH = 10000   # 1%

    # Uniswap V3 SwapRouter ABI (simplified)
    ROUTER_ABI = [
        {
            "inputs": [
                {
                    "components": [
                        {"internalType": "address", "name": "tokenIn", "type": "address"},
                        {"internalType": "address", "name": "tokenOut", "type": "address"},
                        {"internalType": "uint24", "name": "fee", "type": "uint24"},
                        {"internalType": "address", "name": "recipient", "type": "address"},
                        {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                        {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                        {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                        {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
                    ],
                    "internalType": "struct ISwapRouter.ExactInputSingleParams",
                    "name": "params",
                    "type": "tuple",
                }
            ],
            "name": "exactInputSingle",
            "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
            "stateMutability": "payable",
            "type": "function",
        },
        {
            "inputs": [
                {
                    "components": [
                        {"internalType": "bytes", "name": "path", "type": "bytes"},
                        {"internalType": "address", "name": "recipient", "type": "address"},
                        {"internalType": "uint256", "name": "deadline", "type": "uint256"},
                        {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                        {"internalType": "uint256", "name": "amountOutMinimum", "type": "uint256"},
                    ],
                    "internalType": "struct ISwapRouter.ExactInputParams",
                    "name": "params",
                    "type": "tuple",
                }
            ],
            "name": "exactInput",
            "outputs": [{"internalType": "uint256", "name": "amountOut", "type": "uint256"}],
            "stateMutability": "payable",
            "type": "function",
        },
    ]

    # QuoterV2 ABI (simplified)
    QUOTER_ABI = [
        {
            "inputs": [
                {"internalType": "address", "name": "tokenIn", "type": "address"},
                {"internalType": "address", "name": "tokenOut", "type": "address"},
                {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
                {"internalType": "uint24", "name": "fee", "type": "uint24"},
                {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
            ],
            "name": "quoteExactInputSingle",
            "outputs": [
                {"internalType": "uint256", "name": "amountOut", "type": "uint256"},
                {"internalType": "uint160", "name": "sqrtPriceX96After", "type": "uint160"},
                {"internalType": "uint32", "name": "initializedTicksCrossed", "type": "uint32"},
                {"internalType": "uint256", "name": "gasEstimate", "type": "uint256"},
            ],
            "stateMutability": "nonpayable",
            "type": "function",
        },
    ]

    def __init__(
        self,
        rpc_url: str,
        private_key: Optional[str] = None,
        chain_id: int = 1,
        router_address: Optional[str] = None,
        quoter_address: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Initialize Uniswap V3 broker.
        
        Args:
            rpc_url: Web3 RPC endpoint URL
            private_key: Private key for signing transactions
            chain_id: Blockchain chain ID (1=Ethereum mainnet)
            router_address: Custom router address (defaults to mainnet)
            quoter_address: Custom quoter address (defaults to mainnet)
            **kwargs: Additional arguments passed to DEXBrokerBase
        
        Note:
            Contract instances are lazy-initialized to avoid network calls
            during import/build time.
        """
        super().__init__(rpc_url, private_key, chain_id, **kwargs)

        # Use custom addresses if provided, otherwise use mainnet defaults
        self.router_address = router_address or self.ROUTER_ADDRESS
        self.quoter_address = quoter_address or self.QUOTER_ADDRESS

        # Lazy-initialized contracts (no network call at init time)
        self._router = None
        self._quoter = None

        logger.info(
            f"Uniswap V3 broker configured for chain {chain_id}, "
            f"router={self.router_address} (connection deferred)"
        )

    @property
    def router(self):
        """Lazy-initialized router contract."""
        if self._router is None:
            self._router = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.router_address),
                abi=self.ROUTER_ABI
            )
        return self._router

    @property
    def quoter(self):
        """Lazy-initialized quoter contract."""
        if self._quoter is None:
            self._quoter = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.quoter_address),
                abi=self.QUOTER_ABI
            )
        return self._quoter

    def get_quote(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        fee_tier: int = FEE_MEDIUM,
    ) -> Dict[str, Any]:
        """
        Get quote for swapping tokens.
        
        Args:
            token_in: Input token address
            token_out: Output token address
            amount_in: Input amount (human-readable)
            fee_tier: Fee tier (500, 3000, or 10000)
            
        Returns:
            Quote information including expected output amount
        """
        try:
            # Get token decimals
            decimals_in = self._get_token_decimals(token_in)
            decimals_out = self._get_token_decimals(token_out)

            # Convert to token units
            amount_in_units = self._to_token_units(amount_in, decimals_in)

            # Get quote from Quoter contract
            result = self.quoter.functions.quoteExactInputSingle(
                Web3.to_checksum_address(token_in),
                Web3.to_checksum_address(token_out),
                amount_in_units,
                fee_tier,
                0  # sqrtPriceLimitX96 = 0 means no limit
            ).call()

            amount_out_units = result[0]
            amount_out = self._from_token_units(amount_out_units, decimals_out)

            # Calculate price
            price = amount_out / amount_in if amount_in > 0 else Decimal('0')

            return {
                "status": "success",
                "source": self.name,
                "token_in": token_in,
                "token_out": token_out,
                "amount_in": float(amount_in),
                "amount_out": float(amount_out),
                "price": float(price),
                "fee_tier": fee_tier,
                "gas_estimate": result[3],
            }
        except Exception as e:
            logger.error(f"Failed to get quote: {e}")
            return {
                "status": "error",
                "source": self.name,
                "message": str(e),
            }

    def submit_order(
        self,
        symbol: str,  # Format: "TOKENA/TOKENB"
        side: str,
        qty: float,
        price: Optional[float] = None,
        order_type: str = "market",
        fee_tier: int = FEE_MEDIUM,
        slippage_bps: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute swap on Uniswap V3.
        
        Args:
            symbol: Trading pair (e.g., "USDC/WETH")
            side: "buy" or "sell"
            qty: Amount to trade
            price: Ignored for market orders (included for compatibility)
            order_type: Must be "market" (limit orders not supported on DEX)
            fee_tier: Uniswap V3 fee tier (500, 3000, or 10000)
            slippage_bps: Custom slippage tolerance (overrides default)
            
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
                "message": f"Order type '{order_type}' not supported on DEX, use 'market'",
            }

        try:
            # Parse symbol (e.g., "USDC/WETH" or "USDC-WETH")
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
                # Buying token_a with token_b (spend token_b to receive token_a)
                token_in = token_b_addr
                token_out = token_a_addr
                amount_in = Decimal(str(qty))
            elif side.lower() == "sell":
                # Selling token_a for token_b (spend token_a to receive token_b)
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
                fee_tier=fee_tier,
                slippage_bps=slippage_bps,
            )

            # Enrich result with order metadata
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

    def execute_swap(
        self,
        token_in: str,
        token_out: str,
        amount_in: Decimal,
        fee_tier: int = FEE_MEDIUM,
        slippage_bps: Optional[int] = None,
        deadline_seconds: int = 300,
    ) -> Dict[str, Any]:
        """
        Execute single-hop swap on Uniswap V3.
        
        Args:
            token_in: Input token address
            token_out: Output token address
            amount_in: Input amount (human-readable)
            fee_tier: Fee tier (500, 3000, or 10000)
            slippage_bps: Slippage tolerance in basis points
            deadline_seconds: Transaction deadline in seconds from now
            
        Returns:
            Swap execution result with transaction hash
        """
        if not self.account:
            raise RuntimeError("Cannot execute swap without private key")

        try:
            # Get quote first to determine expected output
            quote = self.get_quote(token_in, token_out, amount_in, fee_tier)
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

            # Build swap parameters
            swap_params = {
                'tokenIn': Web3.to_checksum_address(token_in),
                'tokenOut': Web3.to_checksum_address(token_out),
                'fee': fee_tier,
                'recipient': self.account.address,
                'deadline': deadline,
                'amountIn': amount_in_units,
                'amountOutMinimum': min_amount_out_units,
                'sqrtPriceLimitX96': 0,  # No price limit
            }

            # Build transaction
            swap_tx = self.router.functions.exactInputSingle(
                swap_params
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
                f"Swap transaction sent: {tx_hash.hex()}, "
                f"in={amount_in} {token_in}, expected_out={expected_amount_out} {token_out}"
            )

            # Wait for confirmation
            receipt = self._wait_for_transaction(tx_hash.hex())

            if receipt['status'] != 1:
                raise RuntimeError(f"Swap transaction failed: {tx_hash.hex()}")

            logger.info(f"Swap confirmed: {tx_hash.hex()}")

            return {
                "status": "success",
                "tx_hash": tx_hash.hex(),
                "approval_tx": approval_tx,
                "token_in": token_in,
                "token_out": token_out,
                "amount_in": float(amount_in),
                "expected_amount_out": float(expected_amount_out),
                "min_amount_out": float(min_amount_out),
                "fee_tier": fee_tier,
                "gas_used": receipt['gasUsed'],
                "block_number": receipt['blockNumber'],
            }

        except Exception as e:
            logger.error(f"Swap execution failed: {e}")
            return {
                "status": "error",
                "message": str(e),
            }

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get current price for a trading pair.
        
        Resolves token symbols to addresses via the registry, then
        fetches a quote for 1 unit of token_a to derive the price.
        """
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
                    "bid": quote["price"],  # DEX price is symmetric minus fees
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
