#!/usr/bin/env python3
"""
Database Connection Pool

Shared connection pool to prevent connection exhaustion.
PostgreSQL default max_connections=100. Without pooling, each module
creates new connections independently, exhausting the pool.

Usage:
    pool = get_db_pool()
    conn = pool.getconn()
    try:
        cur = conn.cursor()
        # use connection
    finally:
        pool.putconn(conn)
"""

from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import os
import psycopg2.pool
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
    }

# Global pool instance
_pool = None

def get_db_pool(minconn=2, maxconn=10):
    """Get or create the global connection pool.

    Args:
        minconn: Minimum connections to keep open
        maxconn: Maximum connections allowed

    Returns:
        SimpleConnectionPool instance
    """
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.SimpleConnectionPool(
            minconn, maxconn,
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            database=DB_CONFIG["database"],
        )
    return _pool

def close_pool():
    """Close all connections in the pool."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None

def set_serializable_isolation(conn):
    """Set SERIALIZABLE isolation level for critical transactional sections.

    Usage: Use for Phase 3 (position monitor) + Phase 4 (exit execution)
    to prevent race conditions where multiple transactions read/update same position.
    """
    cur = conn.cursor()
    try:
        cur.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        conn.commit()
    finally:
        cur.close()

def set_read_committed_isolation(conn):
    """Reset to default READ_COMMITTED isolation level."""
    cur = conn.cursor()
    try:
        cur.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
        conn.commit()
    finally:
        cur.close()
