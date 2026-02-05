#!/usr/bin/env python3
"""CLI runner for the WatchlistService."""

import argparse
from anvel_watchlist import WatchlistService


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--exchange", "-e", default="binance", help="CCXT exchange id to query"
    )
    p.add_argument("--limit", "-n", type=int, default=100, help="Max symbols to fetch")
    p.add_argument("--db", default="watchlist.db", help="Path to watchlist DB")
    args = p.parse_args()

    svc = WatchlistService(db_path=args.db)
    print(f"Discovering symbols on {args.exchange} (limit={args.limit})...")
    entries = svc.discover_exchange(args.exchange, limit=args.limit)
    svc.persist_symbols(entries)
    print(f"Persisted {len(entries)} symbols to {args.db}")


if __name__ == "__main__":
    main()
