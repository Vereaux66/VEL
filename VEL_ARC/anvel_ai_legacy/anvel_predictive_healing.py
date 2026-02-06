#!/usr/bin/env python3
"""
ANVEL Predictive Self-Healing System - Phase 3 Enhancement
===========================================================

Implements proactive failure detection and autonomous healing capabilities:
- Predictive Failure Detection using anomaly detection and metric forecasting
- Proactive Health Monitoring with early warning system
- Automated Remediation with intelligent action selection
- Chaos Engineering simulation for resilience testing

Reference papers:
- "Predicting Failures in Production Systems" (Microsoft Research, 2020)
- "Learning to Heal: Self-healing Systems in Autonomous Computing" (IBM, 2019)
- "Chaos Engineering: System Resiliency in Practice" (Netflix, 2020)
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

try:
    import torch
    import torch.nn as nn
    from sklearn.ensemble import IsolationForest, RandomForestClassifier
    from sklearn.preprocessing import StandardScaler

    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

    # Create stub classes that raise clear errors when ML libraries are unavailable
    class _MLStub:
        """
        Stub object used when PyTorch or scikit-learn is not available.

        Any attribute access on this object will raise a clear error indicating that
        ML packages are required for predictive healing.
        """

        def __getattr__(self, name: str) -> Any:
            raise NotImplementedError(
                f"PyTorch and scikit-learn are required for predictive healing. "
                f"Cannot access '{name}'. Please install: pip install torch scikit-learn"
            )

        def __call__(self, *args, **kwargs):
            raise NotImplementedError(
                "PyTorch and scikit-learn are required for predictive healing. "
                "Please install: pip install torch scikit-learn"
            )

    class _DummyModule:
        """Dummy base class for when torch.nn.Module is unavailable."""

        pass

    class _NoOpContext:
        """No-op context manager for when torch is unavailable."""

        def __enter__(self):
            return None

        def __exit__(self, *args):
            return None

    def _noop_no_grad():
        """Stub implementation of torch.no_grad that behaves as a no-op context manager."""
        return _NoOpContext()

    # Create stubs for ML objects
    nn = type(
        "nn",
        (),
        {
            "Module": _DummyModule,
            "LSTM": type("LSTM", (), {}),
            "Linear": type("Linear", (), {}),
        },
    )()
    torch = type(
        "torch",
        (),
        {
            "Tensor": type("Tensor", (), {}),
            "device": lambda x: None,
            "cuda": type("cuda", (), {"is_available": lambda: False})(),
            "no_grad": _noop_no_grad,
        },
    )()


# Setup logging
logging.basicConfig(level=logging.INFO)
_healing_logger = logging.getLogger("ANVEL.PredictiveHealing")


# ═══════════════════════════════════════════════════════════════════════════════
# Enums and Data Classes
# ═══════════════════════════════════════════════════════════════════════════════


class ComponentState(Enum):
    """State of a monitored component."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    AT_RISK = "at_risk"
    CRITICAL = "critical"
    FAILED = "failed"
    RECOVERING = "recovering"


class AlertSeverity(Enum):
    """Severity level for alerts."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RemediationAction(Enum):
    """Types of remediation actions."""

    RESTART_COMPONENT = "restart_component"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    CIRCUIT_BREAK = "circuit_break"
    FAILOVER = "failover"
    RATE_LIMIT = "rate_limit"
    CACHE_CLEAR = "cache_clear"
    CONNECTION_RESET = "connection_reset"
    MEMORY_CLEANUP = "memory_cleanup"
    THREAD_POOL_RESET = "thread_pool_reset"


@dataclass
class MetricSnapshot:
    """A snapshot of system metrics at a point in time."""

    timestamp: datetime
    component: str
    cpu_usage: float
    memory_usage: float
    latency_p99: float
    error_rate: float
    throughput: float
    queue_depth: int
    connection_count: int
    custom_metrics: Dict[str, float] = field(default_factory=dict)

    def to_vector(self) -> np.ndarray:
        """Convert to feature vector for ML models."""
        return np.array(
            [
                self.cpu_usage,
                self.memory_usage,
                self.latency_p99,
                self.error_rate,
                self.throughput,
                self.queue_depth,
                self.connection_count,
            ]
        )


@dataclass
class FailurePrediction:
    """Prediction of potential failure."""

    component: str
    probability: float
    time_to_failure: Optional[timedelta]
    predicted_state: ComponentState
    contributing_factors: List[str]
    confidence: float
    recommended_actions: List[RemediationAction]


@dataclass
class Alert:
    """System alert."""

    id: str
    timestamp: datetime
    component: str
    severity: AlertSeverity
    message: str
    prediction: Optional[FailurePrediction]
    acknowledged: bool = False
    resolved: bool = False


@dataclass
class RemediationResult:
    """Result of a remediation action."""

    action: RemediationAction
    component: str
    success: bool
    duration_ms: float
    error_message: Optional[str] = None
    metrics_before: Optional[MetricSnapshot] = None
    metrics_after: Optional[MetricSnapshot] = None


# ═══════════════════════════════════════════════════════════════════════════════
# Anomaly Detection Engine
# ═══════════════════════════════════════════════════════════════════════════════


class AnomalyDetector:
    """
    Multi-method anomaly detection for system metrics.

    Combines:
    - Isolation Forest for multivariate anomalies
    - Statistical methods (Z-score, IQR) for univariate anomalies
    - Temporal patterns for trend-based anomalies
    """

    def __init__(
        self,
        contamination: float = 0.1,
        window_size: int = 100,
        zscore_threshold: float = 3.0,
    ):
        """
        Initialize anomaly detector.

        Args:
            contamination: Expected fraction of anomalies
            window_size: Rolling window size for statistics
            zscore_threshold: Z-score threshold for outliers
        """
        self.contamination = contamination
        self.window_size = window_size
        self.zscore_threshold = zscore_threshold

        if ML_AVAILABLE:
            self.isolation_forest = IsolationForest(
                contamination=contamination,
                random_state=42,
                n_estimators=100,
            )
            self.scaler = StandardScaler()
        else:
            self.isolation_forest = None
            self.scaler = None

        self.history: Dict[str, deque] = {}
        self.trained = False

        _healing_logger.info(
            f"AnomalyDetector initialized: contamination={contamination}, "
            f"window_size={window_size}"
        )

    def add_observation(self, component: str, metrics: MetricSnapshot) -> None:
        """Add observation to history."""
        if component not in self.history:
            self.history[component] = deque(maxlen=self.window_size)
        self.history[component].append(metrics)

    def fit(self, data: np.ndarray) -> None:
        """Fit the anomaly detector on historical data."""
        if not ML_AVAILABLE:
            _healing_logger.warning("ML not available, using statistical methods only")
            return

        self.scaler.fit(data)
        scaled_data = self.scaler.transform(data)
        self.isolation_forest.fit(scaled_data)
        self.trained = True
        _healing_logger.info(f"AnomalyDetector trained on {len(data)} samples")

    def detect(self, metrics: MetricSnapshot) -> Tuple[bool, float, List[str]]:
        """
        Detect if metrics indicate an anomaly.

        Returns:
            is_anomaly: Whether this is an anomaly
            anomaly_score: Score indicating severity (0-1)
            contributing_factors: List of factors contributing to anomaly
        """
        vector = metrics.to_vector()
        contributing_factors = []
        scores = []

        # Isolation Forest detection
        if ML_AVAILABLE and self.trained:
            scaled = self.scaler.transform(vector.reshape(1, -1))
            if_score = -self.isolation_forest.score_samples(scaled)[0]
            scores.append(if_score)

        # Statistical detection (Z-score)
        component = metrics.component
        if component in self.history and len(self.history[component]) >= 10:
            historical = np.array([m.to_vector() for m in self.history[component]])
            mean = historical.mean(axis=0)
            std = historical.std(axis=0) + 1e-8
            zscores = np.abs((vector - mean) / std)

            # Check each dimension
            feature_names = [
                "cpu_usage",
                "memory_usage",
                "latency_p99",
                "error_rate",
                "throughput",
                "queue_depth",
                "connection_count",
            ]
            for i, (z, name) in enumerate(zip(zscores, feature_names)):
                if z > self.zscore_threshold:
                    contributing_factors.append(f"{name} (z={z:.2f})")

            zscore_score = min(zscores.max() / 5.0, 1.0)
            scores.append(zscore_score)

        # Trend detection
        if component in self.history and len(self.history[component]) >= 20:
            recent = list(self.history[component])[-20:]
            recent_vectors = np.array([m.to_vector() for m in recent])

            # Check for increasing trends in error rate
            error_rates = recent_vectors[:, 3]
            if len(error_rates) >= 5:
                trend = np.polyfit(range(len(error_rates)), error_rates, 1)[0]
                if trend > 0.01:
                    contributing_factors.append(
                        f"rising_error_rate (trend={trend:.4f})"
                    )
                    scores.append(min(trend * 10, 1.0))

        # Combine scores
        if scores:
            anomaly_score = np.mean(scores)
        else:
            anomaly_score = 0.0

        is_anomaly = anomaly_score > 0.5 or len(contributing_factors) >= 2

        return is_anomaly, anomaly_score, contributing_factors


# ═══════════════════════════════════════════════════════════════════════════════
# Metric Forecaster
# ═══════════════════════════════════════════════════════════════════════════════


class MetricForecaster:
    """
    LSTM-based metric forecasting for predictive failure detection.

    Predicts future metric values to anticipate failures before they occur.
    """

    class _ForecastLSTM(nn.Module):
        """LSTM for metric forecasting."""

        def __init__(self, input_dim: int, hidden_dim: int, num_layers: int):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=input_dim,
                hidden_size=hidden_dim,
                num_layers=num_layers,
                batch_first=True,
                dropout=0.1 if num_layers > 1 else 0,
            )
            self.fc = nn.Linear(hidden_dim, input_dim)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            lstm_out, _ = self.lstm(x)
            return self.fc(lstm_out[:, -1, :])

    def __init__(
        self,
        input_dim: int = 7,
        hidden_dim: int = 64,
        num_layers: int = 2,
        sequence_length: int = 20,
        forecast_horizon: int = 5,
    ):
        """
        Initialize metric forecaster.

        Args:
            input_dim: Number of metrics to forecast
            hidden_dim: LSTM hidden dimension
            num_layers: Number of LSTM layers
            sequence_length: Input sequence length
            forecast_horizon: Number of steps to forecast
        """
        self.input_dim = input_dim
        self.sequence_length = sequence_length
        self.forecast_horizon = forecast_horizon

        if ML_AVAILABLE:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model = self._ForecastLSTM(input_dim, hidden_dim, num_layers).to(
                self.device
            )
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
            self.scaler = StandardScaler()
        else:
            self.device = None
            self.model = None
            self.optimizer = None
            self.scaler = None

        self.trained = False

        _healing_logger.info(
            f"MetricForecaster initialized: input_dim={input_dim}, "
            f"hidden_dim={hidden_dim}, horizon={forecast_horizon}"
        )

    def train(
        self,
        data: np.ndarray,
        epochs: int = 50,
        batch_size: int = 32,
    ) -> Dict[str, float]:
        """
        Train the forecaster on historical data.

        Args:
            data: Historical metric data (n_samples, n_features)
            epochs: Training epochs
            batch_size: Batch size

        Returns:
            Training history
        """
        if not ML_AVAILABLE:
            _healing_logger.warning("ML not available, forecaster disabled")
            return {"loss": float("nan")}

        self.scaler.fit(data)
        scaled_data = self.scaler.transform(data)

        # Create sequences
        X, y = [], []
        for i in range(len(scaled_data) - self.sequence_length):
            X.append(scaled_data[i : i + self.sequence_length])
            y.append(scaled_data[i + self.sequence_length])

        X = torch.FloatTensor(np.array(X)).to(self.device)
        y = torch.FloatTensor(np.array(y)).to(self.device)

        dataset = torch.utils.data.TensorDataset(X, y)
        dataloader = torch.utils.data.DataLoader(
            dataset, batch_size=batch_size, shuffle=True
        )

        history = {"loss": []}
        self.model.train()

        for epoch in range(epochs):
            epoch_loss = 0
            for batch_x, batch_y in dataloader:
                self.optimizer.zero_grad()
                pred = self.model(batch_x)
                loss = nn.functional.mse_loss(pred, batch_y)
                loss.backward()
                self.optimizer.step()
                epoch_loss += loss.item()

            epoch_loss /= len(dataloader)
            history["loss"].append(epoch_loss)

        self.trained = True
        _healing_logger.info(
            f"MetricForecaster trained: final_loss={history['loss'][-1]:.6f}"
        )
        return history

    def forecast(self, recent_metrics: List[MetricSnapshot]) -> List[np.ndarray]:
        """
        Forecast future metrics.

        Args:
            recent_metrics: Recent metric snapshots (at least sequence_length)

        Returns:
            List of forecasted metric vectors
        """
        if not ML_AVAILABLE or not self.trained:
            return []

        if len(recent_metrics) < self.sequence_length:
            return []

        # Get last sequence_length metrics
        vectors = np.array(
            [m.to_vector() for m in recent_metrics[-self.sequence_length :]]
        )
        scaled = self.scaler.transform(vectors)

        self.model.eval()
        forecasts = []
        current_seq = scaled.copy()

        with torch.no_grad():
            for _ in range(self.forecast_horizon):
                x = torch.FloatTensor(current_seq).unsqueeze(0).to(self.device)
                pred = self.model(x).cpu().numpy()[0]
                forecasts.append(self.scaler.inverse_transform(pred.reshape(1, -1))[0])

                # Roll sequence forward
                current_seq = np.roll(current_seq, -1, axis=0)
                current_seq[-1] = pred

        return forecasts


# ═══════════════════════════════════════════════════════════════════════════════
# Failure Predictor
# ═══════════════════════════════════════════════════════════════════════════════


class FailurePredictor:
    """
    Predicts component failures using historical patterns and ML models.

    Combines:
    - Anomaly detection for current state
    - Metric forecasting for future state
    - Pattern matching from historical failures
    """

    def __init__(
        self,
        failure_threshold: float = 0.7,
        warning_threshold: float = 0.4,
    ):
        """
        Initialize failure predictor.

        Args:
            failure_threshold: Probability threshold for failure prediction
            warning_threshold: Probability threshold for warnings
        """
        self.failure_threshold = failure_threshold
        self.warning_threshold = warning_threshold

        self.anomaly_detector = AnomalyDetector()
        self.forecaster = MetricForecaster()

        if ML_AVAILABLE:
            self.failure_classifier = RandomForestClassifier(
                n_estimators=100,
                random_state=42,
            )
        else:
            self.failure_classifier = None

        self.failure_history: Dict[str, List[MetricSnapshot]] = {}
        self.trained = False

        _healing_logger.info("FailurePredictor initialized")

    def record_failure(
        self, component: str, metrics_before: List[MetricSnapshot]
    ) -> None:
        """Record a failure for learning."""
        if component not in self.failure_history:
            self.failure_history[component] = []
        self.failure_history[component].extend(metrics_before)

    def train(
        self,
        historical_data: Dict[str, List[MetricSnapshot]],
        failure_labels: Dict[str, List[bool]],
    ) -> None:
        """
        Train the failure predictor.

        Args:
            historical_data: Historical metrics by component
            failure_labels: Whether each snapshot led to failure
        """
        # Train anomaly detector
        all_vectors = []
        for metrics_list in historical_data.values():
            all_vectors.extend([m.to_vector() for m in metrics_list])

        if all_vectors:
            self.anomaly_detector.fit(np.array(all_vectors))

        # Train forecaster
        if all_vectors:
            self.forecaster.train(np.array(all_vectors))

        # Train failure classifier
        if ML_AVAILABLE and failure_labels:
            X, y = [], []
            for component, metrics_list in historical_data.items():
                if component in failure_labels:
                    labels = failure_labels[component]
                    for i, (m, label) in enumerate(zip(metrics_list, labels)):
                        X.append(m.to_vector())
                        y.append(int(label))

            if X and sum(y) > 0:  # Need at least some positive labels
                self.failure_classifier.fit(X, y)

        self.trained = True
        _healing_logger.info("FailurePredictor training complete")

    def predict(
        self,
        component: str,
        current_metrics: MetricSnapshot,
        recent_history: List[MetricSnapshot],
    ) -> FailurePrediction:
        """
        Predict failure probability for a component.

        Args:
            component: Component name
            current_metrics: Current metric snapshot
            recent_history: Recent metric history

        Returns:
            Failure prediction with recommendations
        """
        contributing_factors = []
        probabilities = []

        # Anomaly detection
        is_anomaly, anomaly_score, anomaly_factors = self.anomaly_detector.detect(
            current_metrics
        )
        contributing_factors.extend(anomaly_factors)
        if is_anomaly:
            probabilities.append(anomaly_score)

        # Metric forecasting
        forecasts = self.forecaster.forecast(recent_history)
        time_to_failure = None

        for i, forecast in enumerate(forecasts):
            # Check if forecasted metrics exceed thresholds
            if forecast[3] > 0.1:  # error_rate > 10%
                contributing_factors.append(f"forecasted_high_error_rate_t+{i+1}")
                probabilities.append(min(forecast[3] * 5, 1.0))
                if time_to_failure is None:
                    time_to_failure = timedelta(minutes=i + 1)

            if forecast[0] > 0.9:  # cpu_usage > 90%
                contributing_factors.append(f"forecasted_high_cpu_t+{i+1}")
                probabilities.append(forecast[0])

        # Failure classifier (only if trained)
        if ML_AVAILABLE and self.failure_classifier is not None and self.trained:
            try:
                # Check if classifier has been fit
                if hasattr(self.failure_classifier, "estimators_"):
                    proba = self.failure_classifier.predict_proba(
                        current_metrics.to_vector().reshape(1, -1)
                    )[0][1]
                    probabilities.append(proba)
            except Exception:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_PREDICTIVE_HEALING").debug("Exception suppressed in predict")

        # Aggregate probability
        if probabilities:
            failure_probability = np.mean(probabilities)
        else:
            failure_probability = 0.0

        # Determine state
        if failure_probability >= self.failure_threshold:
            predicted_state = ComponentState.CRITICAL
        elif failure_probability >= self.warning_threshold:
            predicted_state = ComponentState.AT_RISK
        elif failure_probability >= 0.2:
            predicted_state = ComponentState.DEGRADED
        else:
            predicted_state = ComponentState.HEALTHY

        # Recommend actions
        recommended_actions = self._recommend_actions(
            current_metrics, contributing_factors, failure_probability
        )

        return FailurePrediction(
            component=component,
            probability=failure_probability,
            time_to_failure=time_to_failure,
            predicted_state=predicted_state,
            contributing_factors=contributing_factors,
            confidence=0.8 if self.trained else 0.5,
            recommended_actions=recommended_actions,
        )

    def _recommend_actions(
        self,
        metrics: MetricSnapshot,
        factors: List[str],
        probability: float,
    ) -> List[RemediationAction]:
        """Recommend remediation actions based on metrics and factors."""
        actions = []

        # High CPU -> Scale up or restart
        if metrics.cpu_usage > 0.8:
            actions.append(RemediationAction.SCALE_UP)

        # High memory -> Memory cleanup
        if metrics.memory_usage > 0.85:
            actions.append(RemediationAction.MEMORY_CLEANUP)

        # High error rate -> Circuit break
        if metrics.error_rate > 0.05:
            actions.append(RemediationAction.CIRCUIT_BREAK)

        # High latency -> Rate limit
        if metrics.latency_p99 > 1000:  # 1 second
            actions.append(RemediationAction.RATE_LIMIT)

        # High queue depth -> Scale up
        if metrics.queue_depth > 1000:
            actions.append(RemediationAction.SCALE_UP)

        # Connection issues -> Reset connections
        if metrics.connection_count > 500 or "connection" in str(factors).lower():
            actions.append(RemediationAction.CONNECTION_RESET)

        # Critical probability -> Failover
        if probability > self.failure_threshold:
            actions.append(RemediationAction.FAILOVER)

        return actions[:3]  # Return top 3 recommendations


# ═══════════════════════════════════════════════════════════════════════════════
# Autonomous Healer
# ═══════════════════════════════════════════════════════════════════════════════


class AutonomousHealer:
    """
    Autonomous healing system that takes remediation actions.

    Implements a decision tree for selecting and executing remediation
    actions based on failure predictions and component state.
    """

    def __init__(
        self,
        auto_remediate: bool = True,
        max_retries: int = 3,
        cooldown_seconds: int = 60,
    ):
        """
        Initialize autonomous healer.

        Args:
            auto_remediate: Whether to automatically execute remediation
            max_retries: Maximum retries for failed remediation
            cooldown_seconds: Cooldown between remediation attempts
        """
        self.auto_remediate = auto_remediate
        self.max_retries = max_retries
        self.cooldown_seconds = cooldown_seconds

        self.action_handlers: Dict[RemediationAction, Callable] = {}
        self.last_action_time: Dict[str, datetime] = {}
        self.action_history: List[RemediationResult] = []

        self._lock = threading.Lock()

        _healing_logger.info(
            f"AutonomousHealer initialized: auto_remediate={auto_remediate}, "
            f"max_retries={max_retries}"
        )

    def register_handler(
        self,
        action: RemediationAction,
        handler: Callable[[str], Tuple[bool, Optional[str]]],
    ) -> None:
        """
        Register a handler for a remediation action.

        Args:
            action: The remediation action
            handler: Callable that takes component name and returns (success, error_message)
        """
        self.action_handlers[action] = handler
        _healing_logger.info(f"Registered handler for {action.value}")

    def _check_cooldown(self, component: str) -> bool:
        """Check if component is in cooldown."""
        if component not in self.last_action_time:
            return False

        elapsed = (datetime.now() - self.last_action_time[component]).total_seconds()
        return elapsed < self.cooldown_seconds

    def execute_remediation(
        self,
        prediction: FailurePrediction,
        metrics: MetricSnapshot,
    ) -> List[RemediationResult]:
        """
        Execute remediation actions for a prediction.

        Args:
            prediction: The failure prediction
            metrics: Current metrics

        Returns:
            List of remediation results
        """
        results = []

        with self._lock:
            # Check cooldown
            if self._check_cooldown(prediction.component):
                _healing_logger.info(
                    f"Component {prediction.component} in cooldown, skipping remediation"
                )
                return results

            # Execute recommended actions
            for action in prediction.recommended_actions:
                if action not in self.action_handlers:
                    _healing_logger.warning(f"No handler for action {action.value}")
                    continue

                if not self.auto_remediate:
                    _healing_logger.info(
                        f"Would execute {action.value} on {prediction.component} "
                        "(auto_remediate=False)"
                    )
                    continue

                # Execute with retries
                for attempt in range(self.max_retries):
                    start_time = time.time()

                    try:
                        success, error = self.action_handlers[action](
                            prediction.component
                        )
                        duration_ms = (time.time() - start_time) * 1000

                        result = RemediationResult(
                            action=action,
                            component=prediction.component,
                            success=success,
                            duration_ms=duration_ms,
                            error_message=error,
                            metrics_before=metrics,
                        )

                        self.action_history.append(result)
                        results.append(result)

                        if success:
                            _healing_logger.info(
                                f"Remediation {action.value} on {prediction.component} "
                                f"succeeded in {duration_ms:.2f}ms"
                            )
                            break
                        else:
                            _healing_logger.warning(
                                f"Remediation {action.value} on {prediction.component} "
                                f"failed (attempt {attempt + 1}): {error}"
                            )

                    except Exception as e:
                        duration_ms = (time.time() - start_time) * 1000
                        result = RemediationResult(
                            action=action,
                            component=prediction.component,
                            success=False,
                            duration_ms=duration_ms,
                            error_message=str(e),
                        )
                        self.action_history.append(result)
                        results.append(result)
                        _healing_logger.error(
                            f"Remediation {action.value} on {prediction.component} "
                            f"raised exception: {e}"
                        )

            # Update cooldown
            self.last_action_time[prediction.component] = datetime.now()

        return results

    def get_action_history(
        self,
        component: Optional[str] = None,
        limit: int = 100,
    ) -> List[RemediationResult]:
        """Get remediation action history."""
        history = self.action_history[-limit:]
        if component:
            history = [r for r in history if r.component == component]
        return history


# ═══════════════════════════════════════════════════════════════════════════════
# Predictive Health Monitor
# ═══════════════════════════════════════════════════════════════════════════════


class PredictiveHealthMonitor:
    """
    Main class for predictive self-healing.

    Integrates:
    - Anomaly detection
    - Metric forecasting
    - Failure prediction
    - Autonomous remediation
    - Alert management
    """

    def __init__(
        self,
        auto_remediate: bool = True,
        check_interval_seconds: int = 10,
        alert_retention_hours: int = 24,
    ):
        """
        Initialize predictive health monitor.

        Args:
            auto_remediate: Whether to automatically execute remediation
            check_interval_seconds: Interval between health checks
            alert_retention_hours: How long to retain alerts
        """
        self.check_interval_seconds = check_interval_seconds
        self.alert_retention_hours = alert_retention_hours

        self.failure_predictor = FailurePredictor()
        self.healer = AutonomousHealer(auto_remediate=auto_remediate)

        self.components: Dict[str, ComponentState] = {}
        self.metric_history: Dict[str, deque] = {}
        self.alerts: List[Alert] = []

        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self._alert_counter = 0

        _healing_logger.info(
            f"PredictiveHealthMonitor initialized: auto_remediate={auto_remediate}, "
            f"check_interval={check_interval_seconds}s"
        )

    def register_component(
        self,
        component: str,
        initial_state: ComponentState = ComponentState.HEALTHY,
    ) -> None:
        """Register a component for monitoring."""
        with self._lock:
            self._register_component_internal(component, initial_state)

    def _register_component_internal(
        self,
        component: str,
        initial_state: ComponentState = ComponentState.HEALTHY,
    ) -> None:
        """Internal registration without lock (caller must hold lock)."""
        self.components[component] = initial_state
        self.metric_history[component] = deque(maxlen=1000)
        _healing_logger.info(f"Registered component: {component}")

    def record_metrics(self, metrics: MetricSnapshot) -> None:
        """Record metrics for a component."""
        with self._lock:
            if metrics.component not in self.components:
                self._register_component_internal(metrics.component)

            self.metric_history[metrics.component].append(metrics)
            self.failure_predictor.anomaly_detector.add_observation(
                metrics.component, metrics
            )

    def check_component(self, component: str) -> Optional[FailurePrediction]:
        """
        Check a component's health and get failure prediction.

        Args:
            component: Component name

        Returns:
            Failure prediction if available
        """
        with self._lock:
            if component not in self.metric_history:
                return None

            history = list(self.metric_history[component])
            if not history:
                return None

            current = history[-1]

        prediction = self.failure_predictor.predict(component, current, history)

        # Update component state
        with self._lock:
            self.components[component] = prediction.predicted_state

        # Create alert if needed
        if prediction.predicted_state in [
            ComponentState.AT_RISK,
            ComponentState.CRITICAL,
        ]:
            self._create_alert(prediction)

        # Execute remediation if needed
        if prediction.probability >= self.failure_predictor.warning_threshold:
            self.healer.execute_remediation(prediction, current)

        return prediction

    def _create_alert(self, prediction: FailurePrediction) -> Alert:
        """Create an alert from a prediction."""
        with self._lock:
            self._alert_counter += 1
            alert_id = f"alert_{self._alert_counter}"

        severity = (
            AlertSeverity.CRITICAL
            if prediction.probability > 0.7
            else AlertSeverity.WARNING
        )

        alert = Alert(
            id=alert_id,
            timestamp=datetime.now(),
            component=prediction.component,
            severity=severity,
            message=f"Component {prediction.component} has {prediction.probability:.1%} "
            f"failure probability. Contributing factors: {', '.join(prediction.contributing_factors[:3])}",
            prediction=prediction,
        )

        with self._lock:
            self.alerts.append(alert)
            # Cleanup old alerts
            cutoff = datetime.now() - timedelta(hours=self.alert_retention_hours)
            self.alerts = [a for a in self.alerts if a.timestamp > cutoff]

        _healing_logger.warning(f"Alert created: {alert.message}")
        return alert

    def get_component_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all components."""
        with self._lock:
            status = {}
            for component, state in self.components.items():
                history = list(self.metric_history.get(component, []))
                status[component] = {
                    "state": state.value,
                    "metric_count": len(history),
                    "last_metric": history[-1] if history else None,
                }
            return status

    def get_active_alerts(self) -> List[Alert]:
        """Get unresolved alerts."""
        with self._lock:
            return [a for a in self.alerts if not a.resolved]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        with self._lock:
            for alert in self.alerts:
                if alert.id == alert_id:
                    alert.acknowledged = True
                    return True
            return False

    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert."""
        with self._lock:
            for alert in self.alerts:
                if alert.id == alert_id:
                    alert.resolved = True
                    return True
            return False

    def start_monitoring(self) -> None:
        """Start background monitoring."""
        if self._running:
            return

        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        _healing_logger.info("Background monitoring started")

    def stop_monitoring(self) -> None:
        """Stop background monitoring."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        _healing_logger.info("Background monitoring stopped")

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._running:
            try:
                with self._lock:
                    components = list(self.components.keys())

                for component in components:
                    self.check_component(component)

                time.sleep(self.check_interval_seconds)

            except Exception as e:
                _healing_logger.error(f"Monitor loop error: {e}")
                time.sleep(self.check_interval_seconds)


# ═══════════════════════════════════════════════════════════════════════════════
# Chaos Engineering
# ═══════════════════════════════════════════════════════════════════════════════


class ChaosSimulator:
    """
    Chaos engineering simulator for testing self-healing capabilities.

    Injects various failure scenarios to verify system resilience.
    """

    def __init__(self, monitor: PredictiveHealthMonitor):
        """
        Initialize chaos simulator.

        Args:
            monitor: The health monitor to test
        """
        self.monitor = monitor
        _healing_logger.info("ChaosSimulator initialized")

    def inject_cpu_spike(self, component: str, duration_seconds: int = 30) -> None:
        """Simulate CPU spike."""
        _healing_logger.info(
            f"Injecting CPU spike on {component} for {duration_seconds}s"
        )

        for _ in range(duration_seconds):
            metrics = MetricSnapshot(
                timestamp=datetime.now(),
                component=component,
                cpu_usage=0.95 + np.random.uniform(-0.05, 0.05),
                memory_usage=0.5,
                latency_p99=200,
                error_rate=0.01,
                throughput=100,
                queue_depth=50,
                connection_count=100,
            )
            self.monitor.record_metrics(metrics)
            time.sleep(1)

    def inject_memory_leak(self, component: str, leak_rate: float = 0.01) -> None:
        """Simulate gradual memory leak."""
        _healing_logger.info(f"Injecting memory leak on {component}")

        memory = 0.5
        for _ in range(50):
            memory = min(0.99, memory + leak_rate)
            metrics = MetricSnapshot(
                timestamp=datetime.now(),
                component=component,
                cpu_usage=0.5,
                memory_usage=memory,
                latency_p99=200 * (1 + memory),
                error_rate=0.01 * (1 + memory),
                throughput=100 * (1 - memory / 2),
                queue_depth=int(50 * (1 + memory)),
                connection_count=100,
            )
            self.monitor.record_metrics(metrics)
            time.sleep(0.5)

    def inject_error_spike(self, component: str, error_rate: float = 0.2) -> None:
        """Simulate error rate spike."""
        _healing_logger.info(f"Injecting error spike ({error_rate:.0%}) on {component}")

        for _ in range(20):
            metrics = MetricSnapshot(
                timestamp=datetime.now(),
                component=component,
                cpu_usage=0.6,
                memory_usage=0.5,
                latency_p99=500,
                error_rate=error_rate + np.random.uniform(-0.05, 0.05),
                throughput=50,
                queue_depth=200,
                connection_count=100,
            )
            self.monitor.record_metrics(metrics)
            time.sleep(0.5)

    def inject_latency_degradation(
        self,
        component: str,
        target_latency: float = 2000,
    ) -> None:
        """Simulate gradual latency degradation."""
        _healing_logger.info(f"Injecting latency degradation on {component}")

        latency = 100
        for _ in range(30):
            latency = min(target_latency, latency * 1.1)
            metrics = MetricSnapshot(
                timestamp=datetime.now(),
                component=component,
                cpu_usage=0.5 + latency / 10000,
                memory_usage=0.5,
                latency_p99=latency,
                error_rate=0.01 * (latency / 100),
                throughput=max(10, 100 - latency / 50),
                queue_depth=int(latency / 10),
                connection_count=100,
            )
            self.monitor.record_metrics(metrics)
            time.sleep(0.5)


# Export public classes
__all__ = [
    "PredictiveHealthMonitor",
    "FailurePredictor",
    "AutonomousHealer",
    "AnomalyDetector",
    "MetricForecaster",
    "ChaosSimulator",
    "MetricSnapshot",
    "FailurePrediction",
    "Alert",
    "RemediationAction",
    "RemediationResult",
    "ComponentState",
    "AlertSeverity",
]
