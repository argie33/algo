#!/usr/bin/env python3
"""
Shared loader utilities - consolidates duplicated functions across loaders.

Functions that were defined identically in 19+ loader files, now centralized here.
"""

import os
from utils.db_connection import get_db_connection
from typing import List
from pathlib import Path
import time
import threading

# Load .env for local development

# Cache for active symbols to reduce database load under parallelism
_symbols_cache = {}
_cache_lock = threading.Lock()
_CACHE_TTL_SECS = 300  # 5 minute cache


def get_active_symbols(max_symbols: int = None, timeout_secs: int = 120) -> List[str]:
    """Get list of active stock symbols from database with timeout protection.

    Used by: load_balance_sheet.py, loadbuyselldaily.py, load_cash_flow.py,
             load_income_statement.py, load_key_metrics.py, loadpricedaily.py,
             load_quality_metrics.py, and others

    Originally defined identically in 19 different files. Consolidated 2026-05-18.

    Args:
        max_symbols: Limit results to N symbols (default: None = all)
        timeout_secs: Timeout for database query (default: 120 seconds for parallel batch execution)
    """
    import signal
    import threading

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
    cache_key = 'all_symbols'
    with _cache_lock:
        if cache_key in _symbols_cache:
            cached_time, cached_symbols = _symbols_cache[cache_key]
            if time.time() - cached_time < _CACHE_TTL_SECS:
                symbols = cached_symbols
                if max_symbols and len(symbols) > max_symbols:
                    symbols = symbols[:max_symbols]
                return symbols

    try:
        result = {'symbols': None, 'error': None}

        def fetch_symbols():
            try:
                conn = get_db_connection(max_retries=2, timeout=10)
                try:
                    cur = conn.cursor()
                    cur.execute("SELECT symbol FROM stock_symbols ORDER BY symbol")
                    rows = cur.fetchall()
                    result['symbols'] = [row[0] for row in rows]
                finally:
                    cur.close()
                    conn.close()
            except Exception as e:
                result['error'] = e

        # Run in thread with timeout for Windows compatibility
        thread = threading.Thread(target=fetch_symbols, daemon=True)
        thread.start()
        thread.join(timeout=timeout_secs)

        if thread.is_alive():
            raise TimeoutError(f"get_active_symbols() exceeded {timeout_secs}s timeout")

        if result['error']:
            raise result['error']

        symbols = result['symbols'] or []

        # Cache the result
        with _cache_lock:
            _symbols_cache[cache_key] = (time.time(), symbols)

        # Limit to max_symbols if specified
        if max_symbols and len(symbols) > max_symbols:
            symbols = symbols[:max_symbols]

        return symbols
    finally:
        # Cancel alarm
        if old_handler is not None:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)


def _resolve_timeframe(cli_arg: str = None) -> str:
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


def _resolve_period(cli_arg: str = None) -> str:
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
