#!/usr/bin/env python3
"""
Connection pool monitoring and alerting.
Tracks database connection health and alerts when nearing capacity.
"""

import os
import logging
from datetime import datetime
from threading import Lock

logger = logging.getLogger('algo_connections')


class ConnectionMonitor:
    """Monitor database connection pool utilization and health."""

    def __init__(self, max_connections=None, alert_threshold_pct=80):
        """
        Initialize connection monitor.

        Args:
            max_connections: Max concurrent connections (default: PG_MAX_CONNECTIONS env var, or 100)
            alert_threshold_pct: Alert when utilization exceeds this % (default: 80)
        """
        self.max_connections = max_connections or int(os.getenv('PG_MAX_CONNECTIONS', '100'))
        self.alert_threshold_pct = alert_threshold_pct
        self.alert_threshold_count = int(self.max_connections * alert_threshold_pct / 100)

        self.active_connections = 0
        self._lock = Lock()

        # Logging
        self.logger = logging.getLogger('algo.connections')
        self.logger.setLevel(logging.WARNING)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def on_connect(self):
        """Call after psycopg2.connect() to register a new connection."""
        with self._lock:
            self.active_connections += 1
            if self.active_connections >= self.alert_threshold_count:
                utilization = 100 * self.active_connections // self.max_connections
                self.logger.warning(
                    f"ALERT: Connection pool at {utilization}% capacity "
                    f"({self.active_connections}/{self.max_connections} connections in use)"
                )

    def on_disconnect(self):
        """Call after connection close to unregister connection."""
        with self._lock:
            if self.active_connections > 0:
                self.active_connections -= 1

    def health_check(self):
        """
        Return current connection pool health status.

        Returns: {
            'timestamp': ISO 8601 datetime,
            'active_connections': int,
            'max_connections': int,
            'utilization_pct': int,
            'healthy': bool (True if below alert threshold),
            'alert': bool (True if at or above alert threshold)
        }
        """
        with self._lock:
            utilization_pct = 100 * self.active_connections // self.max_connections
            healthy = self.active_connections < self.alert_threshold_count

            return {
                'timestamp': datetime.now().isoformat(),
                'active_connections': self.active_connections,
                'max_connections': self.max_connections,
                'utilization_pct': utilization_pct,
                'healthy': healthy,
                'alert': not healthy,
            }

    def reset(self):
        """Reset connection counter (for testing or recovery)."""
        with self._lock:
            self.active_connections = 0


# Global monitor instance
_monitor = None


def get_monitor():
    """Get or create the global connection monitor."""
    global _monitor
    if _monitor is None:
        _monitor = ConnectionMonitor()
    return _monitor


def on_connect():
    """Register a new connection."""
    get_monitor().on_connect()


def on_disconnect():
    """Unregister a closed connection."""
    get_monitor().on_disconnect()


def health_check():
    """Get current connection pool health."""
    return get_monitor().health_check()


def reset():
    """Reset monitor (testing only)."""
    get_monitor().reset()
