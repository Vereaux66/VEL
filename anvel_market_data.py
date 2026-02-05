#!/usr/bin/env python3
"""
ANVEL Market Data Service
- Publishes market ticks to event bus
- Maintains rolling price history per symbol for strategy use
- Uses WebSockets when available (env USE_WS=true), else HTTP polling via broker adapters
"""

import collections
import json
import os
import threading
import time

try:
    import asyncio  # type: ignore

    import websockets

    _HAS_WS = True
except Exception:
    _HAS_WS = False

from typing import Dict, List

from anvel_broker_factory import BrokerFactory
from anvel_event_bus import ANVELEventBus


class ANVELMarketData:
    def __init__(
        self,
        event_bus: ANVELEventBus,
        symbols: List[str],
        broker: str = "kraken",
        window: int = 200,
        interval: float = 1.0,
    ):
        self.bus = event_bus
        self.symbols = [s.upper() for s in symbols]
        self.window = window
        self.interval = interval
        self.history: Dict[str, collections.deque] = {
            s: collections.deque(maxlen=window) for s in self.symbols
        }
        self._stop = threading.Event()
        self._thread: threading.Thread = None  # type: ignore
        self.mode = broker.lower()
        # Use BrokerFactory for read-only data feed adapters
        self.data_feed = BrokerFactory.create_data_feed(self.mode)
        self.use_ws = (
            os.getenv("USE_WS", "").lower() in ("1", "true", "yes")
        ) and _HAS_WS

    def latest_prices(self, symbol: str) -> List[float]:
        q = self.history.get(symbol.upper())
        return list(q) if q else []

    def _publish(self, symbol: str, bid: float, ask: float, src: str):
        mid = None
        try:
            if bid is not None and ask is not None:
                mid = (float(bid) + float(ask)) / 2.0
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_MARKET_DATA").debug("Exception suppressed in _publish")
        if mid is not None:
            self.history[symbol].append(mid)
        payload = {
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "source": src,
            "time": time.time(),
        }
        try:
            self.bus.publish("market.tick", payload)
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_MARKET_DATA").debug("Exception suppressed in _publish")

    def _poll_loop(self):
        while not self._stop.is_set():
            start = time.time()
            for s in self.symbols:
                try:
                    q = self.data_feed.get_quote(s)
                    if "bid" in q and "ask" in q:
                        self._publish(
                            s, q.get("bid"), q.get("ask"), q.get("source", "")
                        )
                except Exception:
                    import logging as _lg  # noqa: E402
                    _lg.getLogger("ANVEL_MARKET_DATA").debug("Exception suppressed in _poll_loop")
            elapsed = time.time() - start
            sleep_left = max(0.0, self.interval - elapsed)
            self._stop.wait(sleep_left)

    async def _ws_kraken(self):
        uri = "wss://ws.kraken.com"
        subs = [
            {
                "event": "subscribe",
                "pair": [f"{s}/USD" for s in self.symbols],
                "subscription": {"name": "ticker"},
            }
        ]
        async with websockets.connect(uri, ping_interval=20) as ws:  # type: ignore
            await ws.send(json.dumps(subs[0]))
            while not self._stop.is_set():
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    data = json.loads(msg)
                    if isinstance(data, list) and len(data) >= 2:
                        info = data[1]
                        pair = data[-1]
                        symbol = str(pair).split("/")[0]
                        bid = float(info["b"][0]) if "b" in info else None
                        ask = float(info["a"][0]) if "a" in info else None
                        self._publish(symbol, bid, ask, "kraken-ws")
                except Exception:
                    await asyncio.sleep(1)

    async def _ws_coinbase(self):
        uri = "wss://ws-feed.exchange.coinbase.com"
        subs = {
            "type": "subscribe",
            "product_ids": [f"{s}-USD" for s in self.symbols],
            "channels": [
                {"name": "ticker", "product_ids": [f"{s}-USD" for s in self.symbols]}
            ],
        }
        async with websockets.connect(uri, ping_interval=20) as ws:  # type: ignore
            await ws.send(json.dumps(subs))
            while not self._stop.is_set():
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    data = json.loads(msg)
                    if data.get("type") == "ticker":
                        product = data.get("product_id", "")
                        symbol = product.split("-")[0]
                        bid = (
                            float(data.get("best_bid"))
                            if data.get("best_bid")
                            else None
                        )
                        ask = (
                            float(data.get("best_ask"))
                            if data.get("best_ask")
                            else None
                        )
                        self._publish(symbol, bid, ask, "coinbase-ws")
                except Exception:
                    await asyncio.sleep(1)

    def _ws_loop(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            if self.mode == "kraken":
                loop.run_until_complete(self._ws_kraken())
            else:
                loop.run_until_complete(self._ws_coinbase())
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_MARKET_DATA").debug("Exception suppressed in _ws_loop")

    def startup(self):
        if self.use_ws:
            self._thread = threading.Thread(target=self._ws_loop, daemon=True)
        else:
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        return "[MD] started"

    def shutdown(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        return "[MD] stopped"
