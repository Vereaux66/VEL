#!/usr/bin/env python3
"""ANVEL Strategy Runner."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from typing import Any, Dict, List, Optional, cast

from anvel_strategy_core import ANVELStrategyCore

try:  # pragma: no cover - optional integration
    from anvel_learning_bridge import LearningStrategyBridge  # type: ignore
except Exception:  # pragma: no cover - fallback when bridge is absent
    LearningStrategyBridge = None  # type: ignore


class ANVELStrategyRunner:
    """Evaluate strategies continuously and publish decisions."""

    def __init__(
        self,
        market_data: Any,
        event_bus: Any,
        symbols: List[str],
        threshold: float = 0.6,
        interval: float = 2.0,
        learning_bridge: Optional[Any] = None,
    ) -> None:
        self.md = market_data
        self.bus = event_bus
        self.symbols = [s.upper() for s in symbols]
        self.interval = interval
        self.core = ANVELStrategyCore()
        self.threshold = threshold
        self._stop = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self.weights: Dict[str, float] = {}
        self.strategy_endpoint = "http://localhost:50054"
        self.use_js = True
        self.learning_bridge: Optional[Any] = None
        self._last_eval: Dict[str, float] = {}

        self._load_strategy_endpoint()
        if learning_bridge is not None:
            self.attach_learning_bridge(learning_bridge)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_strategy_endpoint(self) -> None:
        try:
            if not os.path.exists("anvel_config.json"):
                return
            with open("anvel_config.json", "r", encoding="utf-8") as handle:
                cfg: Dict[str, Any] = json.load(handle)
            system_cfg = cast(Dict[str, Any], cfg.get("system_config") or {})
            hybrid_cfg = cast(Dict[str, Any], system_cfg.get("hybrid") or {})
            endpoint = hybrid_cfg.get("strategy_endpoint")
            if isinstance(endpoint, str) and endpoint.strip():
                self.strategy_endpoint = endpoint.strip()
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_STRATEGY_RUNNER").debug("Exception suppressed in _load_strategy_endpoint")

    def _call_external_strategy(self, prices: List[float]) -> Optional[float]:
        endpoint = self.strategy_endpoint.rstrip("/")
        url = f"{endpoint}/strategy/ensemble"
        try:
            payload = json.dumps({"prices": prices, "weights": self.weights}).encode(
                "utf-8"
            )
            request = urllib.request.Request(url, data=payload, method="POST")
            request.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(request, timeout=2) as response:
                raw = response.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
            value = data.get("score")
            return float(value) if value is not None else None
        except Exception:
            return None

    def _decide(self, context: Dict[str, Any]) -> float:
        prices = context.get("prices", [])
        score: Optional[float] = None

        if self.learning_bridge is not None:
            try:
                score = float(self.learning_bridge.decide(dict(context)))
            except Exception:
                score = None

        if score is None and self.use_js and self.strategy_endpoint:
            score = self._call_external_strategy(prices)

        if score is None:
            score = self.core.ensemble_decision(context)

        return float(score)

    def _publish_signal(self, side: str, symbol: str) -> None:
        payload: Dict[str, Any] = {
            "side": side,
            "symbol": symbol,
            "quantity": 1,
            "strategy": "ensemble",
            "order_type": "market",
        }
        self.bus.publish("trade.signals", payload)

    # ------------------------------------------------------------------
    # Runtime loop
    # ------------------------------------------------------------------
    def _process_symbol(self, symbol: str) -> Optional[float]:
        prices = self.md.latest_prices(symbol)
        if len(prices) < 20:
            return None
        context: Dict[str, Any] = {"symbol": symbol, "prices": prices}
        score = self._decide(context)

        if score >= self.threshold:
            self._publish_signal("buy", symbol)
        elif score <= -self.threshold:
            self._publish_signal("sell", symbol)
        self._last_eval[symbol] = time.time()
        return score

    def _loop(self) -> None:
        while not self._stop:
            start = time.time()
            for symbol in self.symbols:
                self._process_symbol(symbol)

            elapsed = time.time() - start
            sleep_for = self.interval - elapsed
            time.sleep(sleep_for if sleep_for > 0 else 0.1)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def startup(self) -> str:
        self._stop = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return "[STRAT] started"

    def shutdown(self) -> str:
        self._stop = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        return "[STRAT] stopped"

    # ------------------------------------------------------------------
    # Integration hooks
    # ------------------------------------------------------------------
    def update_weights(self, weights: Dict[str, float]) -> None:
        """Update ensemble weights from learning agents."""
        try:
            with self._lock:
                for name, weight in (weights or {}).items():
                    core_weights = getattr(self.core, "weights", {})
                    if isinstance(core_weights, dict) and name in core_weights:
                        core_weights[name] = float(weight)
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_STRATEGY_RUNNER").debug("Exception suppressed in update_weights")

    def attach_learning_bridge(self, bridge: Any) -> str:
        if bridge is None:
            return "[STRAT] no bridge"
        with self._lock:
            self.learning_bridge = bridge
            if getattr(bridge, "strategy", None) is not self.core:
                bridge.strategy = self.core
        self.use_js = False
        return "[STRAT] learning bridge attached"

    def get_learning_bridge(self) -> Optional[Any]:
        return self.learning_bridge

    def handle_market_tick(self, payload: Dict[str, Any]) -> str:
        symbol = (payload or {}).get("symbol")
        if not symbol or symbol.upper() not in self.symbols:
            return "[STRAT] Tick ignored"
        now = time.time()
        last = self._last_eval.get(symbol)
        if last and (now - last) < max(0.1, self.interval / 2):
            return "[STRAT] Tick throttled"
        with self._lock:
            self._process_symbol(symbol)
        return "[STRAT] Tick processed"
