#!/usr/bin/env python3
"""Connection pool health monitoring - provides get_pool_health() for Phase 3."""

from utils.db.pool_monitor import RDSPoolMonitor


def get_pool_health() -> dict[str, int]:
    """Get current connection pool health status.

    Returns:
        dict with keys:
        - available_conns: Number of connections available
        - size: Maximum pool size
        - status: 'HEALTHY', 'WARNING', or 'CRITICAL'

    Used by Phase 3 to detect connection exhaustion before it causes cascade failures.
    """
    monitor = RDSPoolMonitor()
    status = monitor.get_connection_pool_status()

    # Handle error case
    if "_error" in status:
        # Return degraded status - assume pool is exhausted if we can't query it
        return {
            "available_conns": 0,
            "size": 100,
            "status": "CRITICAL",
            "_error": status.get("_error"),
        }

    return {
        "available_conns": status.get("available_connections", 0),
        "size": status.get("max_connections", 100),
        "status": status.get("status", "UNKNOWN"),
    }
