#!/usr/bin/env python3
"""
Unified Broker Factory
======================
Single entry point for creating broker instances.
VEL is DEX-only — all trade execution goes through DEX brokers.
Market data adapters (Coinbase, Kraken) are read-only price feeds.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BrokerFactory:
    """Unified broker factory for VEL.

    Trade execution is DEX-only. ``create_dex`` is the primary method.
    ``create_data_feed`` provides read-only market data adapters for
    price discovery and strategy signals.
    """

    # ------------------------------------------------------------------
    # DEX broker creation (for trade execution)
    # ------------------------------------------------------------------

    @staticmethod
    def create_dex(
        dex_id: str,
        rpc_url: Optional[str] = None,
        private_key: Optional[str] = None,
        max_gas_price_gwei: Optional[Decimal] = None,
        slippage_tolerance_bps: int = 50,
        **kwargs: Any,
    ) -> Any:
        """Create a DEX broker instance.

        Delegates to :class:`anvel_dex_broker_factory.DEXBrokerFactory` which
        handles Uniswap V3, PancakeSwap, and other supported DEXes.

        Parameters
        ----------
        dex_id:
            Identifier for the DEX (e.g. ``"uniswap_v3"``, ``"pancakeswap_v2"``).
        rpc_url:
            JSON-RPC endpoint for the target chain.
        private_key:
            Wallet private key for signing transactions.
        max_gas_price_gwei:
            Upper gas-price limit.
        slippage_tolerance_bps:
            Maximum acceptable slippage in basis points (default 50 = 0.5%).
        """
        try:
            from anvel_dex_broker_factory import get_dex_broker

            return get_dex_broker(
                dex_id,
                rpc_url=rpc_url,
                private_key=private_key,
                max_gas_price_gwei=max_gas_price_gwei,
                slippage_tolerance_bps=slippage_tolerance_bps,
                **kwargs,
            )
        except ImportError:
            logger.error(
                "anvel_dex_broker_factory not available — cannot create DEX broker"
            )
            raise
        except Exception:
            logger.exception("Failed to create DEX broker %s", dex_id)
            raise

    # ------------------------------------------------------------------
    # Data-feed adapters (read-only, for price discovery)
    # ------------------------------------------------------------------

    @staticmethod
    def create_data_feed(source: str, **kwargs: Any) -> Any:
        """Create a read-only market data adapter.

        Parameters
        ----------
        source:
            ``"coinbase"`` or ``"kraken"``.
        """
        source_lower = source.lower()
        if source_lower == "coinbase":
            from anvel_broker_coinbase import CoinbaseBroker
            return CoinbaseBroker(**kwargs)
        if source_lower == "kraken":
            from anvel_broker_kraken import KrakenBroker
            return KrakenBroker(**kwargs)
        raise ValueError(f"Unknown data feed source: {source}")

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @staticmethod
    def list_dexes(**kwargs: Any) -> Any:
        """Return available DEX identifiers."""
        try:
            from anvel_dex_broker_factory import list_available_dexes
            return list_available_dexes(**kwargs)
        except ImportError:
            return []

    @staticmethod
    def list_chains() -> Any:
        """Return available blockchain identifiers."""
        try:
            from anvel_dex_broker_factory import list_available_chains
            return list_available_chains()
        except ImportError:
            return []
