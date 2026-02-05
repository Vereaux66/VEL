#!/usr/bin/env python3
"""
ANVEL Dependency Utilities

Centralized module for handling optional dependencies with graceful fallbacks.
Provides consistent patterns for numpy, pandas, sklearn, and other optional
dependencies across the ANVEL codebase.

Usage:
    from anvel_dependency_utils import np, pd, get_numpy, get_pandas, is_numpy_available

    # Use with fallback
    result = np.mean([1, 2, 3])  # Works whether numpy is installed or not

    # Check availability
    if is_numpy_available():
        import numpy as real_np
        # Use numpy-specific features
"""

from __future__ import annotations

import logging
import math
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

log = logging.getLogger(__name__)

# Type variables for generic functions
T = TypeVar("T")
NumericSequence = Union[List[float], List[int], Tuple[float, ...], Tuple[int, ...]]


# =============================================================================
# Availability Flags
# =============================================================================

_NUMPY_AVAILABLE: Optional[bool] = None
_PANDAS_AVAILABLE: Optional[bool] = None
_SKLEARN_AVAILABLE: Optional[bool] = None
_SCIPY_AVAILABLE: Optional[bool] = None
_TORCH_AVAILABLE: Optional[bool] = None


def is_numpy_available() -> bool:
    """Check if numpy is available."""
    global _NUMPY_AVAILABLE
    if _NUMPY_AVAILABLE is None:
        try:
            import numpy  # noqa: F401
            _NUMPY_AVAILABLE = True
        except ImportError:
            _NUMPY_AVAILABLE = False
    return _NUMPY_AVAILABLE


def is_pandas_available() -> bool:
    """Check if pandas is available."""
    global _PANDAS_AVAILABLE
    if _PANDAS_AVAILABLE is None:
        try:
            import pandas  # noqa: F401
            _PANDAS_AVAILABLE = True
        except ImportError:
            _PANDAS_AVAILABLE = False
    return _PANDAS_AVAILABLE


def is_sklearn_available() -> bool:
    """Check if scikit-learn is available."""
    global _SKLEARN_AVAILABLE
    if _SKLEARN_AVAILABLE is None:
        try:
            import sklearn  # noqa: F401
            _SKLEARN_AVAILABLE = True
        except ImportError:
            _SKLEARN_AVAILABLE = False
    return _SKLEARN_AVAILABLE


def is_scipy_available() -> bool:
    """Check if scipy is available."""
    global _SCIPY_AVAILABLE
    if _SCIPY_AVAILABLE is None:
        try:
            import scipy  # noqa: F401
            _SCIPY_AVAILABLE = True
        except ImportError:
            _SCIPY_AVAILABLE = False
    return _SCIPY_AVAILABLE


def is_torch_available() -> bool:
    """Check if PyTorch is available."""
    global _TORCH_AVAILABLE
    if _TORCH_AVAILABLE is None:
        try:
            import torch  # noqa: F401
            _TORCH_AVAILABLE = True
        except ImportError:
            _TORCH_AVAILABLE = False
    return _TORCH_AVAILABLE


# =============================================================================
# Numpy Fallback Implementation
# =============================================================================

class NumpyFallback:
    """
    Pure Python fallback for numpy functions.

    Provides basic numpy-like functionality when numpy is not installed.
    This allows ANVEL to function in minimal environments.
    """

    @staticmethod
    def mean(a: NumericSequence) -> float:
        """Calculate arithmetic mean."""
        if not a:
            return 0.0
        return sum(a) / len(a)

    @staticmethod
    def std(a: NumericSequence, ddof: int = 0) -> float:
        """
        Calculate standard deviation.

        Args:
            a: Input sequence
            ddof: Delta degrees of freedom (0 for population, 1 for sample)
        """
        if not a or len(a) <= ddof:
            return 0.0
        m = sum(a) / len(a)
        variance = sum((x - m) ** 2 for x in a) / (len(a) - ddof)
        return math.sqrt(variance)

    @staticmethod
    def var(a: NumericSequence, ddof: int = 0) -> float:
        """Calculate variance."""
        if not a or len(a) <= ddof:
            return 0.0
        m = sum(a) / len(a)
        return sum((x - m) ** 2 for x in a) / (len(a) - ddof)

    @staticmethod
    def diff(a: NumericSequence) -> List[float]:
        """Calculate first-order differences."""
        if len(a) < 2:
            return []
        return [float(a[i + 1]) - float(a[i]) for i in range(len(a) - 1)]

    @staticmethod
    def sign(x: float) -> int:
        """Return the sign of a number."""
        if x > 0:
            return 1
        elif x < 0:
            return -1
        return 0

    @staticmethod
    def abs(x: Union[float, int, NumericSequence]) -> Union[float, List[float]]:
        """Return absolute value(s)."""
        if isinstance(x, (list, tuple)):
            return [abs(v) for v in x]
        return abs(x)

    @staticmethod
    def sum(a: NumericSequence) -> float:
        """Sum of elements."""
        return float(sum(a))

    @staticmethod
    def min(a: NumericSequence) -> float:
        """Minimum value."""
        if not a:
            raise ValueError("zero-size array to reduction operation minimum")
        return float(min(a))

    @staticmethod
    def max(a: NumericSequence) -> float:
        """Maximum value."""
        if not a:
            raise ValueError("zero-size array to reduction operation maximum")
        return float(max(a))

    @staticmethod
    def argmin(a: NumericSequence) -> int:
        """Index of minimum value."""
        if not a:
            raise ValueError("attempt to get argmin of an empty sequence")
        return min(range(len(a)), key=lambda i: a[i])

    @staticmethod
    def argmax(a: NumericSequence) -> int:
        """Index of maximum value."""
        if not a:
            raise ValueError("attempt to get argmax of an empty sequence")
        return max(range(len(a)), key=lambda i: a[i])

    @staticmethod
    def percentile(a: NumericSequence, q: float) -> float:
        """
        Calculate the q-th percentile of the data.

        Args:
            a: Input sequence
            q: Percentile (0-100)
        """
        if not a:
            raise ValueError("zero-size array to percentile")
        sorted_a = sorted(a)
        k = (len(sorted_a) - 1) * (q / 100)
        f = int(k)
        c = f + 1
        if c >= len(sorted_a):
            return float(sorted_a[-1])
        return float(sorted_a[f]) + (k - f) * (float(sorted_a[c]) - float(sorted_a[f]))

    @staticmethod
    def median(a: NumericSequence) -> float:
        """Calculate median value."""
        if not a:
            raise ValueError("zero-size array to median")
        return NumpyFallback.percentile(a, 50)

    @staticmethod
    def cumsum(a: NumericSequence) -> List[float]:
        """Cumulative sum."""
        result = []
        total = 0.0
        for x in a:
            total += float(x)
            result.append(total)
        return result

    @staticmethod
    def cumprod(a: NumericSequence) -> List[float]:
        """Cumulative product."""
        result = []
        total = 1.0
        for x in a:
            total *= float(x)
            result.append(total)
        return result

    @staticmethod
    def exp(x: Union[float, NumericSequence]) -> Union[float, List[float]]:
        """Exponential function."""
        if isinstance(x, (list, tuple)):
            return [math.exp(v) for v in x]
        return math.exp(x)

    @staticmethod
    def log(x: Union[float, NumericSequence]) -> Union[float, List[float]]:
        """Natural logarithm."""
        if isinstance(x, (list, tuple)):
            return [math.log(v) if v > 0 else float('-inf') for v in x]
        return math.log(x) if x > 0 else float('-inf')

    @staticmethod
    def sqrt(x: Union[float, NumericSequence]) -> Union[float, List[float]]:
        """Square root."""
        if isinstance(x, (list, tuple)):
            return [math.sqrt(v) if v >= 0 else float('nan') for v in x]
        return math.sqrt(x) if x >= 0 else float('nan')

    @staticmethod
    def clip(
        a: NumericSequence, a_min: Optional[float], a_max: Optional[float]
    ) -> List[float]:
        """Clip values to a range."""
        result = []
        for x in a:
            val = float(x)
            if a_min is not None and val < a_min:
                val = a_min
            if a_max is not None and val > a_max:
                val = a_max
            result.append(val)
        return result

    @staticmethod
    def zeros(shape: Union[int, Tuple[int, ...]]) -> Union[List[float], List[List[float]]]:
        """Create array of zeros."""
        if isinstance(shape, int):
            return [0.0] * shape
        if len(shape) == 1:
            return [0.0] * shape[0]
        if len(shape) == 2:
            return [[0.0] * shape[1] for _ in range(shape[0])]
        raise ValueError("Only 1D and 2D arrays supported in fallback")

    @staticmethod
    def ones(shape: Union[int, Tuple[int, ...]]) -> Union[List[float], List[List[float]]]:
        """Create array of ones."""
        if isinstance(shape, int):
            return [1.0] * shape
        if len(shape) == 1:
            return [1.0] * shape[0]
        if len(shape) == 2:
            return [[1.0] * shape[1] for _ in range(shape[0])]
        raise ValueError("Only 1D and 2D arrays supported in fallback")

    @staticmethod
    def linspace(start: float, stop: float, num: int = 50) -> List[float]:
        """Generate evenly spaced values."""
        if num <= 0:
            return []
        if num == 1:
            return [start]
        step = (stop - start) / (num - 1)
        return [start + i * step for i in range(num)]

    @staticmethod
    def arange(
        start: float, stop: Optional[float] = None, step: float = 1.0
    ) -> List[float]:
        """Generate range of values."""
        if stop is None:
            stop = start
            start = 0.0
        result = []
        current = start
        while current < stop:
            result.append(current)
            current += step
        return result

    @staticmethod
    def where(
        condition: List[bool],
        x: NumericSequence,
        y: NumericSequence,
    ) -> List[float]:
        """Conditional selection."""
        if len(condition) != len(x) or len(condition) != len(y):
            raise ValueError("All arrays must have the same length")
        return [float(x[i]) if c else float(y[i]) for i, c in enumerate(condition)]

    @staticmethod
    def dot(a: NumericSequence, b: NumericSequence) -> float:
        """Dot product of two vectors."""
        if len(a) != len(b):
            raise ValueError("Vectors must have the same length")
        return sum(float(a[i]) * float(b[i]) for i in range(len(a)))

    @staticmethod
    def corrcoef(x: NumericSequence, y: NumericSequence) -> float:
        """
        Calculate Pearson correlation coefficient between x and y.

        Returns a single value (correlation between x and y).
        """
        if len(x) != len(y):
            raise ValueError("x and y must have the same length")
        n = len(x)
        if n < 2:
            return float('nan')

        x_mean = sum(x) / n
        y_mean = sum(y) / n

        numerator = sum((float(x[i]) - x_mean) * (float(y[i]) - y_mean) for i in range(n))
        x_var = sum((float(x[i]) - x_mean) ** 2 for i in range(n))
        y_var = sum((float(y[i]) - y_mean) ** 2 for i in range(n))

        denominator = math.sqrt(x_var * y_var)
        if denominator == 0:
            return float('nan')

        return numerator / denominator


# =============================================================================
# Pandas Fallback Implementation
# =============================================================================

class PandasFallback:
    """
    Minimal pandas fallback for basic operations.

    Provides limited pandas-like functionality when pandas is not installed.
    """

    @staticmethod
    def Series(data: List[Any], index: Optional[List[Any]] = None) -> Dict[Any, Any]:
        """Create a simple series-like dict."""
        if index is None:
            index = list(range(len(data)))
        return dict(zip(index, data))

    @staticmethod
    def DataFrame(
        data: Dict[str, List[Any]], index: Optional[List[Any]] = None
    ) -> Dict[str, Dict[Any, Any]]:
        """Create a simple dataframe-like nested dict."""
        result = {}
        first_key = next(iter(data.keys()), None)
        length = len(data[first_key]) if first_key else 0

        if index is None:
            index = list(range(length))

        for col, values in data.items():
            result[col] = dict(zip(index, values))

        return result

    @staticmethod
    def rolling_mean(data: NumericSequence, window: int) -> List[Optional[float]]:
        """Calculate rolling mean."""
        result: List[Optional[float]] = []
        for i in range(len(data)):
            if i < window - 1:
                result.append(None)
            else:
                window_data = data[i - window + 1:i + 1]
                result.append(sum(window_data) / window)
        return result

    @staticmethod
    def rolling_std(data: NumericSequence, window: int) -> List[Optional[float]]:
        """Calculate rolling standard deviation."""
        result: List[Optional[float]] = []
        for i in range(len(data)):
            if i < window - 1:
                result.append(None)
            else:
                window_data = data[i - window + 1:i + 1]
                mean = sum(window_data) / window
                variance = sum((x - mean) ** 2 for x in window_data) / window
                result.append(math.sqrt(variance))
        return result


# =============================================================================
# Module-Level Exports
# =============================================================================

# Get numpy (real or fallback)
def get_numpy() -> Union[Any, Type[NumpyFallback]]:
    """
    Get numpy module or fallback.

    Returns:
        numpy module if available, otherwise NumpyFallback class
    """
    if is_numpy_available():
        import numpy
        return numpy
    return NumpyFallback


def get_pandas() -> Union[Any, Type[PandasFallback]]:
    """
    Get pandas module or fallback.

    Returns:
        pandas module if available, otherwise PandasFallback class
    """
    if is_pandas_available():
        import pandas
        return pandas
    return PandasFallback


def require_numpy(feature_name: str = "This feature") -> Any:
    """
    Require numpy to be available.

    Args:
        feature_name: Name of the feature requiring numpy

    Raises:
        RuntimeError: If numpy is not available

    Returns:
        numpy module
    """
    if not is_numpy_available():
        raise RuntimeError(
            f"{feature_name} requires numpy. Install with: pip install numpy"
        )
    import numpy
    return numpy


def require_pandas(feature_name: str = "This feature") -> Any:
    """
    Require pandas to be available.

    Args:
        feature_name: Name of the feature requiring pandas

    Raises:
        RuntimeError: If pandas is not available

    Returns:
        pandas module
    """
    if not is_pandas_available():
        raise RuntimeError(
            f"{feature_name} requires pandas. Install with: pip install pandas"
        )
    import pandas
    return pandas


def require_sklearn(feature_name: str = "This feature") -> Any:
    """
    Require scikit-learn to be available.

    Args:
        feature_name: Name of the feature requiring sklearn

    Raises:
        RuntimeError: If sklearn is not available

    Returns:
        sklearn module
    """
    if not is_sklearn_available():
        raise RuntimeError(
            f"{feature_name} requires scikit-learn. Install with: pip install scikit-learn"
        )
    import sklearn
    return sklearn


# Create module-level instances for convenience
np = get_numpy()
pd = get_pandas()


# =============================================================================
# Utility Functions
# =============================================================================

def safe_divide(
    numerator: float,
    denominator: float,
    default: float = 0.0,
) -> float:
    """
    Safely divide two numbers, returning default if denominator is zero.

    Args:
        numerator: The numerator
        denominator: The denominator
        default: Value to return if division is not possible

    Returns:
        Result of division or default value
    """
    if denominator == 0:
        return default
    return numerator / denominator


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    Clamp a value to a range.

    Args:
        value: Value to clamp
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Clamped value
    """
    return max(min_val, min(value, max_val))


def calculate_ema(
    data: NumericSequence,
    period: int,
    smoothing: float = 2.0,
) -> List[float]:
    """
    Calculate Exponential Moving Average.

    Args:
        data: Input price data
        period: EMA period
        smoothing: Smoothing factor (default 2.0)

    Returns:
        List of EMA values
    """
    if len(data) < period:
        return [sum(data) / len(data)] * len(data) if data else []

    multiplier = smoothing / (period + 1)
    ema_values = []

    # Start with SMA for first period
    sma = sum(data[:period]) / period
    ema_values.extend([sma] * period)

    # Calculate EMA for remaining values
    ema = sma
    for i in range(period, len(data)):
        ema = (float(data[i]) - ema) * multiplier + ema
        ema_values.append(ema)

    return ema_values


def calculate_sma(data: NumericSequence, period: int) -> List[Optional[float]]:
    """
    Calculate Simple Moving Average.

    Args:
        data: Input price data
        period: SMA period

    Returns:
        List of SMA values (None for insufficient data points)
    """
    result: List[Optional[float]] = []
    for i in range(len(data)):
        if i < period - 1:
            result.append(None)
        else:
            window = data[i - period + 1:i + 1]
            result.append(sum(window) / period)
    return result


def calculate_percentile_efficient(
    data: NumericSequence,
    percentile: float,
) -> float:
    """
    Calculate percentile using an efficient algorithm.

    Uses partial sorting for O(n) average case complexity
    instead of O(n log n) for full sort.

    Args:
        data: Input data
        percentile: Percentile to calculate (0-100)

    Returns:
        Percentile value
    """
    import heapq

    if not data:
        raise ValueError("Cannot calculate percentile of empty sequence")

    n = len(data)
    k = int(n * percentile / 100)
    k = min(k, n - 1)
    k = max(k, 0)

    # For small datasets, just sort
    if n <= 100:
        sorted_data = sorted(data)
        return float(sorted_data[k])

    # For larger datasets, use partial sorting via heapq
    # Get k+1 smallest elements
    smallest = heapq.nsmallest(k + 1, data)
    return float(smallest[-1])


# =============================================================================
# Dependency Status Report
# =============================================================================

def get_dependency_status() -> Dict[str, bool]:
    """
    Get status of all optional dependencies.

    Returns:
        Dictionary mapping dependency names to availability status
    """
    return {
        "numpy": is_numpy_available(),
        "pandas": is_pandas_available(),
        "sklearn": is_sklearn_available(),
        "scipy": is_scipy_available(),
        "torch": is_torch_available(),
    }


def log_dependency_status() -> None:
    """Log the status of all optional dependencies."""
    status = get_dependency_status()
    available = [name for name, avail in status.items() if avail]
    missing = [name for name, avail in status.items() if not avail]

    if available:
        log.info("Available dependencies: %s", ", ".join(available))
    if missing:
        log.info("Missing dependencies (using fallbacks): %s", ", ".join(missing))
