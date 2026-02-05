#!/usr/bin/env python3
"""Watchlist service: discover symbols via CCXT and persist metadata.

This is a lightweight prototype that normalizes exchange symbol info
and stores it in a local SQLite DB (fallback). It is designed to be
expanded for production (Postgres, robust schema, migrations).
"""

from typing import List, Dict, Any, Optional
import ccxt
import sqlite3
import time
import json
import os


class WatchlistService:
    def __init__(self, db_path: str = "watchlist.db"):
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        need_init = not os.path.exists(self.db_path)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        if need_init:
            self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange TEXT NOT NULL,
                symbol TEXT NOT NULL,
                base TEXT,
                quote TEXT,
                info JSON,
                last_update INTEGER
            )
            """)
        cur.execute("CREATE INDEX idx_exchange_symbol ON symbols(exchange, symbol)")
        self.conn.commit()

    def discover_exchange(
        self, exchange_id: str, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Query CCXT for exchange markets and return normalized symbol metadata."""
        exchange_cls = getattr(ccxt, exchange_id)
        exchange = exchange_cls({"enableRateLimit": True})
        markets = exchange.load_markets()
        results = []
        for i, (symbol, meta) in enumerate(markets.items()):
            base = meta.get("base") or symbol.split("/")[0]
            quote = meta.get("quote") or symbol.split("/")[-1]
            entry = {
                "exchange": exchange_id,
                "symbol": symbol,
                "base": base,
                "quote": quote,
                "info": meta,
                "last_update": int(time.time()),
            }
            results.append(entry)
            if limit and i + 1 >= limit:
                break
        return results

    def persist_symbols(self, entries: List[Dict[str, Any]]):
        cur = self.conn.cursor()
        for e in entries:
            cur.execute(
                "SELECT id FROM symbols WHERE exchange=? AND symbol=?",
                (e["exchange"], e["symbol"]),
            )
            row = cur.fetchone()
            info_json = json.dumps(e.get("info", {}))
            if row:
                cur.execute(
                    "UPDATE symbols SET base=?, quote=?, info=?, last_update=? WHERE id=?",
                    (e["base"], e["quote"], info_json, e["last_update"], row["id"]),
                )
            else:
                cur.execute(
                    "INSERT INTO symbols (exchange, symbol, base, quote, info, last_update) VALUES (?,?,?,?,?,?)",
                    (
                        e["exchange"],
                        e["symbol"],
                        e["base"],
                        e["quote"],
                        info_json,
                        e["last_update"],
                    ),
                )
        self.conn.commit()

    def get_symbols(
        self, exchange: Optional[str] = None, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        if exchange:
            cur.execute(
                "SELECT * FROM symbols WHERE exchange=? ORDER BY symbol LIMIT ?",
                (exchange, limit or -1),
            )
        else:
            cur.execute(
                "SELECT * FROM symbols ORDER BY exchange, symbol LIMIT ?",
                (limit or -1,),
            )
        rows = cur.fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "exchange": r["exchange"],
                    "symbol": r["symbol"],
                    "base": r["base"],
                    "quote": r["quote"],
                    "info": json.loads(r["info"]) if r["info"] else {},
                    "last_update": r["last_update"],
                }
            )
        return out


def _demo():
    svc = WatchlistService()
    # DEX discovery demo - using DeFi tokens
    entries = svc.discover_exchange("uniswap", limit=50)
    svc.persist_symbols(entries)
    print(f"Persisted {len(entries)} symbols from DEX")


if __name__ == "__main__":
    _demo()
