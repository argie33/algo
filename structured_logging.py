#!/usr/bin/env python3
"""
Structured Logging Module
Provides consistent, machine-readable logging across the platform.
Enables better debugging, monitoring, and alerting.
"""

import json
import logging
import sys
from datetime import datetime
from typing import Any, Dict, Optional


class StructuredLogger:
    """Logger that outputs structured JSON for CloudWatch."""

    def __init__(self, name: str, level: int = logging.INFO):
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        # JSON formatter for CloudWatch
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(handler)

    def _format_event(self, event_type: str, level: str, message: str, **kwargs) -> str:
        """Format log event as JSON for CloudWatch."""
        log_event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "logger": self.name,
            "level": level,
            "event_type": event_type,
            "message": message,
        }
        log_event.update(kwargs)
        return json.dumps(log_event, default=str)

    def data_loaded(self, table: str, count: int, source: str = "", duration_ms: float = 0):
        """Log successful data load."""
        self.logger.info(self._format_event(
            "DATA_LOADED",
            "INFO",
            f"Loaded {count} rows into {table}",
            table=table,
            row_count=count,
            source=source,
            duration_ms=duration_ms,
        ))

    def data_load_failed(self, table: str, error: str, rows_attempted: int = 0):
        """Log failed data load."""
        self.logger.error(self._format_event(
            "DATA_LOAD_FAILED",
            "ERROR",
            f"Failed to load {table}: {error}",
            table=table,
            error=error,
            rows_attempted=rows_attempted,
        ))

    def validation_failed(self, subject: str, reason: str, **context):
        """Log validation failure."""
        self.logger.warning(self._format_event(
            "VALIDATION_FAILED",
            "WARNING",
            f"Validation failed for {subject}: {reason}",
            subject=subject,
            reason=reason,
            context=context,
        ))

    def calculation_complete(self, calculation_type: str, symbol: str, result: Any, duration_ms: float = 0):
        """Log calculation completion."""
        self.logger.info(self._format_event(
            "CALCULATION_COMPLETE",
            "INFO",
            f"{calculation_type} calculated for {symbol}",
            calculation_type=calculation_type,
            symbol=symbol,
            duration_ms=duration_ms,
        ))

    def calculation_failed(self, calculation_type: str, symbol: str, error: str):
        """Log calculation failure."""
        self.logger.error(self._format_event(
            "CALCULATION_FAILED",
            "ERROR",
            f"{calculation_type} failed for {symbol}: {error}",
            calculation_type=calculation_type,
            symbol=symbol,
            error=error,
        ))

    def phase_start(self, phase_num: int, phase_name: str, context: Optional[Dict[str, Any]] = None):
        """Log orchestrator phase start."""
        self.logger.info(self._format_event(
            "PHASE_START",
            "INFO",
            f"Phase {phase_num} ({phase_name}) starting",
            phase=phase_num,
            phase_name=phase_name,
            context=context or {},
        ))

    def phase_complete(self, phase_num: int, phase_name: str, result: str = "SUCCESS", duration_ms: float = 0):
        """Log orchestrator phase completion."""
        level = "INFO" if result == "SUCCESS" else "WARNING"
        self.logger.info(self._format_event(
            "PHASE_COMPLETE",
            level,
            f"Phase {phase_num} ({phase_name}) {result}",
            phase=phase_num,
            phase_name=phase_name,
            result=result,
            duration_ms=duration_ms,
        ))

    def phase_failed(self, phase_num: int, phase_name: str, error: str, duration_ms: float = 0):
        """Log orchestrator phase failure."""
        self.logger.error(self._format_event(
            "PHASE_FAILED",
            "ERROR",
            f"Phase {phase_num} ({phase_name}) failed: {error}",
            phase=phase_num,
            phase_name=phase_name,
            error=error,
            duration_ms=duration_ms,
        ))

    def trade_executed(self, symbol: str, side: str, quantity: int, price: float, order_id: str = ""):
        """Log trade execution."""
        self.logger.info(self._format_event(
            "TRADE_EXECUTED",
            "INFO",
            f"Trade executed: {side} {quantity} {symbol} @ {price}",
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_id=order_id,
        ))

    def trade_rejected(self, symbol: str, reason: str, **context):
        """Log trade rejection."""
        self.logger.warning(self._format_event(
            "TRADE_REJECTED",
            "WARNING",
            f"Trade rejected for {symbol}: {reason}",
            symbol=symbol,
            reason=reason,
            context=context,
        ))

    def circuit_breaker_fired(self, breaker_name: str, condition: str, value: Any):
        """Log circuit breaker activation."""
        self.logger.warning(self._format_event(
            "CIRCUIT_BREAKER_FIRED",
            "WARNING",
            f"Circuit breaker '{breaker_name}' fired: {condition} = {value}",
            breaker=breaker_name,
            condition=condition,
            value=value,
        ))

    def data_quality_issue(self, table: str, issue_type: str, details: str, affected_count: int = 0):
        """Log data quality issue."""
        self.logger.warning(self._format_event(
            "DATA_QUALITY_ISSUE",
            "WARNING",
            f"Data quality issue in {table}: {issue_type}",
            table=table,
            issue_type=issue_type,
            details=details,
            affected_count=affected_count,
        ))

    def api_call(self, endpoint: str, method: str = "GET", status_code: int = 200, duration_ms: float = 0):
        """Log API call."""
        level = "INFO" if 200 <= status_code < 300 else "WARNING"
        self.logger.info(self._format_event(
            "API_CALL",
            level,
            f"{method} {endpoint} returned {status_code}",
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
        ))

    def api_error(self, endpoint: str, method: str, error: str, status_code: int = 500):
        """Log API error."""
        self.logger.error(self._format_event(
            "API_ERROR",
            "ERROR",
            f"{method} {endpoint} failed: {error}",
            endpoint=endpoint,
            method=method,
            error=error,
            status_code=status_code,
        ))


# Global logger instance
_logger: Optional[StructuredLogger] = None


def get_logger(name: str) -> StructuredLogger:
    """Get or create structured logger."""
    global _logger
    if _logger is None:
        _logger = StructuredLogger("algo-system")
    return StructuredLogger(name)


def log_data_loaded(table: str, count: int, **kwargs):
    """Convenience function to log data load."""
    get_logger("data-pipeline").data_loaded(table, count, **kwargs)


def log_calculation_complete(calc_type: str, symbol: str, **kwargs):
    """Convenience function to log calculation."""
    get_logger("calculations").calculation_complete(calc_type, symbol, **kwargs)


def log_trade_executed(symbol: str, side: str, quantity: int, price: float, **kwargs):
    """Convenience function to log trade."""
    get_logger("trading").trade_executed(symbol, side, quantity, price, **kwargs)


def log_phase_complete(phase_num: int, phase_name: str, **kwargs):
    """Convenience function to log phase."""
    get_logger("orchestrator").phase_complete(phase_num, phase_name, **kwargs)
