#!/usr/bin/env python3
"""
Coinbase Market Data Adapter
=============================
Read-only price feed adapter using the public Coinbase REST API.
VEL is DEX-only for trade execution — this module only provides
market data quotes for price discovery and strategy signals.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

from anvel_broker_base import BrokerBase

logger = logging.getLogger(__name__)

try:
    import requests as _requests
except ImportError:
    _requests = None  # type: ignore[assignment]


class CoinbaseBroker(BrokerBase):
    """Read-only Coinbase price feed adapter.

    Uses the public Coinbase Exchange REST API for ticker data.
    No authentication required for public market data endpoints.
    """

    name = "coinbase"
    BASE_URL = "https://api.exchange.coinbase.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        super().__init__(api_key, api_secret)
        self._session = _requests.Session() if _requests else None
        self._rate_limit_delay = float(os.getenv("COINBASE_RATE_LIMIT", "0.15"))

    # ------------------------------------------------------------------
    # Market data (read-only)
    # ------------------------------------------------------------------

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Fetch best bid/ask for *symbol* from Coinbase public ticker."""
        product_id = f"{symbol.upper()}-USD"
        try:
            if self._session is None:
                return self._unavailable(symbol, "requests library not installed")
            resp = self._session.get(
                f"{self.BASE_URL}/products/{product_id}/ticker",
                timeout=5,
            )
            if resp.status_code != 200:
                return self._unavailable(symbol, f"HTTP {resp.status_code}")
            data = resp.json()
            time.sleep(self._rate_limit_delay)
            return {
                "symbol": symbol.upper(),
                "bid": float(data["bid"]) if data.get("bid") else None,
                "ask": float(data["ask"]) if data.get("ask") else None,
                "last": float(data["price"]) if data.get("price") else None,
                "volume": float(data["volume"]) if data.get("volume") else None,
                "source": "coinbase",
                "status": "ok",
            }
        except Exception as exc:
            logger.debug("Coinbase quote error for %s: %s", symbol, exc)
            return self._unavailable(symbol, str(exc))

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Alias for get_quote with ticker-style keys."""
        return self.get_quote(symbol)

    # ------------------------------------------------------------------
    # Trade execution — BLOCKED (DEX-only policy)
    # ------------------------------------------------------------------

    def submit_order(self, symbol: str, side: str, qty: float,
                     price: Optional[float] = None,
                     order_type: str = "market") -> Dict[str, Any]:
        return {
            "status": "rejected",
            "reason": "VEL is DEX-only. CEX order execution is disabled.",
            "symbol": symbol,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _unavailable(symbol: str, reason: str) -> Dict[str, Any]:
        return {
            "symbol": symbol.upper(),
            "bid": None,
            "ask": None,
            "source": "coinbase",
            "status": "unavailable",
            "message": reason,
        }
