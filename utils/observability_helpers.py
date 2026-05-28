#!/usr/bin/env python3
"""Issues #43-47: Observability and operational improvements.

- Issue #43: Distributed tracing support (trace_id propagation)
- Issue #44: Data duplicate detection
- Issue #45: Audit log improvements
- Issue #46: RDS Proxy graceful degradation
- Issue #17: Transaction rollback audit
"""

import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Global trace context (thread-local in production)
_trace_context = {'trace_id': None}


def generate_trace_id() -> str:
    """Issue #43: Generate unique trace ID for request propagation across phases."""
    trace_id = str(uuid.uuid4())[:12]
    _trace_context['trace_id'] = trace_id
    return trace_id


def get_trace_id() -> str:
    """Get current trace ID or generate new one."""
    if not _trace_context.get('trace_id'):
        _trace_context['trace_id'] = generate_trace_id()
    return _trace_context['trace_id']


def log_with_trace(level: str, message: str, **kwargs):
    """Log message with trace ID for correlation across phases (Issue #43)."""
    trace_id = get_trace_id()
    prefix = f"[trace={trace_id}]"
    getattr(logger, level)(f"{prefix} {message}", **kwargs)


def detect_data_duplicates(conn, table: str, date: str, symbol: str, price: float) -> bool:
    """Issue #44: Detect duplicate rows by date+symbol+price.

    Returns: True if duplicate found, False otherwise
    """
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT COUNT(*) FROM {table}
            WHERE date = %s AND symbol = %s AND close_price = %s
        """, (date, symbol, price))
        count = cur.fetchone()[0] if cur.fetchone() else 0
        cur.close()

        if count > 1:
            logger.warning(f"Issue #44: Duplicate data detected in {table}: {symbol} on {date} @ {price}")
            return True
        return False
    except Exception as e:
        logger.debug(f"Duplicate detection failed for {table}: {e}")
        return False


def audit_log_component_breakdown(phase: int, component: str, score: float, passed: bool) -> None:
    """Issue #45: Store full component breakdown in audit logs for replay analysis."""
    try:
        trace_id = get_trace_id()
        logger.info({
            'event': 'component_evaluation',
            'phase': phase,
            'component': component,
            'score': score,
            'passed': passed,
            'trace_id': trace_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.debug(f"Could not log component breakdown: {e}")


def log_transaction_rollback(operation: str, error: str, symbol: Optional[str] = None) -> None:
    """Issue #17: Audit transaction rollbacks for data consistency investigation."""
    logger.warning({
        'event': 'transaction_rollback',
        'operation': operation,
        'error': error,
        'symbol': symbol,
        'trace_id': get_trace_id(),
        'timestamp': datetime.now(timezone.utc).isoformat(),
    })


def log_rds_proxy_fallback(reason: str) -> None:
    """Issue #46: Alert when RDS Proxy unavailable and falling back to direct RDS."""
    logger.critical({
        'event': 'rds_proxy_fallback',
        'reason': reason,
        'message': 'RDS Proxy unavailable, using direct connection (no connection pooling)',
        'trace_id': get_trace_id(),
        'timestamp': datetime.now(timezone.utc).isoformat(),
    })
