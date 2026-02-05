#!/usr/bin/env python3
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportMissingImports=false
"""ANVEL Continuous Learning Engine.

This module fuses the analytics backbone with adaptive online learning to
continuously refine trade intelligence while enforcing strict risk
controls. It is designed to run 24/7 with graceful degradation when
scientific dependencies are unavailable.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from pathlib import Path
from operator import attrgetter
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Deque,
    Dict,
    Iterable,
    List,
    Optional,
    Tuple,
    cast,
)
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd  # type: ignore
from numpy.typing import NDArray

try:
    from sklearn.exceptions import NotFittedError  # type: ignore
    from sklearn.linear_model import SGDRegressor  # type: ignore
    from sklearn.preprocessing import StandardScaler  # type: ignore
except Exception as exc:  # pragma: no cover - dependency guard
    raise RuntimeError(
        "scikit-learn is required for continuous learning; install" " scikit-learn>=1.3"
    ) from exc

from anvel_analytics_core import (
    AnalyticsReport,
    AnvelAnalyticsCore,
    PatternInsight,
    RiskProfile,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


FloatArray = NDArray[np.float64]


def _empty_float_dict() -> Dict[str, float]:
    return {}


if TYPE_CHECKING:
    from anvel_event_bus import AnvelEventBus
    from anvel_memory import ANVELPredictiveMemory, AnvelMemory


@dataclass
class LearningSample:
    """Represents a single supervised sample."""

    features: FloatArray
    target: float
    timestamp: pd.Timestamp


@dataclass
class PredictionOutcome:
    """Captures the result of a prediction with diagnostics."""

    prediction: float
    target: Optional[float]
    risk_gate_passed: bool
    confidence: float
    metadata: Dict[str, float] = field(default_factory=_empty_float_dict)


@dataclass
class KnowledgeRecord:
    """Stores distilled learning artifacts for wider system consumption."""

    symbol: str
    timestamp: float
    prediction: float
    target: Optional[float]
    confidence: float
    risk_summary: Dict[str, float]
    pattern_summary: Dict[str, float]
    trailing_metrics: Dict[str, float]
    feature_vector: List[float]
    metadata: Dict[str, float] = field(default_factory=_empty_float_dict)


class KnowledgeRepository:
    """Stores learned insights and broadcasts them to collaborating modules."""

    def __init__(
        self,
        persist_path: Optional[Path] = None,
        retention: int = 5000,
        memory: Optional["AnvelMemory"] = None,
        event_bus: Optional["AnvelEventBus"] = None,
    ):
        self.persist_path = persist_path
        self.retention = retention
        self.memory = memory
        self.event_bus = event_bus
        self._store: Dict[str, Deque[KnowledgeRecord]] = defaultdict(
            lambda: deque(maxlen=self.retention)
        )
        self._lock = threading.Lock()
        if self.persist_path:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: KnowledgeRecord) -> None:
        payload = self._payload(record)
        with self._lock:
            self._store[record.symbol].append(record)
            if self.persist_path:
                with self.persist_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(payload) + "\n")

        if self.memory:
            risk_95 = record.risk_summary.get("var_95", 0.0)
            summary = (
                f"{record.symbol} pred={record.prediction:.4f} "
                f"conf={record.confidence:.2f} risk={risk_95:.4f}"
            )
            self.memory.remember(summary, tag="learning", scope="continuous")

        if self.event_bus:
            self.event_bus.publish("system.update", payload)
            self.event_bus.publish("learning.knowledge", payload)

    def latest(
        self, symbol: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        with self._lock:
            if symbol is not None:
                queue = list(self._store.get(symbol, deque()))
                records = queue[-limit:]
            else:
                records = []
                for queue in self._store.values():
                    records.extend(queue)
                records = sorted(
                    records,
                    key=attrgetter("timestamp"),
                )[-limit:]
        return [self._payload(record) for record in records]

    def performance_snapshot(self, symbol: str, window: int = 100) -> Dict[str, float]:
        with self._lock:
            records = list(self._store.get(symbol, deque()))[-window:]

        if not records:
            return {}

        preds = np.array([r.prediction for r in records], dtype=float)
        confs = np.array([r.confidence for r in records], dtype=float)
        targets = np.array(
            [r.target for r in records if r.target is not None],
            dtype=float,
        )

        snapshot: Dict[str, float] = {
            "avg_prediction": float(preds.mean()),
            "avg_confidence": float(confs.mean()),
            "prediction_volatility": float(preds.std()),
        }

        if targets.size and targets.size == preds.size:
            snapshot["rmse"] = float(np.sqrt(np.mean(np.square(preds - targets))))
        elif targets.size:
            aligned = preds[: targets.size]
            if aligned.size > 1 and targets.size > 1:
                corr_matrix = np.corrcoef(aligned, targets)
                snapshot["prediction_target_corr"] = float(corr_matrix[0, 1])

        return snapshot

    def training_matrix(
        self, symbol: str, window: int = 512
    ) -> Optional[Tuple[FloatArray, FloatArray]]:
        with self._lock:
            records = list(self._store.get(symbol, deque()))[-window:]

        rows: List[List[float]] = []
        targets: List[float] = []
        for record in records:
            if record.target is None:
                continue
            rows.append([float(value) for value in record.feature_vector])
            targets.append(float(record.target))

        if not rows or not targets:
            return None

        feature_matrix = cast(FloatArray, np.asarray(rows, dtype=float))
        target_array = cast(FloatArray, np.asarray(targets, dtype=float))
        return feature_matrix, target_array

    def _payload(self, record: KnowledgeRecord) -> Dict[str, Any]:
        payload = asdict(record)
        payload["feature_vector"] = [float(value) for value in record.feature_vector]
        payload["timestamp"] = float(record.timestamp)
        return payload


class DataConnector:
    """Abstract connector expected by the learning system."""

    def fetch_latest(self, symbol: str, n: int = 500) -> Optional[pd.DataFrame]:
        logger.warning(
            "DataConnector.fetch_latest fallback used for %s; " "returning no data",
            symbol,
        )
        return None


class CSVDataConnector(DataConnector):
    """Simple CSV-backed data connector for offline experimentation."""

    def __init__(self, path_map: Dict[str, str]):
        self.path_map = path_map

    def fetch_latest(self, symbol: str, n: int = 500) -> Optional[pd.DataFrame]:
        path = self.path_map.get(symbol)
        if path is None:
            return None
        try:
            df = pd.read_csv(path)
        except Exception as exc:  # pragma: no cover - IO failure
            logger.warning("Failed to load %s: %s", path, exc)
            return None
        return df.tail(n)


class CoinbaseDataConnector(DataConnector):
    """Fetch recent candle data from the Coinbase public market API."""

    def __init__(
        self,
        product_map: Optional[Dict[str, str]] = None,
        *,
        granularity: int = 60,
        timeout: float = 5.0,
    ) -> None:
        self.product_map = {
            symbol.upper(): product for symbol, product in (product_map or {}).items()
        }
        self.granularity = max(1, int(granularity))
        self.timeout = max(0.1, float(timeout))
        self._max_candles = 300
        self._max_batches = 5

    def _product_id(self, symbol: str) -> str:
        default_product = f"{symbol.upper()}-USD"
        return self.product_map.get(symbol.upper(), default_product)

    def _request_payload(
        self,
        symbol: str,
        product_id: str,
        start_time: Optional[datetime],
        end_time: datetime,
    ) -> Optional[Any]:
        def _format(ts: datetime) -> str:
            return ts.isoformat(timespec="seconds").replace("+00:00", "Z")

        query_variants: List[Dict[str, Any]] = []
        if start_time is not None:
            query_variants.append(
                {
                    "granularity": self.granularity,
                    "start": _format(start_time),
                    "end": _format(end_time),
                }
            )
        query_variants.append({"granularity": self.granularity})

        payload: Optional[Any] = None
        last_error: Optional[Exception] = None

        for params in query_variants:
            url = (
                "https://api.exchange.coinbase.com/products/"
                f"{product_id}/candles?{urlencode(params)}"
            )
            try:
                request = Request(url)
                request.add_header(
                    "User-Agent",
                    "ANVEL-ContinuousLearning/1.0",
                )
                with urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except HTTPError as exc:
                details = ""
                try:
                    raw_body = exc.read()
                    details = raw_body.decode("utf-8") if raw_body else ""
                except Exception:
                    details = exc.reason if hasattr(exc, "reason") else ""
                logger.warning(
                    "Coinbase HTTP error for %s (%s): %s",
                    symbol,
                    exc.code,
                    details or exc,
                )
                last_error = exc
                if exc.code == 400 and "start" in params:
                    continue
                return None
            except (URLError, json.JSONDecodeError) as exc:
                logger.warning("Coinbase candle fetch failed for %s: %s", symbol, exc)
                last_error = exc
                continue
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning(
                    "Unexpected Coinbase fetch error for %s: %s", symbol, exc
                )
                return None

        if payload is None and last_error is not None:
            logger.warning(
                "Coinbase candle fetch exhausted retries for %s: %s",
                symbol,
                last_error,
            )
        return payload

    def _payload_to_frame(self, payload: Any) -> Optional[pd.DataFrame]:
        if not isinstance(payload, list) or not payload:
            return None

        rows: List[Dict[str, Any]] = []
        for entry in payload:
            if not isinstance(entry, list) or len(entry) < 6:
                continue
            try:
                epoch, low, high, open_, close, volume = entry[:6]
                timestamp = pd.to_datetime(float(epoch), unit="s", utc=True)
                rows.append(
                    {
                        "timestamp": timestamp,
                        "open": float(open_),
                        "high": float(high),
                        "low": float(low),
                        "close": float(close),
                        "volume": float(volume),
                    }
                )
            except (TypeError, ValueError):
                continue

        if not rows:
            return None

        frame = pd.DataFrame(rows)
        frame = frame.sort_values("timestamp")
        frame["timestamp"] = frame["timestamp"].dt.tz_localize(None)
        frame = frame.set_index("timestamp", drop=True)
        return frame

    def fetch_latest(
        self,
        symbol: str,
        n: int = 500,
    ) -> Optional[pd.DataFrame]:
        product_id = self._product_id(symbol)
        max_points = self._max_candles * self._max_batches
        target = min(max(1, n), max_points)
        frames: List[pd.DataFrame] = []
        remaining = target
        batch_end = datetime.now(timezone.utc)

        for _ in range(self._max_batches):
            if remaining <= 0:
                break
            window = min(remaining, self._max_candles)
            seconds = self.granularity * max(window - 1, 1)
            start_time = batch_end - timedelta(seconds=seconds)
            payload = self._request_payload(
                symbol,
                product_id,
                start_time,
                batch_end,
            )
            if payload is None:
                break

            frame = self._payload_to_frame(payload)
            if frame is None or frame.empty:
                break

            frames.append(frame)
            remaining -= frame.shape[0]
            earliest = frame.index.min()
            if earliest is None:
                break
            earliest_dt = earliest.to_pydatetime().replace(tzinfo=timezone.utc)
            batch_end = earliest_dt - timedelta(seconds=self.granularity)

        if not frames:
            return None

        combined = pd.concat(frames)
        combined = combined.sort_index()
        combined = combined[~combined.index.duplicated(keep="first")]
        return combined.tail(target).copy()


class FeatureAssembler:
    """Builds model features from market data and analytics outputs."""

    def __init__(self, lookback: int = 30):
        self.lookback = lookback

    def assemble(
        self,
        frame: pd.DataFrame,
        report: AnalyticsReport,
    ) -> Optional[Tuple[FloatArray, FloatArray, List[pd.Timestamp]]]:
        if frame.empty or "close" not in frame:
            return None

        enriched = frame.copy()
        enriched["returns"] = enriched["close"].pct_change().fillna(0.0)
        enriched["ma_fast"] = (
            enriched["close"].rolling(window=max(3, self.lookback // 2)).mean()
        )
        enriched["ma_slow"] = enriched["close"].rolling(window=self.lookback).mean()
        enriched["vol"] = enriched["returns"].rolling(window=self.lookback).std(ddof=0)
        volume_series = enriched.get(
            "volume", pd.Series(index=enriched.index, dtype=float)
        )
        enriched["volume_ma"] = (
            volume_series.rolling(window=self.lookback).mean().fillna(0.0)
        )

        enriched = enriched.dropna()
        if enriched.empty:
            return None

        technical = enriched[["ma_fast", "ma_slow", "vol", "volume_ma"]]
        targets = enriched["returns"].shift(-1).dropna()
        technical = technical.iloc[: len(targets)]

        if technical.empty or targets.empty:
            return None

        pattern_scores = self._aggregate_patterns(report.patterns)
        risk_vector = self._risk_vector(report.risk)
        trailing_metrics = report.trailing_metrics

        analytics_features = np.array(
            [
                trailing_metrics.get("returns", 0.0),
                trailing_metrics.get("volatility", 0.0),
                trailing_metrics.get("confidence", 0.0),
                pattern_scores.get("momentum", 0.0),
                pattern_scores.get("mean_reversion", 0.0),
                pattern_scores.get("volatility_breakout", 0.0),
                risk_vector.get("var_95", 0.0),
                risk_vector.get("cvar_95", 0.0),
                risk_vector.get("ulcer_index", 0.0),
            ],
            dtype=float,
        )

        repeated = np.tile(analytics_features, (technical.shape[0], 1))
        technical_array = cast(
            FloatArray,
            np.asarray(
                technical.to_numpy(dtype=float, copy=False),
                dtype=float,
            ),
        )
        matrix = np.hstack([technical_array, repeated]).astype(float, copy=False)
        timestamps = list(technical.index)

        target_array = cast(
            FloatArray,
            np.asarray(
                targets.to_numpy(dtype=float, copy=False),
                dtype=float,
            ),
        )
        return (
            cast(FloatArray, matrix),
            target_array,
            timestamps,
        )

    def _aggregate_patterns(self, patterns: List[PatternInsight]) -> Dict[str, float]:
        scores: Dict[str, float] = {
            "momentum": 0.0,
            "mean_reversion": 0.0,
            "volatility_breakout": 0.0,
        }
        for pattern in patterns:
            scores[pattern.name] = max(scores.get(pattern.name, 0.0), pattern.score)
        return scores

    def _risk_vector(self, risk: Optional[RiskProfile]) -> Dict[str, float]:
        if risk is None:
            return {}
        return {
            "var_95": risk.var_95,
            "cvar_95": risk.cvar_95,
            "ulcer_index": risk.ulcer_index,
        }


class AdaptiveRiskGate:
    """Rejects predictions when confidence or risk is unacceptable."""

    def __init__(
        self,
        confidence_floor: float = 0.25,
        max_var: float = 0.05,
        min_confidence: float = 0.1,
        max_confidence: float = 0.9,
        min_var: float = 0.01,
        max_var_limit: float = 0.2,
    ):
        self.confidence_floor = confidence_floor
        self.max_var = max_var
        self.min_confidence = min_confidence
        self.max_confidence = max_confidence
        self.min_var = min_var
        self.max_var_limit = max_var_limit
        self._symbol_overrides: Dict[str, Dict[str, float]] = {}

    def allow(self, symbol: str, report: AnalyticsReport, prediction: float) -> bool:
        thresholds = self._symbol_overrides.get(symbol, {})
        confidence_floor = thresholds.get("confidence_floor", self.confidence_floor)
        max_var = thresholds.get("max_var", self.max_var)
        snapshot = report.snapshot
        if snapshot is None:
            return False
        if snapshot.confidence < confidence_floor:
            return False
        if report.risk and abs(report.risk.var_95) > max_var:
            return False
        if abs(prediction) > 0.5:
            return False
        return True

    def update(self, symbol: str, metrics: Dict[str, float]) -> None:
        if not metrics:
            self._symbol_overrides.pop(symbol, None)
            return

        avg_conf = metrics.get("avg_confidence")
        rmse = metrics.get("rmse")
        prediction_vol = metrics.get("prediction_volatility")

        confidence_floor = self.confidence_floor
        if avg_conf is not None:
            confidence_floor = float(
                np.clip(
                    1.0 - avg_conf * 0.5,
                    self.min_confidence,
                    self.max_confidence,
                )
            )

        if rmse is not None:
            confidence_floor = float(
                np.clip(
                    confidence_floor + rmse * 0.2,
                    self.min_confidence,
                    self.max_confidence,
                )
            )
        if prediction_vol is not None:
            confidence_floor = float(
                np.clip(
                    confidence_floor + prediction_vol * 0.1,
                    self.min_confidence,
                    self.max_confidence,
                )
            )

        max_var = self.max_var
        if rmse is not None:
            max_var = float(
                np.clip(
                    self.max_var - rmse * 0.3,
                    self.min_var,
                    self.max_var_limit,
                )
            )
        if prediction_vol is not None:
            max_var = float(
                np.clip(
                    max_var - prediction_vol * 0.2,
                    self.min_var,
                    self.max_var_limit,
                )
            )

        self._symbol_overrides[symbol] = {
            "confidence_floor": confidence_floor,
            "max_var": max_var,
        }


class ModelEnvelope:
    """Wraps an online regressor with scaling and diagnostics."""

    def __init__(self, learning_rate: float = 0.01):
        self.scaler = StandardScaler()
        self.model = SGDRegressor(
            max_iter=1,
            tol=None,
            learning_rate="optimal",
            eta0=learning_rate,
            warm_start=True,
        )
        self._fitted = False
        self.loss_history: List[float] = []
        self._loss_history_max = 1000

    def partial_fit(self, features: FloatArray, targets: FloatArray) -> None:
        features_arr = cast(FloatArray, np.asarray(features, dtype=float))
        targets_arr = cast(FloatArray, np.asarray(targets, dtype=float))
        self.scaler.partial_fit(features_arr)
        transformed = cast(
            FloatArray,
            np.asarray(
                self.scaler.transform(features_arr),
                dtype=float,
            ),
        )
        if not self._fitted:
            self._fitted = True
        self.model.partial_fit(transformed, targets_arr)

    def predict(self, features: FloatArray) -> FloatArray:
        if not self._fitted:
            raise NotFittedError("model not yet trained")
        features_arr = cast(FloatArray, np.asarray(features, dtype=float))
        transformed = cast(
            FloatArray,
            np.asarray(self.scaler.transform(features_arr), dtype=float),
        )
        return cast(
            FloatArray,
            np.asarray(self.model.predict(transformed), dtype=float),
        )

    def record_loss(self, predictions: FloatArray, targets: FloatArray) -> None:
        mse = float(np.mean((predictions - targets) ** 2))
        self.loss_history.append(mse)
        if len(self.loss_history) > self._loss_history_max:
            del self.loss_history[: -self._loss_history_max]


class ContinuousLearningSystem:
    """Coordinates ingestion, analytics, and adaptive online learning."""

    def __init__(
        self,
        connector: DataConnector,
        symbols: Iterable[str],
        interval_seconds: int = 60,
        analytics_window: int = 5000,
        knowledge_repo: Optional[KnowledgeRepository] = None,
        knowledge_persist_path: Optional[str] = None,
        knowledge_retention: int = 5000,
        memory: Optional["AnvelMemory"] = None,
        event_bus: Optional["AnvelEventBus"] = None,
        predictive_memory: Optional["ANVELPredictiveMemory"] = None,
        knowledge_listeners: Optional[
            Iterable[Callable[[KnowledgeRecord], None]]
        ] = None,
    ):
        self.connector = connector
        self.symbols = list(symbols)
        self.interval_seconds = interval_seconds
        self.analytics = AnvelAnalyticsCore(window=analytics_window)
        self.features = FeatureAssembler()
        self.risk_gate = AdaptiveRiskGate()
        self.models: Dict[str, ModelEnvelope] = {}
        self.performance: Dict[str, List[PredictionOutcome]] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.event_bus = event_bus
        self.memory = memory
        self.predictive_memory = predictive_memory
        self._knowledge_listeners: List[Callable[[KnowledgeRecord], None]] = []
        if knowledge_listeners:
            self._knowledge_listeners.extend(knowledge_listeners)

        persist_path = (
            Path(knowledge_persist_path).expanduser()
            if knowledge_persist_path
            else None
        )
        self.knowledge = knowledge_repo or KnowledgeRepository(
            persist_path=persist_path,
            retention=knowledge_retention,
            memory=memory,
            event_bus=event_bus,
        )

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Continuous learning engine started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("Continuous learning engine stopped")

    def is_running(self) -> bool:
        """Check if the continuous learning engine is currently running.

        Returns:
            True if the engine thread is alive and running
        """
        return self._thread is not None and self._thread.is_alive()

    def record_trade(self, symbol: str, pnl: float, note: str = "") -> None:
        self.analytics.record_trade_outcome(symbol, pnl, note)

    def latest_performance(self, symbol: str) -> List[PredictionOutcome]:
        return self.performance.get(symbol, [])[-20:]

    def knowledge_summary(
        self, symbol: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        return self.knowledge.latest(symbol, limit)

    def knowledge_metrics(self, symbol: str, window: int = 100) -> Dict[str, float]:
        return self.knowledge.performance_snapshot(symbol, window)

    def training_batch(
        self, symbol: str, window: int = 512
    ) -> Optional[Tuple[FloatArray, FloatArray]]:
        return self.knowledge.training_matrix(symbol, window)

    def register_knowledge_listener(
        self, listener: Callable[[KnowledgeRecord], None]
    ) -> None:
        self._knowledge_listeners.append(listener)

    def system_status(self) -> Dict[str, Dict[str, float]]:
        status: Dict[str, Dict[str, float]] = {}
        for symbol, outcomes in self.performance.items():
            if not outcomes:
                continue
            recent = outcomes[-10:]
            pass_rate = sum(o.risk_gate_passed for o in recent) / len(recent)
            avg_conf = sum(o.confidence for o in recent) / len(recent)
            status[symbol] = {
                "pass_rate": pass_rate,
                "avg_confidence": avg_conf,
                "samples": len(outcomes),
            }
            status[symbol].update(
                self.knowledge.performance_snapshot(symbol, window=50)
            )
        return status

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            start = time.time()
            for symbol in self.symbols:
                try:
                    self._process_symbol(symbol)
                except Exception as exc:  # pragma: no cover - defensive guard
                    logger.exception("Learning loop failure for %s: %s", symbol, exc)
            elapsed = time.time() - start
            sleep_for = max(1.0, self.interval_seconds - elapsed)
            self._stop_event.wait(timeout=sleep_for)

    def _risk_snapshot(self, report: AnalyticsReport) -> Dict[str, float]:
        risk = report.risk
        if risk is None:
            return {}
        return {
            "var_95": risk.var_95,
            "var_99": risk.var_99,
            "cvar_95": risk.cvar_95,
            "cvar_99": risk.cvar_99,
            "max_drawdown": risk.max_drawdown,
            "ulcer_index": risk.ulcer_index,
        }

    def _process_symbol(self, symbol: str) -> None:
        frame = self.connector.fetch_latest(symbol, n=2000)
        if frame is None or frame.empty:
            return

        self.analytics.ingest_market_frame(symbol, frame)
        report = self.analytics.analytics_report(symbol)

        assembled = self.features.assemble(frame, report)
        if assembled is None:
            return
        features, targets, timestamps = assembled

        model = self.models.setdefault(symbol, ModelEnvelope())
        if len(targets) < 2:
            return

        latest_features = features[-1:]
        latest_target_array = targets[-1]

        train_features = features[:-1]
        train_targets = targets[:-1]

        batch = 128
        for offset in range(0, len(train_targets), batch):
            batch_features = train_features[offset : offset + batch]
            batch_targets = train_targets[offset : offset + batch]
            if batch_features.size == 0 or batch_targets.size == 0:
                continue
            model.partial_fit(batch_features, batch_targets)
            preds = model.predict(batch_features)
            model.record_loss(preds, batch_targets)

        prediction = float(model.predict(latest_features)[0])
        latest_target_value = float(np.asarray(latest_target_array, dtype=float).item())

        risk_summary = self._risk_snapshot(report)
        pattern_summary = {
            insight.name: float(insight.score) for insight in report.patterns
        }
        feature_vector = [float(value) for value in latest_features.ravel()]
        trailing_metrics = dict(report.trailing_metrics)

        allowed = self.risk_gate.allow(symbol, report, prediction)
        outcome = PredictionOutcome(
            prediction=prediction,
            target=latest_target_value,
            risk_gate_passed=allowed,
            confidence=report.snapshot.confidence if report.snapshot else 0.0,
            metadata={
                "timestamp": timestamps[-1].timestamp(),
                "sharpe": report.snapshot.sharpe if report.snapshot else 0.0,
            },
        )

        knowledge_record = KnowledgeRecord(
            symbol=symbol,
            timestamp=time.time(),
            prediction=prediction,
            target=outcome.target,
            confidence=outcome.confidence,
            risk_summary=risk_summary,
            pattern_summary=pattern_summary,
            trailing_metrics=trailing_metrics,
            feature_vector=feature_vector,
            metadata=dict(outcome.metadata),
        )
        self.knowledge.append(knowledge_record)

        knowledge_metrics = self.knowledge.performance_snapshot(symbol, window=200)
        if "avg_confidence" not in knowledge_metrics:
            knowledge_metrics["avg_confidence"] = outcome.confidence
        self.risk_gate.update(symbol, knowledge_metrics)

        if self.predictive_memory and outcome.target is not None:
            alignment = "aligned"
            if outcome.target == 0:
                alignment = "flat"
            elif np.sign(outcome.target) != np.sign(prediction):
                alignment = "opposed"
            self.predictive_memory.learn(f"{symbol}:{alignment}")

        for listener in self._knowledge_listeners:
            try:
                listener(knowledge_record)
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.exception("Knowledge listener failure: %s", exc)

        history = self.performance.setdefault(symbol, [])
        history.append(outcome)
        if len(history) > 5000:
            del history[:-2500]

        alerts = report.alerts[-3:]
        for alert in alerts:
            logger.info("[%s] %s", symbol, alert)
        if not allowed:
            logger.info(
                "[%s] prediction gated | pred=%.4f | conf=%.2f",
                symbol,
                prediction,
                outcome.confidence,
            )
        elif self.event_bus:
            timestamp_str = (
                timestamps[-1].isoformat()
                if timestamps and hasattr(timestamps[-1], "isoformat")
                else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            )
            side = "buy" if prediction >= 0 else "sell"
            signal_payload = {
                "symbol": symbol,
                "side": side,
                "quantity": 1,
                "strategy": "continuous_learning",
                "prediction": prediction,
                "confidence": outcome.confidence,
                "risk": risk_summary,
                "timestamp": timestamp_str,
            }
            self.event_bus.publish("trade.signals", signal_payload)


if __name__ == "__main__":  # pragma: no cover - manual smoke hook
    logging.basicConfig(level=logging.INFO)
    symbols = ["BTC"]
    try:
        live_connector = CoinbaseDataConnector(granularity=60)
        probe = live_connector.fetch_latest(symbols[0], n=120)
        if probe is None or probe.empty:
            raise RuntimeError("empty response from Coinbase")
        connector: DataConnector = live_connector
        logger.info(
            "Coinbase connector ready for %s (%d candles)",
            symbols[0],
            len(probe),
        )
    except Exception as exc:  # pragma: no cover - graceful fallback
        logger.warning("Coinbase connector unavailable (%s); using CSV fallback", exc)
        symbols = ["TEST"]
        dummy_path = {"TEST": "./data/test_prices.csv"}
        connector = CSVDataConnector(dummy_path)

    system = ContinuousLearningSystem(
        connector=connector,
        symbols=symbols,
        interval_seconds=5,
    )
    try:
        system.start()
        time.sleep(15)
        print("Status:", system.system_status())
    finally:
        system.stop()
