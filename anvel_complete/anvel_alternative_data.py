"""
VEL Alternative Data Integration Module

Phase 4.1: Alternative Data Integration for Enhanced Market Intelligence
- Social sentiment analysis (Twitter/X, Reddit, Discord)
- On-chain analytics (whale tracking, DEX flows, gas prices)
- Order book microstructure analysis
- Funding rates and open interest
- News NLP with named entity recognition

This module provides an information edge through non-traditional data sources.
"""

import logging
import threading
import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
from collections import deque
import math

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Data Classes
# =============================================================================


class SentimentSource(Enum):
    """Sources for sentiment data."""

    TWITTER = "twitter"
    REDDIT = "reddit"
    DISCORD = "discord"
    NEWS = "news"
    TELEGRAM = "telegram"


class SentimentLevel(Enum):
    """Sentiment classification levels."""

    VERY_BEARISH = -2
    BEARISH = -1
    NEUTRAL = 0
    BULLISH = 1
    VERY_BULLISH = 2


class OnChainEventType(Enum):
    """Types of on-chain events."""

    WHALE_TRANSFER = auto()
    DEX_SWAP = auto()
    LIQUIDITY_ADD = auto()
    LIQUIDITY_REMOVE = auto()
    NFT_SALE = auto()
    CONTRACT_DEPLOYMENT = auto()
    GAS_SPIKE = auto()
    EXCHANGE_INFLOW = auto()
    EXCHANGE_OUTFLOW = auto()


class OrderFlowType(Enum):
    """Types of order flow signals."""

    IMBALANCE = auto()
    TOXICITY = auto()
    MOMENTUM = auto()
    ABSORPTION = auto()
    SPOOFING = auto()


@dataclass
class SentimentSignal:
    """Sentiment signal from a data source."""

    source: SentimentSource
    asset: str
    sentiment_score: float  # -1 to 1
    confidence: float  # 0 to 1
    volume: int  # Number of data points
    timestamp: datetime
    level: SentimentLevel = SentimentLevel.NEUTRAL
    keywords: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Classify sentiment level based on score."""
        if self.sentiment_score <= -0.6:
            self.level = SentimentLevel.VERY_BEARISH
        elif self.sentiment_score <= -0.2:
            self.level = SentimentLevel.BEARISH
        elif self.sentiment_score >= 0.6:
            self.level = SentimentLevel.VERY_BULLISH
        elif self.sentiment_score >= 0.2:
            self.level = SentimentLevel.BULLISH
        else:
            self.level = SentimentLevel.NEUTRAL


@dataclass
class OnChainMetrics:
    """On-chain analytics metrics."""

    blockchain: str
    asset: str
    timestamp: datetime
    whale_transfers: int
    whale_volume: float
    exchange_inflow: float
    exchange_outflow: float
    dex_volume: float
    active_addresses: int
    gas_price: float
    funding_rate: Optional[float] = None
    open_interest: Optional[float] = None
    net_flow: float = 0.0

    def __post_init__(self):
        """Calculate net flow."""
        self.net_flow = self.exchange_inflow - self.exchange_outflow


@dataclass
class OrderFlowSignal:
    """Order flow analysis signal."""

    exchange: str
    asset: str
    timestamp: datetime
    signal_type: OrderFlowType
    value: float
    direction: int  # -1 sell pressure, 0 neutral, 1 buy pressure
    confidence: float
    bid_depth: float = 0.0
    ask_depth: float = 0.0
    imbalance_ratio: float = 0.0

    def __post_init__(self):
        """Calculate imbalance ratio."""
        total_depth = self.bid_depth + self.ask_depth
        if total_depth > 0:
            self.imbalance_ratio = (self.bid_depth - self.ask_depth) / total_depth


@dataclass
class NewsArticle:
    """Parsed news article with NLP analysis."""

    title: str
    content: str
    source: str
    timestamp: datetime
    entities: List[str]
    sentiment_score: float
    relevance_score: float
    keywords: List[str]
    category: str = "general"


@dataclass
class MarketIntelligence:
    """Aggregated market intelligence from all sources."""

    asset: str
    timestamp: datetime
    sentiment_signals: List[SentimentSignal]
    onchain_metrics: Optional[OnChainMetrics]
    orderflow_signals: List[OrderFlowSignal]
    news_articles: List[NewsArticle]
    composite_score: float = 0.0
    confidence: float = 0.0

    def calculate_composite(self) -> float:
        """Calculate composite intelligence score."""
        scores = []
        weights = []

        # Sentiment component
        if self.sentiment_signals:
            avg_sentiment = sum(
                s.sentiment_score * s.confidence for s in self.sentiment_signals
            ) / len(self.sentiment_signals)
            scores.append(avg_sentiment)
            weights.append(0.3)

        # On-chain component
        if self.onchain_metrics:
            # Normalize net flow to -1 to 1
            flow_signal = math.tanh(self.onchain_metrics.net_flow / 1000000)
            scores.append(flow_signal)
            weights.append(0.25)

        # Order flow component
        if self.orderflow_signals:
            avg_direction = sum(
                s.direction * s.confidence for s in self.orderflow_signals
            ) / len(self.orderflow_signals)
            scores.append(avg_direction)
            weights.append(0.25)

        # News component
        if self.news_articles:
            avg_news_sentiment = sum(
                a.sentiment_score * a.relevance_score for a in self.news_articles
            ) / len(self.news_articles)
            scores.append(avg_news_sentiment)
            weights.append(0.2)

        if not scores:
            return 0.0

        # Weighted average
        total_weight = sum(weights)
        self.composite_score = (
            sum(s * w for s, w in zip(scores, weights)) / total_weight
        )
        self.confidence = total_weight
        return self.composite_score


# =============================================================================
# Base Processor Classes
# =============================================================================


class DataProcessor(ABC):
    """Abstract base class for data processors."""

    @abstractmethod
    def process(self, data: Any) -> Any:
        """Process raw data and return structured output."""
        raise NotImplementedError

    @abstractmethod
    def validate(self, data: Any) -> bool:
        """Validate input data."""
        raise NotImplementedError


# =============================================================================
# Sentiment Analysis
# =============================================================================


class SentimentAnalyzer:
    """
    Multi-source sentiment analysis engine.

    Analyzes text data from various sources to extract sentiment signals.
    Uses lexicon-based and pattern-based analysis.
    """

    # Sentiment lexicon (simplified - in production, use a full lexicon)
    BULLISH_WORDS = {
        "moon",
        "pump",
        "bullish",
        "buy",
        "long",
        "breakout",
        "ath",
        "rally",
        "surge",
        "soar",
        "rocket",
        "gain",
        "profit",
        "up",
        "green",
        "hodl",
        "accumulate",
        "undervalued",
        "opportunity",
        "bullrun",
        "fomo",
    }

    BEARISH_WORDS = {
        "dump",
        "crash",
        "bearish",
        "sell",
        "short",
        "breakdown",
        "atl",
        "plunge",
        "tank",
        "drop",
        "fall",
        "loss",
        "down",
        "red",
        "panic",
        "exit",
        "overvalued",
        "bubble",
        "scam",
        "rug",
        "fear",
    }

    INTENSIFIERS = {"very", "extremely", "super", "mega", "ultra", "absolutely"}
    NEGATORS = {"not", "no", "never", "neither", "don't", "doesn't", "won't"}

    def __init__(self):
        """Initialize the sentiment analyzer."""
        self._lock = threading.RLock()
        self._cache: Dict[str, Tuple[float, datetime]] = {}
        self._cache_ttl = timedelta(minutes=5)

    def analyze_text(self, text: str, asset: str = "") -> Tuple[float, float]:
        """
        Analyze sentiment of a single text.

        Args:
            text: Text to analyze
            asset: Optional asset context

        Returns:
            Tuple of (sentiment_score, confidence)
        """
        if not text or not text.strip():
            return 0.0, 0.0

        # Check cache
        cache_key = hashlib.md5(text.encode()).hexdigest()
        with self._lock:
            if cache_key in self._cache:
                score, cached_time = self._cache[cache_key]
                if datetime.now() - cached_time < self._cache_ttl:
                    return score, 0.8

        # Tokenize and normalize
        words = text.lower().split()
        words = [re.sub(r"[^\w]", "", w) for w in words]
        words = [w for w in words if w]

        if not words:
            return 0.0, 0.0

        bullish_count = 0
        bearish_count = 0
        intensity = 1.0
        negate_next = False

        for i, word in enumerate(words):
            # Check for negation
            if word in self.NEGATORS:
                negate_next = True
                continue

            # Check for intensifiers
            if word in self.INTENSIFIERS:
                intensity = 1.5
                continue

            # Score word
            if word in self.BULLISH_WORDS:
                if negate_next:
                    bearish_count += intensity
                else:
                    bullish_count += intensity
                negate_next = False
                intensity = 1.0
            elif word in self.BEARISH_WORDS:
                if negate_next:
                    bullish_count += intensity
                else:
                    bearish_count += intensity
                negate_next = False
                intensity = 1.0
            else:
                negate_next = False
                intensity = 1.0

        # Calculate sentiment score
        total = bullish_count + bearish_count
        if total == 0:
            score = 0.0
            confidence = 0.1
        else:
            score = (bullish_count - bearish_count) / total
            confidence = min(1.0, total / 10)  # More words = more confident

        # Cache result
        with self._lock:
            self._cache[cache_key] = (score, datetime.now())

        return score, confidence

    def analyze_batch(self, texts: List[str], asset: str = "") -> SentimentSignal:
        """
        Analyze sentiment of multiple texts and aggregate.

        Args:
            texts: List of texts to analyze
            asset: Asset being analyzed

        Returns:
            Aggregated SentimentSignal
        """
        if not texts:
            return SentimentSignal(
                source=SentimentSource.TWITTER,
                asset=asset,
                sentiment_score=0.0,
                confidence=0.0,
                volume=0,
                timestamp=datetime.now(),
            )

        scores = []
        confidences = []
        all_keywords = []

        for text in texts:
            score, confidence = self.analyze_text(text, asset)
            scores.append(score)
            confidences.append(confidence)

            # Extract keywords
            words = text.lower().split()
            keywords = [
                w for w in words if w in self.BULLISH_WORDS or w in self.BEARISH_WORDS
            ]
            all_keywords.extend(keywords)

        # Weighted average by confidence
        total_confidence = sum(confidences)
        if total_confidence > 0:
            avg_score = (
                sum(s * c for s, c in zip(scores, confidences)) / total_confidence
            )
            avg_confidence = total_confidence / len(texts)
        else:
            avg_score = 0.0
            avg_confidence = 0.0

        # Get most common keywords
        keyword_counts: Dict[str, int] = {}
        for kw in all_keywords:
            keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
        top_keywords = sorted(
            keyword_counts.keys(), key=lambda k: keyword_counts[k], reverse=True
        )[:10]

        return SentimentSignal(
            source=SentimentSource.TWITTER,
            asset=asset,
            sentiment_score=avg_score,
            confidence=avg_confidence,
            volume=len(texts),
            timestamp=datetime.now(),
            keywords=top_keywords,
        )


class SentimentProcessor(DataProcessor):
    """
    Process sentiment data from multiple sources.
    """

    def __init__(self):
        """Initialize the sentiment processor."""
        self.analyzer = SentimentAnalyzer()
        self._lock = threading.RLock()
        self._history: Dict[str, deque] = {}  # asset -> recent signals
        self._max_history = 100

    def process(self, data: Dict[str, Any]) -> SentimentSignal:
        """
        Process raw sentiment data.

        Args:
            data: Dictionary with 'texts', 'source', 'asset' keys

        Returns:
            SentimentSignal
        """
        if not self.validate(data):
            raise ValueError("Invalid sentiment data format")

        texts = data.get("texts", [])
        source = SentimentSource(data.get("source", "twitter"))
        asset = data.get("asset", "BTC")

        signal = self.analyzer.analyze_batch(texts, asset)
        signal.source = source

        # Store in history
        with self._lock:
            if asset not in self._history:
                self._history[asset] = deque(maxlen=self._max_history)
            self._history[asset].append(signal)

        return signal

    def validate(self, data: Any) -> bool:
        """Validate sentiment data."""
        if not isinstance(data, dict):
            return False
        if "texts" not in data:
            return False
        if not isinstance(data["texts"], list):
            return False
        return True

    def get_trend(self, asset: str, window: int = 10) -> float:
        """
        Get sentiment trend for an asset.

        Args:
            asset: Asset symbol
            window: Number of recent signals to consider

        Returns:
            Trend value (-1 to 1, positive = improving sentiment)
        """
        with self._lock:
            if asset not in self._history or len(self._history[asset]) < 2:
                return 0.0

            recent = list(self._history[asset])[-window:]
            if len(recent) < 2:
                return 0.0

            # Calculate trend as slope
            first_half = recent[: len(recent) // 2]
            second_half = recent[len(recent) // 2 :]

            first_avg = sum(s.sentiment_score for s in first_half) / len(first_half)
            second_avg = sum(s.sentiment_score for s in second_half) / len(second_half)

            return second_avg - first_avg


# =============================================================================
# On-Chain Analytics
# =============================================================================


class OnChainAnalyzer:
    """
    On-chain data analyzer for blockchain analytics.

    Tracks whale movements, DEX flows, and network metrics.
    """

    # Thresholds for whale detection (in USD equivalent)
    WHALE_THRESHOLD = {"BTC": 1000000, "ETH": 500000, "default": 100000}  # $1M  # $500K

    def __init__(self):
        """Initialize the on-chain analyzer."""
        self._lock = threading.RLock()
        self._events: Dict[str, deque] = {}  # blockchain -> events
        self._max_events = 1000

    def is_whale_transfer(self, asset: str, amount_usd: float) -> bool:
        """Check if a transfer qualifies as a whale transfer."""
        threshold = self.WHALE_THRESHOLD.get(asset, self.WHALE_THRESHOLD["default"])
        return amount_usd >= threshold

    def analyze_transfers(
        self, transfers: List[Dict[str, Any]], asset: str
    ) -> Dict[str, Any]:
        """
        Analyze transfer data for whale activity.

        Args:
            transfers: List of transfer records
            asset: Asset being analyzed

        Returns:
            Dictionary with whale metrics
        """
        whale_transfers = []
        total_volume = 0.0
        whale_volume = 0.0

        for transfer in transfers:
            amount_usd = transfer.get("amount_usd", 0)
            total_volume += amount_usd

            if self.is_whale_transfer(asset, amount_usd):
                whale_transfers.append(transfer)
                whale_volume += amount_usd

        return {
            "whale_count": len(whale_transfers),
            "whale_volume": whale_volume,
            "total_volume": total_volume,
            "whale_ratio": whale_volume / total_volume if total_volume > 0 else 0,
        }

    def analyze_exchange_flows(self, flows: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Analyze exchange inflows and outflows.

        Args:
            flows: List of flow records with 'direction' and 'amount' keys

        Returns:
            Dictionary with inflow, outflow, and net flow
        """
        inflow = 0.0
        outflow = 0.0

        for flow in flows:
            direction = flow.get("direction", "")
            amount = flow.get("amount", 0)

            if direction == "inflow":
                inflow += amount
            elif direction == "outflow":
                outflow += amount

        return {"inflow": inflow, "outflow": outflow, "net_flow": inflow - outflow}

    def record_event(self, blockchain: str, event: Dict[str, Any]):
        """Record an on-chain event."""
        with self._lock:
            if blockchain not in self._events:
                self._events[blockchain] = deque(maxlen=self._max_events)
            self._events[blockchain].append({**event, "timestamp": datetime.now()})

    def get_recent_events(
        self,
        blockchain: str,
        event_type: Optional[OnChainEventType] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get recent events, optionally filtered by type."""
        with self._lock:
            if blockchain not in self._events:
                return []

            events = list(self._events[blockchain])

            if event_type:
                events = [e for e in events if e.get("type") == event_type]

            return events[-limit:]


class OnChainProcessor(DataProcessor):
    """
    Process on-chain data into structured metrics.
    """

    def __init__(self):
        """Initialize the on-chain processor."""
        self.analyzer = OnChainAnalyzer()
        self._lock = threading.RLock()
        self._metrics_history: Dict[str, deque] = {}
        self._max_history = 100

    def process(self, data: Dict[str, Any]) -> OnChainMetrics:
        """
        Process raw on-chain data.

        Args:
            data: Dictionary with blockchain data

        Returns:
            OnChainMetrics
        """
        if not self.validate(data):
            raise ValueError("Invalid on-chain data format")

        blockchain = data.get("blockchain", "ethereum")
        asset = data.get("asset", "ETH")

        # Analyze transfers
        transfers = data.get("transfers", [])
        whale_stats = self.analyzer.analyze_transfers(transfers, asset)

        # Analyze exchange flows
        flows = data.get("flows", [])
        flow_stats = self.analyzer.analyze_exchange_flows(flows)

        metrics = OnChainMetrics(
            blockchain=blockchain,
            asset=asset,
            timestamp=datetime.now(),
            whale_transfers=whale_stats["whale_count"],
            whale_volume=whale_stats["whale_volume"],
            exchange_inflow=flow_stats["inflow"],
            exchange_outflow=flow_stats["outflow"],
            dex_volume=data.get("dex_volume", 0),
            active_addresses=data.get("active_addresses", 0),
            gas_price=data.get("gas_price", 0),
            funding_rate=data.get("funding_rate"),
            open_interest=data.get("open_interest"),
        )

        # Store in history
        with self._lock:
            key = f"{blockchain}:{asset}"
            if key not in self._metrics_history:
                self._metrics_history[key] = deque(maxlen=self._max_history)
            self._metrics_history[key].append(metrics)

        return metrics

    def validate(self, data: Any) -> bool:
        """Validate on-chain data."""
        if not isinstance(data, dict):
            return False
        return True

    def get_flow_trend(self, blockchain: str, asset: str, window: int = 10) -> float:
        """
        Get net flow trend.

        Returns:
            Trend value (positive = net outflow increasing, negative = net inflow increasing)
        """
        with self._lock:
            key = f"{blockchain}:{asset}"
            if key not in self._metrics_history or len(self._metrics_history[key]) < 2:
                return 0.0

            recent = list(self._metrics_history[key])[-window:]
            if len(recent) < 2:
                return 0.0

            first_half = recent[: len(recent) // 2]
            second_half = recent[len(recent) // 2 :]

            first_avg = sum(m.net_flow for m in first_half) / len(first_half)
            second_avg = sum(m.net_flow for m in second_half) / len(second_half)

            return second_avg - first_avg


# =============================================================================
# Order Flow Analysis
# =============================================================================


class OrderFlowAnalyzer:
    """
    Order flow analysis for market microstructure signals.

    Analyzes order book data for imbalance, toxicity, and momentum signals.
    """

    def __init__(self):
        """Initialize the order flow analyzer."""
        self._lock = threading.RLock()
        self._history: Dict[str, deque] = {}  # exchange:asset -> signals
        self._max_history = 1000

    def calculate_imbalance(
        self,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        levels: int = 10,
    ) -> float:
        """
        Calculate order book imbalance.

        Args:
            bids: List of (price, size) tuples
            asks: List of (price, size) tuples
            levels: Number of levels to consider

        Returns:
            Imbalance ratio (-1 to 1, positive = buy pressure)
        """
        # Sum volume at top N levels
        bid_volume = sum(size for _, size in bids[:levels])
        ask_volume = sum(size for _, size in asks[:levels])

        total = bid_volume + ask_volume
        if total == 0:
            return 0.0

        return (bid_volume - ask_volume) / total

    def calculate_toxicity(
        self, trades: List[Dict[str, Any]], window_seconds: int = 60
    ) -> float:
        """
        Calculate trade flow toxicity (VPIN-inspired).

        High toxicity indicates informed trading activity.

        Args:
            trades: List of recent trades
            window_seconds: Time window for analysis

        Returns:
            Toxicity score (0 to 1)
        """
        if not trades:
            return 0.0

        cutoff = datetime.now() - timedelta(seconds=window_seconds)
        recent_trades = [
            t for t in trades if t.get("timestamp", datetime.now()) > cutoff
        ]

        if len(recent_trades) < 2:
            return 0.0

        # Calculate buy/sell volume imbalance
        buy_volume = sum(
            t.get("size", 0) for t in recent_trades if t.get("side") == "buy"
        )
        sell_volume = sum(
            t.get("size", 0) for t in recent_trades if t.get("side") == "sell"
        )

        total_volume = buy_volume + sell_volume
        if total_volume == 0:
            return 0.0

        # Toxicity = absolute imbalance ratio
        imbalance = abs(buy_volume - sell_volume) / total_volume
        return imbalance

    def detect_absorption(
        self, book_snapshots: List[Dict[str, Any]]
    ) -> Tuple[bool, int]:
        """
        Detect absorption patterns (large orders being absorbed).

        Args:
            book_snapshots: Recent order book snapshots

        Returns:
            Tuple of (absorption_detected, direction)
        """
        if len(book_snapshots) < 2:
            return False, 0

        # Compare bid/ask depths over time
        first = book_snapshots[0]
        last = book_snapshots[-1]

        bid_change = last.get("bid_depth", 0) - first.get("bid_depth", 0)
        ask_change = last.get("ask_depth", 0) - first.get("ask_depth", 0)

        # Absorption: one side decreasing while price stable
        price_change = abs(last.get("mid_price", 0) - first.get("mid_price", 0))
        price_threshold = first.get("mid_price", 1) * 0.001  # 0.1% threshold

        if price_change < price_threshold:
            if bid_change < -1000 and ask_change > -100:
                return True, -1  # Buy absorption
            elif ask_change < -1000 and bid_change > -100:
                return True, 1  # Sell absorption

        return False, 0

    def detect_spoofing(
        self, book_changes: List[Dict[str, Any]], threshold: float = 0.5
    ) -> bool:
        """
        Detect potential spoofing activity.

        Spoofing: Large orders placed and quickly cancelled.

        Args:
            book_changes: Recent order book changes
            threshold: Cancellation ratio threshold

        Returns:
            True if spoofing pattern detected
        """
        if len(book_changes) < 10:
            return False

        # Track large order placements and cancellations
        large_placements = 0
        large_cancellations = 0

        for change in book_changes:
            if change.get("type") == "place" and change.get("size", 0) > 10000:
                large_placements += 1
            elif change.get("type") == "cancel" and change.get("size", 0) > 10000:
                large_cancellations += 1

        if large_placements > 0:
            cancel_ratio = large_cancellations / large_placements
            return cancel_ratio > threshold

        return False


class OrderFlowProcessor(DataProcessor):
    """
    Process order flow data into trading signals.
    """

    def __init__(self):
        """Initialize the order flow processor."""
        self.analyzer = OrderFlowAnalyzer()
        self._lock = threading.RLock()
        self._signals: Dict[str, deque] = {}
        self._max_signals = 100

    def process(self, data: Dict[str, Any]) -> OrderFlowSignal:
        """
        Process raw order flow data.

        Args:
            data: Dictionary with order book and trade data

        Returns:
            OrderFlowSignal
        """
        if not self.validate(data):
            raise ValueError("Invalid order flow data format")

        exchange = data.get("exchange", "unknown")
        asset = data.get("asset", "BTC")

        # Get order book data
        bids = data.get("bids", [])
        asks = data.get("asks", [])
        trades = data.get("trades", [])

        # Calculate metrics
        imbalance = self.analyzer.calculate_imbalance(bids, asks)
        toxicity = self.analyzer.calculate_toxicity(trades)

        # Determine signal type and direction
        if abs(imbalance) > 0.3:
            signal_type = OrderFlowType.IMBALANCE
            value = imbalance
            direction = 1 if imbalance > 0 else -1
        elif toxicity > 0.6:
            signal_type = OrderFlowType.TOXICITY
            value = toxicity
            # Direction based on recent trade flow
            buy_vol = sum(t.get("size", 0) for t in trades if t.get("side") == "buy")
            sell_vol = sum(t.get("size", 0) for t in trades if t.get("side") == "sell")
            direction = 1 if buy_vol > sell_vol else -1
        else:
            signal_type = OrderFlowType.MOMENTUM
            value = imbalance
            direction = 1 if imbalance > 0 else (-1 if imbalance < 0 else 0)

        # Calculate confidence
        confidence = min(1.0, (abs(imbalance) + toxicity) / 2)

        # Calculate depth
        bid_depth = sum(size for _, size in bids[:10])
        ask_depth = sum(size for _, size in asks[:10])

        signal = OrderFlowSignal(
            exchange=exchange,
            asset=asset,
            timestamp=datetime.now(),
            signal_type=signal_type,
            value=value,
            direction=direction,
            confidence=confidence,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
        )

        # Store signal
        with self._lock:
            key = f"{exchange}:{asset}"
            if key not in self._signals:
                self._signals[key] = deque(maxlen=self._max_signals)
            self._signals[key].append(signal)

        return signal

    def validate(self, data: Any) -> bool:
        """Validate order flow data."""
        if not isinstance(data, dict):
            return False
        return True


# =============================================================================
# News Processing with NLP
# =============================================================================


class NewsNLPProcessor:
    """
    News article processor with NLP capabilities.

    Extracts entities, sentiment, and relevance from news text.
    """

    # Simple entity patterns (in production, use proper NER)
    CRYPTO_ENTITIES = {
        "bitcoin",
        "btc",
        "ethereum",
        "eth",
        "solana",
        "sol",
        "cardano",
        "ada",
        "ripple",
        "xrp",
        "dogecoin",
        "doge",
        "polygon",
        "matic",
        "avalanche",
        "avax",
    }

    COMPANY_ENTITIES = {
        "coinbase",
        "binance",
        "kraken",
        "ftx",
        "celsius",
        "blockfi",
        "microstrategy",
        "tesla",
        "square",
        "paypal",
        "visa",
        "mastercard",
    }

    REGULATORY_KEYWORDS = {
        "sec",
        "cftc",
        "regulation",
        "ban",
        "legal",
        "lawsuit",
        "investigation",
        "compliance",
        "enforcement",
        "etf",
        "approval",
        "rejection",
    }

    def __init__(self):
        """Initialize the news processor."""
        self.sentiment_analyzer = SentimentAnalyzer()
        self._lock = threading.RLock()

    def extract_entities(self, text: str) -> List[str]:
        """Extract named entities from text."""
        text_lower = text.lower()
        words = set(re.findall(r"\b\w+\b", text_lower))

        entities = []

        # Find crypto entities
        crypto_found = words.intersection(self.CRYPTO_ENTITIES)
        entities.extend(crypto_found)

        # Find company entities
        company_found = words.intersection(self.COMPANY_ENTITIES)
        entities.extend(company_found)

        return list(set(entities))

    def extract_keywords(self, text: str, top_n: int = 10) -> List[str]:
        """Extract important keywords from text."""
        text_lower = text.lower()
        words = re.findall(r"\b\w+\b", text_lower)

        # Filter common words (simplified stop words)
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "can",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "again",
            "further",
            "then",
            "once",
            "and",
            "but",
            "or",
            "nor",
            "so",
            "yet",
            "both",
            "either",
            "neither",
            "not",
            "only",
            "own",
            "same",
            "than",
            "too",
            "very",
            "just",
            "also",
            "now",
            "here",
            "there",
            "when",
            "where",
            "why",
            "how",
            "all",
            "each",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "any",
            "this",
            "that",
            "these",
            "those",
            "what",
            "which",
            "who",
            "whom",
            "it",
            "its",
            "they",
            "them",
            "their",
            "he",
            "she",
            "his",
            "her",
            "him",
            "we",
            "us",
            "our",
            "i",
            "my",
            "me",
        }

        filtered_words = [w for w in words if w not in stop_words and len(w) > 2]

        # Count frequencies
        word_counts: Dict[str, int] = {}
        for word in filtered_words:
            word_counts[word] = word_counts.get(word, 0) + 1

        # Return top keywords
        sorted_words = sorted(
            word_counts.keys(), key=lambda w: word_counts[w], reverse=True
        )
        return sorted_words[:top_n]

    def calculate_relevance(self, text: str, target_asset: str = "") -> float:
        """
        Calculate relevance score for a target asset.

        Args:
            text: Article text
            target_asset: Target asset symbol

        Returns:
            Relevance score (0 to 1)
        """
        text_lower = text.lower()
        target_lower = target_asset.lower()

        # Base relevance from mentions
        mentions = text_lower.count(target_lower)
        mention_score = min(1.0, mentions / 5)

        # Check for related entities
        entities = self.extract_entities(text)
        entity_score = 0.5 if target_lower in entities else 0.0

        # Check for market-moving keywords
        regulatory_count = sum(1 for kw in self.REGULATORY_KEYWORDS if kw in text_lower)
        regulatory_score = min(0.3, regulatory_count * 0.1)

        return min(1.0, mention_score + entity_score + regulatory_score)

    def categorize_article(self, text: str) -> str:
        """Categorize article into types."""
        text_lower = text.lower()

        if any(kw in text_lower for kw in self.REGULATORY_KEYWORDS):
            return "regulatory"
        elif any(
            kw in text_lower for kw in ["price", "rally", "crash", "surge", "drop"]
        ):
            return "price_action"
        elif any(
            kw in text_lower for kw in ["partnership", "acquisition", "merger", "deal"]
        ):
            return "corporate"
        elif any(
            kw in text_lower for kw in ["hack", "exploit", "vulnerability", "security"]
        ):
            return "security"
        elif any(kw in text_lower for kw in ["launch", "release", "update", "upgrade"]):
            return "technology"
        else:
            return "general"

    def process_article(
        self, title: str, content: str, source: str, target_asset: str = ""
    ) -> NewsArticle:
        """
        Process a news article with full NLP analysis.

        Args:
            title: Article title
            content: Article content
            source: News source
            target_asset: Target asset for relevance scoring

        Returns:
            NewsArticle with extracted information
        """
        full_text = f"{title} {content}"

        # Extract entities and keywords
        entities = self.extract_entities(full_text)
        keywords = self.extract_keywords(full_text)

        # Analyze sentiment
        sentiment_score, _ = self.sentiment_analyzer.analyze_text(full_text)

        # Calculate relevance
        relevance_score = self.calculate_relevance(full_text, target_asset)

        # Categorize
        category = self.categorize_article(full_text)

        return NewsArticle(
            title=title,
            content=content,
            source=source,
            timestamp=datetime.now(),
            entities=entities,
            sentiment_score=sentiment_score,
            relevance_score=relevance_score,
            keywords=keywords,
            category=category,
        )


# =============================================================================
# Main Alternative Data Processor
# =============================================================================


class AlternativeDataProcessor:
    """
    Main orchestrator for alternative data processing.

    Aggregates signals from sentiment, on-chain, order flow, and news sources.
    """

    def __init__(self):
        """Initialize the alternative data processor."""
        self.sentiment_processor = SentimentProcessor()
        self.onchain_processor = OnChainProcessor()
        self.orderflow_processor = OrderFlowProcessor()
        self.news_processor = NewsNLPProcessor()

        self._lock = threading.RLock()
        self._intelligence_cache: Dict[str, MarketIntelligence] = {}
        self._cache_ttl = timedelta(minutes=5)

        logger.info("AlternativeDataProcessor initialized")

    def process_sentiment(
        self, source: str, texts: List[str], asset: str
    ) -> SentimentSignal:
        """
        Process sentiment data from a source.

        Args:
            source: Data source (twitter, reddit, etc.)
            texts: List of text data
            asset: Asset symbol

        Returns:
            SentimentSignal
        """
        data = {"source": source, "texts": texts, "asset": asset}
        return self.sentiment_processor.process(data)

    def process_onchain(
        self,
        blockchain: str,
        asset: str,
        transfers: List[Dict[str, Any]],
        flows: List[Dict[str, Any]],
        **kwargs,
    ) -> OnChainMetrics:
        """
        Process on-chain data.

        Args:
            blockchain: Blockchain name
            asset: Asset symbol
            transfers: Transfer data
            flows: Exchange flow data
            **kwargs: Additional metrics (dex_volume, gas_price, etc.)

        Returns:
            OnChainMetrics
        """
        data = {
            "blockchain": blockchain,
            "asset": asset,
            "transfers": transfers,
            "flows": flows,
            **kwargs,
        }
        return self.onchain_processor.process(data)

    def process_order_flow(
        self,
        exchange: str,
        asset: str,
        bids: List[Tuple[float, float]],
        asks: List[Tuple[float, float]],
        trades: List[Dict[str, Any]],
    ) -> OrderFlowSignal:
        """
        Process order flow data.

        Args:
            exchange: Exchange name
            asset: Asset symbol
            bids: Order book bids (price, size)
            asks: Order book asks (price, size)
            trades: Recent trades

        Returns:
            OrderFlowSignal
        """
        data = {
            "exchange": exchange,
            "asset": asset,
            "bids": bids,
            "asks": asks,
            "trades": trades,
        }
        return self.orderflow_processor.process(data)

    def process_news(
        self, title: str, content: str, source: str, target_asset: str = ""
    ) -> NewsArticle:
        """
        Process a news article.

        Args:
            title: Article title
            content: Article content
            source: News source
            target_asset: Target asset for relevance

        Returns:
            NewsArticle
        """
        return self.news_processor.process_article(title, content, source, target_asset)

    def get_market_intelligence(self, asset: str) -> MarketIntelligence:
        """
        Get aggregated market intelligence for an asset.

        Args:
            asset: Asset symbol

        Returns:
            MarketIntelligence with composite score
        """
        with self._lock:
            # Check cache
            if asset in self._intelligence_cache:
                cached = self._intelligence_cache[asset]
                if datetime.now() - cached.timestamp < self._cache_ttl:
                    return cached

            # Build intelligence from available data
            sentiment_signals = []
            if asset in self.sentiment_processor._history:
                recent = list(self.sentiment_processor._history[asset])[-10:]
                sentiment_signals = recent

            # Get on-chain metrics (try multiple blockchains)
            onchain_metrics = None
            for blockchain in ["ethereum", "bitcoin"]:
                key = f"{blockchain}:{asset}"
                if key in self.onchain_processor._metrics_history:
                    recent = list(self.onchain_processor._metrics_history[key])
                    if recent:
                        onchain_metrics = recent[-1]
                        break

            # Get order flow signals
            orderflow_signals = []
            for key, signals in self.orderflow_processor._signals.items():
                if asset in key:
                    orderflow_signals.extend(list(signals)[-5:])

            intelligence = MarketIntelligence(
                asset=asset,
                timestamp=datetime.now(),
                sentiment_signals=sentiment_signals,
                onchain_metrics=onchain_metrics,
                orderflow_signals=orderflow_signals,
                news_articles=[],  # Would be populated from news source
            )

            intelligence.calculate_composite()

            # Cache result
            self._intelligence_cache[asset] = intelligence

            return intelligence

    def get_trading_signal(self, asset: str) -> Dict[str, Any]:
        """
        Generate a trading signal from alternative data.

        Args:
            asset: Asset symbol

        Returns:
            Dictionary with signal, strength, and confidence
        """
        intelligence = self.get_market_intelligence(asset)

        # Determine signal direction
        if intelligence.composite_score > 0.2:
            signal = "BUY"
        elif intelligence.composite_score < -0.2:
            signal = "SELL"
        else:
            signal = "NEUTRAL"

        return {
            "asset": asset,
            "signal": signal,
            "strength": abs(intelligence.composite_score),
            "confidence": intelligence.confidence,
            "composite_score": intelligence.composite_score,
            "timestamp": datetime.now().isoformat(),
            "components": {
                "sentiment_count": len(intelligence.sentiment_signals),
                "has_onchain": intelligence.onchain_metrics is not None,
                "orderflow_count": len(intelligence.orderflow_signals),
            },
        }


# =============================================================================
# Factory Function
# =============================================================================


def create_alternative_data_processor() -> AlternativeDataProcessor:
    """Create and return an AlternativeDataProcessor instance."""
    return AlternativeDataProcessor()


# =============================================================================
# Module Initialization
# =============================================================================

if __name__ == "__main__":
    # Quick test
    processor = create_alternative_data_processor()

    # Test sentiment
    signal = processor.process_sentiment(
        source="twitter",
        texts=["BTC is mooning!", "Very bullish on ETH", "Crypto crash incoming"],
        asset="BTC",
    )
    print(f"Sentiment: {signal.sentiment_score:.2f} ({signal.level.name})")

    # Test order flow
    of_signal = processor.process_order_flow(
        exchange="binance",
        asset="BTC",
        bids=[(50000, 10), (49990, 15), (49980, 20)],
        asks=[(50010, 5), (50020, 8), (50030, 12)],
        trades=[{"side": "buy", "size": 1}, {"side": "sell", "size": 0.5}],
    )
    print(f"Order Flow: {of_signal.signal_type.name}, Direction: {of_signal.direction}")

    # Test intelligence
    intel = processor.get_trading_signal("BTC")
    print(f"Trading Signal: {intel}")
