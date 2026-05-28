#!/usr/bin/env python3
"""Issue #10: Connection pool exhaustion monitoring and alerting.

Tracks pool utilization and alerts when approaching limits.
Helps diagnose database contention and connection leaks.
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Global connection tracker
_connection_stats = {
    'active_connections': 0,
    'peak_connections': 0,
    'connection_errors': 0,
    'last_exhaustion_alert': None,
    'max_pool_size': 100,
}
_stats_lock = threading.Lock()


def on_connect():
    """Record a connection from the pool."""
    with _stats_lock:
        _connection_stats['active_connections'] += 1
        if _connection_stats['active_connections'] > _connection_stats['peak_connections']:
            _connection_stats['peak_connections'] = _connection_stats['active_connections']

        # Alert if approaching pool exhaustion (>90% capacity)
        utilization_pct = (_connection_stats['active_connections'] / _connection_stats['max_pool_size'] * 100)
        if utilization_pct > 90:
            now = datetime.now()
            last_alert = _connection_stats.get('last_exhaustion_alert')
            # Only alert once per minute
            if not last_alert or (now - last_alert).seconds > 60:
                logger.critical(f"Issue #10: Connection pool exhaustion risk: {_connection_stats['active_connections']}/{_connection_stats['max_pool_size']} ({utilization_pct:.0f}%)")
                _connection_stats['last_exhaustion_alert'] = now


def on_disconnect():
    """Record a connection returned to the pool."""
    with _stats_lock:
        _connection_stats['active_connections'] = max(0, _connection_stats['active_connections'] - 1)


def record_connection_error():
    """Record a connection error for diagnostic purposes."""
    with _stats_lock:
        _connection_stats['connection_errors'] += 1
        logger.warning(f"Connection error recorded. Total errors: {_connection_stats['connection_errors']}")


def get_pool_stats() -> Dict:
    """Get current pool statistics."""
    with _stats_lock:
        return {
            'active': _connection_stats['active_connections'],
            'peak': _connection_stats['peak_connections'],
            'max': _connection_stats['max_pool_size'],
            'utilization_pct': (_connection_stats['active_connections'] / _connection_stats['max_pool_size'] * 100),
            'errors': _connection_stats['connection_errors'],
        }


def reset_stats():
    """Reset statistics (for testing or new deployment)."""
    with _stats_lock:
        _connection_stats['active_connections'] = 0
        _connection_stats['peak_connections'] = 0
        _connection_stats['connection_errors'] = 0
        _connection_stats['last_exhaustion_alert'] = None
