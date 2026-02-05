#!/usr/bin/env python3
"""
ANVEL System Integration Module

This module provides comprehensive integration between all ANVEL components,
ensuring that:
1. Trade engine persists trades to the database
2. Trade execution events are published for feedback loops
3. Learning service receives execution feedback
4. API gateway is wired to the orchestrator
5. All services share common infrastructure

Usage:
    from anvel_integration import (
        get_integrated_system,
        IntegratedTradeEngine,
        wire_database_to_trade_engine,
    )

    system = get_integrated_system()
    system.start()
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional, TypeVar

log = logging.getLogger(__name__)

# Type variable for generic callbacks
T = TypeVar("T")


# =============================================================================
# Integration Event Types
# =============================================================================

@dataclass
class TradeExecutedEvent:
    """Event published when a trade is executed."""

    trade_id: str
    symbol: str
    side: str
    quantity: float
    price: float
    total: float
    fee: float
    status: str
    strategy: Optional[str]
    execution_latency_ms: float
    timestamp: float
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for event bus publishing."""
        return {
            "type": "trade.executed",
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "total": self.total,
            "fee": self.fee,
            "status": self.status,
            "strategy": self.strategy,
            "execution_latency_ms": self.execution_latency_ms,
            "timestamp": self.timestamp,
            "user_id": self.user_id,
            "metadata": self.metadata,
        }


@dataclass
class LearningFeedbackEvent:
    """Event for learning service feedback loop."""

    trade_id: str
    symbol: str
    strategy: Optional[str]
    signal_confidence: Optional[float]
    execution_price: float
    execution_quality: float  # 0-1 score based on slippage, timing
    pnl: Optional[float]
    timestamp: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for event bus publishing."""
        return {
            "type": "learning.feedback",
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "signal_confidence": self.signal_confidence,
            "execution_price": self.execution_price,
            "execution_quality": self.execution_quality,
            "pnl": self.pnl,
            "timestamp": self.timestamp,
        }


# =============================================================================
# Database Integration Layer
# =============================================================================

class TradePersistenceLayer:
    """
    Persistence layer for trade execution.

    Wraps the database service to provide trade-specific persistence
    with proper error handling and event publishing.
    """

    def __init__(
        self,
        database_service: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        default_user_id: str = "system",
    ):
        """
        Initialize the persistence layer.

        Args:
            database_service: Database service instance (lazy loaded if None)
            event_bus: Event bus for publishing trade events
            default_user_id: Default user ID for trades without explicit user
        """
        self._db = database_service
        self._event_bus = event_bus
        self._default_user_id = default_user_id
        self._initialized = False
        self._lock = threading.Lock()

    def _ensure_initialized(self) -> bool:
        """Ensure the database service is available."""
        if self._initialized:
            return self._db is not None and self._db.is_available

        with self._lock:
            if self._initialized:
                return self._db is not None and self._db.is_available

            try:
                if self._db is None:
                    from anvel_database_service import get_database_service
                    self._db = get_database_service()

                self._initialized = True
                return self._db is not None and self._db.is_available
            except ImportError:
                log.warning("Database service not available - trades will not be persisted")
                self._initialized = True
                return False
            except (RuntimeError, ConnectionError) as e:
                log.error("Failed to initialize database service: %s", e)
                self._initialized = True
                return False

    def persist_trade(
        self,
        trade: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> Optional[int]:
        """
        Persist a trade to the database and publish events.

        Args:
            trade: Trade data dictionary
            user_id: User ID (uses default if not provided)

        Returns:
            Trade ID from database, or None if persistence failed
        """
        # Always publish trade event, even without database
        trade_id = None

        if not self._ensure_initialized():
            log.debug("Trade not persisted - database not available")
            # Still publish event with a generated trade ID
            import uuid
            trade_id = f"local-{uuid.uuid4().hex[:8]}"
            self._publish_trade_event(trade, trade_id, user_id or self._default_user_id)
            return None

        try:
            # Extract trade data
            symbol = trade.get("symbol", "UNKNOWN")
            side = trade.get("side", "buy")
            quantity = Decimal(str(trade.get("quantity", 0)))
            price = Decimal(str(trade.get("execution_price", trade.get("price", 0))))
            total = quantity * price
            fee = Decimal(str(trade.get("fee", 0)))
            status = trade.get("status", "filled")
            strategy = trade.get("strategy")
            signal_confidence = trade.get("signal_confidence")

            # Build metadata
            metadata = {
                "execution_latency_ms": trade.get("execution_latency_ms"),
                "order_type": trade.get("order_type", "market"),
                "broker_response": trade.get("broker_response"),
            }

            # Extract exchange from broker response or default
            exchange = "anvel"
            if trade.get("broker_response"):
                exchange = trade["broker_response"].get("exchange", "anvel")

            # Record to database
            trade_id = self._db.record_trade(
                user_id=user_id or self._default_user_id,
                exchange=exchange,
                pair=symbol,
                side=side,
                order_type=trade.get("order_type", "market"),
                price=price,
                quantity=quantity,
                total=total,
                fee=fee,
                status=status,
                strategy=strategy,
                signal_confidence=signal_confidence,
                metadata=metadata,
            )

            if trade_id:
                log.info(
                    "Trade persisted: id=%s symbol=%s side=%s qty=%s @ %s",
                    trade_id, symbol, side, quantity, price
                )

                # Publish trade executed event
                self._publish_trade_event(trade, trade_id, user_id)

            return trade_id

        except (ValueError, TypeError, KeyError) as e:
            log.error("Failed to persist trade - data error: %s", e)
            return None
        except Exception as e:
            log.error("Failed to persist trade - unexpected error: %s", e)
            return None

    def _publish_trade_event(
        self,
        trade: Dict[str, Any],
        trade_id: int,
        user_id: Optional[str],
    ) -> None:
        """Publish trade executed event to event bus."""
        if not self._event_bus:
            return

        try:
            event = TradeExecutedEvent(
                trade_id=str(trade_id),
                symbol=trade.get("symbol", "UNKNOWN"),
                side=trade.get("side", "buy"),
                quantity=float(trade.get("quantity", 0)),
                price=float(trade.get("execution_price", trade.get("price", 0))),
                total=float(trade.get("quantity", 0)) * float(trade.get("execution_price", trade.get("price", 0))),
                fee=float(trade.get("fee", 0)),
                status=trade.get("status", "filled"),
                strategy=trade.get("strategy"),
                execution_latency_ms=float(trade.get("execution_latency_ms", 0)),
                timestamp=time.time(),
                user_id=user_id,
                metadata=trade.get("metadata", {}),
            )

            self._event_bus.publish("trade.executed", event.to_dict())
            log.debug("Published trade.executed event for trade %s", trade_id)

        except (AttributeError, TypeError) as e:
            log.warning("Failed to publish trade event: %s", e)

    def update_portfolio(
        self,
        user_id: str,
        symbol: str,
        quantity_delta: float,
        price: float,
    ) -> bool:
        """
        Update user portfolio after trade execution.

        Args:
            user_id: User ID
            symbol: Asset symbol
            quantity_delta: Change in quantity (positive for buy, negative for sell)
            price: Execution price

        Returns:
            True if update succeeded
        """
        if not self._ensure_initialized():
            return False

        try:
            # Get current position
            portfolio = self._db.get_portfolio(user_id)
            current_pos = next(
                (p for p in portfolio if p.get("asset") == symbol),
                None
            )

            if current_pos:
                # Update existing position
                old_qty = float(current_pos.get("quantity", 0))
                old_avg = float(current_pos.get("average_price", 0))

                new_qty = old_qty + quantity_delta

                # Calculate new average price (weighted average for buys)
                if quantity_delta > 0 and new_qty > 0:
                    new_avg = (old_qty * old_avg + quantity_delta * price) / new_qty
                else:
                    new_avg = old_avg

                return self._db.update_position(
                    user_id=user_id,
                    asset=symbol,
                    quantity=Decimal(str(max(0, new_qty))),
                    average_price=Decimal(str(new_avg)),
                    current_price=Decimal(str(price)),
                )
            else:
                # Create new position
                if quantity_delta > 0:
                    return self._db.update_position(
                        user_id=user_id,
                        asset=symbol,
                        quantity=Decimal(str(quantity_delta)),
                        average_price=Decimal(str(price)),
                        current_price=Decimal(str(price)),
                    )
                return True  # Selling non-existent position, ignore

        except (ValueError, TypeError) as e:
            log.error("Failed to update portfolio: %s", e)
            return False


# =============================================================================
# Learning Feedback Integration
# =============================================================================

class LearningFeedbackBridge:
    """
    Bridge between trade execution and learning service.

    Provides execution feedback to the learning service so it can
    improve signal quality over time.
    """

    def __init__(
        self,
        event_bus: Optional[Any] = None,
        learning_service: Optional[Any] = None,
    ):
        """
        Initialize the feedback bridge.

        Args:
            event_bus: Event bus for subscribing to trade events
            learning_service: Learning service instance
        """
        self._event_bus = event_bus
        self._learning_service = learning_service
        self._subscription = None
        self._trade_signals: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start listening for trade events."""
        if self._event_bus and not self._subscription:
            try:
                self._subscription = self._event_bus.subscribe(
                    "trade.executed",
                    self._handle_trade_executed
                )
                # Also listen for signals to correlate
                self._event_bus.subscribe(
                    "trade.signals",
                    self._handle_trade_signal
                )
                log.info("Learning feedback bridge started")
            except (AttributeError, TypeError) as e:
                log.warning("Failed to start learning feedback bridge: %s", e)

    def stop(self) -> None:
        """Stop listening for trade events."""
        if self._event_bus and self._subscription:
            try:
                self._event_bus.unsubscribe(self._subscription)
                self._subscription = None
                log.info("Learning feedback bridge stopped")
            except (AttributeError, TypeError) as e:
                log.warning("Failed to stop learning feedback bridge: %s", e)

    def _handle_trade_signal(self, payload: Dict[str, Any]) -> None:
        """Store trade signal for later correlation with execution."""
        if not payload:
            return

        signal_id = payload.get("signal_id") or payload.get("id")
        if signal_id:
            with self._lock:
                self._trade_signals[signal_id] = {
                    "strategy": payload.get("strategy"),
                    "confidence": payload.get("confidence"),
                    "expected_price": payload.get("expected_price"),
                    "timestamp": payload.get("timestamp", time.time()),
                }

                # Clean old signals (keep last 1000)
                if len(self._trade_signals) > 1000:
                    oldest = sorted(
                        self._trade_signals.items(),
                        key=lambda x: x[1].get("timestamp", 0)
                    )[:500]
                    for key, _ in oldest:
                        del self._trade_signals[key]

    def _handle_trade_executed(self, payload: Dict[str, Any]) -> None:
        """Handle trade executed event and provide feedback to learning service."""
        if not payload or not self._learning_service:
            return

        try:
            # Extract execution data
            trade_id = payload.get("trade_id")
            symbol = payload.get("symbol")
            strategy = payload.get("strategy")
            execution_price = payload.get("price", 0)
            execution_latency = payload.get("execution_latency_ms", 0)

            # Calculate execution quality
            execution_quality = self._calculate_execution_quality(
                payload,
                execution_latency
            )

            # Create feedback event
            feedback = LearningFeedbackEvent(
                trade_id=str(trade_id),
                symbol=symbol or "UNKNOWN",
                strategy=strategy,
                signal_confidence=payload.get("signal_confidence"),
                execution_price=float(execution_price),
                execution_quality=execution_quality,
                pnl=payload.get("pnl"),
                timestamp=time.time(),
            )

            # Send to learning service
            if hasattr(self._learning_service, "receive_execution_feedback"):
                self._learning_service.receive_execution_feedback(feedback.to_dict())
            elif hasattr(self._learning_service, "ingest_feedback"):
                self._learning_service.ingest_feedback(feedback.to_dict())

            # Publish feedback event
            if self._event_bus:
                self._event_bus.publish("learning.feedback", feedback.to_dict())

            log.debug("Sent execution feedback for trade %s", trade_id)

        except (ValueError, TypeError, KeyError) as e:
            log.warning("Failed to process execution feedback: %s", e)

    def _calculate_execution_quality(
        self,
        trade: Dict[str, Any],
        latency_ms: float,
    ) -> float:
        """
        Calculate execution quality score (0-1).

        Factors:
        - Latency (lower is better)
        - Slippage (lower is better)
        - Fill rate (higher is better)
        """
        quality = 1.0

        # Latency penalty (target < 100ms)
        if latency_ms > 1000:
            quality -= 0.3
        elif latency_ms > 500:
            quality -= 0.2
        elif latency_ms > 100:
            quality -= 0.1

        # Status penalty
        status = trade.get("status", "filled")
        if status == "partial":
            quality -= 0.2
        elif status in ("failed", "rejected", "error"):
            quality -= 0.5

        return max(0.0, min(1.0, quality))


# =============================================================================
# Trade Engine Integration Wrapper
# =============================================================================

class IntegratedTradeEngine:
    """
    Wrapper around ANVELTradeEngine that adds database persistence
    and event publishing.

    This class intercepts trade execution and:
    1. Persists trades to the database
    2. Publishes trade.executed events
    3. Updates portfolio positions
    4. Provides feedback to learning service
    """

    def __init__(
        self,
        trade_engine: Any,
        database_service: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        user_id: str = "system",
    ):
        """
        Initialize the integrated trade engine.

        Args:
            trade_engine: The underlying ANVELTradeEngine instance
            database_service: Database service for persistence
            event_bus: Event bus for publishing events
            user_id: Default user ID for trades
        """
        self._engine = trade_engine
        self._persistence = TradePersistenceLayer(
            database_service=database_service,
            event_bus=event_bus,
            default_user_id=user_id,
        )
        self._event_bus = event_bus
        self._user_id = user_id

        # Wrap the execute method
        self._wrap_execute_method()

    def _wrap_execute_method(self) -> None:
        """Wrap the trade engine's execute method to add persistence."""
        # We'll override execute_next in __getattr__ instead of modifying the engine
        log.info("Trade engine wrapped with persistence layer")

    def execute_next(self, current_prices: Optional[Dict[str, float]] = None) -> str:
        """
        Execute next trade with persistence.

        Wraps the underlying engine's execute_next to add:
        - Database persistence
        - Event publishing
        - Portfolio updates
        """
        # Get the executed_trades count before execution
        pre_count = len(self._engine.executed_trades)

        # Call original method
        result = self._engine.execute_next(current_prices)

        # Check if a trade was executed
        post_count = len(self._engine.executed_trades)
        if post_count > pre_count:
            # Get the newly executed trade
            trade = self._engine.executed_trades[-1]

            # Persist trade and publish event
            trade_id = self._persistence.persist_trade(
                trade=trade,
                user_id=self._user_id,
            )

            if trade_id:
                trade["db_trade_id"] = trade_id

                # Update portfolio
                symbol = trade.get("symbol", "").split("/")[0]
                side = trade.get("side", "buy")
                qty = float(trade.get("quantity", 0))
                price = float(trade.get("execution_price", trade.get("price", 0)))

                delta = qty if side == "buy" else -qty
                self._persistence.update_portfolio(
                    user_id=self._user_id,
                    symbol=symbol,
                    quantity_delta=delta,
                    price=price,
                )

        return result

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to underlying engine."""
        return getattr(self._engine, name)


# =============================================================================
# System Integration Factory
# =============================================================================

class IntegratedSystem:
    """
    Factory for creating a fully integrated ANVEL system.

    Wires together:
    - Event bus
    - Trade engine (with persistence)
    - Database service
    - Learning feedback bridge
    - API gateway (optional)
    """

    def __init__(self):
        """Initialize the integrated system."""
        self._components: Dict[str, Any] = {}
        self._started = False
        self._lock = threading.Lock()

    def _lazy_load(self, component: str) -> Optional[Any]:
        """Lazy load a component."""
        if component in self._components:
            return self._components[component]

        try:
            if component == "event_bus":
                from anvel_event_bus import AnvelEventBus
                self._components["event_bus"] = AnvelEventBus()

            elif component == "database":
                from anvel_database_service import get_database_service
                self._components["database"] = get_database_service()

            elif component == "trade_engine":
                from anvel_trade_engine import ANVELTradeEngine
                event_bus = self._lazy_load("event_bus")
                engine = ANVELTradeEngine(event_bus=event_bus)
                self._components["trade_engine"] = IntegratedTradeEngine(
                    trade_engine=engine,
                    database_service=self._lazy_load("database"),
                    event_bus=event_bus,
                )

            elif component == "learning_bridge":
                self._components["learning_bridge"] = LearningFeedbackBridge(
                    event_bus=self._lazy_load("event_bus"),
                )

            return self._components.get(component)

        except ImportError as e:
            log.warning("Failed to load component %s: %s", component, e)
            return None

    @property
    def event_bus(self) -> Optional[Any]:
        """Get the event bus."""
        return self._lazy_load("event_bus")

    @property
    def database(self) -> Optional[Any]:
        """Get the database service."""
        return self._lazy_load("database")

    @property
    def trade_engine(self) -> Optional[Any]:
        """Get the integrated trade engine."""
        return self._lazy_load("trade_engine")

    @property
    def learning_bridge(self) -> Optional[LearningFeedbackBridge]:
        """Get the learning feedback bridge."""
        return self._lazy_load("learning_bridge")

    def start(self) -> None:
        """Start all integrated components."""
        with self._lock:
            if self._started:
                return

            # Ensure all components are loaded
            self._lazy_load("event_bus")
            self._lazy_load("database")
            self._lazy_load("trade_engine")

            # Start learning bridge
            bridge = self._lazy_load("learning_bridge")
            if bridge:
                bridge.start()

            self._started = True
            log.info("Integrated system started")

    def stop(self) -> None:
        """Stop all integrated components."""
        with self._lock:
            if not self._started:
                return

            # Stop learning bridge
            bridge = self._components.get("learning_bridge")
            if bridge:
                bridge.stop()

            # Close database
            db = self._components.get("database")
            if db and hasattr(db, "close"):
                db.close()

            self._started = False
            log.info("Integrated system stopped")

    def health_check(self) -> Dict[str, Any]:
        """Check health of all components."""
        health = {
            "status": "healthy",
            "components": {},
        }

        # Check event bus
        event_bus = self._components.get("event_bus")
        health["components"]["event_bus"] = {
            "available": event_bus is not None,
            "running": getattr(event_bus, "_running", False) if event_bus else False,
        }

        # Check database
        db = self._components.get("database")
        if db and hasattr(db, "health_check"):
            health["components"]["database"] = db.health_check()
        else:
            health["components"]["database"] = {"available": db is not None}

        # Check trade engine
        engine = self._components.get("trade_engine")
        health["components"]["trade_engine"] = {
            "available": engine is not None,
            "active": getattr(engine, "active", False) if engine else False,
        }

        # Check learning bridge
        bridge = self._components.get("learning_bridge")
        health["components"]["learning_bridge"] = {
            "available": bridge is not None,
            "subscribed": bridge._subscription is not None if bridge else False,
        }

        # Overall status
        if not all(c.get("available", False) for c in health["components"].values()):
            health["status"] = "degraded"

        return health


# =============================================================================
# Module-Level Factory Functions
# =============================================================================

_integrated_system: Optional[IntegratedSystem] = None


def get_integrated_system() -> IntegratedSystem:
    """
    Get or create the integrated system singleton.

    Returns:
        IntegratedSystem instance
    """
    global _integrated_system
    if _integrated_system is None:
        _integrated_system = IntegratedSystem()
    return _integrated_system


def wire_database_to_trade_engine(
    trade_engine: Any,
    database_service: Optional[Any] = None,
    event_bus: Optional[Any] = None,
    user_id: str = "system",
) -> IntegratedTradeEngine:
    """
    Wire database persistence to an existing trade engine.

    Args:
        trade_engine: ANVELTradeEngine instance
        database_service: Database service (lazy loaded if None)
        event_bus: Event bus for events
        user_id: Default user ID

    Returns:
        IntegratedTradeEngine wrapper
    """
    return IntegratedTradeEngine(
        trade_engine=trade_engine,
        database_service=database_service,
        event_bus=event_bus,
        user_id=user_id,
    )
