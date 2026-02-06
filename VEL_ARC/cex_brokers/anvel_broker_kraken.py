#!/usr/bin/env python3
"""
Kraken Market Data Adapter
===========================
Read-only price feed adapter using the public Kraken REST API.
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


class KrakenBroker(BrokerBase):
    """Read-only Kraken price feed adapter.

    Uses the public Kraken REST API for ticker data.
    No authentication required for public market data endpoints.
    """

    name = "kraken"
    BASE_URL = "https://api.kraken.com/0/public"

    # Kraken uses non-standard pair names for some assets
    _PAIR_MAP: Dict[str, str] = {
        "BTC": "XXBTZUSD",
        "ETH": "XETHZUSD",
        "XRP": "XXRPZUSD",
        "LTC": "XLTCZUSD",
        "ADA": "ADAUSD",
        "SOL": "SOLUSD",
        "DOT": "DOTUSD",
        "DOGE": "XDGUSD",
        "AVAX": "AVAXUSD",
        "LINK": "LINKUSD",
        "MATIC": "MATICUSD",
        "UNI": "UNIUSD",
        "ATOM": "ATOMUSD",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        super().__init__(api_key, api_secret)
        self._session = _requests.Session() if _requests else None
        self._rate_limit_delay = float(os.getenv("KRAKEN_RATE_LIMIT", "0.2"))

    # ------------------------------------------------------------------
    # Market data (read-only)
    # ------------------------------------------------------------------

    def _kraken_pair(self, symbol: str) -> str:
        sym = symbol.upper()
        return self._PAIR_MAP.get(sym, f"{sym}USD")

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Fetch best bid/ask for *symbol* from Kraken public ticker."""
        pair = self._kraken_pair(symbol)
        try:
            if self._session is None:
                return self._unavailable(symbol, "requests library not installed")
            resp = self._session.get(
                f"{self.BASE_URL}/Ticker",
                params={"pair": pair},
                timeout=5,
            )
            if resp.status_code != 200:
                return self._unavailable(symbol, f"HTTP {resp.status_code}")
            body = resp.json()
            if body.get("error"):
                return self._unavailable(symbol, str(body["error"]))
            result = body.get("result", {})
            if not result:
                return self._unavailable(symbol, "empty result")
            ticker = next(iter(result.values()))
            time.sleep(self._rate_limit_delay)
            return {
                "symbol": symbol.upper(),
                "bid": float(ticker["b"][0]) if "b" in ticker else None,
                "ask": float(ticker["a"][0]) if "a" in ticker else None,
                "last": float(ticker["c"][0]) if "c" in ticker else None,
                "volume": float(ticker["v"][1]) if "v" in ticker else None,
                "source": "kraken",
                "status": "ok",
            }
        except Exception as exc:
            logger.debug("Kraken quote error for %s: %s", symbol, exc)
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
            "source": "kraken",
            "status": "unavailable",
            "message": reason,
        }
