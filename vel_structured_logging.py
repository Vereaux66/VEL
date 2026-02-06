#!/usr/bin/env python3
"""
VEL Structured Logging Configuration
=====================================

Production-grade structured logging with:
- JSON format for log aggregation (ELK, CloudWatch, etc.)
- Trace ID propagation for distributed tracing
- Request context injection
- Log level management
- Async logging for performance
- Security: sensitive data masking

Usage:
    from vel_structured_logging import configure_logging, get_logger, set_trace_id
    
    configure_logging()
    logger = get_logger(__name__)
    
    with set_trace_id("abc123"):
        logger.info("Processing request", extra={"user_id": 123})
"""

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from queue import Queue
from typing import Any, Optional
import re

# Context variables for request tracing
trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
span_id_var: ContextVar[Optional[str]] = ContextVar("span_id", default=None)
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)


# =============================================================================
# Sensitive Data Patterns
# =============================================================================

# Patterns for sensitive data that should be masked
SENSITIVE_PATTERNS = [
    (re.compile(r'(password["\']?\s*[:=]\s*["\']?)([^"\']+)(["\']?)', re.IGNORECASE), r'\1***MASKED***\3'),
    (re.compile(r'(api_?key["\']?\s*[:=]\s*["\']?)([^"\']+)(["\']?)', re.IGNORECASE), r'\1***MASKED***\3'),
    (re.compile(r'(secret["\']?\s*[:=]\s*["\']?)([^"\']+)(["\']?)', re.IGNORECASE), r'\1***MASKED***\3'),
    (re.compile(r'(private_?key["\']?\s*[:=]\s*["\']?)([^"\']+)(["\']?)', re.IGNORECASE), r'\1***MASKED***\3'),
    (re.compile(r'(token["\']?\s*[:=]\s*["\']?)([^"\']{10,})(["\']?)', re.IGNORECASE), r'\1***MASKED***\3'),
    (re.compile(r'(bearer\s+)([a-zA-Z0-9_-]+)', re.IGNORECASE), r'\1***MASKED***'),
    # Wallet addresses - keep first/last 4 chars
    (re.compile(r'(0x[a-fA-F0-9]{8})[a-fA-F0-9]{32}([a-fA-F0-9]{4})'), r'\1...\2'),
]


def mask_sensitive_data(text: str) -> str:
    """Mask sensitive data in log messages."""
    if not isinstance(text, str):
        return text
    
    for pattern, replacement in SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    
    return text


# =============================================================================
# JSON Formatter
# =============================================================================

class VELJSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.
    
    Output format:
    {
        "timestamp": "2024-01-01T00:00:00.000Z",
        "level": "INFO",
        "logger": "vel.trading",
        "message": "Trade executed",
        "trace_id": "abc123",
        "span_id": "def456",
        "request_id": "req789",
        "user_id": "user123",
        "service": "vel-trading",
        "environment": "production",
        "extra": {...}
    }
    """
    
    def __init__(
        self,
        service_name: str = "vel-trading",
        environment: str = "development",
        include_stacktrace: bool = True,
        mask_sensitive: bool = True
    ):
        super().__init__()
        self.service_name = service_name
        self.environment = environment
        self.include_stacktrace = include_stacktrace
        self.mask_sensitive = mask_sensitive
        
        # Fields to exclude from extra
        self.reserved_attrs = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "pathname", "process", "processName", "relativeCreated",
            "stack_info", "exc_info", "exc_text", "thread", "threadName",
            "taskName", "message"
        }
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Base log entry
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self._mask(record.getMessage()),
            "service": self.service_name,
            "environment": self.environment,
        }
        
        # Add context variables
        if trace_id := trace_id_var.get():
            log_entry["trace_id"] = trace_id
        if span_id := span_id_var.get():
            log_entry["span_id"] = span_id
        if request_id := request_id_var.get():
            log_entry["request_id"] = request_id
        if user_id := user_id_var.get():
            log_entry["user_id"] = user_id
        
        # Add source location
        log_entry["source"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName
        }
        
        # Add extra fields
        extra = {}
        for key, value in record.__dict__.items():
            if key not in self.reserved_attrs and not key.startswith("_"):
                try:
                    # Try to serialize
                    json.dumps(value)
                    extra[key] = self._mask_value(value)
                except (TypeError, ValueError):
                    extra[key] = str(value)
        
        if extra:
            log_entry["extra"] = extra
        
        # Add exception info
        if record.exc_info and self.include_stacktrace:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "stacktrace": self._mask(self.formatException(record.exc_info))
            }
        
        return json.dumps(log_entry, default=str, ensure_ascii=False)
    
    def _mask(self, text: str) -> str:
        """Mask sensitive data if enabled."""
        if self.mask_sensitive:
            return mask_sensitive_data(text)
        return text
    
    def _mask_value(self, value: Any) -> Any:
        """Mask sensitive data in values."""
        if isinstance(value, str):
            return self._mask(value)
        if isinstance(value, dict):
            return {k: self._mask_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._mask_value(item) for item in value]
        return value


# =============================================================================
# Console Formatter (Development)
# =============================================================================

class VELConsoleFormatter(logging.Formatter):
    """
    Colored console formatter for development.
    """
    
    COLORS = {
        "DEBUG": "\033[36m",    # Cyan
        "INFO": "\033[32m",     # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",    # Red
        "CRITICAL": "\033[35m", # Magenta
    }
    RESET = "\033[0m"
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        
        # Add trace ID if present
        trace_id = trace_id_var.get()
        trace_str = f" [{trace_id[:8]}]" if trace_id else ""
        
        message = record.getMessage()
        
        formatted = (
            f"{color}{record.levelname:8}{self.RESET} "
            f"{record.name:30}{trace_str} "
            f"{message}"
        )
        
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)
        
        return formatted


# =============================================================================
# Context Managers
# =============================================================================

class TraceContext:
    """Context manager for trace ID propagation."""
    
    def __init__(self, trace_id: Optional[str] = None, span_id: Optional[str] = None):
        self.trace_id = trace_id or str(uuid.uuid4())
        self.span_id = span_id or str(uuid.uuid4())[:8]
        self._trace_token = None
        self._span_token = None
    
    def __enter__(self):
        self._trace_token = trace_id_var.set(self.trace_id)
        self._span_token = span_id_var.set(self.span_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._trace_token is not None:
            trace_id_var.reset(self._trace_token)
        if self._span_token is not None:
            span_id_var.reset(self._span_token)
        return False


class RequestContext:
    """Context manager for request context."""
    
    def __init__(
        self,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        trace_id: Optional[str] = None
    ):
        self.request_id = request_id or str(uuid.uuid4())
        self.user_id = user_id
        self.trace_id = trace_id or str(uuid.uuid4())
        self._request_token = None
        self._trace_token = None
        self._user_token = None
    
    def __enter__(self):
        self._request_token = request_id_var.set(self.request_id)
        self._trace_token = trace_id_var.set(self.trace_id)
        if self.user_id:
            self._user_token = user_id_var.set(self.user_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._request_token is not None:
            request_id_var.reset(self._request_token)
        if self._trace_token is not None:
            trace_id_var.reset(self._trace_token)
        if self._user_token is not None:
            user_id_var.reset(self._user_token)
        return False


def set_trace_id(trace_id: str):
    """Convenience function to set trace ID."""
    return TraceContext(trace_id=trace_id)


def set_request_context(request_id: str = None, user_id: str = None, trace_id: str = None):
    """Convenience function to set request context."""
    return RequestContext(request_id=request_id, user_id=user_id, trace_id=trace_id)


# =============================================================================
# Configuration
# =============================================================================

_logging_configured = False
_queue_listener: Optional[QueueListener] = None


def configure_logging(
    level: str = None,
    json_format: bool = None,
    service_name: str = "vel-trading",
    log_file: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
):
    """
    Configure structured logging for VEL.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: If True, use JSON format; if False, use console format.
                    Defaults to True in production, False otherwise.
        service_name: Service name for log entries
        log_file: Optional file path for logging
        max_bytes: Max size of log file before rotation
        backup_count: Number of backup files to keep
    """
    global _logging_configured, _queue_listener
    
    if _logging_configured:
        return
    
    # Determine settings from environment
    environment = os.environ.get("VEL_ENVIRONMENT", "development")
    if level is None:
        level = os.environ.get("VEL_LOG_LEVEL", "INFO" if environment == "production" else "DEBUG")
    if json_format is None:
        json_format = environment == "production" or os.environ.get("VEL_LOG_JSON", "").lower() == "true"
    
    # Create handlers
    handlers = []
    
    # Create formatter
    if json_format:
        formatter = VELJSONFormatter(
            service_name=service_name,
            environment=environment,
            include_stacktrace=True,
            mask_sensitive=True
        )
    else:
        formatter = VELConsoleFormatter()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)
    
    # File handler (if specified)
    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setFormatter(VELJSONFormatter(
            service_name=service_name,
            environment=environment
        ))
        handlers.append(file_handler)
    
    # Use async logging for better performance
    # Bounded queue to prevent memory exhaustion under load spikes
    # If queue is full, log records will be dropped (backpressure behavior)
    max_queue_size = int(os.environ.get("VEL_LOG_QUEUE_SIZE", "10000"))
    log_queue = Queue(max_queue_size)
    queue_handler = QueueHandler(log_queue)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    root_logger.addHandler(queue_handler)
    
    # Start queue listener
    _queue_listener = QueueListener(log_queue, *handlers, respect_handler_level=True)
    _queue_listener.start()
    
    # Configure third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("gunicorn").setLevel(logging.INFO)
    
    _logging_configured = True
    
    logger = logging.getLogger("vel.logging")
    logger.info(
        "Structured logging configured",
        extra={
            "level": level,
            "format": "json" if json_format else "console",
            "environment": environment,
            "service": service_name
        }
    )


def shutdown_logging():
    """Shutdown logging (flush and close handlers)."""
    global _queue_listener
    if _queue_listener:
        _queue_listener.stop()
        _queue_listener = None


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)


# =============================================================================
# Flask Integration
# =============================================================================

def init_flask_logging(app):
    """
    Initialize logging for Flask application.
    
    Adds request context to all logs within request scope.
    """
    from flask import g, request
    
    @app.before_request
    def before_request():
        # Get or generate trace ID
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        
        # Store in request context
        g.trace_id = trace_id
        g.request_id = request_id
        g.request_start_time = time.time()
        
        # Set context variables and store tokens for cleanup
        g._trace_id_token = trace_id_var.set(trace_id)
        g._request_id_token = request_id_var.set(request_id)
        
        # Log request
        logger = get_logger("vel.http")
        logger.info(
            f"Request started: {request.method} {request.path}",
            extra={
                "http_method": request.method,
                "http_path": request.path,
                "http_query": request.query_string.decode(),
                "remote_addr": request.remote_addr,
                "user_agent": request.headers.get("User-Agent", "")[:100]
            }
        )
    
    @app.after_request
    def after_request(response):
        # Add trace ID to response headers
        if hasattr(g, "trace_id"):
            response.headers["X-Trace-ID"] = g.trace_id
        if hasattr(g, "request_id"):
            response.headers["X-Request-ID"] = g.request_id
        
        # Log response
        duration_ms = (time.time() - g.request_start_time) * 1000 if hasattr(g, "request_start_time") else 0
        
        logger = get_logger("vel.http")
        logger.info(
            f"Request completed: {request.method} {request.path} -> {response.status_code}",
            extra={
                "http_method": request.method,
                "http_path": request.path,
                "http_status": response.status_code,
                "duration_ms": round(duration_ms, 2)
            }
        )
        
        return response
    
    @app.teardown_request
    def teardown_request(exception=None):
        # Reset context variables to prevent leaking IDs to subsequent requests
        # in workers that reuse threads/greenlets
        if hasattr(g, "_trace_id_token"):
            trace_id_var.reset(g._trace_id_token)
        if hasattr(g, "_request_id_token"):
            request_id_var.reset(g._request_id_token)
    
    return app
