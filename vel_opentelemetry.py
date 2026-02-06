#!/usr/bin/env python3
"""
VEL OpenTelemetry Tracing
==========================

Production-grade distributed tracing with OpenTelemetry.

Features:
- Automatic trace context propagation
- Span instrumentation for key operations
- Integration with Jaeger, Zipkin, or AWS X-Ray
- Custom attributes for trading context
- Sampling strategies for high-volume systems

Usage:
    from vel_opentelemetry import init_tracing, trace_operation, get_tracer
    
    # Initialize tracing on startup
    init_tracing(service_name="vel-api")
    
    # Use decorator for automatic tracing
    @trace_operation(name="execute_trade")
    def execute_trade(intent):
        ...
    
    # Or manual spans
    tracer = get_tracer()
    with tracer.start_as_current_span("custom_operation") as span:
        span.set_attribute("chain_id", 1)
        ...
"""

import functools
import logging
import os
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("vel.tracing")

# Try to import OpenTelemetry
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.trace import Status, StatusCode
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    from opentelemetry.propagate import set_global_textmap, inject, extract
    
    # Exporters (conditional imports)
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    logger.warning("OpenTelemetry not available. Install with: pip install opentelemetry-api opentelemetry-sdk")


# =============================================================================
# Configuration
# =============================================================================

class TracingConfig:
    """Configuration for OpenTelemetry tracing."""
    
    def __init__(
        self,
        service_name: str = "vel-trading",
        environment: str = "development",
        exporter_type: str = "console",  # console, jaeger, zipkin, xray, otlp
        endpoint: Optional[str] = None,
        sample_rate: float = 1.0,
        enabled: bool = True
    ):
        self.service_name = service_name
        self.environment = environment
        self.exporter_type = exporter_type
        self.endpoint = endpoint
        self.sample_rate = sample_rate
        self.enabled = enabled
    
    @classmethod
    def from_env(cls) -> "TracingConfig":
        """Load configuration from environment variables."""
        return cls(
            service_name=os.environ.get("OTEL_SERVICE_NAME", "vel-trading"),
            environment=os.environ.get("VEL_ENVIRONMENT", "development"),
            exporter_type=os.environ.get("OTEL_EXPORTER_TYPE", "console"),
            endpoint=os.environ.get("OTEL_EXPORTER_ENDPOINT"),
            sample_rate=float(os.environ.get("OTEL_SAMPLE_RATE", "1.0")),
            enabled=os.environ.get("OTEL_ENABLED", "true").lower() == "true"
        )


# =============================================================================
# Tracer Initialization
# =============================================================================

_tracer_provider: Optional[Any] = None
_tracer: Optional[Any] = None
_config: Optional[TracingConfig] = None


def init_tracing(
    config: Optional[TracingConfig] = None,
    service_name: Optional[str] = None
) -> bool:
    """
    Initialize OpenTelemetry tracing.
    
    Args:
        config: Tracing configuration (or load from env)
        service_name: Override service name
        
    Returns:
        True if initialization succeeded
    """
    global _tracer_provider, _tracer, _config
    
    if not OTEL_AVAILABLE:
        logger.warning("OpenTelemetry not available, tracing disabled")
        return False
    
    _config = config or TracingConfig.from_env()
    
    if service_name:
        _config.service_name = service_name
    
    if not _config.enabled:
        logger.info("Tracing disabled by configuration")
        return False
    
    try:
        # Create resource with service info
        resource = Resource.create({
            SERVICE_NAME: _config.service_name,
            "service.environment": _config.environment,
            "service.version": os.environ.get("VEL_VERSION", "1.0.0"),
        })
        
        # Create tracer provider
        _tracer_provider = TracerProvider(resource=resource)
        
        # Configure exporter based on type
        exporter = _create_exporter(_config)
        if exporter:
            processor = BatchSpanProcessor(exporter)
            _tracer_provider.add_span_processor(processor)
        
        # Set as global provider
        trace.set_tracer_provider(_tracer_provider)
        
        # Set up context propagation
        set_global_textmap(TraceContextTextMapPropagator())
        
        # Get tracer instance
        _tracer = trace.get_tracer(_config.service_name)
        
        logger.info(
            f"OpenTelemetry tracing initialized: service={_config.service_name}, "
            f"exporter={_config.exporter_type}"
        )
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize tracing: {e}")
        return False


def _create_exporter(config: TracingConfig):
    """Create span exporter based on configuration."""
    try:
        if config.exporter_type == "console":
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            return ConsoleSpanExporter()
        
        elif config.exporter_type == "jaeger":
            from opentelemetry.exporter.jaeger.thrift import JaegerExporter
            return JaegerExporter(
                agent_host_name=config.endpoint or "localhost",
                agent_port=6831
            )
        
        elif config.exporter_type == "zipkin":
            from opentelemetry.exporter.zipkin.json import ZipkinExporter
            return ZipkinExporter(
                endpoint=config.endpoint or "http://localhost:9411/api/v2/spans"
            )
        
        elif config.exporter_type == "otlp":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            return OTLPSpanExporter(
                endpoint=config.endpoint or "http://localhost:4317"
            )
        
        elif config.exporter_type == "xray":
            # AWS X-Ray via OTLP
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            return OTLPSpanExporter(
                endpoint=config.endpoint or "http://localhost:4317"
            )
        
        else:
            logger.warning(f"Unknown exporter type: {config.exporter_type}")
            return None
            
    except ImportError as e:
        logger.warning(f"Exporter {config.exporter_type} not available: {e}")
        return None


def shutdown_tracing():
    """Shutdown tracing and flush pending spans."""
    global _tracer_provider
    
    if _tracer_provider:
        try:
            _tracer_provider.shutdown()
            logger.info("Tracing shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down tracing: {e}")


def get_tracer(name: Optional[str] = None):
    """
    Get tracer instance.
    
    Args:
        name: Optional tracer name (defaults to service name)
        
    Returns:
        Tracer instance or NoOpTracer if not initialized
    """
    if not OTEL_AVAILABLE:
        return _NoOpTracer()
    
    if _tracer is None:
        return trace.get_tracer(name or "vel-trading")
    
    if name and name != _config.service_name:
        return trace.get_tracer(name)
    
    return _tracer


# =============================================================================
# No-Op Tracer (when OpenTelemetry is not available)
# =============================================================================

class _NoOpSpan:
    """No-op span for when tracing is disabled."""
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass
    
    def set_attribute(self, key: str, value: Any) -> None:
        pass
    
    def set_status(self, status: Any) -> None:
        pass
    
    def record_exception(self, exception: Exception) -> None:
        pass
    
    def add_event(self, name: str, attributes: Optional[Dict] = None) -> None:
        pass


class _NoOpTracer:
    """No-op tracer for when OpenTelemetry is not available."""
    
    @contextmanager
    def start_as_current_span(self, name: str, **kwargs):
        yield _NoOpSpan()
    
    def start_span(self, name: str, **kwargs):
        return _NoOpSpan()


# =============================================================================
# Decorators and Context Managers
# =============================================================================

def trace_operation(
    name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
    record_exception: bool = True
):
    """
    Decorator to trace a function call.
    
    Args:
        name: Span name (defaults to function name)
        attributes: Static attributes to add to span
        record_exception: Whether to record exceptions
        
    Usage:
        @trace_operation(name="execute_trade", attributes={"component": "executor"})
        def execute_trade(intent):
            ...
    """
    def decorator(func: Callable) -> Callable:
        span_name = name or func.__name__
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                # Add static attributes
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                
                try:
                    result = func(*args, **kwargs)
                    if OTEL_AVAILABLE:
                        span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    if OTEL_AVAILABLE and record_exception:
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise
        
        return wrapper
    return decorator


@contextmanager
def trace_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None
):
    """
    Context manager for creating a traced span.
    
    Args:
        name: Span name
        attributes: Attributes to add to span
        
    Usage:
        with trace_span("database_query", {"db": "postgres"}) as span:
            span.set_attribute("query", "SELECT ...")
            result = db.execute(query)
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield span


# =============================================================================
# Trading-Specific Tracing Helpers
# =============================================================================

def trace_trade_intent(intent_id: str, chain_id: int, protocol: str):
    """Create a span for trade intent processing."""
    return trace_span(
        "trade.intent",
        {
            "vel.intent_id": intent_id,
            "vel.chain_id": chain_id,
            "vel.protocol": protocol,
            "vel.component": "intent_processor"
        }
    )


def trace_trade_execution(
    intent_id: str,
    chain_id: int,
    wallet: str,
    nonce: int
):
    """Create a span for trade execution."""
    # Mask wallet for security
    masked_wallet = f"{wallet[:6]}...{wallet[-4:]}" if len(wallet) > 10 else wallet
    
    return trace_span(
        "trade.execution",
        {
            "vel.intent_id": intent_id,
            "vel.chain_id": chain_id,
            "vel.wallet": masked_wallet,
            "vel.nonce": nonce,
            "vel.component": "executor"
        }
    )


def trace_blockchain_call(chain_id: int, method: str, rpc_url: str):
    """Create a span for blockchain RPC call."""
    # Mask RPC URL (may contain API keys)
    masked_url = rpc_url.split("?")[0] if "?" in rpc_url else rpc_url
    
    return trace_span(
        "blockchain.rpc",
        {
            "vel.chain_id": chain_id,
            "rpc.method": method,
            "rpc.service": masked_url,
            "vel.component": "rpc_client"
        }
    )


def trace_risk_check(intent_id: str, check_type: str):
    """Create a span for risk validation."""
    return trace_span(
        "risk.check",
        {
            "vel.intent_id": intent_id,
            "vel.check_type": check_type,
            "vel.component": "risk_kernel"
        }
    )


# =============================================================================
# Context Propagation Helpers
# =============================================================================

def inject_trace_context(headers: Dict[str, str]) -> Dict[str, str]:
    """
    Inject trace context into HTTP headers.
    
    Args:
        headers: Existing headers dict
        
    Returns:
        Headers with trace context injected
    """
    if not OTEL_AVAILABLE:
        return headers
    
    inject(headers)
    return headers


def extract_trace_context(headers: Dict[str, str]):
    """
    Extract trace context from HTTP headers.
    
    Args:
        headers: HTTP headers containing trace context
        
    Returns:
        Context object
    """
    if not OTEL_AVAILABLE:
        return None
    
    return extract(headers)


# =============================================================================
# Flask Integration
# =============================================================================

def init_flask_tracing(app):
    """
    Initialize tracing for Flask application.
    
    This adds automatic tracing for all HTTP requests.
    """
    if not OTEL_AVAILABLE:
        logger.warning("OpenTelemetry not available, Flask tracing disabled")
        return
    
    try:
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
        FlaskInstrumentor().instrument_app(app)
        logger.info("Flask tracing instrumentation enabled")
    except ImportError:
        logger.warning(
            "Flask instrumentation not available. "
            "Install with: pip install opentelemetry-instrumentation-flask"
        )


# =============================================================================
# Main (for testing)
# =============================================================================

if __name__ == "__main__":
    import time
    
    logging.basicConfig(level=logging.INFO)
    
    # Initialize tracing
    init_tracing(TracingConfig(
        service_name="vel-test",
        exporter_type="console",
        enabled=True
    ))
    
    # Test tracing
    @trace_operation(name="test_function")
    def test_function():
        time.sleep(0.1)
        return "success"
    
    # Run traced function
    result = test_function()
    print(f"Result: {result}")
    
    # Manual span
    with trace_span("manual_span", {"key": "value"}) as span:
        span.set_attribute("custom", "attribute")
        time.sleep(0.05)
    
    # Trade-specific
    with trace_trade_intent("intent_001", 1, "uniswap_v3"):
        time.sleep(0.05)
    
    # Shutdown
    shutdown_tracing()
