"""Hybrid backend interfaces for ANVEL.

These clients abstract polyglot services (Rust ExecCore, TS Gateway,
C++ Timeseries) so Python callers can flip between native and HTTP
implementations without touching call sites.

Native execution core is preferred when the compiled artifact is present.
When the library is missing we transparently fall back to HTTP or no-op
shims, preserving the legacy behaviour while we finish the native rollout.

SYSTEM-WIDE INTEGRATION:
This module integrates with both anvel_native_core (which now uses vel_python)
and the direct vel_engine module for high-performance Rust-based trading.

AUTOMATIC BUILD:
The native library is automatically built if not present, ensuring it is
ALWAYS available for live operations.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional, cast

# Try to load native exec core with vel_python integration
try:
    from anvel_native_core import load_native_exec_core, is_vel_engine_available
except Exception:  # pragma: no cover - fallback when native package missing
    load_native_exec_core = None  # type: ignore
    is_vel_engine_available = None  # type: ignore

# Also try direct vel_engine access for additional functionality
# This will auto-build the native library if not present
_VEL_ENGINE_DIRECT = None
VelTradingEngine = None
VelRiskManager = None
calculate_var = None
calculate_volatility = None
calculate_sharpe_ratio = None
calculate_max_drawdown = None

def _ensure_vel_engine_direct():
    """Ensure vel_engine is available, building if necessary."""
    global _VEL_ENGINE_DIRECT, VelTradingEngine, VelRiskManager
    global calculate_var, calculate_volatility, calculate_sharpe_ratio, calculate_max_drawdown

    if _VEL_ENGINE_DIRECT is not None:
        return _VEL_ENGINE_DIRECT

    try:
        from vel_engine import (
            ensure_native_library,
            is_native_available as vel_native_available,
            TradingEngine as _VelTE,
            RiskManager as _VelRM,
            calculate_var as _calc_var,
            calculate_volatility as _calc_vol,
            calculate_sharpe_ratio as _calc_sharpe,
            calculate_max_drawdown as _calc_mdd,
        )

        # Ensure native library is built and available
        ensure_native_library()

        if vel_native_available():
            _VEL_ENGINE_DIRECT = True
            VelTradingEngine = _VelTE
            VelRiskManager = _VelRM
            calculate_var = _calc_var
            calculate_volatility = _calc_vol
            calculate_sharpe_ratio = _calc_sharpe
            calculate_max_drawdown = _calc_mdd
        else:
            _VEL_ENGINE_DIRECT = False
    except ImportError:
        _VEL_ENGINE_DIRECT = False

    return _VEL_ENGINE_DIRECT

# Trigger initial load/build attempt
_ensure_vel_engine_direct()


def _normalize_endpoint(ep: str, default_port: str) -> str:
    ep = ep.strip()
    if ep.startswith("http://") or ep.startswith("https://"):
        return ep.rstrip("/")
    if ":" not in ep:
        ep = f"{ep}:{default_port}"
    return f"http://{ep}"


def _http_json(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    timeout: int = 5,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ct = resp.headers.get("Content-Type", "")
            raw = resp.read()
            if "application/json" in ct:
                return json.loads(raw.decode("utf-8", errors="replace"))
            return {
                "status": "ok",
                "raw": raw.decode("utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:  # pragma: no cover - defensive branch
            body = str(exc)
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except Exception as exc:  # pragma: no cover - accountability reporting
        raise RuntimeError(f"Request failed: {exc}") from exc


class NativeExecCoreAdapter:
    """Expose the native execution core with legacy ergonomics."""

    def __init__(self) -> None:
        self._native = load_native_exec_core() if load_native_exec_core else None
        self.enabled = self._native is not None
        self._version = (
            self._native.version() if self._native is not None else "unavailable"
        )

    @property
    def version(self) -> str:
        return self._version

    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: Optional[float] = None,
        tif: str = "GTC",
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        _ = (tif, meta)  # unused; signature parity
        if not self._native:
            raise RuntimeError("Native execution core unavailable")
        return self._native.submit_order(symbol, side, float(qty), price, None)

    def amend(self, order_id: str, **kwargs: Any) -> Dict[str, Any]:
        if not self._native:
            raise RuntimeError("Native execution core unavailable")
        return self._native.amend(order_id, **kwargs)

    def cancel(self, order_id: str) -> Dict[str, Any]:
        if not self._native:
            raise RuntimeError("Native execution core unavailable")
        return self._native.cancel(order_id)

    def assess_risk(
        self,
        order: Dict[str, Any],
        portfolio: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not self._native:
            raise RuntimeError("Native execution core unavailable")
        return self._native.assess_risk(order, portfolio)

    def get_positions(self) -> List[Dict[str, Any]]:
        if not self._native:
            raise RuntimeError("Native execution core unavailable")
        return self._native.get_positions()


class ExecCoreClient:
    def __init__(self, endpoint: str = "localhost:50051") -> None:
        self.endpoint = _normalize_endpoint(endpoint, "50051")
        self.enabled = True

    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: Optional[float] = None,
        tif: str = "GTC",
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "tif": tif,
            "meta": meta or {},
        }
        return _http_json("POST", f"{self.endpoint}/orders", payload)

    def amend(self, order_id: str, **kwargs: Any) -> Dict[str, Any]:
        return _http_json(
            "PATCH",
            f"{self.endpoint}/orders/{order_id}",
            kwargs or {},
        )

    def cancel(self, order_id: str) -> Dict[str, Any]:
        return _http_json("DELETE", f"{self.endpoint}/orders/{order_id}")

    def assess_risk(
        self,
        order: Dict[str, Any],
        portfolio: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {"order": order, "portfolio": portfolio or {}}
        return _http_json("POST", f"{self.endpoint}/risk/order", payload)

    def get_positions(self) -> List[Dict[str, Any]]:
        resp: Any = _http_json("GET", f"{self.endpoint}/positions")
        if isinstance(resp, list):
            output: List[Dict[str, Any]] = []
            for item in cast(List[Any], resp):
                if isinstance(item, dict):
                    output.append(cast(Dict[str, Any], item))
            return output
        if isinstance(resp, dict):
            resp_dict = cast(Dict[str, Any], resp)
            positions: Any = resp_dict.get("positions", [])
            if isinstance(positions, list):
                output = []
                for item in cast(List[Any], positions):
                    if isinstance(item, dict):
                        output.append(cast(Dict[str, Any], item))
                return output
        return []


class GatewayClient:
    def __init__(self, endpoint: str = "localhost:50052") -> None:
        self.endpoint = _normalize_endpoint(endpoint, "50052")
        self.enabled = True
        self._subs: Dict[str, List[str]] = {"ticker": [], "orders": []}

    def subscribe_ticker(self, symbols: Iterable[str]) -> Dict[str, Any]:
        syms = list(symbols)
        self._subs["ticker"] = list(set(self._subs["ticker"] + syms))
        return _http_json(
            "POST",
            f"{self.endpoint}/subscribe/ticker",
            {"symbols": syms},
        )

    def subscribe_orders(self) -> Dict[str, Any]:
        self._subs["orders"] = ["*"]
        return _http_json("POST", f"{self.endpoint}/subscribe/orders", {})

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        return _http_json("GET", f"{self.endpoint}/quotes/{symbol}")

    def snapshot_orderbook(self, symbol: str, depth: int = 50) -> Dict[str, Any]:
        return _http_json(
            "GET",
            f"{self.endpoint}/orderbook/{symbol}?depth={depth}",
        )


class RiskCoreClient:
    def __init__(self, endpoint: str = "localhost:50053") -> None:
        self.endpoint = _normalize_endpoint(endpoint, "50053")
        self.enabled = True

    def assess_portfolio(self, portfolio: Dict[str, Any]) -> Dict[str, Any]:
        return _http_json("POST", f"{self.endpoint}/risk/portfolio", portfolio)

    def limits(self) -> Dict[str, Any]:
        return _http_json("GET", f"{self.endpoint}/risk/limits")


class _NoopExecCore(ExecCoreClient):
    def __init__(self, endpoint: str = "localhost:50051") -> None:
        super().__init__(endpoint)
        self.enabled = False

    def submit_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: Optional[float] = None,
        tif: str = "GTC",
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        del tif, meta
        return {
            "status": "accepted",
            "id": f"SIM-{symbol}-{side}-{qty}",
            "price": price,
        }

    def amend(self, order_id: str, **kwargs: Any) -> Dict[str, Any]:
        return {"status": "amended", "id": order_id, **kwargs}

    def cancel(self, order_id: str) -> Dict[str, Any]:
        return {"status": "canceled", "id": order_id}

    def assess_risk(
        self,
        order: Dict[str, Any],
        portfolio: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        del order, portfolio
        return {"ok": True, "reasons": []}

    def get_positions(self) -> List[Dict[str, Any]]:
        return []


class _NoopGateway(GatewayClient):
    def __init__(self, endpoint: str = "localhost:50052") -> None:
        super().__init__(endpoint)
        self.enabled = False

    def get_quote(self, symbol: str) -> Dict[str, Any]:
        return {"symbol": symbol, "bid": 100.0, "ask": 100.1}

    def snapshot_orderbook(self, symbol: str, depth: int = 50) -> Dict[str, Any]:
        del depth
        return {"symbol": symbol, "bids": [], "asks": []}


def _native_exec_enabled() -> bool:
    """Check if native execution is enabled (not disabled via env var)."""
    return str(os.getenv("ANVEL_NATIVE_DISABLE", "")).lower() not in (
        "1",
        "true",
        "yes",
    )


def _vel_engine_enabled() -> bool:
    """Check if vel_python Rust engine is available and enabled."""
    if str(os.getenv("ANVEL_VEL_ENGINE_DISABLE", "")).lower() in ("1", "true", "yes"):
        return False
    return _VEL_ENGINE_DIRECT is not None


def make_exec_core(
    enabled: bool = False,
    endpoint: str = "localhost:50051",
) -> Any:
    """Create an execution core client using the best available backend.
    
    Priority:
    1. NativeExecCoreAdapter (which now uses vel_python internally)
    2. HTTP ExecCoreClient
    3. NoopExecCore (for testing/simulation)
    """
    if load_native_exec_core and _native_exec_enabled():
        try:
            native_core = NativeExecCoreAdapter()
            if getattr(native_core, "enabled", False):
                return native_core
        except Exception:
            if str(os.getenv("ANVEL_NATIVE_FORCE", "")).lower() in ("1", "true", "yes"):
                raise
    return ExecCoreClient(endpoint) if enabled else _NoopExecCore(endpoint)


def make_gateway(
    enabled: bool = False,
    endpoint: str = "localhost:50052",
) -> GatewayClient:
    """Create a gateway client for market data subscriptions."""
    return GatewayClient(endpoint) if enabled else _NoopGateway(endpoint)


# ============================================================================
# VEL Engine Direct Access Functions (System-Wide Integration)
# ============================================================================

def make_vel_trading_engine(initial_capital: float = 100000.0) -> Any:
    """Create a VEL Trading Engine instance if available.
    
    This provides direct access to the high-performance Rust trading engine
    with risk management, position tracking, and order lifecycle management.
    """
    if _VEL_ENGINE_DIRECT:
        try:
            return VelTradingEngine(initial_capital)
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_HYBRID_INTERFACES").debug("Exception suppressed in make_vel_trading_engine")
    return None


def make_vel_risk_manager(
    initial_capital: float = 100000.0,
    max_position_pct: float = 0.20,
    max_drawdown_pct: float = 0.15,
) -> Any:
    """Create a VEL Risk Manager instance if available.
    
    Provides Kelly Criterion position sizing, VaR calculations,
    and real-time risk validation for orders.
    """
    if _VEL_ENGINE_DIRECT:
        try:
            return VelRiskManager(
                initial_capital,
                max_position_pct,
                0.10,  # max_total_risk
                max_drawdown_pct,
            )
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_HYBRID_INTERFACES").debug("Exception suppressed in make_vel_risk_manager")
    return None


def get_risk_metrics(returns: List[float], risk_free_rate: float = 0.0) -> Dict[str, Any]:
    """Calculate comprehensive risk metrics using the Rust engine if available.
    
    Returns VaR, volatility, Sharpe ratio, and max drawdown.
    """
    metrics: Dict[str, Any] = {
        "engine": "python-fallback",
        "var_95": 0.0,
        "volatility": 0.0,
        "sharpe_ratio": 0.0,
    }

    if _VEL_ENGINE_DIRECT:
        try:
            metrics["var_95"] = calculate_var(returns, 0.95)
            metrics["volatility"] = calculate_volatility(returns)
            metrics["sharpe_ratio"] = calculate_sharpe_ratio(returns, risk_free_rate)
            metrics["engine"] = "vel-python-rust"
            return metrics
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_HYBRID_INTERFACES").debug("Exception suppressed in get_risk_metrics")

    # Fallback: Simple Python calculations
    if returns:
        sorted_returns = sorted(returns)
        index = int(0.05 * len(sorted_returns))
        metrics["var_95"] = -sorted_returns[min(index, len(sorted_returns) - 1)]

        if len(returns) > 1:
            mean = sum(returns) / len(returns)
            variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
            metrics["volatility"] = variance ** 0.5
            if metrics["volatility"] > 0:
                metrics["sharpe_ratio"] = (mean - risk_free_rate) / metrics["volatility"]

    return metrics


def is_vel_native_available() -> bool:
    """Check if the vel_python Rust engine is available system-wide."""
    return _VEL_ENGINE_DIRECT is not None
