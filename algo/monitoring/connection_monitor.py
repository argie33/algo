#!/usr/bin/env python3
"""
RDS connection pool monitoring and alerting.

Tracks active connections, alerts when approaching limits, and implements
basic connection timeout for stuck connections.
"""

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class ConnectionPoolMonitor:
    """Monitor RDS connection pool utilization and emit alerts."""

    def __init__(
        self,
        max_connections: int = 100,
        alert_threshold_pct: int = 70,
        timeout_sec: int = 300,
    ):
        """
        Args:
            max_connections: Maximum connections allowed (RDS Proxy = 100)
            alert_threshold_pct: Warn when usage > this percentage (default 70% for 100-conn proxy)
            timeout_sec: Timeout for stuck connections (default 5 min)

        CLUSTER 6 FIX: RDS Proxy has only 100 connections. With 6 tasks x 8 loaders x parallelism,
        we must alert aggressively. Thresholds: 70% (70 conn) warn, 85% (85 conn) critical.
        """
        self.max_connections = max_connections
        self.alert_threshold_pct = alert_threshold_pct
        self.timeout_sec = timeout_sec

        self._lock = threading.Lock()
        self._active_connections = 0
        self._connection_start_times: dict[int, float] = {}  # Connection ID → start time
        self._high_usage_warned = False
        self._last_report = time.time()
        self._report_interval = 60  # Report stats every 60s

    def on_connect(self) -> None:
        """Called when a connection is acquired."""
        with self._lock:
            self._active_connections += 1
            conn_id = id(threading.current_thread())
            self._connection_start_times[conn_id] = time.time()

            usage_pct = (self._active_connections / self.max_connections) * 100

            # Warn on threshold breach (once per threshold level)
            if usage_pct >= self.alert_threshold_pct and not self._high_usage_warned:
                logger.warning(
                    f"[RDS_POOL] ALERT: RDS Proxy connection usage {usage_pct:.0f}% "
                    f"({self._active_connections}/{self.max_connections}). "
                    "CLUSTER 6 FIX: Approaching pool limit. Check for stuck connections (>5min), "
                    "excessive loader parallelism, or long-running transactions. "
                    "See CLAUDE.md → Cluster 6 for mitigation."
                )
                self._high_usage_warned = True

            # Report every 60s if active
            now = time.time()
            if now - self._last_report >= self._report_interval:
                logger.info(
                    f"[RDS_POOL] Status: {self._active_connections}/{self.max_connections} connections "
                    f"({usage_pct:.0f}%)"
                )
                self._last_report = now

    def on_disconnect(self) -> None:
        """Called when a connection is released."""
        with self._lock:
            if self._active_connections > 0:
                self._active_connections -= 1
                conn_id = id(threading.current_thread())
                if conn_id in self._connection_start_times:
                    duration = time.time() - self._connection_start_times[conn_id]
                    del self._connection_start_times[conn_id]

                    # Log connections that held the pool for >30s (potential timeout candidates)
                    if duration > 30:
                        logger.debug(f"[RDS_POOL] Connection held for {duration:.0f}s (long duration)")

            usage_pct = (self._active_connections / self.max_connections) * 100
            if usage_pct < (self.alert_threshold_pct - 20):
                self._high_usage_warned = False  # Reset warning once usage drops back

    def get_status(self) -> dict[str, Any]:
        """Get current pool status."""
        with self._lock:
            usage_pct = (self._active_connections / self.max_connections) * 100
            stuck_connections = [
                (conn_id, time.time() - start_time)
                for conn_id, start_time in self._connection_start_times.items()
                if (time.time() - start_time) > self.timeout_sec
            ]
            return {
                "active_connections": self._active_connections,
                "max_connections": self.max_connections,
                "usage_pct": usage_pct,
                "stuck_connections_count": len(stuck_connections),
                "stuck_details": [
                    {"connection_id": cid, "duration_sec": int(duration)} for cid, duration in stuck_connections
                ],
            }

    def check_and_alert_stuck_connections(self) -> None:
        """Check for stuck connections and log alerts if found."""
        status = self.get_status()
        if status["stuck_connections_count"] > 0:
            logger.error(
                f"[RDS_POOL] ALERT: {status['stuck_connections_count']} stuck connections "
                f"held for >{self.timeout_sec}s. Pool usage {status['usage_pct']:.0f}%. "
                "Check for: infinite loops, deadlocks, network timeouts, or query hangs."
            )


# Global monitor instance
_monitor: ConnectionPoolMonitor | None = None
_monitor_lock = threading.Lock()


def get_monitor() -> ConnectionPoolMonitor:
    """Get or create the global connection monitor."""
    global _monitor
    if _monitor is None:
        with _monitor_lock:
            if _monitor is None:
                max_conns = 100  # RDS t4g.small default
                _monitor = ConnectionPoolMonitor(
                    max_connections=max_conns,
                    alert_threshold_pct=80,  # Warn at 80% usage
                    timeout_sec=300,  # 5-minute timeout for stuck connections
                )
    return _monitor


def on_connect() -> None:
    """Hook called when connection is acquired (from db_connection.py)."""
    get_monitor().on_connect()


def on_disconnect() -> None:
    """Hook called when connection is released (from db_connection.py)."""
    get_monitor().on_disconnect()


def get_pool_status() -> dict[str, Any]:
    """Get current RDS pool status (for monitoring/debugging)."""
    return get_monitor().get_status()


def check_stuck_connections() -> None:
    """Check for and alert on stuck connections."""
    get_monitor().check_and_alert_stuck_connections()
