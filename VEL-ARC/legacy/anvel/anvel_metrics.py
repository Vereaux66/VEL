"""
ANVEL Metrics and Observability Module
Provides OpenTelemetry and Prometheus metrics integration
"""

import os
import sys
import time
from typing import Dict, Any, Optional
from functools import wraps
import logging

# Configure JSON logging
import json
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""

    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add custom fields if present
        if hasattr(record, "trade_id"):
            log_data["trade_id"] = record.trade_id
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms

        return json.dumps(log_data)


def setup_json_logging(logger_name: str = None) -> logging.Logger:
    """Setup JSON structured logging"""
    logger = logging.getLogger(logger_name or "anvel")

    # Only add handler if not already configured
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(os.getenv("ANVEL_LOG_LEVEL", "INFO"))

    return logger


# Prometheus metrics (optional - only if prometheus_client is installed)
try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        Info,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Create mock classes for when Prometheus is not available

    class MockMetric:
        def __init__(self, *args, **kwargs):
            pass

        def __call__(self, *args, **kwargs):
            return self

        def labels(self, **kwargs):
            return self

        def inc(self, amount=1):
            pass

        def observe(self, value):
            pass

        def set(self, value):
            pass

        def info(self, data):
            pass

    Counter = Histogram = Gauge = Info = MockMetric

    def generate_latest():
        return b""

    CONTENT_TYPE_LATEST = "text/plain"


class ANVELMetrics:
    """
    Centralized metrics collector for ANVEL system.
    Supports both Prometheus and OpenTelemetry backends.
    """

    def __init__(self, enable_prometheus: bool = None):
        self.logger = setup_json_logging("anvel.metrics")

        if enable_prometheus is None:
            enable_prometheus = (
                os.getenv("PROMETHEUS_ENABLED", "false").lower() == "true"
            )

        self.prometheus_enabled = enable_prometheus and PROMETHEUS_AVAILABLE

        if self.prometheus_enabled:
            self._init_prometheus_metrics()
            self.logger.info("Prometheus metrics initialized")
        else:
            self.logger.info("Prometheus metrics disabled or unavailable")

        # In-memory metrics for systems without Prometheus
        self.metrics_data = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_failed": 0,
            "trades_executed": 0,
            "trades_successful": 0,
            "trades_failed": 0,
            "active_positions": 0,
            "system_health": "healthy",
        }

    def _init_prometheus_metrics(self):
        """Initialize Prometheus metrics"""
        # HTTP metrics
        self.http_requests_total = Counter(
            "anvel_http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status"],
        )

        self.http_request_duration = Histogram(
            "anvel_http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
        )

        # Trading metrics
        self.trades_total = Counter(
            "anvel_trades_total",
            "Total trades executed",
            ["exchange", "pair", "side", "status"],
        )

        self.trade_pnl = Histogram(
            "anvel_trade_pnl_usd", "Trade profit/loss in USD", ["exchange", "pair"]
        )

        self.active_positions = Gauge(
            "anvel_active_positions", "Number of active positions", ["exchange"]
        )

        self.portfolio_value = Gauge(
            "anvel_portfolio_value_usd", "Total portfolio value in USD"
        )

        # System metrics
        self.system_health = Gauge(
            "anvel_system_health", "System health status (1=healthy, 0=unhealthy)"
        )

        self.ai_predictions = Counter(
            "anvel_ai_predictions_total",
            "Total AI predictions made",
            ["model", "outcome"],
        )

        self.database_operations = Counter(
            "anvel_database_operations_total",
            "Database operations",
            ["operation", "status"],
        )

        self.database_duration = Histogram(
            "anvel_database_operation_duration_seconds",
            "Database operation duration",
            ["operation"],
        )

        # Application info
        self.app_info = Info("anvel_application", "ANVEL application information")
        self.app_info.info(
            {
                "version": os.getenv("APP_VERSION", "2.0.0"),
                "environment": os.getenv("FLASK_ENV", "production"),
                "python_version": sys.version.split()[0],
            }
        )

    def record_http_request(
        self, method: str, endpoint: str, status: int, duration: float
    ):
        """Record HTTP request metrics"""
        self.metrics_data["requests_total"] += 1

        if status < 400:
            self.metrics_data["requests_success"] += 1
        else:
            self.metrics_data["requests_failed"] += 1

        if self.prometheus_enabled:
            self.http_requests_total.labels(
                method=method, endpoint=endpoint, status=str(status)
            ).inc()

            self.http_request_duration.labels(method=method, endpoint=endpoint).observe(
                duration
            )

        self.logger.info(
            f"HTTP {method} {endpoint} {status}",
            extra={"duration_ms": round(duration * 1000, 2)},
        )

    def record_trade(
        self, exchange: str, pair: str, side: str, status: str, pnl: float = None
    ):
        """Record trade execution metrics"""
        self.metrics_data["trades_executed"] += 1

        if status == "success":
            self.metrics_data["trades_successful"] += 1
        else:
            self.metrics_data["trades_failed"] += 1

        if self.prometheus_enabled:
            self.trades_total.labels(
                exchange=exchange, pair=pair, side=side, status=status
            ).inc()

            if pnl is not None:
                self.trade_pnl.labels(exchange=exchange, pair=pair).observe(pnl)

        log_data = {"exchange": exchange, "pair": pair, "side": side, "status": status}
        if pnl is not None:
            log_data["pnl_usd"] = pnl

        self.logger.info(f"Trade executed: {side} {pair} on {exchange}", extra=log_data)

    def update_active_positions(self, exchange: str, count: int):
        """Update active positions count"""
        self.metrics_data["active_positions"] = count

        if self.prometheus_enabled:
            self.active_positions.labels(exchange=exchange).set(count)

    def update_portfolio_value(self, value_usd: float):
        """Update portfolio value"""
        if self.prometheus_enabled:
            self.portfolio_value.set(value_usd)

    def update_system_health(self, healthy: bool):
        """Update system health status"""
        self.metrics_data["system_health"] = "healthy" if healthy else "unhealthy"

        if self.prometheus_enabled:
            self.system_health.set(1 if healthy else 0)

    def record_ai_prediction(self, model: str, outcome: str):
        """Record AI model prediction"""
        if self.prometheus_enabled:
            self.ai_predictions.labels(model=model, outcome=outcome).inc()

    def record_database_operation(self, operation: str, status: str, duration: float):
        """Record database operation metrics"""
        if self.prometheus_enabled:
            self.database_operations.labels(operation=operation, status=status).inc()

            self.database_duration.labels(operation=operation).observe(duration)

        self.logger.debug(
            f"Database {operation} {status}",
            extra={"duration_ms": round(duration * 1000, 2)},
        )

    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get current metrics summary"""
        return self.metrics_data.copy()

    def get_prometheus_metrics(self) -> tuple:
        """Get Prometheus metrics in exposition format"""
        if not self.prometheus_enabled:
            return (b"", "text/plain")

        return (generate_latest(), CONTENT_TYPE_LATEST)


# Global metrics instance
_metrics_instance: Optional[ANVELMetrics] = None


def get_metrics() -> ANVELMetrics:
    """Get or create global metrics instance"""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = ANVELMetrics()
    return _metrics_instance


def track_time(operation_name: str = None):
    """
    Decorator to track execution time of functions.
    Logs duration and records metrics.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            operation = operation_name or func.__name__
            logger = setup_json_logging(func.__module__)

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                logger.debug(
                    f"{operation} completed successfully",
                    extra={"duration_ms": round(duration * 1000, 2)},
                )

                return result
            except Exception as e:
                duration = time.time() - start_time
                logger.error(
                    f"{operation} failed: {str(e)}",
                    extra={"duration_ms": round(duration * 1000, 2)},
                    exc_info=True,
                )
                raise

        return wrapper

    return decorator


# Example usage and integration
if __name__ == "__main__":
    # Setup metrics
    metrics = get_metrics()

    # Simulate some activity
    metrics.record_http_request("GET", "/api/trades", 200, 0.045)
    metrics.record_http_request("POST", "/api/trades", 201, 0.123)
    metrics.record_trade("kraken", "BTC/USD", "buy", "success", 150.50)
    metrics.update_active_positions("kraken", 5)
    metrics.update_system_health(True)

    # Print summary
    print("Metrics Summary:")
    print(json.dumps(metrics.get_metrics_summary(), indent=2))

    # Example of tracked function
    @track_time("database_query")
    def example_db_query():
        time.sleep(0.1)
        return {"result": "data"}

    example_db_query()
