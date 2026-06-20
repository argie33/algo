#!/usr/bin/env python3
"""RDS Connection Pool Monitoring — Critical for preventing exhaustion during EOD pipeline.

Monitors connection pool saturation during high-load periods:
- Morning prep (2:45-9:30 AM): expect <30 connections
- EOD pipeline (4:05-5:30 PM): expect 20-30 RDS connections (well below 100 max)
- Alert threshold: >80% of max (>80 connections)
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict


# Inlined from algo.infrastructure.constants — avoids importing the algo package
# at module load time, which is not available in the API Lambda runtime.
DB_MAX_CONNECTIONS = 100  # db.t4g.small safety threshold
DB_POOL_ALERT_THRESHOLD_PCT = 80  # Alert when pool usage > 80%
DB_POOL_TIMEOUT_SEC = 300

logger = logging.getLogger(__name__)


class RDSPoolMonitor:
    """Monitor PostgreSQL RDS connection pool saturation."""

    MAX_CONNECTIONS = DB_MAX_CONNECTIONS
    ALERT_THRESHOLD_PCT = DB_POOL_ALERT_THRESHOLD_PCT
    CRITICAL_THRESHOLD_PCT = 90  # Critical if >90% full (configurable via constants)

    def __init__(self):
        self.region = os.getenv("AWS_REGION", "us-east-1")

    def get_connection_pool_status(self) -> Dict[str, Any]:
        """Query RDS for current connection pool usage.

        Returns:
            {
                'active_connections': int,
                'max_connections': int,
                'utilization_percent': float,
                'status': 'HEALTHY' | 'WARNING' | 'CRITICAL',
                'available_connections': int,
                'timestamp': datetime
            }
        """
        try:
            from utils.db import DatabaseContext

            with DatabaseContext("read") as cur:
                cur.execute("""
                    SELECT
                        (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) as active_connections,
                        current_setting('max_connections')::int as max_connections
                """)

                row = cur.fetchone()
                if not row:
                    return {
                        "_error": "Failed to query connection status",
                        "timestamp": datetime.now().isoformat(),
                    }

                active = row[0] or 0
                max_conn = row[1] or 100

                utilization_pct = (active / max_conn) * 100 if max_conn > 0 else 0

                if utilization_pct >= self.CRITICAL_THRESHOLD_PCT:
                    status = "CRITICAL"
                elif utilization_pct >= self.ALERT_THRESHOLD_PCT:
                    status = "WARNING"
                else:
                    status = "HEALTHY"

                return {
                    "active_connections": active,
                    "max_connections": max_conn,
                    "utilization_percent": round(utilization_pct, 1),
                    "status": status,
                    "available_connections": max_conn - active,
                    "timestamp": datetime.now().isoformat(),
                }

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Failed to get RDS pool status: {e}")
            return {"_error": str(e), "timestamp": datetime.now().isoformat()}

    def get_slow_queries(self, min_duration_sec: float = 5.0) -> list:
        """Identify slow-running queries that might be holding connections.

        Args:
            min_duration_sec: Only return queries running longer than this

        Returns:
            [
                {
                    'pid': 12345,
                    'user': 'algo_app',
                    'query': 'SELECT ...',
                    'duration_sec': 45.3,
                    'state': 'active' | 'idle in transaction'
                },
                ...
            ]
        """
        try:
            from utils.db import DatabaseContext

            with DatabaseContext("read") as cur:
                cur.execute("""
                    SELECT
                        pid,
                        usename,
                        query,
                        EXTRACT(EPOCH FROM (NOW() - query_start)) as duration_sec,
                        state
                    FROM pg_stat_activity
                    WHERE query_start IS NOT NULL
                    AND EXTRACT(EPOCH FROM (NOW() - query_start)) > {min_duration_sec}
                    AND pid <> pg_backend_pid()
                    ORDER BY query_start ASC
                """)

                slow_queries = []
                for row in cur.fetchall():
                    slow_queries.append(
                        {
                            "pid": row[0],
                            "user": row[1],
                            "query": row[2][:100],  # Truncate long queries
                            "duration_sec": round(float(row[3]), 1) if row[3] else 0,
                            "state": row[4],
                        }
                    )

                return slow_queries

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"Failed to query slow queries: {e}")
            raise

    def get_connection_by_state(self) -> Dict[str, int]:
        """Get breakdown of connections by state.

        Returns:
            {
                'active': 5,
                'idle': 12,
                'idle_in_transaction': 2,
                'fastpath_function_call': 0,
                'other': 1
            }
        """
        try:
            from utils.db import DatabaseContext

            with DatabaseContext("read") as cur:
                cur.execute("""
                    SELECT state, COUNT(*) as count
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                    GROUP BY state
                    ORDER BY count DESC
                """)

                states = {}
                for row in cur.fetchall():
                    state_name = row[0] or "other"
                    states[state_name] = row[1]

                return states

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"Failed to get connection breakdown: {e}")
            raise

    def log_pool_status(self):
        """Log current connection pool status with details."""
        status = self.get_connection_pool_status()

        if "_error" in status:
            logger.error(f"[RDS-POOL] Error: {status['_error']}")
            return

        emoji = {
            "HEALTHY": "🟢",
            "WARNING": "🟡",
            "CRITICAL": "🔴",
        }.get(status["status"], "❓")

        logger.info(
            f"[RDS-POOL] {emoji} {status['status']} - "
            f"{status['active_connections']}/{status['max_connections']} connections "
            f"({status['utilization_percent']:.0f}%)"
        )

        if status["status"] != "HEALTHY":
            # Log additional details for warning/critical
            try:
                states = self.get_connection_by_state()
                logger.warning(f"[RDS-POOL] Connection breakdown: {states}")
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"[RDS-POOL] Failed to get connection breakdown: {e}")

            try:
                slow = self.get_slow_queries()
                if slow:
                    logger.warning(f"[RDS-POOL] {len(slow)} slow queries (>5s):")
                    for q in slow[:3]:  # Show top 3
                        logger.warning(
                            f"  - PID {q['pid']} ({q['duration_sec']:.0f}s): {q['query']}"
                        )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"[RDS-POOL] Failed to query slow queries: {e}")

    def check_eod_readiness(self) -> Dict[str, Any]:
        """Check if RDS is ready for EOD pipeline (4:05 PM).

        Returns:
            {
                'ready_for_eod': bool,
                'pool_status': 'HEALTHY' | 'WARNING' | 'CRITICAL',
                'active_connections': int,
                'max_parallelism': int,  # Recommended max parallel loaders
                'recommendations': [str]
            }
        """
        status = self.get_connection_pool_status()

        if "_error" in status:
            return {
                "ready_for_eod": False,
                "_error": status["_error"],
                "recommendations": [
                    "Cannot check pool status - RDS may be unavailable"
                ],
            }

        pool_pct = status["utilization_percent"]
        available = status["available_connections"]

        recommendations = []

        # EOD pipeline runs ~6 loaders in parallel (stock_prices, technical_data, swing_scores, market_health, etc.)
        # Each loader may use 2-4 connections
        # Safe estimate: need 20-30 available connections
        if available < 20:
            recommendations.append(
                f"Only {available} connections available - reduce parallelism or wait for idle connections"
            )

        if pool_pct > DB_POOL_ALERT_THRESHOLD_PCT:
            recommendations.append(
                f"Pool >{DB_POOL_ALERT_THRESHOLD_PCT}% utilized - monitor closely during EOD, may need to reduce loader parallelism"
            )

        ready = available >= 20 and pool_pct <= DB_POOL_ALERT_THRESHOLD_PCT

        # Estimate max safe parallelism
        # Conservative: reserve 30 connections for running loaders, use rest for system
        max_parallelism = max(
            1, (available - 10) // 3
        )  # 3 connections per parallel loader

        return {
            "ready_for_eod": ready,
            "pool_status": status["status"],
            "active_connections": status["active_connections"],
            "max_connections": status["max_connections"],
            "utilization_percent": pool_pct,
            "available_connections": available,
            "max_parallelism": max_parallelism,
            "recommendations": recommendations,
        }
