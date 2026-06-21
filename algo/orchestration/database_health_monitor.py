#!/usr/bin/env python3
"""Database Health Monitor - Database connectivity and health checks."""

import logging

import psycopg2

from utils.db import DatabaseContext


logger = logging.getLogger(__name__)

class DatabaseHealthMonitor:
    """Monitors database health and connectivity."""

    def check_connectivity(self) -> bool:
        """Test if database is reachable."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute("SELECT 1")
            return True
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.critical(f"[DB_HEALTH] Database unreachable: {e}")
            raise RuntimeError(f"Database connectivity failed: {e}") from e
