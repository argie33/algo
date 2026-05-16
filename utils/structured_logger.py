#!/usr/bin/env python3
"""
Structured Logging - JSON output with trace IDs

All logs are JSON. Easy to query in CloudWatch Insights.

Example:
    logger = get_logger(__name__)
    logger.info("Trade executed", extra={
        "symbol": "AAPL",
        "price": 150.0,
        "shares": 100,
    })

Output (JSON):
    {
      "timestamp": "2026-05-09T15:30:45.123Z",
      "level": "INFO",
      "logger": "algo_trade_executor",
      "message": "Trade executed",
      "trace_id": "RUN-2026-05-09-153045-abc123",
      "symbol": "AAPL",
      "price": 150.0,
      "shares": 100
    }

CloudWatch Insights queries:
    fields @timestamp, symbol, price, message
    | filter symbol = "AAPL"
    | filter @timestamp > "2026-05-09T10:00:00Z"

    fields @timestamp, message, @message
    | filter trace_id = "RUN-2026-05-09-153045-abc123"
    | sort @timestamp asc
"""

import json
import logging
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

# Global trace ID (set once at orchestrator start)
_trace_id: Optional[str] = None


def set_trace_id(trace_id: str) -> None:
    """Set the global trace ID for this run. Called by orchestrator at startup."""
    global _trace_id
    _trace_id = trace_id


def get_trace_id() -> str:
    """Get current trace ID, or generate one."""
    global _trace_id
    if _trace_id is None:
        _trace_id = f"TRACE-{uuid.uuid4().hex[:8]}"
    return _trace_id


class StructuredFormatter(logging.Formatter):
    """Custom JSON formatter - no external dependencies."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Build JSON log entry
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": get_trace_id(),
            "caller": f"{record.filename}:{record.lineno}",
        }

        # Merge in extra fields from the record
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                # Skip internal logging fields
                if not key.startswith('_') and key not in [
                    'name', 'msg', 'args', 'created', 'filename', 'funcName',
                    'levelname', 'levelno', 'lineno', 'module', 'msecs',
                    'message', 'pathname', 'process', 'processName', 'relativeCreated',
                    'thread', 'threadName', 'exc_info', 'exc_text', 'stack_info',
                    'getMessage',
                ]:
                    log_entry[key] = value

        return json.dumps(log_entry, default=str)


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Get a structured logger."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    logger.handlers = []

    # Add structured handler (JSON to stdout)
    handler = logging.StreamHandler(sys.stdout)
    formatter = StructuredFormatter()
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


# Convenience: get logger for main orchestrator
orchestrator_logger = get_logger('algo_orchestrator')


if __name__ == "__main__":
    # Test: show what logs look like
    set_trace_id("RUN-2026-05-09-153045-test123")

    logger = get_logger("test_module")

    logger.info("Simple message")
    logger.info("Trade executed", extra={
        "symbol": "AAPL",
        "price": 150.0,
        "shares": 100,
    })
    logger.warning("Low volume", extra={
        "symbol": "MSFT",
        "volume": 100000,
        "expected_volume": 50000000,
    })
    logger.error("Failed to fetch data", extra={
        "source": "yfinance",
        "error": "Rate limit exceeded",
    })

    print("\n^ All logs are JSON. Paste into CloudWatch Insights.")
