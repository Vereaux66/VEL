"""
VEL Multi-Agent Market Simulator Module

Phase 4.2: Multi-Agent Market Simulation for Strategy Robustness Testing
- Agent-based market modeling with diverse trader behaviors
- Market impact and slippage simulation
- Adversarial trading scenarios
- Strategy stress testing under various market conditions

This module enables realistic backtesting and strategy validation.
"""

import logging
import threading
import random
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple
from collections import deque
import heapq

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Data Classes
# =============================================================================


class OrderSide(Enum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    """Order status."""

    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class AgentType(Enum):
    """Types of trading agents."""

    MARKET_MAKER = auto()
    MOMENTUM = auto()
    MEAN_REVERSION = auto()
    NOISE = auto()
    ARBITRAGE = auto()
    INFORMED = auto()
    HFT = auto()
    RETAIL = auto()
    INSTITUTIONAL = auto()
    ADVERSARIAL = auto()


class MarketCondition(Enum):
    """Market condition states."""

    NORMAL = auto()
    VOLATILE = auto()
    TRENDING_UP = auto()
    TRENDING_DOWN = auto()
    RANGING = auto()
    FLASH_CRASH = auto()
    SQUEEZE = auto()
    LOW_LIQUIDITY = auto()


@dataclass
class Order:
    """Represents a trading order."""

    id: str
    agent_id: str
    side: OrderSide
    order_type: OrderType
    price: float
    quantity: float
    timestamp: datetime
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    average_fill_price: float = 0.0
    stop_price: Optional[float] = None
    time_in_force: str = "GTC"  # Good Till Cancelled

    def remaining_quantity(self) -> float:
        """Get remaining unfilled quantity."""
        return self.quantity - self.filled_quantity


@dataclass
class Trade:
    """Represents an executed trade."""

    id: str
    buyer_order_id: str
    seller_order_id: str
    price: float
    quantity: float
    timestamp: datetime
    buyer_agent_id: str
    seller_agent_id: str
    aggressor_side: OrderSide  # Which side was the aggressor


@dataclass
class Position:
    """Agent's position in an asset."""

    quantity: float = 0.0
    average_entry_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0

    def update_pnl(self, current_price: float):
        """Update unrealized P&L."""
        if self.quantity != 0:
            self.unrealized_pnl = (
                current_price - self.average_entry_price
            ) * self.quantity


@dataclass
class MarketState:
    """Current state of the simulated market."""

    timestamp: datetime
    price: float
    bid_price: float
    ask_price: float
    spread: float
    volume: float
    volatility: float
    condition: MarketCondition
    order_book_imbalance: float = 0.0
    recent_trades: List[Trade] = field(default_factory=list)


@dataclass
class SimulationResult:
    """Results from a market simulation."""

    start_time: datetime
    end_time: datetime
    total_trades: int
    total_volume: float
    price_change: float
    volatility: float
    max_drawdown: float
    agent_results: Dict[str, Dict[str, Any]]
    price_history: List[Tuple[datetime, float]]
    events: List[Dict[str, Any]]


# =============================================================================
# Order Book Implementation
# =============================================================================


class OrderBook:
    """
    Limit order book implementation.

    Maintains bid and ask sides with price-time priority.
    """

    def __init__(self, asset: str):
        """Initialize order book for an asset."""
        self.asset = asset
        self._lock = threading.RLock()

        # Bids: max-heap (negative prices for max behavior)
        # Asks: min-heap
        self._bids: List[Tuple[float, datetime, Order]] = []  # (-price, time, order)
        self._asks: List[Tuple[float, datetime, Order]] = []  # (price, time, order)

        self._orders: Dict[str, Order] = {}  # order_id -> Order

    def add_order(self, order: Order) -> bool:
        """
        Add an order to the book.

        Args:
            order: Order to add

        Returns:
            True if added successfully
        """
        with self._lock:
            if order.id in self._orders:
                return False

            if order.order_type == OrderType.LIMIT:
                if order.side == OrderSide.BUY:
                    heapq.heappush(self._bids, (-order.price, order.timestamp, order))
                else:
                    heapq.heappush(self._asks, (order.price, order.timestamp, order))

                order.status = OrderStatus.OPEN
                self._orders[order.id] = order
                return True

            return False

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        with self._lock:
            if order_id not in self._orders:
                return False

            order = self._orders[order_id]
            order.status = OrderStatus.CANCELLED
            del self._orders[order_id]
            return True

    def get_best_bid(self) -> Optional[Tuple[float, float]]:
        """Get best bid price and quantity."""
        with self._lock:
            while self._bids:
                neg_price, _, order = self._bids[0]
                if order.id in self._orders and order.remaining_quantity() > 0:
                    return (-neg_price, order.remaining_quantity())
                heapq.heappop(self._bids)
            return None

    def get_best_ask(self) -> Optional[Tuple[float, float]]:
        """Get best ask price and quantity."""
        with self._lock:
            while self._asks:
                price, _, order = self._asks[0]
                if order.id in self._orders and order.remaining_quantity() > 0:
                    return (price, order.remaining_quantity())
                heapq.heappop(self._asks)
            return None

    def get_spread(self) -> Optional[float]:
        """Get bid-ask spread."""
        bid = self.get_best_bid()
        ask = self.get_best_ask()
        if bid and ask:
            return ask[0] - bid[0]
        return None

    def get_mid_price(self) -> Optional[float]:
        """Get mid price."""
        bid = self.get_best_bid()
        ask = self.get_best_ask()
        if bid and ask:
            return (bid[0] + ask[0]) / 2
        return None

    def get_depth(self, side: OrderSide, levels: int = 10) -> List[Tuple[float, float]]:
        """Get order book depth for a side."""
        with self._lock:
            result = []
            seen_prices: Dict[float, float] = {}

            if side == OrderSide.BUY:
                for neg_price, _, order in sorted(self._bids):
                    if order.id in self._orders:
                        price = -neg_price
                        qty = order.remaining_quantity()
                        seen_prices[price] = seen_prices.get(price, 0) + qty
            else:
                for price, _, order in sorted(self._asks):
                    if order.id in self._orders:
                        qty = order.remaining_quantity()
                        seen_prices[price] = seen_prices.get(price, 0) + qty

            sorted_prices = sorted(seen_prices.keys(), reverse=(side == OrderSide.BUY))
            for price in sorted_prices[:levels]:
                result.append((price, seen_prices[price]))

            return result

    def get_imbalance(self, levels: int = 5) -> float:
        """Calculate order book imbalance."""
        bids = self.get_depth(OrderSide.BUY, levels)
        asks = self.get_depth(OrderSide.SELL, levels)

        bid_volume = sum(qty for _, qty in bids)
        ask_volume = sum(qty for _, qty in asks)

        total = bid_volume + ask_volume
        if total == 0:
            return 0.0

        return (bid_volume - ask_volume) / total


# =============================================================================
# Matching Engine
# =============================================================================


class MatchingEngine:
    """
    Order matching engine with price-time priority.
    """

    def __init__(self, order_book: OrderBook):
        """Initialize matching engine."""
        self.order_book = order_book
        self._lock = threading.RLock()
        self._trade_counter = 0
        self._trades: List[Trade] = []

    def _generate_trade_id(self) -> str:
        """Generate unique trade ID."""
        self._trade_counter += 1
        return f"T{self._trade_counter:08d}"

    def process_order(self, order: Order) -> List[Trade]:
        """
        Process an incoming order.

        Args:
            order: Order to process

        Returns:
            List of trades generated
        """
        with self._lock:
            trades = []

            if order.order_type == OrderType.MARKET:
                trades = self._match_market_order(order)
            elif order.order_type == OrderType.LIMIT:
                trades = self._match_limit_order(order)

            return trades

    def _match_market_order(self, order: Order) -> List[Trade]:
        """Match a market order."""
        trades = []
        remaining = order.quantity

        while remaining > 0:
            if order.side == OrderSide.BUY:
                best = self.order_book.get_best_ask()
                if not best:
                    break
                price, available = best
            else:
                best = self.order_book.get_best_bid()
                if not best:
                    break
                price, available = best

            # Find and fill against resting order
            fill_qty = min(remaining, available)
            trade = self._execute_fill(order, price, fill_qty)
            if trade:
                trades.append(trade)
                remaining -= fill_qty

        if order.filled_quantity > 0:
            order.status = (
                OrderStatus.FILLED if remaining == 0 else OrderStatus.PARTIALLY_FILLED
            )
            order.average_fill_price = (
                sum(t.price * t.quantity for t in trades) / order.filled_quantity
            )
        else:
            order.status = OrderStatus.REJECTED

        return trades

    def _match_limit_order(self, order: Order) -> List[Trade]:
        """Match a limit order against the book."""
        trades = []
        remaining = order.quantity

        while remaining > 0:
            if order.side == OrderSide.BUY:
                best = self.order_book.get_best_ask()
                if not best or best[0] > order.price:
                    break  # No match possible
                price, available = best
            else:
                best = self.order_book.get_best_bid()
                if not best or best[0] < order.price:
                    break  # No match possible
                price, available = best

            fill_qty = min(remaining, available)
            trade = self._execute_fill(order, price, fill_qty)
            if trade:
                trades.append(trade)
                remaining -= fill_qty

        if order.filled_quantity == order.quantity:
            order.status = OrderStatus.FILLED
        elif order.filled_quantity > 0:
            order.status = OrderStatus.PARTIALLY_FILLED
            # Add remaining to book
            self.order_book.add_order(order)
        else:
            # No fills, add to book
            self.order_book.add_order(order)

        if order.filled_quantity > 0:
            order.average_fill_price = (
                sum(t.price * t.quantity for t in trades) / order.filled_quantity
            )

        return trades

    def _execute_fill(
        self, aggressor: Order, price: float, quantity: float
    ) -> Optional[Trade]:
        """Execute a fill between aggressor and resting order."""
        # Find the resting order
        with self.order_book._lock:
            if aggressor.side == OrderSide.BUY:
                heap = self.order_book._asks
            else:
                heap = self.order_book._bids

            if not heap:
                return None

            # Get the best resting order
            if aggressor.side == OrderSide.BUY:
                _, _, resting = heap[0]
            else:
                _, _, resting = heap[0]

            if resting.id not in self.order_book._orders:
                heapq.heappop(heap)
                return None

            # Execute the fill
            fill_qty = min(quantity, resting.remaining_quantity())

            aggressor.filled_quantity += fill_qty
            resting.filled_quantity += fill_qty

            if resting.remaining_quantity() <= 0:
                resting.status = OrderStatus.FILLED
                del self.order_book._orders[resting.id]
                heapq.heappop(heap)

            # Determine buyer/seller
            if aggressor.side == OrderSide.BUY:
                buyer_id, seller_id = aggressor.agent_id, resting.agent_id
                buyer_order, seller_order = aggressor.id, resting.id
            else:
                buyer_id, seller_id = resting.agent_id, aggressor.agent_id
                buyer_order, seller_order = resting.id, aggressor.id

            trade = Trade(
                id=self._generate_trade_id(),
                buyer_order_id=buyer_order,
                seller_order_id=seller_order,
                price=price,
                quantity=fill_qty,
                timestamp=datetime.now(),
                buyer_agent_id=buyer_id,
                seller_agent_id=seller_id,
                aggressor_side=aggressor.side,
            )

            self._trades.append(trade)
            return trade


# =============================================================================
# Trading Agent Base Class
# =============================================================================


class TradingAgent(ABC):
    """
    Abstract base class for trading agents.
    """

    def __init__(
        self, agent_id: str, agent_type: AgentType, initial_capital: float = 100000.0
    ):
        """Initialize trading agent."""
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.capital = initial_capital
        self.initial_capital = initial_capital
        self.position = Position()
        self.orders: Dict[str, Order] = {}
        self.trades: List[Trade] = []
        self._order_counter = 0
        self._lock = threading.RLock()

    def _generate_order_id(self) -> str:
        """Generate unique order ID."""
        self._order_counter += 1
        return f"{self.agent_id}_O{self._order_counter:06d}"

    @abstractmethod
    def decide(self, market_state: MarketState, order_book: OrderBook) -> List[Order]:
        """
        Make trading decisions based on market state.

        Args:
            market_state: Current market state
            order_book: Current order book

        Returns:
            List of orders to submit
        """
        raise NotImplementedError

    def on_trade(self, trade: Trade, market_state: MarketState):
        """Handle a trade execution."""
        with self._lock:
            self.trades.append(trade)

            # Update position
            if trade.buyer_agent_id == self.agent_id:
                # Bought
                old_qty = self.position.quantity
                new_qty = old_qty + trade.quantity

                if old_qty >= 0:
                    # Adding to long or opening long
                    total_cost = (
                        self.position.average_entry_price * old_qty
                        + trade.price * trade.quantity
                    )
                    self.position.average_entry_price = (
                        total_cost / new_qty if new_qty > 0 else 0
                    )
                else:
                    # Covering short
                    if new_qty >= 0:
                        # Closed short completely, maybe opened long
                        pnl = (self.position.average_entry_price - trade.price) * min(
                            trade.quantity, -old_qty
                        )
                        self.position.realized_pnl += pnl
                        self.capital += pnl
                        if new_qty > 0:
                            self.position.average_entry_price = trade.price
                    else:
                        # Still short
                        pnl = (
                            self.position.average_entry_price - trade.price
                        ) * trade.quantity
                        self.position.realized_pnl += pnl
                        self.capital += pnl

                self.position.quantity = new_qty
                self.capital -= trade.price * trade.quantity

            elif trade.seller_agent_id == self.agent_id:
                # Sold
                old_qty = self.position.quantity
                new_qty = old_qty - trade.quantity

                if old_qty <= 0:
                    # Adding to short or opening short
                    total_cost = (
                        self.position.average_entry_price * abs(old_qty)
                        + trade.price * trade.quantity
                    )
                    self.position.average_entry_price = (
                        total_cost / abs(new_qty) if new_qty != 0 else 0
                    )
                else:
                    # Closing long
                    if new_qty <= 0:
                        # Closed long completely, maybe opened short
                        pnl = (trade.price - self.position.average_entry_price) * min(
                            trade.quantity, old_qty
                        )
                        self.position.realized_pnl += pnl
                        self.capital += pnl
                        if new_qty < 0:
                            self.position.average_entry_price = trade.price
                    else:
                        # Still long
                        pnl = (
                            trade.price - self.position.average_entry_price
                        ) * trade.quantity
                        self.position.realized_pnl += pnl
                        self.capital += pnl

                self.position.quantity = new_qty
                self.capital += trade.price * trade.quantity

            # Update unrealized P&L
            self.position.update_pnl(market_state.price)

    def get_pnl(self) -> float:
        """Get total P&L (realized + unrealized)."""
        return self.position.realized_pnl + self.position.unrealized_pnl

    def get_return(self) -> float:
        """Get return as percentage."""
        return (
            self.capital + self.get_pnl() - self.initial_capital
        ) / self.initial_capital


# =============================================================================
# Concrete Trading Agents
# =============================================================================


class MarketMakerAgent(TradingAgent):
    """
    Market maker agent that provides liquidity.

    Maintains bid-ask quotes around mid price.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 100000.0,
        spread_bps: float = 10.0,
        order_size: float = 10.0,
        max_position: float = 100.0,
    ):
        """Initialize market maker."""
        super().__init__(agent_id, AgentType.MARKET_MAKER, initial_capital)
        self.spread_bps = spread_bps
        self.order_size = order_size
        self.max_position = max_position

    def decide(self, market_state: MarketState, order_book: OrderBook) -> List[Order]:
        """Generate two-sided quotes."""
        orders = []

        mid = market_state.price
        spread = mid * (self.spread_bps / 10000)

        # Adjust spread for volatility
        spread *= 1 + market_state.volatility

        bid_price = mid - spread / 2
        ask_price = mid + spread / 2

        # Adjust for position (skew quotes to reduce inventory)
        pos_ratio = (
            self.position.quantity / self.max_position if self.max_position > 0 else 0
        )
        bid_price *= 1 - pos_ratio * 0.001
        ask_price *= 1 + pos_ratio * 0.001

        # Submit bid if not too long
        if self.position.quantity < self.max_position:
            orders.append(
                Order(
                    id=self._generate_order_id(),
                    agent_id=self.agent_id,
                    side=OrderSide.BUY,
                    order_type=OrderType.LIMIT,
                    price=bid_price,
                    quantity=self.order_size,
                    timestamp=datetime.now(),
                )
            )

        # Submit ask if not too short
        if self.position.quantity > -self.max_position:
            orders.append(
                Order(
                    id=self._generate_order_id(),
                    agent_id=self.agent_id,
                    side=OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    price=ask_price,
                    quantity=self.order_size,
                    timestamp=datetime.now(),
                )
            )

        return orders


class MomentumAgent(TradingAgent):
    """
    Momentum trading agent.

    Buys on positive momentum, sells on negative momentum.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 100000.0,
        lookback: int = 10,
        threshold: float = 0.01,
        order_size: float = 5.0,
    ):
        """Initialize momentum agent."""
        super().__init__(agent_id, AgentType.MOMENTUM, initial_capital)
        self.lookback = lookback
        self.threshold = threshold
        self.order_size = order_size
        self._price_history: deque = deque(maxlen=lookback)

    def decide(self, market_state: MarketState, order_book: OrderBook) -> List[Order]:
        """Trade based on momentum signals."""
        orders = []

        self._price_history.append(market_state.price)

        if len(self._price_history) < self.lookback:
            return orders

        # Calculate momentum
        old_price = self._price_history[0]
        current_price = self._price_history[-1]
        momentum = (current_price - old_price) / old_price

        # Generate signal
        if momentum > self.threshold and self.position.quantity <= 0:
            # Bullish momentum - buy
            orders.append(
                Order(
                    id=self._generate_order_id(),
                    agent_id=self.agent_id,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    price=market_state.price,
                    quantity=self.order_size,
                    timestamp=datetime.now(),
                )
            )
        elif momentum < -self.threshold and self.position.quantity >= 0:
            # Bearish momentum - sell
            orders.append(
                Order(
                    id=self._generate_order_id(),
                    agent_id=self.agent_id,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    price=market_state.price,
                    quantity=self.order_size,
                    timestamp=datetime.now(),
                )
            )

        return orders


class MeanReversionAgent(TradingAgent):
    """
    Mean reversion trading agent.

    Buys when price is below moving average, sells when above.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 100000.0,
        lookback: int = 20,
        deviation_threshold: float = 2.0,
        order_size: float = 5.0,
    ):
        """Initialize mean reversion agent."""
        super().__init__(agent_id, AgentType.MEAN_REVERSION, initial_capital)
        self.lookback = lookback
        self.deviation_threshold = deviation_threshold
        self.order_size = order_size
        self._price_history: deque = deque(maxlen=lookback)

    def decide(self, market_state: MarketState, order_book: OrderBook) -> List[Order]:
        """Trade based on mean reversion signals."""
        orders = []

        self._price_history.append(market_state.price)

        if len(self._price_history) < self.lookback:
            return orders

        # Calculate statistics
        prices = list(self._price_history)
        mean = sum(prices) / len(prices)
        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        std = math.sqrt(variance) if variance > 0 else 1

        # Calculate z-score
        z_score = (market_state.price - mean) / std if std > 0 else 0

        # Generate signals
        if z_score < -self.deviation_threshold and self.position.quantity <= 0:
            # Price below mean - buy
            orders.append(
                Order(
                    id=self._generate_order_id(),
                    agent_id=self.agent_id,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    price=market_state.price,
                    quantity=self.order_size,
                    timestamp=datetime.now(),
                )
            )
        elif z_score > self.deviation_threshold and self.position.quantity >= 0:
            # Price above mean - sell
            orders.append(
                Order(
                    id=self._generate_order_id(),
                    agent_id=self.agent_id,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    price=market_state.price,
                    quantity=self.order_size,
                    timestamp=datetime.now(),
                )
            )

        return orders


class NoiseAgent(TradingAgent):
    """
    Noise trading agent.

    Makes random trades to simulate uninformed market participants.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 100000.0,
        trade_probability: float = 0.1,
        order_size: float = 1.0,
    ):
        """Initialize noise agent."""
        super().__init__(agent_id, AgentType.NOISE, initial_capital)
        self.trade_probability = trade_probability
        self.order_size = order_size

    def decide(self, market_state: MarketState, order_book: OrderBook) -> List[Order]:
        """Make random trading decisions."""
        orders = []

        if random.random() < self.trade_probability:
            side = random.choice([OrderSide.BUY, OrderSide.SELL])
            order_type = random.choice([OrderType.MARKET, OrderType.LIMIT])

            price = market_state.price
            if order_type == OrderType.LIMIT:
                # Random price around mid
                offset = random.uniform(-0.01, 0.01) * price
                price += offset

            orders.append(
                Order(
                    id=self._generate_order_id(),
                    agent_id=self.agent_id,
                    side=side,
                    order_type=order_type,
                    price=price,
                    quantity=self.order_size * random.uniform(0.5, 1.5),
                    timestamp=datetime.now(),
                )
            )

        return orders


class AdversarialAgent(TradingAgent):
    """
    Adversarial trading agent.

    Attempts to exploit other agents' predictable behavior.
    Simulates spoofing, front-running, and manipulation.
    """

    def __init__(
        self,
        agent_id: str,
        initial_capital: float = 100000.0,
        aggression: float = 0.5,
        order_size: float = 20.0,
    ):
        """Initialize adversarial agent."""
        super().__init__(agent_id, AgentType.ADVERSARIAL, initial_capital)
        self.aggression = aggression
        self.order_size = order_size
        self._recent_imbalances: deque = deque(maxlen=10)

    def decide(self, market_state: MarketState, order_book: OrderBook) -> List[Order]:
        """Make adversarial trading decisions."""
        orders = []

        imbalance = order_book.get_imbalance()
        self._recent_imbalances.append(imbalance)

        # Strategy 1: Trade against temporary imbalance (front-running)
        if abs(imbalance) > 0.3 and random.random() < self.aggression:
            # Large imbalance likely to be corrected
            if imbalance > 0:
                # Many bids - price likely to rise, then fall
                # Sell into the buying pressure
                orders.append(
                    Order(
                        id=self._generate_order_id(),
                        agent_id=self.agent_id,
                        side=OrderSide.SELL,
                        order_type=OrderType.LIMIT,
                        price=market_state.ask_price,
                        quantity=self.order_size,
                        timestamp=datetime.now(),
                    )
                )
            else:
                # Many asks - price likely to fall, then rise
                # Buy into the selling pressure
                orders.append(
                    Order(
                        id=self._generate_order_id(),
                        agent_id=self.agent_id,
                        side=OrderSide.BUY,
                        order_type=OrderType.LIMIT,
                        price=market_state.bid_price,
                        quantity=self.order_size,
                        timestamp=datetime.now(),
                    )
                )

        # Strategy 2: Momentum ignition attempt
        if (
            len(self._recent_imbalances) >= 5
            and random.random() < self.aggression * 0.2
        ):
            avg_imbalance = sum(self._recent_imbalances) / len(self._recent_imbalances)
            if abs(avg_imbalance) < 0.1:  # Quiet market
                # Try to trigger momentum
                side = random.choice([OrderSide.BUY, OrderSide.SELL])
                orders.append(
                    Order(
                        id=self._generate_order_id(),
                        agent_id=self.agent_id,
                        side=side,
                        order_type=OrderType.MARKET,
                        price=market_state.price,
                        quantity=self.order_size * 2,
                        timestamp=datetime.now(),
                    )
                )

        return orders


# =============================================================================
# Market Simulator
# =============================================================================


class MarketConditionGenerator:
    """
    Generates market conditions for simulation.
    """

    def __init__(self, base_price: float = 50000.0, base_volatility: float = 0.02):
        """Initialize condition generator."""
        self.base_price = base_price
        self.price = base_price
        self.base_volatility = base_volatility
        self.volatility = base_volatility
        self.condition = MarketCondition.NORMAL
        self._trend = 0.0

    def step(self) -> MarketState:
        """Generate next market state."""
        # Random walk with trend
        random_return = random.gauss(self._trend, self.volatility)
        self.price *= 1 + random_return

        # Calculate spread based on volatility
        spread = self.price * self.volatility * 0.5

        # Randomly change conditions
        if random.random() < 0.02:
            self._change_condition()

        return MarketState(
            timestamp=datetime.now(),
            price=self.price,
            bid_price=self.price - spread / 2,
            ask_price=self.price + spread / 2,
            spread=spread,
            volume=random.uniform(100, 1000),
            volatility=self.volatility,
            condition=self.condition,
        )

    def _change_condition(self):
        """Randomly change market condition."""
        conditions = [
            (MarketCondition.NORMAL, 0.4),
            (MarketCondition.VOLATILE, 0.15),
            (MarketCondition.TRENDING_UP, 0.15),
            (MarketCondition.TRENDING_DOWN, 0.15),
            (MarketCondition.RANGING, 0.1),
            (MarketCondition.LOW_LIQUIDITY, 0.05),
        ]

        r = random.random()
        cumulative = 0
        for condition, prob in conditions:
            cumulative += prob
            if r < cumulative:
                self.condition = condition
                break

        # Adjust parameters based on condition
        if self.condition == MarketCondition.VOLATILE:
            self.volatility = self.base_volatility * 3
            self._trend = 0
        elif self.condition == MarketCondition.TRENDING_UP:
            self.volatility = self.base_volatility
            self._trend = 0.001
        elif self.condition == MarketCondition.TRENDING_DOWN:
            self.volatility = self.base_volatility
            self._trend = -0.001
        elif self.condition == MarketCondition.RANGING:
            self.volatility = self.base_volatility * 0.5
            self._trend = 0
        else:
            self.volatility = self.base_volatility
            self._trend = 0

    def inject_event(self, event_type: str):
        """Inject a market event."""
        if event_type == "flash_crash":
            self.price *= 0.9
            self.volatility = self.base_volatility * 5
            self.condition = MarketCondition.FLASH_CRASH
        elif event_type == "squeeze":
            self.price *= 1.15
            self.volatility = self.base_volatility * 4
            self.condition = MarketCondition.SQUEEZE
        elif event_type == "volatility_spike":
            self.volatility = self.base_volatility * 3


class MultiAgentMarketSimulator:
    """
    Multi-agent market simulation for strategy stress testing.

    Simulates a market with multiple agent types interacting.
    """

    def __init__(self, asset: str = "BTC", base_price: float = 50000.0):
        """Initialize the simulator."""
        self.asset = asset
        self.order_book = OrderBook(asset)
        self.matching_engine = MatchingEngine(self.order_book)
        self.condition_generator = MarketConditionGenerator(base_price)

        self.agents: Dict[str, TradingAgent] = {}
        self._lock = threading.RLock()
        self._price_history: List[Tuple[datetime, float]] = []
        self._events: List[Dict[str, Any]] = []

        logger.info(f"MultiAgentMarketSimulator initialized for {asset}")

    def add_agent(self, agent: TradingAgent):
        """Add a trading agent to the simulation."""
        with self._lock:
            self.agents[agent.agent_id] = agent
            logger.info(f"Added agent {agent.agent_id} ({agent.agent_type.name})")

    def remove_agent(self, agent_id: str):
        """Remove an agent from the simulation."""
        with self._lock:
            if agent_id in self.agents:
                del self.agents[agent_id]

    def create_default_agents(self):
        """Create a default set of diverse agents."""
        # Market makers
        for i in range(2):
            self.add_agent(MarketMakerAgent(f"MM_{i}", spread_bps=5 + i * 5))

        # Momentum traders
        for i in range(3):
            self.add_agent(MomentumAgent(f"MOM_{i}", lookback=10 + i * 5))

        # Mean reversion traders
        for i in range(2):
            self.add_agent(MeanReversionAgent(f"MR_{i}"))

        # Noise traders
        for i in range(5):
            self.add_agent(NoiseAgent(f"NOISE_{i}"))

        # Adversarial trader
        self.add_agent(AdversarialAgent("ADV_0", aggression=0.3))

    def step(self) -> Tuple[MarketState, List[Trade]]:
        """
        Execute one simulation step.

        Returns:
            Tuple of (market_state, trades)
        """
        with self._lock:
            # Generate new market state
            market_state = self.condition_generator.step()

            # Update order book state
            market_state.order_book_imbalance = self.order_book.get_imbalance()

            all_trades = []

            # Each agent makes decisions
            agent_list = list(self.agents.values())
            random.shuffle(agent_list)  # Random order

            for agent in agent_list:
                try:
                    orders = agent.decide(market_state, self.order_book)

                    for order in orders:
                        trades = self.matching_engine.process_order(order)
                        all_trades.extend(trades)

                        # Notify affected agents
                        for trade in trades:
                            if trade.buyer_agent_id in self.agents:
                                self.agents[trade.buyer_agent_id].on_trade(
                                    trade, market_state
                                )
                            if trade.seller_agent_id in self.agents:
                                self.agents[trade.seller_agent_id].on_trade(
                                    trade, market_state
                                )

                except Exception as e:
                    logger.error(f"Error in agent {agent.agent_id}: {e}")

            # Update price history
            self._price_history.append((market_state.timestamp, market_state.price))

            # Update recent trades
            market_state.recent_trades = all_trades[-10:]

            return market_state, all_trades

    def simulate(self, steps: int = 1000) -> SimulationResult:
        """
        Run a full simulation.

        Args:
            steps: Number of simulation steps

        Returns:
            SimulationResult with all metrics
        """
        start_time = datetime.now()
        start_price = self.condition_generator.price

        total_trades = 0
        total_volume = 0.0
        min_price = float("inf")
        max_price = 0.0
        peak_equity = sum(a.capital for a in self.agents.values())
        max_drawdown = 0.0

        for _ in range(steps):
            market_state, trades = self.step()

            total_trades += len(trades)
            total_volume += sum(t.quantity for t in trades)

            min_price = min(min_price, market_state.price)
            max_price = max(max_price, market_state.price)

            # Track drawdown
            current_equity = sum(a.capital for a in self.agents.values())
            peak_equity = max(peak_equity, current_equity)
            drawdown = (
                (peak_equity - current_equity) / peak_equity if peak_equity > 0 else 0
            )
            max_drawdown = max(max_drawdown, drawdown)

        end_time = datetime.now()
        end_price = self.condition_generator.price

        # Collect agent results
        agent_results = {}
        for agent_id, agent in self.agents.items():
            agent.position.update_pnl(end_price)
            agent_results[agent_id] = {
                "type": agent.agent_type.name,
                "final_capital": agent.capital,
                "position": agent.position.quantity,
                "realized_pnl": agent.position.realized_pnl,
                "unrealized_pnl": agent.position.unrealized_pnl,
                "total_pnl": agent.get_pnl(),
                "return_pct": agent.get_return() * 100,
                "trade_count": len(agent.trades),
            }

        # Calculate volatility
        if len(self._price_history) > 1:
            returns = []
            for i in range(1, len(self._price_history)):
                ret = (
                    self._price_history[i][1] - self._price_history[i - 1][1]
                ) / self._price_history[i - 1][1]
                returns.append(ret)
            volatility = (
                math.sqrt(sum(r**2 for r in returns) / len(returns)) if returns else 0
            )
        else:
            volatility = 0

        return SimulationResult(
            start_time=start_time,
            end_time=end_time,
            total_trades=total_trades,
            total_volume=total_volume,
            price_change=(end_price - start_price) / start_price,
            volatility=volatility,
            max_drawdown=max_drawdown,
            agent_results=agent_results,
            price_history=self._price_history.copy(),
            events=self._events.copy(),
        )

    def inject_event(self, event_type: str):
        """Inject a market event for stress testing."""
        self.condition_generator.inject_event(event_type)
        self._events.append({"timestamp": datetime.now(), "type": event_type})
        logger.info(f"Injected event: {event_type}")

    def stress_test(
        self, strategy_agent: TradingAgent, scenarios: List[str] = None
    ) -> Dict[str, SimulationResult]:
        """
        Run stress tests with various scenarios.

        Args:
            strategy_agent: The strategy to test
            scenarios: List of scenario names to run

        Returns:
            Dictionary of scenario name to simulation results
        """
        if scenarios is None:
            scenarios = ["normal", "flash_crash", "squeeze", "volatility_spike"]

        results = {}

        for scenario in scenarios:
            # Reset simulator
            self.order_book = OrderBook(self.asset)
            self.matching_engine = MatchingEngine(self.order_book)
            self.condition_generator = MarketConditionGenerator()
            self._price_history = []
            self._events = []

            # Reset agent
            strategy_agent.capital = strategy_agent.initial_capital
            strategy_agent.position = Position()
            strategy_agent.trades = []

            # Add agents
            self.agents = {strategy_agent.agent_id: strategy_agent}
            self.create_default_agents()

            # Run simulation with event injection
            for step in range(1000):
                if scenario != "normal" and step == 500:
                    self.inject_event(scenario)
                self.step()

            # Collect results
            market_state = self.condition_generator.step()
            strategy_agent.position.update_pnl(market_state.price)

            results[scenario] = self.simulate(0)  # Get final state
            results[scenario].agent_results[strategy_agent.agent_id] = {
                "type": strategy_agent.agent_type.name,
                "final_capital": strategy_agent.capital,
                "position": strategy_agent.position.quantity,
                "realized_pnl": strategy_agent.position.realized_pnl,
                "unrealized_pnl": strategy_agent.position.unrealized_pnl,
                "total_pnl": strategy_agent.get_pnl(),
                "return_pct": strategy_agent.get_return() * 100,
                "trade_count": len(strategy_agent.trades),
            }

        return results


# =============================================================================
# Factory Functions
# =============================================================================


def create_market_simulator(
    asset: str = "BTC", base_price: float = 50000.0
) -> MultiAgentMarketSimulator:
    """Create and configure a market simulator."""
    simulator = MultiAgentMarketSimulator(asset, base_price)
    simulator.create_default_agents()
    return simulator


def create_agent(agent_type: AgentType, agent_id: str, **kwargs) -> TradingAgent:
    """Factory function to create trading agents."""
    agent_classes = {
        AgentType.MARKET_MAKER: MarketMakerAgent,
        AgentType.MOMENTUM: MomentumAgent,
        AgentType.MEAN_REVERSION: MeanReversionAgent,
        AgentType.NOISE: NoiseAgent,
        AgentType.ADVERSARIAL: AdversarialAgent,
    }

    if agent_type not in agent_classes:
        raise ValueError(f"Unknown agent type: {agent_type}")

    return agent_classes[agent_type](agent_id, **kwargs)


# =============================================================================
# Module Initialization
# =============================================================================

if __name__ == "__main__":
    # Quick simulation test
    simulator = create_market_simulator()

    print("Running simulation with default agents...")
    result = simulator.simulate(steps=100)

    print("\nSimulation Results:")
    print(f"  Total trades: {result.total_trades}")
    print(f"  Total volume: {result.total_volume:.2f}")
    print(f"  Price change: {result.price_change*100:.2f}%")
    print(f"  Volatility: {result.volatility*100:.4f}%")
    print(f"  Max drawdown: {result.max_drawdown*100:.2f}%")

    print("\nAgent Results:")
    for agent_id, stats in result.agent_results.items():
        print(
            f"  {agent_id} ({stats['type']}): Return={stats['return_pct']:.2f}%, Trades={stats['trade_count']}"
        )
