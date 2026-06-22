#!/usr/bin/env python3
"""
Shared loader utilities - consolidates duplicated functions across loaders.

Functions that were defined identically in 19+ loader files, now centralized here.
"""

import logging
import os
import threading
import time

import psycopg2

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


def get_api_key(secret_name: str, env_var: str, default: str | None = None) -> str:
    """Fetch API key from AWS Secrets Manager with fallback to environment variable.

    Supports seamless Secrets Manager migration: tries Secrets Manager first,
    falls back to environment variable, then optional default.

    Args:
        secret_name: Name of secret in AWS Secrets Manager (e.g., 'algo-alpaca-key')
        env_var: Environment variable name for fallback (e.g., 'ALPACA_API_KEY')
        default: Default value if both Secrets Manager and env var are missing

    Returns:
        API key string, or None if not found
    """
    try:
        import boto3

        is_lambda = "AWS_LAMBDA_FUNCTION_NAME" in os.environ
        region = os.environ.get("AWS_REGION", "us-east-1")

        if is_lambda:
            try:
                client = boto3.client("secretsmanager", region_name=region)
                response = client.get_secret_value(SecretId=secret_name)
                key = response.get("SecretString")
                if key:
                    logger.debug(f"Fetched {secret_name} from Secrets Manager")
                    return key
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as sm_err:
                logger.debug(f"Secrets Manager fetch failed for {secret_name}: {sm_err}, falling back to env var")
    except ImportError:
        logger.debug("boto3 not available, using env var fallback")

    # Fallback: environment variable
    key = os.environ.get(env_var)
    if key:
        logger.debug(f"Using {env_var} from environment")
        return key

    # Final fallback: default value
    if default:
        logger.debug(f"Using default value for {secret_name}")
        return default

    logger.warning(f"Could not find {secret_name} in Secrets Manager or {env_var} in environment")
    return None


# Cache for active symbols to reduce database load under parallelism
_symbols_cache = {}
_cache_lock = threading.Lock()
_CACHE_TTL_SECS = 300  # 5 minute cache


def get_active_symbols(max_symbols: int | None = None, timeout_secs: int = 120) -> list[str]:
    """Get list of active symbols (stocks and ETFs) from database with timeout protection.

    Used by: load_balance_sheet.py, loadbuyselldaily.py, load_cash_flow.py,
             load_income_statement.py, load_key_metrics.py, loadpricedaily.py,
             load_quality_metrics.py, and others

    Originally defined identically in 19 different files. Consolidated 2026-05-18.
    FIXED 2026-06-07: Include ETFs (was filtering them out, breaking 95% validation)

    Args:
        max_symbols: Limit results to N symbols (default: None = all)
        timeout_secs: Timeout for database query (default: 120 seconds for parallel batch execution)
    """
    import signal

    def timeout_handler(signum, frame):
        raise TimeoutError(f"get_active_symbols() exceeded {timeout_secs}s timeout")

    # Set alarm signal only on Unix-like systems
    old_handler = None
    try:
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout_secs)
    except (AttributeError, ValueError):
        # signal.SIGALRM not available on Windows, use threading timeout instead
        pass

    # Check cache first to reduce database load under parallelism
    cache_key = "all_symbols"
    with _cache_lock:
        if cache_key in _symbols_cache:
            cached_time, cached_symbols = _symbols_cache[cache_key]
            if time.time() - cached_time < _CACHE_TTL_SECS:
                symbols = cached_symbols
                if max_symbols and len(symbols) > max_symbols:
                    symbols = symbols[:max_symbols]
                return symbols

    try:
        result = {"symbols": None, "error": None}

        def fetch_symbols():
            try:
                with DatabaseContext("read") as cur:
                    cur.execute("SELECT symbol FROM stock_symbols WHERE active = true ORDER BY symbol")
                    rows = cur.fetchall()
                    result["symbols"] = [row[0] for row in rows]
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                result["error"] = e

        # Run in thread with timeout for Windows compatibility
        thread = threading.Thread(target=fetch_symbols, daemon=True)
        thread.start()
        thread.join(timeout=timeout_secs)

        if thread.is_alive():
            raise TimeoutError(f"get_active_symbols() exceeded {timeout_secs}s timeout")

        if result["error"]:
            raise result["error"]  # pylint: disable=raising-bad-type

        symbols = result["symbols"] or []

        # Cache the result
        with _cache_lock:
            _symbols_cache[cache_key] = (time.time(), symbols)

        # Limit to max_symbols if specified
        if max_symbols and len(symbols) > max_symbols:
            symbols = symbols[:max_symbols]

        return symbols
    finally:
        # Cancel alarm (only on Unix/Linux where SIGALRM is available)
        if old_handler is not None:
            try:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
            except (AttributeError, ValueError):
                pass


def _resolve_timeframe(cli_arg: str | None = None) -> str:
    """Resolve timeframe from CLI arg or environment variable.

    Used by: loadbuyselldaily.py, loadpricedaily.py

    Priority:
    1. CLI argument (if provided)
    2. LOADER_TYPE environment variable (if contains "monthly" -> "monthly", else "weekly")
    """
    if cli_arg:
        return cli_arg
    loader_type = os.getenv("LOADER_TYPE", "")
    return "monthly" if "monthly" in loader_type else "weekly"


def _resolve_period(cli_arg: str | None = None) -> str:
    """Resolve period from CLI arg or environment variable.

    Used by: load_balance_sheet.py, load_cash_flow.py, load_income_statement.py

    Originally defined identically in 3 different files. Consolidated 2026-05-18.

    Priority:
    1. CLI argument (if provided)
    2. LOADER_PERIOD environment variable (default "quarterly")
    """
    if cli_arg:
        return cli_arg
    return os.getenv("LOADER_PERIOD", "quarterly")


# =======================
# Database Query Helpers
# =======================
# These eliminate 169+ repetitions of `with DatabaseContext("read") as cur:` pattern

def execute_query(query: str, params=None, role: str = "read", timeout: int = 30):
    """Execute a query and return all results.

    Eliminates: with DatabaseContext(role) as cur: cur.execute(...); cur.fetchall()
    Pattern found in 169 locations across 78 files.

    Args:
        query: SQL query string
        params: Query parameters (if any)
        role: 'read' or 'write'
        timeout: Connection timeout in seconds

    Returns:
        List of row tuples/dicts (depends on cursor_factory)
    """
    with DatabaseContext(role, timeout=timeout) as cur:
        cur.execute(query, params)
        return cur.fetchall()


def fetch_one(query: str, params=None, role: str = "read", timeout: int = 30):
    """Execute a query and return single result.

    Eliminates: with DatabaseContext(role) as cur: cur.execute(...); cur.fetchone()

    Args:
        query: SQL query string
        params: Query parameters (if any)
        role: 'read' or 'write'
        timeout: Connection timeout in seconds

    Returns:
        Single row tuple/dict or None
    """
    with DatabaseContext(role, timeout=timeout) as cur:
        cur.execute(query, params)
        return cur.fetchone()


def fetch_latest(
    table: str,
    order_by_col: str,
    where_clause: str | None = None,
    params=None,
    timeout: int = 30,
):
    """Fetch latest row from a table ordered by a specific column.

    Common pattern: SELECT ... FROM table [WHERE ...] ORDER BY col DESC LIMIT 1

    Args:
        table: Table name
        order_by_col: Column to order by (DESC)
        where_clause: Optional WHERE clause (without 'WHERE' keyword)
        params: Parameters for WHERE clause
        timeout: Connection timeout in seconds

    Returns:
        Single row dict or None
    """
    where_sql = f" WHERE {where_clause}" if where_clause else ""
    query = f"SELECT * FROM {table}{where_sql} ORDER BY {order_by_col} DESC LIMIT 1"
    return fetch_one(query, params, timeout=timeout)


def fetch_all(
    table: str,
    where_clause: str | None = None,
    params=None,
    order_by: str | None = None,
    timeout: int = 30,
):
    """Fetch all rows matching optional WHERE clause.

    Common pattern: SELECT ... FROM table [WHERE ...] [ORDER BY ...]

    Args:
        table: Table name
        where_clause: Optional WHERE clause (without 'WHERE' keyword)
        params: Parameters for WHERE clause
        order_by: Optional ORDER BY clause (without 'ORDER BY' keyword)
        timeout: Connection timeout in seconds

    Returns:
        List of row dicts
    """
    where_sql = f" WHERE {where_clause}" if where_clause else ""
    order_sql = f" ORDER BY {order_by}" if order_by else ""
    query = f"SELECT * FROM {table}{where_sql}{order_sql}"
    return execute_query(query, params, timeout=timeout)


def count_rows(
    table: str,
    where_clause: str | None = None,
    params=None,
    timeout: int = 30,
) -> int:
    """Count rows in a table matching optional WHERE clause.

    Args:
        table: Table name
        where_clause: Optional WHERE clause (without 'WHERE' keyword)
        params: Parameters for WHERE clause
        timeout: Connection timeout in seconds

    Returns:
        Row count
    """
    where_sql = f" WHERE {where_clause}" if where_clause else ""
    query = f"SELECT COUNT(*) FROM {table}{where_sql}"
    result = fetch_one(query, params, timeout=timeout)
    return result[0] if result else 0


# =======================
# Circuit Breaker Factory
# =======================
# Eliminates repetitive CircuitBreaker initialization patterns

def create_circuit_breaker(
    name: str,
    importance_name: str = "OPTIONAL",
    failure_threshold: int = 3,
    recovery_timeout_sec: int = 300,
):
    """Factory for common CircuitBreaker patterns.

    Eliminates: Repeated CircuitBreaker(name=..., importance=DataImportance.X) across loaders

    Common patterns:
    - VIX/enrichment data: failure_threshold=3, recovery_timeout=300, importance=OPTIONAL
    - API data (FRED, etc): failure_threshold=3, recovery_timeout=300, importance=REQUIRED
    - Core prices: failure_threshold=2, recovery_timeout=600, importance=CRITICAL

    Args:
        name: Circuit breaker identifier (e.g., "yfinance_vix")
        importance_name: "CRITICAL", "REQUIRED", or "OPTIONAL"
        failure_threshold: Number of failures before opening circuit
        recovery_timeout_sec: Seconds to wait before half-open recovery attempt

    Returns:
        Configured CircuitBreaker instance
    """
    from utils.infrastructure.circuit_breaker import CircuitBreaker, DataImportance

    importance_map = {
        "CRITICAL": DataImportance.CRITICAL,
        "REQUIRED": DataImportance.REQUIRED,
        "OPTIONAL": DataImportance.OPTIONAL,
    }
    importance = importance_map.get(importance_name, DataImportance.OPTIONAL)

    return CircuitBreaker(
        name=name,
        failure_threshold=failure_threshold,
        recovery_timeout_sec=recovery_timeout_sec,
        importance=importance,
    )
