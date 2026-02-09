#!/usr/bin/env python3
"""
ANVEL Meta Controller AI - Consolidated AI Core
===============================================

This module consolidates the useful, operational parts of VEL's AI modules
into a single, disciplined meta-controller that:

1. Acts as a META-CONTROLLER, not a trader
   - Monitors system health
   - Detects anomalies
   - Suggests parameter changes
   - Enforces kill conditions
   - Does NOT generate trades, size positions, or override risk

2. Implements ACTUAL LEARNING through:
   - Statistical learning from outcomes (SGD-based online learning)
   - Persistent learning state with checkpointing
   - Exponential moving average for weight updates
   - Measurable, quantitative improvement metrics

3. Integrates with predictive healing:
   - Anomaly detection using Isolation Forest + Z-score
   - Failure prediction using historical pattern analysis
   - Proactive alerting and component monitoring

4. Provides codebase awareness:
   - AST-based code analysis
   - Issue detection and classification
   - Health monitoring of code quality

Design Principles:
- NO philosophical "consciousness" code
- NO mood-based trading decisions
- NO autonomous trade execution
- ALL outputs are PROPOSALS that require validation
- ALL learning is quantitative and measurable

This is AIR TRAFFIC CONTROL, not the pilot.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from statistics import mean, stdev
from typing import (
    Any,
    Callable,
    Deque,
    Dict,
    List,
    Optional,
    Tuple,
    TYPE_CHECKING,
)

import numpy as np

try:
    from sklearn.linear_model import SGDRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import IsolationForest

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    SGDRegressor = None  # type: ignore
    StandardScaler = None  # type: ignore
    IsolationForest = None  # type: ignore

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ANVEL.MetaController")


# ═══════════════════════════════════════════════════════════════════════════════
# Enums and Constants
# ═══════════════════════════════════════════════════════════════════════════════


class ProposalType(Enum):
    """Types of proposals the meta-controller can make."""

    PARAMETER_ADJUSTMENT = "parameter_adjustment"
    STRATEGY_WEIGHT_CHANGE = "strategy_weight_change"
    RISK_LIMIT_CHANGE = "risk_limit_change"
    CIRCUIT_BREAKER_TRIGGER = "circuit_breaker_trigger"
    COMPONENT_RESTART = "component_restart"
    ALERT = "alert"
    KILL_SIGNAL = "kill_signal"


class ComponentHealth(Enum):
    """Health states for system components."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    AT_RISK = "at_risk"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class LearningSampleType(Enum):
    """Types of learning samples."""

    TRADE_OUTCOME = "trade_outcome"
    PREDICTION_ACCURACY = "prediction_accuracy"
    SYSTEM_HEALTH = "system_health"
    STRATEGY_PERFORMANCE = "strategy_performance"


# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Proposal:
    """
    A proposal from the meta-controller.

    CRITICAL: Proposals are SUGGESTIONS, not actions. They must be
    validated and approved before execution.
    """

    id: str
    timestamp: float
    proposal_type: ProposalType
    component: str
    description: str
    parameters: Dict[str, Any]
    confidence: float  # 0-1, how confident the controller is
    reason: str
    priority: int  # 1-5, where 1 is highest
    approved: bool = False
    executed: bool = False
    execution_result: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "proposal_type": self.proposal_type.value,
            "component": self.component,
            "description": self.description,
            "parameters": self.parameters,
            "confidence": self.confidence,
            "reason": self.reason,
            "priority": self.priority,
            "approved": self.approved,
            "executed": self.executed,
            "execution_result": self.execution_result,
        }


@dataclass
class LearningSample:
    """A sample for the learning system."""

    timestamp: float
    sample_type: LearningSampleType
    features: Dict[str, float]
    target: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LearningMetrics:
    """Metrics tracking learning performance."""

    total_samples: int = 0
    recent_accuracy: float = 0.0
    cumulative_error: float = 0.0
    learning_rate: float = 0.01
    last_update: float = 0.0
    model_version: int = 0


@dataclass
class CodeIssue:
    """A detected code issue."""

    file_path: str
    line_number: int
    issue_type: str
    description: str
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    timestamp: float


@dataclass
class ComponentStatus:
    """Status of a monitored component."""

    name: str
    health: ComponentHealth
    last_check: float
    metrics: Dict[str, float]
    recent_errors: int
    uptime_seconds: float


# ═══════════════════════════════════════════════════════════════════════════════
# Adaptive Learning Engine
# ═══════════════════════════════════════════════════════════════════════════════


class AdaptiveLearningEngine:
    """
    Actual learning engine that uses statistical methods to improve over time.

    This is NOT symbolic heuristics - it implements real online learning:
    - SGD-based regression for continuous targets
    - Exponential moving average for weight smoothing
    - Persistent state with checkpointing
    - Measurable improvement metrics
    """

    def __init__(
        self,
        persistence_path: Optional[Path] = None,
        learning_rate: float = 0.01,
        ema_alpha: float = 0.1,
        max_samples: int = 10000,
    ):
        """
        Initialize the learning engine.

        Args:
            persistence_path: Path for saving/loading learning state
            learning_rate: Base learning rate for SGD
            ema_alpha: Alpha for exponential moving average smoothing
            max_samples: Maximum samples to retain in memory
        """
        self.persistence_path = persistence_path
        self.learning_rate = learning_rate
        self.ema_alpha = ema_alpha
        self.max_samples = max_samples

        # Sample storage
        self._samples: Deque[LearningSample] = deque(maxlen=max_samples)
        self._prediction_history: Deque[Tuple[float, float]] = deque(maxlen=1000)

        # Learning metrics
        self.metrics = LearningMetrics(learning_rate=learning_rate)

        # Strategy weight learning
        self._strategy_weights: Dict[str, float] = {}
        self._strategy_performance: Dict[str, Deque[float]] = {}

        # ML models (if sklearn available)
        self._model: Optional[Any] = None
        self._scaler: Optional[Any] = None
        self._feature_names: List[str] = []

        if SKLEARN_AVAILABLE:
            self._model = SGDRegressor(
                learning_rate="adaptive",
                eta0=learning_rate,
                random_state=42,
                warm_start=True,
            )
            self._scaler = StandardScaler()

        # Thread safety
        self._lock = threading.RLock()

        # Load persisted state if available
        if persistence_path:
            self._load_state()

        logger.info(
            f"AdaptiveLearningEngine initialized: "
            f"lr={learning_rate}, ema_alpha={ema_alpha}, "
            f"sklearn_available={SKLEARN_AVAILABLE}"
        )

    def record_sample(self, sample: LearningSample) -> None:
        """
        Record a learning sample and update models.

        Args:
            sample: The learning sample to record
        """
        with self._lock:
            self._samples.append(sample)
            self.metrics.total_samples += 1
            self.metrics.last_update = time.time()

            # Update based on sample type
            if sample.sample_type == LearningSampleType.STRATEGY_PERFORMANCE:
                self._update_strategy_weights(sample)
            elif sample.sample_type == LearningSampleType.PREDICTION_ACCURACY:
                self._update_prediction_model(sample)
            elif sample.sample_type == LearningSampleType.TRADE_OUTCOME:
                self._update_from_trade(sample)

    def _update_strategy_weights(self, sample: LearningSample) -> None:
        """Update strategy weights based on performance sample."""
        strategy_name = sample.metadata.get("strategy_name")
        if not strategy_name:
            return

        performance = sample.target

        # Initialize if needed
        if strategy_name not in self._strategy_performance:
            self._strategy_performance[strategy_name] = deque(maxlen=100)
            self._strategy_weights[strategy_name] = 1.0

        self._strategy_performance[strategy_name].append(performance)

        # Calculate new weight using EMA
        if len(self._strategy_performance[strategy_name]) >= 5:
            recent_avg = mean(list(self._strategy_performance[strategy_name])[-20:])
            # Weight adjustment formula:
            # - Start with base weight of 1.0
            # - Multiply performance by 0.5 (dampening factor to prevent extreme swings)
            # - This means +100% performance -> 1.5x weight, -100% -> 0.5x weight
            # - The dampening factor of 0.5 provides stability while still rewarding
            #   consistent outperformance and penalizing underperformance
            PERFORMANCE_DAMPENING = 0.5
            raw_weight = 1.0 + (recent_avg * PERFORMANCE_DAMPENING)
            raw_weight = max(0.1, min(2.0, raw_weight))  # Clamp to [0.1, 2.0]

            # EMA smoothing
            current = self._strategy_weights[strategy_name]
            self._strategy_weights[strategy_name] = (
                self.ema_alpha * raw_weight + (1 - self.ema_alpha) * current
            )

    def _update_prediction_model(self, sample: LearningSample) -> None:
        """Update the prediction model with a new sample."""
        if not SKLEARN_AVAILABLE or self._model is None:
            return

        prediction = sample.features.get("prediction", 0.0)
        actual = sample.target

        # Track prediction error
        error = abs(prediction - actual)
        self._prediction_history.append((prediction, actual))
        self.metrics.cumulative_error += error

        # Update accuracy metric
        if len(self._prediction_history) >= 10:
            recent = list(self._prediction_history)[-100:]
            errors = [abs(p - a) for p, a in recent]
            self.metrics.recent_accuracy = 1.0 - min(1.0, mean(errors))

        # Partial fit if we have enough features
        if sample.features:
            self._partial_fit(sample.features, sample.target)

    def _update_from_trade(self, sample: LearningSample) -> None:
        """Update learning from a trade outcome."""
        pnl = sample.target
        strategy = sample.metadata.get("strategy_name", "unknown")

        # Record as strategy performance
        perf_sample = LearningSample(
            timestamp=sample.timestamp,
            sample_type=LearningSampleType.STRATEGY_PERFORMANCE,
            features=sample.features,
            target=1.0 if pnl > 0 else -1.0,  # Normalize to win/loss
            metadata={"strategy_name": strategy, "pnl": pnl},
        )
        self._update_strategy_weights(perf_sample)

    def _partial_fit(self, features: Dict[str, float], target: float) -> None:
        """Perform partial fit on the SGD model."""
        if not SKLEARN_AVAILABLE or self._model is None:
            return

        # Build feature vector
        if not self._feature_names:
            self._feature_names = sorted(features.keys())

        X = np.array([[features.get(f, 0.0) for f in self._feature_names]])

        try:
            # Partial fit scaler
            self._scaler.partial_fit(X)
            X_scaled = self._scaler.transform(X)

            # Partial fit model
            self._model.partial_fit(X_scaled, [target])
            self.metrics.model_version += 1
        except Exception as e:
            logger.warning(f"Partial fit failed: {e}")

    def get_strategy_weights(self) -> Dict[str, float]:
        """Get current strategy weights."""
        with self._lock:
            return dict(self._strategy_weights)

    def predict(self, features: Dict[str, float]) -> Tuple[float, float]:
        """
        Make a prediction with confidence.

        Args:
            features: Feature dictionary

        Returns:
            Tuple of (prediction, confidence)
        """
        if not SKLEARN_AVAILABLE or self._model is None or not self._feature_names:
            return 0.0, 0.0

        with self._lock:
            try:
                X = np.array([[features.get(f, 0.0) for f in self._feature_names]])
                X_scaled = self._scaler.transform(X)
                prediction = float(self._model.predict(X_scaled)[0])
                confidence = min(1.0, self.metrics.recent_accuracy)
                return prediction, confidence
            except Exception as e:
                logger.warning(f"Prediction failed: {e}")
                return 0.0, 0.0

    def get_learning_metrics(self) -> Dict[str, Any]:
        """Get comprehensive learning metrics."""
        with self._lock:
            return {
                "total_samples": self.metrics.total_samples,
                "recent_accuracy": self.metrics.recent_accuracy,
                "cumulative_error": self.metrics.cumulative_error,
                "learning_rate": self.metrics.learning_rate,
                "last_update": self.metrics.last_update,
                "model_version": self.metrics.model_version,
                "strategy_weights": dict(self._strategy_weights),
                "sklearn_available": SKLEARN_AVAILABLE,
            }

    def save_state(self) -> bool:
        """Save learning state to disk."""
        if not self.persistence_path:
            return False

        with self._lock:
            try:
                state = {
                    "metrics": asdict(self.metrics),
                    "strategy_weights": dict(self._strategy_weights),
                    "feature_names": self._feature_names,
                    "samples": [
                        {
                            "timestamp": s.timestamp,
                            "sample_type": s.sample_type.value,
                            "features": s.features,
                            "target": s.target,
                            "metadata": s.metadata,
                        }
                        for s in list(self._samples)[-1000:]  # Save last 1000
                    ],
                }

                self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.persistence_path, "w") as f:
                    json.dump(state, f, indent=2)

                logger.info(f"Learning state saved to {self.persistence_path}")
                return True
            except Exception as e:
                logger.error(f"Failed to save learning state: {e}")
                return False

    def _load_state(self) -> bool:
        """Load learning state from disk."""
        if not self.persistence_path or not self.persistence_path.exists():
            return False

        try:
            with open(self.persistence_path, "r") as f:
                state = json.load(f)

            self._strategy_weights = state.get("strategy_weights", {})
            self._feature_names = state.get("feature_names", [])

            metrics_dict = state.get("metrics", {})
            self.metrics = LearningMetrics(
                total_samples=metrics_dict.get("total_samples", 0),
                recent_accuracy=metrics_dict.get("recent_accuracy", 0.0),
                cumulative_error=metrics_dict.get("cumulative_error", 0.0),
                learning_rate=metrics_dict.get("learning_rate", self.learning_rate),
                last_update=metrics_dict.get("last_update", 0.0),
                model_version=metrics_dict.get("model_version", 0),
            )

            logger.info(
                f"Learning state loaded from {self.persistence_path}: "
                f"{self.metrics.total_samples} samples"
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to load learning state: {e}")
            return False


# ═══════════════════════════════════════════════════════════════════════════════
# Anomaly Detection Engine
# ═══════════════════════════════════════════════════════════════════════════════


class SystemAnomalyDetector:
    """
    Anomaly detection for system metrics using statistical methods.

    Combines:
    - Isolation Forest for multivariate anomalies (if sklearn available)
    - Z-score for univariate anomalies
    - Trend analysis for gradual degradation
    """

    def __init__(
        self,
        contamination: float = 0.1,
        zscore_threshold: float = 3.0,
        window_size: int = 100,
    ):
        """
        Initialize anomaly detector.

        Args:
            contamination: Expected fraction of anomalies for Isolation Forest
            zscore_threshold: Z-score threshold for outlier detection
            window_size: Rolling window size for statistics
        """
        self.contamination = contamination
        self.zscore_threshold = zscore_threshold
        self.window_size = window_size

        # Metric history per component
        self._history: Dict[str, Deque[Dict[str, float]]] = {}

        # Isolation Forest (if available)
        self._isolation_forest: Optional[Any] = None
        self._if_scaler: Optional[Any] = None
        self._if_trained = False

        if SKLEARN_AVAILABLE:
            self._isolation_forest = IsolationForest(
                contamination=contamination,
                random_state=42,
                n_estimators=100,
            )
            self._if_scaler = StandardScaler()

        self._lock = threading.RLock()

        logger.info(
            f"SystemAnomalyDetector initialized: "
            f"contamination={contamination}, zscore_threshold={zscore_threshold}"
        )

    def record_metrics(self, component: str, metrics: Dict[str, float]) -> None:
        """Record metrics for a component."""
        with self._lock:
            if component not in self._history:
                self._history[component] = deque(maxlen=self.window_size)
            self._history[component].append(metrics)

    def detect(
        self, component: str, metrics: Dict[str, float]
    ) -> Tuple[bool, float, List[str]]:
        """
        Detect anomalies in the given metrics.

        Args:
            component: Component name
            metrics: Current metrics

        Returns:
            Tuple of (is_anomaly, anomaly_score, contributing_factors)
        """
        with self._lock:
            self.record_metrics(component, metrics)

            factors: List[str] = []
            scores: List[float] = []

            history = list(self._history.get(component, []))

            # Z-score detection
            if len(history) >= 10:
                zscore_result = self._zscore_detect(metrics, history)
                if zscore_result[0]:
                    factors.extend(zscore_result[2])
                    scores.append(zscore_result[1])

            # Trend detection
            if len(history) >= 20:
                trend_result = self._trend_detect(history)
                if trend_result[0]:
                    factors.extend(trend_result[2])
                    scores.append(trend_result[1])

            # Isolation Forest detection
            if (
                SKLEARN_AVAILABLE
                and self._isolation_forest is not None
                and self._if_trained
            ):
                if_result = self._isolation_forest_detect(metrics)
                if if_result[0]:
                    factors.append("multivariate_anomaly")
                    scores.append(if_result[1])

            # Aggregate
            if scores:
                anomaly_score = float(np.mean(scores))
            else:
                anomaly_score = 0.0

            is_anomaly = anomaly_score > 0.5 or len(factors) >= 2

            return is_anomaly, anomaly_score, factors

    def _zscore_detect(
        self, metrics: Dict[str, float], history: List[Dict[str, float]]
    ) -> Tuple[bool, float, List[str]]:
        """Detect anomalies using Z-score."""
        factors: List[str] = []
        max_zscore = 0.0

        for key, value in metrics.items():
            historical_values = [h.get(key, value) for h in history if key in h]
            if len(historical_values) < 5:
                continue

            hist_mean = mean(historical_values)
            hist_std = stdev(historical_values) if len(historical_values) > 1 else 1.0
            if hist_std == 0:
                hist_std = 1.0

            zscore = abs(value - hist_mean) / hist_std
            if zscore > self.zscore_threshold:
                factors.append(f"{key}_zscore_{zscore:.2f}")
                max_zscore = max(max_zscore, zscore)

        score = min(1.0, max_zscore / 5.0) if max_zscore > 0 else 0.0
        return len(factors) > 0, score, factors

    def _trend_detect(
        self, history: List[Dict[str, float]]
    ) -> Tuple[bool, float, List[str]]:
        """Detect gradual degradation trends."""
        factors: List[str] = []
        max_trend = 0.0

        # Check for trends in critical metrics
        # Trend threshold of 0.01 = 1% increase per observation
        # This is sensitive enough to catch gradual degradation but not too sensitive
        # to trigger on normal variance
        TREND_THRESHOLD = 0.01
        critical_metrics = ["error_rate", "latency_p99", "memory_usage", "cpu_usage"]

        for metric in critical_metrics:
            values = [h.get(metric) for h in history if metric in h]
            if len(values) < 10:
                continue

            # Simple linear regression slope
            x = np.arange(len(values))
            y = np.array(values)
            try:
                slope = np.polyfit(x, y, 1)[0]
                if slope > TREND_THRESHOLD:  # Rising trend
                    factors.append(f"rising_{metric}_trend_{slope:.4f}")
                    max_trend = max(max_trend, slope)
            except Exception:
                continue

        score = min(1.0, max_trend * 10)
        return len(factors) > 0, score, factors

    def _isolation_forest_detect(
        self, metrics: Dict[str, float]
    ) -> Tuple[bool, float, List[str]]:
        """Detect anomalies using Isolation Forest."""
        if not self._if_trained:
            return False, 0.0, []

        try:
            vector = np.array([[metrics.get(k, 0.0) for k in sorted(metrics.keys())]])
            scaled = self._if_scaler.transform(vector)
            score = -self._isolation_forest.score_samples(scaled)[0]
            is_anomaly = score > 0.5
            return is_anomaly, float(score), []
        except Exception:
            return False, 0.0, []

    def train(self, data: List[Dict[str, float]]) -> None:
        """Train the Isolation Forest on historical data."""
        if not SKLEARN_AVAILABLE or len(data) < 50:
            return

        try:
            # Build matrix
            all_keys = sorted(set().union(*(d.keys() for d in data)))
            matrix = np.array([[d.get(k, 0.0) for k in all_keys] for d in data])

            self._if_scaler.fit(matrix)
            scaled = self._if_scaler.transform(matrix)
            self._isolation_forest.fit(scaled)
            self._if_trained = True

            logger.info(f"Isolation Forest trained on {len(data)} samples")
        except Exception as e:
            logger.warning(f"Failed to train Isolation Forest: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# Codebase Awareness Engine
# ═══════════════════════════════════════════════════════════════════════════════


class CodebaseAwarenessEngine:
    """
    Engine for understanding and monitoring the VEL codebase.

    Uses AST analysis to:
    - Detect code issues (empty functions, TODOs, etc.)
    - Track code health over time
    - Identify potential problems before they manifest
    """

    def __init__(self, root_path: Optional[Path] = None):
        """
        Initialize codebase awareness.

        Args:
            root_path: Root path of the codebase to analyze
        """
        self.root_path = root_path or Path(__file__).parent
        self._issues: List[CodeIssue] = []
        self._file_hashes: Dict[str, str] = {}
        self._lock = threading.RLock()

        logger.info(f"CodebaseAwarenessEngine initialized: root={self.root_path}")

    def scan_codebase(
        self, patterns: Optional[List[str]] = None
    ) -> List[CodeIssue]:
        """
        Scan the codebase for issues.

        Args:
            patterns: Glob patterns for files to scan (default: *.py)

        Returns:
            List of detected issues
        """
        if patterns is None:
            patterns = ["*.py"]

        issues: List[CodeIssue] = []

        with self._lock:
            for pattern in patterns:
                for file_path in self.root_path.glob(pattern):
                    if file_path.is_file():
                        file_issues = self._analyze_file(file_path)
                        issues.extend(file_issues)

            self._issues = issues
            return issues

    def _analyze_file(self, file_path: Path) -> List[CodeIssue]:
        """Analyze a single Python file."""
        issues: List[CodeIssue] = []
        now = time.time()

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")

            # Check file hash for changes using SHA256 (stronger than MD5)
            file_hash = hashlib.sha256(content.encode()).hexdigest()
            self._file_hashes[str(file_path)] = file_hash

            # Try to parse AST
            try:
                tree = ast.parse(content, filename=str(file_path))
            except SyntaxError as e:
                issues.append(
                    CodeIssue(
                        file_path=str(file_path),
                        line_number=e.lineno or 0,
                        issue_type="SYNTAX_ERROR",
                        description=f"Syntax error: {e.msg}",
                        severity="CRITICAL",
                        timestamp=now,
                    )
                )
                return issues

            # Walk AST and check for issues
            for node in ast.walk(tree):
                # Empty functions (excluding private and abstract)
                if isinstance(node, ast.FunctionDef):
                    if (
                        len(node.body) == 1
                        and isinstance(node.body[0], ast.Pass)
                        and not node.name.startswith("_")
                    ):
                        issues.append(
                            CodeIssue(
                                file_path=str(file_path),
                                line_number=node.lineno,
                                issue_type="EMPTY_FUNCTION",
                                description=f"Function '{node.name}' is empty",
                                severity="HIGH",
                                timestamp=now,
                            )
                        )

                # NotImplementedError
                if isinstance(node, ast.Raise):
                    if isinstance(node.exc, ast.Call):
                        if isinstance(node.exc.func, ast.Name):
                            if node.exc.func.id == "NotImplementedError":
                                issues.append(
                                    CodeIssue(
                                        file_path=str(file_path),
                                        line_number=node.lineno,
                                        issue_type="NOT_IMPLEMENTED",
                                        description="NotImplementedError found",
                                        severity="CRITICAL",
                                        timestamp=now,
                                    )
                                )

                # Bare except
                if isinstance(node, ast.ExceptHandler):
                    if node.type is None:
                        issues.append(
                            CodeIssue(
                                file_path=str(file_path),
                                line_number=node.lineno,
                                issue_type="BARE_EXCEPT",
                                description="Bare except clause",
                                severity="MEDIUM",
                                timestamp=now,
                            )
                        )

            # Check for TODO/FIXME comments
            for i, line in enumerate(lines, 1):
                line_upper = line.upper()
                if any(m in line_upper for m in ["TODO", "FIXME", "XXX", "HACK"]):
                    issues.append(
                        CodeIssue(
                            file_path=str(file_path),
                            line_number=i,
                            issue_type="TODO_COMMENT",
                            description=f"Placeholder comment: {line.strip()[:100]}",
                            severity="LOW",
                            timestamp=now,
                        )
                    )

        except Exception as e:
            logger.warning(f"Error analyzing {file_path}: {e}")

        return issues

    def get_health_summary(self) -> Dict[str, Any]:
        """Get a summary of codebase health."""
        with self._lock:
            issues_by_severity = {
                "CRITICAL": 0,
                "HIGH": 0,
                "MEDIUM": 0,
                "LOW": 0,
            }
            issues_by_type: Dict[str, int] = {}

            for issue in self._issues:
                issues_by_severity[issue.severity] = (
                    issues_by_severity.get(issue.severity, 0) + 1
                )
                issues_by_type[issue.issue_type] = (
                    issues_by_type.get(issue.issue_type, 0) + 1
                )

            # Calculate health score (0-100)
            # CRITICAL = -20, HIGH = -10, MEDIUM = -5, LOW = -1
            penalties = (
                issues_by_severity["CRITICAL"] * 20
                + issues_by_severity["HIGH"] * 10
                + issues_by_severity["MEDIUM"] * 5
                + issues_by_severity["LOW"] * 1
            )
            health_score = max(0, 100 - penalties)

            return {
                "health_score": health_score,
                "total_issues": len(self._issues),
                "issues_by_severity": issues_by_severity,
                "issues_by_type": issues_by_type,
                "files_scanned": len(self._file_hashes),
            }

    def get_critical_issues(self) -> List[CodeIssue]:
        """Get only critical and high severity issues."""
        with self._lock:
            return [
                i for i in self._issues if i.severity in ("CRITICAL", "HIGH")
            ]


# ═══════════════════════════════════════════════════════════════════════════════
# Meta Controller Core
# ═══════════════════════════════════════════════════════════════════════════════


class ANVELMetaController:
    """
    The consolidated Meta Controller AI for VEL.

    This is the central intelligence layer that:
    - Monitors system health
    - Detects anomalies and predicts failures
    - Learns from outcomes
    - Generates PROPOSALS (not actions)
    - Maintains codebase awareness

    CRITICAL DESIGN PRINCIPLE:
    This controller does NOT execute trades or make capital decisions.
    It provides recommendations that must be validated by rule-based gates.
    """

    def __init__(
        self,
        persistence_path: Optional[Path] = None,
        enable_learning: bool = True,
        enable_anomaly_detection: bool = True,
        enable_codebase_awareness: bool = True,
        proposal_retention_hours: int = 24,
    ):
        """
        Initialize the Meta Controller.

        Args:
            persistence_path: Base path for persistence
            enable_learning: Whether to enable the learning engine
            enable_anomaly_detection: Whether to enable anomaly detection
            enable_codebase_awareness: Whether to enable codebase scanning
            proposal_retention_hours: How long to retain proposals
        """
        self.persistence_path = persistence_path
        self.proposal_retention_hours = proposal_retention_hours

        # Initialize subsystems
        self._learning_engine: Optional[AdaptiveLearningEngine] = None
        self._anomaly_detector: Optional[SystemAnomalyDetector] = None
        self._codebase_engine: Optional[CodebaseAwarenessEngine] = None

        if enable_learning:
            learning_path = (
                persistence_path / "learning_state.json" if persistence_path else None
            )
            self._learning_engine = AdaptiveLearningEngine(
                persistence_path=learning_path
            )

        if enable_anomaly_detection:
            self._anomaly_detector = SystemAnomalyDetector()

        if enable_codebase_awareness:
            self._codebase_engine = CodebaseAwarenessEngine()

        # Proposals
        self._proposals: Deque[Proposal] = deque(maxlen=10000)
        self._proposal_counter = 0

        # Component tracking
        self._components: Dict[str, ComponentStatus] = {}
        self._component_start_times: Dict[str, float] = {}

        # Thread safety
        self._lock = threading.RLock()

        # Background monitoring
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None

        logger.info(
            f"ANVELMetaController initialized: "
            f"learning={enable_learning}, "
            f"anomaly={enable_anomaly_detection}, "
            f"codebase={enable_codebase_awareness}"
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Proposal Generation
    # ═══════════════════════════════════════════════════════════════════════════

    def _create_proposal(
        self,
        proposal_type: ProposalType,
        component: str,
        description: str,
        parameters: Dict[str, Any],
        confidence: float,
        reason: str,
        priority: int = 3,
    ) -> Proposal:
        """Create a new proposal."""
        with self._lock:
            self._proposal_counter += 1
            proposal_id = f"prop_{int(time.time())}_{self._proposal_counter}"

        proposal = Proposal(
            id=proposal_id,
            timestamp=time.time(),
            proposal_type=proposal_type,
            component=component,
            description=description,
            parameters=parameters,
            confidence=confidence,
            reason=reason,
            priority=priority,
        )

        with self._lock:
            self._proposals.append(proposal)
            self._cleanup_old_proposals()

        logger.info(
            f"Proposal created: {proposal_id} - {proposal_type.value} "
            f"for {component} (confidence={confidence:.2f})"
        )

        return proposal

    def _cleanup_old_proposals(self) -> None:
        """Remove old proposals."""
        cutoff = time.time() - (self.proposal_retention_hours * 3600)
        while self._proposals and self._proposals[0].timestamp < cutoff:
            self._proposals.popleft()

    def get_pending_proposals(self) -> List[Proposal]:
        """Get proposals that haven't been approved or executed."""
        with self._lock:
            return [
                p for p in self._proposals if not p.approved and not p.executed
            ]

    def approve_proposal(self, proposal_id: str) -> bool:
        """Approve a proposal for execution."""
        with self._lock:
            for proposal in self._proposals:
                if proposal.id == proposal_id:
                    proposal.approved = True
                    logger.info(f"Proposal approved: {proposal_id}")
                    return True
            return False

    def mark_executed(
        self, proposal_id: str, result: str = "success"
    ) -> bool:
        """Mark a proposal as executed."""
        with self._lock:
            for proposal in self._proposals:
                if proposal.id == proposal_id:
                    proposal.executed = True
                    proposal.execution_result = result
                    return True
            return False

    # ═══════════════════════════════════════════════════════════════════════════
    # Component Monitoring
    # ═══════════════════════════════════════════════════════════════════════════

    def register_component(
        self,
        name: str,
        initial_health: ComponentHealth = ComponentHealth.HEALTHY,
    ) -> None:
        """Register a component for monitoring."""
        with self._lock:
            now = time.time()
            self._components[name] = ComponentStatus(
                name=name,
                health=initial_health,
                last_check=now,
                metrics={},
                recent_errors=0,
                uptime_seconds=0,
            )
            self._component_start_times[name] = now
            logger.info(f"Component registered: {name}")

    def report_component_metrics(
        self,
        component: str,
        metrics: Dict[str, float],
        error_count: int = 0,
    ) -> Optional[Proposal]:
        """
        Report metrics for a component and check for anomalies.

        Args:
            component: Component name
            metrics: Current metrics
            error_count: Number of recent errors

        Returns:
            A proposal if anomalies or issues are detected
        """
        with self._lock:
            if component not in self._components:
                self.register_component(component)

            now = time.time()
            start_time = self._component_start_times.get(component, now)
            uptime = now - start_time

            self._components[component].last_check = now
            self._components[component].metrics = metrics
            self._components[component].recent_errors = error_count
            self._components[component].uptime_seconds = uptime

        # Run anomaly detection
        proposal = None
        if self._anomaly_detector:
            is_anomaly, score, factors = self._anomaly_detector.detect(
                component, metrics
            )

            if is_anomaly:
                # Update health status
                if score > 0.8:
                    health = ComponentHealth.CRITICAL
                    priority = 1
                elif score > 0.6:
                    health = ComponentHealth.AT_RISK
                    priority = 2
                else:
                    health = ComponentHealth.DEGRADED
                    priority = 3

                with self._lock:
                    self._components[component].health = health

                # Create proposal
                proposal = self._create_proposal(
                    proposal_type=ProposalType.ALERT,
                    component=component,
                    description=f"Anomaly detected: {', '.join(factors[:3])}",
                    parameters={
                        "anomaly_score": score,
                        "factors": factors,
                        "metrics": metrics,
                    },
                    confidence=min(0.9, score),
                    reason=f"Anomaly detection triggered with score {score:.2f}",
                    priority=priority,
                )

        return proposal

    def get_component_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all monitored components."""
        with self._lock:
            return {
                name: {
                    "health": status.health.value,
                    "last_check": status.last_check,
                    "metrics": status.metrics,
                    "recent_errors": status.recent_errors,
                    "uptime_seconds": status.uptime_seconds,
                }
                for name, status in self._components.items()
            }

    # ═══════════════════════════════════════════════════════════════════════════
    # Learning Interface
    # ═══════════════════════════════════════════════════════════════════════════

    def record_trade_outcome(
        self,
        strategy_name: str,
        pnl: float,
        features: Dict[str, float],
    ) -> None:
        """
        Record a trade outcome for learning.

        Args:
            strategy_name: Name of the strategy
            pnl: Profit/loss of the trade
            features: Features at trade time
        """
        if not self._learning_engine:
            return

        sample = LearningSample(
            timestamp=time.time(),
            sample_type=LearningSampleType.TRADE_OUTCOME,
            features=features,
            target=pnl,
            metadata={"strategy_name": strategy_name},
        )
        self._learning_engine.record_sample(sample)

    def record_prediction(
        self,
        prediction: float,
        actual: float,
        features: Dict[str, float],
    ) -> None:
        """
        Record a prediction for accuracy tracking.

        Args:
            prediction: The predicted value
            actual: The actual value
            features: Features used for prediction
        """
        if not self._learning_engine:
            return

        sample = LearningSample(
            timestamp=time.time(),
            sample_type=LearningSampleType.PREDICTION_ACCURACY,
            features={**features, "prediction": prediction},
            target=actual,
            metadata={},
        )
        self._learning_engine.record_sample(sample)

    def get_strategy_weight_proposal(self) -> Optional[Proposal]:
        """
        Generate a proposal for strategy weight adjustments.

        Returns:
            A proposal with recommended weight changes, or None
        """
        if not self._learning_engine:
            return None

        weights = self._learning_engine.get_strategy_weights()
        if not weights:
            return None

        # Only propose if we have enough data
        metrics = self._learning_engine.get_learning_metrics()
        if metrics["total_samples"] < 50:
            return None

        return self._create_proposal(
            proposal_type=ProposalType.STRATEGY_WEIGHT_CHANGE,
            component="strategy_runner",
            description="Strategy weight adjustment based on learning",
            parameters={"weights": weights},
            confidence=min(0.8, metrics["recent_accuracy"]),
            reason=f"Learning-based adjustment after {metrics['total_samples']} samples",
            priority=4,
        )

    def get_learning_metrics(self) -> Dict[str, Any]:
        """Get comprehensive learning metrics."""
        if not self._learning_engine:
            return {"enabled": False}

        metrics = self._learning_engine.get_learning_metrics()
        metrics["enabled"] = True
        return metrics

    # ═══════════════════════════════════════════════════════════════════════════
    # Codebase Awareness Interface
    # ═══════════════════════════════════════════════════════════════════════════

    def scan_codebase(self) -> Dict[str, Any]:
        """
        Scan the codebase for issues.

        Returns:
            Health summary of the codebase
        """
        if not self._codebase_engine:
            return {"enabled": False}

        self._codebase_engine.scan_codebase()
        return self._codebase_engine.get_health_summary()

    def get_code_issues(
        self, severity_filter: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get detected code issues.

        Args:
            severity_filter: Only return issues with these severities

        Returns:
            List of issue dictionaries
        """
        if not self._codebase_engine:
            return []

        with self._codebase_engine._lock:
            issues = self._codebase_engine._issues
            if severity_filter:
                issues = [i for i in issues if i.severity in severity_filter]

            return [
                {
                    "file_path": i.file_path,
                    "line_number": i.line_number,
                    "issue_type": i.issue_type,
                    "description": i.description,
                    "severity": i.severity,
                    "timestamp": i.timestamp,
                }
                for i in issues
            ]

    # ═══════════════════════════════════════════════════════════════════════════
    # Kill Switch and Circuit Breaker
    # ═══════════════════════════════════════════════════════════════════════════

    def evaluate_kill_conditions(
        self,
        current_drawdown: float,
        max_drawdown: float = 0.1,
        error_rate: float = 0.0,
        max_error_rate: float = 0.05,
    ) -> Optional[Proposal]:
        """
        Evaluate if kill conditions are met.

        This is a SAFETY function. It generates KILL_SIGNAL proposals
        when critical conditions are detected.

        Args:
            current_drawdown: Current portfolio drawdown (0-1)
            max_drawdown: Maximum allowed drawdown
            error_rate: Current error rate (0-1)
            max_error_rate: Maximum allowed error rate

        Returns:
            A kill proposal if conditions are met
        """
        reasons = []

        if current_drawdown >= max_drawdown:
            reasons.append(
                f"Drawdown {current_drawdown:.2%} >= max {max_drawdown:.2%}"
            )

        if error_rate >= max_error_rate:
            reasons.append(
                f"Error rate {error_rate:.2%} >= max {max_error_rate:.2%}"
            )

        # Check for critical component failures
        with self._lock:
            critical_components = [
                name
                for name, status in self._components.items()
                if status.health == ComponentHealth.CRITICAL
            ]

        if critical_components:
            reasons.append(f"Critical components: {', '.join(critical_components)}")

        if reasons:
            return self._create_proposal(
                proposal_type=ProposalType.KILL_SIGNAL,
                component="system",
                description="Kill signal: " + "; ".join(reasons),
                parameters={
                    "drawdown": current_drawdown,
                    "error_rate": error_rate,
                    "critical_components": critical_components,
                },
                confidence=0.95,
                reason=" | ".join(reasons),
                priority=1,  # Highest priority
            )

        return None

    def generate_circuit_breaker_proposal(
        self,
        component: str,
        reason: str,
        duration_seconds: int = 300,
    ) -> Proposal:
        """
        Generate a circuit breaker proposal.

        Args:
            component: Component to circuit break
            reason: Reason for the circuit break
            duration_seconds: How long to maintain the break

        Returns:
            A circuit breaker proposal
        """
        return self._create_proposal(
            proposal_type=ProposalType.CIRCUIT_BREAKER_TRIGGER,
            component=component,
            description=f"Circuit breaker: {reason}",
            parameters={"duration_seconds": duration_seconds},
            confidence=0.8,
            reason=reason,
            priority=2,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Lifecycle Management
    # ═══════════════════════════════════════════════════════════════════════════

    def start_monitoring(self, interval_seconds: int = 10) -> None:
        """Start background monitoring."""
        if self._running:
            return

        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(interval_seconds,),
            daemon=True,
        )
        self._monitor_thread.start()
        logger.info("Meta Controller monitoring started")

    def stop_monitoring(self) -> None:
        """Stop background monitoring."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("Meta Controller monitoring stopped")

    def _monitoring_loop(self, interval: int) -> None:
        """Background monitoring loop."""
        while self._running:
            try:
                # Check all registered components
                with self._lock:
                    components = list(self._components.keys())

                for component in components:
                    status = self._components.get(component)
                    if status and status.metrics:
                        self.report_component_metrics(
                            component,
                            status.metrics,
                            status.recent_errors,
                        )

                time.sleep(interval)

            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                time.sleep(interval)

    def save_state(self) -> bool:
        """Save controller state to disk."""
        if self._learning_engine:
            return self._learning_engine.save_state()
        return False

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive controller status."""
        return {
            "running": self._running,
            "components": self.get_component_status(),
            "learning": self.get_learning_metrics(),
            "pending_proposals": len(self.get_pending_proposals()),
            "total_proposals": len(self._proposals),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Factory Functions
# ═══════════════════════════════════════════════════════════════════════════════


def create_meta_controller(
    persistence_dir: Optional[str] = None,
    **kwargs,
) -> ANVELMetaController:
    """
    Factory function to create a meta controller.

    Args:
        persistence_dir: Directory for persistence (uses env var if None)
        **kwargs: Additional arguments for ANVELMetaController

    Returns:
        Configured ANVELMetaController instance
    """
    if persistence_dir is None:
        persistence_dir = os.getenv(
            "ANVEL_META_CONTROLLER_DIR", "/tmp/anvel/meta_controller"
        )

    persistence_path = Path(persistence_dir)
    persistence_path.mkdir(parents=True, exist_ok=True)

    return ANVELMetaController(persistence_path=persistence_path, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════════
# Module Exports
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Main controller
    "ANVELMetaController",
    "create_meta_controller",
    # Subsystems
    "AdaptiveLearningEngine",
    "SystemAnomalyDetector",
    "CodebaseAwarenessEngine",
    # Data classes
    "Proposal",
    "LearningSample",
    "LearningMetrics",
    "CodeIssue",
    "ComponentStatus",
    # Enums
    "ProposalType",
    "ComponentHealth",
    "LearningSampleType",
]
