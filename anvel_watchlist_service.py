"""Watchlist management for ANVEL.

This module discovers tradable symbols across multiple exchanges using CCXT,
filters them by configurable liquidity thresholds, and persists a curated
watchlist that downstream components (strategy core, trade engine) can consume.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    import ccxt  # type: ignore
except ImportError:  # pragma: no cover - optional dependency for tests
    ccxt = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass
class WatchlistEntry:
    """Normalized representation of a trading pair."""

    symbol: str
    base: str
    quote: str
    exchange: str
    active: bool
    info: Dict[str, Any]


class WatchlistService:
    """Manage discovery, filtering, and persistence of tradable symbols."""

    def __init__(
        self,
        exchanges: Iterable[str],
        min_daily_volume: float = 1_000_000.0,
        min_price: float = 0.01,
        max_pairs: int = 120,
        storage_path: Path = Path("data/watchlist.json"),
        exchange_factory: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self.exchanges = list(exchanges)
        self.min_daily_volume = min_daily_volume
        self.min_price = min_price
        self.max_pairs = max_pairs
        self.storage_path = storage_path
        self.exchange_factory = exchange_factory or self._default_exchange_factory
        self.current_watchlist: List[WatchlistEntry] = []
        self.last_refreshed: Optional[float] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def refresh(self) -> List[WatchlistEntry]:
        """Discover and persist the latest watchlist."""

        aggregated: List[WatchlistEntry] = []
        for exchange_id in self.exchanges:
            try:
                aggregated.extend(self._collect_from_exchange(exchange_id))
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Watchlist refresh failed for exchange %s", exchange_id
                )
                continue

        aggregated = self._deduplicate(aggregated)
        aggregated = self._rank_and_trim(aggregated)

        self.current_watchlist = aggregated
        self.last_refreshed = time.time()
        self._persist()

        return aggregated

    def load(self) -> List[WatchlistEntry]:
        """Load watchlist from storage if present."""

        if not self.storage_path.exists():
            return []

        with self.storage_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        entries = [
            WatchlistEntry(**entry)  # type: ignore[arg-type]
            for entry in payload.get("entries", [])
        ]
        self.current_watchlist = entries
        self.last_refreshed = payload.get("timestamp")
        return entries

    def get_watchlist(self) -> List[WatchlistEntry]:
        """Return the in-memory watchlist, refreshing from disk if empty."""

        if not self.current_watchlist:
            self.load()
        return list(self.current_watchlist)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _collect_from_exchange(self, exchange_id: str) -> List[WatchlistEntry]:
        exchange = self.exchange_factory(exchange_id)
        markets = exchange.load_markets()  # network call
        entries: List[WatchlistEntry] = []

        for market in markets.values():
            if not market.get("active", True):
                continue
            if market.get("type") and market["type"] != "spot":
                continue

            quote_volume = market.get("info", {}).get("quoteVolume")
            base_volume = market.get("info", {}).get("baseVolume")
            volume = self._coerce_float(quote_volume or base_volume or 0.0)
            if volume < self.min_daily_volume:
                continue

            last_price = self._coerce_float(market.get("info", {}).get("last"))
            if last_price < self.min_price:
                continue

            entry = WatchlistEntry(
                symbol=market.get("symbol"),
                base=market.get("base"),
                quote=market.get("quote"),
                exchange=exchange_id,
                active=market.get("active", True),
                info={
                    "last": last_price,
                    "volume": volume,
                    "precision": market.get("precision"),
                    "limits": market.get("limits"),
                },
            )
            entries.append(entry)

        return entries

    def _deduplicate(self, entries: List[WatchlistEntry]) -> List[WatchlistEntry]:
        deduped: Dict[str, WatchlistEntry] = {}
        for entry in entries:
            key = f"{entry.exchange}:{entry.symbol}"
            if key not in deduped:
                deduped[key] = entry
        return list(deduped.values())

    def _rank_and_trim(self, entries: List[WatchlistEntry]) -> List[WatchlistEntry]:
        ranked = sorted(
            entries,
            key=lambda entry: entry.info.get("volume", 0.0),
            reverse=True,
        )
        return ranked[: self.max_pairs]

    def _persist(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "timestamp": self.last_refreshed,
            "entries": [asdict(entry) for entry in self.current_watchlist],
            "summary": {
                "exchange_breakdown": self.exchange_breakdown(self.current_watchlist)
            },
        }
        with self.storage_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    @staticmethod
    def exchange_breakdown(entries: List[WatchlistEntry]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entry in entries:
            counts.setdefault(entry.exchange, 0)
            counts[entry.exchange] += 1
        return counts

    @staticmethod
    def _coerce_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _default_exchange_factory(exchange_id: str) -> Any:
        if ccxt is None:
            msg = "ccxt is required for default exchange access"
            raise RuntimeError(msg)
        if not hasattr(ccxt, exchange_id):
            raise ValueError(f"Unknown exchange: {exchange_id}")
        exchange_class = getattr(ccxt, exchange_id)
        return exchange_class({"enableRateLimit": True})


def summarize_watchlist(entries: List[WatchlistEntry]) -> Dict[str, Any]:
    """Generate handy statistics for reporting layers."""

    breakdown = WatchlistService.exchange_breakdown(entries)
    top_volume = entries[0].info.get("volume", 0.0) if entries else 0.0
    return {
        "total_pairs": len(entries),
        "exchanges": breakdown,
        "top_volume": top_volume,
    }


__all__ = ["WatchlistService", "WatchlistEntry", "summarize_watchlist"]
