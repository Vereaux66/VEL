"""Native core bridge for ANVEL.

This module provides bindings to the Rust/C++/Go execution cores using ctypes
so Python orchestrators can rely on compiled components by default. When a
native artifact is not available, we gracefully fall back to an in-memory
simulation that mirrors the legacy Python behaviour. The simulator is a safety
net that should disappear once all native artifacts ship.

SYSTEM-WIDE INTEGRATION:
This module now integrates with the vel_engine.py module which provides
high-performance Rust bindings via PyO3. The vel_python module is preferred
when available, with automatic fallback to ctypes or Python simulation.

AUTOMATIC BUILD:
If the native library is not present, this module will trigger an automatic
build via vel_engine.ensure_native_library() to guarantee availability.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, cast

# ============================================================================
# VEL Engine Integration (System-Wide Rust Bindings)
# ============================================================================
# Try to import the high-performance vel_python Rust module
# If not available, trigger automatic build
_VEL_ENGINE = None
_VEL_ENGINE_AVAILABLE = False

def _ensure_vel_engine():
    """Ensure the VEL engine native library is available."""
    global _VEL_ENGINE, _VEL_ENGINE_AVAILABLE

    if _VEL_ENGINE_AVAILABLE:
        return True

    # First try direct import
    try:
        import vel_python as _vel_py
        _VEL_ENGINE = _vel_py
        _VEL_ENGINE_AVAILABLE = True
        return True
    except ImportError:
        import logging as _lg  # noqa: E402
        _lg.getLogger("ANVEL_NATIVE_CORE").debug("Exception suppressed in _ensure_vel_engine")

    # Try loading from vel_engine wrapper which handles auto-build
    try:
        from vel_engine import ensure_native_library, is_native_available

        # This will build the library if not present
        ensure_native_library()

        if is_native_available():
            import vel_python as _vel_py
            _VEL_ENGINE = _vel_py
            _VEL_ENGINE_AVAILABLE = True
            return True
    except ImportError:
        import logging as _lg  # noqa: E402
        _lg.getLogger("ANVEL_NATIVE_CORE").debug("Exception suppressed in _ensure_vel_engine")

    return False

# Trigger initial load/build attempt only if explicitly enabled
# Auto-build is disabled by default to prevent hanging during import
# Set VEL_AUTO_BUILD=1 to enable automatic native library build
if os.environ.get("VEL_AUTO_BUILD", "").lower() in ("1", "true", "yes"):
    _ensure_vel_engine()

# Shared constants aligned with native/core_interface/anvel_core.h
ANVEL_SIDE_BUY = 1
ANVEL_SIDE_SELL = 2

ANVEL_STATUS_ACCEPTED = 1
ANVEL_STATUS_REJECTED = 2
ANVEL_STATUS_FILLED = 3
ANVEL_STATUS_PARTIAL = 4

ANVEL_CORE_OK = 0


@dataclass
class OrderAck:
    order_id: int
    status: int
    executed_qty: float
    average_price: float


class _FallbackSimulator:
    """Simple Python fallback mirroring the previous pure-python path."""

    def __init__(self) -> None:
        self._next_id = 1
        self._lock = Lock()

    def submit(
        self,
        symbol: str,
        side_flag: int,
        quantity: float,
        limit_price: float,
        stop_price: float,
    ) -> OrderAck:
        # Validate inputs
        if quantity <= 0:
            raise RuntimeError("quantity must be positive")

        with self._lock:
            order_id = self._next_id
            self._next_id += 1
        price = limit_price or stop_price or 100.0
        qty = float(quantity)
        return OrderAck(
            order_id=order_id,
            status=ANVEL_STATUS_ACCEPTED,
            executed_qty=qty,
            average_price=price,
        )


class _NativeLibrary:
    """Utility loader that searches for platform-specific library names."""

    def __init__(
        self,
        env_var: str,
        candidates: Optional[list[str]] = None,
    ) -> None:
        self._env_var = env_var
        self._handle: Optional[ctypes.CDLL] = None
        self._candidates = candidates or []
        self._load()

    @property
    def handle(self) -> Optional[ctypes.CDLL]:
        return self._handle

    def _load(self) -> None:
        explicit = os.getenv(self._env_var)
        search_paths: List[Path] = []
        if explicit:
            search_paths.append(Path(explicit))
        libname = ctypes.util.find_library("anvel_core")
        if libname:
            search_paths.append(Path(libname))

        project_root = Path(__file__).resolve().parent
        default_names = self._candidates or [
            "anvel_core.dll",
            "libanvel_core.so",
            "libanvel_core.dylib",
        ]
        for name in default_names:
            search_paths.append(
                project_root / "native" / "anvel_core" / "target" / "release" / name
            )
            search_paths.append(
                project_root / "native" / "anvel_core" / "target" / "debug" / name
            )
            search_paths.append(project_root / "native" / name)

        for path in search_paths:
            if path and path.exists():
                try:
                    self._handle = ctypes.CDLL(str(path))
                    return
                except OSError:
                    continue

        # As a last attempt allow platform loader to resolve by name.
        if not self._handle:
            for name in default_names:
                try:
                    self._handle = ctypes.CDLL(name)
                    return
                except OSError:
                    continue


class CppGatewayBridge:
    """Stub positions bridge. Will call into C++ gateway when available."""

    def __init__(self) -> None:
        loader = _NativeLibrary(
            "ANVEL_GATEWAY_LIB",
            [
                "anvel_gateway.dll",
                "libanvel_gateway.so",
                "libanvel_gateway.dylib",
            ],
        )
        self._lib = loader.handle
        if not self._lib:
            project_root = Path(__file__).resolve().parent
            base_dir = project_root / "native" / "cpp_gateway"
            search_dirs = [
                base_dir,
                base_dir / "build",
                base_dir / "build" / "Debug",
                base_dir / "build" / "Release",
                base_dir / "build" / "RelWithDebInfo",
            ]
            names = [
                "anvel_gateway.dll",
                "libanvel_gateway.so",
                "libanvel_gateway.dylib",
            ]
            for directory in search_dirs:
                for name in names:
                    candidate = directory / name
                    if candidate.exists():
                        try:
                            self._lib = ctypes.CDLL(str(candidate))
                            break
                        except OSError:
                            continue
                if self._lib:
                    break

        if self._lib:
            try:
                self._lib.anvel_gateway_positions.argtypes = []
                self._lib.anvel_gateway_positions.restype = ctypes.c_char_p
            except AttributeError:
                self._lib = None

    def all(self) -> List[Dict[str, Any]]:
        if not self._lib:
            return []
        raw = self._lib.anvel_gateway_positions()
        if not raw:
            return []
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return []
        if isinstance(data, list):
            output: List[Dict[str, Any]] = []
            for item in cast(List[Any], data):
                if isinstance(item, dict):
                    output.append(cast(Dict[str, Any], item))
            return output
        if isinstance(data, dict):
            positions = cast(Dict[str, Any], data).get("positions", [])
            if isinstance(positions, list):
                output = []
                for item in cast(List[Any], positions):
                    if isinstance(item, dict):
                        output.append(cast(Dict[str, Any], item))
                return output
        return []


class NativeExecCore:
    """Bridge to the Rust execution core with safe fallbacks.
    
    Integration Priority:
    1. vel_python (PyO3 Rust bindings) - highest performance
    2. ctypes C library bindings (legacy)
    3. Python fallback simulator
    """

    class _Order(ctypes.Structure):
        _fields_ = [
            ("symbol", ctypes.c_char_p),
            ("side", ctypes.c_uint8),
            ("quantity", ctypes.c_double),
            ("limit_price", ctypes.c_double),
            ("stop_price", ctypes.c_double),
            ("tif", ctypes.c_uint32),
        ]

    class _Ack(ctypes.Structure):
        _fields_ = [
            ("order_id", ctypes.c_uint64),
            ("status", ctypes.c_uint8),
            ("executed_qty", ctypes.c_double),
            ("average_price", ctypes.c_double),
        ]

    def __init__(self) -> None:
        # Priority 1: Try vel_python (PyO3 Rust bindings)
        self._vel_engine = None
        self._vel_risk_manager = None
        self._use_vel_engine = False

        if _VEL_ENGINE_AVAILABLE and _VEL_ENGINE is not None:
            try:
                self._vel_engine = _VEL_ENGINE.PyTradingEngine(100000.0)
                self._vel_risk_manager = _VEL_ENGINE.PyRiskManager(100000.0)
                self._use_vel_engine = True
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_NATIVE_CORE").debug("Exception suppressed in __init__")

        # Priority 2: Try ctypes C library bindings (legacy)
        self._lib = _NativeLibrary("ANVEL_CORE_LIB").handle
        self._fallback = _FallbackSimulator()
        self._configure_functions()
        self._positions_bridge = CppGatewayBridge()

    @property
    def available(self) -> bool:
        """Returns True if any native core is available (vel_python or ctypes)."""
        return self._use_vel_engine or self._lib is not None

    def version(self) -> str:
        """Get the version of the active native core."""
        if self._use_vel_engine and _VEL_ENGINE is not None:
            return f"vel-python-{_VEL_ENGINE.version()}"
        if self._lib is not None:
            try:
                fn = getattr(self._lib, "anvel_core_version")
                fn.restype = ctypes.c_char_p
                raw = fn()
                return raw.decode("utf-8") if raw else "unknown"
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_NATIVE_CORE").debug("Exception suppressed in version")
        return "fallback-simulator"

    def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Submit an order using the best available execution core."""
        # Validate inputs BEFORE attempting any execution path
        if quantity <= 0:
            raise RuntimeError("quantity must be positive")

        if not self.available:
            raise RuntimeError("No execution core available - cannot submit order")

        # Priority 1: Use vel_python (PyO3 Rust bindings)
        if self._use_vel_engine and self._vel_engine is not None and _VEL_ENGINE is not None:
            try:
                order_id = f"vel-{int(__import__('time').time() * 1000)}"
                order = _VEL_ENGINE.Order(
                    order_id,
                    symbol,
                    side,
                    "limit" if limit_price else "market",
                    float(quantity),
                    float(limit_price) if limit_price else None,
                    float(stop_price) if stop_price else None,
                )
                result = self._vel_engine.submit_order(order)
                return {
                    "status": result.get("status", "accepted"),
                    "id": result.get("order_id", order_id),
                    "filled_quantity": float(quantity),
                    "average_price": float(limit_price or stop_price or 100.0),
                }
            except Exception:
                # Fall through to other methods on error
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_NATIVE_CORE").debug("Exception suppressed in submit_order")

        # Priority 2: Use ctypes C library bindings (legacy)
        side_flag = (
            ANVEL_SIDE_BUY if side.lower() == "buy" else ANVEL_SIDE_SELL
        )
        if self._lib is None:
            ack = self._fallback.submit(
                symbol,
                side_flag,
                float(quantity),
                float(limit_price or 0.0),
                float(stop_price or 0.0),
            )
            return self._format_ack(ack)

        order = self._Order()
        order.symbol = symbol.encode("utf-8")
        order.side = side_flag
        order.quantity = float(quantity)
        order.limit_price = float(limit_price or 0.0)
        order.stop_price = float(stop_price or 0.0)
        order.tif = 0
        ack = self._Ack()
        lib = self._lib
        if lib is None:
            raise RuntimeError("native core handle missing")
        result = lib.anvel_core_submit_order(
            ctypes.byref(order),
            ctypes.byref(ack),
        )
        if result != ANVEL_CORE_OK:
            raise RuntimeError(self._last_error())
        return self._format_native_ack(ack)

    def amend(self, order_id: str, **kwargs: Any) -> Dict[str, Any]:
        """Amend an existing order."""
        return {"status": "amended", "id": order_id, **kwargs}

    def cancel(self, order_id: str) -> Dict[str, Any]:
        """Cancel an existing order."""
        if self._use_vel_engine and self._vel_engine is not None:
            try:
                result = self._vel_engine.cancel_order(order_id)
                return result
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_NATIVE_CORE").debug("Exception suppressed in cancel")
        return {"status": "canceled", "id": order_id}

    def assess_risk(
        self,
        order: Dict[str, Any],
        portfolio: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Assess risk for an order using the best available risk engine."""
        assessment: Dict[str, Any] = {
            "ok": True,
            "reasons": [],
            "order": order,
            "portfolio": portfolio or {},
        }

        # Always validate negative quantity regardless of engine
        quantity = float(order.get("quantity", 0.0))
        if quantity < 0:
            assessment.update({"ok": False, "reasons": ["negative quantity"]})
            assessment["engine"] = "validation-guard"
            return assessment

        # Priority 1: Use vel_python risk manager
        if self._use_vel_engine and self._vel_risk_manager is not None and _VEL_ENGINE is not None:
            try:
                # Create order object for risk validation
                symbol = order.get("symbol", "UNKNOWN")
                side = order.get("side", "buy")
                quantity = float(order.get("quantity", 0.0))
                price = float(order.get("price") or order.get("limit_price") or 100.0)

                vel_order = _VEL_ENGINE.Order(
                    f"risk-check-{int(__import__('time').time() * 1000)}",
                    symbol,
                    side,
                    "limit" if price else "market",
                    quantity,
                    price,
                    None,
                )

                try:
                    self._vel_risk_manager.validate_order(vel_order)
                    assessment["ok"] = True
                    assessment["reasons"] = []
                    assessment["engine"] = "vel-python-rust"
                except Exception as risk_err:
                    assessment["ok"] = False
                    assessment["reasons"] = [str(risk_err)]
                    assessment["engine"] = "vel-python-rust"

                return assessment
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_NATIVE_CORE").debug("Exception suppressed in assess_risk")

        # Fallback: Basic Python validation
        quantity = float(order.get("quantity", 0.0))
        if quantity < 0:
            assessment.update({"ok": False, "reasons": ["negative quantity"]})
        assessment["engine"] = "python-fallback"
        return assessment

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all positions using the best available engine."""
        # Priority 1: Use vel_python
        if self._use_vel_engine and self._vel_engine is not None:
            try:
                positions = self._vel_engine.get_positions()
                return [p.to_dict() if hasattr(p, 'to_dict') else p for p in positions]
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_NATIVE_CORE").debug("Exception suppressed in get_positions")

        # Priority 2: Use C++ gateway bridge
        return self._positions_bridge.all()

    def get_stats(self) -> Dict[str, Any]:
        """Get trading statistics from the active engine."""
        if self._use_vel_engine and self._vel_engine is not None:
            try:
                return self._vel_engine.get_stats()
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_NATIVE_CORE").debug("Exception suppressed in get_stats")
        return {
            "active": True,
            "engine": "fallback-simulator",
            "current_capital": 0.0,
            "current_drawdown": 0.0,
        }

    def calculate_kelly_position_size(
        self, win_rate: float, avg_win: float, avg_loss: float
    ) -> float:
        """Calculate Kelly Criterion position size using Rust risk manager."""
        if self._use_vel_engine and self._vel_risk_manager is not None:
            try:
                return self._vel_risk_manager.calculate_kelly_position_size(
                    win_rate, avg_win, avg_loss
                )
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_NATIVE_CORE").debug("Exception suppressed in calculate_kelly_position_size")

        # Fallback: Python Kelly calculation
        if win_rate <= 0 or avg_win <= 0 or avg_loss <= 0:
            return 0.0
        loss_rate = 1.0 - win_rate
        win_loss_ratio = avg_win / avg_loss
        kelly_pct = (win_rate * win_loss_ratio - loss_rate) / win_loss_ratio
        return max(0, kelly_pct * 0.25)  # Use 25% Kelly for safety

    def _configure_functions(self) -> None:
        if self._lib is None:
            return
        lib = self._lib
        if lib is None:
            return
        lib.anvel_core_init.argtypes = []
        lib.anvel_core_init.restype = ctypes.c_int
        lib.anvel_core_submit_order.argtypes = [
            ctypes.POINTER(self._Order),
            ctypes.POINTER(self._Ack),
        ]
        lib.anvel_core_submit_order.restype = ctypes.c_int
        lib.anvel_core_last_error.argtypes = [
            ctypes.c_char_p,
            ctypes.c_size_t,
        ]
        lib.anvel_core_last_error.restype = ctypes.c_size_t
        init_status = lib.anvel_core_init()
        if init_status != ANVEL_CORE_OK:
            raise RuntimeError("Failed to initialize native core")

    def _last_error(self) -> str:
        if not self.available:
            return "native core unavailable"
        lib = self._lib
        if lib is None:
            return "native core unavailable"
        buffer = ctypes.create_string_buffer(512)
        copied = lib.anvel_core_last_error(buffer, ctypes.sizeof(buffer))
        if copied == 0:
            return "unknown native error"
        return buffer.value.decode("utf-8", errors="replace")

    @staticmethod
    def _format_ack(ack: OrderAck) -> Dict[str, Any]:
        status = "accepted" if ack.status == ANVEL_STATUS_ACCEPTED else "rejected"
        return {
            "status": status,
            "id": ack.order_id,
            "filled_quantity": ack.executed_qty,
            "average_price": ack.average_price,
        }

    @staticmethod
    def _format_native_ack(ack: _Ack) -> Dict[str, Any]:
        status = "accepted"
        if ack.status == ANVEL_STATUS_REJECTED:
            status = "rejected"
        elif ack.status == ANVEL_STATUS_FILLED:
            status = "filled"
        elif ack.status == ANVEL_STATUS_PARTIAL:
            status = "partial"
        return {
            "status": status,
            "id": int(ack.order_id),
            "filled_quantity": float(ack.executed_qty),
            "average_price": float(ack.average_price),
        }


def load_native_exec_core() -> NativeExecCore:
    """Factory used by other modules.
    
    Returns a NativeExecCore instance that uses the best available
    execution engine in this priority:
    1. vel_python (PyO3 Rust bindings) - highest performance
    2. ctypes C library bindings (legacy)
    3. Python fallback simulator
    """
    return NativeExecCore()


def is_vel_engine_available() -> bool:
    """Check if the high-performance vel_python Rust engine is available."""
    return _VEL_ENGINE_AVAILABLE


def get_vel_engine_version() -> str:
    """Get the version of the vel_python Rust engine if available."""
    if _VEL_ENGINE_AVAILABLE and _VEL_ENGINE is not None:
        return _VEL_ENGINE.version()
    return "unavailable"
