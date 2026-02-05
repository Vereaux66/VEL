#!/usr/bin/env python3
"""Advanced analytics backbone for ANVEL.

The analytics core ingests market data, maintains rolling statistics, and
produces diagnostics for the trading brain and continuous learning system.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from importlib import util as importlib_util
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, cast

import numpy as np
import pandas as pd


def skew(values: Iterable[float]) -> float:
    data = np.asarray(list(values), dtype=float)
    n = data.size
    if n < 3:
        return 0.0
    mean = float(data.mean())
    std = float(data.std(ddof=0))
    if std == 0.0:
        return 0.0
    standardized = (data - mean) / std
    return float((n / ((n - 1) * (n - 2))) * np.sum(standardized**3))


def kurtosis(values: Iterable[float]) -> float:
    data = np.asarray(list(values), dtype=float)
    n = data.size
    if n < 4:
        return 0.0
    mean = float(data.mean())
    std = float(data.std(ddof=0))
    if std == 0.0:
        return 0.0
    standardized = (data - mean) / std
    term1 = (n * (n + 1)) / ((n - 1) * (n - 2) * (n - 3))
    term2 = (standardized**4).sum()
    term3 = (3 * (n - 1) ** 2) / ((n - 2) * (n - 3))
    return float(term1 * term2 - term3)


logger = logging.getLogger(__name__)


def _load_archive_class(relative_path: str, class_name: str):
    base_path = Path(__file__).resolve().parent / relative_path
    if not base_path.exists():
        raise FileNotFoundError(f"Archive file not found: {base_path}")
    loader = SourceFileLoader(
        f"archive_{class_name}",
        str(base_path),
    )
    spec = importlib_util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise ImportError(f"Cannot create spec for {base_path}")
    module = importlib_util.module_from_spec(spec)
    loader.exec_module(module)
    cls = getattr(module, class_name, None)
    if cls is None:
        raise AttributeError(
            f"Class {class_name} missing from archive module {base_path}"
        )
    return cls


@dataclass
class MetricSnapshot:
    """Single snapshot of summary metrics for a symbol."""

    timestamp: pd.Timestamp
    price: float
    returns: float
    volatility: float
    sharpe: float
    drawdown: float
    skewness: float
    kurt: float
    confidence: float


@dataclass
class RiskProfile:
    """Risk profile across multiple measures."""

    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float
    max_drawdown: float
    ulcer_index: float


@dataclass
class PatternInsight:
    """Represents a detected market pattern."""

    name: str
    score: float
    direction: str
    horizon_minutes: int
    metadata: Dict[str, Any] = field(default_factory=lambda: cast(Dict[str, Any], {}))


@dataclass
class AnalyticsReport:
    """Composite analytics output produced on demand."""

    symbol: str
    snapshot: Optional[MetricSnapshot]
    risk: Optional[RiskProfile]
    patterns: List[PatternInsight]
    trailing_metrics: Dict[str, float]
    alerts: List[str]


class TimeSeriesVault:
    """Maintains rolling windows of market frames per symbol."""

    def __init__(self, maxlen: int = 20000):
        self.maxlen = maxlen
        self.store: Dict[str, deque[pd.DataFrame]] = {}

    def push(self, symbol: str, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        if symbol not in self.store:
            self.store[symbol] = deque(maxlen=self.maxlen)
        self.store[symbol].append(frame.copy())

    def series(self, symbol: str, lookback: int = 1) -> Optional[pd.DataFrame]:
        frames = self.store.get(symbol)
        if not frames:
            return None
        if lookback < len(frames):
            selection = list(frames)[-lookback:]
        else:
            selection = list(frames)
        return pd.concat(selection, axis=0, ignore_index=True)


class RiskEngine:
    """Calculates risk statistics from return series."""

    def compute_profile(self, prices: Optional[pd.Series]) -> Optional[RiskProfile]:
        if prices is None or prices.empty:
            return None
        returns = prices.pct_change().dropna()
        if returns.empty:
            return None

        sorted_returns = np.sort(
            cast(np.ndarray, returns.to_numpy(dtype=float, copy=True))
        )
        var_95 = np.percentile(sorted_returns, 5)
        var_99 = np.percentile(sorted_returns, 1)
        cvar_95 = sorted_returns[sorted_returns <= var_95].mean()
        cvar_99 = sorted_returns[sorted_returns <= var_99].mean()

        rolling_max = prices.cummax()
        drawdowns = (prices / rolling_max) - 1.0
        max_drawdown = float(drawdowns.min())
        ulcer_index = float(np.sqrt(np.mean(np.square(np.minimum(drawdowns, 0)))))

        return RiskProfile(
            var_95=float(var_95),
            var_99=float(var_99),
            cvar_95=float(cvar_95),
            cvar_99=float(cvar_99),
            max_drawdown=max_drawdown,
            ulcer_index=ulcer_index,
        )


class PatternEngine:
    """Detects momentum, mean-reversion, and breakout style patterns."""

    def __init__(self, min_length: int = 120):
        self.min_length = min_length

    def detect(self, prices: Optional[pd.Series]) -> List[PatternInsight]:
        if prices is None or len(prices) < self.min_length:
            return []

        recent = prices.tail(self.min_length)
        returns = recent.pct_change().dropna()
        if returns.empty:
            return []

        patterns: List[PatternInsight] = []

        momentum = float((recent.iloc[-1] / recent.iloc[0]) - 1.0)
        patterns.append(
            PatternInsight(
                name="momentum",
                score=abs(momentum),
                direction="bull" if momentum > 0 else "bear",
                horizon_minutes=30,
                metadata={"cumulative_return": momentum},
            )
        )

        mean = float(recent.mean())
        std = float(recent.std() or 1e-9)
        z_score = float((recent.iloc[-1] - mean) / std)
        patterns.append(
            PatternInsight(
                name="mean_reversion",
                score=abs(z_score),
                direction="bear" if z_score > 0 else "bull",
                horizon_minutes=15,
                metadata={"z_score": z_score},
            )
        )

        window = recent.tail(int(self.min_length / 3))
        denom = recent.max() - recent.min() + 1e-9
        range_ratio = float((window.max() - window.min()) / denom)
        direction = "bull" if window.iloc[-1] > window.mean() else "bear"
        patterns.append(
            PatternInsight(
                name="volatility_breakout",
                score=range_ratio,
                direction=direction,
                horizon_minutes=10,
                metadata={"range_ratio": range_ratio},
            )
        )

        return patterns


class ScenarioEngine:
    """Simulates stress scenarios and returns projected impacts."""

    def __init__(self, shocks: Optional[List[float]] = None):
        self.shocks = shocks or [-0.1, -0.05, 0.05, 0.1]

    def run(self, prices: Optional[pd.Series]) -> Dict[str, float]:
        if prices is None or prices.empty:
            return {}
        last_price = float(prices.iloc[-1])
        return {f"shock_{int(s * 100)}": last_price * (1.0 + s) for s in self.shocks}


class MetricRegistry:
    """Tracks and smooths metrics over time for each symbol."""

    def __init__(self, window: int = 500):
        self.window = window
        self.metrics: Dict[str, deque[MetricSnapshot]] = defaultdict(
            lambda: deque(maxlen=self.window)
        )

    def record(self, symbol: str, snapshot: MetricSnapshot) -> None:
        self.metrics[symbol].append(snapshot)

    def latest(self, symbol: str) -> Optional[MetricSnapshot]:
        queue = self.metrics.get(symbol)
        return queue[-1] if queue else None

    def trailing_average(
        self, symbol: str, metric: str, span: int = 20
    ) -> Optional[float]:
        queue = self.metrics.get(symbol)
        if not queue:
            return None
        values = [
            getattr(snapshot, metric)
            for snapshot in list(queue)[-span:]
            if hasattr(snapshot, metric)
        ]
        if not values:
            return None
        return float(np.mean(values))


class TemporalSignalLab:
    """Generates enriched time-series diagnostics for downstream modules."""

    def __init__(self, history: int = 256):
        self.history = defaultdict(lambda: deque(maxlen=history))

    def generate(self, symbol: str, prices: pd.Series) -> Dict[str, float]:
        if prices.empty:
            return {}
        series = prices.astype(float)
        detrended = series - series.mean()
        spectrum = np.fft.rfft(detrended.to_numpy(copy=True))
        spectral_power = np.abs(spectrum)
        dominant = float(np.max(spectral_power)) if spectral_power.size else 0.0
        second = (
            float(np.partition(spectral_power, -2)[-2])
            if spectral_power.size > 1
            else dominant
        )
        freq_ratio = float(dominant / (second + 1e-9)) if second else 0.0
        volatility = float(series.pct_change().dropna().std() or 0.0)
        z_scores = (detrended / (detrended.std() + 1e-9)).abs()
        anomaly = float(z_scores.tail(1).iloc[0]) if not z_scores.empty else 0.0
        rolling = series.rolling(window=min(50, len(series))).mean().iloc[-1]
        projection = float(rolling)
        features = {
            "spectral_dominance": dominant,
            "frequency_ratio": freq_ratio,
            "volatility_signal": volatility,
            "anomaly_score": anomaly,
            "projection": projection,
        }
        self.history[symbol].append((pd.Timestamp.utcnow(), features))
        return features

    def latest(self, symbol: str) -> Dict[str, float]:
        queue = self.history.get(symbol)
        if not queue:
            return {}
        return queue[-1][1]


class AnvelAnalyticsCore:
    """High-level analytics facade used by the continuous learning system."""

    def __init__(self, window: int = 5000):
        self.vault = TimeSeriesVault(maxlen=window)
        self.risk_engine = RiskEngine()
        self.pattern_engine = PatternEngine()
        self.scenario_engine = ScenarioEngine()
        self.registry = MetricRegistry(window=window)
        self.temporal_lab = TemporalSignalLab()
        self.trade_history: Dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=window)
        )
        self.alert_history: Dict[str, deque[str]] = defaultdict(
            lambda: deque(maxlen=50)
        )
        self.signal_traces: Dict[str, Dict[str, float]] = defaultdict(dict)
        pattern_cls = _load_archive_class(
            (
                "archive_consolidation/ARCHIVE/"
                "phase5-analytics-20251019-054914/anvel_pattern_detector.py"
            ),
            "ANVELPatternDetector",
        )
        detector = pattern_cls()
        detector.register_pattern("momentum_spike", r"momentum")
        detector.register_pattern("mean_reversion", r"mean_reversion")
        data_mining_cls = _load_archive_class(
            (
                "archive_consolidation/ARCHIVE/"
                "phase5-analytics-20251019-054914/anvel_data_mining.py"
            ),
            "ANVELDataMining",
        )
        self.data_mining = data_mining_cls(detector=detector)

    def ingest_market_frame(self, symbol: str, frame: pd.DataFrame) -> None:
        frame = frame.copy()
        if frame.empty:
            return
        if "timestamp" in frame:
            frame = cast(pd.DataFrame, frame.sort_values("timestamp"))
        self.vault.push(symbol, frame)
        self._update_metrics(symbol, frame)

    def record_trade_outcome(self, symbol: str, pnl: float, note: str = "") -> None:
        self.trade_history[symbol].append(float(pnl))
        mining_record = {
            "symbol": symbol,
            "pnl": pnl,
            "note": note,
        }
        self.data_mining.analyze_record(mining_record)
        if abs(pnl) > 0 and (len(self.trade_history[symbol]) % 10 == 0):
            sharpe = self.registry.trailing_average(symbol, "sharpe", span=50) or 0.0
            msg = note or f"P&L {pnl:.2f} | trailing_sharpe {sharpe:.2f}"
            self.alert_history[symbol].append(msg)

    def market_series(
        self, symbol: str, lookback: int = 2000
    ) -> Optional[pd.DataFrame]:
        return self.vault.series(symbol, lookback)

    def analytics_report(self, symbol: str) -> AnalyticsReport:
        series = self.vault.series(symbol)
        prices = (
            series["close"].astype(float)
            if series is not None and "close" in series
            else None
        )
        snapshot = self.registry.latest(symbol)
        risk = self.risk_engine.compute_profile(prices) if prices is not None else None
        patterns = self.pattern_engine.detect(prices) if prices is not None else []

        trailing = {
            "returns": (
                self.registry.trailing_average(symbol, "returns", span=50) or 0.0
            ),
            "volatility": (
                self.registry.trailing_average(symbol, "volatility", span=50) or 0.0
            ),
            "confidence": (
                self.registry.trailing_average(symbol, "confidence", span=50) or 0.0
            ),
        }

        signals = self.signal_traces.get(symbol)
        if signals:
            trailing.update({f"signal_{k}": v for k, v in signals.items()})

        alerts = list(self.alert_history[symbol])
        mining_summary = self.data_mining.summary()
        if mining_summary:
            trailing.update({f"mining_{k}": v for k, v in mining_summary.items()})

        return AnalyticsReport(
            symbol=symbol,
            snapshot=snapshot,
            risk=risk,
            patterns=patterns,
            trailing_metrics=trailing,
            alerts=alerts,
        )

    def scenario_projection(self, symbol: str) -> Dict[str, float]:
        series = self.vault.series(symbol)
        if series is None or "close" not in series:
            return {}
        prices = series["close"]
        return self.scenario_engine.run(prices)

    def _update_metrics(self, symbol: str, frame: pd.DataFrame) -> None:
        if "close" not in frame:
            return
        closes = frame["close"].astype(float)
        if closes.empty:
            return

        returns = closes.pct_change().dropna()
        if returns.empty:
            return

        timestamp = (
            frame["timestamp"].iloc[-1]
            if "timestamp" in frame
            else pd.Timestamp.utcnow()
        )
        volatility = float(returns.std()) * np.sqrt(252) if len(returns) > 1 else 0.0
        sharpe = (
            float((returns.mean() / (returns.std() + 1e-9)) * np.sqrt(252))
            if returns.std()
            else 0.0
        )
        drawdown = float(((closes / closes.cummax()) - 1.0).min())
        skewness = skew(returns)
        kurt = kurtosis(returns)
        confidence = float(
            np.clip(1.0 - abs(skewness) - abs(kurt - 3.0) * 0.1, 0.0, 1.0)
        )

        snapshot = MetricSnapshot(
            timestamp=timestamp,
            price=float(closes.iloc[-1]),
            returns=float(returns.iloc[-1]),
            volatility=volatility,
            sharpe=sharpe,
            drawdown=drawdown,
            skewness=skewness,
            kurt=kurt,
            confidence=confidence,
        )

        self.registry.record(symbol, snapshot)

        if confidence < 0.2:
            alert = f"Low confidence regime detected (conf={confidence:.2f})"
            self.alert_history[symbol].append(alert)

        features = self.temporal_lab.generate(symbol, closes)
        if features:
            self.signal_traces[symbol] = features
            if features.get("anomaly_score", 0.0) > 2.5:
                self.alert_history[symbol].append(
                    "Temporal anomaly spike score=" f"{features['anomaly_score']:.2f}"
                )
