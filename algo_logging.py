#!/usr/bin/env python3
"""
Structured JSON logging for the algo platform.

Usage:
    from algo_logging import get_logger
    logger = get_logger(__name__)
    logger.info("trade.executed", symbol="AAPL", qty=100, price=195.50)

Every log record becomes a CloudWatch-queryable JSON object:
    {"ts": "...", "level": "INFO", "service": "algo_orchestrator",
     "msg": "trade.executed", "symbol": "AAPL", "qty": 100, "price": 195.50}

CloudWatch Insights query examples:
    filter msg = "trade.executed" | stats count() by symbol
    filter level = "ERROR" | sort ts desc | limit 20
"""

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        log: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "service": record.name,
            "msg": record.getMessage(),
        }

        # Merge any extra kwargs passed via logger.info("msg", extra={...})
        for key, val in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                log[key] = val

        if record.exc_info:
            log["exc"] = traceback.format_exception(*record.exc_info)

        return json.dumps(log, default=str)


_STANDARD_ATTRS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
})


def get_logger(name: str, level: str | None = None) -> logging.Logger:
    """
    Return a logger that emits structured JSON to stdout.
    Safe to call multiple times — returns the same logger instance.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    log_level = level or os.getenv("LOG_LEVEL", "INFO")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False

    return logger


def configure_root_logger(level: str = "INFO") -> None:
    """
    Configure the root logger with JSON formatting.
    Call once at application startup (orchestrator __main__).
    """
    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
