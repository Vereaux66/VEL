#!/usr/bin/env python3
"""Central logging configuration for ANVEL."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict

_DEFAULT_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_initialized = False


class JSONFormatter(logging.Formatter):
    """
    Structured JSON formatter for production logging.
    Better for log aggregation systems like ELK, Splunk, CloudWatch.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
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

        # Add extra fields from record
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "trade_id"):
            log_data["trade_id"] = record.trade_id
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id

        return json.dumps(log_data)


class StructuredLogAdapter(logging.LoggerAdapter):
    """
    Adapter to add structured context to log messages.
    Usage: logger.info("Trade executed", extra={"trade_id": 123, "symbol": "BTC/USD"})
    """

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        # Add default context
        if "extra" not in kwargs:
            kwargs["extra"] = {}

        # Add adapter context
        kwargs["extra"].update(self.extra)

        return msg, kwargs


class SafeRotatingFileHandler(RotatingFileHandler):
    """Rotating handler that recovers from Windows tell/seek errors."""

    def shouldRollover(self, record: logging.LogRecord) -> bool:
        try:
            return bool(super().shouldRollover(record))
        except OSError:
            self._reset_stream()
            try:
                return bool(super().shouldRollover(record))
            except OSError:
                return False

    def _reset_stream(self) -> None:
        try:
            self.close()
        except Exception:
            import logging as _lg  # noqa: E402
            _lg.getLogger("ANVEL_LOGGING").debug("Exception suppressed in _reset_stream")
        try:
            stream = self._open()
        except OSError:
            self.close()
        else:
            self.stream = stream


def _make_rotator(
    path: str,
    level: int,
    max_bytes: int,
    backups: int,
) -> SafeRotatingFileHandler:
    handler = SafeRotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backups,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    return handler


def init_logging(
    level: str = "INFO", log_dir: str = "logs", structured: bool = False
) -> logging.Logger:
    """
    Configure root logging once and return the ANVEL logger.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files
        structured: If True, use JSON structured logging for production

    Returns:
        Configured ANVEL logger
    """

    global _initialized
    if _initialized:
        return logging.getLogger("anvel")

    Path(log_dir).mkdir(exist_ok=True)

    logger = logging.getLogger()
    resolved_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(resolved_level)

    # Standard text logs
    logger.addHandler(
        _make_rotator(
            os.path.join(log_dir, "anvel.log"),
            resolved_level,
            max_bytes=5_000_000,
            backups=5,
        )
    )
    logger.addHandler(
        _make_rotator(
            os.path.join(log_dir, "anvel_debug.log"),
            logging.DEBUG,
            max_bytes=10_000_000,
            backups=3,
        )
    )

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(resolved_level)
    console.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    logger.addHandler(console)

    # Optional structured JSON logs for production
    if structured or os.getenv("ANVEL_STRUCTURED_LOGGING", "").lower() == "true":
        json_handler = SafeRotatingFileHandler(
            os.path.join(log_dir, "anvel_structured.json"),
            maxBytes=10_000_000,
            backupCount=10,
            encoding="utf-8",
        )
        json_handler.setLevel(resolved_level)
        json_handler.setFormatter(JSONFormatter())
        logger.addHandler(json_handler)

    _initialized = True
    ann_logger = logging.getLogger("anvel")
    ann_logger.info(
        "Logging initialized (level=%s, dir=%s, structured=%s)",
        level,
        log_dir,
        structured,
    )
    return ann_logger


def get_structured_logger(name: str, **context) -> StructuredLogAdapter:
    """
    Get a logger with structured context.

    Args:
        name: Logger name
        **context: Default context to add to all log messages

    Returns:
        StructuredLogAdapter with context

    Example:
        logger = get_structured_logger("trade_engine", component="execution")
        logger.info("Order executed", extra={"order_id": 123, "symbol": "BTC/USD"})
    """
    logger = logging.getLogger(name)
    return StructuredLogAdapter(logger, context)
