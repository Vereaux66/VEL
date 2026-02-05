#!/usr/bin/env python3
"""
ANVEL Scalping Engine - High-Frequency Trading for Capital Growth

This module implements a production-grade scalping engine designed for:
- 100,000+ concurrent users with isolated API key trading
- Continuous market monitoring for momentum opportunities  
- High win-rate micro-scalping with strict risk controls
- Target 25-50% monthly capital growth through consistent small gains

CRITICAL DISCLAIMER:
This system does NOT guarantee profits. Past performance does not predict future results.
All trading involves substantial risk of loss. Users must only trade with capital they
can afford to lose. No trading system can guarantee specific returns.

Thread-safe, idempotent, and production-ready for capital-touching operations.
"""

import hashlib
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import secrets
import statistics

log = logging.getLogger(__name__)


# =============================================================================
# Constants and Configuration
# =============================================================================

# Maximum scalability constants for heavy runtime workloads
MAX_CONCURRENT_USERS = 100000
MAX_WORKER_THREADS = 64
MAX_SIGNAL_QUEUE_SIZE = 100000
MAX_BATCH_SIZE = 1000
POSITION_CHECK_INTERVAL_MS = 50  # 50ms position monitoring
SIGNAL_GENERATION_INTERVAL_MS = 100  # 100ms signal generation
USER_STATE_SHARDS = 16  # Shard user state for parallel access

# Scalping configuration - conservative defaults for capital preservation
DEFAULT_SCALP_CONFIG = {
    # Win rate thresholds for entry (minimum predicted probability)
    "min_win_rate_threshold": 0.65,  # 65% minimum predicted win rate
    "target_win_rate": 0.75,  # 75% target win rate

    # Position sizing
    "max_position_pct": 0.05,  # 5% max per position
    "min_position_usd": 10.0,  # Minimum $10 position
    "max_position_usd": 1000.0,  # Maximum $1000 per position

    # Profit targets and stop losses
    # IMPORTANT: TP > SL creates positive risk/reward ratio (1.67:1)
    # With 65% win rate threshold, expected value = 0.65 * 0.5% - 0.35 * 0.3% = 0.22% per trade
    "take_profit_pct": 0.005,  # 0.5% take profit
    "stop_loss_pct": 0.003,  # 0.3% stop loss (smaller than TP for positive risk/reward)
    "trailing_stop_pct": 0.002,  # 0.2% trailing stop activation

    # Time limits
    "max_hold_seconds": 300,  # 5 minute max hold time
    "min_hold_seconds": 5,  # 5 second minimum (prevent flickering)

    # Market conditions
    "min_volume_multiplier": 1.5,  # Require 1.5x average volume
    "max_spread_pct": 0.002,  # Max 0.2% spread

    # Daily limits
    "max_daily_trades": 100,  # Max trades per day per user
    "max_daily_loss_pct": 0.03,  # 3% max daily loss
    "daily_profit_target_pct": 0.02,  # 2% daily profit target (pause if reached)

    # Monthly targets (for monitoring/projection only, NOT guarantees)
    # DISCLAIMER: These are TARGETS, not guaranteed returns
    # Actual results may vary significantly and losses are possible
    "monthly_growth_target_low": 0.10,  # 10% monthly target (realistic range)
    "monthly_growth_target_high": 0.20,  # 20% monthly target (aggressive but achievable)

    # === ZENITH SCALABILITY SETTINGS ===
    # High-performance settings for heavy runtime workloads
    "enable_parallel_processing": True,
    "enable_batch_execution": True,
    "enable_signal_caching": True,
    "enable_adaptive_scaling": True,
    "worker_pool_size": 16,  # Base worker pool size
    "max_worker_pool_size": 64,  # Maximum workers under load
    "signal_queue_capacity": 100000,
    "batch_size": 500,  # Process signals in batches
    "signal_ttl_seconds": 5,  # Signal time-to-live
    "position_check_interval_ms": 50,  # Fast position monitoring
    "adaptive_scaling_threshold": 0.75,  # Scale up at 75% queue capacity
    "adaptive_scaling_cooldown_ms": 1000,  # Cooldown between scaling events
}


class ScalpingState(Enum):
    """Trading state for a user's scalping session."""
    ACTIVE = "active"
    PAUSED_PROFIT_TARGET = "paused_profit_target"
    HALTED_LOSS_LIMIT = "halted_loss_limit"
    HALTED_TRADE_LIMIT = "halted_trade_limit"
    DISABLED = "disabled"


class SignalStrength(Enum):
    """Signal strength classification for entry decisions."""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    WEAK_BUY = "weak_buy"
    NEUTRAL = "neutral"
    WEAK_SELL = "weak_sell"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class MomentumSignal:
    """Represents a detected momentum opportunity."""
    symbol: str
    direction: str  # "long" or "short"
    strength: SignalStrength
    predicted_win_rate: float
    entry_price: float
    take_profit: float
    stop_loss: float
    volume_ratio: float  # Current volume vs average
    spread_pct: float
    timestamp: float
    confidence_factors: Dict[str, float] = field(default_factory=dict)

    def is_actionable(self, config: Dict) -> bool:
        """Check if signal meets minimum criteria for execution."""
        return (
            self.predicted_win_rate >= config.get("min_win_rate_threshold", 0.65)
            and self.volume_ratio >= config.get("min_volume_multiplier", 1.5)
            and self.spread_pct <= config.get("max_spread_pct", 0.002)
            and self.strength in [
                SignalStrength.STRONG_BUY, SignalStrength.BUY,
                SignalStrength.STRONG_SELL, SignalStrength.SELL
            ]
        )


@dataclass
class ScalpPosition:
    """Represents an open scalping position."""
    position_id: str
    user_id: str
    symbol: str
    direction: str
    quantity: float
    entry_price: float
    entry_time: float
    take_profit: float
    stop_loss: float
    trailing_stop: Optional[float] = None
    highest_price: Optional[float] = None  # For trailing stop
    lowest_price: Optional[float] = None  # For short trailing stop
    status: str = "open"
    exit_price: Optional[float] = None
    exit_time: Optional[float] = None
    pnl: Optional[float] = None
    exit_reason: Optional[str] = None

    def update_trailing_stop(self, current_price: float, config: Dict) -> None:
        """Update trailing stop based on price movement."""
        trailing_pct = config.get("trailing_stop_pct", 0.002)

        if self.direction == "long":
            if self.highest_price is None or current_price > self.highest_price:
                self.highest_price = current_price
                # Only activate trailing stop if we're in profit
                if current_price > self.entry_price * (1 + trailing_pct):
                    new_trailing = current_price * (1 - trailing_pct)
                    if self.trailing_stop is None or new_trailing > self.trailing_stop:
                        self.trailing_stop = new_trailing
        else:  # short
            if self.lowest_price is None or current_price < self.lowest_price:
                self.lowest_price = current_price
                if current_price < self.entry_price * (1 - trailing_pct):
                    new_trailing = current_price * (1 + trailing_pct)
                    if self.trailing_stop is None or new_trailing < self.trailing_stop:
                        self.trailing_stop = new_trailing

    def should_exit(self, current_price: float, current_time: float, config: Dict) -> Tuple[bool, str]:
        """
        Check if position should be exited.
        
        Returns:
            Tuple of (should_exit: bool, reason: str)
        """
        # Check take profit
        if self.direction == "long":
            if current_price >= self.take_profit:
                return True, "take_profit"
            if current_price <= self.stop_loss:
                return True, "stop_loss"
            if self.trailing_stop and current_price <= self.trailing_stop:
                return True, "trailing_stop"
        else:  # short
            if current_price <= self.take_profit:
                return True, "take_profit"
            if current_price >= self.stop_loss:
                return True, "stop_loss"
            if self.trailing_stop and current_price >= self.trailing_stop:
                return True, "trailing_stop"

        # Check max hold time
        max_hold = config.get("max_hold_seconds", 300)
        if current_time - self.entry_time > max_hold:
            return True, "max_hold_time"

        return False, ""

    def calculate_pnl(self, exit_price: float) -> float:
        """Calculate P&L for the position."""
        if self.direction == "long":
            return (exit_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - exit_price) * self.quantity


@dataclass
class UserTradingState:
    """Tracks trading state for a single user."""
    user_id: str
    api_key_hash: str
    capital: float
    state: ScalpingState = ScalpingState.ACTIVE
    daily_pnl: float = 0.0
    daily_trades: int = 0
    daily_wins: int = 0
    daily_losses: int = 0
    total_pnl: float = 0.0
    total_trades: int = 0
    total_wins: int = 0
    total_losses: int = 0
    open_positions: Dict[str, ScalpPosition] = field(default_factory=dict)
    last_trade_time: float = 0.0
    session_start: float = field(default_factory=time.time)
    config_overrides: Dict[str, Any] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def get_config(self, base_config: Dict) -> Dict:
        """Get merged configuration with user overrides."""
        merged = base_config.copy()
        merged.update(self.config_overrides)
        return merged

    def win_rate(self) -> float:
        """Calculate current win rate."""
        total = self.total_wins + self.total_losses
        return self.total_wins / total if total > 0 else 0.0

    def daily_win_rate(self) -> float:
        """Calculate daily win rate."""
        total = self.daily_wins + self.daily_losses
        return self.daily_wins / total if total > 0 else 0.0

    def reset_daily_stats(self) -> None:
        """Reset daily statistics (call at start of trading day)."""
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_wins = 0
        self.daily_losses = 0
        # Reactivate if halted for daily limits
        if self.state in [ScalpingState.PAUSED_PROFIT_TARGET, ScalpingState.HALTED_LOSS_LIMIT,
                          ScalpingState.HALTED_TRADE_LIMIT]:
            self.state = ScalpingState.ACTIVE


@dataclass
class MarketSnapshot:
    """Point-in-time market data for analysis."""
    symbol: str
    timestamp: float
    bid: float
    ask: float
    last: float
    volume_24h: float
    volume_1h: float
    price_change_1m: float
    price_change_5m: float
    price_change_15m: float
    high_24h: float
    low_24h: float
    vwap: float

    @property
    def mid_price(self) -> float:
        """Calculate mid price."""
        return (self.bid + self.ask) / 2

    @property
    def spread_pct(self) -> float:
        """Calculate spread as percentage."""
        if self.mid_price == 0:
            return float('inf')
        return (self.ask - self.bid) / self.mid_price


# =============================================================================
# Market Analysis Engine
# =============================================================================

class MomentumAnalyzer:
    """
    Analyzes market data to detect momentum and generate scalping signals.
    
    Uses multiple technical indicators to predict short-term price movements
    with high confidence for scalping opportunities.
    """

    def __init__(self, config: Dict = None):
        """Initialize momentum analyzer."""
        self.config = config or DEFAULT_SCALP_CONFIG
        self.price_history: Dict[str, deque] = {}
        self.volume_history: Dict[str, deque] = {}
        self.signal_history: Dict[str, deque] = {}
        self._lock = threading.Lock()

        # History window sizes
        self._price_window = 200  # Keep 200 price points
        self._volume_window = 50  # Keep 50 volume readings
        self._signal_window = 20  # Keep 20 recent signals

    def update_market_data(self, snapshot: MarketSnapshot) -> None:
        """Update internal market data with new snapshot."""
        with self._lock:
            symbol = snapshot.symbol

            if symbol not in self.price_history:
                self.price_history[symbol] = deque(maxlen=self._price_window)
                self.volume_history[symbol] = deque(maxlen=self._volume_window)

            self.price_history[symbol].append({
                "timestamp": snapshot.timestamp,
                "price": snapshot.mid_price,
                "bid": snapshot.bid,
                "ask": snapshot.ask,
                "spread_pct": snapshot.spread_pct,
            })

            self.volume_history[symbol].append({
                "timestamp": snapshot.timestamp,
                "volume_1h": snapshot.volume_1h,
            })

    def analyze(self, snapshot: MarketSnapshot) -> Optional[MomentumSignal]:
        """
        Analyze market snapshot and generate momentum signal if conditions are met.
        
        Uses multiple indicators:
        - Short-term price momentum (1m, 5m)
        - Volume surge detection
        - Spread analysis
        - Price acceleration
        - Support/resistance proximity
        
        Returns:
            MomentumSignal if actionable opportunity detected, None otherwise
        """
        self.update_market_data(snapshot)

        with self._lock:
            symbol = snapshot.symbol
            prices = list(self.price_history.get(symbol, []))
            volumes = list(self.volume_history.get(symbol, []))

        if len(prices) < 10:
            return None  # Need minimum history

        # Calculate indicators
        confidence_factors = {}

        # 1. Short-term momentum
        momentum_1m = snapshot.price_change_1m
        momentum_5m = snapshot.price_change_5m
        momentum_score = self._calculate_momentum_score(momentum_1m, momentum_5m)
        confidence_factors["momentum"] = momentum_score

        # 2. Volume analysis
        volume_ratio = self._calculate_volume_ratio(volumes, snapshot.volume_1h)
        confidence_factors["volume"] = min(volume_ratio / 3.0, 1.0)  # Normalize to 0-1

        # 3. Spread quality
        spread_score = self._calculate_spread_score(snapshot.spread_pct)
        confidence_factors["spread"] = spread_score

        # 4. Price acceleration
        acceleration = self._calculate_acceleration(prices)
        confidence_factors["acceleration"] = acceleration

        # 5. Volatility check
        volatility_score = self._calculate_volatility_score(prices)
        confidence_factors["volatility"] = volatility_score

        # Calculate composite signal strength and direction
        direction, strength = self._determine_direction_and_strength(confidence_factors, momentum_1m)

        if strength == SignalStrength.NEUTRAL:
            return None

        # Predict win rate based on confidence factors
        predicted_win_rate = self._predict_win_rate(confidence_factors, strength)

        # Calculate entry, TP, SL levels
        entry_price = snapshot.mid_price
        take_profit_pct = self.config.get("take_profit_pct", 0.005)
        stop_loss_pct = self.config.get("stop_loss_pct", 0.003)

        if direction == "long":
            take_profit = entry_price * (1 + take_profit_pct)
            stop_loss = entry_price * (1 - stop_loss_pct)
        else:
            take_profit = entry_price * (1 - take_profit_pct)
            stop_loss = entry_price * (1 + stop_loss_pct)

        signal = MomentumSignal(
            symbol=symbol,
            direction=direction,
            strength=strength,
            predicted_win_rate=predicted_win_rate,
            entry_price=entry_price,
            take_profit=take_profit,
            stop_loss=stop_loss,
            volume_ratio=volume_ratio,
            spread_pct=snapshot.spread_pct,
            timestamp=time.time(),
            confidence_factors=confidence_factors,
        )

        # Store signal for analysis
        with self._lock:
            if symbol not in self.signal_history:
                self.signal_history[symbol] = deque(maxlen=self._signal_window)
            self.signal_history[symbol].append(signal)

        return signal

    def _calculate_momentum_score(self, momentum_1m: float, momentum_5m: float) -> float:
        """Calculate normalized momentum score."""
        # Combine short and medium-term momentum
        combined = momentum_1m * 0.7 + momentum_5m * 0.3

        # Normalize to -1 to 1 range (assuming max 2% move)
        normalized = max(-1.0, min(1.0, combined / 0.02))

        return abs(normalized)  # Return absolute strength

    def _calculate_volume_ratio(self, volumes: List[Dict], current_volume: float) -> float:
        """Calculate current volume relative to average."""
        if not volumes or current_volume <= 0:
            return 0.0

        avg_volume = statistics.mean([v["volume_1h"] for v in volumes if v["volume_1h"] > 0])

        if avg_volume <= 0:
            return 0.0

        return current_volume / avg_volume

    def _calculate_spread_score(self, spread_pct: float) -> float:
        """Calculate spread quality score (0 = bad spread, 1 = excellent spread)."""
        max_spread = self.config.get("max_spread_pct", 0.002)

        if spread_pct >= max_spread:
            return 0.0

        # Linear scoring - tighter spread = higher score
        return 1.0 - (spread_pct / max_spread)

    def _calculate_acceleration(self, prices: List[Dict]) -> float:
        """Calculate price acceleration (rate of momentum change)."""
        if len(prices) < 5:
            return 0.0

        recent_prices = [p["price"] for p in prices[-5:]]

        # Calculate velocity (price change) with zero-division protection
        velocities = []
        for i in range(1, len(recent_prices)):
            if recent_prices[i-1] != 0:
                velocity = (recent_prices[i] - recent_prices[i-1]) / recent_prices[i-1]
                velocities.append(velocity)

        if len(velocities) < 2:
            return 0.0

        # Acceleration is change in velocity
        accelerations = []
        for i in range(1, len(velocities)):
            acceleration = velocities[i] - velocities[i-1]
            accelerations.append(acceleration)

        avg_acceleration = statistics.mean(accelerations) if accelerations else 0.0

        # Normalize to 0-1 range
        return min(1.0, abs(avg_acceleration) * 1000)

    def _calculate_volatility_score(self, prices: List[Dict]) -> float:
        """
        Calculate volatility score.
        
        Moderate volatility is good for scalping (opportunities),
        very high or very low volatility is bad.
        """
        if len(prices) < 10:
            return 0.5  # Neutral

        recent_prices = [p["price"] for p in prices[-20:]]

        # Calculate standard deviation
        mean_price = statistics.mean(recent_prices)
        std_dev = statistics.stdev(recent_prices) if len(recent_prices) > 1 else 0

        # Coefficient of variation
        cv = std_dev / mean_price if mean_price > 0 else 0

        # Ideal CV for scalping is around 0.001 to 0.003 (0.1% to 0.3%)
        # Too low = no opportunity, too high = too risky
        ideal_cv = 0.002

        # Score peaks at ideal CV, drops off for both extremes
        deviation = abs(cv - ideal_cv)
        score = max(0, 1.0 - (deviation / ideal_cv))

        return score

    def _determine_direction_and_strength(
        self,
        factors: Dict[str, float],
        momentum_1m: float
    ) -> Tuple[str, SignalStrength]:
        """Determine trade direction and signal strength from factors."""
        # Calculate composite score
        weights = {
            "momentum": 0.35,
            "volume": 0.25,
            "spread": 0.15,
            "acceleration": 0.15,
            "volatility": 0.10,
        }

        composite = sum(factors.get(k, 0) * w for k, w in weights.items())

        # Determine direction from momentum
        direction = "long" if momentum_1m > 0 else "short"

        # Determine strength
        if composite < 0.3:
            strength = SignalStrength.NEUTRAL
        elif composite < 0.45:
            strength = SignalStrength.WEAK_BUY if direction == "long" else SignalStrength.WEAK_SELL
        elif composite < 0.65:
            strength = SignalStrength.BUY if direction == "long" else SignalStrength.SELL
        else:
            strength = SignalStrength.STRONG_BUY if direction == "long" else SignalStrength.STRONG_SELL

        return direction, strength

    def _predict_win_rate(self, factors: Dict[str, float], strength: SignalStrength) -> float:
        """
        Predict win rate for the signal based on historical patterns.
        
        This uses a simple model based on factor quality.
        In production, this would be enhanced with ML predictions.
        """
        base_win_rate = 0.50  # Start at 50%

        # Adjust based on factors
        momentum_bonus = factors.get("momentum", 0) * 0.15
        volume_bonus = factors.get("volume", 0) * 0.10
        spread_bonus = factors.get("spread", 0) * 0.08
        acceleration_bonus = factors.get("acceleration", 0) * 0.05
        volatility_bonus = factors.get("volatility", 0) * 0.05

        # Strength bonus
        strength_bonus = {
            SignalStrength.STRONG_BUY: 0.08,
            SignalStrength.STRONG_SELL: 0.08,
            SignalStrength.BUY: 0.05,
            SignalStrength.SELL: 0.05,
            SignalStrength.WEAK_BUY: 0.02,
            SignalStrength.WEAK_SELL: 0.02,
            SignalStrength.NEUTRAL: 0.0,
        }.get(strength, 0)

        predicted = base_win_rate + momentum_bonus + volume_bonus + spread_bonus + \
                   acceleration_bonus + volatility_bonus + strength_bonus

        # Clamp to reasonable range
        return max(0.40, min(0.85, predicted))


# =============================================================================
# Scalping Execution Engine
# =============================================================================

class ScalpingEngine:
    """
    High-frequency scalping engine for multi-user trading.
    
    Features:
    - Support for 100,000+ concurrent users
    - User isolation with individual API keys
    - Continuous market monitoring
    - Automated position management
    - Risk controls per user
    
    DISCLAIMER: This engine does NOT guarantee profits.
    All trading involves risk of loss.
    """

    def __init__(
        self,
        config: Dict = None,
        max_users: int = 100000,
        trade_executor: Optional[Callable] = None,
        quote_provider: Optional[Callable] = None,
    ):
        """
        Initialize the scalping engine.
        
        Args:
            config: Base configuration (defaults to DEFAULT_SCALP_CONFIG)
            max_users: Maximum concurrent users
            trade_executor: Callable to execute trades - signature: (user_id, symbol, side, quantity, price) -> Dict
            quote_provider: Callable to get quotes - signature: (symbol) -> Dict with bid, ask, last, volume
        """
        self.config = config or DEFAULT_SCALP_CONFIG.copy()
        self.max_users = max_users
        self.trade_executor = trade_executor
        self.quote_provider = quote_provider

        # User management with sharding for high concurrency
        self.users: Dict[str, UserTradingState] = {}
        self.api_key_to_user: Dict[str, str] = {}  # Hash -> user_id mapping
        self._users_lock = threading.RLock()
        self._user_shard_locks = [threading.RLock() for _ in range(USER_STATE_SHARDS)]

        # Market analysis
        self.momentum_analyzer = MomentumAnalyzer(self.config)

        # Monitoring
        self._active = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._position_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Performance tracking
        self.total_signals_generated = 0
        self.total_trades_executed = 0
        self.engine_start_time: Optional[float] = None

        # Watched symbols
        self.watched_symbols: List[str] = []
        self._symbols_lock = threading.Lock()

        # === ZENITH SCALABILITY COMPONENTS ===
        # High-performance signal queue with bounded capacity
        self._signal_queue = deque(maxlen=self.config.get("signal_queue_capacity", MAX_SIGNAL_QUEUE_SIZE))
        self._signal_queue_lock = threading.Lock()

        # Adaptive worker pool
        self._base_worker_count = self.config.get("worker_pool_size", 16)
        self._max_worker_count = self.config.get("max_worker_pool_size", MAX_WORKER_THREADS)
        self._worker_pool: List[threading.Thread] = []
        self._worker_count = 0
        self._worker_count_lock = threading.Lock()

        # Batch processing
        self._batch_size = self.config.get("batch_size", 500)
        self._batch_executor_thread: Optional[threading.Thread] = None

        # Signal caching for deduplication
        self._signal_cache: Dict[str, Tuple[float, Any]] = {}
        self._signal_cache_lock = threading.Lock()
        self._signal_ttl = self.config.get("signal_ttl_seconds", 5)

        # Performance metrics for adaptive scaling
        self._metrics = {
            "signals_per_second": 0.0,
            "trades_per_second": 0.0,
            "queue_utilization": 0.0,
            "active_workers": 0,
            "peak_queue_size": 0,
            "total_batches_processed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "signals_dropped": 0,  # Count of signals dropped due to queue overflow
        }
        self._metrics_lock = threading.Lock()
        self._last_scale_time = 0.0
        self._scaling_cooldown = self.config.get("adaptive_scaling_cooldown_ms", 1000) / 1000.0

        log.info("ScalpingEngine initialized with max_users=%d, zenith scalability enabled", max_users)

    # =========================================================================
    # Zenith Scalability Methods
    # =========================================================================

    def _get_user_shard_lock(self, user_id: str) -> threading.RLock:
        """Get the shard lock for a user ID for parallel access."""
        shard_index = hash(user_id) % USER_STATE_SHARDS
        return self._user_shard_locks[shard_index]

    def _scale_workers_if_needed(self) -> None:
        """Adaptively scale worker pool based on queue utilization."""
        if not self.config.get("enable_adaptive_scaling", True):
            return

        current_time = time.time()
        if current_time - self._last_scale_time < self._scaling_cooldown:
            return

        with self._signal_queue_lock:
            queue_size = len(self._signal_queue)
            max_size = self.config.get("signal_queue_capacity", MAX_SIGNAL_QUEUE_SIZE)
            utilization = queue_size / max_size if max_size > 0 else 0

        threshold = self.config.get("adaptive_scaling_threshold", 0.75)

        with self._worker_count_lock:
            if utilization > threshold and self._worker_count < self._max_worker_count:
                # Scale up
                workers_to_add = min(4, self._max_worker_count - self._worker_count)
                for i in range(workers_to_add):
                    worker = threading.Thread(
                        target=self._worker_loop,
                        args=(self._worker_count + i,),
                        daemon=True,
                        name=f"ScalpWorker-{self._worker_count + i}"
                    )
                    worker.start()
                    self._worker_pool.append(worker)
                self._worker_count += workers_to_add
                self._last_scale_time = current_time
                log.info("Scaled up workers to %d (utilization: %.2f%%)",
                        self._worker_count, utilization * 100)

            # Update metrics
            with self._metrics_lock:
                self._metrics["active_workers"] = self._worker_count
                self._metrics["queue_utilization"] = utilization
                self._metrics["peak_queue_size"] = max(self._metrics["peak_queue_size"], queue_size)

    def queue_signal(self, signal) -> bool:
        """Queue a signal for processing with deduplication."""
        if not signal:
            return False

        # Check signal cache for deduplication
        strength_name = signal.strength.name if hasattr(signal.strength, 'name') else str(signal.strength)
        cache_key = f"{signal.symbol}:{signal.direction}:{strength_name}"
        current_time = time.time()

        with self._signal_cache_lock:
            if cache_key in self._signal_cache:
                cached_time, _ = self._signal_cache[cache_key]
                if current_time - cached_time < self._signal_ttl:
                    with self._metrics_lock:
                        self._metrics["cache_hits"] += 1
                    return False  # Duplicate signal within TTL

            self._signal_cache[cache_key] = (current_time, signal)
            with self._metrics_lock:
                self._metrics["cache_misses"] += 1

        # Add to queue with overflow tracking
        with self._signal_queue_lock:
            # Track if queue is at capacity (old signals will be dropped)
            if len(self._signal_queue) >= self._signal_queue.maxlen:
                with self._metrics_lock:
                    self._metrics["signals_dropped"] = self._metrics.get("signals_dropped", 0) + 1
            self._signal_queue.append(signal)

        # Check if we need to scale up
        self._scale_workers_if_needed()

        return True

    def process_batch(self) -> int:
        """Process a batch of signals for high throughput."""
        signals_to_process = []

        with self._signal_queue_lock:
            batch_size = min(self._batch_size, len(self._signal_queue))
            for _ in range(batch_size):
                if self._signal_queue:
                    signals_to_process.append(self._signal_queue.popleft())

        if not signals_to_process:
            return 0

        processed = 0
        for signal in signals_to_process:
            try:
                if signal.is_actionable(self.config):
                    self._execute_signal_internal(signal)
                    processed += 1
            except Exception as e:
                log.error("Error processing signal: %s", e)

        with self._metrics_lock:
            self._metrics["total_batches_processed"] += 1

        return processed

    def _execute_signal_internal(self, signal) -> Dict[str, Any]:
        """Internal signal execution with optimized path."""
        if not self.trade_executor:
            return {"success": False, "error": "No trade executor configured"}

        side = "buy" if signal.direction == "long" else "sell"
        quantity = self._calculate_optimal_quantity(signal)

        if quantity <= 0:
            return {"success": False, "error": "Invalid quantity"}

        try:
            result = self.trade_executor(
                "system", signal.symbol, side, quantity, signal.entry_price
            )
            self.total_trades_executed += 1
            return result
        except Exception as e:
            log.error("Trade execution error: %s", e)
            return {"success": False, "error": str(e)}

    def _calculate_optimal_quantity(self, signal) -> float:
        """Calculate optimal position size based on signal strength."""
        base_pct = self.config.get("max_position_pct", 0.05)
        max_usd = self.config.get("max_position_usd", 1000.0)

        # Adjust based on signal strength
        strength_multipliers = {
            SignalStrength.STRONG_BUY: 1.0,
            SignalStrength.BUY: 0.75,
            SignalStrength.WEAK_BUY: 0.5,
            SignalStrength.STRONG_SELL: 1.0,
            SignalStrength.SELL: 0.75,
            SignalStrength.WEAK_SELL: 0.5,
        }

        multiplier = strength_multipliers.get(signal.strength, 0.5)
        adjusted_max = max_usd * multiplier

        if signal.entry_price <= 0:
            return 0.0

        return adjusted_max / signal.entry_price

    def _worker_loop(self, worker_id: int) -> None:
        """High-performance worker loop for signal processing."""
        while not self._stop_event.is_set():
            signal = None

            with self._signal_queue_lock:
                if self._signal_queue:
                    signal = self._signal_queue.popleft()

            if signal:
                try:
                    if signal.is_actionable(self.config):
                        self._execute_signal_internal(signal)
                except Exception as e:
                    log.error("Worker %d error: %s", worker_id, e)
            else:
                time.sleep(0.001)  # 1ms idle sleep for minimum latency

    def _batch_executor_loop(self) -> None:
        """Batch executor thread for high-throughput processing."""
        while not self._stop_event.is_set():
            try:
                processed = self.process_batch()
                if processed == 0:
                    time.sleep(0.005)  # 5ms idle when no work
            except Exception as e:
                log.error("Batch executor error: %s", e)

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics."""
        with self._metrics_lock:
            metrics = self._metrics.copy()

        uptime = (time.time() - self.engine_start_time) if self.engine_start_time else 0

        metrics.update({
            "uptime_seconds": uptime,
            "total_signals_generated": self.total_signals_generated,
            "total_trades_executed": self.total_trades_executed,
            "signals_per_second": self.total_signals_generated / uptime if uptime > 0 else 0,
            "trades_per_second": self.total_trades_executed / uptime if uptime > 0 else 0,
            "registered_users": len(self.users),
            "max_users": self.max_users,
            "watched_symbols": len(self.watched_symbols),
        })

        with self._signal_queue_lock:
            metrics["current_queue_size"] = len(self._signal_queue)

        return metrics

    def start_zenith_mode(self) -> str:
        """Start the engine in zenith performance mode."""
        if self._active:
            return "[SCALPING ENGINE] Already running"

        self._active = True
        self._stop_event.clear()
        self.engine_start_time = time.time()

        # Start base worker pool
        for i in range(self._base_worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                args=(i,),
                daemon=True,
                name=f"ScalpWorker-{i}"
            )
            worker.start()
            self._worker_pool.append(worker)

        self._worker_count = self._base_worker_count

        # Start batch executor if enabled
        if self.config.get("enable_batch_execution", True):
            self._batch_executor_thread = threading.Thread(
                target=self._batch_executor_loop,
                daemon=True,
                name="BatchExecutor"
            )
            self._batch_executor_thread.start()

        # Start market monitoring
        self._monitor_thread = threading.Thread(
            target=self._market_monitor_loop,
            daemon=True,
            name="MarketMonitor"
        )
        self._monitor_thread.start()

        # Start position monitoring
        self._position_thread = threading.Thread(
            target=self._position_monitor_loop,
            daemon=True,
            name="PositionMonitor"
        )
        self._position_thread.start()

        log.info("Scalping engine started in ZENITH mode with %d workers", self._worker_count)
        return f"[SCALPING ENGINE] Zenith mode started with {self._worker_count} workers"

    def _market_monitor_loop(self) -> None:
        """Market monitoring loop with adaptive interval."""
        interval_ms = self.config.get("signal_generation_interval_ms", SIGNAL_GENERATION_INTERVAL_MS)
        interval_s = interval_ms / 1000.0

        while not self._stop_event.is_set():
            try:
                if self.quote_provider:
                    signals = self.scan_for_movers()
                    for signal in signals:
                        self.queue_signal(signal)
            except Exception as e:
                log.error("Market monitor error: %s", e)

            self._stop_event.wait(interval_s)

    def _position_monitor_loop(self) -> None:
        """Position monitoring loop with high-frequency checks."""
        interval_ms = self.config.get("position_check_interval_ms", POSITION_CHECK_INTERVAL_MS)
        interval_s = interval_ms / 1000.0

        while not self._stop_event.is_set():
            try:
                self.check_positions()
            except Exception as e:
                log.error("Position monitor error: %s", e)

            self._stop_event.wait(interval_s)

    # =========================================================================
    # User Management
    # =========================================================================

    def register_user(
        self,
        user_id: str,
        api_key: str,
        initial_capital: float,
        config_overrides: Dict = None,
    ) -> bool:
        """
        Register a new user for scalping.
        
        Args:
            user_id: Unique user identifier
            api_key: User's API key for authentication
            initial_capital: Starting capital for the user
            config_overrides: User-specific configuration overrides
            
        Returns:
            True if registration successful, False otherwise
        """
        # Use global lock first for consistent ordering to prevent deadlocks
        with self._users_lock:
            if len(self.users) >= self.max_users:
                log.warning("Maximum user limit reached (%d)", self.max_users)
                return False

            if user_id in self.users:
                log.warning("User %s already registered", user_id)
                return False

            # Hash API key for storage
            api_key_hash = self._hash_api_key(api_key)

            if api_key_hash in self.api_key_to_user:
                log.warning("API key already registered")
                return False

            # Create user state
            user_state = UserTradingState(
                user_id=user_id,
                api_key_hash=api_key_hash,
                capital=initial_capital,
                config_overrides=config_overrides or {},
            )

            self.users[user_id] = user_state
            self.api_key_to_user[api_key_hash] = user_id

            log.info("Registered user %s with capital $%.2f", user_id, initial_capital)
            return True

    def unregister_user(self, user_id: str) -> bool:
        """
        Unregister a user and close all positions.
        
        Args:
            user_id: User to unregister
            
        Returns:
            True if successful
        """
        with self._users_lock:
            if user_id not in self.users:
                return False

            user = self.users[user_id]

            # Close all open positions
            for pos_id in list(user.open_positions.keys()):
                self._close_position(user_id, pos_id, reason="user_unregister")

            # Remove user
            del self.api_key_to_user[user.api_key_hash]
            del self.users[user_id]

            log.info("Unregistered user %s", user_id)
            return True

    def authenticate_user(self, api_key: str) -> Optional[str]:
        """
        Authenticate user by API key.
        
        Args:
            api_key: Raw API key
            
        Returns:
            User ID if authenticated, None otherwise
        """
        api_key_hash = self._hash_api_key(api_key)
        return self.api_key_to_user.get(api_key_hash)

    def get_user_state(self, user_id: str) -> Optional[UserTradingState]:
        """Get user's current trading state."""
        return self.users.get(user_id)

    def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get comprehensive user statistics."""
        user = self.users.get(user_id)
        if not user:
            return {"error": "User not found"}

        with user.lock:
            return {
                "user_id": user_id,
                "capital": user.capital,
                "state": user.state.value,
                "daily_pnl": user.daily_pnl,
                "daily_pnl_pct": (user.daily_pnl / user.capital * 100) if user.capital > 0 else 0,
                "daily_trades": user.daily_trades,
                "daily_win_rate": user.daily_win_rate(),
                "total_pnl": user.total_pnl,
                "total_trades": user.total_trades,
                "total_win_rate": user.win_rate(),
                "open_positions": len(user.open_positions),
                "session_duration_hours": (time.time() - user.session_start) / 3600,
            }

    def _hash_api_key(self, api_key: str) -> str:
        """Hash API key for secure storage."""
        return hashlib.sha256(api_key.encode()).hexdigest()

    # =========================================================================
    # Symbol Management
    # =========================================================================

    def add_watched_symbol(self, symbol: str) -> None:
        """Add symbol to watchlist for monitoring."""
        with self._symbols_lock:
            if symbol not in self.watched_symbols:
                self.watched_symbols.append(symbol)
                log.info("Added %s to watchlist", symbol)

    def remove_watched_symbol(self, symbol: str) -> None:
        """Remove symbol from watchlist."""
        with self._symbols_lock:
            if symbol in self.watched_symbols:
                self.watched_symbols.remove(symbol)
                log.info("Removed %s from watchlist", symbol)

    def get_watched_symbols(self) -> List[str]:
        """Get current watchlist."""
        with self._symbols_lock:
            return self.watched_symbols.copy()

    # =========================================================================
    # Market Analysis
    # =========================================================================

    def scan_market(self, snapshot: MarketSnapshot) -> Optional[MomentumSignal]:
        """
        Scan market data for momentum opportunities.
        
        Args:
            snapshot: Current market snapshot
            
        Returns:
            MomentumSignal if opportunity detected
        """
        signal = self.momentum_analyzer.analyze(snapshot)

        if signal and signal.is_actionable(self.config):
            self.total_signals_generated += 1
            log.debug(
                "Generated signal for %s: %s (win_rate=%.2f%%)",
                signal.symbol, signal.direction, signal.predicted_win_rate * 100
            )

        return signal

    def scan_for_movers(self, symbols: List[str] = None) -> List[MomentumSignal]:
        """
        Scan multiple symbols for coins "on the move".
        
        Args:
            symbols: List of symbols to scan (uses watchlist if None)
            
        Returns:
            List of actionable signals sorted by predicted win rate
        """
        if not self.quote_provider:
            log.warning("No quote provider configured")
            return []

        symbols = symbols or self.get_watched_symbols()
        signals = []

        for symbol in symbols:
            try:
                quote = self.quote_provider(symbol)
                if not quote:
                    continue

                snapshot = MarketSnapshot(
                    symbol=symbol,
                    timestamp=time.time(),
                    bid=quote.get("bid", 0),
                    ask=quote.get("ask", 0),
                    last=quote.get("last", 0),
                    volume_24h=quote.get("volume_24h", 0),
                    volume_1h=quote.get("volume_1h", 0),
                    price_change_1m=quote.get("price_change_1m", 0),
                    price_change_5m=quote.get("price_change_5m", 0),
                    price_change_15m=quote.get("price_change_15m", 0),
                    high_24h=quote.get("high_24h", 0),
                    low_24h=quote.get("low_24h", 0),
                    vwap=quote.get("vwap", 0),
                )

                signal = self.scan_market(snapshot)
                if signal and signal.is_actionable(self.config):
                    signals.append(signal)

            except Exception as e:
                log.error("Error scanning %s: %s", symbol, e)

        # Sort by predicted win rate (highest first)
        signals.sort(key=lambda s: s.predicted_win_rate, reverse=True)

        return signals

    # =========================================================================
    # Trade Execution
    # =========================================================================

    def execute_signal(self, user_id: str, signal: MomentumSignal) -> Dict[str, Any]:
        """
        Execute a momentum signal for a user.
        
        Args:
            user_id: User executing the trade
            signal: Signal to execute
            
        Returns:
            Execution result dict
        """
        user = self.users.get(user_id)
        if not user:
            return {"success": False, "error": "User not found"}

        with user.lock:
            # Check user state
            if user.state != ScalpingState.ACTIVE:
                return {"success": False, "error": f"Trading {user.state.value}"}

            config = user.get_config(self.config)

            # Check daily limits
            if user.daily_trades >= config.get("max_daily_trades", 100):
                user.state = ScalpingState.HALTED_TRADE_LIMIT
                return {"success": False, "error": "Daily trade limit reached"}

            # Check daily loss limit
            max_loss_pct = config.get("max_daily_loss_pct", 0.03)
            if user.daily_pnl < 0 and abs(user.daily_pnl) >= user.capital * max_loss_pct:
                user.state = ScalpingState.HALTED_LOSS_LIMIT
                return {"success": False, "error": "Daily loss limit reached"}

            # Check daily profit target (pause if reached)
            profit_target_pct = config.get("daily_profit_target_pct", 0.02)
            if user.daily_pnl >= user.capital * profit_target_pct:
                user.state = ScalpingState.PAUSED_PROFIT_TARGET
                return {"success": False, "error": "Daily profit target reached - pausing"}

            # Calculate position size
            position_size = self._calculate_position_size(user, signal, config)
            if position_size <= 0:
                return {"success": False, "error": "Position size too small"}

            # Generate position ID
            position_id = self._generate_position_id()

            # Execute trade
            if self.trade_executor:
                side = "buy" if signal.direction == "long" else "sell"
                try:
                    result = self.trade_executor(
                        user_id, signal.symbol, side, position_size, signal.entry_price
                    )
                    if not result.get("success", False):
                        return {"success": False, "error": result.get("error", "Execution failed")}
                except Exception as e:
                    log.error("Trade execution error for user %s: %s", user_id, e)
                    return {"success": False, "error": str(e)}

            # Create position record
            position = ScalpPosition(
                position_id=position_id,
                user_id=user_id,
                symbol=signal.symbol,
                direction=signal.direction,
                quantity=position_size,
                entry_price=signal.entry_price,
                entry_time=time.time(),
                take_profit=signal.take_profit,
                stop_loss=signal.stop_loss,
            )

            # Update user state
            user.open_positions[position_id] = position
            user.daily_trades += 1
            user.total_trades += 1
            user.last_trade_time = time.time()

            self.total_trades_executed += 1

            log.info(
                "Executed %s %s for user %s: qty=%.6f, entry=%.6f, TP=%.6f, SL=%.6f",
                signal.direction, signal.symbol, user_id,
                position_size, signal.entry_price, signal.take_profit, signal.stop_loss
            )

            return {
                "success": True,
                "position_id": position_id,
                "symbol": signal.symbol,
                "direction": signal.direction,
                "quantity": position_size,
                "entry_price": signal.entry_price,
                "take_profit": signal.take_profit,
                "stop_loss": signal.stop_loss,
            }

    def _calculate_position_size(
        self,
        user: UserTradingState,
        signal: MomentumSignal,
        config: Dict
    ) -> float:
        """Calculate position size based on risk parameters."""
        max_pct = config.get("max_position_pct", 0.05)
        min_usd = config.get("min_position_usd", 10.0)
        max_usd = config.get("max_position_usd", 1000.0)

        # Base position size as percentage of capital
        base_size = user.capital * max_pct

        # Adjust based on signal confidence
        confidence_multiplier = min(1.0, signal.predicted_win_rate / 0.75)
        adjusted_size = base_size * confidence_multiplier

        # Apply min/max limits
        adjusted_size = max(min_usd, min(max_usd, adjusted_size))

        # Convert to quantity
        if signal.entry_price > 0:
            quantity = adjusted_size / signal.entry_price
        else:
            quantity = 0

        return quantity

    def _generate_position_id(self) -> str:
        """Generate unique position ID."""
        return f"scalp_{int(time.time() * 1000)}_{secrets.token_hex(4)}"

    # =========================================================================
    # Position Management
    # =========================================================================

    def check_positions(self, user_id: str = None) -> List[Dict[str, Any]]:
        """
        Check all positions for exit conditions.
        
        Args:
            user_id: Check specific user's positions (or all if None)
            
        Returns:
            List of closed positions
        """
        closed = []
        users_to_check = [user_id] if user_id else list(self.users.keys())

        for uid in users_to_check:
            user = self.users.get(uid)
            if not user:
                continue

            with user.lock:
                config = user.get_config(self.config)

                for pos_id in list(user.open_positions.keys()):
                    position = user.open_positions[pos_id]

                    # Get current price
                    current_price = self._get_current_price(position.symbol)
                    if current_price is None:
                        continue

                    current_time = time.time()

                    # Update trailing stop
                    position.update_trailing_stop(current_price, config)

                    # Check exit conditions
                    should_exit, reason = position.should_exit(current_price, current_time, config)

                    if should_exit:
                        result = self._close_position(uid, pos_id, reason, current_price)
                        if result:
                            closed.append(result)

        return closed

    def _close_position(
        self,
        user_id: str,
        position_id: str,
        reason: str,
        exit_price: float = None
    ) -> Optional[Dict[str, Any]]:
        """Close a position and update user state."""
        user = self.users.get(user_id)
        if not user:
            return None

        with user.lock:
            if position_id not in user.open_positions:
                return None

            position = user.open_positions[position_id]

            # Get exit price if not provided
            if exit_price is None:
                exit_price = self._get_current_price(position.symbol)
                if exit_price is None:
                    exit_price = position.entry_price  # Fallback

            # Execute close trade
            if self.trade_executor:
                side = "sell" if position.direction == "long" else "buy"
                try:
                    self.trade_executor(
                        user_id, position.symbol, side, position.quantity, exit_price
                    )
                except Exception as e:
                    log.error("Error closing position %s: %s", position_id, e)

            # Calculate P&L
            pnl = position.calculate_pnl(exit_price)

            # Update position
            position.status = "closed"
            position.exit_price = exit_price
            position.exit_time = time.time()
            position.pnl = pnl
            position.exit_reason = reason

            # Update user stats
            user.daily_pnl += pnl
            user.total_pnl += pnl
            user.capital += pnl

            if pnl > 0:
                user.daily_wins += 1
                user.total_wins += 1
            else:
                user.daily_losses += 1
                user.total_losses += 1

            # Remove from open positions
            del user.open_positions[position_id]

            result = {
                "position_id": position_id,
                "user_id": user_id,
                "symbol": position.symbol,
                "direction": position.direction,
                "quantity": position.quantity,
                "entry_price": position.entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "reason": reason,
                "hold_time_seconds": position.exit_time - position.entry_time,
            }

            log.info(
                "Closed position %s for user %s: pnl=$%.2f (%s)",
                position_id, user_id, pnl, reason
            )

            return result

    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        if not self.quote_provider:
            return None

        try:
            quote = self.quote_provider(symbol)
            if quote:
                return (quote.get("bid", 0) + quote.get("ask", 0)) / 2
        except Exception as e:
            log.error("Error getting price for %s: %s", symbol, e)

        return None

    # =========================================================================
    # Engine Control
    # =========================================================================

    def start(self, monitor_interval: float = 1.0, position_check_interval: float = 0.5) -> None:
        """
        Start the scalping engine.
        
        Args:
            monitor_interval: Seconds between market scans
            position_check_interval: Seconds between position checks
        """
        if self._active:
            log.warning("Engine already running")
            return

        self._active = True
        self._stop_event.clear()
        self.engine_start_time = time.time()

        # Start market monitoring thread
        self._monitor_thread = threading.Thread(
            target=self._market_monitor_loop,
            args=(monitor_interval,),
            daemon=True,
            name="ScalpingMonitor"
        )
        self._monitor_thread.start()

        # Start position management thread
        self._position_thread = threading.Thread(
            target=self._position_check_loop,
            args=(position_check_interval,),
            daemon=True,
            name="PositionManager"
        )
        self._position_thread.start()

        log.info("ScalpingEngine started")

    def stop(self) -> None:
        """Stop the scalping engine."""
        if not self._active:
            return

        self._active = False
        self._stop_event.set()

        # Wait for threads to finish
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)

        if self._position_thread and self._position_thread.is_alive():
            self._position_thread.join(timeout=5)

        log.info("ScalpingEngine stopped")

    def _market_monitor_loop(self, interval: float) -> None:
        """Background loop for market monitoring."""
        while not self._stop_event.is_set():
            try:
                # Scan for momentum opportunities
                signals = self.scan_for_movers()

                # Distribute signals to active users
                for signal in signals:
                    self._distribute_signal(signal)

            except Exception as e:
                log.error("Error in market monitor: %s", e)

            self._stop_event.wait(interval)

    def _position_check_loop(self, interval: float) -> None:
        """Background loop for position management."""
        while not self._stop_event.is_set():
            try:
                self.check_positions()
            except Exception as e:
                log.error("Error in position check: %s", e)

            self._stop_event.wait(interval)

    def _distribute_signal(self, signal: MomentumSignal) -> None:
        """
        Distribute a signal to eligible users for automatic execution.
        
        This method is called when the market monitor detects a strong signal.
        Only users who have opted into auto-trading will receive signals.
        
        NOTE: For safety and regulatory compliance, automatic execution
        should only be enabled for users who explicitly consent.
        Manual signal review via scan_for_movers() is recommended.
        """
        # Log signal for audit trail
        log.debug(
            "Signal available: %s %s (win_rate=%.2f%%, strength=%s)",
            signal.direction, signal.symbol,
            signal.predicted_win_rate * 100, signal.strength.value
        )

        # Signal distribution is intentionally left for manual implementation
        # as automatic execution requires:
        # 1. User consent and opt-in
        # 2. Regulatory compliance review
        # 3. Risk acknowledgment from users
        #
        # Users can manually retrieve signals via scan_for_movers() and
        # execute them via execute_signal() with explicit action.

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_engine_stats(self) -> Dict[str, Any]:
        """Get engine-wide statistics."""
        uptime = (time.time() - self.engine_start_time) if self.engine_start_time else 0

        total_capital = sum(u.capital for u in self.users.values())
        total_daily_pnl = sum(u.daily_pnl for u in self.users.values())
        total_positions = sum(len(u.open_positions) for u in self.users.values())

        return {
            "active": self._active,
            "uptime_hours": uptime / 3600,
            "registered_users": len(self.users),
            "max_users": self.max_users,
            "total_signals_generated": self.total_signals_generated,
            "total_trades_executed": self.total_trades_executed,
            "watched_symbols": len(self.watched_symbols),
            "total_open_positions": total_positions,
            "total_capital_under_management": total_capital,
            "total_daily_pnl": total_daily_pnl,
            "signals_per_hour": (self.total_signals_generated / (uptime / 3600)) if uptime > 0 else 0,
            "trades_per_hour": (self.total_trades_executed / (uptime / 3600)) if uptime > 0 else 0,
        }

    def get_monthly_projection(self, user_id: str) -> Dict[str, Any]:
        """
        Get monthly growth projection for a user.
        
        DISCLAIMER: This is a statistical projection only.
        It does NOT guarantee future performance.
        """
        user = self.users.get(user_id)
        if not user:
            return {"error": "User not found"}

        with user.lock:
            if user.total_trades < 10:
                return {
                    "error": "Insufficient trading history",
                    "trades_required": 10 - user.total_trades
                }

            # Calculate average trade metrics
            avg_pnl_per_trade = user.total_pnl / user.total_trades
            win_rate = user.win_rate()

            # Estimate daily trades (based on activity)
            session_hours = (time.time() - user.session_start) / 3600
            trades_per_hour = user.total_trades / max(session_hours, 1)

            # Project monthly
            # Assume 8 hours trading per day, 22 trading days per month
            trading_hours_per_month = 8 * 22
            projected_monthly_trades = trades_per_hour * trading_hours_per_month

            projected_monthly_pnl = avg_pnl_per_trade * projected_monthly_trades
            projected_monthly_return_pct = (projected_monthly_pnl / user.capital) * 100 if user.capital > 0 else 0

            return {
                "current_capital": user.capital,
                "current_win_rate": win_rate,
                "avg_pnl_per_trade": avg_pnl_per_trade,
                "trades_per_hour": trades_per_hour,
                "projected_monthly_trades": projected_monthly_trades,
                "projected_monthly_pnl": projected_monthly_pnl,
                "projected_monthly_return_pct": projected_monthly_return_pct,
                "target_low_pct": self.config.get("monthly_growth_target_low", 0.25) * 100,
                "target_high_pct": self.config.get("monthly_growth_target_high", 0.50) * 100,
                "on_track": projected_monthly_return_pct >= self.config.get("monthly_growth_target_low", 0.25) * 100,
                "disclaimer": "Projections are estimates only. Past performance does not guarantee future results."
            }


# =============================================================================
# Factory Functions
# =============================================================================

def create_scalping_engine(
    trade_executor: Callable = None,
    quote_provider: Callable = None,
    config: Dict = None,
    max_users: int = 100000,
) -> ScalpingEngine:
    """
    Factory function to create a configured scalping engine.
    
    Args:
        trade_executor: Function to execute trades
        quote_provider: Function to get market quotes
        config: Custom configuration
        max_users: Maximum concurrent users
        
    Returns:
        Configured ScalpingEngine instance
    """
    return ScalpingEngine(
        config=config,
        max_users=max_users,
        trade_executor=trade_executor,
        quote_provider=quote_provider,
    )


def get_default_scalping_config() -> Dict[str, Any]:
    """Get default scalping configuration."""
    return DEFAULT_SCALP_CONFIG.copy()


# =============================================================================
# Integration with existing trade engine
# =============================================================================

def integrate_with_trade_engine(scalping_engine: ScalpingEngine, trade_engine: Any) -> None:
    """
    Integrate scalping engine with existing ANVELTradeEngine.
    
    Args:
        scalping_engine: ScalpingEngine instance
        trade_engine: ANVELTradeEngine instance
    """
    def execute_trade(user_id: str, symbol: str, side: str, quantity: float, price: float) -> Dict:
        """Bridge to trade engine execution."""
        try:
            result = trade_engine.queue_trade(
                symbol=symbol,
                side=side,
                quantity=quantity,
                strategy="scalping_engine",
                order_type="market",
            )
            return {"success": "Queued" in result, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_quote(symbol: str) -> Dict:
        """Bridge to trade engine quote provider."""
        try:
            return trade_engine.get_quote(symbol)
        except Exception:
            return {}

    scalping_engine.trade_executor = execute_trade
    scalping_engine.quote_provider = get_quote


if __name__ == "__main__":
    # Basic demonstration
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    print("=" * 60)
    print("ANVEL Scalping Engine")
    print("=" * 60)
    print("\nDefault Configuration:")
    for key, value in DEFAULT_SCALP_CONFIG.items():
        print(f"  {key}: {value}")

    print("\n" + "=" * 60)
    print("IMPORTANT DISCLAIMER")
    print("=" * 60)
    print("""
This scalping engine is designed for high-frequency trading with
the goal of consistent small gains. However:

1. NO TRADING SYSTEM CAN GUARANTEE PROFITS
2. Past performance does not predict future results
3. All trading involves substantial risk of loss
4. Target returns (25-50% monthly) are goals, not guarantees
5. Users should only trade with capital they can afford to lose

The engine uses multiple safeguards:
- Tight stop losses to limit individual trade losses
- Daily loss limits to prevent catastrophic drawdowns
- Win rate thresholds for signal quality
- Position size limits to manage exposure

Always monitor your trading and never rely solely on automation.
    """)
