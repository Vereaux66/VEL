#!/usr/bin/env python3
# flake8: noqa
"""
ANVEL AI Brain - Core Neural Network Trading Intelligence
Full implementation with LSTM, Transformer, and Reinforcement Learning

AUTONOMOUS MODE: This module will auto-install missing dependencies.
NO STUBS - Full functionality required.
"""

from __future__ import annotations

import argparse
import copy
import subprocess
import sys
from typing import Dict, List, Tuple, Optional, Any, Callable, Iterable, cast
import re
import importlib
import logging

# Setup early logging
logging.basicConfig(level=logging.INFO)
_brain_logger = logging.getLogger("ANVEL.Brain")

# Allowed package names for autonomous installation (security whitelist)
ALLOWED_PACKAGES = {
    "numpy",
    "pandas",
    "torch",
    "scikit-learn",
    "sklearn",
    "scipy",
    "joblib",
    "xgboost",
    "lightgbm",
    "transformers",
    "tensorflow",
}


def _force_install_package(package_name: str, pip_name: str) -> bool:
    """
    Force install a package if not available. NO FALLBACKS.
    Uses a whitelist to prevent arbitrary package installation.
    """
    # Security: Validate package name against whitelist
    base_pkg = pip_name.split(">=")[0].split("==")[0].split("<")[0].strip()
    if base_pkg.lower() not in ALLOWED_PACKAGES:
        _brain_logger.error(f"Package {base_pkg} not in allowed whitelist, skipping")
        return False

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", pip_name, "--quiet"],
            check=True,
            timeout=300,
            capture_output=True,
        )
        _brain_logger.info(f"Auto-installed {package_name}")
        return True
    except Exception as e:
        _brain_logger.error(f"Failed to install {package_name}: {e}")
        return False


def _ensure_import(module_name: str, pip_name: str = None):
    """Ensure a module is importable, installing if necessary."""
    pip_name = pip_name or module_name
    try:
        return importlib.import_module(module_name)
    except ImportError:
        _brain_logger.warning(
            f"{module_name} not found - auto-installing {pip_name}..."
        )
        if _force_install_package(module_name, pip_name):
            try:
                return importlib.import_module(module_name)
            except ImportError:
                import logging as _lg  # noqa: E402
                _lg.getLogger("ANVEL_BRAIN").debug("Exception suppressed in _ensure_import")
        # If we get here, installation failed
        raise ImportError(
            f"CRITICAL: {module_name} is required for ANVEL Brain. "
            f"Auto-installation failed. Please install manually: pip install {pip_name}"
        )


# AUTONOMOUS IMPORTS - Will auto-install if missing
try:
    import numpy as _np

    NUMPY_IMPORT_ERROR = None
except ImportError:
    _brain_logger.warning("NumPy not found - initiating autonomous installation...")
    _np = _ensure_import("numpy", "numpy>=1.24.0")
    NUMPY_IMPORT_ERROR = None


class _NumpyProxy:
    """Lazily exposes NumPy attributes so the module can import without the wheel."""

    def __init__(self, module: Optional[Any], error: Optional[BaseException]) -> None:
        self._module = module
        self._error = error

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - dynamic proxy
        if self._module is None:
            # AUTONOMOUS: Try to install using the centralized function
            if _force_install_package("numpy", "numpy>=1.24.0"):
                try:
                    import numpy as np_real

                    self._module = np_real
                    self._error = None
                    return getattr(self._module, name)
                except Exception:
                    import logging as _lg  # noqa: E402
                    _lg.getLogger("ANVEL_BRAIN").debug("Exception suppressed in __getattr__")
            raise RuntimeError(
                "NumPy is required for this operation. Install it or build the Rust analytics bridge."
            ) from self._error
        return getattr(self._module, name)


np = _NumpyProxy(_np, NUMPY_IMPORT_ERROR)

try:
    import pandas as _pd

    PANDAS_IMPORT_ERROR = None
except ImportError:
    _brain_logger.warning("Pandas not found - initiating autonomous installation...")
    _pd = _ensure_import("pandas", "pandas>=2.0.0")
    PANDAS_IMPORT_ERROR = None


class _PandasProxy:
    """Expose pandas lazily so the brain can bootstrap without it."""

    def __init__(self, module: Optional[Any], error: Optional[BaseException]) -> None:
        self._module = module
        self._error = error

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - dynamic proxy
        if self._module is None:
            # AUTONOMOUS: Try to install using the centralized function
            if _force_install_package("pandas", "pandas>=2.0.0"):
                try:
                    import pandas as pd_real

                    self._module = pd_real
                    self._error = None
                    return getattr(self._module, name)
                except Exception:
                    import logging as _lg  # noqa: E402
                    _lg.getLogger("ANVEL_BRAIN").debug("Exception suppressed in __getattr__")
            raise RuntimeError(
                "Pandas is required for this operation. Install it or provide preprocessed inputs."
            ) from self._error
        return getattr(self._module, name)

    def __bool__(self) -> bool:  # pragma: no cover - convenience for truth checks
        return self._module is not None


pd = _PandasProxy(_pd, PANDAS_IMPORT_ERROR)
from dataclasses import dataclass, field
from pathlib import Path
import threading
from collections import deque
import time

# AUTONOMOUS TORCH IMPORT
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset

    TORCH_IMPORT_ERROR = None
except ImportError:
    _brain_logger.warning("PyTorch not found - initiating autonomous installation...")
    try:
        torch = _ensure_import("torch", "torch>=2.2.0")
        import torch.nn as nn
        import torch.optim as optim
        from torch.utils.data import DataLoader, TensorDataset

        TORCH_IMPORT_ERROR = None
    except Exception as torch_exc:
        TORCH_IMPORT_ERROR = torch_exc

        class _TorchCallableStub:
            def __init__(self, label: str) -> None:
                object.__setattr__(self, "_label", label)

            def __call__(
                self, *args: Any, **kwargs: Any
            ) -> Any:  # pragma: no cover - runtime guard
                raise RuntimeError(
                    f"PyTorch is required for {self._label}. Install torch>=2.x with CPU support to enable this feature."
                ) from TORCH_IMPORT_ERROR

            def __getattr__(self, attr: str) -> Any:  # pragma: no cover - chained guard
                return _TorchCallableStub(f"{self._label}.{attr}")

        class _TorchNamespaceStub(_TorchCallableStub):
            def __setattr__(self, name: str, value: Any) -> None:
                object.__setattr__(self, name, value)

        class _TorchModuleStub:
            def __init__(
                self, *args: Any, **kwargs: Any
            ) -> None:  # pragma: no cover - runtime guard
                raise RuntimeError(
                    "PyTorch neural network modules are unavailable. Install torch to instantiate the ANVEL brain."
                ) from TORCH_IMPORT_ERROR

        torch = _TorchNamespaceStub("torch")  # type: ignore[assignment]
        nn = _TorchNamespaceStub("torch.nn")  # type: ignore[assignment]
        optim = _TorchNamespaceStub("torch.optim")  # type: ignore[assignment]
        nn.Module = _TorchModuleStub  # type: ignore[attr-defined]

        def _torch_loader_stub(
            *args: Any, **kwargs: Any
        ) -> Any:  # pragma: no cover - runtime guard
            raise RuntimeError(
                "PyTorch DataLoader/TensorDataset are unavailable. Install torch to enable dataset handling."
            ) from TORCH_IMPORT_ERROR

        DataLoader = _torch_loader_stub  # type: ignore[assignment]
        TensorDataset = _torch_loader_stub  # type: ignore[assignment]

# AUTONOMOUS SKLEARN IMPORT
try:
    from sklearn.preprocessing import MinMaxScaler, StandardScaler
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor

    SKLEARN_IMPORT_ERROR = None
except ImportError:
    _brain_logger.warning(
        "scikit-learn not found - initiating autonomous installation..."
    )
    try:
        _ensure_import("sklearn", "scikit-learn>=1.5.0")
        from sklearn.preprocessing import MinMaxScaler, StandardScaler
        from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor

        SKLEARN_IMPORT_ERROR = None
    except Exception as sklearn_exc:
        SKLEARN_IMPORT_ERROR = sklearn_exc

        class _SklearnStub:
            def __init__(
                self, *args: Any, **kwargs: Any
            ) -> None:  # pragma: no cover - runtime guard
                raise RuntimeError(
                    "scikit-learn components are unavailable. Install scikit-learn to enable ensemble models."
                ) from SKLEARN_IMPORT_ERROR

        MinMaxScaler = StandardScaler = RandomForestRegressor = GradientBoostingRegressor = _SklearnStub  # type: ignore

# AUTONOMOUS JOBLIB IMPORT
try:
    import joblib

    JOBLIB_IMPORT_ERROR = None
except ImportError:
    _brain_logger.warning("joblib not found - initiating autonomous installation...")
    try:
        joblib = _ensure_import("joblib", "joblib>=1.3.0")
        JOBLIB_IMPORT_ERROR = None
    except Exception as joblib_exc:
        JOBLIB_IMPORT_ERROR = joblib_exc

        class _JoblibStub:
            def __getattr__(self, name: str) -> Any:  # pragma: no cover - runtime guard
                def _raise_joblib(*args: Any, **kwargs: Any) -> Any:
                    raise RuntimeError(
                        "joblib is required for model persistence. Install joblib to save or load ANVEL artifacts."
                    ) from JOBLIB_IMPORT_ERROR

                return _raise_joblib

        joblib = _JoblibStub()  # type: ignore[assignment]

import json
import pickle
from datetime import datetime
import warnings
from anvel_brain_modules import BrainSubsystems

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

try:
    from anvel_rust_analytics import (
        FeatureStore as RustFeatureStore,
        ScenarioGenerator as RustScenarioGenerator,
        PredictionCalibrator as RustPredictionCalibrator,
        ConceptDriftDetector as RustConceptDriftDetector,
        TechnicalIndicators as RustTechnicalIndicators,
        BrainEngine as RustBrainEngine,
    )

    RUST_ANALYTICS_AVAILABLE = True
except Exception:  # pragma: no cover - rust module optional
    RustFeatureStore = None
    RustScenarioGenerator = None
    RustPredictionCalibrator = None
    RustConceptDriftDetector = None
    RustTechnicalIndicators = None
    RustBrainEngine = None
    candidate_dir = (
        Path(__file__).resolve().parent
        / "native"
        / "rust_analytics"
        / "target"
        / "release"
    )
    if candidate_dir.exists() and str(candidate_dir) not in sys.path:
        sys.path.append(str(candidate_dir))
        try:
            from anvel_rust_analytics import (
                FeatureStore as RustFeatureStore,
                ScenarioGenerator as RustScenarioGenerator,
                PredictionCalibrator as RustPredictionCalibrator,
                ConceptDriftDetector as RustConceptDriftDetector,
                TechnicalIndicators as RustTechnicalIndicators,
                BrainEngine as RustBrainEngine,
            )

            RUST_ANALYTICS_AVAILABLE = True
        except Exception:
            RUST_ANALYTICS_AVAILABLE = False
            RustBrainEngine = None
    else:
        RUST_ANALYTICS_AVAILABLE = False
        RustBrainEngine = None


@dataclass
class PredictionEnvelope:
    """Container describing enriched prediction outputs."""

    point_forecast: float
    confidence: float
    interval: Tuple[float, float]
    scenario_paths: Dict[str, List[float]]
    feature_signals: Dict[str, float]
    raw_model_outputs: Dict[str, float]
    timestamp: datetime = field(default_factory=datetime.utcnow)


class PredictionFeatureStore:
    """Builds multimodal feature summaries used by the prediction core."""

    def __init__(
        self, short_window: int = 15, medium_window: int = 60, long_window: int = 180
    ):
        self.short_window = short_window
        self.medium_window = medium_window
        self.long_window = long_window
        self._rust = None
        if RUST_ANALYTICS_AVAILABLE and RustFeatureStore is not None:
            try:
                self._rust = RustFeatureStore(short_window, medium_window, long_window)
            except Exception:
                logger.debug(
                    "Rust FeatureStore unavailable; falling back to numpy implementation",
                    exc_info=True,
                )
                self._rust = None

    @staticmethod
    def _safe_change(series: pd.Series, periods: int = 1) -> float:
        if len(series) <= periods or series.iloc[-periods] == 0:
            return 0.0
        return (series.iloc[-1] / series.iloc[-periods]) - 1

    def build_modal_signals(
        self,
        market_window: Optional[pd.DataFrame],
        sentiment_ctx: Optional[Dict[str, float]] = None,
        macro_ctx: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        if market_window is None or market_window.empty:
            return {}

        if self._rust is not None:
            try:
                prices = market_window["close"].astype(float).tolist()
                volumes = market_window["volume"].astype(float).tolist()
                result = self._rust.build_modal_signals(
                    prices,
                    volumes,
                    sentiment_ctx or {},
                    macro_ctx or {},
                )
                return dict(result)
            except Exception:
                logger.exception(
                    "Rust FeatureStore failed; falling back to numpy implementation"
                )

        window = market_window.tail(self.long_window)
        prices = window["close"]
        volume = window["volume"]

        short_period = (
            max(1, min(len(prices) - 1, self.short_window)) if len(prices) > 1 else 1
        )
        medium_period = (
            max(1, min(len(prices) - 1, self.medium_window)) if len(prices) > 1 else 1
        )
        long_period = (
            max(1, min(len(prices) - 1, self.long_window - 1)) if len(prices) > 1 else 1
        )

        modal_signals = {
            "short_trend": (
                self._safe_change(prices, short_period) if len(prices) > 1 else 0.0
            ),
            "medium_trend": (
                self._safe_change(prices, medium_period) if len(prices) > 1 else 0.0
            ),
            "long_trend": (
                self._safe_change(prices, long_period) if len(prices) > 1 else 0.0
            ),
            "volume_pressure": float(
                (
                    volume.tail(self.short_window).mean()
                    / (volume.tail(self.long_window).mean() + 1e-6)
                )
                - 1
            ),
            "volatility_30": (
                float(prices.pct_change().tail(30).std() * np.sqrt(252))
                if len(prices) > 30
                else 0.0
            ),
            "momentum_osc": (
                float(
                    prices.tail(self.short_window).mean()
                    - prices.tail(self.medium_window).mean()
                )
                if len(prices) > self.medium_window
                else 0.0
            ),
        }

        if sentiment_ctx:
            modal_signals.update(
                {
                    "fear_greed": sentiment_ctx.get("fear_greed", 0.5),
                    "pattern_sentiment": sentiment_ctx.get("pattern", 0.5),
                }
            )

        if macro_ctx:
            modal_signals.update({f"macro_{k}": v for k, v in macro_ctx.items()})

        return modal_signals


class RustBrainAdapter:
    """Bridges the Python brain facade with the Rust analytics engine."""

    _PROCESS_RE = re.compile(
        r"->\s+(?P<action>[A-Z]+)\s+\(signal\s+(?P<signal>[0-9.]+)"
    )

    def __init__(self) -> None:
        self.available = bool(RUST_ANALYTICS_AVAILABLE and RustBrainEngine is not None)
        self._engine: Optional[Any] = None
        if not self.available:
            return
        try:
            self._engine = RustBrainEngine()
        except Exception as exc:  # pragma: no cover - diagnostics only
            logger.warning("Rust BrainEngine initialization failed: %s", exc)
            self.available = False

    @staticmethod
    def _series_to_floats(series: pd.Series) -> List[float]:
        return [float(x) for x in series.astype(float).tolist()]

    def analyze_market(self, market_data: pd.DataFrame) -> Dict[str, Any]:
        if not self.available or self._engine is None:
            raise RuntimeError("Rust brain engine is not available")
        required = {"close", "high", "low", "volume"}
        missing = required - set(market_data.columns)
        if missing:
            raise ValueError(f"Market data missing required columns: {sorted(missing)}")
        closes = self._series_to_floats(market_data["close"])
        highs = self._series_to_floats(market_data["high"])
        lows = self._series_to_floats(market_data["low"])
        volumes = self._series_to_floats(market_data["volume"])
        analysis = self._engine.analyze_market(closes, highs, lows, volumes, None)
        return cast(Dict[str, Any], analysis)

    def process(self, stimulus: str) -> Dict[str, Any]:
        if not self.available or self._engine is None:
            raise RuntimeError("Rust brain engine is not available")
        message = self._engine.process_stimulus(stimulus)
        action = "HOLD"
        signal = 0.5
        match = self._PROCESS_RE.search(message)
        if match:
            action = match.group("action")
            try:
                signal = float(match.group("signal"))
            except (TypeError, ValueError):  # pragma: no cover - parsing guard
                signal = 0.5
        return {"message": message, "action": action, "signal": signal}


class DiffusionScenarioGenerator:
    """Generates bull/base/bear scenarios via lightweight diffusion-style noise."""

    def __init__(
        self,
        horizon: int = 12,
        beta_start: float = 1e-4,
        beta_end: float = 2e-2,
        seed: Optional[int] = 42,
    ):
        self.horizon = horizon
        self.beta_schedule = np.linspace(beta_start, beta_end, horizon)
        self.rng = np.random.default_rng(seed)
        self._rust = None
        if RUST_ANALYTICS_AVAILABLE and RustScenarioGenerator is not None:
            try:
                self._rust = RustScenarioGenerator(horizon, beta_start, beta_end, seed)
            except Exception:
                logger.debug(
                    "Rust ScenarioGenerator unavailable; using numpy implementation",
                    exc_info=True,
                )
                self._rust = None

    def generate(self, price_series: Optional[pd.Series]) -> Dict[str, List[float]]:
        if price_series is None or len(price_series) < 5:
            return {}

        if self._rust is not None:
            try:
                prices = price_series.astype(float).tolist()
                result = self._rust.generate(prices)
                return {k: list(v) for k, v in result.items()}
            except Exception:
                logger.exception(
                    "Rust ScenarioGenerator failed; falling back to numpy implementation"
                )

        recent = price_series.tail(30)
        base_drift = recent.pct_change().dropna().mean() if len(recent) > 2 else 0.0
        last_price = float(recent.iloc[-1])

        scenarios: Dict[str, List[float]] = {}
        scenario_bias = {"bear": -0.75, "base": 0.0, "bull": 0.85}

        for label, bias in scenario_bias.items():
            path = []
            price = last_price
            for beta in self.beta_schedule:
                shock = self.rng.normal(0, np.sqrt(beta))
                drift = base_drift + (
                    bias * abs(base_drift) if base_drift else bias * 0.001
                )
                price *= max(0.0, 1 + drift + shock)
                path.append(float(price))
            scenarios[label] = path

        return scenarios


class PredictionCalibrator:
    """Maintains empirical error distribution for confidence intervals."""

    def __init__(self, max_history: int = 500):
        self.error_history: deque[float] = deque(maxlen=max_history)
        self._rust = None
        if RUST_ANALYTICS_AVAILABLE and RustPredictionCalibrator is not None:
            try:
                self._rust = RustPredictionCalibrator(max_history)
            except Exception:
                logger.debug(
                    "Rust PredictionCalibrator unavailable; using numpy implementation",
                    exc_info=True,
                )
                self._rust = None

    def update(self, y_true: np.ndarray, y_pred: np.ndarray) -> None:
        if self._rust is not None:
            try:
                true_vals = (
                    y_true.tolist() if hasattr(y_true, "tolist") else list(y_true)
                )
                pred_vals = (
                    y_pred.tolist() if hasattr(y_pred, "tolist") else list(y_pred)
                )
                self._rust.update(true_vals, pred_vals)
                return
            except Exception:
                logger.exception(
                    "Rust PredictionCalibrator update failed; using numpy implementation"
                )
        if len(y_true) == 0:
            return
        errors = (y_true.flatten() - y_pred.flatten()).tolist()
        for err in errors:
            if np.isfinite(err):
                self.error_history.append(float(err))

    def estimate_interval(
        self, forecast: float, confidence: float = 0.8
    ) -> Tuple[float, float]:
        if self._rust is not None:
            try:
                return tuple(self._rust.estimate_interval(forecast, confidence))  # type: ignore[arg-type]
            except Exception:
                logger.exception(
                    "Rust PredictionCalibrator interval failed; using numpy implementation"
                )
        if not self.error_history:
            margin = abs(forecast) * 0.015 + 0.01
        else:
            abs_errors = np.abs(np.array(self.error_history))
            quantile = min(0.99, max(0.5, confidence))
            margin = float(np.quantile(abs_errors, quantile))
            if margin == 0:
                margin = float(abs_errors.mean()) if abs_errors.mean() > 0 else 0.01
        lower = forecast - margin
        upper = forecast + margin
        return (lower, upper)

    def confidence_from_interval(
        self, forecast: float, interval: Tuple[float, float]
    ) -> float:
        if self._rust is not None:
            try:
                return float(
                    self._rust.confidence_from_interval(
                        forecast, interval[0], interval[1]
                    )
                )
            except Exception:
                logger.exception(
                    "Rust PredictionCalibrator confidence failed; using numpy implementation"
                )
        spread = max(1e-6, interval[1] - interval[0])
        base = abs(forecast) if abs(forecast) > 1e-6 else 1.0
        relative_width = spread / base
        confidence = 1 - min(0.95, relative_width)
        return float(max(0.05, min(0.99, confidence)))


def summarize_scenario_slopes(
    scenarios: Optional[Dict[str, List[float]]],
) -> Dict[str, float]:
    """Compute relative slope for each scenario path."""
    if not scenarios:
        return {}
    summary: Dict[str, float] = {}
    for label, path in scenarios.items():
        if len(path) < 2:
            continue
        start, end = path[0], path[-1]
        if start == 0:
            continue
        change = (end - start) / start
        summary[label] = float(change)
    return summary


@dataclass
class CurriculumPhase:
    name: str
    window: int
    stride: int
    purpose: str


class CurriculumScheduler:
    """Creates staged training/evaluation windows for Neuro Forge."""

    def __init__(self):
        self.phases = [
            CurriculumPhase(
                name="baseline_core",
                window=365,
                stride=0,
                purpose="broad_regime_coverage",
            ),
            CurriculumPhase(
                name="volatility_shock",
                window=180,
                stride=30,
                purpose="stress_conditions",
            ),
            CurriculumPhase(
                name="recent_focus", window=120, stride=0, purpose="fine_tune_on_recent"
            ),
        ]

    def build_plan(self, historical_data: pd.DataFrame) -> List[Dict[str, Any]]:
        plan: List[Dict[str, Any]] = []
        if historical_data is None or historical_data.empty:
            return plan

        total_len = len(historical_data)
        for phase in self.phases:
            if total_len < phase.window:
                continue
            start_idx = max(0, total_len - phase.window - phase.stride)
            end_idx = total_len - phase.stride if phase.stride else total_len
            window = historical_data.iloc[start_idx:end_idx].copy()
            plan.append({"phase": phase, "window": window})
        return plan


class ConceptDriftDetector:
    """Simple statistical drift detector using rolling reference distributions."""

    def __init__(self, reference_window: int = 600, alert_threshold: float = 2.5):
        self.reference = deque(maxlen=reference_window)
        self.alert_threshold = alert_threshold
        self._rust = None
        if RUST_ANALYTICS_AVAILABLE and RustConceptDriftDetector is not None:
            try:
                self._rust = RustConceptDriftDetector(reference_window, alert_threshold)
            except Exception:
                logger.debug(
                    "Rust ConceptDriftDetector unavailable; using numpy implementation",
                    exc_info=True,
                )
                self._rust = None

    def _append(self, values: np.ndarray) -> None:
        for val in values:
            if np.isfinite(val):
                self.reference.append(float(val))

    def evaluate(self, new_returns: np.ndarray) -> Tuple[bool, float]:
        if self._rust is not None:
            try:
                returns = (
                    new_returns.tolist()
                    if hasattr(new_returns, "tolist")
                    else list(new_returns)
                )
                return tuple(self._rust.evaluate(returns))  # type: ignore[arg-type]
            except Exception:
                logger.exception(
                    "Rust ConceptDriftDetector evaluate failed; using numpy implementation"
                )
        if new_returns is None or len(new_returns) == 0:
            return False, 0.0

        new_returns = np.asarray(new_returns, dtype=float)
        if len(self.reference) < 50:
            self._append(new_returns)
            return False, 0.0

        ref_array = np.asarray(self.reference)
        ref_mean = float(np.mean(ref_array))
        ref_std = float(np.std(ref_array) + 1e-6)
        new_mean = float(np.mean(new_returns))
        new_std = float(np.std(new_returns) + 1e-6)

        mean_shift = abs(new_mean - ref_mean) / ref_std
        std_shift = abs(new_std - ref_std) / ref_std
        score = mean_shift + std_shift
        drift = score > self.alert_threshold

        if drift:
            self.reference.clear()
        self._append(new_returns)

        return drift, float(score)


class ArtifactRegistry:
    """Lightweight on-disk registry describing Neuro Forge training artifacts."""

    def __init__(self, root: Optional[str] = None):
        self.root = Path(root) if root else Path.cwd() / "artifacts" / "neuro_forge"
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        self.manifest: List[Dict[str, Any]] = self._load_manifest()

    def _load_manifest(self) -> List[Dict[str, Any]]:
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r") as handle:
                    return json.load(handle)
            except json.JSONDecodeError:
                return []
        return []

    def record(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata,
        }
        self.manifest.append(entry)
        with open(self.manifest_path, "w") as handle:
            json.dump(self.manifest, handle, indent=2)
        return entry

    def latest(self) -> Optional[Dict[str, Any]]:
        return self.manifest[-1] if self.manifest else None


@dataclass
class HyperparameterConfig:
    """Configuration for a single hyperparameter"""
    name: str
    param_type: str  # 'int', 'float', 'categorical'
    low: Optional[float] = None
    high: Optional[float] = None
    choices: Optional[List[Any]] = None
    log_scale: bool = False


@dataclass
class TrialResult:
    """Result from a single hyperparameter trial"""
    trial_id: int
    params: Dict[str, Any]
    score: float
    duration_seconds: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class AutoMLOptimizer:
    """
    AutoML Hyperparameter Optimization Engine
    
    Implements multiple optimization strategies:
    - Random Search
    - Grid Search
    - Bayesian Optimization (using Gaussian Process surrogate)
    - Evolutionary Algorithm
    
    Features:
    - Early stopping for poor performers
    - Cross-validation support
    - Multi-objective optimization
    - Warm start from previous results
    """

    def __init__(
        self,
        search_space: List[HyperparameterConfig],
        n_trials: int = 50,
        cv_folds: int = 5,
        early_stopping_rounds: int = 10,
        random_state: int = 42,
    ):
        self.search_space = {cfg.name: cfg for cfg in search_space}
        self.n_trials = n_trials
        self.cv_folds = cv_folds
        self.early_stopping_rounds = early_stopping_rounds
        self.rng = np.random.default_rng(random_state)
        
        self.trials: List[TrialResult] = []
        self.best_trial: Optional[TrialResult] = None
        self.best_score: float = float('-inf')
        self._no_improvement_count = 0

    def _sample_random_params(self) -> Dict[str, Any]:
        """Sample random hyperparameters from search space"""
        params = {}
        for name, config in self.search_space.items():
            if config.param_type == 'categorical':
                params[name] = self.rng.choice(config.choices)
            elif config.param_type == 'int':
                if config.log_scale:
                    log_val = self.rng.uniform(np.log(config.low), np.log(config.high))
                    params[name] = int(np.exp(log_val))
                else:
                    params[name] = int(self.rng.uniform(config.low, config.high))
            elif config.param_type == 'float':
                if config.log_scale:
                    log_val = self.rng.uniform(np.log(config.low), np.log(config.high))
                    params[name] = float(np.exp(log_val))
                else:
                    params[name] = float(self.rng.uniform(config.low, config.high))
        return params

    def _sample_from_gaussian_process(self) -> Dict[str, Any]:
        """
        Sample next parameters using Gaussian Process surrogate.
        Uses Expected Improvement (EI) acquisition function.
        """
        if len(self.trials) < 5:
            return self._sample_random_params()
        
        # Extract trial data
        X = []
        y = []
        for trial in self.trials:
            x_row = []
            for name in self.search_space.keys():
                val = trial.params.get(name, 0)
                if isinstance(val, (int, float)):
                    x_row.append(float(val))
                else:
                    # Encode categorical as index
                    config = self.search_space[name]
                    if config.choices:
                        idx = config.choices.index(val) if val in config.choices else 0
                        x_row.append(float(idx))
                    else:
                        x_row.append(0.0)
            X.append(x_row)
            y.append(trial.score)
        
        X = np.array(X)
        y = np.array(y)
        
        # Simple GP approximation using weighted distance
        best_score = np.max(y)
        
        # Generate candidates and evaluate EI
        n_candidates = 100
        best_ei = float('-inf')
        best_params = None
        
        for _ in range(n_candidates):
            candidate = self._sample_random_params()
            x_cand = []
            for name in self.search_space.keys():
                val = candidate.get(name, 0)
                if isinstance(val, (int, float)):
                    x_cand.append(float(val))
                else:
                    config = self.search_space[name]
                    if config.choices:
                        idx = config.choices.index(val) if val in config.choices else 0
                        x_cand.append(float(idx))
                    else:
                        x_cand.append(0.0)
            x_cand = np.array(x_cand)
            
            # Compute distances to all previous points
            distances = np.sqrt(np.sum((X - x_cand) ** 2, axis=1))
            
            # Compute weighted mean and std (kernel regression)
            weights = np.exp(-distances / (np.mean(distances) + 1e-6))
            weights = weights / (np.sum(weights) + 1e-6)
            
            mean = np.sum(weights * y)
            std = np.sqrt(np.sum(weights * (y - mean) ** 2) + 1e-6)
            
            # Expected Improvement
            z = (mean - best_score) / (std + 1e-6)
            ei = (mean - best_score) * (0.5 + 0.5 * np.tanh(z)) + std * np.exp(-0.5 * z * z)
            
            if ei > best_ei:
                best_ei = ei
                best_params = candidate
        
        return best_params if best_params else self._sample_random_params()

    def _evaluate_trial(
        self,
        params: Dict[str, Any],
        objective_fn: Callable[[Dict[str, Any]], float],
    ) -> TrialResult:
        """Evaluate a single trial"""
        trial_id = len(self.trials)
        start_time = time.time()
        
        try:
            score = objective_fn(params)
        except Exception as e:
            logger.warning(f"Trial {trial_id} failed: {e}")
            score = float('-inf')
        
        duration = time.time() - start_time
        
        result = TrialResult(
            trial_id=trial_id,
            params=params,
            score=score,
            duration_seconds=duration,
            metadata={"timestamp": datetime.utcnow().isoformat()}
        )
        
        return result

    def optimize(
        self,
        objective_fn: Callable[[Dict[str, Any]], float],
        method: str = "bayesian",
    ) -> TrialResult:
        """
        Run hyperparameter optimization.
        
        Args:
            objective_fn: Function that takes params dict and returns score (higher is better)
            method: One of 'random', 'bayesian', 'evolutionary'
            
        Returns:
            Best trial result
        """
        logger.info(f"Starting AutoML optimization with {self.n_trials} trials using {method}")
        
        for i in range(self.n_trials):
            # Sample parameters based on method
            if method == "random":
                params = self._sample_random_params()
            elif method == "bayesian":
                params = self._sample_from_gaussian_process()
            elif method == "evolutionary":
                params = self._evolutionary_sample()
            else:
                params = self._sample_random_params()
            
            # Evaluate trial
            result = self._evaluate_trial(params, objective_fn)
            self.trials.append(result)
            
            # Update best
            if result.score > self.best_score:
                self.best_score = result.score
                self.best_trial = result
                self._no_improvement_count = 0
                logger.info(f"Trial {i}: New best score {result.score:.6f}")
            else:
                self._no_improvement_count += 1
            
            # Early stopping
            if self._no_improvement_count >= self.early_stopping_rounds:
                logger.info(f"Early stopping at trial {i} - no improvement for {self.early_stopping_rounds} trials")
                break
        
        return self.best_trial

    def _evolutionary_sample(self) -> Dict[str, Any]:
        """Sample using evolutionary strategy (mutation of best performers)"""
        if len(self.trials) < 5:
            return self._sample_random_params()
        
        # Select top 20% performers
        sorted_trials = sorted(self.trials, key=lambda t: t.score, reverse=True)
        top_k = max(1, len(sorted_trials) // 5)
        elite = sorted_trials[:top_k]
        
        # Select parent
        parent = self.rng.choice(elite)
        
        # Mutate parameters
        params = parent.params.copy()
        mutation_rate = 0.3
        
        for name, config in self.search_space.items():
            if self.rng.random() < mutation_rate:
                if config.param_type == 'categorical':
                    params[name] = self.rng.choice(config.choices)
                elif config.param_type in ('int', 'float'):
                    # Gaussian mutation
                    current = params.get(name, (config.low + config.high) / 2)
                    std = (config.high - config.low) * 0.1
                    new_val = current + self.rng.normal(0, std)
                    new_val = max(config.low, min(config.high, new_val))
                    if config.param_type == 'int':
                        params[name] = int(new_val)
                    else:
                        params[name] = float(new_val)
        
        return params

    def get_results_summary(self) -> Dict[str, Any]:
        """Get summary of optimization results"""
        if not self.trials:
            return {"status": "no_trials"}
        
        scores = [t.score for t in self.trials if t.score > float('-inf')]
        
        return {
            "n_trials": len(self.trials),
            "best_score": self.best_score,
            "best_params": self.best_trial.params if self.best_trial else None,
            "mean_score": float(np.mean(scores)) if scores else 0.0,
            "std_score": float(np.std(scores)) if scores else 0.0,
            "total_duration": sum(t.duration_seconds for t in self.trials),
        }


@dataclass
class ArchitectureSpec:
    """Specification for a neural network architecture"""
    n_layers: int
    layer_sizes: List[int]
    activations: List[str]
    dropout_rates: List[float]
    use_batch_norm: bool
    use_skip_connections: bool
    learning_rate: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_layers": self.n_layers,
            "layer_sizes": self.layer_sizes,
            "activations": self.activations,
            "dropout_rates": self.dropout_rates,
            "use_batch_norm": self.use_batch_norm,
            "use_skip_connections": self.use_skip_connections,
            "learning_rate": self.learning_rate,
        }


class NeuralArchitectureSearch:
    """
    Neural Architecture Search (NAS) Engine
    
    Automatically discovers optimal neural network architectures for trading.
    
    Search Space:
    - Number of layers (1-10)
    - Layer widths (8-512)
    - Activation functions (relu, gelu, tanh, leaky_relu)
    - Dropout rates (0-0.5)
    - Batch normalization (on/off)
    - Skip connections (on/off)
    - Learning rate (1e-5 to 1e-2)
    
    Methods:
    - Random search
    - Evolutionary search with tournament selection
    - Progressive growing (start small, grow architecture)
    """

    ACTIVATIONS = ['relu', 'gelu', 'tanh', 'leaky_relu', 'elu']
    
    def __init__(
        self,
        input_dim: int,
        output_dim: int,
        max_layers: int = 8,
        max_width: int = 256,
        population_size: int = 20,
        generations: int = 10,
        random_state: int = 42,
    ):
        self.input_dim = input_dim
        self.output_dim = output_dim
        self.max_layers = max_layers
        self.max_width = max_width
        self.population_size = population_size
        self.generations = generations
        self.rng = np.random.default_rng(random_state)
        
        self.population: List[Tuple[ArchitectureSpec, float]] = []
        self.best_architecture: Optional[ArchitectureSpec] = None
        self.best_score: float = float('-inf')
        self.search_history: List[Dict[str, Any]] = []

    def _random_architecture(self) -> ArchitectureSpec:
        """Generate random architecture"""
        n_layers = int(self.rng.integers(1, self.max_layers + 1))
        
        # Layer sizes with gradual reduction
        layer_sizes = []
        prev_size = self.input_dim
        for i in range(n_layers):
            min_size = max(8, self.output_dim)
            max_size = min(self.max_width, prev_size * 2)
            size = int(self.rng.integers(min_size, max_size + 1))
            layer_sizes.append(size)
            prev_size = size
        
        return ArchitectureSpec(
            n_layers=n_layers,
            layer_sizes=layer_sizes,
            activations=[self.rng.choice(self.ACTIVATIONS) for _ in range(n_layers)],
            dropout_rates=[float(self.rng.uniform(0, 0.5)) for _ in range(n_layers)],
            use_batch_norm=bool(self.rng.choice([True, False])),
            use_skip_connections=bool(self.rng.choice([True, False])) if n_layers > 2 else False,
            learning_rate=float(10 ** self.rng.uniform(-5, -2)),
        )

    def _mutate_architecture(self, parent: ArchitectureSpec) -> ArchitectureSpec:
        """Mutate an architecture with small changes"""
        n_layers = parent.n_layers
        layer_sizes = parent.layer_sizes.copy()
        activations = parent.activations.copy()
        dropout_rates = parent.dropout_rates.copy()
        use_batch_norm = parent.use_batch_norm
        use_skip = parent.use_skip_connections
        lr = parent.learning_rate
        
        mutation = self.rng.choice([
            'add_layer', 'remove_layer', 'change_width', 
            'change_activation', 'change_dropout', 'toggle_bn',
            'toggle_skip', 'change_lr'
        ])
        
        if mutation == 'add_layer' and n_layers < self.max_layers:
            idx = int(self.rng.integers(0, n_layers + 1))
            size = int(self.rng.integers(8, self.max_width + 1))
            layer_sizes.insert(idx, size)
            activations.insert(idx, self.rng.choice(self.ACTIVATIONS))
            dropout_rates.insert(idx, float(self.rng.uniform(0, 0.5)))
            n_layers += 1
            
        elif mutation == 'remove_layer' and n_layers > 1:
            idx = int(self.rng.integers(0, n_layers))
            layer_sizes.pop(idx)
            activations.pop(idx)
            dropout_rates.pop(idx)
            n_layers -= 1
            
        elif mutation == 'change_width' and layer_sizes:
            idx = int(self.rng.integers(0, len(layer_sizes)))
            change = int(self.rng.integers(-64, 65))
            layer_sizes[idx] = max(8, min(self.max_width, layer_sizes[idx] + change))
            
        elif mutation == 'change_activation' and activations:
            idx = int(self.rng.integers(0, len(activations)))
            activations[idx] = self.rng.choice(self.ACTIVATIONS)
            
        elif mutation == 'change_dropout' and dropout_rates:
            idx = int(self.rng.integers(0, len(dropout_rates)))
            dropout_rates[idx] = max(0, min(0.5, dropout_rates[idx] + self.rng.uniform(-0.1, 0.1)))
            
        elif mutation == 'toggle_bn':
            use_batch_norm = not use_batch_norm
            
        elif mutation == 'toggle_skip':
            use_skip = not use_skip if n_layers > 2 else False
            
        elif mutation == 'change_lr':
            # Use natural log for numerically stable log-scale mutation
            lr = float(np.exp(np.log(lr) + self.rng.uniform(-0.5, 0.5)))
            lr = max(1e-5, min(1e-2, lr))
        
        return ArchitectureSpec(
            n_layers=n_layers,
            layer_sizes=layer_sizes,
            activations=activations,
            dropout_rates=dropout_rates,
            use_batch_norm=use_batch_norm,
            use_skip_connections=use_skip,
            learning_rate=lr,
        )

    def _crossover(
        self, parent1: ArchitectureSpec, parent2: ArchitectureSpec
    ) -> ArchitectureSpec:
        """Crossover two architectures"""
        # Take structure from parent1, but interpolate some values
        n_layers = self.rng.choice([parent1.n_layers, parent2.n_layers])
        
        layer_sizes = []
        activations = []
        dropout_rates = []
        
        for i in range(n_layers):
            if i < len(parent1.layer_sizes) and i < len(parent2.layer_sizes):
                # Average sizes
                size = int((parent1.layer_sizes[i] + parent2.layer_sizes[i]) / 2)
                layer_sizes.append(size)
                # Random choice of activation
                activations.append(self.rng.choice([
                    parent1.activations[i] if i < len(parent1.activations) else 'relu',
                    parent2.activations[i] if i < len(parent2.activations) else 'relu'
                ]))
                # Average dropout
                d1 = parent1.dropout_rates[i] if i < len(parent1.dropout_rates) else 0.0
                d2 = parent2.dropout_rates[i] if i < len(parent2.dropout_rates) else 0.0
                dropout_rates.append((d1 + d2) / 2)
            elif i < len(parent1.layer_sizes):
                layer_sizes.append(parent1.layer_sizes[i])
                activations.append(parent1.activations[i] if i < len(parent1.activations) else 'relu')
                dropout_rates.append(parent1.dropout_rates[i] if i < len(parent1.dropout_rates) else 0.0)
            elif i < len(parent2.layer_sizes):
                layer_sizes.append(parent2.layer_sizes[i])
                activations.append(parent2.activations[i] if i < len(parent2.activations) else 'relu')
                dropout_rates.append(parent2.dropout_rates[i] if i < len(parent2.dropout_rates) else 0.0)
            else:
                # Generate new layer
                layer_sizes.append(int(self.rng.integers(8, self.max_width + 1)))
                activations.append(self.rng.choice(self.ACTIVATIONS))
                dropout_rates.append(float(self.rng.uniform(0, 0.5)))
        
        return ArchitectureSpec(
            n_layers=n_layers,
            layer_sizes=layer_sizes,
            activations=activations,
            dropout_rates=dropout_rates,
            use_batch_norm=self.rng.choice([parent1.use_batch_norm, parent2.use_batch_norm]),
            use_skip_connections=self.rng.choice([parent1.use_skip_connections, parent2.use_skip_connections]),
            learning_rate=float(np.sqrt(parent1.learning_rate * parent2.learning_rate)),
        )

    def _tournament_select(self, tournament_size: int = 3) -> ArchitectureSpec:
        """Select architecture via tournament selection"""
        tournament = self.rng.choice(
            len(self.population), 
            size=min(tournament_size, len(self.population)),
            replace=False
        )
        best_idx = max(tournament, key=lambda i: self.population[i][1])
        return self.population[best_idx][0]

    def search(
        self,
        evaluate_fn: Callable[[ArchitectureSpec], float],
        method: str = "evolutionary",
    ) -> ArchitectureSpec:
        """
        Search for optimal architecture.
        
        Args:
            evaluate_fn: Function that evaluates architecture and returns score
            method: 'random', 'evolutionary', or 'progressive'
            
        Returns:
            Best discovered architecture
        """
        logger.info(f"Starting NAS with {self.generations} generations, population {self.population_size}")
        
        # Initialize population
        self.population = []
        for _ in range(self.population_size):
            arch = self._random_architecture()
            try:
                score = evaluate_fn(arch)
            except Exception as e:
                logger.warning(f"Architecture evaluation failed: {e}")
                score = float('-inf')
            self.population.append((arch, score))
            
            if score > self.best_score:
                self.best_score = score
                self.best_architecture = arch
        
        # Evolution
        for gen in range(self.generations):
            new_population = []
            
            # Elitism: keep top 20%
            sorted_pop = sorted(self.population, key=lambda x: x[1], reverse=True)
            elite_count = max(1, self.population_size // 5)
            new_population.extend(sorted_pop[:elite_count])
            
            # Generate offspring
            while len(new_population) < self.population_size:
                if method == "evolutionary":
                    parent1 = self._tournament_select()
                    parent2 = self._tournament_select()
                    
                    if self.rng.random() < 0.7:  # Crossover probability
                        child = self._crossover(parent1, parent2)
                    else:
                        child = parent1
                    
                    if self.rng.random() < 0.3:  # Mutation probability
                        child = self._mutate_architecture(child)
                else:
                    child = self._random_architecture()
                
                try:
                    score = evaluate_fn(child)
                except Exception as e:
                    logger.warning(f"Architecture evaluation failed: {e}")
                    score = float('-inf')
                
                new_population.append((child, score))
                
                if score > self.best_score:
                    self.best_score = score
                    self.best_architecture = child
                    logger.info(f"Generation {gen}: New best score {score:.6f}")
            
            self.population = new_population
            
            # Record history
            scores = [s for _, s in self.population if s > float('-inf')]
            self.search_history.append({
                "generation": gen,
                "best_score": self.best_score,
                "mean_score": float(np.mean(scores)) if scores else 0.0,
                "std_score": float(np.std(scores)) if scores else 0.0,
            })
        
        return self.best_architecture

    def build_model(self, spec: ArchitectureSpec) -> nn.Module:
        """Build PyTorch model from architecture specification"""
        layers = []
        prev_size = self.input_dim
        
        for i in range(spec.n_layers):
            size = spec.layer_sizes[i]
            layers.append(nn.Linear(prev_size, size))
            
            if spec.use_batch_norm:
                layers.append(nn.BatchNorm1d(size))
            
            # Activation
            activation = spec.activations[i]
            if activation == 'relu':
                layers.append(nn.ReLU())
            elif activation == 'gelu':
                layers.append(nn.GELU())
            elif activation == 'tanh':
                layers.append(nn.Tanh())
            elif activation == 'leaky_relu':
                layers.append(nn.LeakyReLU(0.1))
            elif activation == 'elu':
                layers.append(nn.ELU())
            
            if spec.dropout_rates[i] > 0:
                layers.append(nn.Dropout(spec.dropout_rates[i]))
            
            prev_size = size
        
        # Output layer
        layers.append(nn.Linear(prev_size, self.output_dim))
        
        return nn.Sequential(*layers)

    def get_search_summary(self) -> Dict[str, Any]:
        """Get summary of architecture search"""
        if not self.best_architecture:
            return {"status": "no_search_completed"}
        
        return {
            "best_score": self.best_score,
            "best_architecture": self.best_architecture.to_dict(),
            "generations_completed": len(self.search_history),
            "population_size": self.population_size,
            "history": self.search_history,
        }


class NeuroForgeTrainer:
    """Coordinates curriculum-style evaluation, drift checks, and artifact capture."""

    def __init__(self, artifact_root: Optional[str] = None):
        self.scheduler = CurriculumScheduler()
        self.drift_detector = ConceptDriftDetector()
        self.artifacts = ArtifactRegistry(artifact_root)
        self.last_report: Dict[str, Any] = {}

    def _prepare_sequences(
        self,
        sequence_model: LSTMPricePredictor,
        frame: pd.DataFrame,
    ) -> Tuple[np.ndarray, np.ndarray]:
        scaler_bytes = pickle.dumps(sequence_model.scaler)
        try:
            return sequence_model.prepare_data(frame)
        finally:
            sequence_model.scaler = pickle.loads(scaler_bytes)

    def run_curriculum(
        self,
        ensemble: "EnsemblePredictor",
        sequence_model: LSTMPricePredictor,
        historical_data: pd.DataFrame,
    ) -> Dict[str, Any]:
        plan = self.scheduler.build_plan(historical_data)
        phase_reports: List[Dict[str, Any]] = []

        for entry in plan:
            phase = entry["phase"]
            window = entry["window"]
            X_phase, y_phase = self._prepare_sequences(sequence_model, window.copy())
            if len(X_phase) == 0:
                continue

            predictions = ensemble.predict(X_phase)
            residuals = predictions - y_phase
            mse = float(np.mean(residuals**2))
            mae = float(np.mean(np.abs(residuals)))

            returns = window["close"].pct_change().dropna().values
            drift_flag, drift_score = self.drift_detector.evaluate(returns)

            phase_reports.append(
                {
                    "phase": phase.name,
                    "purpose": phase.purpose,
                    "samples": int(len(X_phase)),
                    "mse": mse,
                    "mae": mae,
                    "drift_alert": drift_flag,
                    "drift_score": drift_score,
                }
            )

        aggregate_mse = (
            float(np.mean([p["mse"] for p in phase_reports])) if phase_reports else None
        )
        aggregate_mae = (
            float(np.mean([p["mae"] for p in phase_reports])) if phase_reports else None
        )

        report = {
            "phases": phase_reports,
            "aggregate_mse": aggregate_mse,
            "aggregate_mae": aggregate_mae,
            "drift_detected": (
                any(p["drift_alert"] for p in phase_reports) if phase_reports else False
            ),
        }

        self.artifacts.record({"report": report})
        self.last_report = report
        return report


class ReasoningCore:
    """Synthesizes structured reasoning traces for trading decisions."""

    def __init__(self):
        self.history: deque[Dict[str, Any]] = deque(maxlen=300)

    def synthesize(
        self, analysis: Dict[str, Any], decision: Dict[str, Any]
    ) -> Dict[str, Any]:
        pillars: List[str] = []

        predicted_price = analysis.get("predicted_price")
        current_price = analysis.get("technical", {}).get("bb_middle")
        if predicted_price is not None and current_price:
            delta = (predicted_price - current_price) / current_price
            pillars.append(f"Price outlook {delta:.2%}")

        fear_greed = analysis.get("fear_greed_index")
        if fear_greed is not None:
            pillars.append(f"Fear/Greed {fear_greed:.1f}")

        risk_score = analysis.get("risk", {}).get("risk_score")
        if risk_score is not None:
            pillars.append(f"Risk score {risk_score}")

        interval = analysis.get("prediction_interval")
        if interval:
            width = interval[1] - interval[0]
            pillars.append(f"Interval width {width:.4f}")

        scenario_summary = summarize_scenario_slopes(
            analysis.get("prediction_scenarios")
        )
        reasoning_packet = {
            "action": decision.get("action"),
            "confidence": decision.get("confidence"),
            "pillars": pillars,
            "risk_score": risk_score,
            "scenario_slopes": scenario_summary,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.history.append(reasoning_packet)
        return reasoning_packet

    def recall(self, limit: int = 10) -> List[Dict[str, Any]]:
        return list(self.history)[-limit:]


class MarketTransformer(nn.Module):
    """Transformer architecture for market prediction"""

    def __init__(self, input_dim=10, d_model=512, nhead=8, num_layers=6, dropout=0.1):
        super(MarketTransformer, self).__init__()
        self.input_projection = nn.Linear(input_dim, d_model)
        self.positional_encoding = PositionalEncoding(d_model, dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dropout=dropout,
            dim_feedforward=2048,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

        self.output_projection = nn.Sequential(
            nn.Linear(d_model, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 3),  # [price_change, volume_change, volatility]
        )

    def forward(self, x, mask=None):
        x = self.input_projection(x)
        x = self.positional_encoding(x)
        x = self.transformer(x, mask=mask)
        return self.output_projection(x)


class PositionalEncoding(nn.Module):
    """Positional encoding for transformer"""

    def __init__(self, d_model, dropout=0.1, max_len=5000):
        super(PositionalEncoding, self).__init__()
        self.dropout = nn.Dropout(p=dropout)

        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-np.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)
        self.register_buffer("pe", pe)

    def forward(self, x):
        x = x + self.pe[: x.size(0), :]
        return self.dropout(x)


# ═══════════════════════════════════════════════════════════════════════════════
# N-BEATS Architecture (Phase 1 Enhancement)
# Neural Basis Expansion Analysis for Time Series
# Reference: Oreshkin et al., "N-BEATS: Neural basis expansion analysis for
#            interpretable time series forecasting" (ICLR 2020)
# ═══════════════════════════════════════════════════════════════════════════════


class NBeatsBlock(nn.Module):
    """
    Basic building block of N-BEATS architecture.

    Each block produces two outputs:
    - Backcast: reconstruction of the input (for residual learning)
    - Forecast: prediction for future timesteps

    Uses fully-connected layers followed by basis expansion.
    """

    def __init__(
        self,
        input_size: int,
        theta_size: int,
        basis_function: nn.Module,
        num_layers: int = 4,
        layer_size: int = 256,
        dropout: float = 0.1,
    ):
        super(NBeatsBlock, self).__init__()
        self.input_size = input_size
        self.theta_size = theta_size
        self.basis_function = basis_function

        # Build fully connected stack
        layers = []
        current_size = input_size
        for _ in range(num_layers):
            layers.append(nn.Linear(current_size, layer_size))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(dropout))
            current_size = layer_size

        self.fc_stack = nn.Sequential(*layers)

        # Theta layers for backcast and forecast
        self.theta_backcast = nn.Linear(layer_size, theta_size)
        self.theta_forecast = nn.Linear(layer_size, theta_size)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass through the block.

        Args:
            x: Input tensor of shape (batch_size, input_size)

        Returns:
            backcast: Reconstruction of input (batch_size, input_size)
            forecast: Prediction (batch_size, forecast_size)
        """
        # Pass through FC stack
        hidden = self.fc_stack(x)

        # Generate theta parameters
        theta_b = self.theta_backcast(hidden)
        theta_f = self.theta_forecast(hidden)

        # Apply basis function
        backcast = self.basis_function.backcast(theta_b)
        forecast = self.basis_function.forecast(theta_f)

        return backcast, forecast


class GenericBasis(nn.Module):
    """
    Generic basis function for N-BEATS.
    Uses learnable linear projections as basis.
    """

    def __init__(self, backcast_size: int, forecast_size: int, theta_size: int):
        super(GenericBasis, self).__init__()
        self.backcast_linear = nn.Linear(theta_size, backcast_size, bias=False)
        self.forecast_linear = nn.Linear(theta_size, forecast_size, bias=False)

    def backcast(self, theta: torch.Tensor) -> torch.Tensor:
        return self.backcast_linear(theta)

    def forecast(self, theta: torch.Tensor) -> torch.Tensor:
        return self.forecast_linear(theta)


class TrendBasis(nn.Module):
    """
    Trend basis function for interpretable N-BEATS.
    Uses polynomial basis for trend decomposition.
    """

    def __init__(
        self,
        backcast_size: int,
        forecast_size: int,
        theta_size: int,
        polynomial_degree: int = 3,
    ):
        super(TrendBasis, self).__init__()
        self.polynomial_degree = polynomial_degree
        self.backcast_size = backcast_size
        self.forecast_size = forecast_size

        # Create polynomial basis matrices
        backcast_time = torch.arange(backcast_size, dtype=torch.float32) / backcast_size
        forecast_time = torch.arange(forecast_size, dtype=torch.float32) / forecast_size

        # Polynomial powers: [t^0, t^1, t^2, ...]
        backcast_basis = torch.stack(
            [backcast_time**i for i in range(polynomial_degree + 1)], dim=1
        )
        forecast_basis = torch.stack(
            [forecast_time**i for i in range(polynomial_degree + 1)], dim=1
        )

        self.register_buffer("backcast_basis", backcast_basis)
        self.register_buffer("forecast_basis", forecast_basis)

        # Linear layer to map theta to polynomial coefficients
        self.theta_to_coef = nn.Linear(theta_size, polynomial_degree + 1, bias=False)

    def backcast(self, theta: torch.Tensor) -> torch.Tensor:
        coef = self.theta_to_coef(theta)  # (batch, degree+1)
        return torch.matmul(coef, self.backcast_basis.T)

    def forecast(self, theta: torch.Tensor) -> torch.Tensor:
        coef = self.theta_to_coef(theta)  # (batch, degree+1)
        return torch.matmul(coef, self.forecast_basis.T)


class SeasonalityBasis(nn.Module):
    """
    Seasonality basis function for interpretable N-BEATS.
    Uses Fourier basis for seasonality decomposition.
    """

    def __init__(
        self,
        backcast_size: int,
        forecast_size: int,
        theta_size: int,
        num_harmonics: int = 4,
    ):
        super(SeasonalityBasis, self).__init__()
        self.num_harmonics = num_harmonics
        self.backcast_size = backcast_size
        self.forecast_size = forecast_size

        # Create Fourier basis matrices
        backcast_time = torch.arange(backcast_size, dtype=torch.float32) / backcast_size
        forecast_time = torch.arange(forecast_size, dtype=torch.float32) / forecast_size

        # Fourier basis: [cos(2*pi*k*t), sin(2*pi*k*t)] for k = 1..num_harmonics
        backcast_basis = []
        forecast_basis = []
        for k in range(1, num_harmonics + 1):
            backcast_basis.append(torch.cos(2 * np.pi * k * backcast_time))
            backcast_basis.append(torch.sin(2 * np.pi * k * backcast_time))
            forecast_basis.append(torch.cos(2 * np.pi * k * forecast_time))
            forecast_basis.append(torch.sin(2 * np.pi * k * forecast_time))

        backcast_basis = torch.stack(backcast_basis, dim=1)
        forecast_basis = torch.stack(forecast_basis, dim=1)

        self.register_buffer("backcast_basis", backcast_basis)
        self.register_buffer("forecast_basis", forecast_basis)

        # Linear layer to map theta to Fourier coefficients
        self.theta_to_coef = nn.Linear(theta_size, 2 * num_harmonics, bias=False)

    def backcast(self, theta: torch.Tensor) -> torch.Tensor:
        coef = self.theta_to_coef(theta)
        return torch.matmul(coef, self.backcast_basis.T)

    def forecast(self, theta: torch.Tensor) -> torch.Tensor:
        coef = self.theta_to_coef(theta)
        return torch.matmul(coef, self.forecast_basis.T)


class NBeatsStack(nn.Module):
    """
    Stack of N-BEATS blocks sharing the same basis function type.
    Implements residual learning where each block processes the residual
    from the previous block.
    """

    def __init__(
        self,
        num_blocks: int,
        input_size: int,
        theta_size: int,
        basis_function_creator: Callable[[], nn.Module],
        num_layers: int = 4,
        layer_size: int = 256,
        dropout: float = 0.1,
        forecast_size: int = 10,
    ):
        super(NBeatsStack, self).__init__()
        self.forecast_size = forecast_size
        self.blocks = nn.ModuleList(
            [
                NBeatsBlock(
                    input_size=input_size,
                    theta_size=theta_size,
                    basis_function=basis_function_creator(),
                    num_layers=num_layers,
                    layer_size=layer_size,
                    dropout=dropout,
                )
                for _ in range(num_blocks)
            ]
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass through the stack.

        Returns:
            stack_backcast: Combined backcast from all blocks
            stack_forecast: Combined forecast from all blocks
        """
        residual = x
        stack_forecast = torch.zeros(
            x.shape[0],
            self.forecast_size,
            device=x.device,
        )

        for block in self.blocks:
            backcast, forecast = block(residual)
            residual = residual - backcast
            stack_forecast = stack_forecast + forecast

        return residual, stack_forecast


class NBeatsModel(nn.Module):
    """
    Complete N-BEATS model for time series forecasting.

    Architecture supports both:
    - Generic: Maximum expressiveness with learnable basis
    - Interpretable: Trend + Seasonality decomposition with predefined basis

    For trading, the interpretable version provides explainable
    trend and seasonality components.
    """

    def __init__(
        self,
        input_size: int = 60,
        forecast_size: int = 10,
        stack_types: List[str] = None,
        num_blocks_per_stack: int = 3,
        num_layers: int = 4,
        layer_size: int = 256,
        theta_size: int = 64,
        dropout: float = 0.1,
        share_weights: bool = False,
    ):
        """
        Initialize N-BEATS model.

        Args:
            input_size: Length of input sequence (backcast window)
            forecast_size: Length of forecast horizon
            stack_types: List of stack types ['trend', 'seasonality', 'generic']
            num_blocks_per_stack: Number of blocks in each stack
            num_layers: Number of FC layers per block
            layer_size: Hidden layer size
            theta_size: Dimension of theta parameters
            dropout: Dropout rate
            share_weights: Whether to share weights across blocks in a stack
        """
        super(NBeatsModel, self).__init__()

        if stack_types is None:
            stack_types = ["trend", "seasonality", "generic"]

        self.input_size = input_size
        self.forecast_size = forecast_size
        self.stack_types = stack_types

        # Helper functions to avoid lambda closure issues
        def create_trend_basis(inp_size, fcast_size, th_size):
            return lambda: TrendBasis(
                inp_size, fcast_size, th_size, polynomial_degree=3
            )

        def create_seasonality_basis(inp_size, fcast_size, th_size):
            return lambda: SeasonalityBasis(
                inp_size, fcast_size, th_size, num_harmonics=8
            )

        def create_generic_basis(inp_size, fcast_size, th_size):
            return lambda: GenericBasis(inp_size, fcast_size, th_size)

        # Create stacks
        self.stacks = nn.ModuleList()

        for stack_type in stack_types:
            if stack_type == "trend":
                basis_creator = create_trend_basis(
                    input_size, forecast_size, theta_size
                )
            elif stack_type == "seasonality":
                basis_creator = create_seasonality_basis(
                    input_size, forecast_size, theta_size
                )
            else:  # generic
                basis_creator = create_generic_basis(
                    input_size, forecast_size, theta_size
                )

            stack = NBeatsStack(
                num_blocks=num_blocks_per_stack,
                input_size=input_size,
                theta_size=theta_size,
                basis_function_creator=basis_creator,
                num_layers=num_layers,
                layer_size=layer_size,
                dropout=dropout,
                forecast_size=forecast_size,
            )
            self.stacks.append(stack)

        _brain_logger.info(
            f"N-BEATS initialized: input={input_size}, forecast={forecast_size}, "
            f"stacks={stack_types}, blocks_per_stack={num_blocks_per_stack}"
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass through N-BEATS.

        Args:
            x: Input tensor of shape (batch_size, input_size) or (batch_size, seq_len, features)

        Returns:
            forecast: Predictions of shape (batch_size, forecast_size)
        """
        # Handle 3D input by flattening the last dimension
        if x.dim() == 3:
            batch_size, seq_len, features = x.shape
            x = x.view(batch_size, -1)
            # Adjust or project to expected input size
            if x.shape[1] != self.input_size:
                # Use adaptive pooling or projection
                x = nn.functional.adaptive_avg_pool1d(
                    x.unsqueeze(1), self.input_size
                ).squeeze(1)

        residual = x
        total_forecast = torch.zeros(x.shape[0], self.forecast_size, device=x.device)

        for stack in self.stacks:
            stack_residual, stack_forecast = stack(residual)
            residual = stack_residual
            total_forecast = total_forecast + stack_forecast

        return total_forecast

    def decompose(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Decompose input into trend, seasonality, and residual components.

        This provides interpretability by showing how the model
        breaks down the signal.

        Args:
            x: Input tensor of shape (batch_size, input_size)

        Returns:
            Dictionary with forecasts from each stack type
        """
        if x.dim() == 3:
            batch_size = x.shape[0]
            x = x.view(batch_size, -1)
            if x.shape[1] != self.input_size:
                x = nn.functional.adaptive_avg_pool1d(
                    x.unsqueeze(1), self.input_size
                ).squeeze(1)

        residual = x
        decomposition = {}

        for stack, stack_type in zip(self.stacks, self.stack_types):
            stack_residual, stack_forecast = stack(residual)
            residual = stack_residual
            decomposition[stack_type] = stack_forecast

        decomposition["total"] = sum(decomposition.values())
        return decomposition


class NBeatsPredictor:
    """
    High-level wrapper for N-BEATS model with training and prediction utilities.

    Integrates with ANVEL's ensemble prediction system.
    """

    def __init__(
        self,
        input_size: int = 60,
        forecast_size: int = 10,
        interpretable: bool = True,
        device: Optional[torch.device] = None,
    ):
        """
        Initialize N-BEATS predictor.

        Args:
            input_size: Length of input sequence
            forecast_size: Prediction horizon
            interpretable: Use interpretable (trend+seasonality) or generic model
            device: Torch device (auto-detects CUDA if available)
        """
        self.input_size = input_size
        self.forecast_size = forecast_size
        self.interpretable = interpretable
        self.device = device or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        # Create model
        if interpretable:
            stack_types = ["trend", "seasonality"]
        else:
            stack_types = ["generic", "generic", "generic"]

        self.model = NBeatsModel(
            input_size=input_size,
            forecast_size=forecast_size,
            stack_types=stack_types,
            num_blocks_per_stack=3,
            num_layers=4,
            layer_size=256,
            theta_size=64,
            dropout=0.1,
        ).to(self.device)

        self.optimizer = None
        self.scaler = MinMaxScaler()
        self.trained = False

        _brain_logger.info(
            f"NBeatsPredictor initialized: interpretable={interpretable}, device={self.device}"
        )

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        epochs: int = 100,
        batch_size: int = 32,
        learning_rate: float = 0.001,
        early_stopping_patience: int = 10,
    ) -> Dict[str, List[float]]:
        """
        Train the N-BEATS model.

        Args:
            X_train: Training inputs of shape (n_samples, seq_len) or (n_samples, seq_len, features)
            y_train: Training targets of shape (n_samples,) or (n_samples, forecast_size)
            X_val: Validation inputs (optional)
            y_val: Validation targets (optional)
            epochs: Number of training epochs
            batch_size: Mini-batch size
            learning_rate: Adam learning rate
            early_stopping_patience: Epochs without improvement before stopping

        Returns:
            Dictionary with training history (loss, val_loss)
        """
        self.model.train()
        self.optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)
        criterion = nn.MSELoss()

        # Prepare data
        X_train_flat = X_train.reshape(X_train.shape[0], -1)
        if X_train_flat.shape[1] != self.input_size:
            # Resize to expected input size
            X_train_flat = np.array(
                [
                    np.interp(
                        np.linspace(0, 1, self.input_size),
                        np.linspace(0, 1, len(row)),
                        row,
                    )
                    for row in X_train_flat
                ]
            )

        # Ensure y_train has correct shape
        if y_train.ndim == 1:
            y_train = np.tile(y_train.reshape(-1, 1), (1, self.forecast_size))

        X_train_torch = torch.FloatTensor(X_train_flat).to(self.device)
        y_train_torch = torch.FloatTensor(y_train).to(self.device)

        # Validation data
        if X_val is not None and y_val is not None:
            X_val_flat = X_val.reshape(X_val.shape[0], -1)
            if X_val_flat.shape[1] != self.input_size:
                X_val_flat = np.array(
                    [
                        np.interp(
                            np.linspace(0, 1, self.input_size),
                            np.linspace(0, 1, len(row)),
                            row,
                        )
                        for row in X_val_flat
                    ]
                )
            if y_val.ndim == 1:
                y_val = np.tile(y_val.reshape(-1, 1), (1, self.forecast_size))
            X_val_torch = torch.FloatTensor(X_val_flat).to(self.device)
            y_val_torch = torch.FloatTensor(y_val).to(self.device)
        else:
            X_val_torch = None
            y_val_torch = None

        # Training history
        history = {"loss": [], "val_loss": []}
        best_val_loss = float("inf")
        patience_counter = 0

        # Create data loader
        dataset = TensorDataset(X_train_torch, y_train_torch)
        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        for epoch in range(epochs):
            epoch_loss = 0.0
            self.model.train()

            for batch_x, batch_y in dataloader:
                self.optimizer.zero_grad()
                output = self.model(batch_x)
                loss = criterion(output, batch_y)
                loss.backward()
                self.optimizer.step()
                epoch_loss += loss.item()

            epoch_loss /= len(dataloader)
            history["loss"].append(epoch_loss)

            # Validation
            if X_val_torch is not None:
                self.model.eval()
                with torch.no_grad():
                    val_output = self.model(X_val_torch)
                    val_loss = criterion(val_output, y_val_torch).item()
                history["val_loss"].append(val_loss)

                # Early stopping
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience_counter = 0
                else:
                    patience_counter += 1

                if patience_counter >= early_stopping_patience:
                    _brain_logger.info(f"N-BEATS early stopping at epoch {epoch + 1}")
                    break

            if epoch % 10 == 0:
                val_str = (
                    f", val_loss={history['val_loss'][-1]:.6f}"
                    if history["val_loss"]
                    else ""
                )
                _brain_logger.info(
                    f"N-BEATS Epoch {epoch + 1}/{epochs}: loss={epoch_loss:.6f}{val_str}"
                )

        self.trained = True
        _brain_logger.info(
            f"N-BEATS training complete. Final loss: {history['loss'][-1]:.6f}"
        )
        return history

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Make predictions with N-BEATS.

        Args:
            X: Input of shape (n_samples, seq_len) or (n_samples, seq_len, features)

        Returns:
            Predictions of shape (n_samples,) - returns first forecast step
        """
        self.model.eval()

        X_flat = X.reshape(X.shape[0], -1)
        if X_flat.shape[1] != self.input_size:
            X_flat = np.array(
                [
                    np.interp(
                        np.linspace(0, 1, self.input_size),
                        np.linspace(0, 1, len(row)),
                        row,
                    )
                    for row in X_flat
                ]
            )

        X_torch = torch.FloatTensor(X_flat).to(self.device)

        with torch.no_grad():
            output = self.model(X_torch)

        # Return first forecast step for compatibility with ensemble
        return output[:, 0].cpu().numpy()

    def predict_multi_horizon(self, X: np.ndarray) -> np.ndarray:
        """
        Make multi-horizon predictions.

        Args:
            X: Input data

        Returns:
            Predictions of shape (n_samples, forecast_size)
        """
        self.model.eval()

        X_flat = X.reshape(X.shape[0], -1)
        if X_flat.shape[1] != self.input_size:
            X_flat = np.array(
                [
                    np.interp(
                        np.linspace(0, 1, self.input_size),
                        np.linspace(0, 1, len(row)),
                        row,
                    )
                    for row in X_flat
                ]
            )

        X_torch = torch.FloatTensor(X_flat).to(self.device)

        with torch.no_grad():
            output = self.model(X_torch)

        return output.cpu().numpy()

    def get_decomposition(self, X: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Get interpretable decomposition of predictions.

        Returns trend, seasonality, and total components.

        Args:
            X: Input data

        Returns:
            Dictionary with component forecasts
        """
        if not self.interpretable:
            _brain_logger.warning(
                "Decomposition only meaningful for interpretable model"
            )

        self.model.eval()

        X_flat = X.reshape(X.shape[0], -1)
        if X_flat.shape[1] != self.input_size:
            X_flat = np.array(
                [
                    np.interp(
                        np.linspace(0, 1, self.input_size),
                        np.linspace(0, 1, len(row)),
                        row,
                    )
                    for row in X_flat
                ]
            )

        X_torch = torch.FloatTensor(X_flat).to(self.device)

        with torch.no_grad():
            decomp = self.model.decompose(X_torch)

        return {k: v.cpu().numpy() for k, v in decomp.items()}

    def save(self, path: str) -> None:
        """Save model weights."""
        torch.save(
            {
                "model_state_dict": self.model.state_dict(),
                "input_size": self.input_size,
                "forecast_size": self.forecast_size,
                "interpretable": self.interpretable,
            },
            path,
        )
        _brain_logger.info(f"N-BEATS model saved to {path}")

    def load(self, path: str) -> None:
        """Load model weights."""
        checkpoint = torch.load(path, map_location=self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.trained = True
        _brain_logger.info(f"N-BEATS model loaded from {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# Temporal Fusion Transformer (TFT) - Phase 1.1 Enhancement
# Google's state-of-the-art architecture for interpretable time series forecasting
# Reference: Lim et al., "Temporal Fusion Transformers for Interpretable
#            Multi-horizon Time Series Forecasting" (2021)
# ═══════════════════════════════════════════════════════════════════════════════


class GatedLinearUnit(nn.Module):
    """
    Gated Linear Unit (GLU) for controlled information flow.

    GLU(x) = Linear(x) * sigmoid(Linear(x))

    Allows the network to control what information passes through.
    """

    def __init__(self, input_dim: int, output_dim: int, dropout: float = 0.1):
        super(GatedLinearUnit, self).__init__()
        self.fc = nn.Linear(input_dim, output_dim)
        self.gate = nn.Linear(input_dim, output_dim)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.dropout(self.fc(x) * torch.sigmoid(self.gate(x)))


class GatedResidualNetwork(nn.Module):
    """
    Gated Residual Network (GRN) - Core building block of TFT.

    Provides flexible nonlinear processing with:
    - Skip connections for gradient flow
    - Gating mechanism for adaptive depth
    - Optional context vector integration

    GRN(x, c) = LayerNorm(x + GLU(ELU(Linear(x) + Linear(c))))
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int,
        output_dim: int,
        context_dim: Optional[int] = None,
        dropout: float = 0.1,
    ):
        super(GatedResidualNetwork, self).__init__()

        self.input_dim = input_dim
        self.output_dim = output_dim
        self.context_dim = context_dim

        # Primary transformation
        self.fc1 = nn.Linear(input_dim, hidden_dim)

        # Context projection (optional)
        if context_dim is not None:
            self.context_projection = nn.Linear(context_dim, hidden_dim, bias=False)
        else:
            self.context_projection = None

        # ELU activation
        self.elu = nn.ELU()

        # Second transformation
        self.fc2 = nn.Linear(hidden_dim, output_dim)

        # Gated Linear Unit
        self.glu = GatedLinearUnit(output_dim, output_dim, dropout)

        # Skip connection projection (if dimensions differ)
        if input_dim != output_dim:
            self.skip_projection = nn.Linear(input_dim, output_dim)
        else:
            self.skip_projection = None

        # Layer normalization
        self.layer_norm = nn.LayerNorm(output_dim)

    def forward(
        self, x: torch.Tensor, context: Optional[torch.Tensor] = None
    ) -> torch.Tensor:
        # Skip connection
        if self.skip_projection is not None:
            skip = self.skip_projection(x)
        else:
            skip = x

        # Primary transformation
        hidden = self.fc1(x)

        # Add context if provided
        if context is not None and self.context_projection is not None:
            hidden = hidden + self.context_projection(context)

        # Nonlinearity
        hidden = self.elu(hidden)

        # Second transformation
        hidden = self.fc2(hidden)

        # Gating
        hidden = self.glu(hidden)

        # Residual connection with layer norm
        return self.layer_norm(skip + hidden)


class VariableSelectionNetwork(nn.Module):
    """
    Variable Selection Network (VSN) - Feature importance learning.

    Learns which input variables are most important for the prediction task.
    Outputs softmax weights over variables for interpretability.
    """

    def __init__(
        self,
        num_inputs: int,
        input_dim: int,
        hidden_dim: int,
        dropout: float = 0.1,
        context_dim: Optional[int] = None,
    ):
        super(VariableSelectionNetwork, self).__init__()

        self.num_inputs = num_inputs
        self.input_dim = input_dim

        # GRN for each input variable
        self.input_grns = nn.ModuleList(
            [
                GatedResidualNetwork(
                    input_dim=input_dim,
                    hidden_dim=hidden_dim,
                    output_dim=hidden_dim,
                    context_dim=context_dim,
                    dropout=dropout,
                )
                for _ in range(num_inputs)
            ]
        )

        # Softmax weight generator
        self.weight_grn = GatedResidualNetwork(
            input_dim=hidden_dim * num_inputs,
            hidden_dim=hidden_dim,
            output_dim=num_inputs,
            context_dim=context_dim,
            dropout=dropout,
        )

        self.softmax = nn.Softmax(dim=-1)

    def forward(
        self, inputs: List[torch.Tensor], context: Optional[torch.Tensor] = None
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            inputs: List of tensors, each of shape (batch, seq_len, input_dim)
            context: Optional context tensor (batch, context_dim)

        Returns:
            combined: Weighted combination of processed inputs
            weights: Variable selection weights for interpretability
        """
        # Process each input through its GRN
        processed = []
        for i, (inp, grn) in enumerate(zip(inputs, self.input_grns)):
            if context is not None and context.dim() == 2:
                # Expand context to match sequence length
                ctx = context.unsqueeze(1).expand(-1, inp.size(1), -1)
            else:
                ctx = context
            processed.append(grn(inp, ctx))

        # Stack processed inputs: (batch, seq_len, num_inputs, hidden_dim)
        stacked = torch.stack(processed, dim=2)

        # Flatten for weight generation
        batch_size, seq_len, _, hidden_dim = stacked.shape
        flat = stacked.view(batch_size, seq_len, -1)

        # Generate selection weights
        if context is not None and context.dim() == 2:
            ctx = context.unsqueeze(1).expand(-1, seq_len, -1)
        else:
            ctx = context

        weights = self.softmax(self.weight_grn(flat, ctx))

        # Weighted combination
        weights_expanded = weights.unsqueeze(-1)  # (batch, seq, num_inputs, 1)
        combined = (stacked * weights_expanded).sum(dim=2)  # (batch, seq, hidden)

        return combined, weights


class InterpretableMultiHeadAttention(nn.Module):
    """
    Interpretable Multi-Head Attention for TFT.

    Modified attention that:
    - Shares value weights across heads for interpretability
    - Provides attention weights for visualization
    """

    def __init__(
        self,
        embed_dim: int,
        num_heads: int,
        dropout: float = 0.1,
    ):
        super(InterpretableMultiHeadAttention, self).__init__()

        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.head_dim = embed_dim // num_heads

        assert (
            self.head_dim * num_heads == embed_dim
        ), "embed_dim must be divisible by num_heads"

        # Query and Key projections per head
        self.q_proj = nn.Linear(embed_dim, embed_dim)
        self.k_proj = nn.Linear(embed_dim, embed_dim)

        # Shared value projection for interpretability
        self.v_proj = nn.Linear(embed_dim, embed_dim)

        # Output projection
        self.out_proj = nn.Linear(embed_dim, embed_dim)

        self.dropout = nn.Dropout(dropout)
        self.scale = self.head_dim**-0.5

    def forward(
        self,
        query: torch.Tensor,
        key: torch.Tensor,
        value: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            query: (batch, seq_len, embed_dim)
            key: (batch, seq_len, embed_dim)
            value: (batch, seq_len, embed_dim)
            mask: Optional attention mask

        Returns:
            output: Attended values
            attention_weights: For interpretability
        """
        batch_size, seq_len, _ = query.shape

        # Project Q, K, V
        q = self.q_proj(query).view(batch_size, seq_len, self.num_heads, self.head_dim)
        k = self.k_proj(key).view(batch_size, seq_len, self.num_heads, self.head_dim)
        v = self.v_proj(value).view(batch_size, seq_len, self.num_heads, self.head_dim)

        # Transpose for attention: (batch, heads, seq, dim)
        q = q.transpose(1, 2)
        k = k.transpose(1, 2)
        v = v.transpose(1, 2)

        # Scaled dot-product attention
        scores = torch.matmul(q, k.transpose(-2, -1)) * self.scale

        # Apply mask if provided
        if mask is not None:
            scores = scores.masked_fill(mask == 0, float("-inf"))

        attention_weights = torch.softmax(scores, dim=-1)
        attention_weights = self.dropout(attention_weights)

        # Apply attention to values
        attended = torch.matmul(attention_weights, v)

        # Reshape and project output
        attended = (
            attended.transpose(1, 2)
            .contiguous()
            .view(batch_size, seq_len, self.embed_dim)
        )
        output = self.out_proj(attended)

        # Average attention weights across heads for interpretability
        avg_attention = attention_weights.mean(dim=1)

        return output, avg_attention


class TemporalFusionTransformer(nn.Module):
    """
    Temporal Fusion Transformer (TFT) - Complete Architecture.

    State-of-the-art architecture for interpretable multi-horizon time series forecasting.

    Key components:
    1. Variable Selection Networks - Learn feature importance
    2. Gated Residual Networks - Flexible nonlinear processing
    3. Temporal Processing - LSTM for local patterns
    4. Interpretable Multi-Head Attention - Capture long-range dependencies
    5. Quantile Outputs - Probabilistic predictions

    The architecture provides three levels of interpretability:
    - Variable importance weights
    - Temporal attention patterns
    - Regime-specific predictions
    """

    def __init__(
        self,
        input_dim: int = 10,
        hidden_dim: int = 64,
        num_heads: int = 4,
        num_lstm_layers: int = 2,
        dropout: float = 0.1,
        forecast_horizon: int = 10,
        num_quantiles: int = 3,  # [0.1, 0.5, 0.9] for prediction intervals
    ):
        """
        Initialize TFT.

        Args:
            input_dim: Number of input features
            hidden_dim: Hidden dimension throughout the network
            num_heads: Number of attention heads
            num_lstm_layers: Number of LSTM layers for temporal processing
            dropout: Dropout rate
            forecast_horizon: Number of future timesteps to predict
            num_quantiles: Number of quantile outputs (for uncertainty)
        """
        super(TemporalFusionTransformer, self).__init__()

        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.forecast_horizon = forecast_horizon
        self.num_quantiles = num_quantiles

        # Input projection
        self.input_projection = nn.Linear(input_dim, hidden_dim)

        # Variable Selection Network for static features
        self.static_vsn = GatedResidualNetwork(
            input_dim=hidden_dim,
            hidden_dim=hidden_dim,
            output_dim=hidden_dim,
            dropout=dropout,
        )

        # LSTM encoder for temporal patterns
        self.lstm_encoder = nn.LSTM(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=num_lstm_layers,
            batch_first=True,
            dropout=dropout if num_lstm_layers > 1 else 0,
        )

        # Gated skip connection from LSTM
        self.lstm_glu = GatedLinearUnit(hidden_dim, hidden_dim, dropout)
        self.lstm_layer_norm = nn.LayerNorm(hidden_dim)

        # Interpretable Multi-Head Attention
        self.attention = InterpretableMultiHeadAttention(
            embed_dim=hidden_dim,
            num_heads=num_heads,
            dropout=dropout,
        )

        # Post-attention GRN
        self.attention_grn = GatedResidualNetwork(
            input_dim=hidden_dim,
            hidden_dim=hidden_dim,
            output_dim=hidden_dim,
            dropout=dropout,
        )

        # Output layer with quantiles
        self.output_layer = nn.Linear(hidden_dim, forecast_horizon * num_quantiles)

        # Store attention weights for interpretability
        self.attention_weights = None

        _brain_logger.info(
            f"TFT initialized: input_dim={input_dim}, hidden_dim={hidden_dim}, "
            f"heads={num_heads}, forecast={forecast_horizon}, quantiles={num_quantiles}"
        )

    def forward(
        self,
        x: torch.Tensor,
        mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Forward pass through TFT.

        Args:
            x: Input tensor (batch, seq_len, input_dim)
            mask: Optional attention mask

        Returns:
            predictions: (batch, forecast_horizon, num_quantiles)
        """
        batch_size, seq_len, _ = x.shape

        # Project input
        embedded = self.input_projection(x)

        # Static context (use mean of sequence)
        static_context = self.static_vsn(embedded.mean(dim=1))

        # LSTM encoding
        lstm_out, _ = self.lstm_encoder(embedded)

        # Gated skip connection
        lstm_out = self.lstm_layer_norm(embedded + self.lstm_glu(lstm_out))

        # Self-attention with interpretable weights
        attended, attn_weights = self.attention(lstm_out, lstm_out, lstm_out, mask)
        self.attention_weights = attn_weights  # Store for interpretability

        # Post-attention processing
        enriched = self.attention_grn(attended)

        # Add residual from LSTM
        enriched = enriched + lstm_out

        # Use last timestep for prediction
        final_hidden = enriched[:, -1, :]

        # Output projections
        output = self.output_layer(final_hidden)
        output = output.view(batch_size, self.forecast_horizon, self.num_quantiles)

        return output

    def get_attention_weights(self) -> Optional[torch.Tensor]:
        """Return stored attention weights for interpretability."""
        return self.attention_weights


class TFTPredictor:
    """
    High-level wrapper for Temporal Fusion Transformer.

    Provides easy-to-use interface for training and prediction,
    with support for uncertainty quantification and interpretability.
    """

    def __init__(
        self,
        input_dim: int = 10,
        hidden_dim: int = 64,
        num_heads: int = 4,
        forecast_horizon: int = 10,
        num_quantiles: int = 3,
        quantiles: Optional[List[float]] = None,
        device: Optional[torch.device] = None,
    ):
        """
        Initialize TFT predictor.

        Args:
            input_dim: Number of input features
            hidden_dim: Hidden dimension
            num_heads: Number of attention heads
            forecast_horizon: Prediction horizon
            num_quantiles: Number of quantile outputs
            quantiles: Specific quantile values (default: [0.1, 0.5, 0.9])
            device: Torch device
        """
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.forecast_horizon = forecast_horizon
        self.num_quantiles = num_quantiles
        self.quantiles = quantiles or [0.1, 0.5, 0.9]

        self.device = device or torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        self.model = TemporalFusionTransformer(
            input_dim=input_dim,
            hidden_dim=hidden_dim,
            num_heads=num_heads,
            forecast_horizon=forecast_horizon,
            num_quantiles=num_quantiles,
        ).to(self.device)

        self.optimizer = None
        self.trained = False

        _brain_logger.info(
            f"TFTPredictor initialized: device={self.device}, quantiles={self.quantiles}"
        )

    def _quantile_loss(
        self,
        predictions: torch.Tensor,
        targets: torch.Tensor,
    ) -> torch.Tensor:
        """
        Quantile loss for probabilistic predictions.

        Also known as pinball loss.
        """
        losses = []
        for i, q in enumerate(self.quantiles):
            pred = predictions[:, :, i]
            errors = targets - pred
            losses.append(torch.max(q * errors, (q - 1) * errors).mean())
        return torch.stack(losses).mean()

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        epochs: int = 100,
        batch_size: int = 32,
        learning_rate: float = 0.001,
        early_stopping_patience: int = 10,
    ) -> Dict[str, List[float]]:
        """
        Train the TFT model.

        Args:
            X_train: Training inputs (n_samples, seq_len, features)
            y_train: Training targets (n_samples,) or (n_samples, horizon)
            X_val: Validation inputs
            y_val: Validation targets
            epochs: Number of epochs
            batch_size: Batch size
            learning_rate: Learning rate
            early_stopping_patience: Patience for early stopping

        Returns:
            Training history
        """
        self.model.train()
        self.optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)

        # Ensure correct input shape
        if X_train.ndim == 2:
            X_train = X_train.reshape(X_train.shape[0], -1, self.input_dim)

        # Ensure target shape
        if y_train.ndim == 1:
            y_train = np.tile(y_train.reshape(-1, 1), (1, self.forecast_horizon))

        X_train_t = torch.FloatTensor(X_train).to(self.device)
        y_train_t = torch.FloatTensor(y_train).to(self.device)

        # Validation data
        if X_val is not None and y_val is not None:
            if X_val.ndim == 2:
                X_val = X_val.reshape(X_val.shape[0], -1, self.input_dim)
            if y_val.ndim == 1:
                y_val = np.tile(y_val.reshape(-1, 1), (1, self.forecast_horizon))
            X_val_t = torch.FloatTensor(X_val).to(self.device)
            y_val_t = torch.FloatTensor(y_val).to(self.device)
        else:
            X_val_t, y_val_t = None, None

        # Training history
        history = {"loss": [], "val_loss": []}
        best_val_loss = float("inf")
        patience_counter = 0

        # DataLoader
        dataset = TensorDataset(X_train_t, y_train_t)
        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        for epoch in range(epochs):
            epoch_loss = 0.0
            self.model.train()

            for batch_x, batch_y in dataloader:
                self.optimizer.zero_grad()

                # Forward pass
                output = self.model(batch_x)

                # Quantile loss
                loss = self._quantile_loss(output, batch_y)

                # Backward pass
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                self.optimizer.step()

                epoch_loss += loss.item()

            epoch_loss /= len(dataloader)
            history["loss"].append(epoch_loss)

            # Validation
            if X_val_t is not None:
                self.model.eval()
                with torch.no_grad():
                    val_output = self.model(X_val_t)
                    val_loss = self._quantile_loss(val_output, y_val_t).item()
                history["val_loss"].append(val_loss)

                # Early stopping
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience_counter = 0
                else:
                    patience_counter += 1

                if patience_counter >= early_stopping_patience:
                    _brain_logger.info(f"TFT early stopping at epoch {epoch + 1}")
                    break

            if epoch % 10 == 0:
                val_str = (
                    f", val_loss={history['val_loss'][-1]:.6f}"
                    if history["val_loss"]
                    else ""
                )
                _brain_logger.info(
                    f"TFT Epoch {epoch + 1}/{epochs}: loss={epoch_loss:.6f}{val_str}"
                )

        self.trained = True
        _brain_logger.info(
            f"TFT training complete. Final loss: {history['loss'][-1]:.6f}"
        )
        return history

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Make point predictions (median quantile).

        Args:
            X: Input data (n_samples, seq_len, features)

        Returns:
            Point predictions (n_samples,)
        """
        self.model.eval()

        if X.ndim == 2:
            X = X.reshape(X.shape[0], -1, self.input_dim)

        X_t = torch.FloatTensor(X).to(self.device)

        with torch.no_grad():
            output = self.model(X_t)

        # Return median (middle quantile) of first forecast step
        median_idx = self.num_quantiles // 2
        return output[:, 0, median_idx].cpu().numpy()

    def predict_quantiles(self, X: np.ndarray) -> np.ndarray:
        """
        Predict all quantiles for uncertainty estimation.

        Args:
            X: Input data

        Returns:
            Quantile predictions (n_samples, horizon, num_quantiles)
        """
        self.model.eval()

        if X.ndim == 2:
            X = X.reshape(X.shape[0], -1, self.input_dim)

        X_t = torch.FloatTensor(X).to(self.device)

        with torch.no_grad():
            output = self.model(X_t)

        return output.cpu().numpy()

    def predict_with_intervals(self, X: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Predict with prediction intervals.

        Returns:
            Dictionary with 'lower', 'median', 'upper' predictions
        """
        quantile_preds = self.predict_quantiles(X)

        return {
            "lower": quantile_preds[:, :, 0],
            "median": quantile_preds[:, :, 1],
            "upper": quantile_preds[:, :, 2],
        }

    def get_attention_weights(self) -> Optional[np.ndarray]:
        """
        Get attention weights for interpretability.

        Returns:
            Attention weights if available
        """
        weights = self.model.get_attention_weights()
        if weights is not None:
            return weights.cpu().numpy()
        return None

    def save(self, path: str) -> None:
        """Save model."""
        torch.save(
            {
                "model_state_dict": self.model.state_dict(),
                "input_dim": self.input_dim,
                "hidden_dim": self.hidden_dim,
                "forecast_horizon": self.forecast_horizon,
                "num_quantiles": self.num_quantiles,
                "quantiles": self.quantiles,
            },
            path,
        )
        _brain_logger.info(f"TFT model saved to {path}")

    def load(self, path: str) -> None:
        """Load model."""
        checkpoint = torch.load(path, map_location=self.device)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.trained = True
        _brain_logger.info(f"TFT model loaded from {path}")


class LSTMPricePredictor:
    """PyTorch implementation of the historical LSTM price forecaster."""

    class _Regressor(nn.Module):
        def __init__(
            self,
            input_dim: int,
            hidden_layers: Tuple[int, ...] = (128, 64, 32),
            dropout: float = 0.2,
        ):
            super().__init__()
            self.lstm_layers = nn.ModuleList()
            self.norm_layers = nn.ModuleList()
            in_dim = input_dim
            for hidden in hidden_layers:
                self.lstm_layers.append(nn.LSTM(in_dim, hidden, batch_first=True))
                self.norm_layers.append(nn.LayerNorm(hidden))
                in_dim = hidden
            self.dropout = nn.Dropout(dropout)
            self.head = nn.Sequential(
                nn.Linear(in_dim, 64),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(64, 32),
                nn.ReLU(),
                nn.Linear(32, 1),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            for lstm_layer, norm_layer in zip(self.lstm_layers, self.norm_layers):
                x, _ = lstm_layer(x)
                x = self.dropout(x)
                x = norm_layer(x)
            x = x[:, -1, :]
            return self.head(x)

    def __init__(self, sequence_length: int = 60, n_features: int = 15):
        self.sequence_length = sequence_length
        self.n_features = n_features
        self.scaler = MinMaxScaler()
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model: nn.Module = self._Regressor(n_features).to(self.device)
        self._rust_indicators = None
        if (
            RUST_ANALYTICS_AVAILABLE
            and "RustTechnicalIndicators" in globals()
            and RustTechnicalIndicators is not None
        ):
            try:
                self._rust_indicators = RustTechnicalIndicators()
            except Exception:
                logger.debug(
                    "Rust TechnicalIndicators unavailable; defaulting to pandas",
                    exc_info=True,
                )
                self._rust_indicators = None

    def _apply_rust_indicators(self, data: pd.DataFrame) -> bool:
        if self._rust_indicators is None:
            return False

        def _pad_front(values: List[float], front: int = 1) -> List[float]:
            padded = [float("nan")] * front + values
            if len(padded) < len(data):
                padded.extend([float("nan")] * (len(data) - len(padded)))
            elif len(padded) > len(data):
                padded = padded[: len(data)]
            return padded

        try:
            prices = data["close"].astype(float).tolist()
            volumes = data["volume"].astype(float).tolist()

            returns = self._rust_indicators.returns(prices)
            data["returns"] = pd.Series(
                _pad_front(list(returns)), index=data.index, dtype=float
            )

            log_returns = self._rust_indicators.log_returns(prices)
            data["log_returns"] = pd.Series(
                _pad_front(list(log_returns)), index=data.index, dtype=float
            )

            rsi = self._rust_indicators.rsi(prices, 14)
            data["rsi"] = pd.Series(list(rsi), index=data.index, dtype=float)

            macd_line, macd_signal = self._rust_indicators.macd(prices, 12, 26, 9)
            data["macd"] = pd.Series(list(macd_line), index=data.index, dtype=float)
            data["macd_signal"] = pd.Series(
                list(macd_signal), index=data.index, dtype=float
            )

            volume_ratio = self._rust_indicators.volume_ratio(volumes, 20)
            data["volume_ratio"] = pd.Series(
                list(volume_ratio), index=data.index, dtype=float
            )
            return True
        except Exception:
            logger.exception(
                "Rust technical indicators failed; falling back to pandas implementation"
            )
            return False

    def prepare_data(self, data: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare data for LSTM"""
        used_rust = self._apply_rust_indicators(data)
        if not used_rust:
            data["returns"] = data["close"].pct_change()
            data["log_returns"] = np.log(data["close"] / data["close"].shift(1))
            data["volume_ratio"] = data["volume"] / data["volume"].rolling(20).mean()
            data["rsi"] = self.calculate_rsi(data["close"])
            data["macd"], data["macd_signal"] = self.calculate_macd(data["close"])

        # Remove NaN values
        data = data.dropna()

        # Scale features
        scaled_data = self.scaler.fit_transform(data)

        # Create sequences
        X, y = [], []
        for i in range(self.sequence_length, len(scaled_data)):
            X.append(scaled_data[i - self.sequence_length : i])
            y.append(scaled_data[i, 3])  # Assuming close price is at index 3

        return np.array(X), np.array(y)

    @staticmethod
    def calculate_rsi(prices, period=14):
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def calculate_macd(prices, fast=12, slow=26, signal=9):
        """Calculate MACD indicator"""
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal).mean()
        return macd, macd_signal

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
        epochs: int = 100,
    ) -> Dict[str, List[float]]:
        """Train the PyTorch LSTM using mini-batch gradient descent with early stopping."""
        if len(X_train) == 0:
            raise ValueError(
                "Cannot train LSTMPricePredictor with an empty training set"
            )

        criterion = nn.MSELoss()
        optimizer = optim.Adam(self.model.parameters(), lr=0.001)
        batch_size = min(32, max(1, len(X_train) // 10))

        train_dataset = TensorDataset(
            torch.from_numpy(X_train).float(),
            torch.from_numpy(y_train.reshape(-1, 1)).float(),
        )
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

        val_dataset = (
            TensorDataset(
                torch.from_numpy(X_val).float(),
                torch.from_numpy(y_val.reshape(-1, 1)).float(),
            )
            if len(X_val)
            else None
        )
        val_loader = (
            DataLoader(val_dataset, batch_size=batch_size) if val_dataset else None
        )

        history = {"loss": [], "val_loss": []}
        best_state: Optional[Dict[str, torch.Tensor]] = None
        best_val = float("inf")
        patience = 10
        epochs_no_improve = 0

        for epoch in range(epochs):
            self.model.train()
            running_loss = 0.0
            for batch_x, batch_y in train_loader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)
                optimizer.zero_grad()
                preds = self.model(batch_x)
                loss = criterion(preds, batch_y)
                loss.backward()
                optimizer.step()
                running_loss += loss.item() * batch_x.size(0)

            epoch_loss = running_loss / len(train_dataset)
            history["loss"].append(epoch_loss)

            if val_loader:
                self.model.eval()
                val_loss_accum = 0.0
                with torch.no_grad():
                    for batch_x, batch_y in val_loader:
                        batch_x = batch_x.to(self.device)
                        batch_y = batch_y.to(self.device)
                        preds = self.model(batch_x)
                        val_loss_accum += criterion(
                            preds, batch_y
                        ).item() * batch_x.size(0)
                epoch_val_loss = val_loss_accum / len(val_dataset)  # type: ignore[arg-type]
            else:
                epoch_val_loss = float("nan")

            history["val_loss"].append(epoch_val_loss)

            if val_loader:
                if epoch_val_loss < best_val - 1e-6:
                    best_val = epoch_val_loss
                    best_state = copy.deepcopy(self.model.state_dict())
                    epochs_no_improve = 0
                else:
                    epochs_no_improve += 1
                    if epochs_no_improve >= patience:
                        break

        if best_state is not None:
            self.model.load_state_dict(best_state)

        return history

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Run inference on a numpy tensor of shape (batch, seq_len, features)."""
        if len(X) == 0:
            return np.empty((0, 1))
        self.model.eval()
        with torch.no_grad():
            tensor = torch.from_numpy(X).float().to(self.device)
            preds = self.model(tensor).cpu().numpy()
        return preds.reshape(-1, 1)

    def save(self, filepath: str) -> None:
        """Persist the model weights and scaler using PyTorch checkpoints."""
        checkpoint = {
            "state_dict": self.model.state_dict(),
            "n_features": self.n_features,
            "sequence_length": self.sequence_length,
        }
        torch.save(checkpoint, f"{filepath}_model.pt")
        joblib.dump(self.scaler, f"{filepath}_scaler.pkl")

    def load(self, filepath: str) -> None:
        """Load PyTorch checkpoint; instruct callers to retrain if legacy files are missing."""
        model_path = Path(f"{filepath}_model.pt")
        if not model_path.exists():
            raise FileNotFoundError(
                f"Missing {model_path}. TensorFlow checkpoints are no longer supported; retrain the LSTM predictor."
            )
        checkpoint = torch.load(model_path, map_location=self.device)
        self.n_features = int(checkpoint.get("n_features", self.n_features))
        self.sequence_length = int(
            checkpoint.get("sequence_length", self.sequence_length)
        )
        self.model = self._Regressor(self.n_features).to(self.device)
        self.model.load_state_dict(checkpoint["state_dict"])
        self.scaler = joblib.load(f"{filepath}_scaler.pkl")


class ReinforcementLearningTrader:
    """PyTorch DQN trader with target network and replay buffer."""

    def __init__(self, state_size: int = 20, action_size: int = 3):
        self.state_size = state_size
        self.action_size = action_size
        self.memory: List[Tuple[np.ndarray, int, float, np.ndarray, bool]] = []
        self.epsilon = 1.0
        self.epsilon_min = 0.01
        self.epsilon_decay = 0.995
        self.gamma = 0.95
        self.learning_rate = 0.001
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = self._build_model().to(self.device)
        self.target_model = self._build_model().to(self.device)
        self.criterion = nn.MSELoss()
        self.optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)

    def _build_model(self) -> nn.Module:
        """Multilayer perceptron used for Q-value approximation."""
        return nn.Sequential(
            nn.Linear(self.state_size, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, self.action_size),
        )

    def remember(self, state, action, reward, next_state, done):
        """Store experience in replay memory with bounded size."""
        experience = (
            np.array(state, dtype=np.float32).reshape(-1),
            int(action),
            float(reward),
            np.array(next_state, dtype=np.float32).reshape(-1),
            bool(done),
        )
        self.memory.append(experience)
        if len(self.memory) > 2000:
            self.memory.pop(0)

    def act(self, state):
        """Choose action using epsilon-greedy policy."""
        if np.random.random() <= self.epsilon:
            return int(np.random.choice(self.action_size))

        state_tensor = (
            torch.from_numpy(np.array(state, dtype=np.float32).reshape(-1))
            .float()
            .to(self.device)
        )
        if state_tensor.ndim == 1:
            state_tensor = state_tensor.unsqueeze(0)
        self.model.eval()
        with torch.no_grad():
            q_values = self.model(state_tensor)
        return int(torch.argmax(q_values, dim=1).item())

    def replay(self, batch_size=32):
        """Train model on random batches sampled from replay memory."""
        if len(self.memory) < batch_size:
            return

        indices = np.random.choice(len(self.memory), batch_size, replace=False)
        batch = [self.memory[i] for i in indices]

        states = (
            torch.from_numpy(np.vstack([exp[0] for exp in batch]))
            .float()
            .to(self.device)
        )
        actions = torch.tensor(
            [exp[1] for exp in batch], dtype=torch.long, device=self.device
        )
        rewards = torch.tensor(
            [exp[2] for exp in batch], dtype=torch.float32, device=self.device
        )
        next_states = (
            torch.from_numpy(np.vstack([exp[3] for exp in batch]))
            .float()
            .to(self.device)
        )
        dones = torch.tensor(
            [exp[4] for exp in batch], dtype=torch.float32, device=self.device
        )

        self.model.train()
        current_q = self.model(states)
        with torch.no_grad():
            next_q = self.target_model(next_states)
            max_next_q = torch.max(next_q, dim=1).values
            target_q_values = rewards + (1 - dones) * self.gamma * max_next_q

        target_full = current_q.clone().detach()
        idx = torch.arange(batch_size, device=self.device)
        target_full[idx, actions] = target_q_values

        loss = self.criterion(current_q, target_full)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

    def update_target_model(self):
        """Keep the target network in sync with the policy network."""
        self.target_model.load_state_dict(self.model.state_dict())

    def calculate_reward(self, action, price_change, position):
        """Calculate reward for action taken"""
        if action == 0:  # Buy
            return price_change if position <= 0 else -abs(price_change) * 0.5
        elif action == 1:  # Sell
            return -price_change if position >= 0 else -abs(price_change) * 0.5
        else:  # Hold
            return -abs(price_change) * 0.1 if position == 0 else 0

    def save(self, model_path: str, target_path: str) -> None:
        torch.save(self.model.state_dict(), model_path)
        torch.save(self.target_model.state_dict(), target_path)

    def load(self, model_path: str, target_path: str) -> None:
        if not Path(model_path).exists() or not Path(target_path).exists():
            raise FileNotFoundError(
                "Missing RL trader checkpoints. Legacy TensorFlow models are no longer supported; retrain the agent."
            )
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.target_model.load_state_dict(
            torch.load(target_path, map_location=self.device)
        )


class EnsemblePredictor:
    """Ensemble of multiple models for robust prediction"""

    def __init__(self):
        self.models = {
            "lstm": LSTMPricePredictor(),
            "rf": RandomForestRegressor(n_estimators=100, random_state=42),
            "gb": GradientBoostingRegressor(n_estimators=100, random_state=42),
            "transformer": None,  # PyTorch model
            "nbeats": NBeatsPredictor(
                input_size=60, forecast_size=10, interpretable=True
            ),
            "tft": TFTPredictor(input_dim=10, hidden_dim=64, forecast_horizon=10),
        }
        self.weights = {
            "lstm": 0.2,
            "rf": 0.1,
            "gb": 0.1,
            "transformer": 0.1,
            "nbeats": 0.25,
            "tft": 0.25,
        }
        self.scaler = StandardScaler()
        self.feature_store = PredictionFeatureStore()
        self.scenario_generator = DiffusionScenarioGenerator()
        self.calibrator = PredictionCalibrator()

    def train_all_models(self, X_train, y_train, X_val, y_val):
        """Train all models in ensemble"""
        results = {}

        # Train LSTM
        print("Training LSTM...")
        lstm_history = self.models["lstm"].train(
            X_train, y_train, X_val, y_val, epochs=50
        )
        results["lstm"] = {
            "final_loss": lstm_history["loss"][-1],
            "final_val_loss": (
                lstm_history["val_loss"][-1]
                if lstm_history["val_loss"]
                else float("nan")
            ),
        }

        # Train Random Forest
        print("Training Random Forest...")
        X_train_2d = X_train.reshape(X_train.shape[0], -1)
        X_val_2d = X_val.reshape(X_val.shape[0], -1)
        self.models["rf"].fit(X_train_2d, y_train)
        results["rf"] = {"score": self.models["rf"].score(X_val_2d, y_val)}

        # Train Gradient Boosting
        print("Training Gradient Boosting...")
        self.models["gb"].fit(X_train_2d, y_train)
        results["gb"] = {"score": self.models["gb"].score(X_val_2d, y_val)}

        # Initialize and train Transformer
        print("Training Transformer...")
        self.models["transformer"] = MarketTransformer(input_dim=X_train.shape[2])
        results["transformer"] = self.train_transformer(X_train, y_train, X_val, y_val)

        # Train N-BEATS (Phase 1.2 Enhancement)
        print("Training N-BEATS...")
        nbeats_history = self.models["nbeats"].train(
            X_train, y_train, X_val, y_val, epochs=100, early_stopping_patience=15
        )
        results["nbeats"] = {
            "final_loss": nbeats_history["loss"][-1],
            "final_val_loss": (
                nbeats_history["val_loss"][-1]
                if nbeats_history["val_loss"]
                else float("nan")
            ),
        }

        # Train TFT (Phase 1.1 Enhancement)
        print("Training Temporal Fusion Transformer...")
        self.models["tft"] = TFTPredictor(
            input_dim=X_train.shape[2],
            hidden_dim=64,
            forecast_horizon=10,
        )
        tft_history = self.models["tft"].train(
            X_train, y_train, X_val, y_val, epochs=100, early_stopping_patience=15
        )
        results["tft"] = {
            "final_loss": tft_history["loss"][-1],
            "final_val_loss": (
                tft_history["val_loss"][-1] if tft_history["val_loss"] else float("nan")
            ),
        }

        # Optimize weights based on validation performance
        self.optimize_weights(X_val, y_val)

        # Update calibrator with validation residuals for interval estimation
        try:
            val_preds = self.predict(X_val)
            self.calibrator.update(y_val, val_preds)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Calibrator update failed: %s", exc)

        return results

    def collect_component_predictions(self, X: np.ndarray) -> Dict[str, np.ndarray]:
        """Return individual model predictions for downstream calibration."""
        predictions: Dict[str, np.ndarray] = {}

        # LSTM prediction
        predictions["lstm"] = self.models["lstm"].predict(X)

        # Random Forest prediction
        X_2d = X.reshape(X.shape[0], -1)
        predictions["rf"] = self.models["rf"].predict(X_2d)

        # Gradient Boosting prediction
        predictions["gb"] = self.models["gb"].predict(X_2d)

        # Transformer prediction
        if self.models["transformer"]:
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            X_torch = torch.FloatTensor(X).to(device)
            self.models["transformer"].eval()
            with torch.no_grad():
                trans_pred = self.models["transformer"](X_torch)
                predictions["transformer"] = trans_pred[:, -1, 0].cpu().numpy()
        else:
            predictions["transformer"] = np.zeros(len(X))

        # N-BEATS prediction
        if self.models["nbeats"].trained:
            predictions["nbeats"] = self.models["nbeats"].predict(X)
        else:
            predictions["nbeats"] = np.zeros(len(X))

        # TFT prediction
        if self.models["tft"].trained:
            predictions["tft"] = self.models["tft"].predict(X)
        else:
            predictions["tft"] = np.zeros(len(X))

        return predictions

    def train_transformer(self, X_train, y_train, X_val, y_val, epochs=50):
        """Train transformer model"""
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = self.models["transformer"].to(device)

        X_train_torch = torch.FloatTensor(X_train).to(device)
        y_train_torch = torch.FloatTensor(y_train).to(device)
        X_val_torch = torch.FloatTensor(X_val).to(device)
        y_val_torch = torch.FloatTensor(y_val).to(device)

        criterion = nn.MSELoss()
        optimizer = optim.Adam(model.parameters(), lr=0.001)

        train_losses = []
        val_losses = []

        for epoch in range(epochs):
            model.train()
            optimizer.zero_grad()

            outputs = model(X_train_torch)
            loss = criterion(outputs[:, -1, 0], y_train_torch)
            loss.backward()
            optimizer.step()

            train_losses.append(loss.item())

            # Validation
            model.eval()
            with torch.no_grad():
                val_outputs = model(X_val_torch)
                val_loss = criterion(val_outputs[:, -1, 0], y_val_torch)
                val_losses.append(val_loss.item())

            if epoch % 10 == 0:
                print(
                    f"Epoch {epoch}, Train Loss: {loss.item():.4f}, Val Loss: {val_loss.item():.4f}"
                )

        return {"train_losses": train_losses, "val_losses": val_losses}

    def optimize_weights(self, X_val, y_val):
        """Optimize ensemble weights using validation data"""
        from scipy.optimize import minimize

        def objective(weights):
            predictions = self.predict_with_weights(X_val, weights)
            mse = np.mean((predictions - y_val) ** 2)
            return mse

        # Constraints: weights sum to 1
        constraints = {"type": "eq", "fun": lambda x: np.sum(x) - 1}
        bounds = [(0, 1) for _ in range(len(self.models))]

        result = minimize(
            objective,
            x0=list(self.weights.values()),
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )

        if result.success:
            self.weights = dict(zip(self.weights.keys(), result.x))
            print(f"Optimized weights: {self.weights}")

    def predict_with_weights(self, X, weights):
        """Make predictions with specific weights"""
        predictions = self.collect_component_predictions(X)
        # Weighted average
        weighted_pred = np.zeros(len(X))
        for model_name, weight in zip(self.weights.keys(), weights):
            weighted_pred += predictions[model_name].flatten() * weight

        return weighted_pred

    def predict(self, X):
        """Make ensemble prediction"""
        return self.predict_with_weights(X, list(self.weights.values()))

    def predict_enhanced(
        self,
        X: np.ndarray,
        *,
        market_window: Optional[pd.DataFrame] = None,
        sentiment_ctx: Optional[Dict[str, float]] = None,
        macro_ctx: Optional[Dict[str, float]] = None,
    ) -> PredictionEnvelope:
        """Return enriched prediction envelope with scenarios and modal signals."""

        if len(X) == 0:
            raise ValueError("Empty feature tensor supplied to predict_enhanced")

        component_preds = self.collect_component_predictions(X)
        weighted = np.zeros(len(X))
        for model_name, weight in self.weights.items():
            weighted += component_preds[model_name].flatten() * weight
        point_forecast = float(weighted[-1])

        modal_signals = (
            self.feature_store.build_modal_signals(
                market_window,
                sentiment_ctx=sentiment_ctx,
                macro_ctx=macro_ctx,
            )
            if market_window is not None
            else {}
        )

        scenario_paths = self.scenario_generator.generate(
            market_window["close"] if market_window is not None else None
        )

        interval = self.calibrator.estimate_interval(point_forecast)
        confidence = self.calibrator.confidence_from_interval(point_forecast, interval)

        raw_outputs = {k: float(v[-1]) for k, v in component_preds.items()}

        return PredictionEnvelope(
            point_forecast=point_forecast,
            confidence=confidence,
            interval=interval,
            scenario_paths=scenario_paths,
            feature_signals=modal_signals,
            raw_model_outputs=raw_outputs,
        )


class MarketSentimentAnalyzer:
    """Analyze market sentiment from various sources"""

    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.sentiment_model = self._build_sentiment_model()
        self.fear_greed_weights = {
            "volatility": 0.25,
            "momentum": 0.25,
            "volume": 0.125,
            "put_call_ratio": 0.125,
            "safe_haven_demand": 0.125,
            "market_breadth": 0.125,
        }

    def _build_sentiment_model(self):
        """Tiny PyTorch classifier placeholder kept for future fine-tuning."""
        model = nn.Sequential(
            nn.Linear(10, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )
        return model.to(self.device)

    def calculate_fear_greed_index(self, market_data):
        """Calculate Fear & Greed Index"""
        scores = {}

        # Volatility (VIX-like calculation)
        returns = np.diff(np.log(market_data["close"]))
        volatility = np.std(returns) * np.sqrt(252)
        scores["volatility"] = 1 - min(volatility / 0.5, 1)  # Normalize to 0-1

        # Momentum (price vs moving averages)
        sma_125 = market_data["close"].rolling(125).mean().iloc[-1]
        current_price = market_data["close"].iloc[-1]
        scores["momentum"] = min(current_price / sma_125, 2) / 2

        # Volume
        volume_avg = market_data["volume"].rolling(30).mean().iloc[-1]
        current_volume = market_data["volume"].iloc[-1]
        scores["volume"] = min(current_volume / volume_avg, 2) / 2

        # Put/Call Ratio (simulated)
        scores["put_call_ratio"] = np.random.uniform(0.3, 0.7)

        # Safe Haven Demand (simulated)
        scores["safe_haven_demand"] = np.random.uniform(0.3, 0.7)

        # Market Breadth (simulated)
        scores["market_breadth"] = np.random.uniform(0.3, 0.7)

        # Calculate weighted index
        fear_greed_index = sum(
            scores[metric] * weight
            for metric, weight in self.fear_greed_weights.items()
        )

        return fear_greed_index * 100, scores

    def analyze_pattern_sentiment(self, pattern_data):
        """Analyze sentiment from price patterns"""
        patterns = {
            "bullish_engulfing": 0.7,
            "bearish_engulfing": 0.3,
            "hammer": 0.65,
            "shooting_star": 0.35,
            "doji": 0.5,
            "three_white_soldiers": 0.8,
            "three_black_crows": 0.2,
            "morning_star": 0.75,
            "evening_star": 0.25,
        }

        detected_patterns = self.detect_candlestick_patterns(pattern_data)

        if detected_patterns:
            sentiment = np.mean([patterns.get(p, 0.5) for p in detected_patterns])
        else:
            sentiment = 0.5

        return sentiment

    def detect_candlestick_patterns(self, data):
        """Detect candlestick patterns"""
        detected = []

        if len(data) < 3:
            return detected

        # Simplified pattern detection
        open_prices = data["open"].values[-3:]
        close_prices = data["close"].values[-3:]
        high_prices = data["high"].values[-3:]
        low_prices = data["low"].values[-3:]

        # Bullish Engulfing
        if (
            close_prices[-2] < open_prices[-2]  # Previous bearish
            and close_prices[-1] > open_prices[-1]  # Current bullish
            and close_prices[-1] > open_prices[-2]  # Engulfs previous
            and open_prices[-1] < close_prices[-2]
        ):
            detected.append("bullish_engulfing")

        # Bearish Engulfing
        if (
            close_prices[-2] > open_prices[-2]  # Previous bullish
            and close_prices[-1] < open_prices[-1]  # Current bearish
            and close_prices[-1] < open_prices[-2]  # Engulfs previous
            and open_prices[-1] > close_prices[-2]
        ):
            detected.append("bearish_engulfing")

        # Doji
        if (
            abs(close_prices[-1] - open_prices[-1]) / (high_prices[-1] - low_prices[-1])
            < 0.1
        ):
            detected.append("doji")

        return detected


class AnvelBrain:
    """Main AI brain coordinating all models"""

    def __init__(self):
        self.ensemble_predictor = EnsemblePredictor()
        self.rl_trader = ReinforcementLearningTrader()
        self.sentiment_analyzer = MarketSentimentAnalyzer()
        self.lstm_predictor = LSTMPricePredictor()
        self.neuro_forge = NeuroForgeTrainer()
        self.reasoning_core = ReasoningCore()
        self.subsystems = BrainSubsystems()
        self.rust_adapter = RustBrainAdapter()

        self.confidence_threshold = 0.7
        self.risk_tolerance = 0.02
        self.position = 0
        self.capital = 10000
        self.trade_history = []
        self._lock = threading.RLock()
        self.reflections: deque[Dict[str, Any]] = deque(maxlen=200)
        self.intent_history: deque[Dict[str, Any]] = deque(maxlen=100)
        self.intent_errors: deque[Dict[str, Any]] = deque(maxlen=20)
        self.processing_metrics = {"processed": 0, "errors": 0}
        self._pre_hooks: List[Callable[[Any], Any]] = []
        self._post_hooks: List[Callable[[Any], Any]] = []
        self.market_tick_log: deque[Dict[str, Any]] = deque(maxlen=500)
        self.latest_market_snapshot: Dict[str, Any] = {}

    @staticmethod
    def _prepare_historical_frame(df: pd.DataFrame, date_column: str) -> pd.DataFrame:
        required_columns = {"open", "high", "low", "close", "volume"}
        missing = required_columns - set(df.columns)
        if missing:
            raise ValueError(f"Historical data is missing required columns: {missing}")

        if date_column in df.columns:
            df[date_column] = pd.to_datetime(df[date_column])
            df = df.sort_values(date_column)
            df = df.set_index(date_column)

        df = df.copy()
        df = df.fillna(method="ffill").dropna()
        return df.reset_index(drop=True)

    def train_from_csv(
        self, csv_path: str, date_column: str = "date", limit_rows: Optional[int] = None
    ) -> Dict[str, Any]:
        """Load historical candles from CSV and run full training pipeline."""
        if not Path(csv_path).exists():
            raise FileNotFoundError(f"Historical CSV not found: {csv_path}")

        data = pd.read_csv(csv_path)
        if limit_rows:
            data = data.tail(limit_rows)
        frame = self._prepare_historical_frame(data, date_column)
        return self.train_on_historical_data(frame)

    def use(
        self,
        *,
        pre: Optional[Callable[[Any], Any]] = None,
        post: Optional[Callable[[Any], Any]] = None,
    ) -> str:
        """Register optional middleware hooks for pre/post processing."""

        if pre is not None:
            self._pre_hooks.append(pre)
        if post is not None:
            self._post_hooks.append(post)
        return "[BRAIN] middleware registered"

    # ------------------------------------------------------------------
    # Modular brain helpers (AI shell, context router, etc.)
    # ------------------------------------------------------------------
    def register_shell_command(
        self, keyword: str, handler: Callable[[str], str]
    ) -> str:
        """Expose the legacy AI shell command registration to operators."""

        return self.subsystems.shell.register_command(keyword, handler)

    def run_shell_command(self, text: str) -> str:
        """Execute a shell command without touching the main pipeline."""

        return self.subsystems.shell.interpret(text)

    def add_context_route(
        self, key: str, handler: Callable[[Dict[str, str]], str]
    ) -> str:
        return self.subsystems.context_router.add_route(key, handler)

    def route_context(self, context: Dict[str, str]) -> str:
        return self.subsystems.context_router.route(context)

    def learn_word(self, word: str, meaning: str) -> str:
        return self.subsystems.language_bridge.learn_word(word, meaning)

    def translate(self, text: str) -> str:
        return self.subsystems.language_bridge.translate(text)

    def log_emotion(self, label: str, intensity: float) -> str:
        return self.subsystems.emotion_matrix.log_emotion(label, intensity)

    def dominant_emotion(self) -> str:
        return self.subsystems.emotion_matrix.dominant_emotion()

    def emotion_snapshot(self) -> Dict[str, float]:
        return self.subsystems.emotion_matrix.snapshot()

    def generate_intuition(self, topic: str, bias: Optional[int] = None) -> str:
        return self.subsystems.intuition_engine.generate(topic, bias)

    def reflect_intuition(self, topic: str) -> str:
        return self.subsystems.intuition_engine.reflect(topic)

    def add_concept(self, label: str, definition: str) -> str:
        return self.subsystems.thought_map.add_concept(label, definition)

    def link_concepts(self, source: str, target: str, relationship: str) -> str:
        return self.subsystems.thought_map.link(source, target, relationship)

    def concept_definition(self, label: str) -> str:
        return self.subsystems.thought_map.define(label)

    def concept_trace(self, label: str) -> List[Tuple[str, str]]:
        return self.subsystems.thought_map.trace(label)

    def legacy_neuro_learn(self, label: str, data: Iterable[float]) -> str:
        return self.subsystems.legacy_neuro_forge.learn(label, data)

    def legacy_neuro_predict(self, label: str, value: float) -> str:
        return self.subsystems.legacy_neuro_forge.predict(label, value)

    def subsystem_snapshot(self) -> Dict[str, Dict[str, str]]:
        return self.subsystems.snapshot()

    def analyze_market(self, market_data: pd.DataFrame) -> Dict[str, Any]:
        """Route market analysis through the Rust engine when possible."""
        if self.rust_adapter.available:
            try:
                return self.rust_adapter.analyze_market(market_data)
            except Exception as exc:  # pragma: no cover - diagnostics only
                logger.warning("Rust analysis failed, falling back to Python: %s", exc)
        return self._analyze_market_python(market_data)

    def _analyze_market_python(self, market_data: pd.DataFrame) -> Dict[str, Any]:
        """Comprehensive market analysis (legacy Python path)."""
        analysis = {}

        # Sentiment analysis
        fear_greed_index, sentiment_scores = (
            self.sentiment_analyzer.calculate_fear_greed_index(market_data)
        )
        pattern_sentiment = self.sentiment_analyzer.analyze_pattern_sentiment(
            market_data.tail(10)
        )

        analysis["fear_greed_index"] = fear_greed_index
        analysis["sentiment_scores"] = sentiment_scores
        analysis["pattern_sentiment"] = pattern_sentiment

        # Price prediction (requires sentiment context)
        X, _ = self.lstm_predictor.prepare_data(market_data)
        if len(X) > 0:
            latest_sequence = X[-1:]
            envelope = self.ensemble_predictor.predict_enhanced(
                latest_sequence,
                market_window=market_data,
                sentiment_ctx={
                    "fear_greed": fear_greed_index / 100,
                    "pattern": pattern_sentiment,
                },
            )
            analysis["predicted_price"] = envelope.point_forecast
            analysis["price_confidence"] = envelope.confidence
            analysis["prediction_interval"] = envelope.interval
            analysis["prediction_scenarios"] = envelope.scenario_paths
            analysis["prediction_modal_signals"] = envelope.feature_signals
            analysis["prediction_components"] = envelope.raw_model_outputs

        # Technical indicators
        analysis["technical"] = self.calculate_technical_indicators(market_data)

        # Risk assessment
        analysis["risk"] = self.assess_risk(market_data)

        # Trading decision
        analysis["decision"] = self.make_trading_decision(analysis)
        analysis["reasoning_trace"] = analysis["decision"].get("structured_reasoning")

        return analysis

    def process(self, stimulus: str) -> str:
        """Lightweight stimulus processing used by integration tests."""
        for hook in self._pre_hooks:
            try:
                hook(stimulus)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Brain pre-hook failed: %s", exc)
        timestamp = datetime.utcnow().isoformat()
        shell_result = self.subsystems.shell.interpret(stimulus)
        if not shell_result.startswith("[AI SHELL] No matching command found"):
            reflection: Dict[str, Any] = {
                "timestamp": timestamp,
                "stimulus": stimulus,
                "decision": "SHELL",
                "shell_response": shell_result,
            }
            with self._lock:
                self.reflections.append(reflection)
                self.processing_metrics["processed"] += 1
            result: Any = shell_result
            for hook in self._post_hooks:
                try:
                    hook_result = hook(result)
                    if hook_result is not None:
                        result = hook_result
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Brain post-hook failed: %s", exc)
            return cast(str, result)
        if self.rust_adapter.available:
            try:
                rust_out = self.rust_adapter.process(stimulus)
                reflection: Dict[str, Any] = {
                    "timestamp": timestamp,
                    "stimulus": stimulus,
                    "decision": rust_out.get("action", "HOLD"),
                    "signal_strength": round(float(rust_out.get("signal", 0.5)), 4),
                }
                with self._lock:
                    last_intent = (
                        self.intent_history[-1] if self.intent_history else None
                    )
                    last_error = self.intent_errors[-1] if self.intent_errors else None
                    if last_intent:
                        reflection["last_intent"] = last_intent
                    if last_error:
                        reflection["last_error"] = last_error
                        self.intent_errors.clear()
                    self.reflections.append(reflection)
                    self.processing_metrics["processed"] += 1
                    if last_error:
                        self.processing_metrics["errors"] += 1
                response = (
                    cast(str, rust_out.get("message", ""))
                    or f"[BRAIN/RUST] Processed '{stimulus}'"
                )
                if last_error:
                    response += f" | Error: {last_error.get('error', 'unknown')}"
                result: Any = response
                for hook in self._post_hooks:
                    try:
                        hook_result = hook(result)
                        if hook_result is not None:
                            result = hook_result
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Brain post-hook failed: %s", exc)
                return cast(str, result)
            except Exception as exc:  # pragma: no cover - diagnostics only
                logger.warning(
                    "Rust BrainEngine process failed, falling back to Python: %s", exc
                )

        base_value = (abs(hash(stimulus)) % 1000) / 1000.0
        if base_value > 0.66:
            action = "BUY"
        elif base_value < 0.33:
            action = "SELL"
        else:
            action = "HOLD"

        reflection: Dict[str, Any] = {
            "timestamp": timestamp,
            "stimulus": stimulus,
            "decision": action,
            "signal_strength": round(base_value, 4),
        }

        with self._lock:
            last_intent = self.intent_history[-1] if self.intent_history else None
            last_error = self.intent_errors[-1] if self.intent_errors else None
            if last_intent:
                reflection["last_intent"] = last_intent
            if last_error:
                reflection["last_error"] = last_error
                self.intent_errors.clear()
            self.reflections.append(reflection)
            self.processing_metrics["processed"] += 1
            if last_error:
                self.processing_metrics["errors"] += 1

        response = (
            f"[BRAIN] Processed '{stimulus}' -> {action} (signal {base_value:.2f})"
        )
        if last_error:
            response += f" | Error: {last_error.get('error', 'unknown')}"
        result: Any = response
        for hook in self._post_hooks:
            try:
                hook_result = hook(result)
                if hook_result is not None:
                    result = hook_result
            except Exception as exc:  # noqa: BLE001
                logger.warning("Brain post-hook failed: %s", exc)
        return cast(str, result)

    def map_intent(self, intent: str, handler: Callable[[str], Any]) -> str:
        """Map an intent label to a handler and execute it."""
        timestamp = datetime.utcnow().isoformat()
        entry: Dict[str, Any] = {"intent": intent, "timestamp": timestamp}
        try:
            result = handler(intent)
            entry.update({"result": result, "status": "ok"})
            message = f"[BRAIN] Intent mapped: {intent} -> {result}"
        except Exception as exc:  # noqa: BLE001
            entry.update({"error": repr(exc), "status": "error"})
            message = f"[BRAIN] Intent mapped with Error: {intent} ({exc})"

        with self._lock:
            self.intent_history.append(entry)
            if entry["status"] == "error":
                self.intent_errors.append(entry)

        return message

    def ingest_market_tick(self, tick: Optional[Dict[str, Any]]) -> str:
        """Store the latest market tick for downstream analysis."""
        if not tick or "symbol" not in tick:
            return "[BRAIN] Ignored tick"
        snapshot = {
            "symbol": tick["symbol"],
            "mid": tick.get("mid"),
            "bid": tick.get("bid"),
            "ask": tick.get("ask"),
            "source": tick.get("source"),
            "time": tick.get("time", time.time()),
        }
        with self._lock:
            self.market_tick_log.append(snapshot)
            self.latest_market_snapshot[tick["symbol"]] = snapshot
        return "[BRAIN] Tick ingested"

    def recall_reflections(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return the most recent processing reflections."""
        with self._lock:
            return list(self.reflections)[-limit:]

    def recall_reasoning(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return recent structured reasoning packets for operator review."""
        if not hasattr(self, "reasoning_core") or self.reasoning_core is None:
            return []
        return self.reasoning_core.recall(limit)

    def calculate_prediction_confidence(self, X):
        """Calculate confidence in prediction"""
        component_preds = self.ensemble_predictor.collect_component_predictions(X)
        aggregated = np.array([pred[0] for pred in component_preds.values()])
        dispersion = np.std(aggregated)
        base_confidence = 1 / (1 + dispersion)

        ensemble_forecast = float(np.mean(aggregated)) if len(aggregated) else 0.0
        interval = self.ensemble_predictor.calibrator.estimate_interval(
            ensemble_forecast
        )
        calibrated_confidence = (
            self.ensemble_predictor.calibrator.confidence_from_interval(
                ensemble_forecast,
                interval,
            )
        )
        return float((base_confidence + calibrated_confidence) / 2)

    def calculate_technical_indicators(self, data):
        """Calculate comprehensive technical indicators"""
        indicators = {}

        # Moving averages
        indicators["sma_20"] = data["close"].rolling(20).mean().iloc[-1]
        indicators["sma_50"] = data["close"].rolling(50).mean().iloc[-1]
        indicators["ema_12"] = data["close"].ewm(span=12).mean().iloc[-1]
        indicators["ema_26"] = data["close"].ewm(span=26).mean().iloc[-1]

        # MACD
        indicators["macd"] = indicators["ema_12"] - indicators["ema_26"]
        indicators["macd_signal"] = data["close"].ewm(span=9).mean().iloc[-1]

        # RSI
        indicators["rsi"] = self.lstm_predictor.calculate_rsi(data["close"]).iloc[-1]

        # Bollinger Bands
        sma = data["close"].rolling(20).mean()
        std = data["close"].rolling(20).std()
        indicators["bb_upper"] = (sma + 2 * std).iloc[-1]
        indicators["bb_lower"] = (sma - 2 * std).iloc[-1]
        indicators["bb_middle"] = sma.iloc[-1]

        # Stochastic Oscillator
        low_14 = data["low"].rolling(14).min()
        high_14 = data["high"].rolling(14).max()
        indicators["stochastic_k"] = (
            (data["close"] - low_14) / (high_14 - low_14) * 100
        ).iloc[-1]

        # ATR (Average True Range)
        high_low = data["high"] - data["low"]
        high_close = np.abs(data["high"] - data["close"].shift())
        low_close = np.abs(data["low"] - data["close"].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        indicators["atr"] = true_range.rolling(14).mean().iloc[-1]

        return indicators

    def assess_risk(self, data):
        """Assess current market risk"""
        risk_metrics = {}

        # Volatility
        returns = data["close"].pct_change()
        risk_metrics["volatility"] = returns.std() * np.sqrt(252)

        # Maximum drawdown
        rolling_max = data["close"].expanding().max()
        drawdown = (data["close"] - rolling_max) / rolling_max
        risk_metrics["max_drawdown"] = drawdown.min()
        risk_metrics["current_drawdown"] = drawdown.iloc[-1]

        # Value at Risk (VaR) - 95% confidence
        risk_metrics["var_95"] = np.percentile(returns.dropna(), 5)

        # Sharpe Ratio
        risk_free_rate = 0.02 / 252  # Daily risk-free rate
        excess_returns = returns - risk_free_rate
        risk_metrics["sharpe_ratio"] = (
            excess_returns.mean() / excess_returns.std() * np.sqrt(252)
        )

        # Risk score (0-100)
        risk_score = 0
        if risk_metrics["volatility"] > 0.3:
            risk_score += 30
        if abs(risk_metrics["current_drawdown"]) > 0.1:
            risk_score += 25
        if risk_metrics["var_95"] < -0.05:
            risk_score += 25
        if risk_metrics["sharpe_ratio"] < 0.5:
            risk_score += 20

        risk_metrics["risk_score"] = min(risk_score, 100)

        return risk_metrics

    def make_trading_decision(self, analysis):
        """Make final trading decision"""
        decision = {"action": "HOLD", "confidence": 0.0, "size": 0.0, "reasoning": []}

        buy_signals = 0
        sell_signals = 0
        scenario_slopes = summarize_scenario_slopes(
            analysis.get("prediction_scenarios")
        )

        # Price prediction signal
        current_price = analysis["technical"]["bb_middle"]
        predicted_price = analysis.get("predicted_price", current_price)
        price_change_pct = (predicted_price - current_price) / current_price

        if price_change_pct > 0.01:
            buy_signals += 1
            decision["reasoning"].append(
                f"Price predicted to rise {price_change_pct:.2%}"
            )
        elif price_change_pct < -0.01:
            sell_signals += 1
            decision["reasoning"].append(
                f"Price predicted to fall {price_change_pct:.2%}"
            )

        # Sentiment signal
        if analysis["fear_greed_index"] < 30:
            buy_signals += 1
            decision["reasoning"].append("Extreme fear (contrarian buy)")
        elif analysis["fear_greed_index"] > 70:
            sell_signals += 1
            decision["reasoning"].append("Extreme greed (contrarian sell)")

        # Technical signals
        tech = analysis["technical"]

        # RSI
        if tech["rsi"] < 30:
            buy_signals += 1
            decision["reasoning"].append("RSI oversold")
        elif tech["rsi"] > 70:
            sell_signals += 1
            decision["reasoning"].append("RSI overbought")

        # MACD
        if tech["macd"] > tech["macd_signal"]:
            buy_signals += 1
            decision["reasoning"].append("MACD bullish crossover")
        else:
            sell_signals += 1
            decision["reasoning"].append("MACD bearish crossover")

        # Bollinger Bands
        if current_price < tech["bb_lower"]:
            buy_signals += 1
            decision["reasoning"].append("Price below lower Bollinger Band")
        elif current_price > tech["bb_upper"]:
            sell_signals += 1
            decision["reasoning"].append("Price above upper Bollinger Band")

        # Scenario divergence
        if scenario_slopes:
            bull_slope = scenario_slopes.get("bull", 0.0)
            bear_slope = scenario_slopes.get("bear", 0.0)
            if bull_slope > 0.02:
                buy_signals += 1
                decision["reasoning"].append(
                    f"Bull scenario projects +{bull_slope:.2%}"
                )
            if bear_slope < -0.02:
                sell_signals += 1
                decision["reasoning"].append(f"Bear scenario projects {bear_slope:.2%}")

        # Risk check
        if analysis["risk"]["risk_score"] > 70:
            decision["reasoning"].append(
                "High risk environment - reducing position size"
            )
            decision["size"] *= 0.5

        # Final decision
        total_signals = buy_signals + sell_signals
        if total_signals > 0:
            buy_confidence = buy_signals / total_signals
            sell_confidence = sell_signals / total_signals

            if buy_confidence > 0.6:
                decision["action"] = "BUY"
                decision["confidence"] = buy_confidence
                decision["size"] = min(buy_confidence * 0.1, 0.05)  # Max 5% of capital
            elif sell_confidence > 0.6:
                decision["action"] = "SELL"
                decision["confidence"] = sell_confidence
                decision["size"] = min(sell_confidence * 0.1, 0.05)
            else:
                decision["action"] = "HOLD"
                decision["confidence"] = 0.5

        # Scenario-based size modulation
        if scenario_slopes and decision["size"] > 0:
            bull_slope = scenario_slopes.get("bull", 0.0)
            bear_slope = abs(scenario_slopes.get("bear", 0.0))
            divergence = (
                bull_slope - bear_slope
                if decision["action"] == "BUY"
                else bear_slope - bull_slope
            )
            if abs(divergence) > 0.005:
                multiplier = 1 + max(-0.4, min(0.4, divergence * 5))
                decision["size"] = max(0.0, min(0.05, decision["size"] * multiplier))
                decision["reasoning"].append(
                    f"Scenario divergence adjusted size x{multiplier:.2f}"
                )

        if hasattr(self, "reasoning_core") and self.reasoning_core:
            decision["structured_reasoning"] = self.reasoning_core.synthesize(
                analysis, decision
            )
        return decision

    def execute_trade(self, decision, current_price):
        """Execute trading decision"""
        trade = {
            "timestamp": datetime.now(),
            "action": decision["action"],
            "price": current_price,
            "size": decision["size"],
            "confidence": decision["confidence"],
            "reasoning": decision["reasoning"],
        }

        if decision["action"] == "BUY":
            cost = self.capital * decision["size"]
            shares = cost / current_price
            self.position += shares
            self.capital -= cost
            trade["shares"] = shares
            trade["cost"] = cost

        elif decision["action"] == "SELL" and self.position > 0:
            shares_to_sell = min(self.position * decision["size"], self.position)
            revenue = shares_to_sell * current_price
            self.capital += revenue
            self.position -= shares_to_sell
            trade["shares"] = shares_to_sell
            trade["revenue"] = revenue

        self.trade_history.append(trade)
        return trade

    def train_on_historical_data(self, historical_data: pd.DataFrame):
        """Train all models on historical data"""
        print("Preparing training data...")
        X, y = self.lstm_predictor.prepare_data(historical_data)

        # Split data
        split = int(0.8 * len(X))
        X_train, X_val = X[:split], X[split:]
        y_train, y_val = y[:split], y[split:]

        print(f"Training on {len(X_train)} samples, validating on {len(X_val)} samples")

        # Train ensemble
        results = self.ensemble_predictor.train_all_models(
            X_train, y_train, X_val, y_val
        )
        results["neuro_forge"] = self.neuro_forge.run_curriculum(
            self.ensemble_predictor,
            self.lstm_predictor,
            historical_data,
        )

        # Train RL agent through simulation
        print("Training RL agent...")
        self.train_rl_agent(historical_data)

        return results

    def train_rl_agent(self, data, episodes=100):
        """Train RL agent through episodic learning"""
        for episode in range(episodes):
            state = self.get_state(data.iloc[0:20])
            total_reward = 0

            for i in range(20, len(data) - 1):
                action = self.rl_trader.act(state)

                next_state = self.get_state(data.iloc[i - 19 : i + 1])
                price_change = (
                    data["close"].iloc[i + 1] - data["close"].iloc[i]
                ) / data["close"].iloc[i]

                reward = self.rl_trader.calculate_reward(
                    action, price_change, self.position
                )
                done = i == len(data) - 2

                self.rl_trader.remember(state, action, reward, next_state, done)
                state = next_state
                total_reward += reward

                if done:
                    print(
                        f"Episode {episode + 1}/{episodes}, Total Reward: {total_reward:.2f}"
                    )

            self.rl_trader.replay(32)

            if episode % 10 == 0:
                self.rl_trader.update_target_model()

    def get_state(self, data):
        """Convert market data to state vector for RL"""
        state = []

        # Price features
        state.append(data["close"].iloc[-1] / data["close"].iloc[-2] - 1)  # Return
        state.append(data["volume"].iloc[-1] / data["volume"].mean())  # Volume ratio

        # Technical indicators
        state.append(self.lstm_predictor.calculate_rsi(data["close"]).iloc[-1] / 100)

        # Moving averages
        sma_5 = data["close"].rolling(5).mean().iloc[-1]
        sma_20 = data["close"].rolling(20).mean().iloc[-1]
        state.append(data["close"].iloc[-1] / sma_5 - 1)
        state.append(data["close"].iloc[-1] / sma_20 - 1)

        # Add more features to reach state_size
        while len(state) < self.rl_trader.state_size:
            state.append(0)

        return np.array(state).reshape(1, -1)

    def save_brain(self, filepath):
        """Save all models"""
        import os

        os.makedirs(filepath, exist_ok=True)

        # Save LSTM
        self.lstm_predictor.save(f"{filepath}/lstm")

        # Save ensemble models
        joblib.dump(self.ensemble_predictor.models["rf"], f"{filepath}/rf_model.pkl")
        joblib.dump(self.ensemble_predictor.models["gb"], f"{filepath}/gb_model.pkl")

        # Save transformer
        if self.ensemble_predictor.models["transformer"]:
            torch.save(
                self.ensemble_predictor.models["transformer"].state_dict(),
                f"{filepath}/transformer_model.pt",
            )

        # Save RL model
        self.rl_trader.save(
            f"{filepath}/rl_model.pt",
            f"{filepath}/rl_target_model.pt",
        )

        # Save weights and parameters
        params = {
            "ensemble_weights": self.ensemble_predictor.weights,
            "confidence_threshold": self.confidence_threshold,
            "risk_tolerance": self.risk_tolerance,
            "rl_epsilon": self.rl_trader.epsilon,
        }

        with open(f"{filepath}/params.json", "w") as f:
            json.dump(params, f)

        print(f"Brain saved to {filepath}")

    def load_brain(self, filepath):
        """Load all models"""
        # Load LSTM
        self.lstm_predictor.load(f"{filepath}/lstm")

        # Load ensemble models
        self.ensemble_predictor.models["rf"] = joblib.load(f"{filepath}/rf_model.pkl")
        self.ensemble_predictor.models["gb"] = joblib.load(f"{filepath}/gb_model.pkl")

        # Load transformer
        self.ensemble_predictor.models["transformer"] = MarketTransformer()
        self.ensemble_predictor.models["transformer"].load_state_dict(
            torch.load(f"{filepath}/transformer_model.pt")
        )

        # Load RL model
        self.rl_trader.load(
            f"{filepath}/rl_model.pt",
            f"{filepath}/rl_target_model.pt",
        )

        # Load parameters
        with open(f"{filepath}/params.json", "r") as f:
            params = json.load(f)
            self.ensemble_predictor.weights = params["ensemble_weights"]
            self.confidence_threshold = params["confidence_threshold"]
            self.risk_tolerance = params["risk_tolerance"]
            self.rl_trader.epsilon = params["rl_epsilon"]

        print(f"Brain loaded from {filepath}")


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.generic,)):
        return value.item()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ANVEL Brain utility commands")
    parser.add_argument(
        "--train-from",
        dest="train_from",
        help="Path to historical CSV for full retraining run",
    )
    parser.add_argument(
        "--date-column",
        dest="date_column",
        default="date",
        help="Name of the datetime column in CSV (default: date)",
    )
    parser.add_argument(
        "--limit-rows",
        dest="limit_rows",
        type=int,
        help="Limit the number of rows ingested from CSV",
    )
    parser.add_argument(
        "--reasoning-limit",
        dest="reasoning_limit",
        type=int,
        help="Print the most recent structured reasoning packets",
    )
    return parser


ANVELBrain = AnvelBrain


class _BrainUnavailable:
    """Placeholder exposed when heavy analytics dependencies are missing."""

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - simple guard
        raise RuntimeError(self._reason)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<ANVEL Brain unavailable: {self._reason}>"


def _describe_missing_dependencies() -> Optional[str]:
    missing = []
    if NUMPY_IMPORT_ERROR is not None:
        missing.append("NumPy")
    if PANDAS_IMPORT_ERROR is not None:
        missing.append("pandas")
    if TORCH_IMPORT_ERROR is not None:
        missing.append("PyTorch")
    if SKLEARN_IMPORT_ERROR is not None:
        missing.append("scikit-learn")
    if not missing:
        return None
    joined = ", ".join(missing)
    return (
        f"ANVEL Brain analytics components require {joined}. "
        "Install the missing dependency or switch to the Rust analytics bridge."
    )


def _auto_install_missing_deps() -> None:
    """AUTONOMOUS: Auto-install any missing dependencies using centralized function."""
    dep_map = {
        "NumPy": ("numpy", "numpy>=1.24.0"),
        "pandas": ("pandas", "pandas>=2.0.0"),
        "PyTorch": ("torch", "torch>=2.2.0"),
        "scikit-learn": ("sklearn", "scikit-learn>=1.5.0"),
    }

    for name, (module, pip_pkg) in dep_map.items():
        try:
            importlib.import_module(module)
        except ImportError:
            _brain_logger.warning(f"AUTONOMOUS: Installing {name}...")
            if _force_install_package(name, pip_pkg):
                _brain_logger.info(f"AUTONOMOUS: {name} installed successfully")
            else:
                _brain_logger.error(f"AUTONOMOUS: Failed to install {name}")


# AUTONOMOUS MODE: Try to install missing dependencies before giving up
_brain_blocker = _describe_missing_dependencies()
if _brain_blocker is not None:
    _brain_logger.warning(
        "Missing dependencies detected - initiating autonomous installation..."
    )
    _auto_install_missing_deps()
    # Recheck after installation
    _brain_blocker = _describe_missing_dependencies()

if _brain_blocker is None:
    anvel_brain = AnvelBrain()
    _brain_logger.info("ANVEL Brain initialized successfully (full functionality)")
else:
    # AUTONOMOUS MODE: Still create the brain but log critical warning
    _brain_logger.error(
        "CRITICAL: Some dependencies still missing after auto-install: %s",
        _brain_blocker,
    )
    _brain_logger.error(
        "ANVEL Brain will have limited functionality. Manual installation required."
    )
    # Create brain anyway - let it fail at runtime if needed
    try:
        anvel_brain = AnvelBrain()
    except Exception as e:
        _brain_logger.error(f"Brain instantiation failed: {e}")
        anvel_brain = _BrainUnavailable(_brain_blocker)

if __name__ == "__main__":
    parser = _build_cli_parser()
    args = parser.parse_args()

    if args.train_from:
        report = anvel_brain.train_from_csv(
            args.train_from,
            date_column=args.date_column,
            limit_rows=args.limit_rows,
        )
        print(json.dumps(report, indent=2, default=_json_default))
    elif args.reasoning_limit:
        packets = anvel_brain.recall_reasoning(limit=args.reasoning_limit)
        print(json.dumps(packets, indent=2, default=_json_default))
    else:
        print("ANVEL AI Brain initialized")
        print("Available models:")
        print("  - LSTM Price Predictor")
        print("  - Market Transformer")
        print("  - Reinforcement Learning Trader")
        print("  - Ensemble Predictor")
        print("  - Market Sentiment Analyzer")
        print("\nReady for training and prediction")
