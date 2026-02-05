#!/usr/bin/env python3
"""CLI helper to refresh the ANVEL watchlist."""

import argparse
import logging
from pathlib import Path

from anvel_watchlist_service import WatchlistService, summarize_watchlist

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("watchlist_sync")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh ANVEL watchlist")
    parser.add_argument(
        "--exchanges",
        nargs="+",
        default=["binance", "kraken", "coinbase"],
        help="Exchange ids supported by CCXT",
    )
    parser.add_argument(
        "--min-volume",
        type=float,
        default=1_000_000.0,
        help="Minimum 24h quote volume required to include a symbol",
    )
    parser.add_argument(
        "--min-price",
        type=float,
        default=0.01,
        help="Minimum last price to include a symbol",
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=120,
        help="Maximum number of pairs to keep in watchlist",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/watchlist.json"),
        help="Destination for watchlist JSON payload",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    service = WatchlistService(
        exchanges=args.exchanges,
        min_daily_volume=args.min_volume,
        min_price=args.min_price,
        max_pairs=args.max_pairs,
        storage_path=args.output,
    )
    entries = service.refresh()
    summary = summarize_watchlist(entries)
    logger.info(
        "Watchlist refreshed: %d pairs across %d exchanges (top volume %.2f)",
        summary["total_pairs"],
        len(summary["exchanges"]),
        summary["top_volume"],
    )


if __name__ == "__main__":
    main()
