#!/usr/bin/env python3
"""
VEL Token Registry
==================
Maps token symbols to on-chain contract addresses across supported chains.
Used by DEX brokers to resolve human-readable symbols (e.g. "WETH")
to EVM addresses for on-chain operations.

The registry is loaded from environment overrides first, then falls back
to the built-in defaults.  Add new tokens via ``register()`` at runtime
or by setting ``VEL_TOKEN_<SYMBOL>_<CHAIN_ID>=0x...`` env vars.

ONLY verified, checksummed mainnet addresses are included.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional, Tuple

from web3 import Web3

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Built-in token addresses (verified mainnet deployments)
# Key: (symbol_upper, chain_id) → checksummed address
# ──────────────────────────────────────────────────────────────────────

_BUILTIN_TOKENS: Dict[Tuple[str, int], str] = {
    # ── Ethereum Mainnet (chain 1) ────────────────────────────────────
    ("WETH",  1): "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    ("USDC",  1): "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    ("USDT",  1): "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    ("DAI",   1): "0x6B175474E89094C44Da98b954EedeAC495271d0F",
    ("WBTC",  1): "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
    ("UNI",   1): "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",
    ("LINK",  1): "0x514910771AF9Ca656af840dff83E8264EcF986CA",
    ("AAVE",  1): "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",
    ("CRV",   1): "0xD533a949740bb3306d119CC777fa900bA034cd52",
    ("MKR",   1): "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2",
    ("COMP",  1): "0xc00e94Cb662C3520282E6f5717214004A7f26888",
    ("SNX",   1): "0xC011a73ee8576Fb46F5E1c5751cA3B9Fe0af2a6F",

    # ── Arbitrum One (chain 42161) ────────────────────────────────────
    ("WETH",  42161): "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    ("USDC",  42161): "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    ("USDT",  42161): "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
    ("DAI",   42161): "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
    ("WBTC",  42161): "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f",
    ("ARB",   42161): "0x912CE59144191C1204E64559FE8253a0e49E6548",

    # ── Optimism (chain 10) ───────────────────────────────────────────
    ("WETH",  10): "0x4200000000000000000000000000000000000006",
    ("USDC",  10): "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
    ("USDT",  10): "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58",
    ("DAI",   10): "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
    ("OP",    10): "0x4200000000000000000000000000000000000042",

    # ── Polygon (chain 137) ───────────────────────────────────────────
    ("WMATIC", 137): "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
    ("WETH",   137): "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
    ("USDC",   137): "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
    ("USDT",   137): "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
    ("DAI",    137): "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",

    # ── Base (chain 8453) ─────────────────────────────────────────────
    ("WETH",  8453): "0x4200000000000000000000000000000000000006",
    ("USDC",  8453): "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    ("DAI",   8453): "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",

    # ── BNB Smart Chain (chain 56) ────────────────────────────────────
    ("WBNB",  56): "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
    ("USDT",  56): "0x55d398326f99059fF775485246999027B3197955",
    ("USDC",  56): "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
    ("BUSD",  56): "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
    ("ETH",   56): "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",
    ("BTCB",  56): "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c",
    ("CAKE",  56): "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",

    # ── Avalanche C-Chain (chain 43114) ───────────────────────────────
    ("WAVAX", 43114): "0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7",
    ("USDC",  43114): "0xB97EF9Ef8734C71904D8002F8b6Bc66Dd9c48a6E",
    ("USDT",  43114): "0x9702230A8Ea53601f5cD2dc00fDBc13d4dF4A8c7",

    # ── zkSync Era (chain 324) ────────────────────────────────────────
    ("WETH",  324): "0x5AEa5775959fBC2557Cc8789bC1bf90A239D9a91",
    ("USDC",  324): "0x1d17CBcF0D6D143135aE902365D2E5e2A16538D4",
}


class TokenRegistry:
    """Resolve token symbols to on-chain addresses.

    Lookup priority:
    1. Runtime overrides added via ``register()``
    2. Environment variables ``VEL_TOKEN_<SYMBOL>_<CHAIN_ID>``
    3. Built-in defaults above
    """

    def __init__(self) -> None:
        self._overrides: Dict[Tuple[str, int], str] = {}
        self._load_env_overrides()

    # ── public API ────────────────────────────────────────────────────

    def resolve(self, symbol: str, chain_id: int) -> Optional[str]:
        """Return the checksummed address for *symbol* on *chain_id*, or ``None``."""
        key = (symbol.upper(), chain_id)

        # 1) runtime override
        addr = self._overrides.get(key)
        if addr:
            return addr

        # 2) env override
        env_key = f"VEL_TOKEN_{symbol.upper()}_{chain_id}"
        env_val = os.getenv(env_key)
        if env_val and Web3.is_address(env_val):
            checksummed = Web3.to_checksum_address(env_val)
            self._overrides[key] = checksummed  # cache for next call
            return checksummed

        # 3) built-in
        return _BUILTIN_TOKENS.get(key)

    def resolve_or_raise(self, symbol: str, chain_id: int) -> str:
        """Like ``resolve`` but raises ``ValueError`` if unresolvable."""
        addr = self.resolve(symbol, chain_id)
        if addr is None:
            raise ValueError(
                f"Unknown token '{symbol}' on chain {chain_id}. "
                f"Register it via VEL_TOKEN_{symbol.upper()}_{chain_id} env var "
                f"or call token_registry.register('{symbol}', {chain_id}, '0x...')"
            )
        return addr

    def register(self, symbol: str, chain_id: int, address: str) -> None:
        """Add or override a token address at runtime."""
        if not Web3.is_address(address):
            raise ValueError(f"Invalid address: {address}")
        checksummed = Web3.to_checksum_address(address)
        self._overrides[(symbol.upper(), chain_id)] = checksummed
        logger.info("Registered token %s on chain %d → %s", symbol, chain_id, checksummed)

    def list_tokens(self, chain_id: Optional[int] = None) -> Dict[str, str]:
        """Return ``{symbol: address}`` for all known tokens, optionally filtered by chain."""
        result: Dict[str, str] = {}
        for (sym, cid), addr in _BUILTIN_TOKENS.items():
            if chain_id is None or cid == chain_id:
                result[f"{sym}:{cid}"] = addr
        for (sym, cid), addr in self._overrides.items():
            if chain_id is None or cid == chain_id:
                result[f"{sym}:{cid}"] = addr
        return result

    # ── internals ─────────────────────────────────────────────────────

    def _load_env_overrides(self) -> None:
        """Scan env for VEL_TOKEN_*_* patterns on import."""
        prefix = "VEL_TOKEN_"
        for key, val in os.environ.items():
            if not key.startswith(prefix):
                continue
            rest = key[len(prefix):]
            # expect SYMBOL_CHAINID, split on last underscore
            parts = rest.rsplit("_", 1)
            if len(parts) != 2:
                continue
            symbol, chain_str = parts
            try:
                chain_id = int(chain_str)
            except ValueError:
                continue
            if Web3.is_address(val):
                self._overrides[(symbol, chain_id)] = Web3.to_checksum_address(val)
                logger.debug("Loaded env token override: %s on chain %d", symbol, chain_id)


# ── global singleton ──────────────────────────────────────────────────

_instance: Optional[TokenRegistry] = None


def get_token_registry() -> TokenRegistry:
    """Return the global ``TokenRegistry`` singleton."""
    global _instance
    if _instance is None:
        _instance = TokenRegistry()
    return _instance


__all__ = [
    "TokenRegistry",
    "get_token_registry",
]
