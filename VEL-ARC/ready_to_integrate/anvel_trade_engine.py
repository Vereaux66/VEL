# flake8: noqa
"""ANVEL Trade Engine - System-Wide Rust Integration

This module provides the core trading engine with full integration to
the high-performance Rust trading layer via vel_python/vel_engine.

The Rust integration provides:
- High-performance order execution
- Risk management (Kelly Criterion, VaR, drawdown protection)
- Position tracking and P&L calculations
- Real-time risk validation

AUTOMATIC BUILD:
The native Rust library is automatically built if not present, ensuring
it is ALWAYS available for live trading operations.
"""
import os
import sys
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import threading
from dataclasses import dataclass, field
from collections import deque
import statistics
from anvel_hybrid_interfaces import (
    make_exec_core,
    make_gateway,
    make_vel_trading_engine,
    make_vel_risk_manager,
)

# DEX-only imports (CEX brokers removed)
from anvel_broker_dex_base import DEXBrokerBase

log = logging.getLogger(__name__)

# Try to import vel_engine for direct access - will auto-build if not present
_VEL_ENGINE = None
VelTradingEngine = None
VelRiskManager = None
VelOrder = None
VelPosition = None

def _ensure_vel_engine():
    """Ensure the VEL engine is available, building if necessary."""
    global _VEL_ENGINE, VelTradingEngine, VelRiskManager, VelOrder, VelPosition
    
    if _VEL_ENGINE is not None:
        return _VEL_ENGINE
    
    try:
        from vel_engine import (
            ensure_native_library,
            TradingEngine as _VelTE,
            RiskManager as _VelRM,
            Order as _VelOrder,
            Position as _VelPosition,
            is_native_available,
        )
        
        # Ensure native library is built and available
        ensure_native_library()
        
        if is_native_available():
            _VEL_ENGINE = True
            VelTradingEngine = _VelTE
            VelRiskManager = _VelRM
            VelOrder = _VelOrder
            VelPosition = _VelPosition
        else:
            _VEL_ENGINE = False
    except ImportError:
        _VEL_ENGINE = False
    
    return _VEL_ENGINE

# Trigger initial load/build attempt on module import
_ensure_vel_engine()


@dataclass
class ExecutionMetrics:
    """Tracks execution timing metrics for performance benchmarking"""
    order_latencies_ns: deque = field(default_factory=lambda: deque(maxlen=10000))
    signal_to_order_ns: deque = field(default_factory=lambda: deque(maxlen=10000))
    total_orders: int = 0
    sub_millisecond_count: int = 0
    
    def record_order_latency(self, latency_ns: int) -> None:
        """Record order execution latency in nanoseconds"""
        self.order_latencies_ns.append(latency_ns)
        self.total_orders += 1
        if latency_ns < 1_000_000:  # Less than 1ms
            self.sub_millisecond_count += 1
    
    def record_signal_latency(self, latency_ns: int) -> None:
        """Record signal-to-order latency in nanoseconds"""
        self.signal_to_order_ns.append(latency_ns)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get execution timing statistics"""
        if not self.order_latencies_ns:
            return {"status": "no_data"}
        
        latencies_ms = [ns / 1_000_000 for ns in self.order_latencies_ns]
        signal_latencies_ms = [ns / 1_000_000 for ns in self.signal_to_order_ns] if self.signal_to_order_ns else []
        
        stats = {
            "total_orders": self.total_orders,
            "sub_millisecond_orders": self.sub_millisecond_count,
            "sub_millisecond_percentage": (self.sub_millisecond_count / self.total_orders * 100) if self.total_orders > 0 else 0,
            "order_latency_ms": {
                "mean": statistics.mean(latencies_ms),
                "median": statistics.median(latencies_ms),
                "min": min(latencies_ms),
                "max": max(latencies_ms),
                "p95": sorted(latencies_ms)[int(len(latencies_ms) * 0.95)] if len(latencies_ms) > 20 else max(latencies_ms),
                "p99": sorted(latencies_ms)[int(len(latencies_ms) * 0.99)] if len(latencies_ms) > 100 else max(latencies_ms),
            }
        }
        
        if signal_latencies_ms:
            stats["signal_to_order_ms"] = {
                "mean": statistics.mean(signal_latencies_ms),
                "median": statistics.median(signal_latencies_ms),
                "min": min(signal_latencies_ms),
                "max": max(signal_latencies_ms),
            }
        
        return stats


class ANVELTradeEngine:
    """
    Advanced trading engine with order management, position tracking,
    risk controls, and performance analytics.
    
    SYSTEM-WIDE RUST INTEGRATION:
    This engine now integrates with the vel_python Rust layer for
    high-performance trading operations when available. The Rust
    engine provides institutional-grade risk management and order
    execution.
    """

    def __init__(self, event_bus: Optional[Any] = None):
        # ================================================================
        # VEL Rust Engine Integration (Primary - System-Wide)
        # ================================================================
        self.vel_trading_engine = None
        self.vel_risk_manager = None
        self.use_vel_engine = False
        
        if _VEL_ENGINE:
            try:
                # Create VEL trading engine with default capital
                self.vel_trading_engine = make_vel_trading_engine(100000.0)
                self.vel_risk_manager = make_vel_risk_manager(100000.0)
                if self.vel_trading_engine is not None:
                    self.use_vel_engine = True
            except (ImportError, RuntimeError, OSError) as e:
                log.debug("VEL engine initialization failed: %s", e)
        
        # ================================================================
        # Hybrid backends (config/env controlled) - Secondary
        # ================================================================
        self.exec_core = make_exec_core(False)
        self.gateway = make_gateway(False)
        try:
            import os, json

            str(os.getenv("ANVEL_HYBRID_ENABLED", "")).lower() in ("1", "true", "yes")
            exec_ep_env = os.getenv("ANVEL_EXEC_CORE_ENDPOINT") or "localhost:50051"
            gw_ep_env = os.getenv("ANVEL_GATEWAY_ENDPOINT") or "localhost:50052"
            exec_ep_cfg = None
            gw_ep_cfg = None
            if os.path.exists("anvel_config.json"):
                with open("anvel_config.json", "r") as _f:
                    _cfg = json.load(_f)
                hyb = (_cfg.get("system_config", {}) or {}).get("hybrid", {})
                bool(hyb.get("enabled", False))
                exec_ep_cfg = hyb.get("exec_core_endpoint")
                gw_ep_cfg = hyb.get("gateway_endpoint")
            exec_ep = exec_ep_cfg or exec_ep_env
            gw_ep = gw_ep_cfg or gw_ep_env
            self.exec_core = make_exec_core(True, exec_ep)
            self.gateway = make_gateway(True, gw_ep)
            # Broker (live mode) — DEX-only execution
            self.broker = None
            tc = (
                (_cfg.get("trading_config") or {})
                if os.path.exists("anvel_config.json")
                else {}
            )
            mode = tc.get("trading_mode", "simulation")
            if str(mode).lower() == "live_trading":
                # DEX-only: create broker via DEX broker factory
                from anvel_dex_broker_factory import get_dex_factory
                dex_factory = get_dex_factory()
                dex_name = tc.get("dex", "uniswap_v3")
                chain_id = int(tc.get("chain_id", 1))
                rpc_url = tc.get("rpc_url") or os.getenv(f"VEL_RPC_{chain_id}")
                private_key = os.getenv("VEL_PRIVATE_KEY") or os.getenv("ANVEL_PRIVATE_KEY")
                self.broker = dex_factory.get_broker(
                    dex_name=dex_name,
                    chain_id=chain_id,
                    rpc_url=rpc_url,
                    private_key=private_key,
                )
                if self.broker:
                    log.info(
                        "Live trading broker initialized: %s on chain %d",
                        dex_name, chain_id,
                    )
                else:
                    log.warning(
                        "Failed to create DEX broker %s on chain %d — "
                        "live trading will not execute orders",
                        dex_name, chain_id,
                    )
        except Exception:
            # Fail hard if hybrid interfaces cannot be initialized
            raise

        self.trade_queue = []
        self.executed_trades = []
        self.open_positions = {}
        self.active = True
        self.lock = threading.Lock()
        
        # Execution metrics for performance benchmarking
        self.execution_metrics = ExecutionMetrics()

        # Advanced features
        self.daily_pnl = 0.0
        self.total_pnl = 0.0
        self.daily_trades = 0
        self.max_daily_trades = 50
        self.max_position_size = 10000  # Default $10k
        self.total_capital = 100000  # Default $100k
        self.scaled_capital = 5000.0  # Start small
        self.base_capital = 5000.0
        self.capital_scale_settings = {
            "growth_threshold": 2000.0,  # Increase when net profits cross this
            "scale_factor": 1.5,  # 50% growth increments
            "max_capital": 100000.0,
            "drawdown_scale": 0.5,  # scale down on drawdowns
            "drawdown_threshold": -1000.0,
        }
        self._scale_anchor_pnl = 0.0
        self._scale_stage = 1
        self._apply_scaled_limits()

        # Risk management
        self.daily_loss_limit = 2000  # Default $2k daily loss
        self.max_positions = 10
        self.position_limits = {}

        # Performance tracking
        self.win_count = 0
        self.loss_count = 0
        self.trade_history_detailed = []

        # Order types
        self.pending_orders = {"market": [], "limit": [], "stop": [], "stop_limit": []}
        # Event bus wiring
        self.event_bus = event_bus
        self._signal_subscription = None
        if self.event_bus:
            self._subscribe_to_signals()
        
        # ================================================================
        # Integrated Scalping Engine (Primary Trading Strategy)
        # ================================================================
        self._scalping_engine = None
        self._scalping_enabled = False
        self._scalping_thread = None
        self._scalping_stop_event = threading.Event()
        self._scalping_worker_pool = []
        self._scalping_task_queue = deque()
        self._scalping_queue_lock = threading.Lock()
        self._default_symbols = ["BTC", "ETH", "SOL", "DOGE", "XRP", "ADA", "AVAX", "MATIC"]
        
        # High-performance worker pool settings
        self._num_workers = min(8, os.cpu_count() or 4)  # Scale with CPU cores
        self._batch_size = 50  # Process signals in batches for efficiency
        self._scan_interval = 1.0  # Market scan interval in seconds
        self._worker_idle_sleep = 0.01  # Worker idle sleep duration in seconds
        self._thread_shutdown_timeout = 5.0  # Thread shutdown timeout in seconds

    def attach_event_bus(self, event_bus: Any) -> str:
        """Attach or replace the event bus subscription."""
        if self._signal_subscription and self.event_bus:
            self.event_bus.unsubscribe(self._signal_subscription)
            self._signal_subscription = None
        self.event_bus = event_bus
        if self.event_bus:
            self._subscribe_to_signals()
            return "[TRADE ENGINE] Event bus attached"
        return "[TRADE ENGINE] Event bus cleared"

    def _subscribe_to_signals(self):
        if not self.event_bus:
            return
        self._signal_subscription = self.event_bus.subscribe(
            "trade.signals", self.handle_trade_signal
        )

    def handle_trade_signal(self, payload: Optional[Dict[str, Any]]):
        """Translate bus payloads into queued trades."""
        if not payload or not isinstance(payload, dict):
            return "[TRADE ENGINE] Ignored invalid signal"
        symbol = payload.get("symbol")
        side = payload.get("side")
        quantity = float(payload.get("quantity", 1) or 0)
        strategy = payload.get("strategy", "bus_signal")
        order_type = payload.get("order_type", "market")
        limit_price = payload.get("limit_price")
        stop_price = payload.get("stop_price")
        if not symbol or not side or quantity <= 0:
            return "[TRADE ENGINE] Invalid signal payload"
        return self.queue_trade(
            symbol=symbol,
            side=side,
            quantity=quantity,
            strategy=strategy,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
        )

    def queue_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        strategy: str,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> str:
        """
        Queue a trade with advanced order types

        Args:
            symbol: Trading symbol (e.g., 'AAPL', 'BTC')
            side: 'buy' or 'sell'
            quantity: Number of units
            strategy: Strategy name that generated signal
            order_type: 'market', 'limit', 'stop', 'stop_limit'
            limit_price: For limit orders
            stop_price: For stop orders
        """
        with self.lock:
            if not self.active:
                return "[TRADE ENGINE] Inactive - trading halted"

            # Check daily trade limit
            if self.daily_trades >= self.max_daily_trades:
                return f"[TRADE ENGINE] Daily trade limit reached ({self.max_daily_trades})"

            # Check daily loss limit
            if abs(self.daily_pnl) >= self.daily_loss_limit and self.daily_pnl < 0:
                self.active = False
                return f"[TRADE ENGINE] Daily loss limit hit (${abs(self.daily_pnl):.2f}). Trading halted."

            # Validate order
            if side.lower() not in ["buy", "sell"]:
                return f"[TRADE ENGINE] Invalid side: {side}"

            # Determine price basis
            price_estimate = limit_price if limit_price else 0.0
            if not price_estimate:
                try:
                    quote = self.get_quote(symbol)
                except (ConnectionError, TimeoutError, ValueError) as e:
                    log.debug("Quote fetch failed for %s: %s", symbol, e)
                    quote = {}
                price_estimate = (
                    quote.get("mid")
                    or quote.get("last")
                    or quote.get("bid")
                    or quote.get("ask")
                    or 100.0
                )

            price_basis = max(price_estimate, 0.01)
            original_quantity = quantity
            quantity_adjusted = False

            if side.lower() == "buy":
                exposure_room = max(self.scaled_capital - self._total_exposure(), 0.0)
                if exposure_room <= 0.0:
                    return "[TRADE ENGINE] No available capital for new positions"

                max_qty_pos = self.max_position_size / price_basis
                max_qty_exposure = exposure_room / price_basis
                allowed_qty = min(quantity, max_qty_pos, max_qty_exposure)

                if allowed_qty <= 0:
                    return f"[TRADE ENGINE] Requested size exceeds scaled capital ${self.scaled_capital:.2f}"

                if allowed_qty < quantity:
                    quantity = round(allowed_qty, 8)
                    quantity_adjusted = True

            position_value = quantity * price_basis

            if position_value > self.max_position_size:
                return f"[TRADE ENGINE] Position size ${position_value:.2f} exceeds limit ${self.max_position_size:.2f}"

            # Check max positions
            if side.lower() == "buy" and len(self.open_positions) >= self.max_positions:
                return (
                    f"[TRADE ENGINE] Maximum positions reached ({self.max_positions})"
                )

            # Check aggregate exposure versus scaled capital
            projected_exposure = self._total_exposure() + position_value
            if projected_exposure > self.scaled_capital:
                return (
                    f"[TRADE ENGINE] Exposure ${projected_exposure:.2f} exceeds scaled capital "
                    f"${self.scaled_capital:.2f}"
                )

            # Create trade order
            trade = {
                "symbol": symbol.upper(),
                "side": side.lower(),
                "quantity": quantity,
                "original_quantity": original_quantity,
                "quantity_adjusted": quantity_adjusted,
                "strategy": strategy,
                "order_type": order_type,
                "limit_price": limit_price,
                "stop_price": stop_price,
                "time_queued": time.time(),
                "time_queued_str": time.ctime(),
                "status": "queued",
            }

            # Add to appropriate queue
            if order_type in self.pending_orders:
                self.pending_orders[order_type].append(trade)
            else:
                self.trade_queue.append(trade)

            return f"[TRADE ENGINE] Queued: {order_type.upper()} {side.upper()} {quantity} {symbol} @ {limit_price if limit_price else 'MARKET'}"

    def execute_next(self, current_prices: Optional[Dict[str, float]] = None) -> str:
        """
        Execute next trade in queue with realistic execution logic.
        
        Tracks execution latency for performance benchmarking.

        Args:
            current_prices: Dict of {symbol: price} for execution
        """
        # Start high-precision timing
        exec_start_ns = time.perf_counter_ns()
        
        with self.lock:
            if not self.trade_queue and not self.pending_orders["market"]:
                return "[TRADE ENGINE] No trades in queue"

            # Process market orders first
            if self.pending_orders["market"]:
                trade = self.pending_orders["market"].pop(0)
            elif self.trade_queue:
                trade = self.trade_queue.pop(0)
            else:
                return "[TRADE ENGINE] No market orders ready"
            
            # Calculate signal-to-execution latency if timestamp available
            if "time_queued" in trade:
                signal_latency_ns = int((time.time() - trade["time_queued"]) * 1_000_000_000)
                self.execution_metrics.record_signal_latency(signal_latency_ns)

            # Get execution price
            symbol = trade["symbol"]
            # Live route if broker available
            if hasattr(self, "broker") and self.broker:
                try:
                    resp = self.broker.submit_order(
                        symbol,
                        trade["side"],
                        trade["quantity"],
                        trade.get("limit_price"),
                        trade.get("order_type", "market"),
                    )
                    trade["broker_response"] = resp
                    if resp.get("status") == "placed":
                        execution_price = (
                            trade.get("limit_price")
                            or self.get_quote(symbol).get(
                                "bid" if trade["side"] == "sell" else "ask"
                            )
                            or 0.0
                        )
                    else:
                        execution_price = (
                            trade.get("limit_price")
                            or self.get_quote(symbol).get("mid")
                            or 100.0
                        )
                except (ConnectionError, TimeoutError, RuntimeError, ValueError) as e:
                    log.warning("Broker order failed for %s: %s", symbol, e)
                    execution_price = trade.get("limit_price") or 100.0
            elif current_prices and symbol in current_prices:
                execution_price = current_prices[symbol]
            else:
                execution_price = (
                    trade.get("limit_price") or 100.0
                )  # Default for simulation

            # Add slippage (realistic execution)
            slippage = 0.001  # 0.1% slippage
            if trade["side"] == "buy":
                execution_price *= 1 + slippage
            else:
                execution_price *= 1 - slippage

            # Execute trade
            trade["status"] = "executed"
            trade["exec_time"] = time.time()
            trade["exec_time_str"] = time.ctime()
            trade["execution_price"] = execution_price
            trade["total_value"] = execution_price * trade["quantity"]

            # Commission (realistic fee)
            commission = trade["total_value"] * 0.001  # 0.1% commission
            trade["commission"] = commission
            trade["net_value"] = trade["total_value"] - commission

            # Update positions
            if trade["side"] == "buy":
                if symbol in self.open_positions:
                    # Average up position
                    pos = self.open_positions[symbol]
                    total_qty = pos["quantity"] + trade["quantity"]
                    avg_price = (
                        pos["avg_price"] * pos["quantity"]
                        + trade["execution_price"] * trade["quantity"]
                    ) / total_qty
                    self.open_positions[symbol] = {
                        "quantity": total_qty,
                        "avg_price": avg_price,
                        "entry_time": pos["entry_time"],
                        "strategy": trade["strategy"],
                    }
                else:
                    # New position
                    self.open_positions[symbol] = {
                        "quantity": trade["quantity"],
                        "avg_price": execution_price,
                        "entry_time": time.time(),
                        "strategy": trade["strategy"],
                    }
            else:  # sell
                if symbol in self.open_positions:
                    pos = self.open_positions[symbol]
                    # Calculate P&L
                    pnl = (execution_price - pos["avg_price"]) * trade[
                        "quantity"
                    ] - commission
                    trade["pnl"] = pnl
                    self.daily_pnl += pnl
                    self.total_pnl += pnl

                    # Track win/loss
                    if pnl > 0:
                        self.win_count += 1
                    else:
                        self.loss_count += 1

                    # Update or close position
                    if trade["quantity"] >= pos["quantity"]:
                        del self.open_positions[symbol]
                    else:
                        pos["quantity"] -= trade["quantity"]

            # Record trade
            self.executed_trades.append(trade)
            self.trade_history_detailed.append(trade)
            self.daily_trades += 1

            self._update_capital_scaling(trade)

            # Keep history manageable
            if len(self.executed_trades) > 1000:
                self.executed_trades = self.executed_trades[-500:]
            
            # Record execution timing
            exec_end_ns = time.perf_counter_ns()
            exec_latency_ns = exec_end_ns - exec_start_ns
            self.execution_metrics.record_order_latency(exec_latency_ns)
            trade["execution_latency_ns"] = exec_latency_ns
            trade["execution_latency_ms"] = exec_latency_ns / 1_000_000

            pnl_str = f", P&L: ${trade.get('pnl', 0):.2f}" if "pnl" in trade else ""
            latency_str = f" ({exec_latency_ns / 1_000_000:.3f}ms)"
            return f"[TRADE ENGINE] Executed {trade['side'].upper()} {trade['quantity']} {trade['symbol']} @ ${execution_price:.2f}{pnl_str}{latency_str}"

    def set_stop_loss(self, symbol: str, stop_price: float) -> str:
        """Set stop loss for an open position"""
        with self.lock:
            if symbol not in self.open_positions:
                return f"[TRADE ENGINE] No open position in {symbol}"

            pos = self.open_positions[symbol]
            pos["stop_loss"] = stop_price

            return f"[TRADE ENGINE] Stop loss set for {symbol} @ ${stop_price:.2f}"

    def set_take_profit(self, symbol: str, target_price: float) -> str:
        """Set take profit for an open position"""
        with self.lock:
            if symbol not in self.open_positions:
                return f"[TRADE ENGINE] No open position in {symbol}"

            pos = self.open_positions[symbol]
            pos["take_profit"] = target_price

            return f"[TRADE ENGINE] Take profit set for {symbol} @ ${target_price:.2f}"

    def check_stop_loss_take_profit(
        self, current_prices: Dict[str, float]
    ) -> List[str]:
        """Check if any positions hit stop loss or take profit"""
        actions = []

        with self.lock:
            symbols_to_close = []

            for symbol, pos in self.open_positions.items():
                if symbol not in current_prices:
                    continue

                current_price = current_prices[symbol]

                # Check stop loss
                if "stop_loss" in pos and current_price <= pos["stop_loss"]:
                    symbols_to_close.append((symbol, "stop_loss", current_price))

                # Check take profit
                elif "take_profit" in pos and current_price >= pos["take_profit"]:
                    symbols_to_close.append((symbol, "take_profit", current_price))

            # Close positions
            for symbol, reason, price in symbols_to_close:
                pos = self.open_positions[symbol]
                result = self.queue_trade(
                    symbol=symbol,
                    side="sell",
                    quantity=pos["quantity"],
                    strategy=f"{reason}_triggered",
                    order_type="market",
                )
                actions.append(f"{result} (Reason: {reason})")

        return (
            actions
            if actions
            else ["[TRADE ENGINE] No stop loss or take profit triggered"]
        )

    def get_open_positions(self) -> Dict[str, Any]:
        """Get all open positions with current status"""
        with self.lock:
            return self.open_positions.copy()

    def get_position_summary(
        self, current_prices: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """Get detailed summary of all positions"""
        with self.lock:
            summary = {
                "total_positions": len(self.open_positions),
                "total_value": 0.0,
                "unrealized_pnl": 0.0,
                "positions": [],
            }

            for symbol, pos in self.open_positions.items():
                current_price = (
                    current_prices.get(symbol, pos["avg_price"])
                    if current_prices
                    else pos["avg_price"]
                )
                current_value = current_price * pos["quantity"]
                cost_basis = pos["avg_price"] * pos["quantity"]
                unrealized_pnl = current_value - cost_basis

                summary["total_value"] += current_value
                summary["unrealized_pnl"] += unrealized_pnl

                summary["positions"].append(
                    {
                        "symbol": symbol,
                        "quantity": pos["quantity"],
                        "avg_price": pos["avg_price"],
                        "current_price": current_price,
                        "unrealized_pnl": unrealized_pnl,
                        "unrealized_pnl_pct": (
                            (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0
                        ),
                        "strategy": pos["strategy"],
                    }
                )

            return summary

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics"""
        with self.lock:
            total_trades = self.win_count + self.loss_count
            win_rate = (self.win_count / total_trades * 100) if total_trades > 0 else 0

            return {
                "total_trades": total_trades,
                "wins": self.win_count,
                "losses": self.loss_count,
                "win_rate": win_rate,
                "daily_pnl": self.daily_pnl,
                "total_pnl": self.total_pnl,
                "daily_trades": self.daily_trades,
                "open_positions": len(self.open_positions),
                "scaled_capital": self.scaled_capital,
                "scale_stage": self._scale_stage,
                "capital_utilization": (
                    (
                        sum(
                            p["quantity"] * p["avg_price"]
                            for p in self.open_positions.values()
                        )
                        / self.scaled_capital
                        * 100
                    )
                    if self.scaled_capital > 0
                    else 0
                ),
            }

    def reset_daily_stats(self):
        """Reset daily statistics (call at start of each day)"""
        with self.lock:
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.active = True  # Re-enable if halted yesterday
            return "[TRADE ENGINE] Daily stats reset"

    def get_execution_metrics(self) -> Dict[str, Any]:
        """
        Get execution timing metrics for performance benchmarking.
        
        Returns:
            Dict with latency statistics including sub-millisecond performance data
        """
        return self.execution_metrics.get_stats()

    def benchmark_execution(self, n_orders: int = 100) -> Dict[str, Any]:
        """
        Run execution benchmark with simulated orders.
        
        Args:
            n_orders: Number of simulated orders to benchmark
            
        Returns:
            Dict with benchmark results
        """
        import random
        
        symbols = ["BTC", "ETH", "SOL", "DOGE", "SHIB"]
        results = []
        
        for i in range(n_orders):
            symbol = random.choice(symbols)
            side = random.choice(["buy", "sell"])
            quantity = random.uniform(0.001, 1.0)
            
            # Queue the trade
            self.queue_trade(
                symbol=symbol,
                side=side,
                quantity=quantity,
                strategy="benchmark",
                order_type="market"
            )
            
            # Execute with timing
            start = time.perf_counter_ns()
            self.execute_next(current_prices={symbol: 100.0})
            end = time.perf_counter_ns()
            
            results.append(end - start)
        
        latencies_ms = [ns / 1_000_000 for ns in results]
        sub_ms = sum(1 for ns in results if ns < 1_000_000)
        
        return {
            "total_orders": n_orders,
            "sub_millisecond_orders": sub_ms,
            "sub_millisecond_percentage": (sub_ms / n_orders) * 100,
            "mean_latency_ms": statistics.mean(latencies_ms),
            "median_latency_ms": statistics.median(latencies_ms),
            "min_latency_ms": min(latencies_ms),
            "max_latency_ms": max(latencies_ms),
            "p95_latency_ms": sorted(latencies_ms)[int(n_orders * 0.95)],
            "p99_latency_ms": sorted(latencies_ms)[int(n_orders * 0.99)],
            "orders_per_second_estimate": 1000 / statistics.mean(latencies_ms) if statistics.mean(latencies_ms) > 0 else 0,
        }

    def history(self, limit: int = 5) -> List:
        """Get recent trade history"""
        with self.lock:
            return (
                self.executed_trades[-limit:]
                if self.executed_trades
                else ["[TRADE ENGINE] No history"]
            )

    def toggle(self, state: bool) -> str:
        """Enable or disable trading"""
        with self.lock:
            self.active = state
            return f"[TRADE ENGINE] {'Activated' if state else 'Deactivated'}"

    def _apply_scaled_limits(self) -> None:
        """Adjust internal limits based on the current scaled capital."""
        self.scaled_capital = max(
            self.base_capital,
            min(
                self.scaled_capital,
                self.capital_scale_settings.get("max_capital", self.scaled_capital),
                self.total_capital,
            ),
        )
        # Limit a single position to 20% of scaled capital (min $250)
        self.max_position_size = max(self.scaled_capital * 0.2, 250.0)
        # Daily loss limit tied to scaled capital (min $200)
        self.daily_loss_limit = max(self.scaled_capital * 0.2, 200.0)

    def _total_exposure(self) -> float:
        """Return notional exposure of all open positions."""
        return sum(
            pos["quantity"] * pos["avg_price"] for pos in self.open_positions.values()
        )

    def _update_capital_scaling(self, trade: Dict[str, Any]) -> None:
        """Grow or shrink trading capital based on realized performance."""
        settings = self.capital_scale_settings
        net_gain = self.total_pnl - self._scale_anchor_pnl
        scaled = False

        if net_gain >= settings["growth_threshold"]:
            self.scaled_capital *= settings["scale_factor"]
            self._scale_anchor_pnl = self.total_pnl
            self._scale_stage += 1
            scaled = True
        elif net_gain <= settings["drawdown_threshold"]:
            self.scaled_capital *= settings["drawdown_scale"]
            self.scaled_capital = max(self.scaled_capital, self.base_capital)
            self._scale_anchor_pnl = self.total_pnl
            self._scale_stage = max(1, self._scale_stage - 1)
            scaled = True

        if scaled:
            self._apply_scaled_limits()

    # Consolidated APIs from submodules
    def route_order(self, exchange: str, order: Dict) -> str:
        if hasattr(self, "broker") and self.broker:
            res = self.broker.submit_order(
                order.get("symbol", "SYM"),
                order.get("side", "buy"),
                order.get("quantity", 0),
                order.get("price"),
            )
            return f"[TRADE ENGINE] Routed via {self.broker.name}: {res.get('status', 'ok')}"
        res = self.exec_core.submit_order(
            order.get("symbol", "SYM"),
            order.get("side", "buy"),
            order.get("quantity", 0),
            order.get("price"),
        )
        return f"[TRADE ENGINE] Routed via ExecCore: {res.get('status', 'ok')} id={res.get('id', '-')}"

    def get_quote(self, symbol: str) -> Dict:
        if hasattr(self, "broker") and self.broker:
            return self.broker.get_quote(symbol)
        return self.gateway.get_quote(symbol)

    def assess_risk(self, order: Dict, portfolio: Optional[Dict] = None) -> Dict:
        return self.exec_core.assess_risk(order, portfolio)

    def set_risk_limits(
        self,
        max_position_size: float = None,
        daily_loss_limit: float = None,
        max_positions: int = None,
        max_daily_trades: int = None,
    ) -> str:
        """Configure risk management limits"""
        with self.lock:
            if max_position_size:
                self.max_position_size = max_position_size
            if daily_loss_limit:
                self.daily_loss_limit = daily_loss_limit
            if max_positions:
                self.max_positions = max_positions
            if max_daily_trades:
                self.max_daily_trades = max_daily_trades

            return "[TRADE ENGINE] Risk limits updated"

    def submit_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        strategy: str = "manual",
        order_type: str = "market",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
    ) -> str:
        """Submit a trade (alias for queue_trade)"""
        return self.queue_trade(
            symbol, side, quantity, strategy, order_type, limit_price, stop_price
        )

    def get_positions(self) -> Dict[str, Any]:
        """Get all open positions (alias for get_open_positions)"""
        return self.get_open_positions()

    def performance_summary(self) -> Dict[str, Any]:
        """Get performance summary (alias for get_performance_stats)"""
        return self.get_performance_stats()

    def close_position(self, symbol: str) -> str:
        """Close a position by symbol"""
        with self.lock:
            if symbol.upper() not in self.open_positions:
                return f"[TRADE ENGINE] No open position for {symbol}"

            position = self.open_positions[symbol.upper()]
            quantity = position.get("quantity", 0)
            side = "sell" if position.get("side", "buy") == "buy" else "buy"

            return self.queue_trade(
                symbol=symbol,
                side=side,
                quantity=quantity,
                strategy="close_position",
                order_type="market",
            )

    # ========================================================================
    # VEL Rust Engine System-Wide Integration Methods
    # ========================================================================
    
    def is_rust_engine_active(self) -> bool:
        """Check if the high-performance Rust trading engine is active."""
        return self.use_vel_engine and self.vel_trading_engine is not None
    
    def get_rust_engine_stats(self) -> Dict[str, Any]:
        """Get statistics from the Rust trading engine if available."""
        if self.use_vel_engine and self.vel_trading_engine is not None:
            try:
                return self.vel_trading_engine.get_stats()
            except (AttributeError, RuntimeError, OSError) as e:
                log.debug("Failed to get Rust engine stats: %s", e)
        return {"engine": "python-fallback", "active": False}
    
    def calculate_risk_metrics(self, returns: List[float]) -> Dict[str, Any]:
        """Calculate comprehensive risk metrics using the Rust engine.
        
        Returns VaR, volatility, and Sharpe ratio.
        """
        return get_risk_metrics(returns)
    
    def get_kelly_position_size(
        self, win_rate: float, avg_win: float, avg_loss: float
    ) -> float:
        """Calculate Kelly Criterion position size using the Rust engine.
        
        Args:
            win_rate: Historical win rate (0.0 to 1.0)
            avg_win: Average winning trade return
            avg_loss: Average losing trade return
            
        Returns:
            Recommended position size as fraction of capital
        """
        if self.use_vel_engine and self.vel_risk_manager is not None:
            try:
                return self.vel_risk_manager.calculate_kelly_position_size(
                    win_rate, avg_win, avg_loss
                )
            except (ValueError, RuntimeError, ZeroDivisionError) as e:
                log.debug("Rust Kelly calculation failed: %s", e)
        
        # Fallback: Python Kelly calculation
        if win_rate <= 0 or avg_win <= 0 or avg_loss <= 0:
            return 0.0
        loss_rate = 1.0 - win_rate
        win_loss_ratio = avg_win / avg_loss
        kelly_pct = (win_rate * win_loss_ratio - loss_rate) / win_loss_ratio
        return max(0, kelly_pct * 0.25)  # Use 25% Kelly for safety
    
    def validate_order_risk(self, order: Dict[str, Any]) -> Dict[str, Any]:
        """Validate an order against risk limits using the Rust engine.
        
        Returns assessment with 'ok' boolean and 'reasons' list.
        """
        if self.use_vel_engine and self.vel_risk_manager is not None and _VEL_ENGINE:
            try:
                symbol = order.get("symbol", "UNKNOWN")
                side = order.get("side", "buy")
                quantity = float(order.get("quantity", 0.0))
                price = float(order.get("price") or order.get("limit_price") or 100.0)
                
                vel_order = VelOrder(
                    f"risk-{int(time.time() * 1000)}",
                    symbol,
                    side,
                    "limit" if price else "market",
                    quantity,
                    price,
                    None,
                )
                
                try:
                    self.vel_risk_manager.validate_order(vel_order)
                    return {"ok": True, "reasons": [], "engine": "vel-rust"}
                except (ValueError, RuntimeError) as risk_err:
                    return {"ok": False, "reasons": [str(risk_err)], "engine": "vel-rust"}
            except (TypeError, AttributeError, KeyError) as e:
                log.debug("VelOrder creation failed: %s", e)
        
        # Fallback: Basic validation
        assessment = {"ok": True, "reasons": [], "engine": "python-fallback"}
        quantity = float(order.get("quantity", 0.0))
        if quantity <= 0:
            assessment["ok"] = False
            assessment["reasons"].append("Invalid quantity")
        return assessment
    
    def get_engine_info(self) -> Dict[str, Any]:
        """Get information about the active trading engines."""
        info = {
            "rust_engine_active": self.use_vel_engine,
            "rust_engine_available": _VEL_ENGINE is True,
            "exec_core_enabled": getattr(self.exec_core, "enabled", False),
            "gateway_enabled": getattr(self.gateway, "enabled", False),
            "broker_type": type(self.broker).__name__ if self.broker else None,
            "scalping_enabled": self._scalping_enabled,
            "scalping_engine_active": self._scalping_engine is not None,
        }
        
        if self.use_vel_engine and self.vel_trading_engine is not None:
            try:
                stats = self.vel_trading_engine.get_stats()
                info["rust_engine_stats"] = stats
            except (AttributeError, RuntimeError) as e:
                log.debug("Failed to get Rust engine stats: %s", e)

        if self._scalping_engine is not None:
            try:
                info["scalping_stats"] = self._scalping_engine.get_engine_stats()
            except (AttributeError, RuntimeError) as e:
                log.debug("Failed to get scalping stats: %s", e)
        
        return info
    
    # =========================================================================
    # Integrated Scalping Mode (Primary Default Strategy)
    # =========================================================================
    
    def enable_scalping_mode(
        self,
        symbols: List[str] = None,
        config: Dict = None,
        auto_trade: bool = False,
        num_workers: int = None,
        zenith_mode: bool = True,
    ) -> str:
        """
        Enable scalping as the primary trading strategy.
        
        This activates the high-frequency scalping engine with momentum
        detection and automated signal generation.
        
        Args:
            symbols: List of symbols to monitor (defaults to major cryptos)
            config: Custom scalping configuration
            auto_trade: Enable automatic trade execution for generated signals
            num_workers: Number of worker threads for parallel processing
            zenith_mode: Enable maximum performance mode with adaptive scaling
            
        Returns:
            Status message
        """
        if self._scalping_enabled:
            return "[TRADE ENGINE] Scalping mode already enabled"
        
        # Import scalping components
        try:
            from anvel_scalping_engine import (
                ScalpingEngine,
                create_scalping_engine,
                DEFAULT_SCALP_CONFIG,
                MAX_WORKER_THREADS,
            )
        except ImportError:
            return "[TRADE ENGINE] Scalping engine not available"
        
        # Create scalping engine with optimized config for heavy workloads
        scalping_config = DEFAULT_SCALP_CONFIG.copy()
        if config:
            scalping_config.update(config)
        
        # Performance optimizations for heavy runtime workloads
        scalping_config.setdefault("batch_processing", True)
        scalping_config.setdefault("parallel_signal_generation", True)
        
        # === ZENITH MODE OPTIMIZATIONS ===
        if zenith_mode:
            scalping_config.update({
                "enable_parallel_processing": True,
                "enable_batch_execution": True,
                "enable_signal_caching": True,
                "enable_adaptive_scaling": True,
                "worker_pool_size": num_workers or 16,
                "max_worker_pool_size": MAX_WORKER_THREADS,
                "batch_size": 500,
                "signal_ttl_seconds": 5,
                "position_check_interval_ms": 50,
                "signal_generation_interval_ms": 100,
            })
        
        self._scalping_engine = create_scalping_engine(
            config=scalping_config,
            max_users=100000,
            trade_executor=self._execute_scalping_trade,
            quote_provider=self.get_quote,
        )
        
        # Configure symbols
        symbols = symbols or self._default_symbols
        for symbol in symbols:
            self._scalping_engine.add_watched_symbol(symbol)
        
        # Configure worker pool for heavy workloads
        if num_workers:
            self._num_workers = num_workers
        
        self._scalping_enabled = True
        self._auto_trade_enabled = auto_trade
        self._zenith_mode = zenith_mode
        
        # Start in zenith mode or standard mode
        if zenith_mode:
            result = self._scalping_engine.start_zenith_mode()
            return f"[TRADE ENGINE] ZENITH MODE: {result}"
        else:
            # Start standard scalping threads
            self._start_scalping_workers()
            return f"[TRADE ENGINE] Scalping mode enabled with {len(symbols)} symbols, {self._num_workers} workers"
    
    def enable_zenith_scalping(
        self,
        symbols: List[str] = None,
        num_workers: int = 32,
        batch_size: int = 500,
        auto_trade: bool = True,
    ) -> str:
        """
        Enable ZENITH performance mode for maximum scalability.
        
        This is the highest performance mode optimized for:
        - 100,000+ concurrent users
        - Heavy runtime workloads
        - Maximum throughput signal processing
        - Adaptive worker scaling
        
        Args:
            symbols: List of symbols to monitor
            num_workers: Base worker pool size (scales up automatically)
            batch_size: Signal batch processing size
            auto_trade: Enable automatic trade execution
            
        Returns:
            Status message
        """
        config = {
            "worker_pool_size": num_workers,
            "max_worker_pool_size": 64,
            "batch_size": batch_size,
            "enable_adaptive_scaling": True,
            "adaptive_scaling_threshold": 0.60,  # Scale earlier
            "signal_ttl_seconds": 3,  # Faster signal expiry
            "position_check_interval_ms": 25,  # 25ms position checks
            "signal_generation_interval_ms": 50,  # 50ms signal generation
        }
        
        return self.enable_scalping_mode(
            symbols=symbols,
            config=config,
            auto_trade=auto_trade,
            num_workers=num_workers,
            zenith_mode=True,
        )
    
    def get_zenith_metrics(self) -> Dict[str, Any]:
        """Get ZENITH mode performance metrics."""
        if not self._scalping_engine:
            return {"error": "Scalping engine not initialized"}
        
        try:
            metrics = self._scalping_engine.get_performance_metrics()
            metrics["zenith_mode_enabled"] = getattr(self, "_zenith_mode", False)
            metrics["trade_engine_trades_queued"] = len(self.trade_queue)
            metrics["trade_engine_executed"] = len(self.executed_trades)
            return metrics
        except (AttributeError, RuntimeError, KeyError) as e:
            return {"error": str(e)}
    
    def disable_scalping_mode(self) -> str:
        """Disable scalping mode and stop all scalping threads."""
        if not self._scalping_enabled:
            return "[TRADE ENGINE] Scalping mode not enabled"
        
        self._scalping_stop_event.set()
        
        # Stop worker threads
        for worker in self._scalping_worker_pool:
            if worker.is_alive():
                worker.join(timeout=self._thread_shutdown_timeout)
        
        # Stop main scalping thread
        if self._scalping_thread and self._scalping_thread.is_alive():
            self._scalping_thread.join(timeout=self._thread_shutdown_timeout)
        
        # Stop the scalping engine
        if self._scalping_engine:
            self._scalping_engine.stop()
        
        self._scalping_enabled = False
        self._scalping_worker_pool = []
        
        return "[TRADE ENGINE] Scalping mode disabled"
    
    def _start_scalping_workers(self) -> None:
        """Start the scalping worker pool for high-throughput processing."""
        self._scalping_stop_event.clear()
        
        # Start worker threads for parallel signal processing
        for i in range(self._num_workers):
            worker = threading.Thread(
                target=self._scalping_worker_loop,
                args=(i,),
                daemon=True,
                name=f"ScalpingWorker-{i}"
            )
            worker.start()
            self._scalping_worker_pool.append(worker)
        
        # Start main market scanning thread
        self._scalping_thread = threading.Thread(
            target=self._scalping_scan_loop,
            daemon=True,
            name="ScalpingScanner"
        )
        self._scalping_thread.start()
    
    def _scalping_scan_loop(self) -> None:
        """Main market scanning loop for the scalping engine."""
        while not self._scalping_stop_event.is_set():
            try:
                if self._scalping_engine and self._scalping_enabled:
                    # Scan for momentum signals
                    signals = self._scalping_engine.scan_for_movers()
                    
                    # Queue signals for worker processing
                    if signals:
                        with self._scalping_queue_lock:
                            for signal in signals:
                                self._scalping_task_queue.append(signal)
                        
                        # Publish to event bus if available
                        if self.event_bus:
                            for signal in signals:
                                self.event_bus.publish("scalping.signal", {
                                    "symbol": signal.symbol,
                                    "direction": signal.direction,
                                    "strength": signal.strength.value,
                                    "predicted_win_rate": signal.predicted_win_rate,
                                    "entry_price": signal.entry_price,
                                    "take_profit": signal.take_profit,
                                    "stop_loss": signal.stop_loss,
                                })
            except Exception as e:
                log.error("Error in scalping scan loop: %s", e)
            
            self._scalping_stop_event.wait(self._scan_interval)
    
    def _scalping_worker_loop(self, worker_id: int) -> None:
        """Worker thread for processing scalping signals."""
        while not self._scalping_stop_event.is_set():
            signal = None
            
            # Get signal from queue
            with self._scalping_queue_lock:
                if self._scalping_task_queue:
                    signal = self._scalping_task_queue.popleft()
            
            if signal:
                try:
                    # Process signal
                    if self._auto_trade_enabled:
                        # Execute trade automatically
                        self._process_scalping_signal(signal)
                except Exception as e:
                    log.error("Error in scalping worker %d: %s", worker_id, e)
            else:
                # No signals to process, wait briefly
                time.sleep(self._worker_idle_sleep)
    
    def _process_scalping_signal(self, signal) -> Dict[str, Any]:
        """Process a scalping signal and potentially execute a trade."""
        if not self._scalping_engine:
            return {"success": False, "error": "Scalping engine not initialized"}
        
        # Validate signal meets criteria
        if not signal.is_actionable(self._scalping_engine.config):
            return {"success": False, "error": "Signal not actionable"}
        
        # Execute trade via trade queue
        side = "buy" if signal.direction == "long" else "sell"
        
        # Calculate position size based on capital and config
        config = self._scalping_engine.config
        max_pct = config.get("max_position_pct", 0.05)
        max_usd = config.get("max_position_usd", 1000.0)
        
        position_value = min(self.scaled_capital * max_pct, max_usd)
        quantity = position_value / signal.entry_price if signal.entry_price > 0 else 0
        
        if quantity <= 0:
            return {"success": False, "error": "Invalid position size"}
        
        result = self.queue_trade(
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            strategy="scalping_momentum",
            order_type="market",
        )
        
        return {"success": "Queued" in result, "result": result}
    
    def _execute_scalping_trade(
        self,
        user_id: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float
    ) -> Dict[str, Any]:
        """Execute a trade from the scalping engine."""
        try:
            result = self.queue_trade(
                symbol=symbol,
                side=side,
                quantity=quantity,
                strategy=f"scalping_{user_id}",
                order_type="market",
            )
            return {"success": "Queued" in result, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_scalping_signals(self) -> List[Dict[str, Any]]:
        """Get current actionable scalping signals."""
        if not self._scalping_engine:
            return []
        
        signals = self._scalping_engine.scan_for_movers()
        return [
            {
                "symbol": s.symbol,
                "direction": s.direction,
                "strength": s.strength.value,
                "predicted_win_rate": s.predicted_win_rate,
                "entry_price": s.entry_price,
                "take_profit": s.take_profit,
                "stop_loss": s.stop_loss,
                "volume_ratio": s.volume_ratio,
                "spread_pct": s.spread_pct,
                "actionable": s.is_actionable(self._scalping_engine.config),
            }
            for s in signals
        ]
    
    def get_scalping_stats(self) -> Dict[str, Any]:
        """Get scalping engine statistics."""
        if not self._scalping_engine:
            return {"enabled": False}
        
        stats = self._scalping_engine.get_engine_stats()
        stats["enabled"] = self._scalping_enabled
        stats["auto_trade_enabled"] = getattr(self, "_auto_trade_enabled", False)
        stats["num_workers"] = self._num_workers
        stats["queue_size"] = len(self._scalping_task_queue)
        
        return stats


class AnvelTradeEngine(ANVELTradeEngine):
    """Concrete trade engine lifecycle wrapper."""

    def __init__(self, event_bus: Optional[Any] = None):
        super().__init__(event_bus=event_bus)

    def startup(self):
        self.active = True
        if self.event_bus and not self._signal_subscription:
            self._subscribe_to_signals()
        return "[TRADE ENGINE] ready"

    def shutdown(self):
        self.active = False
        # Stop scalping mode if enabled
        if self._scalping_enabled:
            self.disable_scalping_mode()
        if self.event_bus and self._signal_subscription:
            self.event_bus.unsubscribe(self._signal_subscription)
            self._signal_subscription = None
        return "[TRADE ENGINE] halted"


# =============================================================================
# Scalping Engine Integration
# =============================================================================

# Import scalping engine components if available
_SCALPING_ENGINE = None
_MULTIUSER_MANAGER = None

try:
    from anvel_scalping_engine import (
        ScalpingEngine,
        create_scalping_engine,
        integrate_with_trade_engine,
        MomentumAnalyzer,
        DEFAULT_SCALP_CONFIG,
    )
    from anvel_multiuser_manager import (
        MultiUserManager,
        create_user_manager,
        UserTradingContext,
    )
    _SCALPING_ENGINE = True
except ImportError:
    _SCALPING_ENGINE = False


def is_scalping_engine_available() -> bool:
    """Check if scalping engine components are available."""
    return _SCALPING_ENGINE


def create_scalping_trade_engine(
    initial_capital: float = 100000.0,
    max_users: int = 100000,
    scalping_config: Dict = None,
) -> Tuple[ANVELTradeEngine, Any, Any]:
    """
    Create a complete trading system with scalping capabilities.
    
    Args:
        initial_capital: Base trading capital
        max_users: Maximum concurrent users for scalping
        scalping_config: Custom scalping configuration
        
    Returns:
        Tuple of (trade_engine, scalping_engine, user_manager)
    """
    if not _SCALPING_ENGINE:
        raise RuntimeError("Scalping engine components not available")
    
    # Create trade engine
    trade_engine = ANVELTradeEngine()
    trade_engine.total_capital = initial_capital
    
    # Create scalping engine
    scalping_engine = create_scalping_engine(
        config=scalping_config,
        max_users=max_users,
    )
    
    # Integrate with trade engine
    integrate_with_trade_engine(scalping_engine, trade_engine)
    
    # Create user manager
    user_manager = create_user_manager(max_users=max_users)
    
    return trade_engine, scalping_engine, user_manager


def get_scalping_config() -> Dict:
    """Get default scalping configuration."""
    if not _SCALPING_ENGINE:
        return {}
    return DEFAULT_SCALP_CONFIG.copy()
