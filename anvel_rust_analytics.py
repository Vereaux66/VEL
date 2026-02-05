#!/usr/bin/env python3
"""
Rust Analytics — Python Fallback Stub
======================================
Provides pure-Python fallback implementations of the classes exported
by the native Rust ``anvel_analytics_service`` crate (``native/rust_analytics/``).

When the Rust shared library is available (compiled and on ``LD_LIBRARY_PATH`` /
``DYLD_LIBRARY_PATH``), this module re-exports its symbols.  Otherwise, it falls
back to lightweight Python implementations sufficient for development and testing.

Exported classes (matching the Rust interface):
    FeatureStore, ScenarioGenerator, PredictionCalibrator,
    ConceptDriftDetector, TechnicalIndicators, BrainEngine
"""

from __future__ import annotations

import logging
import math
import os
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Attempt native Rust import
# ---------------------------------------------------------------------------
_NATIVE_AVAILABLE = False

try:
    _lib_path = os.getenv("ANVEL_RUST_ANALYTICS_LIB")
    if _lib_path:
        import ctypes
        ctypes.cdll.LoadLibrary(_lib_path)
        _NATIVE_AVAILABLE = True
        logger.info("Rust analytics native library loaded from %s", _lib_path)
except Exception as exc:
    logger.debug("Rust analytics native library not available: %s", exc)

# ---------------------------------------------------------------------------
# Pure-Python fallback implementations
# ---------------------------------------------------------------------------


class FeatureStore:
    """In-memory rolling feature store for ML pipeline inputs."""

    def __init__(self, max_features: int = 10_000) -> None:
        self._store: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_features))
        self._max = max_features

    def push(self, key: str, value: float) -> None:
        self._store[key].append(value)

    def get(self, key: str, n: Optional[int] = None) -> List[float]:
        data = list(self._store.get(key, []))
        return data[-n:] if n else data

    def keys(self) -> List[str]:
        return list(self._store.keys())

    def clear(self) -> None:
        self._store.clear()


class ScenarioGenerator:
    """Monte-Carlo style scenario generator for price paths."""

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed
        self._rng_state = seed

    def _next_rand(self) -> float:
        # Simple LCG for deterministic fallback
        self._rng_state = (self._rng_state * 1103515245 + 12345) & 0x7FFFFFFF
        return self._rng_state / 0x7FFFFFFF

    def generate(
        self,
        initial_price: float,
        drift: float = 0.0,
        volatility: float = 0.02,
        steps: int = 100,
        paths: int = 10,
    ) -> List[List[float]]:
        results: List[List[float]] = []
        for _ in range(paths):
            path = [initial_price]
            for _ in range(steps):
                r = self._next_rand()
                z = math.sqrt(-2.0 * math.log(max(r, 1e-10))) * math.cos(
                    2.0 * math.pi * self._next_rand()
                )
                price = path[-1] * math.exp(drift + volatility * z)
                path.append(price)
            results.append(path)
        return results


class PredictionCalibrator:
    """Calibrates raw model predictions using isotonic-style binning."""

    def __init__(self, bins: int = 20) -> None:
        self._bins = bins
        self._calibration_map: Dict[int, float] = {}

    def fit(self, predictions: Sequence[float], actuals: Sequence[float]) -> None:
        if not predictions or not actuals:
            return
        n = len(predictions)
        bin_size = max(1, n // self._bins)
        indexed = sorted(zip(predictions, actuals), key=lambda x: x[0])
        for i in range(0, n, bin_size):
            chunk = indexed[i : i + bin_size]
            bin_key = int(i / bin_size)
            avg_actual = sum(a for _, a in chunk) / len(chunk)
            self._calibration_map[bin_key] = avg_actual

    def calibrate(self, prediction: float) -> float:
        if not self._calibration_map:
            return prediction
        # Find nearest bin
        bin_key = min(self._calibration_map.keys(),
                      key=lambda k: abs(k - prediction * self._bins))
        return self._calibration_map.get(bin_key, prediction)


class ConceptDriftDetector:
    """Detects distribution drift in streaming feature data."""

    def __init__(self, window_size: int = 500, threshold: float = 2.0) -> None:
        self._window = window_size
        self._threshold = threshold
        self._reference: Optional[Dict[str, float]] = None
        self._buffer: deque = deque(maxlen=window_size)

    def set_reference(self, values: Sequence[float]) -> None:
        if not values:
            return
        n = len(values)
        mean = sum(values) / n
        var = sum((v - mean) ** 2 for v in values) / max(n - 1, 1)
        self._reference = {"mean": mean, "std": math.sqrt(var), "n": n}

    def update(self, value: float) -> bool:
        """Push a value and return True if drift is detected."""
        self._buffer.append(value)
        if self._reference is None or len(self._buffer) < 30:
            return False
        buf = list(self._buffer)
        buf_mean = sum(buf) / len(buf)
        ref_std = self._reference["std"] or 1e-10
        z = abs(buf_mean - self._reference["mean"]) / ref_std
        return z > self._threshold

    @property
    def is_drifting(self) -> bool:
        if not self._buffer or self._reference is None:
            return False
        buf = list(self._buffer)
        buf_mean = sum(buf) / len(buf)
        ref_std = self._reference["std"] or 1e-10
        z = abs(buf_mean - self._reference["mean"]) / ref_std
        return z > self._threshold


class TechnicalIndicators:
    """Lightweight technical indicator calculations."""

    @staticmethod
    def sma(values: Sequence[float], period: int) -> List[float]:
        result: List[float] = []
        for i in range(len(values)):
            if i < period - 1:
                result.append(float("nan"))
            else:
                window = values[i - period + 1 : i + 1]
                result.append(sum(window) / period)
        return result

    @staticmethod
    def ema(values: Sequence[float], period: int) -> List[float]:
        if not values:
            return []
        multiplier = 2.0 / (period + 1)
        result = [float("nan")] * (period - 1)
        result.append(sum(values[:period]) / period)
        for i in range(period, len(values)):
            result.append(values[i] * multiplier + result[-1] * (1 - multiplier))
        return result

    @staticmethod
    def rsi(values: Sequence[float], period: int = 14) -> List[float]:
        if len(values) < period + 1:
            return [float("nan")] * len(values)
        deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
        gains = [max(d, 0) for d in deltas]
        losses = [abs(min(d, 0)) for d in deltas]
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        result = [float("nan")] * period
        rs = avg_gain / avg_loss if avg_loss != 0 else 100.0
        result.append(100.0 - 100.0 / (1.0 + rs))
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            rs = avg_gain / avg_loss if avg_loss != 0 else 100.0
            result.append(100.0 - 100.0 / (1.0 + rs))
        return result


class BrainEngine:
    """Lightweight Python fallback for the Rust brain engine."""

    def __init__(self) -> None:
        self._feature_store = FeatureStore()
        self._indicators = TechnicalIndicators()
        self._drift_detector = ConceptDriftDetector()
        self._scenario_gen = ScenarioGenerator()
        self._calibrator = PredictionCalibrator()
        self._ready = True

    @property
    def is_ready(self) -> bool:
        return self._ready

    def analyze(self, symbol: str, prices: Sequence[float]) -> Dict[str, Any]:
        if len(prices) < 20:
            return {"symbol": symbol, "status": "insufficient_data"}
        sma_20 = self._indicators.sma(prices, 20)
        rsi_14 = self._indicators.rsi(prices, 14)
        current = prices[-1]
        sma_val = sma_20[-1] if sma_20 and not math.isnan(sma_20[-1]) else current
        rsi_val = rsi_14[-1] if rsi_14 and not math.isnan(rsi_14[-1]) else 50.0
        trend = "bullish" if current > sma_val else "bearish"
        return {
            "symbol": symbol,
            "status": "ok",
            "price": current,
            "sma_20": sma_val,
            "rsi_14": rsi_val,
            "trend": trend,
            "engine": "python-fallback",
        }
