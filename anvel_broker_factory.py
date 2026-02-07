#!/usr/bin/env python3
"""
Unified Broker Factory
======================
Single entry point for creating broker instances.
VEL is DEX-only — all trade execution goes through DEX brokers.

CEX POLICY: Centralized exchange integrations have been removed to enforce
DEX-only trading. Price data should be obtained from on-chain oracles or
DEX pools directly.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


class BrokerFactory:
    """Unified broker factory for VEL.

    Trade execution is DEX-only. ``create_dex`` is the primary method.

    CEX POLICY: Centralized exchange integrations have been removed.
    Price discovery should use on-chain data from DEX pools or oracles.
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
    # CEX data feeds removed - Use DEX/on-chain price discovery
    # ------------------------------------------------------------------

    @staticmethod
    def create_data_feed(source: str, **kwargs: Any) -> Any:
        """DEPRECATED: CEX data feeds have been removed.

        VEL enforces DEX-only trading. Price discovery should use on-chain
        data from DEX pools or decentralized oracles (e.g., Chainlink).

        Raises
        ------
        NotImplementedError
            Always raised. CEX integrations are no longer supported.
        """
        raise NotImplementedError(
            f"CEX data feed '{source}' is no longer supported. "
            "VEL enforces DEX-only trading. Use on-chain price discovery "
            "from DEX pools or decentralized oracles instead."
        )

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @staticmethod
    def list_dexes(**kwargs: Any) -> List[str]:
        """Return available DEX identifiers."""
        try:
            from anvel_dex_broker_factory import list_available_dexes
            return list_available_dexes(**kwargs)
        except ImportError:
            return []

    @staticmethod
    def list_chains() -> List[int]:
        """Return available blockchain identifiers."""
        try:
            from anvel_dex_broker_factory import list_available_chains
            return list_available_chains()
        except ImportError:
            return []
