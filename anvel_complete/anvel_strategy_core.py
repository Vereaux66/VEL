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
        if len(prices) < 20:
            return 0.0

        # Calculate historical volatility
        returns = np.diff(prices[-20:]) / prices[-21:-1]
        volatility = np.std(returns)

        # Calculate current move
        current_return = (prices[-1] - prices[-2]) / prices[-2]

        # In high volatility, be more cautious
        # In low volatility, be more aggressive
        if volatility > 0.02:  # High volatility (2%+)
            # Only trade strong signals
            if abs(current_return) > volatility * 2:
                return np.sign(current_return) * 0.5
        else:  # Low volatility
            # More aggressive on smaller moves
            if abs(current_return) > volatility * 1.5:
                return np.sign(current_return) * 0.8

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
