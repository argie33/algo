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

import os
import psycopg2.pool
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
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
