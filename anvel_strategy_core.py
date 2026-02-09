from anvel_dependency_utils import get_numpy

np = get_numpy()

from typing import Dict, Callable, Any, List, Tuple, Optional, Union
from dataclasses import dataclass
import time
import logging

logger = logging.getLogger("anvel.strategy")


@dataclass
class PatternMatch:
    """Represents a detected chart pattern"""
    pattern_type: str
    confidence: float
    direction: str  # 'bullish', 'bearish', 'neutral'
    price_target: Optional[float] = None
    stop_loss: Optional[float] = None
    description: str = ""


class PatternDiscoveryEngine:
    """
    Chart Pattern Discovery Engine
    
    Detects common chart patterns:
    - Head and Shoulders (bearish reversal)
    - Inverse Head and Shoulders (bullish reversal)
    - Double Top (bearish reversal)
    - Double Bottom (bullish reversal)
    - Triangle (continuation/breakout)
    - Cup and Handle (bullish continuation)
    - Wedge patterns (Rising/Falling)
    """

    def __init__(self, min_pattern_length: int = 10, tolerance: float = 0.02):
        """
        Initialize pattern discovery engine.
        
        Args:
            min_pattern_length: Minimum data points needed for pattern detection
            tolerance: Percentage tolerance for peak/trough matching
        """
        self.min_pattern_length = min_pattern_length
        self.tolerance = tolerance
        self.detected_patterns: List[PatternMatch] = []

    def _find_local_extrema(
        self, prices: List[float], window: int = 5
    ) -> Tuple[List[int], List[int]]:
        """
        Find local maxima and minima indices using an optimized sliding window approach.

        Uses a more efficient O(n) algorithm with early exit conditions.

        Args:
            prices: List of price values
            window: Half-window size for detecting extrema

        Returns:
            Tuple of (peak_indices, trough_indices)
        """
        peaks: List[int] = []
        troughs: List[int] = []

        n = len(prices)
        if n < window * 2 + 1:
            return peaks, troughs

        for i in range(window, n - window):
            current = prices[i]
            is_peak = True
            is_trough = True

            # Check neighbors with early exit optimization
            for j in range(1, window + 1):
                left = prices[i - j]
                right = prices[i + j]

                # For peaks: current must be >= all neighbors
                if current < left or current < right:
                    is_peak = False
                # For troughs: current must be <= all neighbors
                if current > left or current > right:
                    is_trough = False

                # Early exit if neither peak nor trough
                if not is_peak and not is_trough:
                    break

            if is_peak:
                peaks.append(i)
            elif is_trough:
                troughs.append(i)

        return peaks, troughs

    def _prices_approximately_equal(self, p1: float, p2: float) -> bool:
        """Check if two prices are approximately equal within tolerance"""
        if p1 == 0:
            return abs(p2) < self.tolerance
        return abs(p1 - p2) / p1 <= self.tolerance

    def detect_head_and_shoulders(
        self, prices: List[float]
    ) -> Optional[PatternMatch]:
        """
        Detect Head and Shoulders pattern (bearish reversal).
        
        Pattern: Left shoulder, head (higher), right shoulder (similar to left)
        """
        if len(prices) < self.min_pattern_length:
            return None

        peaks, troughs = self._find_local_extrema(prices, window=3)

        if len(peaks) < 3 or len(troughs) < 2:
            return None

        # Look for pattern in recent peaks
        for i in range(len(peaks) - 2):
            left_shoulder = prices[peaks[i]]
            head = prices[peaks[i + 1]]
            right_shoulder = prices[peaks[i + 2]]

            # Head should be higher than shoulders
            # Shoulders should be approximately equal
            if (head > left_shoulder and head > right_shoulder and
                self._prices_approximately_equal(left_shoulder, right_shoulder)):

                # Find neckline (troughs between peaks)
                neckline_troughs = [t for t in troughs if peaks[i] < t < peaks[i + 2]]
                if len(neckline_troughs) >= 2:
                    neckline = (prices[neckline_troughs[0]] + prices[neckline_troughs[-1]]) / 2
                    current_price = prices[-1]

                    # Pattern confirmed if price breaks below neckline
                    if current_price < neckline:
                        pattern_height = head - neckline
                        price_target = neckline - pattern_height

                        confidence = min(0.9, 0.6 + (head - left_shoulder) / head * 2)

                        return PatternMatch(
                            pattern_type="head_and_shoulders",
                            confidence=confidence,
                            direction="bearish",
                            price_target=price_target,
                            stop_loss=head * 1.01,
                            description=f"H&S pattern with head at {head:.2f}, neckline at {neckline:.2f}"
                        )

        return None

    def detect_inverse_head_and_shoulders(
        self, prices: List[float]
    ) -> Optional[PatternMatch]:
        """
        Detect Inverse Head and Shoulders pattern (bullish reversal).
        
        Pattern: Left shoulder (trough), head (lower trough), right shoulder (trough)
        """
        if len(prices) < self.min_pattern_length:
            return None

        peaks, troughs = self._find_local_extrema(prices, window=3)

        if len(troughs) < 3 or len(peaks) < 2:
            return None

        for i in range(len(troughs) - 2):
            left_shoulder = prices[troughs[i]]
            head = prices[troughs[i + 1]]
            right_shoulder = prices[troughs[i + 2]]

            # Head should be lower than shoulders
            if (head < left_shoulder and head < right_shoulder and
                self._prices_approximately_equal(left_shoulder, right_shoulder)):

                neckline_peaks = [p for p in peaks if troughs[i] < p < troughs[i + 2]]
                if len(neckline_peaks) >= 2:
                    neckline = (prices[neckline_peaks[0]] + prices[neckline_peaks[-1]]) / 2
                    current_price = prices[-1]

                    if current_price > neckline:
                        pattern_height = neckline - head
                        price_target = neckline + pattern_height

                        confidence = min(0.9, 0.6 + (left_shoulder - head) / left_shoulder * 2)

                        return PatternMatch(
                            pattern_type="inverse_head_and_shoulders",
                            confidence=confidence,
                            direction="bullish",
                            price_target=price_target,
                            stop_loss=head * 0.99,
                            description=f"Inverse H&S with head at {head:.2f}, neckline at {neckline:.2f}"
                        )

        return None

    def detect_double_top(self, prices: List[float]) -> Optional[PatternMatch]:
        """
        Detect Double Top pattern (bearish reversal).
        
        Pattern: Two peaks at approximately same level with trough between
        """
        if len(prices) < self.min_pattern_length:
            return None

        peaks, troughs = self._find_local_extrema(prices, window=3)

        if len(peaks) < 2:
            return None

        for i in range(len(peaks) - 1):
            peak1 = prices[peaks[i]]
            peak2 = prices[peaks[i + 1]]

            if self._prices_approximately_equal(peak1, peak2):
                # Find trough between peaks
                between_troughs = [t for t in troughs if peaks[i] < t < peaks[i + 1]]
                if between_troughs:
                    trough = prices[min(between_troughs, key=lambda t: prices[t])]
                    current_price = prices[-1]

                    if current_price < trough:
                        pattern_height = ((peak1 + peak2) / 2) - trough
                        price_target = trough - pattern_height

                        return PatternMatch(
                            pattern_type="double_top",
                            confidence=0.75,
                            direction="bearish",
                            price_target=price_target,
                            stop_loss=max(peak1, peak2) * 1.01,
                            description=f"Double top at {(peak1+peak2)/2:.2f}, support broken at {trough:.2f}"
                        )

        return None

    def detect_double_bottom(self, prices: List[float]) -> Optional[PatternMatch]:
        """
        Detect Double Bottom pattern (bullish reversal).
        
        Pattern: Two troughs at approximately same level with peak between
        """
        if len(prices) < self.min_pattern_length:
            return None

        peaks, troughs = self._find_local_extrema(prices, window=3)

        if len(troughs) < 2:
            return None

        for i in range(len(troughs) - 1):
            trough1 = prices[troughs[i]]
            trough2 = prices[troughs[i + 1]]

            if self._prices_approximately_equal(trough1, trough2):
                between_peaks = [p for p in peaks if troughs[i] < p < troughs[i + 1]]
                if between_peaks:
                    peak = prices[max(between_peaks, key=lambda p: prices[p])]
                    current_price = prices[-1]

                    if current_price > peak:
                        pattern_height = peak - ((trough1 + trough2) / 2)
                        price_target = peak + pattern_height

                        return PatternMatch(
                            pattern_type="double_bottom",
                            confidence=0.75,
                            direction="bullish",
                            price_target=price_target,
                            stop_loss=min(trough1, trough2) * 0.99,
                            description=f"Double bottom at {(trough1+trough2)/2:.2f}, resistance broken at {peak:.2f}"
                        )

        return None

    def detect_triangle(self, prices: List[float]) -> Optional[PatternMatch]:
        """
        Detect Triangle patterns (ascending, descending, symmetric).
        
        Triangles indicate consolidation before breakout.
        """
        if len(prices) < self.min_pattern_length + 5:
            return None

        peaks, troughs = self._find_local_extrema(prices, window=2)

        if len(peaks) < 2 or len(troughs) < 2:
            return None

        # Get recent peaks and troughs
        recent_peaks = sorted(peaks[-4:])
        recent_troughs = sorted(troughs[-4:])

        if len(recent_peaks) < 2 or len(recent_troughs) < 2:
            return None

        # Calculate trend lines
        peak_prices = [prices[p] for p in recent_peaks]
        trough_prices = [prices[t] for t in recent_troughs]

        peak_slope = (peak_prices[-1] - peak_prices[0]) / max(1, recent_peaks[-1] - recent_peaks[0])
        trough_slope = (trough_prices[-1] - trough_prices[0]) / max(1, recent_troughs[-1] - recent_troughs[0])

        current_price = prices[-1]

        # Ascending triangle: flat top, rising bottom
        if abs(peak_slope) < 0.001 and trough_slope > 0.001:
            if current_price > peak_prices[-1]:
                return PatternMatch(
                    pattern_type="ascending_triangle",
                    confidence=0.7,
                    direction="bullish",
                    price_target=peak_prices[-1] + (peak_prices[-1] - trough_prices[0]),
                    description="Ascending triangle breakout"
                )

        # Descending triangle: flat bottom, falling top
        elif abs(trough_slope) < 0.001 and peak_slope < -0.001:
            if current_price < trough_prices[-1]:
                return PatternMatch(
                    pattern_type="descending_triangle",
                    confidence=0.7,
                    direction="bearish",
                    price_target=trough_prices[-1] - (peak_prices[0] - trough_prices[-1]),
                    description="Descending triangle breakdown"
                )

        # Symmetric triangle: converging trend lines
        elif peak_slope < 0 and trough_slope > 0:
            apex = (peak_prices[-1] + trough_prices[-1]) / 2
            height = peak_prices[0] - trough_prices[0]

            if current_price > peak_prices[-1]:
                return PatternMatch(
                    pattern_type="symmetric_triangle_bullish",
                    confidence=0.65,
                    direction="bullish",
                    price_target=apex + height,
                    description="Symmetric triangle bullish breakout"
                )
            elif current_price < trough_prices[-1]:
                return PatternMatch(
                    pattern_type="symmetric_triangle_bearish",
                    confidence=0.65,
                    direction="bearish",
                    price_target=apex - height,
                    description="Symmetric triangle bearish breakdown"
                )

        return None

    def detect_wedge(self, prices: List[float]) -> Optional[PatternMatch]:
        """
        Detect Rising and Falling Wedge patterns.
        
        Rising Wedge: Bearish reversal
        Falling Wedge: Bullish reversal
        """
        if len(prices) < self.min_pattern_length + 5:
            return None

        peaks, troughs = self._find_local_extrema(prices, window=2)

        if len(peaks) < 3 or len(troughs) < 3:
            return None

        peak_prices = [prices[p] for p in peaks[-3:]]
        trough_prices = [prices[t] for t in troughs[-3:]]

        # Both lines must be sloping in same direction for wedge
        peak_rising = peak_prices[-1] > peak_prices[0]
        trough_rising = trough_prices[-1] > trough_prices[0]

        # Check for converging lines
        high_range = peak_prices[-1] - trough_prices[-1]
        low_range = peak_prices[0] - trough_prices[0]
        converging = high_range < low_range

        current_price = prices[-1]

        # Rising Wedge (bearish)
        if peak_rising and trough_rising and converging:
            if current_price < trough_prices[-1]:
                return PatternMatch(
                    pattern_type="rising_wedge",
                    confidence=0.7,
                    direction="bearish",
                    price_target=trough_prices[0],
                    description="Rising wedge breakdown - bearish reversal"
                )

        # Falling Wedge (bullish)
        elif not peak_rising and not trough_rising and converging:
            if current_price > peak_prices[-1]:
                return PatternMatch(
                    pattern_type="falling_wedge",
                    confidence=0.7,
                    direction="bullish",
                    price_target=peak_prices[0],
                    description="Falling wedge breakout - bullish reversal"
                )

        return None

    def discover_patterns(self, prices: List[float]) -> List[PatternMatch]:
        """
        Run all pattern detection algorithms and return discovered patterns.
        
        Args:
            prices: List of price data
            
        Returns:
            List of detected patterns sorted by confidence
        """
        if len(prices) < self.min_pattern_length:
            return []

        patterns = []

        # Run all detection algorithms
        detectors = [
            self.detect_head_and_shoulders,
            self.detect_inverse_head_and_shoulders,
            self.detect_double_top,
            self.detect_double_bottom,
            self.detect_triangle,
            self.detect_wedge,
        ]

        for detector in detectors:
            try:
                pattern = detector(prices)
                if pattern is not None:
                    patterns.append(pattern)
            except (ValueError, IndexError, TypeError, ZeroDivisionError) as e:
                logger.warning("Pattern detection error in %s: %s", detector.__name__, e)
            except RuntimeError as e:
                logger.error("Runtime error in %s: %s", detector.__name__, e)

        # Sort by confidence
        patterns.sort(key=lambda p: p.confidence, reverse=True)
        self.detected_patterns = patterns

        return patterns

    def get_trading_signal(self, prices: List[float]) -> float:
        """
        Get aggregate trading signal from discovered patterns.
        
        Returns:
            Float between -1 (strong sell) and 1 (strong buy)
        """
        patterns = self.discover_patterns(prices)

        if not patterns:
            return 0.0

        # Weighted average of pattern signals
        total_weight = 0.0
        weighted_signal = 0.0

        for pattern in patterns:
            weight = pattern.confidence
            if pattern.direction == "bullish":
                signal = weight
            elif pattern.direction == "bearish":
                signal = -weight
            else:
                signal = 0.0

            weighted_signal += signal * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        return weighted_signal / total_weight


class ANVELStrategyCore:
    """
    Advanced Strategy Core with Technical Indicators and Pattern Discovery
    
    Features:
    - 6 built-in trading strategies
    - MACD, RSI, and other technical indicators
    - Pattern discovery engine for chart patterns
    - Ensemble decision making
    """

    def __init__(self):
        """Initialize strategy core with all components"""
        self.strategies: Dict[str, Callable] = {}
        self.weights: Dict[str, float] = {}
        self.execution_log: List[Tuple[str, float, float]] = []
        self.performance_tracker: Dict[str, Dict[str, Any]] = {}
        self.pattern_discovery = PatternDiscoveryEngine()
        self._register_builtin_strategies()

    def _register_builtin_strategies(self):
        """Register advanced built-in trading strategies"""
        self.register("momentum_advanced", self._momentum_strategy)
        self.register("mean_reversion_ml", self._mean_reversion_ml)
        self.register("breakout_enhanced", self._breakout_strategy)
        self.register("volatility_adaptive", self._volatility_strategy)
        self.register("trend_following", self._trend_following)
        self.register("scalping_micro", self._scalping_strategy)
        self.register("high_win_rate_scalping", self._high_win_rate_scalping)
        # Enhanced strategies
        self.register("ichimoku_cloud", self._ichimoku_cloud_strategy)
        self.register("fibonacci_retracement", self._fibonacci_retracement_strategy)
        self.register("stochastic_oscillator", self._stochastic_oscillator_strategy)
        self.register("adx_trend_strength", self._adx_trend_strength_strategy)
        self.register("bollinger_squeeze", self._bollinger_squeeze_strategy)
        self.register("macd_divergence", self._macd_divergence_strategy)
        self.register("volume_profile", self._volume_profile_strategy)
        self.register("order_flow_imbalance", self._order_flow_imbalance_strategy)

        # Set equal weights initially
        for name in self.strategies:
            self.weights[name] = 1.0

    def _momentum_strategy(self, context: Dict[str, Any]) -> float:
        """Advanced momentum strategy with RSI and MACD"""
        prices = context.get("prices", [])
        if len(prices) < 26:  # Need enough data for MACD
            return 0.0

        # Calculate RSI
        rsi = self._calculate_rsi(prices)

        # Calculate MACD
        macd = self._calculate_macd(prices)
        macd_histogram = macd["histogram"]
        macd_line = macd["macd_line"]
        signal_line = macd["signal_line"]

        # Calculate momentum score
        recent_change = (
            (prices[-1] - prices[-5]) / prices[-5] if len(prices) >= 5 else 0
        )
        momentum_score = recent_change * 100

        # MACD crossover detection
        macd_bullish = macd_line > signal_line and macd_histogram > 0
        macd_bearish = macd_line < signal_line and macd_histogram < 0

        # Combine RSI, MACD, and momentum signals
        if rsi < 30 and macd_bullish and momentum_score > 0:
            # Strong oversold reversal with MACD confirmation
            return 0.9
        elif rsi > 70 and macd_bearish and momentum_score < 0:
            # Strong overbought reversal with MACD confirmation
            return -0.9
        elif rsi < 30 and momentum_score > 0:
            # Oversold + upward momentum (no MACD confirm)
            return 0.7
        elif rsi > 70 and momentum_score < 0:
            # Overbought + downward momentum (no MACD confirm)
            return -0.7
        elif macd_bullish and rsi > 50:
            # MACD bullish crossover with RSI above 50
            return 0.6
        elif macd_bearish and rsi < 50:
            # MACD bearish crossover with RSI below 50
            return -0.6
        elif rsi > 50 and momentum_score > 2:
            # Strong uptrend
            return 0.5

        return momentum_score / 10  # Normalized score

    def _mean_reversion_ml(self, context: Dict[str, Any]) -> float:
        """ML-enhanced mean reversion strategy"""
        prices = context.get("prices", [])
        if len(prices) < 20:
            return 0.0

        # Calculate moving average and deviation
        ma = np.mean(prices[-20:])
        std = np.std(prices[-20:])
        current = prices[-1]

        # Z-score calculation
        z_score = (current - ma) / (std + 1e-6)

        # Bollinger Band logic with ML confidence
        if z_score < -2:  # 2 std below mean
            confidence = min(abs(z_score) / 3, 1.0)
            return confidence * 0.9  # Strong buy signal
        elif z_score > 2:  # 2 std above mean
            confidence = min(abs(z_score) / 3, 1.0)
            return -confidence * 0.9  # Strong sell signal

        return -z_score * 0.3  # Scaled mean reversion

    def _breakout_strategy(self, context: Dict[str, Any]) -> float:
        """Enhanced breakout detection with volume confirmation"""
        prices = context.get("prices", [])
        volumes = context.get("volumes", [])

        if len(prices) < 20:
            return 0.0

        # Find support and resistance
        recent = prices[-20:]
        resistance = max(recent)
        support = min(recent)
        current = prices[-1]

        # Calculate breakout strength
        range_size = resistance - support
        if range_size < 0.01:
            return 0.0

        # Volume confirmation (if available)
        volume_factor = 1.0
        if volumes and len(volumes) >= 5:
            avg_volume = np.mean(volumes[-5:])
            recent_volume = volumes[-1]
            volume_factor = min(recent_volume / (avg_volume + 1), 2.0)

        # Upside breakout
        if current > resistance * 1.001:  # 0.1% above resistance
            strength = ((current - resistance) / range_size) * volume_factor
            return min(strength, 1.0)

        # Downside breakout
        if current < support * 0.999:  # 0.1% below support
            strength = ((support - current) / range_size) * volume_factor
            return -min(strength, 1.0)

        return 0.0

    def _volatility_strategy(self, context: Dict[str, Any]) -> float:
        """Adaptive strategy based on market volatility"""
        prices = context.get("prices", [])
        if len(prices) < 21:
            return 0.0

        # Calculate historical volatility with explicit conversion
        price_slice = prices[-20:]
        prev_prices = prices[-21:-1]
        
        # Calculate returns manually to avoid numpy type issues
        returns = []
        for i in range(len(price_slice)):
            if prev_prices[i] != 0:
                returns.append((price_slice[i] - prev_prices[i]) / prev_prices[i])
        
        if len(returns) < 2:
            return 0.0
        
        volatility = np.std(returns)

        # Calculate current move
        current_return = (prices[-1] - prices[-2]) / prices[-2] if prices[-2] != 0 else 0

        # In high volatility, be more cautious
        # In low volatility, be more aggressive
        if volatility > 0.02:  # High volatility (2%+)
            # Only trade strong signals
            if abs(current_return) > volatility * 2:
                return float(np.sign(current_return)) * 0.5
        else:  # Low volatility
            # More aggressive on smaller moves
            if abs(current_return) > volatility * 1.5:
                return float(np.sign(current_return)) * 0.8

        return 0.0

    def _trend_following(self, context: Dict[str, Any]) -> float:
        """Multi-timeframe trend following"""
        prices = context.get("prices", [])
        if len(prices) < 50:
            return 0.0

        # Short-term trend (10 periods)
        short_ma = np.mean(prices[-10:])

        # Medium-term trend (20 periods)
        medium_ma = np.mean(prices[-20:])

        # Long-term trend (50 periods)
        long_ma = np.mean(prices[-50:])

        current = prices[-1]

        # All trends aligned upward
        if current > short_ma > medium_ma > long_ma:
            strength = (current - long_ma) / long_ma
            return min(strength * 10, 0.9)

        # All trends aligned downward
        if current < short_ma < medium_ma < long_ma:
            strength = (long_ma - current) / long_ma
            return -min(strength * 10, 0.9)

        # Mixed signals - smaller position
        if current > short_ma:
            return 0.3
        elif current < short_ma:
            return -0.3

        return 0.0

    def _scalping_strategy(self, context: Dict[str, Any]) -> float:
        """High-frequency scalping strategy with enhanced momentum detection."""
        prices = context.get("prices", [])
        volumes = context.get("volumes", [])

        if len(prices) < 5:
            return 0.0

        # === Short-term momentum analysis ===
        micro_trend = (prices[-1] - prices[-3]) / prices[-3] if prices[-3] != 0 else 0

        # === Volume confirmation ===
        volume_factor = 1.0
        if volumes and len(volumes) >= 5:
            avg_volume = sum(volumes[-5:]) / 5
            if avg_volume > 0:
                volume_ratio = volumes[-1] / avg_volume
                # Require volume spike for stronger signals
                if volume_ratio >= 1.5:
                    volume_factor = min(1.5, volume_ratio / 2)

        # === Price acceleration ===
        acceleration = 0.0
        if len(prices) >= 5:
            recent_changes = [(prices[i] - prices[i-1]) / prices[i-1]
                            for i in range(-4, 0) if prices[i-1] != 0]
            if len(recent_changes) >= 2:
                # Positive acceleration = momentum increasing
                acceleration = recent_changes[-1] - recent_changes[0]

        # === Spread check (if bid/ask available) ===
        bid = context.get("bid", 0)
        ask = context.get("ask", 0)
        spread_ok = True
        if bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread_pct = (ask - bid) / mid if mid > 0 else float('inf')
            spread_ok = spread_pct <= 0.002  # Max 0.2% spread

        if not spread_ok:
            return 0.0  # Don't trade with wide spreads

        # === Generate signal ===
        # Strong momentum with volume confirmation
        if micro_trend > 0.002 and acceleration > 0 and volume_factor >= 1.2:
            return min(0.9, 0.7 * volume_factor)
        elif micro_trend < -0.002 and acceleration < 0 and volume_factor >= 1.2:
            return max(-0.9, -0.7 * volume_factor)

        # Moderate momentum
        if micro_trend > 0.001:
            return 0.5 * volume_factor
        elif micro_trend < -0.001:
            return -0.5 * volume_factor

        return 0.0

    def _high_win_rate_scalping(self, context: Dict[str, Any]) -> float:
        """
        High win-rate scalping strategy focused on consistent small gains.
        
        Targets 65%+ win rate through conservative entry criteria:
        - Strong momentum confirmation
        - Volume surge detection
        - Tight spread requirements
        - Multiple indicator alignment
        """
        prices = context.get("prices", [])
        volumes = context.get("volumes", [])

        if len(prices) < 20:
            return 0.0

        # Calculate multiple indicators
        rsi = self._calculate_rsi(prices)
        macd = self._calculate_macd(prices)

        # Short-term momentum
        momentum_1m = (prices[-1] - prices[-2]) / prices[-2] if len(prices) >= 2 and prices[-2] != 0 else 0
        momentum_5m = (prices[-1] - prices[-6]) / prices[-6] if len(prices) >= 6 and prices[-6] != 0 else 0

        # Volume ratio
        volume_ratio = 1.0
        if volumes and len(volumes) >= 10:
            avg_volume = sum(volumes[-10:]) / 10
            if avg_volume > 0 and len(volumes) > 0:
                volume_ratio = volumes[-1] / avg_volume

        # Price volatility check
        if len(prices) >= 10:
            recent_prices = prices[-10:]
            price_std = (sum((p - sum(recent_prices)/10)**2 for p in recent_prices) / 9) ** 0.5
            volatility_pct = price_std / (sum(recent_prices)/10) if sum(recent_prices) > 0 else 0

            # Skip if volatility too high (risky) or too low (no opportunity)
            if volatility_pct > 0.03 or volatility_pct < 0.001:
                return 0.0

        # === High confidence BUY signals ===
        bullish_conditions = [
            rsi < 40,  # Oversold
            macd["histogram"] > 0,  # MACD bullish
            momentum_1m > 0.001,  # Short-term up
            momentum_5m > 0.002,  # Medium-term up
            volume_ratio >= 1.3,  # Volume surge
        ]

        bullish_score = sum(bullish_conditions)

        # === High confidence SELL signals ===
        bearish_conditions = [
            rsi > 60,  # Overbought
            macd["histogram"] < 0,  # MACD bearish
            momentum_1m < -0.001,  # Short-term down
            momentum_5m < -0.002,  # Medium-term down
            volume_ratio >= 1.3,  # Volume surge
        ]

        bearish_score = sum(bearish_conditions)

        # Require 4+ conditions for high confidence
        if bullish_score >= 4:
            confidence = min(0.9, 0.6 + bullish_score * 0.1)
            return confidence
        elif bearish_score >= 4:
            confidence = min(0.9, 0.6 + bearish_score * 0.1)
            return -confidence

        # Moderate confidence with 3 conditions
        if bullish_score >= 3 and bearish_score < 2:
            return 0.5
        elif bearish_score >= 3 and bullish_score < 2:
            return -0.5

        return 0.0

    def _ichimoku_cloud_strategy(self, context: Dict[str, Any]) -> float:
        """
        Ichimoku Cloud (Ichimoku Kinko Hyo) trading strategy.
        
        Uses five lines to determine trend, momentum, and support/resistance:
        - Tenkan-sen (Conversion Line): 9-period mid-point
        - Kijun-sen (Base Line): 26-period mid-point
        - Senkou Span A (Leading Span A): Midpoint of Tenkan/Kijun, plotted 26 periods ahead
        - Senkou Span B (Leading Span B): 52-period mid-point, plotted 26 periods ahead
        - Chikou Span (Lagging Span): Current close plotted 26 periods back
        
        Strong signals when multiple confirmations align:
        - Price above/below cloud
        - Tenkan/Kijun crossover
        - Chikou Span confirmation
        """
        prices = context.get("prices", [])
        highs = context.get("highs", prices)
        lows = context.get("lows", prices)
        
        if len(prices) < 52:
            return 0.0
        
        # Calculate Tenkan-sen (Conversion Line) - 9-period
        tenkan_high = max(highs[-9:])
        tenkan_low = min(lows[-9:])
        tenkan_sen = (tenkan_high + tenkan_low) / 2
        
        # Calculate Kijun-sen (Base Line) - 26-period
        kijun_high = max(highs[-26:])
        kijun_low = min(lows[-26:])
        kijun_sen = (kijun_high + kijun_low) / 2
        
        # Calculate Senkou Span A (Leading Span A)
        senkou_span_a = (tenkan_sen + kijun_sen) / 2
        
        # Calculate Senkou Span B (Leading Span B) - 52-period
        senkou_high = max(highs[-52:])
        senkou_low = min(lows[-52:])
        senkou_span_b = (senkou_high + senkou_low) / 2
        
        # Current price and cloud boundaries
        current_price = prices[-1]
        cloud_top = max(senkou_span_a, senkou_span_b)
        cloud_bottom = min(senkou_span_a, senkou_span_b)
        
        # Chikou Span comparison (current price vs price 26 periods ago)
        chikou_bullish = current_price > prices[-26] if len(prices) >= 26 else False
        chikou_bearish = current_price < prices[-26] if len(prices) >= 26 else False
        
        # Previous Tenkan/Kijun for crossover detection (9 and 26 periods ending 1 bar ago)
        prev_tenkan_high = max(highs[-10:-1]) if len(highs) >= 10 else max(highs[:-1])
        prev_tenkan_low = min(lows[-10:-1]) if len(lows) >= 10 else min(lows[:-1])
        prev_tenkan = (prev_tenkan_high + prev_tenkan_low) / 2
        
        prev_kijun_high = max(highs[-27:-1]) if len(highs) >= 27 else max(highs[:-1])
        prev_kijun_low = min(lows[-27:-1]) if len(lows) >= 27 else min(lows[:-1])
        prev_kijun = (prev_kijun_high + prev_kijun_low) / 2
        
        # Detect TK crossover
        tk_bullish_cross = prev_tenkan <= prev_kijun and tenkan_sen > kijun_sen
        tk_bearish_cross = prev_tenkan >= prev_kijun and tenkan_sen < kijun_sen
        
        # Cloud thickness (market uncertainty)
        cloud_thickness = abs(senkou_span_a - senkou_span_b) / current_price
        thick_cloud = cloud_thickness > 0.02  # More than 2% = strong S/R
        
        # === Signal Generation ===
        signal = 0.0
        
        # Strong Bullish: Price above cloud + TK cross + Chikou confirms
        if current_price > cloud_top:
            signal += 0.4  # Above cloud is bullish
            if tk_bullish_cross:
                signal += 0.3  # TK bullish crossover
            if chikou_bullish:
                signal += 0.2  # Chikou confirmation
            if tenkan_sen > kijun_sen:
                signal += 0.1  # Tenkan above Kijun
        
        # Strong Bearish: Price below cloud + TK cross + Chikou confirms
        elif current_price < cloud_bottom:
            signal -= 0.4  # Below cloud is bearish
            if tk_bearish_cross:
                signal -= 0.3  # TK bearish crossover
            if chikou_bearish:
                signal -= 0.2  # Chikou confirmation
            if tenkan_sen < kijun_sen:
                signal -= 0.1  # Tenkan below Kijun
        
        # Inside cloud: Consolidation, reduce signal strength
        else:
            # Inside cloud, look for edge breakout potential
            distance_to_top = (cloud_top - current_price) / current_price
            distance_to_bottom = (current_price - cloud_bottom) / current_price
            
            if distance_to_top < 0.005 and tenkan_sen > kijun_sen:
                signal = 0.3  # Near top breakout
            elif distance_to_bottom < 0.005 and tenkan_sen < kijun_sen:
                signal = -0.3  # Near bottom breakdown
        
        return max(-1.0, min(1.0, signal))

    def _fibonacci_retracement_strategy(self, context: Dict[str, Any]) -> float:
        """
        Fibonacci Retracement trading strategy.
        
        Uses key Fibonacci levels (23.6%, 38.2%, 50%, 61.8%, 78.6%) to identify
        potential support/resistance zones during pullbacks in trends.
        
        Strategy logic:
        - Identify swing high/low
        - Calculate Fibonacci levels
        - Look for price reactions at key levels
        - Confirm with momentum
        """
        prices = context.get("prices", [])
        volumes = context.get("volumes", [])
        
        if len(prices) < 30:
            return 0.0
        
        # Find swing high and swing low in recent data
        lookback = min(50, len(prices))
        recent_prices = prices[-lookback:]
        
        swing_high_idx = recent_prices.index(max(recent_prices))
        swing_low_idx = recent_prices.index(min(recent_prices))
        
        swing_high = max(recent_prices)
        swing_low = min(recent_prices)
        
        if swing_high == swing_low:
            return 0.0
        
        price_range = swing_high - swing_low
        current_price = prices[-1]
        
        # Determine trend direction (high before low = downtrend, low before high = uptrend)
        is_uptrend = swing_low_idx < swing_high_idx
        
        # Fibonacci retracement levels
        fib_levels = {
            0.236: swing_high - (price_range * 0.236) if is_uptrend else swing_low + (price_range * 0.236),
            0.382: swing_high - (price_range * 0.382) if is_uptrend else swing_low + (price_range * 0.382),
            0.500: swing_high - (price_range * 0.500) if is_uptrend else swing_low + (price_range * 0.500),
            0.618: swing_high - (price_range * 0.618) if is_uptrend else swing_low + (price_range * 0.618),
            0.786: swing_high - (price_range * 0.786) if is_uptrend else swing_low + (price_range * 0.786),
        }
        
        # Fibonacci extension levels (for profit targets)
        fib_extensions = {
            1.272: swing_high + (price_range * 0.272) if is_uptrend else swing_low - (price_range * 0.272),
            1.618: swing_high + (price_range * 0.618) if is_uptrend else swing_low - (price_range * 0.618),
        }
        
        # Check proximity to Fibonacci levels (within 0.5%)
        tolerance = 0.005
        at_fib_level = None
        fib_strength = 0.0
        
        for level, price_level in fib_levels.items():
            if abs(current_price - price_level) / current_price < tolerance:
                at_fib_level = level
                # 61.8% (golden ratio) is strongest, 50% is second
                if level == 0.618:
                    fib_strength = 0.9
                elif level == 0.500:
                    fib_strength = 0.8
                elif level == 0.382:
                    fib_strength = 0.7
                else:
                    fib_strength = 0.5
                break
        
        if at_fib_level is None:
            return 0.0
        
        # Momentum confirmation
        momentum_5 = (prices[-1] - prices[-6]) / prices[-6] if len(prices) >= 6 else 0
        momentum_10 = (prices[-1] - prices[-11]) / prices[-11] if len(prices) >= 11 else 0
        
        # Volume confirmation
        volume_surge = 1.0
        if volumes and len(volumes) >= 10:
            avg_vol = sum(volumes[-10:]) / 10
            if avg_vol > 0 and len(volumes) > 0:
                volume_surge = volumes[-1] / avg_vol
        
        signal = 0.0
        
        # In uptrend, buy at Fib support levels if momentum turning up
        if is_uptrend and at_fib_level:
            if momentum_5 > 0 and momentum_10 < 0:  # Momentum turning positive
                signal = fib_strength * min(1.5, volume_surge)
            elif momentum_5 > 0.002:  # Strong upward momentum
                signal = fib_strength * 0.8
        
        # In downtrend, sell at Fib resistance levels if momentum turning down
        elif not is_uptrend and at_fib_level:
            if momentum_5 < 0 and momentum_10 > 0:  # Momentum turning negative
                signal = -fib_strength * min(1.5, volume_surge)
            elif momentum_5 < -0.002:  # Strong downward momentum
                signal = -fib_strength * 0.8
        
        return max(-1.0, min(1.0, signal))

    def _stochastic_oscillator_strategy(self, context: Dict[str, Any]) -> float:
        """
        Stochastic Oscillator trading strategy.
        
        Compares closing price to price range over a period.
        Uses %K (fast) and %D (slow) lines for signals.
        
        Key levels:
        - Oversold: Below 20
        - Overbought: Above 80
        
        Signals:
        - %K crossing above %D in oversold = Buy
        - %K crossing below %D in overbought = Sell
        - Bullish/Bearish divergences
        """
        prices = context.get("prices", [])
        highs = context.get("highs", prices)
        lows = context.get("lows", prices)
        
        k_period = 14
        d_period = 3
        
        if len(prices) < k_period + d_period:
            return 0.0
        
        # Calculate %K values for the last d_period + 1 periods (for crossover detection)
        k_values = []
        data_len = len(prices)
        
        for i in range(d_period + 1):
            # Calculate end index for this historical %K calculation
            end_idx = data_len - (d_period - i)
            start_idx = max(0, end_idx - k_period)
            
            if end_idx <= 0 or start_idx >= end_idx:
                k_values.append(50.0)
                continue
            
            period_highs = highs[start_idx:end_idx]
            period_lows = lows[start_idx:end_idx]
            close = prices[end_idx - 1]
            
            highest_high = max(period_highs) if period_highs else prices[-1]
            lowest_low = min(period_lows) if period_lows else prices[-1]
            
            if highest_high == lowest_low:
                k_values.append(50.0)
            else:
                k_value = ((close - lowest_low) / (highest_high - lowest_low)) * 100
                k_values.append(k_value)
        
        # Current %K
        current_k = k_values[-1]
        
        # %D is SMA of %K
        current_d = sum(k_values[-d_period:]) / d_period
        prev_d = sum(k_values[-d_period-1:-1]) / d_period if len(k_values) > d_period else current_d
        
        prev_k = k_values[-2] if len(k_values) >= 2 else current_k
        
        # Detect crossovers
        k_crosses_above_d = prev_k <= prev_d and current_k > current_d
        k_crosses_below_d = prev_k >= prev_d and current_k < current_d
        
        # Zone detection
        is_oversold = current_k < 20 and current_d < 20
        is_overbought = current_k > 80 and current_d > 80
        near_oversold = current_k < 30
        near_overbought = current_k > 70
        
        signal = 0.0
        
        # Strong bullish: Crossover in oversold zone
        if k_crosses_above_d and is_oversold:
            signal = 0.9
        # Moderate bullish: Crossover near oversold
        elif k_crosses_above_d and near_oversold:
            signal = 0.7
        # Weak bullish: Any bullish crossover
        elif k_crosses_above_d:
            signal = 0.4
        
        # Strong bearish: Crossover in overbought zone
        elif k_crosses_below_d and is_overbought:
            signal = -0.9
        # Moderate bearish: Crossover near overbought
        elif k_crosses_below_d and near_overbought:
            signal = -0.7
        # Weak bearish: Any bearish crossover
        elif k_crosses_below_d:
            signal = -0.4
        
        # Extreme zone warnings (no crossover yet but in extreme zone)
        elif is_oversold and current_k > prev_k:
            signal = 0.5  # Momentum turning in oversold
        elif is_overbought and current_k < prev_k:
            signal = -0.5  # Momentum turning in overbought
        
        return signal

    def _adx_trend_strength_strategy(self, context: Dict[str, Any]) -> float:
        """
        ADX (Average Directional Index) trend strength strategy.
        
        ADX measures trend strength (not direction):
        - ADX < 20: Weak/no trend (range-bound)
        - ADX 20-40: Developing trend
        - ADX 40-60: Strong trend
        - ADX > 60: Very strong trend
        
        +DI and -DI determine direction:
        - +DI > -DI: Uptrend
        - -DI > +DI: Downtrend
        
        Strategy:
        - Trade with trend when ADX > 25
        - Use DI crossovers for entry signals
        - Stronger signals in stronger trends
        """
        prices = context.get("prices", [])
        highs = context.get("highs", prices)
        lows = context.get("lows", prices)
        
        period = 14
        
        if len(prices) < period + 2:
            return 0.0
        
        # Calculate True Range and Directional Movement
        tr_values = []
        plus_dm_values = []
        minus_dm_values = []
        
        for i in range(-period - 1, 0):
            high = highs[i]
            low = lows[i]
            prev_close = prices[i - 1]
            prev_high = highs[i - 1]
            prev_low = lows[i - 1]
            
            # True Range
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_values.append(tr)
            
            # Directional Movement
            up_move = high - prev_high
            down_move = prev_low - low
            
            plus_dm = up_move if (up_move > down_move and up_move > 0) else 0
            minus_dm = down_move if (down_move > up_move and down_move > 0) else 0
            
            plus_dm_values.append(plus_dm)
            minus_dm_values.append(minus_dm)
        
        # Smoothed averages (Wilder's smoothing)
        atr = sum(tr_values) / period
        smoothed_plus_dm = sum(plus_dm_values) / period
        smoothed_minus_dm = sum(minus_dm_values) / period
        
        # +DI and -DI
        plus_di = (smoothed_plus_dm / atr * 100) if atr > 0 else 0
        minus_di = (smoothed_minus_dm / atr * 100) if atr > 0 else 0
        
        # DX and ADX
        di_sum = plus_di + minus_di
        dx = (abs(plus_di - minus_di) / di_sum * 100) if di_sum > 0 else 0
        
        # Simplified ADX (would need historical DX for true smoothed ADX)
        adx = dx  # In production, use smoothed average of DX values
        
        # Detect DI crossover
        # For crossover detection, calculate previous DIs
        prev_tr = tr_values[-2] if len(tr_values) >= 2 else tr_values[-1]
        prev_plus_dm = plus_dm_values[-2] if len(plus_dm_values) >= 2 else plus_dm_values[-1]
        prev_minus_dm = minus_dm_values[-2] if len(minus_dm_values) >= 2 else minus_dm_values[-1]
        
        prev_plus_di = (prev_plus_dm / prev_tr * 100) if prev_tr > 0 else 0
        prev_minus_di = (prev_minus_dm / prev_tr * 100) if prev_tr > 0 else 0
        
        bullish_cross = prev_plus_di <= prev_minus_di and plus_di > minus_di
        bearish_cross = prev_plus_di >= prev_minus_di and plus_di < minus_di
        
        signal = 0.0
        
        # Strong trend with DI alignment
        if adx >= 40:
            trend_multiplier = 1.0
        elif adx >= 25:
            trend_multiplier = 0.7
        elif adx >= 20:
            trend_multiplier = 0.4
        else:
            # Weak trend - avoid trading
            return 0.0
        
        # Direction from DI
        if plus_di > minus_di:
            # Uptrend
            di_strength = (plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
            signal = di_strength * trend_multiplier
            
            if bullish_cross:
                signal = min(1.0, signal + 0.3)  # Bonus for fresh crossover
        
        elif minus_di > plus_di:
            # Downtrend
            di_strength = (minus_di - plus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
            signal = -di_strength * trend_multiplier
            
            if bearish_cross:
                signal = max(-1.0, signal - 0.3)  # Bonus for fresh crossover
        
        return max(-1.0, min(1.0, signal))

    def _bollinger_squeeze_strategy(self, context: Dict[str, Any]) -> float:
        """
        Bollinger Band Squeeze strategy.
        
        Detects periods of low volatility (squeeze) that often precede
        explosive moves. Combines Bollinger Bands with Keltner Channels.
        
        Squeeze condition: BB inside KC
        - When squeeze releases, trade in direction of momentum
        
        Also uses BB %B for overbought/oversold:
        - %B > 1: Price above upper band (overbought)
        - %B < 0: Price below lower band (oversold)
        """
        prices = context.get("prices", [])
        highs = context.get("highs", prices)
        lows = context.get("lows", prices)
        
        bb_period = 20
        bb_std_mult = 2.0
        kc_period = 20
        kc_atr_mult = 1.5
        
        if len(prices) < max(bb_period, kc_period) + 10:
            return 0.0
        
        # Bollinger Bands
        bb_sma = np.mean(prices[-bb_period:])
        bb_std = np.std(prices[-bb_period:])
        bb_upper = bb_sma + (bb_std * bb_std_mult)
        bb_lower = bb_sma - (bb_std * bb_std_mult)
        
        # Keltner Channel (using ATR)
        atr_values = []
        for i in range(-kc_period, 0):
            high = highs[i]
            low = lows[i]
            prev_close = prices[i - 1]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            atr_values.append(tr)
        
        atr = sum(atr_values) / kc_period
        kc_middle = np.mean(prices[-kc_period:])
        kc_upper = kc_middle + (atr * kc_atr_mult)
        kc_lower = kc_middle - (atr * kc_atr_mult)
        
        # Squeeze detection: BB inside KC
        is_squeeze = bb_lower > kc_lower and bb_upper < kc_upper
        
        # Check previous squeeze state
        prev_bb_sma = np.mean(prices[-bb_period-1:-1])
        prev_bb_std = np.std(prices[-bb_period-1:-1])
        prev_bb_upper = prev_bb_sma + (prev_bb_std * bb_std_mult)
        prev_bb_lower = prev_bb_sma - (prev_bb_std * bb_std_mult)
        
        prev_kc_middle = np.mean(prices[-kc_period-1:-1])
        prev_kc_upper = prev_kc_middle + (atr * kc_atr_mult)
        prev_kc_lower = prev_kc_middle - (atr * kc_atr_mult)
        
        was_squeeze = prev_bb_lower > prev_kc_lower and prev_bb_upper < prev_kc_upper
        
        # Squeeze release detection
        squeeze_release = was_squeeze and not is_squeeze
        
        # Current price position
        current_price = prices[-1]
        
        # %B calculation (where price is relative to bands)
        bb_width = bb_upper - bb_lower
        percent_b = (current_price - bb_lower) / bb_width if bb_width > 0 else 0.5
        
        # Momentum for direction
        momentum_12 = (prices[-1] - prices[-13]) / prices[-13] if len(prices) >= 13 else 0
        momentum_6 = (prices[-1] - prices[-7]) / prices[-7] if len(prices) >= 7 else 0
        
        signal = 0.0
        
        # Squeeze release signals (highest priority)
        if squeeze_release:
            if momentum_6 > 0 and momentum_12 > 0:
                signal = 0.9  # Bullish breakout
            elif momentum_6 < 0 and momentum_12 < 0:
                signal = -0.9  # Bearish breakdown
        
        # Currently in squeeze - prepare for breakout
        elif is_squeeze:
            # Low volatility, wait for direction
            if momentum_6 > 0.005:
                signal = 0.3  # Preparing for bullish
            elif momentum_6 < -0.005:
                signal = -0.3  # Preparing for bearish
        
        # Not in squeeze - use %B for mean reversion
        else:
            if percent_b > 1.0:  # Above upper band
                signal = -0.6  # Overbought, expect pullback
            elif percent_b < 0.0:  # Below lower band
                signal = 0.6  # Oversold, expect bounce
            elif percent_b > 0.8:
                signal = -0.3
            elif percent_b < 0.2:
                signal = 0.3
        
        return max(-1.0, min(1.0, signal))

    def _macd_divergence_strategy(self, context: Dict[str, Any]) -> float:
        """
        MACD Divergence detection strategy.
        
        Identifies divergences between price and MACD, which often
        precede trend reversals:
        
        Bullish Divergence: Price makes lower low, MACD makes higher low
        Bearish Divergence: Price makes higher high, MACD makes lower high
        
        Also considers histogram divergences for earlier signals.
        """
        prices = context.get("prices", [])
        
        if len(prices) < 50:
            return 0.0
        
        # Calculate MACD for recent history using explicit slicing
        macd_history = []
        histogram_history = []
        n = len(prices)
        
        for offset in range(30, 0, -1):
            end_idx = n - offset + 1
            if end_idx > 0:
                macd_data = self._calculate_macd(prices[:end_idx])
                macd_history.append(macd_data["macd_line"])
                histogram_history.append(macd_data["histogram"])
        
        current_macd = self._calculate_macd(prices)
        macd_history.append(current_macd["macd_line"])
        histogram_history.append(current_macd["histogram"])
        
        # Find local extrema in price
        price_window = prices[-30:]
        
        def find_local_min_max(data, window=5):
            mins = []
            maxs = []
            for i in range(window, len(data) - window):
                if all(data[i] <= data[i-j] for j in range(1, window+1)) and \
                   all(data[i] <= data[i+j] for j in range(1, window+1)):
                    mins.append((i, data[i]))
                if all(data[i] >= data[i-j] for j in range(1, window+1)) and \
                   all(data[i] >= data[i+j] for j in range(1, window+1)):
                    maxs.append((i, data[i]))
            return mins, maxs
        
        price_mins, price_maxs = find_local_min_max(price_window, window=3)
        macd_mins, macd_maxs = find_local_min_max(macd_history, window=3)
        
        signal = 0.0
        
        # Check for bullish divergence (price lower low, MACD higher low)
        if len(price_mins) >= 2 and len(macd_mins) >= 2:
            # Recent price lows
            price_low_1 = price_mins[-2][1]
            price_low_2 = price_mins[-1][1]
            
            # Corresponding MACD lows
            macd_low_1 = macd_mins[-2][1]
            macd_low_2 = macd_mins[-1][1]
            
            # Bullish divergence: price makes lower low, MACD makes higher low
            if price_low_2 < price_low_1 and macd_low_2 > macd_low_1:
                divergence_strength = (macd_low_2 - macd_low_1) / abs(macd_low_1) if macd_low_1 != 0 else 0
                signal = min(0.9, 0.6 + divergence_strength * 2)
        
        # Check for bearish divergence (price higher high, MACD lower high)
        if len(price_maxs) >= 2 and len(macd_maxs) >= 2:
            # Recent price highs
            price_high_1 = price_maxs[-2][1]
            price_high_2 = price_maxs[-1][1]
            
            # Corresponding MACD highs
            macd_high_1 = macd_maxs[-2][1]
            macd_high_2 = macd_maxs[-1][1]
            
            # Bearish divergence: price makes higher high, MACD makes lower high
            if price_high_2 > price_high_1 and macd_high_2 < macd_high_1:
                divergence_strength = (macd_high_1 - macd_high_2) / abs(macd_high_1) if macd_high_1 != 0 else 0
                signal = max(-0.9, -(0.6 + divergence_strength * 2))
        
        # Histogram divergence (faster signal)
        hist_mins, hist_maxs = find_local_min_max(histogram_history, window=2)
        
        if signal == 0 and len(price_mins) >= 2 and len(hist_mins) >= 2:
            if price_mins[-1][1] < price_mins[-2][1] and hist_mins[-1][1] > hist_mins[-2][1]:
                signal = 0.5  # Histogram bullish divergence
        
        if signal == 0 and len(price_maxs) >= 2 and len(hist_maxs) >= 2:
            if price_maxs[-1][1] > price_maxs[-2][1] and hist_maxs[-1][1] < hist_maxs[-2][1]:
                signal = -0.5  # Histogram bearish divergence
        
        return signal

    def _volume_profile_strategy(self, context: Dict[str, Any]) -> float:
        """
        Volume Profile trading strategy.
        
        Analyzes volume distribution across price levels to identify:
        - POC (Point of Control): Price with highest volume
        - Value Area: Price range with 70% of volume
        - HVN (High Volume Nodes): Strong support/resistance
        - LVN (Low Volume Nodes): Weak areas, price moves fast through
        
        Strategy:
        - Trade bounces from POC/HVN
        - Trade breakouts through LVN
        """
        prices = context.get("prices", [])
        volumes = context.get("volumes", [])
        
        if len(prices) < 30 or not volumes or len(volumes) < 30:
            return 0.0
        
        # Ensure equal lengths
        min_len = min(len(prices), len(volumes))
        prices = prices[-min_len:]
        volumes = volumes[-min_len:]
        
        # Create volume profile (volume at each price level)
        price_min = min(prices)
        price_max = max(prices)
        price_range = price_max - price_min
        
        if price_range == 0:
            return 0.0
        
        # Create price bins (20 levels)
        num_bins = 20
        bin_size = price_range / num_bins
        volume_profile = [0.0] * num_bins
        
        for i, (price, volume) in enumerate(zip(prices, volumes)):
            bin_idx = min(int((price - price_min) / bin_size), num_bins - 1)
            volume_profile[bin_idx] += volume
        
        total_volume = sum(volume_profile)
        if total_volume == 0:
            return 0.0
        
        # Find POC (Point of Control) - highest volume price level
        poc_bin = volume_profile.index(max(volume_profile))
        poc_price = price_min + (poc_bin + 0.5) * bin_size
        
        # Calculate Value Area (70% of volume centered around POC)
        sorted_bins = sorted(range(num_bins), key=lambda x: volume_profile[x], reverse=True)
        value_area_volume = 0
        value_area_bins = []
        
        for bin_idx in sorted_bins:
            value_area_bins.append(bin_idx)
            value_area_volume += volume_profile[bin_idx]
            if value_area_volume >= total_volume * 0.7:
                break
        
        va_low = price_min + min(value_area_bins) * bin_size
        va_high = price_min + (max(value_area_bins) + 1) * bin_size
        
        # Find HVN (High Volume Nodes) and LVN (Low Volume Nodes)
        avg_volume = total_volume / num_bins
        hvn_bins = [i for i, v in enumerate(volume_profile) if v > avg_volume * 1.5]
        lvn_bins = [i for i, v in enumerate(volume_profile) if v < avg_volume * 0.5]
        
        current_price = prices[-1]
        current_bin = min(int((current_price - price_min) / bin_size), num_bins - 1)
        
        # Price momentum
        momentum = (prices[-1] - prices[-6]) / prices[-6] if len(prices) >= 6 else 0
        
        signal = 0.0
        
        # === Trading Logic ===
        
        # Near POC (strong support/resistance)
        poc_distance = abs(current_price - poc_price) / poc_price
        if poc_distance < 0.01:  # Within 1% of POC
            # Expect bounce from POC
            if momentum > 0.002:
                signal = 0.6  # Bouncing up from POC support
            elif momentum < -0.002:
                signal = -0.6  # Bouncing down from POC resistance
        
        # Price at Value Area boundaries
        elif abs(current_price - va_low) / va_low < 0.01:
            if momentum > 0:
                signal = 0.5  # Bouncing from VA low
            else:
                signal = -0.3  # Breaking below VA
        
        elif abs(current_price - va_high) / va_high < 0.01:
            if momentum < 0:
                signal = -0.5  # Bouncing from VA high
            else:
                signal = 0.3  # Breaking above VA
        
        # At LVN - expect fast moves
        elif current_bin in lvn_bins:
            # In low volume area, strong momentum expected to continue
            if momentum > 0.003:
                signal = 0.7  # Fast move up through LVN
            elif momentum < -0.003:
                signal = -0.7  # Fast move down through LVN
        
        # At HVN - expect consolidation/reversal
        elif current_bin in hvn_bins:
            # High volume area, mean reversion more likely
            if momentum > 0.005:
                signal = -0.3  # Overbought at resistance
            elif momentum < -0.005:
                signal = 0.3  # Oversold at support
        
        return max(-1.0, min(1.0, signal))

    def _order_flow_imbalance_strategy(self, context: Dict[str, Any]) -> float:
        """
        Order Flow Imbalance strategy.
        
        Analyzes the balance between buying and selling pressure using:
        - Bid/Ask volume imbalance
        - Trade delta (buy volume - sell volume)
        - Absorption detection
        - Institutional footprint
        
        Note: Requires tick-level or detailed order data for best results.
        This implementation uses candle data approximation.
        """
        prices = context.get("prices", [])
        volumes = context.get("volumes", [])
        highs = context.get("highs", prices)
        lows = context.get("lows", prices)
        opens = context.get("opens", [])
        
        if len(prices) < 20 or not volumes or len(volumes) < 20:
            return 0.0
        
        # Work with only the last 20 periods for efficiency
        prices_20 = prices[-20:]
        volumes_20 = volumes[-20:]
        highs_20 = highs[-20:] if len(highs) >= 20 else highs
        lows_20 = lows[-20:] if len(lows) >= 20 else lows
        
        # Generate opens for just the 20 periods we need
        if opens and len(opens) >= 20:
            opens_20 = opens[-20:]
        else:
            # Approximate opens using previous close
            opens_20 = [prices_20[0]] + prices_20[:-1]
        
        min_len = min(len(prices_20), len(volumes_20), len(highs_20), len(lows_20), len(opens_20))
        prices_20 = prices_20[-min_len:]
        volumes_20 = volumes_20[-min_len:]
        highs_20 = highs_20[-min_len:]
        lows_20 = lows_20[-min_len:]
        opens_20 = opens_20[-min_len:]
        
        # === Estimate Buy/Sell Volume using candle analysis ===
        buy_volumes = []
        sell_volumes = []
        deltas = []
        
        for i in range(len(prices_20)):
            o, h, l, c, v = opens_20[i], highs_20[i], lows_20[i], prices_20[i], volumes_20[i]
            
            # Range
            candle_range = h - l
            if candle_range == 0:
                buy_pct = 0.5
            else:
                # Estimate buy % based on close position in range
                buy_pct = (c - l) / candle_range
            
            buy_vol = v * buy_pct
            sell_vol = v * (1 - buy_pct)
            delta = buy_vol - sell_vol
            
            buy_volumes.append(buy_vol)
            sell_volumes.append(sell_vol)
            deltas.append(delta)
        
        # === Calculate imbalance metrics ===
        
        # Cumulative delta
        cumulative_delta = sum(deltas)
        recent_delta = sum(deltas[-5:])
        
        # Delta momentum
        delta_momentum = recent_delta - sum(deltas[-10:-5])
        
        # Imbalance ratio
        total_buy = sum(buy_volumes)
        total_sell = sum(sell_volumes)
        imbalance_ratio = (total_buy - total_sell) / (total_buy + total_sell) if (total_buy + total_sell) > 0 else 0
        
        # Recent imbalance
        recent_buy = sum(buy_volumes[-5:])
        recent_sell = sum(sell_volumes[-5:])
        recent_imbalance = (recent_buy - recent_sell) / (recent_buy + recent_sell) if (recent_buy + recent_sell) > 0 else 0
        
        # === Absorption detection ===
        # Price not moving despite high volume = absorption
        price_change = (prices_20[-1] - prices_20[-6]) / prices_20[-6] if len(prices_20) >= 6 else 0
        volume_spike = volumes_20[-1] > (sum(volumes_20[-10:]) / 10) * 1.5 if len(volumes_20) >= 10 else False
        
        is_absorption = volume_spike and abs(price_change) < 0.002
        
        # === Signal generation ===
        signal = 0.0
        
        # Strong imbalance with momentum confirmation
        if recent_imbalance > 0.3 and delta_momentum > 0:
            signal = min(0.9, recent_imbalance + 0.3)
        elif recent_imbalance < -0.3 and delta_momentum < 0:
            signal = max(-0.9, recent_imbalance - 0.3)
        
        # Moderate imbalance
        elif recent_imbalance > 0.15:
            signal = 0.5
        elif recent_imbalance < -0.15:
            signal = -0.5
        
        # Absorption - potential reversal
        if is_absorption:
            if cumulative_delta > 0 and recent_delta < 0:
                signal = -0.6  # Buyers absorbed, reversal down
            elif cumulative_delta < 0 and recent_delta > 0:
                signal = 0.6  # Sellers absorbed, reversal up
        
        # Delta divergence
        if price_change > 0.01 and recent_delta < 0:
            signal = -0.4  # Rising price but sell pressure
        elif price_change < -0.01 and recent_delta > 0:
            signal = 0.4  # Falling price but buy pressure
        
        return max(-1.0, min(1.0, signal))

    def _calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate Relative Strength Index"""
        if len(prices) < period + 1:
            return 50.0

        deltas = np.diff(prices[-period - 1 :])

        # Handle both numpy arrays and lists (fallback case)
        if isinstance(deltas, list):
            gains = [d if d > 0 else 0.0 for d in deltas]
            losses = [-d if d < 0 else 0.0 for d in deltas]
        else:
            # NumPy array
            gains = deltas.copy()
            losses = deltas.copy()
            gains[gains < 0] = 0
            losses[losses > 0] = 0
            losses = abs(losses)

        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return np.mean(prices) if prices else 0.0

        multiplier = 2.0 / (period + 1)
        ema = np.mean(prices[:period])  # Start with SMA

        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    def _calculate_macd(
        self,
        prices: List[float],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Dict[str, float]:
        """
        Calculate MACD (Moving Average Convergence Divergence)
        
        Uses incremental EMA calculation for O(n) complexity.
        
        Returns:
            Dict with 'macd_line', 'signal_line', 'histogram'
        """
        if len(prices) < slow_period + signal_period:
            return {"macd_line": 0.0, "signal_line": 0.0, "histogram": 0.0}

        # Calculate EMAs incrementally for efficiency (O(n) instead of O(n²))
        fast_multiplier = 2.0 / (fast_period + 1)
        slow_multiplier = 2.0 / (slow_period + 1)
        signal_multiplier = 2.0 / (signal_period + 1)

        # Initialize EMAs with SMA of first periods
        fast_ema = np.mean(prices[:fast_period])
        slow_ema = np.mean(prices[:slow_period])

        # Calculate MACD history using incremental EMA
        macd_history = []

        for i in range(slow_period, len(prices)):
            price = prices[i]

            # Update fast EMA
            if i >= fast_period:
                fast_ema = (price - fast_ema) * fast_multiplier + fast_ema
            else:
                # Still in initialization period for fast EMA
                fast_ema = np.mean(prices[:i+1])

            # Update slow EMA
            slow_ema = (price - slow_ema) * slow_multiplier + slow_ema

            # MACD line = fast EMA - slow EMA
            macd_value = fast_ema - slow_ema
            macd_history.append(macd_value)

        # Current MACD line
        macd_line = macd_history[-1] if macd_history else 0.0

        # Calculate signal line (EMA of MACD)
        if len(macd_history) >= signal_period:
            # Initialize signal EMA with SMA
            signal_ema = np.mean(macd_history[:signal_period])

            # Calculate signal EMA incrementally
            for macd_val in macd_history[signal_period:]:
                signal_ema = (macd_val - signal_ema) * signal_multiplier + signal_ema

            signal_line = signal_ema
        else:
            signal_line = np.mean(macd_history) if macd_history else 0.0

        # Calculate histogram
        histogram = macd_line - signal_line

        return {
            "macd_line": macd_line,
            "signal_line": signal_line,
            "histogram": histogram
        }

    def register(self, name: str, func: Callable):
        """Register a custom strategy"""
        if name in self.strategies:
            return f"[STRATEGY] '{name}' already registered"
        self.strategies[name] = func
        self.weights[name] = 1.0
        return f"[STRATEGY] Registered: {name}"

    def evaluate_all(self, context: Dict[str, Any]) -> Dict[str, Union[float, str]]:
        """
        Evaluate all strategies and return scores.

        Args:
            context: Trading context with prices, volumes, etc.

        Returns:
            Dictionary mapping strategy names to scores or error messages
        """
        scores: Dict[str, Union[float, str]] = {}
        timestamp = time.time()

        for name, func in self.strategies.items():
            try:
                score = func(context)
                scores[name] = score
                self.execution_log.append((name, score, timestamp))

                # Track performance
                if name not in self.performance_tracker:
                    self.performance_tracker[name] = {
                        "scores": [],
                        "wins": 0,
                        "total": 0,
                    }
                self.performance_tracker[name]["scores"].append(score)

            except (ValueError, TypeError, KeyError) as e:
                scores[name] = f"Error: {e}"
                logger.warning("Strategy %s failed with %s: %s", name, type(e).__name__, e)
            except (ZeroDivisionError, IndexError) as e:
                scores[name] = f"Error: {e}"
                logger.warning("Strategy %s calculation error: %s", name, e)

        # Keep log size manageable
        if len(self.execution_log) > 1000:
            self.execution_log = self.execution_log[-500:]

        return scores

    def best(self, context: Dict[str, Any]) -> Tuple[str, float]:
        """Get best strategy and its score"""
        scores = self.evaluate_all(context)
        filtered = {k: v for k, v in scores.items() if isinstance(v, (int, float))}

        if not filtered:
            return "[STRATEGY] No valid results", 0.0

        best_name = max(filtered, key=filtered.get)
        best_score = filtered[best_name]

        return best_name, best_score

    def ensemble_decision(self, context: Dict[str, Any]) -> float:
        """
        Make ensemble decision using weighted average of all strategies
        Returns: float between -1 (strong sell) and 1 (strong buy)
        """
        scores = self.evaluate_all(context)
        filtered = {k: v for k, v in scores.items() if isinstance(v, (int, float))}

        if not filtered:
            return 0.0

        # Weighted average
        total_weight = sum(self.weights.get(name, 1.0) for name in filtered.keys())
        weighted_score = sum(
            score * self.weights.get(name, 1.0) for name, score in filtered.items()
        )

        return weighted_score / total_weight if total_weight > 0 else 0.0

    def update_weights_by_performance(self):
        """Dynamically adjust strategy weights based on historical performance"""
        for name, tracker in self.performance_tracker.items():
            if tracker["total"] > 10:  # Need minimum trades to adjust
                win_rate = tracker["wins"] / tracker["total"]
                # Increase weight for successful strategies
                self.weights[name] = 0.5 + (win_rate * 1.5)

        return "[STRATEGY] Weights updated based on performance"

    def get_performance_report(self) -> Dict[str, Any]:
        """Get performance report for all strategies"""
        report = {}
        for name, tracker in self.performance_tracker.items():
            if tracker["total"] > 0:
                report[name] = {
                    "win_rate": tracker["wins"] / tracker["total"],
                    "total_signals": tracker["total"],
                    "current_weight": self.weights.get(name, 1.0),
                    "avg_score": (
                        np.mean(tracker["scores"][-100:]) if tracker["scores"] else 0
                    ),
                }
        return report

    def log(self, limit: int = 5) -> List:
        """Get recent execution log"""
        return (
            self.execution_log[-limit:]
            if self.execution_log
            else ["[STRATEGY] No execution log"]
        )
