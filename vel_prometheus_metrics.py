#!/usr/bin/env python3
"""
VEL Prometheus Metrics Exporter
================================

Production-grade metrics collection and Prometheus exposition for the VEL trading platform.

Metrics Categories:
- Trading: Intents, executions, success/failure rates, latency
- Risk: Circuit breaker state, risk blocks, position values
- System: Resource usage, queue depth, connection states
- Blockchain: RPC latency, nonce usage, gas prices

Usage:
    from vel_prometheus_metrics import VELMetricsCollector, get_metrics_collector
    
    # Record a trade execution
    metrics = get_metrics_collector()
    metrics.record_execution(chain_id=1, success=True, latency_ms=150)
    
    # Get Prometheus metrics
    metrics.get_metrics()  # Returns Prometheus format text
"""

import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        Summary,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

logger = logging.getLogger("vel.metrics.prometheus")


# =============================================================================
# Metric Definitions
# =============================================================================

# Histogram buckets for latency measurements (in seconds)
LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)

# Histogram buckets for gas prices (in gwei)
GAS_BUCKETS = (1, 5, 10, 25, 50, 100, 200, 500, 1000, 2000, 5000)


@dataclass
class MetricState:
    """Internal state for fallback metrics when Prometheus is not available."""
    counters: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    gauges: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    histograms: Dict[str, List[float]] = field(default_factory=lambda: defaultdict(list))


class VELMetricsCollector:
    """
    Centralized metrics collector for the VEL trading platform.
    
    Provides Prometheus-compatible metrics with graceful fallback when
    prometheus_client is not available.
    """
    
    def __init__(self, namespace: str = "vel", subsystem: str = "trading"):
        """
        Initialize metrics collector.
        
        Args:
            namespace: Prometheus metric namespace
            subsystem: Prometheus metric subsystem
        """
        self.namespace = namespace
        self.subsystem = subsystem
        self._lock = threading.Lock()
        self._registry = CollectorRegistry() if PROMETHEUS_AVAILABLE else None
        self._fallback_state = MetricState() if not PROMETHEUS_AVAILABLE else None
        
        # Initialize all metrics
        self._init_metrics()
        
        logger.info(f"VEL Metrics Collector initialized (prometheus_client: {PROMETHEUS_AVAILABLE})")
    
    def _init_metrics(self):
        """Initialize all metrics."""
        if PROMETHEUS_AVAILABLE:
            self._init_prometheus_metrics()
        else:
            logger.warning("prometheus_client not available, using fallback metrics")
    
    def _init_prometheus_metrics(self):
        """Initialize Prometheus metrics."""
        # ─────────────────────────────────────────────────────────────────────
        # Trading Metrics
        # ─────────────────────────────────────────────────────────────────────
        
        # Intent counters
        self.intents_total = Counter(
            f"{self.namespace}_intents_total",
            "Total number of trading intents received",
            ["chain_id", "protocol", "signal_type"],
            registry=self._registry
        )
        
        self.intents_rejected = Counter(
            f"{self.namespace}_intents_rejected_total",
            "Total number of trading intents rejected",
            ["chain_id", "reason"],
            registry=self._registry
        )
        
        # Execution counters
        self.executions_total = Counter(
            f"{self.namespace}_executions_total",
            "Total number of trade executions",
            ["chain_id", "protocol", "status"],
            registry=self._registry
        )
        
        # Execution latency histogram
        self.execution_latency = Histogram(
            f"{self.namespace}_execution_latency_seconds",
            "Trade execution latency in seconds",
            ["chain_id", "protocol"],
            buckets=LATENCY_BUCKETS,
            registry=self._registry
        )
        
        # Trade value (in USD equivalent)
        self.trade_value_usd = Counter(
            f"{self.namespace}_trade_value_usd_total",
            "Total trade value in USD",
            ["chain_id", "direction"],
            registry=self._registry
        )
        
        # ─────────────────────────────────────────────────────────────────────
        # Risk Metrics
        # ─────────────────────────────────────────────────────────────────────
        
        # Circuit breaker state
        self.circuit_breaker_state = Gauge(
            f"{self.namespace}_circuit_breaker_state",
            "Circuit breaker state (0=closed, 1=open/halted)",
            ["scope"],
            registry=self._registry
        )
        
        # Risk blocks
        self.risk_blocks_total = Counter(
            f"{self.namespace}_risk_blocks_total",
            "Total number of trades blocked by risk engine",
            ["reason"],
            registry=self._registry
        )
        
        # Position value
        self.position_value_usd = Gauge(
            f"{self.namespace}_position_value_usd",
            "Current position value in USD",
            ["chain_id", "token"],
            registry=self._registry
        )
        
        # Daily PnL
        self.daily_pnl_usd = Gauge(
            f"{self.namespace}_daily_pnl_usd",
            "Daily profit/loss in USD",
            registry=self._registry
        )
        
        # Max daily loss limit
        self.daily_loss_limit_usd = Gauge(
            f"{self.namespace}_daily_loss_limit_usd",
            "Maximum daily loss limit in USD",
            registry=self._registry
        )
        
        # ─────────────────────────────────────────────────────────────────────
        # Blockchain Metrics
        # ─────────────────────────────────────────────────────────────────────
        
        # RPC latency
        self.rpc_latency = Histogram(
            f"{self.namespace}_rpc_latency_seconds",
            "Blockchain RPC call latency",
            ["chain_id", "method"],
            buckets=LATENCY_BUCKETS,
            registry=self._registry
        )
        
        # RPC errors
        self.rpc_errors_total = Counter(
            f"{self.namespace}_rpc_errors_total",
            "Total number of RPC errors",
            ["chain_id", "error_type"],
            registry=self._registry
        )
        
        # Gas price
        self.gas_price_gwei = Gauge(
            f"{self.namespace}_gas_price_gwei",
            "Current gas price in gwei",
            ["chain_id"],
            registry=self._registry
        )
        
        # Nonce
        self.current_nonce = Gauge(
            f"{self.namespace}_current_nonce",
            "Current nonce for wallet",
            ["chain_id", "wallet"],
            registry=self._registry
        )
        
        # Pending transactions
        self.pending_transactions = Gauge(
            f"{self.namespace}_pending_transactions",
            "Number of pending transactions",
            ["chain_id"],
            registry=self._registry
        )
        
        # ─────────────────────────────────────────────────────────────────────
        # System Metrics
        # ─────────────────────────────────────────────────────────────────────
        
        # Queue depth
        self.queue_depth = Gauge(
            f"{self.namespace}_queue_depth",
            "Number of items in queue",
            ["queue_name"],
            registry=self._registry
        )
        
        # Active connections
        self.active_connections = Gauge(
            f"{self.namespace}_active_connections",
            "Number of active connections",
            ["connection_type"],
            registry=self._registry
        )
        
        # Lock wait time
        self.lock_wait_time = Histogram(
            f"{self.namespace}_lock_wait_seconds",
            "Time spent waiting for distributed locks",
            ["lock_type"],
            buckets=LATENCY_BUCKETS,
            registry=self._registry
        )
        
        # Health check status
        self.health_check_status = Gauge(
            f"{self.namespace}_health_check_status",
            "Health check status (1=healthy, 0=unhealthy)",
            ["component"],
            registry=self._registry
        )
        
        # Uptime
        self._start_time = time.time()
        self.uptime_seconds = Gauge(
            f"{self.namespace}_uptime_seconds",
            "Service uptime in seconds",
            registry=self._registry
        )
        
        # App info
        self.app_info = Gauge(
            f"{self.namespace}_app_info",
            "Application information",
            ["version", "environment"],
            registry=self._registry
        )
        
        # Set initial values
        version = os.environ.get("VEL_VERSION", "1.0.0")
        environment = os.environ.get("VEL_ENVIRONMENT", "development")
        self.app_info.labels(version=version, environment=environment).set(1)
    
    # ─────────────────────────────────────────────────────────────────────────
    # Recording Methods
    # ─────────────────────────────────────────────────────────────────────────
    
    def record_intent(
        self,
        chain_id: int,
        protocol: str,
        signal_type: str = "swap"
    ):
        """Record a trading intent."""
        if PROMETHEUS_AVAILABLE:
            self.intents_total.labels(
                chain_id=str(chain_id),
                protocol=protocol,
                signal_type=signal_type
            ).inc()
        else:
            with self._lock:
                key = f"intents_total:{chain_id}:{protocol}:{signal_type}"
                self._fallback_state.counters[key] += 1
    
    def record_rejection(self, chain_id: int, reason: str):
        """Record a rejected intent."""
        if PROMETHEUS_AVAILABLE:
            self.intents_rejected.labels(
                chain_id=str(chain_id),
                reason=reason
            ).inc()
        else:
            with self._lock:
                key = f"intents_rejected:{chain_id}:{reason}"
                self._fallback_state.counters[key] += 1
    
    def record_execution(
        self,
        chain_id: int,
        protocol: str,
        success: bool,
        latency_seconds: float,
        value_usd: float = 0,
        direction: str = "buy"
    ):
        """Record a trade execution."""
        status = "success" if success else "failed"
        
        if PROMETHEUS_AVAILABLE:
            self.executions_total.labels(
                chain_id=str(chain_id),
                protocol=protocol,
                status=status
            ).inc()
            
            self.execution_latency.labels(
                chain_id=str(chain_id),
                protocol=protocol
            ).observe(latency_seconds)
            
            if value_usd > 0:
                self.trade_value_usd.labels(
                    chain_id=str(chain_id),
                    direction=direction
                ).inc(value_usd)
        else:
            with self._lock:
                self._fallback_state.counters[f"executions:{chain_id}:{status}"] += 1
                self._fallback_state.histograms[f"latency:{chain_id}"].append(latency_seconds)
    
    def record_risk_block(self, reason: str):
        """Record a risk-blocked trade."""
        if PROMETHEUS_AVAILABLE:
            self.risk_blocks_total.labels(reason=reason).inc()
        else:
            with self._lock:
                self._fallback_state.counters[f"risk_blocks:{reason}"] += 1
    
    def set_circuit_breaker_state(self, scope: str, is_open: bool):
        """Set circuit breaker state."""
        if PROMETHEUS_AVAILABLE:
            self.circuit_breaker_state.labels(scope=scope).set(1 if is_open else 0)
        else:
            with self._lock:
                self._fallback_state.gauges[f"circuit_breaker:{scope}"] = 1 if is_open else 0
    
    def set_daily_pnl(self, pnl_usd: float, limit_usd: float):
        """Set daily PnL metrics."""
        if PROMETHEUS_AVAILABLE:
            self.daily_pnl_usd.set(pnl_usd)
            self.daily_loss_limit_usd.set(limit_usd)
        else:
            with self._lock:
                self._fallback_state.gauges["daily_pnl_usd"] = pnl_usd
                self._fallback_state.gauges["daily_loss_limit_usd"] = limit_usd
    
    def record_rpc_call(
        self,
        chain_id: int,
        method: str,
        latency_seconds: float,
        error: Optional[str] = None
    ):
        """Record an RPC call."""
        if PROMETHEUS_AVAILABLE:
            self.rpc_latency.labels(
                chain_id=str(chain_id),
                method=method
            ).observe(latency_seconds)
            
            if error:
                self.rpc_errors_total.labels(
                    chain_id=str(chain_id),
                    error_type=error
                ).inc()
        else:
            with self._lock:
                self._fallback_state.histograms[f"rpc_latency:{chain_id}:{method}"].append(latency_seconds)
                if error:
                    self._fallback_state.counters[f"rpc_errors:{chain_id}:{error}"] += 1
    
    def set_gas_price(self, chain_id: int, gas_price_gwei: float):
        """Set current gas price."""
        if PROMETHEUS_AVAILABLE:
            self.gas_price_gwei.labels(chain_id=str(chain_id)).set(gas_price_gwei)
        else:
            with self._lock:
                self._fallback_state.gauges[f"gas_price:{chain_id}"] = gas_price_gwei
    
    def set_nonce(self, chain_id: int, wallet: str, nonce: int):
        """Set current nonce."""
        # Mask wallet address for security
        masked_wallet = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else wallet
        if PROMETHEUS_AVAILABLE:
            self.current_nonce.labels(
                chain_id=str(chain_id),
                wallet=masked_wallet
            ).set(nonce)
        else:
            with self._lock:
                self._fallback_state.gauges[f"nonce:{chain_id}:{masked_wallet}"] = nonce
    
    def set_pending_transactions(self, chain_id: int, count: int):
        """Set pending transaction count."""
        if PROMETHEUS_AVAILABLE:
            self.pending_transactions.labels(chain_id=str(chain_id)).set(count)
        else:
            with self._lock:
                self._fallback_state.gauges[f"pending_tx:{chain_id}"] = count
    
    def set_queue_depth(self, queue_name: str, depth: int):
        """Set queue depth."""
        if PROMETHEUS_AVAILABLE:
            self.queue_depth.labels(queue_name=queue_name).set(depth)
        else:
            with self._lock:
                self._fallback_state.gauges[f"queue_depth:{queue_name}"] = depth
    
    def set_health_status(self, component: str, is_healthy: bool):
        """Set health check status."""
        if PROMETHEUS_AVAILABLE:
            self.health_check_status.labels(component=component).set(1 if is_healthy else 0)
        else:
            with self._lock:
                self._fallback_state.gauges[f"health:{component}"] = 1 if is_healthy else 0
    
    def record_lock_wait(self, lock_type: str, wait_seconds: float):
        """Record lock wait time."""
        if PROMETHEUS_AVAILABLE:
            self.lock_wait_time.labels(lock_type=lock_type).observe(wait_seconds)
        else:
            with self._lock:
                self._fallback_state.histograms[f"lock_wait:{lock_type}"].append(wait_seconds)
    
    def get_metrics(self) -> bytes:
        """Get Prometheus-format metrics."""
        if PROMETHEUS_AVAILABLE:
            # Update uptime
            self.uptime_seconds.set(time.time() - self._start_time)
            return generate_latest(self._registry)
        else:
            # Return basic fallback metrics
            lines = []
            with self._lock:
                for key, value in self._fallback_state.counters.items():
                    lines.append(f"# TYPE {key.replace(':', '_')} counter")
                    lines.append(f"{key.replace(':', '_')} {value}")
                for key, value in self._fallback_state.gauges.items():
                    lines.append(f"# TYPE {key.replace(':', '_')} gauge")
                    lines.append(f"{key.replace(':', '_')} {value}")
            return "\n".join(lines).encode()
    
    def get_content_type(self) -> str:
        """Get Prometheus content type."""
        if PROMETHEUS_AVAILABLE:
            return CONTENT_TYPE_LATEST
        return "text/plain; charset=utf-8"


# =============================================================================
# Global Instance
# =============================================================================

_metrics_collector: Optional[VELMetricsCollector] = None
_metrics_lock = threading.Lock()


def get_metrics_collector() -> VELMetricsCollector:
    """Get global metrics collector instance."""
    global _metrics_collector
    if _metrics_collector is None:
        with _metrics_lock:
            if _metrics_collector is None:
                _metrics_collector = VELMetricsCollector()
    return _metrics_collector


def reset_metrics_collector():
    """Reset metrics collector (for testing)."""
    global _metrics_collector
    with _metrics_lock:
        _metrics_collector = None
