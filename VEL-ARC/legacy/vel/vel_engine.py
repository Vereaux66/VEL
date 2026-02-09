"""VEL Native Trading Engine - Python Integration Module

This module provides a seamless Python interface to the high-performance
Rust trading engine. It automatically builds and loads the native library
ensuring it is ALWAYS present for live operations.

AUTOMATIC BUILD:
If the native library is not found, this module will automatically:
1. Check for Rust toolchain (install if missing)
2. Build the vel-python crate in release mode
3. Install the library to the project root
4. Load the native module

Usage:
    from vel_engine import TradingEngine, Order, Position, RiskManager
    
    engine = TradingEngine(initial_capital=10000.0)
    order = Order(
        id="order-001",
        symbol="BTC/USD",
        side="buy",
        order_type="limit",
        quantity=0.1,
        price=50000.0
    )
    result = engine.submit_order(order)
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("vel_engine")

# Project root for library discovery and building
_PROJECT_ROOT = Path(__file__).resolve().parent

# Try to import the native Rust module
_NATIVE_AVAILABLE = False
_VEL_PYTHON = None
_BUILD_ATTEMPTED = False

def _check_rust_toolchain() -> bool:
    """Check if Rust/Cargo is available."""
    try:
        result = subprocess.run(
            ["cargo", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _install_rust_toolchain() -> bool:
    """Install Rust toolchain via rustup."""
    logger.info("Installing Rust toolchain...")
    system = platform.system().lower()

    try:
        if system == "windows":
            import urllib.request
            rustup_url = "https://win.rustup.rs/x86_64"
            rustup_path = _PROJECT_ROOT / "rustup-init.exe"
            urllib.request.urlretrieve(rustup_url, rustup_path)
            result = subprocess.run(
                [str(rustup_path), "-y", "--default-toolchain", "stable"],
                capture_output=True,
                text=True,
                timeout=600,
            )
            rustup_path.unlink(missing_ok=True)
            if result.returncode != 0:
                return False
        else:
            result = subprocess.run(
                ["sh", "-c", "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y"],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                return False

        # Add Cargo to PATH
        cargo_bin = Path.home() / ".cargo" / "bin"
        if cargo_bin.exists():
            os.environ["PATH"] = f"{cargo_bin}{os.pathsep}{os.environ.get('PATH', '')}"

        return _check_rust_toolchain()
    except Exception as e:
        logger.error(f"Failed to install Rust: {e}")
        return False


def _build_native_library() -> bool:
    """Build the native vel_python library."""
    global _BUILD_ATTEMPTED

    if _BUILD_ATTEMPTED:
        return False
    _BUILD_ATTEMPTED = True

    vel_trading_dir = _PROJECT_ROOT / "vel-trading"
    if not vel_trading_dir.exists():
        logger.warning("vel-trading directory not found, cannot build native library")
        return False

    # Check for Rust toolchain
    if not _check_rust_toolchain():
        logger.info("Rust toolchain not found, installing...")
        if not _install_rust_toolchain():
            logger.error("Failed to install Rust toolchain")
            return False

    logger.info("Building native VEL library (this may take a minute)...")

    try:
        # Build the vel-python crate
        result = subprocess.run(
            ["cargo", "build", "--release", "-p", "vel-python"],
            cwd=vel_trading_dir,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode != 0:
            logger.error(f"Cargo build failed: {result.stderr[:200]}")
            return False

        # Find and copy the built library
        target_dir = vel_trading_dir / "target" / "release"
        system = platform.system().lower()

        if system == "windows":
            src_names = ["vel_python.dll", "vel_python.pyd"]
            dest_name = "vel_python.pyd"
        elif system == "darwin":
            src_names = ["libvel_python.dylib", "vel_python.so"]
            dest_name = "vel_python.so"
        else:
            src_names = ["libvel_python.so", "vel_python.so"]
            dest_name = "vel_python.so"

        for src_name in src_names:
            src_lib = target_dir / src_name
            if src_lib.exists():
                dest_lib = _PROJECT_ROOT / dest_name
                shutil.copy2(src_lib, dest_lib)
                logger.info(f"Installed native library: {dest_lib}")
                return True

        logger.error("Built library not found in target directory")
        return False

    except subprocess.TimeoutExpired:
        logger.error("Build timed out")
        return False
    except Exception as e:
        logger.error(f"Build error: {e}")
        return False


def _find_native_library() -> bool:
    """Attempt to find and load the native VEL library. Build if not found."""
    global _NATIVE_AVAILABLE, _VEL_PYTHON

    # Check if already loaded
    if _VEL_PYTHON is not None:
        return _NATIVE_AVAILABLE

    # Search paths for the native library
    search_paths = [
        _PROJECT_ROOT / "vel-trading" / "target" / "release",
        _PROJECT_ROOT / "vel-trading" / "target" / "debug",
        _PROJECT_ROOT / "native" / "lib",
        _PROJECT_ROOT,
        Path.cwd() / "vel-trading" / "target" / "release",
    ]

    # Platform-specific library names
    if sys.platform == "win32":
        lib_names = ["vel_python.pyd", "vel_python.dll"]
    elif sys.platform == "darwin":
        lib_names = ["libvel_python.dylib", "vel_python.so"]
    else:
        lib_names = ["libvel_python.so", "vel_python.so"]

    # Try to find the library
    for search_path in search_paths:
        for lib_name in lib_names:
            lib_path = search_path / lib_name
            if lib_path.exists():
                try:
                    # Add to path and import
                    sys.path.insert(0, str(search_path))
                    import vel_python as vp
                    _VEL_PYTHON = vp
                    _NATIVE_AVAILABLE = True
                    logger.info(f"Loaded native VEL library from {lib_path}")
                    return True
                except ImportError as e:
                    logger.debug(f"Failed to load {lib_path}: {e}")
                    continue

    # Try direct import in case it's in the Python path
    try:
        import vel_python as vp
        _VEL_PYTHON = vp
        _NATIVE_AVAILABLE = True
        logger.info("Loaded native VEL library from Python path")
        return True
    except ImportError:
        import logging as _lg  # noqa: E402
        _lg.getLogger("VEL_ENGINE").debug("Exception suppressed in _find_native_library")

    # Library not found - BUILD IT AUTOMATICALLY
    logger.info("Native library not found, building automatically...")
    if _build_native_library():
        # Try to load again after building
        for search_path in [_PROJECT_ROOT, _PROJECT_ROOT / "vel-trading" / "target" / "release"]:
            for lib_name in lib_names:
                lib_path = search_path / lib_name
                if lib_path.exists():
                    try:
                        sys.path.insert(0, str(search_path))
                        import vel_python as vp
                        _VEL_PYTHON = vp
                        _NATIVE_AVAILABLE = True
                        logger.info(f"Loaded freshly built native library from {lib_path}")
                        return True
                    except ImportError as e:
                        logger.debug(f"Failed to load freshly built {lib_path}: {e}")
                        continue

    logger.warning("Native VEL library not available, using Python fallback")
    return False


def ensure_native_library() -> bool:
    """Ensure the native library is present, building if necessary.
    
    This function guarantees the native library is available for live operations.
    Call this at system startup to ensure full performance.
    
    Returns:
        True if native library is available, False otherwise
    """
    if _find_native_library():
        return True

    # Force a build attempt even if previously attempted
    global _BUILD_ATTEMPTED
    _BUILD_ATTEMPTED = False

    if _build_native_library():
        return _find_native_library()

    return False


def is_native_available() -> bool:
    """Check if the native Rust library is available."""
    _find_native_library()
    return _NATIVE_AVAILABLE


def version() -> str:
    """Get the VEL engine version."""
    if _find_native_library() and _VEL_PYTHON:
        return _VEL_PYTHON.version()
    return "1.0.0-python-fallback"


# =============================================================================
# Python Fallback Classes
# =============================================================================

class _FallbackOrder:
    """Pure Python Order implementation."""

    def __init__(
        self,
        id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ):
        import time
        self._id = id
        self._symbol = symbol
        self._side = side.lower()
        self._order_type = order_type.lower()
        self._quantity = float(quantity)
        self._price = float(price) if price else None
        self._stop_price = float(stop_price) if stop_price else None
        self._filled_quantity = 0.0
        self._remaining_quantity = float(quantity)
        self._status = "pending"
        self._timestamp = int(time.time() * 1000)

    @property
    def id(self) -> str:
        return self._id

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def side(self) -> str:
        return self._side

    @property
    def order_type(self) -> str:
        return self._order_type

    @property
    def quantity(self) -> float:
        return self._quantity

    @property
    def price(self) -> Optional[float]:
        return self._price

    @property
    def stop_price(self) -> Optional[float]:
        return self._stop_price

    @property
    def filled_quantity(self) -> float:
        return self._filled_quantity

    @property
    def remaining_quantity(self) -> float:
        return self._remaining_quantity

    @property
    def status(self) -> str:
        return self._status

    @property
    def timestamp(self) -> int:
        return self._timestamp

    def is_active(self) -> bool:
        return self._status in ("pending", "partially_filled")

    def is_complete(self) -> bool:
        return self._status in ("filled", "cancelled", "rejected")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self._id,
            "symbol": self._symbol,
            "side": self._side,
            "order_type": self._order_type,
            "quantity": self._quantity,
            "price": self._price,
            "stop_price": self._stop_price,
            "filled_quantity": self._filled_quantity,
            "remaining_quantity": self._remaining_quantity,
            "status": self._status,
            "timestamp": self._timestamp,
            "is_active": self.is_active(),
            "is_complete": self.is_complete(),
        }

    def __repr__(self) -> str:
        return (
            f"Order(id='{self._id}', symbol='{self._symbol}', "
            f"side='{self._side}', type='{self._order_type}', "
            f"qty={self._quantity}, price={self._price}, status='{self._status}')"
        )


class _FallbackPosition:
    """Pure Python Position implementation."""

    def __init__(self, symbol: str, side: str, quantity: float, entry_price: float):
        import time
        self._symbol = symbol
        self._side = side.lower()
        self._quantity = float(quantity)
        self._entry_price = float(entry_price)
        self._current_price = float(entry_price)
        self._unrealized_pnl = 0.0
        self._realized_pnl = 0.0
        self._timestamp = int(time.time() * 1000)

    @property
    def symbol(self) -> str:
        return self._symbol

    @property
    def side(self) -> str:
        return "long" if self._side == "buy" else "short"

    @property
    def quantity(self) -> float:
        return self._quantity

    @property
    def entry_price(self) -> float:
        return self._entry_price

    @property
    def current_price(self) -> float:
        return self._current_price

    @property
    def unrealized_pnl(self) -> float:
        return self._unrealized_pnl

    @property
    def realized_pnl(self) -> float:
        return self._realized_pnl

    def total_pnl(self) -> float:
        return self._unrealized_pnl + self._realized_pnl

    def value(self) -> float:
        return self._current_price * self._quantity

    def update_price(self, price: float) -> None:
        self._current_price = float(price)
        price_diff = self._current_price - self._entry_price
        pnl = price_diff * self._quantity
        self._unrealized_pnl = pnl if self._side == "buy" else -pnl

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self._symbol,
            "side": self.side,
            "quantity": self._quantity,
            "entry_price": self._entry_price,
            "current_price": self._current_price,
            "unrealized_pnl": self._unrealized_pnl,
            "realized_pnl": self._realized_pnl,
            "total_pnl": self.total_pnl(),
            "value": self.value(),
        }

    def __repr__(self) -> str:
        return (
            f"Position(symbol='{self._symbol}', side='{self.side}', "
            f"qty={self._quantity}, entry={self._entry_price}, "
            f"current={self._current_price}, pnl={self._unrealized_pnl})"
        )


class _FallbackRiskManager:
    """Pure Python Risk Manager implementation."""

    def __init__(
        self,
        initial_capital: float,
        max_position_pct: float = 0.20,
        max_total_risk: float = 0.10,
        max_drawdown_pct: float = 0.15,
        correlation_limit: float = 0.7,
        max_daily_trades: int = 50,
        max_exposure: float = 100000.0,
    ):
        self._initial_capital = float(initial_capital)
        self._current_capital = float(initial_capital)
        self._peak_capital = float(initial_capital)
        self._max_position_pct = float(max_position_pct)
        self._max_total_risk = float(max_total_risk)
        self._max_drawdown_pct = float(max_drawdown_pct)
        self._correlation_limit = float(correlation_limit)
        self._max_daily_trades = int(max_daily_trades)
        self._max_exposure = float(max_exposure)
        self._daily_trades = 0
        self._positions: Dict[str, Any] = {}

    def current_capital(self) -> float:
        return self._current_capital

    def current_drawdown(self) -> float:
        if self._peak_capital == 0:
            return 0.0
        return (self._peak_capital - self._current_capital) / self._peak_capital

    def daily_trade_count(self) -> int:
        return self._daily_trades

    def total_exposure(self) -> float:
        return sum(p.get("value", 0) for p in self._positions.values())

    def update_capital(self, pnl: float) -> None:
        self._current_capital += pnl
        if self._current_capital > self._peak_capital:
            self._peak_capital = self._current_capital

    def increment_daily_trades(self) -> None:
        self._daily_trades += 1

    def reset_daily_trades(self) -> None:
        self._daily_trades = 0

    def calculate_kelly_position_size(
        self, win_rate: float, avg_win: float, avg_loss: float
    ) -> float:
        if win_rate <= 0 or avg_win <= 0 or avg_loss <= 0:
            return 0.0
        loss_rate = 1.0 - win_rate
        win_loss_ratio = avg_win / avg_loss
        kelly_pct = (win_rate * win_loss_ratio - loss_rate) / win_loss_ratio
        safe_kelly = kelly_pct * 0.25
        final_pct = max(0, min(safe_kelly, self._max_position_pct))
        return self._current_capital * final_pct

    def calculate_dynamic_stop_loss(
        self, entry_price: float, volatility: float, side: str, atr_multiplier: float
    ) -> float:
        stop_distance = entry_price * volatility * atr_multiplier
        if side.lower() in ("buy", "long"):
            return entry_price - stop_distance
        return entry_price + stop_distance

    def validate_order(self, order: Any) -> bool:
        # Check daily trade limit
        if self._daily_trades >= self._max_daily_trades:
            raise RuntimeError("Daily trade limit exceeded")

        # Check drawdown
        if self.current_drawdown() > self._max_drawdown_pct:
            raise RuntimeError("Drawdown limit exceeded")

        # Check position size
        order_value = order.quantity * (order.price or 0)
        max_size = self._current_capital * self._max_position_pct
        if order_value > max_size:
            raise RuntimeError(f"Position size {order_value} exceeds limit {max_size}")

        return True

    def get_positions(self) -> List[Dict[str, Any]]:
        return list(self._positions.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_capital": self._current_capital,
            "current_drawdown": self.current_drawdown(),
            "daily_trade_count": self._daily_trades,
            "total_exposure": self.total_exposure(),
        }

    def __repr__(self) -> str:
        return (
            f"RiskManager(capital={self._current_capital}, "
            f"drawdown={self.current_drawdown()}, trades={self._daily_trades})"
        )


class _FallbackTradingEngine:
    """Pure Python Trading Engine implementation."""

    def __init__(
        self,
        initial_capital: float = 10000.0,
        max_position_pct: float = 0.20,
        max_drawdown_pct: float = 0.15,
    ):
        self._orders: Dict[str, Any] = {}
        self._positions: Dict[str, Any] = {}
        self._trades: List[Any] = []
        self._risk_manager = _FallbackRiskManager(
            initial_capital, max_position_pct, max_drawdown_pct=max_drawdown_pct
        )
        self._active = True
        self._daily_pnl = 0.0
        self._total_pnl = 0.0
        self._win_count = 0
        self._loss_count = 0

    def is_active(self) -> bool:
        return self._active

    def shutdown(self) -> None:
        self._active = False

    def submit_order(self, order: Any) -> Dict[str, Any]:
        if not self._active:
            raise RuntimeError("Trading engine is not active")

        self._risk_manager.validate_order(order)
        self._orders[order.id] = order
        self._risk_manager.increment_daily_trades()

        return {
            "status": "accepted",
            "order_id": order.id,
            "message": "Order submitted successfully",
        }

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        if order_id not in self._orders:
            raise RuntimeError("Order not found")

        order = self._orders[order_id]
        if hasattr(order, "is_complete") and order.is_complete():
            raise RuntimeError("Order is already complete")

        del self._orders[order_id]
        return {"status": "cancelled", "order_id": order_id}

    def get_order(self, order_id: str) -> Optional[Any]:
        return self._orders.get(order_id)

    def get_active_orders(self) -> List[Any]:
        return [o for o in self._orders.values() if hasattr(o, "is_active") and o.is_active()]

    def get_positions(self) -> List[Any]:
        return list(self._positions.values())

    def get_position(self, symbol: str) -> Optional[Any]:
        return self._positions.get(symbol)

    def get_trades(self) -> List[Any]:
        return self._trades.copy()

    def record_trade(self, trade: Any) -> None:
        pnl = trade.net_value() if hasattr(trade, "net_value") else 0.0

        self._daily_pnl += pnl
        self._total_pnl += pnl

        if pnl > 0:
            self._win_count += 1
        elif pnl < 0:
            self._loss_count += 1

        self._risk_manager.update_capital(pnl)
        self._trades.append(trade)

    def update_position(
        self, symbol: str, side: str, quantity: float, price: float
    ) -> None:
        pos = _FallbackPosition(symbol, side, quantity, price)
        self._positions[symbol] = pos

    def close_position(self, symbol: str) -> Optional[Any]:
        return self._positions.pop(symbol, None)

    def current_capital(self) -> float:
        return self._risk_manager.current_capital()

    def current_drawdown(self) -> float:
        return self._risk_manager.current_drawdown()

    def daily_pnl(self) -> float:
        return self._daily_pnl

    def total_pnl(self) -> float:
        return self._total_pnl

    def win_count(self) -> int:
        return self._win_count

    def loss_count(self) -> int:
        return self._loss_count

    def win_rate(self) -> float:
        total = self._win_count + self._loss_count
        return self._win_count / total if total > 0 else 0.0

    def reset_daily_stats(self) -> None:
        self._daily_pnl = 0.0
        self._risk_manager.reset_daily_trades()

    def get_stats(self) -> Dict[str, Any]:
        return {
            "active": self._active,
            "current_capital": self.current_capital(),
            "current_drawdown": self.current_drawdown(),
            "daily_pnl": self._daily_pnl,
            "total_pnl": self._total_pnl,
            "win_count": self._win_count,
            "loss_count": self._loss_count,
            "win_rate": self.win_rate(),
            "daily_trade_count": self._risk_manager.daily_trade_count(),
            "total_exposure": self._risk_manager.total_exposure(),
            "open_positions": len(self._positions),
            "active_orders": len(self.get_active_orders()),
        }

    def __repr__(self) -> str:
        return (
            f"TradingEngine(capital={self.current_capital():.2f}, "
            f"pnl={self._total_pnl:.2f}, positions={len(self._positions)}, "
            f"orders={len(self._orders)}, win_rate={self.win_rate()*100:.2f}%)"
        )


# =============================================================================
# Public API - Auto-selects native or fallback
# =============================================================================

def Order(
    id: str,
    symbol: str,
    side: str,
    order_type: str,
    quantity: float,
    price: Optional[float] = None,
    stop_price: Optional[float] = None,
) -> Union[Any, _FallbackOrder]:
    """Create an Order object using native library if available."""
    if _find_native_library() and _VEL_PYTHON:
        return _VEL_PYTHON.Order(id, symbol, side, order_type, quantity, price, stop_price)
    return _FallbackOrder(id, symbol, side, order_type, quantity, price, stop_price)


def Position(
    symbol: str,
    side: str,
    quantity: float,
    entry_price: float,
) -> Union[Any, _FallbackPosition]:
    """Create a Position object using native library if available."""
    if _find_native_library() and _VEL_PYTHON:
        return _VEL_PYTHON.Position(symbol, side, quantity, entry_price)
    return _FallbackPosition(symbol, side, quantity, entry_price)


def Quote(symbol: str, bid: float, ask: float) -> Any:
    """Create a Quote object using native library if available."""
    if _find_native_library() and _VEL_PYTHON:
        return _VEL_PYTHON.Quote(symbol, bid, ask)
    # Simple fallback
    return {"symbol": symbol, "bid": bid, "ask": ask, "mid_price": (bid + ask) / 2}


def Trade(
    id: str,
    order_id: str,
    symbol: str,
    side: str,
    price: float,
    quantity: float,
    fee: float,
) -> Any:
    """Create a Trade object using native library if available."""
    if _find_native_library() and _VEL_PYTHON:
        return _VEL_PYTHON.Trade(id, order_id, symbol, side, price, quantity, fee)
    # Simple fallback - match Rust behavior
    import time
    gross_value = price * quantity
    # Net value represents total cash flow:
    # - Buy: gross + fee (total cost to acquire the asset)
    # - Sell: gross - fee (net proceeds after selling)
    if side.lower() == "buy":
        net_value = gross_value + fee
    else:
        net_value = gross_value - fee
    return {
        "id": id, "order_id": order_id, "symbol": symbol, "side": side,
        "price": price, "quantity": quantity, "fee": fee,
        "gross_value": gross_value,
        "net_value": net_value,
        "timestamp": int(time.time() * 1000),
    }


def RiskManager(
    initial_capital: float,
    max_position_pct: float = 0.20,
    max_total_risk: float = 0.10,
    max_drawdown_pct: float = 0.15,
    correlation_limit: float = 0.7,
    max_daily_trades: int = 50,
    max_exposure: float = 100000.0,
) -> Union[Any, _FallbackRiskManager]:
    """Create a RiskManager using native library if available."""
    if _find_native_library() and _VEL_PYTHON:
        return _VEL_PYTHON.PyRiskManager(
            initial_capital, max_position_pct, max_total_risk,
            max_drawdown_pct, correlation_limit, max_daily_trades, max_exposure
        )
    return _FallbackRiskManager(
        initial_capital, max_position_pct, max_total_risk,
        max_drawdown_pct, correlation_limit, max_daily_trades, max_exposure
    )


def TradingEngine(
    initial_capital: float = 10000.0,
    max_position_pct: float = 0.20,
    max_drawdown_pct: float = 0.15,
) -> Union[Any, _FallbackTradingEngine]:
    """Create a TradingEngine using native library if available."""
    if _find_native_library() and _VEL_PYTHON:
        return _VEL_PYTHON.PyTradingEngine(initial_capital, max_position_pct, max_drawdown_pct)
    return _FallbackTradingEngine(initial_capital, max_position_pct, max_drawdown_pct)


# =============================================================================
# Risk Calculation Functions
# =============================================================================

def calculate_var(returns: List[float], confidence_level: float = 0.95) -> float:
    """Calculate Value at Risk using historical method."""
    if _find_native_library() and _VEL_PYTHON:
        return _VEL_PYTHON.calculate_var(returns, confidence_level)
    if not returns:
        return 0.0
    sorted_returns = sorted(returns)
    index = int((1.0 - confidence_level) * len(sorted_returns))
    index = min(index, len(sorted_returns) - 1)
    return -sorted_returns[index]


def calculate_volatility(returns: List[float]) -> float:
    """Calculate portfolio volatility."""
    if _find_native_library() and _VEL_PYTHON:
        return _VEL_PYTHON.calculate_volatility(returns)
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return variance ** 0.5


def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.0) -> float:
    """Calculate Sharpe ratio."""
    if _find_native_library() and _VEL_PYTHON:
        return _VEL_PYTHON.calculate_sharpe_ratio(returns, risk_free_rate)
    if not returns:
        return 0.0
    mean_return = sum(returns) / len(returns)
    volatility = calculate_volatility(returns)
    if volatility == 0:
        return 0.0
    return (mean_return - risk_free_rate) / volatility


def calculate_max_drawdown(equity_curve: List[float]) -> float:
    """Calculate maximum drawdown from equity curve."""
    if _find_native_library() and _VEL_PYTHON:
        return _VEL_PYTHON.calculate_max_drawdown(equity_curve)
    if not equity_curve:
        return 0.0
    max_dd = 0.0
    peak = equity_curve[0]
    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (peak - value) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd


# Initialize on import
_find_native_library()

__all__ = [
    "version",
    "is_native_available",
    "ensure_native_library",
    "Order",
    "Position",
    "Quote",
    "Trade",
    "RiskManager",
    "TradingEngine",
    "calculate_var",
    "calculate_volatility",
    "calculate_sharpe_ratio",
    "calculate_max_drawdown",
]
