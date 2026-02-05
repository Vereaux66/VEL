#!/usr/bin/env python3
"""Bridge continuous learning outputs into strategy and decision layers."""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, List, Optional, cast

try:  # pragma: no cover - scientific stack may be absent in tests
    import numpy as np
except Exception:  # pragma: no cover - fallback maths
    np = None

from anvel_continuous_learning import (
    ContinuousLearningSystem,
    KnowledgeRecord,
)
from anvel_strategy_core import ANVELStrategyCore

logger = logging.getLogger(__name__)


def _clamp(value: float, lower: float, upper: float) -> float:
    """Clamp ``value`` between ``lower`` and ``upper`` inclusive."""
    return max(lower, min(upper, value))


def _safe_correlation(xs: List[float], ys: List[float]) -> Optional[float]:
    """Compute correlation without depending on numpy at runtime."""
    n = min(len(xs), len(ys))
    if n < 3:
        return None
    mean_x = sum(xs[:n]) / n
    mean_y = sum(ys[:n]) / n
    cov = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n)) / n
    var_x = sum((xs[i] - mean_x) ** 2 for i in range(n)) / n
    var_y = sum((ys[i] - mean_y) ** 2 for i in range(n)) / n
    if var_x == 0.0 or var_y == 0.0:
        return None
    return cov / math.sqrt(var_x * var_y)


@dataclass
class SymbolKnowledgeStats:
    """Running statistics for knowledge emitted by the learning engine."""

    symbol: str
    entry_count: int = 0
    total: int = 0
    correct: int = 0
    sum_abs_error: float = 0.0
    sum_confidence: float = 0.0
    predictions: Deque[float] = field(default_factory=lambda: deque(maxlen=256))
    targets: Deque[float] = field(default_factory=lambda: deque(maxlen=256))
    last_prediction: float = 0.0
    last_confidence: float = 0.0
    last_risk: Dict[str, float] = field(
        default_factory=lambda: cast(Dict[str, float], {})
    )
    last_timestamp: float = 0.0

    def register(self, entry: Dict[str, Any]) -> None:
        prediction = float(entry.get("prediction", 0.0))
        confidence = float(entry.get("confidence", 0.0))
        timestamp = float(entry.get("timestamp", 0.0))
        risk = dict(entry.get("risk", {}))

        self.entry_count += 1
        self.last_prediction = prediction
        self.last_confidence = confidence
        self.last_risk = risk
        self.last_timestamp = timestamp
        self.sum_confidence += confidence
        self.predictions.append(prediction)

        target = entry.get("target")
        if target is None:
            return

        target_value = float(target)
        self.total += 1
        self.targets.append(target_value)
        self.sum_abs_error += abs(target_value - prediction)

        if target_value != 0.0 and math.copysign(1.0, target_value) == math.copysign(
            1.0, prediction
        ):
            self.correct += 1

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def mae(self) -> float:
        return self.sum_abs_error / self.total if self.total else 0.0

    @property
    def mean_confidence(self) -> float:
        if not self.entry_count:
            return 0.0
        return self.sum_confidence / self.entry_count

    @property
    def correlation(self) -> Optional[float]:
        if len(self.predictions) < 3 or len(self.targets) < 3:
            return None
        if np is not None:  # pragma: no branch - prefer numpy when available
            try:
                preds = np.asarray(list(self.predictions), dtype=float)
                trgs = np.asarray(list(self.targets), dtype=float)
                matrix = np.corrcoef(preds, trgs)
                value = float(matrix[0, 1])
                if math.isnan(value):
                    return None
                return value
            except Exception:  # pragma: no cover - fallback path
                return _safe_correlation(list(self.predictions), list(self.targets))
        return _safe_correlation(list(self.predictions), list(self.targets))


class LearningStrategyBridge:
    """Fuse continuous learning signals into strategy layer decisions."""

    def __init__(
        self,
        learning: ContinuousLearningSystem,
        strategy: Optional[ANVELStrategyCore] = None,
        *,
        symbols: Optional[Iterable[str]] = None,
        history_limit: int = 512,
        boost_limit: float = 0.65,
        risk_penalty_scale: float = 15.0,
        error_penalty_scale: float = 6.0,
        prediction_scale: float = 10.0,
        confidence_scale: float = 1.0,
        risk_gate_scale: float = 10.0,
        bias_floor: float = 0.2,
        bias_ceiling: float = 1.15,
        auto_recalibrate: bool = True,
        recalibration_interval: int = 25,
    ) -> None:
        self.learning = learning
        self.strategy = strategy
        self.history_limit = history_limit
        self.boost_limit = boost_limit
        self.risk_penalty_scale = risk_penalty_scale
        self.error_penalty_scale = error_penalty_scale
        self.prediction_scale = prediction_scale
        self.confidence_scale = confidence_scale
        self.risk_gate_scale = risk_gate_scale
        self.bias_floor = bias_floor
        self.bias_ceiling = bias_ceiling
        self.auto_recalibrate = auto_recalibrate
        self.recalibration_interval = recalibration_interval

        self._history: Dict[str, Deque[Dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=self.history_limit)
        )
        self._stats: Dict[str, SymbolKnowledgeStats] = {}
        self._bias: Dict[str, float] = defaultdict(lambda: 1.0)
        self._boost: Dict[str, float] = defaultdict(float)

        logger.debug("Binding learning bridge to continuous learning system")
        self.learning.register_knowledge_listener(self._on_knowledge)
        self._prime_existing(symbols)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def decide(self, context: Dict[str, Any]) -> float:
        """Return a strategy decision blended with learning-derived bias."""
        if not self.strategy:
            raise RuntimeError("Strategy core not attached to bridge")

        symbol = context.get("symbol")
        strategy_context = dict(context)
        if symbol:
            latest = self.latest(symbol)
            if latest:
                strategy_context.setdefault("knowledge_meta", latest)
                strategy_context.setdefault("knowledge_metrics", self.metrics(symbol))

        base_signal = self.strategy.ensemble_decision(strategy_context)
        if symbol is None:
            return float(_clamp(base_signal, -1.0, 1.0))

        bias = self._bias.get(symbol, 1.0)
        boost = self._boost.get(symbol, 0.0)
        adjusted = base_signal * bias + boost
        return float(_clamp(adjusted, -1.0, 1.0))

    def recalibrate_strategy_weights(self) -> Dict[str, float]:
        """Scale strategy weights based on aggregate knowledge accuracy."""
        if not self.strategy:
            return {}

        weights = cast(Dict[str, float], getattr(self.strategy, "weights", {}))
        if not weights:
            return {}

        accuracy = self.global_accuracy
        adjustment = _clamp(0.8 + accuracy, 0.6, 1.3)
        for name, weight in list(weights.items()):
            weights[name] = _clamp(weight * adjustment, 0.1, 2.0)
        return dict(weights)

    def latest(self, symbol: str) -> Optional[Dict[str, Any]]:
        history = self._history.get(symbol)
        if not history:
            return None
        return dict(history[-1])

    def history(self, symbol: str, limit: int = 20) -> List[Dict[str, Any]]:
        history = self._history.get(symbol)
        if not history:
            return []
        return [dict(entry) for entry in list(history)[-limit:]]

    def metrics(self, symbol: str) -> Dict[str, Any]:
        stats = self._stats.get(symbol)
        if not stats:
            return {}
        return {
            "accuracy": stats.accuracy,
            "mae": stats.mae,
            "mean_confidence": stats.mean_confidence,
            "correlation": stats.correlation,
            "bias": self._bias.get(symbol, 1.0),
            "boost": self._boost.get(symbol, 0.0),
            "timestamp": stats.last_timestamp,
        }

    @property
    def global_accuracy(self) -> float:
        total = 0
        correct = 0
        for stats in self._stats.values():
            total += stats.total
            correct += stats.correct
        return correct / total if total else 0.0

    # ------------------------------------------------------------------
    # Internal plumbing
    # ------------------------------------------------------------------
    def _prime_existing(self, symbols: Optional[Iterable[str]]) -> None:
        seed_symbols: Iterable[str]
        if symbols is not None:
            seed_symbols = symbols
        else:
            seed_symbols = getattr(self.learning, "symbols", [])
        for symbol in seed_symbols:
            payloads = self.learning.knowledge_summary(
                symbol,
                limit=self.history_limit,
            )
            for payload in payloads:
                entry = self._normalize_payload(payload)
                self._register_entry(symbol, entry, warm_start=True)

    def _on_knowledge(self, record: KnowledgeRecord) -> None:
        try:
            entry: Dict[str, Any] = {
                "symbol": record.symbol,
                "timestamp": record.timestamp,
                "prediction": record.prediction,
                "target": record.target,
                "confidence": record.confidence,
                "risk": dict(record.risk_summary),
                "patterns": dict(record.pattern_summary),
                "trailing": dict(record.trailing_metrics),
                "metadata": dict(record.metadata),
            }
            self._register_entry(record.symbol, entry, warm_start=False)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception(
                "Learning bridge failed to ingest record: %s",
                exc,
            )

    def _register_entry(
        self,
        symbol: str,
        entry: Dict[str, Any],
        *,
        warm_start: bool,
    ) -> None:
        history = self._history[symbol]
        history.append(entry)

        stats = self._stats.get(symbol)
        if stats is None:
            stats = SymbolKnowledgeStats(symbol=symbol)
            self._stats[symbol] = stats
        stats.register(entry)

        self._bias[symbol] = self._compute_bias(stats)
        self._boost[symbol] = self._compute_boost(stats)

        if (
            self.strategy
            and self.auto_recalibrate
            and not warm_start
            and stats.total
            and stats.total % self.recalibration_interval == 0
        ):
            self.recalibrate_strategy_weights()

    def _compute_bias(self, stats: SymbolKnowledgeStats) -> float:
        risk = stats.last_risk or {}
        risk_penalty = max(
            abs(risk.get("var_95", 0.0)),
            abs(risk.get("cvar_95", 0.0)),
        )
        bias = 1.0 - risk_penalty * self.risk_penalty_scale
        bias *= _clamp(0.5 + stats.accuracy, 0.5, 1.5)
        if stats.mae:
            bias *= _clamp(
                1.0 - stats.mae * self.error_penalty_scale,
                0.3,
                1.2,
            )
        return _clamp(bias, self.bias_floor, self.bias_ceiling)

    def _compute_boost(self, stats: SymbolKnowledgeStats) -> float:
        risk = stats.last_risk or {}
        risk_penalty = max(
            abs(risk.get("var_95", 0.0)),
            abs(risk.get("cvar_95", 0.0)),
        )
        gate = stats.mean_confidence * self.confidence_scale
        gate *= _clamp(0.5 + stats.accuracy, 0.0, 1.5)
        gate = _clamp(gate - risk_penalty * self.risk_gate_scale, 0.0, 1.0)
        boost = stats.last_prediction * self.prediction_scale * gate
        return _clamp(boost, -self.boost_limit, self.boost_limit)

    def _normalize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "symbol": payload.get("symbol"),
            "timestamp": float(payload.get("timestamp", 0.0)),
            "prediction": float(payload.get("prediction", 0.0)),
            "target": payload.get("target"),
            "confidence": float(payload.get("confidence", 0.0)),
            "risk": dict(payload.get("risk_summary", payload.get("risk", {}))),
            "patterns": dict(payload.get("pattern_summary", {})),
            "trailing": dict(payload.get("trailing_metrics", {})),
            "metadata": dict(payload.get("metadata", {})),
        }


__all__ = ["LearningStrategyBridge", "SymbolKnowledgeStats"]
